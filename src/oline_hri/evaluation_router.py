"""Router-only Step 16 measurement; selected routes are never executed."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
import sys
from time import perf_counter_ns
from typing import Callable, Optional, Sequence, TextIO
from uuid import uuid4

from .config import AppConfig, ConfigError, ROUTER_MODEL_ID, load_config, parse_config
from .evaluation import EvaluationError, EvaluationSuite, load_evaluation_suite
from .evaluation_runner import (
    EvaluationRunError, _CanonicalJsonlWriter, _chat_result_record,
    _config_sha256, _error_type, _new_private_output_path, _timestamp,
    execution_cases,
)
from .evaluation_scoring import evaluation_suite_sha256
from .ollama import ChatMessage, OllamaClient
from .routing import (
    ConversationRouter, MEMORY_REQUIRED_DEMONSTRATION_MESSAGES,
    MEMORY_REQUIRED_SCHEMA, MEMORY_REQUIRED_SYSTEM_PROMPT, MODEL_SIZE_SCHEMA,
    MODEL_SIZE_SYSTEM_PROMPT, ROUTER_SEED, ROUTER_TEMPERATURE, RoutingBackend,
)


ROUTER_OBSERVATION_SCHEMA_VERSION = 3
_CLASSIFIER_ORDER = ("memory_required", "model_size")
_MEMORY_REQUIRED_MESSAGE_PREFIX = (
    ChatMessage(role="system", content=MEMORY_REQUIRED_SYSTEM_PROMPT),
    *MEMORY_REQUIRED_DEMONSTRATION_MESSAGES,
)
_MODEL_SIZE_MESSAGE_PREFIX = (
    ChatMessage(role="system", content=MODEL_SIZE_SYSTEM_PROMPT),
)


class _RouterBackend:
    """Record metadata and enforce a small-model routing request boundary."""

    def __init__(self, delegate: RoutingBackend) -> None:
        self.delegate = delegate
        self.memory_required_generation = None
        self.model_size_generation = None
        self.call_count = 0
        self.error_type = None
        self.error_stage = None
        self.runtime_input = None

    def chat(self, model, messages, *, response_format=None,
             temperature=None, seed=None):
        expected_calls = (
            (
                "memory_required",
                MEMORY_REQUIRED_SCHEMA,
                _MEMORY_REQUIRED_MESSAGE_PREFIX,
            ),
            ("model_size", MODEL_SIZE_SCHEMA, _MODEL_SIZE_MESSAGE_PREFIX),
        )
        if self.call_count >= len(expected_calls):
            raise EvaluationRunError("only two production routing calls are allowed")
        stage, expected_schema, expected_prefix = expected_calls[self.call_count]
        messages = tuple(messages)
        if (
            model != ROUTER_MODEL_ID
            or response_format != expected_schema
            or temperature != ROUTER_TEMPERATURE or seed != ROUTER_SEED
            or len(messages) != len(expected_prefix) + 1
            or messages[:-1] != expected_prefix
            or messages[-1].role != "user"
            or (
                self.runtime_input is not None
                and messages[-1] != self.runtime_input
            )
        ):
            raise EvaluationRunError("only production small-model routing is allowed")
        if self.runtime_input is None:
            self.runtime_input = messages[-1]
        self.call_count += 1
        try:
            result = self.delegate.chat(
                model, messages, response_format=response_format,
                temperature=temperature, seed=seed,
            )
            generation = _chat_result_record(result)
            if generation is None:
                raise EvaluationRunError("router returned invalid result metadata")
            if stage == "memory_required":
                self.memory_required_generation = generation
            else:
                self.model_size_generation = generation
            return result
        except BaseException as error:
            self.error_type = _error_type(error)
            self.error_stage = stage
            raise


def _distribution(values):
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "p50": ordered[ceil(len(ordered) * .50) - 1] if ordered else None,
        "p95": ordered[ceil(len(ordered) * .95) - 1] if ordered else None,
        "total": sum(ordered),
    }


def _message_sequence_sha256(messages: Sequence[ChatMessage]) -> str:
    encoded = json.dumps(
        [message.to_dict() for message in messages],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return sha256(encoded).hexdigest()


def score_router_observations(suite: EvaluationSuite, records: Sequence[dict]) -> dict:
    """Score one suite-bound run, including failed and missing expected slots."""

    execution_cases(suite)
    if (
        not records or records[0].get("record_type") != "router_run_start"
        or records[0].get("schema_version") != ROUTER_OBSERVATION_SCHEMA_VERSION
        or records[0].get("suite_sha256") != evaluation_suite_sha256(suite)
        or records[0].get("scope") != "router_only"
        or records[0].get("expected_case_ids") != [case.id for case in suite.cases]
        or records[0].get("classifier_order") != list(_CLASSIFIER_ORDER)
    ):
        raise EvaluationRunError("router observations do not match the suite")
    header = records[0]
    by_id = {}
    expected_ids = {case.id for case in suite.cases}
    for record in records[1:]:
        if record.get("record_type") == "router_run_end":
            continue
        if (
            record.get("record_type") != "router_case"
            or record.get("case_id") not in expected_ids
            or record["case_id"] in by_id
            or record.get("run_id") != header["run_id"]
        ):
            raise EvaluationRunError("router observation slot is invalid or duplicated")
        by_id[record["case_id"]] = record

    memory_confusion = {gold: {p: 0 for p in ("false", "true", "failed", "missing")}
                        for gold in ("false", "true")}
    model_confusion = {gold: {p: 0 for p in ("small", "large", "failed", "missing")}
                       for gold in ("small", "large")}
    memory_correct = model_correct = joint_correct = successful = 0
    large_selected = incorrect_escalations = incorrect_non_escalations = 0
    expected_large = sum(c.expected_route.model_size == "large" for c in suite.cases)
    latency, prompt_tokens, output_tokens, reported_duration = [], [], [], []
    memory_prompt_tokens, memory_output_tokens, memory_duration = [], [], []
    model_prompt_tokens, model_output_tokens, model_duration = [], [], []
    classifier_calls = memory_calls = model_calls = 0
    for case in suite.cases:
        record = by_id.get(case.id)
        predicted_memory = predicted_model = "missing" if record is None else "failed"
        if record is not None:
            wall = record.get("wall_ns")
            if type(wall) is not int or wall < 0:
                raise EvaluationRunError("router wall duration is invalid")
            latency.append(wall / 1_000_000)
            call_count = record.get("classifier_calls_attempted")
            if type(call_count) is not int or not 0 <= call_count <= 2:
                raise EvaluationRunError("router classifier call count is invalid")
            classifier_calls += call_count
            memory_calls += call_count >= 1
            model_calls += call_count >= 2

            generations = []
            for stage, prompt_target, output_target, duration_target in (
                (
                    "memory_required",
                    memory_prompt_tokens,
                    memory_output_tokens,
                    memory_duration,
                ),
                ("model_size", model_prompt_tokens, model_output_tokens, model_duration),
            ):
                generation = record.get(f"{stage}_generation")
                if generation is None:
                    continue
                if not isinstance(generation, dict):
                    raise EvaluationRunError("router generation metadata is invalid")
                prompt_count = generation.get("prompt_eval_count")
                output_count = generation.get("eval_count")
                duration_ns = generation.get("total_duration_ns")
                if (
                    type(prompt_count) is not int or prompt_count < 0
                    or type(output_count) is not int or output_count < 0
                ):
                    raise EvaluationRunError("router token count is invalid")
                if type(duration_ns) is not int or duration_ns < 0:
                    raise EvaluationRunError("router reported duration is invalid")
                prompt_target.append(prompt_count)
                output_target.append(output_count)
                duration_target.append(duration_ns / 1_000_000)
                generations.append((stage, prompt_count, output_count, duration_ns))

            generation_stages = {item[0] for item in generations}
            if (
                ("memory_required" in generation_stages and call_count < 1)
                or ("model_size" in generation_stages and call_count < 2)
                or (
                    "model_size" in generation_stages
                    and "memory_required" not in generation_stages
                )
            ):
                raise EvaluationRunError("router generation order is invalid")
            if generations:
                prompt_tokens.append(sum(item[1] for item in generations))
                output_tokens.append(sum(item[2] for item in generations))
                reported_duration.append(
                    sum(item[3] for item in generations) / 1_000_000
                )
            if record.get("status") == "ok":
                decision = record.get("decision")
                if (
                    not isinstance(decision, dict)
                    or set(decision) != {"memory_required", "model_size"}
                    or type(decision["memory_required"]) is not bool
                    or decision["model_size"] not in {"small", "large"}
                ):
                    raise EvaluationRunError("router decision is invalid")
                if call_count != 2 or generation_stages != set(_CLASSIFIER_ORDER):
                    raise EvaluationRunError(
                        "successful route must preserve both classifier generations"
                    )
                predicted_memory = str(decision["memory_required"]).lower()
                predicted_model = decision["model_size"]
                successful += 1
            elif record.get("status") != "error":
                raise EvaluationRunError("router observation status is invalid")
        gold_memory = str(case.expected_route.memory_required).lower()
        gold_model = case.expected_route.model_size
        memory_confusion[gold_memory][predicted_memory] += 1
        model_confusion[gold_model][predicted_model] += 1
        memory_correct += predicted_memory == gold_memory
        model_correct += predicted_model == gold_model
        joint_correct += predicted_memory == gold_memory and predicted_model == gold_model
        large_selected += predicted_model == "large"
        incorrect_escalations += predicted_model == "large" and gold_model == "small"
        incorrect_non_escalations += predicted_model == "small" and gold_model == "large"
    count = len(suite.cases)
    return {
        "schema_version": ROUTER_OBSERVATION_SCHEMA_VERSION,
        "scope": "router_only", "run_id": header["run_id"],
        "started_at": header["started_at"],
        "finished_at": (records[-1].get("finished_at")
                        if records[-1].get("record_type") == "router_run_end" else None),
        "suite_sha256": header["suite_sha256"], "config_sha256": header["config_sha256"],
        "annotation_status": suite.annotation_status,
        "expected_slots": count, "observed_slots": len(by_id),
        "successful_slots": successful, "failed_slots": len(by_id) - successful,
        "missing_slots": count - len(by_id),
        "accuracy_denominator": count,
        "memory_accuracy": memory_correct / count,
        "model_accuracy": model_correct / count,
        "joint_accuracy": joint_correct / count,
        "memory_confusion_gold_rows": memory_confusion,
        "model_confusion_gold_rows": model_confusion,
        "expected_large_routes": expected_large,
        "selected_large_routes": large_selected,
        "selected_large_fraction": large_selected / count,
        "incorrect_escalations": incorrect_escalations,
        "incorrect_non_escalations": incorrect_non_escalations,
        "failed_or_missing_expected_large": sum(
            model_confusion["large"][key] for key in ("failed", "missing")
        ),
        "classifier_calls_attempted": classifier_calls,
        "memory_required_calls_attempted": memory_calls,
        "model_size_calls_attempted": model_calls,
        "wall_latency_ms_all_attempts": _distribution(latency),
        "ollama_total_duration_ms_reported": _distribution(reported_duration),
        "memory_required_ollama_total_duration_ms_reported": _distribution(
            memory_duration
        ),
        "model_size_ollama_total_duration_ms_reported": _distribution(model_duration),
        "prompt_tokens_reported": _distribution(prompt_tokens),
        "output_tokens_reported": _distribution(output_tokens),
        "memory_required_prompt_tokens_reported": _distribution(memory_prompt_tokens),
        "memory_required_output_tokens_reported": _distribution(memory_output_tokens),
        "model_size_prompt_tokens_reported": _distribution(model_prompt_tokens),
        "model_size_output_tokens_reported": _distribution(model_output_tokens),
        "large_inference_calls": 0, "answer_generation_calls": 0,
        "answer_quality": "not_evaluated", "four_baseline_comparison": "not_completed",
        "limitations": [
            "One stateless two-classifier routing attempt per case; failures remain in denominators.",
            "Route selection does not execute a generator or measure compute saved.",
            "Per-case token and duration totals sum available metadata from both classifiers.",
            "A failed memory classifier prevents the model-size classifier from running.",
            "Gold annotations remain pending independent review.",
        ],
    }


def run_router_evaluation(
    suite: EvaluationSuite, config: AppConfig, *, output_dir: str | Path,
    backend: Optional[RoutingBackend] = None,
    clock_ns: Callable[[], int] = perf_counter_ns,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    progress: Optional[TextIO] = None,
) -> dict:
    """Persist gold-free routing observations, then write a separate summary."""

    cases = execution_cases(suite)
    config = parse_config(config.to_dict())
    output_dir = Path(output_dir)
    observations_path = _new_private_output_path(output_dir / "observations.jsonl")
    summary_path = _new_private_output_path(output_dir / "summary.json")
    run_id = uuid4().hex
    records = [{
        "record_type": "router_run_start",
        "schema_version": ROUTER_OBSERVATION_SCHEMA_VERSION,
        "scope": "router_only", "run_id": run_id, "started_at": _timestamp(now()),
        "suite_id": suite.suite_id, "suite_sha256": evaluation_suite_sha256(suite),
        "config_sha256": _config_sha256(config), "expected_case_ids": [c.case_id for c in cases],
        "suite_evaluation_at": suite.evaluation_at,
        "router_model": ROUTER_MODEL_ID, "temperature": ROUTER_TEMPERATURE,
        "seed": ROUTER_SEED, "thinking": config.generation.thinking,
        "context_length": config.generation.context_length,
        "max_output_tokens": config.generation.max_output_tokens,
        "classifier_order": list(_CLASSIFIER_ORDER),
        "memory_required_system_prompt_sha256": sha256(
            MEMORY_REQUIRED_SYSTEM_PROMPT.encode()
        ).hexdigest(),
        "memory_required_message_prefix_sha256": _message_sequence_sha256(
            _MEMORY_REQUIRED_MESSAGE_PREFIX
        ),
        "model_size_system_prompt_sha256": sha256(
            MODEL_SIZE_SYSTEM_PROMPT.encode()
        ).hexdigest(),
        "memory_required_schema_sha256": sha256(
            json.dumps(
                MEMORY_REQUIRED_SCHEMA, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        "model_size_schema_sha256": sha256(
            json.dumps(MODEL_SIZE_SCHEMA, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "runner_source_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "generator_execution": False,
    }]
    delegate = backend if backend is not None else OllamaClient(config.ollama, config.generation)
    with _CanonicalJsonlWriter(observations_path) as writer:
        writer.write(records[0])
        for index, case in enumerate(cases, 1):
            recorder = _RouterBackend(delegate)
            router = ConversationRouter(recorder, model=ROUTER_MODEL_ID)
            record = {
                "record_type": "router_case", "run_id": run_id,
                "case_id": case.case_id, "started_at": _timestamp(now()),
                "status": "error", "decision": None, "error_type": None,
            }
            started = clock_ns()
            try:
                route = router.route(case.prompt)
                record["decision"] = {
                    "memory_required": route.decision.memory_required,
                    "model_size": route.decision.model_size,
                }
                record["status"] = "ok"
            except BaseException as error:
                record["error_type"] = _error_type(error)
                if not isinstance(error, Exception):
                    raise
            finally:
                elapsed = clock_ns() - started
                if elapsed < 0:
                    raise EvaluationRunError("router monotonic clock moved backwards")
                record.update({
                    "finished_at": _timestamp(now()), "wall_ns": elapsed,
                    "classifier_calls_attempted": recorder.call_count,
                    "memory_required_generation": recorder.memory_required_generation,
                    "model_size_generation": recorder.model_size_generation,
                    "backend_error_type": recorder.error_type,
                    "backend_error_stage": recorder.error_stage,
                })
                writer.write(record)
                records.append(record)
            if progress is not None:
                print(f"router {index}/{len(cases)} {case.case_id}: {record['status']}",
                      file=progress, flush=True)
        records.append({"record_type": "router_run_end", "run_id": run_id,
                        "finished_at": _timestamp(now()), "observed_slots": len(cases)})
        writer.write(records[-1])
    summary = score_router_observations(suite, records)
    with _CanonicalJsonlWriter(summary_path) as writer:
        writer.write(summary)
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--suite", type=Path)
    args = parser.parse_args(argv)
    try:
        summary = run_router_evaluation(
            load_evaluation_suite(args.suite), load_config(args.config),
            output_dir=args.output_dir, progress=sys.stdout,
        )
    except (EvaluationRunError, EvaluationError, ConfigError, OSError) as error:
        print(f"Router-only evaluation failed ({type(error).__name__}).", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Router-only evaluation interrupted; completed observations retained.",
              file=sys.stderr)
        return 130
    print(json.dumps({key: summary[key] for key in (
        "scope", "expected_slots", "failed_slots", "memory_accuracy",
        "model_accuracy", "joint_accuracy",
    )}, sort_keys=True))
    return 0 if summary["failed_slots"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
