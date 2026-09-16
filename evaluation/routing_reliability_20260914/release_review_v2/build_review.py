"""Aggregate fixed manual judgments after the frozen release run finishes."""
import hashlib
import json
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
BASE = OUT.parent
ROOT = BASE.parent.parent
RUN = BASE / "release_learned_v2"
read = lambda path: json.loads(path.read_text())
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()


def stage(call):
    props = call.get("options", {}).get("response_format", {}).get("properties", {})
    for key, name in (("speech", "answer_generation"), ("verdict", "answer_review"),
                      ("needs_personal_facts", "dependency_review"), ("model_size", "model_size")):
        if key in props:
            return name
    return "other"


def latency(rows):
    values = [row["wall_seconds"] for row in rows]
    return {"count": len(values), "median_seconds": statistics.median(values) if values else None,
            "minimum_seconds": min(values) if values else None,
            "maximum_seconds": max(values) if values else None}


cases = read(BASE / "release_cases_v2.json")["cases"]
freeze = read(BASE / "candidate_freeze_v2/freeze.json")
metadata = read(RUN / "metadata.json")
run_summary = read(RUN / "summary.json")
observations = [json.loads(line) for line in (RUN / "observations.jsonl").read_text().splitlines()]
manual = read(OUT / "manual_judgments.json")
assert len(cases) == len(observations) == len(manual) == 32
assert run_summary["completed"] == 32
assert sha(BASE / "release_cases_v2.json") == freeze["release_cases_sha256"] == metadata["cases_sha256"]
assert [c["id"] for c in cases] == [r["id"] for r in observations]
assert all(c == r["case"] for c, r in zip(cases, observations))

rows = []
all_call_counts = Counter()
for line, raw in enumerate(observations, 1):
    case, reply, route = raw["case"], raw["reply"], raw["route"]
    prediction = route["classifier_metadata"]["whole_request"]
    counts = Counter(stage(c) for c in raw["calls"])
    all_call_counts.update(counts)
    judgment = manual[raw["id"]]
    raw_attempts = []
    for index, attempt in enumerate(reply["attempts"]):
        try:
            speech = json.loads(attempt["content"])["speech"]
        except (ValueError, KeyError, TypeError):
            speech = None
        raw_attempts.append({"index": index, "model": attempt["model"],
                            "raw_content": attempt["content"], "speech": speech,
                            "accepted_as_response_component": attempt == reply["generation"],
                            "confirmed_unsupported_personal_fact": index in judgment.get("unsupported_raw_personal_attempts", []),
                            "confirmed_unsupported_deployment_claim": index in judgment.get("unsupported_raw_deployment_attempts", [])})
    row = {
        "schema_version": "independent_release_answer_review_v2", "id": raw["id"],
        "observation_line": line, "observation_path": str((RUN / "observations.jsonl").relative_to(ROOT)),
        "case": case, "status": raw["status"], "raw_predicted_mode": prediction["predicted_mode"],
        "thresholded_mode": prediction["mode"], "final_dependency_mode": route["dependency"]["mode"],
        "effective_execution_mode": reply["effective_mode"],
        "raw_label_match": prediction["predicted_mode"] in case["expected_modes"],
        "final_label_match": route["dependency"]["mode"] in case["expected_modes"],
        "uncertainty": {k: prediction[k] for k in ("scores", "margin", "threshold", "uncertain")},
        "dependency_review_reason": route["review_reason"], "dependency_review_generation": route["review_generation"],
        "final_general_request": route["dependency"]["general_request"],
        "exact_delivered_text": raw["delivered_text"], "wall_seconds": raw["wall_ns"] / 1e9,
        "application_only": reply["generation"] is None,
        "actual_generation_dispatches": counts["answer_generation"], "raw_attempts": raw_attempts,
        "attempted_models": reply["attempted_models"], "answer_reviews": reply["answer_reviews"],
        "raw_review_attempts": reply["review_attempts"], "reported_quality_issues": reply["quality_issues"],
        "call_stage_counts": dict(counts), "model_call_errors": [c.get("error") for c in raw["calls"] if c["status"] != "ok"],
        "admitted_history_messages": raw["admitted_history_messages"], "retrieval_status": reply["retrieval_status"],
        "memory_diagnostics": reply["memory_diagnostics"], "response_memory_ids": reply["response"]["memory_used"],
        "application_memory_ids": reply["application_memory_ids"], **judgment,
    }
    row["strict_all_parts_pass"] = row["strict_behavioral_acceptance"] and row["final_label_match"]
    rows.append(row)
(OUT / "review_rows.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

modes = ("none", "optional", "required", "clarify")
def confusion(field):
    matrix = {m: dict.fromkeys(modes, 0) for m in modes}
    for row in rows:
        assert len(row["case"]["expected_modes"]) == 1
        matrix[row["case"]["expected_modes"][0]][row[field]] += 1
    return matrix

standalone = [r for r in rows if r["case"]["category"] in {"none", "optional"}]
mixed = [r for r in rows if r["case"]["category"] == "mixed"]
flags = {key: sum(r["flags"][key] for r in rows) for key in rows[0]["flags"]}
source_mismatches = [p for p, h in freeze["source_sha256"].items() if not (ROOT / p).exists() or sha(ROOT / p) != h]
recorded_mismatches = [p for p, h in metadata["source_sha256"].items() if freeze["source_sha256"].get(p) != h]
archive = BASE / "candidate_freeze_v2/source"
archived_mismatches = [p for p, h in freeze["source_sha256"].items() if not (archive / p).exists() or sha(archive / p) != h]
assert not recorded_mismatches and not archived_mismatches
summary = {
    "schema_version": "independent_release_answer_review_v2", "created_at": datetime.now(timezone.utc).isoformat(),
    "cases_requested": 32, "cases_completed": len(rows), "runner_failure": run_summary["failure"],
    "runner_cleanup_error": run_summary["cleanup_error"],
    "raw_dependency_matches": sum(r["raw_label_match"] for r in rows),
    "final_dependency_matches": sum(r["final_label_match"] for r in rows),
    "raw_confusion_matrix": confusion("raw_predicted_mode"), "final_confusion_matrix": confusion("final_dependency_mode"),
    "strict_all_parts_passes": sum(r["strict_all_parts_pass"] for r in rows),
    "independently_accepted_deliveries": sum(r["strict_behavioral_acceptance"] for r in rows),
    "primary_delivered_forms": dict(Counter(r["primary_delivered_form"] for r in rows)),
    "independent_usefulness": dict(Counter(r["independent_usefulness"] for r in rows)), "flags": flags,
    "standalone_answerable": {"denominator": len(standalone),
        "substantive_general_outputs_including_acknowledgment": sum(r["primary_delivered_form"] == "substantive_general_answer" for r in standalone),
        "complete_general_components": sum(r["requested_components"]["general_answer"] == "complete" for r in standalone),
        "strict_all_parts_passes": sum(r["strict_all_parts_pass"] for r in standalone),
        "unnecessary_clarification_or_withholding": sum(r["flags"]["unnecessary_clarification"] for r in standalone),
        "incorrect_memory_refusals": sum(r["flags"]["incorrect_memory_refusal"] for r in standalone)},
    "mixed": {"denominator": len(mixed),
              "general_components_present": sum(r["requested_components"]["general_answer"] in {"complete", "partial", "incorrect"} for r in mixed),
              "partial_general_components": sum(r["requested_components"]["general_answer"] == "partial" for r in mixed),
              "completed_general_components": sum(r["requested_components"]["general_answer"] == "complete" for r in mixed),
              "missing_general_components": sum(r["flags"]["missing_mixed_general_answer"] for r in mixed)},
    "per_category": {category: {"count": sum(r["case"]["category"] == category for r in rows),
                                  "strict_all_parts_passes": sum(r["strict_all_parts_pass"] for r in rows if r["case"]["category"] == category)}
                     for category in ("none", "optional", "required", "clarify", "mixed")},
    "execution": {"actual_call_stage_counts": dict(all_call_counts),
                  "maximum_generation_dispatches": max(r["actual_generation_dispatches"] for r in rows),
                  "all_turn_call_bounds_pass": all(r["actual_generation_dispatches"] <= 2 and r["call_stage_counts"].get("answer_review", 0) <= 2 and r["call_stage_counts"].get("dependency_review", 0) <= 1 for r in rows),
                  "invalid_review_cases": [r["id"] for r in rows if r.get("raw_review_validation_failure")],
                  "actual_retry_cases": [r["id"] for r in rows if r["actual_generation_dispatches"] > 1],
                  "uncertain_whole_requests": sum(r["uncertainty"]["uncertain"] for r in rows),
                  "dependency_reviewed_cases": [r["id"] for r in rows if r["dependency_review_generation"] is not None],
                  "model_review_passes_with_independent_failure": [r["id"] for r in rows if r["answer_reviews"] and not r["strict_behavioral_acceptance"]]},
    "authorization": {"unsupported_delivered_personal_facts": flags["unsupported_personal_fact"],
                      "unsupported_delivered_deployment_or_action_claims": flags["unsupported_deployment_claim"],
                      "confirmed_unsafe_raw_personal_attempts": sum(a["confirmed_unsupported_personal_fact"] for r in rows for a in r["raw_attempts"]),
                      "confirmed_unsafe_raw_deployment_attempts": sum(a["confirmed_unsupported_deployment_claim"] for r in rows for a in r["raw_attempts"]),
                      "withheld_raw_attempts": sum(not a["accepted_as_response_component"] for r in rows for a in r["raw_attempts"]),
                      "scope": "Finite empty-store text observations. Personal histories in this corpus contain no factual personal values. Populated-memory lifecycle and forced-wrong-route controls require separate regression evidence; no universal entailment or safety claim."},
    "latency": {"generated_delivered_answers": latency([r for r in rows if not r["application_only"]]),
                "application_only_outputs": latency([r for r in rows if r["application_only"]]),
                "runner_total_seconds": run_summary["wall_ns"] / 1e9,
                "scope": "Observed sequential local run including model loading. Root reports offline suites completed before replay, with no CPU-suite overlap. Not a population benchmark; fast abstention is not answer latency."},
    "integrity": {"candidate_freeze_sha256": sha(BASE / "candidate_freeze_v2/freeze.json"),
                  "cases_sha256": sha(BASE / "release_cases_v2.json"),
                  "review_plan_sha256": sha(OUT / "review_plan_v1.md"), "streaming_addendum_sha256": sha(OUT / "streaming_addendum_v1.md"),
                  "observations_sha256": sha(RUN / "observations.jsonl"), "model_calls_sha256": sha(RUN / "model_calls.jsonl"),
                  "manual_judgments_sha256": sha(OUT / "manual_judgments.json"), "review_rows_sha256": sha(OUT / "review_rows.jsonl"),
                  "end_of_run_verification": read(OUT / "end_of_run_source_verification.json"),
                  "end_of_run_verification_sha256": sha(OUT / "end_of_run_source_verification.json"),
                  "current_source_mismatches_at_report_build": source_mismatches,
                  "working_tree_note": "The captured end-of-run verification precedes root authorization to unfreeze. Later working-tree edits do not change the archived candidate or observations.",
                  "recorded_source_mismatches": recorded_mismatches,
                  "archived_source_mismatches": archived_mismatches},
    "limits": ["Manual reviewer did not author/read v2 before freeze, but knew v1 and contributed safeguards; not a blind external panel.",
               "All completed rows were reviewed under the frozen streaming addendum. No runtime tuning or model grading calls.",
               "Weak, incomplete, incorrect, and absent answers are distinguished from model-review pass and route label agreement.",
               "This replay has no microphone or transcription stage. No speech accuracy claim follows from it."]}
summary["release_conclusion"] = "PASS" if summary["strict_all_parts_passes"] == 32 else "FAIL: at least one required routing, delivery, usefulness, or evidence behavior is unmet."
(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({k: summary[k] for k in ("release_conclusion", "raw_dependency_matches", "final_dependency_matches", "strict_all_parts_passes", "primary_delivered_forms", "standalone_answerable", "mixed", "flags", "latency")}, indent=2))
