"""Offline lifecycle routing regressions; no generated-answer accuracy claims."""

import json
import unittest

from oline_hri.evaluation_systems import MemoryOnlyRouter
from oline_hri.lightweight_routing import LightweightRouter
from oline_hri.ollama import ChatMessage
from oline_hri.routing import (
    ConversationRouter, MEMORY_REQUIRED_HISTORY_SYSTEM_PROMPT,
    MEMORY_REQUIRED_SCHEMA, MODEL_SIZE_SCHEMA, memory_intent_policy,
)
from test_memory_intent_regressions import Backend, CLOSED_INTERVALS, SMALL, LARGE


RECALL_REQUESTS = (
    "What is my preferred breakfast?",
    "Who is my swimming partner?",
    "Where is my camera?",
    "What time is my dental appointment on 2027-03-12?",
    "Where was my winter concert on 2027-02-10?",
    "Earlier I told you about my breakfast preference. Which breakfast do I prefer now?",
    "Returning to my earlier swimming partner information, who is my current swimming partner?",
    "Earlier I told you where my camera is. Where is my camera located now?",
    "Returning to my earlier camera information, where should I find my camera now?",
    "Earlier I told you about my dental appointment on 2027-03-12. What start time is currently recorded?",
    "Returning to my earlier dental appointment, what is its recorded start time on 2027-03-12 now?",
    "Earlier I told you about my winter concert on 2027-02-10. Which venue is in the current record?",
    "Returning to my earlier winter concert, what venue is now recorded for that event on 2027-02-10?",
    "What breakfast preference did I tell you earlier, before I asked you to forget it?",
    "Which swimming partner did I name earlier, before I asked you to forget that information?",
)
HISTORY = (
    ChatMessage("user", "I prefer oatmeal for breakfast."),
    ChatMessage("assistant", "Your preferred breakfast is oatmeal."),
)


class LifecycleRoutingRevalidationTests(unittest.TestCase):
    def test_current_and_historical_recall_require_authorized_state_with_any_history(self):
        for text in RECALL_REQUESTS:
            for history in ((), HISTORY):
                with self.subTest(text=text, retained=bool(history)):
                    self.assertEqual(memory_intent_policy(text, history),
                                     (True, "policy_personal"))

    def test_legacy_preserves_raw_false_decision_and_independent_compute(self):
        for size in ("small", "large"):
            backend = Backend(memory=False, size=size)
            route = ConversationRouter(backend, model=SMALL).route(
                RECALL_REQUESTS[5], history=HISTORY,
            )
            self.assertTrue(route.decision.memory_required)
            self.assertEqual(route.memory_decision_source, "policy_personal")
            self.assertEqual(route.decision.model_size, size)
            self.assertEqual(route.model_size_decision_source, "model")
            self.assertEqual([call[2] for call in backend.calls],
                             [MEMORY_REQUIRED_SCHEMA, MODEL_SIZE_SCHEMA])
            self.assertIs(route.memory_required_generation, backend.results[0])
            self.assertIs(route.model_size_generation, backend.results[1])
            self.assertFalse(json.loads(route.memory_required_generation.content)["memory_required"])

    def test_lightweight_routes_personal_history_without_classifier_work(self):
        for text in RECALL_REQUESTS:
            backend = Backend(memory=False)
            route = LightweightRouter(backend, small_model=SMALL, large_model=LARGE).route(
                text, history=HISTORY,
            )
            with self.subTest(text=text):
                self.assertTrue(route.decision.memory_required)
                self.assertEqual(route.memory_decision_source, "policy_personal")
                self.assertIsNone(route.memory_required_generation)
                self.assertEqual(backend.calls, [])

    def test_fixed_generator_uses_same_revalidation_policy_without_compute_change(self):
        backend = Backend(memory=False)
        route = MemoryOnlyRouter(backend, model=LARGE, fixed_model_size="large").route(
            RECALL_REQUESTS[6], history=HISTORY,
        )
        self.assertTrue(route.decision.memory_required)
        self.assertEqual(route.decision.model_size, "large")
        self.assertEqual(len(backend.calls), 1)
        self.assertIs(route.memory_required_generation, backend.results[0])

    def test_personal_pronoun_questions_revalidate_without_authorizing_old_values(self):
        for text, history in (
            ("Where is it now?", (ChatMessage("user", "My camera is in the cupboard."),)),
            ("When is her birthday?", (ChatMessage("user", "Mira is my project partner."),)),
            ("What about that preference?", HISTORY),
            ("Where are they?", (ChatMessage("assistant", "Your boots are in the attic."),)),
        ):
            with self.subTest(text=text):
                backend = Backend(memory=False)
                route = ConversationRouter(backend, model=SMALL).route(text, history=history)
                self.assertTrue(route.decision.memory_required)
                self.assertEqual(route.memory_decision_source, "policy_personal")
                self.assertFalse(json.loads(route.memory_required_generation.content)["memory_required"])

    def test_unrelated_general_topics_do_not_import_older_personal_history(self):
        history = (*HISTORY, ChatMessage("user", "Ada Lovelace wrote notes on the analytical engine."),
                   ChatMessage("assistant", "She collaborated with Charles Babbage."))
        for text in ("When is her birthday?", "Tell me more about it."):
            with self.subTest(text=text):
                self.assertEqual(memory_intent_policy(text, history), (None, "model"))
        for reply in (
            "Her work may help your project.",
            "Do you have any questions about her work?",
            "Your question is about her work.",
        ):
            with self.subTest(reply=reply):
                history = (ChatMessage("user", "Tell me about Ada Lovelace."),
                           ChatMessage("assistant", reply))
                self.assertEqual(memory_intent_policy("When is her birthday?", history),
                                 (None, "model"))

    def test_general_questions_quoted_recall_and_supplied_values_are_not_forced_to_memory(self):
        for text in (
            "What is gravity?",
            "How do I repair my camera?",
            'Quote this question: "Earlier I told you about my camera. Where is it now?"',
            "Explain why an earlier preference might be corrected.",
            "I prefer oatmeal for breakfast.",
            "My camera is in the cupboard. Translate that into French.",
            "I work in a lab. What is gravity?",
        ):
            with self.subTest(text=text):
                self.assertIsNot(memory_intent_policy(text, HISTORY)[0], True)
        for text in CLOSED_INTERVALS:
            with self.subTest(text=text):
                self.assertEqual(memory_intent_policy(text, HISTORY), (False, "policy_general"))

    def test_history_classifier_prompt_requires_revalidation_even_when_answer_is_present(self):
        self.assertIn("even when prior_turns contains a possible answer", MEMORY_REQUIRED_HISTORY_SYSTEM_PROMPT)
        self.assertIn("corrected, forgotten or expired", MEMORY_REQUIRED_HISTORY_SYSTEM_PROMPT)
        self.assertIn("Historical personal recall also requires memory", MEMORY_REQUIRED_HISTORY_SYSTEM_PROMPT)
        self.assertNotIn("Return false when the needed fact", MEMORY_REQUIRED_HISTORY_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
