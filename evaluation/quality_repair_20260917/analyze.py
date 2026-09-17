"""Reproduce fresh-evaluation metrics without inference or production imports.

Inputs default to sibling cases.json, candidate_freeze.json,
adjudicated_judgments.json and collection/{integrity_*,models_*,run/*}.
All planned cases remain in success denominators, including errors and absences.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MODES = ("none", "optional", "required", "clarify")
BOUNDS = {"answer_generation": 2, "answer_review": 2, "dependency_review": 1,
          "compute_classifier": 1}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def quantile(values, fraction):
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def latency(rows):
    values = [row["wall_seconds"] for row in rows if row["wall_seconds"] is not None]
    return {"n": len(values), "planned_in_group": len(rows), "missing_latency": len(rows) - len(values),
            "p50_seconds": quantile(values, .5), "p95_seconds": quantile(values, .95),
            "mean_seconds": statistics.mean(values) if values else None,
            "minimum_seconds": min(values) if values else None,
            "maximum_seconds": max(values) if values else None}


def rate(count, total):
    return {"count": count, "denominator": total, "rate": count / total if total else None}


def fields_in_schema(schema):
    if not isinstance(schema, dict):
        return set()
    fields = set(schema.get("properties", {}))
    for key in ("oneOf", "anyOf", "allOf"):
        for branch in schema.get(key, []):
            fields.update(fields_in_schema(branch))
    return fields


def call_role(call):
    fields = fields_in_schema(call.get("options", {}).get("response_format"))
    if fields & {"speech", "steps_for_user", "instructions", "steps", "answer_parts"}:
        return "answer_generation"
    if "verdict" in fields:
        return "answer_review"
    if "needs_personal_facts" in fields or fields == {"mode"}:
        return "dependency_review"
    if "model_size" in fields:
        return "compute_classifier"
    raise ValueError("unknown actual model-call schema: " + repr(sorted(fields)))


def normalize_judgments(payload):
    if isinstance(payload, dict) and "judgments" in payload:
        payload = payload["judgments"]
    if isinstance(payload, dict):
        payload = [dict(value, id=key) for key, value in payload.items()]
    require(isinstance(payload, list), "judgments must be a list, judgments list, or ID mapping")
    result = {}
    for row in payload:
        require(isinstance(row, dict) and isinstance(row.get("id"), str), "invalid judgment ID")
        require(row["id"] not in result, "duplicate judgment: " + row["id"])
        quality = row.get("quality_pass", row.get("strict_quality_pass"))
        require(type(quality) is bool, "judgment quality_pass must be boolean: " + row["id"])
        flags = row.get("flags", [])
        require(isinstance(flags, list) and all(isinstance(flag, str) for flag in flags),
                "judgment flags must be strings: " + row["id"])
        components = row.get("required_components_pass", [])
        require(isinstance(components, list) and all(isinstance(item, dict) and type(item.get("pass")) is bool
                                                    for item in components),
                "invalid component pass fields: " + row["id"])
        require(not quality or all(item["pass"] for item in components),
                "quality pass contradicts failed component: " + row["id"])
        if "useful_general_help" in row:
            require(type(row["useful_general_help"]) is bool or row["useful_general_help"] is None,
                    "useful_general_help must be boolean or null")
        subtypes = row.get("unsupported_subtypes", [])
        require(isinstance(subtypes, list) and all(isinstance(item, str) for item in subtypes),
                "unsupported_subtypes must be a list of strings")
        result[row["id"]] = dict(row, quality_pass=quality)
    return result


def count_summary(rows):
    total = len(rows)
    return {"planned": total,
            **{name: rate(sum(row[name] for row in rows), total) for name in (
                "raw_match", "thresholded_match", "final_match", "quality_pass", "combined_pass")},
            "useful_general_help": rate(sum(row["useful_general_help"] is True for row in rows), total),
            "general_component_cases": sum(row["general_component_expected"] for row in rows),
            "useful_general_help_when_expected": rate(
                sum(row["useful_general_help"] is True and row["general_component_expected"] for row in rows),
                sum(row["general_component_expected"] for row in rows)),
            "effective_mode_match": rate(sum(row["effective_match"] is True for row in rows),
                                         sum(row["expected_effective_modes"] is not None for row in rows)),
            "observed": sum(row["status"] != "missing" for row in rows),
            "errors": sum(row["status"] == "error" for row in rows),
            "missing": sum(row["status"] == "missing" for row in rows),
            "delivered": sum(row["delivered"] for row in rows),
            "generated_delivery": sum(row["generated_delivery"] for row in rows),
            "application_delivery": sum(row["application_delivery"] for row in rows)}


def build(cases, observations, judgments, *, observations_source="collection/run/observations.jsonl"):
    planned_ids = [case["id"] for case in cases]
    require(len(set(planned_ids)) == len(planned_ids), "duplicate planned case ID")
    observed_ids = [row["id"] for row in observations]
    require(observed_ids == planned_ids[:len(observed_ids)], "observations must be the planned case-order prefix")
    require(not set(judgments) - set(planned_ids), "judgments contain unplanned case IDs")
    observed = {row["id"]: row for row in observations}
    rows = []
    for index, case in enumerate(cases, 1):
        observation = observed.get(case["id"])
        if observation:
            require(observation["case"] == case, "embedded case differs from frozen corpus: " + case["id"])
            require(observation.get("stage") == "conversation" and observation.get("policy") == "learned",
                    "unexpected stage/policy: " + case["id"])
        expected = case["expected_modes"]
        require(isinstance(expected, list) and len(expected) == 1 and expected[0] in MODES,
                "this preregistered corpus requires one expected dependency mode per case")
        observation = observation or {}
        status = observation.get("status", "missing")
        require(status in {"ok", "error", "missing"}, "unknown observation status")
        route, reply = observation.get("route") or {}, observation.get("reply") or {}
        prediction = (route.get("classifier_metadata") or {}).get("whole_request") or {}
        judgment = judgments.get(case["id"])
        delivered = status == "ok" and bool(observation.get("delivered_text", "").strip())
        raw = prediction.get("predicted_mode")
        thresholded = prediction.get("mode")
        final = (route.get("dependency") or {}).get("mode")
        effective = reply.get("effective_mode")
        for name, mode in (("raw", raw), ("thresholded", thresholded), ("final", final), ("effective", effective)):
            require(mode is None or mode in MODES, "invalid " + name + " mode: " + case["id"])
        quality = bool(delivered and judgment and judgment["quality_pass"])
        rubric = case.get("rubric", {})
        expected_effective = case.get("expected_effective_modes", rubric.get("expected_effective_modes"))
        if expected_effective is None:
            single_effective = case.get("expected_effective_mode", rubric.get("expected_effective_mode"))
            expected_effective = [single_effective] if single_effective is not None else None
        if expected_effective is not None:
            require(isinstance(expected_effective, list) and expected_effective
                    and all(mode in MODES for mode in expected_effective), "invalid expected effective modes")
        calls = []
        for call_index, call in enumerate(observation.get("calls", []), 1):
            require(call.get("case_id") == case["id"], "call has mismatched case ID")
            result = call.get("result") or {}
            calls.append({"index": call_index, "role": call_role(call), "model": call["model"],
                          "status": call["status"], "wall_ns": call["wall_ns"],
                          "done_reason": result.get("done_reason"),
                          "load_duration_ns": result.get("load_duration_ns"),
                          "total_duration_ns": result.get("total_duration_ns"),
                          "prompt_eval_count": result.get("prompt_eval_count"),
                          "eval_count": result.get("eval_count"), "error": call.get("error"),
                          "source": observations_source + ":case.calls[" + str(call_index - 1) + "]"})
        call_counts = Counter(call["role"] for call in calls)
        violations = {role: {"actual": call_counts[role], "maximum": maximum}
                      for role, maximum in BOUNDS.items() if call_counts[role] > maximum}
        wall_ns = observation.get("wall_ns")
        require(wall_ns is None or type(wall_ns) is int and wall_ns >= 0, "invalid case wall duration")
        flags = list(dict.fromkeys(judgment.get("flags", []))) if judgment else []
        if status == "missing":
            flags.append("missing_observation")
        elif status == "error":
            flags.append("execution_error")
        if not judgment:
            flags.append("missing_judgment")
        generated = delivered and reply.get("generation") is not None
        generation_call_index = None
        if generated:
            generation_call_index = next((offset for offset, call in enumerate(observation.get("calls", []), 1)
                                          if call.get("result") == reply["generation"]
                                          and call_role(call) == "answer_generation"), None)
            require(generation_call_index is not None, "selected generation absent from actual calls: " + case["id"])
        rows.append({
            "id": case["id"], "index": index, "category": case.get("category", "uncategorized"),
            "expected_modes": expected, "raw_mode": raw, "thresholded_mode": thresholded,
            "final_mode": final, "effective_mode": effective,
            "raw_match": status == "ok" and raw in expected,
            "thresholded_match": status == "ok" and thresholded in expected,
            "final_match": status == "ok" and final in expected,
            "expected_effective_modes": expected_effective,
            "effective_match": (status == "ok" and effective in expected_effective)
                               if expected_effective is not None else None,
            "quality_pass": quality, "combined_pass": quality and final in expected,
            "status": status, "error": observation.get("error"), "delivered": delivered,
            "delivered_text": observation.get("delivered_text"), "generated_delivery": generated,
            "application_delivery": delivered and not generated,
            "generation_policy": reply.get("generation_policy"),
            "generation_model": (reply.get("generation") or {}).get("model"),
            "selected_generation_call_index": generation_call_index,
            "fallback_from_model": reply.get("fallback_from_model"),
            "compute_selected_size": (route.get("decision") or {}).get("model_size"),
            "memory_decision_source": route.get("memory_decision_source"),
            "review_reason": route.get("review_reason"),
            "classifier_uncertain": prediction.get("uncertain"),
            "classifier_margin": prediction.get("margin"),
            "classifier_threshold": prediction.get("threshold"),
            "retrieval_status": reply.get("retrieval_status"),
            "memory_diagnostics": reply.get("memory_diagnostics"),
            "application_memory_ids": reply.get("application_memory_ids", []),
            "reference_ids": reply.get("reference_ids", []),
            "admitted_history_messages": observation.get("admitted_history_messages"),
            "supplied_history_messages": len(case.get("prior_turns", [])),
            "attempts": reply.get("attempts", []), "attempted_models": reply.get("attempted_models", []),
            "answer_reviews": reply.get("answer_reviews", []), "review_attempts": reply.get("review_attempts", []),
            "runtime_quality_issues": reply.get("quality_issues", []),
            "general_component_expected": bool(case.get("general_component_expected", rubric.get("general_component_expected", False))),
            "useful_general_help": judgment.get("useful_general_help") if judgment and delivered else False,
            "judgment": judgment, "flags": list(dict.fromkeys(flags)),
            "wall_seconds": wall_ns / 1e9 if wall_ns is not None else None,
            "calls": calls, "call_counts": dict(call_counts), "call_bound_violations": violations,
        })
    return rows


def aggregate(rows):
    by_mode = {mode: [row for row in rows if mode in row["expected_modes"]] for mode in MODES}
    by_category = {category: [row for row in rows if row["category"] == category]
                   for category in sorted({row["category"] for row in rows})}
    confusion = {}
    for field in ("raw_mode", "thresholded_mode", "final_mode", "effective_mode"):
        confusion[field] = {mode: dict(Counter((row[field] or "unavailable") if row["status"] == "ok"
                                               else row["status"] for row in subset))
                            for mode, subset in by_mode.items()}
    calls = [call for row in rows for call in row["calls"]]
    role_model = Counter((call["role"], call["model"]) for call in calls)
    latency_groups = {"overall_observed": rows,
                      "delivered_model_generated": [row for row in rows if row["generated_delivery"]],
                      "application_only": [row for row in rows if row["application_delivery"]],
                      "full_quality": [row for row in rows if row["quality_pass"]],
                      "combined_success": [row for row in rows if row["combined_pass"]]}
    return {
        "schema_version": "fresh_routing_metrics_v1", "summary": count_summary(rows),
        "per_mode": {mode: count_summary(subset) for mode, subset in by_mode.items()},
        "per_category": {category: count_summary(subset) for category, subset in by_category.items()},
        "confusion": confusion,
        "flags": dict(sorted(Counter(flag for row in rows for flag in row["flags"]).items())),
        "primary_outcomes": dict(Counter((row["judgment"] or {}).get("primary_outcome", "unreviewed") for row in rows)),
        "unsupported_subtypes": dict(Counter(subtype for row in rows for subtype in
                                             (row["judgment"] or {}).get("unsupported_subtypes", []))),
        "generation_policies": dict(Counter(row["generation_policy"] or "unavailable" for row in rows)),
        "selected_generation_models": dict(Counter(row["generation_model"] or "application_or_unavailable" for row in rows)),
        "classifier_threshold_rejections": sum(row["classifier_uncertain"] is True for row in rows),
        "raw_to_final_mode_changes": sum(row["raw_mode"] is not None and row["final_mode"] is not None
                                          and row["raw_mode"] != row["final_mode"] for row in rows),
        "generation_model_fallbacks": sum(row["fallback_from_model"] is not None for row in rows),
        "actual_calls": {"total": len(calls), "by_role": dict(Counter(call["role"] for call in calls)),
                         "by_model": dict(Counter(call["model"] for call in calls)),
                         "by_role_and_model": [{"role": role, "model": model, "count": count}
                                               for (role, model), count in sorted(role_model.items())],
                         "by_status": dict(Counter(call["status"] for call in calls)),
                         "declared_bounds_per_case": BOUNDS,
                         "bound_violations": {row["id"]: row["call_bound_violations"] for row in rows if row["call_bound_violations"]},
                         "call_count_distribution": dict(sorted(Counter(len(row["calls"]) for row in rows).items())),
                         "generation_attempt_distribution": dict(sorted(Counter(row["call_counts"].get("answer_generation", 0) for row in rows).items())),
                         "case_wall_seconds_total": sum(row["wall_seconds"] or 0 for row in rows),
                         "recorded_call_wall_seconds_total": sum(call["wall_ns"] for call in calls) / 1e9,
                         "backend_total_seconds_available": sum(call["total_duration_ns"] or 0 for call in calls) / 1e9,
                         "backend_load_seconds_available": sum(call["load_duration_ns"] or 0 for call in calls) / 1e9,
                         "calls_missing_backend_duration": sum(call["total_duration_ns"] is None for call in calls),
                         "timing_interpretation": "Backend load is inside backend total; calls are inside case wall. Different timing scopes cannot identify causal overhead."},
        "latency": {**{name: latency(subset) for name, subset in latency_groups.items()},
                    "per_category": {category: latency(subset) for category, subset in by_category.items()},
                    "per_mode": {mode: latency(subset) for mode, subset in by_mode.items()},
                    "quantile_method": "linear interpolation at (n-1)*q", "units": "seconds"},
        "quality_deadlines": {str(deadline): rate(sum(row["quality_pass"] and row["wall_seconds"] is not None
                                                      and row["wall_seconds"] <= deadline for row in rows), len(rows))
                              for deadline in (5, 10, 30, 60)},
        "combined_deadlines": {str(deadline): rate(sum(row["combined_pass"] and row["wall_seconds"] is not None
                                                       and row["wall_seconds"] <= deadline for row in rows), len(rows))
                               for deadline in (5, 10, 30, 60)},
        "generated_quality_deadlines": {
            str(deadline): rate(sum(row["generated_delivery"] and row["quality_pass"]
                                    and row["wall_seconds"] is not None and row["wall_seconds"] <= deadline
                                    for row in rows), sum(row["generated_delivery"] for row in rows))
            for deadline in (5, 10, 30, 60)},
        "generated_quality_deadlines_all_planned": {
            str(deadline): rate(sum(row["generated_delivery"] and row["quality_pass"]
                                    and row["wall_seconds"] is not None and row["wall_seconds"] <= deadline
                                    for row in rows), len(rows)) for deadline in (5, 10, 30, 60)},
        "deadline_interpretation": "quality_deadlines and combined_deadlines use all planned cases and include appropriate application replies. generated_quality_deadlines is conditional on delivered model-generated text; generated_quality_deadlines_all_planned uses the full planned denominator.",
        "review_complete": all(row["judgment"] is not None for row in rows),
        "interpretation": "Finite single-pass assistant-reviewed empty-memory text evaluation; effective fallback modes never replace final dependency labels. Errors and missing cases fail planned-case metrics.",
    }


def verify_inputs(args, cases, observations):
    collection = args.collection
    artifact_manifest = read(collection / "artifact_sha256.json")
    for name, frozen_hash in artifact_manifest.items():
        path = collection / name
        require(path.is_file() and digest(path) == frozen_hash, "sealed collection artifact changed: " + name)
    before, after = read(collection / "integrity_before.json"), read(collection / "integrity_after.json")
    require(before == after, "collection source/config/corpus/embedding integrity changed")
    require(before["cases_sha256"] == digest(args.cases), "corpus hash differs from collected corpus")
    candidate = read(args.candidate_manifest)["source_sha256"]
    for name, frozen_hash in candidate.items():
        require(before["source_sha256"].get(name) == frozen_hash, "candidate source mismatch: " + name)
        require(digest(args.source_root / name) == frozen_hash, "verification source drift: " + name)
        archived = args.candidate_manifest.parent / "candidate_source" / name
        require(archived.is_file() and digest(archived) == frozen_hash, "archived candidate drift: " + name)
    models_before, models_after = read(collection / "models_before.json"), read(collection / "models_after.json")
    require(models_before == models_after, "configured model identity or server version changed")
    metadata, summary = read(collection / "run/metadata.json"), read(collection / "run/summary.json")
    require(metadata["cases_sha256"] == digest(args.cases), "runner corpus hash mismatch")
    require(metadata["config_sha256"] == sha256(json.dumps(before["config"], sort_keys=True).encode()).hexdigest(),
            "runner configuration differs from guarded configuration")
    require(metadata["stage"] == "conversation" and metadata["policy"] == "learned", "runner stage/policy mismatch")
    require(metadata["case_count"] == len(cases) == summary["case_count"], "planned denominator mismatch")
    require(summary["completed"] == len(observations), "runner completed count differs from raw rows")
    require(summary["label_matches"] == sum(row["diagnostic"]["label_match"] is True for row in observations),
            "runner label-match count mismatch")
    for name, frozen_hash in metadata["source_sha256"].items():
        require(before["source_sha256"].get(name) == frozen_hash, "runner source hash mismatch: " + name)
    raw_calls_path = collection / "run/model_calls.jsonl"
    raw_calls = jsonl(raw_calls_path) if raw_calls_path.exists() else []
    require(raw_calls == [call for row in observations for call in row.get("calls", [])],
            "durable model-call log differs from observation call provenance")
    for call in raw_calls:
        require(call["model"] in models_before["models"], "call uses unfrozen model identity")
        if call.get("result"):
            require(call["result"]["model"] == call["model"], "returned model differs from requested model")
    inputs = [args.cases, args.judgments, args.candidate_manifest, collection / "artifact_sha256.json",
              collection / "integrity_before.json", collection / "integrity_after.json",
              collection / "models_before.json", collection / "models_after.json",
              collection / "run/metadata.json", collection / "run/summary.json",
              HERE / "protocol.md", Path(__file__).resolve()]
    if (collection / "run/observations.jsonl").exists():
        inputs.append(collection / "run/observations.jsonl")
    if args.freeze_manifest:
        frozen = read(args.freeze_manifest)
        if "cases_sha256" in frozen:
            require(frozen["cases_sha256"] == digest(args.cases), "preregistered corpus hash mismatch")
        for name, frozen_hash in frozen.get("source_sha256", {}).items():
            if name in before["source_sha256"]:
                require(before["source_sha256"][name] == frozen_hash, "preregistered runtime source mismatch: " + name)
            require(digest(args.source_root / name) == frozen_hash, "verification runtime source drift: " + name)
        if "source_sha256" in frozen:
            for name, runtime_hash in before["source_sha256"].items():
                require(frozen["source_sha256"].get(name) == runtime_hash, "runtime source was not frozen: " + name)
        hashes = frozen.get("files", frozen.get("sha256", frozen.get("artifact_sha256", frozen)))
        require(isinstance(hashes, dict), "unsupported freeze manifest schema")
        for name, frozen_hash in hashes.items():
            require(isinstance(frozen_hash, str) and len(frozen_hash) == 64, "freeze hash must be SHA256")
            path = args.freeze_manifest.parent / name
            require(path.is_file() and digest(path) == frozen_hash, "pre-inference artifact changed: " + name)
        inputs.append(args.freeze_manifest)
    return {"verified": True, "verification_source_root": str(args.source_root.resolve()),
            "input_sha256": {str(path.resolve()): digest(path) for path in inputs},
            "models": models_before, "runner_summary": summary,
            "collection_finish": read(collection / "finish.json"),
            "frozen_artifact_manifest_verified": args.freeze_manifest is not None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=HERE / "cases.json")
    parser.add_argument("--collection", type=Path, default=HERE / "collection")
    parser.add_argument("--judgments", type=Path, default=HERE / "adjudicated_judgments.json")
    parser.add_argument("--candidate-manifest", type=Path, default=HERE / "candidate_freeze.json")
    parser.add_argument("--source-root", type=Path, default=ROOT,
                        help="Working repository or the archived candidate_source root for historical reanalysis")
    parser.add_argument("--freeze-manifest", type=Path)
    parser.add_argument("--expected-count", type=int, default=48)
    parser.add_argument("--output-dir", type=Path, default=HERE)
    args = parser.parse_args(argv)
    payload = read(args.cases)
    cases = payload["cases"] if isinstance(payload, dict) else payload
    require(len(cases) == args.expected_count, "planned case count differs from expected count")
    observations_path = args.collection / "run/observations.jsonl"
    observations = jsonl(observations_path) if observations_path.exists() else []
    judgments = normalize_judgments(read(args.judgments))
    rows = build(cases, observations, judgments, observations_source=str(observations_path.resolve()))
    integrity = verify_inputs(args, cases, observations)
    metrics = aggregate(rows)
    metrics["integrity"] = integrity
    finish, summary = integrity["collection_finish"], integrity["runner_summary"]
    clean_finalization = (finish.get("failure") is None and not finish.get("cleanup_errors")
                          and finish.get("guard_violation") is None and summary.get("failure") is None
                          and summary.get("cleanup_error") is None)
    metrics["evaluation_complete"] = bool(len(observations) == len(cases) and metrics["review_complete"]
                                           and clean_finalization)
    metrics["operational_success"] = bool(finish.get("complete"))
    metrics["completion_interpretation"] = "Evaluation completion means all planned cases and judgments were captured with verified integrity and clean finalization. Candidate execution errors, quality failures, and call-bound violations remain measured outcomes."
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    (args.output_dir / "per_case.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows))
    print(json.dumps(metrics["summary"], indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError, TypeError) as error:
        print("ANALYSIS FAILED: " + type(error).__name__ + ": " + str(error), file=sys.stderr)
        raise SystemExit(1)
