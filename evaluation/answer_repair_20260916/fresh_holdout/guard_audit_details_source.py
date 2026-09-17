"""Reproduce the original fresh holdout's operational audit from artifacts only."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE / name).read_text())


def lines(name):
    return [json.loads(line) for line in (HERE / name).read_text().splitlines()]


def role(call):
    fields = set(call.get("options", {}).get("response_format", {}).get("properties", {}))
    if "verdict" in fields:
        return "answer_review"
    if fields == {"mode"} or "needs_personal_facts" in fields:
        return "dependency_review"
    if "model_size" in fields:
        return "compute"
    if fields & {"speech", "answer_parts", "steps_for_user", "instructions", "steps"}:
        return "answer_generation"
    return "unknown"


audit = read("independent_audit.json")
start = read("collection/start.json")
finish = read("collection/finish.json")
summary = read("collection/run/summary.json")
launch = read("collection/launch.json")
rows = lines("collection/run/observations.jsonl")
calls = lines("collection/run/model_calls.jsonl")
telemetry = lines("collection/telemetry.jsonl")
over = [(i, sample) for i, sample in enumerate(telemetry) if sample["swap"]["used_mb"] > 1024]
first_error = next(i for i, call in enumerate(calls) if call["status"] == "error")
assert all(call["error"]["message"] == "telemetry swap ceiling crossed" for call in calls[first_error:])
inputs = ["independent_audit.json", "collection/start.json", "collection/finish.json",
          "collection/run/summary.json", "collection/launch.json", "collection/run/observations.jsonl",
          "collection/run/model_calls.jsonl", "collection/telemetry.jsonl", Path(__file__).name]
result = {
    "created_at": datetime.now(timezone.utc).isoformat(),
    "scope": "Original fresh holdout only. Read-only artifact audit; no device or model calls, no changed source, settings, or guards.",
    "operational_success": finish["complete"],
    "evaluation_complete": audit["evaluation_complete"],
    "all_planned_observations_recorded": len(rows) == 16,
    "checks_passed": audit["checks_passed"],
    "checks_failed": audit["checks_failed"],
    "failed_checks": [check for check in audit["checks"] if not check["passed"]],
    "integrity_interpretation": "Both failed audit checks describe the retained resource-guard failure. Source, tests, corpus, sealed collection, judgments, metric arithmetic, model identities, empty memory, and cleanup checks pass.",
    "guard_failure": finish["failure"],
    "guard_violation": finish["guard_violation"],
    "start_utc": start["captured_at"],
    "finish_utc": finish["snapshot"]["captured_at"],
    "snapshot_interval_seconds": (datetime.fromisoformat(finish["snapshot"]["captured_at"]) - datetime.fromisoformat(start["captured_at"])).total_seconds(),
    "runner_wall_seconds": summary["wall_ns"] / 1e9,
    "start_available_kib": start["memory"]["mem_available_kib"],
    "start_swap_used_kib": start["memory"]["swap_used_kib"],
    "start_max_temperature_c": max(start["temperatures_c"].values()),
    "runtime_swap_ceiling_kib": launch["policy"]["max_runtime_swap_used_kib"],
    "telemetry": {
        "samples": len(telemetry),
        "duration_seconds": (telemetry[-1]["monotonic_ns"] - telemetry[0]["monotonic_ns"]) / 1e9,
        "minimum_total_minus_used_ram_mib": min(sample["ram"]["total_mb"] - sample["ram"]["used_mb"] for sample in telemetry),
        "maximum_swap_used_mib": max(sample["swap"]["used_mb"] for sample in telemetry),
        "maximum_temperature_c": max(value for sample in telemetry for value in sample["temperatures_c"].values()),
        "over_swap_ceiling_samples": len(over),
        "first_over_swap_ceiling_sample_index_1_based": over[0][0] + 1,
        "first_over_swap_ceiling_monotonic_ns": over[0][1]["monotonic_ns"],
        "first_over_swap_ceiling_seconds_after_first_sample": (over[0][1]["monotonic_ns"] - telemetry[0]["monotonic_ns"]) / 1e9,
        "memory_measurement_note": "Tegrastats total-minus-used RAM is not /proc/meminfo MemAvailable. Samples bound the observed telemetry crossing; no exact unsampled onset is inferred.",
    },
    "attempt_accounting": {
        "recorded_client_attempts": len(calls),
        "successful_recorded_model_results": sum(call["status"] == "ok" for call in calls),
        "recorded_errors": sum(call["status"] == "error" for call in calls),
        "by_role": dict(Counter(role(call) for call in calls)),
        "first_guard_error_case": calls[first_error]["case_id"],
        "first_guard_error_role": role(calls[first_error]),
        "first_guard_error_call_wall_seconds": calls[first_error]["wall_ns"] / 1e9,
        "subsequent_latched_error_attempts": len(calls) - first_error - 1,
        "interpretation": "Case 001 recorded one successful raw generation, then its answer-review attempt returned the swap-guard error. Its retry and all subsequent recorded attempts returned the latched error. These client attempts are not 25 successful backend inferences; no review result or model-generated delivery survived the guard. Frozen TransparentGuardedClient checks the guard before entering the backend and after it returns.",
    },
    "per_case_outcomes": [{"id": row["id"], "status": row["status"], "wall_seconds": row["wall_ns"] / 1e9,
                           "recorded_client_attempts": len(row["calls"]), "error": row.get("error"),
                           "delivered_text": row.get("delivered_text")} for row in rows],
    "measured_counts": audit["arithmetic"]["counts"],
    "planned_denominator": 16,
    "delivered_model_generated_answers": audit["arithmetic"]["latency"]["delivered_model_generated"]["n"],
    "latency": audit["arithmetic"]["latency"],
    "quality_interpretation": "0/16 delivered tasks passed under this failed device run. This does not estimate model answer quality under a clean operational run. All eight errors and eight generic application clarifications remain in the planned denominator.",
    "latency_interpretation": "The median and p95 include rapid guard rejections and generic fallback returns. They must not be used as successful-answer responsiveness or a speedup headline. No delivered generated answer or quality-pass latency exists for this attempt.",
    "cleanup_errors": finish["cleanup_errors"],
    "final_resident_models": finish["snapshot"]["resident_models"],
    "final_swap_used_kib": finish["snapshot"]["memory"]["swap_used_kib"],
    "final_available_kib": finish["snapshot"]["memory"]["mem_available_kib"],
    "artifact_sha256": {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in inputs},
}
with (HERE / "guard_audit_details.json").open("x", encoding="utf-8") as stream:
    json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
    stream.write("\n")
print(json.dumps({key: result[key] for key in ("checks_passed", "checks_failed", "operational_success", "evaluation_complete", "measured_counts")}, indent=2))
