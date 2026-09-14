"""Independent offline arithmetic, grouping, provenance and host-state audit.

Uses only Python's standard library and saved artifacts. It imports no model,
execution or analysis code and performs no semantic regrading. Output is new.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import hmac
import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = Path(__file__).resolve().parent
SUCCESS = {"complete": "supported", "appropriate_abstention": "abstain", "appropriate_uncertainty": "uncertain"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def equal_number(left, right):
    check(math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-8), f"numeric mismatch: {left}, {right}")


def distribution(values):
    values = sorted(values)
    def percentile(q):
        position = (len(values) - 1) * q
        lower, upper = math.floor(position), math.ceil(position)
        return values[lower] + (values[upper] - values[lower]) * (position - lower)
    return {"n": len(values), "mean": math.fsum(values) / len(values), "p50": percentile(.5),
            "p95": percentile(.95), "min": values[0], "max": values[-1], "sum": math.fsum(values)}


def audit():
    analysis, tables = EXPERIMENT / "analysis_v2_reviewed", EXPERIMENT / "report_v2"
    freeze_path = EXPERIMENT / "frozen_v2/freeze.json"
    frozen, report, state = read(freeze_path), read(analysis / "analysis.json"), read(EXPERIMENT / "final_state_v2.json")
    workload = read(EXPERIMENT / "frozen_v2/workload.json")
    manifest, metrics = read(analysis / "review_manifest.json"), jsonl(analysis / "row_metrics.jsonl")
    mapping, worksheet = jsonl(analysis / "blinded_mapping.jsonl"), jsonl(analysis / "blinded_review.jsonl")
    quality, run_root = report["semantic_review"], Path(report["run_root"])
    check(sha(freeze_path) == report["freeze_sha256"] == state["freeze_sha256"], "freeze digest mismatch")
    check(sha(EXPERIMENT / "frozen_v2/workload.json") == report["workload_sha256"] == frozen["workload_sha256"], "workload digest mismatch")
    check(report["complete"] and report["integrity_valid"] and report["integrity_errors"] == [], "analysis is not complete and valid")
    check(state["valid"] and all(value is True for value in state["checks"].values()), "final host audit is not valid")
    check(state["source_sha256"] == frozen["source_sha256"], "final source map mismatch")
    for relative, expected in frozen["source_sha256"].items():
        check(sha(ROOT / relative) == sha(EXPERIMENT / "frozen_v2/source" / relative) == expected, f"source changed: {relative}")
    for model, metadata in frozen["models"].items():
        check(all(state["models"][model][key] == value for key, value in metadata.items()), "final model metadata changed")
    check(state["ollama_version"] == frozen["ollama_version"], "final server version changed")
    before, raw, per_session = read(run_root / "before.json"), [], {}
    for session in report["sessions"]:
        path = run_root / session["directory"]
        records, finish = jsonl(path / "observations.jsonl"), read(path / "finish.json")
        check(len(records) == 48 and len({row["id"] for row in records}) == 48, "session count or uniqueness mismatch")
        check([row["id"] for row in records] == [row["id"] for row in workload["execution_cases"]], "case order mismatch")
        check(all(row["arm"] == session["arm"] and row["repetition"] == session["repetition"] and row["index"] == index
                  for index, row in enumerate(records, 1)), "slot identity mismatch")
        for name, expected in session["artifact_sha256"].items():
            check(sha(path / name) == expected, f"session artifact changed: {path.name}/{name}")
        check(session["valid"] and session["complete"] and not session["errors"], "session analysis failed")
        check(finish["status"] == "complete_with_errors" and finish["resident_models"] == [] and finish["cleanup_errors"] == [], "terminal cleanup mismatch")
        check(all(finish[key] is True for key in ("source_unchanged", "model_metadata_unchanged", "ollama_version_unchanged")), "terminal verification failed")
        check(finish["source_sha256"] == frozen["source_sha256"] and finish["guard_violation"] is None
              and finish["telemetry_reader_error"] is None, "terminal source/guard mismatch")
        check(all(finish[key] == before[key] for key in ("boot_id", "power_mode", "thermal_trip_events")), "terminal device state changed")
        raw.extend(records)
        per_session[(session["arm"], session["repetition"])] = records
    raw_by = {(row["arm"], row["repetition"], row["id"]): row for row in raw}
    check(len(raw) == len(raw_by) == len(metrics) == 432, "complete observation coverage mismatch")
    for row in metrics:
        original = raw_by[(row["arm"], row["repetition"], row["case_id"])]
        check(row["status"] == original["status"] and row["delivered"] == (original["status"] == "ok"), "metric delivery state differs")
        equal_number(row["wall_seconds"], original["wall_ns"] / 1e9)
    reviews = {}
    for relative, expected in report["semantic_review_input_sha256"].items():
        path = ROOT / relative
        check(sha(path) == expected, "review input changed")
        for opinion in jsonl(path):
            check(opinion["review_id"] not in reviews, "duplicate resolved review ID")
            reviews[opinion["review_id"]] = opinion
    check(len(reviews) == len(worksheet) == len(mapping) == quality["resolved_unique_outputs"] == quality["observed_unique_outputs"] == 145, "review-group coverage mismatch")
    check(quality["reviewer_types"] == ["assistant"] and not quality["human_validation_complete"]
          and not quality["pending_unique_output_ids"] and not quality["conflicting_review_ids"], "review status differs")
    key, groups = bytes.fromhex(manifest["private_blinding_seed"]), defaultdict(set)
    for row in raw:
        delivered = row["status"] == "ok"
        identity = {"case_id": row["id"], "delivered": delivered, "response": row.get("response") if delivered else None}
        if delivered:
            memory = row.get("memory") or {}
            known, supplied = "supplied_ids" in memory, set(memory.get("supplied_ids", []))
            if not known:
                for call in row["calls"]:
                    if call["purpose"] != "generation":
                        continue
                    schema = (((call.get("response_format") or {}).get("properties") or {}).get("memory_used") or {})
                    identifiers = (schema.get("items") or {}).get("enum")
                    if isinstance(identifiers, list):
                        known = True
                        supplied.update(identifiers)
                    elif schema.get("maxItems") == 0:
                        known = True
            identity["supplied_memory_ids"] = sorted(supplied) if known else None
        review_id = "review_" + hmac.new(key, canonical(identity), "sha256").hexdigest()[:24]
        groups[review_id].add((row["arm"], row["repetition"], row["id"]))
    check(set(groups) == set(reviews) == {row["review_id"] for row in worksheet}, "HMAC grouping differs")
    scores = {}
    for group in mapping:
        review_id = group["review_id"]
        observed = {(row["arm"], row["repetition"], row["case_id"]) for row in group["observations"]}
        check(observed == groups[review_id] and len(observed) == len(group["observations"]), "mapped observations differ")
        opinion = reviews[review_id]
        expected = {key: opinion[key] for key in ("reviewer_type", "reviewer_id", "judgment", "unsupported_personal_claim", "forbidden_or_stale_claim", "notes")}
        check(all(value == expected for value in quality["review_opinions"][review_id]), "stored review opinion differs")
        for identity in observed:
            row, good = raw_by[identity], opinion["judgment"] in SUCCESS
            check((opinion["judgment"] == "technical_failure") == (row["status"] != "ok"), "non-delivery judgment mismatch")
            if good:
                check(row["status"] == "ok" and not opinion["unsupported_personal_claim"] and not opinion["forbidden_or_stale_claim"], "invalid successful judgment")
                check(workload["rubrics"][row["id"]]["mode"] == SUCCESS[opinion["judgment"]], "success/rubric mode mismatch")
            scores[identity] = good
    arms = {}
    for arm in ("small", "large", "cascade"):
        selected = [row for row in raw if row["arm"] == arm]
        delivered, failed = [row for row in selected if row["status"] == "ok"], [row for row in selected if row["status"] != "ok"]
        aggregate, graded = report["arms"][arm], quality["arms"][arm]
        correct = sum(value for identity, value in scores.items() if identity[0] == arm)
        check(len(selected) == graded["reviewed_attempts"] == 144 and correct == graded["correct_reviewed"], "quality denominator/numerator mismatch")
        check(len(delivered) == aggregate["delivered"] and len(failed) == aggregate["technical_failures"], "delivery totals mismatch")
        for label, population in (("latency_all_seconds", selected), ("latency_delivered_seconds", delivered), ("latency_failed_seconds", failed)):
            for field, value in distribution([row["wall_ns"] / 1e9 for row in population]).items():
                equal_number(value, aggregate[label][field])
        for stratum in {row["stratum"] for row in selected}:
            subset = [row for row in selected if row["stratum"] == stratum]
            check(len(subset) == 36 and sum(scores[(arm, row["repetition"], row["id"])] for row in subset)
                  == graded["by_stratum"][stratum]["correct_reviewed"], "stratum counts mismatch")
        counts = Counter(call["purpose"] for row in selected for call in row["calls"])
        requested = Counter(call["requested_model"] for row in selected for call in row["calls"])
        actual = Counter(call["actual_model"] for row in selected for call in row["calls"] if call["purpose"] == "generation")
        check(counts == {"memory_selector": 99, "generation": 144}, "actual call counts differ")
        if arm != "cascade":
            check(set(requested) == {"qwen3:0.6b" if arm == "small" else "qwen3:1.7b"}, "fixed arm called another model")
        loading = sum((call.get("generation") or call.get("raw_generation"))["load_duration_ns"] for row in selected for call in row["calls"]) / 1e9
        equal_number(loading, aggregate["ollama_load_seconds"]["sum"])
        rounds = [sum(scores[(arm, repetition, row["id"])] for row in per_session[(arm, repetition)]) for repetition in (1, 2, 3)]
        check(rounds == [graded["by_repetition"][str(rep)]["correct_reviewed"] for rep in (1, 2, 3)], "round quality differs")
        curve = report["deadline_quality_curve"]["arms"][arm]
        good_times = sorted(row["wall_ns"] / 1e9 for row in selected if scores[(arm, row["repetition"], row["id"])] and row["status"] == "ok")
        for point in curve["points"]:
            count = bisect_right(good_times, point["deadline_seconds"])
            check(count == point["correct_delivered_count"], "deadline count mismatch")
            equal_number(count / 144, point["fraction_of_planned"])
        arms[arm] = {"attempts": 144, "correct": correct, "delivered": len(delivered), "failed": len(failed),
                     "correct_by_round": rounds, "mean_s": aggregate["latency_all_seconds"]["mean"],
                     "p50_s": aggregate["latency_all_seconds"]["p50"], "p95_s": aggregate["latency_all_seconds"]["p95"],
                     "actual_generator_calls": dict(actual), "backend_loading_s": loading}
    for snapshot in (state["snapshot"], state["batch_finish"]["snapshot"]):
        check(snapshot["resident_models"] == [] and snapshot["fan_pwm"] > 0, "final residency/fan failed")
        check(all(snapshot[name] == before[name] for name in ("boot_id", "power_mode", "thermal_trip_events")), "final host state changed")
        check(not any(snapshot["thermal_trip_events"].values()) and snapshot["memory"]["swap_total_kib"] == 3901608, "final trip/swap state changed")
    check(len(state["sessions"]) == len(state["batch_finish"]["sessions"]) == 9 and state["batch_finish"]["failure"] is None, "final batch incomplete")
    check(sha(run_root / "batch_finish.json") == state["batch_finish_sha256"], "final batch hash mismatch")
    for entry in state["sessions"]:
        path = run_root / entry["session"]
        check(sha(path / "finish.json") == entry["finish_sha256"] and sha(path / "summary.json") == entry["summary_sha256"], "final session digest mismatch")
    check(len(state["swap_topology"]) == 6 and sum(item["size_kib"] for item in state["swap_topology"]) == 3901608
          and all(item["device"].startswith("/dev/zram") for item in state["swap_topology"]), "logical zram topology mismatch")
    correction = report["analysis_compatibility_correction"]
    check(sha(analysis / correction["adapter_archive"]) == correction["adapter_sha256"]
          and sha(analysis / correction["dependency_archive"]) == correction["dependency_sha256"], "analysis adapter archive mismatch")
    resume = report["resume_provenance"]
    check(resume["valid"] and resume["errors"] == [] and resume["retained_complete_session_count"] == 2
          and len(resume["original_errors_before_wording_compatibility"]) == 1, "resume correction scope differs")
    for proof in resume["revised_temperature_wording_proofs"]:
        path = Path(proof["path"])
        check(proof["measured_start_max_temperature_c"] == max(read(path / "start.json")["temperatures_c"].values()) >= 55, "rejection temperature proof differs")
        for name, expected in proof["artifact_sha256"].items():
            check(sha(path / name) == expected, "startup rejection artifact changed")
        check(not any((path / name).exists() for name in proof["absence_checked"]), "excluded startup contains inference evidence")
    provenance = read(tables / "provenance.json")
    for name, expected in provenance["input_sha256"].items():
        check(sha(analysis / name) == expected, "renderer input changed")
    for name, expected in provenance["output_sha256"].items():
        check(sha(tables / name) == expected, "rendered output changed")
    check(sha(EXPERIMENT / "render_v2_report.py") == provenance["renderer_sha256"], "renderer source changed")
    agreement = read(EXPERIMENT / "reviews_v2/review_agreement_v2.json")
    for name, expected in agreement["input_sha256"].items():
        check(sha(EXPERIMENT / "reviews_v2" / name) == expected, "review-agreement input changed")
    agreed = total = 0
    for cohort in (1, 2, 3, 5, 6):
        first = {item["review_id"]: item for item in jsonl(EXPERIMENT / f"reviews_v2/reviewer_a_cohort{cohort}.jsonl")}
        second = {item["review_id"]: item for item in jsonl(EXPERIMENT / f"reviews_v2/reviewer_b_cohort{cohort}.jsonl")}
        check(first.keys() == second.keys(), "initial reviewer coverage mismatch")
        total += len(first)
        agreed += sum(all(first[key][field] == second[key][field] for field in agreement["comparison_fields"]) for key in first)
    check(total == 145 and agreed == agreement["initial_exact_label_and_flag_agreement"] == 142, "initial reviewer agreement mismatch")
    inputs = [analysis / name for name in ("analysis.json", "row_metrics.jsonl", "blinded_mapping.jsonl", "blinded_review.jsonl", "review_manifest.json")]
    inputs += [freeze_path, tables / "provenance.json", tables / "tables.md", EXPERIMENT / "final_state_v2.json", EXPERIMENT / "reviews_v2/review_agreement_v2.json"]
    return {"schema_version": 1, "recorded_at": datetime.now(timezone.utc).isoformat(), "valid": True,
            "audit_script_sha256": sha(Path(__file__)), "scope": "Independent saved-artifact arithmetic/grouping/hash audit; no model calls, no semantic regrading, no existing files changed",
            "input_sha256": {str(path.relative_to(ROOT)): sha(path) for path in inputs},
            "observed_attempts": 432, "review_groups": 145, "initial_reviewer_agreement": {"agreed": 142, "total": 145},
            "frozen_source_files_checked": len(frozen["source_sha256"]), "arms": arms,
            "checks": {key: True for key in ("raw_observation_uniqueness", "review_group_hmac_and_evidence_identity", "all_attempt_review_coverage", "quality_and_stratum_counts", "latency_quantiles_and_loading", "sole_model_controls", "deadline_curve_counts", "raw_and_rendered_hashes", "frozen_sources_and_final_model_metadata", "final_cleanup_and_host_state", "resume_correction_proofs", "initial_reviewer_agreement")},
            "interpretation": ["All numbers agree with the reviewed report.", "The cascade's pooled latency advantage over large-only reverses in rounds 2 and 3 and does not isolate a causal routing gain.", "Cascade made 141 large and 3 small generator calls; observed loading cost exceeded large-only.", "Assistant-only judgments on 48 requests repeated three times do not establish independent human validation or 144 independent samples."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit()
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({"valid": result["valid"], "observed_attempts": result["observed_attempts"],
                      "review_groups": result["review_groups"], "output": str(args.output.resolve())}), flush=True)


if __name__ == "__main__":
    main()
