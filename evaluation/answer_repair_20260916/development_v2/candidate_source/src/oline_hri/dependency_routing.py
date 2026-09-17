"""Local dependency predictions with bounded review and deterministic sizing.

Uncertain or clarification predictions receive one four-mode completeness
review. Explicit unstated recall cannot be erased by a fallible classifier.
No routing decision authorizes personal facts or changes evidence checks.
"""

from dataclasses import asdict, is_dataclass
import math
import re

from .ollama import ChatResult, OllamaError
from .dependency_review import (
    MODE_REVIEW_VERSION, dependency_mode_review_messages, dependency_mode_review_schema,
    fragment_candidates, parse_dependency_mode_review,
)
from .routing import (
    ROUTER_SEED, ROUTER_TEMPERATURE, RouteDecision,
    RoutingError, _bounded_history, _user_text,
)
from .semantic_routing import MemoryDependency, SemanticRoutingResult
from .reply_guard import (
    current_assertions, has_unstated_recall_intent, is_drafting_followup, is_drafting_request,
)
from .timing import trace_span


_MODES = frozenset({"none", "optional", "required", "clarify"})
SIZE_POLICY_VERSION = "dependency_size_policy_v2"
TASK_GUARD_VERSION = "bounded_task_answerability_v1"
_SHORT_SOCIAL = re.compile(
    r"(?:hi|hello|hey|good\s+(?:morning|afternoon|evening|night)|"
    r"thanks(?:\s+a\s+lot)?|thank\s+you|goodbye|bye|see\s+you\s+later)[.! ]*", re.I,
)
_DEICTIC_EDIT = re.compile(
    r"(?:^|[.!?;]\s+)(?:please\s+)?"
    r"(?:use|choose|select|pick|change|replace|make|shorten|rewrite|rephrase|edit|fix)\s+"
    r"(?:(?:the\s+)?(?:other|first|second|third|fourth|last)\s+"
    r"(?:one|option|version|title|message|draft|choice)|"
    r"(?:it|that|this)(?:\s+one)?|the\s+(?:message|draft))\b", re.I,
)
_RECORD_REFERENCE = re.compile(
    r"\b(?:remember|remembered|recall|remind|forgot|earlier|previous|previously|prior|told|said|usual|normally|"
    r"stored|saved|recorded|preferences?|favorite|favourite|past\s+(?:chats?|trips?|choices?)|"
    r"last\s+time)\b", re.I,
)
_PERSONAL_REFERENCE = re.compile(r"\b(?:i|we|you|my|mine|our|ours|your|yours|me|myself)\b", re.I)
_PRIVATE_ATTRIBUTE = re.compile(
    r"\b(?:medical|diagnosis|schedule|address|birthday|biography|preferences?|"
    r"relationship|childhood|health\s+condition)\b", re.I,
)


def _bounded_task_mode(text, history):
    """Recognize self-contained task forms, never supply personal evidence.

    These are positive input contracts, not a general intent classifier. A
    failed match leaves the learned/review path intact. Current data and draft
    provenance matter; task difficulty and output constraints do not imply a
    missing personal record.
    """
    if _RECORD_REFERENCE.search(text):
        return None
    if is_drafting_followup(text) and history:
        ordinal = re.search(r"\b(first|second|third|fourth|last|\d+(?:st|nd|rd|th))\s+"
                            r"(?:one|draft|option|version)\b", text, re.I)
        previous = next((m.content for m in reversed(history) if m.role == "assistant"), "")
        labels = {int(n) for n in re.findall(r"\b(?:version|option|draft)\s+(\d+)\s*:",
                                           previous, re.I)}
        if ordinal and labels and any(m.role == "user" and is_drafting_request(m.content)
                                      for m in history):
            word = ordinal.group(1).lower()
            index = {"first": 1, "second": 2, "third": 3, "fourth": 4,
                     "last": max(labels)}.get(word)
            if index is None:
                index = int(re.match(r"\d+", word).group())
            if index in labels:
                return "none", "supplied_ordinal_draft"
    if re.fullmatch(
        r"(?:the\s+)?(?:numbers|values)\s+are\s+[-+\d.,\s]+(?:and\s+[-+\d.]+)?[.]?\s*"
        r"(?:please\s+)?(?:work\s+it\s+out|calculate\s+it|compute\s+it|find\s+the\s+result)[.!?]*",
        text, re.I,
    ):
        return "clarify", "unspecified_numeric_operation"
    # Editing explicitly quoted text does not endorse the quoted assertions.
    if (re.match(r"^(?:please\s+)?(?:rewrite|rephrase|translate)\b", text, re.I)
            and re.search(r'"[^"\n]+"|\x27[^\x27\n]+\x27', text)):
        return "none", "supplied_literal_edit"
    # A supplied recipient, date/time and venue can be reused as wording in
    # an invitation. This does not establish any persistent personal record.
    if (is_drafting_request(text) and re.search(r"\b(?:invitation|invite)\b", text, re.I)
            and re.search(r"\b(?:to|for)\s+(?:(?:my|our)\s+\w+\s+)?[A-Z][\w'-]+\b", text)
            and re.search(r"\b(?:\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?|noon|midnight)\b", text, re.I)
            and re.search(r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow)\b|"
                          r"\b\d{1,2}\s+[A-Z][a-z]+\b", text, re.I)
            and re.search(r"\b(?:at|in)\s+(?:(?:my|our|the)\s+\w+|[A-Z][\w'-]+)", text)):
        return "none", "supplied_invitation"
    if (not _PERSONAL_REFERENCE.search(text)
            and not re.search(r"\b[A-Z][\w'-]*['’]s\b", text)
            and not _PRIVATE_ATTRIBUTE.search(text)):
        if is_drafting_request(text) and not _DEICTIC_EDIT.search(text):
            return "none", "nonpersonal_artifact"
        if (re.match(r"^(?:please\s+)?(?:convert|format|sort|order|arrange|alphabetize|put)\b", text, re.I)
                and re.search(r":\s*\S", text)):
            return "none", "supplied_data_transform"
        if (re.match(r"^(?:please\s+)?(?:explain|describe|define|compare|contrast)\s+\S", text, re.I)
                and not re.search(r"\b(?:it|that|this|these|those|other)\b", text, re.I)):
            return "none", "nonpersonal_explanation"
    if (current_assertions(text)
            and re.search(r"\b\d+(?:\s+|[-])(?:minutes?|hours?)\b", text, re.I)
            and re.search(r"\b(?:plan|steps|phases|timeline)\b", text, re.I)
            and re.search(r"\b(?:i\s+have|my\s+[^.!?]{1,150}\s+are|the\s+room\s+has)\b", text, re.I)
            and re.search(r"\b(?:using|use|include)\b[^.!?]{0,150}"
                          r"\b(?:listed|supplied|these|those|all)\b", text, re.I)):
        return "none", "current_resource_plan"
    return None


def _recognizable_recall(text):
    # An isolated question prefix must not conceal a value asserted elsewhere
    # in the current input. Mixed/unclear cases still receive semantic review.
    if current_assertions(text):
        return False
    return has_unstated_recall_intent(text) or any(
        has_unstated_recall_intent(candidate["personal_part"])
        for candidate in fragment_candidates(text)
    )


def _generator_policy(text, mode, fragment, reviewed):
    """Choose a candidate size without loading a model just to select one."""
    if mode == "clarify":
        return "small", "application_clarification"
    if mode == "required" and not fragment:
        # Retrieval still decides whether a generated answer is needed.
        return "large", "memory_answer_deferred"
    if reviewed:
        return "large", "resident_large"
    if mode == "none" and _SHORT_SOCIAL.fullmatch(text):
        return "small", "short_social"
    return "large", "substantive_general"


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
            recall_intent = _recognizable_recall(remainder)
            checks.append({"part": "recall", "end": start, "prediction": asdict(recalled),
                           "recognizable_recall_intent": recall_intent})
            if recall_intent:
                checks[-1]["accepted_by"] = "recall_guard"
                return part, checks, candidate["index"]
        return "", checks, 0

    def route(self, user_text, *, history=()):
        text = _user_text(user_text)
        safe_history = _bounded_history(history)
        with trace_span("dependency_classifier", policy="dependency_v1"):
            prediction = self._classifier.classify(text, history=safe_history)
            mode = _prediction_mode(prediction)
            fragment, checks = "", []
        recall_intent = _recognizable_recall(text)
        task_guard = None if recall_intent else _bounded_task_mode(text, safe_history)
        reason = (None if recall_intent or task_guard else
                  "memory_clarify" if prediction.predicted_mode == "clarify" else
                  "memory_uncertain" if prediction.uncertain else
                  # A confident local label cannot establish which artifact
                  # an edit refers to. Review supplied context; do not force
                  # clarification merely because the request uses a pronoun.
                  "answerability_unclear" if _DEICTIC_EDIT.search(text) else
                  "unverified_required" if mode == "required" else None)
        review_generation, review_error, selected_index = None, None, 0
        reviewed_mode = None
        uncertain = prediction.uncertain
        memory_source = "dependency_classifier"
        if recall_intent:
            mode, uncertain = "required", False
            if prediction.mode != "required":
                memory_source = "dependency_recall_guard"
        elif task_guard:
            mode, uncertain = task_guard[0], task_guard[0] == "clarify"
            memory_source = "dependency_task_guard"
        if reason:
            try:
                with trace_span("memory_review", model=self._large_model,
                                policy="dependency_v1", reason=reason):
                    review_generation = self._backend.chat(
                        self._large_model,
                        dependency_mode_review_messages(text, safe_history),
                        response_format=dependency_mode_review_schema(),
                        temperature=ROUTER_TEMPERATURE, seed=ROUTER_SEED,
                    )
                if (not isinstance(review_generation, ChatResult)
                        or review_generation.model != self._large_model
                        or review_generation.done_reason != "stop"):
                    raise RoutingError("invalid dependency review metadata")
                reviewed_mode = parse_dependency_mode_review(review_generation.content)
                mode, uncertain = reviewed_mode, reviewed_mode == "clarify"
                memory_source = "dependency_review"
            except (OllamaError, RoutingError) as exc:
                review_error = {"type": type(exc).__name__, "message": str(exc)}
                mode, fragment, uncertain = "clarify", "", True
                memory_source = "dependency_clarification"
        if mode == "required":
            fragment, checks, selected_index = self._general_fragment(text)
        size, size_reason = _generator_policy(text, mode, fragment, review_generation is not None)
        source = SIZE_POLICY_VERSION
        if self._fixed_model_size:
            size, source, size_reason = self._fixed_model_size, "fixed", "fixed"
        fragment_source = None
        if fragment:
            fragment_source = ("recall_guard_and_raw_parts" if checks[-1].get("accepted_by") == "recall_guard"
                               else "review_and_raw_parts" if review_generation else
                               "accepted_dependency_and_raw_parts")
        # Form remains an explicit punctuation hint, not a grammatical claim.
        form = "question" if text.endswith("?") else "request"
        label = {"none": "", "optional": "personal context",
                 "required": "stored personal fact", "clarify": "request context"}[mode]
        dependency = MemoryDependency(form, mode, label, fragment, uncertain)
        return SemanticRoutingResult(
            decision=RouteDecision(mode in {"optional", "required"}, size),
            dependency=dependency, policy="dependency_v1",
            memory_required_generation=None, model_size_generation=None,
            memory_decision_source=memory_source,
            model_size_decision_source=source,
            fixed_generator_model=(self._small_model if self._fixed_model_size == "small"
                                   else self._large_model if self._fixed_model_size == "large" else None),
            classifier_metadata={"whole_request": asdict(prediction), "fragment_checks": checks,
                                 "form_source": "punctuation_hint",
                                 "recognizable_recall_intent": recall_intent,
                                 "task_guard": ({"version": TASK_GUARD_VERSION,
                                                 "mode": task_guard[0], "reason": task_guard[1]}
                                                if task_guard else None),
                                 "compute_policy": {"version": SIZE_POLICY_VERSION,
                                                    "reason": size_reason, "selected_size": size},
                                 "review": {"version": MODE_REVIEW_VERSION,
                                            "mode": reviewed_mode,
                                            "selected_index": selected_index, "error": review_error},
                                 "fragment_decision_source": fragment_source},
            review_generation=review_generation, review_reason=reason,
        )
