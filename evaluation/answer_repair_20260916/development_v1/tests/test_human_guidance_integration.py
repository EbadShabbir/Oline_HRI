"""Practical quality repair must remain bounded and evidence checked."""

import json
import unittest

from oline_hri.conversation import ConversationError
from oline_hri.timing import TraceRecorder
from test_conversation_routed import FakeBackend, GENERAL_LARGE_MODEL, LARGE_MODEL, SMALL_MODEL, chat_result
from test_reliable_conversation import StubReviewer, reliable, semantic_route


REQUEST = "Help me tidy my desk."
TIMED_REQUEST = "I have twenty minutes. Help me tidy my desk."
BAD = "I can help you tidy your desk. Please let me know what you need."
STEPS = [
    "Clear rubbish and group loose papers.",
    "Put supplies away and clear your work area.",
    "Wipe the surface and check it is usable.",
]


def guidance(steps=STEPS, *, model=LARGE_MODEL, **kwargs):
    return chat_result(raw=json.dumps({"steps_for_user": steps}), model=model, **kwargs)


class HumanGuidanceIntegrationTests(unittest.TestCase):
    def test_desk_retry_delivers_reviewed_steps_preserving_actual_model_output(self):
        first, second = chat_result(BAD), guidance()
        backend = FakeBackend((first, second))
        session, _, retriever, reviewer = reliable(backend)
        trace = TraceRecorder()
        with trace.activate():
            reply = session.send(REQUEST)

        self.assertEqual(reply.effective_mode, "none")
        self.assertEqual(reply.response_transform, "human_guidance_steps")
        self.assertEqual(reply.response.memory_used, ())
        self.assertEqual(reply.response.gesture_id, "NO_ACTION")
        self.assertIn(STEPS[0], reply.response.speech)
        self.assertIs(reply.generation, second)
        self.assertEqual(reply.attempts, (first, second))
        self.assertEqual(reply.attempted_models, (SMALL_MODEL, LARGE_MODEL))
        self.assertEqual(reply.fallback_from_model, SMALL_MODEL)
        self.assertEqual(retriever.retrieve_calls, [])
        self.assertEqual(len(reviewer.calls), 1)
        self.assertEqual(reviewer.calls[0]["answer"], reply.response.speech)
        self.assertNotIn(BAD, repr(backend.calls[1]))
        self.assertNotIn(BAD, repr(session.messages))
        self.assertEqual(set(backend.calls[1][2]["properties"]), {"steps_for_user"})
        self.assertIn("previous attempt only offered help", backend.calls[1][1][0].content)
        spans = [event for event in trace.events if event["name"] == "answer_generation"]
        self.assertEqual(len(spans), 2)
        self.assertEqual(spans[-1]["attributes"]["content"], second.content)

    def test_optional_without_evidence_can_use_the_same_reviewed_repair(self):
        backend = FakeBackend((chat_result(BAD), guidance()))
        session, _, retriever, reviewer = reliable(backend, route=semantic_route("optional"))
        reply = session.send(REQUEST)
        self.assertEqual(reply.effective_mode, "none")
        self.assertEqual(reply.response_transform, "human_guidance_steps")
        self.assertEqual(len(retriever.retrieve_calls), 1)
        self.assertEqual(reply.response.memory_used, ())
        self.assertEqual(len(reviewer.calls), 1)

    def test_review_rejection_still_prevents_delivery_and_third_attempt(self):
        backend = FakeBackend((chat_result(BAD), guidance()))
        reviewer = StubReviewer((("retry", "unhelpful_answer"),))
        session, _, _, _ = reliable(backend, reviewer=reviewer)
        reply = session.send(REQUEST)
        self.assertIsNone(reply.generation)
        self.assertEqual(reply.generation_policy, "application_clarification")
        self.assertEqual(len(backend.calls), 2)
        self.assertEqual(len(reply.answer_reviews), 1)
        self.assertNotIn(STEPS[0], reply.response.speech)

    def test_typed_output_cannot_bypass_personal_fact_checks(self):
        invented = "Your sister is Leila. Put her papers in a pile."
        backend = FakeBackend((chat_result(BAD), guidance([invented])))
        session, _, _, reviewer = reliable(backend)
        reply = session.send(REQUEST)
        self.assertIsNone(reply.generation)
        self.assertIn("unsupported_personal_claim", reply.quality_issues)
        self.assertEqual(reviewer.calls, [])
        self.assertNotIn("Leila", reply.response.speech)
        self.assertNotIn("Leila", repr(session.messages))

    def test_application_numbering_does_not_disguise_empty_scaffolding(self):
        second = guidance(["Please provide more details."])
        backend = FakeBackend((chat_result(BAD), second))
        session, _, _, reviewer = reliable(backend)
        reply = session.send(REQUEST)
        self.assertIsNone(reply.generation)
        self.assertEqual(reply.attempts[-1], second)
        self.assertEqual(reviewer.calls, [])
        self.assertEqual(len(backend.calls), 2)
        self.assertNotIn("1.", reply.response.speech)

    def test_timer_framing_cannot_disguise_a_nonanswer_or_escalate_to_a_memory_model(self):
        second = guidance(["Please provide more details."], model=GENERAL_LARGE_MODEL)
        backend = FakeBackend((second,))
        session, _, _, reviewer = reliable(backend)
        reply = session.send(TIMED_REQUEST)
        self.assertIsNone(reply.generation)
        self.assertEqual(reply.attempts, (second,))
        self.assertEqual(reply.attempted_models, (GENERAL_LARGE_MODEL,))
        self.assertEqual(reviewer.calls, [])
        self.assertEqual(len(backend.calls), 1)
        self.assertNotIn("timer", reply.response.speech)

    def test_malformed_actor_and_truncated_guidance_are_never_delivered(self):
        for second in (
            guidance(["I'll gather your papers and put them away."]),
            guidance(done_reason="length"),
            chat_result(raw=guidance().content, model=SMALL_MODEL),
            chat_result("Sort the papers.", model=LARGE_MODEL),
        ):
            with self.subTest(raw=second.content, stop=second.done_reason):
                backend = FakeBackend((chat_result(BAD), second))
                session, _, _, reviewer = reliable(backend)
                reply = session.send(REQUEST)
                self.assertIsNone(reply.generation)
                self.assertEqual(len(backend.calls), 2)
                self.assertEqual(reply.attempts[-1], second)
                self.assertEqual(reviewer.calls, [])

    def test_untimed_good_first_answer_keeps_standard_contract_and_one_attempt(self):
        backend = FakeBackend((chat_result("Sort papers, put supplies away, then wipe the desk."),))
        session, _, _, _ = reliable(backend)
        reply = session.send("Help me tidy my desk.")
        self.assertIsNone(reply.response_transform)
        self.assertEqual(reply.attempted_models, (SMALL_MODEL,))
        self.assertIn("speech", backend.calls[0][2]["properties"])

    def test_timed_plan_uses_general_large_and_retains_the_original_small_route(self):
        first = guidance(model=GENERAL_LARGE_MODEL)
        backend = FakeBackend((first,))
        session, _, retriever, reviewer = reliable(backend)
        reply = session.send(TIMED_REQUEST)
        self.assertEqual(reply.attempted_models, (GENERAL_LARGE_MODEL,))
        self.assertEqual(reply.route.decision.model_size, "small")
        self.assertIsNone(reply.fallback_from_model)
        self.assertEqual(reply.generation_policy, "practical_guidance_large")
        self.assertTrue(reply.response.speech.startswith("Set a 20-minute timer."))
        self.assertTrue(reply.response.speech.endswith("Stop when it rings."))
        self.assertEqual(reply.response_transform, "human_guidance_steps")
        self.assertIs(reply.generation, first)
        self.assertEqual(len(reviewer.calls), 1)
        self.assertEqual(retriever.retrieve_calls, [])
        self.assertEqual(backend.calls[0][2]["properties"]["steps_for_user"]["items"]["type"], "string")

    def test_required_recall_never_enters_practical_generation(self):
        backend = FakeBackend()
        session, _, _, reviewer = reliable(backend, route=semantic_route("required"))
        reply = session.send("Where did I put my desk key?")
        self.assertIsNone(reply.generation)
        self.assertEqual(backend.calls, [])
        self.assertEqual(reviewer.calls, [])

    def test_guidance_preflight_rejects_over_budget_before_dispatch(self):
        backend = FakeBackend()
        session, _, _, _ = reliable(backend)
        session._context_length = 512
        with self.assertRaises(ConversationError):
            session._guidance_attempt(
                REQUEST * 10, model=LARGE_MODEL, history=(), backend=backend, issues=(),
            )
        self.assertEqual(backend.calls, [])


if __name__ == "__main__":
    unittest.main()
