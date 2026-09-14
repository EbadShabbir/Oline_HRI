"""Run one sequential, guarded zero-shot ARC capability arm on the Jetson.

This measures benchmark generation and production routing, not the full spoken
CLARA system. No memory database, retrieval, answer templates, or gold feedback
is used. Run small, large, cascade, then extra in separate invocations.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import platform
import sys
from time import perf_counter, perf_counter_ns, sleep

from oline_hri.config import load_config
from oline_hri.evaluation_model_pairs import (
    SafetyGateError, _DurableJsonlWriter, _StreamingSafetyMonitor,
    _canonical_bytes, _force_unload, _http_json, _installed_models, _model_metadata,
    _model_name, _new_private_directory, _require_start_safe, _resident_models, _write_new_json,
    capture_safety_snapshot,
)
from oline_hri.ollama import ChatMessage, OllamaClient, OllamaError
from oline_hri.routing import ConversationRouter
from run_pair_remediation_validation import GuardedBackend, GuardedSampler, require_ready


SMALL_MODEL = "qwen3:0.6b"
LARGE_MODEL = "qwen3:1.7b"
CONTEXT_LENGTH = 2048
MAX_OUTPUT_TOKENS = 192
SYSTEM_PROMPT = (
    "Answer the multiple-choice science question. Choose exactly one of the "
    "provided option labels. Return only a JSON object with one key, answer, "
    'whose value is that label, for example {"answer":"A"}. '
    "Do not include an explanation."
)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"nonstandard JSON constant: {value}")


def load_dataset(path):
    raw = path.read_bytes()
    dataset = json.loads(raw, object_pairs_hook=_unique_object,
                         parse_constant=_reject_constant)
    if not isinstance(dataset, dict) or not isinstance(dataset.get("metadata"), dict):
        raise ValueError("dataset needs a metadata object")
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("dataset needs a nonempty cases list")
    identifiers = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("each case must be an object")
        for field in ("id", "subset", "question", "answerKey"):
            if not isinstance(case.get(field), str) or not case[field].strip():
                raise ValueError(f"case needs a nonempty {field}")
        if case["id"] in identifiers:
            raise ValueError("duplicate case ID")
        identifiers.add(case["id"])
        choices = case.get("choices")
        if not isinstance(choices, list) or len(choices) < 2:
            raise ValueError("case needs at least two choices")
        labels = []
        for choice in choices:
            if not isinstance(choice, dict) or any(
                not isinstance(choice.get(field), str) or not choice[field].strip()
                for field in ("label", "text")
            ):
                raise ValueError("choice needs nonempty label and text")
            labels.append(choice["label"])
        if len(labels) != len(set(labels)) or case["answerKey"] not in labels:
            raise ValueError("choice labels must be unique and contain the gold label")
    return dataset, sha256(raw).hexdigest()


def question_text(case):
    return case["question"] + "\n\n" + "\n".join(
        f'{choice["label"]}. {choice["text"]}' for choice in case["choices"]
    )


def generation_messages(case):
    # Gold, subset, case IDs, and benchmark metadata never enter model messages.
    return (ChatMessage("system", SYSTEM_PROMPT),
            ChatMessage("user", question_text(case)))


def answer_schema(case):
    return {
        "type": "object",
        "properties": {"answer": {"type": "string", "enum": [
            choice["label"] for choice in case["choices"]
        ]}},
        "required": ["answer"], "additionalProperties": False,
    }


def parse_answer(content, labels):
    value = json.loads(content, object_pairs_hook=_unique_object,
                       parse_constant=_reject_constant)
    if (not isinstance(value, dict) or set(value) != {"answer"}
            or not isinstance(value["answer"], str) or value["answer"] not in labels):
        raise ValueError("answer must be exactly one available label in a JSON object")
    return value["answer"]


def arm_config(config, arm, extra_model):
    if arm not in {"small", "large", "cascade", "extra"}:
        raise ValueError("unknown evaluation arm")
    if arm == "cascade":
        ollama = replace(config.ollama, small_model=SMALL_MODEL,
                         general_large_model=LARGE_MODEL, large_model=LARGE_MODEL)
    else:
        model = {"small": SMALL_MODEL, "large": LARGE_MODEL, "extra": extra_model}[arm]
        _model_name(model)
        if not model.startswith("qwen"):
            raise ValueError("this capability comparison requires a Qwen model")
        # OllamaClient ties permanent residency to its small-model role. Mapping
        # every role to the sole arm model makes large-only genuinely resident
        # and prevents any hidden classifier or peer-model calls.
        ollama = replace(config.ollama, small_model=model,
                         general_large_model=model, large_model=model,
                         request_timeout_seconds=max(
                             config.ollama.request_timeout_seconds,
                             config.ollama.large_request_timeout_seconds))
    generation = replace(config.generation, context_length=CONTEXT_LENGTH,
                         max_output_tokens=MAX_OUTPUT_TOKENS,
                         temperature=0.0, thinking=False)
    return replace(config, ollama=ollama, generation=generation)


class BenchmarkBackend(GuardedBackend):
    """Keep the established Jetson checks and capture complete benchmark calls."""

    def __init__(self, client, snapshot, sampler, allowed_models):
        super().__init__(client, snapshot, sampler)
        self.allowed_models = frozenset(allowed_models)
        self.attempted_models = set()
        self.transport_error = None

    def check(self):
        result = super().check()
        unexpected = [item.get("name", item.get("model"))
                      for item in _resident_models()
                      if item.get("name", item.get("model")) not in self.allowed_models]
        if unexpected:
            self.sampler.monitor.violation = "unexpected model became resident"
            raise SafetyGateError(self.sampler.monitor.violation)
        return result

    def chat(self, model, messages, **kwargs):
        if model not in self.allowed_models:
            raise SafetyGateError("attempt to call a model outside this arm")
        self.check()
        self.attempted_models.add(model)
        checkpoint = len(self.calls)
        started = perf_counter_ns()
        fields = set((kwargs.get("response_format") or {}).get("properties", {}))
        purpose = "generation" if fields == {"answer"} else "classifier"
        failure = None
        try:
            result = super().chat(model, messages, **kwargs)
            if result.model != model:
                raise OllamaError("generation returned unexpected model metadata")
            return result
        except BaseException as error:
            failure = {"error": type(error).__name__, "message": str(error)}
            if isinstance(error, SafetyGateError):
                self.sampler.monitor.violation = str(error)
            if isinstance(error, OllamaError):
                self.transport_error = error
            raise
        finally:
            if len(self.calls) == checkpoint:
                self.calls.append({"wall_ns": perf_counter_ns() - started})
            record = self.calls[-1]
            record.update(
                requested_model=model, purpose=purpose,
                messages=[message.to_dict() for message in messages],
                request={"response_format": kwargs.get("response_format"),
                         "temperature": kwargs.get("temperature"),
                         "seed": kwargs.get("seed")},
            )
            record["actual_model"] = record.get("generation", {}).get("model")
            if failure is not None:
                record.update(failure)
            record["status"] = "error" if failure is not None else "ok"


def run_cases(cases, arm, config, backend, writer, records):
    router = ConversationRouter(backend, model=SMALL_MODEL) if arm == "cascade" else None
    for index, case in enumerate(cases, 1):
        # A router wraps ordinary Exceptions, so both before/after checks are
        # needed to keep a safety trip from becoming an ordinary scored error.
        backend.check()
        started = perf_counter_ns()
        checkpoint = len(backend.calls)
        record = {"case_id": case["id"], "subset": case["subset"], "arm": arm,
                  "index": index, "gold": case["answerKey"], "correct": False,
                  "answer": None, "route": None, "status": "error"}
        fatal = None
        try:
            if router is not None:
                route = router.route(question_text(case))
                record["route"] = asdict(route)
                model = SMALL_MODEL if route.decision.model_size == "small" else LARGE_MODEL
            else:
                model = config.ollama.small_model
            record["selected_model"] = model
            generation = backend.chat(model, generation_messages(case),
                                      response_format=answer_schema(case),
                                      temperature=0.0, seed=42)
            record["generation"] = asdict(generation)
            if generation.model != model:
                raise ValueError("answer returned by unexpected model")
            if generation.done_reason == "length":
                raise ValueError("answer was truncated")
            answer = parse_answer(generation.content,
                                  [choice["label"] for choice in case["choices"]])
            record.update(answer=answer, correct=answer == case["answerKey"], status="ok")
        except BaseException as error:
            record.update(error=type(error).__name__, message=str(error))
            if isinstance(error, (KeyboardInterrupt, SystemExit, SafetyGateError)):
                fatal = error
            elif backend.transport_error is not None:
                # The production router wraps transport failures in RoutingError.
                # Preserve the original failure and stop rather than retrying an
                # unhealthy server on the next benchmark question.
                fatal = backend.transport_error
                record.update(error=type(fatal).__name__, message=str(fatal))
        try:
            backend.check()
        except BaseException as error:
            fatal = error
            record.update(status="interrupted", correct=False,
                          error=type(error).__name__, message=str(error))
        if fatal is not None:
            record.update(status="error" if isinstance(fatal, OllamaError) else "interrupted",
                          correct=False)
        record.update(wall_ns=perf_counter_ns() - started,
                      calls=backend.calls[checkpoint:])
        writer.write(record)
        records.append(record)
        print(f"{arm} {index}/{len(cases)} {case['id']}: {record['status']} "
              f"correct={record['correct']} model={record.get('selected_model')} "
              f"wall_s={record['wall_ns'] / 1e9:.3f}", flush=True)
        if fatal is not None:
            raise fatal


def distribution(values):
    ordered = sorted(values)
    if not ordered:
        return {"n": 0, "mean": None, "p50": None, "p95": None, "min": None, "max": None}
    def quantile(q):
        position = (len(ordered) - 1) * q
        lower, upper = math.floor(position), math.ceil(position)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return {"n": len(ordered), "mean": sum(ordered) / len(ordered),
            "p50": quantile(.5), "p95": quantile(.95), "min": ordered[0], "max": ordered[-1]}


def summarize(cases, records, status):
    def group(expected, observed):
        correct = sum(record["correct"] for record in observed)
        return {"planned": len(expected), "attempted": len(observed), "correct": correct,
                "accuracy": correct / len(expected) if expected else None,
                "errors": sum(record["status"] != "ok" for record in observed),
                "unattempted": len(expected) - len(observed),
                "latency_seconds": distribution([record["wall_ns"] / 1e9 for record in observed])}
    result = {"status": status, **group(cases, records),
              "accuracy_denominator": "all frozen cases; failures and unattempted cases receive zero",
              "by_subset": {subset: group(
                  [case for case in cases if case["subset"] == subset],
                  [record for record in records if record["subset"] == subset])
                  for subset in sorted({case["subset"] for case in cases})},
              "first_case_seconds": records[0]["wall_ns"] / 1e9 if records else None,
              "later_case_latency_seconds": distribution([r["wall_ns"] / 1e9 for r in records[1:]]),
              "selected_models": dict(Counter(r.get("selected_model", "no_generation") for r in records)),
              "memory_intent_true": sum(bool((r.get("route") or {}).get("decision", {}).get("memory_required"))
                                        for r in records)}
    calls = [call for record in records for call in record["calls"]]
    result["calls_by_purpose"] = {}
    for purpose in ("classifier", "generation"):
        selected = [call for call in calls if call["purpose"] == purpose]
        result["calls_by_purpose"][purpose] = {
            "count": len(selected),
            "wall_seconds": distribution([call["wall_ns"] / 1e9 for call in selected]),
            **{label: distribution([call["generation"][field] / 1e9 for call in selected
                                   if "generation" in call])
               for label, field in (("load_seconds", "load_duration_ns"),
                                    ("prefill_seconds", "prompt_eval_duration_ns"),
                                    ("decode_seconds", "eval_duration_ns"))},
        }
    return result


def source_hashes():
    root = Path(__file__).resolve().parents[1]
    paths = list((root / "src" / "oline_hri").glob("*.py"))
    paths += [Path(__file__).resolve(), root / "scripts" / "run_pair_remediation_validation.py"]
    return {str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--arm", required=True, choices=("small", "large", "cascade", "extra"))
    parser.add_argument("--extra-model", default="qwen2.5:3b-instruct-q3_K_S")
    args = parser.parse_args(argv)
    dataset, digest = load_dataset(args.dataset)
    config = arm_config(load_config(), args.arm, args.extra_model)
    allowed = tuple(dict.fromkeys((config.ollama.small_model, config.ollama.large_model)))
    os.umask(0o077)
    directory = _new_private_directory(args.output_dir.absolute())
    records, cleanup_errors = [], []
    status, failure = "incomplete", None
    sampler = backend = monitor = None
    try:
        start = capture_safety_snapshot()
        _write_new_json(directory / "start.json", start)
        if args.arm == "extra":
            _require_start_safe(start)
        else:
            require_ready(start, small_only=False)
        installed = _installed_models()
        models = {}
        for model in allowed:
            if model not in installed:
                raise ValueError(f"model is not installed: {model}")
            models[model] = _model_metadata(model, installed)
        _write_new_json(directory / "manifest.json", {
            "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
            "arm": args.arm, "case_count": len(dataset["cases"]),
            "dataset_path": str(args.dataset.resolve()), "dataset_sha256": digest,
            "artifact_dataset_sha256": sha256(_canonical_bytes(dataset)).hexdigest(),
            "dataset_metadata": dataset["metadata"], "models": models,
            "source_sha256": source_hashes(), "config": config.to_dict(),
            "system_prompt": SYSTEM_PROMPT, "generation_seed": 42,
            "hardware": platform.uname()._asdict(), "python": sys.version,
            "ollama_version": _http_json("/api/version"),
            "residency_policy": "production_serial" if args.arm == "cascade" else "sole_model_resident",
            "scope": "zero-shot ARC generation; cascade uses production router; no retrieval or personal database",
        })
        _write_new_json(directory / "dataset.json", dataset)
        client = OllamaClient(config.ollama, config.generation)
        with _DurableJsonlWriter(directory / "telemetry.jsonl") as telemetry:
            monitor = _StreamingSafetyMonitor(telemetry)
            sampler = GuardedSampler(monitor)
            backend = BenchmarkBackend(client, start, sampler, allowed)
            with sampler:
                try:
                    # Require an actual telemetry record before any inference.
                    deadline = perf_counter() + 5
                    while not sampler.samples and perf_counter() < deadline:
                        backend.check()
                        sleep(.05)
                    if not sampler.samples:
                        raise SafetyGateError("no initial telemetry sample")
                    backend.check()
                    with _DurableJsonlWriter(directory / "observations.jsonl") as writer:
                        run_cases(dataset["cases"], args.arm, config, backend, writer, records)
                    backend.check()
                finally:
                    # Only unload tags this run actually attempted to use.
                    cleanup_errors.extend(_force_unload(sorted(backend.attempted_models)))
        status = "complete" if all(record["status"] == "ok" for record in records) else "complete_with_errors"
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
        status = "interrupted" if isinstance(error, (KeyboardInterrupt, SystemExit, SafetyGateError)) else "failed"
    finally:
        if cleanup_errors:
            status = "cleanup_failed"
        if sampler is not None:
            _write_new_json(directory / "telemetry_summary.json", sampler.summary())
        try:
            finish_snapshot = capture_safety_snapshot()
        except BaseException as error:
            finish_snapshot = {"snapshot_error": type(error).__name__, "message": str(error)}
            if status.startswith("complete"):
                status = "finish_snapshot_failed"
        _write_new_json(directory / "summary.json", summarize(dataset["cases"], records, status))
        _write_new_json(directory / "finish.json", {
            "status": status, "failure": failure, "completed_cases": len(records),
            "planned_cases": len(dataset["cases"]), "cleanup_errors": cleanup_errors,
            "guard_violation": monitor.violation if monitor is not None else None,
            "telemetry_reader_error": str(sampler._reader_error) if sampler is not None and sampler._reader_error else None,
            **finish_snapshot,
        })
    print(f"ARTIFACTS {directory} status={status}", flush=True)
    return 0 if status in {"complete", "complete_with_errors"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
