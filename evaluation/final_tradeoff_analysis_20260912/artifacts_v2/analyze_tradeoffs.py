"""Descriptive post-collection analysis of the completed Step 3 text pilot.

This runs no models and never modifies its inputs. Resolved quality comes from
the blinded mapping and semantic review, not the pending row-metric placeholder.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import shutil
import statistics

HERE = Path(__file__).resolve().parent
STEP3 = HERE.parent / "post_memory_comparison_20260912"
ARMS = ("small", "large", "cascade")
LABELS = {"small": "Small-only", "large": "Large-only", "cascade": "Cascade"}
COLORS = {"small": "#0072B2", "large": "#D55E00", "cascade": "#009E73"}
SUCCESS = {"complete", "appropriate_abstention", "appropriate_uncertainty"}
READOUTS = (5, 10, 15, 30)


def check(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def key(row):
    return row["arm"], row["repetition"], row["case_id"]


def load_inputs():
    directory = STEP3 / "analysis_v2_reviewed"
    names = ("analysis.json", "semantic_review.json", "blinded_mapping.jsonl",
             "blinded_review.jsonl", "review_manifest.json", "row_metrics.jsonl",
             "deadline_quality_curve.json")
    hashes = {str(directory / name): digest(directory / name) for name in names}
    report = read(directory / "analysis.json")
    completed = read(STEP3 / "completion_v2.json")
    check(digest(directory / "analysis.json") == completed["result_files_sha256"][
        "evaluation/post_memory_comparison_20260912/analysis_v2_reviewed/analysis.json"],
        "Completed Step 3 analysis changed")
    check(report["complete"] and report["integrity_valid"] and report["observed_attempts"] == 432,
          "Requires the complete, valid 432-attempt comparison")
    review = read(directory / "semantic_review.json")
    check(review == report["semantic_review"], "Saved semantic review differs")
    check(review["resolved_unique_outputs"] == 145 and not review["pending_unique_output_ids"]
          and not review["conflicting_review_ids"], "Quality review is incomplete")
    check(review["reviewer_types"] == ["assistant"] and not review["human_validation_complete"],
          "Unexpected review provenance")
    manifest = read(directory / "review_manifest.json")
    check(manifest["mapping_sha256"] == digest(directory / "blinded_mapping.jsonl")
          and manifest["blinded_worksheet_sha256"] == digest(directory / "blinded_review.jsonl"),
          "Blinded mapping or worksheet hash mismatch")
    mapping = lines(directory / "blinded_mapping.jsonl")
    worksheet = {row["review_id"]: row for row in lines(directory / "blinded_review.jsonl")}
    check(len(mapping) == len(worksheet) == 145, "Unexpected blinded-group coverage")
    scores = {}
    for group in mapping:
        review_id = group["review_id"]
        opinions = review["review_opinions"][review_id]
        check(len(opinions) == 1, "Expected one resolved judgment per group")
        opinion = opinions[0]
        success = opinion["judgment"] in SUCCESS
        check(not success or not (opinion["unsupported_personal_claim"] or
                                  opinion["forbidden_or_stale_claim"]), "Disqualified full success")
        for observation in group["observations"]:
            identity = key(observation)
            check(identity not in scores, "Duplicate mapped request")
            scores[identity] = {"review_id": review_id, "judgment": opinion["judgment"],
                                "correct": success,
                                "unsupported_personal_claim": opinion["unsupported_personal_claim"],
                                "forbidden_or_stale_claim": opinion["forbidden_or_stale_claim"]}
    rows = lines(directory / "row_metrics.jsonl")
    check(len(rows) == len(scores) == len({key(row) for row in rows}) == 432,
          "Unexpected or duplicated attempt coverage")
    placeholders = Counter()
    for row in rows:
        placeholders[str(row["semantic_quality"])] += 1
        row.update(scores[key(row)])
        check(not row["correct"] or row["delivered"], "A failed delivery received quality credit")
        check(math.isfinite(row["wall_seconds"]) and row["wall_seconds"] > 0,
              "Invalid request latency")
    cases = {row["case_id"] for row in rows}
    check(len(cases) == 48, "Unexpected distinct-item count")
    for arm in ARMS:
        check(sum(row["arm"] == arm for row in rows) == 144, "Unequal arm coverage")
        for repetition in (1, 2, 3):
            subset = [row for row in rows if row["arm"] == arm and row["repetition"] == repetition]
            check(len(subset) == 48 and {row["case_id"] for row in subset} == cases,
                  "Incomplete or mismatched repeated workload")
    curve = read(directory / "deadline_quality_curve.json")
    check(curve == report["deadline_quality_curve"], "Saved deadline curve differs")
    for arm in ARMS:
        subset = [row for row in rows if row["arm"] == arm]
        check(curve["arms"][arm]["planned_denominator"] == 144, "Wrong curve denominator")
        for point in curve["arms"][arm]["points"]:
            count = sum(row["correct"] and row["wall_seconds"] <= point["deadline_seconds"]
                        for row in subset)
            check(count == point["correct_delivered_count"] and math.isclose(
                count / 144, point["fraction_of_planned"], abs_tol=1e-12),
                "Deadline curve does not match resolved request-level quality")
    return report, rows, hashes, dict(placeholders)


def summarize(report, rows):
    result = {"arms": {}, "deadline_readouts": [], "repetitions": [],
              "paired_success_patterns": report["semantic_review"]["paired_success_patterns"]}
    for arm in ARMS:
        selected = [row for row in rows if row["arm"] == arm]
        old = report["arms"][arm]
        sessions = [session for session in report["sessions"] if session["arm"] == arm]
        correct = sum(row["correct"] for row in selected)
        check(correct == report["semantic_review"]["arms"][arm]["correct_reviewed"],
              "Quality total mismatch")
        mean = statistics.mean(row["wall_seconds"] for row in selected)
        check(math.isclose(mean, old["latency_all_seconds"]["mean"], abs_tol=1e-12),
              "Mean latency mismatch")
        energy = sum(session["telemetry"]["whole_interval_energy_joules"] for session in sessions)
        request_energy = sum(session["telemetry"]["request_intervals_energy_joules"] for session in sessions)
        covered = sum(session["telemetry"]["request_interval_covered_seconds"] for session in sessions)
        requested = sum(row["wall_seconds"] for row in selected)
        generator_models = Counter(model for row in selected for model in row["generation_models"])
        result["arms"][arm] = {
            "attempts": 144, "distinct_items": 48, "correct": correct,
            "quality_percent": 100 * correct / 144,
            "delivered": sum(row["delivered"] for row in selected),
            "latency_all_seconds": old["latency_all_seconds"],
            "latency_delivered_seconds": old["latency_delivered_seconds"],
            "generator_models": dict(generator_models),
            "backend_load_seconds": sum(row["ollama_load_seconds"] for row in selected),
            "whole_interval_energy_joules": energy,
            "whole_interval_joules_per_attempt": energy / 144,
            "whole_interval_joules_per_full_success": energy / correct,
            "request_interval_energy_joules": request_energy,
            "request_interval_coverage_seconds": covered,
            "request_interval_requested_seconds": requested,
            "request_energy_coverage_fraction": covered / requested,
            "peak_whole_device_ram_mib": max(s["telemetry"]["peak_ram_used_mb"] for s in sessions),
            "peak_whole_device_logical_swap_mib": max(s["telemetry"]["peak_swap_used_mb"] for s in sessions),
        }
        for deadline in READOUTS:
            result["deadline_readouts"].append({"arm": arm, "deadline_seconds": deadline,
                "correct_delivered": sum(row["correct"] and row["wall_seconds"] <= deadline for row in selected),
                "validated_delivered": sum(row["delivered"] and row["wall_seconds"] <= deadline for row in selected),
                "denominator": 144})
        for repetition in (1, 2, 3):
            subset = [row for row in selected if row["repetition"] == repetition]
            result["repetitions"].append({"arm": arm, "repetition": repetition, "attempts": 48,
                "correct": sum(row["correct"] for row in subset),
                "mean_seconds": statistics.mean(row["wall_seconds"] for row in subset)})
    return result


def table(headers, body):
    return "\n".join(["| " + " | ".join(headers) + " |",
                       "| " + " | ".join("---" for _ in headers) + " |"] +
                      ["| " + " | ".join(str(value) for value in row) + " |" for row in body])


def markdown(result):
    parts = ["# Final quality, latency and cost analysis", "",
        "This is a post-collection analysis of Step 3's 432 attempts, not another model experiment. "
        "It adds figures, descriptive deadline readouts and measured cost summaries without changing any "
        "answer or judgment. Step 4 was not named in the saved plan; this final-analysis scope was stated "
        "as the working interpretation while clarification was requested.", "",
        "Quality is full-rubric success including appropriate abstention when called for, assessed by "
        "blinded assistant reviewers. Human validation remains pending. Each arm repeats the same 48 requests "
        "three times; repetitions and shared scenarios are dependent. No confidence interval, significance "
        "claim, noninferiority margin, quality floor or acceptance deadline is inferred.", "",
        "## Overall observed tradeoff", "",
        table(["System", "Success / attempts", "Mean / median / p95, s", "Validated"], [
            [LABELS[arm], f"{value['correct']}/144 ({value['quality_percent']:.1f}%)",
             " / ".join(f"{value['latency_all_seconds'][key]:.3f}" for key in ("mean", "p50", "p95")),
             f"{value['delivered']}/144"] for arm, value in result["arms"].items()]), "",
        "All-attempt timing includes cold loads and failures. A fast invalid response earns no success credit. "
        "This measures the complete text pipeline, not spoken latency. The larger system's memory classifier "
        "can change supplied evidence, so these are not matched-evidence generator-capability measurements.", "",
        "## Correct answers delivered by a deadline", "",
        "The complete empirical curves are primary. The 5, 10, 15 and 30-second rows below are post-hoc reading "
        "coordinates, not chosen application requirements or success thresholds. Every denominator includes "
        "all 144 requested tasks, including failures.", "",
        table(["Deadline", "Small-only", "Large-only", "Cascade"], [
            [f"{deadline} s"] + [f"{next(row['correct_delivered'] for row in result['deadline_readouts'] if row['arm']==arm and row['deadline_seconds']==deadline)}/144"
                                   for arm in ARMS] for deadline in READOUTS]), "",
        "![Correct delivery and validated delivery curves](deadline_curves.png)", "",
        "The left panel counts only fully correct delivered answers. The right panel counts every validated "
        "delivery, including semantically wrong answers. These are different outcomes; neither uses only "
        "successful requests as its denominator. Curves are right-continuous and use complete request time.", "",
        "## Repetition and complementary outcomes", "",
        table(["System", "Round", "Success / 48", "Mean time, s"], [
            [LABELS[row["arm"]], row["repetition"], row["correct"], f"{row['mean_seconds']:.3f}"]
            for row in sorted(result["repetitions"], key=lambda x: (x["repetition"], ARMS.index(x["arm"]))) ]), "",
        "![Pooled tradeoff and each repeated session](quality_latency_rounds.png)", "",
        "The pooled cascade mean is 20.8% below large-only, but large-only is faster in rounds 2 and 3. "
        "Large-only round 1 had much less reported GPU allocation (61.5%) than the first cascade session's "
        "large model (83.6–86.2%). This makes causal attribution to routing inappropriate. Only 3/144 cascade "
        "generations used small; 141 used large. The observed aggregate points are not an optimized or "
        "statistically established Pareto frontier.", "",
        "Large-only alone succeeds on 4, 6 and 7 cases that small-only misses in the respective rounds; "
        "small-only alone succeeds on 5 cases in each round. The deployed cascade still misses small-only "
        "wins. These paired results describe complementary complete-system behavior, not a deployable "
        "oracle or a measured latency for a different routing policy. The exact patterns are in summary.json.", "",
        "## Measured cost and additional complexity", "",
        table(["System", "Whole sampled energy, kJ", "J / attempted task", "Total J / full success", "Backend loading, s", "Actual small / large generators"], [
            [LABELS[arm], f"{v['whole_interval_energy_joules']/1000:.3f}",
             f"{v['whole_interval_joules_per_attempt']:.1f}", f"{v['whole_interval_joules_per_full_success']:.1f}",
             f"{v['backend_load_seconds']:.3f}",
             f"{v['generator_models'].get('qwen3:0.6b',0)} / {v['generator_models'].get('qwen3:1.7b',0)}"]
            for arm,v in result["arms"].items()]), "",
        "Energy integrates sampled whole-device VDD_IN, including setup, cleanup and background work, "
        "without idle subtraction. Scheduler waits are excluded. Total joules divided by full successes "
        "allocates the cost of every failed or wrong attempt too; it is not energy measured only on correct "
        "requests. Loading is already included in latency/energy and must not be added again. Separate "
        "request-window energy and its sampling coverage are saved in summary.json. These results do not "
        "isolate model energy or predict another session order.", "",
        table(["System", "Peak whole-device RAM, MiB", "Peak logical swap, MiB"], [
            [LABELS[arm], v["peak_whole_device_ram_mib"], v["peak_whole_device_logical_swap_mib"]]
            for arm,v in result["arms"].items()]), "",
        "These are session maxima with background activity, not isolated model footprints. Existing zram "
        "occupancy is logical usage of compressed pages in physical RAM, not additional RAM or a measure "
        "of active swapping. CPU and GPU allocations share physical memory on this Jetson.", "",
        "## Supported conclusion and remaining evidence", "",
        "This pilot does not establish a useful adaptive-selection advantage. Cascade adds two successes "
        "over large-only and four over small-only across 144 dependent attempts, while taking 3.85 times "
        "the small-only mean request time and incurring greater loading cost than either fixed arm. "
        "The general-task gains coexist with personal-recall regressions, and every system scores 0/36 on "
        "full temporal/synthesis rubrics. Neither a requirement-level feasible winner nor quality equivalence "
        "has been established.", "",
        "New independent scenarios and human grading, matched-evidence generator controls, stable-placement "
        "replication, retrieval-policy ablations, live changing-memory episodes and microphone-to-speaker "
        "tests remain separate work. Existing ARC results are not pooled into this application pilot. "
        "No runtime, memory database, swap configuration or model residency was changed for this analysis.", "",
        "Figures are provided as PNG previews and vector PDF/SVG. CSV files contain the plotted curves, "
        "deadline readouts and per-round values. Input hashes, analysis source and plotting package versions "
        "are preserved in provenance.json and the archived script.", ""]
    return "\n".join(parts)


def figures(rows, result, output):
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/clara-step4-matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "svg.hashsalt": "clara-step4-observed-v1", "pdf.fonttype": 42})
    max_time = max(row["wall_seconds"] for row in rows)
    times = sorted({0.0, 55.0} | {row["wall_seconds"] for row in rows})
    curves = []
    fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.5), constrained_layout=True)
    for arm in ARMS:
        subset = [row for row in rows if row["arm"] == arm]
        correct = [100*sum(row["correct"] and row["wall_seconds"] <= t for row in subset)/144 for t in times]
        delivered = [100*sum(row["delivered"] and row["wall_seconds"] <= t for row in subset)/144 for t in times]
        for t, good, sent in zip(times, correct, delivered):
            curves.append({"arm": arm, "deadline_seconds": t,
                           "correct_delivered_percent_of_144": good,
                           "validated_delivered_percent_of_144": sent})
        axes[0].step(times, correct, where="post", label=LABELS[arm], color=COLORS[arm], linewidth=2)
        axes[1].step(times, delivered, where="post", label=LABELS[arm], color=COLORS[arm], linewidth=2)
    for axis in axes:
        axis.set(xlim=(0, 55), ylim=(0, 100), xlabel="Complete text-response deadline (s)",
                 ylabel="Percentage of all 144 requested tasks")
        axis.grid(alpha=.2)
        axis.legend(loc="upper left" if axis is axes[0] else "lower right", frameon=False)
    axes[0].set_title("(a) Fully correct and delivered")
    axes[1].set_title("(b) Validated delivery, regardless of correctness")
    fig.suptitle("Observed deadline curves · 48 items × 3 repeats ·assistant-scored quality", fontsize=11)
    save_figure(fig, output / "deadline_curves")
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.7), constrained_layout=True)
    for index, arm in enumerate(ARMS):
        value = result["arms"][arm]
        mean = value["latency_all_seconds"]["mean"]
        quality = value["quality_percent"]
        axes[0].scatter(mean, quality, color=COLORS[arm], s=75, label=LABELS[arm], zorder=3)
        offsets = {"small": (8, -20), "large": (6, -21), "cascade": (-8, 12)}
        axes[0].annotate(f"{LABELS[arm]}\n{value['correct']}/144", (mean, quality),
                         textcoords="offset points", xytext=offsets[arm], fontsize=9,
                         ha="right" if arm == "cascade" else "left")
        subset = [row for row in result["repetitions"] if row["arm"] == arm]
        xs = [row["repetition"] + (index-1)*.24 for row in subset]
        heights = [row["mean_seconds"] for row in subset]
        bars = axes[1].bar(xs, heights, width=.22, color=COLORS[arm], label=LABELS[arm])
        axes[1].bar_label(bars, labels=[f"{value:.2f}" for value in heights], fontsize=8, padding=3)
    axes[0].set(xlim=(0, 16), ylim=(0, 40), xlabel="Mean complete request time (s)",
                ylabel="Full-rubric success (% of 144 attempts)", title="(a) Pooled observed quality/time points")
    axes[1].set(xticks=[1, 2, 3], xticklabels=["Round 1", "Round 2", "Round 3"], ylim=(0, 21),
                ylabel="Mean complete request time (s)", title="(b) The speed ranking changes by round")
    axes[1].legend(frameon=False, loc="upper right", fontsize=9)
    for axis in axes:
        axis.grid(axis="y", alpha=.2)
        axis.set_axisbelow(True)
    fig.suptitle("Cold loads and failures included ·placement varied ·no independent-sample intervals", fontsize=11)
    save_figure(fig, output / "quality_latency_rounds")
    plt.close(fig)
    return curves


def save_figure(figure, stem):
    for extension in ("png", "pdf", "svg"):
        figure.savefig(stem.with_suffix("."+extension), dpi=220, bbox_inches="tight")


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def write_csv(path, rows):
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    report, rows, inputs, placeholders = load_inputs()
    result = summarize(report, rows)
    result.update({"scope": "post-collection descriptive analysis; no new inference or scoring",
                   "attempts": 432, "distinct_requests": 48, "repetition_count": 3,
                   "review_groups": 145, "human_validation_complete": False,
                   "deadline_readout_scope": "post-hoc descriptive coordinates; not acceptance thresholds",
                   "no_quality_or_responsiveness_requirement_selected": True,
                   "row_metric_quality_placeholders_ignored": placeholders})
    os.umask(0o077)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    curves = figures(rows, result, args.output_dir)
    write_json(args.output_dir / "summary.json", result)
    write_csv(args.output_dir / "deadline_readouts.csv", result["deadline_readouts"])
    write_csv(args.output_dir / "deadline_curves.csv", curves)
    write_csv(args.output_dir / "repetitions.csv", result["repetitions"])
    with (args.output_dir / "report.md").open("x", encoding="utf-8") as stream:
        stream.write(markdown(result))
    shutil.copyfile(__file__, args.output_dir / "analyze_tradeoffs.py")
    outputs = {path.name: digest(path) for path in sorted(args.output_dir.iterdir()) if path.is_file()}
    check(all(digest(Path(path)) == expected for path, expected in inputs.items()),
          "Input evidence changed during analysis")
    write_json(args.output_dir / "provenance.json", {
        "recorded_at": datetime.now(timezone.utc).isoformat(), "script_sha256": digest(Path(__file__)),
        "input_sha256": inputs, "output_sha256": outputs, "inputs_unchanged": True,
        "python": platform.python_version(),
        "plotting_packages": {name: version(name) for name in ("matplotlib", "numpy", "pillow")},
        "inference_calls": 0, "scoring_changes": False, "system_configuration_changes": False,
        "quality_source": "Resolved semantic_review.review_opinions joined through blinded_mapping; row_metrics.semantic_quality ignored",
        "deadline_curve_verified_from_request_labels": True,
        "deadline_readouts": list(READOUTS), "deadline_readout_scope": "descriptive post-hoc coordinates, not requirements",
        "plotting_environment": "separate temporary virtual environment; CLARA runtime environment unchanged",
    })
    print(json.dumps({"status": "complete", "attempts": len(rows), "output": str(args.output_dir.resolve()),
                      "quality_percent": {arm: v["quality_percent"] for arm,v in result["arms"].items()}}))


if __name__ == "__main__":
    main()
