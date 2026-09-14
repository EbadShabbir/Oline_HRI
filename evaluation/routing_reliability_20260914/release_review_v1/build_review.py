"""Combine fixed manual judgments with frozen observations; no inference or tuning."""
import hashlib
import json
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
BASE = OUT.parent
RUN = BASE / "release_learned_v1"


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(call):
    props = call.get("options", {}).get("response_format", {}).get("properties", {})
    if "speech" in props:
        return "answer_generation"
    if "verdict" in props:
        return "answer_review"
    if "model_size" in props:
        return "model_size_classification"
    return "other"


def latency(rows):
    values = sorted(r["wall_seconds"] for r in rows)
    return {
        "count": len(values),
        "median_seconds": statistics.median(values) if values else None,
        "minimum_seconds": min(values) if values else None,
        "maximum_seconds": max(values) if values else None,
    }


cases = read(BASE / "release_cases_v1.json")
observations = [json.loads(line) for line in (RUN / "observations.jsonl").read_text().splitlines()]
manual = read(OUT / "manual_judgments.json")
freeze = read(BASE / "candidate_freeze_v1/freeze.json")
metadata = read(RUN / "metadata.json")
run_summary = read(RUN / "summary.json")
assert len(cases) == len(observations) == len(manual) == 32
assert [r["id"] for r in cases] == [r["id"] for r in observations]
assert sha(BASE / "release_cases_v1.json") == freeze["cases_sha256"] == metadata["cases_sha256"]
assert all(r["case"] == c for r, c in zip(observations, cases))
assert run_summary["completed"] == 32 and run_summary["failure"] is None

rows = []
call_counts = Counter()
for number, raw in enumerate(observations, 1):
    case = raw["case"]
    route = raw["route"]
    reply = raw["reply"]
    decision = route["classifier_metadata"]["whole_request"]
    calls = raw["calls"]
    per_case_calls = Counter(stage(c) for c in calls)
    call_counts.update(per_case_calls)
    attempts = []
    for attempt in reply["attempts"]:
        payload = json.loads(attempt["content"])
        attempts.append({
            "model": attempt["model"], "raw_content": attempt["content"],
            "speech": payload["speech"], "memory_used": payload["memory_used"],
            "delivered": payload["speech"] == raw["delivered_text"],
            "independently_confirmed_unsupported_personal_fact": False,
            "independently_confirmed_unsupported_deployment_claim": raw["id"] == "release_none_01",
        })
    row = {
        "schema_version": "independent_release_answer_review_v1",
        "id": raw["id"], "observation_line": number,
        "observation_path": str((RUN / "observations.jsonl").relative_to(ROOT)),
        "category": case["category"], "current_request": case["text"],
        "prior_turns": case["prior_turns"], "expected_modes": case["expected_modes"],
        "expected_general_fragment": case["expected_general_fragment"],
        "raw_predicted_mode": decision["predicted_mode"],
        "thresholded_classifier_mode": decision["mode"],
        "final_dependency_mode": route["dependency"]["mode"],
        "effective_execution_mode": reply["effective_mode"],
        "raw_label_match": decision["predicted_mode"] in case["expected_modes"],
        "final_label_match": route["dependency"]["mode"] in case["expected_modes"],
        "uncertainty": {k: decision[k] for k in ("scores", "margin", "threshold", "uncertain")},
        "final_general_fragment": route["dependency"]["general_request"],
        "dependency_review_count": int(route["review_generation"] is not None),
        "dependency_review_reason": route["review_reason"],
        "exact_delivered_text": raw["delivered_text"],
        "status": raw["status"],
        "wall_seconds": raw["wall_ns"] / 1e9,
        "application_only": reply["generation"] is None,
        "generation_attempt_count": len(reply["attempts"]),
        "generation_models": reply["attempted_models"],
        "answer_review_count": len(reply["answer_reviews"]),
        "raw_review_attempt_count": len(reply["review_attempts"]),
        "answer_reviews": [{"verdict": r["verdict"], "reason": r["reason"],
                            "model": r["generation"]["model"]} for r in reply["answer_reviews"]],
        "reported_quality_issues": reply["quality_issues"],
        "raw_attempts": attempts,
        "model_call_stage_counts": dict(per_case_calls),
        "model_call_errors": [c.get("error") for c in calls if c["status"] != "ok"],
        "admitted_history_messages": raw["admitted_history_messages"],
        "retrieval_status": reply["retrieval_status"],
        "memory_diagnostics": reply["memory_diagnostics"],
        "response_memory_ids": reply["response"]["memory_used"],
        "application_memory_ids": reply["application_memory_ids"],
        "delivery_evidence_scope": "No personal records in the isolated store; all delivered memory IDs empty. This run does not exercise deletion races with populated evidence.",
        **manual[raw["id"]],
    }
    assert row["generation_attempt_count"] == per_case_calls["answer_generation"]
    assert row["answer_review_count"] == per_case_calls["answer_review"]
    assert row["generation_attempt_count"] <= 2
    rows.append(row)

(OUT / "review_rows.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
modes = ("none", "optional", "required", "clarify")
def confusion(key):
    matrix = {expected: {actual: 0 for actual in modes} for expected in modes}
    for row in rows:
        assert len(row["expected_modes"]) == 1
        matrix[row["expected_modes"][0]][row[key]] += 1
    return matrix

standalone = [r for r in rows if r["expected_modes"][0] in {"none", "optional"}]
mixed = [r for r in rows if r["expected_general_fragment"]]
required = [r for r in rows if r["expected_modes"] == ["required"] and not r["expected_general_fragment"]]
clarify = [r for r in rows if r["expected_modes"] == ["clarify"]]
flags = {flag: sum(r["flags"][flag] for r in rows) for flag in rows[0]["flags"]}
source_mismatches = [path for path, expected in freeze["source_sha256"].items()
                     if not (ROOT / path).is_file() or sha(ROOT / path) != expected]
recorded_source_mismatches = [path for path, digest in metadata["source_sha256"].items()
                             if freeze["source_sha256"].get(path) != digest]
archive = BASE / "candidate_freeze_v1/source"
archived_source_mismatches = [path for path, expected in freeze["source_sha256"].items()
                            if not (archive / path).is_file() or sha(archive / path) != expected]
assert not archived_source_mismatches and not recorded_source_mismatches
summary = {
    "schema_version": "independent_release_answer_review_v1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "release_conclusion": "FAIL: final dependency, answerability, mixed completion, and answer quality requirements are not met.",
    "cases_requested": 32, "observations_completed": len(rows),
    "raw_dependency_label_matches": sum(r["raw_label_match"] for r in rows),
    "final_dependency_label_matches": sum(r["final_label_match"] for r in rows),
    "raw_confusion_matrix": confusion("raw_predicted_mode"),
    "final_confusion_matrix": confusion("final_dependency_mode"),
    "strict_behavioral_acceptance": sum(r["strict_behavioral_acceptance"] and r["final_label_match"] for r in rows),
    "primary_delivered_forms": dict(Counter(r["primary_delivered_form"] for r in rows)),
    "independent_usefulness": dict(Counter(r["independent_usefulness"] for r in rows)),
    "flags": flags,
    "standalone_answerable": {
        "denominator": len(standalone),
        "some_substantive_general_content": sum(r["primary_delivered_form"] == "substantive_general_answer" for r in standalone),
        "general_component_complete": sum(r["requested_components"]["general_answer"] == "complete" for r in standalone),
        "strict_behavioral_acceptance": sum(r["strict_behavioral_acceptance"] for r in standalone),
        "unnecessary_clarification_or_withholding": sum(r["flags"]["unnecessary_clarification"] for r in standalone),
        "incorrect_personal_memory_refusal": sum(r["flags"]["incorrect_memory_refusal"] for r in standalone),
    },
    "mixed": {"denominator": len(mixed), "general_components_completed": 0,
              "missing_general_components": sum(r["flags"]["missing_mixed_general_answer"] for r in mixed)},
    "required_only": {"denominator": len(required), "appropriate_missing_fact_questions":
                      sum(r["requested_components"]["personal_information_request"] == "complete" for r in required)},
    "unresolved_requests": {"denominator": len(clarify), "appropriate_clarification":
                            sum(r["flags"]["appropriate_clarification"] for r in clarify)},
    "bounded_execution": {
        "uncertain_whole_requests": sum(r["uncertainty"]["uncertain"] for r in rows),
        "uncertain_whole_requests_short_clarification": sum(r["uncertainty"]["uncertain"] and r["final_dependency_mode"] == "clarify" for r in rows),
        "dependency_large_reviews": sum(r["dependency_review_count"] for r in rows),
        "max_actual_generation_attempts": max(r["generation_attempt_count"] for r in rows),
        "actual_retry_cases": [r["id"] for r in rows if r["generation_attempt_count"] > 1],
        "pre_generation_operational_failure_cases": ["release_optional_02"],
        "model_call_stage_counts": dict(call_counts),
        "model_review_passes_with_independent_failure": [r["id"] for r in rows if r["answer_review_count"] and not r["strict_behavioral_acceptance"]],
    },
    "authorization": {
        "unsupported_delivered_personal_facts": flags["unsupported_personal_fact"],
        "unsupported_delivered_deployment_or_action_claims": flags["unsupported_deployment_claim"],
        "unsupported_raw_personal_facts_independently_confirmed": 0,
        "withheld_raw_attempts": sum(not a["delivered"] for r in rows for a in r["raw_attempts"]),
        "false_positive_guard_note": "The withheld first thank-you draft is labeled unsupported_personal_claim by the guard; the manual review does not confirm an actual personal assertion in its hope/conditional/draft wording.",
        "scope": "Finite empty-store observations show no personal-value leak. Populated-memory deletion, correction, expiry, race, and deliberately wrong-route guarantees require the separate regression suite and are not established universally by this run.",
    },
    "latency": {
        "generated_delivered_answers": latency([r for r in rows if not r["application_only"]]),
        "application_only_outputs": latency([r for r in rows if r["application_only"]]),
        "runner_total_seconds": run_summary["wall_ns"] / 1e9,
        "scope": "Observed sequential local run including model loading; concurrent root tests occurred. Fast abstention is not answer latency. Not a controlled benchmark.",
    },
    "integrity": {
        "candidate_freeze_sha256": sha(BASE / "candidate_freeze_v1/freeze.json"),
        "cases_sha256": sha(BASE / "release_cases_v1.json"),
        "review_plan_sha256": sha(OUT / "review_plan_v1.md"),
        "observations_sha256": sha(RUN / "observations.jsonl"),
        "model_calls_sha256": sha(RUN / "model_calls.jsonl"),
        "manual_judgments_sha256": sha(OUT / "manual_judgments.json"),
        "review_rows_sha256": sha(OUT / "review_rows.jsonl"),
        "source_mismatches_at_review_end": source_mismatches,
        "working_tree_note": "Root started the next authorized candidate after the v1 runner completed. Post-run working-tree differences do not replace the archived v1 candidate or recorded run hashes.",
        "archived_source_mismatches_against_freeze": archived_source_mismatches,
        "recorded_source_mismatches_against_freeze": recorded_source_mismatches,
        "runner_cleanup_error": run_summary["cleanup_error"],
    },
    "limits": [
        "Manual review by the original corpus author, who also contributed guard/compatibility work; not a blind external human panel.",
        "No new model calls or external factual research were used for grading.",
        "Weak dinner and keyboard-practice content is distinguished from wholly absent answers; the two-versus-three count failure is not hidden in a general-answer tally.",
        "This is a single-pass 32-case text test, not a microphone/transcription test or a universal semantic/entailment guarantee.",
        "No source, prompt, model, release case, or expected label was changed using release observations. A later revised candidate needs new independent release material.",
    ],
}
(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({k: summary[k] for k in ("release_conclusion", "raw_dependency_label_matches", "final_dependency_label_matches", "strict_behavioral_acceptance", "primary_delivered_forms", "standalone_answerable", "mixed", "flags", "latency")}, indent=2))
