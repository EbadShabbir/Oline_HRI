"""Excluded 12-attempt live integration check; never part of the frozen test.

Run manually before collection with --output pointing to a new directory.
Uses the main runner's actual guarded request path, not a second implementation.
No answer-quality scoring or final-test fixture is loaded here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from time import perf_counter, perf_counter_ns, sleep

import run_independent_retrieval as runner
from independent_retrieval_adapter import (
    ADAPTER_POLICY, materialize_snapshot, open_snapshot, snapshot_digest,
)
from oline_hri.evaluation_systems import single_model_config
from post_memory_device_guard import stage2_limits, require_ready, policy_dict


PROFILE = "excluded_independent_retrieval_smoke_v1"
MEMORY_ID = "mem_00000000000000000000000000009001"
POLICY_ORDER = ("OFF", "ALWAYS", "SELECTIVE")


def fixture():
    seed = {
        "profile_id": PROFILE, "evaluation_at": "2026-11-02T12:00:00.000000Z",
        "retention_days": 30, "other_profile_seeds": [],
        "events": [{"id": "excluded_smoke_fruit", "at": "2026-11-01T12:00:00.000000Z",
                    "operation": "remember", "memory_id": MEMORY_ID,
                    "canonical_text": "The user's favorite fruit is mango.", "kind": "preference"}],
    }
    cases = [{"id": "excluded_smoke_recall", "prompt": "What is my favorite fruit?",
              "profile_id": PROFILE, "consent_authorized": True},
             {"id": "excluded_smoke_general", "prompt": "What is 2 plus 3?",
              "profile_id": PROFILE, "consent_authorized": True}]
    return seed, cases


def wait_for_admission(baseline, waits, model):
    """Use unchanged admission checks and the runner's ten-minute recovery cap."""
    began = perf_counter_ns()
    deadline = perf_counter() + 600
    while True:
        state = runner.pair.capture_safety_snapshot()
        if any(state[key] != baseline[key] for key in ("boot_id", "thermal_trip_events", "power_mode")):
            raise runner.pair.SafetyGateError("device state changed during excluded smoke")
        if state["memory"]["swap_total_kib"] != baseline["memory"]["swap_total_kib"]:
            raise runner.pair.SafetyGateError("swap capacity changed during excluded smoke")
        try:
            require_ready(state)
            if max(state["temperatures_c"].values()) >= 54:
                raise runner.pair.SafetyGateError("smoke cooldown to below 54 C")
            waits.write({"event": "admission_complete", "model": model,
                         "wall_ns": perf_counter_ns() - began, "snapshot": state})
            return state
        except runner.pair.SafetyGateError as error:
            waits.write({"event": "admission_wait", "model": model,
                         "snapshot": state, "error": str(error)})
            if state["resident_models"] or perf_counter() >= deadline:
                raise
            print(f"SMOKE WAIT {model}: {error}", flush=True)
            sleep(20)


def read_rows(directory):
    return [json.loads(line) for path in sorted(directory.glob("model_*/policy_*/observations.jsonl"))
            for line in path.read_text().splitlines() if line.strip()]


def audit_rows(rows):
    """Check concrete execution inputs and evidence, never semantic correctness."""
    errors = []
    def check(condition, message):
        if not condition:
            errors.append(message)

    expected = {(model, policy, case_id) for model in runner.MODELS for policy in POLICY_ORDER
                for case_id in ("excluded_smoke_recall", "excluded_smoke_general")}
    keys = [(row["model"], row["policy"], row["case"]["id"]) for row in rows]
    check(len(rows) == 12 and len(set(keys)) == 12 and set(keys) == expected,
          "exactly twelve unique development attempts are required")
    general_inputs = []
    for row in rows:
        key = f"{row['model']} {row['policy']} {row['case']['id']}"
        model, policy, case_id = row["model"], row["policy"], row["case"]["id"]
        details = row.get("adapter", {})
        calls = details.get("calls", [])
        generation = [call for call in calls if call.get("purpose") == "generation"]
        check(row.get("status") in {"ok", "error", "interrupted"}, key + ": missing delivery status")
        check(details.get("authorization", {}).get("authorized") is True, key + ": not authorized")
        check(bool(generation), key + ": missing generation request")
        for call in calls:
            check(call.get("requested_model") == model, key + ": non-condition requested model")
            if call.get("status") == "ok":
                check(call.get("actual_model") == model, key + ": non-condition actual model")
                check(call.get("raw_generation", {}).get("model") == model,
                      key + ": returned model metadata mismatch")
            check(call.get("purpose") in {"generation", "memory_selector"}, key + ": unexpected helper role")
            if call.get("purpose") == "memory_selector":
                check(policy == "SELECTIVE", key + ": classifier outside SELECTIVE")
            messages = call.get("messages", [])
            roles = [message.get("role") for message in messages]
            # A fresh personal/no-evidence turn legitimately adds a second
            # system instruction. It must still have only the current user
            # request and no retained assistant or earlier user turn.
            check(len(messages) >= 2 and roles[-1:] == ["user"]
                  and all(role == "system" for role in roles[:-1])
                  and row["case"]["prompt"] in messages[-1].get("content", ""),
                  key + ": unexpected history or message roles")
        http = [call for call in row.get("http_calls", []) if call.get("endpoint") == "/api/chat"]
        check(len(http) == len(calls), key + ": missing durable HTTP call")
        for call in http:
            body = call["body"]
            check(body.get("model") == model, key + ": wrong HTTP model")
            check(body.get("options") == {"num_ctx": 2048, "num_predict": 192, "temperature": 0.0, "seed": 42},
                  key + ": decoding differs from declared settings")
            check(body.get("think") is False and body.get("stream") is False,
                  key + ": thinking/streaming differs")
            check(body.get("keep_alive") == -1, key + ": sole model not retained")
            if call.get("status") == "ok":
                check(call.get("response", {}).get("model") == model, key + ": raw actual model differs")
        supplied = details.get("supplied_ids", [])
        if policy == "OFF":
            check(details.get("retrieval_attempts") == 0 and details.get("inspected_ids") == [] and supplied == [],
                  key + ": OFF memory access or evidence leakage")
            inputs = json.dumps([{k: call.get(k) for k in ("messages", "options")} for call in calls]).lower()
            check("mango" not in inputs and MEMORY_ID not in inputs, key + ": OFF fact leaked into model inputs")
        if case_id == "excluded_smoke_recall" and policy != "OFF":
            check(details.get("retrieval_attempts") == 1, key + ": authorized recall did not retrieve once")
            check(supplied == [MEMORY_ID], key + ": authorized recall evidence was not supplied")
            check(all(event.get("current") is True for event in details.get("freshness_calls", [])),
                  key + ": freshness rejected unchanged snapshot")
        if case_id == "excluded_smoke_general":
            check(supplied == [], key + ": irrelevant personal fact supplied to general question")
            expected_retrieval = (int(bool(details.get("selection", {}).get("retrieval_selected")))
                                  if policy == "SELECTIVE" else int(policy == "ALWAYS"))
            check(details.get("retrieval_attempts") == expected_retrieval,
                  key + ": general request retrieval policy mismatch")
            general_inputs.append([{k: call.get(k) for k in ("messages", "options")} for call in generation])
        for phase in ("api_ps_before", "api_ps_after"):
            residents = row.get(phase)
            check(isinstance(residents, list) and len(residents) <= 1, key + ": incomplete/multiple residency")
            if isinstance(residents, list):
                check(all(item.get("name", item.get("model")) == model for item in residents),
                      key + ": resident non-condition model")
    check(len(general_inputs) == 6 and all(value == general_inputs[0] for value in general_inputs),
          "general generation messages and schema/options differ across six conditions")
    return {"passed": not errors, "errors": errors, "attempted": len(rows),
            "delivered": sum(row.get("status") == "ok" for row in rows),
            "delivery_failures": sum(row.get("status") != "ok" for row in rows),
            "semantic_quality_scored": False, "included_in_864_test_attempts": False}


def run_model(directory, model_index, start, seed, cases, prepared_path):
    model = runner.MODELS[model_index]
    config = single_model_config(runner.configuration(), model)
    target = runner.pair._new_private_directory(directory / f"model_{model_index + 1}")
    runner.write(target / "start.json", start)
    runner.write(target / "configuration.json", config.to_dict())
    status = "incomplete"
    failure = None
    errors = []
    client = backend = sampler = None
    logical_before = None
    snapshot = target / "memory.sqlite3"
    try:
        with runner.pair._DurableJsonlWriter(target / "http_calls.jsonl") as http, \
             runner.pair._DurableJsonlWriter(target / "telemetry.jsonl") as telemetry:
            client = runner.DurableClient(config.ollama, config.generation, http_writer=http, retain_large_model=True)
            monitor = runner.pair._StreamingSafetyMonitor(telemetry)
            sampler = runner.GuardedSampler(monitor)
            backend = runner.ComparisonBackend(client, start, sampler, (model,))
            with sampler:
                try:
                    runner.initial_sample(backend, sampler)
                    setup_began = perf_counter_ns()
                    embedder = runner.BgeOnnxEmbedder(config.embedding.model_directory, config.embedding.intra_op_threads)
                    if not prepared_path.exists():
                        _, setup = materialize_snapshot(prepared_path, seed, embedder)
                        runner.write(directory / "prepared_snapshot.json", setup)
                    shutil.copyfile(prepared_path, snapshot)
                    logical_before = snapshot_digest(snapshot)
                    if logical_before != snapshot_digest(prepared_path):
                        raise ValueError("development snapshot copy differs")
                    store = open_snapshot(snapshot, seed, embedder)
                    runner.write(target / "setup.json", {"wall_ns": perf_counter_ns() - setup_began,
                                 "logical_sha256": logical_before})
                    backend.check()
                    for policy_index, policy in enumerate(POLICY_ORDER):
                        policy_dir = runner.pair._new_private_directory(target / f"policy_{policy_index + 1}_{policy.lower()}")
                        slot = {"slot": model_index * 3 + policy_index + 1, "model": model,
                                "policy": policy, "repetition": 0, "excluded_development_smoke": True}
                        runner.run_cases(cases, slot, config, backend, store, policy_dir)
                    status = "complete"
                finally:
                    cleanup_began = perf_counter_ns()
                    errors.extend(runner.cleanup_owned(client, backend))
                    runner.write(target / "cleanup_timing.json", {"wall_ns": perf_counter_ns() - cleanup_began})
    except BaseException as error:
        status = "interrupted"
        failure = {"type": type(error).__name__, "message": str(error)}
    finally:
        if snapshot.exists():
            try:
                logical_after = snapshot_digest(snapshot)
                runner.write(target / "snapshot_verification.json", {"before": logical_before,
                             "after": logical_after, "unchanged": logical_after == logical_before})
                if logical_after != logical_before:
                    errors.append("development snapshot mutated")
            except BaseException as error:
                errors.append("snapshot verification failed: " + type(error).__name__)
        try:
            finish = runner.pair.capture_safety_snapshot()
            if finish["resident_models"]:
                errors.append("model remained resident after cleanup")
            if any(finish[key] != start[key] for key in ("boot_id", "thermal_trip_events", "power_mode")):
                errors.append("boot/trips/power changed")
            if finish["memory"]["swap_total_kib"] != start["memory"]["swap_total_kib"]:
                errors.append("swap capacity changed")
        except BaseException as error:
            finish = {"error": type(error).__name__, "message": str(error)}
            errors.append("missing final device snapshot")
        runner.write(target / "finish.json", finish)
        if sampler is not None:
            runner.write(target / "telemetry_summary.json", sampler.summary())
        rows = [json.loads(line) for path in target.glob("policy_*/observations.jsonl")
                for line in path.read_text().splitlines() if line.strip()]
        if status == "complete" and any(row["status"] != "ok" for row in rows):
            status = "complete_with_errors"
        if errors:
            status = "verification_failed"
        summary = {"model": model, "status": status, "failure": failure, "errors": errors,
                   "attempted": len(rows), "planned": 6, "included_in_final_test": False}
        runner.write(target / "summary.json", summary)
    return summary


def child_model(directory, model_index):
    """One isolated model process, matching primary collection boundaries."""
    try:
        with runner.inference_lock(), stage2_limits():
            start = runner.pair.capture_safety_snapshot()
            require_ready(start)
            baseline = json.loads((directory / "before.json").read_text())
            if any(start[key] != baseline[key] for key in ("boot_id", "thermal_trip_events", "power_mode")):
                raise runner.pair.SafetyGateError("device state changed before smoke child admission")
            seed, cases = fixture()
            summary = run_model(directory, model_index, start, seed, cases,
                                directory / "prepared_memory.sqlite3")
            return 0 if summary["status"].startswith("complete") else 1
    except BaseException as error:
        runner.write(directory / f"child_start_failure_{model_index + 1}.json",
                     {"type": type(error).__name__, "message": str(error),
                      "model_index": model_index, "included_in_final_test": False})
        return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-index", type=int, choices=(0, 1), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if sys.flags.optimize:
        raise ValueError("nonoptimized Python required")
    if args.model_index is not None:
        return child_model(args.output.absolute(), args.model_index)
    directory = runner.pair._new_private_directory(args.output.absolute())
    seed, cases = fixture()
    source_hashes = {**runner.sources(), str(Path(__file__).resolve().relative_to(runner.ROOT)):
                     runner.file_hash(Path(__file__).resolve())}
    runner.write(directory / "manifest.json", {"purpose": "excluded pre-collection integration validation",
                 "planned_attempts": 12, "memory_seed": seed, "execution_cases": cases,
                 "config": runner.configuration().to_dict(), "adapter_policy": ADAPTER_POLICY,
                 "source_sha256": source_hashes, "device_policy": policy_dict(),
                 "model_order": list(runner.MODELS), "policy_order": list(POLICY_ORDER),
                 "model_session_isolation": "separate child process per model; parent batch lock and child inference lock",
                 "semantic_quality_scored": False, "included_in_864_test_attempts": False})
    status = "incomplete"
    failure = None
    sessions = []
    try:
        with runner.batch_lock(), stage2_limits():
            runner.require_exclusive()
            baseline = runner.pair.capture_safety_snapshot()
            runner.write(directory / "before.json", baseline)
            runner.write(directory / "models.json", {"models": runner.model_inventory(),
                         "ollama_version": runner.pair._http_json("/api/version")})
            with runner.pair._DurableJsonlWriter(directory / "startup_waits.jsonl") as waits:
                for model_index, model in enumerate(runner.MODELS):
                    wait_for_admission(baseline, waits, model)
                    result = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                                             "--output", str(directory), "--model-index", str(model_index)])
                    summary_path = directory / f"model_{model_index + 1}" / "summary.json"
                    session = (json.loads(summary_path.read_text()) if summary_path.exists()
                               else {"model": model, "status": "child_admission_failed", "attempted": 0})
                    session["child_exit_code"] = result.returncode
                    sessions.append(session)
                    if result.returncode or not session["status"].startswith("complete"):
                        raise RuntimeError(f"excluded smoke interrupted for {model}")
            status = "complete"
    except BaseException as error:
        status = "interrupted"
        failure = {"type": type(error).__name__, "message": str(error)}
    finally:
        rows = read_rows(directory)
        audit = audit_rows(rows)
        source_now = {relative: runner.file_hash(runner.ROOT / relative) for relative in source_hashes}
        audit["source_unchanged"] = source_now == source_hashes
        if not audit["source_unchanged"]:
            audit["passed"] = False
            audit["errors"].append("source changed during excluded smoke")
        if not audit["passed"] and status == "complete":
            status = "validation_failed"
        elif status == "complete" and audit["delivery_failures"]:
            status = "complete_with_errors"
        runner.write(directory / "validation.json", audit)
        try:
            finish = runner.host()
        except BaseException as error:
            finish = {"error": type(error).__name__, "message": str(error)}
            status = "verification_failed"
        runner.write(directory / "finish.json", {"status": status, "failure": failure,
                     "sessions": sessions, "host": finish, "attempted": len(rows),
                     "planned": 12, "included_in_864_test_attempts": False})
        runner.seal(directory)
    print(f"EXCLUDED SMOKE {status} {directory}", flush=True)
    return 0 if status.startswith("complete") else 1


if __name__ == "__main__":
    sys.exit(main())
