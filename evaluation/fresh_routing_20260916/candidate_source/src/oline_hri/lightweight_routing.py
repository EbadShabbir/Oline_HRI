"""Explicit heuristic routing with one optional resident-model memory call.

This policy is untrained and makes no accuracy or performance guarantee. Unknown
reasoning demand selects the large generator. Memory need remains independent
of compute demand, using the existing intent gates and classifier contract.
"""

from __future__ import annotations

import re
from threading import Lock
from typing import Sequence

from .ollama import ChatMessage, ChatResult, OllamaError
from .timing import traced, trace_span
from .routing import (
    MEMORY_REQUIRED_SCHEMA,
    ROUTER_SEED,
    ROUTER_TEMPERATURE,
    RouteDecision,
    RoutingBackend,
    RoutingError,
    RoutingResult,
    _memory_classifier_inputs,
    memory_intent_policy,
    parse_memory_required_decision,
    requires_large_reasoning,
)


_SOCIAL = re.compile(
    r"(?:hello|hi|hey|good\s+(?:morning|afternoon|evening|night)|"
    r"thanks|thank\s+you|you(?:'|’)re\s+welcome|goodbye|bye|"
    r"how\s+are\s+you)[.!?\s]*", re.IGNORECASE,
)
_REASONING_OR_CONSTRAINT = re.compile(
    r"\b(?:compare|contrast|reconcile|reason(?:ing)?|analy[sz]e|evaluate|"
    r"justify|prove|derive|optimi[sz]e|plan|schedule|timeline|sequence|order|"
    r"steps?|coordinate|synthesi[sz]e|"
    r"calculate|compute|solve|explain|why|how|before|after|unless|while|"
    r"must|should|constraints?|conditions?|budget|limits?|least|most|"
    r"required|optional|both|each|either|neither|except|remaining|difference|"
    r"total|until|within|between|best|worst|shortest|longest|cheapest|"
    r"times|divided|multiply|subtract|sum|ratio|percent|probability|"
    r"equation|matrix|integral|derivative|factorial|proof)\b|"
    r"\btrade[ -]?offs?\b|\b(?:and|then|but|versus)\b|[+*/=<>]",
    re.IGNORECASE,
)
_DIRECT_QUESTION = re.compile(
    r"(?:what|which|who|when|where)\s+"
    r"(?:is|are|was|were|do|does|did|have|has)\s+[\w'’ -]+[.!?\s]*",
    re.IGNORECASE,
)
_DIRECT_FACT = re.compile(
    r"(?:who\s+(?:wrote|invented|discovered|created|painted|composed|founded)|"
    r"(?:please\s+)?define)\s+[\w'’ -]+[.!?\s]*", re.IGNORECASE,
)


def _small_eligible(text: str, prior_turns: Sequence[ChatMessage]) -> bool:
    """Bounded easy-case recognition; length alone never establishes difficulty."""
    if requires_large_reasoning(text):
        return False
    if _SOCIAL.fullmatch(text):
        return True
    if prior_turns or _REASONING_OR_CONSTRAINT.search(text):
        return False
    if len(text) > 180 or len(text.split()) > 18:
        return False
    return bool(_DIRECT_QUESTION.fullmatch(text) or _DIRECT_FACT.fullmatch(text))


class LightweightRouter:
    """Deterministic compute choice and at most one memory classifier call.

The backend's optional resident_model property must be a cached hint, not an
HTTP query. This router never loads/unloads a model solely to classify compute.
Consecutive easy turns are counted only while the large model remains resident.
"""

    def __init__(self, backend: RoutingBackend, *, small_model: str,
                 large_model: str, small_streak_before_switch: int = 2) -> None:
        for name in (small_model, large_model):
            if not isinstance(name, str) or not name.strip() or name != name.strip():
                raise ValueError("router models must be nonempty exact model names")
        if small_model == large_model:
            raise ValueError("lightweight routing requires distinct small and large models")
        if type(small_streak_before_switch) is not int or small_streak_before_switch <= 0:
            raise ValueError("small_streak_before_switch must be a positive integer")
        self._backend = backend
        self._small_model, self._large_model = small_model, large_model
        self._small_streak_before_switch = small_streak_before_switch
        self._small_streak = 0
        self._lock = Lock()

    def _resident_hint(self) -> str | None:
        value = getattr(self._backend, "resident_model", None)
        return value if isinstance(value, str) and value in {self._small_model, self._large_model} else None

    def route(self, user_text: str, *, history: Sequence[ChatMessage] = ()) -> RoutingResult:
        with self._lock:
            with trace_span("deterministic_routing", policy="lightweight_v1", phase="initial") as timing:
                text, prior_turns, _, messages = _memory_classifier_inputs(user_text, history)
                resident = self._resident_hint()
                easy = _small_eligible(text, prior_turns)
                if not easy or resident != self._large_model:
                    self._small_streak = 0
                streak = (min(self._small_streak + 1, self._small_streak_before_switch)
                          if easy and resident == self._large_model else 0)
                if not easy:
                    size, size_source = "large", "lightweight_large"
                elif resident == self._large_model and streak < self._small_streak_before_switch:
                    size, size_source = "large", "lightweight_resident"
                else:
                    size, size_source = "small", "lightweight_small"
                preferred = self._small_model if size == "small" else self._large_model
                memory_required, memory_source = memory_intent_policy(text, prior_turns)
                timing.update(easy=easy, resident_hint=resident, small_streak=streak, model_size=size, model_size_source=size_source, memory_required=memory_required, memory_source=memory_source)
            memory_generation = None
            if memory_required is None:
                memory_generation = self._classify(resident or preferred, messages)
                memory_required = parse_memory_required_decision(memory_generation.content, require_form=True)
                memory_source = "resident_model"
            with trace_span("deterministic_routing", policy="lightweight_v1", phase="final") as timing:
                end_resident = self._resident_hint()
                if size_source == "lightweight_resident" and end_resident != self._large_model:
                    size_source = "lightweight_large"
                self._small_streak = streak if end_resident == self._large_model else 0
                timing.update(resident_hint=end_resident, small_streak=self._small_streak, model_size=size, model_size_source=size_source, memory_required=memory_required, memory_source=memory_source)
            return RoutingResult(
                decision=RouteDecision(memory_required, size),
                memory_required_generation=memory_generation,
                model_size_generation=None,
                memory_decision_source=memory_source,
                model_size_decision_source=size_source,
                policy="lightweight_v1", resident_model=end_resident,
            )

    @traced("memory_classifier")
    def _classify(self, model: str, messages: Sequence[ChatMessage]) -> ChatResult:
        try:
            generation = self._backend.chat(
                model, messages, response_format=MEMORY_REQUIRED_SCHEMA,
                temperature=ROUTER_TEMPERATURE, seed=ROUTER_SEED,
            )
        except OllamaError:
            raise RoutingError("memory classification request failed") from None
        # Other exceptions, including safety/boot guards and BaseException
        # interrupts, propagate unchanged rather than becoming fallback routes.
        if not isinstance(generation, ChatResult):
            raise RoutingError("memory classifier returned malformed metadata")
        if generation.model != model:
            raise RoutingError("memory classifier returned unexpected model metadata")
        if generation.done_reason == "length":
            raise RoutingError("memory classifier response was truncated")
        if generation.done_reason != "stop":
            raise RoutingError("memory classifier did not report a completed response")
        return generation
