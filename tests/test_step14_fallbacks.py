"""Deterministic safety contract for Step 14 generation fallbacks."""

from __future__ import annotations

import json
from types import SimpleNamespace
import unittest

from oline_hri.conversation import Conversation, ConversationError
from oline_hri.memory import MemoryItem, MemoryStoreError
from oline_hri.ollama import (
    ChatResult,
    OllamaError,
    OllamaTimeoutError,
)
from oline_hri.response import ResponseValidationError
from oline_hri.retrieval import HybridMatch
from oline_hri.routing import (
    ConversationRouter,
    RouteDecision,
    RoutingResult,
)


SMALL_MODEL = "qwen3:0.6b"
LARGE_MODEL = "qwen3:4b"


def chat_result(
    speech: str = "Okay.",
    *,
    model: str = SMALL_MODEL,
    memory_used: tuple[str, ...] = (),
    done_reason: str = "stop",
    raw: str | None = None,
) -> ChatResult:
    content = raw
    if content is None:
        content = json.dumps(
            {
                "speech": speech,
                "gesture_id": "NO_ACTION",
                "memory_used": list(memory_used),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return ChatResult(
        model=model,
        content=content,
        done_reason=done_reason,
        total_duration_ns=1,
        load_duration_ns=0,
        prompt_eval_count=1,
        eval_count=1,
        eval_duration_ns=1,
    )


def routing_result(
    *, memory_required: bool = False, model_size: str = "small"
) -> RoutingResult:
    memory_required_generation = ChatResult(
        model=SMALL_MODEL,
        content=json.dumps(
            {"memory_required": memory_required}, separators=(",", ":")
        ),
        done_reason="stop",
        total_duration_ns=1,
        load_duration_ns=0,
        prompt_eval_count=1,
        eval_count=1,
        eval_duration_ns=1,
    )
    model_size_generation = ChatResult(
        model=SMALL_MODEL,
        content=json.dumps({"model_size": model_size}, separators=(",", ":")),
        done_reason="stop",
        total_duration_ns=1,
        load_duration_ns=0,
        prompt_eval_count=1,
        eval_count=1,
        eval_duration_ns=1,
    )
    return RoutingResult(
        decision=RouteDecision(memory_required, model_size),
        memory_required_generation=memory_required_generation,
        model_size_generation=model_size_generation,
    )


def memory_match() -> HybridMatch:
    timestamp = "2026-09-06T00:00:00.000000Z"
    item = MemoryItem(
        id="mem_00000000000000000000000000000001",
        profile_id="step14_test",
        kind="preference",
        canonical_text="User prefers jasmine tea without sugar.",
        source_turn_id=None,
        event_time=None,
        sensitivity="normal",
        consent_status="confirmed",
        confidence=1.0,
        importance=3,
        status="active",
        supersedes_id=None,
        valid_from=timestamp,
        valid_until=None,
        retention_until=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    return HybridMatch(
        memory=item,
        fused_score=1.0 / 61.0,
        keyword_rank=-1.0,
        keyword_position=1,
        semantic_score=0.9,
        semantic_position=1,
    )


class ScriptedBackend:
    def __init__(self, outcomes: tuple[object, ...]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[
            tuple[str, tuple[object, ...], object, object, object]
        ] = []

    def chat(
        self,
        model,
        messages,
        *,
        response_format=None,
        temperature=None,
        seed=None,
    ):
        self.calls.append(
            (
                model,
                tuple(messages),
                response_format,
                temperature,
                seed,
            )
        )
        if not self.outcomes:
            raise AssertionError("unexpected backend call")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class ScriptedRouter:
    def __init__(self, outcomes: tuple[object, ...]) -> None:
        self.outcomes = list(outcomes)
        self.calls = []

    def route(self, user_text, *, history=()):
        self.calls.append((user_text, tuple(history)))
        if not self.outcomes:
            raise AssertionError("unexpected router call")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class ScriptedRetriever:
    def __init__(
        self,
        result: object = (),
        *,
        snapshot_outcomes: tuple[object, ...] = (),
    ) -> None:
        self.result = result
        self.snapshot_outcomes = list(snapshot_outcomes)
        self.retrieve_calls = []
        self.current_calls = []

    def retrieve(self, query, *, limit=3):
        self.retrieve_calls.append((query, limit))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result

    def is_current(self, matches):
        self.current_calls.append(tuple(matches))
        if not self.snapshot_outcomes:
            raise AssertionError("unexpected snapshot check")
        outcome = self.snapshot_outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def routed_conversation(backend, router, retriever) -> Conversation:
    return Conversation(
        backend,
        system_prompt="Be helpful, safe, and concise.",
        router=router,
        retriever=retriever,
        small_model=SMALL_MODEL,
        large_model=LARGE_MODEL,
    )


class Step14FallbackTests(unittest.TestCase):
    def test_large_timeout_falls_back_once_with_identical_request_contract(
        self,
    ) -> None:
        private_detail = "private backend timeout detail"
        route = routing_result(model_size="large")
        backend = ScriptedBackend(
            (
                OllamaTimeoutError(private_detail),
                chat_result("Best-effort answer.", model=SMALL_MODEL),
            )
        )
        router = ScriptedRouter((route,))
        retriever = ScriptedRetriever()
        conversation = routed_conversation(backend, router, retriever)

        reply = conversation.send("Compare the options carefully.")

        self.assertEqual(
            [call[0] for call in backend.calls],
            [LARGE_MODEL, SMALL_MODEL],
        )
        self.assertEqual(backend.calls[0][1], backend.calls[1][1])
        self.assertEqual(backend.calls[0][2], backend.calls[1][2])
        self.assertIs(reply.route, route)
        self.assertEqual(reply.generation.model, SMALL_MODEL)
        self.assertEqual(reply.fallback_from_model, LARGE_MODEL)
        self.assertEqual(reply.response.speech, "Best-effort answer.")
        self.assertEqual(retriever.retrieve_calls, [])
        self.assertEqual(retriever.current_calls, [])
        self.assertEqual(
            [message.role for message in conversation.messages],
            ["system", "user", "assistant"],
        )
        self.assertEqual(
            [
                message.content
                for message in conversation.messages
                if message.role == "user"
            ],
            ["Compare the options carefully."],
        )
        self.assertNotIn(
            private_detail,
            "\n".join(message.content for message in conversation.messages),
        )

    def test_large_rag_timeout_rechecks_same_snapshot_around_fallback(
        self,
    ) -> None:
        match = memory_match()
        route = routing_result(memory_required=True, model_size="large")
        backend = ScriptedBackend(
            (
                OllamaTimeoutError("large request timed out"),
                chat_result(
                    "You prefer jasmine tea without sugar.",
                    model=SMALL_MODEL,
                    memory_used=(match.memory.id,),
                ),
            )
        )
        router = ScriptedRouter((route,))
        retriever = ScriptedRetriever(
            (match,), snapshot_outcomes=(True, True, True)
        )
        conversation = routed_conversation(backend, router, retriever)

        reply = conversation.send("How do I take my tea?")

        self.assertEqual(
            [call[0] for call in backend.calls],
            [LARGE_MODEL, SMALL_MODEL],
        )
        self.assertEqual(backend.calls[0][1], backend.calls[1][1])
        self.assertEqual(backend.calls[0][2], backend.calls[1][2])
        self.assertEqual(
            retriever.retrieve_calls,
            [("How do I take my tea?", 3)],
        )
        self.assertEqual(retriever.current_calls, [(match,), (match,), (match,)])
        self.assertEqual(reply.retrieval, (match,))
        self.assertEqual(reply.response.memory_used, (match.memory.id,))
        self.assertEqual(reply.fallback_from_model, LARGE_MODEL)
        self.assertEqual(
            reply.memory_diagnostics.to_dict(),
            {
                "retrieved_ids": [match.memory.id],
                "supplied_ids": [match.memory.id],
                "model_used_ids": [match.memory.id],
            },
        )
        memory_schema = backend.calls[0][2]["properties"]["memory_used"]
        self.assertEqual(memory_schema["items"]["enum"], [match.memory.id])
        self.assertEqual(memory_schema["minItems"], 1)

    def test_timeout_fallback_is_not_used_for_a_selected_small_model(self) -> None:
        backend = ScriptedBackend(
            (
                OllamaTimeoutError("private small timeout"),
                chat_result("must not run", model=SMALL_MODEL),
            )
        )
        conversation = routed_conversation(
            backend,
            ScriptedRouter((routing_result(model_size="small"),)),
            ScriptedRetriever(),
        )

        with self.assertRaises(ConversationError) as caught:
            conversation.send("Simple request.")

        self.assertNotIn("private small timeout", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assertEqual([call[0] for call in backend.calls], [SMALL_MODEL])
        self.assertEqual(len(conversation.messages), 1)

    def test_ordinary_large_backend_error_does_not_fallback(self) -> None:
        private_detail = "private ordinary backend failure"
        backend = ScriptedBackend(
            (
                OllamaError(private_detail),
                chat_result("must not run", model=SMALL_MODEL),
            )
        )
        conversation = routed_conversation(
            backend,
            ScriptedRouter((routing_result(model_size="large"),)),
            ScriptedRetriever(),
        )

        with self.assertRaises(ConversationError) as caught:
            conversation.send("Complex request.")

        self.assertNotIn(private_detail, str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assertEqual([call[0] for call in backend.calls], [LARGE_MODEL])
        self.assertEqual(len(conversation.messages), 1)

    def test_invalid_large_responses_never_trigger_fallback(self) -> None:
        invalid_cases = (
            (
                "malformed metadata",
                SimpleNamespace(model=LARGE_MODEL),
                ConversationError,
            ),
            (
                "malformed JSON",
                chat_result(model=LARGE_MODEL, raw="not-json"),
                ResponseValidationError,
            ),
            (
                "truncated",
                chat_result(model=LARGE_MODEL, done_reason="length"),
                ResponseValidationError,
            ),
            (
                "wrong model",
                chat_result(model=SMALL_MODEL),
                ConversationError,
            ),
            (
                "unsafe action",
                chat_result(
                    model=LARGE_MODEL,
                    raw=(
                        '{"speech":"Unsafe","gesture_id":"WAVE",'
                        '"memory_used":[]}'
                    ),
                ),
                ResponseValidationError,
            ),
        )
        for label, invalid_result, expected_error in invalid_cases:
            with self.subTest(label=label):
                backend = ScriptedBackend(
                    (
                        invalid_result,
                        chat_result("must not run", model=SMALL_MODEL),
                    )
                )
                conversation = routed_conversation(
                    backend,
                    ScriptedRouter((routing_result(model_size="large"),)),
                    ScriptedRetriever(),
                )

                with self.assertRaises(expected_error):
                    conversation.send("Complex request.")

                self.assertEqual([call[0] for call in backend.calls], [LARGE_MODEL])
                self.assertEqual(len(conversation.messages), 1)

    def test_router_timeout_is_not_a_generation_fallback(self) -> None:
        backend = ScriptedBackend(
            (
                OllamaTimeoutError("private router timeout"),
                chat_result("must not run", model=SMALL_MODEL),
            )
        )
        router = ConversationRouter(backend, model=SMALL_MODEL)
        conversation = routed_conversation(
            backend, router, ScriptedRetriever()
        )

        with self.assertRaisesRegex(
            ConversationError, "route classification failed"
        ) as caught:
            conversation.send("Classify this request.")

        self.assertNotIn("private router timeout", str(caught.exception))
        self.assertEqual([call[0] for call in backend.calls], [SMALL_MODEL])
        self.assertEqual(len(conversation.messages), 1)

    def test_retrieval_and_initial_staleness_stop_before_generation(self) -> None:
        match = memory_match()
        cases = (
            (
                "retrieval error",
                ScriptedRetriever(MemoryStoreError("private index error")),
            ),
            (
                "stale before generation",
                ScriptedRetriever((match,), snapshot_outcomes=(False,)),
            ),
        )
        for label, retriever in cases:
            with self.subTest(label=label):
                backend = ScriptedBackend(
                    (chat_result("must not run", model=SMALL_MODEL),)
                )
                conversation = routed_conversation(
                    backend,
                    ScriptedRouter(
                        (routing_result(memory_required=True, model_size="large"),)
                    ),
                    retriever,
                )

                with self.assertRaises(ConversationError) as caught:
                    conversation.send("Use my preference in a complex answer.")

                self.assertNotIn("private index error", str(caught.exception))
                self.assertEqual(backend.calls, [])
                self.assertEqual(len(conversation.messages), 1)

    def test_stale_snapshot_prevents_or_rolls_back_rag_fallback(self) -> None:
        match = memory_match()
        cases = (
            ("stale before fallback", (True, False), 1),
            ("stale after fallback", (True, True, False), 2),
        )
        for label, snapshots, expected_backend_calls in cases:
            with self.subTest(label=label):
                backend = ScriptedBackend(
                    (
                        OllamaTimeoutError("large timeout"),
                        chat_result(
                            "Personalized fallback.",
                            model=SMALL_MODEL,
                            memory_used=(match.memory.id,),
                        ),
                    )
                )
                retriever = ScriptedRetriever(
                    (match,), snapshot_outcomes=snapshots
                )
                conversation = routed_conversation(
                    backend,
                    ScriptedRouter(
                        (routing_result(memory_required=True, model_size="large"),)
                    ),
                    retriever,
                )

                with self.assertRaisesRegex(ConversationError, "no longer current"):
                    conversation.send("Use my preference in a complex answer.")

                self.assertEqual(len(backend.calls), expected_backend_calls)
                self.assertEqual(
                    len(retriever.current_calls), len(snapshots)
                )
                self.assertEqual(len(conversation.messages), 1)

    def test_fallback_failure_is_sanitized_and_preserves_prior_history(self) -> None:
        private_detail = "private small fallback failure"
        backend = ScriptedBackend(
            (
                chat_result("First answer.", model=SMALL_MODEL),
                OllamaTimeoutError("large timeout"),
                OllamaError(private_detail),
            )
        )
        router = ScriptedRouter(
            (
                routing_result(model_size="small"),
                routing_result(model_size="large"),
            )
        )
        conversation = routed_conversation(
            backend, router, ScriptedRetriever()
        )
        conversation.send("First turn.")
        history_before = conversation.messages

        with self.assertRaises(ConversationError) as caught:
            conversation.send("Complex second turn.")

        self.assertNotIn(private_detail, str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assertEqual(
            [call[0] for call in backend.calls],
            [SMALL_MODEL, LARGE_MODEL, SMALL_MODEL],
        )
        self.assertEqual(conversation.messages, history_before)

    def test_invalid_fallback_output_is_never_committed(self) -> None:
        backend = ScriptedBackend(
            (
                OllamaTimeoutError("large timeout"),
                chat_result(
                    model=SMALL_MODEL,
                    raw=(
                        '{"speech":"Unsafe","gesture_id":"WAVE",'
                        '"memory_used":[]}'
                    ),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            ScriptedRouter((routing_result(model_size="large"),)),
            ScriptedRetriever(),
        )

        with self.assertRaises(ResponseValidationError):
            conversation.send("Complex request.")

        self.assertEqual(
            [call[0] for call in backend.calls],
            [LARGE_MODEL, SMALL_MODEL],
        )
        self.assertEqual(len(conversation.messages), 1)


if __name__ == "__main__":
    unittest.main()
