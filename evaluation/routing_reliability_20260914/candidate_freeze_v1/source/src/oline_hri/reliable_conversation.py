"""Answerability, evidence authorization and bounded reply repair.

The semantic prediction never authorizes a fact. Personal turns do not enter
reusable task history, retrieval snapshots are revalidated through delivery,
and reply checks run on every generated answer regardless of the route.
Historical Conversation remains available for reproducing earlier evaluations.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from contextlib import contextmanager
import re
from typing import Sequence

from .answer_guidance import general_response_rule
from .answer_review import AnswerReview, AnswerReviewer
from .conversation import (
    Conversation, ConversationError, ConversationReply, MemoryDiagnostics,
    MAX_RETRIEVED_MEMORIES, _bounded_history, _required_memory_ids,
    _require_current_snapshot, _validated_retrieval, _user_text,
    _verified_composed_answer, _verified_preference_answer,
)
from .memory import is_question_shaped_memory
from .memory_evidence import parse_subject_request
from .ollama import ChatMessage, ChatResult
from .reply_guard import (
    current_assertions, inspect_reply, is_drafting_request, is_drafting_followup,
    safe_history_pair,
)
from .response import RobotResponse, ResponseValidationError
from .routing import RouteDecision, RoutingError, RoutingResult, privacy_abstention
from .semantic_routing import MemoryDependency, SemanticRoutingResult
from .timing import trace_span


_GENERAL_CONTEXT = (
    " Answer the current request directly with concrete useful information. "
    "Personal facts may come only from the current supplied assertions or the "
    "authorized records. Questions and guesses are not assertions. Task history "
    "contains drafts/general discussion, never authority for personal facts. "
    "Do not claim to know an unstated preference, possession, relationship, "
    "diagnosis, past action or schedule. Do not repeat earlier replies. "
    "Treat first-person wording in the human's request as referring to the human. "
    "If asked for advice, provide it now rather than offering to provide it later. "
    "If the human only shares a fact, acknowledge it briefly without claiming it "
    "as your own. Hardware capabilities are unknown unless deployment facts state them."
)
_CLARIFICATION = "Could you clarify what you would like me to help with?"
_MISSING_QUESTIONS = {
    "personal preference": "I don't have that preference available. What preference should I use?",
    "personal schedule": "I don't have that schedule available. Could you tell me the relevant time or date?",
    "personal relationship": "I don't have that relationship detail available. Could you tell me who you mean?",
    "personal constraint": "I don't have that constraint available. Could you provide the detail I should use?",
    "past event": "I don't have that past detail available. Could you tell me what happened?",
    "stored personal fact": "I don't have that personal detail available. Could you tell me the missing information?",
    "personal context": "I don't have that personal context available. Could you provide the relevant details?",
}


def deployment_facts(config) -> tuple[str, ...]:
    return (
        "This application is Oline HRI, an offline conversational robot assistant.",
        f"Its configured language models are {config.ollama.small_model} and {config.ollama.large_model}.",
        "Speech input uses local Whisper and Silero voice activity detection; replies are terminal text.",
    )


@dataclass(frozen=True)
class ReliableConversationReply(ConversationReply):
    # Application clarification has no invented model-generation metadata.
    generation: ChatResult | None
    dependency: MemoryDependency | None = None
    effective_mode: str = "none"
    retrieval_status: str = "skipped"
    attempts: tuple[ChatResult, ...] = ()
    attempted_models: tuple[str, ...] = ()
    answer_reviews: tuple[AnswerReview, ...] = ()
    review_attempts: tuple[ChatResult, ...] = ()
    quality_issues: tuple[str, ...] = ()
    application_memory_ids: tuple[str, ...] = ()


class _ExecutionRouter:
    """Project a validated semantic decision into the existing evidence engine.

    This private projection is an execution instruction, not a replacement for
    the raw prediction. ReliableConversationReply retains the original route,
    effective mode and retrieval status separately.
    """
    def __init__(self, original: SemanticRoutingResult, *, use_memory: bool, size: str, model: str):
        self._route = RoutingResult(
            decision=RouteDecision(use_memory, size),
            # This is an application execution instruction for one fixed
            # generator. Classifier provenance stays on the original outer
            # reply; a local decision must never invent model generations.
            policy="fixed_memory_v1", fixed_generator_model=model,
            memory_required_generation=None, model_size_generation=None,
            memory_decision_source="policy_personal" if use_memory else "policy_general",
            model_size_decision_source="fixed_generator",
        )

    def route(self, user_text, *, history=()):
        return self._route


class _SnapshotRetriever:
    def __init__(self, underlying, matches):
        self._underlying = underlying
        self._matches = matches

    def retrieve(self, query, *, limit):
        return self._matches[:limit]

    def is_current(self, matches):
        return self._underlying.is_current(matches)


class _AttemptBackend:
    """Keep raw returned generations even when downstream validation rejects."""
    def __init__(self, underlying, attempts, attempted_models):
        self._underlying = underlying
        self._attempts = attempts
        self._attempted_models = attempted_models

    def chat(self, *args, **kwargs):
        self._attempted_models.append(args[0] if args else kwargs["model"])
        result = self._underlying.chat(*args, **kwargs)
        if isinstance(result, ChatResult):
            self._attempts.append(result)
        return result


def _known_direct_recall(text: str) -> bool:
    request = parse_subject_request(text)
    return bool(request and request.mode == "direct"
                and any(facet.owner == "user" and facet.attribute is not None
                        for facet in request.facets))


def _checked_route(route: object, text: str) -> SemanticRoutingResult:
    if not isinstance(route, SemanticRoutingResult):
        raise ConversationError("reliable conversation requires a semantic route")
    # Reconstruct to validate even a forged/mutated dataclass supplied by an adapter.
    dependency = route.dependency
    if not isinstance(dependency, MemoryDependency):
        raise ConversationError("invalid semantic dependency")
    MemoryDependency(dependency.form, dependency.mode, dependency.missing_fact,
                     dependency.general_request, dependency.uncertain)
    if dependency.general_request and dependency.general_request not in text:
        raise ConversationError("general subrequest is not part of the current input")
    if route.decision.memory_required != (dependency.mode in {"optional", "required"}):
        raise ConversationError("semantic route has contradictory retrieval intent")
    return route


class ReliableConversation(Conversation):
    """New live runtime; existing store/retrieval contracts remain authoritative."""

    def __init__(self, backend, *, router, retriever, small_model: str,
                 large_model: str, general_large_model: str | None = None,
                 system_prompt: str, context_length: int = 2048,
                 max_output_tokens: int = 192, runtime_facts: Sequence[str] = (),
                 reviewer: AnswerReviewer | None = None):
        super().__init__(
            backend, router=router, retriever=retriever, small_model=small_model,
            large_model=large_model, general_large_model=general_large_model,
            system_prompt=system_prompt, context_length=context_length,
            max_output_tokens=max_output_tokens,
        )
        self._context_length = context_length
        self._max_output_tokens = max_output_tokens
        self._runtime_facts = tuple(runtime_facts)
        self._reviewer = reviewer or AnswerReviewer(backend, model=large_model)
        self._last_turn_withheld = False

    def clear(self):
        super().clear()
        self._last_turn_withheld = False

    @contextmanager
    def disclosure_guard(self, reply: ReliableConversationReply):
        """Revalidate personal evidence while the caller writes final text.

        Callers must enter only for the final short write, after diagnostics;
        no inference or interactive operation may hold this database lock.
        """
        if not isinstance(reply, ReliableConversationReply):
            raise ConversationError("guarded output requires a reliable reply")
        if not reply.response.memory_used:
            yield
            return
        identifiers = set(reply.response.memory_used)
        supplied = tuple(match for match in reply.retrieval
                         if match.memory.id in identifiers)
        if {match.memory.id for match in supplied} != identifiers:
            raise ConversationError("personal reply has no complete evidence snapshot")
        guard = getattr(self._retriever, "disclosure_guard", None)
        if not callable(guard):
            raise ConversationError("retriever does not support guarded output")
        with guard(supplied):
            yield

    def _safe_history(self):
        """Recheck admission even if an external caller seeded old _messages."""
        safe = []
        draft_context = False
        messages = self._messages[1:]
        for offset in range(0, len(messages) - 1, 2):
            user, assistant = messages[offset:offset + 2]
            drafting = (is_drafting_request(user.content)
                        or draft_context and is_drafting_followup(user.content))
            # Canonical history is plain delivered speech; old JSON histories
            # are deliberately not treated as reusable personal evidence.
            if (user.role == "user" and assistant.role == "assistant"
                    and safe_history_pair(user.content, assistant.content, drafting=drafting)):
                safe.extend((user, assistant))
                draft_context = drafting
            else:
                # A detached "summarize that" answer can carry the values of
                # a preceding unsafe pair. Normal live history contains only
                # admitted pairs; quarantine an externally seeded mixed log.
                return ()
        return _bounded_history(safe)

    def _application_reply(self, speech, *, route, mode, retrieval_status,
                           retrieved=(), attempts=(), attempted_models=(), reviews=(),
                           review_attempts=(), issues=()):
        self._last_turn_withheld = True
        return ReliableConversationReply(
            response=RobotResponse(speech=speech, gesture_id="NO_ACTION", memory_used=()),
            generation=None, route=route, dependency=route.dependency,
            effective_mode=mode, retrieval_status=retrieval_status,
            memory_diagnostics=MemoryDiagnostics(retrieved_ids=tuple(
                match.memory.id for match in retrieved)),
            attempts=tuple(attempts), attempted_models=tuple(attempted_models),
            answer_reviews=tuple(reviews), review_attempts=tuple(review_attempts),
            quality_issues=tuple(issues), generation_policy="application_clarification",
        )

    def _send(self, user_text: str) -> ReliableConversationReply:
        text = _user_text(user_text)
        history = self._safe_history()
        # A bare follow-up after withheld personal content cannot silently
        # inherit an older, unrelated general topic.
        if self._last_turn_withheld:
            history = ()
        with trace_span("routing") as span:
            route = _checked_route(self._router.route(text, history=history), text)
            span["policy"] = route.policy
        dependency = route.dependency
        mode = dependency.mode
        private_reply = privacy_abstention(text)
        if private_reply is not None:
            return self._application_reply(private_reply, route=route, mode="clarify",
                                           retrieval_status="skipped")
        if dependency.uncertain or mode == "clarify":
            return self._application_reply(_CLARIFICATION, route=route, mode="clarify",
                                           retrieval_status="skipped")
        # This complete fact grammar is an independent evidence safeguard,
        # not a pronoun-based classifier. A forced wrong route cannot bypass it.
        if mode in {"none", "optional"} and _known_direct_recall(text):
            mode = "required"

        retrieved = ()
        linked = ()
        retrieval_status = "skipped"
        recall_request = (text.replace(dependency.general_request, "", 1).strip()
                          if dependency.general_request else text)
        if dependency.general_request:
            recall_request = re.sub(r"[,;]?\s*and\s*$", "", recall_request,
                                    flags=re.I).strip(" ,;")
        if mode in {"optional", "required"}:
            try:
                with trace_span("retrieval", dependency=mode):
                    retrieved = _validated_retrieval(self._retriever.retrieve(
                        text, limit=MAX_RETRIEVED_MEMORIES))
                    candidates = tuple(match for match in retrieved
                                       if not is_question_shaped_memory(match.memory.canonical_text))
                    ids = set(_required_memory_ids(candidates, recall_request))
                    linked = tuple(match for match in candidates if match.memory.id in ids)
                    if linked:
                        _require_current_snapshot(self._retriever, linked)
                retrieval_status = "matched" if linked else "empty_or_irrelevant"
            except Exception as exc:
                # No personal evidence is disclosed after any retrieval failure.
                # Optional personalization remains answerable in general terms.
                linked = ()
                retrieval_status = "unavailable"

        request = text
        prefix = ""
        verified_prefix = ""
        mixed_constraint = None
        if mode == "required" and dependency.general_request and linked:
            # A mixed request must not confuse the bounded personal-fact
            # grammar. Compose its recall part from verified records, then
            # generate the independent general part with no personal values.
            identifiers = tuple(match.memory.id for match in linked)
            composed = _verified_composed_answer(linked, recall_request, identifiers)
            literal = (composed.speech if composed else
                       _verified_preference_answer(linked, recall_request, identifiers))
            if literal:
                verified_prefix = literal + " "
                mixed_constraint = composed.constraint if composed else "verified_preference"
                request = dependency.general_request
            else:
                # Related evidence without a verified answer is not enough to
                # assert the personal part; preserve independent general help.
                prefix = "I couldn't verify that personal detail. Could you provide it? "
                request = dependency.general_request
                linked = ()
                retrieval_status = "unverified_mixed_evidence"
        if mode == "required" and not linked and not prefix:
            question = _MISSING_QUESTIONS.get(
                dependency.missing_fact, _MISSING_QUESTIONS["stored personal fact"])
            fragment = dependency.general_request
            if not fragment or _known_direct_recall(fragment):
                return self._application_reply(
                    question, route=route, mode="required", retrieval_status=retrieval_status,
                    retrieved=retrieved,
                )
            # Copy-only extraction; never send an unanswered personal question
            # to an unconstrained general generator as if it were a known fact.
            request = fragment
            prefix = question + " "

        use_memory = bool(linked)
        effective_mode = mode if use_memory or mode == "required" else "none"
        model = (self._small_model if route.decision.model_size == "small"
                 else self._large_model if use_memory else self._general_large_model)
        attempts = []
        attempted_models = []
        reviews = []
        review_attempts = []
        issues = []
        prior_replies = tuple(message.content for message in history
                              if message.role == "assistant")
        draft_context = False
        for message in history:
            if message.role == "user":
                draft_context = (is_drafting_request(message.content)
                                 or draft_context and is_drafting_followup(message.content))
        drafting = (is_drafting_request(request)
                    or draft_context and is_drafting_followup(request))
        # Authorized assertions are request-local; previous user statements
        # are never recycled here, including after a falsely general route.
        facts = (*current_assertions(request), *(match.memory.canonical_text for match in linked))
        system = self._base_system_prompt + _GENERAL_CONTEXT
        if self._runtime_facts:
            system += " Verified deployment facts: " + " ".join(self._runtime_facts)
        accepted = None
        evidence_reset = False
        for attempt_number in range(2):
            if attempt_number and not evidence_reset:
                if model == self._large_model:
                    break
                model = self._large_model
            evidence_reset = False
            try:
                if linked:
                    _require_current_snapshot(self._retriever, linked)
                request_system = system
                if mode == "optional" and not linked:
                    request_system += (
                        " Personalization is optional and no permitted personal records are available."
                        " Complete the general request now with a concrete answer or example;"
                        " do not ask for optional preferences or promise to give ideas later."
                    )
                engine = self._engine(
                    route, request, model=model, linked=() if verified_prefix else linked, history=history,
                    system=request_system, retry=bool(attempt_number),
                    backend=_AttemptBackend(self._backend, attempts, attempted_models),
                )
                candidate = engine.send(request)
                if verified_prefix:
                    ids = tuple(match.memory.id for match in linked)
                    candidate = replace(
                        candidate,
                        response=RobotResponse(
                            speech=verified_prefix + candidate.response.speech,
                            gesture_id="NO_ACTION", memory_used=ids, allowed_memory_ids=ids),
                        retrieval=linked,
                        memory_diagnostics=MemoryDiagnostics(
                            retrieved_ids=ids, supplied_ids=(), model_used_ids=()),
                        answer_constraint=mixed_constraint,
                        response_transform="verified_mixed_prefix",
                    )
                checked_request = text if verified_prefix else request
                candidate_issues = inspect_reply(
                    checked_request, candidate.response.speech, authorized_facts=facts,
                    prior_replies=prior_replies, drafting=drafting,
                )
                if candidate_issues:
                    issues.extend(candidate_issues)
                    continue
                try:
                    review = self._reviewer.review(
                        checked_request, candidate.response.speech, authorized_facts=facts,
                        history=history if not linked else (), drafting=drafting,
                        deployment_facts=self._runtime_facts,
                    )
                finally:
                    raw_review = getattr(self._reviewer, "last_generation", None)
                    if isinstance(raw_review, ChatResult):
                        review_attempts.append(raw_review)
                reviews.append(review)
                if not review_attempts or review_attempts[-1] is not review.generation:
                    review_attempts.append(review.generation)
                if review.verdict != "pass":
                    issues.append(review.reason)
                    if review.verdict == "clarify":
                        break
                    continue
                if linked:
                    # Review can take time; freshness is checked again at the
                    # final disclosure boundary, not only before inference.
                    _require_current_snapshot(self._retriever, linked)
                accepted = candidate
                break
            except (ConversationError, ResponseValidationError, RoutingError) as exc:
                issues.append(type(exc).__name__)
                if mode == "optional" and linked:
                    linked = ()
                    facts = current_assertions(request)
                    effective_mode = "none"
                    retrieval_status = "optional_evidence_discarded"
                    evidence_reset = True
            except Exception as exc:
                # Bounded operational failure gives clarification, never an
                # unchecked candidate. KeyboardInterrupt is not swallowed.
                issues.append(type(exc).__name__)

        if accepted is None:
            speech = (_MISSING_QUESTIONS.get(dependency.missing_fact,
                                            _MISSING_QUESTIONS["stored personal fact"])
                      if "unsupported_personal_claim" in issues else
                      "I couldn't give a reliable answer to that. Could you add a little detail or rephrase it?")
            return self._application_reply(
                speech, route=route, mode="clarify", retrieval_status=retrieval_status,
                retrieved=retrieved, attempts=attempts, attempted_models=attempted_models,
                reviews=reviews, review_attempts=review_attempts, issues=issues,
            )
        response = accepted.response
        if prefix:
            response = RobotResponse(speech=prefix + response.speech,
                                     gesture_id="NO_ACTION", memory_used=response.memory_used)
        safe = not linked and not prefix and safe_history_pair(text, response.speech, drafting=drafting)
        self._last_turn_withheld = not safe
        self._messages = [ChatMessage("system", self._base_system_prompt), *history]
        if safe:
            self._messages = [self._messages[0], *_bounded_history((
                *history, ChatMessage("user", text), ChatMessage("assistant", response.speech),
            ))]
        return ReliableConversationReply(
            response=response, generation=accepted.generation, route=route,
            retrieval=accepted.retrieval, dependency=dependency,
            effective_mode=effective_mode, retrieval_status=retrieval_status,
            memory_diagnostics=MemoryDiagnostics(
                retrieved_ids=tuple(match.memory.id for match in retrieved),
                supplied_ids=accepted.memory_diagnostics.supplied_ids,
                model_used_ids=accepted.memory_diagnostics.model_used_ids,
            ),
            fallback_from_model=(attempted_models[0] if len(attempted_models) > 1
                                 and attempted_models[-1] != attempted_models[0] else None),
            attempts=tuple(attempts), attempted_models=tuple(attempted_models),
            answer_reviews=tuple(reviews), review_attempts=tuple(review_attempts),
            quality_issues=tuple(issues),
            application_memory_ids=(response.memory_used if verified_prefix else ()),
            generation_policy=("reliable_quality_retry" if len(attempted_models) > 1
                               else "reliable_generation"),
            answer_constraint=accepted.answer_constraint,
            response_transform=accepted.response_transform, reference_ids=accepted.reference_ids,
        )

    def _engine(self, route, request, *, model, linked, history, system, retry, backend):
        if retry:
            system += " Complete the request now. Avoid repetition, unsupported personal claims, and promises to answer later."
        if linked:
            # The evidence engine already supplies the full citation and
            # grounding policy. Keep additional guidance short enough for
            # the configured 2048-token context and its conservative budget.
            memory_system = self._base_system_prompt + " Answer directly and avoid repetition."
            return Conversation(
                backend, router=_ExecutionRouter(
                    route, use_memory=True,
                    size="small" if model == self._small_model else "large", model=model),
                retriever=_SnapshotRetriever(self._retriever, linked),
                small_model=self._small_model, large_model=self._large_model,
                general_large_model=self._general_large_model, system_prompt=memory_system,
                context_length=self._context_length, max_output_tokens=self._max_output_tokens,
                fixed_generator_model=model,
            )
        engine = Conversation(
            backend, model=model, system_prompt=system + general_response_rule(request),
            context_length=self._context_length, max_output_tokens=self._max_output_tokens,
        )
        engine._messages = [ChatMessage("system", engine._base_system_prompt), *history]
        return engine
