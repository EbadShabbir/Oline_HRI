"""Local learned dependency decisions with independent generator selection.

The classifier predicts a request dependency, never a personal fact. Margins
are finite calibration diagnostics; rejected predictions ask for clarification.
The Qwen semantic experiment remains separately reproducible.
"""

from dataclasses import asdict, is_dataclass
import math
import re

from .ollama import ChatResult, OllamaError
from .routing import (
    MODEL_SIZE_SCHEMA, ROUTER_SEED, ROUTER_TEMPERATURE, RouteDecision,
    RoutingError, _bounded_history, _classification_messages,
    _encoded_classifier_input, _user_text, parse_model_size_decision,
)
from .semantic_routing import MemoryDependency, SemanticRoutingResult, SEMANTIC_SIZE_SYSTEM_PROMPT
from .timing import trace_span


_MODES = frozenset({"none", "optional", "required", "clarify"})


def _finite(value):
    if type(value) not in {int, float}:
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _prediction_mode(prediction):
    if not is_dataclass(prediction) or isinstance(prediction, type):
        raise RoutingError("dependency classifier returned an invalid prediction")
    try:
        mode, raw, uncertain = prediction.mode, prediction.predicted_mode, prediction.uncertain
        scores, margin, threshold = prediction.scores, prediction.margin, prediction.threshold
    except AttributeError:
        raise RoutingError("dependency classifier returned an invalid prediction") from None
    if (type(mode) is not str or type(raw) is not str
            or mode not in _MODES or raw not in _MODES
            or type(uncertain) is not bool
            or not isinstance(scores, dict) or set(scores) != _MODES
            or any(not _finite(value) for value in (*scores.values(), margin, threshold))
            or margin < 0 or threshold < 0
            or not isinstance(getattr(prediction, "model_manifest", None), dict)
            or (uncertain and mode != "clarify") or (not uncertain and mode != raw)):
        raise RoutingError("dependency classifier returned an invalid decision")
    if uncertain:
        return "clarify"
    return prediction.mode


class LearnedSemanticRouter:
    def __init__(self, backend, *, classifier, small_model, large_model,
                 fixed_model_size=None):
        if fixed_model_size is not None and (type(fixed_model_size) is not str
                                             or fixed_model_size not in {"small", "large"}):
            raise ValueError("invalid fixed generator size")
        if any(not isinstance(model, str) or not model.strip() or model != model.strip()
               for model in (small_model, large_model)) or small_model == large_model:
            raise ValueError("router models must be distinct exact names")
        if not callable(getattr(classifier, "classify", None)):
            raise ValueError("a dependency classifier is required")
        self._backend, self._classifier = backend, classifier
        self._small_model, self._large_model = small_model, large_model
        self._fixed_model_size = fixed_model_size

    def _general_fragment(self, text):
        """Test at most three syntactic suffixes, with no intent phrase list.

        Both parts must independently pass the learned classifier's calibrated
        threshold. The suffix must stand alone without any previous history.
        """
        boundaries = sorted(set(match.end() for match in re.finditer(
            r"[.!?;]\s+|,?\s+and\s+", text, re.I)), reverse=True)[:3]
        checks = []
        for start in boundaries:
            part = text[start:].strip()
            remainder = re.sub(r"[,;]?\s*and\s*$", "", text[:start], flags=re.I).strip(" ,;")
            if not part or not remainder or len(part) > 500:
                continue
            predicted = self._classifier.classify(part, history=())
            fragment_mode = _prediction_mode(predicted)
            checks.append({"part": "general", "start": start, "prediction": asdict(predicted)})
            if fragment_mode != "none":
                continue
            recalled = self._classifier.classify(remainder, history=())
            recall_mode = _prediction_mode(recalled)
            checks.append({"part": "recall", "end": start, "prediction": asdict(recalled)})
            if recall_mode == "required":
                return part, checks
        return "", checks

    def route(self, user_text, *, history=()):
        text = _user_text(user_text)
        safe_history = _bounded_history(history)
        with trace_span("dependency_classifier", policy="dependency_v1"):
            prediction = self._classifier.classify(text, history=safe_history)
            mode = _prediction_mode(prediction)
            fragment, checks = self._general_fragment(text) if mode == "required" else ("", [])
        # The local classifier predicts dependency only. This carrier's form
        # is a punctuation hint, not a claimed grammatical model prediction.
        form = "question" if text.endswith("?") else "request"
        label = {"none": "", "optional": "personal context",
                 "required": "stored personal fact", "clarify": "request context"}[mode]
        dependency = MemoryDependency(form, mode, label, fragment, prediction.uncertain)
        size, generation = self._fixed_model_size, None
        source = "fixed" if size else "semantic_model"
        if size is None:
            try:
                with trace_span("compute_classifier", model=self._small_model, policy="dependency_v1"):
                    generation = self._backend.chat(
                        self._small_model,
                        _classification_messages(SEMANTIC_SIZE_SYSTEM_PROMPT,
                                                 _encoded_classifier_input(text, safe_history)),
                        response_format=MODEL_SIZE_SCHEMA,
                        temperature=ROUTER_TEMPERATURE, seed=ROUTER_SEED,
                    )
                if (not isinstance(generation, ChatResult) or generation.model != self._small_model
                        or generation.done_reason != "stop"):
                    raise RoutingError("invalid compute classifier metadata")
                size = parse_model_size_decision(generation.content)
            except (OllamaError, RoutingError):
                size, source = "large", "semantic_size_fallback"
        return SemanticRoutingResult(
            decision=RouteDecision(mode in {"optional", "required"}, size),
            dependency=dependency, policy="dependency_v1",
            memory_required_generation=None, model_size_generation=generation,
            memory_decision_source=("dependency_clarification" if prediction.uncertain
                                    else "dependency_classifier"),
            model_size_decision_source=source,
            fixed_generator_model=(self._small_model if self._fixed_model_size == "small"
                                   else self._large_model if self._fixed_model_size == "large" else None),
            classifier_metadata={"whole_request": asdict(prediction), "fragment_checks": checks,
                                 "form_source": "punctuation_hint"},
        )
