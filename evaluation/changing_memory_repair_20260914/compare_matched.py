#!/usr/bin/env python3
"""Compare sealed baseline and repair judgments without inference or rescoring."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import csv
import json
import math
from pathlib import Path
import statistics
import sys


CLASSES = {"correct_recall", "appropriate_uncertainty", "partial", "incorrect",
           "inappropriate_uncertainty", "no_delivered_answer"}
METRICS = ("planned", "delivered", "useful_correct", "forbidden_disclosure",
           "revoked_original_disclosure", "unstored_replacement_disclosure",
           "withheld", "interrupted", "missing")
DIMENSIONS = ((), ("branch",), ("history_mode",), ("after_restart",), ("expected_kind",),
              ("branch", "history_mode"), ("branch", "after_restart", "history_mode"),
              ("expected_kind", "after_restart", "history_mode"), ("scenario_id",))


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def verify_seal(directory):
    manifest = read_json(directory / "seal.json")["sha256"]
    paths = {str(p.relative_to(directory)) for p in directory.rglob("*")
             if p.is_file() and p != directory / "seal.json"}
    if paths != set(manifest) or any(digest(directory / p) != h for p, h in manifest.items()):
        raise ValueError(f"Seal mismatch: {directory}")


def write_json(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def write_csv(path, rows):
    if not rows:
        raise ValueError("A comparison table must have explicit rows")
    with path.open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict))
                             else value for key, value in row.items()})


def seal(directory):
    write_json(directory / "seal.json", {"sha256": {str(p.relative_to(directory)): digest(p)
        for p in sorted(directory.rglob("*")) if p.is_file()},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "immutability": "SHA256 manifest, exclusive creation and read-only permissions; not privileged WORM"})
    for path in directory.rglob("*"):
        path.chmod(0o500 if path.is_dir() else 0o400)
    directory.chmod(0o500)


def load_analysis(directory):
    verify_seal(directory)
    provenance, metrics = read_json(directory / "provenance.json"), read_json(directory / "metrics.json")
    agreement = read_json(directory / "review_agreement.json")
    if (provenance.get("partial") is not False or metrics.get("partial") is not False
            or provenance.get("human_validation") != "pending"
            or agreement.get("resolved_before_diagnostics") is not True):
        raise ValueError("Comparison requires final assistant reviews frozen before diagnostics")
    votes = read_json(directory / "frozen_votes/resolved.json")
    rows = [json.loads(line) for line in (directory / "reviewed_answers.jsonl").read_text().splitlines() if line.strip()]
    indexed = {row["checkpoint_id"]: row for row in rows}
    if not rows or len(indexed) != len(rows) or metrics["all"]["planned"] != len(rows):
        raise ValueError("Analysis planned counts or unique checkpoint identities disagree")
    for row in rows:
        expected, vote, diagnostic = row["expected"], row["judgment"], row["diagnostics"]
        if expected["checkpoint_id"] != row["checkpoint_id"] or votes.get(row["blind_id"]) != vote:
            raise ValueError("Reviewed checkpoint does not bind its frozen expected state and vote")
        if not row["observed"] or diagnostic["status"] not in {"delivered", "withheld", "interrupted"}:
            raise ValueError("Final comparison requires every explicit checkpoint attempt")
        if vote.get("classification") not in CLASSES or any(type(vote.get(k)) is not bool for k in
                ("useful_correct", "forbidden_disclosure")):
            raise ValueError("Invalid frozen judgment")
        forbidden = vote.get("disclosed_forbidden_values")
        if (not isinstance(forbidden, list) or not set(forbidden) <= set(expected["forbidden_values"])
                or bool(forbidden) != vote["forbidden_disclosure"]
                or vote["useful_correct"] != (vote["classification"] in {"correct_recall", "appropriate_uncertainty"})
                or (vote["useful_correct"] and vote["forbidden_disclosure"])):
            raise ValueError("Frozen success/disclosure judgment contradicts its rubric or classification")
        if diagnostic["status"] == "delivered":
            if not isinstance(row["delivered_answer"], str) or not row["delivered_answer"].strip():
                raise ValueError("Delivered attempt lacks an answer")
        elif (row["delivered_answer"] is not None or vote["useful_correct"] or vote["forbidden_disclosure"]
              or vote["classification"] != "no_delivered_answer"):
            raise ValueError("Undelivered attempt cannot count as useful recall or disclosure")
    return rows, provenance


def bind_rows(baseline_rows, repair_rows, expected_checkpoints=96):
    """Bind identical questions, authorized states, rubrics and checkpoint metadata."""
    baseline = {row["checkpoint_id"]: row for row in baseline_rows}
    repaired = {row["checkpoint_id"]: row for row in repair_rows}
    if len(baseline) != len(baseline_rows) or len(repaired) != len(repair_rows):
        raise ValueError("Duplicate comparison checkpoint")
    if expected_checkpoints <= 0 or len(repair_rows) != expected_checkpoints:
        raise ValueError("Repair analysis does not match the requested planned checkpoint count")
    if not set(repaired) <= set(baseline):
        raise ValueError("Repair checkpoint is absent from the original baseline")
    for key, row in repaired.items():
        if row["expected"] != baseline[key]["expected"]:
            raise ValueError(f"Expected state/question/rubric or schedule differs: {key}")
    # Each selected scenario retains the complete unchanged lifecycle suite.
    scenario_counts = Counter(row["expected"]["scenario_id"] for row in repair_rows)
    if any(count != 24 for count in scenario_counts.values()):
        raise ValueError("Matched regression must retain all 24 checkpoints per scenario")
    for scenario in scenario_counts:
        branches = Counter(row["expected"]["branch"] for row in repair_rows if row["expected"]["scenario_id"] == scenario)
        if branches != Counter({"correction": 10, "deletion": 7, "expiry": 7}):
            raise ValueError("Matched regression must preserve independent lifecycle branches")
    return [(baseline[key], repaired[key]) for key in sorted(repaired)]


def counts(rows):
    result = dict.fromkeys(METRICS, 0)
    result["planned"] = len(rows)
    for row in rows:
        e, j, d = row["expected"], row["judgment"], row["diagnostics"]
        result["delivered"] += d["status"] == "delivered"
        result["useful_correct"] += j["useful_correct"]
        result["forbidden_disclosure"] += j["forbidden_disclosure"]
        revoked = e["mutation_state"] in {"correction", "deletion", "expiry"}
        result["revoked_original_disclosure"] += revoked and e["original_subject_value"] in j["disclosed_forbidden_values"]
        result["unstored_replacement_disclosure"] += (e["branch"] in {"deletion", "expiry"}
            and e["replacement_subject_value"] in j["disclosed_forbidden_values"])
        result["withheld"] += d["status"] == "withheld"
        result["interrupted"] += d["status"] == "interrupted"
        result["missing"] += not row["observed"]
    return result


def aggregate(pairs):
    output = []
    for dimensions in DIMENSIONS:
        values = sorted({tuple(after["expected"][key] for key in dimensions) for _, after in pairs}, key=repr)
        for value in values:
            selected = [(before, after) for before, after in pairs
                        if tuple(after["expected"][key] for key in dimensions) == value]
            old, new = counts([a for a, _ in selected]), counts([b for _, b in selected])
            group = dict(zip(dimensions, value))
            row = {"dimensions": "+".join(dimensions) or "all", "group": json.dumps(group, sort_keys=True)}
            for metric in METRICS:
                row.update({"baseline_" + metric: old[metric], "repair_" + metric: new[metric],
                            "delta_" + metric: new[metric] - old[metric]})
            output.append(row)
    return output


def recorded_wall_seconds(row):
    """Use explicit measured timing, not the analyzer's missing-field zero default."""
    diagnostic = row["diagnostics"]
    raw = row.get("observed_record") or {}
    value = diagnostic.get("wall_seconds")
    if "wall_ns" not in raw or value is None:
        return None
    nanos = raw["wall_ns"]
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            or value < 0 or isinstance(nanos, bool) or not isinstance(nanos, int) or nanos < 0
            or not math.isclose(value, nanos / 1e9, rel_tol=1e-12, abs_tol=1e-12)):
        raise ValueError("Recorded conversation wall timing is invalid or contradicts its trace")
    return float(value)


def timing_summary(rows):
    values = [value for row in rows if (value := recorded_wall_seconds(row)) is not None]
    values.sort()
    return {"eligible_attempts": len(rows), "timed_attempts": len(values),
            "missing_timing": len(rows) - len(values),
            "median_seconds": statistics.median(values) if values else None,
            "p95_seconds": values[math.ceil(.95 * len(values)) - 1] if values else None}


def latency_table(pairs):
    output = []
    for dimensions in DIMENSIONS:
        values = sorted({tuple(after["expected"][key] for key in dimensions) for _, after in pairs}, key=repr)
        for value in values:
            selected = [(before, after) for before, after in pairs
                        if tuple(after["expected"][key] for key in dimensions) == value]
            for scope in ("all_attempts", "delivered_only"):
                row = {"dimensions": "+".join(dimensions) or "all", "group": json.dumps(dict(zip(dimensions, value)), sort_keys=True),
                       "scope": scope}
                for label, index in (("baseline", 0), ("repair", 1)):
                    members = [pair[index] for pair in selected if scope == "all_attempts" or pair[index]["diagnostics"]["status"] == "delivered"]
                    row.update({label + "_" + key: count for key, count in timing_summary(members).items()})
                for key in ("median_seconds", "p95_seconds"):
                    a, b = row["baseline_" + key], row["repair_" + key]
                    row["delta_" + key] = b - a if a is not None and b is not None else None
                output.append(row)
    return output


def generator_counts_table(pairs):
    output = []
    for dimensions in DIMENSIONS:
        values = sorted({tuple(after["expected"][key] for key in dimensions) for _, after in pairs}, key=repr)
        for value in values:
            selected = [(before, after) for before, after in pairs
                        if tuple(after["expected"][key] for key in dimensions) == value]
            for label, index in (("baseline", 0), ("repair", 1)):
                counts_by_model, missing, empty = Counter(), 0, 0
                for pair in selected:
                    models = pair[index]["diagnostics"].get("actual_generator_models")
                    if models is None:
                        missing += 1
                    elif not isinstance(models, list) or not all(isinstance(m, str) and m for m in models):
                        raise ValueError("Recorded actual generator model list is invalid")
                    else:
                        counts_by_model.update(models)
                        empty += not models
                output.append({"dimensions": "+".join(dimensions) or "all", "group": json.dumps(dict(zip(dimensions, value)), sort_keys=True),
                    "system": label, "checkpoint_attempts": len(selected), "model_metadata_missing": missing,
                    "checkpoints_with_no_returned_generator_model": empty,
                    "actual_generator_calls": sum(counts_by_model.values()), "actual_generator_model_calls": dict(counts_by_model)})
    return output


def transition(before, after, field, names):
    return names[(bool(before["judgment"][field]), bool(after["judgment"][field]))]


def checkpoint_table(pairs):
    output = []
    for old, new in pairs:
        e = new["expected"]
        row = {"checkpoint_id": new["checkpoint_id"], "scenario_id": e["scenario_id"], "branch": e["branch"],
               "history_mode": e["history_mode"], "after_restart": e["after_restart"], "expected_kind": e["expected_kind"],
               "question": e["question"], "expected_value": e["expected_value"]}
        for label, answer in (("baseline", old), ("repair", new)):
            row.update({label + "_classification": answer["judgment"]["classification"],
                        label + "_status": answer["diagnostics"]["status"],
                        label + "_useful_correct": answer["judgment"]["useful_correct"],
                        label + "_forbidden_values": answer["judgment"]["disclosed_forbidden_values"],
                        label + "_delivered_answer": answer["delivered_answer"],
                        label + "_review_reason": answer["judgment"]["reason"]})
        row["classification_changed"] = old["judgment"]["classification"] != new["judgment"]["classification"]
        row["answer_text_changed"] = old["delivered_answer"] != new["delivered_answer"]
        row["usefulness_transition"] = transition(old, new, "useful_correct", {
            (True, True): "both_useful", (False, True): "gained_usefulness", (True, False): "lost_usefulness",
            (False, False): "both_unsuccessful"})
        row["disclosure_transition"] = transition(old, new, "forbidden_disclosure", {
            (True, True): "both_disclose", (True, False): "disclosure_eliminated", (False, True): "disclosure_introduced",
            (False, False): "neither_discloses"})
        output.append(row)
    return output


def diagnostic_tables(repair_rows):
    """Copy only recorded new-system metadata; unknown never becomes inferred."""
    output, groups = [], Counter()
    for row in repair_rows:
        d = row["diagnostics"]
        observed = row.get("observed_record") or {}
        route = d.get("route") or {}
        decision = route.get("decision") or {}
        item = {"checkpoint_id": row["checkpoint_id"],
                "answer_constraint": observed.get("answer_constraint"),
                "constraint_field_present": "answer_constraint" in observed,
                "constraint_source": "observed_record.answer_constraint" if "answer_constraint" in observed else None,
                "generation_policy": d.get("generation_policy"),
                "generation_policy_field_present": "generation_policy" in d,
                "route_policy": route.get("policy"), "memory_required": decision.get("memory_required"),
                "nominal_model_size": decision.get("model_size"),
                "actual_generator_models": d.get("actual_generator_models"),
                "response_transform": d.get("response_transform")}
        output.append(item)
        for field in ("answer_constraint", "generation_policy", "route_policy", "memory_required", "nominal_model_size", "response_transform"):
            groups[(field, json.dumps(item[field], sort_keys=True))] += 1
    summaries = [{"field": field, "recorded_value": value, "checkpoints": count}
                 for (field, value), count in sorted(groups.items())]
    return output, summaries


def compare(args):
    baseline_path, repair_path, output = args.baseline.resolve(), args.repair.resolve(), args.output.resolve()
    if baseline_path == repair_path or any(output.is_relative_to(path) for path in (baseline_path, repair_path)):
        raise ValueError("Comparison output and the two analyses must be separate")
    input_hashes = {str(path / "seal.json"): digest(path / "seal.json") for path in (baseline_path, repair_path)}
    baseline, _ = load_analysis(baseline_path)
    repair, _ = load_analysis(repair_path)
    pairs = bind_rows(baseline, repair, args.expected_checkpoints)
    aggregates, checkpoints = aggregate(pairs), checkpoint_table(pairs)
    latency, generators = latency_table(pairs), generator_counts_table(pairs)
    categories = Counter((row["baseline_classification"], row["repair_classification"]) for row in checkpoints)
    category_rows = [{"baseline_classification": a, "repair_classification": b, "checkpoints": count,
                      "classification_changed": a != b} for (a, b), count in sorted(categories.items())]
    details, summaries = diagnostic_tables(repair)
    if any(digest(Path(path)) != h for path, h in input_hashes.items()):
        raise ValueError("Input analysis changed during comparison")
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name, rows in (("aggregate", aggregates), ("checkpoints", checkpoints), ("classification_transitions", category_rows),
                       ("repair_recorded_diagnostics", details), ("repair_diagnostic_summary", summaries),
                       ("wall_latency", latency), ("actual_generator_counts", generators)):
        write_csv(output / f"{name}.csv", rows)
    summary = {"scope": "Targeted matched development regression selected after baseline failures; not held-out.",
               "matched_checkpoints": len(pairs), "baseline_full_checkpoints_context_only": len(baseline),
               "baseline_matched": counts([a for a, _ in pairs]), "repair_matched": counts([b for _, b in pairs]),
               "usefulness_transitions": dict(Counter(r["usefulness_transition"] for r in checkpoints)),
               "disclosure_transitions": dict(Counter(r["disclosure_transition"] for r in checkpoints)),
               "classification_transitions": category_rows, "aggregates": aggregates,
               "wall_latency": latency, "actual_generator_counts": generators,
               "answer_text_changed": sum(r["answer_text_changed"] for r in checkpoints),
               "human_validation": "pending", "new_semantic_scoring": False, "inference": False}
    write_json(output / "comparison.json", summary)
    before, after = summary["baseline_matched"], summary["repair_matched"]
    text = ["# Matched changing-memory repair comparison", "",
            f"The same {len(pairs)} checkpoint IDs and complete expected-state/rubric objects match exactly.", "",
            "| Metric | Original matched baseline | Repaired runtime | Change |", "| --- | ---: | ---: | ---: |"]
    text += [f"| {key} | {before[key]} | {after[key]} | {after[key] - before[key]:+d} |" for key in METRICS]
    text += ["", "These selected development scenarios were chosen after baseline failures. This is a targeted matched regression, not held-out evaluation. The full baseline count is context only and is never used as a comparison denominator.", "",
             "Existing frozen assistant judgments determine every success/disclosure/category count. No answer is rescored. Withholding, interruption and missing delivery never count as useful recall. Human validation is pending.", "",
             "`aggregate.csv` includes all checkpoints and branch, history, restart, expected-kind and scenario splits. All deltas are repair minus baseline; positive disclosure or withholding deltas mean more failures. `classification_transitions.csv` reports both changed and unchanged judgment categories. `checkpoints.csv` preserves both delivered answers and original review reasons.", "",
             "`revoked_original_disclosure` requires a correction/deletion/expiry state and the original subject value in the frozen disclosed-value list. `unstored_replacement_disclosure` concerns replacement claims in deletion/expiry branches that never stored that value. These are judgment-derived counts, not new text matching.", "",
             "Repair diagnostic files copy recorded new-system metadata only. Constraints come from the trace preserved in observed_record; routing and generation policy come from diagnostics. Null means absent or explicitly null; field-present flags distinguish those for constraint/generation policy. No constraint, policy or actual model is inferred from a task label or the answer text. These fields diagnose delivered-system paths; an answer constraint does not establish unconstrained model reasoning.", "",
             "`wall_latency.csv` reports measured end-to-end conversation-checkpoint wall time, including routing, retrieval, generation and validation. It excludes setup/mutation turns and admission/cooling gaps between operations. Timing requires an explicit wall_ns trace and matching diagnostic wall_seconds; missing timing is counted, never replaced with zero. Median uses the ordinary sample median; p95 is nearest-rank ceil(0.95*n). All-attempt rows include withheld/interrupted checkpoints. Delivered-only rows condition separately on each system's delivered status, so their membership and sample counts can differ. Deltas are descriptive, not randomized causal latency estimates.", "",
             "`actual_generator_counts.csv` counts returned generator model tags recorded in diagnostics for each system on the matched checkpoints. Multiple generation/fallback calls count separately; classifier calls and setup disclosures are excluded. Missing metadata and explicit empty returned-model lists are separate fields. Nominal routing decisions never substitute for actual model calls.", "",
             "Results concern text, real worker process restart and controlled logical expiry. They do not establish universal dialogue handling, power-loss recovery or spoken performance.", "",
             "Reproduce with the command recorded in `provenance.json` and a new output directory. Inputs and output are sealed; all unfavorable baseline and repair judgments are preserved."]
    (output / "README.md").write_text("\n".join(text) + "\n")
    (output / "comparison_source.py").write_bytes(Path(__file__).read_bytes())
    write_json(output / "provenance.json", {"created_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv], "script_sha256": digest(__file__), "input_sha256": input_hashes,
        "baseline": str(baseline_path), "repair": str(repair_path), "expected_checkpoints": args.expected_checkpoints,
        "exact_expected_object_match": True, "matched_checkpoint_ids": [a["checkpoint_id"] for a, _ in pairs],
        "new_semantic_scoring": False, "inference": False, "human_validation": "pending"})
    seal(output)
    print(json.dumps({"output": str(output), "matched": len(pairs), "baseline": before, "repair": after}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--repair", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-checkpoints", type=int, default=96)
    compare(parser.parse_args())


if __name__ == "__main__":
    main()
