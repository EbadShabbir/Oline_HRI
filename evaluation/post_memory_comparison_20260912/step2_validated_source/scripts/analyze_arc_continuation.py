"""Audit diagnostic ARC item coverage across an interrupted and recovery segment.

This never executes inference or changes original artifacts. It retains the
parent's failed feasibility result and reports recovery accuracy separately.
The existing four-arm analyzer and its stricter validation are not modified.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re

import analyze_arc_capability as capability


PARENT_OBSERVATIONS_SHA256 = "b36374afae51d6724a83ed718de05068c5b0c4ed592e7d2a2bf5afc5d31a9314"
FULL_DATASET_SHA256 = "c0e858c862381a6ddf04de56f53d3d12113ac01920aa6a5f7fe30c297f80c4a5"
CONTINUATION_LAUNCHER_SHA256 = "376ce5716a946cd35149786ef2a7f225f9b2596b40b77d763f27c29b1bf1202d"
CONTINUATION_PROTOCOL_SHA256 = "8946eb8e90e5e4e996c879c41fe449d41599f456acf0bd9bc36af47844719b31"
PLACEMENT_EVIDENCE_SHA256 = "1ce3ee1dc8bf0464bcf78d2a1e6697dc82d131bbea1c42bda1826fb1d330e560"
DEFAULT_PLACEMENT_EVIDENCE = capability.PROJECT_ROOT / "evaluation/arc_capability_20260911/qwen25_3b_offload_logs.json"
START_LIMITS = {
    "min_available_ram_kib": 2359296, "max_swap_used_kib": 786432,
    "max_temperature_c_exclusive": 55, "fan_running": True,
    "thermal_trip_events_zero": True, "power_mode": "15W mode 0", "resident_model_count": 0,
}
RUNTIME_LIMITS = {
    "min_available_ram_kib": 786432, "max_swap_used_kib": 1048576,
    "max_temperature_c_exclusive": 68,
}
PARENT_ARCHIVES = {
    name: "parent_" + name for name in (
        "manifest.json", "observations.jsonl", "finish.json", "dataset.json",
        "execution_amendment.json", "execution_launcher.py", "execution_amendment.md",
    )
}


def require(condition, message, errors):
    if not condition:
        errors.append(message)


def file_hash(path):
    return sha256(path.read_bytes()).hexdigest()


def audit_placement(path, parent_path, continuation_path):
    """Bind curated primary service logs to both run windows and parse placement."""
    evidence = capability.read_json(path)
    if file_hash(path) != PLACEMENT_EVIDENCE_SHA256 or evidence.get("model") != capability.EXTRA:
        raise ValueError("placement evidence differs from the frozen primary log artifact")
    segments = {}
    for segment in evidence["segments"]:
        name, records = segment["segment"], segment["records"]
        if name not in {"original", "continuation"} or name in segments:
            raise ValueError("unexpected placement evidence segment")
        raw = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
        if len(records) != segment["selected_record_count"] or sha256(raw).hexdigest() != segment["selected_records_sha256"]:
            raise ValueError("curated placement record count/hash mismatch")
        run = parent_path if name == "original" else continuation_path
        start, finish = capability.read_json(run / "start.json"), capability.read_json(run / "finish.json")
        began = datetime.fromisoformat(start["captured_at"])
        ended = datetime.fromisoformat(finish["captured_at"])
        for record in records:
            if (record["boot_id"] != start["boot_id"].replace("-", "")
                    or record["unit"] != "ollama.service"
                    or not began <= datetime.fromisoformat(record["timestamp_utc"]) <= ended):
                raise ValueError("placement record falls outside the matching run/boot")
        messages = "\n".join(record["message"] for record in records)
        if evidence["model_blob_sha256"] not in messages:
            raise ValueError("placement records do not identify the expected model blob")
        offload = re.findall(r"offloaded (\d+)/(\d+) layers to GPU", messages)
        if len(offload) != 1:
            raise ValueError("placement evidence needs exactly one final offload decision")
        buffers = {}
        for device, kind, size in re.findall(
            r"\b(CUDA0|CUDA_Host|CPU)\s+(model|KV) buffer size\s*=\s*([0-9.]+) MiB", messages
        ):
            buffers[f"{device}_{kind}_mib"] = float(size)
        contexts = set(re.findall(r"\bn_ctx\s*=\s*(\d+)", messages))
        batches = set(re.findall(r"\bn_batch\s*=\s*(\d+)", messages))
        if contexts != {"2048"} or batches != {"512"}:
            raise ValueError("placement log context/batch differs from reported conditions")
        segments[name] = {
            "gpu_offloaded_layers": int(offload[0][0]), "total_layers": int(offload[0][1]),
            "buffers_mib": buffers, "context_length": 2048, "batch_size": 512,
            "record_count": len(records), "selected_records_sha256": segment["selected_records_sha256"],
            "fit_messages": [record["message"] for record in records
                             if "common_params_fit_impl" in record["message"] or "common_fit_params" in record["message"]],
        }
    if set(segments) != {"original", "continuation"}:
        raise ValueError("placement evidence must cover both segments")
    return {"source_path": str(path), "source_sha256": file_hash(path),
            "model_blob_sha256": evidence["model_blob_sha256"], "segments": segments,
            "finding": evidence["finding"],
            "limitation": "placement changed automatically; logs do not isolate its effect on latency from other state differences"}


def audit_policy(path, manifest, provenance, full_digest, parent_manifest, start, errors):
    amendment = capability.read_json(path / "execution_amendment.json")
    require(isinstance(amendment, dict), "effective execution amendment must be an object", errors)
    if not isinstance(amendment, dict):
        return {}
    require(amendment == manifest.get("execution_amendment"),
            "effective amendment differs between manifest and sidecar", errors)
    expected = {
        "schema_version": 1, "arm": "extra", "model": capability.EXTRA,
        "scope": "diagnostic_remaining_questions_continuation",
        "launcher_path": "scripts/run_arc_qwen25_continue.py",
        "launcher_archive": "execution_launcher.py",
        "launcher_sha256": CONTINUATION_LAUNCHER_SHA256,
        "protocol_amendment_path": "evaluation/arc_capability_20260911/continuation_protocol.md",
        "protocol_amendment_archive": "execution_amendment.md",
        "protocol_amendment_sha256": CONTINUATION_PROTOCOL_SHA256,
        "dataset_sha256": full_digest, "runtime_guards_unchanged": False,
        "start_limits": START_LIMITS, "runtime_limits": RUNTIME_LIMITS,
        "original_start_swap_ceiling_kib": 131072,
        "original_runtime_swap_ceiling_kib": 524288,
        "original_retry_start_limits": capability.EXTRA_START_LIMITS,
        "parent_feasibility_failure_preserved": True, "system_settings_changed": False,
    }
    for key, value in expected.items():
        require(amendment.get(key) == value and (
            type(value) is not bool or type(amendment.get(key)) is bool
        ), f"effective execution amendment has unexpected {key}", errors)
    require(amendment.get("original_runner_sha256") == parent_manifest["source_sha256"].get("scripts/run_arc_capability.py"),
            "effective amendment does not bind the original frozen runner", errors)
    require(bool(amendment.get("rationale")) and bool(amendment.get("interpretation")),
            "effective amendment lacks rationale or interpretation", errors)
    guards = {"runtime_available_RAM", "temperature", "boot_id", "thermal_trip_events",
              "single_model_residency", "model_artifact_admission"}
    require(set(amendment.get("unchanged_guards", [])) == guards,
            "effective amendment does not identify the expected unchanged guards", errors)
    archive_checks = {}
    for label, archive, digest_field in (
        ("execution_launcher", "execution_launcher.py", "launcher_sha256"),
        ("protocol", "execution_amendment.md", "protocol_amendment_sha256"),
    ):
        actual = file_hash(path / archive)
        declared = amendment.get(digest_field)
        require(actual == declared, f"{archive} differs from declared SHA-256", errors)
        archive_checks[label] = {"archive": archive, "sha256": actual}
    require(amendment.get("launcher_sha256") == provenance.get("launcher_sha256"),
            "continuation and effective amendment identify different launchers", errors)
    require((path / "execution_launcher.py").read_bytes() == (path / "continuation_launcher.py").read_bytes(),
            "two continuation launcher archives differ", errors)

    memory, temperatures = start.get("memory", {}), start.get("temperatures_c", {})
    available, swap = memory.get("mem_available_kib"), memory.get("swap_used_kib")
    require(capability.positive_number(available) and available >= START_LIMITS["min_available_ram_kib"],
            "continuation startup available RAM is below 2.25 GiB", errors)
    require(capability.positive_number(swap) and swap <= START_LIMITS["max_swap_used_kib"],
            "continuation startup swap exceeds 768 MiB", errors)
    valid_temperatures = (isinstance(temperatures, dict) and bool(temperatures)
                          and all(capability.positive_number(value) for value in temperatures.values()))
    require(valid_temperatures, "continuation startup temperature data invalid", errors)
    peak = max(temperatures.values()) if valid_temperatures else None
    require(peak is not None and peak < 55, "continuation startup temperature is not below 55 C", errors)
    require(start.get("resident_models") == [], "continuation starts with resident models", errors)
    require(capability.positive_number(start.get("fan_pwm"), zero=False), "continuation fan not running", errors)
    trips = start.get("thermal_trip_events")
    require(isinstance(trips, dict) and bool(trips) and all(type(v) is int and v == 0 for v in trips.values()),
            "continuation startup thermal-trip counters nonzero or missing", errors)
    require(bool(re.fullmatch(r"NV Power Mode:\s*15W\s*\n0\s*", start.get("power_mode", ""))),
            "continuation startup power mode differs from 15 W mode 0", errors)
    return {"metadata": amendment, "archive_checks": archive_checks,
            "start_snapshot": {"available_ram_kib": available, "swap_used_kib": swap,
                               "maximum_temperature_c": peak},
            "interpretation": "runtime swap allowance changed for diagnostic recovery; original failure is preserved"}


def audit_continuation(path, parent_path, full_dataset, parent_manifest, parent_rows, parent_finish):
    errors = []
    result = {"directory": str(path), "status": "missing", "complete": False,
              "validation_errors": errors, "observed_requests": 0, "accuracy": None,
              "artifact_sha256": {}}
    if not path.is_dir():
        return result, [], []
    rows, scores = [], []
    try:
        manifest = capability.read_json(path / "manifest.json")
        provenance = capability.read_json(path / "continuation.json")
        result["manifest"] = manifest
        result["continuation"] = provenance
        require(manifest.get("continuation") == provenance,
                "continuation sidecar differs from manifest", errors)
        require(provenance.get("schema_version") == 1 and provenance.get("scope") == "remaining_questions_after_interruption",
                "unknown continuation schema/scope", errors)
        require(provenance.get("diagnostic_continuation") is True,
                "this analyzer requires explicit diagnostic continuation", errors)
        require(Path(provenance.get("parent_run", "")).resolve() == parent_path,
                "continuation links a different parent run", errors)
        require(provenance.get("full_dataset_sha256") == FULL_DATASET_SHA256,
                "continuation full-dataset digest mismatch", errors)
        require(provenance.get("parent_archives") == PARENT_ARCHIVES,
                "unexpected parent archive mapping", errors)
        parent_hashes = provenance.get("parent_artifact_sha256", {})
        require(set(parent_hashes) == set(PARENT_ARCHIVES), "parent hash inventory mismatch", errors)
        for filename, archive in PARENT_ARCHIVES.items():
            actual_parent = file_hash(parent_path / filename)
            require(actual_parent == parent_hashes.get(filename) == file_hash(path / archive),
                    f"parent evidence changed or archive mismatch: {filename}", errors)
        require(parent_hashes.get("observations.jsonl") == PARENT_OBSERVATIONS_SHA256,
                "parent observations differ from the designated interrupted run", errors)
        accepted = [row["case_id"] for row in parent_rows if row["status"] == "ok"]
        expected_cases = [case for case in full_dataset["cases"] if case["id"] not in set(accepted)]
        indices = [i for i, case in enumerate(full_dataset["cases"], 1) if case["id"] not in set(accepted)]
        require(len(accepted) == 83 and indices == list(range(84, 101)),
                "parent does not define the expected 83 accepted plus 17 remaining items", errors)
        require(provenance.get("accepted_parent_case_ids") == accepted,
                "accepted-parent list differs from status-only selection", errors)
        require(provenance.get("remaining_case_ids") == [case["id"] for case in expected_cases]
                and provenance.get("original_indices") == indices,
                "continuation does not contain exactly the designated remaining items", errors)
        require(provenance.get("local_to_original_index") == {str(i): old for i, old in enumerate(indices, 1)},
                "local-to-original index mapping mismatch", errors)
        require(provenance.get("timing_scope") == "separate_segment_with_cold_load",
                "continuation does not disclose separate timing segment", errors)
        require(bool(provenance.get("reason")), "continuation lacks recovery rationale", errors)
        require(provenance.get("launcher_path") == "scripts/run_arc_qwen25_continue.py"
                and provenance.get("launcher_archive") == "continuation_launcher.py",
                "unexpected continuation launcher path/archive", errors)
        require(file_hash(path / "continuation_launcher.py") == provenance.get("launcher_sha256"),
                "continuation launcher archive hash mismatch", errors)

        derived_raw = (path / "dataset.json").read_bytes()
        derived = capability.decode_json(derived_raw)
        derived_cases = capability.validate_dataset(derived)
        require(derived_cases == expected_cases, "derived dataset cases/order differ from original remainder", errors)
        require(manifest.get("dataset_sha256") == provenance.get("derived_dataset_sha256") == sha256(derived_raw).hexdigest(),
                "derived input dataset SHA-256 mismatch", errors)
        require(manifest.get("artifact_dataset_sha256") == sha256(capability.canonical_bytes(derived)).hexdigest(),
                "derived canonical dataset SHA-256 mismatch", errors)
        require(manifest.get("dataset_metadata") == derived["metadata"], "derived dataset metadata mismatch", errors)
        source_metadata = {key: value for key, value in derived["metadata"].items() if key != "continuation"}
        require(source_metadata == full_dataset["metadata"], "original dataset provenance changed in derived metadata", errors)
        derived_provenance = derived["metadata"].get("continuation", {})
        require(derived_provenance.get("full_dataset_sha256") == FULL_DATASET_SHA256
                and derived_provenance.get("parent_observations_sha256") == PARENT_OBSERVATIONS_SHA256
                and derived_provenance.get("original_indices") == indices,
                "derived metadata linkage differs from original parent/remainder", errors)
        require(manifest.get("case_count") == 17, "continuation planned count is not 17", errors)
        for field in ("arm", "models", "source_sha256", "config", "system_prompt", "generation_seed",
                      "residency_policy", "ollama_version"):
            require(manifest.get(field) == parent_manifest.get(field),
                    f"continuation changes original inference identity/configuration: {field}", errors)

        start = capability.read_json(path / "start.json")
        result["effective_policy"] = audit_policy(path, manifest, provenance, FULL_DATASET_SHA256,
                                                   parent_manifest, start, errors)
        rows = capability.read_jsonl(path / "observations.jsonl")
        result["observed_requests"] = len(rows)
        require(len(rows) <= 17, "continuation contains unexpected extra attempts", errors)
        for index, (row, case) in enumerate(zip(rows, expected_cases), 1):
            problems, correct = capability.validate_record(row, case, index, "extra")
            errors.extend(problems)
            scores.append(correct)
        telemetry = capability.read_jsonl(path / "telemetry.jsonl")
        result["telemetry"] = capability.telemetry_metrics(telemetry)
        result["timing"] = capability.latency_metrics(rows)
        result["diagnostic_counts"] = capability.partial_diagnostics(expected_cases, rows, scores)
        try:
            finish = capability.read_json(path / "finish.json")
        except FileNotFoundError:
            result["status"] = "incomplete"
            finish = {}
        else:
            result["finish"] = finish
            result["status"] = finish.get("status", "incomplete")
            require(finish.get("planned_cases") == 17 and finish.get("completed_cases") == len(rows),
                    "continuation finish count mismatch", errors)
            for field in ("boot_id", "thermal_trip_events"):
                require(start.get(field) is not None and start.get(field) == finish.get(field),
                        f"continuation {field} changed within segment", errors)
            require(finish.get("cleanup_errors") == [] and finish.get("resident_models") == [],
                    "continuation cleanup is incomplete", errors)
        if result["status"] in capability.COMPLETE_STATUSES:
            require(len(rows) == 17, "complete continuation lacks all 17 designated requests", errors)
            require(not any(finish.get(key) for key in (
                "failure", "guard_violation", "telemetry_reader_error", "cleanup_errors")),
                    "complete continuation has a recorded execution/guard failure", errors)
            require(bool(telemetry), "completed continuation has no telemetry", errors)
            if telemetry:
                require(result["telemetry"]["peak_swap_used_mb"] <= 1024
                        and result["telemetry"]["peak_temperature_c"] < 68,
                        "completed continuation crossed its diagnostic runtime limits", errors)
            summary = capability.read_json(path / "summary.json")
            require(summary.get("status") == result["status"] and summary.get("correct") == sum(scores)
                    and summary.get("attempted") == len(rows), "continuation saved summary differs from raw scoring", errors)
            telemetry_summary = capability.read_json(path / "telemetry_summary.json")
            require(telemetry_summary.get("sample_count") == len(telemetry), "telemetry summary count mismatch", errors)
        require(parent_finish.get("status") == "interrupted"
                and parent_finish.get("failure", {}).get("message") == "swap use crossed the runtime ceiling",
                "original parent feasibility failure is not preserved", errors)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        errors.append(f"continuation artifact audit: {error}")
    result["complete"] = (result["status"] in capability.COMPLETE_STATUSES and len(rows) == 17
                          and all(row.get("status") == "ok" for row in rows) and not errors)
    if result["status"] in capability.COMPLETE_STATUSES and errors:
        result["status"] = "invalid_artifacts"
    for name in ("manifest.json", "dataset.json", "continuation.json", "continuation_launcher.py",
                 "execution_amendment.json", "execution_launcher.py", "execution_amendment.md",
                 "start.json", "finish.json", "observations.jsonl", "telemetry.jsonl",
                 "summary.json", "telemetry_summary.json", *PARENT_ARCHIVES.values()):
        file = path / name
        if file.is_file():
            result["artifact_sha256"][name] = file_hash(file)
    return result, rows, scores


def build_report(dataset_path, run_root, continuation_path, placement_path=DEFAULT_PLACEMENT_EVIDENCE):
    full_digest = file_hash(dataset_path)
    if full_digest != FULL_DATASET_SHA256:
        raise ValueError("analysis is restricted to the original frozen 100-case dataset")
    full = capability.read_json(dataset_path)
    cases = capability.validate_dataset(full)
    baseline = capability.analyze(dataset_path, run_root)
    parent_path = (run_root / "04_qwen25_3b").resolve()
    parent = baseline["arms"]["extra"]
    if (parent["status"] != "interrupted" or parent["observed"] != 84 or parent["validation_errors"]
            or file_hash(parent_path / "observations.jsonl") != PARENT_OBSERVATIONS_SHA256):
        raise ValueError("parent must be the independently validated interrupted 84-attempt run")
    parent_manifest = capability.read_json(parent_path / "manifest.json")
    parent_finish = capability.read_json(parent_path / "finish.json")
    parent_rows = capability.read_jsonl(parent_path / "observations.jsonl")
    if any(row["status"] != "ok" for row in parent_rows[:83]) or parent_rows[83]["status"] != "interrupted":
        raise ValueError("parent statuses differ from the designated 83 accepted plus interrupted item")
    continuation, continuation_rows, continuation_scores = audit_continuation(
        continuation_path, parent_path, full, parent_manifest, parent_rows, parent_finish)
    result = {
        "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "analysis_source_sha256": file_hash(Path(__file__)),
        "reused_validator_source_sha256": file_hash(Path(capability.__file__)),
        "full_dataset_sha256": full_digest, "dataset_metadata": full["metadata"],
        "parent": parent, "continuation": continuation,
        "original_four_arm_evaluation_complete": baseline["all_arms_complete"],
        "baseline_arms": {key: value for key, value in baseline["arms"].items() if key != "extra"},
        "cross_arm_validation_errors": baseline["cross_arm_validation_errors"],
        "composite": None,
        "execution_cost": {
            "parent_attempts_including_interrupted": len(parent_rows),
            "continuation_attempts": len(continuation_rows),
            "all_attempts": len(parent_rows) + len(continuation_rows),
            "all_attempt_request_seconds": capability.distribution(
                [row["wall_ns"] / 1e9 for row in parent_rows + continuation_rows]),
            "parent_first_request_seconds": parent["timing"]["first_request_seconds"],
            "continuation_first_request_seconds": continuation.get("timing", {}).get("first_request_seconds"),
            "scope": "sum/distribution of all attempt wall times, including failed item 84 and both cold loads; excludes recovery downtime",
        },
        "interpretation": "diagnostic composite item accuracy; original 512 MiB runtime-limit feasibility failure is unchanged",
    }
    if not continuation["complete"]:
        result["status"] = "diagnostic_continuation_incomplete"
        return result
    result["backend_placement"] = audit_placement(placement_path, parent_path, continuation_path)
    merged = parent_rows[:83] + continuation_rows
    merged_scores = [row["correct"] for row in parent_rows[:83]] + continuation_scores
    observation_hashes = {source: file_hash(source / "observations.jsonl")
                          for source in (parent_path, continuation_path)}
    items = []
    for index, (case, row, correct) in enumerate(zip(cases, merged, merged_scores), 1):
        source = parent_path if index <= 83 else continuation_path
        items.append({
            "original_index": index, "case_id": case["id"], "subset": case["subset"],
            "question": case["question"], "choices": case["choices"],
            "source_run": str(source), "source_local_index": row["index"],
            "source_observations_sha256": observation_hashes[source],
            "answer": row.get("answer"), "gold": case["answerKey"], "correct": correct,
            "request_status": row["status"], "actual_model": row.get("generation", {}).get("model"),
            "placement_segment": "original" if index <= 83 else "continuation",
            "gpu_offloaded_layers": result["backend_placement"]["segments"][
                "original" if index <= 83 else "continuation"]["gpu_offloaded_layers"],
        })
    composite = {"status": "complete_item_coverage_across_two_segments",
                 "score": capability.score_group(cases, merged, merged_scores),
                 "by_subset": {}, "items": items, "paired_descriptive": {},
                 "retried_original_indices": [84],
                 "parent_interrupted_attempt": parent_rows[83],
                 "selection_rule": "first 83 parent status-ok outputs plus the designated recovery attempt for each original item 84–100; no best-of-output selection",
                 "scope": "diagnostic composite across changed startup/runtime conditions; not an uninterrupted successful deployment run"}
    for subset in sorted({case["subset"] for case in cases}):
        indices = [i for i, case in enumerate(cases) if case["subset"] == subset]
        composite["by_subset"][subset] = capability.score_group(
            [cases[i] for i in indices], [merged[i] for i in indices], [merged_scores[i] for i in indices])
    for arm, directory, _ in capability.ARMS:
        if arm == "extra" or not baseline["arms"][arm]["complete"]:
            continue
        other_rows = capability.read_jsonl(run_root / directory / "observations.jsonl")
        composite["paired_descriptive"][arm] = capability.paired(
            arm, "extra_diagnostic_composite", [row["correct"] for row in other_rows], merged_scores, cases)
    result["composite"] = composite
    result["status"] = "diagnostic_composite_complete"
    return result


def render_markdown(report):
    continuation, parent = report["continuation"], report["parent"]
    composite = report["composite"]
    lines = ["Qwen2.5 3B diagnostic ARC continuation", "",
             f"Generated {report['created_at']}. Status: **{report['status']}**.", "",
             "The original Qwen2.5 run remains **interrupted by the 512 MiB runtime swap limit**. "
             "This report keeps that feasibility failure and separately evaluates the user-requested "
             "recovery of original questions 84–100. Questions 1–83 are not replayed; their accepted "
             "outputs are retained regardless of correctness.", ""]
    if composite:
        lines.extend([
            f"The recovery segment completed {continuation['observed_requests']}/17 designated requests. "
            f"The resulting **diagnostic composite** is {capability.score_text(composite['score'])}. "
            "This combines 83 accepted parent answers with 17 designated recovery outcomes under "
            "changed resource limits. It is not a successful uninterrupted 100-question run.", "",
            "| System / result type | Overall | ARC-Easy | ARC-Challenge |",
            "| --- | --- | --- | --- |",
        ])
        for arm in ("small", "large", "cascade"):
            baseline = report["baseline_arms"][arm]
            if baseline["complete"]:
                lines.append(f"| {baseline['title']} / original completed run | {capability.score_text(baseline['score'])} | "
                             f"{capability.score_text(baseline['by_subset']['ARC-Easy'])} | "
                             f"{capability.score_text(baseline['by_subset']['ARC-Challenge'])} |")
        lines.extend([
            f"| Qwen2.5 3B / diagnostic composite | {capability.score_text(composite['score'])} | "
            f"{capability.score_text(composite['by_subset']['ARC-Easy'])} | "
            f"{capability.score_text(composite['by_subset']['ARC-Challenge'])} |", "",
            "Original question 84 is represented twice in the execution record: its parent attempt "
            "was interrupted and its designated recovery attempt contributes to composite item scoring. "
            "The interrupted parent's raw answer is retained as evidence and is not substituted for "
            "the recovery output. Per-item source directory, source observation hash, local/original "
            "index, question, choices, label, and correctness are recorded in "
            "[composite_answers.jsonl](composite_answers.jsonl) and analysis.json.", "",
        ])
    else:
        lines.extend([
            f"The continuation is `{continuation['status']}` with "
            f"{continuation['observed_requests']}/17 observations. Composite 100-question accuracy "
            "is withheld until all designated requests complete and the artifacts validate.", "",
        ])
    parent_diagnostic = parent.get("partial_diagnostics", {})
    child_diagnostic = continuation.get("diagnostic_counts", {})
    lines.extend([
        f"Parent progress: 84 attempted requests, 83 successful requests, "
        f"{parent_diagnostic.get('correct_successful_answers', 'unknown')} correct accepted answers, "
        "and one interrupted request. "
        f"Recovery progress: {child_diagnostic.get('attempted_requests', 0)} attempted, "
        f"{child_diagnostic.get('successful_requests', 0)} successful, "
        f"{child_diagnostic.get('correct_successful_answers', 0)} correct accepted answers.", "",
        "| Segment | Attempted requests | First request s | All mean / median / p95 s | "
        "Later mean / median / p95 s | Peak RAM / swap MiB | Peak temperature C |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ])
    for title, segment, count in (
        ("Original interrupted parent", parent, parent["observed"]),
        ("Diagnostic recovery", continuation, continuation["observed_requests"]),
    ):
        timing, telemetry = segment.get("timing"), segment.get("telemetry", {})
        if not timing:
            continue
        all_time, later = timing["all_requests_seconds"], timing["later_requests_seconds"]
        lines.append(f"| {title} | {count} | {capability.number(timing['first_request_seconds'])} | "
                     f"{' / '.join(capability.number(all_time[key]) for key in ('mean', 'p50', 'p95'))} | "
                     f"{' / '.join(capability.number(later[key]) for key in ('mean', 'p50', 'p95'))} | "
                     f"{capability.number(telemetry.get('peak_ram_used_mb'), 0)} / "
                     f"{capability.number(telemetry.get('peak_swap_used_mb'), 0)} | "
                     f"{capability.number(telemetry.get('peak_temperature_c'))} |")
    cost = report["execution_cost"]
    lines.extend([
        "", f"Total observed execution cost is {cost['all_attempts']} attempts and "
        f"{capability.number(cost['all_attempt_request_seconds']['sum'])} seconds of request wall time, "
        "including the interrupted parent request and both segment cold loads. This sum excludes "
        "the recovery gap, device checks, and idle time between segments; it must not be reported "
        "as uninterrupted end-to-end completion latency. Full call load/prefill/decode distributions "
        "and all-attempt timing are retained in analysis.json.", "",
        "The recovery uses an explicitly documented diagnostic policy: startup available RAM "
        "at least 2.25 GiB and swap at most 768 MiB; runtime available RAM at least 768 MiB, "
        "swap at most **1 GiB**, and temperature below 68 C. Startup temperature below 55 C, "
        "active fan, thermal-trip/reset checks, one resident model, model-artifact checks, and "
        "cleanup remain required. The earlier parent's amended startup limits were 2.5 GiB RAM "
        "and 384 MiB swap, with the original **512 MiB runtime swap limit**. The runtime swap "
        "policy changed for this recovery; no claim is made that the stricter feasibility "
        "requirement was met.", "",
        "The parent manifest, observations, finish record, dataset, startup amendment, launcher, "
        "and protocol text are archived in the recovery directory and hash-checked against the "
        "untouched originals. The diagnostic launcher and new policy are archived separately. "
        "Original inference source hashes, model artifact/digest, prompt, schema, decoding settings, "
        "and question/choice order are compared with the parent. Additional launcher behavior "
        "and its effective resource policy are disclosed independently of those unchanged sources.", "",
    ])
    placement = report.get("backend_placement")
    if placement:
        old, new = placement["segments"]["original"], placement["segments"]["continuation"]
        lines.extend([
            "**Backend placement also changed between segments.** The original run offloaded "
            f"{old['gpu_offloaded_layers']}/{old['total_layers']} layers to GPU; the continuation "
            f"offloaded {new['gpu_offloaded_layers']}/{new['total_layers']} and used mixed CPU/GPU "
            "execution. Both logs show context 2048 and batch 512. The continuation timing is "
            f"therefore not an all-layers-on-GPU 3B measurement, and the {composite['score']['correct']}/100 diagnostic score "
            "combines item outputs across two placements.", "",
            "| Segment | Layers offloaded to GPU | CUDA model buffer MiB | Host model buffer MiB | "
            "CPU KV / CUDA KV MiB |", "| --- | --- | --- | --- | --- |",
        ])
        for name, data in placement["segments"].items():
            buffers = data["buffers_mib"]
            lines.append(f"| {name} | {data['gpu_offloaded_layers']}/{data['total_layers']} | "
                         f"{capability.number(buffers.get('CUDA0_model_mib'))} | "
                         f"{capability.number(buffers.get('CUDA_Host_model_mib'))} | "
                         f"{capability.number(buffers.get('CPU_KV_mib'))} / "
                         f"{capability.number(buffers.get('CUDA0_KV_mib'))} |")
        lines.extend([
            "", "The backend's automatic fitting logs show that it retained 37 GPU layers with "
            "2692 MiB free for the original load, but selected 30 with 2337 MiB free for the "
            "continuation to retain its 1024 MiB free-device-memory target. These logs establish "
            "the placement decision; they do not isolate how much of the observed timing "
            "difference placement caused versus other device-state differences.", "",
            f"Primary evidence: [curated Ollama loading and fitting logs]({placement['source_path']}), "
            f"SHA-256 `{placement['source_sha256']}`. Record hashes, timestamps, boot IDs, model "
            "blob identity, run windows, and final offload counts were independently checked.", "",
        ])
    policy = continuation.get("effective_policy", {})
    if policy:
        metadata = policy["metadata"]
        lines.extend([
            f"Diagnostic launcher SHA-256: `{metadata.get('launcher_sha256')}`. "
            f"Diagnostic protocol SHA-256: `{metadata.get('protocol_amendment_sha256')}`. "
            f"Startup snapshot: `{json.dumps(policy['start_snapshot'], sort_keys=True)}`.", "",
        ])
    if composite and composite["paired_descriptive"]:
        lines.extend([
            "| Reference → diagnostic composite | Both correct | Reference only | Composite only | Neither | "
            "Composite minus reference | Exact paired p |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ])
        for name, pair in composite["paired_descriptive"].items():
            lines.append(f"| {name} → 3B composite | {pair['both_correct']} | {pair['first_only_correct']} | "
                         f"{pair['second_only_correct']} | {pair['neither_correct']} | "
                         f"{pair['second_minus_first_percentage_points']:+.1f} pp | "
                         f"{pair['exact_mcnemar_two_sided_p']:.4g} |")
        lines.extend(["", "Intervals and paired tests are descriptive and unadjusted for multiple comparisons. "
                      "The pooled Wilson interval is approximate for this equal-stratum sample. "
                      "The composite has a recovery attempt and changed device/resource conditions. "
                      "A nonsignificant difference does not establish quality equivalence.", ""])
    lines.extend([
        "The benchmark is the same 50 ARC-Easy and 50 ARC-Challenge questions from "
        "[AllenAI ARC](https://huggingface.co/datasets/allenai/ai2_arc), "
        "[Clark et al. (2018)](https://arxiv.org/abs/1803.05457), CC-BY-SA-4.0. "
        "It measures zero-shot schema-constrained answer-label generation with 2,048-token context, "
        "192-token output limit, temperature 0, seed 42, and thinking disabled. "
        "Public data may occur in model training. This is neither a full ARC leaderboard evaluation "
        "nor personal-memory, conversational, or spoken robot evaluation. "
        "Qwen2.5 3B Q3_K_S differs in model family and quantization from the Qwen3 Q4_K_M pair; "
        "the comparison does not isolate parameter count.", "",
        f"Full frozen dataset SHA-256: `{report['full_dataset_sha256']}`. "
        f"Parent: `{parent['directory']}`. Recovery: `{continuation['directory']}`.", "",
    ])
    if continuation.get("finish", {}).get("failure"):
        lines.extend([f"Recovery failure: `{json.dumps(continuation['finish']['failure'], sort_keys=True)}`.", ""])
    if continuation["validation_errors"]:
        lines.extend(["Validation findings:", ""])
        lines.extend(f"- {issue}" for issue in continuation["validation_errors"])
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=capability.DEFAULT_DATASET)
    parser.add_argument("--run-root", type=Path, default=capability.DEFAULT_RUN_ROOT)
    parser.add_argument("--continuation-run", type=Path, required=True)
    parser.add_argument("--placement-evidence", type=Path, default=DEFAULT_PLACEMENT_EVIDENCE)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    run_root, continuation_path, output = args.run_root.resolve(), args.continuation_run.resolve(), args.output_dir.resolve()
    if output == run_root or run_root in output.parents or output == continuation_path or continuation_path in output.parents:
        parser.error("analysis outputs must remain outside immutable raw run directories")
    targets = [output / "analysis.json", output / "report.md", output / "composite_answers.jsonl"]
    if any(target.exists() for target in targets):
        parser.error("choose a fresh output directory; existing analysis artifacts are not overwritten")
    report = build_report(args.dataset.resolve(), run_root, continuation_path, args.placement_evidence.resolve())
    markdown = render_markdown(report)
    output.mkdir(parents=True, exist_ok=True)
    with targets[0].open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    with targets[1].open("x", encoding="utf-8") as stream:
        stream.write(markdown)
    if report["composite"] is not None:
        with targets[2].open("x", encoding="utf-8") as stream:
            for item in report["composite"]["items"]:
                stream.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "analysis": str(targets[0]), "report": str(targets[1]),
                      "composite_answers": str(targets[2]) if report["composite"] is not None else None}))
    return 0 if report["composite"] is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
