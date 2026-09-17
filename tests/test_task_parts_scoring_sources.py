"""Source-derived formatting has to preserve raw text and the suite prompt."""

from copy import deepcopy
import json
import unittest
from unittest.mock import Mock

from oline_hri.evaluation import load_evaluation_suite
from oline_hri.evaluation_runner import EvaluationRunError, _EvaluationBackend, _chat_purpose, _schema_supplied_ids
from oline_hri.evaluation_scoring import (
    EvaluationScoringError, _cascade, parse_observation_jsonl, score_observations,
)
from oline_hri.ollama import ChatMessage, ChatResult
from oline_hri.task_parts import TaskLayout, parts_schema
from test_evaluation_scoring import _raw_records
from test_typed_evaluation_compatibility import transformed_record


class TaskPartsSourceScoringTests(unittest.TestCase):
    def test_calculation_result_is_independently_derived_from_supplied_operands(self):
        for request, expression, answer in (
            ("Multiply seven by four, then add three. Return only the integer.", "7*4+3", "31"),
            ("Calculate (12+8)/4. Return only the integer.", "(12+8)/4", "5"),
            ("Compute ten divided by three then multiplied by three. Return only the integer.", "(10/3)*3", "10"),
            ("Subtract seven from one hundred and twenty-three. Return only the integer.", "123-7", "116"),
        ):
            record = transformed_record([expression], answer)
            record["response_transform_request"] = request
            with self.subTest(expression=expression):
                self.assertEqual(_cascade(record)["response"]["speech"], answer)
                record["response"]["speech"] = str(int(answer) + 1)
                with self.assertRaises(EvaluationScoringError):
                    _cascade(record)

    def test_calculation_rejects_executable_syntax_unsupplied_operands_and_inexact_answers(self):
        request = "Calculate 7 times 4 plus 3. Return only the integer."
        for expression in ("7*4+99", "7**4", "7//4", "7/4", "__import__('os').system('id')",
                           "[7,4][0]", "(lambda:7)()", "True+7", "7/(4-4)"):
            record = transformed_record([expression], "31")
            record["response_transform_request"] = request
            with self.subTest(expression=expression), self.assertRaises(EvaluationScoringError):
                _cascade(record)
        record = transformed_record(["7*4+3"], "31")
        with self.assertRaises(EvaluationScoringError):
            _cascade(record)

    def test_historical_integer_parts_do_not_become_expression_claims(self):
        record = transformed_record(["31"], "31")
        record["response_transform_request"] = "Calculate 7 times 4 plus 3. Return only the integer."
        self.assertEqual(_cascade(record)["response"]["speech"], "31")

    def test_numbering_prefixes_and_header_are_rederived_from_source(self):
        for request, parts, speech in (
            ("Give three numbered steps.", ["Fold.", "Press.", "Open."],
             "1. Fold.\n2. Press.\n3. Open."),
            ("Give three numbered steps.", ["1. Fold.", "2) Press.", "3. Open."],
             "1. Fold.\n2. Press.\n3. Open."),
            ("Give three numbered lines. Use prefixes Start:, Middle:, Finish:.",
             ["Fold.", "Middle: Press.", "Open."],
             "1. Start: Fold.\n2. Middle: Press.\n3. Finish: Open."),
            ("Return CSV with header shelf,boxes.", ["north,6", "south,2"],
             "shelf,boxes\nnorth,6\nsouth,2"),
            ("Return CSV with header shelf,boxes.", ["shelf,boxes", "north,6"],
             "shelf,boxes\nshelf,boxes\nnorth,6"),
            ("Return only the integer.", ["31"], "31"),
            ('Return CSV from text "header old,value". Use header new,value.', ["row,6"], "new,value\nrow,6"),
        ):
            with self.subTest(request=request):
                record = transformed_record(parts, speech)
                record["response_transform_request"] = request
                self.assertEqual(_cascade(record)["response"]["speech"], speech)

    def test_missing_source_cannot_authorize_added_labels_header_or_numbering(self):
        for parts, speech in (
            (["north,6"], "shelf,boxes\nnorth,6"),
            (["Fold.", "Open."], "Start: Fold.\nEnd: Open."),
            (["Fold.", "Open."], "1. Fold.\n2. Open."),
        ):
            with self.subTest(speech=speech), self.assertRaises(EvaluationScoringError):
                _cascade(transformed_record(parts, speech))

    def test_tampered_source_derived_text_and_negative_csv_directives_are_rejected(self):
        for request, parts, speech in (
            ("Return CSV with header shelf,boxes.", ["north,6"], "shelf,people\nnorth,6"),
            ("Return CSV with header shelf,boxes.", ["shelf,boxes", "north,6"], "shelf,boxes\nnorth,6"),
            ("Give two numbered lines. Use prefixes Start:, End:.", ["Fold.", "Open."],
             "1. Start: Fold.\n2. Finish: Open."),
            ("Give two numbered steps.", ["Fold.", "Open."], "1. Fold.\n3. Open."),
            ("Give two numbered steps.", ["1. Fold.", "3. Open."], "1. Fold.\n2. Open."),
            ("Do not return CSV with header shelf,boxes.", ["north,6"], "shelf,boxes\nnorth,6"),
            ("Explain CSV with header shelf,boxes.", ["north,6"], "shelf,boxes\nnorth,6"),
            ("Return CSV. Do not use header shelf,boxes.", ["north,6"], "shelf,boxes\nnorth,6"),
            ("Give two lines. Do not use labels Start:, End:.", ["Fold.", "Open."], "Start: Fold.\nEnd: Open."),
            ("Give two lines. Do not use numbered lines.", ["Fold.", "Open."], "1. Fold.\n2. Open."),
            ('Explain the phrase "numbered lines" in two sentences.', ["Fold.", "Open."], "1. Fold.\n2. Open."),
            ("Explain a numbered list in exactly two lines.", ["Fold.", "Open."], "1. Fold.\n2. Open."),
        ):
            record = transformed_record(parts, speech)
            record["response_transform_request"] = request
            with self.subTest(speech=speech), self.assertRaises(EvaluationScoringError):
                _cascade(record)

    def test_recorded_source_must_match_sha_bound_suite_prompt_at_scoring(self):
        suite = load_evaluation_suite()
        records = _raw_records()
        row = next(row for row in records if row.get("record_type") == "case"
                   and not row["cascade"]["retrieval_invoked"])
        row["cascade"] = transformed_record(["Hello."], "Hello.")
        actual = next(case.prompt for case in suite.cases if case.id == row["case_id"])
        row["cascade"]["response_transform_request"] = actual
        observations = parse_observation_jsonl("".join(json.dumps(item) + "\n" for item in records))
        self.assertTrue(score_observations(suite, observations)["protocol"]["complete"])
        row["cascade"]["response_transform_request"] = "Return CSV with header shelf,boxes."
        row["cascade"]["response"]["speech"] = "shelf,boxes\nHello."
        tampered = parse_observation_jsonl("".join(json.dumps(item) + "\n" for item in records))
        with self.assertRaisesRegex(EvaluationScoringError, "exact suite prompt"):
            score_observations(suite, tampered)

    def test_source_field_cannot_be_attached_to_unrelated_transform(self):
        record = transformed_record(["Fold.", "Open."], "1. Fold.\n2. Open.", "human_guidance_steps")
        record["response_transform_request"] = "Give two numbered steps."
        with self.assertRaises(EvaluationScoringError):
            _cascade(record)

    def test_recorder_retains_actual_format_request_including_literal_fragment(self):
        request = "Give two numbered lines."
        result = ChatResult("qwen3:1.7b", '{"answer_parts":["Fold.","Open."]}',
                            "stop", 2_000_000, 100_000, 20, 8, 1_000_000)
        backend = Mock()
        backend.chat.return_value = result
        recorder = _EvaluationBackend(backend, iter(range(100)).__next__)
        recorder.chat(result.model, (ChatMessage("system", "Return JSON."),
                                    ChatMessage("user", request)),
                      response_format=parts_schema(TaskLayout("lines", 2, numbered=True)))
        self.assertEqual(recorder.calls_since(0)[0]["response_transform_request"], request)

    def test_integer_and_header_schemas_are_closed_and_have_no_memory_authority(self):
        for layout in (TaskLayout("integer", 1), TaskLayout("calculation", 1),
                       TaskLayout("csv", header="shelf,boxes")):
            schema = parts_schema(layout)
            self.assertEqual(_chat_purpose(schema), "generation")
            self.assertEqual(_schema_supplied_ids(schema, purpose="generation"), ())
            changed = deepcopy(schema)
            changed["properties"]["answer_parts"]["items"]["maxLength"] += 1
            with self.assertRaises(EvaluationRunError):
                _chat_purpose(changed)


if __name__ == "__main__":
    unittest.main()
