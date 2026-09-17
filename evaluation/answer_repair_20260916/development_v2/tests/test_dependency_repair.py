"""Offline counterexamples for answerability review and scoped draft history."""

from dataclasses import asdict
import unittest

from oline_hri.dependency_review import parse_dependency_mode_review
from oline_hri.dependency_routing import SIZE_POLICY_VERSION
from oline_hri.ollama import ChatMessage, OllamaError
from oline_hri.reply_guard import (
    has_unstated_recall_intent, is_drafting_followup, is_drafting_request,
    safe_history_pair, inspect_reply,
)
from oline_hri.routing import RoutingError

from test_dependency_routing import Backend, Classifier, prediction, reviewed, router
from test_conversation_routed import FakeBackend, FakeRetriever, LARGE_MODEL
from test_reliable_conversation import reliable


class DependencyRepairTests(unittest.TestCase):
    def test_positive_task_contracts_do_not_depend_on_fallible_mode_review(self):
        cases = (
            ("Compose a five-line verse about snow on a rooftop.", "none", "nonpersonal_artifact"),
            ("Format these amounts as JSON: copper 11; silver 7.", "none", "supplied_data_transform"),
            ("Explain triangles and circles in three sentences.", "none", "nonpersonal_explanation"),
            ("I have 14 minutes, cardboard, glue, and scissors. Give a timed plan using these materials.",
             "none", "current_resource_plan"),
            ("The values are 5, 10, and 25. Please calculate it.", "clarify", "unspecified_numeric_operation"),
            ("Write an invitation to my colleague Mira for lunch this Friday at noon in the lounge.",
             "none", "supplied_invitation"),
        )
        for text, mode, reason in cases:
            with self.subTest(text=text):
                backend = Backend(review=reviewed("required"))
                result = router(Classifier(default=prediction("required")), backend).route(text)
                self.assertEqual(result.dependency.mode, mode)
                self.assertEqual(result.memory_decision_source, "dependency_task_guard")
                self.assertEqual(result.classifier_metadata["task_guard"]["reason"], reason)
                self.assertEqual(backend.calls, [])

    def test_task_forms_do_not_erase_unsupplied_personal_or_private_inputs(self):
        for text in (
            "Compose a poem about my childhood memories.",
            "Format my saved address as JSON.",
            "I have 14 minutes. Give a plan using my usual medical schedule.",
            "Describe Amara's medical condition.",
            "Explain the schedule of Noor.",
            "Write an invitation to my colleague using the remembered meeting details.",
        ):
            with self.subTest(text=text):
                backend = Backend(review=reviewed("required"))
                result = router(Classifier(default=prediction("required")), backend).route(text)
                self.assertEqual(result.dependency.mode, "required")
                self.assertIsNone(result.classifier_metadata["task_guard"])

    def test_request_wording_is_not_a_current_personal_value(self):
        text = ('An assistant guessed "Your usual arrival gate is North Gate." '
                'Which gate have I actually told you I use? Report my stated gate, not a guess.')
        backend = Backend(review=reviewed("clarify"))
        result = router(Classifier(default=prediction("required")), backend).route(text)
        self.assertEqual(result.dependency.mode, "required")
        self.assertTrue(result.classifier_metadata["recognizable_recall_intent"])
        self.assertEqual(backend.calls, [])

    def test_declarative_tail_cannot_become_a_general_subrequest(self):
        text = "Give a plan for preparing a display. I only need the preparation plan."
        classifier = Classifier(default=prediction("required"))
        result = router(classifier, Backend(review=reviewed("required"))).route(text)
        self.assertEqual(result.dependency.general_request, "")

    def test_heading_only_list_is_a_nonanswer_but_inline_payload_is_retained(self):
        request = "Give a three-item picnic checklist."
        self.assertIn("promise_only", inspect_reply(request, "Here's a three-item picnic checklist:"))
        self.assertNotIn("promise_only", inspect_reply(request, "Checklist: water, sandwiches, napkins."))
        self.assertNotIn("promise_only", inspect_reply(request, "Here's a picnic checklist:\n- Water\n- Sandwiches\n- Napkins"))
        self.assertNotIn("promise_only", inspect_reply("Return CSV.", "item,count\nwater,1"))

    def test_deictic_edits_review_confident_none_and_optional_without_forcing_a_mode(self):
        request = ("Badge captions include Star Watcher, Lunar Scout, and Orbit Guide. "
                   "No caption has been selected. Choose the other one.")
        for raw_mode in ("none", "optional"):
            with self.subTest(raw_mode=raw_mode):
                raw = prediction(raw_mode)
                backend = Backend(review=reviewed("clarify"))
                result = router(Classifier(default=raw), backend).route(request)
                self.assertEqual(result.dependency.mode, "clarify")
                self.assertEqual(result.review_reason, "answerability_unclear")
                self.assertEqual(result.classifier_metadata["whole_request"], asdict(raw))
                self.assertEqual(len(backend.calls), 1)
        # The same syntax is complete when a single source artifact is given.
        history = (ChatMessage("user", "Draft a badge caption about astronomy."),
                   ChatMessage("assistant", "Stars invite us to explore."))
        backend = Backend(review=reviewed("none"))
        result = router(Classifier(default=prediction("none")), backend).route(
            "Make it shorter.", history=history)
        self.assertEqual(result.dependency.mode, "none")
        self.assertEqual(result.review_reason, "answerability_unclear")
        self.assertIn("Stars invite us to explore.", backend.calls[0][1][-1].content)

    def test_explicit_artifact_request_does_not_trigger_deictic_review(self):
        backend = Backend(review=OllamaError("no unresolved edit"))
        result = router(Classifier(default=prediction("none")), backend).route(
            "Write two badge captions about astronomy.")
        self.assertEqual(result.dependency.mode, "none")
        self.assertIsNone(result.review_reason)
        self.assertEqual(backend.calls, [])

    def test_complete_task_can_recover_from_both_confident_wrong_modes(self):
        request = "Arrange these values from smallest to largest: 28, 6, 15."
        for raw_mode in ("required", "clarify"):
            with self.subTest(raw_mode=raw_mode):
                raw = prediction(raw_mode)
                backend = Backend(review=reviewed("none"))
                result = router(Classifier(default=raw), backend).route(request)
                self.assertEqual(result.dependency.mode, "none")
                self.assertFalse(result.dependency.uncertain)
                self.assertFalse(result.decision.memory_required)
                self.assertEqual(result.classifier_metadata["whole_request"], asdict(raw))
                self.assertEqual(result.decision.model_size, "large")
                self.assertIsNone(result.model_size_generation)
                self.assertEqual(backend.calls, [])
                self.assertEqual(result.memory_decision_source, "dependency_task_guard")

    def test_relative_clause_recall_survives_wrong_raw_prediction_and_mixed_suffix(self):
        recall = "Who is the musician I said I liked best?"
        general = "Separately, explain a refrain."
        text = recall + " " + general
        for raw_mode in ("none", "optional", "clarify"):
            with self.subTest(raw_mode=raw_mode):
                raw = prediction("clarify", predicted_mode=raw_mode, uncertain=True, margin=0.01)
                classifier = Classifier({text: raw, recall: prediction("none"),
                                         general: prediction("none")})
                backend = Backend(review=OllamaError("explicit recall must not be downgraded"))
                result = router(classifier, backend).route(text)
                self.assertEqual(result.dependency.mode, "required")
                self.assertEqual(result.dependency.general_request, general)
                self.assertEqual(result.memory_decision_source, "dependency_recall_guard")
                self.assertEqual(result.classifier_metadata["fragment_decision_source"],
                                 "recall_guard_and_raw_parts")
                self.assertEqual(result.classifier_metadata["whole_request"], asdict(raw))
                self.assertEqual(backend.calls, [])

    def test_current_value_prevents_prefix_only_recall_override(self):
        text = "I said I liked Corelli. Which composer did I say I liked?"
        backend = Backend(review=reviewed("none"))
        result = router(Classifier(default=prediction("required")), backend).route(text)
        self.assertFalse(result.classifier_metadata["recognizable_recall_intent"])
        self.assertEqual(result.dependency.mode, "none")
        self.assertEqual(len(backend.calls), 1)

    def test_recovered_recall_never_uses_deleted_history_as_evidence(self):
        text = "Who is the musician I said I liked best?"
        classifier_backend = Backend(review=OllamaError("must not be called"))
        answer_backend, retriever = FakeBackend(), FakeRetriever()
        session, _, _, _ = reliable(
            answer_backend, router=router(Classifier(default=prediction("none")), classifier_backend),
            retriever=retriever,
        )
        session._messages.extend((ChatMessage("user", "My favorite musician is Corelli."),
                                  ChatMessage("assistant", "Your favorite musician is Corelli.")))
        reply = session.send(text)
        self.assertEqual(reply.effective_mode, "required")
        self.assertEqual(reply.response.memory_used, ())
        self.assertNotIn("Corelli", reply.response.speech)
        self.assertEqual(answer_backend.calls, [])
        self.assertEqual(classifier_backend.calls, [])
        self.assertEqual(len(retriever.retrieve_calls), 1)

    def test_mode_review_exact_contract_and_legacy_boolean_separation(self):
        for mode in ("none", "optional", "required", "clarify"):
            self.assertEqual(parse_dependency_mode_review('{"mode":"' + mode + '"}'), mode)
        for invalid in ('{"needs_personal_facts":false}', '{"mode":false}',
                        '{"mode":"unknown"}', '{"mode":"none","mode":"required"}',
                        '{"mode":"none","general_request":"invented"}', '[]'):
            with self.subTest(invalid=invalid), self.assertRaises(RoutingError):
                parse_dependency_mode_review(invalid)

    def test_sizing_is_explicit_and_does_not_load_compute_classifier(self):
        for text, size, reason in (
            ("Good evening!", "small", "short_social"),
            ("Explain a pulley in two sentences.", "large", "substantive_general"),
            ("Draft a courteous reminder.", "large", "substantive_general"),
        ):
            with self.subTest(text=text):
                backend = Backend(OllamaError("compute must not run"))
                result = router(Classifier(default=prediction("none")), backend).route(text)
                self.assertEqual(result.decision.model_size, size)
                self.assertEqual(result.model_size_decision_source, SIZE_POLICY_VERSION)
                self.assertEqual(result.classifier_metadata["compute_policy"]["reason"], reason)
                self.assertIsNone(result.model_size_generation)
                self.assertEqual(backend.calls, [])


class DraftArtifactHistoryTests(unittest.TestCase):
    request = "Give me two short announcements for our pottery sale on 21 March in Hall 3."
    drafts = ("Version 1: Our pottery sale is on 21 March in Hall 3. Bring a pot to share.\n"
              "Version 2: Join our pottery sale on 21 March. We will meet in Hall 3.")
    edit = "Use the second version and make it one sentence, keeping the date and place."
    answer = "Join our pottery sale on 21 March in Hall 3."

    def test_supplied_event_artifact_and_scoped_edit_are_admitted(self):
        self.assertTrue(is_drafting_request(self.request))
        self.assertTrue(safe_history_pair(self.request, self.drafts))
        self.assertTrue(is_drafting_followup(self.edit))
        self.assertTrue(safe_history_pair(
            self.edit, self.answer, drafting=True,
            artifact_context=self.request + "\n" + self.drafts,
        ))
        self.assertFalse(safe_history_pair(self.edit, self.answer, drafting=True))
        self.assertFalse(safe_history_pair(
            "Make the second one more concise.",
            "Join the garden meetup at Cedar Hall Saturday at 2.",
        ))

    def test_artifact_scope_rejects_new_values_and_personal_disclosures(self):
        for answer in (
            self.answer.replace("21", "22"),
            self.answer.replace("Hall", "Gallery"),
            self.answer + " Your camera is in the cabinet.",
            self.answer + " I live in Rome.",
            self.answer + " Our password is 1234.",
        ):
            with self.subTest(answer=answer):
                self.assertFalse(safe_history_pair(
                    self.edit, answer, drafting=True,
                    artifact_context=self.request + "\n" + self.drafts,
                ))
        for request in (
            "Give me two announcements using my remembered meeting details.",
            "Our meeting is on 21 March in Hall 3.",
            "Give me two invitations for my cousin in Hall 3.",
        ):
            with self.subTest(request=request):
                self.assertFalse(safe_history_pair(request, self.answer))

    def test_artifact_edit_is_not_permission_for_later_personal_recall(self):
        self.assertTrue(has_unstated_recall_intent("What date did I say our sale was?"))
        self.assertFalse(safe_history_pair(
            "What date did I say our sale was?", "Your sale was on 21 March.",
            drafting=True, artifact_context=self.request + "\n" + self.drafts,
        ))
        self.assertFalse(has_unstated_recall_intent(
            'Rewrite the sentence "I said I liked Corelli" in the future tense.'))
        self.assertFalse(has_unstated_recall_intent("What does 'I said hello' mean?"))


if __name__ == "__main__":
    unittest.main()
