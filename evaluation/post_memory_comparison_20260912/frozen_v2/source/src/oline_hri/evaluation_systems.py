"""Explicit experimental adapters for complete single-model system comparisons.

Production adaptive defaults are unchanged. Fixed systems classify only memory
need, using their own sole model; compute selection is configuration, not a
second classifier call. Conversation retains its production retrieval, helpers,
and validators while its explicit fixed-generator option enforces generation.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from .config import AppConfig
from .ollama import ChatMessage, ChatResult, OllamaError
from .routing import (
    MEMORY_REQUIRED_SCHEMA, ROUTER_SEED, ROUTER_TEMPERATURE,
    RouteDecision, RoutingBackend, RoutingError, RoutingResult,
    _memory_classifier_inputs, memory_intent_policy, parse_memory_required_decision,
)


def single_model_config(config: AppConfig, model: str) -> AppConfig:
    """Give the sole model permanent residency and no configured peer models.

Pass the original distinct logical role names to Conversation, together with
fixed_generator_model=model; pass this derived config only to OllamaClient.
The selected model retains its original request timeout and generation config.
"""
    original = config.ollama
    if model not in {original.small_model, original.general_large_model, original.large_model}:
        raise ValueError("single model must be one of the original configured models")
    timeout = (original.request_timeout_seconds if model == original.small_model
               else original.large_request_timeout_seconds)
    return replace(config, ollama=replace(
        original, small_model=model, general_large_model=model, large_model=model,
        request_timeout_seconds=timeout,
    ))


class MemoryOnlyRouter:
    """One genuine memory classifier call and an explicitly fixed compute route."""

    def __init__(self, backend: RoutingBackend, *, model: str, fixed_model_size: str):
        if not isinstance(model, str) or not model.strip() or model != model.strip():
            raise ValueError("memory classifier model must be a nonempty exact name")
        if fixed_model_size not in {"small", "large"}:
            raise ValueError("fixed_model_size must be small or large")
        self._backend = backend
        self._model = model
        self._fixed_model_size = fixed_model_size

    def route(self, user_text: str, *, history: Sequence[ChatMessage] = ()) -> RoutingResult:
        text, prior_turns, _, memory_messages = _memory_classifier_inputs(user_text, history)
        try:
            generation = self._backend.chat(
                self._model, memory_messages, response_format=MEMORY_REQUIRED_SCHEMA,
                temperature=ROUTER_TEMPERATURE, seed=ROUTER_SEED,
            )
        except Exception:
            raise RoutingError("memory classification request failed") from None
        if not isinstance(generation, ChatResult):
            raise RoutingError("memory classifier returned malformed metadata")
        if generation.model != self._model:
            raise RoutingError("memory classifier returned unexpected model metadata")
        if generation.done_reason == "length":
            raise RoutingError("memory classifier response was truncated")
        memory_required = parse_memory_required_decision(generation.content, require_form=True)
        policy, source = memory_intent_policy(text, prior_turns)
        if policy is not None:
            memory_required = policy
        return RoutingResult(
            decision=RouteDecision(memory_required, self._fixed_model_size),
            memory_required_generation=generation,
            model_size_generation=None,
            memory_decision_source=source,
            model_size_decision_source="fixed_generator",
        )


class OptimizedMemoryOnlyRouter:
    """Shared policy-first memory intent with zero or one sole-model call.

    Compute is fixed configuration. This explicit adapter avoids charging a
    fixed system for a classifier whose answer the common policy already knows.
    The historical one-call adapter above remains unchanged for its old runs.
    """

    def __init__(self, backend: RoutingBackend, *, model: str, fixed_model_size: str):
        if not isinstance(model, str) or not model.strip() or model != model.strip():
            raise ValueError("fixed model must be a nonempty exact name")
        if fixed_model_size not in {"small", "large"}:
            raise ValueError("fixed_model_size must be small or large")
        self._backend, self._model = backend, model
        self._fixed_model_size = fixed_model_size

    def route(self, user_text: str, *, history: Sequence[ChatMessage] = ()) -> RoutingResult:
        text, prior_turns, _, messages = _memory_classifier_inputs(user_text, history)
        memory_required, source = memory_intent_policy(text, prior_turns)
        generation = None
        if memory_required is None:
            try:
                generation = self._backend.chat(
                    self._model, messages, response_format=MEMORY_REQUIRED_SCHEMA,
                    temperature=ROUTER_TEMPERATURE, seed=ROUTER_SEED,
                )
            except OllamaError:
                raise RoutingError("fixed memory classification request failed") from None
            if not isinstance(generation, ChatResult) or generation.model != self._model:
                raise RoutingError("fixed memory classifier returned unexpected metadata")
            if generation.done_reason != "stop":
                raise RoutingError("fixed memory classifier did not complete")
            memory_required = parse_memory_required_decision(generation.content, require_form=True)
            source = "fixed_model"
        resident = getattr(self._backend, "resident_model", None)
        return RoutingResult(
            decision=RouteDecision(memory_required, self._fixed_model_size),
            memory_required_generation=generation, model_size_generation=None,
            memory_decision_source=source, model_size_decision_source="fixed_generator",
            policy="fixed_memory_v1", resident_model=resident if resident == self._model else None,
            fixed_generator_model=self._model,
        )
