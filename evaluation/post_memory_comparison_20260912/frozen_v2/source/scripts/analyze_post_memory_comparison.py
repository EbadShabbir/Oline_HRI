"""Offline analysis for the explicitly frozen post-memory comparison profile.

The original Stage 2 analyzer keeps its original default routing contract.
This entry point explicitly selects the optimized fixed-memory/lightweight
contract while reusing its artifact, timing, partial-run and blinded-review
machinery. No inference, database access or mutation of raw artifacts occurs.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re

import analyze_complete_system as base


PROFILE_ID = "post_memory_comparison_v1"
POLICY_SOURCES = {"policy_privacy", "policy_personal", "policy_general"}
EXECUTION_POLICY = {
    "memory_policy": "policy_first_shared", "fixed_router_policy": "fixed_memory_v1",
    "adaptive_router_policy": "lightweight_v1", "fresh_history_each_request": True,
    "persistent_router_state": True, "retain_large_model": True,
    "automatic_memory_capture": False, "generation_seed": 42,
    "small_streak_before_switch": 2,
}
SOURCE_REQUIREMENTS = {
    "scripts/run_post_memory_comparison.py", "src/oline_hri/routing.py",
    "src/oline_hri/lightweight_routing.py", "src/oline_hri/conversation.py",
    "src/oline_hri/evaluation_systems.py", "src/oline_hri/ollama.py",
    "src/oline_hri/memory_evidence.py", "src/oline_hri/grounded_composition.py",
}


def execution_policy(arm):
    fixed = None if arm == "cascade" else base.SMALL if arm == "small" else base.LARGE
    return {**EXECUTION_POLICY, "router_policy": "lightweight_v1" if fixed is None else "fixed_memory_v1",
            "fixed_generator_model": fixed,
            "allowed_models": [base.SMALL, base.LARGE] if fixed is None else [fixed]}


def frozen_arm_orders(frozen):
    """Read the immutable three-period Latin square without changing defaults."""
    orders = frozen.get("counterbalanced_arm_orders")
    arms = set(base.ALLOWED)
    if (not isinstance(orders, (list, tuple)) or len(orders) != 3
            or any(not isinstance(row, (list, tuple)) or len(row) != 3
                   or any(not isinstance(arm, str) for arm in row)
                   or set(row) != arms for row in orders)
            or any({orders[row][column] for row in range(3)} != arms
                   for column in range(3))):
        raise ValueError("freeze must declare a balanced three-by-three arm counterbalance")
    return tuple(tuple(row) for row in orders)


def validate_freeze_contract(frozen):
    if frozen.get("profile_id") != PROFILE_ID:
        raise ValueError("freeze does not declare the post-memory comparison profile")
    if frozen.get("execution_policies") != {arm: execution_policy(arm) for arm in base.ALLOWED}:
        raise ValueError("freeze does not declare the exact post-memory execution policy")
    frozen_arm_orders(frozen)
    sources = frozen.get("source_sha256")
    if (not isinstance(sources, dict) or not SOURCE_REQUIREMENTS.issubset(sources)
            or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                   for value in sources.values())):
        raise ValueError("freeze lacks the post-memory source provenance")


def _resident_names(values, label, allowed, errors):
    if not isinstance(values, list):
        errors.append(f"{label} resident snapshot is absent")
        return []
    names = [value.get("name", value.get("model")) if isinstance(value, dict) else None
             for value in values]
    base.require(len(names) <= 1 and all(name in allowed for name in names),
                 f"{label} has unexpected or simultaneous resident models", errors)
    return names


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate classifier JSON field")
        result[key] = value
    return result


def validate_route_contract(record, arm):
    """Audit real calls and route provenance, including failed observations."""
    errors = []
    base.require(record.get("profile_id") == PROFILE_ID,
                 "row does not declare the post-memory comparison profile", errors)
    calls = record.get("calls")
    if not isinstance(calls, list):
        return ["post-memory calls must be a list"]
    selectors = [call for call in calls if call.get("purpose") == "memory_selector"]
    generators = [call for call in calls if call.get("purpose") == "generation"]
    base.require(len(selectors) <= 1, "post-memory made more than one memory classification", errors)
    base.require(not any(call.get("purpose") == "compute_selector" for call in calls),
                 "post-memory made a compute-classifier call", errors)
    # The original common validator checks requested and returned model tags,
    # duration metadata, seed, statuses, and fixed-generation constraints.
    for call in calls:
        fields = (call.get("response_format") or {}).get("properties", {})
        expected = "generation" if "speech" in fields else "memory_selector" if "memory_required" in fields else None
        base.require(call.get("purpose") == expected,
                     "call purpose differs from its actual response schema", errors)
    for field in ("resident_hint_before", "resident_hint_after"):
        base.require(field in record and (record[field] is None or record[field] in base.ALLOWED[arm]),
                     f"{field} is missing or outside this arm", errors)
    base.require(record.get("post_snapshot_attempted") is True,
                 "post-request residency snapshot was not explicitly attempted", errors)
    for field in ("api_ps_before", "api_ps_after"):
        snapshot_error = record.get("post_snapshot_error")
        if (field == "api_ps_after" and field in record and record[field] is None
                and record.get("status") == "interrupted"
                and record.get("post_snapshot_attempted") is True
                and isinstance(snapshot_error, dict)
                and isinstance(snapshot_error.get("error"), str) and snapshot_error["error"]
                and isinstance(snapshot_error.get("message"), str) and snapshot_error["message"]):
            # The post-request /api/ps can fail independently of the guard.
            # Preserve the interruption and report absent coverage, never invent a
            # successful residency observation. Final cleanup is still audited.
            continue
        _resident_names(record.get(field), field, base.ALLOWED[arm], errors)
    route = record.get("route")
    if route is None:
        base.require(record.get("status") != "ok", "delivered request lacks route provenance", errors)
        return errors
    if not isinstance(route, dict):
        return errors + ["route provenance is malformed"]
    decision = route.get("decision", {})
    base.require(type(decision.get("memory_required")) is bool
                 and decision.get("model_size") in {"small", "large"},
                 "route decision is malformed", errors)
    base.require(route.get("model_size_generation") is None,
                 "post-memory recorded a compute-classifier generation", errors)
    memory_source = route.get("memory_decision_source")
    memory_generation = route.get("memory_required_generation")
    if memory_source in POLICY_SOURCES:
        base.require(not selectors and memory_generation is None,
                     "deterministic memory policy fabricated or performed a classifier call", errors)
        expected = memory_source in {"policy_personal", "policy_privacy"}
        base.require(decision.get("memory_required") is expected,
                     "deterministic memory decision disagrees with policy source", errors)
    else:
        expected_source = "resident_model" if arm == "cascade" else "fixed_model"
        base.require(memory_source == expected_source,
                     "unrecognized post-memory classifier decision source", errors)
        base.require(len(selectors) == 1 and isinstance(memory_generation, dict),
                     "classifier route lacks exactly one real memory generation", errors)
        if len(selectors) == 1 and isinstance(memory_generation, dict):
            call = selectors[0]
            base.require(call.get("status") == "ok" and call.get("generation") == memory_generation,
                         "route classifier metadata differs from the actual successful call", errors)
            base.require(memory_generation.get("done_reason") == "stop",
                         "route accepted incomplete classifier output", errors)
            try:
                parsed = json.loads(memory_generation["content"], object_pairs_hook=_unique_json_object)
            except (KeyError, TypeError, ValueError):
                parsed = None
            base.require(isinstance(parsed, dict) and set(parsed) == {"form", "memory_required"}
                         and type(parsed["form"]) is str and parsed["form"] in {"question", "statement", "request"}
                         and type(parsed["memory_required"]) is bool
                         and parsed["memory_required"] is decision.get("memory_required"),
                         "memory decision differs from actual classifier output", errors)
    if arm == "cascade":
        base.require(route.get("policy") == "lightweight_v1"
                     and route.get("fixed_generator_model") is None,
                     "cascade is not the declared lightweight adaptive route", errors)
        source = route.get("model_size_decision_source")
        base.require(source in {"lightweight_small", "lightweight_large", "lightweight_resident"},
                     "cascade compute provenance is not lightweight", errors)
        base.require(decision.get("model_size") == ("small" if source == "lightweight_small" else "large"),
                     "lightweight decision/source mismatch", errors)
        base.require(route.get("resident_model") is None or route.get("resident_model") in base.ALLOWED[arm],
                     "route resident hint is outside cascade models", errors)
        if source == "lightweight_resident":
            base.require(route.get("resident_model") == base.LARGE,
                         "resident compute decision lacks a large-model hint", errors)
        if selectors:
            preferred = base.SMALL if decision.get("model_size") == "small" else base.LARGE
            expected_classifier = record.get("resident_hint_before") or preferred
            base.require(selectors[0].get("requested_model") == expected_classifier,
                         "cascade classifier did not use the resident or selected model", errors)
    else:
        fixed = base.SMALL if arm == "small" else base.LARGE
        base.require(route.get("policy") == "fixed_memory_v1"
                     and route.get("fixed_generator_model") == fixed,
                     "fixed arm lacks its declared optimized fixed-memory policy", errors)
        base.require(route.get("model_size_decision_source") == "fixed_generator"
                     and decision.get("model_size") == arm,
                     "fixed arm recorded an adaptive compute decision", errors)
    if record.get("status") == "ok" and generators:
        base.require(generators[-1].get("status") == "ok"
                     and generators[-1].get("generation") == record.get("generation"),
                     "delivered generation differs from the final actual model call", errors)
    return errors


def validate_manifest_contract(manifest, frozen, arm):
    errors = []
    base.require(manifest.get("profile_id") == PROFILE_ID == frozen.get("profile_id"),
                 "manifest/freeze comparison profile mismatch", errors)
    base.require(manifest.get("execution_policy") == execution_policy(arm)
                 == frozen.get("execution_policies", {}).get(arm),
                 "manifest/freeze execution policy mismatch", errors)
    return errors


def validate_session_contract(path, records, manifest, finish, frozen, result):
    """Profile-specific durable transport/source checks, in addition to common auditing."""
    errors = []
    try:
        if finish is not None:
            base.require(finish.get("source_sha256") == frozen["source_sha256"]
                         and finish.get("source_unchanged") is True,
                         "terminal execution source verification differs from freeze", errors)
            base.require(finish.get("model_metadata_unchanged") is True
                         and finish.get("ollama_version_unchanged") is True,
                         "terminal model/server verification failed", errors)
        http_path = path / "http_calls.jsonl"
        if not http_path.is_file():
            if records or result["status"] in base.COMPLETE:
                errors.append("post-memory durable HTTP evidence is absent")
            return errors
        result["artifact_sha256"][http_path.name] = base.file_hash(http_path)
        http = base.read_jsonl(http_path)
        allowed = base.ALLOWED[result["arm"]]
        for index, request in enumerate(http):
            body = request.get("body", {})
            base.require(body.get("model") in allowed,
                         f"HTTP {index}: model outside arm", errors)
            base.require(base.nonnegative(request.get("started_monotonic_ns"))
                         and base.nonnegative(request.get("wall_ns"))
                         and request.get("status") in {"ok", "error"},
                         f"HTTP {index}: invalid interval/status", errors)
            if request.get("endpoint") == "/api/chat":
                base.require(body.get("keep_alive") == -1
                             and body.get("stream") is False and body.get("think") is False,
                             f"HTTP {index}: generation/residency flags differ", errors)
                base.require(body.get("options") == {
                    "num_ctx": 2048, "num_predict": 192, "temperature": 0.0, "seed": 42},
                             f"HTTP {index}: actual generation options differ", errors)
            else:
                base.require(request.get("endpoint") == "/api/generate"
                             and body == {"model": body.get("model"), "prompt": "",
                                          "stream": False, "keep_alive": 0},
                             f"HTTP {index}: unexpected endpoint or non-unload generation", errors)
        offset = 0
        for row in records:
            row_http = row.get("http_calls")
            if not isinstance(row_http, list):
                errors.append(f"row {row.get('index')}: HTTP call slice is absent")
                continue
            base.require(http[offset:offset + len(row_http)] == row_http,
                         f"row {row.get('index')}: HTTP slice differs from durable evidence", errors)
            offset += len(row_http)
            for item in row_http:
                base.require(row["started_monotonic_ns"] <= item["started_monotonic_ns"]
                             and item["started_monotonic_ns"] + item["wall_ns"] <= row["finished_monotonic_ns"],
                             f"row {row.get('index')}: HTTP interval outside request interval", errors)
            chats = [item for item in row_http if item.get("endpoint") == "/api/chat"]
            cursor = 0
            for call in row.get("calls", []):
                if cursor >= len(chats):
                    base.require(call.get("status") == "error",
                                 f"row {row.get('index')}: successful call has no actual HTTP request", errors)
                    continue
                request = chats[cursor]
                fields = (request["body"].get("format") or {}).get("properties", {})
                purpose = "generation" if "speech" in fields else "memory_selector" if "memory_required" in fields else None
                if (call.get("status") == "error"
                        and (request["body"].get("model") != call.get("requested_model")
                             or purpose != call.get("purpose"))):
                    # Validation/peer eviction can fail before a chat is sent;
                    # a later logged timeout fallback still owns its own HTTP.
                    continue
                base.require(request["body"].get("model") == call.get("requested_model")
                             and purpose == call.get("purpose"),
                             f"row {row.get('index')}: call differs from actual HTTP model/schema", errors)
                if call.get("status") == "ok":
                    base.require(request.get("status") == "ok",
                                 f"row {row.get('index')}: successful call has failed transport", errors)
                cursor += 1
            base.require(cursor == len(chats), f"row {row.get('index')}: unaccounted HTTP inference", errors)
        if finish is not None:
            base.require(all(item.get("endpoint") == "/api/generate" for item in http[offset:]),
                         "terminal session has inference outside recorded attempts", errors)
        result["http_evidence"] = {"requests": len(http), "mapped_request_http": offset,
                                   "remaining_requests": len(http) - offset}
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        errors.append(f"post-memory evidence validation failed: {type(error).__name__}: {error}")
    return errors


def decorate_report(report, rows):
    report["comparison_profile"] = PROFILE_ID
    report["report_title"] = "Post-memory complete text-system comparison"
    report["profile_analyzer_sha256"] = base.file_hash(Path(__file__))
    report["routing_contract"] = {
        "fixed": "fixed_memory_v1: deterministic memory policy, otherwise own sole-model classifier",
        "cascade": "lightweight_v1: deterministic compute selection and zero/one resident/selected-model memory classifier",
        "compute_classifier_calls": 0,
        "counts_include_failed_attempts": True,
        "observed_call_purposes": dict(Counter(call.get("purpose") for row in rows for call in row.get("calls", []))),
        "interrupted_without_post_request_residency_snapshot": [
            {"arm": row.get("arm"), "repetition": row.get("repetition"), "case_id": row.get("id")}
            for row in rows if row.get("status") == "interrupted" and row.get("api_ps_after") is None],
        "residency_scope": "Actual recorded before/after snapshots; absent interrupted post-checks are unknown. Client hints are not server guarantees.",
    }


def analyze(workload_path, freeze_path, run_root):
    return base.analyze(workload_path, freeze_path, run_root, comparison_profile=PROFILE_ID)


def main(argv=None):
    return base.main(argv, comparison_profile=PROFILE_ID)


if __name__ == "__main__":
    raise SystemExit(main())
