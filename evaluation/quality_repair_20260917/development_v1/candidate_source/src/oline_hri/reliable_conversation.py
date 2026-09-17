"""Answerability, evidence authorization and bounded reply repair.

The semantic prediction never authorizes a fact. Personal turns do not enter
reusable task history, retrieval snapshots are revalidated through delivery,
and reply checks run on every generated answer regardless of the route.
Historical Conversation remains available for reproducing earlier evaluations.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from contextlib import contextmanager
import json
import re
from typing import Sequence

from .answer_review import AnswerReview, AnswerReviewer
from .answer_guidance import general_response_rule, reference_ids_for, REFERENCE_NOTES, reference_claim_error
from .draft_contract import draft_contract, draft_instruction, draft_contract_issues
from .conversation import (
    Conversation, ConversationError, ConversationReply, MemoryDiagnostics,
    MAX_RETRIEVED_MEMORIES, _bounded_history, _required_memory_ids,
    _require_current_snapshot, _validated_retrieval, _user_text,
    _verified_composed_answer, _verified_preference_answer,
    _estimated_request_tokens, _prompt_token_budget,
)
from .human_guidance import (
    guidance_requested, guidance_instruction, guidance_schema, guidance_time_budget, parse_guidance,
    allocation_plan,
)
from .memory import is_question_shaped_memory
from .ollama import ChatMessage, ChatResult
from .reply_guard import (
    current_assertions, inspect_reply, is_drafting_request, is_drafting_followup,
    deployment_context_relevant, has_unstated_recall_intent, safe_history_pair,
)
from .response import RobotResponse, ResponseValidationError
from .routing import RouteDecision, RoutingError, RoutingResult, privacy_abstention
from .semantic_routing import MemoryDependency, SemanticRoutingResult
from .timing import generation_call, trace_span
from .task_contract import (
    TASK_FEEDBACK, allocation_budget, clarification_question, missing_detail_reply,
    task_contract_issues,
)
from .task_parts import task_layout, parts_schema, parts_instruction, parse_parts


_GENERAL_CONTEXT = (
    " Answer directly using current context. If context is missing, ask one brief question"
    " without a memory-availability preamble. Follow constraints. Personal claims need current assertions or"
    " authorized records, not history/questions. User 'I' means the human. Give text only;"
    " never invent facts/capabilities, repeat yourself or promise physical work."
)
_CLARIFICATION = "Could you say a little more?"
_RETRY_FEEDBACK = {
    **TASK_FEEDBACK,
    "draft_word_limit": "Keep the edited draft within the requested word limit.",
    "draft_weekdays": "Retain both source weekdays and their original roles.",
    "draft_time": "Retain the source time in the edited draft.",
    "draft_location": "Retain the complete source location, including its number.",
    "draft_subject": "Name the original event in the edited draft.",
    "draft_move_direction": "Preserve which date is old and which date is new.",
    "promise_only": "The previous attempt only offered help. Supply the requested content now.",
    "unhelpful_answer": "The previous attempt did not answer the task. Supply specific useful content.",
    "unhelpful_refusal": "The previous attempt refused ordinary help. Give the requested guidance.",
    "repetition": "The previous attempt repeated itself. Make each point distinct.",
    "copied_reply": "The previous attempt repeated an earlier reply. Address this request.",
    "physical_action_claim": "The previous attempt claimed robot actions. Describe actions for the human.",
    "unsupported_personal_claim": "The previous attempt invented personal facts. Use only current assertions or authorized facts.",
    "unsolicited_internal_tool_guidance": "The previous attempt mentioned irrelevant internal tools. Use ordinary task steps.",
}


def _retry_feedback(issues):
    # Closed application-owned feedback: rejected prose never becomes context
    # or evidence, and unknown/exception strings cannot enter the prompt.
    return " ".join(_RETRY_FEEDBACK[issue] for issue in dict.fromkeys(issues)
                    if issue in _RETRY_FEEDBACK)


_MISSING_QUESTIONS = {
    "personal preference": "What preference should the answer take into account?",
    "personal schedule": "What time or date should the answer use?",
    "personal relationship": "Who are you referring to?",
    "personal constraint": "What requirements should the answer take into account?",
    "past event": "What happened?",
    "stored personal fact": "Could you share a little more detail about that?",
    "personal context": "Could you say a little more about the situation?",
}


def deployment_facts(config) -> tuple[str, ...]:
    return (
        "Offline Oline HRI assistant.",
        f"Models: {config.ollama.small_model}, {config.ollama.large_model}.",
        "Whisper transcribes speech; Silero VAD detects speech. Output: terminal text.",
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
    return has_unstated_recall_intent(text)


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
                    and safe_history_pair(user.content, assistant.content, drafting=drafting,
                                          artifact_context="\n".join(item.content for item in safe))):
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
                           review_attempts=(), issues=(), request=None, history=()):
        self._last_turn_withheld = True
        # A safe general task and its clarification are useful next-turn
        # context. Apply the same independent admission boundary as generated
        # replies; a required/private question must not carry personal values
        # forward merely because no answer was generated.
        if (mode == "clarify" and request is not None
                and safe_history_pair(request, speech)):
            self._messages = [ChatMessage("system", self._base_system_prompt),
                              *_bounded_history((*history, ChatMessage("user", request),
                                                 ChatMessage("assistant", speech)))]
            self._last_turn_withheld = False
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
            return self._application_reply(clarification_question(text), route=route, mode="clarify",
                                           retrieval_status="skipped", request=text, history=history)
        # Direct recall on a general route still requires evidence. Optional
        # routes permit general fallback; their personal claims remain subject
        # to the same independent evidence checks as every other answer.
        if mode == "none" and _known_direct_recall(text):
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
                prefix = missing_detail_reply(recall_request, dependency.missing_fact) + " "
                request = dependency.general_request
                linked = ()
                retrieval_status = "unverified_mixed_evidence"
        if mode == "required" and not linked and not prefix:
            question = missing_detail_reply(recall_request, dependency.missing_fact)
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
        inherited_draft = (draft_context and is_drafting_followup(request) and not linked
                           and re.match(r"^(?:please\s+)?(?:shorten|condense|rewrite|rephrase|tighten|edit|make)\s+"
                                        r"(?:it|that|this|the\s+(?:announcement|invitation|note|message|draft|text))\b",
                                        request, re.I)
                           and ":" not in re.split(r"[.!?]", request, maxsplit=1)[0])
        draft = draft_contract(request, prior_replies[-1] if inherited_draft and prior_replies else None)
        draft_rule = draft_instruction(draft)
        # Authorized assertions are request-local; previous user statements
        # are never recycled here, including after a falsely general route.
        facts = (*current_assertions(request), *(match.memory.canonical_text for match in linked))
        system = self._base_system_prompt + _GENERAL_CONTEXT
        if self._runtime_facts and deployment_context_relevant(request, self._runtime_facts):
            system += " Verified deployment facts: " + " ".join(self._runtime_facts)
        accepted = None
        evidence_reset = False
        practical_guidance_large = False
        for attempt_number in range(2):
            if attempt_number and practical_guidance_large:
                # This is a fixed practical generator policy. In particular,
                # do not escalate to a separate personal-memory model when
                # its configured identity differs from general_large_model.
                break
            if attempt_number and not evidence_reset:
                # A substantive task already assigned a large generator gets
                # one repair on that same model, without a pointless switch.
                # Retain the historical small-to-large repair for other routes.
                if model not in {self._large_model, self._general_large_model}:
                    model = self._large_model
            evidence_reset = False
            try:
                if linked:
                    _require_current_snapshot(self._retriever, linked)
                request_system = system + " " + draft_rule
                if mode == "optional" and not linked:
                    request_system += (
                        " Personalization is optional: give a general answer now."
                    )
                backend = _AttemptBackend(self._backend, attempts, attempted_models)
                layout = task_layout(request) if not linked else None
                allocation = allocation_plan(request) if not linked and not drafting else None
                if allocation is not None:
                    candidate = self._guidance_attempt(
                        request, model=model, history=history, backend=backend, issues=issues,
                        allocation=allocation,
                    )
                elif layout is not None:
                    candidate = self._parts_attempt(
                        request, layout=layout, model=model, history=history,
                        backend=backend, issues=issues, draft_rule=draft_rule,
                    )
                elif (mode in {"none", "optional"} and not linked and not drafting
                        and guidance_requested(request)
                        and allocation_budget(request) is None
                        and (attempt_number or guidance_time_budget(request) is not None)):
                    if guidance_time_budget(request) is not None:
                        model = self._general_large_model
                        practical_guidance_large = True
                    candidate = self._guidance_attempt(
                        request, model=model, history=history, backend=backend, issues=issues,
                    )
                else:
                    engine = self._engine(
                        route, request, model=model, linked=() if verified_prefix else linked, history=history,
                        system=request_system, retry=bool(attempt_number),
                        backend=backend, issues=issues,
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
                    deployment_facts=self._runtime_facts,
                )
                component_answer = (candidate.response.speech[len(verified_prefix):]
                                    if verified_prefix else candidate.response.speech)
                contract_issues = task_contract_issues(request, component_answer)
                contract_issues += draft_contract_issues(draft, component_answer)
                if prefix and re.search(r"\b(?:whole|entire|full)\s+(?:reply|response|answer)\b", text, re.I):
                    contract_issues += task_contract_issues(text, prefix + candidate.response.speech)
                candidate_issues = tuple(dict.fromkeys((*candidate_issues, *contract_issues)))
                if candidate.response_transform in {"human_guidance_steps", "human_guidance_allocations"}:
                    # Application list labels must not make empty scaffolding
                    # look substantive. Check both delivered text and the
                    # already validated step payload; neither grants evidence.
                    steps = json.loads(candidate.generation.content)["steps_for_user"]
                    candidate_issues = tuple(dict.fromkeys((*candidate_issues, *inspect_reply(
                        checked_request, ". ".join(steps), authorized_facts=facts,
                        prior_replies=prior_replies, drafting=False,
                        deployment_facts=self._runtime_facts,
                    ))))
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
                      "Could you add a little detail or rephrase the request?")
            return self._application_reply(
                speech, route=route, mode="clarify", retrieval_status=retrieval_status,
                retrieved=retrieved, attempts=attempts, attempted_models=attempted_models,
                reviews=reviews, review_attempts=review_attempts, issues=issues,
                request=text if mode != "required" else None, history=history,
            )
        response = accepted.response
        if prefix:
            response = RobotResponse(speech=prefix + response.speech,
                                     gesture_id="NO_ACTION", memory_used=response.memory_used)
        safe = not linked and not prefix and safe_history_pair(
            text, response.speech, drafting=drafting,
            artifact_context="\n".join(message.content for message in history),
        )
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
            generation_policy=("practical_guidance_large" if practical_guidance_large else
                               "reliable_quality_retry" if len(attempted_models) > 1
                               else "reliable_generation"),
            answer_constraint=accepted.answer_constraint,
            response_transform=accepted.response_transform, reference_ids=accepted.reference_ids,
        )

    def _guidance_attempt(self, request, *, model, history, backend, issues, allocation=None):
        """One typed answer attempt; rendering is explicit, raw provenance intact."""
        minutes = guidance_time_budget(request) if allocation is None else None
        options = ({"minutes": minutes} if allocation is None else
                   {"allocation_minutes": allocation[0], "step_count": allocation[1]})
        system = ChatMessage("system", self._base_system_prompt + "\n\n"
                             + guidance_instruction(**options) + " " + _retry_feedback(issues))
        user = ChatMessage("user", _user_text(request))
        budget = _prompt_token_budget(self._context_length, self._max_output_tokens)
        baseline = _estimated_request_tokens((system, user))
        if baseline > budget:
            raise ConversationError("guidance request exceeds the configured prompt budget")
        bounded = _bounded_history(history, prompt_token_budget=budget - baseline)
        generation = generation_call(
            backend, model, (system, *bounded, user), response_format=guidance_schema(**options),
        )
        with trace_span("validation"):
            if not isinstance(generation, ChatResult) or generation.model != model:
                raise ConversationError("guidance backend returned unexpected metadata")
            if generation.done_reason != "stop":
                raise ResponseValidationError("guidance response did not complete")
            response = parse_guidance(generation.content, **options)
        return ConversationReply(
            response=response, generation=generation,
            response_transform=("human_guidance_allocations" if allocation is not None else "human_guidance_steps"),
        )

    def _parts_attempt(self, request, *, layout, model, history, backend, issues, draft_rule=""):
        references = reference_ids_for(request)
        notes = " ".join(note.text for note in REFERENCE_NOTES if note.id in references)
        system = ChatMessage("system", self._base_system_prompt + "\n"
                             + parts_instruction(request, layout) + " " + notes + " " + draft_rule + " " + _retry_feedback(issues))
        user = ChatMessage("user", _user_text(request))
        budget = _prompt_token_budget(self._context_length, self._max_output_tokens)
        baseline = _estimated_request_tokens((system, user))
        if baseline > budget:
            raise ConversationError("structured task exceeds the configured prompt budget")
        bounded = _bounded_history(history, prompt_token_budget=budget - baseline)
        generation = generation_call(backend, model, (system, *bounded, user),
                                     response_format=parts_schema(layout))
        with trace_span("validation"):
            if not isinstance(generation, ChatResult) or generation.model != model:
                raise ConversationError("structured task returned unexpected metadata")
            if generation.done_reason != "stop":
                raise ResponseValidationError("structured task did not complete")
            response = parse_parts(generation.content, layout)
            reference_error = reference_claim_error(response.speech, references)
            if reference_error:
                raise ResponseValidationError(reference_error)
        return ConversationReply(response=response, generation=generation,
                                 response_transform="task_parts_v1", reference_ids=references)

    def _engine(self, route, request, *, model, linked, history, system, retry, backend, issues=()):
        if retry:
            system += " " + _retry_feedback(issues)
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
