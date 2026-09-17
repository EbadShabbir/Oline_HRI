"""Learned-router contracts with injected predictions and no model artifacts."""

from dataclasses import asdict, dataclass, field, replace
import json
from types import SimpleNamespace
import unittest

from oline_hri.dependency_classifier import DependencyPrediction
from oline_hri.dependency_routing import LearnedSemanticRouter, SIZE_POLICY_VERSION
from oline_hri.dependency_review import (
    DEPENDENCY_REVIEW_SCHEMA, DEPENDENCY_REVIEW_PROMPT, DEPENDENCY_REVIEW_EXAMPLES,
    dependency_review_schema, dependency_review_messages, fragment_candidates, parse_dependency_review,
    DEPENDENCY_MODE_REVIEW_SCHEMA, parse_dependency_mode_review,
)
from oline_hri.ollama import ChatMessage, OllamaError
from oline_hri.routing import MODEL_SIZE_SCHEMA, RoutingError

from test_conversation_routed import (
    FakeBackend, FakeRetriever, LARGE_MODEL, SMALL_MODEL, chat_result, hybrid_match, memory,
)
from test_reliable_conversation import reliable


def prediction(mode="none", **changes):
    raw_mode = changes.get("predicted_mode", mode)
    margin = changes.get("margin", 1.0)
    value = DependencyPrediction(
        mode=mode, predicted_mode=mode,
        scores={key: margin if key == raw_mode else 0.0
                for key in ("none", "optional", "required", "clarify")},
        margin=1.0, threshold=0.2, uncertain=False, general_request="",
        model_manifest={"schema_version": "dependency_classifier_v1",
                        "fingerprint": "unit-fixture-fingerprint",
                        "training": {"corpus_sha256": "unit-fixture-corpus"}},
    )
    return replace(value, **changes)


@dataclass(frozen=True)
class Classifier:
    """Frozen adapter; returned values use the real frozen prediction shape."""
    outcomes: dict = field(default_factory=dict)
    default: object = field(default_factory=lambda: prediction("clarify"))
    calls: list = field(default_factory=list)

    def classify(self, text, *, history=()):
        self.calls.append((text, tuple(history)))
        result = self.outcomes.get(text, self.default)
        if isinstance(result, BaseException):
            raise result
        return result


def reviewed(mode="required", index=0, **changes):
    return chat_result(raw=json.dumps({"mode": mode}), model=LARGE_MODEL, **changes)


class Backend:
    def __init__(self, result=None, *, review=None):
        self.result = result if result is not None else chat_result(raw='{"model_size":"small"}')
        self.review = review if review is not None else reviewed()
        self.calls = []

    def chat(self, model, messages, **options):
        self.calls.append((model, tuple(messages), options))
        result = self.review if model == LARGE_MODEL else self.result
        if isinstance(result, BaseException):
            raise result
        return result


def router(classifier, backend=None, **options):
    return LearnedSemanticRouter(
        backend or Backend(), classifier=classifier, small_model=SMALL_MODEL,
        large_model=LARGE_MODEL, **options,
    )


class DependencyRoutingTests(unittest.TestCase):
    def test_four_modes_preserve_local_scores_and_manifest_without_fake_generation(self):
        for mode in ("none", "optional", "required", "clarify"):
            with self.subTest(mode=mode):
                raw = prediction(mode)
                classifier = Classifier(default=raw)
                backend = Backend(review=reviewed(mode))
                result = router(classifier, backend).route(
                    "Where is my compass?" if mode == "required" else "Please handle this request")
                self.assertEqual(result.dependency.mode, mode)
                self.assertEqual(result.decision.memory_required, mode in {"optional", "required"})
                self.assertEqual(result.policy, "dependency_v1")
                self.assertIsNone(result.memory_required_generation)
                self.assertIsNone(result.model_size_generation)
                self.assertEqual(result.model_size_decision_source, SIZE_POLICY_VERSION)
                self.assertEqual(result.classifier_metadata["whole_request"], asdict(raw))
                self.assertEqual(result.classifier_metadata["form_source"], "punctuation_hint")
                self.assertEqual(len(classifier.calls), 1)
                self.assertEqual(len(backend.calls), int(mode == "clarify"))
                if mode == "clarify":
                    self.assertIs(result.review_generation, backend.review)
                    self.assertEqual(backend.calls[0][2]["response_format"], DEPENDENCY_MODE_REVIEW_SCHEMA)
                else:
                    self.assertIsNone(result.review_generation)
                    self.assertIsNone(result.review_reason)

    def test_accepted_required_without_recall_intent_gets_one_independent_review(self):
        raw = prediction("required")
        for reviewed_mode in ("none", "optional", "required", "clarify"):
            with self.subTest(reviewed_mode=reviewed_mode):
                backend = Backend(review=reviewed(reviewed_mode))
                result = router(Classifier(default=raw), backend).route("Can you help me plan my day?")
                self.assertEqual(result.dependency.mode, reviewed_mode)
                self.assertEqual(result.dependency.uncertain, reviewed_mode == "clarify")
                self.assertEqual(result.review_reason, "unverified_required")
                self.assertIs(result.review_generation, backend.review)
                self.assertEqual(result.classifier_metadata["whole_request"], asdict(raw))
                self.assertFalse(result.classifier_metadata["recognizable_recall_intent"])
                self.assertEqual([call[0] for call in backend.calls], [LARGE_MODEL])
                envelope = json.loads(backend.calls[0][1][-1].content)
                self.assertEqual(set(envelope), {"current_message", "task_context"})
                self.assertNotIn("predicted_mode", repr(envelope))

    def test_accepted_explicit_recall_without_remember_skips_review(self):
        for text in ("Where are my keys?", "What time is my appointment?",
                     "Which fabric did I choose for the cushion covers?",
                     "What did I tell you about my appointment last time?",
                     "Show me my saved address.", "What does the previous record say?"):
            with self.subTest(text=text):
                backend = Backend(review=OllamaError("must not be called"))
                result = router(Classifier(default=prediction("required")), backend,
                                fixed_model_size="small").route(text)
                self.assertEqual(result.dependency.mode, "required")
                self.assertTrue(result.classifier_metadata["recognizable_recall_intent"])
                self.assertIsNone(result.review_generation)
                self.assertEqual(backend.calls, [])

    def test_unverified_required_malformed_review_stays_uncertain(self):
        backend = Backend(review=chat_result(raw="not JSON", model=LARGE_MODEL))
        result = router(Classifier(default=prediction("required")), backend,
                        fixed_model_size="small").route("Can you help me plan my day?")
        self.assertEqual(result.dependency.mode, "clarify")
        self.assertTrue(result.dependency.uncertain)
        self.assertEqual(result.review_reason, "unverified_required")
        self.assertIs(result.review_generation, backend.review)
        self.assertEqual(len(backend.calls), 1)

    def test_uncertainty_preserves_raw_class_and_asks_for_clarification(self):
        raw = prediction("clarify", predicted_mode="required", uncertain=True,
                         scores={"none": 0.3, "optional": 0.2, "required": 0.35, "clarify": 0.1},
                         margin=0.05, threshold=0.2)
        backend = Backend(review=chat_result(raw="not JSON", model=LARGE_MODEL))
        result = router(Classifier(default=raw), backend, fixed_model_size="small").route("Use the previous detail")
        self.assertEqual(result.dependency.mode, "clarify")
        self.assertTrue(result.dependency.uncertain)
        self.assertFalse(result.decision.memory_required)
        self.assertEqual(result.memory_decision_source, "dependency_clarification")
        self.assertEqual(result.classifier_metadata["whole_request"]["predicted_mode"], "required")
        self.assertEqual(result.classifier_metadata["whole_request"]["margin"], 0.05)

    def test_deterministic_generator_size_does_not_call_unused_compute_backend(self):
        backend = Backend(OllamaError("compute should never be called"))
        result = router(Classifier(default=prediction("optional")), backend).route("Suggest a craft")
        self.assertEqual(result.dependency.mode, "optional")
        self.assertTrue(result.decision.memory_required)
        self.assertEqual(result.decision.model_size, "large")
        self.assertEqual(result.model_size_decision_source, SIZE_POLICY_VERSION)
        self.assertIsNone(result.model_size_generation)
        self.assertEqual(backend.calls, [])

    def test_safe_task_history_reaches_whole_request_and_independent_review(self):
        history = (ChatMessage("user", "Explain tides."),
                   ChatMessage("assistant", "The Moon's gravity contributes to ocean tides."))
        classifier = Classifier(default=prediction("clarify"))
        backend = Backend(review=reviewed("none"))
        result = router(classifier, backend).route("Give another example.", history=history)
        self.assertEqual(classifier.calls[0][1], history)
        envelope = json.loads(backend.calls[0][1][-1].content)
        self.assertEqual(envelope["task_context"], [message.to_dict() for message in history])
        self.assertEqual(result.dependency.mode, "none")
        self.assertIsNone(result.model_size_generation)

    def test_safety_exceptions_and_interrupts_are_not_hidden_by_size_fallback(self):
        class StopGuard(RuntimeError):
            pass

        for failure in (StopGuard("resource guard"), KeyboardInterrupt()):
            with self.subTest(source="classifier", failure=type(failure).__name__):
                backend = Backend()
                with self.assertRaises(type(failure)):
                    router(Classifier(default=failure), backend).route("Explain tides.")
                self.assertEqual(backend.calls, [])
            with self.subTest(source="backend", failure=type(failure).__name__):
                with self.assertRaises(type(failure)):
                    router(Classifier(default=prediction("clarify")), Backend(review=failure)).route("Handle this request.")

    def test_mixed_suffix_is_literal_and_both_parts_are_checked_without_history(self):
        general = "Explain how magnets work."
        for text, recall in (
            ("Where is my compass? " + general, "Where is my compass?"),
            ("Recall my saved compass location; " + general, "Recall my saved compass location"),
            ("Recall my saved compass location, and " + general, "Recall my saved compass location"),
            ("Recall my saved compass location and " + general, "Recall my saved compass location"),
        ):
            with self.subTest(text=text):
                classifier = Classifier({text: prediction("required"), general: prediction("none"),
                                         recall: prediction("required")})
                result = router(classifier, Backend(review=reviewed(index=1)), fixed_model_size="small").route(
                    text, history=(ChatMessage("user", "An older general task."),))
                self.assertEqual(result.dependency.general_request, general)
                self.assertIn(general, text)
                self.assertEqual(classifier.calls[1:], [(general, ()), (recall, ())])
                self.assertEqual([check["part"] for check in result.classifier_metadata["fragment_checks"]],
                                 ["general", "recall"])

    def test_reviewed_mixed_suffix_survives_local_margin_rejection(self):
        text, general, recall = "Where is my compass? Explain magnets.", "Explain magnets.", "Where is my compass?"
        uncertain_none = prediction("clarify", predicted_mode="none", uncertain=True, margin=0.01)
        uncertain_required = prediction("clarify", predicted_mode="required", uncertain=True, margin=0.01)
        for suffix, remainder in ((uncertain_none, prediction("required")),
                                  (prediction("none"), uncertain_required),
                                  (prediction("none"), prediction("optional")),
                                  (prediction("required"), prediction("required"))):
            with self.subTest(suffix=suffix, remainder=remainder):
                classifier = Classifier({text: prediction("required"), general: suffix, recall: remainder})
                result = router(classifier, Backend(review=reviewed(index=1)), fixed_model_size="small").route(text)
                self.assertEqual(result.dependency.general_request,
                                 general if suffix.predicted_mode == "none" else "")
                self.assertFalse(result.dependency.uncertain)

    def test_fragment_search_tests_only_three_earliest_sentence_boundaries(self):
        text = "Recall the saved note? Explain the first part? Explain the second part? Explain the third part? Explain the last part?"
        classifier = Classifier({text: prediction("required")})
        result = router(classifier, fixed_model_size="small").route(text)
        self.assertEqual(result.dependency.general_request, "")
        self.assertEqual([call[0] for call in classifier.calls[1:]], [
            "Explain the first part? Explain the second part? Explain the third part? Explain the last part?",
            "Explain the second part? Explain the third part? Explain the last part?", "Explain the third part? Explain the last part?",
        ])
        self.assertEqual(len(classifier.calls), 4)

    def test_full_comparison_precedes_internal_noun_coordination(self):
        for connector, general in (
            ("? ", "What is the difference between a metronome and a tuner?"),
            (" and ", "what is the difference between a metronome and a tuner?"),
            (" and ", "explain the difference between a metronome and a tuner."),
        ):
            recall = "Who led my previous lesson"
            text = recall + connector + general
            prefix = recall + "?" if connector == "? " else recall
            classifier = Classifier({text: prediction("required"), general: prediction("none"),
                                     prefix: prediction("required")}, default=prediction("none"))
            with self.subTest(text=text):
                result = router(classifier, fixed_model_size="small").route(text)
                self.assertEqual(result.dependency.general_request, general)
                self.assertEqual([call[0] for call in classifier.calls], [text, general, prefix])
                self.assertTrue(all(candidate["general_part"] not in {"a tuner?", "a tuner."}
                                    for candidate in fragment_candidates(text)))

    def test_sentence_priority_and_cap_preserve_all_general_clauses(self):
        general = "Explain compression. Compare PNG and JPEG and GIF and TIFF."
        text = "Which room did I reserve? " + general
        candidates = fragment_candidates(text)
        self.assertEqual(candidates[0]["general_part"], general)
        self.assertLessEqual(len(candidates), 3)
        self.assertFalse(any(candidate["general_part"].startswith(("JPEG", "GIF", "TIFF"))
                             for candidate in candidates))

    def test_unresolved_or_list_suffix_is_not_promoted_to_general_request(self):
        for text in ("Recall the shopping list, and milk and oats.",
                     "Where is my compass? Explain that."):
            with self.subTest(text=text):
                classifier = Classifier({text: prediction("required")}, default=prediction("clarify"))
                result = router(classifier, fixed_model_size="small").route(text)
                self.assertEqual(result.dependency.general_request, "")
                self.assertTrue(all(not call[1] for call in classifier.calls))

    def test_fixed_size_skips_compute_and_rejects_invalid_values_consistently(self):
        for size in ("small", "large"):
            with self.subTest(size=size):
                backend = Backend()
                result = router(Classifier(default=prediction()), backend, fixed_model_size=size).route("Explain tides.")
                self.assertEqual(result.decision.model_size, size)
                self.assertEqual(result.model_size_decision_source, "fixed")
                self.assertIsNone(result.model_size_generation)
                self.assertEqual(backend.calls, [])
        for size in (False, True, "", "medium", [], {}):
            with self.subTest(size=size), self.assertRaises(ValueError):
                router(Classifier(), fixed_model_size=size)

    def test_invalid_prediction_contract_is_rejected_before_compute(self):
        invalid = (
            None, object(), {"mode": "none"}, prediction(mode=[]),
            SimpleNamespace(**asdict(prediction())),
            prediction(predicted_mode="unknown"), prediction(uncertain=1),
            prediction(predicted_mode="required"),
            prediction(scores={"none": float("nan"), "optional": 0.0, "required": 0.0, "clarify": 0.0}),
            prediction(scores={"none": 1.0}), prediction(margin=-1.0),
            prediction(threshold=float("nan")), prediction(model_manifest="not a manifest"),
            prediction(scores={"none": 10 ** 1000, "optional": 0.0, "required": 0.0, "clarify": 0.0}),
        )
        for value in invalid:
            with self.subTest(value=value):
                backend = Backend()
                with self.assertRaises(RoutingError):
                    router(Classifier(default=value), backend).route("Explain tides.")
                self.assertEqual(backend.calls, [])

        # Invalid fragment predictions must fail before audit serialization.
        text, fragment = "Where is my compass? Explain magnets.", "Explain magnets."
        for value in (None, SimpleNamespace(**asdict(prediction()))):
            with self.subTest(fragment_prediction=value):
                backend = Backend()
                classifier = Classifier({text: prediction("required"), fragment: value})
                with self.assertRaises(RoutingError):
                    router(classifier, backend).route(text)
                self.assertEqual(backend.calls, [])

    def test_learned_required_route_uses_evidence_without_inventing_classifier_generation(self):
        item = memory(1, "Your compass is in the linen drawer.")
        backend = FakeBackend()
        learned = router(Classifier(default=prediction("required")), fixed_model_size="small")
        session, _, _, _ = reliable(backend, router=learned,
                                   retriever=FakeRetriever((hybrid_match(item),)))
        result = session.send("Where is my compass?")
        self.assertEqual(result.response.speech, item.canonical_text)
        self.assertEqual(result.response.memory_used, (item.id,))
        self.assertIsNone(result.route.memory_required_generation)
        self.assertEqual(result.route.classifier_metadata["whole_request"]["predicted_mode"], "required")

    def test_wrapper_accepts_mixed_comma_and_suffix_without_leaking_prefix_to_generator(self):
        general = "Explain how magnets work."
        recall = "Where is my compass"
        text = recall + ", and " + general
        item = memory(1, "Your compass is in the linen drawer.")
        classifier = Classifier({text: prediction("required"), general: prediction("none"),
                                 recall: prediction("required")})
        backend = FakeBackend((chat_result("Magnets exert forces through magnetic fields."),))
        session, _, _, _ = reliable(
            backend, router=router(classifier, Backend(review=reviewed(index=1)), fixed_model_size="small"),
            retriever=FakeRetriever((hybrid_match(item),)),
        )
        result = session.send(text)
        self.assertEqual(result.response.speech,
                         item.canonical_text + " Magnets exert forces through magnetic fields.")
        self.assertEqual(result.response_transform, "verified_mixed_prefix")
        self.assertEqual(result.response.memory_used, (item.id,))
        self.assertNotIn("linen", repr(backend.calls))

    def test_uncertain_general_can_be_resolved_without_changing_raw_prediction_or_compute_size(self):
        raw = prediction("clarify", predicted_mode="none", uncertain=True, margin=0.01)
        backend = Backend(review=reviewed("none"))
        history = (ChatMessage("user", "Explain tides."), ChatMessage("assistant", "Water levels change."))
        result = router(Classifier(default=raw), backend).route("Give another example.", history=history)
        self.assertEqual(result.dependency.mode, "none")
        self.assertFalse(result.dependency.uncertain)
        self.assertEqual(result.classifier_metadata["whole_request"], asdict(raw))
        self.assertIs(result.review_generation, backend.review)
        self.assertEqual(result.decision.model_size, "large")
        self.assertEqual([call[0] for call in backend.calls], [LARGE_MODEL])
        envelope = json.loads(backend.calls[0][1][-1].content)
        self.assertEqual(envelope["task_context"], [message.to_dict() for message in history])
        self.assertEqual(set(envelope), {"current_message", "task_context"})
        self.assertNotIn("expected_modes", envelope)

    def test_accepted_required_avoids_fallible_review_override(self):
        backend = Backend(review=reviewed("none"))
        result = router(Classifier(default=prediction("required")), backend, fixed_model_size="small").route("Use my saved itinerary.")
        self.assertEqual(result.dependency.mode, "required")
        self.assertIsNone(result.review_reason)
        self.assertEqual(backend.calls, [])
        self.assertIsNone(result.review_generation)

    def test_required_below_calibration_support_receives_one_review(self):
        raw = prediction("clarify", predicted_mode="required", uncertain=True, margin=0.01)
        backend = Backend(review=reviewed("none"))
        result = router(Classifier(default=raw), backend, fixed_model_size="small").route("Edit the supplied draft.")
        self.assertEqual(result.dependency.mode, "none")
        self.assertEqual(result.review_reason, "memory_uncertain")
        self.assertEqual(len(backend.calls), 1)
        self.assertIs(result.review_generation, backend.review)

    def test_malformed_truncated_wrong_model_and_unavailable_reviews_fail_closed_once(self):
        failures = (chat_result(raw="broken", model=LARGE_MODEL), reviewed(done_reason="length"),
                    chat_result(raw='{"mode":"none","general_index":0}', model=SMALL_MODEL),
                    OllamaError("review unavailable"),
                    chat_result(raw='{"mode":"none","general_index":0,"extra":true}', model=LARGE_MODEL))
        for failure in failures:
            backend = Backend(review=failure)
            with self.subTest(failure=failure):
                raw = prediction("clarify", predicted_mode="required", uncertain=True, margin=0.01)
                result = router(Classifier(default=raw), backend, fixed_model_size="large").route("Recall the retained fact.")
                self.assertEqual(result.dependency.mode, "clarify")
                self.assertTrue(result.dependency.uncertain)
                self.assertEqual(len(backend.calls), 1)
                self.assertIsNotNone(result.classifier_metadata["review"]["error"])
                if isinstance(failure, OllamaError):
                    self.assertIsNone(result.review_generation)
                else:
                    self.assertIs(result.review_generation, failure)

    def test_review_parser_requires_exact_boolean_and_rejects_mixed_metadata(self):
        self.assertIs(parse_dependency_review('{"needs_personal_facts":true}'), True)
        self.assertIs(parse_dependency_review('{"needs_personal_facts":false}'), False)
        for value in ('{"needs_personal_facts":1}', '{"needs_personal_facts":"false"}',
                      '{"needs_personal_facts":false,"general_index":1}',
                      '{"needs_personal_facts":true,"needs_personal_facts":false}',
                      '[]', '```json\n{}\n```'):
            with self.subTest(value=value), self.assertRaises(RoutingError):
                parse_dependency_review(value)
        self.assertEqual(dependency_review_schema(), DEPENDENCY_REVIEW_SCHEMA)
        self.assertLessEqual(len(DEPENDENCY_REVIEW_PROMPT.split()), 100)
        self.assertEqual(len(DEPENDENCY_REVIEW_EXAMPLES), 3)
        messages = dependency_review_messages("An ambiguous request.", ())
        self.assertEqual(len(messages), 8)
        self.assertEqual(json.loads(messages[-1].content), {"current_message": "An ambiguous request.", "task_context": []})

    def test_uncertain_modes_receive_one_exact_mode_review(self):
        for raw_mode in ("none", "optional", "required"):
            for mode in ("none", "optional", "required", "clarify"):
                raw = prediction("clarify", predicted_mode=raw_mode, uncertain=True, margin=0.01)
                backend = Backend(review=reviewed(mode))
                with self.subTest(raw_mode=raw_mode, mode=mode):
                    result = router(Classifier(default=raw), backend, fixed_model_size="small").route("Handle this request")
                    self.assertEqual(result.dependency.mode, mode)
                    self.assertEqual(result.dependency.uncertain, mode == "clarify")
                    self.assertEqual(result.classifier_metadata["whole_request"], asdict(raw))
                    self.assertEqual(result.classifier_metadata["review"]["mode"], mode)
                    self.assertEqual([call[0] for call in backend.calls], [LARGE_MODEL])

    def test_raw_clarify_uses_completeness_review_and_rejects_legacy_boolean(self):
        for uncertain in (False, True):
            raw = prediction("clarify", uncertain=uncertain, margin=0.01 if uncertain else 1.0)
            for mode in ("none", "optional", "required", "clarify"):
                backend = Backend(review=reviewed(mode))
                with self.subTest(uncertain=uncertain, mode=mode):
                    result = router(Classifier(default=raw), backend, fixed_model_size="small").route("Use that one")
                    self.assertEqual(result.dependency.mode, mode)
                    self.assertEqual(result.dependency.uncertain, mode == "clarify")
                    self.assertEqual(result.classifier_metadata["whole_request"], asdict(raw))
                    self.assertIs(result.review_generation, backend.review)
                    self.assertEqual(result.review_reason, "memory_clarify")
                    self.assertEqual(len(backend.calls), 1)
        backend = Backend(review=chat_result(raw='{"needs_personal_facts":false}', model=LARGE_MODEL))
        result = router(Classifier(default=prediction("clarify")), backend).route("Use that one")
        self.assertEqual(result.dependency.mode, "clarify")
        self.assertIsNotNone(result.classifier_metadata["review"]["error"])

    def test_reviewed_clarification_has_no_fabricated_compute_generation(self):
        raw = prediction("clarify", uncertain=True, margin=0.01)
        backend = Backend(review=reviewed("clarify"))
        result = router(Classifier(default=raw), backend).route("Use that one")
        self.assertEqual(result.dependency.mode, "clarify")
        self.assertEqual(result.decision.model_size, "small")
        self.assertIsNone(result.model_size_generation)
        self.assertIs(result.review_generation, backend.review)
        self.assertEqual(result.classifier_metadata["compute_policy"]["reason"], "application_clarification")
        self.assertEqual([call[0] for call in backend.calls], [LARGE_MODEL])

    def test_reviewed_clarify_delivers_question_without_retrieval_or_answer_generation(self):
        for uncertain in (False, True):
            raw = prediction("clarify", uncertain=uncertain, margin=0.01 if uncertain else 1.0)
            classifier_backend = Backend(review=reviewed("clarify"))
            answer_backend, retriever = FakeBackend(), FakeRetriever()
            learned = router(Classifier(default=raw), classifier_backend, fixed_model_size="small")
            session, _, _, reviewer = reliable(answer_backend, router=learned, retriever=retriever)
            with self.subTest(uncertain=uncertain):
                result = session.send("Use that one")
                self.assertTrue(result.response.speech.endswith("?"))
                self.assertEqual(result.effective_mode, "clarify")
                self.assertEqual(result.retrieval_status, "skipped")
                self.assertEqual(result.response.memory_used, ())
                self.assertEqual(len(classifier_backend.calls), 1)
                self.assertEqual(answer_backend.calls, [])
                self.assertEqual(retriever.retrieve_calls, [])
                self.assertEqual(reviewer.calls, [])


if __name__ == "__main__":
    unittest.main()
