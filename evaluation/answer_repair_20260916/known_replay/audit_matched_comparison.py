"""Independent raw-data cross-check of this cohort's preserved paired reports.

This script imports neither compare_matched nor analyze. It never reads holdout
authoring and writes only a new audit report beside this script.
"""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parents[2] / "evaluation/fresh_routing_20260916"
UPDATED = HERE / "matched_with_operational_status"


def read(path):
    return json.loads(path.read_text())


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def judgment_map(path):
    value = read(path)
    if isinstance(value, dict) and "judgments" in value:
        value = value["judgments"]
    return value if isinstance(value, dict) else {row["id"]: row for row in value}


def scores(row, judgment):
    good = row["status"] == "ok"
    route = row.get("route") or {}
    prediction = (route.get("classifier_metadata") or {}).get("whole_request") or {}
    modes = {"raw_match": prediction.get("predicted_mode"), "thresholded_match": prediction.get("mode"),
             "final_match": (route.get("dependency") or {}).get("mode")}
    result = {key: good and value in row["case"]["expected_modes"] for key, value in modes.items()}
    delivered = good and bool(row.get("delivered_text", "").strip())
    result["quality_pass"] = bool(delivered and judgment["quality_pass"])
    result["combined_pass"] = result["quality_pass"] and result["final_match"]
    result.update(status=row["status"], delivered=delivered,
                  generated_delivery=delivered and (row.get("reply") or {}).get("generation") is not None,
                  wall_seconds=row["wall_ns"] / 1e9)
    return result


def latency(rows):
    values = sorted(row["wall_seconds"] for row in rows)
    result = {"n": len(values), "mean_seconds": math.fsum(values) / len(values)}
    for percentile in (50, 95):
        index = (len(values) - 1) * percentile / 100
        left, right = math.floor(index), math.ceil(index)
        result[f"p{percentile}_seconds"] = values[left] if left == right else (
            values[left] * (right - index) + values[right] * (index - left))
    return result


def main():
    checks = []

    def check(condition, label, detail=None):
        checks.append({"check": label, "passed": bool(condition), "detail": detail})

    old = records(ORIGINAL / "collection/run/observations.jsonl")
    new = records(HERE / "collection/run/observations.jsonl")
    old_j = judgment_map(ORIGINAL / "adjudicated_judgments.json")
    new_j = judgment_map(HERE / "adjudicated_judgments.json")
    report = read(HERE / "matched_comparison.json")
    updated = read(UPDATED / "matched_comparison.json")
    paired = records(HERE / "matched_per_case.jsonl")
    old_hashes = {str(path): digest(path) for path in (HERE / "matched_comparison.json", HERE / "matched_per_case.jsonl")}
    matched_ids = [row["id"] for row in old if row["status"] == "ok"]
    excluded = {row["id"] for row in old if row["status"] != "ok"}
    expected_excluded = {"fresh_035", "fresh_036", "fresh_044", "fresh_046", "fresh_047"}
    check(len(old) == len(new) == len({row["id"] for row in new}) == 48, "all 48 replay observations retained")
    check(len(matched_ids) == 43 and excluded == expected_excluded, "original 43 valid and five setup-error subsets")
    check(report["matched_ids"] == matched_ids == [row["id"] for row in paired], "exact matched IDs and original order")
    check(digest(ORIGINAL / "cases.json") == digest(HERE / "cases.json"), "entire original and replay frozen corpus bytes agree")
    old_by_id, new_by_id = {row["id"]: row for row in old}, {row["id"]: row for row in new}
    before = {row["id"]: scores(row, old_j[row["id"]]) for row in old}
    after = {row["id"]: scores(row, new_j[row["id"]]) for row in new}
    for identifier in matched_ids:
        old_case, new_case = old_by_id[identifier]["case"], new_by_id[identifier]["case"]
        check(old_case["text"].encode() == new_case["text"].encode()
              and old_case.get("prior_turns", []) == new_case.get("prior_turns", [])
              and old_case["expected_modes"] == new_case["expected_modes"]
              and old_case.get("rubric") == new_case.get("rubric"), "unchanged prompt/context/criteria: " + identifier)
    for name, group in (("matched_before", [before[i] for i in matched_ids]),
                        ("matched_after", [after[i] for i in matched_ids]),
                        ("final_full_cohort", list(after.values()))):
        supplied = report[name]
        check(supplied["planned"] == len(group), name + " denominator")
        for key in ("raw_match", "thresholded_match", "final_match", "quality_pass", "combined_pass"):
            count = sum(row[key] for row in group)
            check(supplied[key]["count"] == count and supplied[key]["denominator"] == len(group)
                  and math.isclose(supplied[key]["rate"], count / len(group)), name + "/" + key)
        check(supplied["statuses"] == dict(Counter(row["status"] for row in group)), name + " statuses preserve errors")
        expected_latency = latency(group)
        check(all(math.isclose(supplied["wall_latency"][key], value, rel_tol=1e-12, abs_tol=1e-9)
                  for key, value in expected_latency.items()), name + " independent linear percentiles", expected_latency)
    transitions = {name: [] for name in ("fail_to_pass", "pass_to_fail", "pass_to_pass", "fail_to_fail")}
    for row in paired:
        identifier = row["id"]
        transition = ("pass" if before[identifier]["quality_pass"] else "fail") + "_to_" + (
            "pass" if after[identifier]["quality_pass"] else "fail")
        transitions[transition].append(identifier)
        preserved = all(row[label][key] == source[identifier][key]
                        for label, source in (("before", before), ("after", after))
                        for key in ("status", "raw_match", "thresholded_match", "final_match", "quality_pass", "combined_pass", "wall_seconds"))
        check(preserved and row["quality_transition"] == transition and
              math.isclose(row["wall_delta_seconds"], after[identifier]["wall_seconds"] - before[identifier]["wall_seconds"],
                           rel_tol=1e-12, abs_tol=1e-9) and
              all(row["score_deltas"][key] == int(after[identifier][key]) - int(before[identifier][key])
                  for key in ("raw_match", "thresholded_match", "final_match", "quality_pass", "combined_pass")),
              "paired values and deltas: " + identifier)
    check(report["quality_transitions"] == {key: {"count": len(ids), "ids": ids} for key, ids in transitions.items()},
          "quality transitions match raw observations and adjudications")
    subset = report["original_setup_failures_excluded"]
    check(subset["count"] == 5 and {row["id"] for row in subset["cases"]} == excluded,
          "setup failures stay outside the paired comparison")
    for row in subset["cases"]:
        check(all(row["final_replay"][key] == after[row["id"]][key] for key in after[row["id"]]),
              "newly covered input values: " + row["id"])
    check(after["fresh_043"]["status"] == "error" and "fresh_043" in matched_ids
          and not after["fresh_043"]["quality_pass"], "guard-aborted case remains a matched failure")
    for path_string, expected in report["input_sha256"].items():
        path = Path(path_string)
        if path.name == "compare_matched.py":
            path = HERE / "matched_comparison_source_v1.py"
        check(digest(path) == expected, "original comparison input/source hash: " + str(path))
    for key in ("matched_count", "matched_ids", "matched_before", "matched_after", "quality_transitions",
                "final_full_cohort", "original_setup_failures_excluded"):
        check(updated[key] == report[key], "operational-status addition preserves measurement: " + key)
    check((UPDATED / "matched_per_case.jsonl").read_bytes() == (HERE / "matched_per_case.jsonl").read_bytes(),
          "updated paired rows are byte-for-byte unchanged")
    outcome = updated["replay_collection_outcome"]
    check(outcome["wrapper_complete"] is False and outcome["runner_exit_code"] == 1
          and outcome["guard_violation"] == "available memory crossed the runtime floor"
          and outcome["cleanup_errors"] == [], "updated comparison explicitly preserves guard failure and clean cleanup")
    for path_string, expected in updated["input_sha256"].items():
        check(digest(Path(path_string)) == expected, "updated comparison input/source hash: " + path_string)
    check(all(digest(Path(path)) == value for path, value in old_hashes.items()), "previous comparison artifacts not rewritten")
    result = {"passed": all(item["passed"] for item in checks),
              "checks_passed": sum(item["passed"] for item in checks),
              "checks_failed": sum(not item["passed"] for item in checks), "checks": checks,
              "operational_success": False, "evaluation_complete": False,
              "interpretation": "Comparison arithmetic and provenance verify; the replay still failed its memory guard. This audit does not validate a clean operational run or infer causal speedup.",
              "original_comparison_sha256": old_hashes,
              "auditor_sha256": digest(Path(__file__))}
    with (HERE / "matched_independent_audit.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({key: result[key] for key in ("passed", "checks_passed", "checks_failed")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
