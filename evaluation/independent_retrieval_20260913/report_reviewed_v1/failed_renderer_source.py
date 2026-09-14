"""Render completed reviewed independent-retrieval analysis; standard library only.

This module never imports inference code, loads a model, rescans personal
memory, assigns judgments, or recomputes statistical intervals. All outcomes
come from the supplied sealed analysis and its reviewed attempt CSV.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import shlex
import statistics
from urllib.parse import quote


MODELS = ("qwen3:0.6b", "qwen3:1.7b")
POLICIES = ("OFF", "ALWAYS", "SELECTIVE")
CATEGORIES = (
    ("direct_personal_recall", "Direct recall"),
    ("paraphrased_personal_recall", "Paraphrased recall"),
    ("multi_fact_personal", "Multi-fact personal"),
    ("general_no_memory", "General without memory need"),
    ("unknown_or_conflicting", "Unknown or conflicting"),
    ("lifecycle_or_authorization", "Lifecycle or authorization"),
)
COMPARISONS = ("SELECTIVE-ALWAYS", "SELECTIVE-OFF", "ALWAYS-OFF")


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=False)
        stream.write("\n")


def verify_analysis(directory):
    manifest = read(directory / "seal.json")["sha256"]
    files = {str(p.relative_to(directory)) for p in directory.rglob("*")
             if p.is_file() and p != directory / "seal.json"}
    if files != set(manifest):
        raise ValueError("analysis file set differs from its seal")
    for relative, expected in manifest.items():
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("invalid analysis seal path")
        if digest(directory / relative) != expected:
            raise ValueError("analysis artifact differs from seal: " + relative)
    summary = read(directory / "analysis.json")
    audit = summary["audit"]
    if not audit.get("valid") or audit.get("errors"):
        raise ValueError("report requires a valid collection-integrity audit")
    terminal_coverage = audit.get("batch_status") == "complete" or (
        audit.get("batch_status") == "interrupted" and audit.get("complete_logical_slots") == 18
        and audit.get("strict_frozen_global_prefix") is True)
    if (not terminal_coverage or audit.get("observed_attempts") != 864
            or audit.get("planned_attempts") != 864 or audit.get("unobserved_attempts")):
        raise ValueError("this renderer requires the completed 864-attempt comparison")
    if "complete_logical_slots" in audit and (audit["complete_logical_slots"] != 18
            or not audit.get("strict_frozen_global_prefix")):
        raise ValueError("completed logical slots must preserve the strict original schedule")
    review = summary["review"]
    if (review.get("status") != "assistant_reviewed" or not review.get("judged_groups")
            or review["judged_groups"] != review["unique_blinded_groups"]):
        raise ValueError("all blinded output groups must have frozen supplied judgments")
    return summary


def decode_csv(path):
    boolean_fields = {"task_success", "known_fact_cautious_miss", "abstained", "failure",
        "unsupported_claim", "unsupported_personal_claim", "forbidden_disclosure", "explicit_conflict",
        "authorized", "memory_need", "retrieval_selected", "selection_decision", "selection_resolved",
        "selection_unresolved", "cold_first_request", "helper_speech_enum", "complete_relevant_retrieved",
        "complete_relevant_supplied", "posthoc_known_answer_without_supplied_evidence"}
    def decode(key, value):
        if value == "":
            return None
        if key in boolean_fields and value in ("True", "False"):
            return value == "True"
        if key in {"inspected_ids", "supplied_ids"}:
            return json.loads(value)
        return value
    with Path(path).open(newline="") as stream:
        rows = [{key: decode(key, value) for key, value in row.items()} for row in csv.DictReader(stream)]
    for row in rows:
        for key in ("slot", "index", "repetition", "selector_calls", "retrieval_attempts",
                    "fragment_offset", "local_index", "scheduled_index"):
            if row.get(key) is not None:
                row[key] = int(row[key])
        for key in ("request_s", "selection_s", "retrieval_s", "loading_s"):
            if row.get(key) is not None:
                row[key] = float(row[key])
    return rows


def cell(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(
        ">", "&gt;").replace("|", "\\|").replace("\n", "<br>")


def table(headers, rows):
    return "\n".join(["| " + " | ".join(map(cell, headers)) + " |",
                      "| " + " | ".join("---" for _ in headers) + " |",
                      *("| " + " | ".join(map(cell, row)) + " |" for row in rows)]) + "\n"


def number(value, places=3, signed=False):
    if value is None:
        return "n/a"
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("nonfinite report metric")
    return format(value, ("+" if signed else "") + f".{places}f")


def percent(value, places=1):
    return "n/a" if value is None else number(float(value) * 100, places) + "%"


def fraction(value, denominator):
    return f"{int(value)}/{int(denominator)}" if value is not None and denominator not in (None, 0) else "n/a"


def mean_metric(group, key):
    return group.get("timing", {}).get(key, {}).get("mean")


def nullable_sum(values):
    values = list(values)
    return sum(values) if values and all(value is not None for value in values) else None


def maximum(values):
    values = [value for value in values if value is not None]
    return max(values) if values else None


def link(path, output, label):
    relative = os.path.relpath(Path(path).resolve(), output.resolve())
    return f"[{label}]({quote(relative, safe='/._-')})"


def interval(paired, metric, *, percent_points=False):
    value = paired.get("differences", {}).get(metric + "_difference")
    if value is None:
        return "n/a"
    scale = 100 if percent_points else 1
    places = 1 if percent_points else 3
    values = [float(value[key]) * scale for key in ("mean", "bootstrap_95_low", "bootstrap_95_high")]
    return f"{number(values[0], places, True)} [{number(values[1], places, True)}, {number(values[2], places, True)}]"


def subgroup(rows, model, policy, answerability=None):
    selected = [r for r in rows if r["model"] == model and r["policy"] == policy
                and (answerability is None or r["answerability"] == answerability)]
    return {"attempts": len(selected), "success": sum(r["task_success"] for r in selected),
            "cautious_misses": sum(r["known_fact_cautious_miss"] for r in selected),
            "cautious_misses_without_unsupported_or_forbidden_claims": sum(
                r["known_fact_cautious_miss"] and not r["unsupported_claim"] and not r["forbidden_disclosure"]
                for r in selected),
            "known_success_without_runtime_evidence": sum(
                r.get("posthoc_known_answer_without_supplied_evidence", False) for r in selected),
            "unsupported": sum(r["unsupported_claim"] for r in selected),
            "unsupported_personal": sum(r["unsupported_personal_claim"] for r in selected),
            "failures": sum(r["failure"] for r in selected)}


def known_pairs(rows, model):
    values = defaultdict(list)
    for row in rows:
        if row["model"] == model and row["answerability"] == "known_authorized":
            values[row["case_id"], row["policy"]].append(int(row["task_success"]))
    result = Counter()
    for case_id in sorted({key[0] for key in values}):
        always = statistics.mean(values[case_id, "ALWAYS"])
        selective = statistics.mean(values[case_id, "SELECTIVE"])
        result["selective_higher" if selective > always else "always_higher" if selective < always else "equal"] += 1
    return dict(result)


def interpret(model, overall, paired, rows):
    always, selective, off = (subgroup(rows, model, policy, "known_authorized") for policy in ("ALWAYS", "SELECTIVE", "OFF"))
    pair = known_pairs(rows, model)
    if not always["success"] and not selective["success"]:
        quality = "Neither ALWAYS nor SELECTIVE achieved a known-authorized recall success; useful personalization was not demonstrated."
    elif always["success"] == selective["success"]:
        quality = (f"ALWAYS and SELECTIVE had equal observed known-authorized success totals "
                   f"({fraction(selective['success'], selective['attempts'])} each).")
    elif selective["success"] > always["success"]:
        quality = (f"SELECTIVE had more known-authorized successes "
                   f"({fraction(selective['success'], selective['attempts'])}) than ALWAYS "
                   f"({fraction(always['success'], always['attempts'])}).")
    else:
        quality = (f"SELECTIVE lost known-authorized success relative to ALWAYS: "
                   f"{fraction(selective['success'], selective['attempts'])} versus "
                   f"{fraction(always['success'], always['attempts'])}.")
    quality += (f" Across distinct known requests, SELECTIVE had higher mean success on {pair.get('selective_higher', 0)}, "
                f"lower on {pair.get('always_higher', 0)}, and equal on {pair.get('equal', 0)}; "
                f"OFF achieved {fraction(off['success'], off['attempts'])} known-fact task successes.")
    a, s = overall[model, "ALWAYS"], overall[model, "SELECTIVE"]
    access_difference = a["unnecessary_retrievals"] - s["unnecessary_retrievals"]
    if access_difference > 0:
        access = f"SELECTIVE avoided {access_difference} unnecessary retrieval attempts"
    elif access_difference < 0:
        access = f"SELECTIVE added {-access_difference} unnecessary retrieval attempts"
    else:
        access = "SELECTIVE did not change the number of unnecessary retrieval attempts"
    access += (f" ({fraction(s['unnecessary_retrievals'], s['no_memory_needed_authorized'])} "
               f"versus {fraction(a['unnecessary_retrievals'], a['no_memory_needed_authorized'])} authorized no-memory tasks).")
    contrast = paired[model, "SELECTIVE-ALWAYS", "overall"]
    delta = contrast["differences"]["request_s_difference"]["mean"]
    if delta < 0:
        timing = f"SELECTIVE saved an observed {number(-delta)} seconds per attempted request on average"
    elif delta > 0:
        timing = f"SELECTIVE added an observed {number(delta)} seconds per attempted request on average"
    else:
        timing = "SELECTIVE had equal observed mean complete request time"
    timing += (f", including its selection costs (SELECTIVE−ALWAYS: {interval(contrast, 'request_s')} seconds; "
               "descriptive 95% scenario-bootstrap interval).")
    return f"**{model}.** {quality} {access} {timing}"


def render_tables(summary, rows):
    overall = {(r["model"], r["policy"]): r for r in summary["overall"]}
    categories = {(r["model"], r["policy"], r["category"]): r for r in summary["by_category"]}
    paired = {(r["model"], r["comparison"], r["category"]): r for r in summary["paired"]}
    parts = ["# Independent retrieval: detailed tables\n",
             "ALWAYS means ALWAYS PERMITTED. All times are seconds. Repetitions are dependent observations; "
             "counts retain all attempts. Bracketed paired intervals are the analyzer's frozen 95% scenario-bootstrap intervals.\n"]
    for model in MODELS:
        parts.append(f"## {model}: answer quality and complete request time\n")
        values = []
        for category, title in CATEGORIES:
            for policy in POLICIES:
                group = categories[model, policy, category]
                timing = group["timing"]["request_s"]
                values.append([title, policy, fraction(group["task_success"], group["attempts"]),
                    group["unsupported_claim"], group["unsupported_personal_claim"], group["abstained"],
                    group["failures"], number(timing["mean"]), number(timing["median"]), number(timing["p95"])])
        parts.append(table(["Category", "Policy", "Success", "Unsupported", "Personal unsupported", "Abstained", "Failures", "Mean", "Median", "p95"], values))
        parts.append(f"## {model}: paired differences\n")
        values = []
        for category, title in (("overall", "Overall"), *CATEGORIES):
            for comparison in COMPARISONS:
                item = paired[model, comparison, category]
                quality = item.get("quality_pairs", {})
                values.append([title, comparison, f"{item['paired_requests']} / {item['paired_attempts']}",
                    interval(item, "task_success", percent_points=True), interval(item, "request_s"),
                    interval(item, "unnecessary_retrievals"),
                    f"{quality.get('left_only', 0)} / {quality.get('right_only', 0)}"])
        parts.append(table(["Category", "Left−right", "Requests / repeated pairs", "Success Δ, pp [95%]", "Request Δ, s [95%]", "Unnecessary retrieval Δ/task [95%]", "Left-only / right-only successes"], values))
        parts.append("Positive differences favor the left condition for success and increase cost for time/access. "
                     "Left-only/right-only counts are repeated paired attempts, not independent requests. "
                     "Paired unnecessary-retrieval Δ/task averages over every paired request, with zeros on "
                     "needed and denied tasks; it is not the difference between rates restricted to authorized "
                     "no-memory tasks.\n")
        parts.append(f"## {model}: retrieval, relevance and disclosure by category\n")
        values = []
        for category, title in CATEGORIES:
            for policy in POLICIES:
                group = categories[model, policy, category]
                values.append([title, policy, group["retrieval_attempts"],
                    fraction(group["unnecessary_retrievals"], group["no_memory_needed_authorized"]),
                    percent(group["retrieved_evidence_coverage"]), percent(group["supplied_evidence_coverage"]),
                    group["irrelevant_inspected"], group["irrelevant_source_candidates"], group["irrelevant_supplied"]])
        parts.append(table(["Category", "Policy", "Retrievals", "Unnecessary / eligible tasks", "Relevant retrieved", "Relevant supplied", "Irrelevant inspected", "Irrelevant bounded candidates", "Irrelevant supplied"], values))
        parts.append("Evidence percentages divide the sum of relevant retrieved/supplied ID occurrences by "
                     "the sum of all frozen relevant-ID occurrences; they are not means of per-question "
                     "coverage. Questions with no relevant IDs contribute no coverage denominator. "
                     "Inspection/candidate/disclosure totals sum each attempt's unique IDs, so the same "
                     "memory can contribute again on another request or repetition; these are not globally "
                     "unique memory counts.\n")
    parts.append("## Known-authorized personalization and unavailable information\n")
    values = []
    for model in MODELS:
        for policy in POLICIES:
            known = subgroup(rows, model, policy, "known_authorized")
            values.append([model, policy, fraction(known["success"], known["attempts"]), known["cautious_misses"],
                known["cautious_misses_without_unsupported_or_forbidden_claims"],
                known["known_success_without_runtime_evidence"], known["unsupported_personal"], known["failures"]])
    parts.append(table(["Generator", "Policy", "Known successes", "Misses with abstention", "Such misses without unsupported/forbidden claims", "Known successes with no supplied evidence", "Personal unsupported", "Failures"], values))
    values = []
    for model in MODELS:
        for answerability in ("unknown", "conflicting", "unavailable_lifecycle", "unauthorized"):
            values.append([model, answerability, *(fraction(subgroup(rows, model, p, answerability)["success"],
                subgroup(rows, model, p, answerability)["attempts"]) for p in POLICIES)])
    parts.append(table(["Generator", "Unavailable/uncertain task", "OFF success", "ALWAYS success", "SELECTIVE success"], values))
    parts.append("Abstention on a known authorized fact remains a missed task in every condition. "
                 "The no-unsupported-claim subset describes caution and is not counted as successful recall. "
                 "Unknown/conflicting/restricted successes follow the same uncertainty/refusal rubric in every condition.\n")
    parts.append("Unsupported-claim flags judge factual truth using the question, common full authorized "
                 "reference context and general knowledge, not the evidence actually supplied at runtime. "
                 "A correct known answer produced without supplied personal evidence can therefore pass the "
                 "task rubric; its separate count above does not establish memory-grounded recall.\n")
    parts.append("## Selection, stage timings and helper behavior\n")
    values = []
    for model in MODELS:
        for policy in POLICIES:
            group = overall[model, policy]
            values.append([model, policy, group["classifier_calls"], group.get("selection_unresolved_authorized_requests", "n/a"),
                percent(group["selection_sensitivity"]), percent(group["selection_specificity"]),
                number(mean_metric(group, "selection_s")), number(mean_metric(group, "selector_call_s")),
                number(mean_metric(group, "retrieval_s")), number(mean_metric(group, "generation_s")),
                number(mean_metric(group, "validation_s")), number(mean_metric(group, "loading_s")),
                number(mean_metric(group, "residual_request_s"))])
    parts.append(table(["Generator", "Policy", "Classifier calls", "Unresolved decisions", "Selection sensitivity", "Specificity", "Selection mean", "Classifier mean", "Retrieval mean", "Generation mean", "Validation mean", "Nested loading mean", "Residual mean"], values))
    parts.append("Classifier time is inside selection time; model loading/prefill/decode are inside model calls. "
                 "Do not add nested stage durations again. Every stage mean divides by all attempted requests "
                 "in that condition, including zero time when that stage was not invoked. Selection sensitivity "
                 "and specificity use resolved authorized decisions only; unresolved and unauthorized requests "
                 "are excluded from those decision denominators and unresolved counts remain visible. "
                 "Residual time contains unlisted bookkeeping and checks.\n")
    values = []
    for model in MODELS:
        for policy in POLICIES:
            group = overall[model, policy]
            values.append([model, policy, group["helper_speech_enum"], json.dumps(group["helpers"], sort_keys=True),
                json.dumps(group["transformations"], sort_keys=True), group["prompt_tokens"], group["output_tokens"],
                group["authorization_violations"], group["forbidden_disclosure"], group["explicit_conflict"]])
    parts.append(table(["Generator", "Policy", "Literal speech constraints", "Helper counts", "Transformations", "Prompt tokens", "Output tokens", "Authorization violations", "Forbidden disclosures", "Explicit conflicts"], values))
    parts.append("Helpers have identical configured availability; evidence can change their realized use, prompts, "
                 "output lengths and validation paths. These are complete-policy effects, not isolated generator capability.\n")
    parts.append("## Repetition-level totals\n")
    values = []
    for group in sorted(summary["by_repetition"], key=lambda r: (MODELS.index(r["model"]), r["repetition"], POLICIES.index(r["policy"]))):
        values.append([group["model"], group["repetition"], group["policy"],
            fraction(group["task_success"], group["attempts"]), group["retrieval_attempts"], group["unnecessary_retrievals"],
            number(mean_metric(group, "request_s")), group["failures"]])
    parts.append(table(["Generator", "Repetition", "Policy", "Success", "Retrievals", "Unnecessary", "Request mean", "Failures"], values))
    parts.append("## Physical fragment costs and device state\n")
    values = []
    for session in sorted(summary["sessions"], key=lambda s: s["slot"]):
        session_rows = [r for r in rows if r.get("physical_fragment_id") == session["physical_fragment_id"]] if session.get("physical_fragment_id") else [r for r in rows if r["slot"] == session["slot"]]
        scheduled_range = f"{session.get('first_scheduled_index', 1)}–{session.get('last_scheduled_index', session['attempted'])}"
        values.append([session.get("physical_fragment_id", session["slot"]), session["slot"], scheduled_range,
            session["model"], session["policy"], session["repetition"], session["attempted"],
            number(session["cold_first_request_s"]), number(session["warm_request_s"]["mean"]),
            number(sum(r["loading_s"] for r in session_rows)), number(session["setup_s"]),
            number(session.get("cleanup_complete_s")), number(session.get("session_wall_amortized_s")),
            number(session.get("admission_supervisor_overhead_s", session.get("admission_wait_s"))),
            number(session.get("supervisor_fragment_amortized_s", session.get("supervisor_slot_amortized_s", session.get("session_plus_admission_amortized_s"))))])
    parts.append(table(["Physical fragment", "Logical slot", "Scheduled indices", "Generator", "Policy", "Rep", "Attempts", "Cold first", "Warm mean", "Nested load total", "Setup", "Cleanup", "Fragment/attempt", "Admission/supervisor overhead", "Supervisor fragment/attempt"], values))
    parts.append("Each row is one physical worker with its own setup, cleanup, model load and cold first request, "
                 "including suffix workers whose first scheduled index exceeds 1. Admission/supervisor overhead "
                 "is that fragment's elapsed supervisor time minus its request-bearing worker's session time. "
                 "It includes rejected launches, guard checks, ledger verification and waiting, plus worker import/startup and "
                 "exit/sealing residual; it is not pure waiting. Supervisor fragment/attempt includes that "
                 "overhead once. Missing original fatal-fragment overhead remains n/a.\n")
    boundaries = summary["audit"].get("between_collection_request_boundary_gaps", [])
    if boundaries:
        parts.append(table(["Prior fragment", "Next fragment", "Between-collection request boundary gap, s"],
            [[Path(b["before_directory"]).name, Path(b["after_directory"]).name,
              number(b["request_boundary_gap_s"])] for b in boundaries]))
        parts.append("Boundary gaps run from the prior request finish to the next collection's first request start. "
                     "They include prior cleanup, the off-run pause, later admission and setup. They are separate "
                     "from supervisor overhead, are not pure pause, and are not added to measured request totals.\n")
    supervisor_intervals = summary["audit"].get("collection_supervisor_intervals", [])
    if supervisor_intervals:
        parts.append(table(["Collection", "Supervisor wall, s", "Prior seal header to supervisor start, s"],
            [[Path(s["directory"]).name, number(s.get("supervisor_wall_s")),
              number(s.get("seal_header_to_supervisor_start_s"))] for s in supervisor_intervals]))
        parts.append("The seal-header gap includes earlier sealing/exit and the off-run pause. Supervisor wall "
                     "includes verification, orchestration and child exit/sealing, but excludes the parent "
                     "final batch manifest, sealing and exit. These scopes overlap "
                     "other diagnostic timings and are not added to request or fragment totals.\n")
    values = []
    for model in MODELS:
        for policy in POLICIES:
            sessions = [s for s in summary["sessions"] if s["model"] == model and s["policy"] == policy]
            values.append([model, policy, maximum(s["ram_peak_mib"] for s in sessions),
                maximum(s["swap_peak_mib"] for s in sessions), number(maximum(s["temperature_peak_c"] for s in sessions), 2),
                number(min((s["gpu_allocation_fraction"]["min"] for s in sessions if s["gpu_allocation_fraction"]["min"] is not None), default=None)),
                number(maximum(s["gpu_allocation_fraction"]["max"] for s in sessions)),
                number(nullable_sum(s["board_energy_j"] for s in sessions), 1),
                number(maximum(s["telemetry_gap_s"]["max"] for s in sessions))])
    parts.append(table(["Generator", "Policy", "Peak RAM, MiB", "Peak logical swap, MiB", "Peak °C", "GPU allocation min", "GPU allocation max", "Physical-fragment board J", "Max telemetry gap, s"], values))
    parts.append("GPU allocation fractions are model placement, not utilization or fractions of computation. "
                 "Logical compressed swap is not extra physical RAM. Board energy covers each physical fragment's sampled "
                 "telemetry interval, includes background power, has no idle subtraction, and excludes admission waiting "
                 "and all between-fragment gaps. "
                 "A condition total is n/a if any session has no valid powered sample-pair interval. Otherwise it "
                 "sums the available sample-pair intervals; missing-power intervals may be omitted, so a numeric "
                 "total does not establish complete energy coverage.\n")
    return "\n".join(parts)


def render_answers(rows, prompts):
    parts = ["# Delivered answers and failures by request\n",
             "Exact delivered answer strings appear below; rejected raw generations remain in the collection artifacts. "
             "Identical outcomes are grouped only within the same request, generator and policy, listing every repetition.\n"]
    for case_id in sorted({r["case_id"] for r in rows}):
        members = [r for r in rows if r["case_id"] == case_id]
        prompt = prompts.get(members[0]["review_id"], "Question unavailable in supplied analysis")
        parts.extend([f"## {case_id}\n", prompt + "\n"])
        grouped = defaultdict(list)
        for row in members:
            key = (row["model"], row["policy"], row["status"], row["label"], row["answer"],
                   row["unsupported_claim"], row["unsupported_personal_claim"], row["forbidden_disclosure"])
            grouped[key].append(row["repetition"])
        values = []
        for key, repetitions in sorted(grouped.items(), key=lambda pair: (MODELS.index(pair[0][0]), POLICIES.index(pair[0][1]), min(pair[1]))):
            model, policy, status, label, answer, unsupported, personal, forbidden = key
            values.append([model, policy, ", ".join(map(str, sorted(repetitions))), status, label,
                f"{unsupported}/{personal}/{forbidden}", answer if status == "ok" else "No answer delivered"])
        parts.append(table(["Generator", "Policy", "Repetitions", "Delivery", "Judgment", "Unsupported/personal/forbidden", "Delivered answer"], values))
    return "\n".join(parts)


def render_report(summary, rows, analysis, output, provenance, review_provenance=None):
    overall = {(r["model"], r["policy"]): r for r in summary["overall"]}
    paired = {(r["model"], r["comparison"], r["category"]): r for r in summary["paired"]}
    delivered = sum(not r["failure"] for r in rows)
    parts = ["# CLARA independent personal-memory retrieval experiment\n",
             f"Completed **{len(rows)}/864 planned attempts**, with {delivered} delivered answers and "
             f"{len(rows)-delivered} retained failures. The 48 fictional requests were tested under OFF, "
             "ALWAYS PERMITTED and SELECTIVE for each fixed generator, with three timing repetitions. "
             "Answer quality is assistant-reviewed; independent human validation remains pending.\n",
             "The question is whether selective retrieval retains useful personalization while reducing "
             "unnecessary access and complete request time after paying selection costs.\n"]
    for model in MODELS:
        parts.append(interpret(model, overall, paired, rows) + "\n")
    parts.append("Equal observed totals do not establish equivalent quality. Paired losses and rescues are retained below; "
                 "no noninferiority margin or acceptance deadline was declared.\n")
    values = []
    for model in MODELS:
        for policy in POLICIES:
            group = overall[model, policy]
            known = subgroup(rows, model, policy, "known_authorized")
            timing = group["timing"]["request_s"]
            values.append([model, policy, fraction(group["task_success"], group["attempts"]),
                fraction(known["success"], known["attempts"]), known["cautious_misses"],
                fraction(group["unnecessary_retrievals"], group["no_memory_needed_authorized"]),
                number(timing["mean"]), number(timing["median"]), number(timing["p95"]), group["failures"]])
    parts.append(table(["Generator", "Policy", "Task success", "Known-fact success", "Known misses with abstention", "Unnecessary retrieval", "Mean s", "Median s", "p95 s", "Failures"], values))
    parts.append("Known-authorized recall uses the same rubric in every condition. A cautious OFF abstention is a "
                 "missed personalization task. Unknown, conflicting and restricted facts succeed through the "
                 "frozen uncertainty/refusal rubric. Unsupported claims and the subset of cautious misses without "
                 "unsupported or forbidden claims are reported separately in [the detailed tables](tables.md).\n")
    parts.append("## Category comparison\n")
    parts.append("Each cell is task successes / repeated attempts, followed by mean complete request seconds. "
                 "Each category contains eight distinct requests repeated three times.\n")
    by_category = {(r["model"], r["policy"], r["category"]): r for r in summary["by_category"]}
    values = []
    for model in MODELS:
        for category, title in CATEGORIES:
            cells = []
            for policy in POLICIES:
                group = by_category[model, policy, category]
                cells.append(f"{fraction(group['task_success'], group['attempts'])}; {number(mean_metric(group, 'request_s'))} s")
            values.append([model, title, *cells])
    parts.append(table(["Generator", "Category", "OFF", "ALWAYS", "SELECTIVE"], values))
    parts.append("## Paired quality and time\n")
    values = []
    for model in MODELS:
        for comparison in COMPARISONS:
            group = paired[model, comparison, "overall"]
            direction = group["request_mean_success_direction"]
            values.append([model, comparison, interval(group, "task_success", percent_points=True),
                interval(group, "request_s"),
                f"{direction.get('left_higher', 0)} / {direction.get('right_higher', 0)} / {direction.get('equal', 0)}"])
    parts.append(table(["Generator", "Left−right", "Success Δ, pp [95%]", "Request Δ, s [95%]", "Requests: left higher / right higher / equal"], values))
    parts.append("The analyzer first averages paired repetitions within a request, then resamples all eight "
                 "whole scenario clusters with replacement, retaining their questions and conditions. The "
                 f"{summary['dependence']['bootstrap_replicates']:,} replicates use seed "
                 f"{summary['dependence']['bootstrap_seed']}. These descriptive intervals have only eight "
                 "fictional clusters behind them. Category-specific contrasts and repeated paired wins/losses "
                 "are in [tables.md](tables.md).\n")
    parts.append("## What was measured\n")
    values = []
    for model in MODELS:
        for policy in POLICIES:
            group = overall[model, policy]
            values.append([model, policy, group["classifier_calls"], number(mean_metric(group, "selection_s")),
                group["retrieval_attempts"], number(mean_metric(group, "retrieval_s")),
                percent(group["supplied_evidence_coverage"]), group["irrelevant_inspected"], group["irrelevant_supplied"],
                group["unsupported_claim"], group["unsupported_personal_claim"]])
    parts.append(table(["Generator", "Policy", "Classifier calls", "Selection mean s", "Retrievals", "Retrieval mean s", "Relevant evidence supplied", "Irrelevant inspected", "Irrelevant supplied", "Unsupported", "Personal unsupported"], values))
    parts.append("Unnecessary retrieval uses authorized no-memory requests as its denominator. Legitimate "
                 "unknown-fact lookups still need memory even when their relevant-ID set is empty; empty sets "
                 "have undefined evidence coverage. Reported coverage divides relevant evidence occurrences "
                 "supplied by all frozen relevant-ID occurrences, rather than averaging per-question coverage. "
                 "Denied consent and prohibited-data requests are counted "
                 "separately as authorization checks. Inspected records are the unique eligible records "
                 "materialized during exact semantic scans plus lexical results; supplied records are the "
                 "bounded evidence actually passed to generation. Counts sum unique IDs within each attempt, "
                 "including repeated inspection across requests. Bounded search candidates are a separate metric.\n")
    parts.append("Complete request latency includes selection, retrieval, generation, validation, in-request "
                 "checks and cold first loads, including failed attempts. Model load/prefill/decode values are "
                 "nested diagnostics. Setup, cleanup, admission overhead, warm timing, repetitions, helper "
                 "use, placement, power and telemetry gaps are shown separately in the detailed tables. "
                 "Stage means use all attempted requests, including zeros when a stage was not invoked. "
                 "Selection accuracy excludes unresolved and unauthorized decisions. "
                 "Evidence-dependent helpers and output lengths can change complete-system timing; the "
                 "comparison does not isolate raw generator capability.\n")
    parts.append("Unsupported-claim judgments use the common full authorized truth context, not actual "
                 "runtime evidence. The detailed known-fact table separately identifies correct task answers "
                 "with no supplied evidence; those outcomes do not establish memory-grounded recall.\n")
    rewrites = audit.get("generation_request_rewrites", [])
    if rewrites:
        parts.append(f"The frozen evidence helper rewrote the current question in {len(rewrites)} calls "
                     f"covering {len({r['original_request'] for r in rewrites})} distinct questions. "
                     "It interpreted possessive relationship phrases as person names, title-cased them and "
                     "added 'to me'. OFF retained the original question. These recorded rewrites are "
                     "evidence-dependent helper behavior; semantic neutrality is not established. "
                     "The initial offline audit incorrectly required the original wording as a substring. "
                     "Its failed artifact is preserved; the corrected audit verifies fresh roles and the "
                     "exact source-hash-verified helper transformation. No runtime source, observation, "
                     "reference, judgment rule or statistical rule was changed. Exact original and submitted "
                     "questions are retained in the integrity audit's generation_request_rewrites.\n")
    parts.append("## Controls, review and retained evidence\n")
    parts.append("The approved protocol crossed the same three retrieval policies with fixed Qwen3 0.6B and "
                 "1.7B generators at context 2048, output cap 192, temperature 0, seed 42 and thinking disabled. "
                 "Sole-model classification/rendering, fresh conversations, shared prompts "
                 "and helpers, and fixed prepared memory snapshots were audited before and after collection. "
                 "Consent, profile, prohibited-data, correction/deletion, expiry and freshness checks remained "
                 "active. ALWAYS bypassed memory-need selection while retaining authorization and bounded "
                 "evidence selection. OFF received no personal evidence. This tests already-applied lifecycle "
                 "changes; live propagation remains separate.\n")
    review = summary["review"]
    parts.append(f"The supplied analysis contains frozen assistant judgments for all "
                 f"{review['judged_groups']}/{review['unique_blinded_groups']} distinct question/outcome groups. "
                 "Blinded packets hid explicit model, policy, timing, repetition, actual supplied evidence and "
                 "the private mapping. Identical outputs were grouped only within their question. "
                 "[All delivered answers and failures](answers.md) retain the outcome-to-repetition mapping.\n")
    if review_provenance is not None:
        counts = []
        for key, title in (("total_groups", "reviewed groups"), ("agreement_count", "initial agreements"),
                           ("disagreement_count", "initial disagreements"), ("adjudicated_count", "adjudications")):
            if key in review_provenance and isinstance(review_provenance[key], (int, float)):
                counts.append(f"{int(review_provenance[key])} {title}")
        parts.append("Independent review provenance is preserved in [review_provenance.json](review_provenance.json)" +
                     (": " + "; ".join(counts) if counts else "") + ". Human validation remains pending.\n")
    else:
        parts.append("Separate original-review agreement and adjudication provenance was not supplied to this "
                     "renderer; no agreement count is inferred from the resolved judgment file.\n")
    failures = Counter(r["error"] or "unspecified" for r in rows if r["failure"])
    parts.append("Failure classes: " + ("; ".join(f"{name}: {count}" for name, count in sorted(failures.items()))
                 if failures else "none observed") + ". "
                 f"There were {summary.get('instability_groups', 0)} request/condition groups with different "
                 "delivered outcomes across repetitions. Rejected outputs are not scored as delivered text.\n")
    audit = summary["audit"]
    parts.append(f"Collection terminal status: **{audit['batch_status']}**. "
                 "Completed attempt coverage counts every scheduled terminal observation, including failures.\n")
    if "physical_fragments" in audit:
        parts.append(f"The original {audit['planned_logical_slots']} logical schedule slots completed across "
                     f"{audit['physical_fragments']} physical request-bearing fragments. Every attempted request, "
                     "including guarded interruptions, remains once at its frozen position; continuation runs "
                     "cover only never-started suffixes. Each new physical fragment contributes another cold "
                     "first load and separate setup/cleanup. These realized timing differences are retained. "
                     f"Supervisor overhead is unavailable for {audit.get('unavailable_fragment_supervisor_overheads', 0)} "
                     "physical fragments and is not imputed as zero.\n")
    rejections = audit.get("rejected_admissions", [])
    if rejections:
        parts.append(f"The collection retained {len(rejections)} rejected admission records. Their startup "
                     "checks and waiting are separate from the 864 requested-task latencies; see the sealed "
                     "admission audit and detailed fragment costs. "
                     f"The final collection inherited {audit.get('inherited_rejected_admission_count', 0)} "
                     f"and added {audit.get('new_rejected_admission_count', len(rejections))} such records.\n")
    parts.append("## Limits and reproduction\n")
    parts.append("This is an assistant-authored fictional coverage experiment with 48 questions nested in eight "
                 "shared-topic scenarios. Repeated timing runs are dependent, and the balanced categories do "
                 "not estimate household request frequencies. Policies occupy each within-model position once; "
                 "three rounds leave a 2:1 model-order asymmetry. Thermal/cache state, measured CPU/GPU "
                 "placement, output lengths, helpers and cold-start allocation can affect timing. No population "
                 "equivalence, safety guarantee, live-memory propagation claim or spoken/HRI deadline follows "
                 "from this text experiment. Null and unfavorable results are retained.\n")
    parts.append("Source artifacts: " + "; ".join([
        link(analysis / "analysis.json", output, "reviewed numeric analysis"),
        link(analysis / "audit.json", output, "collection integrity audit"),
        link(analysis / "attempts.csv", output, "all measured attempts"),
        link(analysis / "paired_request_means.csv", output, "paired request means"),
        link(analysis / "provenance.json", output, "analysis provenance"),
        link(analysis / "commands.sh", output, "analysis reproduction command"),
        link(Path(provenance["run"]), output, "raw collection traces, evidence, requests, outputs and telemetry"),
        link(Path(provenance["freeze"]), output, "approved protocol, source, models and prepared snapshot"),
    ]) + ". This renderer's inputs and source are hashed in [provenance.json](provenance.json); "
         "[commands.sh](commands.sh) regenerates these tables into a new directory.\n")
    return "\n".join(parts)


def seal(directory):
    write_json(directory / "seal.json", {"created_at": datetime.now(timezone.utc).isoformat(),
        "sha256": {str(p.relative_to(directory)): digest(p) for p in sorted(directory.rglob("*")) if p.is_file()},
        "immutability": "exclusive creation, SHA256 manifest and read-only permissions; not privileged WORM"})
    for path in directory.rglob("*"):
        path.chmod(0o500 if path.is_dir() else 0o400)
    directory.chmod(0o500)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review-provenance", type=Path)
    args = parser.parse_args(argv)
    analysis = args.analysis.resolve()
    summary = verify_analysis(analysis)
    rows = decode_csv(analysis / "attempts.csv")
    if len(rows) != 864 or len({r["observation_key"] for r in rows}) != 864:
        raise ValueError("attempt CSV must contain 864 unique reviewed observations")
    if any(type(row.get("task_success")) is not bool for row in rows):
        raise ValueError("attempt CSV contains missing semantic judgments")
    for group in summary["overall"]:
        members = [r for r in rows if r["model"] == group["model"] and r["policy"] == group["policy"]]
        if len(members) != group["attempts"] or sum(r["task_success"] for r in members) != group["task_success"]:
            raise ValueError("summary and reviewed attempt outcomes differ")
    provenance = read(analysis / "provenance.json")
    review = read(args.review_provenance) if args.review_provenance else None
    prompts = {}
    packet = analysis / "blinded" / "packet_a.jsonl"
    for line in packet.read_text().splitlines():
        item = json.loads(line)
        prompts[item["review_id"]] = item["prompt"]
    output = args.output.absolute()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    (output / "report.md").write_text(render_report(summary, rows, analysis, output, provenance, review))
    (output / "tables.md").write_text(render_tables(summary, rows))
    (output / "answers.md").write_text(render_answers(rows, prompts))
    source = output / "report_source.py"
    source.write_bytes(Path(__file__).read_bytes())
    if args.review_provenance:
        (output / "review_provenance.json").write_bytes(args.review_provenance.read_bytes())
    inputs = [analysis / name for name in ("seal.json", "analysis.json", "attempts.csv", "provenance.json")]
    inputs.append(packet)
    write_json(output / "provenance.json", {"created_at": datetime.now(timezone.utc).isoformat(),
        "renderer_sha256": digest(Path(__file__)), "analysis_directory": str(analysis),
        "input_sha256": {str(p): digest(p) for p in inputs},
        "review_provenance_sha256": digest(args.review_provenance) if args.review_provenance else None,
        "statistics": "uses supplied analyzer's paired intervals; no bootstrap or semantic scoring performed",
        "human_validation": "pending"})
    command = [str(Path(__file__).resolve().parents[1] / ".venv/bin/python"), str(Path(__file__).resolve()),
               "--analysis", str(analysis), "--output", "/absolute/path/to/a/new/report-directory"]
    if args.review_provenance:
        command += ["--review-provenance", str(args.review_provenance.resolve())]
    (output / "commands.sh").write_text("# Offline renderer only. Use a new output directory.\n" + shlex.join(command) + "\n")
    seal(output)
    print(json.dumps({"output": str(output), "attempts": len(rows), "review": summary["review"]["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
