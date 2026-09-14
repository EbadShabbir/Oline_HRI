"""Audit Stage 2 artifacts, summarize measurements, and prepare blinded review.

Purely offline: no inference, no changes to raw runs, no semantic quality score.
Frozen regex checks are lexical signals only, including when all match. Missing
sessions and failed requests remain explicit rather than becoming good answers.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import hmac
from itertools import combinations
import json
import math
import os
from pathlib import Path
import random
import re
import secrets

from analyze_arc_capability import canonical_bytes, distribution, read_json, read_jsonl


SMALL, LARGE = "qwen3:0.6b", "qwen3:1.7b"
ARM_ORDERS = (("small", "large", "cascade"),
              ("large", "cascade", "small"),
              ("cascade", "small", "large"))
ALLOWED = {"small": {SMALL}, "large": {LARGE}, "cascade": {SMALL, LARGE}}
COMPLETE = {"complete", "complete_with_errors"}
EXPECTED_LIMITS = {
    "min_start_available_kib": 2097152, "max_start_swap_used_kib": 786432,
    "max_start_temperature_c_exclusive": 55.0,
    "min_runtime_available_kib": 786432, "max_runtime_swap_used_kib": 1048576,
    "max_runtime_temperature_c_exclusive": 68.0,
}


def file_hash(path):
    return sha256(path.read_bytes()).hexdigest()


def require(condition, message, errors):
    if not condition:
        errors.append(message)


def nonnegative(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def session_slots(arm_orders=None):
    orders = ARM_ORDERS if arm_orders is None else arm_orders
    return [(f"{index:02d}_{arm}_r{repetition}", arm, repetition)
            for index, (repetition, arm) in enumerate(
                ((repetition, arm) for repetition, arms in enumerate(orders, 1) for arm in arms), 1)]


def validate_workload(workload):
    cases = workload["execution_cases"]
    ids = [case["id"] for case in cases]
    if len(cases) != 48 or len(set(ids)) != 48 or set(ids) != set(workload["rubrics"]):
        raise ValueError("expected 48 unique requests with exactly matched frozen rubrics")
    for case in cases:
        if set(case) != {"id", "stratum", "scenario_id", "prompt"}:
            raise ValueError("unexpected execution-case fields")
        rubric = workload["rubrics"][case["id"]]
        checks = rubric["automated_checks"]
        if checks["kind"] != "lexical_signals_only":
            raise ValueError("only explicitly lexical automated checks are supported")
        for group in checks["required_groups"]:
            if not group["any"]:
                raise ValueError("lexical groups must contain a pattern")
            for pattern in group["any"]:
                re.compile(pattern, re.IGNORECASE)
        for pattern in checks["forbidden_presence_patterns"]:
            re.compile(pattern, re.IGNORECASE)
    return cases


def lexical_signals(record, rubric):
    """Presence can match a negation; absence can miss a valid paraphrase."""
    checks = rubric["automated_checks"]
    if record["status"] != "ok":
        return {"status": "not_evaluated_no_delivery", "semantic_correctness": None,
                "required_group_count": len(checks["required_groups"]),
                "required_groups_matched": None, "all_required_groups_matched": None,
                "missing_group_claims": [], "forbidden_presence_patterns_matched": []}
    speech = record["response"]["speech"]
    matches = [any(re.search(pattern, speech, re.IGNORECASE) for pattern in group["any"])
               for group in checks["required_groups"]]
    return {
        "status": "lexical_signals_only", "semantic_correctness": None,
        "required_group_count": len(matches), "required_groups_matched": sum(matches),
        "all_required_groups_matched": all(matches) if matches else None,
        "missing_group_claims": [group["claim"] for group, match in zip(checks["required_groups"], matches) if not match],
        "forbidden_presence_patterns_matched": [pattern for pattern in checks["forbidden_presence_patterns"]
                                                if re.search(pattern, speech, re.IGNORECASE)],
    }


def validate_row(record, case, index, arm, repetition, *, comparison_profile=None):
    errors = []
    for key in ("id", "prompt", "stratum", "scenario_id"):
        require(record.get(key) == case[key], f"case field mismatch: {key}", errors)
    require(record.get("arm") == arm and record.get("repetition") == repetition
            and record.get("index") == index, "arm/repetition/index mismatch", errors)
    require(record.get("status") in {"ok", "error", "interrupted"}, "unknown request status", errors)
    require(nonnegative(record.get("wall_ns")), "invalid request wall time", errors)
    if nonnegative(record.get("started_monotonic_ns")) and nonnegative(record.get("finished_monotonic_ns")):
        require(record["wall_ns"] == record["finished_monotonic_ns"] - record["started_monotonic_ns"],
                "request clock interval differs from wall time", errors)
    else:
        errors.append("missing request monotonic interval")
    calls = record.get("calls", [])
    require(isinstance(calls, list), "calls must be a list", errors)
    for call in calls:
        requested, actual = call.get("requested_model"), call.get("actual_model")
        require(requested in ALLOWED[arm], "request used a model outside the arm", errors)
        require(actual is None or actual == requested, "returned/requested model mismatch", errors)
        require(nonnegative(call.get("wall_ns")), "invalid call wall time", errors)
        require(call.get("purpose") in {"memory_selector", "compute_selector", "generation"},
                "unknown model-call purpose", errors)
        call_generation = call.get("generation") or call.get("raw_generation")
        if call_generation is not None:
            require(call_generation.get("model") == requested, "raw model metadata mismatch", errors)
            for field in ("total_duration_ns", "load_duration_ns", "prompt_eval_duration_ns", "eval_duration_ns"):
                require(nonnegative(call_generation.get(field)), f"invalid {field}", errors)
        if call.get("status") == "ok":
            require(actual == requested and call.get("generation") is not None,
                    "successful call lacks actual model/result", errors)
        require(call.get("seed") == 42, "model call did not record frozen seed 42", errors)
    if arm != "cascade":
        require(not any(call.get("purpose") == "compute_selector" for call in calls),
                "fixed arm made an unnecessary compute-classifier call", errors)
    if comparison_profile is not None:
        from analyze_post_memory_comparison import PROFILE_ID, validate_route_contract
        if comparison_profile != PROFILE_ID:
            raise ValueError("unsupported explicit comparison profile")
        errors.extend(validate_route_contract(record, arm))
    if record.get("status") == "ok":
        purposes = Counter(call.get("purpose") for call in calls)
        if comparison_profile is None:
            require(purposes["memory_selector"] == 1, "delivered request needs one memory selection", errors)
            require(purposes["compute_selector"] == (1 if arm == "cascade" else 0),
                    "unexpected compute selection count", errors)
        require(purposes["generation"] in ({1, 2} if arm == "cascade" else {1}),
                "unexpected generation count", errors)
        response = record.get("response", {})
        require(isinstance(response.get("speech"), str) and bool(response.get("speech")),
                "delivered response has no speech", errors)
        generation = record.get("generation", {})
        require(generation.get("model") in ALLOWED[arm], "delivered model outside arm", errors)
        require(generation.get("done_reason") != "length", "truncated response marked delivered", errors)
        route = record.get("route", {})
        if arm != "cascade":
            require(route.get("model_size_generation") is None
                    and route.get("model_size_decision_source") == "fixed_generator",
                    "fixed compute decision is not explicitly recorded", errors)
            require(record.get("fallback_from_model") is None, "fixed arm fell back", errors)
            require(record.get("generation_policy") in {"fixed_generator", "fixed_generator_verified_constraint"},
                    "fixed generator policy absent", errors)
        memory = record.get("memory", {})
        cited = response.get("memory_used", [])
        require(len(cited) == len(set(cited)), "duplicate delivered citation", errors)
        require(set(cited).issubset(memory.get("supplied_ids", [])), "citation was not supplied", errors)
        require(cited == memory.get("model_used_ids"), "citation diagnostics differ from delivery", errors)
    return errors


def telemetry_metrics(samples, rows):
    if not samples:
        return {"sample_count": 0}
    timestamps = [sample["monotonic_ns"] for sample in samples]
    if any(right <= left for left, right in zip(timestamps, timestamps[1:])):
        raise ValueError("telemetry timestamps are not strictly increasing")
    watts = [sample["vdd_in"]["instant_mw"] / 1000 for sample in samples]
    if any(not nonnegative(value) for value in watts):
        raise ValueError("invalid telemetry power")
    energy = math.fsum((left + right) / 2 * (end - start) / 1e9
                       for left, right, start, end in zip(watts, watts[1:], timestamps, timestamps[1:]))
    result = {
        "sample_count": len(samples), "duration_seconds": (timestamps[-1] - timestamps[0]) / 1e9,
        "whole_interval_energy_joules": energy,
        "peak_ram_used_mb": max(sample["ram"]["used_mb"] for sample in samples),
        "peak_swap_used_mb": max(sample["swap"]["used_mb"] for sample in samples),
        "peak_temperature_c": max(max(sample["temperatures_c"].values()) for sample in samples),
        "gpu_activity_percent": distribution([sample["gr3d_percent"] for sample in samples]),
        "scope": "whole device including setup and cleanup; no idle subtraction; onboard VDD_IN estimate",
    }
    # Clip trapezoids to each request interval. Interpolate endpoint power and
    # leave unsampled prefixes/suffixes uncovered; do not extrapolate energy.
    request_energy, covered_ns = 0.0, 0
    for row in rows:
        a, b = row["started_monotonic_ns"], row["finished_monotonic_ns"]
        for t0, t1, p0, p1 in zip(timestamps, timestamps[1:], watts, watts[1:]):
            left, right = max(a, t0), min(b, t1)
            if right <= left:
                continue
            pa = p0 + (p1 - p0) * (left - t0) / (t1 - t0)
            pb = p0 + (p1 - p0) * (right - t0) / (t1 - t0)
            request_energy += (pa + pb) / 2 * (right - left) / 1e9
            covered_ns += right - left
    result.update(request_intervals_energy_joules=request_energy,
                  request_interval_covered_seconds=covered_ns / 1e9,
                  request_interval_requested_seconds=sum(row["wall_ns"] for row in rows) / 1e9,
                  request_energy_scope="whole-device energy during covered request intervals, not model-only energy")
    return result


def inspect_session(root, directory, arm, repetition, workload, frozen, *, comparison_profile=None):
    path = root / directory
    result = {"directory": directory, "arm": arm, "repetition": repetition,
              "planned": 48, "attempted": 0, "delivered": 0, "complete": False,
              "valid": False, "status": "missing", "errors": [], "artifact_sha256": {},
              "missing_artifacts": []}
    if not path.exists():
        return result, []
    errors = result["errors"]
    result["status"] = "in_progress_or_incomplete"
    records, manifest, start, finish = [], None, None, None
    for name in ("manifest.json", "workload.json", "start.json", "finish.json",
                 "memory_setup.json", "observations.jsonl", "telemetry.jsonl", "summary.json"):
        if not (path / name).is_file():
            result["missing_artifacts"].append(name)
        else:
            result["artifact_sha256"][name] = file_hash(path / name)
    try:
        if (path / "manifest.json").is_file():
            manifest = read_json(path / "manifest.json")
            result["manifest"] = manifest
            require(manifest.get("arm") == arm and manifest.get("repetition") == repetition,
                    "manifest slot mismatch", errors)
            require(manifest.get("frozen") == frozen, "manifest differs from the externally supplied freeze", errors)
            require(set(manifest.get("models", {})) == ALLOWED[arm], "wrong permitted models", errors)
            require(all(manifest["models"][model] == frozen["models"][model] for model in ALLOWED[arm]),
                    "model artifact differs from freeze", errors)
            require(manifest.get("ollama_version") == frozen["ollama_version"], "Ollama version differs", errors)
            require(manifest.get("generation_seed") == 42, "manifest generation seed differs", errors)
            config = manifest["config"]
            require(config["generation"] == {"context_length": 2048, "max_output_tokens": 192,
                                               "temperature": 0.0, "thinking": False},
                    "generation settings differ", errors)
            require(set(config["ollama"][key] for key in ("small_model", "general_large_model", "large_model"))
                    == ALLOWED[arm], "client model residency roles differ from arm", errors)
            if comparison_profile is not None:
                from analyze_post_memory_comparison import validate_manifest_contract
                errors.extend(validate_manifest_contract(manifest, frozen, arm))
        if (path / "workload.json").is_file():
            require(read_json(path / "workload.json") == workload, "archived workload differs", errors)
        if (path / "start.json").is_file():
            start = read_json(path / "start.json")
            result["start"] = start
        if (path / "finish.json").is_file():
            finish = read_json(path / "finish.json")
            result["finish"] = finish
            result["status"] = finish.get("status", "unknown")
        if start is not None and manifest is not None:
            policy = manifest["device_policy"]
            require(all(policy.get(key) == expected for key, expected in EXPECTED_LIMITS.items()),
                    "device limits differ from the declared common Stage 2 policy", errors)
            require(start.get("resident_models") == [], "session did not start empty", errors)
            require(start["memory"]["mem_available_kib"] >= policy["min_start_available_kib"], "startup RAM gate failed", errors)
            require(start["memory"]["swap_used_kib"] <= policy["max_start_swap_used_kib"], "startup swap gate failed", errors)
            require(max(start["temperatures_c"].values()) < policy["max_start_temperature_c_exclusive"],
                    "startup temperature gate failed", errors)
            require(type(start.get("fan_pwm")) is int and start["fan_pwm"] > 0, "startup fan unavailable", errors)
            require(bool(start.get("thermal_trip_events")) and not any(start["thermal_trip_events"].values()),
                    "startup thermal trip counters unavailable/nonzero", errors)
            require(bool(re.search(r"NV Power Mode:\s*15W\s*\n0\s*\Z", start.get("power_mode", ""))),
                    "startup power mode differs", errors)
        if finish is not None:
            require(finish.get("resident_models") == [], "cleanup left a resident model", errors)
            require(finish.get("cleanup_errors") == [], "model cleanup failed", errors)
            require(type(finish.get("fan_pwm")) is int and finish["fan_pwm"] > 0,
                    "finish fan is unavailable or stopped", errors)
            if start is not None:
                require(finish.get("boot_id") == start.get("boot_id"), "boot changed during session", errors)
                require(finish.get("thermal_trip_events") == start.get("thermal_trip_events"),
                        "thermal trips changed during session", errors)
                require(finish.get("power_mode") == start.get("power_mode"), "power mode changed during session", errors)
            if result["status"] in COMPLETE:
                require(finish.get("guard_violation") is None and finish.get("telemetry_reader_error") is None,
                        "completed session recorded a safety/telemetry violation", errors)
        if (path / "memory_setup.json").is_file():
            setup = read_json(path / "memory_setup.json")
            require(sha256(canonical_bytes(setup["snapshot"])).hexdigest() == setup["snapshot_sha256"],
                    "memory snapshot digest does not match", errors)
            result["memory_snapshot_sha256"] = setup["snapshot_sha256"]
            result["memory_setup_seconds"] = setup["wall_ns"] / 1e9
            seed = workload["memory_seed"]
            profiles = sorted({item["profile_id"] for item in setup["snapshot"]})
            require(all(profile == seed["profile_id"] for profile in profiles),
                    "memory snapshot contains a profile outside the synthetic workload", errors)
            for event in setup.get("events", []):
                if isinstance(event.get("result"), dict):
                    require(event["result"].get("profile_id") == seed["profile_id"],
                            "memory setup event contains a different profile", errors)
            result["memory_execution_scope"] = {
                "database_path": str((path / "memory.sqlite3").resolve()),
                "database_path_source": "explicit session-local path in frozen runner; analyzer reads saved snapshots only",
                "profile_id": seed["profile_id"], "retention_days": seed.get("retention_days", 7),
                "evaluation_at": seed["evaluation_at"], "snapshot_profile_ids": profiles,
                "snapshot_rows": len(setup["snapshot"]),
                "base_config_overridden_fields": ["memory.database_path", "memory.profile_id", "memory.retention_days"],
            }
        if (path / "observations.jsonl").is_file():
            records = read_jsonl(path / "observations.jsonl")
            require(len(records) <= 48, "session contains more than 48 attempts", errors)
            for index, (record, case) in enumerate(zip(records, workload["execution_cases"]), 1):
                errors.extend(f"row {index}: {error}" for error in validate_row(
                    record, case, index, arm, repetition, comparison_profile=comparison_profile))
            require(len({record.get("id") for record in records}) == len(records), "duplicate request ID", errors)
            require(all(left["finished_monotonic_ns"] <= right["started_monotonic_ns"]
                        for left, right in zip(records, records[1:])), "request intervals overlap or are reordered", errors)
        result["attempted"] = len(records)
        result["delivered"] = sum(record["status"] == "ok" for record in records)
        result["first_request_seconds"] = records[0]["wall_ns"] / 1e9 if records else None
        result["later_request_latency_seconds"] = distribution([record["wall_ns"] / 1e9 for record in records[1:]])
        result["request_latency_seconds"] = distribution([record["wall_ns"] / 1e9 for record in records])
        if result["status"] in COMPLETE:
            require(not result["missing_artifacts"], f"completed session is missing {result['missing_artifacts']}", errors)
            require(len(records) == 48, "completed session lacks 48 attempts", errors)
            require(all(record["status"] != "interrupted" for record in records),
                    "completed session contains an interrupted attempt", errors)
        if (path / "telemetry.jsonl").is_file():
            samples = read_jsonl(path / "telemetry.jsonl")
            result["telemetry"] = telemetry_metrics(samples, records)
            if result["status"] in COMPLETE and manifest is not None:
                policy = manifest["device_policy"]
                require(bool(samples), "completed session has no telemetry", errors)
                require(all(sample["swap"]["used_mb"] <= policy["max_runtime_swap_used_kib"] / 1024
                            and sample["ram"]["total_mb"] - sample["ram"]["used_mb"] >= policy["min_runtime_available_kib"] / 1024
                            and max(sample["temperatures_c"].values()) < policy["max_runtime_temperature_c_exclusive"]
                            for sample in samples), "completed session crossed a sampled runtime guard", errors)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        errors.append(f"artifact validation failed: {type(error).__name__}: {error}")
    if comparison_profile is not None:
        from analyze_post_memory_comparison import validate_session_contract
        errors.extend(validate_session_contract(path, records, manifest, finish, frozen, result))
    result["valid"] = not errors
    result["complete"] = result["valid"] and result["status"] in COMPLETE and len(records) == 48
    return result, records


def supplied_evidence(record):
    """Recover the evidence schema even when output validation rejected delivery."""
    memory = record.get("memory") or {}
    generation_calls = [call for call in record.get("calls", []) if call.get("purpose") == "generation"]
    supplied, supplied_known = set(), "supplied_ids" in memory
    supplied_source = "delivered_memory_diagnostics" if supplied_known else "unknown_no_generation_schema"
    if supplied_known:
        supplied.update(memory["supplied_ids"])
    else:
        for call in generation_calls:
            memory_schema = ((call.get("response_format") or {}).get("properties", {}).get("memory_used") or {})
            identifiers = memory_schema.get("items", {}).get("enum")
            if isinstance(identifiers, list):
                supplied.update(identifiers)
                supplied_known = True
            elif memory_schema.get("maxItems") == 0:
                supplied_known = True
        if supplied_known:
            supplied_source = "generation_response_schema"
    return supplied, supplied_known, supplied_source


def row_metrics(record, rubric):
    calls = record.get("calls", [])
    raw_generation = [call.get("generation") or call.get("raw_generation") for call in calls
                      if call.get("generation") is not None or call.get("raw_generation") is not None]
    generation_calls = [call for call in calls if call.get("purpose") == "generation"]
    supplied, supplied_known, supplied_source = supplied_evidence(record)
    cited = set((record.get("response") or {}).get("memory_used", []))
    required, forbidden = set(rubric["required_memory_ids"]), set(rubric["forbidden_memory_ids"])
    routing = record.get("routing_wall_ns")
    if routing is None:
        routing = sum(call["wall_ns"] for call in calls if call.get("purpose") != "generation")
    generation_wall = sum(call["wall_ns"] for call in generation_calls)
    retrieval = sum(call["wall_ns"] for call in record.get("retrieval_calls", []))
    return {
        "arm": record["arm"], "repetition": record["repetition"], "case_id": record["id"],
        "stratum": record["stratum"], "scenario_id": record["scenario_id"],
        "status": record["status"], "delivered": record["status"] == "ok",
        "wall_seconds": record["wall_ns"] / 1e9, "routing_seconds": routing / 1e9,
        "generation_call_wall_seconds": generation_wall / 1e9, "retrieval_seconds": retrieval / 1e9,
        "unaccounted_wall_seconds": (record["wall_ns"] - routing - generation_wall - retrieval) / 1e9,
        "unaccounted_scope": "packing, helper logic, validation and outer backend checks; not isolated validation time",
        "ollama_load_seconds": sum(item["load_duration_ns"] for item in raw_generation) / 1e9,
        "ollama_prefill_seconds": sum(item["prompt_eval_duration_ns"] for item in raw_generation) / 1e9,
        "ollama_decode_seconds": sum(item["eval_duration_ns"] for item in raw_generation) / 1e9,
        "reported_ollama_load_count_over_100ms": sum(item["load_duration_ns"] > 100_000_000 for item in raw_generation),
        "call_counts": dict(Counter(call["purpose"] for call in calls)),
        "model_call_count": len(calls), "calls_with_reported_duration_metadata": len(raw_generation),
        "generation_models": [call.get("actual_model") or call.get("requested_model") for call in generation_calls],
        "answer_constraint": record.get("answer_constraint"), "generation_policy": record.get("generation_policy"),
        "response_transform": record.get("response_transform"), "fallback_from_model": record.get("fallback_from_model"),
        "retrieval_invoked": bool(record.get("retrieval_calls")),
        "supplied_ids": sorted(supplied) if supplied_known else None, "cited_ids": sorted(cited),
        "supplied_evidence_known": supplied_known, "supplied_evidence_source": supplied_source,
        "required_ids_missing_from_evidence": sorted(required - supplied) if supplied_known else None,
        "required_ids_missing_from_citations": sorted(required - cited),
        "forbidden_supplied_ids": sorted(forbidden & supplied) if supplied_known else None,
        "forbidden_cited_ids": sorted(forbidden & cited),
        "lexical_signals": lexical_signals(record, rubric),
        "semantic_quality": "pending_blinded_review",
    }


def aggregate_metrics(rows, planned):
    delivered = [row for row in rows if row["delivered"]]
    return {
        "planned": planned, "attempted": len(rows), "unattempted": planned - len(rows),
        "distinct_observed_cases": len({row["case_id"] for row in rows}),
        "observed_repetitions": sorted({row["repetition"] for row in rows}),
        "delivered": len(delivered), "technical_failures": len(rows) - len(delivered),
        "latency_all_seconds": distribution([row["wall_seconds"] for row in rows]),
        "latency_delivered_seconds": distribution([row["wall_seconds"] for row in delivered]),
        "latency_failed_seconds": distribution([row["wall_seconds"] for row in rows if not row["delivered"]]),
        **{field: distribution([row[field] for row in rows]) for field in (
            "routing_seconds", "generation_call_wall_seconds", "retrieval_seconds", "unaccounted_wall_seconds",
            "ollama_load_seconds", "ollama_prefill_seconds", "ollama_decode_seconds")},
        "generation_models": dict(Counter(model for row in rows for model in row["generation_models"])),
        "model_call_count": sum(row["model_call_count"] for row in rows),
        "calls_with_reported_duration_metadata": sum(row["calls_with_reported_duration_metadata"] for row in rows),
        "answer_constraints": dict(Counter(row["answer_constraint"] or "none" for row in rows)),
        "generation_policies": dict(Counter(row["generation_policy"] or "none" for row in rows)),
        "response_transforms": dict(Counter(row["response_transform"] or "none" for row in rows)),
        "fallback_count": sum(row["fallback_from_model"] is not None for row in rows),
        "retrieval_requests": sum(row["retrieval_invoked"] for row in rows),
        "delivered_with_missing_required_citations": sum(bool(row["required_ids_missing_from_citations"]) for row in delivered),
        "delivered_with_forbidden_citations": sum(bool(row["forbidden_cited_ids"]) for row in delivered),
        "requests_supplied_forbidden_ids": sum(bool(row["forbidden_supplied_ids"]) for row in rows),
        "requests_with_unknown_supplied_evidence": sum(not row["supplied_evidence_known"] for row in rows),
        "delivered_with_lexical_missing_signals": sum(bool(row["lexical_signals"]["missing_group_claims"]) for row in delivered),
        "delivered_with_forbidden_presence_signals": sum(bool(row["lexical_signals"]["forbidden_presence_patterns_matched"]) for row in delivered),
        "lexical_signal_warning": "Pattern presence/absence is not semantic correctness, including negated mentions and paraphrases.",
        "semantic_quality": "pending_blinded_review", "semantic_correctness_rate": None,
    }


def variability(cases, raw_rows):
    result = []
    for arm in ALLOWED:
        for case in cases:
            selected = [row for row in raw_rows if row["arm"] == arm and row["id"] == case["id"]]
            signatures = Counter(sha256(canonical_bytes({"status": row["status"], "response": row.get("response")})).hexdigest()
                                 for row in selected)
            result.append({"arm": arm, "case_id": case["id"], "scenario_id": case["scenario_id"],
                           "observed_repetitions": len(selected), "unique_delivery_outcomes": len(signatures),
                           "outcome_sha256_counts": dict(signatures),
                           "latency_seconds": distribution([row["wall_ns"] / 1e9 for row in selected])})
    return result


def paired_latency(cases, rows):
    indexed = defaultdict(list)
    for row in rows:
        indexed[(row["arm"], row["case_id"])].append(row["wall_seconds"])
    result = []
    for left, right in combinations(ALLOWED, 2):
        by_scenario = defaultdict(list)
        differences = []
        for case in cases:
            a, b = indexed[(left, case["id"])], indexed[(right, case["id"])]
            if len(a) != 3 or len(b) != 3:
                continue
            difference = sum(a) / 3 - sum(b) / 3
            differences.append(difference)
            by_scenario[case["scenario_id"]].append(difference)
        interval = None
        if by_scenario:
            randomizer = random.Random(20260911)
            groups = list(by_scenario.values())
            bootstraps = []
            for _ in range(2000):
                sampled = [value for group in randomizer.choices(groups, k=len(groups)) for value in group]
                bootstraps.append(sum(sampled) / len(sampled))
            bootstraps.sort()
            interval = [bootstraps[49], bootstraps[1949]]
        result.append({"left_minus_right": f"{left}-{right}", "paired_distinct_cases": len(differences),
                       "scenario_groups": len(by_scenario), "case_mean_latency_difference_seconds": distribution(differences),
                       "exploratory_scenario_bootstrap_mean_95pct_interval_seconds": interval,
                       "scope": "three timing repetitions averaged per item; cases paired and scenario groups resampled; shared profile/session effects remain"})
    return result


def make_blinded_review(workload, raw_rows, seed):
    key = bytes.fromhex(seed)
    if len(key) != 32:
        raise ValueError("blind seed must be 64 hexadecimal characters")
    cases = {case["id"]: case for case in workload["execution_cases"]}
    eligible = set(workload["memory_seed"]["expected_state"]["eligible_current_memory_ids"])
    facts = {event["memory_id"]: event["canonical_text"] for event in workload["memory_seed"]["events"]
             if event["operation"] in {"remember", "correct"}}
    groups = {}
    mapping = defaultdict(list)
    for row in raw_rows:
        delivered = row["status"] == "ok"
        supplied, supplied_known, _ = supplied_evidence(row) if delivered else (set(), False, None)
        supplied_ids = sorted(supplied) if supplied_known else None
        identity = {"case_id": row["id"], "delivered": delivered,
                    "response": row.get("response") if delivered else None}
        if delivered:
            identity["supplied_memory_ids"] = supplied_ids
        review_id = "review_" + hmac.new(key, canonical_bytes(identity), "sha256").hexdigest()[:24]
        rubric = workload["rubrics"][row["id"]]
        cited = set(row["response"].get("memory_used", [])) if delivered else set()
        noncurrent_ids = ((supplied | cited) - eligible) | set(rubric["forbidden_memory_ids"])
        def current_facts(identifiers):
            return [{"memory_id": identifier, "text": facts[identifier]}
                    for identifier in sorted(set(identifiers) & eligible)]
        # Do not expose variant frequencies, arm counts, classifier decisions,
        # model names, sampling settings, timings, or other raw-run metadata.
        groups[review_id] = {
            "review_id": review_id, "prompt": cases[row["id"]]["prompt"],
            "rubric": {field: rubric[field] for field in (
                "mode", "reference_answer", "required_claims", "forbidden_claims",
                "required_memory_ids", "forbidden_memory_ids")},
            "required_gold_current_evidence": current_facts(rubric["required_memory_ids"]),
            "actually_supplied_memory_ids": supplied_ids,
            "actually_supplied_current_evidence": current_facts(supplied) if supplied_known else None,
            "cited_current_facts_not_supplied": current_facts(cited - supplied),
            "noncurrent_or_unknown_memory_ids": sorted(noncurrent_ids),
            "noncurrent_or_unknown_memory_ids_scope": "Reference-forbidden IDs plus actually supplied/cited IDs outside eligible current facts; presence in this list alone does not establish exposure.",
            "actual_noncurrent_supplied_or_cited_ids": sorted((supplied | cited) - eligible),
            "delivered_response": row.get("response") if delivered else None,
            "delivery_status": "delivered" if delivered else "technical_failure_no_validated_delivery",
            "review": {"reviewer_type": None, "reviewer_id": None, "judgment": None,
                       "unsupported_personal_claim": None, "forbidden_or_stale_claim": None,
                       "notes": None},
        }
        mapping[review_id].append({"arm": row["arm"], "repetition": row["repetition"],
                                   "case_id": row["id"], "index": row["index"], "status": row["status"]})
    return [groups[key] for key in sorted(groups)], [
        {"review_id": key, "observations": mapping[key]} for key in sorted(mapping)]


def review_coverage(planned, observed, reviewed, correct):
    if not 0 <= correct <= reviewed <= observed <= planned:
        raise ValueError("invalid semantic-review observation denominators")
    graded = observed > 0 and reviewed == observed
    return {
        "observed_attempts": observed, "pending_observed_reviews": observed - reviewed,
        "unattempted_planned_requests": planned - observed,
        "observed_correctness_rate": correct / observed if graded else None,
        "planned_attempt_coverage": observed / planned,
        "conservative_correct_deliveries_per_planned": correct / planned if graded else None,
        "review_status": ("not_attempted" if observed == 0 else "pending_observed_reviews" if not graded
                          else "fully_graded_complete_coverage" if observed == planned
                          else "fully_graded_observed_incomplete_coverage"),
    }


def apply_reviews(report, workload, worksheet, mapping, reviews):
    """Require explicit judgments for every variant; never infer semantic success."""
    entries = {entry["review_id"]: entry for entry in worksheet}
    accepted = defaultdict(list)
    success_modes = {"complete": "supported", "appropriate_abstention": "abstain",
                     "appropriate_uncertainty": "uncertain"}
    judgments = set(success_modes) | {"partial", "incorrect", "inappropriate_abstention", "technical_failure"}
    for raw in reviews:
        review_id = raw["review_id"]
        review = raw.get("review", raw)
        if review_id not in entries:
            raise ValueError(f"review ID is not in the selected raw-run worksheet: {review_id}")
        if review.get("judgment") not in judgments:
            raise ValueError(f"unknown or pending review judgment: {review_id}")
        if review.get("reviewer_type") not in {"assistant", "human"} or not review.get("reviewer_id"):
            raise ValueError("reviewer type and identity must be explicit")
        for field in ("unsupported_personal_claim", "forbidden_or_stale_claim"):
            if type(review.get(field)) is not bool:
                raise ValueError(f"review needs a boolean {field}")
        if not isinstance(review.get("notes"), str) or not review["notes"].strip():
            raise ValueError("review needs a brief claim-grounded explanation")
        entry = entries[review_id]
        delivered = entry["delivery_status"] == "delivered"
        judgment = review["judgment"]
        if (judgment == "technical_failure") == delivered:
            raise ValueError("technical-failure judgment must match non-delivery")
        if not delivered and (review["unsupported_personal_claim"] or review["forbidden_or_stale_claim"]):
            raise ValueError("non-delivered text cannot be labeled a delivered disclosure")
        if judgment in success_modes:
            if entry["rubric"]["mode"] != success_modes[judgment]:
                raise ValueError("successful judgment does not match the frozen rubric mode")
            if review["unsupported_personal_claim"] or review["forbidden_or_stale_claim"]:
                raise ValueError("a successful judgment cannot include unsupported or forbidden personal claims")
        accepted[review_id].append({key: review[key] for key in (
            "reviewer_type", "reviewer_id", "judgment", "unsupported_personal_claim", "forbidden_or_stale_claim", "notes")})
    resolved, conflicts = {}, []
    for review_id, opinions in accepted.items():
        signatures = {(opinion["judgment"], opinion["unsupported_personal_claim"], opinion["forbidden_or_stale_claim"])
                      for opinion in opinions}
        if len(signatures) != 1:
            conflicts.append(review_id)
        else:
            resolved[review_id] = opinions[0]
    observed_keys = [(observation["arm"], observation["repetition"], observation["case_id"])
                     for item in mapping for observation in item["observations"]]
    if len(observed_keys) != len(set(observed_keys)):
        raise ValueError("review mapping contains duplicate observations")
    case_scores = defaultdict(dict)
    for item in mapping:
        review = resolved.get(item["review_id"])
        if review is None:
            continue
        for observation in item["observations"]:
            case_scores[(observation["arm"], observation["case_id"])][observation["repetition"]] = review
    quality = {}
    for arm in ALLOWED:
        per_round = {}
        all_opinions = []
        for repetition in (1, 2, 3):
            opinions = [case_scores[(arm, case["id"])][repetition] for case in workload["execution_cases"]
                        if repetition in case_scores[(arm, case["id"])]]
            all_opinions.extend(opinions)
            correct = sum(opinion["judgment"] in success_modes for opinion in opinions)
            per_round[str(repetition)] = {
                "planned": 48, "reviewed": len(opinions), "pending_or_unattempted": 48 - len(opinions),
                "correct_reviewed": correct, "correctness_rate": correct / 48 if len(opinions) == 48 else None,
                **review_coverage(48, sum(key[0] == arm and key[1] == repetition for key in observed_keys),
                                  len(opinions), correct),
            }
        correct = sum(opinion["judgment"] in success_modes for opinion in all_opinions)
        by_stratum = {}
        for stratum in sorted({case["stratum"] for case in workload["execution_cases"]}):
            stratum_cases = [case for case in workload["execution_cases"] if case["stratum"] == stratum]
            opinions = [opinion for case in stratum_cases for opinion in case_scores[(arm, case["id"])].values()]
            planned = len(stratum_cases) * 3
            stratum_correct = sum(opinion["judgment"] in success_modes for opinion in opinions)
            by_stratum[stratum] = {
                "planned_attempts": planned, "reviewed_attempts": len(opinions),
                "correct_reviewed": stratum_correct,
                "correctness_rate": stratum_correct / planned if len(opinions) == planned else None,
                **review_coverage(planned, sum(key[0] == arm and key[2] in {case["id"] for case in stratum_cases}
                                              for key in observed_keys), len(opinions), stratum_correct),
            }
        quality[arm] = {
            "planned_attempts": 144, "reviewed_attempts": len(all_opinions),
            "pending_or_unattempted": 144 - len(all_opinions), "correct_reviewed": correct,
            "correctness_rate": correct / 144 if len(all_opinions) == 144 else None,
            **review_coverage(144, sum(key[0] == arm for key in observed_keys), len(all_opinions), correct),
            "by_repetition": per_round, "by_stratum": by_stratum,
            "judgments": dict(Counter(opinion["judgment"] for opinion in all_opinions)),
            "unsupported_personal_claim_attempts": sum(opinion["unsupported_personal_claim"] for opinion in all_opinions),
            "forbidden_or_stale_claim_attempts": sum(opinion["forbidden_or_stale_claim"] for opinion in all_opinions),
            "distinct_observed_cases": len({key[2] for key in observed_keys if key[0] == arm}),
            "quality_unit_note": "144 planned attempts across 48 planned distinct cases; observed counts may be smaller. Shared scenario/profile dependencies remain; no 144-independent-observation interval.",
        }
    paired = []
    for left, right in combinations(ALLOWED, 2):
        repetitions = {}
        for repetition in (1, 2, 3):
            counts = Counter()
            for case in workload["execution_cases"]:
                a, b = case_scores[(left, case["id"])].get(repetition), case_scores[(right, case["id"])].get(repetition)
                if a is None or b is None:
                    counts["pending_or_unattempted"] += 1
                    continue
                a_ok, b_ok = a["judgment"] in success_modes, b["judgment"] in success_modes
                counts["both_correct" if a_ok and b_ok else "left_only_correct" if a_ok
                       else "right_only_correct" if b_ok else "neither_correct"] += 1
            repetitions[str(repetition)] = dict(counts)
        paired.append({"left": left, "right": right, "by_repetition": repetitions,
                       "interpretation": "descriptive paired cases; repeated rounds are not independent quality samples"})
    reviewer_types = sorted({opinion["reviewer_type"] for opinions in accepted.values() for opinion in opinions})
    review_report = {
        "status": "complete_for_observed_unique_outputs" if len(resolved) == len(entries) else "pending_unique_output_reviews",
        "observed_unique_outputs": len(entries), "resolved_unique_outputs": len(resolved),
        "pending_unique_output_ids": sorted(set(entries) - set(resolved)), "conflicting_review_ids": sorted(conflicts),
        "reviewer_types": reviewer_types, "human_validation_complete": reviewer_types == ["human"] and len(resolved) == len(entries),
        "arms": quality, "paired_success_patterns": paired, "review_opinions": dict(accepted),
        "coverage_note": "Observed correctness uses only attempted requests after all their outputs are graded, including technical failures. It is not full-workload accuracy when requests are missing. Correct deliveries divided by all planned requests is a conservative demonstrated-coverage fraction; unattempted requests are not demonstrated successes. Unreviewed outputs remain pending.",
    }
    report["semantic_review"] = review_report
    report["semantic_review_status"] = review_report["status"] + "; reviewer types: " + ", ".join(reviewer_types)
    return review_report


def deadline_quality_curve(report, metrics, mapping):
    """Exact empirical step function; never publish partially reviewed curves."""
    result = {
        "status": "pending_complete_collection_and_semantic_review", "arms": None,
        "definition": "At deadline t, count validated, fully correct deliveries with request wall time <= t; divide by all 144 planned requests per arm.",
        "scope": "Descriptive only: 48 distinct requests repeated three times, with shared scenario/profile dependence; no selected acceptance cutoff or independent-sample interval.",
        "review_note": "Uses resolved final rubric judgments, including appropriate abstention/uncertainty in their matching modes. Assistant review is not independent human validation.",
    }
    review = report.get("semantic_review")
    if not (report.get("complete") and report.get("integrity_valid") and review
            and review["status"] == "complete_for_observed_unique_outputs"
            and not review["conflicting_review_ids"]
            and all(review["arms"][arm]["reviewed_attempts"] == 144 for arm in ALLOWED)):
        return result
    by_key = {(row["arm"], row["repetition"], row["case_id"]): row for row in metrics}
    if len(metrics) != 432 or len(by_key) != 432:
        raise ValueError("deadline curve requires 432 distinct planned observations")
    deadlines = sorted({0.0, *(row["wall_seconds"] for row in metrics)})
    if not all(nonnegative(value) for value in deadlines):
        raise ValueError("deadline curve requires finite nonnegative wall times")
    successes = defaultdict(list)
    seen = set()
    success_judgments = {"complete", "appropriate_abstention", "appropriate_uncertainty"}
    for entry in mapping:
        opinions = review["review_opinions"].get(entry["review_id"], [])
        signatures = {(opinion["judgment"], opinion["unsupported_personal_claim"],
                       opinion["forbidden_or_stale_claim"]) for opinion in opinions}
        if len(signatures) != 1:
            raise ValueError("deadline curve needs one resolved judgment for every mapped output")
        judgment, unsupported, forbidden = next(iter(signatures))
        correct = judgment in success_judgments and not unsupported and not forbidden
        for observation in entry["observations"]:
            key = (observation["arm"], observation["repetition"], observation["case_id"])
            if key not in by_key or key in seen:
                raise ValueError("deadline curve review mapping is duplicated or differs from observations")
            seen.add(key)
            row = by_key[key]
            if bool(row["delivered"]) != (observation["status"] == "ok"):
                raise ValueError("deadline curve delivery state differs from review mapping")
            if correct and row["delivered"]:
                successes[row["arm"]].append(row["wall_seconds"])
    if seen != set(by_key):
        raise ValueError("deadline curve review mapping omits planned observations")
    arms = {}
    for arm in ALLOWED:
        selected = [row for row in metrics if row["arm"] == arm]
        counts = Counter(row["repetition"] for row in selected)
        case_ids = {row["case_id"] for row in selected}
        if counts != {1: 48, 2: 48, 3: 48} or len(case_ids) != 48:
            raise ValueError("deadline curve requires all 48 items in each arm and repetition")
        times = sorted(successes[arm])
        arms[arm] = {"planned_denominator": 144, "correct_delivered": len(times),
                     "points": [{"deadline_seconds": time,
                                 "correct_delivered_count": bisect_right(times, time),
                                 "fraction_of_planned": bisect_right(times, time) / 144}
                                for time in deadlines]}
    result.update(status="complete_descriptive_curve", arms=arms,
                  max_observed_seconds=deadlines[-1], interpolation="right_continuous_step",
                  reviewer_types=review["reviewer_types"], human_validation_complete=review["human_validation_complete"])
    return result


def inspect_resume_origin(run_root, freeze_path, sessions, *, arm_orders=None):
    """Permit only declared whole-session reuse; never join attempted tails."""
    origin_path = run_root / "resume_origin.json"
    linked = [directory for directory, _, _ in session_slots(arm_orders) if (run_root / directory).is_symlink()]
    if not origin_path.is_file():
        return ({"valid": False, "errors": ["linked sessions lack resume_origin.json"],
                 "retained_complete_session_count": 0, "excluded_startup_rejections": []}
                if linked else None)
    errors = []
    result = {"valid": False, "errors": errors, "origin_sha256": file_hash(origin_path),
              "retained_complete_session_count": 0, "excluded_startup_rejections": []}
    try:
        origin = read_json(origin_path)
        result["origin"] = origin
        require(origin.get("schema_version") == 1, "unknown resume origin schema", errors)
        require(origin.get("freeze_sha256") == file_hash(freeze_path), "resume freeze digest differs", errors)
        require(origin.get("scheduler_handoff_temperature_c_exclusive") == 54
                and origin.get("unchanged_arm_start_temperature_c_exclusive") == 55,
                "resume scheduler/arm temperature policy differs", errors)
        launcher_archive = run_root / "resume_launcher.py"
        launcher = launcher_archive if launcher_archive.is_file() else Path(__file__).with_name("resume_complete_system_batch.py")
        require(file_hash(launcher) == origin.get("resume_script_sha256"), "resume launcher digest differs", errors)
        result["launcher_verification_source"] = str(launcher)
        result["launcher_archived"] = launcher_archive.is_file()
        prior = Path(origin["prior_root"])
        require(file_hash(prior / "batch_finish.json") == origin.get("prior_batch_finish_sha256"),
                "prior batch finish digest differs", errors)
        require(file_hash(prior / "before.json") == file_hash(run_root / "before.json"),
                "resumed root changed the original batch before-state", errors)
        retained = origin["retained_complete_sessions"]
        names = [entry["directory"] for entry in retained]
        expected_prefix = [slot[0] for slot in session_slots(arm_orders)[:len(retained)]]
        require(0 < len(retained) < 9 and names == expected_prefix,
                "retained sessions are not a nonempty complete prefix", errors)
        require(sorted(linked) == sorted(names), "linked sessions differ from the declared retained prefix", errors)
        by_name = {session["directory"]: session for session in sessions}
        for entry in retained:
            directory = entry["directory"]
            source = Path(entry["source"])
            link = run_root / directory
            require(source.resolve() == (prior / directory).resolve() == link.resolve(),
                    "retained session link points to a different source", errors)
            require(file_hash(link / "observations.jsonl") == entry["observations_sha256"],
                    "retained observations digest differs", errors)
            require(file_hash(link / "finish.json") == entry["finish_sha256"], "retained finish digest differs", errors)
            require(by_name[directory]["complete"] and by_name[directory]["attempted"] == 48,
                    "retained session was not already a complete 48-item session", errors)
        result["retained_complete_session_count"] = len(retained)
        rejected = [Path(origin["prior_startup_rejection"])]
        local_rejections = run_root / "startup_rejections"
        if local_rejections.is_dir():
            rejected.extend(sorted(path for path in local_rejections.iterdir() if path.is_dir()))
        for path in rejected:
            summary, finish = read_json(path / "summary.json"), read_json(path / "finish.json")
            observations = path / "observations.jsonl"
            require(summary.get("attempted") == 0 and not (path / "manifest.json").exists()
                    and (not observations.exists() or observations.stat().st_size == 0),
                    "an excluded startup rejection contains attempted inference", errors)
            require((finish.get("failure") or {}).get("message") == "Stage 2 startup temperature must be below 55 C",
                    "excluded startup failure was not the declared temperature handoff rejection", errors)
            require(finish.get("resident_models") == [] and finish.get("cleanup_errors") == [],
                    "excluded startup rejection has unresolved cleanup", errors)
            result["excluded_startup_rejections"].append({
                "path": str(path), "attempted_requests": summary.get("attempted"),
                "summary_sha256": file_hash(path / "summary.json"), "finish_sha256": file_hash(path / "finish.json"),
                "failure": finish.get("failure"),
            })
        result["note"] = (
            "A complete session is retained unchanged after a later zero-request startup rejection. "
            "Only unattempted sessions were subsequently run; no request tail was joined and no completed answer was retried. "
            "The scheduler waits below 54 C; each arm still enforces its original below-55 C startup gate."
        )
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        errors.append(f"resume provenance validation failed: {type(error).__name__}: {error}")
    result["valid"] = not errors
    return result


def inspect_schedule_continuation(run_root, freeze_path, sessions, baseline, *, arm_orders=None):
    """Audit unchanged terminal prefixes and newly attempted independent slots."""
    origin_path = run_root / "schedule_continuation_origin.json"
    if not origin_path.is_file():
        terminal_failure_seen = False
        for session in sessions:
            if terminal_failure_seen and session["status"] != "missing":
                return {"valid": False, "errors": ["later sessions follow a terminal failure without continuation provenance"],
                        "schedule_terminal": False}
            terminal_failure_seen |= session["status"] == "interrupted"
        return None
    errors = []
    result = {"valid": False, "errors": errors, "schedule_terminal": False,
              "orchestration_finished": False, "status": "in_progress",
              "unattempted_slots": [{"directory": session["directory"], "arm": session["arm"],
                                     "repetition": session["repetition"]}
                                    for session in sessions if session["status"] == "missing"],
              "origin_sha256": file_hash(origin_path), "resource_interrupted_sessions": []}
    allowed = {"available memory crossed the runtime floor", "telemetry RAM floor crossed"}
    try:
        origin = read_json(origin_path)
        result["origin"] = origin
        require(origin.get("schema_version") == 1, "unknown continuation schema", errors)
        require(origin.get("freeze_sha256") == file_hash(freeze_path), "continuation freeze differs", errors)
        require(file_hash(run_root / "continued_schedule_launcher.py") == origin.get("launcher_sha256"),
                "archived continuation launcher digest differs", errors)
        require(origin.get("dependency_sha256") == {
            "resume_complete_system_batch.py": file_hash(run_root / "resume_launcher.py")},
            "archived scheduler dependency differs", errors)
        require(file_hash(run_root / "batch_finish.json") == origin.get("prior_batch_finish_sha256"),
                "original interrupted batch finish changed", errors)
        require(set(origin.get("recoverable_failure_messages", [])) == allowed,
                "continued resource-failure policy differs", errors)
        require(origin.get("scheduler_handoff_temperature_c_exclusive") == 54
                and origin.get("unchanged_arm_start_temperature_c_exclusive") == 55,
                "continued scheduler/arm startup gates differ", errors)
        retained = origin["retained_terminal_sessions"]
        slots = session_slots(arm_orders)
        require(0 < len(retained) < 9, "continuation needs a nonempty terminal prefix", errors)
        require(origin["remaining_slots"] == [
            {"index": index, "arm": arm, "repetition": repetition}
            for index, (_, arm, repetition) in enumerate(slots, 1) if index > len(retained)],
            "remaining independent slots differ from original counterbalance", errors)
        progress_path = run_root / "continued_schedule_progress.jsonl"
        progress = read_jsonl(progress_path) if progress_path.is_file() else []
        items = retained + progress
        require(len(items) <= 9, "continuation repeats planned sessions", errors)
        by_name = {session["directory"]: session for session in sessions}
        for index, item in enumerate(items):
            directory, arm, repetition = slots[index]
            require((item["directory"], item["arm"], item["repetition"]) == (directory, arm, repetition),
                    "continued terminal ledger is not the original ordered prefix", errors)
            session = by_name[directory]
            path = run_root / directory
            require(item["status"] == session["status"] and item["attempted"] == session["attempted"]
                    and item["planned"] == 48 and item["unattempted"] == 48 - session["attempted"],
                    f"terminal session counters differ: {directory}", errors)
            expected_files = item["artifact_sha256"]
            require(set(expected_files) == {p.name for p in path.iterdir() if p.is_file()},
                    f"terminal artifact set changed: {directory}", errors)
            for name, digest in expected_files.items():
                require(Path(name).name == name and name not in {".", ".."}, "invalid terminal artifact name", errors)
                if Path(name).name == name and name not in {".", ".."}:
                    require(file_hash(path / name) == digest, f"terminal artifact changed: {directory}/{name}", errors)
            finish = session["finish"]
            require(all(finish.get(key) == baseline[key] for key in ("boot_id", "power_mode", "thermal_trip_events")),
                    f"terminal device continuity differs: {directory}", errors)
            require(finish.get("resident_models") == [] and finish.get("cleanup_errors") == []
                    and finish.get("telemetry_reader_error") is None,
                    f"terminal cleanup/telemetry unresolved: {directory}", errors)
            if not session["complete"]:
                failure = finish.get("failure") or {}
                rows = read_jsonl(path / "observations.jsonl")
                require(session["status"] == "interrupted" and failure.get("type") == "SafetyGateError"
                        and failure.get("message") in allowed and finish.get("guard_violation") in allowed,
                        f"retained failure is outside the declared RAM policy: {directory}", errors)
                require(bool(rows) and rows[-1]["status"] == "interrupted"
                        and all(row["status"] in {"ok", "error"} for row in rows[:-1]),
                        f"terminal partial request prefix differs: {directory}", errors)
                result["resource_interrupted_sessions"].append({
                    "directory": directory, "attempted": session["attempted"],
                    "unattempted": 48 - session["attempted"], "failure": failure,
                })
        result.update(retained_terminal_session_count=len(retained),
                      newly_recorded_terminal_session_count=len(progress))
        finish_path = run_root / "continued_schedule_finish.json"
        if finish_path.is_file():
            finish = read_json(finish_path)
            result["finish"] = finish
            result["orchestration_finished"] = True
            result["status"] = finish["status"]
            result["unattempted_slot_reason"] = (finish.get("failure") or {}).get("message")
            result["finish_sha256"] = file_hash(finish_path)
            require(finish.get("sessions") == items, "continued finish differs from immutable terminal ledger", errors)
            snapshot = finish["snapshot"]
            require(all(snapshot.get(key) == baseline[key] for key in ("boot_id", "power_mode", "thermal_trip_events")),
                    "continued schedule final device continuity differs", errors)
            require(snapshot.get("resident_models") == [] and type(snapshot.get("fan_pwm")) is int
                    and snapshot["fan_pwm"] > 0, "continued schedule final residency/fan unresolved", errors)
            if finish["status"] in {"complete", "complete_schedule_with_session_failures"}:
                require(len(items) == 9 and finish.get("failure") is None, "completed schedule lacks nine terminal sessions", errors)
                require((finish["status"] == "complete_schedule_with_session_failures")
                        == bool(result["resource_interrupted_sessions"]),
                        "schedule status hides or invents a resource interruption", errors)
                result["schedule_terminal"] = len(items) == 9
        result["note"] = (
            "Independent preplanned sessions continue after retained RAM-floor interruptions under the same frozen arm guards. "
            "Interrupted requests and unattempted tails remain in their original sessions; no failed answer or missing tail is retried. "
            "A terminal nine-session schedule does not imply complete 432-request coverage or device feasibility."
        )
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError) as error:
        errors.append(f"continuation provenance validation failed: {type(error).__name__}: {error}")
    result["valid"] = not errors
    return result


def analyze(workload_path, freeze_path, run_root, *, comparison_profile=None, arm_orders=None):
    workload, frozen = read_json(workload_path), read_json(freeze_path)
    if comparison_profile is not None:
        from analyze_post_memory_comparison import PROFILE_ID, frozen_arm_orders, validate_freeze_contract
        if comparison_profile != PROFILE_ID:
            raise ValueError("unsupported explicit comparison profile")
        validate_freeze_contract(frozen)
        declared_orders = frozen_arm_orders(frozen)
        if arm_orders is not None and tuple(tuple(row) for row in arm_orders) != declared_orders:
            raise ValueError("explicit arm order differs from the frozen counterbalance")
        arm_orders = declared_orders
    elif frozen.get("profile_id") == "post_memory_comparison_v1":
        raise ValueError("post-memory artifacts require their explicit comparison profile")
    cases = validate_workload(workload)
    if file_hash(workload_path) != frozen["workload_sha256"]:
        raise ValueError("workload does not match the supplied freeze")
    orders = ARM_ORDERS if arm_orders is None else arm_orders
    slots = session_slots(orders)
    sessions, raw_rows, errors = [], [], []
    for directory, arm, repetition in slots:
        session, rows = inspect_session(run_root, directory, arm, repetition, workload, frozen,
                                        comparison_profile=comparison_profile)
        sessions.append(session)
        raw_rows.extend(rows)
    expected_dirs = {slot[0] for slot in slots}
    unexpected = [path.name for path in run_root.iterdir()
                  if path.is_dir() and (path / "manifest.json").is_file() and path.name not in expected_dirs]
    require(not unexpected, f"unexpected session directories: {unexpected}", errors)
    keys = [(row.get("arm"), row.get("repetition"), row.get("id")) for row in raw_rows]
    require(len(keys) == len(set(keys)), "duplicate arm/repetition/case observations", errors)
    snapshots = {session.get("memory_snapshot_sha256") for session in sessions if session.get("memory_snapshot_sha256")}
    require(len(snapshots) <= 1, "memory snapshots differ across sessions", errors)
    memory_scopes = [session["memory_execution_scope"] for session in sessions if "memory_execution_scope" in session]
    scope_signatures = {canonical_bytes({key: scope[key] for key in (
        "profile_id", "retention_days", "evaluation_at", "snapshot_profile_ids")}) for scope in memory_scopes}
    require(len(scope_signatures) <= 1, "synthetic memory execution scopes differ across sessions", errors)
    manifests = [session["manifest"] for session in sessions if "manifest" in session]
    if manifests:
        reference = {key: value for key, value in manifests[0]["config"].items() if key != "ollama"}
        require(all({key: value for key, value in manifest["config"].items() if key != "ollama"} == reference
                    for manifest in manifests), "shared configuration differs across sessions", errors)
        require(all(manifest["device_policy"] == manifests[0]["device_policy"] for manifest in manifests),
                "device policy differs across sessions", errors)
    boots = {session["start"].get("boot_id") for session in sessions if "start" in session}
    require(len(boots) <= 1, "boot differs across sessions", errors)
    before = read_json(run_root / "before.json") if (run_root / "before.json").is_file() else None
    if before is not None:
        require(before.get("resident_models") == [], "batch did not begin with no resident model", errors)
        require(not boots or before.get("boot_id") in boots, "batch initial boot differs", errors)
    batch = read_json(run_root / "batch_finish.json") if (run_root / "batch_finish.json").is_file() else None
    if batch is not None:
        require(batch["snapshot"].get("resident_models") == [], "batch cleanup left a model resident", errors)
        require(not boots or batch["snapshot"].get("boot_id") in boots, "batch final boot differs", errors)
        if before is not None:
            require(batch["snapshot"].get("power_mode") == before.get("power_mode"), "batch final power mode differs", errors)
            require(batch["snapshot"].get("thermal_trip_events") == before.get("thermal_trip_events"),
                    "batch thermal trip counters differ", errors)
        expected_order = [(arm, repetition) for _, arm, repetition in slots]
        actual_order = [(session["arm"], session["repetition"]) for session in batch["sessions"]]
        require(actual_order == expected_order[:len(actual_order)], "batch order differs from counterbalance", errors)
    resume = inspect_resume_origin(run_root, freeze_path, sessions, arm_orders=orders)
    if resume is not None:
        errors.extend(f"resume: {error}" for error in resume["errors"])
    continuation = inspect_schedule_continuation(run_root, freeze_path, sessions, before, arm_orders=orders)
    if continuation is not None:
        errors.extend(f"schedule continuation: {error}" for error in continuation["errors"])
    all_valid = not errors and all(session["valid"] for session in sessions if session["status"] != "missing")
    complete = all_valid and all(session["complete"] for session in sessions) and len(raw_rows) == 432
    metrics = []
    metric_rows = []
    for index, row in enumerate(raw_rows):
        try:
            metrics.append(row_metrics(row, workload["rubrics"][row["id"]]))
            metric_rows.append(row)
        except (KeyError, TypeError, ValueError) as error:
            errors.append(f"raw observation {index + 1} cannot be summarized: {error}")
            all_valid, complete = False, False
    report = {
        "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "workload_sha256": file_hash(workload_path), "freeze_sha256": file_hash(freeze_path),
        "analyzer_sha256": file_hash(Path(__file__)), "run_root": str(run_root.resolve()),
        "analyzer_utility_sha256": file_hash(Path(__file__).with_name("analyze_arc_capability.py")),
        "raw_selection": "Only the explicitly selected run root, including declared complete-session links; diagnostic requests and incomplete session tails are never merged.",
        "integrity_valid": all_valid, "complete": complete, "incomplete": not complete,
        "integrity_errors": errors, "planned_sessions": 9, "planned_attempts": 432,
        "counterbalanced_arm_orders": [list(row) for row in orders],
        "observed_attempts": len(raw_rows), "distinct_request_items": 48,
        "distinct_scenarios": len({case["scenario_id"] for case in cases}),
        "quality_sample_note": "The design plans three deterministic repetitions; achieved coverage is reported separately. Repetitions are not additional independent quality samples, and scenario/shared-profile dependencies remain.",
        "semantic_review_status": "pending_blinded_review; no semantic quality estimate yet",
        "sessions": sessions,
        "arms": {arm: aggregate_metrics([row for row in metrics if row["arm"] == arm], 144) for arm in ALLOWED},
        "by_stratum": {arm: {stratum: aggregate_metrics(
            [row for row in metrics if row["arm"] == arm and row["stratum"] == stratum],
            3 * sum(case["stratum"] == stratum for case in cases))
            for stratum in sorted({case["stratum"] for case in cases})} for arm in ALLOWED},
        "per_case_variability": variability(cases, metric_rows),
        "paired_latency": paired_latency(cases, metrics),
        "timing_note": "Ollama load/prefill/decode are contained in call wall time; do not add them again. Cold first requests and setup are reported separately.",
        "batch_finish": batch,
        "resume_provenance": resume,
        "schedule_continuation_provenance": continuation,
        "memory_execution": {
            "profile_id": workload["memory_seed"]["profile_id"],
            "retention_days": workload["memory_seed"].get("retention_days", 7),
            "evaluation_at": workload["memory_seed"]["evaluation_at"],
            "database_path_pattern": "<session-directory>/memory.sqlite3",
            "observed_setup_sessions": len(memory_scopes),
            "observed_scope_equivalence": len(scope_signatures) == 1 if memory_scopes else None,
            "note": "The manifest config records loaded application defaults with model-role overrides. The frozen runner explicitly constructs a separate MemoryStore in each session using the synthetic workload profile, retention period, and fixed evaluation clock. The application's configured personal-memory database/profile is not used. Saved snapshots verify the observed profiles and equality across sessions; the analyzer does not open the databases.",
        },
    }
    if comparison_profile is not None:
        from analyze_post_memory_comparison import decorate_report
        decorate_report(report, raw_rows)
    return report, workload, metric_rows, metrics


def number(value):
    return "—" if value is None else f"{value:.3f}"


def render_markdown(report):
    lines = ["# " + report.get("report_title", "Stage 2 complete text-system pilot"), "",
             f"Collection: {'complete' if report['complete'] else 'incomplete'}; "
             f"{report['observed_attempts']}/{report['planned_attempts']} planned attempts. "
             f"Artifact integrity: {'valid for observed sessions' if report['integrity_valid'] else 'validation failures present'}.", "",
             report["semantic_review_status"] + ". Regex signals and delivery validity are not answer-quality scores.", "",
             "| System | Attempts | Validated deliveries | Median all (s) | p95 all (s) | Median delivered (s) | Median failed (s) |", 
             "|---|---:|---:|---:|---:|---:|---:|"]
    for arm, value in report["arms"].items():
        lines.append(f"| {arm} | {value['attempted']}/{value['planned']} | {value['delivered']} | "
                     f"{number(value['latency_all_seconds']['p50'])} | {number(value['latency_all_seconds']['p95'])} | "
                     f"{number(value['latency_delivered_seconds']['p50'])} | "
                     f"{number(value.get('latency_failed_seconds', {}).get('p50'))} |")
    lines += ["", "| Session | Status | Deliveries | First request (s) | Setup (s) | Peak RAM / swap (MiB) |", 
              "|---|---|---:|---:|---:|---:|"]
    for session in report["sessions"]:
        telemetry = session.get("telemetry", {})
        first = session.get("first_request_seconds")
        lines.append(f"| {session['directory']} | {session['status']} | {session['delivered']}/{session['planned']} | "
                     f"{number(first)} | {number(session.get('memory_setup_seconds'))} | "
                     f"{telemetry.get('peak_ram_used_mb', '—')} / {telemetry.get('peak_swap_used_mb', '—')} |")
    lines += ["", "| System | Calls by actual generator | Helper constraints | Retrieval requests | Missing lexical signals | Forbidden presence signals |",
              "|---|---|---:|---:|---:|---:|"]
    for arm, value in report["arms"].items():
        helpers = sum(count for name, count in value["answer_constraints"].items() if name != "none")
        lines.append(f"| {arm} | {json.dumps(value['generation_models'], sort_keys=True)} | {helpers} | "
                     f"{value['retrieval_requests']} | {value['delivered_with_lexical_missing_signals']} | "
                     f"{value['delivered_with_forbidden_presence_signals']} |")
    if "semantic_review" in report:
        review = report["semantic_review"]
        lines += ["", f"Semantic review: {review['resolved_unique_outputs']}/{review['observed_unique_outputs']} unique outputs resolved; "
                  f"reviewer types: {', '.join(review['reviewer_types']) or 'none'}. Assistant review is not independent human validation.",
                  "", "| System | Correct / observed | Reviewed / planned | Round 1 | Round 2 | Round 3 |",
                  "|---|---:|---:|---:|---:|---:|"]
        for arm, value in review["arms"].items():
            observed_score = (f"{value['correct_reviewed']}/{value['observed_attempts']}" if value["observed_correctness_rate"] is not None else "pending")
            rounds = [(f"{group['correct_reviewed']}/{group['observed_attempts']} observed" if group["observed_correctness_rate"] is not None
                       else f"{group['reviewed']}/{group['observed_attempts']} reviewed")
                      + f"; {group['observed_attempts']}/48 attempted" for group in value["by_repetition"].values()]
            lines.append(f"| {arm} | {observed_score} | {value['reviewed_attempts']}/144 | " + " | ".join(rounds) + " |")
        lines += ["", review["coverage_note"]]
    curve = report.get("deadline_quality_curve")
    if curve is not None:
        if curve["status"] == "complete_descriptive_curve":
            lines += ["", "The empirical correct-by-deadline curve is available in deadline_quality_curve.json and deadline_quality_curve.csv. "
                      "It uses the complete request wall time, has a denominator of 144 planned attempts per arm, and retains failed requests in that denominator. "
                      "The right-continuous steps describe every deadline from zero through the largest observed latency; no acceptance deadline was selected."]
        else:
            lines += ["", "The correct-by-deadline curve is withheld until collection and semantic review are complete."]
    lines += ["", "Lexical presence can match a negated statement; valid paraphrases can miss a pattern. Empty check lists do not establish correctness. Failed requests cannot count as correct abstentions.",
              "", report["quality_sample_note"], "", report["timing_note"],
              "", "Energy and resource peaks include background activity. Whole-interval telemetry includes setup and cleanup; request-window energy uses only intervals covered by samples.",
              "", "The blinded worksheet hides explicit system identity, timing, repetition, and variant frequency. Response wording can still suggest system identity. Human review is pending."]
    if "memory_execution" in report:
        memory_scope = report["memory_execution"]
        lines += ["", memory_scope["note"],
                  f"Actual synthetic profile: {memory_scope['profile_id']}; retention: {memory_scope['retention_days']} days; "
                  f"evaluation clock: {memory_scope['evaluation_at']}; database: {memory_scope['database_path_pattern']}."]
    if report.get("resume_provenance") is not None:
        origin = report["resume_provenance"]
        lines += ["", origin.get("note", "Resume provenance validation failed."),
                  f"Retained complete sessions: {origin['retained_complete_session_count']}; "
                  f"excluded startup-only rejections: {len(origin['excluded_startup_rejections'])}."]
    if report.get("schedule_continuation_provenance") is not None:
        continued = report["schedule_continuation_provenance"]
        lines += ["", continued.get("note", "Independent-session continuation provenance failed validation.")]
        for item in continued.get("resource_interrupted_sessions", []):
            lines.append(f"Retained resource interruption: {item['directory']}, {item['attempted']}/48 attempted, "
                         f"{item['unattempted']} unattempted; {item['failure']['message']}.")
        if continued.get("orchestration_finished") and continued.get("unattempted_slots"):
            lines += ["The scheduler ended with unattempted sessions: "
                      + ", ".join(item["directory"] for item in continued["unattempted_slots"])
                      + ". Recorded reason: " + str(continued.get("unattempted_slot_reason")) + "."]
    if report["integrity_errors"] or any(session["errors"] for session in report["sessions"]):
        lines += ["", "Artifact validation findings:"]
        lines += [f"- {error}" for error in report["integrity_errors"]]
        lines += [f"- {session['directory']}: {error}" for session in report["sessions"] for error in session["errors"]]
    return "\n".join(lines) + "\n"


def write_new(path, value, *, lines=False):
    with path.open("xb") as stream:
        if lines:
            for item in value:
                stream.write(canonical_bytes(item))
        else:
            stream.write(canonical_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None, *, comparison_profile=None, arm_orders=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", required=True, type=Path)
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--blind-seed", help="Optional reproducible private 32-byte hexadecimal seed")
    parser.add_argument("--blind-seed-from", type=Path, help="Reuse private seed from an earlier review_manifest.json")
    parser.add_argument("--reviews", action="append", default=[], type=Path,
                        help="Reviewed JSONL; repeat for separately graded strata")
    args = parser.parse_args(argv)
    report, workload, raw_rows, metrics = analyze(args.workload, args.freeze, args.run_root,
                                                comparison_profile=comparison_profile, arm_orders=arm_orders)
    if args.blind_seed and args.blind_seed_from:
        parser.error("choose --blind-seed or --blind-seed-from")
    seed = args.blind_seed or (read_json(args.blind_seed_from)["private_blinding_seed"]
                              if args.blind_seed_from else secrets.token_hex(32))
    worksheet, mapping = make_blinded_review(workload, raw_rows, seed)
    review_report = None
    if args.reviews:
        reviews = [review for path in args.reviews for review in read_jsonl(path)]
        review_report = apply_reviews(report, workload, worksheet, mapping, reviews)
        report["semantic_review_input_sha256"] = {str(path): file_hash(path) for path in args.reviews}
    curve = deadline_quality_curve(report, metrics, mapping)
    report["deadline_quality_curve"] = curve
    os.umask(0o077)
    args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    write_new(args.output_dir / "analysis.json", report)
    write_new(args.output_dir / "row_metrics.jsonl", metrics, lines=True)
    write_new(args.output_dir / "blinded_review.jsonl", worksheet, lines=True)
    write_new(args.output_dir / "blinded_mapping.jsonl", mapping, lines=True)
    if review_report is not None:
        write_new(args.output_dir / "semantic_review.json", review_report)
    if curve["status"] == "complete_descriptive_curve":
        write_new(args.output_dir / "deadline_quality_curve.json", curve)
        with (args.output_dir / "deadline_quality_curve.csv").open("x", encoding="utf-8") as stream:
            stream.write("arm,deadline_seconds,correct_delivered_count,planned_denominator,fraction_of_planned\n")
            for arm, values in curve["arms"].items():
                for point in values["points"]:
                    stream.write(f"{arm},{point['deadline_seconds']},{point['correct_delivered_count']},144,{point['fraction_of_planned']}\n")
            stream.flush()
            os.fsync(stream.fileno())
    write_new(args.output_dir / "review_manifest.json", {
        "status": review_report["status"] if review_report else "pending_semantic_review", "unique_review_entries": len(worksheet),
        "mapped_raw_observations": len(raw_rows), "private_blinding_seed": seed,
        "blinded_worksheet_sha256": file_hash(args.output_dir / "blinded_review.jsonl"),
        "mapping_sha256": file_hash(args.output_dir / "blinded_mapping.jsonl"),
        "grouping_version": 2,
        "grouping": "identical case, delivered response, and exact supplied-memory ID set (unknown distinct from empty); technical non-deliveries grouped per case; no frequencies shown to reviewer",
        "reviewer_warning": "Keep the mapping and seed away from blinded raters. Record reviewer type and disagreements; assistant review is not independent human validation.",
        "submission_fields": ["review_id", "reviewer_type", "reviewer_id", "judgment",
                              "unsupported_personal_claim", "forbidden_or_stale_claim", "notes"],
    })
    with (args.output_dir / "report.md").open("x", encoding="utf-8") as stream:
        stream.write(render_markdown(report))
    print(json.dumps({"complete": report["complete"], "integrity_valid": report["integrity_valid"],
                      "observed_attempts": report["observed_attempts"], "review_entries": len(worksheet),
                      "output_dir": str(args.output_dir.resolve())}), flush=True)
    return 0 if report["integrity_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
