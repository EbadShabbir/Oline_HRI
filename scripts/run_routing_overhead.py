"""Frozen, serialized four-turn routing-overhead collection and diagnostic replay."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import signal
import shlex
import subprocess
import sys
from time import monotonic, monotonic_ns, sleep

from oline_hri.config import load_config
from oline_hri.conversation import Conversation
from oline_hri.embedding import BgeOnnxEmbedder, REQUIRED_ASSET_SHA256
from oline_hri.evaluation_model_pairs import (
    SafetyGateError, _DurableJsonlWriter, _StreamingSafetyMonitor, _canonical_bytes,
    _http_json, _installed_models, _model_metadata, _new_private_directory,
    _resident_models, _write_new_json,
)
from oline_hri.evaluation_systems import single_model_config
from oline_hri.ollama import ChatMessage, ChatResult
from oline_hri.routing import RouteDecision, RoutingResult
from oline_hri.timing import TraceRecorder, trace_span
from post_memory_device_guard import capture_safety_snapshot, require_ready, stage2_limits, policy_dict
from run_complete_system import RecordingRetriever, RecordingRouter, materialize_seed, load_workload
from run_pair_remediation_validation import GuardedSampler
from run_post_memory_comparison import (
    ComparisonClient, ComparisonBackend, cleanup_owned, make_router, package_versions,
)

ROOT = Path(__file__).resolve().parents[1]
SMALL, LARGE = "qwen3:0.6b", "qwen3:1.7b"
PROFILE = "routing_overhead_v1"
ORDERS = (("small", "large", "adaptive"), ("large", "adaptive", "small"),
          ("adaptive", "small", "large"))
LOCK = Path("/tmp/clara-jetson-inference.lock")


def utc():
    return datetime.now(timezone.utc).isoformat()


def source_hashes():
    paths = list((ROOT / "src/oline_hri").glob("*.py"))
    paths += [ROOT / "scripts" / name for name in (
        "run_routing_overhead.py", "analyze_routing_overhead.py",
        "run_post_memory_comparison.py", "post_memory_device_guard.py",
        "run_complete_system.py", "run_pair_remediation_validation.py",
        "run_arc_capability.py", "complete_system_device_guard.py",
    )]
    paths += list((ROOT / "tests").glob("test_routing_overhead*.py"))
    paths.append(ROOT / "tests/test_routing_timing.py")
    paths += [ROOT / "evaluation/routing_overhead_20260912" / name for name in
              ("continue_collection.py", "analyze_continued.py")]
    paths.append(ROOT / "config/default.json")
    return {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def validate_workload(workload):
    sequences = workload["sequences"]
    if len(sequences) != 12 or len({s["id"] for s in sequences}) != 12:
        raise ValueError("exactly 12 unique sequences required")
    if any(sum(s["pattern"] == p for s in sequences) != 3 for p in ("EEEE", "DDDD", "EDED", "DDEE")):
        raise ValueError("three variants of every pattern required")
    ids = [i for s in sequences for i in s["case_ids"]]
    if any(len(s["case_ids"]) != 4 for s in sequences) or len(ids) != len(set(ids)):
        raise ValueError("four distinct turns in each sequence required")
    if set(ids) != {c["id"] for c in workload["execution_cases"]}:
        raise ValueError("sequence and case IDs differ")
    if workload.get("initial_history") != []:
        raise ValueError("this freeze requires empty initial history")


def config_for(arm):
    config = load_config()
    config = replace(config, generation=replace(config.generation, context_length=2048,
                     max_output_tokens=192, temperature=0.0, thinking=False))
    if arm in {"small", "large"}:
        config = single_model_config(config, SMALL if arm == "small" else LARGE)
    return config


def process_audit():
    """Archive host processes and refuse known competing inference clients."""
    result = subprocess.run(["ps", "-eo", "pid,ppid,args"], text=True, capture_output=True, check=True)
    conflicts = []
    rows = [line.strip().split(None, 2) for line in result.stdout.splitlines()[1:]]
    parents = {int(p[0]): int(p[1]) for p in rows if len(p) == 3}
    ancestors, current = set(), os.getpid()
    while current and current not in ancestors:
        ancestors.add(current)
        current = parents.get(current, 0)
    for line in result.stdout.splitlines()[1:]:
        parts = line.strip().split(None, 2)
        if len(parts) != 3:
            continue
        command = parts[2]
        # Never treat this harness or the Ollama server/runner as another client.
        if int(parts[0]) in ancestors or "codex" in command:
            continue
        if (("python" in command and any(x in command for x in
              ("scripts/run_", "scripts/check_", "run_routing_overhead.py", "oline_hri chat")))
                or "ollama run " in command or "whisper-cli" in command):
            conflicts.append(line)
    connections = subprocess.run(["ss", "-tnp"], text=True, capture_output=True, check=False)
    return {"captured_at": utc(), "processes": result.stdout,
            "tcp_connections": connections.stdout, "conflicts": conflicts}


def server_configuration():
    result = subprocess.run(["systemctl", "show", "ollama", "--property=Environment", "--value"],
                            text=True, capture_output=True, check=False)
    allowed = {"OLLAMA_NUM_PARALLEL", "OLLAMA_MAX_LOADED_MODELS", "OLLAMA_HOST",
               "OLLAMA_KEEP_ALIVE", "OLLAMA_FLASH_ATTENTION", "OLLAMA_CONTEXT_LENGTH",
               "OLLAMA_KV_CACHE_TYPE", "OLLAMA_SCHED_SPREAD", "CUDA_VISIBLE_DEVICES"}
    selected = {item.split("=", 1)[0]: item.split("=", 1)[1]
                for item in shlex.split(result.stdout) if "=" in item and item.split("=", 1)[0] in allowed}
    return {"service_query_exit_code": result.returncode, "selected_environment": selected,
            "swap_topology": Path("/proc/swaps").read_text()}


@contextmanager
def exclusive_inference():
    with LOCK.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SafetyGateError("another CLARA collection holds the inference lock") from None
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()} {utc()} {PROFILE}\n")
        handle.flush()
        yield handle.fileno()


def verify_eviction(model):
    observations = []
    deadline = monotonic() + 30
    while True:
        state = list(_resident_models())
        observations.append({"monotonic_ns": monotonic_ns(), "models": state})
        if not any(m.get("name", m.get("model")) == model for m in state):
            return {"verified_absent": model, "polls": observations}
        if monotonic() >= deadline:
            raise SafetyGateError("unload acknowledged but model eviction was not verified")
        sleep(.02)


def route_from_record(value):
    result = dict(value)
    result["decision"] = RouteDecision(**result["decision"])
    for key in ("memory_required_generation", "model_size_generation"):
        if result.get(key) is not None:
            result[key] = ChatResult(**result[key])
    return RoutingResult(**result)


class ReplayRouter:
    """Return previously observed route metadata; never invoke a selector."""
    def __init__(self):
        self.original = None

    def route(self, text, *, history=()):
        with trace_span("routing_bypass", diagnostic=True, reused_selector_metadata=True):
            return route_from_record(self.original["route"])


class OverheadClient(ComparisonClient):
    expected_bodies = None

    def _post_json(self, endpoint, body, **kwargs):
        if self.expected_bodies is not None and endpoint == "/api/chat":
            if not self.expected_bodies or body != self.expected_bodies.pop(0):
                raise SafetyGateError("diagnostic replay generation HTTP body differs from adaptive trace")
        return super()._post_json(endpoint, body, **kwargs)


class OverheadBackend(ComparisonBackend):
    expected_requests = None

    def chat(self, model, messages, **kwargs):
        if self.expected_requests is not None:
            if "speech" not in (kwargs.get("response_format") or {}).get("properties", {}):
                self.transport_error = SafetyGateError("selection call attempted in diagnostic replay")
                raise self.transport_error
            actual = {"model": model, "messages": [m.to_dict() for m in messages],
                      "response_format": kwargs.get("response_format")}
            if not self.expected_requests or actual != self.expected_requests.pop(0):
                self.transport_error = SafetyGateError("diagnostic replay generation arguments differ from adaptive trace")
                raise self.transport_error
        try:
            return super().chat(model, messages, **kwargs)
        finally:
            with trace_span("residency_audit", phase="after_backend_call", model=model) as placement:
                placement["models"] = list(_resident_models())


def replay_expectations(record):
    requests = [{"model": c["requested_model"], "messages": c["messages"],
                 "response_format": c["response_format"]}
                for c in record["calls"] if c["purpose"] == "generation"]
    bodies = [h["body"] for h in record["http_calls"] if h["endpoint"] == "/api/chat"
              and "speech" in h["body"].get("format", {}).get("properties", {})]
    if len(requests) != len(bodies):
        raise ValueError("adaptive trace has unmatched generation requests")
    return requests, bodies


def collect_turns(cases, sequence, arm, repetition, conversation, router, backend,
                  retriever, writer, event_writer, records, replay=None):
    for index, case in enumerate(cases, 1):
        backend.transport_error = None
        router.result, router.wall_ns = None, 0
        if replay is not None:
            original = replay[index - 1]
            if original["id"] != case["id"] or not original.get("route"):
                raise ValueError("adaptive trace is not replayable")
            router.delegate.original = original
            conversation._messages = [ChatMessage(**m) for m in original["history_before"]]
            backend.expected_requests, backend.client.expected_bodies = replay_expectations(original)
        call_start, http_start, retrieval_start = len(backend.calls), len(backend.client.http_calls), len(retriever.calls)
        record = {**case, "sequence_id": sequence["id"], "pattern": sequence["pattern"],
                  "workload_label": sequence["pattern"][index-1], "arm": arm,
                  "repetition": repetition, "index": index, "status": "error",
                  "history_before": [m.to_dict() for m in conversation.messages],
                  "resident_hint_before": backend.resident_model,
                  "api_ps_before": None,
                  "diagnostic_replay": replay is not None}
        if replay is not None:
            record["replayed_from"] = {"sequence_id": sequence["id"], "repetition": repetition,
                                        "index": index, "arm": "adaptive"}
        recorder = TraceRecorder(sink=lambda event: event_writer.write(
            {"sequence_id": sequence["id"], "arm": arm, "repetition": repetition,
             "index": index, **event}), eviction_verifier=verify_eviction)
        # Attempt markers survive a kill before the completed observation exists.
        event_writer.write({"kind": "turn_attempt", **record, "monotonic_ns": monotonic_ns()})
        # This is admission/audit work, outside complete request latency.
        try:
            backend.check()
            record["api_ps_before"] = list(_resident_models())
        except BaseException as error:
            record.update(status="interrupted", error=type(error).__name__, message=str(error),
                          phase="before_request", request_started=False, wall_ns=None, events=[], calls=[], http_calls=[],
                          route=None, api_ps_after=None)
            writer.write(record)
            records.append(record)
            raise
        started, fatal = monotonic_ns(), None
        try:
            with recorder.activate():
                reply = conversation.send(case["prompt"])
            record.update(status="ok", response=reply.response.to_dict(),
                          generation=asdict(reply.generation), memory=reply.memory_diagnostics.to_dict(),
                          answer_constraint=reply.answer_constraint, generation_policy=reply.generation_policy,
                          response_transform=reply.response_transform, reference_ids=list(reply.reference_ids),
                          fallback_from_model=reply.fallback_from_model)
            if replay is not None and (backend.expected_requests or backend.client.expected_bodies):
                raise SafetyGateError("diagnostic replay did not consume every adaptive generation request")
        except BaseException as error:
            record.update(error=type(error).__name__, message=str(error), status="error")
            if isinstance(error, (KeyboardInterrupt, SystemExit, SafetyGateError)):
                fatal = error
            elif backend.transport_error is not None:
                fatal = backend.transport_error
        finished = monotonic_ns()
        record.update(started_monotonic_ns=started, finished_monotonic_ns=finished,
                      wall_ns=finished-started, events=recorder.events,
                      calls=backend.calls[call_start:], http_calls=backend.client.http_calls[http_start:],
                      retrieval_calls=retriever.calls[retrieval_start:], routing_wall_ns=router.wall_ns,
                      route=asdict(router.result) if router.result is not None else None,
                      resident_hint_after=backend.resident_model,
                      history_after=[m.to_dict() for m in conversation.messages])
        try:
            backend.check()
        except BaseException as error:
            record["post_guard_error"] = {"type": type(error).__name__, "message": str(error)}
            fatal = error
        try:
            record["api_ps_after"] = list(_resident_models())
        except BaseException as error:
            record["api_ps_after"] = None
            record["post_snapshot_error"] = {"type": type(error).__name__, "message": str(error)}
            fatal = error
        if fatal is not None:
            record["status"] = "interrupted"
        writer.write(record)
        records.append(record)
        print(f"{sequence['id']} r{repetition} {arm} {index}/4 {record['status']} "
              f"{record['wall_ns']/1e9:.3f}s {record.get('generation',{}).get('model')}", flush=True)
        if fatal is not None:
            raise fatal


def check_freeze(args):
    workload, frozen = load_workload(args.workload), json.loads(args.freeze.read_text())
    validate_workload(workload)
    if frozen["profile_id"] != PROFILE or source_hashes() != frozen["source_sha256"]:
        raise ValueError("source or profile differs from freeze")
    if sha256(args.workload.read_bytes()).hexdigest() != frozen["workload_sha256"]:
        raise ValueError("workload differs from freeze")
    if (config_for("adaptive").to_dict() != frozen["config"] or package_versions() != frozen["packages"]
            or policy_dict() != frozen["device_policy"] or sys.version != frozen["python"]):
        raise ValueError("configuration, runtime or guard differs from freeze")
    installed = _installed_models()
    if any(_model_metadata(m, installed) != frozen["models"][m] for m in (SMALL, LARGE)):
        raise ValueError("installed model digests or metadata differ from freeze")
    if _http_json("/api/version") != frozen["ollama_version"]:
        raise ValueError("Ollama version differs from freeze")
    return workload, frozen


def session(args):
    if getattr(args, "lock_fd", None) is None:
        with exclusive_inference() as descriptor:
            args.lock_fd = descriptor
            return session(args)
    if os.fstat(args.lock_fd).st_ino != LOCK.stat().st_ino:
        raise SafetyGateError("invalid inherited inference lease")
    fcntl.flock(args.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    workload, frozen = check_freeze(args)
    sequence = next(s for s in workload["sequences"] if s["id"] == args.sequence)
    cases = {c["id"]: c for c in workload["execution_cases"]}
    config = config_for(args.arm)
    directory = _new_private_directory(args.output_dir.absolute())
    replay = None
    if args.arm == "replay":
        replay = [json.loads(line) for line in args.replay.read_text().splitlines()]
        if len(replay) != 4:
            raise ValueError("replay requires a complete four-turn adaptive attempt")
    _write_new_json(directory / "manifest.json", {
        "profile_id": PROFILE, "created_at": utc(), "sequence_id": sequence["id"],
        "pattern": sequence["pattern"], "arm": args.arm, "repetition": args.repetition,
        "sequence": sequence, "config": config.to_dict(), "generation_seed": 42,
        "freeze_sha256": sha256(args.freeze.read_bytes()).hexdigest(),
        "persistent_history": True, "persistent_router_and_residency": True,
        "cold_state": "new process and BGE instance; verified no Ollama model; OS page caches retained",
        "replay_source": str(args.replay) if replay is not None else None,
        "replay_source_sha256": sha256(args.replay.read_bytes()).hexdigest() if replay is not None else None,
    })
    records, cleanup_errors = [], []
    failure, status, startup_ns, cleanup_ns = None, "incomplete", 0, 0
    sequence_start = sequence_end = None
    admitted = False
    client = backend = sampler = monitor = None
    start = None
    envelope_start = monotonic_ns()
    with stage2_limits():
        try:
            audit = process_audit()
            _write_new_json(directory / "process_audit.json", audit)
            if audit["conflicts"]:
                raise SafetyGateError("competing experiment detected")
            start = capture_safety_snapshot()
            _write_new_json(directory / "start.json", start)
            require_ready(start)
            admitted = True
            with _DurableJsonlWriter(directory / "http_calls.jsonl") as http_writer, \
                 _DurableJsonlWriter(directory / "events.jsonl") as event_writer, \
                 _DurableJsonlWriter(directory / "telemetry.jsonl") as telemetry:
                client = OverheadClient(config.ollama, config.generation, http_writer=http_writer,
                                        retain_large_model=True)
                monitor = _StreamingSafetyMonitor(telemetry)
                sampler = GuardedSampler(monitor)
                allowed = (SMALL,) if args.arm == "small" else (LARGE,) if args.arm == "large" else (SMALL, LARGE)
                backend = OverheadBackend(client, start, sampler, allowed)
                with sampler:
                    try:
                        deadline = monotonic() + 5
                        while not sampler.samples and monotonic() < deadline:
                            sleep(.05)
                        if not sampler.samples:
                            raise SafetyGateError("initial telemetry unavailable")
                        backend.check()
                        setup_start = monotonic_ns()
                        sequence_start = setup_start
                        event_writer.write({"kind": "startup_begin", "monotonic_ns": setup_start})
                        embedder = BgeOnnxEmbedder(config.embedding.model_directory, config.embedding.intra_op_threads)
                        store, memory_events = materialize_seed(workload["memory_seed"], directory / "memory.sqlite3", embedder)
                        retriever = RecordingRetriever(store)
                        router = RecordingRouter(ReplayRouter() if args.arm == "replay" else
                                                 make_router(backend, "cascade" if args.arm == "adaptive" else args.arm))
                        conversation = Conversation(
                            backend, system_prompt=config.conversation.system_prompt,
                            router=router, retriever=retriever, small_model=SMALL,
                            general_large_model=LARGE, large_model=LARGE,
                            context_length=2048, max_output_tokens=192,
                            fixed_generator_model=SMALL if args.arm == "small" else LARGE if args.arm == "large" else None,
                        )
                        startup_ns = monotonic_ns() - setup_start
                        snapshot = [m.to_dict() for m in store.list_memories(include_inactive=True)]
                        _write_new_json(directory / "startup.json", {
                            "start_ns": setup_start, "end_ns": setup_start+startup_ns, "wall_ns": startup_ns,
                            "events": memory_events, "memory_snapshot": snapshot,
                            "memory_snapshot_sha256": sha256(_canonical_bytes(snapshot)).hexdigest(),
                            "embedding_placement": "CPUExecutionProvider, 2 intra-op threads",
                            "embedding_asset_sha256": dict(REQUIRED_ASSET_SHA256),
                            "model_startup_accounting": "first backend load is nested in first request; never add it again",
                        })
                        with _DurableJsonlWriter(directory / "observations.jsonl") as writer:
                            collect_turns([cases[i] for i in sequence["case_ids"]], sequence,
                                          args.arm, args.repetition, conversation, router, backend,
                                          retriever, writer, event_writer, records, replay)
                        status = "complete" if all(r["status"] == "ok" for r in records) else "complete_with_errors"
                    finally:
                        sequence_end = monotonic_ns()
                        cleanup_start = monotonic_ns()
                        cleanup_trace = TraceRecorder(sink=lambda e: event_writer.write({"index": "cleanup", **e}),
                                                      eviction_verifier=verify_eviction)
                        with cleanup_trace.activate():
                            cleanup_errors.extend(cleanup_owned(client, backend))
                        cleanup_ns = monotonic_ns() - cleanup_start
                        _write_new_json(directory / "cleanup.json", {"wall_ns": cleanup_ns,
                                        "events": cleanup_trace.events, "errors": cleanup_errors})
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
            status = "blocked_preflight" if not admitted else "interrupted"
        finally:
            if sampler is not None:
                _write_new_json(directory / "telemetry_summary.json", sampler.summary())
            try:
                finish = capture_safety_snapshot()
                if admitted and (finish["resident_models"] or finish["fan_pwm"] <= 0 or
                        any(finish[k] != start[k] for k in ("boot_id", "thermal_trip_events", "power_mode")) or
                        finish["memory"]["swap_total_kib"] != start["memory"]["swap_total_kib"]):
                    cleanup_errors.append("final host/residency invariants changed")
            except BaseException as error:
                finish = {"snapshot_error": type(error).__name__, "message": str(error)}
                cleanup_errors.append("final snapshot unavailable")
            unchanged = source_hashes() == frozen["source_sha256"]
            if not unchanged:
                cleanup_errors.append("source changed during collection")
            if cleanup_errors:
                status = "cleanup_failed"
            request_total = sum(r.get("wall_ns") or 0 for r in records)
            sequence_total = sequence_end-sequence_start if sequence_start is not None and sequence_end is not None else 0
            _write_new_json(directory / "finish.json", {
                **finish, "status": status, "failure": failure, "admitted": admitted,
                "arm": args.arm, "repetition": args.repetition, "sequence_id": sequence["id"],
                "pattern": sequence["pattern"], "attempted": len(records), "planned": 4,
                "startup_ns": startup_ns, "request_total_ns": request_total,
                "sequence_total_ns": sequence_total,
                "request_plus_startup_ns": startup_ns+request_total,
                "sequence_gaps_ns": sequence_total-startup_ns-request_total,
                "sequence_start_ns": sequence_start, "sequence_end_ns": sequence_end,
                "envelope_ns": monotonic_ns()-envelope_start, "cleanup_ns": cleanup_ns,
                "cleanup_errors": cleanup_errors, "source_unchanged": unchanged,
                "guard_violation": monitor.violation if monitor is not None else None,
            })
    print(f"SEQUENCE FINISHED {directory.name}: {status}", flush=True)
    return 0 if status in {"complete", "complete_with_errors"} else 1


def freeze(args):
    workload = load_workload(args.workload)
    validate_workload(workload)
    validation = json.loads(args.validation.read_text())
    if validation["exit_code"] or validation["failures"] or validation["errors"]:
        raise ValueError("successful offline validation required")
    hashes = source_hashes()
    if hashes != validation["source_sha256"]:
        raise ValueError("source changed since offline validation")
    config = config_for("adaptive")
    for rel, expected in REQUIRED_ASSET_SHA256.items():
        if sha256((Path(config.embedding.model_directory).expanduser()/rel).read_bytes()).hexdigest() != expected:
            raise ValueError("embedding asset changed")
    installed = _installed_models()
    audit = process_audit()
    if audit["conflicts"]:
        raise SafetyGateError("competing experiment detected")
    value = {
        "schema_version": 1, "profile_id": PROFILE, "created_at": utc(),
        "source_sha256": hashes, "workload_sha256": sha256(args.workload.read_bytes()).hexdigest(),
        "protocol_sha256": sha256(args.protocol.read_bytes()).hexdigest(),
        "validation_sha256": sha256(args.validation.read_bytes()).hexdigest(),
        "models": {m: _model_metadata(m, installed) for m in (SMALL, LARGE)},
        "ollama_version": _http_json("/api/version"), "config": config.to_dict(),
        "generation": asdict(config.generation), "generation_seed": 42,
        "embedding_asset_sha256": dict(REQUIRED_ASSET_SHA256),
        "packages": package_versions(), "python": sys.version, "hardware": platform.uname()._asdict(),
        "device_policy": policy_dict(), "snapshot": capture_safety_snapshot(), "process_audit": audit,
        "server_configuration": server_configuration(),
        "arm_orders": ORDERS, "diagnostic_replay_order": "after each matched three-arm block",
        "sequences": 12, "turns_per_sequence": 4, "repetitions": 3,
        "main_attempts": 432, "diagnostic_attempts": 144, "no_inference_during_freeze": True,
    }
    directory = _new_private_directory(args.output_dir.absolute())
    for rel in hashes:
        dest = directory / "source" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT/rel).read_bytes())
    for name, path in (("workload.json", args.workload), ("protocol.md", args.protocol),
                       ("offline_validation.json", args.validation)):
        (directory/name).write_bytes(path.read_bytes())
    if source_hashes() != hashes:
        raise ValueError("source changed during archive")
    _write_new_json(directory / "freeze.json", value)
    print(f"FROZEN {directory}; zero inference", flush=True)
    return 0


def slots(workload):
    for rep, order in enumerate(ORDERS, 1):
        for sequence in workload["sequences"]:
            for arm in (*order, "replay"):
                yield sequence["id"], rep, arm


def batch(args):
    workload, frozen = check_freeze(args)
    directory = _new_private_directory(args.output_dir.absolute())
    planned = list(slots(workload))
    _write_new_json(directory / "batch_plan.json", {"created_at": utc(), "slots": planned,
                    "main_attempts": 432, "diagnostic_attempts": 144,
                    "cold_wait_seconds": 600, "scheduler_temperature_target_c": 54.0,
                    "freeze_sha256": sha256(args.freeze.read_bytes()).hexdigest()})
    completed, status, failure = [], "incomplete", None
    baseline = None
    try:
        with exclusive_inference() as lease, _DurableJsonlWriter(directory / "scheduler.jsonl") as scheduler:
            baseline = capture_safety_snapshot()
            _write_new_json(directory / "before.json", baseline)
            for seq, rep, arm in planned:
                name = f"{seq}_r{rep}_{arm}"
                deadline = monotonic()+600
                while True:
                    state, audit = capture_safety_snapshot(), process_audit()
                    scheduler.write({"kind": "preflight", "slot": name, "snapshot": state, "audit": audit})
                    if audit["conflicts"]:
                        raise SafetyGateError("competing experiment detected")
                    if any(state[k] != baseline[k] for k in ("boot_id", "thermal_trip_events", "power_mode")):
                        raise SafetyGateError("host invariants changed")
                    try:
                        with stage2_limits():
                            require_ready(state)
                        if max(state["temperatures_c"].values()) >= 54:
                            raise SafetyGateError("scheduler cooling target below 54 C")
                        break
                    except SafetyGateError as error:
                        scheduler.write({"kind": "wait", "slot": name, "reason": str(error), "at": utc()})
                        if state["resident_models"] or monotonic() >= deadline:
                            raise
                        print(f"COOLING {name}: {error}", flush=True)
                        sleep(10)
                command = [sys.executable, str(Path(__file__).resolve()), "session",
                           "--workload", str(args.workload.resolve()), "--freeze", str(args.freeze.resolve()),
                           "--output-dir", str(directory/name), "--sequence", seq,
                           "--repetition", str(rep), "--arm", arm, "--lock-fd", str(lease)]
                if arm == "replay":
                    command += ["--replay", str(directory/f"{seq}_r{rep}_adaptive"/"observations.jsonl")]
                scheduler.write({"kind": "launch", "slot": name, "command": command, "at": utc()})
                print(f"SESSION {len(completed)+1}/{len(planned)} {name}", flush=True)
                result = subprocess.run(command, check=False, pass_fds=(lease,))
                completed.append({"slot": name, "exit_code": result.returncode})
                if result.returncode:
                    raise RuntimeError(f"{name} ended with {result.returncode}; preserved without tail stitching")
            check_freeze(args)
            status = "complete"
    except BaseException as error:
        status, failure = "interrupted", {"type": type(error).__name__, "message": str(error)}
    finally:
        try:
            final = capture_safety_snapshot()
        except BaseException as error:
            final = {"error": type(error).__name__, "message": str(error)}
        _write_new_json(directory / "batch_finish.json", {"status": status, "failure": failure,
                        "completed": completed, "planned": len(planned), "snapshot": final,
                        "source_unchanged": source_hashes() == frozen["source_sha256"],
                        "server_configuration": server_configuration()})
    return 0 if status == "complete" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "run", "session"))
    parser.add_argument("--workload", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--freeze", type=Path)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--validation", type=Path)
    parser.add_argument("--sequence")
    parser.add_argument("--repetition", type=int, choices=(1,2,3))
    parser.add_argument("--arm", choices=("small", "large", "adaptive", "replay"))
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--lock-fd", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt("SIGTERM")))
    return {"freeze": freeze, "run": batch, "session": session}[args.mode](args)


if __name__ == "__main__":
    raise SystemExit(main())
