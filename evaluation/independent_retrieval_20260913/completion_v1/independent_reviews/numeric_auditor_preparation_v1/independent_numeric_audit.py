"""Independent standard-library arithmetic audit of CLARA's retrieval experiment.

Run only after inference and blinded judgments have finished. This module never
imports the experiment analyzer, invokes inference, or assigns semantic scores.
It reconstructs counts and timings from sealed raw observations and resolved
external judgments, then compares them with published machine-readable tables.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import random
import shutil
import statistics
import sys
import traceback


MODELS = ("qwen3:0.6b", "qwen3:1.7b")
POLICIES = ("OFF", "ALWAYS", "SELECTIVE")
CONTRASTS = (("SELECTIVE", "ALWAYS"), ("SELECTIVE", "OFF"), ("ALWAYS", "OFF"))
FLAGS = ("unsupported_claim", "unsupported_personal_claim", "abstained",
         "explicit_conflict", "forbidden_disclosure")
TIMINGS = ("request_s", "authorization_s", "selection_s", "selector_call_s",
           "retrieval_s", "shared_intent_s", "response_evidence_linking_s",
           "generation_s", "validation_s", "loading_s", "prefill_s", "decode_s",
           "backend_total_s", "residual_request_s")
PAIR_METRICS = ("request_s", "selection_s", "retrieval_s", "generation_s",
                "validation_s", "loading_s", "retrieval_attempts",
                "unnecessary_retrievals", "irrelevant_inspected",
                "irrelevant_supplied", "supplied_coverage", "failure",
                "task_success", "unsupported_claim", "unsupported_personal_claim",
                "abstained", "known_fact_cautious_miss")
BOOTSTRAP_METRICS = ("request_s_difference", "task_success_difference")
BOOTSTRAP_SEED, BOOTSTRAP_REPEATS = 2026091399, 10000


def read_json(path):
    return json.loads(Path(path).read_text())


def read_jsonl(path):
    path = Path(path)
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def digest(path):
    checksum = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def verify_seal(directory):
    directory = Path(directory)
    expected = read_json(directory / "seal.json")["sha256"]
    found = {str(path.relative_to(directory)) for path in directory.rglob("*")
             if path.is_file() and path != directory / "seal.json"}
    if found != set(expected):
        raise ValueError(f"sealed file membership changed: {directory}")
    for relative, checksum in expected.items():
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("unsafe manifest path")
        if digest(directory / relative) != checksum:
            raise ValueError(f"sealed contents changed: {directory / relative}")


def quantile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def distribution(values):
    values = [value for value in values if value is not None]
    if not values:
        return dict(n=0, mean=None, median=None, p95=None, total=0, min=None, max=None)
    return dict(n=len(values), mean=statistics.mean(values), median=statistics.median(values),
                p95=quantile(values, .95), total=sum(values), min=min(values), max=max(values))


def fraction(numerator, denominator):
    return numerator / denominator if denominator else None


class Checks:
    def __init__(self):
        self.count = 0
        self.errors = []

    def equal(self, name, actual, expected):
        self.count += 1
        if isinstance(actual, (float, int)) and not isinstance(actual, bool) \
                and isinstance(expected, (float, int)) and not isinstance(expected, bool):
            same = math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)
        else:
            same = actual == expected
        if not same:
            self.errors.append(dict(check=name, actual=actual, expected=expected))

    def true(self, name, condition):
        self.equal(name, bool(condition), True)


def observation_id(row):
    return f"slot_{row['slot']:02d}:{row['case']['id']}"


def read_csv(path):
    def parse(value):
        if value == "":
            return None
        if value in ("True", "False"):
            return value == "True"
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    with Path(path).open(newline="") as stream:
        return [{key: parse(value) for key, value in row.items()} for row in csv.DictReader(stream)]


def reconstruct(raw, reference, judgment):
    """Independent per-observation arithmetic, without analyzer helpers."""
    adapter = raw["adapter"]
    relevant = set(reference["relevant_evidence_ids"])
    inspected = {identifier for event in adapter["inspection_events"] for identifier in event["ids"]}
    retrieved = set(adapter["retrieved_ids"])
    supplied = {entry["memory"]["id"] for entry in adapter["supplied_evidence"]}
    candidates = {entry["memory"]["id"] for call in adapter["search_calls"] for entry in call.get("results", [])}
    authorized = reference["authorization_expected"]
    selection = adapter["selection"]
    route = selection.get("route")
    resolved = authorized and (selection.get("source") in ("policy_off", "policy_always")
        or isinstance(route, dict) and type(route.get("decision", {}).get("memory_required")) is bool)
    calls = raw["calls"]
    generations = [call.get("generation") or call.get("raw_generation") or {} for call in calls]
    phases = defaultdict(int)
    for span in raw["trace"]:
        phases[span["name"]] += span.get("wall_ns") or 0
    selector_calls = [call for call in adapter["calls"] if call["purpose"] == "memory_selector"]
    retrieval_count = len(adapter["retrieval_calls"])
    result = dict(observation_key=observation_id(raw), case_id=raw["case"]["id"],
        model=raw["model"], policy=raw["policy"], repetition=raw["repetition"], slot=raw["slot"],
        index=raw["index"], category=reference["category"], scenario_id=reference["scenario_id"],
        answerability=reference["answerability"], authorized=authorized, memory_need=reference["memory_need"],
        status=raw["status"], failure=raw["status"] != "ok", cold_first_request=raw["index"] == 1,
        request_s=(raw["finished_monotonic_ns"] - raw["started_monotonic_ns"]) / 1e9,
        authorization_s=adapter["authorization"].get("wall_ns", 0) / 1e9,
        selection_s=selection.get("wall_ns", 0) / 1e9,
        selector_calls=len(selector_calls), selector_call_s=sum(call["wall_ns"] for call in selector_calls) / 1e9,
        selection_source=selection.get("source"), selection_resolved=resolved,
        selection_unresolved=authorized and not resolved,
        selection_decision=selection.get("retrieval_selected") if resolved else None,
        retrieval_selected=selection.get("retrieval_selected"), retrieval_attempts=retrieval_count,
        unnecessary_retrievals=retrieval_count if authorized and not reference["memory_need"] else 0,
        authorization_violations=retrieval_count if not authorized else 0,
        retrieval_s=sum(call["wall_ns"] for call in adapter["retrieval_calls"]) / 1e9,
        shared_intent_s=adapter["framing"].get("intent_wall_ns", 0) / 1e9,
        response_evidence_linking_s=adapter["framing"].get("evidence_linking_wall_ns", 0) / 1e9,
        generation_s=phases["answer_generation"] / 1e9, validation_s=phases["validation"] / 1e9,
        prompt_tokens=sum(item.get("prompt_eval_count") or 0 for item in generations),
        output_tokens=sum(item.get("eval_count") or 0 for item in generations),
        relevant_count=len(relevant), relevant_retrieved=len(relevant & retrieved), relevant_supplied=len(relevant & supplied),
        retrieved_coverage=fraction(len(relevant & retrieved), len(relevant)),
        supplied_coverage=fraction(len(relevant & supplied), len(relevant)),
        complete_relevant_retrieved=relevant <= retrieved if relevant else None,
        complete_relevant_supplied=relevant <= supplied if relevant else None,
        inspected_count=len(inspected), irrelevant_inspected=len(inspected - relevant),
        source_candidate_count=len(candidates), irrelevant_source_candidates=len(candidates - relevant),
        retrieved_count=len(retrieved), irrelevant_retrieved=len(retrieved - relevant),
        supplied_count=len(supplied), irrelevant_supplied=len(supplied - relevant),
        inspected_ids=sorted(inspected), supplied_ids=sorted(supplied),
        helper_constraint=adapter["helper_behavior"]["answer_constraint"],
        helper_speech_enum=adapter["helper_behavior"]["speech_enum"] is not None,
        response_transform=adapter["helper_behavior"]["response_transform"],
        label=judgment["label"], task_success=judgment["label"] in ("complete", "appropriate_abstention"),
        **{flag: judgment[flag] for flag in FLAGS})
    for field, name in (("load_duration_ns", "loading_s"), ("prompt_eval_duration_ns", "prefill_s"),
                        ("eval_duration_ns", "decode_s"), ("total_duration_ns", "backend_total_s")):
        result[name] = sum(item.get(field) or 0 for item in generations) / 1e9
    result["residual_request_s"] = result["request_s"] - sum(result[field] for field in
        ("authorization_s", "selection_s", "retrieval_s", "shared_intent_s", "response_evidence_linking_s", "generation_s", "validation_s"))
    result["known_fact_cautious_miss"] = reference["answerability"] == "known_authorized" and judgment["abstained"] and not result["task_success"]
    result["posthoc_known_answer_without_supplied_evidence"] = reference["answerability"] == "known_authorized" and result["task_success"] and not supplied
    return result


def summarize(rows):
    counts = lambda key: sum(row[key] for row in rows)
    authorized = [row for row in rows if row["authorized"]]
    needed = [row for row in authorized if row["memory_need"]]
    unneeded = [row for row in authorized if not row["memory_need"]]
    needed_resolved = [row for row in needed if row["selection_resolved"]]
    unneeded_resolved = [row for row in unneeded if row["selection_resolved"]]
    with_evidence = [row for row in rows if row["relevant_count"]]
    result = dict(attempts=len(rows), distinct_requests=len({row["case_id"] for row in rows}),
        scenario_clusters=len({row["scenario_id"] for row in rows}), delivered=sum(not row["failure"] for row in rows),
        failures=counts("failure"), authorized_requests=len(authorized), no_memory_needed_authorized=len(unneeded),
        retrieval_attempts=counts("retrieval_attempts"), unnecessary_retrievals=counts("unnecessary_retrievals"),
        unnecessary_retrieval_rate=fraction(counts("unnecessary_retrievals"), len(unneeded)),
        unnecessary_fraction_of_retrievals=fraction(counts("unnecessary_retrievals"), counts("retrieval_attempts")),
        retrievals_per_task=fraction(counts("retrieval_attempts"), len(rows)), authorization_violations=counts("authorization_violations"),
        selection_sensitivity=fraction(sum(row["selection_decision"] is True for row in needed_resolved), len(needed_resolved)),
        selection_specificity=fraction(sum(row["selection_decision"] is False for row in unneeded_resolved), len(unneeded_resolved)),
        selection_resolved_authorized_requests=len(needed_resolved) + len(unneeded_resolved),
        selection_unresolved_authorized_requests=counts("selection_unresolved"),
        selection_unresolved_needed=len(needed) - len(needed_resolved), selection_unresolved_unneeded=len(unneeded) - len(unneeded_resolved),
        selection_resolution_rate=fraction(len(needed_resolved) + len(unneeded_resolved), len(authorized)),
        classifier_calls=counts("selector_calls"), selection_sources=dict(Counter(row["selection_source"] for row in rows)),
        relevant_evidence_occurrences=counts("relevant_count"),
        retrieved_evidence_coverage=fraction(counts("relevant_retrieved"), counts("relevant_count")),
        supplied_evidence_coverage=fraction(counts("relevant_supplied"), counts("relevant_count")),
        requests_with_relevant_evidence=len(with_evidence),
        complete_relevant_retrieved=sum(row["complete_relevant_retrieved"] for row in with_evidence),
        complete_relevant_supplied=sum(row["complete_relevant_supplied"] for row in with_evidence),
        empty_relevant_lookup_requests=sum(row["retrieval_attempts"] for row in rows if not row["relevant_count"]),
        quality_reviewed_attempts=len(rows), task_success=counts("task_success"), success_rate=fraction(counts("task_success"), len(rows)),
        labels=dict(Counter(row["label"] for row in rows)), helpers=dict(Counter(row["helper_constraint"] or "none" for row in rows)),
        helper_speech_enum=counts("helper_speech_enum"), transformations=dict(Counter(row["response_transform"] or "none" for row in rows)))
    for key in ("inspected_count", "irrelevant_inspected", "source_candidate_count", "irrelevant_source_candidates",
                "retrieved_count", "irrelevant_retrieved", "supplied_count", "irrelevant_supplied", "prompt_tokens", "output_tokens",
                *FLAGS, "known_fact_cautious_miss", "posthoc_known_answer_without_supplied_evidence"):
        result[key] = counts(key)
    result["timing"] = {key: distribution(row[key] for row in rows) for key in TIMINGS}
    for field, selected in (("cold_first_request_s", [row for row in rows if row["cold_first_request"]]),
                            ("warm_request_s", [row for row in rows if not row["cold_first_request"]]),
                            ("success_conditional_request_s", [row for row in rows if row["task_success"]])):
        result[field] = distribution(row["request_s"] for row in selected)
    return result


def compare_summary(checks, label, expected, published):
    for key, value in expected.items():
        if key == "timing":
            for metric, stats in value.items():
                for statistic, number in stats.items():
                    checks.equal(f"{label}/{metric}/{statistic}", published[key][metric][statistic], number)
        elif key.endswith("_request_s"):
            for statistic, number in value.items():
                checks.equal(f"{label}/{key}/{statistic}", published[key][statistic], number)
        else:
            checks.equal(f"{label}/{key}", published.get(key), value)


def audit_pairs(rows, published, request_table, checks, include_bootstrap):
    lookup = {(row["model"], row["policy"], row["case_id"], row["repetition"]): row for row in rows}
    case_ids = sorted({row["case_id"] for row in rows})
    scenario_ids = sorted({row["scenario_id"] for row in rows})
    categories = sorted({row["category"] for row in rows})
    published_by_key = {(row["model"], row["comparison"], row["category"]): row for row in published}
    published_requests = {(row["model"], row["comparison"], row["case_id"]): row for row in request_table}
    request_means, raw_pairs = [], []
    for model in MODELS:
        for left, right in CONTRASTS:
            contrast = left + "-" + right
            for case_id in case_ids:
                pairs = []
                for repetition in (1, 2, 3):
                    a = lookup.get((model, left, case_id, repetition))
                    b = lookup.get((model, right, case_id, repetition))
                    if a is None or b is None:
                        continue
                    item = dict(model=model, comparison=contrast, case_id=case_id, category=a["category"],
                                scenario_id=a["scenario_id"], repetition=repetition)
                    for metric in PAIR_METRICS:
                        if a[metric] is not None and b[metric] is not None:
                            item[metric + "_difference"] = float(a[metric]) - float(b[metric])
                    item["quality_pair"] = ("both_success" if a["task_success"] and b["task_success"] else
                        "left_only" if a["task_success"] else "right_only" if b["task_success"] else "neither_success")
                    pairs.append(item)
                raw_pairs.extend(pairs)
                if not pairs:
                    continue
                mean = dict(model=model, comparison=contrast, case_id=case_id, category=pairs[0]["category"],
                            scenario_id=pairs[0]["scenario_id"], paired_repetitions=len(pairs))
                for metric in PAIR_METRICS:
                    key = metric + "_difference"
                    values = [pair[key] for pair in pairs if key in pair]
                    if values:
                        mean[key] = statistics.mean(values)
                request_means.append(mean)
                reported = published_requests[(model, contrast, case_id)]
                for key, value in mean.items():
                    checks.equal(f"paired_request/{model}/{contrast}/{case_id}/{key}", reported.get(key), value)
    checks.equal("paired request table length", len(request_table), len(request_means))
    generator = random.Random(BOOTSTRAP_SEED)
    draws = [[generator.randrange(len(scenario_ids)) for _ in scenario_ids] for _ in range(BOOTSTRAP_REPEATS)] if scenario_ids else []
    scenario_records = []
    for model in MODELS:
        for left, right in CONTRASTS:
            contrast = left + "-" + right
            for category in ("overall", *categories):
                selected = [row for row in request_means if row["model"] == model and row["comparison"] == contrast
                            and (category == "overall" or row["category"] == category)]
                attempts = [row for row in raw_pairs if row["model"] == model and row["comparison"] == contrast
                            and (category == "overall" or row["category"] == category)]
                reported = published_by_key[(model, contrast, category)]
                label = f"paired_summary/{model}/{contrast}/{category}"
                checks.equal(label + "/paired_requests", reported["paired_requests"], len(selected))
                checks.equal(label + "/paired_attempts", reported["paired_attempts"], len(attempts))
                checks.equal(label + "/quality_pairs", reported["quality_pairs"], dict(Counter(row["quality_pair"] for row in attempts)))
                directions = Counter("left_higher" if row["task_success_difference"] > 0 else
                    "right_higher" if row["task_success_difference"] < 0 else "equal" for row in selected)
                checks.equal(label + "/request_mean_success_direction", reported["request_mean_success_direction"], dict(directions))
                for metric in PAIR_METRICS:
                    key = metric + "_difference"
                    values = [row[key] for row in selected if key in row]
                    if not values:
                        continue
                    stats = reported["differences"][key]
                    checks.equal(label + "/" + key + "/mean", stats["mean"], statistics.mean(values))
                    checks.equal(label + "/" + key + "/distinct_requests", stats["distinct_requests"], len(values))
                    totals, counts = [], []
                    for scenario in scenario_ids:
                        scenario_values = [row[key] for row in selected if row["scenario_id"] == scenario and key in row]
                        totals.append(sum(scenario_values)); counts.append(len(scenario_values))
                        scenario_records.append(dict(model=model, comparison=contrast, category=category,
                            scenario_id=scenario, metric=key, requests=len(scenario_values),
                            mean=statistics.mean(scenario_values) if scenario_values else None))
                    checks.equal(label + "/" + key + "/weighted_scenario_mean", stats["mean"], sum(totals) / sum(counts))
                    if include_bootstrap and key in BOOTSTRAP_METRICS:
                        samples = []
                        for draw in draws:
                            denominator = sum(counts[index] for index in draw)
                            if denominator:
                                samples.append(sum(totals[index] for index in draw) / denominator)
                        checks.equal(label + "/" + key + "/bootstrap_low", stats["bootstrap_95_low"], quantile(samples, .025))
                        checks.equal(label + "/" + key + "/bootstrap_high", stats["bootstrap_95_high"], quantile(samples, .975))
                        checks.equal(label + "/" + key + "/bootstrap_n", stats["bootstrap_nonempty_resamples"], len(samples))
    return request_means, scenario_records


def run_audit(args):
    checks = Checks()
    freeze, run, analysis = args.freeze.resolve(), args.run.resolve(), args.analysis.resolve()
    for directory in (freeze, run, analysis):
        verify_seal(directory)
    frozen, runtime, references = (read_json(freeze / name) for name in ("freeze.json", "runtime.json", "references.json"))
    report = read_json(analysis / "analysis.json")
    schedule = {slot["slot"]: slot for slot in frozen["schedule"]}
    cases = {case["id"]: case for case in runtime["execution_cases"]}
    finish = read_json(run / "batch_finish.json")
    checks.equal("frozen schedule length", len(schedule), 18)
    checks.equal("frozen request count", len(cases), 48)
    checks.equal("planned attempts", frozen["planned_attempts"], 864)
    checks.true("analysis reports valid integrity", report["audit"]["valid"])
    checks.equal("run freeze", read_json(run / "plan.json")["freeze_sha256"], digest(freeze / "freeze.json"))
    raw, sessions = [], []
    for entry in finish["sessions"]:
        directory = Path(entry["directory"])
        verify_seal(directory)
        slot = schedule[entry["slot"]]
        summary = read_json(directory / "summary.json")
        records = read_jsonl(directory / "observations.jsonl")
        checks.equal(f"slot{entry['slot']}/manifest", read_json(directory / "manifest.json")["slot"], slot)
        checks.equal(f"slot{entry['slot']}/attempts", summary["attempted"], len(records))
        checks.equal(f"slot{entry['slot']}/request_order", [row["case"]["id"] for row in records], slot["request_ids"][:len(records)])
        for index, row in enumerate(records, 1):
            key = observation_id(row)
            checks.equal(key + "/case", row["case"], cases[row["case"]["id"]])
            checks.equal(key + "/index", row["index"], index)
            for name in ("slot", "model", "policy", "repetition"):
                checks.equal(key + "/" + name, row[name], slot[name])
            checks.equal(key + "/wall_ns", row["wall_ns"], row["finished_monotonic_ns"] - row["started_monotonic_ns"])
            checks.true(key + "/sole_model", all(call["requested_model"] == slot["model"] for call in row["calls"]))
        raw.extend(records)
        sessions.append(dict(slot=slot["slot"], attempts=len(records), directory=str(directory), status=summary["status"]))
    observed_keys = [observation_id(row) for row in raw]
    checks.equal("unique raw observations", len(set(observed_keys)), len(observed_keys))
    complete_sessions = [session for session in sessions if session["attempts"] == 48]
    if not args.allow_incomplete:
        checks.equal("completed collection", finish["status"], "complete")
        checks.equal("request-bearing complete sessions", len(complete_sessions), 18)
        checks.equal("observed attempts", len(raw), 864)
    checks.equal("reported observed attempts", report["audit"]["observed_attempts"], len(raw))
    checks.equal("reported complete sessions", report["audit"]["complete_sessions"], len(complete_sessions))
    for entry in finish.get("rejected_sessions", []):
        directory = Path(entry["directory"]); verify_seal(directory)
        checks.equal(f"admission/{directory.name}/attempts", read_json(directory / "summary.json")["attempted"], 0)
        for name in ("observations.jsonl", "events.jsonl", "http_calls.jsonl"):
            checks.equal(f"admission/{directory.name}/{name}", len(read_jsonl(directory / name)), 0)
    checks.equal("reported rejected admissions", report["audit"]["rejected_admission_count"], len(finish.get("rejected_sessions", [])))
    mappings = read_json(analysis / "private/mapping.json")
    judgments_list = read_jsonl(analysis / "resolved_reviews.jsonl")
    judgments = {item["review_id"]: item for item in judgments_list}
    checks.equal("unique review judgments", len(judgments), len(judgments_list))
    checks.equal("review mapping identities", set(judgments), {item["review_id"] for item in mappings})
    by_key = {observation_id(row): row for row in raw}
    assigned = {}
    for mapping in mappings:
        group = [by_key[key] for key in mapping["observation_keys"]]
        checks.equal(mapping["review_id"] + "/same_case", {row["case"]["id"] for row in group}, {mapping["case_id"]})
        outcomes = {(row["status"], row.get("response", {}).get("speech") if row["status"] == "ok" else None) for row in group}
        checks.equal(mapping["review_id"] + "/same_delivered_outcome", len(outcomes), 1)
        for row in group:
            key = observation_id(row)
            checks.true(key + "/unique_mapping", key not in assigned)
            assigned[key] = mapping["review_id"]
    checks.equal("complete review mapping", set(assigned), set(observed_keys))
    rows = []
    published_attempts = {row["observation_key"]: row for row in read_csv(analysis / "attempts.csv")}
    for raw_row in raw:
        key = observation_id(raw_row)
        reference = references["cases"][raw_row["case"]["id"]]
        judgment = judgments[assigned[key]]
        checks.equal(key + "/technical_failure", judgment["label"] == "technical_failure", raw_row["status"] != "ok")
        if reference["answerability"] in ("known_authorized", "self_contained_general"):
            checks.true(key + "/no_rewarded_abstention", judgment["label"] != "appropriate_abstention")
        row = reconstruct(raw_row, reference, judgment)
        row["review_id"] = assigned[key]
        checks.equal(key + "/inspected_ids", row["inspected_ids"], sorted(raw_row["adapter"]["inspected_ids"]))
        checks.equal(key + "/supplied_ids", row["supplied_ids"], sorted(raw_row["adapter"]["supplied_ids"]))
        checks.equal(key + "/retrieval_attempts", row["retrieval_attempts"], raw_row["adapter"]["retrieval_attempts"])
        for field, value in row.items():
            checks.equal(key + "/published_" + field, published_attempts[key].get(field), value)
        rows.append(row)
    checks.equal("attempt CSV membership", set(published_attempts), set(observed_keys))
    independent = {}
    for table, grouping in (("overall", ("model", "policy")), ("by_category", ("model", "policy", "category")),
                            ("by_repetition", ("model", "policy", "repetition"))):
        groups = defaultdict(list)
        for row in rows:
            groups[tuple(row[key] for key in grouping)].append(row)
        reported = {tuple(item[key] for key in grouping): item for item in report[table]}
        checks.equal(table + "/group_membership", set(reported), set(groups))
        independent[table] = []
        for group, members in sorted(groups.items()):
            result = summarize(members)
            compare_summary(checks, table + "/" + "/".join(map(str, group)), result, reported[group])
            independent[table].append({**dict(zip(grouping, group)), **result})
    request_means, scenario_means = audit_pairs(rows, report["paired"], read_csv(analysis / "paired_request_means.csv"), checks, not args.skip_bootstrap)
    known = [row for row in rows if row["answerability"] == "known_authorized"]
    known_groups = defaultdict(list)
    for row in known:
        known_groups[(row["model"], row["policy"])].append(row)
    known_summary = [dict(model=key[0], policy=key[1], attempts=len(group),
        success=sum(row["task_success"] for row in group), cautious_misses=sum(row["known_fact_cautious_miss"] for row in group),
        failures=sum(row["failure"] for row in group)) for key, group in sorted(known_groups.items())]
    return dict(passed=not checks.errors, checks=checks.count, errors=checks.errors,
        observed_attempts=len(rows), complete_sessions=len(complete_sessions), unique_review_groups=len(mappings),
        quality_origin="external resolved assistant judgments; no new semantic scoring; human validation pending",
        method="Independent standard-library parsing/arithmetic; no imports from analyzer or inference runtime",
        bootstrap_scope="request time and task-success differences" if not args.skip_bootstrap else "not recomputed",
        bootstrap_seed=BOOTSTRAP_SEED, bootstrap_repeats=BOOTSTRAP_REPEATS,
        independent_summaries=independent, known_personalization=known_summary,
        paired_request_means=request_means, paired_scenario_means=scenario_means,
        provenance={"freeze_seal_sha256": digest(freeze / "seal.json"), "run_seal_sha256": digest(run / "seal.json"),
            "analysis_seal_sha256": digest(analysis / "seal.json"), "references_sha256": digest(freeze / "references.json"),
            "mapping_sha256": digest(analysis / "private/mapping.json"), "resolved_reviews_sha256": digest(analysis / "resolved_reviews.jsonl"),
            "audit_source_sha256": digest(Path(__file__)), "python": sys.version})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--skip-bootstrap", action="store_true")
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    shutil.copyfile(__file__, args.output / "independent_numeric_audit.py")
    try:
        result = run_audit(args)
    except Exception as error:
        result = dict(passed=False, exception=type(error).__name__, message=str(error), traceback=traceback.format_exc(),
                      audit_source_sha256=digest(Path(__file__)))
    result["created_at"] = datetime.now(timezone.utc).isoformat()
    with (args.output / "numeric_audit.json").open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, default=lambda value: sorted(value) if isinstance(value, set) else str(value))
        stream.write("\n")
    with (args.output / "seal.json").open("x") as stream:
        json.dump({"sha256": {path.name: digest(path) for path in args.output.iterdir() if path.is_file() and path.name != "seal.json"},
                   "immutability": "exclusive output creation, SHA256 manifest, read-only files; not privileged WORM"}, stream, indent=2, sort_keys=True)
        stream.write("\n")
    for path in args.output.iterdir():
        path.chmod(0o400)
    args.output.chmod(0o500)
    print(json.dumps(dict(output=str(args.output), passed=result["passed"], checks=result.get("checks"), errors=len(result.get("errors", [])), exception=result.get("exception"))))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
