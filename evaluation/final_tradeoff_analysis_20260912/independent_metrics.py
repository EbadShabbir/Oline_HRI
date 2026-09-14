#!/usr/bin/env python3
"""Audit descriptive tradeoff metrics using saved artifacts only (standard library).

Run from any working directory with --output /absolute/path/to/a/new/audit.json.
The output is created exclusively; existing files cannot be overwritten.
No model, scoring, router, or historical artifact is changed. Per-attempt
correctness is mapped directly from the saved resolved assistant judgments, then
checked against saved deadline, per-repetition, and paired review aggregates.
This audits existing judgments and measurements; it does not re-grade answers.
"""

import argparse
import hashlib
import itertools
import json
import math
from collections import Counter
from decimal import Decimal
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "post_memory_comparison_20260912"
ARMS = ("small", "large", "cascade")
DEADLINES = (5, 10, 15, 30)
FILES = {
    "analysis": SOURCE / "analysis_v2_reviewed/analysis.json",
    "rows": SOURCE / "analysis_v2_reviewed/row_metrics.jsonl",
    "curve": SOURCE / "analysis_v2_reviewed/deadline_quality_curve.json",
    "report_summary": SOURCE / "report_v2/summary.json",
    "mapping": SOURCE / "analysis_v2_reviewed/blinded_mapping.jsonl",
    "semantic_review": SOURCE / "analysis_v2_reviewed/semantic_review.json",
    "manifest": SOURCE / "analysis_v2_reviewed/review_manifest.json",
    "worksheet": SOURCE / "analysis_v2_reviewed/blinded_review.jsonl",
}


def decimal_sum(values):
    """Retain the exact decimal spelling of published JSON energy estimates."""
    return sum((Decimal(str(value)) for value in values), Decimal(0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New JSON output path; must not already exist")
    args = parser.parse_args()
    analysis = json.loads(FILES["analysis"].read_text())
    rows = [json.loads(line) for line in FILES["rows"].read_text().splitlines()]
    curve = json.loads(FILES["curve"].read_text())
    summary = json.loads(FILES["report_summary"].read_text())
    mapping = [json.loads(line) for line in FILES["mapping"].read_text().splitlines()]
    reviews = json.loads(FILES["semantic_review"].read_text())
    manifest = json.loads(FILES["manifest"].read_text())
    assert hashlib.sha256(FILES["mapping"].read_bytes()).hexdigest() == manifest["mapping_sha256"]
    assert hashlib.sha256(FILES["worksheet"].read_bytes()).hexdigest() == manifest["blinded_worksheet_sha256"]
    assert reviews == analysis["semantic_review"]
    assert analysis["integrity_valid"] and analysis["complete"]
    assert analysis["semantic_review"]["human_validation_complete"] is False
    assert analysis["semantic_review"]["reviewer_types"] == ["assistant"]
    assert len(rows) == 432
    assert len({r["case_id"] for r in rows}) == 48
    by_key = {(r["arm"], r["repetition"], r["case_id"]): r for r in rows}
    assert len(by_key) == len(rows)
    correct = {}
    judgments = {}
    for entry in mapping:
        opinions = reviews["review_opinions"][entry["review_id"]]
        verdicts = {opinion["judgment"] for opinion in opinions}
        assert len(verdicts) == 1, "Expected resolved, non-conflicting opinions"
        judgment = next(iter(verdicts))
        for observation in entry["observations"]:
            key = (observation["arm"], observation["repetition"], observation["case_id"])
            assert key in by_key and key not in correct
            assert observation["status"] == by_key[key]["status"]
            judgments[key] = judgment
            correct[key] = by_key[key]["delivered"] and judgment in ("complete", "appropriate_abstention")
    assert len(mapping) == manifest["unique_review_entries"] == 145
    assert len(correct) == manifest["mapped_raw_observations"] == len(rows)
    all_times = sorted({0.0, *(r["wall_seconds"] for r in rows)})
    for arm in ARMS:
        assert curve["arms"][arm]["planned_denominator"] == 144
        points = curve["arms"][arm]["points"]
        assert [point["deadline_seconds"] for point in points] == all_times
        for point in points:
            count = sum(
                correct[key] and row["wall_seconds"] <= point["deadline_seconds"]
                for key, row in by_key.items() if key[0] == arm
            )
            assert point["correct_delivered_count"] == count
            assert math.isclose(point["fraction_of_planned"], count / 144)
        assert points[-1]["correct_delivered_count"] == curve["arms"][arm]["correct_delivered"]

    result = {
        "source_sha256": {
            str(path.relative_to(HERE.parent.parent)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in FILES.values()
        },
        "correctness_method": (
            "Map existing resolved assistant judgments through blinded_mapping directly "
            "to each arm/repetition/case; independently recompute deadline curves, "
            "per-repetition totals, and paired patterns. Mapping and worksheet hashes "
            "verified against review_manifest without disclosing its private seed."
        ),
        "row_metrics_quality_caveat": (
            "Saved row_metrics semantic_quality fields still say pending_blinded_review; "
            "quality comes from resolved semantic_review judgments, not that stale field."
        ),
        "denominator_per_arm": 144,
        "distinct_items": 48,
        "distinct_scenarios": len({r["scenario_id"] for r in rows}),
        "repetitions": 3,
        "human_validation_complete": False,
        "deadline_convention": "success if delivered and fully correct and request wall_seconds <= t",
        "arms": {},
        "paired_patterns": [],
        "caveats": [
            "The 144 attempts per arm are 48 items repeated three times, not 144 independent quality samples.",
            "Scoring is assistant-only; complete and appropriate abstention can count as rubric success.",
            "Deadlines are descriptive reporting points, not acceptance thresholds.",
            "Quality and speed rankings describe this workload and recorded schedule; no significance or causal routing claim follows.",
            "Energy uses onboard VDD_IN whole-device estimates, includes idle energy, and is not model-only or marginal energy.",
            "Whole-session energy includes setup/cleanup; request energy covers only the telemetered part of request intervals.",
            "No counterfactual policy latency or energy has been estimated.",
        ],
    }
    for arm in ARMS:
        subset = [row for row in rows if row["arm"] == arm]
        assert len(subset) == 144
        quality = sum(correct[(arm, row["repetition"], row["case_id"])] for row in subset)
        assert quality == analysis["semantic_review"]["arms"][arm]["correct_reviewed"]
        assert quality == summary["review"]["arms"][arm]["correct_reviewed"]
        deadline_counts = {}
        for deadline in DEADLINES:
            n = sum(
                correct[(arm, row["repetition"], row["case_id"])] and row["wall_seconds"] <= deadline
                for row in subset
            )
            saved = max(
                point["correct_delivered_count"] for point in curve["arms"][arm]["points"]
                if point["deadline_seconds"] <= deadline
            )
            assert n == saved
            deadline_counts[str(deadline)] = {"correct_delivered": n, "fraction_of_attempts": n / 144}
        per_rep = {}
        for rep in (1, 2, 3):
            subrep = [row for row in subset if row["repetition"] == rep]
            n = sum(correct[(arm, rep, row["case_id"])] for row in subrep)
            assert len(subrep) == 48
            assert n == analysis["semantic_review"]["arms"][arm]["by_repetition"][str(rep)]["correct_reviewed"]
            per_rep[str(rep)] = {
                "attempts": 48,
                "delivered": sum(row["delivered"] for row in subrep),
                "correct": n,
                "correct_fraction": n / 48,
                "mean_latency_all_attempts_seconds": math.fsum(row["wall_seconds"] for row in subrep) / 48,
                "deadline_correct_counts": {
                    str(deadline): sum(correct[(arm, rep, row["case_id"])] and row["wall_seconds"] <= deadline for row in subrep)
                    for deadline in DEADLINES
                },
            }
        sessions = [session for session in analysis["sessions"] if session["arm"] == arm]
        assert len(sessions) == 3
        energy_fields = (
            "whole_interval_energy_joules", "request_intervals_energy_joules",
            "duration_seconds", "request_interval_covered_seconds", "request_interval_requested_seconds",
        )
        exact = {
            field: decimal_sum(session["telemetry"][field] for session in sessions)
            for field in energy_fields
        }
        request_energy = exact["request_intervals_energy_joules"]
        covered_seconds = exact["request_interval_covered_seconds"]
        requested_seconds = exact["request_interval_requested_seconds"]
        energy = {
            "session_count": 3,
            "totals_exact_decimal_from_source": {key: str(value) for key, value in exact.items()},
            "request_energy_joules_per_attempt": float(request_energy / 144),
            "whole_session_energy_joules_per_attempt": float(exact["whole_interval_energy_joules"] / 144),
            "request_interval_coverage_fraction": float(covered_seconds / requested_seconds),
            "mean_whole_device_power_in_covered_request_intervals_watts": float(request_energy / covered_seconds),
            "sessions": [
                {"repetition": session["repetition"], **{field: session["telemetry"][field] for field in energy_fields}}
                for session in sessions
            ],
        }
        mean_latency = math.fsum(row["wall_seconds"] for row in subset) / 144
        assert math.isclose(mean_latency, analysis["arms"][arm]["latency_all_seconds"]["mean"])
        result["arms"][arm] = {
            "attempts": 144,
            "delivered": sum(row["delivered"] for row in subset),
            "correct": quality,
            "correct_fraction": quality / 144,
            "mean_latency_all_attempts_seconds": mean_latency,
            "deadline_counts": deadline_counts,
            "by_repetition": per_rep,
            "whole_device_energy": energy,
        }

    categories = ("both_correct", "left_only_correct", "right_only_correct", "neither_correct")
    for left, right in itertools.combinations(ARMS, 2):
        saved = next(
            item for item in analysis["semantic_review"]["paired_success_patterns"]
            if (item["left"], item["right"]) == (left, right)
        )
        pair_result = {"left": left, "right": right, "by_repetition": {}}
        pooled = Counter()
        for rep in (1, 2, 3):
            cases = sorted(row["case_id"] for row in rows if row["arm"] == left and row["repetition"] == rep)
            members = {category: [] for category in categories}
            faster = Counter({"left_faster": 0, "right_faster": 0, "equal_latency": 0})
            for case in cases:
                left_key, right_key = (left, rep, case), (right, rep, case)
                left_ok, right_ok = correct[left_key], correct[right_key]
                category = (
                    "both_correct" if left_ok and right_ok else
                    "left_only_correct" if left_ok else
                    "right_only_correct" if right_ok else "neither_correct"
                )
                members[category].append(case)
                left_time, right_time = by_key[left_key]["wall_seconds"], by_key[right_key]["wall_seconds"]
                faster["left_faster" if left_time < right_time else "right_faster" if right_time < left_time else "equal_latency"] += 1
            counts = {category: len(members[category]) for category in categories}
            assert sum(counts.values()) == 48
            assert counts == {category: saved["by_repetition"][str(rep)].get(category, 0) for category in categories}
            pooled.update(counts)
            pair_result["by_repetition"][str(rep)] = {"counts": counts, "case_ids": members, "paired_latency_counts": dict(faster)}
        pair_result["pooled_attempt_counts_descriptive_only"] = dict(pooled)
        result["paired_patterns"].append(pair_result)

    result["audit_passed"] = True
    output = args.output
    with output.open("x") as destination:
        destination.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(output)
    for arm, values in result["arms"].items():
        print(arm, values["correct"], values["mean_latency_all_attempts_seconds"], values["deadline_counts"])
        print("energy", values["whole_device_energy"]["totals_exact_decimal_from_source"])


if __name__ == "__main__":
    main()
