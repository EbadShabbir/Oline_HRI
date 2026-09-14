"""Independently validate and summarize the four serialized ARC capability arms.

Uses only the Python standard library, never imports the inference runner, and
never modifies raw artifacts. Missing/incomplete/invalid arms have no completed
accuracy estimate. Output files are created exclusively, so reruns need a new
output directory or filenames removed deliberately by the caller.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from itertools import combinations
import json
import math
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "evaluation/arc_capability_20260911/dataset.json"
DEFAULT_RUN_ROOT = Path(
    "/home/b2jetson/.local/share/oline-hri/evaluation-runs/arc-capability-20260911"
)
SMALL, LARGE, EXTRA = "qwen3:0.6b", "qwen3:1.7b", "qwen2.5:3b-instruct-q3_K_S"
ARMS = (
    ("small", "01_small", "Qwen3 0.6B"),
    ("large", "02_large", "Qwen3 1.7B"),
    ("cascade", "03_cascade", "CLARA generator selection"),
    ("extra", "04_qwen25_3b", "Qwen2.5 3B Q3_K_S"),
)
EXPECTED_MODELS = {
    "small": {SMALL}, "large": {LARGE}, "cascade": {SMALL, LARGE}, "extra": {EXTRA},
}
COMPLETE_STATUSES = {"complete", "complete_with_errors"}
SYSTEM_PROMPT = (
    "Answer the multiple-choice science question. Choose exactly one of the "
    "provided option labels. Return only a JSON object with one key, answer, "
    'whose value is that label, for example {"answer":"A"}. '
    "Do not include an explanation."
)
EXTRA_START_LIMITS = {
    "min_available_ram_kib": 2621440, "max_swap_used_kib": 393216,
    "max_temperature_c_exclusive": 55, "fan_running": True,
    "thermal_trip_events_zero": True, "power_mode": "15W mode 0",
    "resident_model_count": 0,
}
UNCHANGED_RUNTIME_LIMITS = {
    "min_available_ram_kib": 786432, "max_swap_used_kib": 524288,
    "max_temperature_c_exclusive": 68,
}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"nonstandard JSON constant: {value}")


def decode_json(value):
    return json.loads(value, object_pairs_hook=unique_object, parse_constant=reject_constant)


def canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def read_json(path):
    return decode_json(path.read_bytes())


def read_jsonl(path):
    records = []
    with path.open(encoding="utf-8") as stream:
        for index, line in enumerate(stream, 1):
            if not line.strip():
                raise ValueError(f"blank JSONL record at {path.name}:{index}")
            try:
                record = decode_json(line)
            except (ValueError, TypeError) as error:
                raise ValueError(f"invalid JSONL at {path.name}:{index}: {error}") from error
            if not isinstance(record, dict):
                raise ValueError(f"non-object JSONL at {path.name}:{index}")
            records.append(record)
    return records


def distribution(values):
    values = sorted(values)
    if not values:
        return {"n": 0, "mean": None, "p50": None, "p95": None,
                "min": None, "max": None, "sum": 0}

    def quantile(q):
        position = (len(values) - 1) * q
        lower, upper = math.floor(position), math.ceil(position)
        return values[lower] + (values[upper] - values[lower]) * (position - lower)

    return {"n": len(values), "mean": math.fsum(values) / len(values),
            "p50": quantile(.5), "p95": quantile(.95), "min": values[0],
            "max": values[-1], "sum": math.fsum(values)}


def wilson(correct, count):
    if not count:
        return None
    z = 1.959963984540054
    p, z2 = correct / count, z * z
    center = (p + z2 / (2 * count)) / (1 + z2 / count)
    half = z * math.sqrt(p * (1 - p) / count + z2 / (4 * count * count)) / (1 + z2 / count)
    return [max(0, center - half), min(1, center + half)]


def exact_mcnemar(first_only, second_only):
    """Two-sided exact conditional binomial test on discordant pairs."""
    n = first_only + second_only
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(first_only, second_only) + 1))
    return min(1.0, 2 * tail / (2 ** n))


def question_text(case):
    return case["question"] + "\n\n" + "\n".join(
        f'{choice["label"]}. {choice["text"]}' for choice in case["choices"]
    )


def parse_answer(content, labels):
    value = decode_json(content)
    if (not isinstance(value, dict) or set(value) != {"answer"}
            or not isinstance(value["answer"], str) or value["answer"] not in labels):
        raise ValueError("answer is not exactly one available label")
    return value["answer"]


def positive_number(value, *, zero=True):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and (value >= 0 if zero else value > 0))


def validate_dataset(dataset):
    if not isinstance(dataset, dict) or not isinstance(dataset.get("metadata"), dict):
        raise ValueError("frozen dataset has no metadata")
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("frozen dataset has no cases")
    seen = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("dataset case must be an object")
        for name in ("id", "subset", "question", "answerKey"):
            if not isinstance(case.get(name), str) or not case[name]:
                raise ValueError(f"invalid dataset field {name}")
        if case["id"] in seen:
            raise ValueError(f"duplicate dataset ID {case['id']}")
        seen.add(case["id"])
        choices = case.get("choices")
        if not isinstance(choices, list) or len(choices) < 2:
            raise ValueError("dataset case needs at least two choices")
        labels = []
        for choice in choices:
            if not isinstance(choice, dict) or any(
                not isinstance(choice.get(field), str) or not choice[field]
                for field in ("label", "text")
            ):
                raise ValueError("invalid dataset choice")
            labels.append(choice["label"])
        if len(labels) != len(set(labels)) or case["answerKey"] not in labels:
            raise ValueError("invalid dataset answer labels")
    return cases


def validate_record(record, case, index, arm):
    errors = []

    def check(condition, message):
        if not condition:
            errors.append(f"case {index} ({case['id']}): {message}")

    for field, expected in (("case_id", case["id"]), ("subset", case["subset"]),
                            ("gold", case["answerKey"]), ("index", index), ("arm", arm)):
        check(record.get(field) == expected, f"{field} differs from frozen case")
    check(record.get("status") in {"ok", "error", "interrupted"}, "invalid status")
    check(type(record.get("correct")) is bool, "correct must be a boolean")
    check(positive_number(record.get("wall_ns")), "invalid wall duration")
    labels = [choice["label"] for choice in case["choices"]]
    selected = record.get("selected_model")
    check(selected is None or selected in EXPECTED_MODELS[arm], "unpermitted selected model")
    route = record.get("route")
    if arm != "cascade":
        check(route is None, "single-model arm contains a route")
        if record.get("status") == "ok":
            check(selected == next(iter(EXPECTED_MODELS[arm])), "wrong sole model")
    elif route is not None:
        check(isinstance(route, dict), "route must be an object")
        if isinstance(route, dict):
            decision = route.get("decision", {})
            check(isinstance(decision, dict), "route decision must be an object")
            if isinstance(decision, dict):
                check(type(decision.get("memory_required")) is bool, "invalid memory decision")
                size = decision.get("model_size")
                check(size in {"small", "large"}, "invalid size decision")
                if size in {"small", "large"}:
                    check(selected == {"small": SMALL, "large": LARGE}[size],
                          "selected model disagrees with final route")

    calls = record.get("calls")
    if not isinstance(calls, list):
        check(False, "calls must be a list")
        calls = []
    generators, classifiers = [], []
    for call_index, call in enumerate(calls, 1):
        if not isinstance(call, dict):
            check(False, f"call {call_index} must be an object")
            continue
        purpose = call.get("purpose")
        check(purpose in {"generation", "classifier"}, f"call {call_index} unknown purpose")
        check(positive_number(call.get("wall_ns")), f"call {call_index} invalid wall time")
        requested = call.get("requested_model")
        check(requested in EXPECTED_MODELS[arm], f"call {call_index} unpermitted model")
        if "model" in call:
            check(call["model"] == requested, f"call {call_index} requested/model mismatch")
        generated = call.get("generation")
        if generated is not None:
            check(isinstance(generated, dict), f"call {call_index} invalid generation")
            if isinstance(generated, dict):
                check(generated.get("model") == requested == call.get("actual_model"),
                      f"call {call_index} actual model mismatch")
                for field in ("total_duration_ns", "load_duration_ns", "eval_duration_ns",
                              "prompt_eval_duration_ns", "prompt_eval_count", "eval_count"):
                    check(positive_number(generated.get(field)),
                          f"call {call_index} invalid {field}")
        request = call.get("request", {})
        check(isinstance(request, dict), f"call {call_index} request must be an object")
        if not isinstance(request, dict):
            request = {}
        check(request.get("temperature") == 0 and request.get("seed") == 42,
              f"call {call_index} decoding mismatch")
        if purpose == "generation":
            generators.append(call)
            check(requested == selected, "generation model differs from selected model")
            expected_messages = [{"role": "system", "content": SYSTEM_PROMPT},
                                 {"role": "user", "content": question_text(case)}]
            check(call.get("messages") == expected_messages,
                  "generator input differs from common gold-free prompt")
            expected_schema = {"type": "object", "properties": {
                "answer": {"type": "string", "enum": labels}},
                "required": ["answer"], "additionalProperties": False}
            check(request.get("response_format") == expected_schema,
                  "answer schema differs from all offered native labels")
        elif purpose == "classifier":
            classifiers.append(call)
            check(arm == "cascade" and requested == SMALL,
                  "classifier outside cascade/small model")
            messages = call.get("messages", [])
            if messages and isinstance(messages[-1], dict):
                # Production router normalizes horizontal whitespace before punctuation.
                content = messages[-1].get("content", "")
                try:
                    envelope = decode_json(content.split("\n", 1)[1])
                    normalized = re.sub(r"[ \t]+(?=[,.;:!?])", "", question_text(case).strip())
                    check(envelope == {"prior_turns": [], "current_user_text": normalized},
                          "classifier input differs from full gold-free case")
                except (IndexError, ValueError, TypeError, AttributeError):
                    check(False, "cannot independently parse classifier input")
            else:
                check(False, "classifier messages missing")
            if call.get("status") == "ok" and isinstance(generated, dict):
                try:
                    classified = decode_json(generated.get("content"))
                    fields = set(request.get("response_format", {}).get("properties", {}))
                    if len(classifiers) == 1:
                        check(fields == {"form", "memory_required"}, "memory classifier schema mismatch")
                        check(isinstance(classified, dict) and set(classified) == fields
                              and classified.get("form") in {"question", "statement", "request"}
                              and type(classified.get("memory_required")) is bool,
                              "raw memory classifier output is invalid")
                    else:
                        check(fields == {"model_size"}, "size classifier schema mismatch")
                        check(isinstance(classified, dict) and set(classified) == fields
                              and classified.get("model_size") in {"small", "large"},
                              "raw size classifier output is invalid")
                    check(generated.get("done_reason") != "length", "successful classifier was truncated")
                except (ValueError, TypeError, AttributeError):
                    check(False, "cannot independently parse classifier output")

    check(len(generators) <= 1, "multiple generator attempts")
    check(len(classifiers) <= (2 if arm == "cascade" else 0), "unexpected classifier count")
    if record.get("status") == "ok":
        check(len(generators) == 1, "successful case lacks exactly one generator")
        check(len(classifiers) == (2 if arm == "cascade" else 0),
              "successful case has unexpected classifier count")
        check(all(call.get("status") == "ok" for call in calls),
              "successful case includes failed call")
        if arm == "cascade":
            check(route is not None, "successful cascade case has no route")
    generation = record.get("generation")
    raw_answer = None
    if generation is not None:
        check(isinstance(generation, dict), "record generation is not an object")
        if isinstance(generation, dict):
            check(generation.get("model") == selected, "record actual model mismatch")
            if generators:
                check(generators[0].get("generation") == generation,
                      "record generation differs from raw call")
            try:
                raw_answer = parse_answer(generation.get("content"), labels)
                if generation.get("done_reason") == "length":
                    raw_answer = None
            except (ValueError, TypeError):
                raw_answer = None
    if record.get("status") == "ok":
        check(raw_answer is not None, "successful answer cannot be independently parsed")
        check(record.get("answer") == raw_answer, "saved answer differs from raw output")
    expected_correct = bool(record.get("status") == "ok" and raw_answer == case["answerKey"])
    check(record.get("correct") is expected_correct, "saved correctness differs from raw scoring")
    if arm == "cascade" and isinstance(route, dict) and len(classifiers) == 2:
        for call, name in zip(classifiers, ("memory_required_generation", "model_size_generation")):
            check(call.get("generation") == route.get(name), "route raw output differs from call")
        try:
            decision = route["decision"]
            for field, source_key, call_index in (
                ("memory_required", "memory_decision_source", 0),
                ("model_size", "model_size_decision_source", 1),
            ):
                if route.get(source_key) == "model":
                    decoded = decode_json(classifiers[call_index]["generation"]["content"])
                    check(decoded[field] == decision[field], "unmodified route disagrees with raw classifier")
            if route.get("model_size_decision_source") == "policy_complex":
                check(decision["model_size"] == "large", "complexity override failed to select large")
        except (KeyError, ValueError, TypeError):
            check(False, "cannot verify route provenance")
    return errors, expected_correct


def telemetry_metrics(records):
    previous = None
    for sample in records:
        timestamp = sample.get("monotonic_ns")
        if not positive_number(timestamp) or (previous is not None and timestamp <= previous):
            raise ValueError("telemetry timestamps are invalid or unordered")
        previous = timestamp
        for field in ("ram", "swap"):
            if not isinstance(sample.get(field), dict) or not positive_number(sample[field].get("used_mb")):
                raise ValueError(f"invalid telemetry {field}")
        sensors = sample.get("temperatures_c")
        if not isinstance(sensors, dict) or not sensors or any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            for value in sensors.values()
        ):
            raise ValueError("invalid telemetry temperatures")
    return {"sample_count": len(records),
            "peak_ram_used_mb": max((r["ram"]["used_mb"] for r in records), default=None),
            "peak_swap_used_mb": max((r["swap"]["used_mb"] for r in records), default=None),
            "peak_temperature_c": max((max(r["temperatures_c"].values()) for r in records), default=None),
            "sample_interval_ms": 500,
            "scope": "whole-device samples during inference and cleanup, not model-only memory"}


def latency_metrics(records):
    values = [record["wall_ns"] / 1e9 for record in records if positive_number(record.get("wall_ns"))]
    purposes = {}
    for purpose in ("classifier", "generation"):
        calls = [call for r in records for call in r.get("calls", [])
                 if isinstance(call, dict) and call.get("purpose") == purpose]
        metrics = {"call_count": len(calls),
                   "failed_calls": sum(call.get("status") != "ok" for call in calls),
                   "wall_seconds": distribution([call["wall_ns"] / 1e9 for call in calls
                                                 if positive_number(call.get("wall_ns"))])}
        generations = [call["generation"] for call in calls if isinstance(call.get("generation"), dict)]
        for label, field in (("load_seconds", "load_duration_ns"),
                             ("prefill_seconds", "prompt_eval_duration_ns"),
                             ("decode_seconds", "eval_duration_ns")):
            metrics[label] = distribution([g[field] / 1e9 for g in generations
                                           if positive_number(g.get(field))])
        for field in ("prompt_eval_count", "eval_count"):
            metrics[field] = distribution([g[field] for g in generations
                                           if positive_number(g.get(field))])
        purposes[purpose] = metrics
    return {"all_requests_seconds": distribution(values),
            "first_request_seconds": values[0] if values else None,
            "later_requests_seconds": distribution(values[1:]), "by_purpose": purposes,
            "scope": "elapsed nonstreaming MCQ turn; includes safety checks and serial loading"}


def inspect_execution_amendment(path, arm, manifest, digest):
    """Validate the explicit extra-only launcher separately from frozen sources.

    Archived code is never executed. Archive hashes establish which additional
    launcher and protocol text were used; the unchanged source map still must
    match every earlier arm. The saved start snapshot independently establishes
    compliance with the declared amended startup limits.
    """
    errors, details = [], None
    manifest_amendment = (manifest or {}).get("execution_amendment")
    sidecar = path / "execution_amendment.json"
    if manifest_amendment is None and not sidecar.exists():
        return details, errors
    if arm != "extra":
        errors.append("execution amendment is permitted only for the extra arm")
    try:
        amendment = read_json(sidecar)
        if not isinstance(amendment, dict):
            raise ValueError("execution amendment is not an object")
        details = {"metadata": amendment, "archive_verification": {}}
        if amendment != manifest_amendment:
            errors.append("execution amendment sidecar differs from manifest declaration")
        expected = {
            "schema_version": 1, "arm": "extra", "model": EXTRA,
            "scope": "extra_startup_only",
            "launcher_path": "scripts/run_arc_qwen25_retry.py",
            "launcher_archive": "execution_launcher.py",
            "protocol_amendment_path": "evaluation/arc_capability_20260911/extra_startup_amendment.md",
            "protocol_amendment_archive": "execution_amendment.md",
            "dataset_sha256": digest, "original_start_swap_ceiling_kib": 131072,
            "start_limits": EXTRA_START_LIMITS, "runtime_limits": UNCHANGED_RUNTIME_LIMITS,
            "runtime_guards_unchanged": True, "system_settings_changed": False,
        }
        for field, value in expected.items():
            if amendment.get(field) != value or (
                type(value) is bool and type(amendment.get(field)) is not bool
            ):
                errors.append(f"execution amendment has unexpected {field}")
        rationale = amendment.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            errors.append("execution amendment lacks an explicit rationale")
        original_hash = (manifest or {}).get("source_sha256", {}).get("scripts/run_arc_capability.py")
        if not original_hash or amendment.get("original_runner_sha256") != original_hash:
            errors.append("execution amendment does not identify the frozen original runner")
        for prefix, archive, source in (
            ("launcher", "execution_launcher.py", "scripts/run_arc_qwen25_retry.py"),
            ("protocol_amendment", "execution_amendment.md",
             "evaluation/arc_capability_20260911/extra_startup_amendment.md"),
        ):
            declared = amendment.get(prefix + "_sha256")
            archive_hash = sha256((path / archive).read_bytes()).hexdigest()
            if not isinstance(declared, str) or re.fullmatch("[0-9a-f]{64}", declared) is None:
                errors.append(f"invalid {prefix} provenance hash")
            if declared != archive_hash:
                errors.append(f"archived {prefix} does not match declared SHA-256")
            current = PROJECT_ROOT / source
            current_hash = sha256(current.read_bytes()).hexdigest() if current.is_file() else None
            details["archive_verification"][prefix] = {
                "archive": archive, "declared_sha256": declared, "archive_sha256": archive_hash,
                "current_workspace_sha256": current_hash,
                "current_workspace_matches_archive": current_hash == archive_hash,
                "note": "archived bytes are authoritative if workspace files later change",
            }
        start = read_json(path / "start.json")
        memory = start.get("memory", {})
        temperatures = start.get("temperatures_c", {})
        available, swap = memory.get("mem_available_kib"), memory.get("swap_used_kib")
        if not positive_number(available) or available < EXTRA_START_LIMITS["min_available_ram_kib"]:
            errors.append("amended extra start snapshot is below the 2.5 GiB available-RAM floor")
        if not positive_number(swap) or swap > EXTRA_START_LIMITS["max_swap_used_kib"]:
            errors.append("amended extra start snapshot exceeds the 384 MiB swap ceiling")
        if not isinstance(temperatures, dict) or not temperatures or any(
            not positive_number(value) for value in temperatures.values()
        ):
            errors.append("amended extra start snapshot has invalid temperature data")
            peak = None
        else:
            peak = max(temperatures.values())
            if peak >= EXTRA_START_LIMITS["max_temperature_c_exclusive"]:
                errors.append("amended extra start temperature is not below 55 C")
        if start.get("resident_models") != []:
            errors.append("amended extra start snapshot has resident models or missing residency data")
        if not positive_number(start.get("fan_pwm"), zero=False):
            errors.append("amended extra start snapshot does not show a running fan")
        trips = start.get("thermal_trip_events")
        if not isinstance(trips, dict) or not trips or any(value != 0 for value in trips.values()):
            errors.append("amended extra start snapshot has nonzero or missing thermal-trip counters")
        if not re.fullmatch(r"NV Power Mode:\s*15W\s*\n0\s*", start.get("power_mode", "")):
            errors.append("amended extra start snapshot is not in 15 W mode 0")
        details["start_snapshot_verification"] = {
            "available_ram_kib": available, "swap_used_kib": swap, "maximum_temperature_c": peak,
            "original_128_mib_swap_criterion_met": positive_number(swap) and swap <= 131072,
            "startup_policy": "documented extra-only amendment; original 128 MiB ceiling does not apply",
        }
    except (OSError, ValueError, TypeError, AttributeError) as error:
        errors.append(f"execution amendment: {error}")
    if details is not None:
        details["validated"] = not errors
    return details, errors


def inspect_arm(run_root, arm, directory, title, dataset, digest):
    path = run_root / directory
    result = {"arm": arm, "title": title, "directory": str(path), "status": "missing",
              "complete": False, "planned": len(dataset["cases"]), "observed": 0,
              "accuracy": None, "validation_errors": [], "artifact_sha256": {}}
    if not path.exists():
        preflight_path = run_root / "04_extra_preflight.json"
        if arm == "extra" and preflight_path.exists():
            preflight = read_json(preflight_path)
            if (preflight.get("status") == "blocked"
                    and preflight.get("model") == EXTRA
                    and preflight.get("inference_attempted") is False):
                result["status"] = "preflight_blocked"
                result["preflight"] = preflight
                result["artifact_sha256"]["04_extra_preflight.json"] = sha256(
                    preflight_path.read_bytes()).hexdigest()
        return result, None, []
    errors = result["validation_errors"]
    manifest = finish = None
    records = []
    try:
        manifest = read_json(path / "manifest.json")
        if not isinstance(manifest, dict):
            raise ValueError("manifest is not an object")
        result["models"] = manifest.get("models", {})
        result["manifest"] = {key: manifest.get(key) for key in (
            "created_at", "dataset_sha256", "artifact_dataset_sha256", "source_sha256",
            "system_prompt", "generation_seed", "hardware", "python", "ollama_version",
            "residency_policy", "config")}
        if manifest.get("arm") != arm or manifest.get("case_count") != len(dataset["cases"]):
            errors.append("manifest arm/case count mismatch")
        if manifest.get("dataset_sha256") != digest:
            errors.append("manifest input dataset SHA-256 mismatch")
        if manifest.get("artifact_dataset_sha256") != sha256(canonical_bytes(dataset)).hexdigest():
            errors.append("manifest canonical dataset SHA-256 mismatch")
        if manifest.get("dataset_metadata") != dataset["metadata"]:
            errors.append("manifest dataset provenance mismatch")
        if read_json(path / "dataset.json") != dataset:
            errors.append("arm dataset differs from frozen dataset")
        if manifest.get("system_prompt") != SYSTEM_PROMPT or manifest.get("generation_seed") != 42:
            errors.append("manifest generation prompt/seed mismatch")
        config = manifest.get("config", {})
        if config.get("generation") != {"context_length": 2048, "max_output_tokens": 192,
                                        "temperature": 0.0, "thinking": False}:
            errors.append("manifest generation configuration mismatch")
        models = manifest.get("models", {})
        if set(models) != EXPECTED_MODELS[arm]:
            errors.append("manifest model set differs from authorized arm")
        for name, model in models.items():
            if not isinstance(model, dict) or not model.get("digest") or not model.get("quantization_level"):
                errors.append(f"model digest/quantization missing: {name}")
            elif not positive_number(model.get("parameter_count"), zero=False):
                errors.append(f"model reported parameter count missing: {name}")
        sources = manifest.get("source_sha256")
        if not isinstance(sources, dict) or not sources or any(
            not isinstance(value, str) or re.fullmatch("[0-9a-f]{64}", value) is None
            for value in sources.values()
        ):
            errors.append("invalid or missing frozen source SHA-256 map")
    except (OSError, ValueError, TypeError, AttributeError) as error:
        errors.append(f"manifest/dataset: {error}")
    amendment, amendment_errors = inspect_execution_amendment(path, arm, manifest, digest)
    errors.extend(amendment_errors)
    if amendment is not None:
        result["execution_amendment"] = amendment
    try:
        records = read_jsonl(path / "observations.jsonl")
        result["observed"] = len(records)
        if len(records) > len(dataset["cases"]):
            errors.append("more observations than frozen cases")
        independently_scored = []
        for index, (record, case) in enumerate(zip(records, dataset["cases"]), 1):
            case_errors, correct = validate_record(record, case, index, arm)
            errors.extend(case_errors)
            independently_scored.append(correct)
        result["_scores"] = independently_scored
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as error:
        errors.append(f"observations: {error}")
    try:
        finish = read_json(path / "finish.json")
        result["status"] = finish.get("status", "incomplete")
        result["finish"] = {key: finish.get(key) for key in (
            "status", "failure", "cleanup_errors", "guard_violation", "telemetry_reader_error",
            "boot_id", "thermal_trip_events", "resident_models", "power_mode")}
        if finish.get("completed_cases") != len(records) or finish.get("planned_cases") != len(dataset["cases"]):
            errors.append("finish observation/planned count mismatch")
        if result["status"] in COMPLETE_STATUSES:
            if len(records) != len(dataset["cases"]):
                errors.append("complete status without all frozen cases")
            if any(finish.get(key) for key in ("failure", "cleanup_errors", "guard_violation", "telemetry_reader_error")):
                errors.append("complete status with a recorded execution/guard failure")
            if finish.get("resident_models"):
                errors.append("complete arm did not unload resident models")
            start = read_json(path / "start.json")
            if arm == "extra" and amendment is None:
                memory = start.get("memory", {})
                if (not positive_number(memory.get("mem_available_kib"))
                        or memory["mem_available_kib"] < 2621440
                        or not positive_number(memory.get("swap_used_kib"))
                        or memory["swap_used_kib"] > 131072):
                    errors.append("extra start violates original RAM/swap limits without a validated amendment")
            if start.get("resident_models"):
                errors.append("arm started with resident models")
            for field in ("boot_id", "thermal_trip_events"):
                if not start.get(field) or start.get(field) != finish.get(field):
                    errors.append(f"start/finish {field} changed or missing")
            summary = read_json(path / "summary.json")
            if summary.get("status") != result["status"] or summary.get("attempted") != len(records):
                errors.append("saved summary status/count mismatch")
            if summary.get("correct") != sum(result.get("_scores", [])):
                errors.append("saved summary correctness differs from raw scoring")
    except FileNotFoundError:
        result["status"] = "incomplete"
    except (OSError, ValueError, TypeError, AttributeError) as error:
        errors.append(f"finish/start/summary: {error}")
    try:
        telemetry = read_jsonl(path / "telemetry.jsonl")
        result["telemetry"] = telemetry_metrics(telemetry)
        if result["status"] in COMPLETE_STATUSES:
            if not telemetry:
                errors.append("completed arm lacks telemetry")
            elif result["telemetry"]["peak_swap_used_mb"] > 512 or result["telemetry"]["peak_temperature_c"] >= 68:
                errors.append("completed arm telemetry crosses a frozen resource guard")
            saved = read_json(path / "telemetry_summary.json")
            if saved.get("sample_count") != len(telemetry):
                errors.append("telemetry summary sample count mismatch")
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as error:
        errors.append(f"telemetry: {error}")
    result["timing"] = latency_metrics(records)
    result["selected_models"] = dict(Counter(r.get("selected_model", "none") for r in records))
    result["memory_intent_true"] = sum(bool((r.get("route") or {}).get("decision", {}).get("memory_required"))
                                        for r in records)
    result["status_counts"] = dict(Counter(r.get("status", "missing") for r in records))
    for filename in ("manifest.json", "dataset.json", "observations.jsonl", "telemetry.jsonl",
                     "start.json", "finish.json", "summary.json", "telemetry_summary.json",
                     "execution_amendment.json", "execution_launcher.py", "execution_amendment.md"):
        file = path / filename
        if file.exists():
            result["artifact_sha256"][filename] = sha256(file.read_bytes()).hexdigest()
    return result, manifest, records


def score_group(cases, records, scores):
    correct = sum(scores)
    return {"count": len(cases), "correct": correct,
            "accuracy": correct / len(cases) if cases else None,
            "wilson_95": wilson(correct, len(cases)),
            "failed_requests": sum(record["status"] != "ok" for record in records)}


def partial_diagnostics(cases, records, scores):
    """Describe observed progress without constructing an incomplete accuracy."""
    successful = [row for row in records if row["status"] == "ok"]
    unaccepted = []
    for row, case in zip(records, cases):
        if row["status"] == "ok":
            continue
        labels = [choice["label"] for choice in case["choices"]]
        for call in row["calls"]:
            generation = call.get("generation")
            if call.get("purpose") != "generation" or not isinstance(generation, dict):
                continue
            label = None
            try:
                if generation.get("done_reason") != "length":
                    label = parse_answer(generation.get("content"), labels)
            except (ValueError, TypeError):
                pass
            unaccepted.append({
                "case_id": case["id"], "index": row["index"], "raw_label": label,
                "raw_label_matches_gold": label == case["answerKey"],
                "accepted_answer": row.get("answer"), "request_status": row["status"],
                "request_error": row.get("error"), "request_error_message": row.get("message"),
                "scored_correct": False,
                "note": "backend output retained for diagnosis; request failed before successful acceptance",
            })
    return {
        "planned_requests": len(cases), "attempted_requests": len(records),
        "successful_requests": len(successful),
        "unsuccessful_requests": len(records) - len(successful),
        "unattempted_requests": len(cases) - len(records),
        "correct_successful_answers": sum(scores),
        "by_subset": {subset: {
            "attempted_requests": sum(row["subset"] == subset for row in records),
            "successful_requests": sum(row["subset"] == subset for row in successful),
            "correct_successful_answers": sum(score for row, score in zip(records, scores)
                                               if row["subset"] == subset),
        } for subset in sorted({case["subset"] for case in cases})},
        "successful_request_latency_seconds": distribution([row["wall_ns"] / 1e9 for row in successful]),
        "later_successful_request_latency_seconds": distribution(
            [row["wall_ns"] / 1e9 for row in successful if row["index"] > 1]),
        "unaccepted_backend_outputs": unaccepted,
        "scope": "diagnostic counts and observed timing only; no completed accuracy, interval, or paired comparison",
    }


def paired(first, second, first_scores, second_scores, cases):
    def group(indices):
        counts = Counter((first_scores[i], second_scores[i]) for i in indices)
        n = len(indices)
        first_only, second_only = counts[(True, False)], counts[(False, True)]
        return {"count": n, "both_correct": counts[(True, True)],
                "first_only_correct": first_only, "second_only_correct": second_only,
                "neither_correct": counts[(False, False)],
                "second_minus_first_percentage_points": 100 * (second_only - first_only) / n if n else None,
                "exact_mcnemar_two_sided_p": exact_mcnemar(first_only, second_only),
                "first_only_case_ids": [cases[i]["id"] for i in indices if first_scores[i] and not second_scores[i]],
                "second_only_case_ids": [cases[i]["id"] for i in indices if second_scores[i] and not first_scores[i]]}
    return {"first": first, "second": second, **group(list(range(len(cases)))),
            "by_subset": {subset: group([i for i, case in enumerate(cases) if case["subset"] == subset])
                          for subset in sorted({case["subset"] for case in cases})}}


def cascade_analysis(results, records, cases):
    small, large, cascade = (results[name]["_scores"] for name in ("small", "large", "cascade"))
    routed = records["cascade"]
    opportunities = [i for i in range(len(cases)) if large[i] and not small[i]]
    regressions = [i for i in range(len(cases)) if small[i] and not large[i]]
    captured = [i for i in opportunities if cascade[i]]
    selected_large = [i for i in opportunities if routed[i].get("selected_model") == LARGE]
    oracle = [left or right for left, right in zip(small, large)]
    consistency = [i for i, row in enumerate(routed)
                   if row.get("selected_model") in {SMALL, LARGE}
                   and row.get("answer") != records["small" if row["selected_model"] == SMALL else "large"][i].get("answer")]
    selected_baseline = [large[i] if row.get("selected_model") == LARGE else
                         small[i] if row.get("selected_model") == SMALL else False
                         for i, row in enumerate(routed)]
    small_mean = results["small"]["timing"]["all_requests_seconds"]["mean"]
    large_mean = results["large"]["timing"]["all_requests_seconds"]["mean"]
    cascade_mean = results["cascade"]["timing"]["all_requests_seconds"]["mean"]
    return {"large_only_correct_opportunities": len(opportunities),
            "large_only_correct_captured": len(captured),
            "large_only_correct_missed": len(opportunities) - len(captured),
            "opportunities_routed_large": len(selected_large),
            "opportunities_routed_small_or_failed": len(opportunities) - len(selected_large),
            "captured_case_ids": [cases[i]["id"] for i in captured],
            "missed_case_ids": [cases[i]["id"] for i in opportunities if not cascade[i]],
            "small_only_correct_cases": len(regressions),
            "small_only_correct_lost": sum(not cascade[i] for i in regressions),
            "oracle_pair_correct": sum(oracle), "oracle_pair_accuracy": sum(oracle) / len(cases),
            "oracle_warning": "hypothetical selection using observed gold correctness, not an implemented router",
            "selected_baseline_replay_correct": sum(selected_baseline),
            "actual_cascade_correct": sum(cascade),
            "selected_generator_answer_disagreements": len(consistency),
            "selected_generator_disagreement_case_ids": [cases[i]["id"] for i in consistency],
            "cascade_minus_small_accuracy_pp": 100 * (sum(cascade) - sum(small)) / len(cases),
            "cascade_minus_large_accuracy_pp": 100 * (sum(cascade) - sum(large)) / len(cases),
            "cascade_minus_small_mean_seconds": cascade_mean - small_mean,
            "cascade_minus_large_mean_seconds": cascade_mean - large_mean,
            "cascade_over_small_mean_latency_ratio": cascade_mean / small_mean if small_mean else None,
            "cascade_over_large_mean_latency_ratio": cascade_mean / large_mean if large_mean else None}


def analyze(dataset_path, run_root):
    raw = dataset_path.read_bytes()
    dataset = decode_json(raw)
    cases = validate_dataset(dataset)
    digest = sha256(raw).hexdigest()
    results, manifests, records = {}, {}, {}
    for arm, directory, title in ARMS:
        results[arm], manifests[arm], records[arm] = inspect_arm(
            run_root, arm, directory, title, dataset, digest)
    cross_errors = []
    available = [(arm, manifest) for arm, manifest in manifests.items() if manifest]
    if available:
        reference_arm, reference = available[0]
        for arm, manifest in available[1:]:
            for field in ("source_sha256", "system_prompt", "generation_seed", "dataset_sha256",
                          "artifact_dataset_sha256", "dataset_metadata", "ollama_version"):
                if manifest.get(field) != reference.get(field):
                    issue = f"{field} differs between {reference_arm} and {arm}"
                    cross_errors.append(issue)
                    results[reference_arm]["validation_errors"].append(issue)
                    results[arm]["validation_errors"].append(issue)
        known = {}
        for arm, manifest in available:
            for name, metadata in manifest.get("models", {}).items():
                identity = {key: metadata.get(key) for key in (
                    "digest", "size", "parameter_count", "quantization_level", "family", "format")}
                if name in known and known[name][1] != identity:
                    issue = f"model identity changes between arms: {name}"
                    cross_errors.append(issue)
                    results[arm]["validation_errors"].append(issue)
                    results[known[name][0]]["validation_errors"].append(issue)
                known[name] = (arm, identity)
    for arm, result in results.items():
        result["complete"] = (result["status"] in COMPLETE_STATUSES
                              and not result["validation_errors"] and result["observed"] == len(cases))
        if result["complete"]:
            result["score"] = score_group(cases, records[arm], result["_scores"])
            result["accuracy"] = result["score"]["accuracy"]
            result["by_subset"] = {}
            for subset in sorted({case["subset"] for case in cases}):
                indices = [i for i, case in enumerate(cases) if case["subset"] == subset]
                result["by_subset"][subset] = score_group(
                    [cases[i] for i in indices], [records[arm][i] for i in indices],
                    [result["_scores"][i] for i in indices])
        elif result["validation_errors"] and result["status"] in COMPLETE_STATUSES:
            result["status"] = "invalid_artifacts"
        if not result["complete"] and result["observed"] and not result["validation_errors"]:
            result["partial_diagnostics"] = partial_diagnostics(cases, records[arm], result["_scores"])
    pairs = {}
    for (first, _, _), (second, _, _) in combinations(ARMS, 2):
        if results[first]["complete"] and results[second]["complete"]:
            pairs[f"{first}_vs_{second}"] = paired(
                first, second, results[first]["_scores"], results[second]["_scores"], cases)
    cascade = None
    if all(results[arm]["complete"] for arm in ("small", "large", "cascade")):
        cascade = cascade_analysis(results, records, cases)
    for result in results.values():
        result.pop("_scores", None)
    return {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
            "dataset_path": str(dataset_path.resolve()), "dataset_sha256": digest,
            "dataset_metadata": dataset["metadata"], "case_order": [case["id"] for case in cases],
            "analysis_source_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "run_root": str(run_root.resolve()), "all_arms_complete": all(r["complete"] for r in results.values()),
            "arms": results, "cross_arm_validation_errors": cross_errors,
            "paired": pairs, "cascade": cascade,
            "statistical_notes": [
                "Wilson 95% binomial intervals are descriptive; equal-stratum pooled interval is approximate.",
                "McNemar exact two-sided p-values are exploratory, unadjusted for multiple comparisons.",
                "No nonsignificance/equivalence claim, no repeated-run timing uncertainty.",
                "Oracle and baseline replay reuse observed outputs and are diagnostics, not deployed systems.",
            ]}


def number(value, digits=2):
    return "—" if value is None else f"{value:.{digits}f}"


def score_text(group):
    if not group:
        return "not available"
    low, high = group["wilson_95"]
    return (f"{group['correct']}/{group['count']} ({100 * group['accuracy']:.1f}%; "
            f"95% CI {100 * low:.1f}–{100 * high:.1f}%)")


def render_markdown(report):
    arms = report["arms"]
    complete = report["all_arms_complete"]
    count = len(report["case_order"])
    lines = [f"ARC capability pilot: {'completed' if complete else 'incomplete'}", "",
             f"Generated {report['created_at']}. {sum(r['complete'] for r in arms.values())}/4 arms "
             f"completed and independently validated against the same {count} frozen questions.", "",
             "This is a zero-shot, closed-book, JSON-constrained generated-label comparison on "
             "50 ARC-Easy and 50 ARC-Challenge test questions. Native labels and option order are "
             "preserved. The dataset comes from [AllenAI ARC](https://huggingface.co/datasets/allenai/ai2_arc), "
             "[Clark et al. (2018)](https://arxiv.org/abs/1803.05457), under CC-BY-SA-4.0.", "",
             "| Arm | Status | Overall accuracy (Wilson 95%) | ARC-Easy | ARC-Challenge | Failed requests |",
             "| --- | --- | --- | --- | --- | --- |"]
    for arm, _, title in ARMS:
        result = arms[arm]
        if result["complete"]:
            lines.append(f"| {title} | {result['status']} | {score_text(result['score'])} | "
                         f"{score_text(result['by_subset'].get('ARC-Easy'))} | "
                         f"{score_text(result['by_subset'].get('ARC-Challenge'))} | "
                         f"{result['score']['failed_requests']} |")
        else:
            lines.append(f"| {title} | {result['status']}; {result['observed']}/{count} observed | "
                         "withheld | withheld | withheld | — |")
    lines.extend(["", "Errors and truncated/invalid responses count as incorrect in completed arms. "
                  "An incomplete or invalid arm has no completed accuracy estimate. Wilson intervals "
                  "describe sampling uncertainty; the pooled equal-stratum interval is approximate.", ""])
    for arm, result in arms.items():
        diagnostic = result.get("partial_diagnostics")
        if not diagnostic:
            continue
        lines.extend([
            f"**Partial {arm} diagnostic:** {diagnostic['attempted_requests']} requests were attempted: "
            f"{diagnostic['successful_requests']} succeeded and {diagnostic['unsuccessful_requests']} "
            f"were unsuccessful; {diagnostic['unattempted_requests']} frozen requests were not attempted. "
            f"There were {diagnostic['correct_successful_answers']} correct accepted answers among the "
            "successful requests. These progress counts are not a completed benchmark accuracy and "
            "are excluded from accuracy intervals and paired model comparisons.", "",
        ])
        for output in diagnostic["unaccepted_backend_outputs"]:
            lines.extend([
                f"Request {output['index']} (`{output['case_id']}`) retained backend label "
                f"`{output['raw_label']}` (matches gold: {output['raw_label_matches_gold']}), but "
                f"its status is `{output['request_status']}` and accepted answer is "
                f"`{output['accepted_answer']}`. The failed request is not counted as a correct "
                "accepted answer; raw generation availability does not override the recorded "
                "safety interruption.", "",
            ])
        successful = diagnostic["successful_request_latency_seconds"]
        later = diagnostic["later_successful_request_latency_seconds"]
        lines.extend([
            f"For the {successful['n']} successful {arm} requests only, mean / median / p95 elapsed "
            f"time is {number(successful['mean'])} / {number(successful['p50'])} / "
            f"{number(successful['p95'])} s. Excluding the first request, the "
            f"{later['n']} later successful requests have mean / median / p95 "
            f"{number(later['mean'])} / {number(later['p50'])} / {number(later['p95'])} s. "
            "The main timing table below includes all observed attempts, including the interrupted "
            "request. This stopped run does not establish complete-workload latency or resource feasibility.", "",
        ])
    if report["paired"]:
        lines.extend(["| Paired comparison (first → second) | Both correct | First only | Second only | Neither | "
                      "Second minus first | Exact McNemar p |",
                      "| --- | --- | --- | --- | --- | --- | --- |"])
        for pair in report["paired"].values():
            lines.append(f"| {pair['first']} → {pair['second']} | {pair['both_correct']} | "
                         f"{pair['first_only_correct']} | {pair['second_only_correct']} | "
                         f"{pair['neither_correct']} | {pair['second_minus_first_percentage_points']:+.1f} pp | "
                         f"{pair['exact_mcnemar_two_sided_p']:.4g} |")
        lines.extend(["", "Paired exact p-values are descriptive, unadjusted for multiple comparisons. "
                      "A nonsignificant result does not establish equivalent quality. Per-subset paired "
                      "counts and discordant question IDs are retained in analysis.json.", ""])
    cascade = report.get("cascade")
    if cascade:
        lines.extend([
            f"The standalone 1.7B model rescued {cascade['large_only_correct_opportunities']} requests "
            "that 0.6B answered incorrectly. "
            f"The cascade answered {cascade['large_only_correct_captured']} of these correctly and "
            f"missed {cascade['large_only_correct_missed']}; "
            f"{cascade['opportunities_routed_large']} were routed to 1.7B. "
            f"It lost {cascade['small_only_correct_lost']} of the "
            f"{cascade['small_only_correct_cases']} requests where standalone 0.6B alone was correct.", "",
            f"Cascade selections: {json.dumps(arms['cascade']['selected_models'], sort_keys=True)}. "
            f"Memory intent was true on {arms['cascade']['memory_intent_true']} requests; retrieval was disabled.", "",
            f"Cascade accuracy changed by {cascade['cascade_minus_small_accuracy_pp']:+.1f} percentage "
            f"points versus 0.6B and {cascade['cascade_minus_large_accuracy_pp']:+.1f} versus 1.7B. "
            f"Mean elapsed latency changed by {cascade['cascade_minus_small_mean_seconds']:+.2f} s "
            f"and {cascade['cascade_minus_large_mean_seconds']:+.2f} s, respectively.", "",
            f"A hypothetical oracle choosing a correct standalone 0.6B/1.7B output could answer "
            f"{cascade['oracle_pair_correct']}/{count} correctly. This uses answer-key knowledge and "
            "is not a deployable result. "
            f"Replaying the cascade's choices against standalone outputs gives "
            f"{cascade['selected_baseline_replay_correct']}/{count}; the live cascade achieved "
            f"{cascade['actual_cascade_correct']}/{count}. "
            f"There were {cascade['selected_generator_answer_disagreements']} answer-label disagreements "
            "between cascade generation and the corresponding selected standalone generator.", "",
        ])
    lines.extend(["| Arm | First request s | All mean / p50 / p95 s | Later mean / p50 / p95 s | "
                  "Peak RAM / swap MiB | Peak temperature C |", "| --- | --- | --- | --- | --- | --- |"])
    for arm, _, title in ARMS:
        result = arms[arm]
        if "timing" not in result:
            continue
        timing, telemetry = result["timing"], result.get("telemetry", {})
        all_values, later = timing["all_requests_seconds"], timing["later_requests_seconds"]
        suffix = " (unvalidated)" if result["validation_errors"] else " (partial)" if not result["complete"] else ""
        lines.append(f"| {title}{suffix} | {number(timing['first_request_seconds'])} | "
                     f"{' / '.join(number(all_values[k]) for k in ('mean', 'p50', 'p95'))} | "
                     f"{' / '.join(number(later[k]) for k in ('mean', 'p50', 'p95'))} | "
                     f"{number(telemetry.get('peak_ram_used_mb'), 0)} / "
                     f"{number(telemetry.get('peak_swap_used_mb'), 0)} | "
                     f"{number(telemetry.get('peak_temperature_c'))} |")
    lines.extend(["", "Wall time includes serial routing/loading and in-turn safety/metadata checks. "
                  "Each arm starts without a resident model; its first request is separated, but operating-system "
                  "cache state is not reset. These are nonstreaming short-answer times, not first-token or "
                  "speech-to-answer measurements. Resource peaks are sampled whole-device values, including "
                  "desktop processes and cleanup, at 500 ms intervals.", "",
                  "| Arm / purpose | Calls | Mean wall s | Mean load s | Mean prefill s | Mean decode s |",
                  "| --- | --- | --- | --- | --- | --- |"])
    for arm, _, title in ARMS:
        for purpose, values in arms[arm].get("timing", {}).get("by_purpose", {}).items():
            if not values["call_count"]:
                continue
            suffix = (" (unvalidated)" if arms[arm]["validation_errors"] else
                      " (partial)" if not arms[arm]["complete"] else "")
            lines.append(f"| {title} / {purpose}{suffix} | {values['call_count']} | "
                         f"{number(values['wall_seconds']['mean'])} | {number(values['load_seconds']['mean'])} | "
                         f"{number(values['prefill_seconds']['mean'])} | {number(values['decode_seconds']['mean'])} |")
    lines.extend(["", "Load/prefill/decode values are reported by the inference backend; wall time also "
                  "contains work outside those fields. Distribution summaries, totals, and token counts are "
                  "included in analysis.json.", "",
                  "All generators use 2,048-token context, a 192-token output ceiling, temperature 0, seed 42, "
                  "and thinking disabled. Fixed single-model arms keep their sole generator resident. The "
                  "cascade uses the deployed two-call 0.6B router and its serial eviction policy under a common "
                  "MCQ adapter; no personal memory, retrieval, answer composition, authored reference notes, "
                  "conversation history, STT, or TTS are used. This is CLARA generator selection, not the full application.", "",
                  "The fourth arm is **Qwen2.5 3B Q3_K_S**, selected under the user's 3B-or-4B allowance. "
                  "The frozen protocol excludes the installed 4B artifact because of its recorded loading "
                  "watchdog reset and the existing artifact-size guard. **No 4B accuracy was measured.** "
                  "The [official 3B model card](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct) describes "
                  "the source model; [the Ollama artifact](https://ollama.com/library/qwen2.5:3b-instruct-q3_K_S) "
                  "identifies the quantized variant. Family and quantization differ from the Qwen3 pair, so "
                  "these results compare deployed artifacts and cannot isolate parameter count.", "",
                  "| Actual artifact | GGUF reported parameters | Quantization | Artifact bytes | Full digest |",
                  "| --- | --- | --- | --- | --- |"])
    models = {}
    for result in arms.values():
        models.update(result.get("models", {}))
    for name, model in sorted(models.items()):
        lines.append(f"| {name} | {model.get('parameter_count', '—')} | "
                     f"{model.get('quantization_level', '—')} | {model.get('size', '—')} | "
                     f"`{model.get('digest', '—')}` |")
    lines.extend(["", "Nominal tags and GGUF-reported parameter counts are both retained; their numbers "
                  "can differ. Runtime and host metadata, source hashes, and per-arm manifest hashes are "
                  "retained in analysis.json.", "",
                  "The planned collection order was 0.6B, 1.7B, cascade, then 3B; completed arms are identified above. "
                  "Startup/cache/thermal states and other device work may differ; timing is descriptive and "
                  "not a counterbalanced repeated-run estimate. Public ARC questions may occur in training "
                  "data. This science-MCQ pilot establishes neither unseen-task generalization nor personal-memory "
                  "correctness, HRI quality, or spoken responsiveness. Scores are not directly comparable to "
                  "full ARC or the likelihood-normalized leaderboard score in "
                  "[lm-eval's ARC configuration](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/lm_eval/tasks/arc/arc_easy.yaml).", "",
                  f"Frozen dataset SHA-256: `{report['dataset_sha256']}`. "
                  f"Dataset revision: `{report['dataset_metadata'].get('revision')}`.", "",
                  f"Raw artifacts: `{report['run_root']}`. This report was independently recomputed from raw "
                  "answer JSON and checks exact dataset/order, source hashes, common prompts, decoding settings, "
                  "native label schemas, model attribution, recorded completion state, and telemetry.", ""])
    for arm, result in arms.items():
        if result.get("execution_amendment"):
            execution = result["execution_amendment"]
            metadata = execution["metadata"]
            checked = execution.get("start_snapshot_verification", {})
            state = "validated" if execution.get("validated") else "failed validation"
            lines.extend([
                f"The {arm} arm has an explicit **amended startup policy** ({state}). Its startup "
                "swap ceiling is 384 MiB instead of the original frozen 128 MiB criterion. The "
                "2.5 GiB available-RAM startup floor remains in force. Recorded runtime limits "
                "remain 768 MiB minimum available RAM, 512 MiB maximum swap, and temperature below "
                "68 C, with the original monitoring and serial-residency guards. This is an "
                "extra-only execution amendment, not a claim that the original fourth-arm "
                "startup criterion passed.", "",
                f"The amended start snapshot recorded "
                f"{number(checked.get('available_ram_kib') / 1024 if checked.get('available_ram_kib') is not None else None, 1)} "
                "MiB available RAM, "
                f"{number(checked.get('swap_used_kib') / 1024 if checked.get('swap_used_kib') is not None else None, 1)} "
                f"MiB swap, and peak temperature {number(checked.get('maximum_temperature_c'))} C. "
                f"Original 128 MiB swap criterion met: {checked.get('original_128_mib_swap_criterion_met', 'unknown')}. "
                "The report independently checks this snapshot against the amended limits, "
                "running fan, zero thermal-trip counters, 15 W power mode, and no resident model.", "",
                f"Original generator, router, runtime-guard, and benchmark-runner file hashes "
                "remain subject to the same cross-arm equality checks. The extra startup launcher "
                "is additional code recorded separately: "
                f"`{metadata.get('launcher_path')}`, SHA-256 `{metadata.get('launcher_sha256')}`. "
                f"Its archived bytes are `{result['directory']}/execution_launcher.py`. "
                "The protocol amendment is also archived as `execution_amendment.md` with "
                f"SHA-256 `{metadata.get('protocol_amendment_sha256')}`. "
                "Both archives are checked against the manifest/sidecar declaration; all details "
                "are retained in analysis.json. The amendment records no system-settings changes.", "",
                "This amendment was introduced after the earlier three arms. The fourth condition "
                "must therefore be described as a documented amended-startup run, with its own "
                "device/cache state, rather than a run entirely under the original frozen "
                "execution protocol. It does not alter the common questions, prompts, decoding, "
                "scoring, or runtime limits.", "",
            ])
        if result.get("preflight"):
            preflight = result["preflight"]
            memory = preflight["snapshot"]["memory"]
            lines.extend([
                f"The {arm} condition was blocked before inference. Available RAM was "
                f"{memory['mem_available_kib'] / 1024:.1f} MiB (required: at least 2560 MiB); "
                f"swap use was {memory['swap_used_kib'] / 1024:.1f} MiB (required: at most 128 MiB). "
                "No fourth-model score is available. The complete preflight snapshot and its hash "
                "are retained in analysis.json.", "",
            ])
        if result["validation_errors"]:
            lines.append(f"Validation findings for {arm}:")
            lines.append("")
            lines.extend(f"- {error}" for error in result["validation_errors"])
            lines.append("")
        if not result["complete"] and result.get("finish", {}).get("failure"):
            lines.extend([f"Recorded {arm} failure: `{json.dumps(result['finish']['failure'], sort_keys=True)}`.", ""])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    output_dir, run_root = args.output_dir.resolve(), args.run_root.resolve()
    if output_dir == run_root or run_root in output_dir.parents:
        parser.error("output directory must be outside the immutable raw run root")
    paths = [output_dir / "analysis.json", output_dir / "report.md"]
    if any(path.exists() for path in paths):
        parser.error("analysis.json/report.md already exists; choose a new output directory")
    report = analyze(args.dataset.resolve(), run_root)
    markdown = render_markdown(report)
    output_dir.mkdir(parents=True, exist_ok=True)
    with paths[0].open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    with paths[1].open("x", encoding="utf-8") as stream:
        stream.write(markdown)
    print(json.dumps({"all_arms_complete": report["all_arms_complete"],
                      "statuses": {key: value["status"] for key, value in report["arms"].items()},
                      "analysis": str(paths[0]), "report": str(paths[1])}))
    return 0 if report["all_arms_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
