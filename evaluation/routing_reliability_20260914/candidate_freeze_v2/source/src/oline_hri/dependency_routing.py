"""Local learned dependency decisions with independent generator selection.

The classifier predicts a request dependency, never a personal fact. Margins
are finite calibration diagnostics. Uncertain predictions receive one larger
review before clarification or recall; generator sizing is separate.
"""

from dataclasses import asdict, is_dataclass
import math

from .ollama import ChatResult, OllamaError
from .dependency_review import (
    REVIEW_VARIANT, dependency_review_messages, dependency_review_schema,
    fragment_candidates, parse_dependency_review,
)
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
        """Propose literal mixed parts using independent raw local predictions.

        Called after an accepted or reviewed required decision. The local
        uncertainty remains visible in the audit;
        no part authorizes facts, and downstream evidence checks still apply.
        """
        checks = []
        for candidate in fragment_candidates(text):
            start, part, remainder = candidate["start"], candidate["general_part"], candidate["personal_part"]
            predicted = self._classifier.classify(part, history=())
            _prediction_mode(predicted)
            checks.append({"part": "general", "start": start, "prediction": asdict(predicted)})
            if predicted.predicted_mode != "none":
                continue
            recalled = self._classifier.classify(remainder, history=())
            _prediction_mode(recalled)
            checks.append({"part": "recall", "end": start, "prediction": asdict(recalled)})
            if recalled.predicted_mode == "required":
                return part, checks, candidate["index"]
        return "", checks, 0

    def route(self, user_text, *, history=()):
        text = _user_text(user_text)
        safe_history = _bounded_history(history)
        with trace_span("dependency_classifier", policy="dependency_v1"):
            prediction = self._classifier.classify(text, history=safe_history)
            mode = _prediction_mode(prediction)
            fragment, checks = "", []
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
        # Sizing runs first so a subsequent review may leave the large model
        # resident. Its answer cannot change the independently selected size.
        reason = "memory_uncertain" if prediction.uncertain else None
        review_generation, review_error, selected_index = None, None, 0
        needs_personal_facts = None
        uncertain = prediction.uncertain
        memory_source = "dependency_classifier"
        if reason:
            try:
                with trace_span("memory_review", model=self._large_model,
                                policy="dependency_v1", reason=reason):
                    review_generation = self._backend.chat(
                        self._large_model,
                        dependency_review_messages(text, safe_history),
                        response_format=dependency_review_schema(),
                        temperature=ROUTER_TEMPERATURE, seed=ROUTER_SEED,
                    )
                if (not isinstance(review_generation, ChatResult)
                        or review_generation.model != self._large_model
                        or review_generation.done_reason != "stop"):
                    raise RoutingError("invalid dependency review metadata")
                needs_personal_facts = parse_dependency_review(review_generation.content)
                mode = ("required" if needs_personal_facts else prediction.predicted_mode
                        if prediction.predicted_mode in {"optional", "clarify"} else "none")
                uncertain = bool(mode == "clarify" and prediction.uncertain)
                memory_source = "dependency_review"
            except (OllamaError, RoutingError) as exc:
                review_error = {"type": type(exc).__name__, "message": str(exc)}
                mode, fragment, uncertain = "clarify", "", True
                memory_source = "dependency_clarification"
        if mode == "required":
            fragment, checks, selected_index = self._general_fragment(text)
        # Form remains an explicit punctuation hint, not a grammatical claim.
        form = "question" if text.endswith("?") else "request"
        label = {"none": "", "optional": "personal context",
                 "required": "stored personal fact", "clarify": "request context"}[mode]
        dependency = MemoryDependency(form, mode, label, fragment, uncertain)
        return SemanticRoutingResult(
            decision=RouteDecision(mode in {"optional", "required"}, size),
            dependency=dependency, policy="dependency_v1",
            memory_required_generation=None, model_size_generation=generation,
            memory_decision_source=memory_source,
            model_size_decision_source=source,
            fixed_generator_model=(self._small_model if self._fixed_model_size == "small"
                                   else self._large_model if self._fixed_model_size == "large" else None),
            classifier_metadata={"whole_request": asdict(prediction), "fragment_checks": checks,
                                 "form_source": "punctuation_hint",
                                 "review": {"version": "indispensable_personal_facts_v1", "variant": REVIEW_VARIANT,
                                            "needs_personal_facts": needs_personal_facts,
                                            "selected_index": selected_index, "error": review_error},
                                 "fragment_decision_source": ("review_and_raw_parts" if review_generation else
                                                              "accepted_dependency_and_raw_parts") if fragment else None},
            review_generation=review_generation, review_reason=reason,
        )
