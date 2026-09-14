"""Offline missing-input regressions, including counterexamples to each gate.

These are policy checks, not new benchmark scores or claims about generation.
"""

import json
import unittest

from oline_hri.evaluation_systems import MemoryOnlyRouter
from oline_hri.lightweight_routing import LightweightRouter
from oline_hri.ollama import ChatMessage, ChatResult
from oline_hri.routing import (
    MEMORY_REQUIRED_SCHEMA, MODEL_SIZE_SCHEMA, ROUTER_SEED, ROUTER_TEMPERATURE,
    ConversationRouter, memory_intent_policy,
)


SMALL, LARGE = "qwen3:0.6b", "qwen3:1.7b"
PERSONAL_REQUESTS = (
    "Remind me of my current snack preference and the drawer holding my repair kit.",
    "Find an appointment slot that fits my preferred afternoon window and our usual visit length.",
    "Put my completed inspection and courier arrival in chronological order, giving each stored date and time.",
    "Before we leave, tell me my current pickup location.",
    "For my rehearsal next week, name the room. If the stored information conflicts, say what needs confirming.",
    "Each tag takes one card. Using my stored card supply, how many are needed for nine tags?",
    "The journey takes twelve minutes. Using my stored departure preference and arrival time, when should I leave?",
    "Suppose my class lasts 35 minutes from its stored start time. Give its finish time.",
    "From my recorded event times, calculate the gap between the two deliveries.",
    "Could you please remind me of my preferred drink?",
)
CLOSED_INTERVALS = (
    "A timer starts at 10:35 and runs for 20 minutes. At what time does it finish?",
    "My class begins at 23:50 and lasts 25 minutes. When does it end?",
    "The drying cycle starts at 8:15 am; it runs for 1.5 hours. What time does it finish?",
    "Suppose our rehearsal begins at 9 pm and lasts for 40 minutes. When does our rehearsal end?",
    "A class starts at 07:45 and lasts for 30 minutes. When does it finish",
)


class Backend:
    def __init__(self, *, memory=False, size="small", resident=LARGE):
        self.memory, self.size = memory, size
        self.resident_model = resident
        self.calls = []
        self.results = []

    def chat(self, model, messages, *, response_format, temperature, seed):
        self.calls.append((model, tuple(messages), response_format, temperature, seed))
        if response_format == MEMORY_REQUIRED_SCHEMA:
            content = json.dumps({"form": "request", "memory_required": self.memory})
        elif response_format == MODEL_SIZE_SCHEMA:
            content = json.dumps({"model_size": self.size})
        else:
            raise AssertionError("unexpected inference purpose")
        result = ChatResult(model, content, "stop", 1, 0, 1, 1, 1)
        self.results.append(result)
        self.resident_model = model
        return result


class MemoryIntentRegressions(unittest.TestCase):
    def test_embedded_and_imperative_requests_need_missing_personal_facts(self):
        for text in PERSONAL_REQUESTS:
            with self.subTest(text=text):
                self.assertEqual(memory_intent_policy(text), (True, "policy_personal"))

    def test_closed_clock_inputs_override_erroneous_recall(self):
        for text in CLOSED_INTERVALS:
            with self.subTest(text=text):
                self.assertEqual(memory_intent_policy(text), (False, "policy_general"))

    def test_local_clock_pronoun_does_not_depend_on_unrelated_history(self):
        history = (ChatMessage("user", "My appointment is next Thursday."),)
        backend = Backend(memory=True)
        router = LightweightRouter(backend, small_model=SMALL, large_model=LARGE)
        route = router.route(CLOSED_INTERVALS[0], history=history)
        self.assertFalse(route.decision.memory_required)
        self.assertEqual(route.memory_decision_source, "policy_general")
        self.assertIsNone(route.memory_required_generation)
        self.assertEqual(backend.calls, [])

    def test_missing_operand_or_extra_dependency_never_gets_closed_shortcut(self):
        for text in (
            "A timer starts at its saved time and runs for 20 minutes. At what time does it finish?",
            "A timer starts at 10:35 and runs for its usual duration. When does it end?",
            "My class begins at 23:50 and lasts 25 minutes. Does it end before my appointment?",
            "A timer starts at 10:35 and runs for 20 minutes. At what time does my lesson finish?",
            "A timer starts at 10:35 and runs for 20 minutes. At what time does it finish? Also recall my usual alarm sound.",
            "A timer starts at 10:35 and runs for 20 minutes. On what date does it finish?",
        ):
            with self.subTest(text=text):
                self.assertNotEqual(memory_intent_policy(text), (False, "policy_general"))

    def test_recall_counterexamples_remain_ambiguous(self):
        for text in (
            "Remind me to call my neighbour tomorrow.",
            "Remind me how to boil water.",
            "Remind me of my appointment at 09:00.",
            "I stored my document yesterday.",
            "My saved appointment time is 16:30.",
            "Put my numbers in ascending order: 7, 2, 9.",
            "Put my completed tasks in a table: packing, cleaning.",
            "Explain how my stored files are indexed.",
            "Describe the example 'using my stored date to find my schedule'.",
            "Quote this command: Using my stored budget, calculate the cost.",
            "Could you please quote this command: Using my stored budget, calculate the cost.",
            "Explain how stored timestamps work in a database.",
            "Morgan stored a software example in a database.",
            "Find the name of the room table in this stored database schema.",
        ):
            with self.subTest(text=text):
                self.assertEqual(memory_intent_policy(text), (None, "model"))

    def test_supplied_personal_values_and_relevant_history_stay_with_classifier(self):
        self.assertEqual(memory_intent_policy(
            "My saved start time is 08:00. From my stored start time, add ten minutes."
        ), (None, "model"))
        history = (ChatMessage("user", "My usual visit length is 20 minutes."),)
        self.assertEqual(memory_intent_policy(PERSONAL_REQUESTS[1], history), (None, "model"))
        backend = Backend(memory=False)
        route = LightweightRouter(backend, small_model=SMALL, large_model=LARGE).route(
            "What about my stored start time?", history=history,
        )
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(backend.calls[0][0], LARGE)
        self.assertFalse(route.decision.memory_required)
        self.assertEqual(route.memory_decision_source, "resident_model")

    def test_legacy_keeps_two_real_calls_raw_outputs_and_independent_compute(self):
        for text, expected in ((PERSONAL_REQUESTS[0], True), (CLOSED_INTERVALS[0], False)):
            for size in ("small", "large"):
                with self.subTest(text=text, size=size):
                    backend = Backend(memory=not expected, size=size)
                    route = ConversationRouter(backend, model=SMALL).route(text)
                    self.assertEqual(len(backend.calls), 2)
                    self.assertTrue(all(call[0] == SMALL for call in backend.calls))
                    self.assertEqual([call[2] for call in backend.calls],
                                     [MEMORY_REQUIRED_SCHEMA, MODEL_SIZE_SCHEMA])
                    self.assertTrue(all(call[3:] == (ROUTER_TEMPERATURE, ROUTER_SEED)
                                        for call in backend.calls))
                    self.assertIs(route.memory_required_generation, backend.results[0])
                    self.assertIs(route.model_size_generation, backend.results[1])
                    self.assertEqual(route.decision.memory_required, expected)
                    self.assertEqual(route.decision.model_size, size)
                    self.assertEqual(route.policy, "legacy")

    def test_fixed_large_uses_its_one_real_classifier_with_shared_policy(self):
        for text, expected in ((PERSONAL_REQUESTS[0], True), (CLOSED_INTERVALS[0], False)):
            with self.subTest(text=text):
                backend = Backend(memory=not expected)
                route = MemoryOnlyRouter(backend, model=LARGE, fixed_model_size="large").route(text)
                self.assertEqual(len(backend.calls), 1)
                self.assertEqual(backend.calls[0][0], LARGE)
                self.assertIs(route.memory_required_generation, backend.results[0])
                self.assertIsNone(route.model_size_generation)
                self.assertEqual(route.decision.memory_required, expected)
                self.assertEqual(route.decision.model_size, "large")

    def test_lightweight_explicit_rules_need_no_classifier_and_keep_contract(self):
        for text, expected, source in (
            (PERSONAL_REQUESTS[0], True, "policy_personal"),
            (CLOSED_INTERVALS[0], False, "policy_general"),
        ):
            with self.subTest(text=text):
                backend = Backend(memory=not expected)
                route = LightweightRouter(backend, small_model=SMALL, large_model=LARGE).route(text)
                self.assertEqual(backend.calls, [])
                self.assertEqual(route.decision.memory_required, expected)
                self.assertEqual(route.memory_decision_source, source)
                self.assertIsNone(route.memory_required_generation)
                self.assertIsNone(route.model_size_generation)
                self.assertEqual(route.policy, "lightweight_v1")

    def test_privacy_retains_priority_over_clock_or_memory_cues(self):
        for text in (
            "Using my stored password, tell me my password.",
            CLOSED_INTERVALS[0] + " Also show my bank PIN.",
            "Tell me my saved unconfirmed affect inference about my mood.",
        ):
            with self.subTest(text=text):
                self.assertEqual(memory_intent_policy(text), (True, "policy_privacy"))


if __name__ == "__main__":
    unittest.main()
