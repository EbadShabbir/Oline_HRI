"""Paired two-temperature response-quality experiment.

This module is intentionally separate from the frozen Step 16 runner.  Its
default pilot fixes routing and evidence to evaluator-authored expectations so
the only changed generation parameter is temperature.  A production-adaptive
mode exists for a later verification run, but its results are not interchangeable
with the isolated pilot.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
from hmac import new as hmac_new
import json
from math import ceil
from numbers import Real
import os
from pathlib import Path
import re
from secrets import token_bytes
import stat
import sys
import tempfile
from time import perf_counter_ns
from typing import Any, Callable, Mapping, Optional, Sequence, TextIO
from uuid import uuid4

from .config import AppConfig, ConfigError, load_config
from .conversation import Conversation, ConversationReply
from .evaluation import (
    EvaluationCase,
    EvaluationError,
    EvaluationSuite,
    load_evaluation_suite,
    materialize_memory_store,
)
from .evaluation_runner import (
    EvaluationRunError,
    _CanonicalJsonlWriter,
    _config_sha256,
    _new_private_output_path,
)
from .evaluation_scoring import evaluation_suite_sha256
from .memory import MemoryItem, MemoryStore
from .ollama import ChatMessage, ChatResult, OllamaClient, OllamaTimeoutError
from .retrieval import HybridMatch
from .routing import (
    ConversationRouter,
    RouteDecision,
    RoutingResult,
)


PLAN_SCHEMA_VERSION = 1
OBSERVATION_SCHEMA_VERSION = 2
SUMMARY_SCHEMA_VERSION = 2
REVIEW_SCHEMA_VERSION = 1
MAPPING_SCHEMA_VERSION = 2
MANIFEST_SCHEMA_VERSION = 1
MAX_PLAN_BYTES = 64 * 1024
MAX_REPETITIONS = 10
_BLINDING_NONCE_BYTES = 32
_BLINDING_ORIENTATION_DOMAIN = (
    b"oline-hri-temperature-ab-candidate-orientation-v1"
)

OBSERVATIONS_NAME = "observations.jsonl"
SUMMARY_NAME = "summary.json"
PAIRED_REVIEW_NAME = "paired_review.jsonl"
PAIR_KEY_NAME = "pair_key.json"
MANIFEST_NAME = "manifest.json"
ARTIFACT_NAMES = (
    OBSERVATIONS_NAME,
    SUMMARY_NAME,
    PAIRED_REVIEW_NAME,
    PAIR_KEY_NAME,
    MANIFEST_NAME,
)

FIXED_EXPECTED = "fixed_expected"
PRODUCTION_ADAPTIVE = "production_adaptive"
FIXED_REQUIRED = "fixed_required"

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PLAN_PATH = (
    _PROJECT_ROOT / "evaluation" / "response_quality_temperature_ab_v1.json"
)
_SOURCE_PATHS = (
    "src/oline_hri/config.py",
    "src/oline_hri/conversation.py",
    "src/oline_hri/embedding.py",
    "src/oline_hri/evaluation.py",
    "src/oline_hri/evaluation_experiment.py",
    "src/oline_hri/evaluation_runner.py",
    "src/oline_hri/evaluation_scoring.py",
    "src/oline_hri/memory.py",
    "src/oline_hri/ollama.py",
    "src/oline_hri/relationships.py",
    "src/oline_hri/response.py",
    "src/oline_hri/retrieval.py",
    "src/oline_hri/routing.py",
)
_IDENTIFIER_PATTERN = re.compile(r"[a-z][a-z0-9_.-]{0,127}\Z")
_RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


class TemperatureExperimentError(RuntimeError):
    """Raised when a trustworthy paired experiment cannot be completed."""


@dataclass(frozen=True)
class TemperatureArm:
    """One generator-temperature arm."""

    name: str
    temperature: float


@dataclass(frozen=True)
class TemperatureExperimentPlan:
    """Validated immutable plan for a paired temperature experiment."""

    experiment_id: str
    description: str
    case_ids: tuple[str, ...]
    repetitions: int
    base_seed: int
    context_length: int
    max_output_tokens: int
    routing_mode: str
    evidence_mode: str
    arms: tuple[TemperatureArm, TemperatureArm]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": PLAN_SCHEMA_VERSION,
            "experiment_id": self.experiment_id,
            "description": self.description,
            "case_ids": list(self.case_ids),
            "repetitions": self.repetitions,
            "base_seed": self.base_seed,
            "context_length": self.context_length,
            "max_output_tokens": self.max_output_tokens,
            "routing_mode": self.routing_mode,
            "evidence_mode": self.evidence_mode,
            "arms": [
                {"name": arm.name, "temperature": arm.temperature}
                for arm in self.arms
            ],
        }


@dataclass(frozen=True)
class TemperatureExperimentResult:
    """Published artifacts from one completed experiment."""

    run_id: str
    observations_path: Path
    summary_path: Path
    paired_review_path: Path
    pair_key_path: Path
    manifest_path: Path
    attempts: int
    errors: int


class _AttemptBackend:
    """Override only generator sampling and retain bounded call metadata."""

    def __init__(
        self,
        delegate: Any,
        *,
        temperature: float,
        seed: int,
        clock_ns: Callable[[], int],
    ) -> None:
        self._delegate = delegate
        self._temperature = temperature
        self._seed = seed
        self._clock_ns = clock_ns
        self.calls: list[dict[str, object]] = []

    def chat(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        *,
        response_format: Optional[Mapping[str, Any]] = None,
        temperature: Optional[float] = None,
        seed: Optional[int] = None,
    ) -> ChatResult:
        purpose = _chat_purpose(response_format)
        if purpose == "generation":
            if temperature is not None or seed is not None:
                raise TemperatureExperimentError(
                    "generator supplied unexpected sampling overrides"
                )
            effective_temperature = self._temperature
            effective_seed = self._seed
        else:
            # ConversationRouter supplies its production temperature and seed
            # explicitly.  Never replace them with the experimental values.
            effective_temperature = temperature
            effective_seed = seed

        started = self._clock_ns()
        try:
            result = self._delegate.chat(
                model,
                messages,
                response_format=response_format,
                temperature=effective_temperature,
                seed=effective_seed,
            )
        except BaseException as exc:
            self.calls.append(
                {
                    "purpose": purpose,
                    "model": model,
                    "temperature": effective_temperature,
                    "seed": effective_seed,
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "wall_ns": _elapsed_ns(started, self._clock_ns()),
                    "generation": None,
                }
            )
            # Conversation's production policy retries a timed-out large
            # generation with the small model.  That is useful in chat, but it
            # would misattribute a 0.6B answer to a 4B temperature arm here.
            # Translate the timeout after recording it so this experiment has
            # exactly one generator attempt per declared arm slot.
            if purpose == "generation" and isinstance(exc, OllamaTimeoutError):
                raise TemperatureExperimentError(
                    "temperature experiment generation timed out"
                ) from None
            raise

        if not isinstance(result, ChatResult):
            self.calls.append(
                {
                    "purpose": purpose,
                    "model": model,
                    "temperature": effective_temperature,
                    "seed": effective_seed,
                    "status": "error",
                    "error_type": "InvalidChatResult",
                    "wall_ns": _elapsed_ns(started, self._clock_ns()),
                    "generation": None,
                }
            )
            return result
        self.calls.append(
            {
                "purpose": purpose,
                "model": model,
                "temperature": effective_temperature,
                "seed": effective_seed,
                "status": "ok",
                "error_type": None,
                "wall_ns": _elapsed_ns(started, self._clock_ns()),
                "generation": _generation_record(result),
            }
        )
        return result


class _ExpectedRouter:
    """Return evaluator-fixed route metadata without an inference call."""

    def __init__(self, decision: RouteDecision, *, model: str) -> None:
        self._result = RoutingResult(
            decision=decision,
            memory_required_generation=_fixed_route_generation(
                model,
                json.dumps(
                    {"memory_required": decision.memory_required},
                    separators=(",", ":"),
                ),
            ),
            model_size_generation=_fixed_route_generation(
                model,
                json.dumps(
                    {"model_size": decision.model_size},
                    separators=(",", ":"),
                ),
            ),
        )

    def route(
        self, user_text: str, *, history: Sequence[ChatMessage] = ()
    ) -> RoutingResult:
        return self._result


class _FixedRequiredRetriever:
    """Return exactly evaluator-required current records for one case."""

    def __init__(
        self,
        store: MemoryStore,
        case: EvaluationCase,
        items: Mapping[str, MemoryItem],
    ) -> None:
        self._store = store
        self._prompt = case.prompt
        required = case.retrieval_gold.required_ids
        if len(required) > 3:
            raise TemperatureExperimentError(
                "selected case requires more than three evidence records"
            )
        try:
            selected = tuple(items[memory_id] for memory_id in required)
        except KeyError:
            raise TemperatureExperimentError(
                "selected case requires unavailable evidence"
            ) from None
        if not store.retrieval_snapshot_is_current(selected):
            raise TemperatureExperimentError(
                "selected case requires ineligible evidence"
            )
        self._matches = tuple(
            HybridMatch(
                memory=item,
                fused_score=1.0 / (60 + position),
                keyword_rank=-1.0 / position,
                keyword_position=position,
                semantic_score=None,
                semantic_position=None,
            )
            for position, item in enumerate(selected, start=1)
        )

    def retrieve(self, query: str, *, limit: int = 3) -> tuple[HybridMatch, ...]:
        if query != self._prompt or limit != 3:
            raise TemperatureExperimentError(
                "fixed evidence was requested outside its declared case"
            )
        return self._matches

    def is_current(self, matches: Sequence[HybridMatch]) -> bool:
        return self._store.retrieval_snapshot_is_current(
            tuple(match.memory for match in matches)
        )


def load_experiment_plan(
    path: str | Path | None = None,
) -> TemperatureExperimentPlan:
    """Load and strictly validate one temperature-experiment plan."""

    source = _DEFAULT_PLAN_PATH if path is None else Path(path)
    try:
        metadata = source.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_PLAN_BYTES:
            raise TemperatureExperimentError("experiment plan is not a bounded file")
        raw = source.read_bytes()
    except TemperatureExperimentError:
        raise
    except (OSError, RuntimeError, ValueError):
        raise TemperatureExperimentError("experiment plan could not be read") from None
    if len(raw) > MAX_PLAN_BYTES:
        raise TemperatureExperimentError("experiment plan is too large")
    try:
        decoded = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except TemperatureExperimentError:
        raise
    except (UnicodeDecodeError, ValueError, OverflowError, RecursionError):
        raise TemperatureExperimentError("experiment plan is not valid JSON") from None
    return _parse_plan(decoded)


def validate_experiment_plan(
    plan: TemperatureExperimentPlan, suite: EvaluationSuite
) -> tuple[EvaluationCase, ...]:
    """Validate selected IDs against the exact suite and return manifest order."""

    if not isinstance(plan, TemperatureExperimentPlan):
        raise TemperatureExperimentError("experiment plan is invalid")
    if not isinstance(suite, EvaluationSuite):
        raise TemperatureExperimentError("evaluation suite is invalid")
    # Direct API callers must satisfy the same exact schema and bounds as a
    # JSON-loaded plan; frozen dataclasses alone do not enforce field values.
    if _parse_plan(plan.to_dict()) != plan:
        raise TemperatureExperimentError("experiment plan is invalid")
    known = {case.id: case for case in suite.cases}
    unknown = set(plan.case_ids).difference(known)
    if unknown:
        raise TemperatureExperimentError("experiment selects an unknown case ID")
    selected_ids = set(plan.case_ids)
    selected = tuple(case for case in suite.cases if case.id in selected_ids)
    if len(selected) != len(plan.case_ids):
        raise TemperatureExperimentError("experiment case selection is invalid")
    for case in selected:
        if len(case.retrieval_gold.required_ids) > 3:
            raise TemperatureExperimentError(
                "selected case exceeds fixed-evidence capacity"
            )
    return selected


def run_temperature_experiment(
    suite: EvaluationSuite,
    config: AppConfig,
    plan: TemperatureExperimentPlan,
    output_dir: str | Path,
    *,
    backend: Optional[Any] = None,
    run_id: Optional[str] = None,
    clock_ns: Callable[[], int] = perf_counter_ns,
    utc_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    progress: Optional[TextIO] = None,
    _blinding_nonce: Optional[bytes | str] = None,
) -> TemperatureExperimentResult:
    """Run paired attempts and publish canonical private artifacts."""

    if not isinstance(config, AppConfig):
        raise TemperatureExperimentError("configuration is invalid")
    if config.generation.thinking:
        raise TemperatureExperimentError("temperature experiment requires thinking=false")
    cases = validate_experiment_plan(plan, suite)
    normalized_run_id = _run_id(run_id)
    paths = _artifact_paths(output_dir)
    # Validate every destination before model or database work starts.
    for path in paths.values():
        _new_private_output_path(path)
    # The nonce is deliberately absent from the public experiment header.  Its
    # only serialized copy is written to pair_key.json after the blinded review
    # artifact has been created.
    blinding_nonce = _canonical_blinding_nonce(_blinding_nonce)

    effective_generation = replace(
        config.generation,
        context_length=plan.context_length,
        max_output_tokens=plan.max_output_tokens,
    )
    shared_backend = (
        backend
        if backend is not None
        else OllamaClient(config.ollama, effective_generation)
    )
    started_at = _timestamp(utc_now())
    suite_sha = evaluation_suite_sha256(suite)
    plan_sha = _canonical_sha256(plan.to_dict())
    header = {
        "record_type": "temperature_experiment_header",
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "run_id": normalized_run_id,
        "experiment_id": plan.experiment_id,
        "started_at": started_at,
        "suite_id": suite.suite_id,
        "suite_sha256": suite_sha,
        "config_sha256": _config_sha256(config),
        "plan_sha256": plan_sha,
        "case_ids": [case.id for case in cases],
        "repetitions": plan.repetitions,
        "base_seed": plan.base_seed,
        "context_length": plan.context_length,
        "max_output_tokens": plan.max_output_tokens,
        "thinking": False,
        "routing_mode": plan.routing_mode,
        "evidence_mode": plan.evidence_mode,
        "arms": [
            {"name": arm.name, "temperature": arm.temperature}
            for arm in plan.arms
        ],
        "models": {
            "router": config.ollama.small_model,
            "small_generator": config.ollama.small_model,
            "general_large_generator": config.ollama.general_large_model,
            "large_generator": config.ollama.large_model,
        },
        "source": _source_snapshot(),
    }

    attempts: list[dict[str, object]] = []
    output_path = paths[OBSERVATIONS_NAME]
    output_parent = output_path.parent
    with tempfile.TemporaryDirectory(
        prefix=".oline-hri-temperature-ab-", dir=str(output_parent)
    ) as directory:
        database_path = Path(directory) / "memory.sqlite3"
        store = materialize_memory_store(suite, database_path)
        items = {
            item.id: item for item in store.list_memories(include_inactive=True)
        }
        with _CanonicalJsonlWriter(output_path) as writer:
            writer.write(header)
            pair_ordinal = 0
            attempt_ordinal = 0
            for repetition in range(1, plan.repetitions + 1):
                paired_seed = plan.base_seed + repetition - 1
                for case in cases:
                    pair_ordinal += 1
                    ordered_arms = (
                        plan.arms
                        if pair_ordinal % 2 == 1
                        else tuple(reversed(plan.arms))
                    )
                    for arm in ordered_arms:
                        attempt_ordinal += 1
                        record = _run_attempt(
                            case,
                            arm,
                            repetition=repetition,
                            paired_seed=paired_seed,
                            pair_ordinal=pair_ordinal,
                            attempt_ordinal=attempt_ordinal,
                            run_id=normalized_run_id,
                            plan=plan,
                            config=config,
                            shared_backend=shared_backend,
                            store=store,
                            items=items,
                            clock_ns=clock_ns,
                            utc_now=utc_now,
                        )
                        attempts.append(record)
                        writer.write(record)
                        if progress is not None:
                            print(
                                f"temperature-ab {attempt_ordinal}/"
                                f"{len(cases) * plan.repetitions * 2} "
                                "attempts completed",
                                file=progress,
                                flush=True,
                            )
            writer.write(
                {
                    "record_type": "temperature_experiment_end",
                    "schema_version": OBSERVATION_SCHEMA_VERSION,
                    "run_id": normalized_run_id,
                    "finished_at": _timestamp(utc_now()),
                    "expected_attempts": len(cases) * plan.repetitions * 2,
                    "observed_attempts": len(attempts),
                    "errors": sum(item["status"] != "ok" for item in attempts),
                    "completed": True,
                }
            )

    summary = _summary(header, cases, attempts)
    review, key = _paired_review(
        header,
        cases,
        attempts,
        blinding_nonce=blinding_nonce,
    )
    _write_one(paths[SUMMARY_NAME], summary)
    _write_many(paths[PAIRED_REVIEW_NAME], review)
    _write_one(paths[PAIR_KEY_NAME], key)
    manifest_inputs = ARTIFACT_NAMES[:-1]
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "record_type": "temperature_experiment_manifest",
        "run_id": normalized_run_id,
        "experiment_id": plan.experiment_id,
        "plan_sha256": plan_sha,
        "suite_sha256": suite_sha,
        "artifacts_sha256": {
            name: sha256(paths[name].read_bytes()).hexdigest()
            for name in manifest_inputs
        },
    }
    _write_one(paths[MANIFEST_NAME], manifest)
    errors = sum(item["status"] != "ok" for item in attempts)
    return TemperatureExperimentResult(
        run_id=normalized_run_id,
        observations_path=paths[OBSERVATIONS_NAME],
        summary_path=paths[SUMMARY_NAME],
        paired_review_path=paths[PAIRED_REVIEW_NAME],
        pair_key_path=paths[PAIR_KEY_NAME],
        manifest_path=paths[MANIFEST_NAME],
        attempts=len(attempts),
        errors=errors,
    )


def _run_attempt(
    case: EvaluationCase,
    arm: TemperatureArm,
    *,
    repetition: int,
    paired_seed: int,
    pair_ordinal: int,
    attempt_ordinal: int,
    run_id: str,
    plan: TemperatureExperimentPlan,
    config: AppConfig,
    shared_backend: Any,
    store: MemoryStore,
    items: Mapping[str, MemoryItem],
    clock_ns: Callable[[], int],
    utc_now: Callable[[], datetime],
) -> dict[str, object]:
    attempt_backend = _AttemptBackend(
        shared_backend,
        temperature=arm.temperature,
        seed=paired_seed,
        clock_ns=clock_ns,
    )
    expected_decision = RouteDecision(
        case.expected_route.memory_required,
        case.expected_route.model_size,
    )
    router = (
        _ExpectedRouter(expected_decision, model=config.ollama.small_model)
        if plan.routing_mode == FIXED_EXPECTED
        else ConversationRouter(attempt_backend, model=config.ollama.small_model)
    )
    retriever = _FixedRequiredRetriever(store, case, items)
    conversation = Conversation(
        attempt_backend,
        system_prompt=config.conversation.system_prompt,
        router=router,
        retriever=retriever,
        small_model=config.ollama.small_model,
        general_large_model=config.ollama.general_large_model,
        large_model=config.ollama.large_model,
        context_length=plan.context_length,
        max_output_tokens=plan.max_output_tokens,
        # Compare sampled model prose, not application-composed constants.
        grounded_composition=False,
    )
    started = clock_ns()
    record: dict[str, object] = {
        "record_type": "temperature_experiment_attempt",
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "run_id": run_id,
        "attempt_ordinal": attempt_ordinal,
        "pair_ordinal": pair_ordinal,
        "repetition": repetition,
        "case_id": case.id,
        "arm": arm.name,
        "temperature": arm.temperature,
        "seed": paired_seed,
        "started_at": _timestamp(utc_now()),
        "status": "error",
        "error_type": None,
        "wall_ns": None,
        "route": None,
        "response": None,
        "generation": None,
        "citation_annotations_removed": 0,
        "fallback_from_model": None,
        "memory_diagnostics": None,
        "backend_calls": None,
    }
    try:
        reply = conversation.send(case.prompt)
        if reply.fallback_from_model is not None:
            raise TemperatureExperimentError(
                "temperature experiment unexpectedly used a fallback"
            )
        record.update(_reply_record(reply))
        record["status"] = "ok"
    except BaseException as exc:
        if not isinstance(exc, Exception):
            raise
        record["error_type"] = type(exc).__name__
    finally:
        record["wall_ns"] = _elapsed_ns(started, clock_ns())
        backend_calls = list(attempt_backend.calls)
        record["backend_calls"] = backend_calls
        # Keep boundary sanitization visible even when a later application
        # validator rejects the response and no top-level generation survives.
        record["citation_annotations_removed"] = sum(
            _recorded_citation_annotations_removed(call.get("generation"))
            for call in backend_calls
            if call.get("purpose") == "generation"
        )
    return record


def _reply_record(reply: ConversationReply) -> dict[str, object]:
    route = reply.route
    if route is None:
        raise TemperatureExperimentError("adaptive experiment returned no route")
    return {
        "route": {
            "memory_required": route.decision.memory_required,
            "model_size": route.decision.model_size,
        },
        "response": reply.response.to_dict(),
        "generation": _generation_record(reply.generation),
        "fallback_from_model": reply.fallback_from_model,
        "memory_diagnostics": reply.memory_diagnostics.to_dict(),
    }


def _summary(
    header: Mapping[str, object],
    cases: Sequence[EvaluationCase],
    attempts: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    case_map = {case.id: case for case in cases}
    arms = tuple(str(item["name"]) for item in header["arms"])
    per_arm: dict[str, object] = {}
    for arm in arms:
        selected = tuple(item for item in attempts if item["arm"] == arm)
        successful = tuple(item for item in selected if item["status"] == "ok")
        wall = [int(item["wall_ns"]) for item in selected]
        generation_calls = [
            call
            for item in selected
            for call in item["backend_calls"]
            if call["purpose"] == "generation"
        ]
        output_tokens = [
            int(call["generation"]["eval_count"])
            for call in generation_calls
            if call["generation"] is not None
        ]
        annotation_counts = [
            _attempt_citation_annotations_removed(item) for item in selected
        ]
        attempts_with_annotations_removed = sum(
            count > 0 for count in annotation_counts
        )
        route_correct = 0
        evidence_exact = 0
        citation_exact = 0
        for item in successful:
            case = case_map[str(item["case_id"])]
            expected_route = {
                "memory_required": case.expected_route.memory_required,
                "model_size": case.expected_route.model_size,
            }
            route_correct += item["route"] == expected_route
            diagnostics = item["memory_diagnostics"]
            evidence_exact += (
                diagnostics["supplied_ids"]
                == list(case.retrieval_gold.required_ids)
            )
            citation_exact += (
                diagnostics["model_used_ids"]
                == list(case.answer_rubric.required_citation_ids)
            )
        per_arm[arm] = {
            "expected_attempts": len(cases) * int(header["repetitions"]),
            "observed_attempts": len(selected),
            "successful_attempts": len(successful),
            "error_attempts": len(selected) - len(successful),
            "structured_success_rate": _ratio(len(successful), len(selected)),
            "route_accuracy": _ratio(route_correct, len(selected)),
            "fixed_evidence_exact_rate": _ratio(evidence_exact, len(selected)),
            "required_citation_exact_rate": _ratio(
                citation_exact, len(selected)
            ),
            "attempt_wall_ns": _distribution(wall),
            "generator_wall_ns": _distribution(
                [int(call["wall_ns"]) for call in generation_calls]
            ),
            "output_tokens": _distribution(output_tokens),
            "citation_annotations_removed": sum(annotation_counts),
            "attempts_with_citation_annotations_removed": (
                attempts_with_annotations_removed
            ),
            "citation_annotation_removal_rate": _ratio(
                attempts_with_annotations_removed, len(selected)
            ),
            "large_generator_invocations": sum(
                call["model"]
                in {
                    header["models"]["general_large_generator"],
                    header["models"]["large_generator"],
                }
                for call in generation_calls
            ),
            "fallback_attempts": sum(
                item["fallback_from_model"] is not None for item in successful
            ),
        }
    expected = len(cases) * int(header["repetitions"]) * 2
    return {
        "record_type": "temperature_experiment_summary",
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "run_id": header["run_id"],
        "experiment_id": header["experiment_id"],
        "suite_sha256": header["suite_sha256"],
        "plan_sha256": header["plan_sha256"],
        "routing_mode": header["routing_mode"],
        "evidence_mode": header["evidence_mode"],
        "expected_attempts": expected,
        "observed_attempts": len(attempts),
        "completed": len(attempts) == expected,
        "arms": per_arm,
        "answer_quality": {
            "status": "pending_blinded_paired_review",
            "preferred_arm": None,
            "review_pairs": len(cases) * int(header["repetitions"]),
            "note": (
                "Objective runtime metrics do not select the better response. "
                "Complete paired_review.jsonl before decoding pair_key.json."
            ),
        },
        "limitations": [
            "One-repetition default is a pilot, not a variability estimate.",
            "Fixed expected routing and required evidence isolate generation "
            "temperature and do not measure adaptive routing or retrieval quality.",
            "Paired human review is required for response-quality conclusions.",
        ],
    }


def _paired_review(
    header: Mapping[str, object],
    cases: Sequence[EvaluationCase],
    attempts: Sequence[Mapping[str, object]],
    *,
    blinding_nonce: str,
) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
    by_slot = {
        (int(item["repetition"]), str(item["case_id"]), str(item["arm"])): item
        for item in attempts
    }
    arm_names = tuple(str(item["name"]) for item in header["arms"])
    blind_offset = _blinding_orientation(blinding_nonce)
    reviews = []
    mappings = []
    pair_index = 0
    for repetition in range(1, int(header["repetitions"]) + 1):
        for case in cases:
            pair_index += 1
            opaque = json.dumps(
                [header["run_id"], repetition, case.id],
                ensure_ascii=True,
                separators=(",", ":"),
            )
            review_id = "pair_" + sha256(opaque.encode("utf-8")).hexdigest()[:24]
            # Pick one secret starting orientation per run, then alternate it
            # across pairs. Independent per-case coin flips can accidentally
            # put one arm first in every row of a small pilot.
            ordered_names = (
                arm_names
                if (blind_offset + pair_index - 1) % 2 == 0
                else tuple(reversed(arm_names))
            )
            candidates = []
            candidate_map: dict[str, str] = {}
            for position, arm_name in enumerate(ordered_names, start=1):
                label = f"candidate_{position}"
                item = by_slot[(repetition, case.id, arm_name)]
                answered = item["status"] == "ok"
                response = item["response"] if answered else None
                candidates.append(
                    {
                        "label": label,
                        "response_status": "answered" if answered else "failed",
                        "response_speech": (
                            response["speech"] if response is not None else None
                        ),
                        "required_citation_exact": (
                            response["memory_used"]
                            == list(case.answer_rubric.required_citation_ids)
                            if response is not None
                            else False
                        ),
                    }
                )
                candidate_map[label] = arm_name
            reviews.append(
                {
                    "schema_version": REVIEW_SCHEMA_VERSION,
                    "review_id": review_id,
                    "prompt": case.prompt,
                    "rubric": {
                        "mode": case.answer_rubric.mode,
                        "reference_answer": case.answer_rubric.reference_answer,
                        "required_claims": list(case.answer_rubric.required_claims),
                        "forbidden_claims": list(case.answer_rubric.forbidden_claims),
                    },
                    "candidates": candidates,
                    "judgment": {
                        "preference": None,
                        "candidate_1_correct": None,
                        "candidate_2_correct": None,
                        "notes": None,
                    },
                }
            )
            mappings.append(
                {
                    "review_id": review_id,
                    "case_id": case.id,
                    "repetition": repetition,
                    "paired_seed": int(header["base_seed"]) + repetition - 1,
                    **candidate_map,
                }
            )
    key = {
        "record_type": "temperature_experiment_pair_key",
        "schema_version": MAPPING_SCHEMA_VERSION,
        "run_id": header["run_id"],
        "experiment_id": header["experiment_id"],
        "warning": "Open only after paired review judgments are frozen.",
        "blinding_nonce": blinding_nonce,
        "orientation_algorithm": "hmac-sha256-domain-v1-low-bit",
        "mappings": mappings,
    }
    return tuple(reviews), key


def _canonical_blinding_nonce(value: Optional[bytes | str]) -> str:
    """Return one validated 256-bit nonce in canonical lowercase hex."""

    if value is None:
        raw = token_bytes(_BLINDING_NONCE_BYTES)
    elif isinstance(value, bytes):
        raw = value
    elif isinstance(value, str):
        if re.fullmatch(r"[0-9A-Fa-f]{64}", value) is None:
            raise TemperatureExperimentError("blinding nonce is invalid")
        raw = bytes.fromhex(value)
    else:
        raise TemperatureExperimentError("blinding nonce is invalid")
    if len(raw) != _BLINDING_NONCE_BYTES:
        raise TemperatureExperimentError("blinding nonce is invalid")
    return raw.hex()


def _blinding_orientation(blinding_nonce: str) -> int:
    """Derive the first candidate orientation without using public metadata."""

    canonical = _canonical_blinding_nonce(blinding_nonce)
    digest = hmac_new(
        bytes.fromhex(canonical),
        _BLINDING_ORIENTATION_DOMAIN,
        sha256,
    ).digest()
    return digest[0] & 1


def _parse_plan(value: object) -> TemperatureExperimentPlan:
    data = _exact_mapping(
        value,
        {
            "schema_version",
            "experiment_id",
            "description",
            "case_ids",
            "repetitions",
            "base_seed",
            "context_length",
            "max_output_tokens",
            "routing_mode",
            "evidence_mode",
            "arms",
        },
        "experiment plan",
    )
    if _integer(data["schema_version"], "schema_version", 1, 1) != 1:
        raise TemperatureExperimentError("unsupported experiment plan schema")
    experiment_id = _identifier(data["experiment_id"], "experiment_id")
    description = _text(data["description"], "description", 1, 1000)
    raw_cases = _array(data["case_ids"], "case_ids", 1, 30)
    case_ids = tuple(_identifier(item, "case_id") for item in raw_cases)
    if len(case_ids) != len(set(case_ids)):
        raise TemperatureExperimentError("experiment case IDs must be unique")
    repetitions = _integer(data["repetitions"], "repetitions", 1, MAX_REPETITIONS)
    base_seed = _integer(data["base_seed"], "base_seed", 0, 2**63 - 1)
    if base_seed + repetitions - 1 > 2**63 - 1:
        raise TemperatureExperimentError("paired seed schedule is out of range")
    context_length = _integer(
        data["context_length"], "context_length", 128, 131072
    )
    max_output_tokens = _integer(
        data["max_output_tokens"], "max_output_tokens", 1, context_length
    )
    routing_mode = _choice(
        data["routing_mode"],
        "routing_mode",
        {FIXED_EXPECTED, PRODUCTION_ADAPTIVE},
    )
    evidence_mode = _choice(
        data["evidence_mode"], "evidence_mode", {FIXED_REQUIRED}
    )
    raw_arms = _array(data["arms"], "arms", 2, 2)
    arms = []
    for raw_arm in raw_arms:
        arm = _exact_mapping(raw_arm, {"name", "temperature"}, "arm")
        arms.append(
            TemperatureArm(
                name=_identifier(arm["name"], "arm name"),
                temperature=_number(arm["temperature"], "temperature", 0.0, 2.0),
            )
        )
    if len({arm.name for arm in arms}) != 2:
        raise TemperatureExperimentError("arm names must be unique")
    if arms[0].temperature == arms[1].temperature:
        raise TemperatureExperimentError("arm temperatures must differ")
    return TemperatureExperimentPlan(
        experiment_id=experiment_id,
        description=description,
        case_ids=case_ids,
        repetitions=repetitions,
        base_seed=base_seed,
        context_length=context_length,
        max_output_tokens=max_output_tokens,
        routing_mode=routing_mode,
        evidence_mode=evidence_mode,
        arms=(arms[0], arms[1]),
    )


def _artifact_paths(output_dir: str | Path) -> dict[str, Path]:
    try:
        directory = Path(output_dir).expanduser()
    except (TypeError, ValueError, RuntimeError):
        raise TemperatureExperimentError("output directory is invalid") from None
    return {name: directory / name for name in ARTIFACT_NAMES}


def _source_snapshot() -> dict[str, object]:
    files = []
    aggregate = sha256()
    for relative in _SOURCE_PATHS:
        path = _PROJECT_ROOT / relative
        try:
            payload = path.read_bytes()
        except OSError:
            raise TemperatureExperimentError(
                "experiment source provenance could not be captured"
            ) from None
        encoded_path = relative.encode("utf-8")
        aggregate.update(len(encoded_path).to_bytes(4, "big"))
        aggregate.update(encoded_path)
        aggregate.update(len(payload).to_bytes(8, "big"))
        aggregate.update(payload)
        files.append(
            {
                "path": relative,
                "size_bytes": len(payload),
                "sha256": sha256(payload).hexdigest(),
            }
        )
    return {
        "aggregate_algorithm": (
            "sha256-u32be-path-length-path-u64be-content-length-content-v1"
        ),
        "aggregate_sha256": aggregate.hexdigest(),
        "files": files,
    }


def _write_one(path: Path, value: Mapping[str, object]) -> None:
    with _CanonicalJsonlWriter(path) as writer:
        writer.write(value)


def _write_many(path: Path, values: Sequence[Mapping[str, object]]) -> None:
    with _CanonicalJsonlWriter(path) as writer:
        for value in values:
            writer.write(value)


def _chat_purpose(response_format: Optional[Mapping[str, Any]]) -> str:
    if not isinstance(response_format, Mapping):
        return "unknown"
    if "oneOf" in response_format:
        from .semantic_routing import SEMANTIC_REVIEW_SCHEMA

        return "route_memory_required" if response_format == SEMANTIC_REVIEW_SCHEMA else "unknown"
    properties = response_format.get("properties")
    if not isinstance(properties, Mapping):
        return "unknown"
    fields = frozenset(properties)
    if fields in ({"memory_required"}, {"form", "memory_required"}):
        return "route_memory_required"
    if fields == {"needs_personal_facts"}:
        from .dependency_review import DEPENDENCY_REVIEW_SCHEMA

        if response_format == DEPENDENCY_REVIEW_SCHEMA:
            return "route_dependency_review"
    if fields == {"form", "mode"}:
        from .semantic_routing import SEMANTIC_MODE_SCHEMA

        if response_format == SEMANTIC_MODE_SCHEMA:
            return "route_memory_required"
    if fields == {"answer_source"}:
        from .semantic_routing import ANSWERABILITY_SCHEMA

        if response_format == ANSWERABILITY_SCHEMA:
            return "route_answerability"
    if fields == {"form", "mode", "missing_fact", "general_request", "uncertain"}:
        from .semantic_routing import SEMANTIC_MEMORY_SCHEMA

        if response_format == SEMANTIC_MEMORY_SCHEMA:
            return "route_memory_required"
    if fields == {"model_size"}:
        return "route_model_size"
    if fields == {"speech", "gesture_id", "memory_used"}:
        return "generation"
    return "unknown"


def _fixed_route_generation(model: str, content: str) -> ChatResult:
    return ChatResult(
        model=model,
        content=content,
        done_reason="fixed_experiment",
        total_duration_ns=0,
        load_duration_ns=0,
        prompt_eval_count=0,
        eval_count=0,
        eval_duration_ns=0,
    )


def _generation_record(value: ChatResult) -> dict[str, object]:
    return {
        "model": value.model,
        "content": value.content,
        "done_reason": value.done_reason,
        "total_duration_ns": value.total_duration_ns,
        "load_duration_ns": value.load_duration_ns,
        "prompt_eval_count": value.prompt_eval_count,
        "prompt_eval_duration_ns": value.prompt_eval_duration_ns,
        "eval_count": value.eval_count,
        "eval_duration_ns": value.eval_duration_ns,
        "citation_annotations_removed": _chat_result_citation_annotations_removed(
            value
        ),
    }


def _chat_result_citation_annotations_removed(value: ChatResult) -> int:
    """Return validated additive telemetry, defaulting older results to zero."""

    removed = getattr(value, "citation_annotations_removed", 0)
    if type(removed) is not int or removed < 0:
        raise TemperatureExperimentError(
            "chat result contains invalid citation-annotation telemetry"
        )
    return removed


def _recorded_citation_annotations_removed(value: object) -> int:
    """Read one optional generation-record count without breaking v1 data."""

    if not isinstance(value, Mapping):
        return 0
    removed = value.get("citation_annotations_removed", 0)
    if type(removed) is not int or removed < 0:
        raise TemperatureExperimentError(
            "generation record contains invalid citation-annotation telemetry"
        )
    return removed


def _attempt_citation_annotations_removed(value: Mapping[str, object]) -> int:
    """Read the v2 attempt aggregate while treating historical v1 as zero."""

    removed = value.get("citation_annotations_removed", 0)
    if type(removed) is not int or removed < 0:
        raise TemperatureExperimentError(
            "attempt contains invalid citation-annotation telemetry"
        )
    return removed


def _distribution(values: Sequence[int]) -> dict[str, Optional[int]]:
    if not values:
        return {"count": 0, "p50": None, "p95": None, "total": 0}
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "p50": ordered[max(0, ceil(0.50 * len(ordered)) - 1)],
        "p95": ordered[max(0, ceil(0.95 * len(ordered)) - 1)],
        "total": sum(ordered),
    }


def _ratio(numerator: int, denominator: int) -> Optional[float]:
    return None if denominator == 0 else numerator / denominator


def _elapsed_ns(started: int, finished: int) -> int:
    elapsed = finished - started
    if elapsed < 0:
        raise TemperatureExperimentError("monotonic clock moved backwards")
    return elapsed


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise TemperatureExperimentError("experiment timestamp is invalid")
    normalized = value.astimezone(timezone.utc)
    return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _run_id(value: Optional[str]) -> str:
    result = uuid4().hex if value is None else value
    if not isinstance(result, str) or _RUN_ID_PATTERN.fullmatch(result) is None:
        raise TemperatureExperimentError("run ID is invalid")
    return result


def _canonical_sha256(value: Mapping[str, object]) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        raise TemperatureExperimentError("experiment plan is not canonical") from None
    return sha256(payload).hexdigest()


def _exact_mapping(
    value: object, fields: set[str], label: str
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise TemperatureExperimentError(f"{label} fields are invalid")
    return value


def _array(value: object, label: str, minimum: int, maximum: int) -> list[object]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise TemperatureExperimentError(f"{label} is invalid")
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise TemperatureExperimentError(f"{label} is invalid")
    return value


def _text(value: object, label: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise TemperatureExperimentError(f"{label} is invalid")
    return value


def _integer(value: object, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TemperatureExperimentError(f"{label} is invalid")
    if not minimum <= value <= maximum:
        raise TemperatureExperimentError(f"{label} is out of range")
    return value


def _number(value: object, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TemperatureExperimentError(f"{label} is invalid")
    result = float(value)
    if not minimum <= result <= maximum:
        raise TemperatureExperimentError(f"{label} is out of range")
    return result


def _choice(value: object, label: str, choices: set[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise TemperatureExperimentError(f"{label} is invalid")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise TemperatureExperimentError("experiment plan has duplicate fields")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise TemperatureExperimentError("experiment plan has a nonstandard number")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m oline_hri.evaluation_experiment",
        description="Run a paired two-temperature response-quality experiment",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate plan and case IDs")
    validate.add_argument("--plan", type=Path, default=None)
    validate.add_argument("--dataset", type=Path, default=None)
    run = commands.add_parser("run", help="run the paired local experiment")
    run.add_argument("--plan", type=Path, default=None)
    run.add_argument("--dataset", type=Path, default=None)
    run.add_argument("--config", type=Path, default=None)
    run.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    """Validate or execute without printing prompts, answers, or private errors."""

    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    args = _build_parser().parse_args(argv)
    try:
        plan = load_experiment_plan(args.plan)
        suite = load_evaluation_suite(args.dataset)
        cases = validate_experiment_plan(plan, suite)
        if args.command == "validate":
            print(
                f"temperature experiment plan valid: {plan.experiment_id} "
                f"({len(cases)} cases, {plan.repetitions} repetition)",
                file=output,
            )
            return 0
        config = load_config(args.config)
        result = run_temperature_experiment(
            suite,
            config,
            plan,
            args.output_dir,
            progress=errors,
        )
    except KeyboardInterrupt:
        print(
            "temperature experiment interrupted; completed observations retained",
            file=errors,
        )
        return 130
    except (
        ConfigError,
        EvaluationError,
        EvaluationRunError,
        TemperatureExperimentError,
        OSError,
        ValueError,
    ):
        print(
            "temperature experiment error: request could not be completed safely",
            file=errors,
        )
        return 2
    print(
        f"temperature experiment complete: {result.run_id} "
        f"({result.attempts} attempts, {result.errors} errors)",
        file=output,
    )
    return 0 if result.errors == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
