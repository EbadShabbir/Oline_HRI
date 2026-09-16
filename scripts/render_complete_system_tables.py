"""Render descriptive tables from a validated, fully reviewed observed population."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from analyze_arc_capability import distribution


ARMS = ("small", "large", "cascade")
LABELS = {"small": "Qwen3 0.6B alone", "large": "Qwen3 1.7B alone", "cascade": "CLARA cascade"}
SUCCESS = {"complete", "appropriate_abstention", "appropriate_uncertainty"}


def read(path):
    return json.loads(path.read_text())


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def n(value):
    return "—" if value is None else f"{value:.3f}"


def fraction(a, b):
    return "—" if not b else f"{a}/{b} ({100*a/b:.1f}%)"


def render(source):
    report = read(source / "analysis.json")
    quality = report["semantic_review"]
    if not report["integrity_valid"] or quality["status"] != "complete_for_observed_unique_outputs" or quality["conflicting_review_ids"]:
        raise ValueError("tables require valid artifacts and resolved observed reviews")
    rows = jsonl(source / "row_metrics.jsonl")
    mappings = jsonl(source / "blinded_mapping.jsonl")
    scores = {}
    for entry in mappings:
        opinions = quality["review_opinions"][entry["review_id"]]
        assert len({(o["judgment"], o["unsupported_personal_claim"], o["forbidden_or_stale_claim"]) for o in opinions}) == 1
        for observation in entry["observations"]:
            key = (observation["arm"], observation["repetition"], observation["case_id"])
            assert key not in scores
            scores[key] = opinions[0]["judgment"] in SUCCESS
    assert len(scores) == len(rows) == report["observed_attempts"]
    assert len({(r["arm"], r["repetition"], r["case_id"]) for r in rows}) == len(rows)
    for arm in ARMS:
        assert sum(value for key, value in scores.items() if key[0] == arm) == quality["arms"][arm]["correct_reviewed"]
    lines = ["### Observed coverage and answer quality", "",
        "Correctness is assistant-assessed full-rubric success, including appropriate abstention or uncertainty only when the rubric calls for it. Technical failures count as unsuccessful attempted requests. These are observed rates with unequal coverage, not complete three-round scores or independent samples.", "",
        "| System | Attempts / planned | Distinct items observed | Validated / attempted | Correct / attempted | Unattempted requests |",
        "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for arm in ARMS:
        a, q = report["arms"][arm], quality["arms"][arm]
        distinct = len({r["case_id"] for r in rows if r["arm"] == arm})
        lines.append(f"| {LABELS[arm]} | {a['attempted']}/{a['planned']} | {distinct} | {fraction(a['delivered'], a['attempted'])} | {fraction(q['correct_reviewed'], a['attempted'])} | {a['unattempted']} |")
    lines += ["", "### Same observed requests across all three systems", ""]
    common = set.intersection(*[{r["case_id"] for r in rows if r["arm"] == arm and r["repetition"] == 1} for arm in ARMS])
    lines += [f"This comparison uses the same {len(common)} first-round requests observed in every arm, including interrupted or withheld responses as failures. The subset ends at the cascade stop; it is not a separately sampled benchmark. All latency values are seconds and include the initial cold request.", "",
        "| System | Correct / common items | Validated / common items | Mean all | Median all | p95 all | Median delivered | p95 delivered |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    matched = {}
    for arm in ARMS:
        selected = [r for r in rows if r["arm"] == arm and r["repetition"] == 1 and r["case_id"] in common]
        all_t = distribution([r["wall_seconds"] for r in selected])
        delivered = [r for r in selected if r["delivered"]]
        delivered_t = distribution([r["wall_seconds"] for r in delivered])
        correct = sum(scores[(arm, 1, r["case_id"])] for r in selected)
        matched[arm] = {"attempts": len(selected), "correct": correct, "delivered": len(delivered), "all_latency_seconds": all_t, "delivered_latency_seconds": delivered_t,
                        "stratum_counts": dict(Counter(r["stratum"] for r in selected))}
        lines.append(f"| {LABELS[arm]} | {fraction(correct, len(selected))} | {len(delivered)}/{len(selected)} | {n(all_t['mean'])} | {n(all_t['p50'])} | {n(all_t['p95'])} | {n(delivered_t['p50'])} | {n(delivered_t['p95'])} |")
    lines += ["", "The backend placement differs between arms and sessions. Matched prompts control item coverage, but do not isolate the effect of routing from CPU/GPU placement or device state.", "",
        "### Correctness by request category", "",
        "Cells are correct / observed attempts; achieved repetition counts differ between arms. Each category had 36 planned attempts per arm.", "",
        "| Category | Qwen3 0.6B alone | Qwen3 1.7B alone | CLARA cascade |",
        "| --- | ---: | ---: | ---: |"]
    strata = [("routine_general", "Routine general"), ("general_multiconstraint", "General, multiple constraints"),
              ("personal_recall", "Direct personal recall"), ("personal_temporal_synthesis", "Personal temporal / synthesis")]
    for stratum, label in strata:
        values = [quality["arms"][arm]["by_stratum"][stratum] for arm in ARMS]
        lines.append("| " + label + " | " + " | ".join(fraction(v["correct_reviewed"], v["observed_attempts"]) for v in values) + " |")
    lines += ["", "### Session outcomes and timing", "",
        "All timing is in seconds, from text-request entry to full validated delivery or failure. Mean, median and p95 here include failed attempts and the initial request. Setup is reported separately below. No request in an interrupted session is replaced.", "",
        "| Session | Outcome | Attempts / 48 | Validated | Correct | First | Mean all | Median all | p95 all | Total request time |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for s in report["sessions"]:
        selected = [r for r in rows if r["arm"] == s["arm"] and r["repetition"] == s["repetition"]]
        t = distribution([r["wall_seconds"] for r in selected])
        correct = sum(scores[(r["arm"], r["repetition"], r["case_id"])] for r in selected)
        outcome = {"complete_with_errors": "Completed with withheld outputs", "missing": "Not started"}.get(s["status"], s["status"])
        if s["status"] == "interrupted":
            guard = (s.get("finish") or {}).get("guard_violation")
            outcome = "RAM-floor interruption" if guard in {"available memory crossed the runtime floor", "telemetry RAM floor crossed"} else f"Interrupted: {guard or 'see finish record'}"
        lines.append(f"| {s['directory']} | {outcome} | {len(selected)}/48 | {s['delivered']} | {correct if selected else '—'} | {n(s.get('first_request_seconds'))} | {n(t['mean'])} | {n(t['p50'])} | {n(t['p95'])} | {n(t['sum']) if selected else '—'} |")
    lines += ["", "### Delivered-response and failed-attempt latency", "",
        "These pooled values describe the observed population, whose coverage and placement vary. Validated delivery does not imply a correct answer.", "",
        "| System | Delivered count | Delivered mean / median / p95, s | Failed count | Failed mean / median / p95, s |",
        "| --- | ---: | ---: | ---: | ---: |"]
    for arm in ARMS:
        a = report["arms"][arm]
        d, f = a["latency_delivered_seconds"], a["latency_failed_seconds"]
        lines.append(f"| {LABELS[arm]} | {d['n']} | {' / '.join(n(d[k]) for k in ('mean','p50','p95'))} | {f['n']} | {' / '.join(n(f[k]) for k in ('mean','p50','p95'))} |")
    lines += ["", "### Pipeline calls and loading cost", "",
        "Counts and totals cover observed attempts, including failures. Routing includes loading needed by classifiers. Backend loading time is already contained in request/call time; do not add it again.", "",
        "| System | Memory / compute / generation calls | Actual 0.6B / 1.7B generator calls | Total routing, s | Total retrieval, s | Total backend loading, s | Loading / total request time |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for arm in ARMS:
        a = report["arms"][arm]
        counts = Counter()
        for row in rows:
            if row["arm"] == arm:
                counts.update(row["call_counts"])
        load, wall = a["ollama_load_seconds"]["sum"], a["latency_all_seconds"]["sum"]
        lines.append(f"| {LABELS[arm]} | {' / '.join(str(counts[k]) for k in ('memory_selector','compute_selector','generation'))} | {a['generation_models'].get('qwen3:0.6b',0)} / {a['generation_models'].get('qwen3:1.7b',0)} | {n(a['routing_seconds']['sum'])} | {n(a['retrieval_seconds']['sum'])} | {n(load)} | {100*load/wall:.1f}% |")
    lines += ["", "### Whole-device resources and setup", "",
        "RAM and logical swap are MiB; energy is kJ. Peaks and total energy include embedding/database setup and model cleanup. Energy integrates onboard VDD_IN samples without idle subtraction and includes desktop activity; it is not calibrated model-only energy.", "",
        "| Session | Setup, s | Peak RAM | Peak swap | Peak temperature, °C | Observed interval, s | Whole-interval energy, kJ | Request-interval energy, kJ |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for s in report["sessions"]:
        if not s["attempted"]:
            continue
        t = s["telemetry"]
        lines.append(f"| {s['directory']} | {n(s.get('memory_setup_seconds'))} | {t['peak_ram_used_mb']} | {t['peak_swap_used_mb']} | {n(t['peak_temperature_c'])} | {n(t['duration_seconds'])} | {n(t['whole_interval_energy_joules']/1000)} | {n(t['request_intervals_energy_joules']/1000)} |")
    uncovered = []
    for s in report["sessions"]:
        t = s.get("telemetry") or {}
        covered, requested = t.get("request_interval_covered_seconds"), t.get("request_interval_requested_seconds")
        if covered is not None and requested is not None and requested - covered > 0.000001:
            uncovered.append(f"{s['directory']} covers {n(covered)} of {n(requested)} request seconds")
    energy_note = "Request-energy integration covers only sampled overlap. "
    energy_note += ("; ".join(uncovered) + "; uncovered intervals are not extrapolated. ") if uncovered else "Every executed request interval has sampled overlap over its full duration. "
    energy_note += "Scheduler waits and gaps between sessions are outside these intervals."
    lines += ["", energy_note, "",
        "### Semantic judgment breakdown", "",
        "Counts retain repeated observations; these are not counts of independent questions. The forbidden-claim flag follows each whole rubric, including general-task constraints, and is not a personal-data disclosure count.", "",
        "| System | Complete | Appropriate abstention | Appropriate uncertainty | Partial | Incorrect | Inappropriate abstention | Technical failure | Unsupported personal claim | Forbidden / stale rubric claim |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for arm in ARMS:
        q = quality["arms"][arm]
        counts = [q["judgments"].get(k, 0) for k in ("complete","appropriate_abstention","appropriate_uncertainty","partial","incorrect","inappropriate_abstention","technical_failure")]
        counts += [q["unsupported_personal_claim_attempts"], q["forbidden_or_stale_claim_attempts"]]
        lines.append("| " + LABELS[arm] + " | " + " | ".join(map(str, counts)) + " |")
    return "\n".join(lines) + "\n", matched


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    content, matched = render(args.analysis_dir)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "tables.md").write_text(content)
    (args.output_dir / "matched_first_round.json").write_text(json.dumps(matched, indent=2) + "\n")
    provenance = {"source_directory": str(args.analysis_dir.resolve()), "renderer_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
                  "input_sha256": {name: sha256((args.analysis_dir/name).read_bytes()).hexdigest() for name in ("analysis.json","row_metrics.jsonl","blinded_mapping.jsonl")}}
    (args.output_dir / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")


if __name__ == "__main__":
    main()
