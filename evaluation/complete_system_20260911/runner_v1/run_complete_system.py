"""One frozen Stage 2 text-system session; never reads answer gold during execution."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import sys
from time import perf_counter, perf_counter_ns, sleep

from oline_hri.config import load_config
from oline_hri.conversation import Conversation
from oline_hri.embedding import BgeOnnxEmbedder, REQUIRED_ASSET_SHA256
from oline_hri.evaluation_model_pairs import (
    SafetyGateError, _DurableJsonlWriter, _StreamingSafetyMonitor,
    _canonical_bytes, _force_unload, _http_json, _installed_models,
    _model_metadata, _new_private_directory, _resident_models, _write_new_json,
    capture_safety_snapshot,
)
from oline_hri.evaluation_systems import MemoryOnlyRouter, single_model_config
from oline_hri.memory import MemoryStore
from oline_hri.ollama import OllamaClient, OllamaError
from oline_hri.retrieval import HybridRetriever
from oline_hri.routing import ConversationRouter
from run_arc_capability import distribution
from run_pair_remediation_validation import GuardedBackend, GuardedSampler
from complete_system_device_guard import stage2_limits, require_ready, policy_dict


ROOT = Path(__file__).resolve().parents[1]
SMALL, LARGE = "qwen3:0.6b", "qwen3:1.7b"
ARM_ORDERS = (("small", "large", "cascade"),
              ("large", "cascade", "small"),
              ("cascade", "small", "large"))


def load_workload(path):
    value = json.loads(path.read_text())
    cases = value["execution_cases"]
    ids = [case["id"] for case in cases]
    if not cases or len(ids) != len(set(ids)) or set(ids) != set(value["rubrics"]):
        raise ValueError("workload needs unique cases and exactly matched rubrics")
    for case in cases:
        if set(case) != {"id", "stratum", "scenario_id", "prompt"}:
            raise ValueError("execution case contains unexpected fields")
        if not isinstance(case["prompt"], str) or not 0 < len(case["prompt"]) <= 1000:
            raise ValueError("invalid prompt length")
    return value


def materialize_seed(seed, path, embedder=None):
    """Replay confirmed fictional events via the real lifecycle APIs."""
    if path.exists():
        raise ValueError("refusing to overwrite a memory database")
    clock_value = [None]
    generated = iter(e["memory_id"] for e in seed["events"]
                     if e["operation"] in {"remember", "correct"})
    store = MemoryStore(path, profile_id=seed["profile_id"],
                        clock=lambda: clock_value[0],
                        memory_id_factory=lambda: next(generated), embedder=embedder,
                        retention_days=seed.get("retention_days", 7))
    event_log = []
    for event in seed["events"]:
        clock_value[0] = datetime.fromisoformat(event["at"].replace("Z", "+00:00"))
        if event["operation"] == "remember":
            item = store.remember(event["canonical_text"], kind=event["kind"],
                                  source_turn_id=event["id"],
                                  **{key: event[key] for key in
                                     ("event_time", "valid_until", "retention_until") if key in event})
            if item.id != event["memory_id"]:
                raise ValueError("memory ID replay diverged")
            result = item.to_dict()
        elif event["operation"] == "correct":
            item = store.correct(event["target_id"], event["canonical_text"])
            if item.id != event["memory_id"]:
                raise ValueError("correction ID replay diverged")
            result = item.to_dict()
        elif event["operation"] == "forget":
            result = list(store.forget(event["target_id"]))
        else:
            raise ValueError("unknown memory event operation")
        event_log.append({"event_id": event["id"], "operation": event["operation"], "result": result})
    clock_value[0] = datetime.fromisoformat(seed["evaluation_at"].replace("Z", "+00:00"))
    if next(generated, None) is not None:
        raise ValueError("memory ID replay incomplete")
    return store, event_log


class RecordingRetriever:
    def __init__(self, store):
        self.delegate = HybridRetriever(store)
        self.calls = []

    def retrieve(self, query, *, limit=3):
        started = perf_counter_ns()
        record = {"limit": limit}
        try:
            matches = self.delegate.retrieve(query, limit=limit)
            record["matches"] = [{"memory": match.memory.to_dict(),
                                  "fused_score": match.fused_score} for match in matches]
            return matches
        except BaseException as error:
            record["error"] = type(error).__name__
            raise
        finally:
            record["wall_ns"] = perf_counter_ns() - started
            self.calls.append(record)

    def is_current(self, matches):
        return self.delegate.is_current(matches)


class RecordingRouter:
    def __init__(self, delegate):
        self.delegate = delegate
        self.result = None
        self.wall_ns = 0

    def route(self, text, *, history=()):
        started = perf_counter_ns()
        try:
            self.result = self.delegate.route(text, history=history)
            return self.result
        finally:
            self.wall_ns = perf_counter_ns() - started


class SystemBackend(GuardedBackend):
    def __init__(self, client, snapshot, sampler, allowed_models):
        super().__init__(client, snapshot, sampler)
        self.allowed_models = frozenset(allowed_models)
        self.attempted_models = set()
        self.transport_error = None

    def check(self):
        state = super().check()
        if any(m.get("name", m.get("model")) not in self.allowed_models
               for m in _resident_models()):
            self.sampler.monitor.violation = "unexpected model became resident"
            raise SafetyGateError(self.sampler.monitor.violation)
        return state

    def chat(self, model, messages, **kwargs):
        if model not in self.allowed_models:
            self.sampler.monitor.violation = "attempt to call a model outside this arm"
            raise SafetyGateError(self.sampler.monitor.violation)
        self.check()
        self.attempted_models.add(model)
        checkpoint = len(self.calls)
        started = perf_counter_ns()
        failure = None
        try:
            result = super().chat(model, messages, **kwargs)
            if result.model != model:
                raise OllamaError("returned model differs from requested model")
            return result
        except BaseException as error:
            failure = {"error": type(error).__name__, "message": str(error)}
            if isinstance(error, SafetyGateError):
                self.sampler.monitor.violation = str(error)
            if isinstance(error, OllamaError):
                self.transport_error = error
            raise
        finally:
            if len(self.calls) == checkpoint:
                self.calls.append({"wall_ns": perf_counter_ns() - started})
            record = self.calls[-1]
            fields = (kwargs.get("response_format") or {}).get("properties", {})
            purpose = ("generation" if "speech" in fields else
                       "memory_selector" if "memory_required" in fields else "compute_selector")
            record.update(purpose=purpose, requested_model=model,
                          actual_model=record.get("generation", {}).get("model"),
                          messages=[m.to_dict() for m in messages],
                          response_format=kwargs.get("response_format"),
                          status="error" if failure else "ok")
            if failure:
                record.update(failure)


def run_cases(cases, arm, repetition, config, backend, store, writer, records):
    """Only gold-free ExecutionCases and seeded memory cross this boundary."""
    for index, case in enumerate(cases, 1):
        backend.check()
        # A production cascade timeout can recover via its logged fallback.
        # Do not let that previous turn's transport error poison a later turn.
        backend.transport_error = None
        retriever = RecordingRetriever(store)
        router = (ConversationRouter(backend, model=SMALL) if arm == "cascade"
                  else MemoryOnlyRouter(backend, model=SMALL if arm == "small" else LARGE,
                                        fixed_model_size=arm))
        router = RecordingRouter(router)
        conversation = Conversation(
            backend, system_prompt=config.conversation.system_prompt,
            router=router, retriever=retriever, small_model=SMALL,
            general_large_model=LARGE, large_model=LARGE,
            context_length=config.generation.context_length,
            max_output_tokens=config.generation.max_output_tokens,
            fixed_generator_model=None if arm == "cascade" else SMALL if arm == "small" else LARGE,
        )
        checkpoint = len(backend.calls)
        started = perf_counter_ns()
        record = {**case, "arm": arm, "repetition": repetition, "index": index,
                  "started_monotonic_ns": started, "status": "error"}
        fatal = None
        try:
            reply = conversation.send(case["prompt"])
            record.update(status="ok", response=reply.response.to_dict(),
                          route=asdict(reply.route), memory=reply.memory_diagnostics.to_dict(),
                          generation=asdict(reply.generation),
                          answer_constraint=reply.answer_constraint,
                          generation_policy=reply.generation_policy,
                          response_transform=reply.response_transform,
                          reference_ids=list(reply.reference_ids),
                          fallback_from_model=reply.fallback_from_model)
        except BaseException as error:
            record.update(error=type(error).__name__, message=str(error))
            if isinstance(error, (KeyboardInterrupt, SystemExit, SafetyGateError)):
                fatal = error
            elif backend.transport_error is not None:
                fatal = backend.transport_error
        # Text latency ends when validation completes. Backend checks within
        # send are included; only this outer post-request check is excluded.
        finished = perf_counter_ns()
        record.update(finished_monotonic_ns=finished, wall_ns=finished - started,
                      calls=backend.calls[checkpoint:], retrieval_calls=retriever.calls,
                      routing_wall_ns=router.wall_ns,
                      route=asdict(router.result) if router.result is not None else None)
        try:
            backend.check()
        except BaseException as error:
            fatal = error
            record.update(status="interrupted", error=type(error).__name__, message=str(error))
        if fatal is not None:
            record["status"] = "interrupted"
        writer.write(record)
        records.append(record)
        print(f"{arm} r{repetition} {index}/{len(cases)} {case['id']}: "
              f"{record['status']} {record['wall_ns']/1e9:.3f}s", flush=True)
        if fatal is not None:
            raise fatal


def source_hashes():
    paths = list((ROOT / "src" / "oline_hri").glob("*.py"))
    paths += [ROOT / "scripts" / name for name in (
        "run_complete_system.py", "run_complete_system_batch.py", "complete_system_device_guard.py",
        "run_arc_capability.py", "run_pair_remediation_validation.py")]
    paths += [ROOT / "config" / "default.json"]
    return {str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--arm", choices=("small", "large", "cascade"), required=True)
    parser.add_argument("--repetition", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--freeze", required=True, type=Path)
    args = parser.parse_args(argv)
    workload = load_workload(args.workload)
    frozen = json.loads(args.freeze.read_text())
    if sha256(args.workload.read_bytes()).hexdigest() != frozen["workload_sha256"]:
        raise ValueError("workload differs from freeze")
    if source_hashes() != frozen["source_sha256"]:
        raise ValueError("source differs from freeze")
    config = load_config()
    config = replace(config, generation=replace(config.generation, context_length=2048,
                     max_output_tokens=192, temperature=0.0, thinking=False))
    if args.arm != "cascade":
        config = single_model_config(config, SMALL if args.arm == "small" else LARGE)
    allowed = tuple(dict.fromkeys((config.ollama.small_model, config.ollama.large_model)))
    os.umask(0o077)
    directory = _new_private_directory(args.output_dir.absolute())
    records, cleanup_errors = [], []
    status, failure = "incomplete", None
    sampler = backend = monitor = None
    with stage2_limits():
        try:
            start = capture_safety_snapshot()
            _write_new_json(directory / "start.json", start)
            require_ready(start)
            installed = _installed_models()
            models = {model: _model_metadata(model, installed) for model in allowed}
            if any(models[model] != frozen["models"][model] for model in allowed):
                raise ValueError("installed model metadata differs from freeze")
            version = _http_json("/api/version")
            if version != frozen["ollama_version"]:
                raise ValueError("Ollama version differs from freeze")
            # BgeOnnxEmbedder verifies each file against these pinned hashes
            # before constructing its runtime; source_sha256 also pins this code.
            if dict(REQUIRED_ASSET_SHA256) != frozen["embedding_asset_sha256"]:
                raise ValueError("embedding asset contract differs from freeze")
            _write_new_json(directory / "manifest.json", {
                "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                "arm": args.arm, "repetition": args.repetition,
                "frozen": frozen, "workload_path": str(args.workload.resolve()),
                "models": models, "config": config.to_dict(), "generation_seed": 42,
                "device_policy": policy_dict(), "hardware": platform.uname()._asdict(),
                "python": sys.version, "ollama_version": version,
                "scope": "text request pipeline; stateless history, natural model residency; static lifecycle snapshot",
            })
            _write_new_json(directory / "workload.json", workload)
            client = OllamaClient(config.ollama, config.generation)
            with _DurableJsonlWriter(directory / "telemetry.jsonl") as telemetry:
                monitor = _StreamingSafetyMonitor(telemetry)
                sampler = GuardedSampler(monitor)
                backend = SystemBackend(client, start, sampler, allowed)
                with sampler:
                    try:
                        deadline = perf_counter() + 5
                        while not sampler.samples and perf_counter() < deadline:
                            backend.check()
                            sleep(.05)
                        if not sampler.samples:
                            raise SafetyGateError("no initial telemetry sample")
                        backend.check()
                        setup_start = perf_counter_ns()
                        embedder = BgeOnnxEmbedder(config.embedding.model_directory,
                                                   config.embedding.intra_op_threads)
                        store, events = materialize_seed(workload["memory_seed"],
                                                         directory / "memory.sqlite3", embedder)
                        snapshot = [item.to_dict() for item in store.list_memories(include_inactive=True)]
                        _write_new_json(directory / "memory_setup.json", {
                            "wall_ns": perf_counter_ns() - setup_start, "events": events,
                            "snapshot": snapshot, "snapshot_sha256": sha256(_canonical_bytes(snapshot)).hexdigest(),
                        })
                        backend.check()
                        with _DurableJsonlWriter(directory / "observations.jsonl") as writer:
                            run_cases(workload["execution_cases"], args.arm, args.repetition,
                                      config, backend, store, writer, records)
                    finally:
                        cleanup_errors.extend(_force_unload(sorted(backend.attempted_models)))
            status = "complete" if all(r["status"] == "ok" for r in records) else "complete_with_errors"
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
            status = "interrupted" if isinstance(error, (KeyboardInterrupt, SystemExit, SafetyGateError)) else "failed"
        finally:
            if cleanup_errors:
                status = "cleanup_failed"
            if sampler is not None:
                _write_new_json(directory / "telemetry_summary.json", sampler.summary())
            try:
                finish = capture_safety_snapshot()
            except BaseException as error:
                finish = {"snapshot_error": type(error).__name__, "message": str(error)}
                status = "finish_snapshot_failed"
            _write_new_json(directory / "summary.json", {
                "status": status, "arm": args.arm, "repetition": args.repetition,
                "planned": len(workload["execution_cases"]), "attempted": len(records),
                "delivered": sum(r["status"] == "ok" for r in records),
                "latency_seconds": distribution([r["wall_ns"] / 1e9 for r in records]),
                "first_case_seconds": records[0]["wall_ns"] / 1e9 if records else None,
            })
            _write_new_json(directory / "finish.json", {
                **finish, "status": status, "failure": failure, "cleanup_errors": cleanup_errors,
                "guard_violation": monitor.violation if monitor is not None else None,
                "telemetry_reader_error": str(sampler._reader_error) if sampler is not None and sampler._reader_error else None,
            })
    print(f"ARTIFACTS {directory} status={status}", flush=True)
    return 0 if status in {"complete", "complete_with_errors"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
