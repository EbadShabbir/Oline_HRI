"""Typed generations preserve raw calls without gaining personal authority."""
from copy import deepcopy
import json
import unittest
from unittest.mock import Mock

from oline_hri.evaluation_experiment import _AttemptBackend, _chat_purpose as experiment_purpose
from oline_hri.evaluation_runner import (
    EvaluationRunError, _EvaluationBackend, _chat_purpose as runner_purpose, _schema_supplied_ids,
)
from oline_hri.evaluation_scoring import EvaluationScoringError, _backend_calls, _cascade
from oline_hri.human_guidance import guidance_schema
from oline_hri.ollama import ChatResult
from oline_hri.task_parts import TaskLayout, parts_schema
from test_evaluation_scoring import _raw_records


def transformed_record(parts, speech, transform="task_parts_v1"):
    record = deepcopy(next(row["cascade"] for row in _raw_records()
                           if row.get("record_type") == "case" and not row["cascade"]["retrieval_invoked"]))
    field = "answer_parts" if transform == "task_parts_v1" else "steps_for_user"
    record["response_transform"] = transform
    record["response"] = {"speech": speech, "gesture_id": "NO_ACTION", "memory_used": []}
    record["generation"]["content"] = json.dumps({field: parts})
    for call in record["backend_calls"]:
        if call["purpose"] == "generation":
            call["generation"] = deepcopy(record["generation"])
    return record


class TypedEvaluationCompatibilityTests(unittest.TestCase):
    def test_closed_parts_and_guidance_have_an_explicit_empty_memory_allowlist(self):
        schemas = [parts_schema(TaskLayout("lines", 3)), parts_schema(TaskLayout("csv")),
                   guidance_schema(), guidance_schema(allocation_minutes=4),
                   guidance_schema(allocation_minutes=7, step_count=3)]
        for schema in schemas:
            with self.subTest(schema=schema):
                self.assertEqual(runner_purpose(schema), "generation")
                self.assertEqual(experiment_purpose(schema), "generation")
                self.assertEqual(_schema_supplied_ids(schema, purpose="generation"), ())

    def test_looser_or_authority_bearing_parts_schemas_remain_rejected(self):
        for mutation in ("extra_field", "loose", "optional", "long_strings", "wrong_count", "boolean_count"):
            schema = parts_schema(TaskLayout("lines", 3))
            if mutation == "extra_field":
                schema["properties"]["memory_used"] = {"type": "array"}
            elif mutation == "loose":
                schema["additionalProperties"] = True
            elif mutation == "optional":
                schema["required"] = []
            elif mutation == "long_strings":
                schema["properties"]["answer_parts"]["items"]["maxLength"] = 1000
            elif mutation == "wrong_count":
                schema["properties"]["answer_parts"]["maxItems"] = 5
            else:
                schema["properties"]["answer_parts"].update(minItems=True, maxItems=True)
            with self.subTest(mutation=mutation):
                with self.assertRaises(EvaluationRunError):
                    runner_purpose(schema)
                self.assertEqual(experiment_purpose(schema), "unknown")
                with self.assertRaises(EvaluationRunError):
                    _schema_supplied_ids(schema, purpose="generation")

    def test_recorders_keep_original_typed_json_and_existing_sampling_contract(self):
        for kind in ("runner", "experiment"):
            result = ChatResult("qwen3:1.7b", '{"answer_parts":["One.","Two."]}', "stop",
                                2_000_000, 100_000, 20, 8, 1_000_000)
            delegate = Mock()
            delegate.chat.return_value = result
            recorder = (_EvaluationBackend(delegate, iter(range(100)).__next__) if kind == "runner" else
                        _AttemptBackend(delegate, temperature=0.8, seed=123, clock_ns=iter(range(100)).__next__))
            schema = parts_schema(TaskLayout("sentences", 2))
            self.assertIs(recorder.chat(result.model, (), response_format=schema), result)
            calls = recorder.calls_since(0) if kind == "runner" else recorder.calls
            self.assertEqual(calls[0]["purpose"], "generation")
            self.assertEqual(calls[0]["generation"]["content"], result.content)
            self.assertEqual(delegate.chat.call_args.kwargs["response_format"], schema)
            if kind == "runner":
                self.assertEqual(calls[0]["supplied_ids"], ())
            else:
                self.assertEqual((calls[0]["temperature"], calls[0]["seed"]), (0.8, 123))

    def test_typed_transform_keeps_multiline_text_and_original_generation(self):
        record = transformed_record(["Rain falls", "Leaves shine"], "Rain falls\nLeaves shine")
        parsed = _cascade(record)
        self.assertEqual(parsed["response"]["speech"], "Rain falls\nLeaves shine")
        self.assertEqual(parsed["generation"]["content"], record["generation"]["content"])
        self.assertEqual(parsed["supplied_ids"], ())
        legacy = deepcopy(record)
        legacy.pop("response_transform")
        with self.assertRaises(EvaluationScoringError):
            _cascade(legacy)
        for transform in ("human_guidance_steps", "human_guidance_allocations"):
            guided = transformed_record(["Sort the papers.", "Stack the papers."],
                                        "1. Sort the papers.\n2. Stack the papers.", transform)
            self.assertEqual(_cascade(guided)["response_transform"], transform)

    def test_typed_transform_cannot_add_memory_authority_or_unrecorded_text(self):
        good = transformed_record(["Rain falls", "Leaves shine"], "Rain falls\nLeaves shine")
        for mutation in ("memory", "supplied", "privacy", "new_text", "new_raw_field", "unrecorded", "control"):
            record = deepcopy(good)
            if mutation == "memory":
                record["response"]["memory_used"] = ["mem_" + "0" * 32]
            elif mutation == "supplied":
                record["supplied_ids"] = ["mem_" + "0" * 32]
            elif mutation == "privacy":
                record["privacy_gate"] = True
            elif mutation == "new_text":
                record["response"]["speech"] = "Rain falls\nYour usual tree is oak."
            elif mutation == "new_raw_field":
                record["generation"]["content"] = '{"answer_parts":["Rain falls"],"memory_used":[]}'
            elif mutation == "unrecorded":
                record["backend_calls"] = []
            else:
                record["response"]["speech"] = "Rain falls\rLeaves shine"
            with self.subTest(mutation=mutation), self.assertRaises(EvaluationScoringError):
                _cascade(record)

    def test_legacy_four_call_bound_is_not_relaxed_for_typed_generation(self):
        record = transformed_record(["Rain falls"], "Rain falls")
        generation = next(call for call in record["backend_calls"] if call["purpose"] == "generation")
        with self.assertRaises(EvaluationScoringError):
            _backend_calls([deepcopy(generation) for _ in range(5)])


if __name__ == "__main__":
    unittest.main()
