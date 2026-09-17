"""Bounded answerability regressions with deliberately wrong model decisions."""

import unittest

from oline_hri.ollama import ChatMessage
from oline_hri.reply_guard import has_unstated_recall_intent

from test_conversation_routed import FakeBackend, FakeRetriever
from test_dependency_routing import Backend, Classifier, prediction, reviewed, router
from test_reliable_conversation import reliable, semantic_route


class RecallAndAmbiguityRepairTests(unittest.TestCase):
    def _route(self, text, *, history=(), predicted="none"):
        backend = Backend(review=reviewed("none"))
        result = router(Classifier(default=prediction(predicted)), backend).route(text, history=history)
        return result, backend

    def test_reference_only_desire_cannot_erase_explicit_recall(self):
        for text in (
            "Which pattern did I tell you I had chosen for my patchwork cushion? "
            "I want the pattern I already selected, not a new suggestion.",
            "Which route did I choose? I only want the route I picked earlier.",
            "What colour did I select? I need the colour I previously selected, not a guess.",
        ):
            for predicted in ("none", "required", "clarify"):
                with self.subTest(text=text, predicted=predicted):
                    result, backend = self._route(text, predicted=predicted)
                    self.assertEqual(result.dependency.mode, "required")
                    self.assertTrue(has_unstated_recall_intent(text))
                    self.assertEqual(backend.calls, [])

    def test_supplied_value_still_answers_personal_question(self):
        for text in (
            "Which pattern did I choose? I chose stripes.",
            "I selected amber. What colour did I select?",
            "Which route did I choose? I want the coastal route I selected.",
            "Which pattern did I choose? I want the pattern I already selected. I selected stars.",
        ):
            with self.subTest(text=text):
                result, _ = self._route(text)
                self.assertEqual(result.dependency.mode, "none")
                self.assertFalse(has_unstated_recall_intent(text))

    def test_no_evidence_recall_never_reaches_answer_generator(self):
        text = "Which route did I choose? I want the route I already selected."
        route_backend = Backend(review=reviewed("none"))
        answer_backend, retriever = FakeBackend(), FakeRetriever()
        session, _, _, reviewer = reliable(
            answer_backend, router=router(Classifier(default=prediction("none")), route_backend),
            retriever=retriever,
        )
        result = session.send(text)
        self.assertIn("don't have", result.response.speech)
        self.assertEqual(result.effective_mode, "required")
        self.assertEqual(result.response.memory_used, ())
        self.assertEqual(answer_backend.calls, [])
        self.assertEqual(reviewer.calls, [])
        self.assertEqual(route_backend.calls, [])
        self.assertEqual(len(retriever.retrieve_calls), 1)

    def test_independent_execution_guard_preserves_wrong_route_metadata(self):
        backend, route = FakeBackend(), semantic_route("none")
        session, _, retriever, reviewer = reliable(backend, route=route)
        result = session.send("Which route did I choose? I want the route I already selected.")
        self.assertIs(result.route, route)
        self.assertEqual(result.route.dependency.mode, "none")
        self.assertEqual(result.effective_mode, "required")
        self.assertIn("don't have", result.response.speech)
        self.assertEqual(result.response.memory_used, ())
        self.assertEqual(len(retriever.retrieve_calls), 1)
        self.assertEqual(backend.calls, [])
        self.assertEqual(reviewer.calls, [])

    def test_multiple_supplied_artifacts_need_target_selection(self):
        examples = (
            "There are two draft labels: 'Keep dry' and 'Handle with care.' Rewrite the label firmly.",
            'There are three titles: "Clear skies", "Quiet paths", and "Open doors". Shorten the title.',
            'Draft 1: "Good morning". Draft 2: "Welcome home". Rewrite the draft warmly.',
        )
        for text in examples:
            for predicted in ("none", "required", "clarify"):
                with self.subTest(text=text, predicted=predicted):
                    result, backend = self._route(text, predicted=predicted)
                    self.assertEqual(result.dependency.mode, "clarify")
                    self.assertEqual(result.classifier_metadata["task_guard"]["reason"],
                                     "ambiguous_artifact_target")
                    self.assertEqual(backend.calls, [])

    def test_explicit_artifact_selections_are_not_withheld(self):
        prefix = "There are two draft labels: 'Keep dry' and 'Handle with care.' "
        for request in (
            "Rewrite both labels firmly.", "Rewrite the first label firmly.",
            "Rewrite the label 'Keep dry' firmly.", "Rewrite the label about handling firmly.",
            "Use the second one. Rewrite the label firmly.",
        ):
            with self.subTest(request=request):
                result, _ = self._route(prefix + request)
                self.assertEqual(result.dependency.mode, "none")

    def test_admitted_multiple_drafts_need_selection_and_single_draft_does_not(self):
        for content, expected in (
            ('Two drafts: "Hello there" and "Welcome back".', "clarify"),
            ('One draft: "Welcome back".', "none"),
        ):
            result, _ = self._route("Rewrite the draft warmly.", history=(
                ChatMessage("user", "Write a greeting."), ChatMessage("assistant", content),
            ))
            self.assertEqual(result.dependency.mode, expected)

    def test_ambiguous_pronoun_cannot_be_resolved_by_a_wrong_none_prediction(self):
        for names in (("Noor", "Emil"), ("Gita", "Zane")):
            text = (f"The sentence is '{names[0]} told {names[1]} that they should hold the map.' "
                    "Replace 'they' with the intended person's name.")
            result, backend = self._route(text)
            self.assertEqual(result.dependency.mode, "clarify")
            self.assertEqual(result.classifier_metadata["task_guard"]["reason"],
                             "ambiguous_pronoun_reference")
            self.assertEqual(backend.calls, [])

    def test_explicit_pronoun_meaning_or_replacement_is_not_withheld(self):
        sentence = "The sentence is 'Noor told Emil that they should hold the map.' "
        for request in (
            "Here 'they' refers to Emil. Replace 'they' with the intended person's name.",
            "Replace 'they' with the intended person's name. Here 'they' refers to Emil.",
            "Replace 'they' with Noor.",
        ):
            with self.subTest(request=request):
                result, _ = self._route(sentence + request)
                self.assertEqual(result.dependency.mode, "none")
        result, _ = self._route("The sentence is 'Noor said they should hold the map.' "
                                "Replace 'they' with the intended person's name.")
        self.assertEqual(result.dependency.mode, "none")

    def test_conversion_cannot_assume_missing_endpoint_units(self):
        for text in ("Convert 35 into the other unit, please.", "Convert 18 to kilograms.",
                     "Convert 9 centimetres.", "Convert 6."):
            with self.subTest(text=text):
                result, backend = self._route(text)
                self.assertEqual(result.dependency.mode, "clarify")
                self.assertEqual(result.classifier_metadata["task_guard"]["reason"],
                                 "missing_conversion_units")
                self.assertEqual(backend.calls, [])

    def test_supplied_units_and_representation_changes_remain_answerable(self):
        for text in ("Convert 35 centimetres to metres.", "Convert 3.5 kg into grams.",
                     "Convert 24 to binary.", "Convert 35 to words.",
                     "Convert 0.25 to a fraction.", "Convert these rows into CSV: red,3; blue,2."):
            with self.subTest(text=text):
                result, _ = self._route(text)
                self.assertEqual(result.dependency.mode, "none")
        result, _ = self._route("Convert 35.", history=(
            ChatMessage("user", "Convert inches to centimetres."),
            ChatMessage("assistant", "What number of inches?"),
        ))
        self.assertEqual(result.dependency.mode, "none")

    def test_optional_fallback_and_supplied_drafts_keep_their_modes(self):
        for text, expected in (
            ("Suggest a garden name using my past preferences if available; otherwise pick a general name.", "optional"),
            ("Rewrite 'I chose a blue pattern' in the past tense.", "none"),
            ("I want a new pattern for my scarf. Suggest one.", "none"),
            ("Explain why a unit conversion needs a starting and target unit.", "none"),
        ):
            with self.subTest(text=text):
                result, _ = self._route(text, predicted=expected)
                self.assertEqual(result.dependency.mode, expected)


if __name__ == "__main__":
    unittest.main()
