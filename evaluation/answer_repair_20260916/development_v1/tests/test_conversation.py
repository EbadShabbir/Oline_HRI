import json
import unittest

from oline_hri.conversation import Conversation, ConversationError
from oline_hri.ollama import ChatResult, OllamaError
from oline_hri.response import ROBOT_RESPONSE_SCHEMA, ResponseValidationError


def result(
    speech: str = "Hello.", *, raw: str = "", done_reason: str = "stop"
) -> ChatResult:
    content = raw or (
        '{"speech":'
        f"{json.dumps(speech, ensure_ascii=False)},"
        '"gesture_id":"NO_ACTION","memory_used":[]}'
    )
    return ChatResult(
        model="qwen3:0.6b",
        content=content,
        done_reason=done_reason,
        total_duration_ns=1,
        load_duration_ns=0,
        prompt_eval_count=1,
        eval_count=1,
        eval_duration_ns=1,
    )


class FakeBackend:
    def __init__(self) -> None:
        self.calls = []

    def chat(self, model, messages, *, response_format=None):
        self.calls.append((model, tuple(messages), response_format))
        return result(f"answer {len(self.calls)}")


class ConversationTests(unittest.TestCase):
    def test_multiple_turns_include_previous_messages(self) -> None:
        backend = FakeBackend()
        conversation = Conversation(
            backend, model="qwen3:0.6b", system_prompt="Be helpful."
        )

        first = conversation.send("Hello")
        second = conversation.send("What did I say?")

        self.assertEqual(first.response.speech, "answer 1")
        self.assertEqual(second.response.speech, "answer 2")
        self.assertEqual(len(backend.calls[0][1]), 2)
        self.assertEqual(len(backend.calls[1][1]), 4)
        self.assertEqual(backend.calls[1][1][1].content, "Hello")
        self.assertEqual(backend.calls[0][2], ROBOT_RESPONSE_SCHEMA)
        self.assertEqual(
            backend.calls[1][1][2].content,
            '{"speech":"answer 1","gesture_id":"NO_ACTION","memory_used":[]}',
        )

    def test_clear_removes_turns_but_preserves_system_prompt(self) -> None:
        backend = FakeBackend()
        conversation = Conversation(
            backend, model="qwen3:0.6b", system_prompt="Be helpful."
        )
        conversation.send("Hello")

        conversation.clear()

        self.assertEqual(len(conversation.messages), 1)
        self.assertEqual(conversation.messages[0].role, "system")

    def test_failed_turn_is_not_added_to_history(self) -> None:
        private_detail = "backend echoed a private prompt"

        class FailingBackend:
            def chat(self, model, messages, *, response_format=None):
                raise OllamaError(private_detail)

        conversation = Conversation(
            FailingBackend(), model="qwen3:0.6b", system_prompt="Be helpful."
        )

        with self.assertRaises(ConversationError) as caught:
            conversation.send("This should fail")

        self.assertEqual(str(caught.exception), "chat generation request failed")
        self.assertNotIn(private_detail, str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assertEqual(len(conversation.messages), 1)
        self.assertEqual(conversation.messages[0].role, "system")

    def test_context_settings_are_strictly_validated(self) -> None:
        cases = (
            {"context_length": True},
            {"context_length": 127},
            {"context_length": 131073},
            {"context_length": 2048.0},
            {"max_output_tokens": True},
            {"max_output_tokens": 0},
            {"max_output_tokens": 2049},
            {"max_output_tokens": 1.5},
            {"context_length": 256, "max_output_tokens": 128},
        )
        for settings in cases:
            with self.subTest(settings=settings):
                with self.assertRaises(ValueError):
                    Conversation(
                        FakeBackend(),
                        model="qwen3:0.6b",
                        system_prompt="Be helpful.",
                        **settings,
                    )

    def test_unicode_heavy_request_is_rejected_before_generation(self) -> None:
        backend = FakeBackend()
        conversation = Conversation(
            backend,
            model="qwen3:0.6b",
            system_prompt="Be helpful.",
        )

        with self.assertRaisesRegex(ConversationError, "context budget"):
            conversation.send("🙂" * 400)

        self.assertEqual(backend.calls, [])
        self.assertEqual(len(conversation.messages), 1)

    def test_aggregate_budget_prunes_unicode_history_as_a_complete_turn(self) -> None:
        class SequencedBackend(FakeBackend):
            def __init__(self) -> None:
                super().__init__()
                self.outcomes = [result("🙂" * 100), result("Done.")]

            def chat(self, model, messages, *, response_format=None):
                self.calls.append((model, tuple(messages), response_format))
                return self.outcomes.pop(0)

        backend = SequencedBackend()
        conversation = Conversation(
            backend,
            model="qwen3:0.6b",
            system_prompt="Be helpful.",
            context_length=1024,
            max_output_tokens=256,
        )
        conversation.send("First turn")

        conversation.send("Second turn")

        self.assertEqual(
            [message.role for message in backend.calls[1][1]],
            ["system", "user"],
        )
        self.assertEqual(backend.calls[1][1][-1].content, "Second turn")

    def test_output_reserve_can_reject_an_otherwise_bounded_request(self) -> None:
        backend = FakeBackend()
        conversation = Conversation(
            backend,
            model="qwen3:0.6b",
            system_prompt="Be helpful.",
            context_length=640,
            max_output_tokens=300,
        )

        with self.assertRaisesRegex(ConversationError, "context budget"):
            conversation.send("Hello")

        self.assertEqual(backend.calls, [])

    def test_invalid_structured_response_is_not_added_to_history(self) -> None:
        class InvalidBackend:
            def chat(self, model, messages, *, response_format=None):
                return result(
                    raw=(
                        '{"speech":"Unsafe","gesture_id":"WAVE",'
                        '"memory_used":[]}'
                    )
                )

        conversation = Conversation(
            InvalidBackend(), model="qwen3:0.6b", system_prompt="Be helpful."
        )

        with self.assertRaisesRegex(ResponseValidationError, "NO_ACTION"):
            conversation.send("Wave")

        self.assertEqual(len(conversation.messages), 1)

    def test_truncated_response_is_rejected_before_history_commit(self) -> None:
        class TruncatedBackend:
            def chat(self, model, messages, *, response_format=None):
                return result("Partial reply", done_reason="length")

        conversation = Conversation(
            TruncatedBackend(), model="qwen3:0.6b", system_prompt="Be helpful."
        )

        with self.assertRaisesRegex(ResponseValidationError, "truncated"):
            conversation.send("Hello")

        self.assertEqual(len(conversation.messages), 1)


if __name__ == "__main__":
    unittest.main()
