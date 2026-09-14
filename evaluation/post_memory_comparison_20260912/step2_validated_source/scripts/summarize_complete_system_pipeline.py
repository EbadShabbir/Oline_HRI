"""Source-linked diagnostic counts; never regrade withheld model output."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from analyze_complete_system import file_hash, read_json, read_jsonl, row_metrics, write_new


def key(row):
    return row["arm"], row["repetition"], row.get("case_id", row.get("id"))


def summarize(rows, metrics, rubrics):
    indexed = {key(row): row for row in metrics}
    personal = [row for row in rows if row["stratum"].startswith("personal_")]
    required = [row for row in personal if rubrics[row["id"]]["required_memory_ids"]]
    delivered_required = [row for row in required if row["status"] == "ok"]
    known_required = [row for row in required if indexed[key(row)]["supplied_evidence_known"]]
    covered = lambda row: set(rubrics[row["id"]]["required_memory_ids"]) & set(indexed[key(row)]["supplied_ids"] or [])
    return {
        "attempted": len(rows), "status_counts": dict(Counter(row["status"] for row in rows)),
        "retrieval_call_count": sum(len(row.get("retrieval_calls", [])) for row in rows),
        "requests_with_retrieval": sum(bool(row.get("retrieval_calls")) for row in rows),
        "route_memory_required": dict(Counter(str(((row.get("route") or {}).get("decision") or {}).get("memory_required", "unknown")) for row in rows)),
        "personal_attempts": len(personal), "personal_attempts_with_required_ids": len(required),
        "required_evidence_known_attempts": len(known_required),
        "required_evidence_unknown_attempts": len(required) - len(known_required),
        "all_required_ids_supplied_attempts": sum(not indexed[key(row)]["required_ids_missing_from_evidence"] for row in known_required),
        "some_required_ids_missing_from_evidence_attempts": sum(bool(indexed[key(row)]["required_ids_missing_from_evidence"]) for row in known_required),
        "required_id_occurrences": sum(len(rubrics[row["id"]]["required_memory_ids"]) for row in required),
        "required_id_occurrences_supplied": sum(len(covered(row)) for row in known_required),
        "delivered_personal_attempts_with_required_ids": len(delivered_required),
        "delivered_personal_with_missing_required_citations": sum(bool(indexed[key(row)]["required_ids_missing_from_citations"]) for row in delivered_required),
        "delivered_personal_missing_required_citation_occurrences": sum(len(indexed[key(row)]["required_ids_missing_from_citations"]) for row in delivered_required),
        "requests_with_known_forbidden_supplied_ids": sum(bool(indexed[key(row)]["forbidden_supplied_ids"]) for row in rows),
        "delivered_with_forbidden_cited_ids": sum(bool(indexed[key(row)]["forbidden_cited_ids"]) for row in rows if row["status"] == "ok"),
        "reference_ids_field": dict(Counter("unrecorded" if "reference_ids" not in row else "nonempty" if row["reference_ids"] else "empty" for row in rows)),
        "recorded_reference_ids": dict(Counter(identifier for row in rows for identifier in row.get("reference_ids", []))),
        "answer_constraints": dict(Counter(row.get("answer_constraint") or "none" if "answer_constraint" in row else "unrecorded" for row in rows)),
        "response_transforms": dict(Counter(row.get("response_transform") or "none" if "response_transform" in row else "unrecorded" for row in rows)),
        "model_call_purposes": dict(Counter(call["purpose"] for row in rows for call in row.get("calls", []))),
        "backend_call_errors": dict(Counter(f"{call.get('error')}: {call.get('message')}" for row in rows for call in row.get("calls", []) if call.get("error"))),
        "request_errors": dict(Counter(f"{row.get('error')}: {row.get('message')}" for row in rows if row["status"] != "ok")),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--workload", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    report_path = args.analysis / "analysis.json"
    report, workload = read_json(report_path), read_json(args.workload)
    if not report["integrity_valid"] or file_hash(args.workload) != report["workload_sha256"]:
        raise ValueError("diagnostics require an integrity-valid source snapshot and matching workload")
    metrics_path = args.analysis / "row_metrics.jsonl"
    metrics = read_jsonl(metrics_path)
    rows, sources = [], {}
    for session in report["sessions"]:
        if session["status"] == "missing":
            continue
        path = Path(report["run_root"]) / session["directory"] / "observations.jsonl"
        expected = session["artifact_sha256"]["observations.jsonl"]
        if file_hash(path) != expected:
            raise ValueError(f"source observations changed: {path}")
        sources[str(path)] = expected
        rows.extend(read_jsonl(path))
    if len(rows) != report["observed_attempts"] or len(rows) != len(metrics) or len({key(row) for row in rows}) != len(rows):
        raise ValueError("observation/metric coverage differs")
    indexed = {key(row): row for row in metrics}
    for row in rows:
        if row_metrics(row, workload["rubrics"][row["id"]]) != indexed[key(row)]:
            raise ValueError("saved metrics differ from independently reconstructed observations")
    failures, examples = [], []
    for row in rows:
        if row["status"] != "ok":
            failures.append({"arm": row["arm"], "repetition": row["repetition"], "case_id": row["id"],
                "status": row["status"], "error": row.get("error"), "message": row.get("message"),
                "retrieval_call_count": len(row.get("retrieval_calls", [])),
                "supplied_ids": indexed[key(row)]["supplied_ids"], "semantic_score_credit": 0,
                "backend_errors": [{field: call.get(field) for field in ("purpose", "error", "message")}
                                   for call in row.get("calls", []) if call.get("error")]})
        if row["id"] == "s2_r08":
            generators = [call for call in row.get("calls", []) if call["purpose"] == "generation"]
            call = generators[-1] if generators else {}
            generation = call.get("generation") or call.get("raw_generation") or {}
            candidate = json.loads(generation["content"]) if generation.get("content") else None
            schema = ((call.get("response_format") or {}).get("properties") or {}).get("memory_used", {})
            examples.append({"arm": row["arm"], "repetition": row["repetition"], "status": row["status"],
                "prompt": row["prompt"], "reference_answer": workload["rubrics"][row["id"]]["reference_answer"],
                "required_memory_ids": workload["rubrics"][row["id"]]["required_memory_ids"],
                "route_memory_required": row["route"]["decision"]["memory_required"],
                "retrieved_facts": [{"memory_id": match["memory"]["id"], "text": match["memory"]["canonical_text"]}
                                    for retrieval in row.get("retrieval_calls", []) for match in retrieval.get("matches", [])],
                "supplied_ids": indexed[key(row)]["supplied_ids"],
                "generation_memory_used_schema": schema,
                "undelivered_candidate": candidate,
                "candidate_clock_strings": re.findall(r"\b\d{2}:\d{2}\b", (candidate or {}).get("speech", "")),
                "validation_error": row.get("message"), "semantic_score_credit": 0})
    result = {
        "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "diagnostic_script_sha256": file_hash(Path(__file__)),
        "metric_utility_sha256": file_hash(Path(__file__).with_name("analyze_complete_system.py")),
        "source_analysis": str(report_path), "source_analysis_sha256": file_hash(report_path),
        "source_metrics_sha256": file_hash(metrics_path), "workload_sha256": file_hash(args.workload),
        "source_observations_sha256": sources,
        "frozen_execution_source_sha256": next(session["manifest"]["frozen"]["source_sha256"] for session in report["sessions"] if "manifest" in session),
        "overall": summarize(rows, metrics, workload["rubrics"]),
        "by_session": {f"{arm}_r{repetition}": summarize([row for row in rows if key(row)[:2] == (arm, repetition)], metrics, workload["rubrics"])
                       for arm, repetition in sorted({key(row)[:2] for row in rows})},
        "by_stratum": {stratum: summarize([row for row in rows if row["stratum"] == stratum], metrics, workload["rubrics"])
                       for stratum in sorted({row["stratum"] for row in rows})},
        "failed_attempts": failures, "timer_example_s2_r08": examples,
        "interpretation": [
            "Diagnostics do not revise frozen rubrics, semantic reviews, or technical-failure scores. Withheld raw text is not a delivered answer.",
            "Required-ID supply and citation coverage are mechanical evidence checks, not semantic correctness. Empty gold requirements do not establish success.",
            "reference_ids, answer_constraint, and response_transform are recorded only on completed replies; missing fields on failed requests are unknown, not evidence that the path did not run.",
            "The timer is self-contained but all observed sessions selected personal retrieval and required the two irrelevant citation IDs in the generation schema. The later temporal validator withheld the candidate.",
            "For this timer, small/cascade candidates contain the correct 10:55 arithmetic result while both large candidates say 11:15. Irrelevant personal citations remain invalid, so this is not established as a validator-only false positive and no candidate earns score credit.",
        ],
    }
    write_new(args.output, result)
    print(json.dumps({"output": str(args.output), "attempted": len(rows), "status_counts": result["overall"]["status_counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
