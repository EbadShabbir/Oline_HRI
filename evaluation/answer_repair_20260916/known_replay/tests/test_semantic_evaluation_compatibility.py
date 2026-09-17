"""Semantic classification compatibility without rewriting historical audits."""

from copy import deepcopy
import json
import unittest
from unittest.mock import Mock

from oline_hri.evaluation_experiment import (
    _AttemptBackend,
    _chat_purpose as experiment_purpose,
)
from oline_hri.evaluation_runner import (
    EvaluationRunError,
    _EvaluationBackend,
    _chat_purpose as runner_purpose,
    _schema_supplied_ids,
)
from oline_hri.evaluation_scoring import (
    EvaluationScoringError,
    _backend_calls,
    _route,
    _route_generation_value,
)
from oline_hri.ollama import ChatResult
from oline_hri.response import ROBOT_RESPONSE_SCHEMA
from oline_hri.routing import MEMORY_REQUIRED_SCHEMA, MODEL_SIZE_SCHEMA
from oline_hri.semantic_routing import (
    ANSWERABILITY_SCHEMA, SEMANTIC_MEMORY_SCHEMA, SEMANTIC_MODE_SCHEMA,
    SEMANTIC_REVIEW_SCHEMA,
)


def semantic_payload(mode="none", **changes):
    payload = {
        "form": "request",
        "mode": mode,
        "missing_fact": (
            "request context" if mode == "clarify" else
            "personal preference" if mode in {"optional", "required"} else ""
        ),
        "general_request": "",
        "uncertain": False,
    }
    return {**payload, **changes}


def generation(payload):
    return {
        "model": "qwen3:0.6b",
        "content": payload if isinstance(payload, str) else json.dumps(payload),
        "done_reason": "stop",
        "total_duration_ns": 2_000_000,
        "load_duration_ns": 100_000,
        "prompt_eval_count": 20,
        "prompt_eval_duration_ns": 500_000,
        "eval_count": 10,
        "eval_duration_ns": 1_000_000,
        "generation_tokens_per_second": 10_000.0,
    }


def route_record(mode):
    return {
        "source": "model",
        "memory_required": mode in {"optional", "required"},
        "model_size": "small",
        "wall_ns": 500_000,
        "memory_required_generation": generation(semantic_payload(mode)),
        "model_size_generation": generation({"model_size": "small"}),
    }


class SemanticEvaluationCompatibilityTests(unittest.TestCase):
    def test_call_purpose_recognizes_semantic_and_preserves_existing_schemas(self):
        historical = {
            "type": "object",
            "properties": {"memory_required": {"type": "boolean"}},
            "required": ["memory_required"],
            "additionalProperties": False,
        }
        for schema, expected in (
            (historical, "route_memory_required"),
            (MEMORY_REQUIRED_SCHEMA, "route_memory_required"),
            (SEMANTIC_MODE_SCHEMA, "route_memory_required"),
            (SEMANTIC_MEMORY_SCHEMA, "route_memory_required"),
            (SEMANTIC_REVIEW_SCHEMA, "route_memory_required"),
            (ANSWERABILITY_SCHEMA, "route_answerability"),
            (MODEL_SIZE_SCHEMA, "route_model_size"),
            (ROBOT_RESPONSE_SCHEMA, "generation"),
        ):
            with self.subTest(expected=expected, schema=schema):
                copy = deepcopy(schema)
                self.assertEqual(runner_purpose(copy), expected)
                self.assertEqual(experiment_purpose(copy), expected)
                self.assertEqual(copy, schema)

    def test_semantic_purpose_requires_the_complete_schema_contract(self):
        invalid = []
        missing_field = deepcopy(SEMANTIC_MEMORY_SCHEMA)
        del missing_field["properties"]["uncertain"]
        invalid.append(missing_field)
        weakened = deepcopy(SEMANTIC_MEMORY_SCHEMA)
        weakened["required"] = []
        invalid.append(weakened)
        extended = deepcopy(SEMANTIC_MEMORY_SCHEMA)
        extended["properties"]["memory_required"] = {"type": "boolean"}
        invalid.append(extended)
        loose = deepcopy(SEMANTIC_MEMORY_SCHEMA)
        loose["additionalProperties"] = True
        invalid.append(loose)
        for schema in (*invalid, None, {}, {"properties": []}):
            with self.subTest(schema=schema):
                with self.assertRaises(EvaluationRunError):
                    runner_purpose(schema)
                self.assertEqual(experiment_purpose(schema), "unknown")

    def test_compact_stage_schemas_are_recognized_only_with_their_exact_contract(self):
        for original in (SEMANTIC_MODE_SCHEMA, ANSWERABILITY_SCHEMA):
            for mutation in ("optional", "extra", "loose", "different_enum"):
                with self.subTest(schema=original, mutation=mutation):
                    schema = deepcopy(original)
                    if mutation == "optional":
                        schema["required"] = []
                    elif mutation == "extra":
                        schema["properties"]["unexpected"] = {"type": "string"}
                    elif mutation == "loose":
                        schema["additionalProperties"] = True
                    else:
                        field = "mode" if "mode" in schema["properties"] else "answer_source"
                        schema["properties"][field]["enum"] = ["unexpected"]
                    with self.assertRaises(EvaluationRunError):
                        runner_purpose(schema)
                    self.assertEqual(experiment_purpose(schema), "unknown")

    def test_discriminated_review_purpose_requires_all_exact_branches(self):
        self.assertIsNone(_schema_supplied_ids(
            SEMANTIC_REVIEW_SCHEMA, purpose=runner_purpose(SEMANTIC_REVIEW_SCHEMA),
        ))
        for mutation in ("missing_branch", "changed_const", "loose_branch", "top_level_properties"):
            with self.subTest(mutation=mutation):
                schema = deepcopy(SEMANTIC_REVIEW_SCHEMA)
                if mutation == "missing_branch":
                    schema["oneOf"].pop()
                elif mutation == "changed_const":
                    schema["oneOf"][0]["properties"]["mode"] = {"const": "required"}
                elif mutation == "loose_branch":
                    schema["oneOf"][0]["additionalProperties"] = True
                else:
                    schema["properties"] = {"memory_required": {"type": "boolean"}}
                with self.assertRaises(EvaluationRunError):
                    runner_purpose(schema)
                self.assertEqual(experiment_purpose(schema), "unknown")

    def test_semantic_compatibility_boolean_records_retrieval_not_answerability(self):
        for mode, expected in (
            ("none", False), ("optional", True),
            ("required", True), ("clarify", False),
        ):
            with self.subTest(mode=mode):
                raw = generation(semantic_payload(mode))
                original = deepcopy(raw)
                self.assertIs(_route_generation_value(raw, "memory_required"), expected)
                self.assertEqual(raw, original)

    def test_compact_mode_raw_decision_has_only_a_retrieval_compatibility_view(self):
        for mode in ("none", "optional", "required", "clarify"):
            with self.subTest(mode=mode):
                raw = generation(json.dumps({"form": "request", "mode": mode}, indent=2))
                original = deepcopy(raw)
                self.assertIs(_route_generation_value(raw, "memory_required"), mode in {"optional", "required"})
                self.assertEqual(raw, original)
                record = route_record(mode)
                record["memory_required_generation"] = raw
                self.assertEqual(_route(record, "adaptive"), record)

    def test_compact_parser_rejects_invalid_or_extended_stage_payloads(self):
        private = "private fixture value"
        for payload in (
            {"form": "request", "mode": private},
            {"form": private, "mode": "none"},
            {"form": "statement", "mode": "required"},
            {"form": "statement", "mode": "optional"},
            {"form": "request", "mode": "required", "answer_source": "current_inputs"},
            {"form": "request", "mode": "required", "missing_fact": "personal context"},
            {"mode": "none"},
            '{"form":"request","mode":"none","mode":"required"}',
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(EvaluationScoringError) as caught:
                    _route_generation_value(generation(payload), "memory_required")
                self.assertNotIn(private, str(caught.exception))

    def test_answerability_probe_never_becomes_a_boolean_or_legacy_route_stage(self):
        self.assertIsNone(_schema_supplied_ids(ANSWERABILITY_SCHEMA, purpose="route_answerability"))
        for answer_source in ("current_inputs", "personal_record", "unclear"):
            with self.subTest(answer_source=answer_source):
                raw = generation({"answer_source": answer_source})
                with self.assertRaises(EvaluationScoringError):
                    _route_generation_value(raw, "memory_required")
                with self.assertRaises(EvaluationScoringError):
                    _backend_calls([{
                        "purpose": "route_answerability", "model": "qwen3:0.6b",
                        "wall_ns": 1, "status": "ok", "error_type": None, "generation": raw,
                    }])

    def test_backend_recorders_preserve_independent_raw_probe_and_sampling(self):
        raw = '{\n  "answer_source": "current_inputs"\n}'
        result = ChatResult("qwen3:0.6b", raw, "stop", 2_000_000, 100_000, 20, 10, 1_000_000,
                            prompt_eval_duration_ns=500_000)
        for recorder_type in ("runner", "experiment"):
            with self.subTest(recorder=recorder_type):
                delegate = Mock()
                delegate.chat.return_value = result
                clock = iter(range(100)).__next__
                if recorder_type == "runner":
                    recorder = _EvaluationBackend(delegate, clock)
                else:
                    recorder = _AttemptBackend(delegate, temperature=0.8, seed=123, clock_ns=clock)
                self.assertIs(recorder.chat(
                    "qwen3:0.6b", (), response_format=ANSWERABILITY_SCHEMA,
                    temperature=0.0, seed=42,
                ), result)
                calls = recorder.calls_since(0) if recorder_type == "runner" else recorder.calls
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0]["purpose"], "route_answerability")
                self.assertEqual(calls[0]["generation"]["content"], raw)
                self.assertEqual((calls[0]["temperature"], calls[0]["seed"]), (0.0, 42))
                self.assertEqual(delegate.chat.call_args.kwargs["temperature"], 0.0)
                self.assertEqual(delegate.chat.call_args.kwargs["seed"], 42)
                if recorder_type == "runner":
                    self.assertIsNone(calls[0]["supplied_ids"])

    def test_historical_boolean_and_form_payloads_remain_exactly_as_recorded(self):
        for expected in (False, True):
            for form in (None, "statement", "question", "request"):
                with self.subTest(expected=expected, form=form):
                    payload = {"memory_required": expected}
                    if form is not None:
                        payload["form"] = form
                    raw = generation(json.dumps(payload, indent=2) + "\n")
                    original = deepcopy(raw)
                    self.assertIs(_route_generation_value(raw, "memory_required"), expected)
                    self.assertEqual(raw, original)
        self.assertEqual(
            _route_generation_value(generation({"model_size": "large"}), "model_size"),
            "large",
        )

    def test_invalid_semantic_metadata_is_rejected_without_echoing_values(self):
        private = "private fixture value"
        invalid = [
            semantic_payload(mode=private),
            semantic_payload(form=private),
            semantic_payload("required", missing_fact=private),
            semantic_payload("required", missing_fact=""),
            semantic_payload("clarify", missing_fact="personal schedule"),
            semantic_payload("none", missing_fact="personal preference"),
            semantic_payload("optional", form="statement"),
            semantic_payload(uncertain="false"),
            semantic_payload(uncertain=1),
            semantic_payload("none", general_request=private),
            semantic_payload("required", general_request=private * 200),
            semantic_payload("required", memory_required=True),
        ]
        missing = semantic_payload()
        del missing["uncertain"]
        invalid.append(missing)
        duplicate = json.dumps(semantic_payload()).replace(
            '"mode": "none"', '"mode": "none", "mode": "required"'
        )
        nonstandard = json.dumps(semantic_payload()).replace(
            '"uncertain": false', '"uncertain": NaN'
        )
        for payload in (*invalid, duplicate, nonstandard):
            with self.subTest(payload=payload):
                with self.assertRaises(EvaluationScoringError) as caught:
                    _route_generation_value(generation(payload), "memory_required")
                self.assertNotIn(private, str(caught.exception))

    def test_semantic_payload_does_not_change_historical_model_size_contract(self):
        with self.assertRaises(EvaluationScoringError):
            _route_generation_value(generation(semantic_payload()), "model_size")
        for payload in (
            {"memory_required": 1},
            {"form": "invalid", "memory_required": True},
            {"memory_required": True, "extra": "unexpected"},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(EvaluationScoringError):
                    _route_generation_value(generation(payload), "memory_required")

    def test_route_reader_preserves_raw_semantic_payload_and_detects_mismatch(self):
        for mode in ("none", "optional", "required", "clarify"):
            with self.subTest(mode=mode):
                record = route_record(mode)
                original = deepcopy(record)
                self.assertEqual(_route(record, "adaptive"), original)
                self.assertEqual(record, original)
                record["memory_required"] = not record["memory_required"]
                with self.assertRaisesRegex(EvaluationScoringError, "contradicts"):
                    _route(record, "adaptive")

    def test_legacy_route_reader_does_not_absorb_versioned_review_semantics(self):
        record = route_record("none")
        record["source"] = "hybrid"
        record["decision_sources"] = {
            "memory_required": "semantic_review", "model_size": "model"
        }
        with self.assertRaises(EvaluationScoringError):
            _route(record, "adaptive")
        record = route_record("none")
        record["review_generation"] = generation(semantic_payload("required"))
        with self.assertRaises(EvaluationScoringError):
            _route(record, "adaptive")
        record = route_record("none")
        record["answerability_generation"] = generation({"answer_source": "current_inputs"})
        with self.assertRaises(EvaluationScoringError):
            _route(record, "adaptive")


if __name__ == "__main__":
    unittest.main()
