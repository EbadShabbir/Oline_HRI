"""Descriptive comparison of the original 43 valid prompts and their known replay.

Reads each cohort's frozen cases, original raw observations and adjudicated
judgments. It never imports the analyzer, changes inputs, substitutes normalized
follow-ups, or reads holdout authoring. Run after both cohorts are fully graded.
Every matched prompt remains in both denominators, including new failures.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent / "fresh_routing_20260916"
MODES = {"none", "optional", "required", "clarify"}
ORIGINAL_SETUP_IDS = {"fresh_035", "fresh_036", "fresh_044", "fresh_046", "fresh_047"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def judgments_by_id(payload):
    if isinstance(payload, dict) and "judgments" in payload:
        payload = payload["judgments"]
    if isinstance(payload, dict):
        payload = [dict(value, id=identifier) for identifier, value in payload.items()]
    require(isinstance(payload, list), "invalid adjudicated judgments")
    result = {}
    for judgment in payload:
        identifier = judgment["id"]
        require(identifier not in result, "duplicate adjudication: " + identifier)
        require(type(judgment.get("quality_pass")) is bool, "quality must be boolean: " + identifier)
        require(not judgment["quality_pass"] or
                all(item.get("pass") is True for item in judgment.get("required_components_pass", [])),
                "passing judgment has a failed required component: " + identifier)
        result[identifier] = judgment
    return result


def load_cohort(directory):
    directory = Path(directory).resolve()
    cases_path = directory / "cases.json"
    raw_path = directory / "collection/run/observations.jsonl"
    judgments_path = directory / "adjudicated_judgments.json"
    payload = read(cases_path)
    cases = payload["cases"] if isinstance(payload, dict) else payload
    observations = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    judgments = judgments_by_id(read(judgments_path))
    identifiers = [case["id"] for case in cases]
    require(len(identifiers) == len(set(identifiers)), "duplicate planned case IDs")
    require([row["id"] for row in observations] == identifiers, "raw observations must cover every frozen case in order")
    require(set(judgments) == set(identifiers), "adjudications must cover the complete cohort")
    require(all(row.get("case") == case for row, case in zip(observations, cases)), "embedded case differs from frozen case")
    metadata_path = directory / "collection/run/metadata.json"
    require(read(metadata_path)["cases_sha256"] == sha(cases_path), "runner corpus hash does not match frozen cases")
    manifest_path = directory / "collection/artifact_sha256.json"
    sealed = read(manifest_path)
    require(sealed.get("run/observations.jsonl") == sha(raw_path), "raw observations do not match their collection seal")
    paths = (cases_path, raw_path, judgments_path, metadata_path, manifest_path)
    return cases, observations, judgments, {str(path): sha(path) for path in paths}


def score(case, observation, judgment):
    identifier = case["id"]
    require(observation.get("status") in {"ok", "error"}, "invalid observation status: " + identifier)
    require(type(observation.get("wall_ns")) is int and observation["wall_ns"] >= 0,
            "every observed turn needs its actual nonnegative wall duration: " + identifier)
    expected = case["expected_modes"]
    require(isinstance(expected, list) and len(expected) == 1 and expected[0] in MODES,
            "invalid expected dependency mode: " + identifier)
    route, reply = observation.get("route") or {}, observation.get("reply") or {}
    predicted = (route.get("classifier_metadata") or {}).get("whole_request") or {}
    ok = observation["status"] == "ok"
    delivered = ok and bool(observation.get("delivered_text", "").strip())
    final = (route.get("dependency") or {}).get("mode")
    quality = delivered and judgment["quality_pass"]
    return {"status": observation["status"], "raw_mode": predicted.get("predicted_mode"),
            "thresholded_mode": predicted.get("mode"), "final_mode": final,
            "effective_mode": reply.get("effective_mode"),
            "raw_match": ok and predicted.get("predicted_mode") in expected,
            "thresholded_match": ok and predicted.get("mode") in expected,
            "final_match": ok and final in expected, "quality_pass": bool(quality),
            "combined_pass": bool(quality and final in expected),
            "delivered": delivered, "generated_delivery": delivered and reply.get("generation") is not None,
            "wall_seconds": observation["wall_ns"] / 1e9, "error": observation.get("error")}


def summary(rows):
    count = len(rows)
    ordered = sorted(row["wall_seconds"] for row in rows)
    latency = {"n": count, "scope": "All planned matched/selected observed turns, including errors and application replies."}
    for name, q in (("p50_seconds", 0.5), ("p95_seconds", 0.95)):
        if ordered:
            rank = (count - 1) * q
            low, high = math.floor(rank), math.ceil(rank)
            latency[name] = ordered[low] + (ordered[high] - ordered[low]) * (rank - low)
        else:
            latency[name] = None
    latency["mean_seconds"] = math.fsum(ordered) / count if count else None
    return {"planned": count,
            **{key: {"count": sum(row[key] for row in rows), "denominator": count,
                     "rate": sum(row[key] for row in rows) / count if count else None}
               for key in ("raw_match", "thresholded_match", "final_match", "quality_pass", "combined_pass")},
            "statuses": dict(Counter(row["status"] for row in rows)),
            "delivered": sum(row["delivered"] for row in rows),
            "generated_delivery": sum(row["generated_delivery"] for row in rows), "wall_latency": latency}


def compare(original_cases, original_raw, original_judgments, replay_cases, replay_raw, replay_judgments):
    original_ids = [case["id"] for case in original_cases]
    require(len(original_ids) == len(set(original_ids)), "duplicate original IDs")
    require(len(replay_cases) == len(original_cases) and {case["id"] for case in replay_cases} == set(original_ids),
            "known replay must retain every original case exactly once")
    require(len(original_raw) == len(original_ids) and {row["id"] for row in original_raw} == set(original_ids),
            "original observations incomplete or duplicated")
    require(len(replay_raw) == len(original_ids) and {row["id"] for row in replay_raw} == set(original_ids),
            "known replay observations incomplete or duplicated; cannot drop new failures")
    require(set(original_judgments) == set(replay_judgments) == set(original_ids), "complete adjudications required")
    old_cases = {case["id"]: case for case in original_cases}
    new_cases = {case["id"]: case for case in replay_cases}
    old_raw = {row["id"]: row for row in original_raw}
    new_raw = {row["id"]: row for row in replay_raw}
    matched, setup, all_final = [], [], []
    for identifier in original_ids:
        before_case, after_case = old_cases[identifier], new_cases[identifier]
        require(before_case["text"].encode("utf-8") == after_case["text"].encode("utf-8"),
                "prompt bytes changed: " + identifier)
        require(before_case.get("prior_turns", []) == after_case.get("prior_turns", []),
                "supplied history changed: " + identifier)
        for field in ("expected_modes", "rubric", "general_component_expected"):
            require(before_case.get(field) == after_case.get(field), "evaluation criterion changed: " + identifier + "/" + field)
        before = score(before_case, old_raw[identifier], original_judgments[identifier])
        after = score(after_case, new_raw[identifier], replay_judgments[identifier])
        all_final.append(after)
        if before["status"] != "ok":
            setup.append({"id": identifier, "original_status": before["status"],
                          "original_error": before["error"], "final_replay": after})
            continue
        transition = ("pass" if before["quality_pass"] else "fail") + "_to_" + ("pass" if after["quality_pass"] else "fail")
        matched.append({"id": identifier, "category": before_case.get("category"),
                        "expected_modes": before_case["expected_modes"],
                        "prompt_utf8_sha256": hashlib.sha256(before_case["text"].encode("utf-8")).hexdigest(),
                        "before": before, "after": after, "quality_transition": transition,
                        "score_deltas": {key: int(after[key]) - int(before[key]) for key in
                                         ("raw_match", "thresholded_match", "final_match", "quality_pass", "combined_pass")},
                        "wall_delta_seconds": after["wall_seconds"] - before["wall_seconds"]})
    transitions = {name: [row["id"] for row in matched if row["quality_transition"] == name]
                   for name in ("fail_to_pass", "pass_to_fail", "pass_to_pass", "fail_to_fail")}
    before_summary = summary([row["before"] for row in matched])
    after_summary = summary([row["after"] for row in matched])
    return {"matched_count": len(matched), "matched_ids": [row["id"] for row in matched],
            "matched_before": before_summary, "matched_after": after_summary,
            "quality_transitions": {name: {"count": len(ids), "ids": ids} for name, ids in transitions.items()},
            "final_full_cohort": summary(all_final),
            "original_setup_failures_excluded": {"count": len(setup), "cases": setup,
                "final_replay_summary": summary([row["final_replay"] for row in setup]),
                "interpretation": "These prompts never reached a model in the original release run. Their final replay is newly covered input, not a paired improvement over prior model answers."},
            "latency_interpretation": "Same prompt bytes and criteria, different historical sessions. Median/p95 use linear interpolation at (n-1)*q over every selected case. Per-case wall deltas are after minus before; these descriptive measurements do not establish a causal speedup.",
            "review_interpretation": "Quality uses each cohort's preserved adjudications; it does not claim identical reviewers or an independently blinded paired regrade."}, matched


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-dir", type=Path, default=ORIGINAL)
    parser.add_argument("--replay-dir", type=Path, default=HERE / "known_replay")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    output_dir = args.output_dir or args.replay_dir
    summary_path, rows_path = output_dir / "matched_comparison.json", output_dir / "matched_per_case.jsonl"
    require(not summary_path.exists() and not rows_path.exists(), "comparison output already exists; choose a new output directory")
    original = load_cohort(args.original_dir)
    replay = load_cohort(args.replay_dir)
    report, matched = compare(*original[:3], *replay[:3])
    require(len(original[0]) == len(replay[0]) == 48 and report["matched_count"] == 43,
            "this comparison requires the preregistered original 48 and exactly 43 valid original turns")
    excluded = {row["id"] for row in report["original_setup_failures_excluded"]["cases"]}
    require(excluded == ORIGINAL_SETUP_IDS, "original setup-error subset differs from the documented five IDs")
    require(all(row.get("calls") == [] and row.get("route") is None and not row.get("delivered_text")
                and row.get("error") == {"type": "ValueError", "message": "user message cannot contain control characters"}
                for row in original[1] if row["id"] in excluded), "excluded inputs were not the documented zero-call validation failures")
    report.update(created_at=datetime.now(timezone.utc).isoformat(), schema_version="matched_known_replay_v1",
                  original_dir=str(args.original_dir.resolve()), replay_dir=str(args.replay_dir.resolve()),
                  input_sha256={**original[3], **replay[3], str(Path(__file__).resolve()): sha(Path(__file__))})
    output_dir.mkdir(parents=True, exist_ok=True)
    with rows_path.open("x", encoding="utf-8") as stream:
        for row in matched:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    with summary_path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"matched_count": report["matched_count"], "before": report["matched_before"],
                      "after": report["matched_after"], "output": str(summary_path)}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as error:
        raise SystemExit("MATCHED COMPARISON FAILED: " + str(error))
