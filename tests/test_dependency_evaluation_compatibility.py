"""Record real dependency reviews without converting them to legacy routes."""

from copy import deepcopy
import unittest
from unittest.mock import Mock

from oline_hri.dependency_review import DEPENDENCY_REVIEW_SCHEMA
from oline_hri.evaluation_experiment import (
    _AttemptBackend, _chat_purpose as experiment_purpose,
)
from oline_hri.evaluation_runner import (
    EvaluationRunError, _EvaluationBackend, _chat_purpose as runner_purpose,
    _schema_supplied_ids,
)
from oline_hri.evaluation_scoring import (
    EvaluationScoringError, _backend_calls, _route_generation_value,
)
from oline_hri.ollama import ChatResult


class DependencyEvaluationCompatibilityTests(unittest.TestCase):
    def test_exact_boolean_review_has_a_distinct_purpose_and_no_memory_allowlist(self):
        schema = deepcopy(DEPENDENCY_REVIEW_SCHEMA)
        for purpose in (runner_purpose, experiment_purpose):
            self.assertEqual(purpose(schema), "route_dependency_review")
        self.assertIsNone(_schema_supplied_ids(schema, purpose=runner_purpose(schema)))
        self.assertEqual(schema, DEPENDENCY_REVIEW_SCHEMA)

    def test_review_recognition_rejects_weakened_or_extended_contracts(self):
        for mutation in ("optional", "extra", "loose", "wrong_type", "one_of"):
            with self.subTest(mutation=mutation):
                schema = deepcopy(DEPENDENCY_REVIEW_SCHEMA)
                if mutation == "optional":
                    schema["required"] = []
                elif mutation == "extra":
                    schema["properties"]["mode"] = {"type": "string"}
                elif mutation == "loose":
                    schema["additionalProperties"] = True
                elif mutation == "wrong_type":
                    schema["properties"]["needs_personal_facts"] = {"type": "string"}
                else:
                    schema["oneOf"] = []
                with self.assertRaises(EvaluationRunError):
                    runner_purpose(schema)
                self.assertEqual(experiment_purpose(schema), "unknown")

    def test_both_backend_recorders_preserve_actual_review_even_when_json_is_invalid(self):
        for raw in ('{\n  "needs_personal_facts": false\n}', "malformed fixture response"):
            for kind in ("runner", "experiment"):
                with self.subTest(raw=raw, kind=kind):
                    result = ChatResult("qwen3:1.7b", raw, "stop", 2_000_000, 100_000,
                                        20, 8, 1_000_000, prompt_eval_duration_ns=500_000)
                    delegate = Mock()
                    delegate.chat.return_value = result
                    clock = iter(range(100)).__next__
                    recorder = (_EvaluationBackend(delegate, clock) if kind == "runner" else
                                _AttemptBackend(delegate, temperature=0.8, seed=123, clock_ns=clock))
                    self.assertIs(recorder.chat(
                        result.model, (), response_format=deepcopy(DEPENDENCY_REVIEW_SCHEMA),
                        temperature=0.0, seed=42,
                    ), result)
                    calls = recorder.calls_since(0) if kind == "runner" else recorder.calls
                    self.assertEqual(len(calls), 1)
                    call = calls[0]
                    self.assertEqual(call["purpose"], "route_dependency_review")
                    self.assertEqual(call["generation"]["content"], raw)
                    self.assertEqual(call["generation"]["model"], result.model)
                    self.assertEqual(call["generation"]["total_duration_ns"], 2_000_000)
                    self.assertEqual(call["generation"]["prompt_eval_duration_ns"], 500_000)
                    self.assertEqual((call["temperature"], call["seed"]), (0.0, 42))
                    self.assertEqual(delegate.chat.call_args.kwargs["temperature"], 0.0)
                    self.assertEqual(delegate.chat.call_args.kwargs["seed"], 42)
                    if kind == "runner":
                        self.assertIsNone(call["supplied_ids"])

    def test_legacy_observation_reader_cannot_misreport_review_as_a_classifier(self):
        # The versioned reliability runner stores dependency_v1 in full. This
        # older reader instead promises two small Boolean/size classifications;
        # silently admitting a review would invent that historical provenance.
        from test_semantic_evaluation_compatibility import generation

        raw = generation({"needs_personal_facts": False})
        raw["model"] = "qwen3:1.7b"
        with self.assertRaises(EvaluationScoringError):
            _route_generation_value(raw, "memory_required")
        with self.assertRaises(EvaluationScoringError):
            _backend_calls([{
                "purpose": "route_dependency_review", "model": raw["model"],
                "wall_ns": 1, "status": "ok", "error_type": None, "generation": raw,
            }])


if __name__ == "__main__":
    unittest.main()
