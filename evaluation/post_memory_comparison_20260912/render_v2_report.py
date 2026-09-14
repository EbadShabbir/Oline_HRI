"""Render reviewed post-memory measurements without importing execution code.

Reads saved analysis and source-hashed runtime artifacts only. It never grades
an answer, reads a live database, calls a model, or replaces an output directory.
"""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
from html import escape
import json
import math
import os
from pathlib import Path


ARMS = ("small", "large", "cascade")
LABELS = {"small": "qwen3:0.6b alone", "large": "qwen3:1.7b alone",
          "cascade": "CLARA lightweight selection"}
MODELS = {"small": "qwen3:0.6b", "large": "qwen3:1.7b"}
SUCCESS = {"complete", "appropriate_abstention", "appropriate_uncertainty"}
INPUTS = ("analysis.json", "row_metrics.jsonl", "blinded_mapping.jsonl")


def check(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def number(value, places=3):
    return "—" if value is None else f"{value:.{places}f}"


def fraction(numerator, denominator):
    return "—" if denominator == 0 else f"{numerator}/{denominator} ({100 * numerator / denominator:.1f}%)"


def triple(value):
    return " / ".join(number((value or {}).get(key)) for key in ("mean", "p50", "p95"))


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def table(lines, title, headers, rows, note=None):
    lines.extend(["", f"## {title}", ""])
    if note:
        lines.extend([note, ""])
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    lines.extend("| " + " | ".join(cell(item) for item in row) + " |" for row in rows)


def validate_inputs(source):
    hashes = {name: digest(source / name) for name in INPUTS}
    report = read_json(source / "analysis.json")
    rows = read_jsonl(source / "row_metrics.jsonl")
    mapping = read_jsonl(source / "blinded_mapping.jsonl")
    quality = report.get("semantic_review") or {}
    check(report.get("comparison_profile") == "post_memory_comparison_v1", "wrong comparison profile")
    check(report.get("integrity_valid") is True and not report.get("integrity_errors"),
          "report must have valid artifact integrity")
    check(quality.get("status") == "complete_for_observed_unique_outputs"
          and not quality.get("conflicting_review_ids")
          and not quality.get("pending_unique_output_ids"), "all observed reviews must be resolved")
    check(report.get("planned_attempts") == 432 and report.get("distinct_request_items") == 48,
          "expected 48 distinct requests, three arms and three repetitions")
    keys = [(row["arm"], row["repetition"], row["case_id"]) for row in rows]
    check(len(keys) == len(set(keys)) == report["observed_attempts"], "observation count or uniqueness differs")
    check(set(row["arm"] for row in rows) <= set(ARMS), "unknown arm in observations")
    indexed = dict(zip(keys, rows))
    scores, flags, review_ids = {}, {}, set()
    for group in mapping:
        review_id = group["review_id"]
        check(review_id not in review_ids, "duplicate review group")
        review_ids.add(review_id)
        opinions = quality["review_opinions"].get(review_id, [])
        signatures = {(item["judgment"], item["unsupported_personal_claim"],
                       item["forbidden_or_stale_claim"]) for item in opinions}
        check(len(signatures) == 1, "missing or conflicting judgment")
        judgment, unsupported, forbidden = next(iter(signatures))
        good = judgment in SUCCESS
        check(not good or not (unsupported or forbidden), "successful judgment includes a disqualifying claim")
        for observation in group["observations"]:
            key = (observation["arm"], observation["repetition"], observation["case_id"])
            check(key in indexed and key not in scores, "review mapping omits, adds or duplicates an observation")
            row = indexed[key]
            check(row["status"] == observation["status"] and row["delivered"] == (observation["status"] == "ok"),
                  "review delivery status differs from saved metrics")
            check((judgment == "technical_failure") == (not row["delivered"]), "technical-failure review differs")
            check(not good or row["delivered"], "non-delivery cannot receive quality credit")
            scores[key], flags[key] = good, (unsupported, forbidden)
    check(set(scores) == set(indexed), "review mapping does not cover all observed attempts")
    check(len(review_ids) == quality["resolved_unique_outputs"] == quality["observed_unique_outputs"],
          "unique review counts differ")
    for arm in ARMS:
        selected = [row for row in rows if row["arm"] == arm]
        aggregate, graded = report["arms"][arm], quality["arms"][arm]
        correct = sum(value for key, value in scores.items() if key[0] == arm)
        check(len(selected) == aggregate["attempted"] == graded["observed_attempts"] == graded["reviewed_attempts"],
              f"{arm}: attempted/reviewed counts differ")
        check(aggregate["planned"] == 144 and aggregate["unattempted"] == 144 - len(selected),
              f"{arm}: planned denominator differs")
        check(sum(row["delivered"] for row in selected) == aggregate["delivered"]
              and aggregate["technical_failures"] == len(selected) - aggregate["delivered"],
              f"{arm}: delivery counts differ")
        check(correct == graded["correct_reviewed"], f"{arm}: correctness count differs")
    check(len(report["sessions"]) == 9, "expected nine planned session slots")
    for session in report["sessions"]:
        selected = [row for row in rows if (row["arm"], row["repetition"])
                    == (session["arm"], session["repetition"])]
        check(len(selected) == session["attempted"], "session coverage differs")
    if report["complete"]:
        check(len(rows) == 432 and all(session["complete"] for session in report["sessions"]),
              "complete report lacks all planned observations")
    review_manifest = source / "review_manifest.json"
    if review_manifest.is_file():
        manifest = read_json(review_manifest)
        check(manifest["mapping_sha256"] == hashes["blinded_mapping.jsonl"], "review mapping hash differs")
        check(manifest["mapped_raw_observations"] == len(rows), "review manifest coverage differs")
        hashes[review_manifest.name] = digest(review_manifest)
    return report, rows, scores, hashes


def runtime_evidence(report, rows):
    """Read only hashed observations; extract call identity and /api/ps fields.

    Returned data deliberately omit speech, prompts, classifier content and
    memory facts. All answer-quality judgments still come from saved reviews.
    """
    indexed = {(row["arm"], row["repetition"], row["case_id"]): row for row in rows}
    sources, observations, artifacts = {}, [], {}
    calls = {arm: {"requested": Counter(), "returned": Counter(), "returned_generator": Counter(),
                   "unknown_returned_model": 0} for arm in ARMS}
    placement = {}
    for session in report["sessions"]:
        for tag, metadata in (session.get("manifest") or {}).get("models", {}).items():
            check(tag not in artifacts or artifacts[tag] == metadata, "model artifact metadata differs across sessions")
            artifacts[tag] = metadata
        if not session["attempted"]:
            continue
        path = Path(report["run_root"]) / session["directory"] / "observations.jsonl"
        expected = session["artifact_sha256"].get("observations.jsonl")
        check(expected is not None and digest(path) == expected, "raw observation hash differs from reviewed analysis")
        sources[str(path.resolve())] = expected
        records = read_jsonl(path)
        check(len(records) == session["attempted"], "raw observation count differs from reviewed analysis")
        for record in records:
            arm, repetition = session["arm"], session["repetition"]
            key = (record["arm"], record["repetition"], record["id"])
            check(key in indexed and key[:2] == (arm, repetition)
                  and record["status"] == indexed[key]["status"], "raw observation identity differs")
            for call in record.get("calls", []):
                calls[arm]["requested"][call["requested_model"]] += 1
                generation = call.get("generation") or call.get("raw_generation") or {}
                returned = call.get("actual_model") or generation.get("model")
                if returned is None:
                    calls[arm]["unknown_returned_model"] += 1
                else:
                    calls[arm]["returned"][returned] += 1
                    if call.get("purpose") == "generation":
                        calls[arm]["returned_generator"][returned] += 1
            item = {"session": session["directory"], "arm": arm, "repetition": repetition,
                    "case_id": record["id"], "index": record["index"], "status": record["status"]}
            for field in ("api_ps_before", "api_ps_after"):
                snapshots = record.get(field)
                item[field] = None if not isinstance(snapshots, list) else []
                if not isinstance(snapshots, list):
                    continue
                for snapshot in snapshots:
                    tag = snapshot.get("name", snapshot.get("model"))
                    size, vram = snapshot.get("size"), snapshot.get("size_vram")
                    numeric = (type(size) in (int, float) and math.isfinite(size) and size > 0
                               and type(vram) in (int, float) and math.isfinite(vram) and vram >= 0)
                    ratio = vram / size if numeric else None
                    item[field].append({"model": tag, "size_bytes": size, "size_vram_bytes": vram,
                                        "vram_fraction_of_reported_allocation": ratio})
                    group = placement.setdefault((session["directory"], tag), {"snapshot_count": 0, "sizes": [], "vram": [], "ratios": []})
                    group["snapshot_count"] += 1
                    if numeric:
                        group["sizes"].append(size)
                        group["vram"].append(vram)
                        group["ratios"].append(ratio)
            observations.append(item)
    check(len(observations) == len(rows), "runtime evidence coverage differs")
    result = {"model_artifacts": artifacts,
              "calls_by_arm": {arm: {key: dict(value) if isinstance(value, Counter) else value
                                      for key, value in values.items()} for arm, values in calls.items()},
              "placement_by_session_model": [{"session": session, "model": tag, **values}
                                               for (session, tag), values in placement.items()],
              "per_request_snapshots": observations,
              "scope": "Observed /api/ps allocation fields before and after each request; allocation ratio is not GPU compute share or an offloaded-layer count"}
    return result, sources


def render(source):
    report, rows, scores, hashes = validate_inputs(source)
    evidence, raw_hashes = runtime_evidence(report, rows)
    hashes.update(raw_hashes)
    quality = report["semantic_review"]
    types = quality["reviewer_types"]
    reviewer = "assistant-assessed" if types == ["assistant"] else "human-assessed" if types == ["human"] else "assessed by assistant and human reviewers"
    coverage = "All nine sessions and 432 planned attempts are complete." if report["complete"] else (
        f"Coverage is incomplete: {report['observed_attempts']}/432 planned attempts were observed; "
        "the missing requests remain unattempted.")
    lines = ["# Post-memory system comparison", "", coverage, "",
             f"Answer quality is {reviewer} full-rubric success. "
             "Correctness includes appropriate abstention or uncertainty only when required by the frozen rubric. "
             "Withheld, failed and interrupted attempts receive no quality credit. "
             + ("Independent human validation remains pending." if not quality["human_validation_complete"] else "The saved review reports complete human grading."), "",
             "The statistical unit is the request: 48 distinct requests repeated three times per system, "
             "with shared scenario and synthetic-profile dependencies. The 144 planned attempts per system "
             "are not 144 independent quality samples. All comparisons here are descriptive; no quality or responsiveness pass threshold is inferred.", "",
             "Timing runs from text-request entry to full validated delivery or failure. It includes classifier, retrieval, "
             "generation and validation work. This is a complete text-pipeline snapshot comparison; live memory capture, speech input and speech output are outside its scope.", "",
             "Frozen session order: " + " → ".join(
                 ", ".join(LABELS[arm] for arm in order) for order in report["counterbalanced_arm_orders"]) + "."]

    table(lines, "Exact model artifacts", ["Ollama tag", "Reported parameter size", "Parameter count", "Quantization", "Artifact bytes", "Digest"], [
        [tag, metadata.get("parameter_size", "—"), metadata.get("parameter_count", "—"),
         metadata.get("quantization_level", "—"), metadata.get("size", "—"), metadata.get("digest", "—")]
        for tag, metadata in sorted(evidence["model_artifacts"].items())],
        "The tag is an artifact identifier, not an independently verified parameter count. The metadata values are copied exactly from the frozen model inspection.")

    table(lines, "Observed quality and delivery", ["System", "Observed / planned", "Distinct items", "Validated", "Technical failures", "Correct / observed", "Correct / planned"], [
        [LABELS[arm], f"{a['attempted']}/{a['planned']}", a["distinct_observed_cases"], a["delivered"],
         a["technical_failures"], fraction(q["correct_reviewed"], a["attempted"]), fraction(q["correct_reviewed"], a["planned"])]
        for arm in ARMS for a, q in [(report["arms"][arm], quality["arms"][arm])]],
        "Correct / planned is demonstrated correct-delivery coverage. When coverage is incomplete, it is not full-workload accuracy. Validated delivery alone does not establish correctness.")
    table(lines, "Request latency", ["System", "All mean / p50 / p95, s", "Delivered mean / p50 / p95, s", "Failed mean / p50 / p95, s"], [
        [LABELS[arm], triple(a["latency_all_seconds"]), triple(a["latency_delivered_seconds"]), triple(a["latency_failed_seconds"])]
        for arm in ARMS for a in [report["arms"][arm]]],
        "Pooled observed attempts include each session's initial cold request. Missing populations show an em dash; a zero failure count is not zero failure latency.")
    strata = sorted({row["stratum"] for row in rows} | set(report["by_stratum"]["small"]))
    table(lines, "Quality by request category", ["Category", "System", "Correct / observed", "Validated", "Failures", "Observed / planned"], [
        [stratum.replace("_", " "), LABELS[arm], fraction(q["correct_reviewed"], a["attempted"]),
         a["delivered"], a["technical_failures"], f"{a['attempted']}/{a['planned']}"]
        for stratum in strata for arm in ARMS
        for a, q in [(report["by_stratum"][arm][stratum], quality["arms"][arm]["by_stratum"][stratum])]])

    session_rows = []
    for session in report["sessions"]:
        key = (session["arm"], session["repetition"])
        correct = sum(value for item, value in scores.items() if item[:2] == key)
        later = session.get("later_request_latency_seconds") or {}
        outcome = session["status"]
        guard = (session.get("finish") or {}).get("guard_violation")
        if guard:
            outcome += f": {guard}"
        session_rows.append([session["directory"], outcome, f"{session['attempted']}/48", session["delivered"],
                             fraction(correct, session["attempted"]), number(session.get("first_request_seconds")),
                             triple(session.get("request_latency_seconds")), triple(later)])
    table(lines, "Repetitions and cold versus later requests", ["Session", "Outcome", "Observed", "Validated", "Correct / observed", "First, s", "All mean / p50 / p95, s", "Later mean / p50 / p95, s"], session_rows,
          "Sessions appear in executed order. Each started without a resident generator; the first request includes cold loading. Later-request distributions exclude only that session's first attempt, including any failed first attempt.")

    calls_rows = []
    for arm in ARMS:
        a, counts = report["arms"][arm], Counter()
        for row in rows:
            if row["arm"] == arm:
                counts.update(row["call_counts"])
        returned = evidence["calls_by_arm"][arm]
        calls_rows.append([LABELS[arm], " / ".join(str(counts[purpose]) for purpose in ("memory_selector", "compute_selector", "generation")),
                           a["model_call_count"], a["calls_with_reported_duration_metadata"],
                           " / ".join(str(returned["returned_generator"].get(MODELS[size], 0)) for size in ("small", "large")),
                           returned["unknown_returned_model"],
                           a["fallback_count"], a["retrieval_requests"],
                           number(a["routing_seconds"]["sum"]), number(a["retrieval_seconds"]["sum"]),
                           number(a["ollama_load_seconds"]["sum"])])
    table(lines, "Recorded calls and loading", ["System", "Memory / compute / generator calls", "All calls", "Duration metadata available", "Returned 0.6b / 1.7b generator tags", "Calls without returned model", "Fallbacks", "Retrieval requests", "Routing total, s", "Retrieval total, s", "Backend load total, s"], calls_rows,
          "Counts include failed attempts. Returned generator identities come from source-hashed raw call metadata, including responses later withheld by validation; requested tags do not fill missing returned identities. Backend loading is already contained in call/request time. Duration totals cover only calls with returned timing metadata. No compute-classifier inference is permitted by this profile.")

    residency_rows, resource_rows = [], []
    for session in report["sessions"]:
        start, finish = session.get("start"), session.get("finish")
        manifest, telemetry = session.get("manifest") or {}, session.get("telemetry") or {}
        allowed = (manifest.get("execution_policy") or {}).get("allowed_models")
        def empty_snapshot(snapshot):
            if not isinstance(snapshot, dict) or "resident_models" not in snapshot:
                return "unknown"
            return "empty" if snapshot["resident_models"] == [] else "nonempty"
        residency_rows.append([session["directory"], ", ".join(allowed) if allowed else "—",
                               empty_snapshot(start), empty_snapshot(finish),
                               "—" if finish is None else json.dumps(finish.get("cleanup_errors"))])
        energy = lambda key: None if telemetry.get(key) is None else telemetry[key] / 1000
        resource_rows.append([session["directory"], number(session.get("memory_setup_seconds")),
                              number(telemetry.get("peak_ram_used_mb"), 1), number(telemetry.get("peak_swap_used_mb"), 1),
                              number(telemetry.get("peak_temperature_c"), 2), number(telemetry.get("duration_seconds")),
                              number(energy("whole_interval_energy_joules")), number(energy("request_intervals_energy_joules")),
                              f"{number(telemetry.get('request_interval_covered_seconds'))} / {number(telemetry.get('request_interval_requested_seconds'))}"])
    missing_post = (report.get("routing_contract") or {}).get("interrupted_without_post_request_residency_snapshot", [])
    table(lines, "Residency and cleanup evidence", ["Session", "Permitted model tags", "Start residency", "Finish residency", "Cleanup errors"], residency_rows,
          f"The analyzer audits recorded request snapshots and model calls against each arm's allowed tags. {len(missing_post)} interrupted attempts lack a successful post-request residency snapshot. "
          "Per-request server snapshots are archived in runtime_evidence.json. They observe residency at the recorded boundaries; no switch count is inferred from cached hints.")
    def span(values, scale=1):
        return "—" if not values else f"{min(values)/scale:.1f}–{max(values)/scale:.1f}"
    table(lines, "Observed CPU/GPU allocation", ["Session", "Resident tag", "Snapshots", "Numeric allocation snapshots", "Reported allocation range, MiB", "GPU allocation range, MiB", "GPU / reported allocation range, %"], [
        [group["session"], group["model"], group["snapshot_count"], len(group["ratios"]),
         span(group["sizes"], 1048576), span(group["vram"], 1048576), span(group["ratios"], 0.01)]
        for group in evidence["placement_by_session_model"]],
        "Ollama /api/ps size and size_vram describe reported allocation, not a fraction of model computation. Jetson GPU allocation shares physical memory with the CPU; it is not additional physical RAM. A ratio below 100% records partial GPU allocation and is a possible latency factor. These measurements do not establish equal CPU/GPU placement across arms, and do not isolate a causal routing effect.")
    table(lines, "Whole-device resources and energy", ["Session", "Memory setup, s", "Peak RAM, MiB", "Peak logical swap, MiB", "Peak temperature, °C", "Sampled interval, s", "Whole interval, kJ", "Request intervals, kJ", "Request coverage / requested, s"], resource_rows,
          "Existing zram swap occupancy is logical usage backed by compressed pages in physical RAM. It cannot be added to physical RAM capacity or usage, and occupancy alone is not a measure of active swapping. Onboard VDD_IN energy integrates sampled whole-device power without idle subtraction. The whole interval includes setup and cleanup plus background activity. Request energy covers sampled overlap only; unsampled prefixes/suffixes are not extrapolated. Scheduler waits and gaps between sessions are excluded. This is not calibrated model-only energy.")
    policy_rows = []
    seen = set()
    for session in report["sessions"]:
        policy = (session.get("manifest") or {}).get("device_policy")
        if policy and json.dumps(policy, sort_keys=True) not in seen:
            seen.add(json.dumps(policy, sort_keys=True))
            policy_rows.append([number(policy["min_start_available_kib"] / 1024, 0),
                                number(policy["max_start_swap_used_kib"] / 1024, 0),
                                number(policy["min_runtime_available_kib"] / 1024, 0),
                                number(policy["max_runtime_swap_used_kib"] / 1024, 0),
                                number(policy["max_start_temperature_c_exclusive"], 1),
                                number(policy["max_runtime_temperature_c_exclusive"], 1)])
    table(lines, "Recorded admission and runtime limits", ["Minimum start RAM, MiB", "Maximum start swap, MiB", "Minimum runtime RAM, MiB", "Maximum runtime swap, MiB", "Start temperature below, °C", "Runtime temperature below, °C"], policy_rows,
          "These are the limits saved in this analysis, including any frozen amendment. A terminal resource interruption remains a failure of that recorded session; missing requests are not silently replaced.")
    judgments = ("complete", "appropriate_abstention", "appropriate_uncertainty", "partial", "incorrect", "inappropriate_abstention", "technical_failure")
    table(lines, "Semantic judgments", ["System"] + [name.replace("_", " ") for name in judgments]
          + ["Unsupported personal claim", "Forbidden / stale rubric claim"], [
              [LABELS[arm]] + [q["judgments"].get(name, 0) for name in judgments]
              + [q["unsupported_personal_claim_attempts"], q["forbidden_or_stale_claim_attempts"]]
              for arm in ARMS for q in [quality["arms"][arm]]],
          "Counts map resolved blinded judgments back to attempts, retaining repetitions. The forbidden-claim flag covers the whole rubric, including general-task constraints; it is not solely a personal-data exposure count.")
    lines.extend(["", f"Blinded review resolved {quality['resolved_unique_outputs']} unique evidence-aware output groups "
                  f"covering {len(rows)} observed attempts. Identical responses are grouped only for the same request "
                  "and supplied-memory ID set; non-deliveries are grouped per request. Grouping reduces duplicate grading, not the denominator.", "",
                  f"Workload SHA-256: `{report['workload_sha256']}`. Freeze SHA-256: `{report['freeze_sha256']}`.", ""])
    summary = {key: report.get(key) for key in ("comparison_profile", "complete", "observed_attempts", "planned_attempts",
               "counterbalanced_arm_orders", "workload_sha256", "freeze_sha256", "arms", "by_stratum", "routing_contract")}
    summary["review"] = {key: quality[key] for key in ("reviewer_types", "human_validation_complete", "observed_unique_outputs", "resolved_unique_outputs", "arms")}
    return "\n".join(lines), summary, report, hashes, evidence


def deadline_svg(report):
    curve = report.get("deadline_quality_curve") or {}
    check(report["complete"] and curve.get("status") == "complete_descriptive_curve",
          "deadline figure requires all 432 attempts and complete reviewed quality")
    maximum = curve["max_observed_seconds"]
    check(isinstance(maximum, (int, float)) and math.isfinite(maximum) and maximum > 0, "invalid deadline range")
    left, top, width, height = 78, 72, 640, 300
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="820" height="520" viewBox="0 0 820 520">',
             '<rect width="820" height="520" fill="white"/>',
             '<g font-family="sans-serif" fill="#17202a">',
             '<text x="78" y="30" font-size="18">Correct validated delivery by deadline</text>']
    for index in range(6):
        x, y = left + width * index / 5, top + height * (1 - index / 5)
        parts.extend([f'<path d="M {left} {y} H {left+width}" stroke="#dde2e6"/>',
                      f'<text x="67" y="{y+4}" text-anchor="end" font-size="12">{index*20}%</text>',
                      f'<text x="{x}" y="395" text-anchor="middle" font-size="12">{maximum*index/5:.1f}</text>'])
    for index, (arm, color) in enumerate(zip(ARMS, ("#1769aa", "#b35216", "#318342"))):
        values = curve["arms"][arm]
        check(values["planned_denominator"] == 144, "deadline figure denominator differs")
        path = f"M {left} {top+height}"
        previous = 0.0
        for point in values["points"]:
            deadline, fraction_value = point["deadline_seconds"], point["fraction_of_planned"]
            check(previous <= deadline <= maximum and 0 <= fraction_value <= 1, "invalid deadline point")
            path += f" H {left+width*deadline/maximum:.3f} V {top+height*(1-fraction_value):.3f}"
            previous = deadline
        path += f" H {left+width}"
        parts.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        parts.append(f'<text x="{left + index*245}" y="450" font-size="12" fill="{color}">{escape(LABELS[arm])}</text>')
    review_note = "Reviewers: " + ", ".join(report["semantic_review"]["reviewer_types"])
    if not report["semantic_review"]["human_validation_complete"]:
        review_note += "; independent human validation pending."
    parts.extend(['<text x="398" y="422" text-anchor="middle" font-size="13">Text-request deadline (seconds)</text>',
                  '<text x="78" y="478" font-size="11">48 requests × 3 repetitions per arm; descriptive assessed quality, no chosen pass deadline.</text>',
                  f'<text x="78" y="498" font-size="11">{escape(review_note)}</text>',
                  '</g></svg>'])
    return "\n".join(parts) + "\n"


def write_new(path, text):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--figure", action="store_true", help="Add an SVG deadline curve; requires complete reviewed 432-attempt coverage")
    args = parser.parse_args(argv)
    content, summary, report, hashes, evidence = render(args.analysis_dir)
    figure = deadline_svg(report) if args.figure else None
    check(all(digest(args.analysis_dir / name) == value for name, value in hashes.items()), "input changed during rendering")
    provenance = {"renderer_sha256": digest(Path(__file__)), "analysis_directory": str(args.analysis_dir.resolve()),
                  "input_sha256": hashes, "raw_artifacts_read": bool(evidence["per_request_snapshots"]), "grading_performed": False,
                  "scope": "Descriptive rendering of saved artifact-validated and fully reviewed observed measurements"}
    os.umask(0o077)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    write_new(args.output_dir / "tables.md", content)
    write_new(args.output_dir / "summary.json", json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    write_new(args.output_dir / "runtime_evidence.json", json.dumps(evidence, indent=2, ensure_ascii=False) + "\n")
    if figure is not None:
        write_new(args.output_dir / "deadline_quality.svg", figure)
    provenance["output_sha256"] = {path.name: digest(path) for path in args.output_dir.iterdir() if path.is_file()}
    write_new(args.output_dir / "provenance.json", json.dumps(provenance, indent=2) + "\n")
    print(json.dumps({"output_dir": str(args.output_dir.resolve()), "observed_attempts": report["observed_attempts"],
                      "complete": report["complete"], "figure": figure is not None}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
