"""Strict verdict parsing and independent review inputs."""

from dataclasses import replace
import json
import unittest

from oline_hri.answer_review import AnswerReviewer, parse_answer_review
from oline_hri.ollama import ChatMessage
from oline_hri.routing import RoutingError
from test_conversation_routed import FakeBackend, LARGE_MODEL, chat_result


class ReviewBackend(FakeBackend):
    def chat(self, model, messages, *, response_format=None, temperature=None, seed=None):
        self.review_options = (temperature, seed)
        return super().chat(model, messages, response_format=response_format)


class AnswerReviewTests(unittest.TestCase):
    def test_verdict_reason_pairs(self):
        for verdict, reason in (("pass", "supported_answer"),
                                ("retry", "unsupported_personal_claim"),
                                ("retry", "unhelpful_answer"),
                                ("clarify", "unresolved_request")):
            raw = chat_result(raw=json.dumps(dict(verdict=verdict, reason=reason)), model=LARGE_MODEL)
            reviewed = parse_answer_review(raw, model=LARGE_MODEL)
            self.assertEqual(reviewed.verdict, verdict)
            self.assertIs(reviewed.generation, raw)

    def test_malformed_or_inconsistent_verdicts_cannot_authorize_output(self):
        for raw in ('[]', 'null', '{"verdict":"pass","reason":"unhelpful_answer"}',
                    '{"verdict":"pass","reason":"supported_answer","fact":"invented"}',
                    '{"verdict":"retry","verdict":"pass","reason":"supported_answer"}',
                    '{"verdict":true,"reason":"supported_answer"}', 'x' * 513):
            with self.subTest(raw=raw), self.assertRaises(RoutingError):
                parse_answer_review(chat_result(raw=raw, model=LARGE_MODEL), model=LARGE_MODEL)

    def test_wrong_model_and_truncated_verdict_are_rejected(self):
        raw = chat_result(raw='{"verdict":"pass","reason":"supported_answer"}', model=LARGE_MODEL)
        for invalid in (replace(raw, model="unrequested"), replace(raw, done_reason="length")):
            with self.assertRaises(RoutingError):
                parse_answer_review(invalid, model=LARGE_MODEL)

    def test_review_separates_authorized_facts_from_request_and_context(self):
        raw = chat_result(raw='{"verdict":"pass","reason":"supported_answer"}', model=LARGE_MODEL)
        backend = ReviewBackend((raw,))
        reviewer = AnswerReviewer(backend, model=LARGE_MODEL)
        reviewer.review("What are your specifications?", "This is Oline HRI.",
                        authorized_facts=(), deployment_facts=("This is Oline HRI.",),
                        history=(ChatMessage("user", "Explain processors."),))
        envelope = json.loads(backend.calls[0][1][-1].content)
        self.assertEqual(envelope["authorized_facts"], [])
        self.assertEqual(envelope["deployment_facts"], ["This is Oline HRI."])
        self.assertEqual(envelope["task_context"], [{"role": "user", "content": "Explain processors."}])
        self.assertIs(reviewer.last_generation, raw)

    def test_invalid_raw_review_is_retained_for_diagnostics(self):
        raw = chat_result(raw="malformed", model=LARGE_MODEL)
        reviewer = AnswerReviewer(ReviewBackend((raw,)), model=LARGE_MODEL)
        with self.assertRaises(RoutingError):
            reviewer.review("Explain gravity.", "Gravity attracts masses.")
        self.assertIs(reviewer.last_generation, raw)


if __name__ == "__main__":
    unittest.main()
