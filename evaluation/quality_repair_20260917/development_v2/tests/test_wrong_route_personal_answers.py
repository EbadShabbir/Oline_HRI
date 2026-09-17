"""Wrong-route fixtures must not authorize personal values or hide raw routing."""

import unittest

from test_conversation_routed import FakeBackend, LARGE_MODEL, chat_result
from test_reliable_conversation import reliable, semantic_route


CASES = (
    ("Which fabric did I choose for the cushion covers?", "Linen.", "I chose linen."),
    ("What is the current start time for the weaving session after the correction?",
     "It starts at 6 PM.", "My weaving session starts at 6 PM."),
    ("Who is Neris in relation to me?", "Your cousin.", "Neris is my cousin."),
    ("What was the name of the pottery class I attended?",
     "The class was called Clay Basics.", "My pottery class was called Clay Basics."),
)


class WrongRoutePersonalAnswerTests(unittest.TestCase):
    def test_missing_record_overrides_execution_without_fabricating_route_metadata(self):
        for question, unsupported_answer, _ in CASES:
            with self.subTest(question=question):
                backend = FakeBackend()
                route = semantic_route("none")
                session, _, retriever, reviewer = reliable(backend, route=route)
                reply = session.send(question)
                self.assertIs(reply.route, route)
                self.assertEqual(reply.route.dependency.mode, "none")
                self.assertEqual(reply.effective_mode, "required")
                self.assertTrue(reply.response.speech.startswith("I don't have that earlier information available. "))
                self.assertEqual(reply.response.speech.count("?"), 1)
                self.assertTrue(reply.response.speech.endswith("?"))
                self.assertNotIn(unsupported_answer.rstrip(".").lower(), reply.response.speech.lower())
                self.assertNotRegex(reply.response.speech.lower(), r"\b(?:remember|recalled|verified)\b")
                if "Neris" in question:
                    self.assertIn("how Neris is related to you", reply.response.speech)
                    self.assertNotIn("person's name", reply.response.speech)
                self.assertEqual(reply.response.memory_used, ())
                self.assertEqual(len(retriever.retrieve_calls), 1)
                self.assertEqual(backend.calls, [])
                self.assertEqual(reviewer.calls, [])
                self.assertEqual(reply.attempts, ())
                self.assertEqual(session.messages[1:], ())

    def test_unrelated_current_assertion_cannot_authorize_fabricated_values(self):
        for question, answer, _ in CASES:
            with self.subTest(question=question):
                backend = FakeBackend((chat_result(answer), chat_result(answer, model=LARGE_MODEL)))
                session, _, _, reviewer = reliable(backend, route=semantic_route("none"))
                reply = session.send("I have a notebook. " + question)
                self.assertNotEqual(reply.response.speech, answer)
                self.assertIn("unsupported_personal_claim", reply.quality_issues)
                self.assertEqual(reply.response.memory_used, ())
                self.assertEqual(len(reply.attempts), 2)
                self.assertEqual(reviewer.calls, [])
                self.assertIsNone(reply.generation)

    def test_current_supplied_values_can_answer_without_retrieval(self):
        for question, answer, fact in CASES:
            with self.subTest(question=question):
                backend = FakeBackend((chat_result(answer),))
                session, _, retriever, reviewer = reliable(backend, route=semantic_route("none"))
                reply = session.send(fact + " " + question)
                self.assertEqual(reply.response.speech, answer)
                self.assertEqual(reply.effective_mode, "none")
                self.assertEqual(retriever.retrieve_calls, [])
                self.assertEqual(len(reply.attempts), 1)
                self.assertEqual(len(reviewer.calls), 1)

    def test_same_value_on_an_unrelated_subject_is_withheld_even_when_reviewer_would_pass(self):
        for question, answer in (
            ("My cousin Mira paints. Who is Neris in relation to me?", "Your cousin."),
            ("My curtains are linen. Which fabric did I choose for cushion covers?", "Linen."),
        ):
            with self.subTest(question=question):
                backend = FakeBackend((chat_result(answer), chat_result(answer, model=LARGE_MODEL)))
                session, _, _, reviewer = reliable(backend, route=semantic_route("none"))
                reply = session.send(question)
                self.assertNotEqual(reply.response.speech, answer)
                self.assertIn("unsupported_personal_claim", reply.quality_issues)
                self.assertEqual(len(reply.attempts), 2)
                self.assertEqual(reviewer.calls, [])
                self.assertIsNone(reply.generation)


if __name__ == "__main__":
    unittest.main()
