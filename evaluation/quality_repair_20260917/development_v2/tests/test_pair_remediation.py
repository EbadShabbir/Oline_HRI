"""Regressions for the failures observed in the 2026-09-09 memory run."""

import json
import unittest

from oline_hri.config import load_config
from oline_hri.conversation import Conversation, ConversationError
from oline_hri.evaluation import load_evaluation_suite
from oline_hri.evaluation_scoring import _route, EvaluationScoringError
from oline_hri.ollama import ChatMessage
from oline_hri.response import ResponseValidationError
from oline_hri.routing import ConversationRouter, memory_intent_policy
from test_routing import FakeBackend as RouterBackend, chat_result as router_result
from test_conversation_routed import (
    FakeBackend, FakeRetriever, FakeRouter, SMALL_MODEL, LARGE_MODEL,
    chat_result, hybrid_match, memory, routed_conversation, routing_result,
)
from test_memory_grounding_review_regressions import (
    _recency_comparison_memories, _RECENCY_COMPARISON_PROMPT,
    _RECENCY_COMPARISON_SPEECH,
)
from test_evaluation_scoring import _route as route_record


class PairRemediationTests(unittest.TestCase):
    def test_observed_router_failures_with_raw_generations_preserved(self):
        false_positives = {2, 3, 4, 5, 7}
        false_negatives = {20, 25, 27, 28, 29, 30}
        for number, case in enumerate(load_evaluation_suite().cases, 1):
            expected = case.expected_route
            raw_memory = expected.memory_required
            if number in false_positives | false_negatives:
                raw_memory = not raw_memory
            raw_size = "small" if number in {29, 30} else expected.model_size
            raw = router_result(json.dumps({"form": "question", "memory_required": raw_memory}))
            backend = RouterBackend((raw, router_result(json.dumps({"model_size": raw_size}))))
            with self.subTest(case=case.id):
                result = ConversationRouter(backend, model=SMALL_MODEL).route(case.prompt)
                self.assertEqual(result.decision.memory_required, expected.memory_required)
                self.assertEqual(result.decision.model_size, expected.model_size)
                self.assertIs(result.memory_required_generation, raw)
                self.assertEqual(len(backend.calls), 2)

    def test_policy_near_misses_and_history(self):
        for text, expected in (
            ("What is my project called?", True),
            ("What is a robotics project?", False),
            ("What is Theo's role in my project?", True),
            ("How do I make tea?", False),
            ("How do I fix my phone?", False),
            ("My phone will not start.", None),
            ("I prefer ginger tea.", None),
            ("What is a home address?", False),
            ("What is a bank PIN?", False),
            ("What is an unconfirmed affect inference?", False),
            ("Did you save any unconfirmed affect inference about me?", True),
            ("What did I say I prefer?", True),
        ):
            with self.subTest(text=text):
                self.assertIs(memory_intent_policy(text)[0], expected)
        history = (ChatMessage(role="user", content="I prefer ginger tea."),)
        self.assertEqual(memory_intent_policy("What did I say I prefer?", history), (True, "policy_personal"))

    def test_privacy_gate_blocks_retrieval_even_with_an_incorrect_router(self):
        for required in (False, True):
            retriever = FakeRetriever((hybrid_match(memory(1, "My bank PIN is 1234.")),))
            backend = FakeBackend((chat_result("Your PIN is 1234."),))
            conversation = routed_conversation(backend, FakeRouter((routing_result(required),)), retriever)
            reply = conversation.send("What is my bank PIN?")
            self.assertEqual(retriever.retrieve_calls, [])
            self.assertNotIn("1234", reply.response.speech)
            self.assertEqual(reply.response.memory_used, ())
            self.assertNotIn("1234", str(backend.calls))

    def test_project_name_coverage_accepts_correct_name_and_rejects_wrong_one(self):
        item = _recency_comparison_memories()[1]
        for name in ("Luma", "Nova"):
            backend = FakeBackend((chat_result(f"{name} is your tabletop robot project.", memory_used=(item.id,)),))
            conversation = routed_conversation(backend, FakeRouter((routing_result(True),)), FakeRetriever((hybrid_match(item),)))
            if name == "Luma":
                self.assertIn("Luma", conversation.send("What is my tabletop robot project called?").response.speech)
            else:
                with self.assertRaises(ResponseValidationError):
                    conversation.send("What is my tabletop robot project called?")

    def test_192_output_preserves_three_record_context_budget(self):
        items = _recency_comparison_memories()
        ids = tuple(item.id for item in items)
        for cap in (192, 256, 384):
            backend = FakeBackend((chat_result(_RECENCY_COMPARISON_SPEECH, memory_used=ids, model=LARGE_MODEL),))
            conversation = Conversation(
                backend, system_prompt=load_config().conversation.system_prompt,
                router=FakeRouter((routing_result(True, "large"),)),
                retriever=FakeRetriever(tuple(hybrid_match(item, i) for i, item in enumerate(items, 1))),
                small_model=SMALL_MODEL, large_model=LARGE_MODEL,
                context_length=2048, max_output_tokens=cap,
                grounded_composition=False,  # Isolate the raw context-budget contract.
            )
            if cap in (192, 256):
                self.assertEqual(conversation.send(_RECENCY_COMPARISON_PROMPT).memory_diagnostics.supplied_ids, ids)
            else:
                with self.assertRaisesRegex(ConversationError, "context budget"):
                    conversation.send(_RECENCY_COMPARISON_PROMPT)

    def test_scorer_accepts_explicit_policy_and_rejects_unexplained_override(self):
        case = load_evaluation_suite().cases[1]
        record = route_record("adaptive", case)
        record["memory_required_generation"]["content"] = '{"memory_required":true}'
        with self.assertRaises(EvaluationScoringError):
            _route(record, "adaptive")
        record.update(source="hybrid", decision_sources={"memory_required": "policy_general", "model_size": "model"})
        self.assertFalse(_route(record, "adaptive")["memory_required"])
        record["memory_required"] = True
        with self.assertRaises(EvaluationScoringError):
            _route(record, "adaptive")

    def test_old_partial_timeline_candidates_do_not_force_adjacent_records(self):
        # The live retriever supplied these three records, including irrelevant
        # neighboring facts. Packing must not silently discard a required ID.
        navigation, kickoff, _ = _recency_comparison_memories()
        meeting = memory(3, "Mira prefers project meetings between 09:00 and 11:00.")
        items = (navigation, kickoff, meeting)
        prompt = next(case.prompt for case in load_evaluation_suite().cases
                      if case.id == "memory_large_temporal")
        backend = FakeBackend((chat_result("Not an answer."),))
        conversation = Conversation(
            backend, system_prompt=load_config().conversation.system_prompt,
            router=FakeRouter((routing_result(True, "large"),)),
            retriever=FakeRetriever(tuple(hybrid_match(item, i) for i, item in enumerate(items, 1))),
            small_model=SMALL_MODEL, large_model=LARGE_MODEL,
            context_length=2048, max_output_tokens=192,
        )
        # Generation is intentionally invalid: this test checks evidence
        # packing, not acceptance of unrelated model output.
        with self.assertRaises((ResponseValidationError, ConversationError)):
            conversation.send(prompt)
        self.assertEqual(len(backend.calls), 1)
        allowed = backend.calls[0][2]["properties"]["memory_used"]["items"]["enum"]
        self.assertEqual(tuple(allowed), (items[0].id,))
