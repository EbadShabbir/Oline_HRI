"""Supplement frozen routing analysis with raw-backend and sequence detail.

Offline only; does not change runtime, frozen source, raw files or judgments.
During collection, only sessions with finish.json enter the snapshot. After a
terminal batch_finish.json exists, incomplete attempt directories are included.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import statistics
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("routing_continued_detail_core", HERE / "analyze_continued.py")
mixed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mixed)
core = mixed.core
NS = core.NS
ARMS = core.ARMS


def total_known(values):
    values = list(values)
    return sum(values) if values and all(value is not None for value in values) else None


def sum_or_zero(rows, key):
    return 0 if not rows else total_known(row.get(key) for row in rows)


def seconds(value):
    return value / NS if core.number(value) else None


def difference(left, right):
    return left - right if left is not None and right is not None else None


def snapshot(args):
    terminal = (args.run_root / "batch_finish.json").is_file()
    selected, omitted = [], []
    for manifest in sorted(args.run_root.glob("*/manifest.json")):
        directory = manifest.parent
        (selected if terminal or (directory / "finish.json").is_file() else omitted).append(directory)
    with tempfile.TemporaryDirectory(prefix="clara-routing-detail-snapshot-") as temporary:
        view = Path(temporary)
        for directory in selected:
            destination = view / directory.name
            destination.mkdir()
            for path in directory.iterdir():
                if path.is_file():
                    (destination / path.name).symlink_to(path.resolve())
        loader = mixed.MixedFreezeLoader(args)
        result = loader(view, args.workload, args.freeze)
    return result, dict(snapshot_at=datetime.now(timezone.utc).isoformat(),
        terminal_batch_record_present=terminal, selected_session_directories=[str(path.resolve()) for path in selected],
        active_session_directories_omitted=[str(path.resolve()) for path in omitted],
        freeze_compatibility=loader.proof["compatibility"],
        exceptional_whole_sequence_eligibility=loader.proof["eligibility_normalization"])


def ancestors(event, by_id):
    values, parent = [], event.get("parent_id")
    while parent in by_id:
        if parent in values:
            raise ValueError("cyclic event parents")
        values.append(parent)
        parent = by_id[parent].get("parent_id")
    return values


def raw_backend_rows(records):
    """One row per actual backend HTTP span; never duplicate calls/HTTP metadata."""
    rows = []
    for record in records:
        events = record.get("events", [])
        by_id = {event["id"]: event for event in events}
        backend = sorted((event for event in events if event["name"] == "backend_chat"), key=lambda event: event["start_ns"])
        audits = [event for event in events if event["name"] == "residency_audit"]
        for ordinal, event in enumerate(backend, 1):
            attributes = event.get("attributes", {})
            chain = [by_id[parent]["name"] for parent in ancestors(event, by_id)]
            purpose = ("generation" if "answer_generation" in chain else "memory_selector" if "memory_classifier" in chain
                       else "compute_selector" if "compute_classifier" in chain else "unknown")
            response = attributes.get("backend_response") or {}
            speech_schema = attributes.get("request", {}).get("format", {}).get("properties", {}).get("speech", {})
            requested = attributes.get("requested_model", attributes.get("request", {}).get("model"))
            actual = response.get("model", attributes.get("actual_model"))
            matches = [audit for audit in audits if audit.get("parent_id") == event.get("parent_id")
                       and audit.get("start_ns", 0) >= event["end_ns"]]
            audit = min(matches, key=lambda value: value["start_ns"]) if matches else None
            state = audit.get("attributes", {}).get("models") if audit else None
            row = {key: record.get(key) for key in ("attempt_directory", "sequence_id", "pattern", "arm", "repetition", "id", "index")}
            row.update(backend_call_index=ordinal, purpose=purpose, request_status=record["status"],
                backend_span_status=event["status"], requested_model=requested, actual_model=actual,
                backend_span_wall_seconds=seconds(event.get("wall_ns")),
                output_tokens=response.get("eval_count", attributes.get("eval_count")),
                prompt_tokens=response.get("prompt_eval_count", attributes.get("prompt_eval_count")),
                cached_prompt_tokens=response.get("prompt_eval_cached_count"),
                done_reason=response.get("done_reason", attributes.get("done_reason")),
                backend_done=response.get("done"), raw_response_present=bool(response),
                literal_speech_schema_constrained=("enum" in speech_schema or "const" in speech_schema),
                residency_after_call=state, **core.placement(state, actual))
            for name in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
                row[name + "_seconds"] = seconds(response.get(name, attributes.get("backend_" + name + "_ns")))
            row["backend_nonload_total_seconds"] = difference(row["total_duration_seconds"], row["load_duration_seconds"])
            row["backend_metadata_overlaps_wall"] = True
            rows.append(row)
    return rows


def turn_rows(records, calls, judgments):
    by_turn = defaultdict(list)
    for call in calls:
        by_turn[call["attempt_directory"], call["index"]].append(call)
    rows, previous = [], {}
    for raw in records:
        name = raw["attempt_directory"]
        all_calls = by_turn[name, raw["index"]]
        generation = [call for call in all_calls if call["purpose"] == "generation"]
        classifiers = [call for call in all_calls if call["purpose"] in {"memory_selector", "compute_selector"}]
        actual = generation[-1]["actual_model"] if generation else core.model_for_turn(raw)
        route = raw.get("route") or {}
        before = core.residents(raw.get("api_ps_before"))
        old = previous.get(name)
        condition = ("cold_start" if before == [] else "resident_same_model" if before == [actual]
                     else "model_switch" if before is not None and actual is not None else "unknown")
        row = {key: raw.get(key) for key in ("attempt_directory", "sequence_id", "pattern", "arm", "repetition", "id", "index", "status", "workload_label")}
        row.update(request_wall_seconds=seconds(raw.get("wall_ns")),
            selected_model_size=(route.get("decision") or {}).get("model_size"),
            model_decision_source=route.get("model_size_decision_source"),
            memory_required=(route.get("decision") or {}).get("memory_required"),
            memory_decision_source=route.get("memory_decision_source"),
            actual_final_generator=actual, all_generator_calls=[call["actual_model"] for call in generation],
            backend_generation_calls=len(generation), requested_generation_calls=sum(call.get("purpose") == "generation" for call in raw.get("calls", [])),
            backend_classifier_calls=len(classifiers), generation_tokens_known_calls=sum(call["output_tokens"] is not None for call in generation),
            generation_output_tokens_all_calls=sum_or_zero(generation, "output_tokens"),
            final_generation_output_tokens=generation[-1]["output_tokens"] if generation else None,
            classifier_output_tokens=sum_or_zero(classifiers, "output_tokens"),
            all_backend_output_tokens=sum_or_zero(all_calls, "output_tokens"),
            final_generator_gpu_allocation_fraction=generation[-1].get("gpu_allocation_fraction") if generation else None,
            residency_before=before, residency_after=core.residents(raw.get("api_ps_after")),
            residency_condition=condition, previous_generator=old["actual_final_generator"] if old else None,
            following_turn_of_condition=old["residency_condition"] if old else None,
            return_to_small=bool(old and old["actual_final_generator"] == core.LARGE and actual == core.SMALL),
            after_small_return=bool(old and old["return_to_small"]),
            first_backend_caller=all_calls[0]["purpose"] if all_calls else None,
            application_answer_constraint=bool(raw.get("answer_constraint")) if "answer_constraint" in raw else None,
            literal_speech_schema_constrained=any(call["literal_speech_schema_constrained"] for call in generation) if generation else None,
            generation_policy=raw.get("generation_policy"),
            fallback_from_model=raw.get("fallback_from_model"), quality_label=None, correct=None)
        if raw.get("dangling_attempt_marker"):
            # A killed process may have decoded output not yet captured in a
            # completed observation. No observed backend span is not zero work.
            row["generation_output_tokens_all_calls"] = None
            row["classifier_output_tokens"] = None
            row["all_backend_output_tokens"] = None
        for category, relevant in (("all_backend", all_calls), ("generation_backend", generation), ("classifier_backend", classifiers)):
            for field in ("load_duration_seconds", "prompt_eval_duration_seconds", "eval_duration_seconds", "total_duration_seconds"):
                row[category + "_" + field] = sum_or_zero(relevant, field)
        for component, value in raw.get("exclusive_components_ns", {}).items():
            row["exclusive_" + component + "_seconds"] = value / NS
        judgment = judgments.get((name, raw.get("id"), raw.get("index")))
        if judgment:
            row.update(quality_label=judgment["label"], correct=judgment["correct"])
        rows.append(row)
        previous[name] = row
    return rows


def sequence_rows(runs, turns):
    by_session = defaultdict(list)
    for turn in turns:
        by_session[turn["attempt_directory"]].append(turn)
    rows = []
    for run in runs:
        seen = sorted(by_session[run["attempt_directory"]], key=lambda row: row["index"])
        row = dict(run)
        row.update(selected_model_sequence=[turn["selected_model_size"] for turn in seen],
            actual_generator_sequence=[turn["actual_final_generator"] for turn in seen],
            all_actual_generator_calls=[turn["all_generator_calls"] for turn in seen],
            workload_label_sequence=[turn["workload_label"] for turn in seen],
            model_decision_sources=[turn["model_decision_source"] for turn in seen],
            memory_decision_sources=[turn["memory_decision_source"] for turn in seen],
            return_to_small_turns=[turn["index"] for turn in seen if turn["return_to_small"]],
            transitions_with_no_following_observation=[turn["index"] for turn in seen if turn["residency_condition"] == "model_switch"
                and not any(other["index"] == turn["index"] + 1 for other in seen)],
            quality_reviewed_turns=sum(turn["quality_label"] is not None for turn in seen),
            correct_delivered_turns=sum(turn["correct"] for turn in seen) if seen and all(turn["correct"] is not None for turn in seen) else None)
        for key in ("generation_output_tokens_all_calls", "classifier_output_tokens", "all_backend_output_tokens",
                    "backend_generation_calls", "backend_classifier_calls"):
            row[key] = sum_or_zero(seen, key)
        for category in ("all_backend", "generation_backend", "classifier_backend"):
            for field in ("load_duration_seconds", "prompt_eval_duration_seconds", "eval_duration_seconds", "total_duration_seconds"):
                name = category + "_" + field
                row[name] = sum_or_zero(seen, name)
        row["residency_audit_seconds"] = sum(turn.get("exclusive_residency_audit_seconds", 0) for turn in seen)
        row["request_plus_startup_seconds"] = (run["startup_seconds"] + run["request_seconds"]
            if run["startup_seconds"] is not None and run["request_seconds"] is not None else None)
        if run["pattern"] == "DDEE" and run["arm"] == "adaptive":
            row["selected_LLLS_observed"] = row["selected_model_sequence"] == ["large", "large", "large", "small"]
            row["actual_LLLS_observed"] = row["actual_generator_sequence"] == [core.LARGE, core.LARGE, core.LARGE, core.SMALL]
            row["first_easy_held_by_residency_rule"] = len(seen) >= 3 and seen[2]["model_decision_source"] == "lightweight_resident"
        rows.append(row)
    return rows


def paired_rows(sequences, turns):
    sequence_lookup = {(row["sequence_id"], row["repetition"], row["arm"]): row for row in sequences if row["complete"]}
    turn_lookup = {(row["sequence_id"], row["repetition"], row["index"], row["arm"]): row for row in turns}
    paired_sequences, paired_turns = [], []
    for key, adaptive in sequence_lookup.items():
        sequence, repetition, arm = key
        if arm != "adaptive":
            continue
        for comparator in ("small", "large", "replay"):
            other = sequence_lookup.get((sequence, repetition, comparator))
            if other is None:
                continue
            pair = dict(sequence_id=sequence, pattern=adaptive["pattern"], repetition=repetition, comparator=comparator,
                adaptive_source_freeze=adaptive.get("source_freeze"), comparator_source_freeze=other.get("source_freeze"),
                identical_actual_generator_sequence=adaptive["all_actual_generator_calls"] == other["all_actual_generator_calls"],
                adaptive_original_status=adaptive["status"], comparator_original_status=other["status"])
            metrics = ["startup_seconds", "request_seconds", "sequence_gaps_seconds", "sequence_seconds", "cleanup_seconds",
                       "generation_output_tokens_all_calls", "classifier_output_tokens", "all_backend_output_tokens", "residency_audit_seconds",
                       "correct_delivered_turns"] + [category + "_" + name for category in ("all_backend", "generation_backend", "classifier_backend")
                       for name in ("load_duration_seconds", "prompt_eval_duration_seconds", "eval_duration_seconds", "total_duration_seconds")]
            for metric in metrics:
                pair["adaptive_minus_comparator_" + metric] = difference(adaptive.get(metric), other.get(metric))
            pair["adaptive_minus_comparator_request_seconds_excluding_direct_residency_audits"] = difference(
                pair["adaptive_minus_comparator_request_seconds"], pair["adaptive_minus_comparator_residency_audit_seconds"])
            paired_sequences.append(pair)
            for index in (1, 2, 3, 4):
                left, right = turn_lookup.get((sequence, repetition, index, "adaptive")), turn_lookup.get((sequence, repetition, index, comparator))
                if left is None or right is None:
                    continue
                entry = dict(sequence_id=sequence, pattern=adaptive["pattern"], repetition=repetition, index=index, comparator=comparator,
                    adaptive_status=left["status"], comparator_status=right["status"],
                    adaptive_actual_generator=left["actual_final_generator"], comparator_actual_generator=right["actual_final_generator"],
                    adaptive_residency_condition=left["residency_condition"], comparator_residency_condition=right["residency_condition"],
                    adaptive_following_turn_of_condition=left["following_turn_of_condition"],
                    adaptive_correct=left["correct"], comparator_correct=right["correct"])
                for metric in ["request_wall_seconds", "generation_output_tokens_all_calls", "classifier_output_tokens", "all_backend_output_tokens",
                               "final_generator_gpu_allocation_fraction"] + [category + "_" + name for category in
                               ("all_backend", "generation_backend", "classifier_backend") for name in
                               ("load_duration_seconds", "prompt_eval_duration_seconds", "eval_duration_seconds", "total_duration_seconds")]:
                    if metric in left or metric in right:
                        entry["adaptive_minus_comparator_" + metric] = difference(left.get(metric), right.get(metric))
                if left["correct"] is not None and right["correct"] is not None:
                    entry["quality_outcome"] = ("both_correct" if left["correct"] and right["correct"] else "adaptive_only_correct"
                        if left["correct"] else "comparator_only_correct" if right["correct"] else "neither_correct")
                paired_turns.append(entry)
    return paired_sequences, paired_turns


def grouped(rows, keys, metrics):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(key) for key in keys)].append(row)
    output = []
    for values, members in sorted(groups.items(), key=lambda item: str(item[0])):
        result = dict(zip(keys, values), observed_rows=len(members))
        for metric in metrics:
            values = [row.get(metric) for row in members]
            observed = core.dist(values)
            result[metric + "_known_count"] = observed["n"]
            result[metric + "_mean"] = observed["mean"]
            result[metric + "_sum"] = observed["total"] if observed["n"] == len(members) else None
            result[metric + "_min"] = observed["min"]
            result[metric + "_max"] = observed["max"]
        output.append(result)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run-root", "previous-root", "previous-freeze", "freeze", "workload", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--blind-dir", type=Path)
    parser.add_argument("--reviews", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    result, provenance = snapshot(args)
    workload, frozen, runs, records, _, _, _, errors = result
    if errors:
        raise ValueError(f"input integrity audit failed: {errors}")
    judgments, quality = core.quality_join(records, args.blind_dir, args.reviews)
    calls = raw_backend_rows(records)
    turns = turn_rows(records, calls, judgments)
    sequences = sequence_rows(runs, turns)
    sequence_pairs, turn_pairs = paired_rows(sequences, turns)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    pattern = grouped([row for row in sequences if row["complete"]], ["pattern", "arm", "repetition"],
        ["startup_seconds", "request_seconds", "sequence_gaps_seconds", "sequence_seconds", "cleanup_seconds",
         "generation_output_tokens_all_calls", "all_backend_load_duration_seconds", "all_backend_prompt_eval_duration_seconds", "all_backend_eval_duration_seconds"])
    placement = grouped(calls, ["arm", "purpose", "actual_model"],
        ["gpu_allocation_fraction", "loaded_bytes", "gpu_allocated_bytes", "output_tokens", "prompt_tokens"])
    conditions = []
    for condition in ("residency_condition", "following_turn_of_condition", "return_to_small", "after_small_return"):
        conditions.extend(dict(grouping=condition, **row) for row in grouped(turns, ["arm", condition],
            ["request_wall_seconds", "generation_output_tokens_all_calls", "all_backend_load_duration_seconds"]))
    for name, values in (("raw_backend_calls", calls), ("turn_details", turns), ("sequence_details", sequences),
                        ("per_pattern_repetition", pattern), ("placement_by_backend", placement),
                        ("cold_transition_following", conditions), ("paired_sequence_components", sequence_pairs),
                        ("paired_turn_components", turn_pairs)):
        core.table(args.output_dir / (name + ".csv"), values)
    rejected = [row for row in turns if row["status"] != "ok"]
    ddee = [row for row in sequences if row["arm"] == "adaptive" and row["pattern"] == "DDEE"]
    coverage = dict(snapshot_sessions=len(sequences), observed_turns=len(turns), eligible_complete_sequences=sum(row["complete"] for row in sequences),
        raw_backend_calls=len(calls), raw_generation_calls=sum(call["purpose"] == "generation" for call in calls),
        generation_output_token_metadata_missing_calls=sum(call["purpose"] == "generation" and call["output_tokens"] is None for call in calls),
        rejected_or_interrupted_turns=len(rejected), rejected_turns_with_generation_output_token_counts=sum(row["generation_output_tokens_all_calls"] is not None for row in rejected),
        output_tokens_on_rejected_turns=total_known(row["generation_output_tokens_all_calls"] for row in rejected) if rejected else 0,
        adaptive_DDEE_sequences_observed=len(ddee), adaptive_DDEE_selected_LLLS=sum(row.get("selected_LLLS_observed", False) for row in ddee),
        adaptive_DDEE_actual_LLLS=sum(row.get("actual_LLLS_observed", False) for row in ddee),
        small_returns=sum(row["return_to_small"] for row in turns), requests_after_small_return=sum(row["after_small_return"] for row in turns),
        validation_only_delivery_count=sum(row["status"] == "ok" for row in turns), quality=quality,
        audit_errors=errors, note="Counts describe the current snapshot. Repetitions, turns and shared templates/profile are dependent.")
    core.write(args.output_dir / "coverage.json", coverage)
    provenance.update(report_script_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        raw_backend_source="One backend_chat span per HTTP call; backend_response metadata retained even on later answer-validation failure.",
        input_sha256={str(path.resolve()): sha256(path.read_bytes()).hexdigest() for path in [args.workload, args.freeze, args.previous_freeze]},
        observation_sha256={str((args.run_root / row["attempt_directory"] / "observations.jsonl").resolve()):
            sha256((args.run_root / row["attempt_directory"] / "observations.jsonl").read_bytes()).hexdigest()
            for row in runs if (args.run_root / row["attempt_directory"] / "observations.jsonl").is_file()},
        offline_only=True, inference_performed=False, frozen_or_raw_source_changed=False)
    core.write(args.output_dir / "provenance.json", provenance)
    (args.output_dir / "report_details_source.py").write_bytes(Path(__file__).read_bytes())
    core.write(args.output_dir / "command.json", dict(script=str(Path(__file__).resolve()),
        arguments={key: [str(path.resolve()) for path in value] if isinstance(value, list) else
                   str(value.resolve()) if isinstance(value, Path) else value for key, value in vars(args).items()},
        reproduction="Use a new output directory; script depends on the unchanged sibling mixed-freeze adapter and frozen core analyzer."))
    (args.output_dir / "reporting_caveats.md").write_text(
        "# Supplementary reporting scope\n\n"
        "This snapshot supplements the frozen core analyzer. It does not replace its disjoint timing audit or its dependent-sequence analysis. "
        "During collection, an active session without finish.json is explicitly omitted; terminal batches include unfinished attempt directories.\n\n"
        "The core turn output-token field uses delivered generation metadata and is missing for rejected answers. These tables instead retain "
        "backend_response token counts from every actual backend_chat span, including generation later rejected by validation. Calls, client HTTP "
        "records and trace metadata describe the same operation and are not summed as separate calls. Unknown metadata remains missing.\n\n"
        "Backend load/prefill/decode durations overlap the measured wall spans. All-backend loading includes classifiers and generators; "
        "a cold classifier can pay the load which the diagnostic replay pays in generation. Generation-only load differences must not be "
        "presented as net loading savings. No backend duration is added to sequence or request totals.\n\n"
        "The primary sequence total is startup plus requests plus measured gaps. Cleanup is shown separately. Paired component deltas use "
        "adaptive minus comparator; positive values mean adaptive is slower or uses more tokens. Exact replay inputs do not ensure identical "
        "placement, output length, numerical execution, cache state or temperature. The replay also has a fixed last position. Direct residency-audit "
        "subtraction is a diagnostic and does not remove these confounds.\n\n"
        "DDEE route tables show selected and actual LLLS separately. A small-model return on turn4 has no observed following request. "
        "Report that absence explicitly; do not infer a fifth-turn saving from EEEE resident requests. Following-turn rows preserve their "
        "actual preceding transition, workload position and model. GPU allocation fractions are allocated bytes, not utilization or compute fractions.\n\n"
        "Per-pattern/per-repetition tables are descriptive. Three repetitions of a sequence are dependent, and shared templates/profile further "
        "limit independence. Review is optional input here; no useful-answer or quality–latency improvement follows from faster execution or "
        "validated delivery alone. The original interrupted validation-failure turn remains a failed answer after the exact audited sequence-eligibility repair.\n")
    print(json.dumps(coverage, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
