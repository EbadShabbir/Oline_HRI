"""Aggregate fixed manual judgments for the completed focused check."""
import hashlib
import json
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
BASE = OUT.parent
ROOT = BASE.parent.parent
RUN = BASE / "quality_learned_v3"
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def stage(call):
    props = call.get("options", {}).get("response_format", {}).get("properties", {})
    return next((value for key, value in (("speech", "answer_generation"),
                ("verdict", "answer_review"), ("needs_personal_facts", "dependency_review"),
                ("model_size", "model_size")) if key in props), "other")


def latency(rows):
    values = [row["wall_seconds"] for row in rows]
    return {"count": len(values), "median_seconds": statistics.median(values) if values else None,
            "minimum_seconds": min(values) if values else None,
            "maximum_seconds": max(values) if values else None}


corpus = read(BASE / "quality_cases_v3.json")
cases = corpus["cases"]
freeze = read(BASE / "candidate_freeze_v3/freeze.json")
metadata = read(RUN / "metadata.json")
run_summary = read(RUN / "summary.json")
observations = [json.loads(line) for line in (RUN / "observations.jsonl").read_text().splitlines()]
manual = read(OUT / "manual_judgments.json")
assert len(cases) == len(observations) == len(manual) == run_summary["completed"] == 8
assert sha(BASE / "quality_cases_v3.json") == metadata["cases_sha256"]
assert [c["id"] for c in cases] == [r["id"] for r in observations]
rows = []
all_counts = Counter()
for raw, case in zip(observations, cases):
    assert raw["case"] == case
    reply, route = raw["reply"], raw["route"]
    prediction = route["classifier_metadata"]["whole_request"]
    counts = Counter(stage(call) for call in raw["calls"])
    all_counts.update(counts)
    judgment = manual[case["id"]]
    attempts = [{"index": index, "model": attempt["model"], "raw_content": attempt["content"],
                 "accepted_as_response_component": attempt == reply["generation"],
                 "confirmed_unsupported_personal_fact": index in judgment["confirmed_unsupported_raw_personal_attempts"],
                 "confirmed_unsupported_deployment_guidance": index in judgment["confirmed_unsupported_raw_deployment_guidance_attempts"]}
                for index, attempt in enumerate(reply["attempts"])]
    row = {
        "schema_version": "focused_quality_independent_review_v3", "id": case["id"], "case": case,
        "status": raw["status"], "raw_predicted_mode": prediction["predicted_mode"],
        "thresholded_mode": prediction["mode"], "final_dependency": route["dependency"],
        "effective_execution_mode": reply["effective_mode"],
        "raw_label_match": prediction["predicted_mode"] in case["expected_modes"],
        "final_label_match": route["dependency"]["mode"] in case["expected_modes"],
        "uncertainty": {k: prediction[k] for k in ("scores", "margin", "threshold", "uncertain")},
        "dependency_review": route["review_generation"], "dependency_review_reason": route["review_reason"],
        "exact_delivered_text": raw["delivered_text"], "wall_seconds": raw["wall_ns"] / 1e9,
        "application_only_output": reply["generation"] is None,
        "raw_attempts": attempts, "raw_review_attempts": reply["review_attempts"],
        "answer_reviews": reply["answer_reviews"], "quality_issues": reply["quality_issues"],
        "actual_call_counts": dict(counts),
        "all_call_bounds_pass": counts["answer_generation"] <= 2 and counts["answer_review"] <= 2 and counts["dependency_review"] <= 1,
        "all_transport_calls_ok": all(c["status"] == "ok" for c in raw["calls"]),
        "admitted_history_messages": raw["admitted_history_messages"], "retrieval_status": reply["retrieval_status"],
        "memory_diagnostics": reply["memory_diagnostics"], "response_memory_ids": reply["response"]["memory_used"],
        "application_memory_ids": reply["application_memory_ids"], **judgment,
    }
    row["strict_all_parts_pass"] = row["final_label_match"] and row["independent_behavior_pass"]
    rows.append(row)
(OUT / "review_rows.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))

optional = [r for r in rows if r["case"]["expected_modes"] == ["optional"]]
general = [r for r in rows if r["case"]["expected_modes"] == ["none"]]
recorded_mismatches = [p for p, h in metadata["source_sha256"].items() if freeze["source_sha256"].get(p) != h]
archive = BASE / "candidate_freeze_v3/source"
archived_mismatches = [p for p, h in freeze["source_sha256"].items() if not (archive / p).exists() or sha(archive / p) != h]
assert not recorded_mismatches and not archived_mismatches
summary = {
    "schema_version": "focused_quality_independent_review_v3", "created_at": datetime.now(timezone.utc).isoformat(),
    "scope": "Focused eight-case check, not a new full routing release, representative sample, or factual benchmark.",
    "cases_requested": 8, "cases_completed": len(rows), "runner_failure": run_summary["failure"],
    "cleanup_error": run_summary["cleanup_error"],
    "raw_dependency_matches": sum(r["raw_label_match"] for r in rows),
    "final_dependency_matches": sum(r["final_label_match"] for r in rows),
    "independent_behavior_passes": sum(r["independent_behavior_pass"] for r in rows),
    "strict_all_parts_passes": sum(r["strict_all_parts_pass"] for r in rows),
    "delivery_grades": dict(Counter(r["delivery_grade"] for r in rows)),
    "primary_delivered_forms": dict(Counter(r["primary_delivered_form"] for r in rows)),
    "review_check_counts": dict(Counter(c["result"] for r in rows for c in r["criterion_results"])),
    "flags": {key: sum(r["flags"][key] for r in rows) for key in rows[0]["flags"]},
    "optional": {"count": len(optional), "complete": sum(r["delivery_grade"] == "complete" for r in optional),
                 "strict_all_parts_passes": sum(r["strict_all_parts_pass"] for r in optional)},
    "general_and_positive_controls": {"count": len(general), "complete": sum(r["delivery_grade"] == "complete" for r in general),
                 "strict_all_parts_passes": sum(r["strict_all_parts_pass"] for r in general)},
    "authorization": {"unsupported_delivered_personal_facts": sum(r["flags"]["unsupported_personal_fact"] for r in rows),
                      "unsupported_delivered_deployment_or_action_guidance": sum(r["flags"]["unsupported_deployment_or_action_claim"] for r in rows),
                      "claimed_performed_physical_actions": sum(r.get("claimed_physical_action", False) for r in rows),
                      "raw_guard_false_positive_concern_cases": [r["id"] for r in rows if r.get("raw_guard_false_positive_concern")],
                      "withheld_attempts": sum(not a["accepted_as_response_component"] for r in rows for a in r["raw_attempts"]),
                      "confirmed_unsupported_raw_personal_attempts": sum(a["confirmed_unsupported_personal_fact"] for r in rows for a in r["raw_attempts"]),
                      "confirmed_unsupported_raw_deployment_guidance_attempts": sum(a["confirmed_unsupported_deployment_guidance"] for r in rows for a in r["raw_attempts"])},
    "actual_call_counts": dict(all_counts), "all_call_bounds_pass": all(r["all_call_bounds_pass"] for r in rows),
    "actual_retry_cases": [r["id"] for r in rows if r["actual_call_counts"].get("answer_generation", 0) > 1],
    "model_review_passes_with_independent_failure": [r["id"] for r in rows if r["answer_reviews"] and not r["independent_behavior_pass"]],
    "latency": {"generated_deliveries": latency([r for r in rows if not r["application_only_output"]]),
                "application_only_outputs": latency([r for r in rows if r["application_only_output"]]),
                "runner_seconds": run_summary["wall_ns"] / 1e9,
                "scope": "Sequential local observed latency including loading. Root reports heavy tests finished before replay. Not a general performance benchmark."},
    "integrity": {"freeze_sha256": sha(BASE / "candidate_freeze_v3/freeze.json"),
                  "corpus_sha256": sha(BASE / "quality_cases_v3.json"), "plan_sha256": sha(OUT / "review_plan_v1.md"),
                  "metadata_sha256": sha(RUN / "metadata.json"),
                  "run_summary_sha256": sha(RUN / "summary.json"),
                  "observations_sha256": sha(RUN / "observations.jsonl"), "model_calls_sha256": sha(RUN / "model_calls.jsonl"),
                  "recorded_source_mismatches": recorded_mismatches, "archived_source_mismatches": archived_mismatches,
                  "end_of_run_verification": read(OUT / "end_of_run_verification.json")},
    "limitations": ["Manual reviewer knew earlier failures and contributed safeguards; not an external blind panel.",
                    "Empty canonical store and finite examples cannot establish universal personal-evidence or public-factual correctness.",
                    "All predeclared count/content criteria remain unchanged; model review is not the independent judgment.",
                    "No microphone or speech-transcription stage was exercised."]}
summary["conclusion"] = "PASS for this focused check only" if summary["strict_all_parts_passes"] == 8 else "FAIL: focused criteria not met on every case"
(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(summary, ensure_ascii=False, indent=2))
