"""One immutable post-memory-fix session with optimized fixed or lightweight routing."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version as package_version
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
from oline_hri.evaluation_systems import OptimizedMemoryOnlyRouter, single_model_config
from oline_hri.lightweight_routing import LightweightRouter
from complete_system_device_guard import stage2_limits, require_ready, policy_dict
from run_arc_capability import distribution
from run_complete_system import (
    RecordingOllamaClient, RecordingRetriever, RecordingRouter, SystemBackend,
    load_workload, materialize_seed,
)
from run_pair_remediation_validation import GuardedSampler


ROOT = Path(__file__).resolve().parents[1]
PROFILE_ID = "post_memory_comparison_v1"
SMALL, LARGE = "qwen3:0.6b", "qwen3:1.7b"
ARM_ORDERS = (("small", "large", "cascade"), ("large", "cascade", "small"),
              ("cascade", "small", "large"))
EXECUTION_POLICY = {
    "memory_policy": "policy_first_shared", "fixed_router_policy": "fixed_memory_v1",
    "adaptive_router_policy": "lightweight_v1", "fresh_history_each_request": True,
    "persistent_router_state": True, "retain_large_model": True,
    "automatic_memory_capture": False, "generation_seed": 42,
    "small_streak_before_switch": 2,
}


def execution_policy(arm):
    if arm not in {"small", "large", "cascade"}:
        raise ValueError("unknown comparison arm")
    fixed = None if arm == "cascade" else SMALL if arm == "small" else LARGE
    return {**EXECUTION_POLICY, "router_policy": "lightweight_v1" if fixed is None else "fixed_memory_v1",
            "fixed_generator_model": fixed, "allowed_models": [SMALL, LARGE] if fixed is None else [fixed]}


def package_versions():
    return {name: package_version(name) for name in ("numpy", "onnxruntime", "tokenizers")}


def source_hashes():
    """Pin execution, analysis, orchestration and all application dependencies."""
    paths = list((ROOT / "src/oline_hri").glob("*.py"))
    paths += [ROOT / "scripts" / name for name in (
        "run_post_memory_comparison.py", "freeze_post_memory_comparison.py",
        "run_post_memory_batch.py", "analyze_post_memory_comparison.py",
        "analyze_complete_system.py", "analyze_arc_capability.py", "run_complete_system.py", "run_arc_capability.py",
        "run_pair_remediation_validation.py", "complete_system_device_guard.py",
    )]
    paths.append(ROOT / "config/default.json")
    return {str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)}


class ComparisonClient(RecordingOllamaClient):
    """Archive actual HTTP bodies, including serial peer unloads and cleanup."""

    def __init__(self, *args, http_writer, **kwargs):
        super().__init__(*args, **kwargs)
        self.http_writer, self.http_calls = http_writer, []

    def _post_json(self, endpoint, body, **kwargs):
        record = {"endpoint": endpoint, "body": body,
                  "started_monotonic_ns": perf_counter_ns(), "status": "error"}
        try:
            payload = super()._post_json(endpoint, body, **kwargs)
            record.update(status="ok", response=payload)
            return payload
        except BaseException as error:
            record.update(error=type(error).__name__, message=str(error))
            raise
        finally:
            record["wall_ns"] = perf_counter_ns() - record["started_monotonic_ns"]
            self.http_calls.append(record)
            self.http_writer.write(record)


class ComparisonBackend(SystemBackend):
    @property
    def resident_model(self):
        """Actual client cache, never a fabricated hint or an HTTP query."""
        return self.client.resident_model


def make_router(backend, arm):
    if arm == "cascade":
        return LightweightRouter(backend, small_model=SMALL, large_model=LARGE,
                                 small_streak_before_switch=2)
    if arm not in {"small", "large"}:
        raise ValueError("unknown comparison arm")
    return OptimizedMemoryOnlyRouter(backend, model=SMALL if arm == "small" else LARGE,
                                    fixed_model_size=arm)


def run_cases(cases, arm, repetition, config, backend, store, writer, records):
    """Persistent router/residency, fresh history, and an identical memory path."""
    router = RecordingRouter(make_router(backend, arm))
    for index, case in enumerate(cases, 1):
        backend.check()
        backend.transport_error = None
        router.result, router.wall_ns = None, 0
        retriever = RecordingRetriever(store)
        conversation = Conversation(
            backend, system_prompt=config.conversation.system_prompt, router=router,
            retriever=retriever, small_model=SMALL, general_large_model=LARGE, large_model=LARGE,
            context_length=config.generation.context_length,
            max_output_tokens=config.generation.max_output_tokens,
            fixed_generator_model=None if arm == "cascade" else SMALL if arm == "small" else LARGE,
        )
        checkpoint, http_checkpoint = len(backend.calls), len(backend.client.http_calls)
        record = {**case, "profile_id": PROFILE_ID, "arm": arm, "repetition": repetition,
                  "index": index, "status": "error", "resident_hint_before": backend.resident_model,
                  "api_ps_before": list(_resident_models())}
        started = perf_counter_ns()
        record["started_monotonic_ns"] = started
        fatal = None
        try:
            reply = conversation.send(case["prompt"])
            record.update(status="ok", response=reply.response.to_dict(),
                          memory=reply.memory_diagnostics.to_dict(), generation=asdict(reply.generation),
                          answer_constraint=reply.answer_constraint,
                          generation_policy=reply.generation_policy, response_transform=reply.response_transform,
                          reference_ids=list(reply.reference_ids), fallback_from_model=reply.fallback_from_model)
        except BaseException as error:
            record.update(error=type(error).__name__, message=str(error))
            if isinstance(error, (KeyboardInterrupt, SystemExit, SafetyGateError)):
                fatal = error
            elif backend.transport_error is not None:
                fatal = backend.transport_error
        finished = perf_counter_ns()
        record.update(finished_monotonic_ns=finished, wall_ns=finished - started,
                      calls=backend.calls[checkpoint:], http_calls=backend.client.http_calls[http_checkpoint:],
                      retrieval_calls=retriever.calls, routing_wall_ns=router.wall_ns,
                      route=asdict(router.result) if router.result is not None else None,
                      resident_hint_after=backend.resident_model)
        try:
            backend.check()
        except BaseException as error:
            fatal = error
            record.update(error=type(error).__name__, message=str(error))
        # Try this read even after a guard abort. An unavailable snapshot is
        # explicit missing evidence, never an invented empty-residency result.
        record["post_snapshot_attempted"] = True
        try:
            record["api_ps_after"] = list(_resident_models())
        except BaseException as error:
            record["api_ps_after"] = None
            record["post_snapshot_error"] = {"error": type(error).__name__, "message": str(error)}
            if fatal is None:
                fatal = error
                record.update(error=type(error).__name__, message=str(error))
        if fatal is not None:
            record["status"] = "interrupted"
        writer.write(record)
        records.append(record)
        print(f"{arm} r{repetition} {index}/{len(cases)} {case['id']}: "
              f"{record['status']} {record['wall_ns']/1e9:.3f}s", flush=True)
        if fatal is not None:
            raise fatal


def cleanup_owned(client, backend):
    if not backend.attempted_models:
        return []
    errors = []
    try:
        client.unload_all()
    except BaseException as error:
        errors.append(f"client cleanup: {type(error).__name__}: {error}")
        errors.extend(_force_unload(sorted(backend.attempted_models)))
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", required=True, type=Path)
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--arm", required=True, choices=("small", "large", "cascade"))
    parser.add_argument("--repetition", required=True, type=int, choices=(1, 2, 3))
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)
    workload, frozen = load_workload(args.workload), json.loads(args.freeze.read_text())
    if frozen.get("profile_id") != PROFILE_ID:
        raise ValueError("wrong comparison freeze profile")
    if sha256(args.workload.read_bytes()).hexdigest() != frozen["workload_sha256"]:
        raise ValueError("workload differs from freeze")
    if source_hashes() != frozen["source_sha256"]:
        raise ValueError("source differs from freeze")
    base = load_config()
    if asdict(base.embedding) != frozen["embedding_config"]:
        raise ValueError("embedding configuration differs from freeze")
    if dict(REQUIRED_ASSET_SHA256) != frozen["embedding_asset_sha256"]:
        raise ValueError("embedding asset contract differs from freeze")
    config = replace(base, generation=replace(base.generation, context_length=2048,
                     max_output_tokens=192, temperature=0.0, thinking=False))
    if (asdict(config.generation) != frozen["generation"] or frozen["generation_seed"] != 42
            or config.to_dict() != frozen["base_config"] or package_versions() != frozen["packages"]
            or sys.version != frozen["python"] or policy_dict() != frozen["device_policy"]):
        raise ValueError("generation, configuration, software, or device policy differs from freeze")
    if frozen["execution_policies"][args.arm] != execution_policy(args.arm):
        raise ValueError("execution policy differs from freeze")
    if args.arm != "cascade":
        config = single_model_config(config, SMALL if args.arm == "small" else LARGE)
    allowed = tuple(dict.fromkeys((config.ollama.small_model, config.ollama.general_large_model,
                                  config.ollama.large_model)))
    expected = (SMALL, LARGE) if args.arm == "cascade" else (SMALL if args.arm == "small" else LARGE,)
    if set(allowed) != set(expected):
        raise ValueError("client roles differ from permitted arm models")
    os.umask(0o077)
    directory = _new_private_directory(args.output_dir.absolute())
    records, cleanup_errors = [], []
    status, failure, admitted = "incomplete", None, False
    sampler = backend = monitor = client = None
    with stage2_limits():
        try:
            start = capture_safety_snapshot()
            _write_new_json(directory / "start.json", start)
            require_ready(start)
            admitted = True
            installed = _installed_models()
            models = {model: _model_metadata(model, installed) for model in allowed}
            if any(models[model] != frozen["models"][model] for model in allowed):
                raise ValueError("installed model metadata differs from freeze")
            version = _http_json("/api/version")
            if version != frozen["ollama_version"]:
                raise ValueError("Ollama version differs from freeze")
            _write_new_json(directory / "manifest.json", {
                "schema_version": 1, "profile_id": PROFILE_ID,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "arm": args.arm, "repetition": args.repetition, "frozen": frozen,
                "workload_path": str(args.workload.resolve()), "models": models,
                "config": config.to_dict(), "generation_seed": 42,
                "execution_policy": execution_policy(args.arm), "preflight_only": args.preflight_only,
                "device_policy": policy_dict(), "hardware": platform.uname()._asdict(),
                "python": sys.version, "ollama_version": version,
                "scope": "text pipeline; fresh history, persistent router and residency; synthetic lifecycle snapshot",
            })
            _write_new_json(directory / "workload.json", workload)
            if args.preflight_only:
                status = "preflight_passed_no_inference"
            else:
                with _DurableJsonlWriter(directory / "http_calls.jsonl") as http_writer, \
                     _DurableJsonlWriter(directory / "telemetry.jsonl") as telemetry:
                    client = ComparisonClient(config.ollama, config.generation,
                                              http_writer=http_writer, retain_large_model=True)
                    monitor = _StreamingSafetyMonitor(telemetry)
                    sampler = GuardedSampler(monitor)
                    backend = ComparisonBackend(client, start, sampler, allowed)
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
                                "snapshot": snapshot,
                                "snapshot_sha256": sha256(_canonical_bytes(snapshot)).hexdigest(),
                            })
                            backend.check()
                            with _DurableJsonlWriter(directory / "observations.jsonl") as writer:
                                run_cases(workload["execution_cases"], args.arm, args.repetition,
                                          config, backend, store, writer, records)
                            status = ("complete" if all(r["status"] == "ok" for r in records)
                                      else "complete_with_errors")
                        finally:
                            cleanup_errors.extend(cleanup_owned(client, backend))
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
            status = ("blocked_preflight" if not admitted else "interrupted"
                      if isinstance(error, (KeyboardInterrupt, SystemExit, SafetyGateError)) else "failed")
        finally:
            if sampler is not None:
                try:
                    _write_new_json(directory / "telemetry_summary.json", sampler.summary())
                except BaseException as error:
                    cleanup_errors.append(f"telemetry summary: {type(error).__name__}: {error}")
            try:
                finish = capture_safety_snapshot()
                if admitted and (finish["resident_models"] or finish["fan_pwm"] <= 0
                                 or finish["boot_id"] != start["boot_id"]
                                 or finish["thermal_trip_events"] != start["thermal_trip_events"]
                                 or finish["power_mode"] != start["power_mode"]):
                    cleanup_errors.append("final residency, fan, boot, thermal trips, or power mode check failed")
            except BaseException as error:
                finish = {"snapshot_error": type(error).__name__, "message": str(error)}
                cleanup_errors.append("final device snapshot unavailable")
            verification = {"source_unchanged": False, "model_metadata_unchanged": False,
                            "ollama_version_unchanged": False}
            try:
                verification["source_sha256"] = source_hashes()
                verification["source_unchanged"] = verification["source_sha256"] == frozen["source_sha256"]
                installed = _installed_models()
                verification["model_metadata_unchanged"] = all(
                    _model_metadata(model, installed) == frozen["models"][model] for model in allowed)
                verification["ollama_version_unchanged"] = _http_json("/api/version") == frozen["ollama_version"]
            except BaseException as error:
                verification["end_verification_error"] = f"{type(error).__name__}: {error}"
            if not all(verification[key] for key in
                       ("source_unchanged", "model_metadata_unchanged", "ollama_version_unchanged")):
                status = "end_verification_failed"
            if monitor is not None and monitor.violation:
                status = "interrupted"
            if cleanup_errors:
                status = "cleanup_failed"
            _write_new_json(directory / "summary.json", {
                "status": status, "profile_id": PROFILE_ID, "arm": args.arm, "repetition": args.repetition,
                "planned": len(workload["execution_cases"]), "attempted": len(records),
                "delivered": sum(r["status"] == "ok" for r in records),
                "latency_seconds": distribution([r["wall_ns"] / 1e9 for r in records]),
                "first_case_seconds": records[0]["wall_ns"] / 1e9 if records else None,
            })
            _write_new_json(directory / "finish.json", {
                **finish, **verification, "profile_id": PROFILE_ID, "status": status,
                "failure": failure, "admitted": admitted, "cleanup_errors": cleanup_errors,
                "guard_violation": monitor.violation if monitor is not None else None,
                "telemetry_reader_error": str(sampler._reader_error) if sampler is not None and sampler._reader_error else None,
            })
    print(f"ARTIFACTS {directory} status={status}", flush=True)
    return 0 if status in {"complete", "complete_with_errors", "preflight_passed_no_inference"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
