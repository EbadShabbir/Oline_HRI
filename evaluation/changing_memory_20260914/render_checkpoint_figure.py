#!/usr/bin/env python3
"""Render the sealed assistant-reviewed checkpoint table; never infer scores.

Use system python3 on this Jetson: its installed matplotlib is available there.
No model, embedding, live trace, or unadjudicated answer file is read.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys


# These positions are the frozen authored schedule, not an ordering selected from scores.
STAGES = [
    ("correction", "prestore", "Before storing\nretained"),
    ("correction", "recalled", "Original recall\nretained"),
    ("correction", "corrected_retained", "After correction\nretained"),
    ("correction", "corrected_fresh", "After correction\nfresh"),
    ("correction", "historical_retained", "Historical control\nretained"),
    ("correction", "historical_fresh", "Historical control\nfresh"),
    ("correction", "restart_retained", "After restart\nretained"),
    ("correction", "restart_fresh", "After restart\nfresh"),
    ("correction", "restart_historical_retained", "Restart historical\nretained"),
    ("correction", "restart_historical_fresh", "Restart historical\nfresh"),
    ("deletion", "recalled", "Original recall\nretained"),
    ("deletion", "deleted_retained", "After deletion\nretained"),
    ("deletion", "deleted_fresh", "After deletion\nfresh"),
    ("deletion", "deleted_historical_retained", "Forgotten past\nretained"),
    ("deletion", "restart_retained", "After restart\nretained"),
    ("deletion", "restart_fresh", "After restart\nfresh"),
    ("deletion", "restart_historical_retained", "Restart forgotten past\nretained"),
    ("expiry", "before_retained", "Before expiry\nretained"),
    ("expiry", "before_fresh", "Before expiry\nfresh"),
    ("expiry", "at_retained", "At expiry\nretained"),
    ("expiry", "at_fresh", "At expiry\nfresh"),
    ("expiry", "after_retained", "After expiry\nretained"),
    ("expiry", "restart_retained", "After restart\nretained"),
    ("expiry", "restart_fresh", "After restart\nfresh"),
]
COLORS = {
    "R": ("Useful correct known recall", "#19776b", "white"),
    "U": ("Appropriate uncertainty", "#3e79b2", "white"),
    "D": ("Forbidden fact disclosure", "#c43c49", "white"),
    "F": ("Other unsuccessful delivered answer", "#e2b34c", "#17212b"),
    "W": ("Withheld or interrupted", "#727a86", "white"),
    "M": ("Missing final checkpoint record", "#f0f1f3", "#17212b"),
}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def verify_seal(directory):
    manifest = json.loads((directory / "seal.json").read_text())["sha256"]
    actual = {str(p.relative_to(directory)) for p in directory.rglob("*")
              if p.is_file() and p != directory / "seal.json"}
    if actual != set(manifest) or any(digest(directory / name) != value for name, value in manifest.items()):
        raise ValueError("Final analysis seal does not match its files")


def seal(directory):
    write(directory / "seal.json", {"sha256": {str(p.relative_to(directory)): digest(p)
          for p in sorted(directory.rglob("*")) if p.is_file()},
          "created_at": datetime.now(timezone.utc).isoformat(),
          "immutability": "exclusive creation, SHA256 manifest, read-only permissions; not privileged WORM"})
    for path in directory.rglob("*"):
        path.chmod(0o500 if path.is_dir() else 0o400)
    directory.chmod(0o500)


def figure_code(row):
    """Map existing judgments/status to display categories; no text scoring."""
    vote = row["judgment"]
    if vote["forbidden_disclosure"]:
        return "D"
    if not row["observed"] or row["diagnostics"]["status"] == "missing":
        return "M"
    if row["diagnostics"]["status"] != "delivered":
        return "W"
    if vote["useful_correct"]:
        if vote["classification"] == "appropriate_uncertainty":
            return "U"
        if vote["classification"] == "correct_recall":
            return "R"
        raise ValueError("Successful judgment has an incompatible classification")
    return "F"


def load_cells(analysis):
    verify_seal(analysis)
    provenance = json.loads((analysis / "provenance.json").read_text())
    if provenance["partial"]:
        raise ValueError("This figure requires a final analysis, not a partial snapshot")
    if provenance.get("human_validation") != "pending":
        raise ValueError("Review provenance changed; update the figure caption explicitly")
    rows = [json.loads(line) for line in (analysis / "reviewed_answers.jsonl").read_text().splitlines() if line.strip()]
    indexed = {row["checkpoint_id"]: row for row in rows}
    if len(rows) != 288 or len(indexed) != 288:
        raise ValueError("Exactly 288 unique planned checkpoint rows are required")
    scenario_ids = sorted({row["expected"]["scenario_id"] for row in rows})
    if len(scenario_ids) != 12:
        raise ValueError("Exactly 12 scenarios are required")
    cells = []
    for scenario_id in scenario_ids:
        for column, (branch, stage, label) in enumerate(STAGES, 1):
            key = f"{scenario_id}_{branch}_{stage}"
            if key not in indexed:
                raise ValueError(f"Missing frozen stage {key}")
            row = indexed[key]
            expected, vote, diagnostic = row["expected"], row["judgment"], row["diagnostics"]
            if expected["scenario_id"] != scenario_id or expected["branch"] != branch:
                raise ValueError(f"Stage identity disagreement: {key}")
            code = figure_code(row)
            cells.append({"scenario_id": scenario_id, "category": expected["category"],
                "column": column, "branch": branch, "stage": stage, "stage_label": label,
                "checkpoint_id": key, "blind_id": row["blind_id"], "logical_time": expected["logical_time"],
                "history_mode": expected["history_mode"], "after_restart": expected["after_restart"],
                "expected_kind": expected["expected_kind"], "expected_value": expected["expected_value"],
                "observed": row["observed"], "status": diagnostic["status"], "classification": vote["classification"],
                "useful_correct": vote["useful_correct"], "forbidden_disclosure": vote["forbidden_disclosure"],
                "disclosed_forbidden_values": json.dumps(vote["disclosed_forbidden_values"], ensure_ascii=False),
                "figure_code": code, "figure_label": COLORS[code][0], "fill_hex": COLORS[code][1],
                "delivered_answer": row["delivered_answer"], "judgment_reason": vote["reason"]})
    return cells, scenario_ids


def draw(cells, scenario_ids, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch, Rectangle

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "pdf.fonttype": 42, "ps.fonttype": 42})
    figure, axes = plt.subplots(1, 3, figsize=(22, 9), gridspec_kw={"width_ratios": [10, 7, 7]}, sharey=True)
    figure.subplots_adjust(left=0.115, right=0.99, bottom=0.29, top=0.82, wspace=0.07)
    branch_titles = (("correction", "CORRECTION · 10 checkpoints", 10),
                     ("deletion", "DELETION · 7 checkpoints", 7),
                     ("expiry", "EXPIRY · 7 checkpoints", 7))
    categories = {c["scenario_id"]: c["category"].replace("_", " ") for c in cells}
    for axis, (branch, title, ncols) in zip(axes, branch_titles):
        branch_stages = [(stage, label) for b, stage, label in STAGES if b == branch]
        by_key = {(c["scenario_id"], c["stage"]): c for c in cells if c["branch"] == branch}
        for y, scenario_id in enumerate(scenario_ids):
            for x, (stage, _) in enumerate(branch_stages):
                cell = by_key[(scenario_id, stage)]
                code = cell["figure_code"]
                axis.add_patch(Rectangle((x - .5, y - .5), 1, 1, facecolor=COLORS[code][1],
                                         edgecolor="white", linewidth=1.2,
                                         hatch="///" if code == "M" else None))
                axis.text(x, y, code, ha="center", va="center", color=COLORS[code][2], fontsize=10, weight="bold")
        axis.set(xlim=(-.5, ncols - .5), ylim=(11.5, -.5))
        axis.set_xticks(range(ncols), [label for _, label in branch_stages], rotation=55, ha="right", fontsize=9)
        axis.set_yticks(range(12), [f"{s.upper()} · {categories[s]}" for s in scenario_ids], fontsize=10)
        axis.tick_params(axis="both", length=0, pad=7)
        axis.set_title(title, loc="left", fontsize=12, weight="bold", pad=16)
        for spine in axis.spines.values():
            spine.set_visible(False)
    figure.text(.115, .951, "CLARA changing-memory checkpoints", fontsize=23, weight="bold", color="#17212b")
    figure.text(.115, .907, "12 fictional scenarios × 24 checkpoints · judgments of final delivered answers", fontsize=13, color="#374151")
    figure.text(.115, .872, "Independent blinded assistant review · human validation pending", fontsize=11, color="#4b5563")
    legend = [Patch(facecolor=color, edgecolor="none", label=f"{code}  {label}", hatch="///" if code == "M" else None)
              for code, (label, color, _) in COLORS.items()]
    figure.legend(handles=legend, loc="lower left", bbox_to_anchor=(.111, .093), ncol=3, frameon=False,
                  fontsize=10, columnspacing=2.5, handlelength=1.5, handleheight=1.2)
    figure.text(.115, .063, "Disclosure takes visual priority. Withheld or missing answers never count as useful recall. Historical controls are independently authorized dated events.",
                fontsize=9, color="#4b5563")
    figure.text(.115, .035, "Scope: actual process restart with evaluation history rehydration and controlled logical-time expiry; excludes power-loss recovery and spoken performance.",
                fontsize=9, color="#4b5563")
    figure.savefig(output / "checkpoint_heatmap.png", dpi=220, facecolor="white")
    figure.savefig(output / "checkpoint_heatmap.pdf", facecolor="white", metadata={
        "Title": "CLARA changing-memory checkpoints", "Subject": "Assistant-reviewed final delivered answers; human validation pending",
        "Creator": "render_checkpoint_figure.py"})
    plt.close(figure)
    return matplotlib.__version__


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cells, scenarios = load_cells(args.analysis)
    output = args.output.absolute()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    with (output / "sourcedata.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(cells[0]))
        writer.writeheader(); writer.writerows(cells)
    matplotlib_version = draw(cells, scenarios, output)
    write(output / "provenance.json", {"analysis": str(args.analysis.absolute()),
          "analysis_seal_sha256": digest(args.analysis / "seal.json"),
          "reviewed_answers_sha256": digest(args.analysis / "reviewed_answers.jsonl"),
          "script_sha256": digest(Path(__file__)), "command": sys.argv,
          "python": sys.version, "matplotlib": matplotlib_version, "cell_count": len(cells),
          "category_counts": {code: sum(c["figure_code"] == code for c in cells) for code in COLORS},
          "score_origin": "Existing sealed assistant judgments only; no answer-text scoring or score inference.",
          "human_validation": "pending", "frozen_stages": STAGES})
    (output / "README.md").write_text(
        "# Changing-memory checkpoint figure\n\nEach of 288 cells maps exactly to one row in `sourcedata.csv`. "
        "PNG is for viewing; PDF preserves vector cells and embedded text for export. "
        "Disclosure has priority over other categories. Useful known recall includes original, replacement and legitimate historical-control answers. "
        "Unknown-fact success is shown separately as appropriate uncertainty. Withheld/interrupted and missing answers are unsuccessful. "
        "Scores come only from the sealed reviewed-answer artifact. Independent blinded assistant review; human validation is pending.\n\n"
        "The study concerns real process restart and controlled logical-time expiry; it establishes neither power-loss recovery nor spoken performance.\n")
    seal(output)
    print(json.dumps({"output": str(output), "cells": len(cells), "matplotlib": matplotlib_version}))


if __name__ == "__main__":
    main()
