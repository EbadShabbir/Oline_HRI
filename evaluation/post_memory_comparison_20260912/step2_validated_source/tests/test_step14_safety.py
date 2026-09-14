from io import StringIO
import json
from threading import Event, Lock, Thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from oline_hri.cli import main
from oline_hri.conversation import Conversation, ConversationError
from oline_hri.memory import MemoryItem, MemoryStoreError
from oline_hri.ollama import ChatResult
from oline_hri.retrieval import HybridMatch
from oline_hri.routing import RouteDecision, RoutingError, RoutingResult


SMALL_MODEL = "qwen3:0.6b"
LARGE_MODEL = "qwen3:4b"
SAFE_CHAT_ERROR = "chat error: request could not be completed safely\n"
PRIVATE_DETAIL = "private-stage-detail-that-must-not-be-exposed"
PRIVATE_CAUSE = "private-cause-that-must-not-be-exposed"
_PRIVATE_FAILURE = object()


def chat_result(
    speech: str,
    *,
    memory_used: tuple[str, ...] = (),
    model: str = SMALL_MODEL,
) -> ChatResult:
    return ChatResult(
        model=model,
        content=json.dumps(
            {
                "speech": speech,
                "gesture_id": "NO_ACTION",
                "memory_used": list(memory_used),
            },
            separators=(",", ":"),
        ),
        done_reason="stop",
        total_duration_ns=1,
        load_duration_ns=0,
        prompt_eval_count=1,
        eval_count=1,
        eval_duration_ns=1,
    )


def routing_result(memory_required: bool = False) -> RoutingResult:
    return RoutingResult(
        decision=RouteDecision(memory_required, "small"),
        memory_required_generation=ChatResult(
            model=SMALL_MODEL,
            content=json.dumps(
                {"memory_required": memory_required},
                separators=(",", ":"),
            ),
            done_reason="stop",
            total_duration_ns=1,
            load_duration_ns=0,
            prompt_eval_count=1,
            eval_count=1,
            eval_duration_ns=1,
        ),
        model_size_generation=ChatResult(
            model=SMALL_MODEL,
            content='{"model_size":"small"}',
            done_reason="stop",
            total_duration_ns=1,
            load_duration_ns=0,
            prompt_eval_count=1,
            eval_count=1,
            eval_duration_ns=1,
        ),
    )


def memory() -> MemoryItem:
    timestamp = "2026-09-06T00:00:00.000000Z"
    return MemoryItem(
        id="mem_00000000000000000000000000000001",
        profile_id="alice",
        kind="preference",
        canonical_text="User prefers the stale-private tea.",
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


def hybrid_match(item: MemoryItem) -> HybridMatch:
    return HybridMatch(
        memory=item,
        fused_score=1.0 / 61.0,
        keyword_rank=-1.0,
        keyword_position=1,
        semantic_score=0.9,
        semantic_position=1,
    )


def raise_private(error_type: type[Exception]) -> None:
    try:
        raise RuntimeError(PRIVATE_CAUSE)
    except RuntimeError as cause:
        raise error_type(PRIVATE_DETAIL) from cause


class ScriptedRouter:
    def __init__(self, outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls = []

    def route(self, user_text, *, history=()):
        self.calls.append((user_text, tuple(history)))
        outcome = self.outcomes.pop(0)
        if outcome is _PRIVATE_FAILURE:
            raise_private(RoutingError)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class ScriptedRetriever:
    def __init__(self, retrieval_outcomes=(), snapshot_outcomes=()) -> None:
        self.retrieval_outcomes = list(retrieval_outcomes)
        self.snapshot_outcomes = list(snapshot_outcomes)
        self.retrieve_calls = []
        self.current_calls = []

    def retrieve(self, query, *, limit=3):
        self.retrieve_calls.append((query, limit))
        outcome = self.retrieval_outcomes.pop(0)
        if outcome is _PRIVATE_FAILURE:
            raise_private(MemoryStoreError)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def is_current(self, matches):
        self.current_calls.append(tuple(matches))
        outcome = self.snapshot_outcomes.pop(0)
        if outcome is _PRIVATE_FAILURE:
            raise_private(MemoryStoreError)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class ScriptedBackend:
    def __init__(self, outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls = []

    def chat(self, model, messages, *, response_format=None):
        self.calls.append((model, tuple(messages), response_format))
        outcome = self.outcomes.pop(0)
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


class Step14ConversationSafetyTests(unittest.TestCase):
    def test_memory_backed_turn_cannot_become_stale_reusable_history(self) -> None:
        item = memory()
        match = hybrid_match(item)
        router = ScriptedRouter(
            (routing_result(False), routing_result(True), routing_result(False))
        )
        retriever = ScriptedRetriever(((match,),), (True, True))
        backend = ScriptedBackend(
            (
                chat_result("A safe general answer."),
                chat_result(
                    "You prefer the stale-private tea.",
                    memory_used=(item.id,),
                ),
                chat_result("A later safe answer."),
            )
        )
        conversation = routed_conversation(backend, router, retriever)

        conversation.send("First general question.")
        reusable_before_memory = conversation.messages
        conversation.send("What tea do I prefer?")

        self.assertEqual(conversation.messages, reusable_before_memory)
        self.assertFalse(
            any(
                "stale-private" in message.content or item.id in message.content
                for message in conversation.messages
            )
        )

        # Simulate the previously supplied record being corrected or forgotten.
        # No subsequent request may depend on that old snapshot or its generated
        # paraphrase, even if routing does not request memory on the next turn.
        retriever.snapshot_outcomes.append(False)
        conversation.send("Continue with a general answer.")

        next_route_history = router.calls[-1][1]
        next_generation_messages = backend.calls[-1][1]
        for messages in (next_route_history, next_generation_messages):
            combined = "\n".join(message.content for message in messages)
            self.assertNotIn("stale-private", combined)
            self.assertNotIn(item.id, combined)
            self.assertNotIn("What tea do I prefer?", combined)
        self.assertEqual(len(retriever.current_calls), 2)

    def test_private_component_failures_are_sanitized_without_history_commit(
        self,
    ) -> None:
        item = memory()
        match = hybrid_match(item)
        cases = (
            (
                "router",
                ScriptedRouter((_PRIVATE_FAILURE,)),
                ScriptedRetriever(),
                ScriptedBackend(()),
                0,
                "route classification failed",
            ),
            (
                "retrieval",
                ScriptedRouter((routing_result(True),)),
                ScriptedRetriever((_PRIVATE_FAILURE,)),
                ScriptedBackend(()),
                0,
                "personal-memory retrieval failed",
            ),
            (
                "pre-generation snapshot",
                ScriptedRouter((routing_result(True),)),
                ScriptedRetriever(((match,),), (_PRIVATE_FAILURE,)),
                ScriptedBackend(()),
                0,
                "personal-memory freshness check failed",
            ),
            (
                "post-generation snapshot",
                ScriptedRouter((routing_result(True),)),
                ScriptedRetriever(
                    ((match,),), (True, _PRIVATE_FAILURE)
                ),
                ScriptedBackend(
                    (
                        chat_result(
                            "You prefer the stale-private tea.", memory_used=(item.id,)
                        ),
                    )
                ),
                1,
                "personal-memory freshness check failed",
            ),
        )

        for (
            label,
            router,
            retriever,
            backend,
            expected_backend_calls,
            expected_public_error,
        ) in cases:
            with self.subTest(stage=label):
                conversation = routed_conversation(backend, router, retriever)

                with self.assertRaises(ConversationError) as caught:
                    conversation.send("What tea do I prefer?")

                self.assertEqual(
                    str(caught.exception),
                    expected_public_error,
                )
                self.assertNotIn(PRIVATE_DETAIL, str(caught.exception))
                self.assertNotIn(PRIVATE_CAUSE, str(caught.exception))
                self.assertIsNone(caught.exception.__cause__)
                self.assertTrue(caught.exception.__suppress_context__)
                self.assertEqual(len(backend.calls), expected_backend_calls)
                self.assertEqual(
                    [message.role for message in conversation.messages],
                    ["system"],
                )

    def test_concurrent_failed_turn_releases_lock_without_committing_input(
        self,
    ) -> None:
        class ObservedLock:
            def __init__(self) -> None:
                self._lock = Lock()
                self._count_lock = Lock()
                self._attempts = 0
                self.second_waiting = Event()

            def __enter__(self):
                with self._count_lock:
                    self._attempts += 1
                    if self._attempts == 2:
                        self.second_waiting.set()
                self._lock.acquire()
                return self

            def __exit__(self, exc_type, exc_value, traceback) -> None:
                self._lock.release()

        class BlockingRouter(ScriptedRouter):
            def __init__(self) -> None:
                super().__init__((routing_result(False),))
                self.first_started = Event()
                self.release_first = Event()

            def route(self, user_text, *, history=()):
                self.calls.append((user_text, tuple(history)))
                if len(self.calls) == 1:
                    self.first_started.set()
                    if not self.release_first.wait(timeout=5):
                        raise AssertionError("first turn was not released")
                    raise_private(RoutingError)
                return self.outcomes.pop(0)

        router = BlockingRouter()
        backend = ScriptedBackend((chat_result("Second turn succeeded."),))
        conversation = routed_conversation(
            backend, router, ScriptedRetriever()
        )
        observed_lock = ObservedLock()
        conversation._turn_lock = observed_lock
        replies = []
        errors = []

        def send(text):
            try:
                replies.append(conversation.send(text))
            except BaseException as exc:
                errors.append(exc)

        first = Thread(target=send, args=("failed private turn",), daemon=True)
        second = Thread(target=send, args=("successful turn",), daemon=True)
        first.start()
        self.assertTrue(router.first_started.wait(timeout=5))
        second.start()
        self.assertTrue(observed_lock.second_waiting.wait(timeout=5))

        router.release_first.set()
        first.join(timeout=5)
        second.join(timeout=5)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            str(errors[0]), "route classification failed"
        )
        self.assertIsNone(errors[0].__cause__)
        self.assertEqual(len(replies), 1)
        self.assertEqual(router.calls[1][1], ())
        generated_text = "\n".join(
            message.content for message in backend.calls[0][1]
        )
        self.assertNotIn("failed private turn", generated_text)
        self.assertEqual(
            [message.content for message in conversation.messages[1::2]],
            ["successful turn"],
        )


class Step14CliSafetyTests(unittest.TestCase):
    def test_interactive_failure_is_sanitized_and_next_turn_continues(self) -> None:
        class ScriptedConversation:
            def __init__(self) -> None:
                self.calls = []

            def send(self, text):
                self.calls.append(text)
                if len(self.calls) == 1:
                    raise_private(ConversationError)
                return SimpleNamespace(
                    response=SimpleNamespace(speech="Recovered response.")
                )

            def clear(self):
                raise AssertionError("clear was not requested")

        conversation = ScriptedConversation()
        output = StringIO()
        errors = StringIO()
        with patch(
            "oline_hri.cli.Conversation", return_value=conversation
        ):
            result = main(
                ["chat"],
                stdin=StringIO("failed private turn\nsuccessful turn\n/exit\n"),
                stdout=output,
                stderr=errors,
            )

        self.assertEqual(result, 0)
        self.assertEqual(conversation.calls, ["failed private turn", "successful turn"])
        self.assertEqual(errors.getvalue(), SAFE_CHAT_ERROR)
        self.assertIn("robot> Recovered response.\n", output.getvalue())
        self.assertNotIn(PRIVATE_DETAIL, output.getvalue() + errors.getvalue())
        self.assertNotIn(PRIVATE_CAUSE, output.getvalue() + errors.getvalue())

    def test_one_shot_failure_uses_same_safe_message_and_exit_three(self) -> None:
        class FailingConversation:
            def send(self, text):
                raise_private(ConversationError)

        output = StringIO()
        errors = StringIO()
        with patch(
            "oline_hri.cli.Conversation", return_value=FailingConversation()
        ):
            result = main(
                ["chat", "--prompt", "private one-shot prompt"],
                stdout=output,
                stderr=errors,
            )

        self.assertEqual(result, 3)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(errors.getvalue(), SAFE_CHAT_ERROR)
        self.assertNotIn(PRIVATE_DETAIL, errors.getvalue())
        self.assertNotIn(PRIVATE_CAUSE, errors.getvalue())


if __name__ == "__main__":
    unittest.main()
