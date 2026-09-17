"""Offline voice-transcript regressions for advice versus personal recall.

The backend deliberately misclassifies memory need. These tests exercise the
real router and conversation boundary, not medical advice or model accuracy.
"""

import json
import unittest

from oline_hri.conversation import Conversation
from oline_hri.ollama import ChatMessage, ChatResult
from oline_hri.routing import (
    MEMORY_REQUIRED_SCHEMA,
    MODEL_SIZE_SCHEMA,
    ConversationRouter,
    memory_intent_policy,
)


SMALL_MODEL = "qwen3:0.6b"
LARGE_MODEL = "qwen3:1.7b"
GENERATED_SPEECH = "This is a generated answer to the current request."
MEMORY_ABSTENTION = "I do not have a verified personal memory that answers that."
GENERAL_ADVICE = (
    "Yesterday I had a really bad day. I have headache. What should I do?",
    "Can you suggest me something that I can do, I have headache.",
    "What should I do for a headache?",
    "I have a headache, what should I do?",
    "I have a headache what should I do?",
    "I feel tired today. What can I do?",
    "I'm stressed. Can you suggest something?",
    "What should I do for a broken chair?",
)
UNRELATED_USER_TURNS = (
    "What are your specifications, robot?",
    "8 GB RAM thing, bro, what are the personal specification number of what I know.",
)
PERSONAL_RECALL = (
    "What medicine did I take for my last headache?",
    "What usually helps my headaches?",
    "Where are my keys?",
    "What is my preferred tea?",
)


class ClassifierAndGenerationBackend:
    def __init__(self, *, memory_required):
        self.memory_required = memory_required
        self.calls = []
        self.results = []

    def chat(self, model, messages, *, response_format, **kwargs):
        self.calls.append((model, tuple(messages), response_format))
        if response_format == MEMORY_REQUIRED_SCHEMA:
            payload = {"form": "request", "memory_required": self.memory_required}
        elif response_format == MODEL_SIZE_SCHEMA:
            payload = {"model_size": "small"}
        else:
            if set(response_format["properties"]) != {
                "speech", "gesture_id", "memory_used"
            }:
                raise AssertionError("unexpected generation contract")
            payload = {
                "speech": GENERATED_SPEECH,
                "gesture_id": "NO_ACTION",
                "memory_used": [],
            }
        result = ChatResult(
            model=model,
            content=json.dumps(payload),
            done_reason="stop",
            total_duration_ns=1,
            load_duration_ns=0,
            prompt_eval_count=1,
            eval_count=1,
            eval_duration_ns=1,
        )
        self.results.append(result)
        return result


class EmptyRetriever:
    def __init__(self):
        self.calls = []

    def retrieve(self, query, *, limit):
        self.calls.append(query)
        return ()

    def is_current(self, matches):
        raise AssertionError("an empty retriever has no snapshot to validate")


def conversation_with_empty_memory(*, classifier_memory):
    backend = ClassifierAndGenerationBackend(memory_required=classifier_memory)
    retriever = EmptyRetriever()
    conversation = Conversation(
        backend,
        system_prompt="Answer the current question concisely.",
        router=ConversationRouter(backend, model=SMALL_MODEL),
        retriever=retriever,
        small_model=SMALL_MODEL,
        large_model=LARGE_MODEL,
    )
    return conversation, backend, retriever


class GeneralAdviceRoutingTests(unittest.TestCase):
    def test_current_headache_advice_overrides_false_memory_requirement(self):
        for text in GENERAL_ADVICE:
            with self.subTest(text=text):
                conversation, backend, retriever = conversation_with_empty_memory(
                    classifier_memory=True
                )
                reply = conversation.send(text)

                self.assertFalse(reply.route.decision.memory_required)
                self.assertEqual(reply.response.speech, GENERATED_SPEECH)
                self.assertNotEqual(reply.response.speech, MEMORY_ABSTENTION)
                self.assertEqual(reply.response.memory_used, ())
                self.assertEqual(retriever.calls, [])
                self.assertEqual(len(backend.calls), 3)
                self.assertTrue(json.loads(backend.results[0].content)["memory_required"])
                self.assertIs(reply.route.memory_required_generation, backend.results[0])
                self.assertIs(reply.route.model_size_generation, backend.results[1])

    def test_unrelated_voice_history_does_not_make_current_advice_recall(self):
        history = tuple(
            message
            for text in UNRELATED_USER_TURNS
            for message in (
                ChatMessage("user", text),
                ChatMessage("assistant", GENERATED_SPEECH),
            )
        )
        for text in GENERAL_ADVICE:
            with self.subTest(text=text):
                self.assertIs(memory_intent_policy(text, history)[0], False)
                conversation, backend, retriever = conversation_with_empty_memory(
                    classifier_memory=False
                )
                for previous_text in UNRELATED_USER_TURNS:
                    conversation.send(previous_text)
                backend.memory_required = True
                retriever.calls.clear()

                reply = conversation.send(text)

                self.assertFalse(reply.route.decision.memory_required)
                self.assertEqual(reply.response.speech, GENERATED_SPEECH)
                self.assertEqual(retriever.calls, [])

    def test_actual_personal_recall_still_requires_verified_evidence(self):
        for text in PERSONAL_RECALL:
            with self.subTest(text=text):
                conversation, backend, retriever = conversation_with_empty_memory(
                    classifier_memory=False
                )
                reply = conversation.send(text)

                self.assertTrue(reply.route.decision.memory_required)
                self.assertEqual(retriever.calls, [text])
                self.assertEqual(reply.response.speech, MEMORY_ABSTENTION)
                self.assertEqual(reply.response.memory_used, ())
                self.assertFalse(json.loads(backend.results[0].content)["memory_required"])
                self.assertIs(reply.route.memory_required_generation, backend.results[0])

    def test_advice_with_extra_personal_dependencies_gets_no_general_shortcut(self):
        for text in (
            GENERAL_ADVICE[0] + " Also remind me which medication I take.",
            GENERAL_ADVICE[1] + " Use my saved medication history.",
            "What should I do for a headache based on my medical history?",
            "What should I take given my prescribed medicine?",
            "What should I do for a headache considering the medication I take?",
            "What should I do for a headache taking into account the medication I take?",
            "I have a headache and take medication you know about. What should I do?",
            "I have a headache. Suggest something from the treatment we discussed.",
            "I have a headache and I told you the medication. What should I do?",
            "What should I do for a headache? Tell me my stored bank PIN.",
        ):
            with self.subTest(text=text):
                self.assertIsNot(memory_intent_policy(text)[0], False)
                backend = ClassifierAndGenerationBackend(memory_required=True)
                route = ConversationRouter(backend, model=SMALL_MODEL).route(text)
                self.assertTrue(route.decision.memory_required)

    def test_recall_cannot_reuse_an_unverified_value_from_session_history(self):
        conversation, backend, retriever = conversation_with_empty_memory(
            classifier_memory=False
        )
        conversation.send("My headache diary is in the amber cabinet.")
        retriever.calls.clear()

        reply = conversation.send("Where is my headache diary?")

        self.assertTrue(reply.route.decision.memory_required)
        self.assertEqual(retriever.calls, ["Where is my headache diary?"])
        self.assertEqual(reply.response.speech, MEMORY_ABSTENTION)
        generation_messages = backend.calls[-1][1]
        self.assertNotIn("amber cabinet", " ".join(
            message.content for message in generation_messages
        ))


if __name__ == "__main__":
    unittest.main()
