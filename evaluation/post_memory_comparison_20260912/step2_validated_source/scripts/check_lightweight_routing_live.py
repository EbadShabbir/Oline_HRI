"""Guarded five-request integration diagnostic; not a quality benchmark.

Run one policy per fresh output directory. --preflight-only never calls models.
The original Stage 2 device limits remain unchanged, including its startup
swap ceiling. This diagnostic uses current source hashes, not the old freeze.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, perf_counter_ns, sleep

from oline_hri.config import load_config
from oline_hri.conversation import Conversation
from oline_hri.evaluation_model_pairs import (
    SafetyGateError, _DurableJsonlWriter, _StreamingSafetyMonitor,
    _force_unload, _http_json, _installed_models, _model_metadata,
    _new_private_directory, _resident_models, _write_new_json,
)
from oline_hri.lightweight_routing import LightweightRouter
from oline_hri.routing import ConversationRouter
from complete_system_device_guard import (
    capture_safety_snapshot, policy_dict, require_ready, stage2_limits,
)
from run_complete_system import RecordingOllamaClient, RecordingRouter, SystemBackend
from run_pair_remediation_validation import GuardedSampler


ROOT = Path(__file__).resolve().parents[1]
HARD = "Compare bicycles and buses for general urban travel. Give one advantage of each."
EASY = "What is photosynthesis?"
PROMPTS = (HARD, HARD, EASY, EASY, EASY)


class IntegrationCheckError(RuntimeError):
    """The diagnostic did not establish its intended lifecycle behavior."""


class EmptyDiagnosticRetriever:
    """Explicit empty fixture; records unexpected memory access, never opens a DB."""

    def __init__(self):
        self.calls = []

    def retrieve(self, query, *, limit=3):
        self.calls.append({"query": query, "limit": limit,
                           "scope": "unexpected retrieval against empty diagnostic fixture"})
        return ()

    def is_current(self, matches):
        if matches:
            raise IntegrationCheckError("empty diagnostic fixture received memory evidence")
        return True


class HttpRecordingClient(RecordingOllamaClient):
    def __init__(self, *args, http_writer, **kwargs):
        super().__init__(*args, **kwargs)
        self.http_writer = http_writer
        self.http_calls = []

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


class DiagnosticBackend(SystemBackend):
    @property
    def resident_model(self):
        """Forward the real client's cached hint; no classifier or HTTP work."""
        return self.client.resident_model


def current_source_hashes():
    paths = list((ROOT / "src/oline_hri").glob("*.py"))
    paths += [ROOT / "scripts" / name for name in (
        "check_lightweight_routing_live.py", "complete_system_device_guard.py",
        "run_complete_system.py", "run_pair_remediation_validation.py", "run_arc_capability.py")]
    paths.append(ROOT / "config/default.json")
    return {str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest() for path in sorted(paths)}


def run_sequence(policy, config, backend, writer, records):
    small, large = config.ollama.small_model, config.ollama.large_model
    delegate = (LightweightRouter(backend, small_model=small, large_model=large)
                if policy == "lightweight" else ConversationRouter(backend, model=small))
    # Router state and model residency persist; conversational history does not.
    router = RecordingRouter(delegate)
    expected = (large, large, large, small, small)
    for index, prompt in enumerate(PROMPTS, 1):
        backend.check()
        retriever = EmptyDiagnosticRetriever()
        checkpoint = len(backend.calls)
        http_checkpoint = len(backend.client.http_calls)
        router.result = None
        record = {"index": index, "prompt": prompt, "policy": policy, "status": "error",
                  "resident_hint_before": backend.resident_model,
                  "api_ps_before": list(_resident_models())}
        failure = None
        started = perf_counter_ns()
        try:
            conversation = Conversation(
                backend, system_prompt=config.conversation.system_prompt,
                router=router, retriever=retriever, small_model=small,
                general_large_model=config.ollama.general_large_model, large_model=large,
                context_length=config.generation.context_length,
                max_output_tokens=config.generation.max_output_tokens,
            )
            reply = conversation.send(prompt)
            record.update(response=reply.response.to_dict(), generation=asdict(reply.generation),
                          generation_policy=reply.generation_policy,
                          answer_constraint=reply.answer_constraint,
                          response_transform=reply.response_transform,
                          fallback_from_model=reply.fallback_from_model,
                          memory=reply.memory_diagnostics.to_dict())
            if retriever.calls or reply.route.decision.memory_required:
                raise IntegrationCheckError("general diagnostic unexpectedly requested personal memory")
            if any(call.get("status") == "error" for call in backend.calls[checkpoint:]):
                raise IntegrationCheckError("a model call failed, including a recovered fallback")
            if policy == "lightweight":
                if reply.route.model_size_generation is not None or reply.route.memory_required_generation is not None:
                    raise IntegrationCheckError("explicit general prompts unexpectedly used a classifier")
                if reply.generation.model != expected[index - 1]:
                    raise IntegrationCheckError("lightweight generator lifecycle differs from L,L,L,S,S")
            record["status"] = "ok"
        except BaseException as error:
            failure = error
            record.update(error=type(error).__name__, message=str(error))
        finally:
            record.update(wall_ns=perf_counter_ns() - started,
                          calls=backend.calls[checkpoint:],
                          http_calls=backend.client.http_calls[http_checkpoint:],
                          route=asdict(router.result) if router.result is not None else None,
                          retrieval_calls=retriever.calls,
                          resident_hint_after=backend.resident_model)
            try:
                backend.check()
                record["api_ps_after"] = list(_resident_models())
            except BaseException as error:
                failure = error
                record.update(status="error", error=type(error).__name__, message=str(error))
            writer.write(record)
            records.append(record)
        print(f"{policy} {index}/{len(PROMPTS)}: {record['status']}", flush=True)
        if failure is not None:
            raise failure


def cleanup_owned(client, backend):
    """Use the client's normal cleanup, then independent recovery if required."""
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
    parser.add_argument("--policy", required=True, choices=("llm", "lightweight"))
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)
    directory = _new_private_directory(args.output_dir.absolute())
    config = load_config()
    config = replace(config, generation=replace(config.generation, context_length=2048,
                                               max_output_tokens=192, temperature=0.0, thinking=False))
    models = tuple(dict.fromkeys((config.ollama.small_model, config.ollama.general_large_model,
                                  config.ollama.large_model)))
    _write_new_json(directory / "plan.json", {
        "created_at": datetime.now(timezone.utc).isoformat(), "policy": args.policy,
        "preflight_only": args.preflight_only, "prompts": PROMPTS,
        "scope": "current-source routing/residency integration diagnostic; no quality estimate, embeddings or personal DB",
        "source_sha256": current_source_hashes(), "device_policy": policy_dict(),
        "retain_large_model": args.policy == "lightweight",
        "generation": asdict(config.generation), "generation_seed": 42,
        "models": models, "fresh_history_each_request": True,
        "persistent_router_state": True, "max_requests": len(PROMPTS),
    })
    status, failure, admitted = "incomplete", None, False
    records, cleanup_errors = [], []
    sampler = monitor = backend = client = None
    with stage2_limits():
        try:
            start = capture_safety_snapshot()
            _write_new_json(directory / "start.json", start)
            require_ready(start)
            admitted = True
            if args.preflight_only:
                status = "preflight_passed_no_inference"
            else:
                installed = _installed_models()
                _write_new_json(directory / "models.json", {
                    "models": {model: _model_metadata(model, installed) for model in models},
                    "ollama_version": _http_json("/api/version"),
                })
                with _DurableJsonlWriter(directory / "http_calls.jsonl") as http_writer, \
                     _DurableJsonlWriter(directory / "telemetry.jsonl") as telemetry:
                    client = HttpRecordingClient(config.ollama, config.generation, http_writer=http_writer,
                                                 retain_large_model=args.policy == "lightweight")
                    monitor = _StreamingSafetyMonitor(telemetry)
                    sampler = GuardedSampler(monitor)
                    backend = DiagnosticBackend(client, start, sampler, models)
                    with sampler:
                        try:
                            deadline = perf_counter() + 5
                            while not sampler.samples and perf_counter() < deadline:
                                backend.check()
                                sleep(.05)
                            if not sampler.samples:
                                raise SafetyGateError("no initial telemetry sample")
                            with _DurableJsonlWriter(directory / "observations.jsonl") as writer:
                                run_sequence(args.policy, config, backend, writer, records)
                            status = "complete"
                        finally:
                            cleanup_errors.extend(cleanup_owned(client, backend))
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
            status = "blocked_preflight" if not admitted else "failed"
        finally:
            if sampler is not None:
                try:
                    _write_new_json(directory / "telemetry_summary.json", sampler.summary())
                except BaseException as error:
                    cleanup_errors.append(f"telemetry summary: {type(error).__name__}: {error}")
            try:
                finish = capture_safety_snapshot()
                if admitted and finish["resident_models"]:
                    cleanup_errors.append("resident model remains after diagnostic cleanup")
                if admitted and (finish["boot_id"] != start["boot_id"]
                                 or finish["thermal_trip_events"] != start["thermal_trip_events"]
                                 or finish["power_mode"] != start["power_mode"]):
                    cleanup_errors.append("boot, thermal trips, or power mode changed")
            except BaseException as error:
                finish = {"snapshot_error": type(error).__name__, "message": str(error)}
                cleanup_errors.append("final device snapshot unavailable")
            if cleanup_errors:
                status = "cleanup_failed"
            _write_new_json(directory / "finish.json", {
                **finish, "status": status, "policy": args.policy, "failure": failure,
                "admitted": admitted, "planned": len(PROMPTS), "attempted": len(records),
                "cleanup_errors": cleanup_errors,
                "guard_violation": monitor.violation if monitor is not None else None,
                "scope": "integration diagnostic only; not an old frozen evaluation result",
            })
    print(f"ARTIFACTS {directory} status={status}", flush=True)
    return 0 if status in {"complete", "preflight_passed_no_inference"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
