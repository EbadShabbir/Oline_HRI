"""Contract and control-flow checks, using no live model or personal store.

These tests establish bounded behavior under injected decisions. They do not
claim that a probabilistic classifier labels unseen language correctly.
"""

from dataclasses import replace
import json
import unittest

from oline_hri.ollama import ChatMessage, ChatResult, OllamaError
from oline_hri.routing import (
    MAX_ROUTER_HISTORY_CHARACTERS,
    MAX_ROUTER_HISTORY_MESSAGES,
    MODEL_SIZE_SCHEMA,
    ROUTER_SEED,
    ROUTER_TEMPERATURE,
    RouteDecision,
    RoutingError,
    RoutingResult,
)
from oline_hri.semantic_routing import (
    MAX_GENERAL_REQUEST_CHARACTERS,
    MAX_SEMANTIC_RESPONSE_CHARACTERS,
    MISSING_FACT_LABELS,
    ANSWERABILITY_SCHEMA,
    SEMANTIC_DEMONSTRATION_MESSAGES,
    SEMANTIC_MEMORY_SCHEMA,
    SEMANTIC_MODE_SCHEMA,
    SEMANTIC_REVIEW_SCHEMA,
    SEMANTIC_MEMORY_SOURCES,
    SEMANTIC_REVIEW_REASONS,
    SEMANTIC_SIZE_SOURCES,
    MemoryDependency,
    SemanticRouter,
    SemanticRoutingResult,
    parse_memory_dependency,
    parse_semantic_generation,
    parse_answerability,
    parse_review_dependency,
)


SMALL = "test:small"
LARGE = "test:large"


def payload(mode="none", *, form="request", missing_fact=None,
            general_request="", uncertain=False):
    if missing_fact is None:
        missing_fact = {"none": "", "optional": "personal preference",
                        "required": "stored personal fact", "clarify": "request context"}[mode]
    return dict(form=form, mode=mode, missing_fact=missing_fact,
                general_request=general_request, uncertain=uncertain)


def generation(content, model=SMALL, **changes):
    result = ChatResult(
        model=model, content=content if isinstance(content, str) else json.dumps(content),
        done_reason="stop", total_duration_ns=101, load_duration_ns=3,
        prompt_eval_count=12, eval_count=20, eval_duration_ns=7,
        prompt_eval_duration_ns=91,
    )
    return replace(result, **changes)


class Backend:
    def __init__(self, *, mode="none", form="request", size="small", probe="current_inputs", review=None):
        self.results = {
            "mode": generation({"form": form, "mode": mode}),
            "size": generation({"model_size": size}),
            "probe": generation({"answer_source": probe}),
            "review": generation(payload(mode), model=LARGE) if review is None else review,
        }
        self.calls = []
        self.resident_model = None

    def chat(self, model, messages, **kwargs):
        self.calls.append((model, tuple(messages), kwargs))
        schema = kwargs["response_format"]
        stage = ("mode" if schema is SEMANTIC_MODE_SCHEMA else "size" if schema is MODEL_SIZE_SCHEMA
                 else "probe" if schema is ANSWERABILITY_SCHEMA else "review" if schema is SEMANTIC_REVIEW_SCHEMA else None)
        if stage is None or stage not in self.results:
            raise AssertionError("unexpected or repeated inference")
        result = self.results.pop(stage)
        if isinstance(result, BaseException):
            raise result
        self.resident_model = model
        return result


def router(backend, **kwargs):
    return SemanticRouter(backend, small_model=SMALL, large_model=LARGE, **kwargs)


def envelope(call):
    return json.loads(call[1][-1].content.split("\n", 1)[1])


class MemoryDependencyTests(unittest.TestCase):
    def test_four_modes_have_separate_semantics(self):
        for mode in ("none", "optional", "required", "clarify"):
            with self.subTest(mode=mode):
                value = payload(mode)
                self.assertEqual(parse_memory_dependency(json.dumps(value)), MemoryDependency(**value))

    def test_missing_fields_extra_fields_and_duplicate_keys_are_rejected(self):
        for key in payload():
            value = payload()
            del value[key]
            with self.subTest(missing=key), self.assertRaises(RoutingError):
                parse_memory_dependency(json.dumps(value))
        value = payload()
        value["memory_required"] = False
        with self.assertRaises(RoutingError):
            parse_memory_dependency(json.dumps(value))
        duplicate = json.dumps(payload())[:-1] + ',"mode":"required"}'
        with self.assertRaises(RoutingError):
            parse_memory_dependency(duplicate)

    def test_non_json_wrappers_nonstandard_values_and_wrong_types_rejected(self):
        values = [None, {}, "[]", "null", "false", '"text"',
                  "```json\n" + json.dumps(payload()) + "\n```",
                  json.dumps(payload()) + " explanatory prose", "{" * 1200,
                  " " * (MAX_SEMANTIC_RESPONSE_CHARACTERS + 1)]
        for value in values:
            with self.subTest(value_type=type(value)), self.assertRaises(RoutingError):
                parse_memory_dependency(value)
        for key, value in (("form", "advice"), ("mode", "never"), ("mode", []),
                           ("uncertain", 0), ("uncertain", "false"),
                           ("missing_fact", None), ("general_request", []),
                           ("uncertain", float("nan"))):
            candidate = payload()
            candidate[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(RoutingError):
                parse_memory_dependency(json.dumps(candidate))

    def test_missing_fact_cannot_contain_personal_values(self):
        for label in ("meeting at 09:45", "Alex", "at the station", "secret 1234", "private information\n"):
            with self.subTest(label=label), self.assertRaises(RoutingError) as caught:
                parse_memory_dependency(json.dumps(payload("required", missing_fact=label)))
            self.assertNotIn(label, str(caught.exception))
        self.assertEqual(set(SEMANTIC_MEMORY_SCHEMA["properties"]["missing_fact"]["enum"]), MISSING_FACT_LABELS)

    def test_cross_field_inconsistencies_rejected(self):
        for candidate in (
            payload("none", missing_fact="personal preference"),
            payload("required", missing_fact=""),
            payload("required", missing_fact="request context"),
            payload("optional", missing_fact=""),
            payload("clarify", missing_fact="personal schedule"),
            payload("none", general_request="Explain clouds."),
            payload("optional", general_request="Explain clouds."),
            payload("required", form="statement"),
            payload("optional", form="statement"),
        ):
            with self.subTest(candidate=candidate), self.assertRaises(RoutingError):
                parse_memory_dependency(json.dumps(candidate))

    def test_mixed_request_requires_exact_current_substring(self):
        user = "When is my appointment? Explain a first appointment."
        candidate = payload("required", general_request="Explain a first appointment.")
        parsed = parse_memory_dependency(json.dumps(candidate), user_text=user)
        self.assertEqual(parsed.general_request, candidate["general_request"])
        for part in ("explain a first appointment.", "Give a diagnosis.", user,
                     " Explain a first appointment.", "x" * (MAX_GENERAL_REQUEST_CHARACTERS + 1)):
            with self.subTest(part=part), self.assertRaises(RoutingError):
                parse_memory_dependency(json.dumps(payload("required", general_request=part)), user_text=user)

    def test_schema_has_no_redundant_retrieval_boolean(self):
        self.assertEqual(set(SEMANTIC_MEMORY_SCHEMA["properties"]),
                         {"form", "mode", "missing_fact", "general_request", "uncertain"})
        self.assertEqual(set(SEMANTIC_MEMORY_SCHEMA["required"]), set(SEMANTIC_MEMORY_SCHEMA["properties"]))
        self.assertFalse(SEMANTIC_MEMORY_SCHEMA["additionalProperties"])

    def test_result_rejects_boolean_mode_contradiction(self):
        for mode in ("none", "optional", "required", "clarify"):
            dep = MemoryDependency(**payload(mode))
            with self.subTest(mode=mode), self.assertRaises(RoutingError):
                SemanticRoutingResult(
                    decision=RouteDecision(mode not in {"optional", "required"}, "small"),
                    memory_required_generation=None, model_size_generation=None, dependency=dep,
                )

    def test_short_raw_adapter_derives_labels_without_fabricating_text(self):
        for mode in ("none", "optional", "required", "clarify"):
            parsed = parse_semantic_generation(json.dumps({"form": "request", "mode": mode}))
            self.assertEqual(parsed.mode, mode)
            self.assertEqual(parsed.general_request, "")
            self.assertIn(parsed.missing_fact, MISSING_FACT_LABELS)
        for value in ('{"mode":"none"}', '{"form":"request","mode":"none","extra":true}',
                      '{"form":"request","mode":[]}', '{"form":"statement","mode":"required"}'):
            with self.subTest(value=value), self.assertRaises(RoutingError):
                parse_semantic_generation(value)
        self.assertEqual(parse_semantic_generation(json.dumps(payload())), MemoryDependency(**payload()))
        with self.assertRaises(RoutingError):
            parse_memory_dependency('{"form":"question","mode":"none"}')

    def test_probe_parser_is_strict_and_cannot_stand_in_for_memory_mode(self):
        for source in ("current_inputs", "personal_record", "unclear"):
            self.assertEqual(parse_answerability(json.dumps({"answer_source": source})), source)
        for value in ('{}', '{"answer_source":true}', '{"answer_source":"unknown"}',
                      '{"answer_source":"unclear","mode":"none"}',
                      '{"answer_source":"unclear","answer_source":"current_inputs"}'):
            with self.subTest(value=value), self.assertRaises(RoutingError):
                parse_answerability(value)
        with self.assertRaises(RoutingError):
            parse_semantic_generation('{"answer_source":"personal_record"}')

    def test_review_schema_has_disjoint_complete_metadata_branches(self):
        self.assertEqual(set(SEMANTIC_REVIEW_SCHEMA), {"oneOf"})
        branches = SEMANTIC_REVIEW_SCHEMA["oneOf"]
        self.assertEqual(len(branches), 4)
        modes = set()
        for branch in branches:
            properties = branch["properties"]
            self.assertEqual(set(branch["required"]), set(SEMANTIC_MEMORY_SCHEMA["required"]))
            self.assertFalse(branch["additionalProperties"])
            mode = properties["mode"]["const"]
            modes.add(mode)
            value = payload(mode, missing_fact=properties["missing_fact"]["const"],
                            uncertain=properties["uncertain"]["const"])
            self.assertEqual(parse_review_dependency(json.dumps(value)).mode, mode)
            if mode != "required":
                self.assertEqual(properties["general_request"], {"const": ""})
            else:
                self.assertEqual(properties["general_request"]["maxLength"], MAX_GENERAL_REQUEST_CHARACTERS)
        self.assertEqual(modes, {"none", "optional", "required", "clarify"})

    def test_runtime_review_parser_rejects_metadata_contradictions_even_without_decoder(self):
        for value in (payload("none", uncertain=True), payload("required", uncertain=True),
                      payload("optional", missing_fact="personal preference"),
                      payload("clarify", uncertain=False),
                      payload("clarify", uncertain=True, general_request="Explain a lever.")):
            # These are valid historical full-schema objects; new decoding and
            # its independent parser both prevent the contradictory metadata.
            parse_memory_dependency(json.dumps(value))
            with self.subTest(value=value), self.assertRaises(RoutingError):
                parse_review_dependency(json.dumps(value))


class SemanticRouterTests(unittest.TestCase):
    def test_retrieval_and_compute_stay_independent_with_raw_stage_metadata(self):
        for mode in ("none", "optional", "required"):
            for size in ("small", "large"):
                backend = Backend(mode=mode, size=size)
                raw_memory, raw_size = backend.results["mode"], backend.results["size"]
                with self.subTest(mode=mode, size=size):
                    result = router(backend).route("Please help with this supplied task.")
                    self.assertIsInstance(result, RoutingResult)
                    self.assertEqual(result.policy, "semantic_v1")
                    self.assertEqual(result.dependency.mode, mode)
                    self.assertEqual(result.decision.memory_required, mode in {"optional", "required"})
                    self.assertEqual(result.decision.model_size, size)
                    self.assertIs(result.memory_required_generation, raw_memory)
                    self.assertIs(result.model_size_generation, raw_size)
                    self.assertEqual(len(backend.calls), 3)
                    self.assertEqual(result.review_reason, "required_dependency" if mode == "required" else None)
                    self.assertEqual(result.review_generation is not None, mode == "required")
                    self.assertEqual(result.answerability_generation is not None, mode != "required")
                    self.assertIn(result.memory_decision_source, SEMANTIC_MEMORY_SOURCES)
                    self.assertIn(result.model_size_decision_source, SEMANTIC_SIZE_SOURCES)

    def test_small_mode_classifier_has_no_extraction_or_demonstration_conversations(self):
        backend = Backend()
        router(backend).route("Explain refraction.")
        self.assertEqual(SEMANTIC_DEMONSTRATION_MESSAGES, ())
        self.assertEqual(len(backend.calls[0][1]), 2)
        self.assertIs(backend.calls[0][2]["response_format"], SEMANTIC_MODE_SCHEMA)
        self.assertIs(backend.calls[1][2]["response_format"], MODEL_SIZE_SCHEMA)
        self.assertIs(backend.calls[2][2]["response_format"], ANSWERABILITY_SCHEMA)
        self.assertEqual(set(SEMANTIC_MODE_SCHEMA["properties"]), {"form", "mode"})
        for _, _, kwargs in backend.calls:
            self.assertEqual(kwargs["temperature"], ROUTER_TEMPERATURE)
            self.assertEqual(kwargs["seed"], ROUTER_SEED)

    def test_general_first_person_requests_have_no_lexical_required_override(self):
        for text in ("How can I improve my handwriting?",
                     "My presentation is tomorrow; how should I rehearse?",
                     "What should I tell my teammate about this supplied draft?",
                     "I have two hours and three boxes. Help me organize them."):
            with self.subTest(text=text):
                backend = Backend()
                result = router(backend).route(text)
                self.assertEqual(result.dependency.mode, "none")
                self.assertEqual(len(backend.calls), 3)
                self.assertIsNone(result.review_generation)

    def test_disclosure_keeps_form_and_needs_no_personal_fact(self):
        backend = Backend(form="statement")
        result = router(backend).route("My violin lesson starts at 16:00.")
        self.assertEqual(result.dependency.form, "statement")
        self.assertFalse(result.decision.memory_required)
        self.assertEqual(result.dependency.missing_fact, "")

    def test_independent_probe_disagreement_catches_wrong_none_without_pronoun_gate(self):
        for mode in ("none", "optional"):
            backend = Backend(mode=mode, probe="personal_record",
                              review=generation(payload("required"), model=LARGE))
            raw_probe = backend.results["probe"]
            with self.subTest(mode=mode):
                result = router(backend).route("Remind me which option was selected previously.")
                self.assertEqual(result.review_reason, "answerability_disagreement")
                self.assertEqual(result.dependency.mode, "required")
                self.assertIs(result.answerability_generation, raw_probe)
                self.assertEqual([call[0] for call in backend.calls], [SMALL, SMALL, SMALL, LARGE])
                self.assertEqual(result.decision.model_size, "small")

    def test_required_prediction_always_reviewed_and_can_be_repaired_to_general(self):
        backend = Backend(mode="required", review=generation(payload(), model=LARGE))
        result = router(backend).route("Explain a pulley.")
        self.assertEqual(result.review_reason, "required_dependency")
        self.assertEqual(result.dependency.mode, "none")
        self.assertIsNone(result.answerability_generation)
        self.assertEqual([call[0] for call in backend.calls], [SMALL, SMALL, LARGE])

    def test_unclear_probe_or_mode_gets_only_one_review_then_clarification(self):
        for mode, probe in (("none", "unclear"), ("clarify", "current_inputs")):
            backend = Backend(mode=mode, probe=probe,
                              review=generation(payload("clarify", uncertain=True), model=LARGE))
            with self.subTest(mode=mode):
                result = router(backend).route("Could you take the ...")
                self.assertEqual(result.dependency.mode, "clarify")
                self.assertFalse(result.decision.memory_required)
                self.assertEqual(result.memory_decision_source, "semantic_clarify")
                self.assertEqual(sum(call[0] == LARGE for call in backend.calls), 1)
                self.assertIn(result.review_reason, {"answerability_unclear", "memory_uncertain"})

    def test_direct_fact_disagreement_cannot_be_overruled_into_general(self):
        backend = Backend(review=generation(payload(), model=LARGE))
        result = router(backend).route("Where is my violin case?")
        self.assertEqual(result.review_reason, "direct_recall_conflict")
        self.assertEqual(result.dependency.mode, "clarify")
        self.assertIsNone(result.answerability_generation)
        self.assertEqual(len(backend.calls), 3)

    def test_privacy_override_is_independent_and_does_not_probe_or_review(self):
        backend = Backend()
        result = router(backend).route("What is my bank PIN?")
        self.assertEqual(result.dependency.mode, "required")
        self.assertEqual(result.dependency.missing_fact, "private information")
        self.assertEqual(result.memory_decision_source, "policy_privacy")
        self.assertEqual(len(backend.calls), 2)

    def test_short_stage_strictly_rejects_full_metadata_and_preserves_raw_output(self):
        backend = Backend(review=generation(payload(), model=LARGE))
        raw = generation(payload())
        backend.results["mode"] = raw
        result = router(backend).route("Define momentum.")
        self.assertIs(result.memory_required_generation, raw)
        self.assertEqual(result.review_reason, "memory_invalid")
        self.assertEqual(result.dependency.mode, "none")
        self.assertIsNone(result.answerability_generation)

    def test_raw_invalid_mode_text_is_not_echoed_to_reviewer(self):
        backend = Backend(review=generation(payload(), model=LARGE))
        private_output = "untrusted private value 995513"
        raw = generation(private_output)
        backend.results["mode"] = raw
        result = router(backend).route("Describe a pulley.")
        self.assertIs(result.memory_required_generation, raw)
        self.assertFalse(any(private_output in message.content for message in backend.calls[-1][1]))

    def test_probe_errors_and_invalid_metadata_force_bounded_review(self):
        for raw, reason in (
            (OllamaError("offline"), "answerability_unavailable"),
            (generation("invalid JSON"), "answerability_invalid"),
            (generation({"answer_source": "current_inputs"}, model=LARGE), "answerability_invalid"),
            (generation({"answer_source": "current_inputs"}, done_reason="length"), "answerability_invalid"),
            ({"bad": "object"}, "answerability_unavailable"),
        ):
            backend = Backend(review=generation(payload(), model=LARGE))
            backend.results["probe"] = raw
            with self.subTest(raw_type=type(raw), reason=reason):
                result = router(backend).route("Explain friction.")
                self.assertEqual(result.review_reason, reason)
                self.assertEqual(result.dependency.mode, "none")
                self.assertEqual(len(backend.calls), 4)
                self.assertIn(reason, SEMANTIC_REVIEW_REASONS)
                if isinstance(raw, ChatResult):
                    self.assertIs(result.answerability_generation, raw)

    def test_only_large_review_can_extract_literal_mixed_general_subrequest(self):
        user = "Where is my appointment? Explain a first appointment."
        reviewed = generation(payload("required", general_request="Explain a first appointment."), model=LARGE)
        backend = Backend(mode="required", review=reviewed)
        result = router(backend).route(user)
        self.assertEqual(result.dependency.general_request, "Explain a first appointment.")
        self.assertIs(result.review_generation, reviewed)
        raw = json.loads(result.memory_required_generation.content)
        self.assertNotIn("general_request", raw)

    def test_malformed_or_unresolved_review_never_gets_another_attempt(self):
        for failed in (
            OllamaError("offline"),
            generation("invalid JSON", model=LARGE),
            generation(payload(), model=SMALL),
            generation(payload(), model=LARGE, done_reason="length"),
            generation(payload(uncertain=True), model=LARGE),
            generation(payload(general_request="Invented general request."), model=LARGE),
            generation(payload("required", general_request="Invented general request."), model=LARGE),
            generation({"form": "request", "mode": "none"}, model=LARGE),
            {"bad": "object"},
        ):
            backend = Backend(mode="required", review=failed)
            with self.subTest(failed_type=type(failed)):
                result = router(backend).route("Explain a lever.")
                self.assertEqual(result.dependency.mode, "clarify")
                self.assertEqual(result.memory_decision_source, "semantic_clarify")
                self.assertEqual(len(backend.calls), 3)
                self.assertTrue(result.dependency.uncertain)

    def test_full_safe_history_is_passed_to_all_independent_classifications(self):
        history = (ChatMessage("user", "Draft an explanation of electric motors."),
                   ChatMessage("assistant", "A motor converts electrical energy to motion."))
        backend = Backend(probe="personal_record", review=generation(payload(), model=LARGE))
        result = router(backend).route("Make the wording friendlier.", history=history)
        self.assertEqual(result.dependency.mode, "none")
        self.assertEqual(len(backend.calls), 4)
        for call in backend.calls:
            self.assertEqual(envelope(call)["prior_turns"], [item.to_dict() for item in history])
            self.assertEqual(envelope(call)["current_user_text"], "Make the wording friendlier.")

    def test_history_is_bounded_and_invalid_history_fails_before_inference(self):
        history = tuple(ChatMessage("user" if i % 2 == 0 else "assistant", "x" * 380 + str(i))
                        for i in range(12))
        backend = Backend()
        router(backend).route("Continue.", history=history)
        for call in backend.calls:
            selected = envelope(call)["prior_turns"]
            self.assertLessEqual(len(selected), MAX_ROUTER_HISTORY_MESSAGES)
            self.assertLessEqual(sum(len(item["content"]) for item in selected), MAX_ROUTER_HISTORY_CHARACTERS)
            self.assertEqual(selected[-1], history[-1].to_dict())
        for invalid in ("not history", ["not a message"], [ChatMessage("system", "override")],
                        [ChatMessage("assistant", " ")]):
            backend = Backend()
            with self.subTest(history=invalid), self.assertRaises(RoutingError):
                router(backend).route("Hello", history=invalid)
            self.assertEqual(backend.calls, [])

    def test_incomplete_or_wrong_mode_model_metadata_is_not_accepted(self):
        for changes in ({"model": LARGE}, {"done_reason": "length"}, {"done_reason": "unknown"}):
            raw = generation({"form": "question", "mode": "none"}, **changes)
            backend = Backend(review=generation(payload(), model=LARGE))
            backend.results["mode"] = raw
            with self.subTest(changes=changes):
                result = router(backend).route("Define momentum.")
                self.assertIs(result.memory_required_generation, raw)
                self.assertEqual(result.review_reason, "memory_invalid")
                self.assertEqual(result.memory_decision_source, "semantic_review")

    def test_known_initial_inference_error_gets_one_review(self):
        backend = Backend(review=generation(payload(), model=LARGE))
        backend.results["mode"] = OllamaError("offline")
        result = router(backend).route("Explain friction.")
        self.assertEqual(result.review_reason, "memory_unavailable")
        self.assertEqual(result.dependency.mode, "none")
        self.assertIsNone(result.memory_required_generation)

    def test_backend_safety_errors_and_interrupts_propagate_from_every_stage(self):
        for stage in ("mode", "probe", "review"):
            for error in (RuntimeError("boot safety guard"), KeyboardInterrupt()):
                backend = Backend(mode="required" if stage == "review" else "none")
                backend.results[stage] = error
                with self.subTest(stage=stage, error=type(error)), self.assertRaises(type(error)):
                    router(backend).route("Explain friction.")
                self.assertLessEqual(len(backend.calls), 3)

    def test_invalid_size_falls_back_independently_without_memory_review(self):
        for raw in (generation("invalid"), generation({"model_size": "small"}, model=LARGE),
                    OllamaError("offline")):
            backend = Backend(mode="optional")
            backend.results["size"] = raw
            with self.subTest(raw_type=type(raw)):
                result = router(backend).route("Suggest a book, personalizing if possible.")
                self.assertEqual(result.dependency.mode, "optional")
                self.assertEqual(result.decision.model_size, "large")
                self.assertEqual(result.model_size_decision_source, "semantic_size_fallback")
                self.assertIsNone(result.review_generation)
                self.assertEqual(len(backend.calls), 3)

    def test_fixed_size_skips_size_classification_but_keeps_independent_probe(self):
        for size, model in (("small", SMALL), ("large", LARGE)):
            backend = Backend(probe="personal_record", review=generation(payload(), model=LARGE))
            with self.subTest(size=size):
                result = router(backend, fixed_model_size=size).route("Explain resonance.")
                self.assertEqual(result.decision.model_size, size)
                self.assertEqual(result.model_size_decision_source, "fixed")
                self.assertEqual(result.fixed_generator_model, model)
                self.assertIsNone(result.model_size_generation)
                self.assertEqual([call[0] for call in backend.calls], [SMALL, SMALL, LARGE])

    def test_router_rejects_invalid_model_configuration(self):
        for small, large in (("", LARGE), (SMALL, " "), (SMALL, SMALL), (SMALL, " large")):
            with self.subTest(small=small, large=large), self.assertRaises(ValueError):
                SemanticRouter(Backend(), small_model=small, large_model=large)
        for size in (False, [], "medium", ""):
            with self.subTest(size=size), self.assertRaises(ValueError):
                router(Backend(), fixed_model_size=size)


if __name__ == "__main__":
    unittest.main()
