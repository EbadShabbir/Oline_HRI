"""Independent final artifact audit. Standard library only; never imports analyze.

Run only after the collections, metrics and adjudications have finished.
Checks arithmetic and artifacts, not the reviewers' substantive judgments.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sqlite3

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FOLLOWUP_IDS = {"fresh_035", "fresh_036", "fresh_044", "fresh_046", "fresh_047"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def cases_at(path):
    value = read(path)
    return value["cases"] if isinstance(value, dict) else value


def sha(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


def independent_latency(values):
    ordered = sorted(values)
    if not ordered:
        return {"n": 0, "p50_seconds": None, "p95_seconds": None, "mean_seconds": None,
                "minimum_seconds": None, "maximum_seconds": None}
    result = {"n": len(ordered), "mean_seconds": math.fsum(ordered) / len(ordered),
              "minimum_seconds": ordered[0], "maximum_seconds": ordered[-1]}
    for percent in (50, 95):
        rank = (len(ordered) - 1) * percent / 100
        left, right = math.floor(rank), math.ceil(rank)
        result[f"p{percent}_seconds"] = (ordered[left] if left == right else
            ordered[left] * (right - rank) + ordered[right] * (rank - left))
    return result


def approximate_equal(actual, expected):
    if actual is None or expected is None:
        return actual is expected
    return math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-8)


class Audit:
    def __init__(self):
        self.checks = []

    def check(self, condition, label, detail=None):
        self.checks.append({"check": label, "passed": bool(condition), "detail": detail})

    def hashes(self, base, expected, label):
        mismatches = [name for name, value in expected.items()
                      if not (base / name).is_file() or sha(base / name) != value]
        self.check(not mismatches, label, mismatches)


def schema_names(value):
    names = set()
    if isinstance(value, dict):
        if isinstance(value.get("properties"), dict):
            names.update(value["properties"])
        for nested in value.values():
            names.update(schema_names(nested))
    elif isinstance(value, list):
        for nested in value:
            names.update(schema_names(nested))
    return names


def independent_role(call):
    names = schema_names(call["options"].get("response_format"))
    if any(name in names for name in ("speech", "steps_for_user", "instructions", "steps")):
        return "answer_generation"
    for marker, role in (("verdict", "answer_review"), ("needs_personal_facts", "dependency_review"),
                         ("model_size", "compute_classifier")):
        if marker in names:
            return role
    return "unrecognized"


def judgments_at(path):
    value = read(path)
    if isinstance(value, dict) and "judgments" in value:
        value = value["judgments"]
    if isinstance(value, dict):
        return value
    if len(value) != len({row["id"] for row in value}):
        raise ValueError("duplicate adjudication ID")
    return {row["id"]: row for row in value}


def independent_rows(cases, raw, judgments):
    indexed = {row["id"]: row for row in raw}
    result = []
    for case in cases:
        row = indexed.get(case["id"], {})
        route, reply = row.get("route") or {}, row.get("reply") or {}
        prediction = (route.get("classifier_metadata") or {}).get("whole_request") or {}
        good_status = row.get("status") == "ok"
        delivered = good_status and bool(row.get("delivered_text", "").strip())
        judgment = judgments.get(case["id"], {})
        quality = bool(delivered and judgment.get("quality_pass") is True and
                       all(item["pass"] for item in judgment.get("required_components_pass", [])))
        final = (route.get("dependency") or {}).get("mode")
        expected = case["expected_modes"]
        result.append({"id": case["id"], "category": case["category"], "expected": expected[0],
                       "raw_match": good_status and prediction.get("predicted_mode") in expected,
                       "thresholded_match": good_status and prediction.get("mode") in expected,
                       "final_match": good_status and final in expected, "quality_pass": quality,
                       "combined_pass": quality and final in expected,
                       "generated": delivered and reply.get("generation") is not None,
                       "application": delivered and reply.get("generation") is None,
                       "seconds": row.get("wall_ns", 0) / 1e9 if row else None,
                       "status": row.get("status", "missing")})
    return result


def check_metrics(audit, rows, metrics, label):
    summary = metrics["summary"]
    audit.check(summary["planned"] == len(rows), label + ": planned denominator")
    counts = {}
    for key in ("raw_match", "thresholded_match", "final_match", "quality_pass", "combined_pass"):
        count = sum(row[key] for row in rows)
        counts[key] = count
        supplied = summary[key]
        audit.check(supplied["count"] == count and supplied["denominator"] == len(rows)
                    and approximate_equal(supplied["rate"], count / len(rows)), label + ": " + key)
    for field, metric in (("category", "per_category"), ("expected", "per_mode")):
        for group in sorted({row[field] for row in rows}):
            subset = [row for row in rows if row[field] == group]
            entry = metrics[metric][group]
            audit.check(entry["planned"] == len(subset), f"{label}: {metric}/{group} denominator")
            for key in counts:
                audit.check(entry[key]["count"] == sum(row[key] for row in subset)
                            and entry[key]["denominator"] == len(subset), f"{label}: {metric}/{group}/{key}")
    groups = {"overall_observed": rows,
              "delivered_model_generated": [row for row in rows if row["generated"]],
              "application_only": [row for row in rows if row["application"]],
              "full_quality": [row for row in rows if row["quality_pass"]],
              "combined_success": [row for row in rows if row["combined_pass"]]}
    latency_result = {}
    for name, subset in groups.items():
        computed = independent_latency([row["seconds"] for row in subset if row["seconds"] is not None])
        latency_result[name] = computed
        audit.check(all(approximate_equal(metrics["latency"][name][key], value) for key, value in computed.items()),
                    f"{label}: latency/{name}", computed)
    for dimension, key in (("category", "per_category"), ("expected", "per_mode")):
        for group in sorted({row[dimension] for row in rows}):
            computed = independent_latency([row["seconds"] for row in rows if row[dimension] == group and row["seconds"] is not None])
            audit.check(all(approximate_equal(metrics["latency"][key][group][name], value)
                            for name, value in computed.items()), f"{label}: latency/{key}/{group}")
    for seconds in (5, 10, 30, 60):
        for field, metric in (("quality_pass", "quality_deadlines"), ("combined_pass", "combined_deadlines")):
            count = sum(row[field] and row["seconds"] is not None and row["seconds"] <= seconds for row in rows)
            audit.check(metrics[metric][str(seconds)]["count"] == count
                        and metrics[metric][str(seconds)]["denominator"] == len(rows), f"{label}: {metric}/{seconds}")
        count = sum(row["generated"] and row["quality_pass"] and row["seconds"] <= seconds for row in rows)
        for metric, denominator in (("generated_quality_deadlines", sum(row["generated"] for row in rows)),
                                    ("generated_quality_deadlines_all_planned", len(rows))):
            audit.check(metrics[metric][str(seconds)]["count"] == count
                        and metrics[metric][str(seconds)]["denominator"] == denominator, f"{label}: {metric}/{seconds}")
    return {"planned": len(rows), "counts": counts, "statuses": dict(Counter(row["status"] for row in rows)),
            "latency": latency_result}


def audit_resources(audit, collection, label):
    start, finish = read(collection / "start.json"), read(collection / "finish.json")
    end = finish["snapshot"]
    audit.check(start["memory"]["mem_available_kib"] >= 2 * 1024 * 1024
                and start["memory"]["swap_used_kib"] <= 768 * 1024
                and max(start["temperatures_c"].values()) < 55, label + ": startup resource gates")
    audit.check(not start["resident_models"] and not end["resident_models"], label + ": initial/final model eviction")
    audit.check(start["fan_pwm"] > 0 and end["fan_pwm"] > 0, label + ": running fan snapshots")
    audit.check(all(start[key] == end[key] for key in ("boot_id", "power_mode", "thermal_trip_events"))
                and start["memory"]["swap_total_kib"] == end["memory"]["swap_total_kib"],
                label + ": device invariants")
    audit.check(bool(re.search(r"NV Power Mode:\s*15W\s*\n0\s*$", start["power_mode"]))
                and bool(start["thermal_trip_events"]) and not any(start["thermal_trip_events"].values()),
                label + ": power mode and zero trip counters")
    audit.check(finish["failure"] is None and not finish["cleanup_errors"] and finish["guard_violation"] is None,
                label + ": guard and cleanup outcome")
    telemetry = lines(collection / "telemetry.jsonl")
    free = [sample["ram"]["total_mb"] - sample["ram"]["used_mb"] for sample in telemetry]
    swap = [sample["swap"]["used_mb"] for sample in telemetry]
    temperature = [max(sample["temperatures_c"].values()) for sample in telemetry]
    timestamps = [sample["monotonic_ns"] for sample in telemetry]
    gaps = [(later - earlier) / 1e9 for earlier, later in zip(timestamps, timestamps[1:])]
    audit.check(bool(telemetry) and len(telemetry) == finish["telemetry"]["sample_count"], label + ": telemetry count")
    audit.check(all(0 < gap <= 5 for gap in gaps), label + ": telemetry monotonic and unstalled")
    audit.check(bool(telemetry) and min(free) >= 768 and max(swap) <= 1024 and max(temperature) < 68,
                label + ": sampled runtime RAM/swap/temperature bounds")
    return {"samples": len(telemetry), "minimum_free_ram_mb": min(free), "maximum_swap_used_mb": max(swap),
            "maximum_temperature_c": max(temperature), "maximum_sample_gap_seconds": max(gaps, default=0),
            "residency_scope": "Snapshots show startup/final empty. Existing backend checks enforce at most one resident model; raw tegrastats has no model-residency field."}


def audit_memory(audit, collection, raw, label):
    retrieval_path = collection / "run/retrieval_calls.jsonl"
    retrieval = lines(retrieval_path) if retrieval_path.exists() else []
    retrieval_results = [row for row in retrieval if row["operation"] == "retrieve"]
    audit.check(all(row["status"] == "ok" and row.get("result") == [] for row in retrieval_results),
                label + ": all retrieval results empty")
    evidence = []
    for row in raw:
        reply = row.get("reply") or {}
        diagnostics = reply.get("memory_diagnostics") or {}
        for name in ("retrieved_ids", "supplied_ids", "model_used_ids"):
            if diagnostics.get(name):
                evidence.append({"id": row["id"], "field": name})
        for name in ("reference_ids", "application_memory_ids", "retrieval"):
            if reply.get(name):
                evidence.append({"id": row["id"], "field": name})
        if (reply.get("response") or {}).get("memory_used"):
            evidence.append({"id": row["id"], "field": "response.memory_used"})
    audit.check(not evidence, label + ": no fabricated memory evidence IDs", evidence)
    database = collection / "run/memory.sqlite3"
    before = sha(database)
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        counts = {name: connection.execute('SELECT count(*) FROM "' + name + '"').fetchone()[0]
                  for name in ("memory_item", "memory_audit", "memory_embedding", "memory_fts")}
        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
    audit.check(not any(counts.values()) and quick_check == "ok", label + ": isolated SQLite empty and valid", counts)
    audit.check(sha(database) == before, label + ": SQLite audit was read-only")
    return {"retrieval_calls": len(retrieval_results), "table_counts": counts, "database_quick_check": quick_check}


def flat(text):
    return " ".join(text.casefold().split())


def audit_prompt_boundaries(audit, cases, calls, label):
    all_rubric_strings = [text for case in cases for key in ("required_components", "forbidden")
                          for text in case.get("rubric", {}).get(key, []) if isinstance(text, str)]
    uniqueness = Counter(flat(text) for text in all_rubric_strings)
    cases_by_id = {case["id"]: case for case in cases}
    hidden_keys = re.compile(r'["\'](?:expected_modes|required_components|forbidden|rubric|general_component_expected|clarification_expected)["\']\s*:')
    findings = []
    checked = 0
    for call_index, call in enumerate(calls, 1):
        case = cases_by_id[call["case_id"]]
        authorized_input = " ".join([case["text"], *[message["content"] for message in case.get("prior_turns", [])]])
        authorized_flat = flat(authorized_input)
        candidates = [phrase for phrase in all_rubric_strings if len(phrase) >= 40 and len(phrase.split()) >= 6
                      and uniqueness[flat(phrase)] == 1 and flat(phrase) not in authorized_flat]
        for message in call["messages"]:
            content = message["content"]
            checked += 1
            for match in hidden_keys.finditer(content):
                if match.group() not in authorized_input:
                    findings.append({"call_index": call_index, "id": case["id"], "kind": "hidden_rubric_key", "value": match.group()})
            if case["id"] in content and case["id"] not in authorized_input:
                findings.append({"call_index": call_index, "id": case["id"], "kind": "hidden_case_id"})
            for phrase in candidates:
                if flat(phrase) in flat(content):
                    findings.append({"call_index": call_index, "id": case["id"], "kind": "unique_complete_rubric_literal", "value": phrase})
    audit.check(not findings, label + ": no hidden labels or unique rubric literals in model prompts", findings)
    return {"messages_checked": checked, "rubric_strings_available": len(all_rubric_strings), "findings": findings,
            "scope": "Checks hidden rubric-field keys, case IDs, and unique complete rubric sentences >=40 characters/6 words absent from authorized input. Generic mode words are intentionally excluded; this literal check is not proof against semantic leakage."}


def audit_collection(audit, *, name, collection, cases_path, judgments_path, metrics_path, freeze_path, expected_count):
    cases, raw = cases_at(cases_path), lines(collection / "run/observations.jsonl")
    judgments, metrics, freeze = judgments_at(judgments_path), read(metrics_path), read(freeze_path)
    audit.check(len(cases) == expected_count == len(raw), name + ": complete case count")
    audit.check([row["id"] for row in raw] == [case["id"] for case in cases], name + ": exact frozen order")
    audit.check(len({row["id"] for row in raw}) == len(raw), name + ": unique observation IDs")
    audit.check(set(judgments) == {case["id"] for case in cases}, name + ": exact adjudication coverage")
    audit.check(all(row["case"] == case for row, case in zip(raw, cases)), name + ": embedded cases unchanged")
    audit.check(freeze["cases_sha256"] == sha(cases_path), name + ": frozen corpus hash")
    audit.hashes(ROOT, freeze["source_sha256"], name + ": working source SHA256")
    audit.hashes(freeze_path.parent, freeze["artifact_sha256"], name + ": preregistered artifact SHA256")
    audit.hashes(collection, read(collection / "artifact_sha256.json"), name + ": sealed collection SHA256")
    initial, final = read(collection / "integrity_before.json"), read(collection / "integrity_after.json")
    audit.check(initial == final and initial["cases_sha256"] == sha(cases_path), name + ": before/after source/config/corpus/embedding")
    audit.check(all(freeze["source_sha256"].get(path) == value for path, value in initial["source_sha256"].items()),
                name + ": runtime sources were frozen")
    models = read(collection / "models_before.json")
    audit.check(models == read(collection / "models_after.json"), name + ": model/server identity unchanged")
    audit.check(all(re.fullmatch(r"[0-9a-f]{64}", row["digest"]) and 0 < row["parameter_count"] < 4_000_000_000
                    and row["size"] <= 1_610_612_736 for row in models["models"].values()), name + ": model artifact bounds")
    calls = lines(collection / "run/model_calls.jsonl")
    audit.check(calls == [call for row in raw for call in row["calls"]], name + ": raw-call exact correspondence")
    call_counts = Counter(independent_role(call) for call in calls)
    audit.check("unrecognized" not in call_counts, name + ": all call schemas recognized")
    audit.check(dict(call_counts) == metrics["actual_calls"]["by_role"] and len(calls) == metrics["actual_calls"]["total"],
                name + ": independent model-call counts")
    bounds = {"answer_generation": 2, "answer_review": 2, "dependency_review": 1, "compute_classifier": 1}
    violations = []
    for row in raw:
        counts = Counter(independent_role(call) for call in row["calls"])
        if any(counts[role] > maximum for role, maximum in bounds.items()):
            violations.append({"id": row["id"], "counts": dict(counts)})
    audit.check(not violations, name + ": bounded generation/review calls", violations)
    audit.check(all(call["model"] in models["models"] for call in calls), name + ": only frozen models called")
    independently_scored = independent_rows(cases, raw, judgments)
    arithmetic = check_metrics(audit, independently_scored, metrics, name)
    resources = audit_resources(audit, collection, name)
    memory = audit_memory(audit, collection, raw, name)
    prompts = audit_prompt_boundaries(audit, cases, calls, name)
    return {"arithmetic": arithmetic, "resources": resources, "memory": memory, "prompt_boundaries": prompts,
            "actual_calls": dict(call_counts), "model_identities": models, "case_ids": [case["id"] for case in cases]}, independently_scored, raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "independent_audit.json")
    parser.add_argument("--supplement-collection", type=Path, default=HERE / "collection_whitespace")
    parser.add_argument("--supplement-metrics", type=Path, default=HERE / "whitespace_analysis/metrics.json")
    parser.add_argument("--supplement-judgments", type=Path, default=HERE / "whitespace_adjudicated_judgments.json")
    parser.add_argument("--primary-only", action="store_true",
                        help="Audit primary results while supplemental adjudication is still pending")
    args = parser.parse_args(argv)
    audit, result = Audit(), {"created_at": datetime.now(timezone.utc).isoformat(),
                              "method": "Independent standard-library recomputation; analyze.py and individual reviews are never imported/read."}
    try:
        candidate = read(HERE / "candidate_freeze.json")["source_sha256"]
        harness = read(HERE / "harness_freeze.json")["source_sha256"]
        audit.hashes(HERE / "candidate_source", candidate, "archived candidate SHA256")
        audit.hashes(HERE / "harness_source", harness, "archived harness SHA256")
        original_cases = cases_at(HERE / "cases.json")
        original_ids = [case["id"] for case in original_cases]
        authored_ids = [case["id"] for case in cases_at(HERE / "authoring/cases.json")]
        random.Random(20260916).shuffle(authored_ids)
        audit.check(original_ids == authored_ids, "preregistered seeded shuffle of authored IDs")
        audit.check(set(original_ids) == {f"fresh_{number:03}" for number in range(1, 49)}, "exact original fresh_001..fresh_048 IDs")
        primary, primary_rows, primary_raw = audit_collection(audit, name="primary", collection=HERE / "collection",
            cases_path=HERE / "cases.json", judgments_path=HERE / "adjudicated_judgments.json",
            metrics_path=HERE / "metrics.json", freeze_path=HERE / "evaluation_freeze.json", expected_count=48)
        result["primary"] = primary
        if args.supplement_collection.exists() and not args.primary_only:
            supplemental_cases = cases_at(HERE / "whitespace_followup_cases.json")
            audit.check([case["id"] for case in supplemental_cases] == [identifier for identifier in original_ids if identifier in FOLLOWUP_IDS],
                        "supplement contains exactly preregistered five IDs in relative order")
            old_cases = {case["id"]: case for case in original_cases}
            for case in supplemental_cases:
                original = old_cases[case["id"]]
                expected = dict(original, text=original["text"].replace("\n", " "))
                audit.check(case == expected, "supplement whitespace-only input change: " + case["id"])
            eligibility = [row["id"] for row in primary_raw if row["id"] in FOLLOWUP_IDS and row["status"] == "error"
                and row.get("error") == {"type": "ValueError", "message": "user message cannot contain control characters"}
                and row.get("route") is None and row.get("calls") == [] and not row.get("delivered_text") and not row.get("reply")]
            audit.check(set(eligibility) == FOLLOWUP_IDS, "supplement mechanical zero-call rejection eligibility")
            supplementary, supplemental_rows, supplemental_raw = audit_collection(audit, name="supplement", collection=args.supplement_collection,
                cases_path=HERE / "whitespace_followup_cases.json", judgments_path=args.supplement_judgments,
                metrics_path=args.supplement_metrics, freeze_path=HERE / "whitespace_followup_freeze.json", expected_count=5)
            result["supplement"] = supplementary
            combined = [row for row in primary_rows if row["id"] not in FOLLOWUP_IDS] + supplemental_rows
            result["exploratory_corrected_input"] = {"denominator": len(combined),
                "counts": {key: sum(row[key] for row in combined) for key in ("raw_match", "thresholded_match", "final_match", "quality_pass", "combined_pass")},
                "warning": "43 original observations plus 5 normalized observations from another session; not the preregistered 48-case result or a single-session latency estimate."}
            audit.check(len(primary_raw) + len(supplemental_raw) == 53, "all 53 attempts preserved")
        result["audited_artifact_sha256"] = {"script": sha(Path(__file__)), "primary_metrics": sha(HERE / "metrics.json"),
            "primary_judgments": sha(HERE / "adjudicated_judgments.json")}
    except Exception as error:
        audit.check(False, "audit execution completed", {"type": type(error).__name__, "message": str(error)})
    result["checks"] = audit.checks
    result["checks_passed"] = sum(check["passed"] for check in audit.checks)
    result["checks_failed"] = sum(not check["passed"] for check in audit.checks)
    result["passed"] = bool(audit.checks) and result["checks_failed"] == 0
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    print(json.dumps({key: result[key] for key in ("passed", "checks_passed", "checks_failed")}, indent=2))
    for check in audit.checks:
        if not check["passed"]:
            print("FAILED: " + check["check"] + " " + json.dumps(check["detail"]))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
