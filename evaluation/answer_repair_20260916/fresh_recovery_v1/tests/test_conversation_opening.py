"""Natural clarification and safe task continuation without model inference."""

import unittest

from test_conversation_routed import FakeBackend, FakeRouter, SMALL_MODEL, chat_result
from test_reliable_conversation import reliable, semantic_route


class ConversationOpeningTests(unittest.TestCase):
    def test_each_missing_personal_dependency_asks_one_question_without_generation(self):
        cases = (
            ("personal preference", "Which pattern do I prefer?"),
            ("personal schedule", "When is my next lesson?"),
            ("personal relationship", "Who is my hiking partner?"),
            ("personal constraint", "What restrictions apply to my trip?"),
            ("past event", "What happened at my last rehearsal?"),
            ("stored personal fact", "Where did I leave my notebook?"),
            ("personal context", "What is my current project?"),
        )
        for missing, request in cases:
            with self.subTest(missing=missing):
                route = semantic_route("required", missing=missing)
                backend = FakeBackend()
                session, _, retriever, reviewer = reliable(backend, route=route)

                reply = session.send(request)

                disclaimer = "I don't have that earlier information available. "
                self.assertTrue(reply.response.speech.startswith(disclaimer))
                question = reply.response.speech[len(disclaimer):]
                self.assertRegex(question, r"^(?:What|Who|Which|When|Where|How|Could|Can)\b")
                self.assertTrue(reply.response.speech.endswith("?"))
                self.assertEqual(reply.response.speech.count("?"), 1)
                self.assertNotRegex(question.lower(), r"\b(?:remember|recalled|verified|mem_[0-9a-f]+)\b")
                self.assertEqual(reply.effective_mode, "required")
                self.assertEqual(reply.retrieval_status, "empty_or_irrelevant")
                self.assertIs(reply.route, route)
                self.assertEqual(len(retriever.retrieve_calls), 1)
                self.assertIsNone(reply.generation)
                self.assertEqual(reply.generation_policy, "application_clarification")
                self.assertEqual(reply.attempts, ())
                self.assertEqual(reply.attempted_models, ())
                self.assertEqual(reply.answer_reviews, ())
                self.assertEqual(reply.review_attempts, ())
                self.assertEqual(reply.response.memory_used, ())
                self.assertEqual(backend.calls, [])
                self.assertEqual(reviewer.calls, [])
                self.assertEqual(session.messages[1:], ())

    def test_i_and_me_with_current_inputs_do_not_override_a_general_route(self):
        cases = (
            ("Can you explain recursion to me?", "Recursion is a function calling itself."),
            ("How can I learn a programming language?", "Start with variables and loops, then write a small game."),
            ("I have paper and ten minutes. Suggest something I can make.", "Fold a paper bookmark."),
            ("Can you help me choose a game for four players?", "Try a cooperative word game with alternating clues."),
        )
        for request, answer in cases:
            with self.subTest(request=request):
                route = semantic_route("none")
                backend = FakeBackend((chat_result(answer),))
                session, _, retriever, reviewer = reliable(backend, route=route)

                reply = session.send(request)

                self.assertEqual(reply.response.speech, answer)
                self.assertIs(reply.route, route)
                self.assertEqual(reply.effective_mode, "none")
                self.assertEqual(reply.retrieval_status, "skipped")
                self.assertEqual(retriever.retrieve_calls, [])
                self.assertEqual(len(backend.calls), 1)
                self.assertEqual(reply.attempted_models, (SMALL_MODEL,))
                self.assertEqual(len(reviewer.calls), 1)
                self.assertEqual(reply.response.memory_used, ())

    def test_general_clarification_becomes_context_for_the_supplied_detail(self):
        request = "Explain that process."
        detail = "The evaporation process."
        answer = "Evaporation is the escape of molecules from a liquid surface into a gas."
        router = FakeRouter((semantic_route("clarify"), semantic_route("none")))
        backend = FakeBackend((chat_result(answer),))
        session, _, retriever, reviewer = reliable(backend, router=router)

        opening = session.send(request)

        self.assertEqual(opening.response.speech.count("?"), 1)
        self.assertIn("what result", opening.response.speech)
        self.assertNotIn("evaporation", opening.response.speech.lower())
        self.assertIsNone(opening.generation)
        self.assertEqual(backend.calls, [])
        self.assertEqual(reviewer.calls, [])
        expected_context = [request, opening.response.speech]
        self.assertEqual([message.content for message in session.messages[1:]], expected_context)

        reply = session.send(detail)

        self.assertEqual(reply.response.speech, answer)
        self.assertEqual([message.content for message in router.calls[1][1]], expected_context)
        self.assertEqual([message.content for message in backend.calls[0][1][1:-1]], expected_context)
        self.assertEqual([message.content for message in reviewer.calls[0]["history"]], expected_context)
        self.assertEqual(backend.calls[0][1][-1].content, detail)
        self.assertEqual(retriever.retrieve_calls, [])

    def test_personal_and_private_clarifications_are_withheld_from_the_next_task(self):
        cases = (
            ("Where did I put it?", semantic_route("clarify")),
            ("I enjoy collecting maps. What should I do about that?", semantic_route("clarify")),
            ("What is my account password?", semantic_route("none")),
        )
        followup = "Explain evaporation."
        answer = "Evaporation changes liquid water into water vapor."
        for request, first_route in cases:
            with self.subTest(request=request):
                router = FakeRouter((first_route, semantic_route("none")))
                backend = FakeBackend((chat_result(answer),))
                session, _, retriever, reviewer = reliable(backend, router=router)

                opening = session.send(request)

                self.assertIsNone(opening.generation)
                self.assertEqual(session.messages[1:], ())
                self.assertEqual(backend.calls, [])

                reply = session.send(followup)

                self.assertEqual(reply.response.speech, answer)
                self.assertEqual(router.calls[1][1], ())
                self.assertEqual(backend.calls[0][1][1:-1], ())
                self.assertEqual(reviewer.calls[0]["history"], ())
                self.assertNotIn(request, repr(backend.calls))
                self.assertEqual(retriever.retrieve_calls, [])

    def test_required_missing_question_does_not_become_general_task_history(self):
        request = "When is my next lesson?"
        router = FakeRouter((semantic_route("required", missing="personal schedule"),
                             semantic_route("none")))
        backend = FakeBackend((chat_result("Evaporation changes liquid water into water vapor."),))
        session, _, _, reviewer = reliable(backend, router=router)

        opening = session.send(request)
        session.send("Explain evaporation.")

        self.assertIsNone(opening.generation)
        self.assertEqual(router.calls[1][1], ())
        self.assertEqual(backend.calls[0][1][1:-1], ())
        self.assertEqual(reviewer.calls[0]["history"], ())

    def test_clear_discards_an_admitted_task_clarification(self):
        request = "Explain that process."
        router = FakeRouter((semantic_route("clarify"), semantic_route("none")))
        backend = FakeBackend((chat_result("A lever turns around a fulcrum to move a load."),))
        session, _, _, reviewer = reliable(backend, router=router)
        session.send(request)
        self.assertEqual(len(session.messages), 3)

        session.clear()
        self.assertEqual(session.messages[1:], ())
        reply = session.send("Explain a lever.")

        self.assertIsNotNone(reply.generation)
        self.assertEqual(router.calls[1][1], ())
        self.assertEqual(backend.calls[0][1][1:-1], ())
        self.assertEqual(reviewer.calls[0]["history"], ())
        self.assertNotIn(request, repr(backend.calls))


if __name__ == "__main__":
    unittest.main()
