"""Small synthetic audit checks: no models, production imports, or real cohorts."""
import copy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("repair_measurement_audit_v2", HERE / "audit_results_v2.py")
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


def call(marker, content="sample"):
    result = {"model": "model", "content": content, "total_duration_ns": 20,
              "load_duration_ns": 5}
    return {"case_id": "example", "model": "model", "status": "ok", "wall_ns": 30,
            "options": {"response_format": {"properties": {marker: {"type": "string"}}}},
            "result": result}


class IndependentAuditTests(unittest.TestCase):
    def calculation_row(self, request, expression, delivered):
        row = self.parts_row(request, [expression], delivered)
        row["calls"][0]["options"]["response_format"]["properties"]["answer_parts"]["items"] = {
            "type": "string", "minLength": 1, "maxLength": 160, "pattern": r"^[0-9+*/() -]+$"}
        return row

    def test_expression_is_independently_evaluated_from_current_operands(self):
        row = self.calculation_row("How many tokens in seven groups of four plus three? Return only the integer.", "7*4+3", "31")
        result = audit_module.audit_parts_transforms(audit_module.Audit(), [row])
        self.assertFalse(result["findings"])
        self.assertEqual(result["arithmetic_reconstructions"][0]["independently_computed_integer"], "31")
        self.assertEqual(result["arithmetic_reconstructions"][0]["supplied_operand_magnitudes"], [3, 4, 7])
        for incorrect in ("23", "7*4+3"):
            row["delivered_text"] = row["reply"]["response"]["speech"] = incorrect
            self.assertTrue(audit_module.audit_parts_transforms(audit_module.Audit(), [row])["findings"])

    def test_arithmetic_provenance_does_not_claim_expression_semantics(self):
        row = self.calculation_row("Calculate 7 times 4 plus 3. Return only the integer.", "7*4-3", "25")
        result = audit_module.audit_parts_transforms(audit_module.Audit(), [row])
        self.assertFalse(result["findings"])
        self.assertIn("do not establish", result["scope"])

    def test_wrong_constants_guessed_result_and_relaxed_calculation_schema_fail(self):
        request = "Calculate seven times four plus three. Return only the integer."
        for expression in ("31", "7*4+1", "7**4", "7/3"):
            row = self.calculation_row(request, expression, "31")
            self.assertTrue(audit_module.audit_parts_transforms(audit_module.Audit(), [row])["findings"])
        row = self.calculation_row(request, "7*4+3", "31")
        row["calls"][0]["options"]["response_format"]["properties"]["answer_parts"]["items"]["maxLength"] = 600
        self.assertTrue(audit_module.audit_parts_transforms(audit_module.Audit(), [row])["findings"])

    def test_only_matching_consecutive_raw_markers_are_normalized(self):
        request = "Return two numbered lines with prefixes First:, Last:."
        row = self.parts_row(request, ["1. First: Begin.", "2) Finish."], "1. First: Begin.\n2. Last: Finish.")
        self.assertFalse(audit_module.audit_parts_transforms(audit_module.Audit(), [row])["findings"])
        for wrong in (["2. Begin.", "1. Finish."], ["1. Begin.", "2. "], ["- Begin.", "Finish."]):
            bad = self.parts_row(request, wrong, "1. First: Begin.\n2. Last: Finish.")
            self.assertTrue(audit_module.audit_parts_transforms(audit_module.Audit(), [bad])["findings"])

    def test_public_note_requires_frozen_literal_topic_and_prompt_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "src/oline_hri/answer_guidance.py"
            source.parent.mkdir(parents=True)
            source.write_text('REFERENCE_NOTES = (ReferenceNote("folding_v1", r"paper", "Fold back and forth.", ("https://example.org/folding",)),)\n')
            frozen = {"src/oline_hri/answer_guidance.py": sha256(source.read_bytes()).hexdigest()}
            row = self.parts_row("Explain paper folding.", ["Fold back and forth."], "Fold back and forth.")
            row["reply"]["reference_ids"] = ["folding_v1"]
            row["calls"][0]["messages"].insert(0, {"role": "system", "content": "Public note: Fold back and forth."})
            audit = audit_module.Audit()
            report = audit_module.audit_public_references(audit, [row], root, frozen)
            self.assertFalse(report["findings"])
            self.assertTrue(all(item["passed"] for item in audit.checks))
            for mutation in ("unknown", "missing_prompt", "source_drift"):
                changed = copy.deepcopy(row)
                if mutation == "unknown":
                    changed["reply"]["reference_ids"] = ["invented_personal_record"]
                elif mutation == "missing_prompt":
                    changed["calls"][0]["messages"] = changed["calls"][0]["messages"][1:]
                else:
                    source.write_text(source.read_text() + "# changed\n")
                bad = audit_module.Audit()
                audit_module.audit_public_references(bad, [changed], root, frozen)
                self.assertTrue(any(not item["passed"] for item in bad.checks))

    def parts_row(self, request, parts, speech, *, fragment=""):
        result = {"model": "model", "content": json.dumps({"answer_parts": parts})}
        raw_call = {"case_id": "typed", "model": "model", "result": result,
                    "messages": [{"role": "user", "content": fragment or request}],
                    "options": {"response_format": {"properties": {"answer_parts": {
                        "minItems": len(parts), "maxItems": len(parts)}}}}}
        return {"id": "typed", "case": {"text": request}, "calls": [raw_call],
                "route": {"dependency": {"mode": "required" if fragment else "none",
                                           "general_request": fragment}},
                "delivered_text": speech,
                "reply": {"response_transform": "task_parts_v1", "generation": result,
                          "effective_mode": "required" if fragment else "none",
                          "response": {"speech": speech}}}

    def test_source_derived_header_numbering_and_prefixes_reconstruct(self):
        fixtures = [
            self.parts_row("Produce CSV. The header must be place,count.", ["east,4"], "place,count\neast,4"),
            self.parts_row("Return two numbered lines with prefixes First:, Last:.",
                           ["First: Begin.", "Finish."], "1. First: Begin.\n2. Last: Finish."),
            self.parts_row("Return only the integer.", ["17"], "17"),
        ]
        for row in fixtures:
            with self.subTest(request=row["case"]["text"]):
                audit = audit_module.Audit()
                report = audit_module.audit_parts_transforms(audit, [row])
                self.assertFalse(report["findings"])
                self.assertTrue(all(check["passed"] for check in audit.checks))

    def test_unrequested_header_changed_content_and_unbound_prompt_fail(self):
        rows = [
            self.parts_row("Return two separate lines.", ["east,4", "west,5"], "place,count\neast,4\nwest,5"),
            self.parts_row("Return two separate lines.", ["Original.", "Second."], "Changed.\nSecond."),
            self.parts_row("Return two separate lines.", ["Original.", "Second."], "Original.\nSecond."),
        ]
        rows[-1]["calls"][0]["messages"][0]["content"] = "Invented formatting authority."
        for row in rows:
            audit = audit_module.Audit()
            report = audit_module.audit_parts_transforms(audit, [row])
            self.assertTrue(report["findings"])
            self.assertFalse(audit.checks[-1]["passed"])

    def test_csv_first_data_row_equal_to_header_is_retained(self):
        request = "Produce CSV. The header must be place,count."
        row = self.parts_row(request, ["place,count", "east,4"], "place,count\nplace,count\neast,4")
        result = audit_module.audit_parts_transforms(audit_module.Audit(), [row])
        self.assertFalse(result["findings"])
        row["delivered_text"] = row["reply"]["response"]["speech"] = "place,count\neast,4"
        result = audit_module.audit_parts_transforms(audit_module.Audit(), [row])
        self.assertTrue(result["findings"])

    def test_negated_header_and_prefix_are_not_inserted(self):
        rows = [
            self.parts_row("Produce CSV. Do not use header place,count.", ["east,4", "west,2"], "east,4\nwest,2"),
            self.parts_row("Return two lines. Avoid prefixes First:, Last:.", ["Begin.", "Finish."], "Begin.\nFinish."),
        ]
        for row in rows:
            result = audit_module.audit_parts_transforms(audit_module.Audit(), [row])
            self.assertFalse(result["findings"])

    def test_quoted_directive_is_skipped_but_quoted_header_value_is_literal(self):
        rows = [
            self.parts_row('Return CSV from text "header old,value". Use header new,value.',
                           ["east,4"], "new,value\neast,4"),
            self.parts_row('Return CSV. Use header "place,count".', ["east,4"], "place,count\neast,4"),
            self.parts_row('Explain syntax "labels First:, Last:" in exactly two lines.',
                           ["Begin.", "Finish."], "Begin.\nFinish."),
            self.parts_row('Return two lines. Avoid prefixes Old:, Bad:. Use prefixes First:, Last:.',
                           ["Begin.", "Finish."], "First: Begin.\nLast: Finish."),
        ]
        for row in rows:
            with self.subTest(request=row["case"]["text"]):
                result = audit_module.audit_parts_transforms(audit_module.Audit(), [row])
                self.assertFalse(result["findings"])

    def test_numbered_input_quoted_approximate_and_negated_mentions_are_not_output_directives(self):
        requests = [
            "Explain a numbered list in two sentences.",
            'The source says "Return two numbered lines." Give two sentences.',
            "Do not give two numbered lines. Give two sentences.",
            "Describe the source with two numbered lines in two sentences.",
            "Return at most two numbered lines.",
            "Return two numbered lines for each example.",
        ]
        for request in requests:
            with self.subTest(request=request):
                self.assertFalse(audit_module._numbered_directive(request, 2))
                row = self.parts_row(request, ["First sentence.", "Second sentence."], "First sentence. Second sentence.")
                self.assertFalse(audit_module.audit_parts_transforms(audit_module.Audit(), [row])["findings"])

    def test_scalar_schema_requires_positive_unquoted_source_directive(self):
        for request, allowed in (("Return only the integer.", True),
                ("Do not return only the integer; explain the result.", False),
                ('Explain the phrase "Return only the integer."', False)):
            row = self.parts_row(request, ["17"], "17")
            row["calls"][0]["options"]["response_format"]["properties"]["answer_parts"]["items"] = {"pattern": r"^[+-]?\d+$"}
            result = audit_module.audit_parts_transforms(audit_module.Audit(), [row])
            self.assertEqual(not result["findings"], allowed)

    def test_mixed_fragment_is_literal_and_prefix_remains_separately_exposed(self):
        fragment = "Give three checklist items."
        prefix = "I don't have that earlier information available. Could you remind me of the person's name? "
        row = self.parts_row("Who did I select? " + fragment, ["One.", "Two.", "Three."],
                             prefix + "- One.\n- Two.\n- Three.", fragment=fragment)
        audit = audit_module.Audit()
        report = audit_module.audit_parts_transforms(audit, [row])
        self.assertFalse(report["findings"])
        self.assertEqual(report["mixed_missing_evidence_prefixes"], [{"id": "typed", "prefix": prefix}])
        row["case"]["text"] = "A request without that fragment."
        bad = audit_module.audit_parts_transforms(audit_module.Audit(), [row])
        self.assertTrue(bad["findings"])

    def test_linear_percentiles_and_missing_latency(self):
        result = audit_module.independent_latency([21, 1, 9, 5])
        self.assertEqual(result["n"], 4)
        self.assertEqual(result["p50_seconds"], 7)
        self.assertAlmostEqual(result["p95_seconds"], 19.2)
        self.assertIsNone(audit_module.independent_latency([])["p95_seconds"])

    def test_errors_and_missing_cases_stay_in_denominator_without_effective_route_credit(self):
        cases = [{"id": name, "category": "synthetic", "expected_modes": ["none"]}
                 for name in ("reply", "error", "missing")]
        observations = [
            {"id": "reply", "status": "ok", "delivered_text": "Useful answer.", "wall_ns": 2_000_000_000,
             "route": {"dependency": {"mode": "required"}, "classifier_metadata": {
                 "whole_request": {"predicted_mode": "none", "mode": "none"}}},
             "reply": {"effective_mode": "none", "generation": {"model": "model"}}},
            {"id": "error", "status": "error", "delivered_text": "", "wall_ns": 0},
        ]
        judgments = {case["id"]: {"quality_pass": True} for case in cases}
        rows = audit_module.independent_rows(cases, observations, judgments)
        self.assertEqual(len(rows), 3)
        self.assertEqual(sum(row["quality_pass"] for row in rows), 1)
        self.assertEqual(sum(row["combined_pass"] for row in rows), 0)
        self.assertEqual([row["status"] for row in rows], ["ok", "error", "missing"])
        self.assertIsNone(rows[-1]["seconds"])
        self.assertFalse(rows[0]["final_match"])
        self.assertEqual(rows[0]["effective_mode"], "none")

    def test_actual_role_detection_covers_new_and_historical_review_and_guidance(self):
        for marker, expected in (("mode", "dependency_review"), ("needs_personal_facts", "dependency_review"),
                                 ("steps", "answer_generation"), ("instructions", "answer_generation"),
                                 ("answer_parts", "answer_generation"),
                                 ("speech", "answer_generation"), ("verdict", "answer_review"),
                                 ("model_size", "compute_classifier"), ("other", "unrecognized")):
            with self.subTest(marker=marker):
                self.assertEqual(audit_module.independent_role(call(marker)), expected)

    def test_attempt_omission_and_fabricated_compute_are_detected(self):
        calls = [call("speech", "withheld"), call("speech", "delivered"), call("verdict", "pass")]
        row = {"id": "example", "calls": calls,
               "route": {"model_size_decision_source": "dependency_size_policy_v2", "model_size_generation": None},
               "reply": {"attempts": [c["result"] for c in calls[:2]], "attempted_models": ["model", "model"],
                         "generation": calls[1]["result"], "review_attempts": [calls[2]["result"]],
                         "answer_reviews": [{"generation": calls[2]["result"]}]}}
        good = audit_module.Audit()
        report = audit_module.audit_calls(good, [row], calls, {"models": {"model": {}}})
        self.assertTrue(all(check["passed"] for check in good.checks))
        self.assertEqual(report["by_role"], {"answer_generation": 2, "answer_review": 1})
        self.assertTrue(report["candidate_within_declared_call_bounds"])
        altered = copy.deepcopy(row)
        altered["reply"]["attempts"] = altered["reply"]["attempts"][1:]
        bad = audit_module.Audit()
        audit_module.audit_calls(bad, [altered], calls, {"models": {"model": {}}})
        self.assertTrue(any(not check["passed"] for check in bad.checks))
        fabricated = copy.deepcopy(row)
        fabricated["route"]["model_size_generation"] = {"model": "model", "content": "large"}
        bad = audit_module.Audit()
        audit_module.audit_calls(bad, [fabricated], calls, {"models": {"model": {}}})
        self.assertTrue(any(not check["passed"] for check in bad.checks))

    def test_historical_archive_is_explicit_and_tampering_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            cohort = Path(directory)
            archived = cohort / "candidate_source"
            archived.mkdir()
            source = archived / "synthetic_source.py"
            source.write_text("answer = 42\n")
            hashes = {"synthetic_source.py": audit_module.sha(source)}
            good = audit_module.Audit()
            report = audit_module.audit_sources(good, cohort, archived, {"source_sha256": hashes}, {"source_sha256": hashes})
            self.assertTrue(all(check["passed"] for check in good.checks))
            self.assertEqual(report["working_source_drift"], ["synthetic_source.py"])
            source.write_text("answer = 43\n")
            bad = audit_module.Audit()
            audit_module.audit_sources(bad, cohort, archived, {"source_sha256": hashes}, {"source_sha256": hashes})
            self.assertTrue(any(not check["passed"] for check in bad.checks))

    def test_sqlite_audit_is_read_only_and_detects_nonempty_store(self):
        with tempfile.TemporaryDirectory() as directory:
            collection = Path(directory)
            (collection / "run").mkdir()
            path = collection / "run/memory.sqlite3"
            with sqlite3.connect(path) as connection:
                for name in ("memory_item", "memory_audit", "memory_embedding", "memory_fts"):
                    connection.execute(f"CREATE TABLE {name} (id INTEGER)")
            before = audit_module.sha(path)
            good = audit_module.Audit()
            audit_module.audit_memory(good, collection, [], "synthetic")
            self.assertTrue(all(check["passed"] for check in good.checks))
            self.assertEqual(audit_module.sha(path), before)
            failed = {"operation": "retrieve", "case_id": "synthetic", "status": "error",
                      "error": {"type": "ValueError", "message": "invalid query"}}
            (collection / "run/retrieval_calls.jsonl").write_text(json.dumps(failed) + "\n")
            preserved_error = audit_module.Audit()
            report = audit_module.audit_memory(preserved_error, collection, [], "synthetic")
            self.assertTrue(all(check["passed"] for check in preserved_error.checks))
            self.assertEqual(report["successful_empty_retrievals"], 0)
            self.assertEqual(report["retrieval_error_count"], 1)
            self.assertFalse(report["candidate_retrieval_operations_successful"])
            with sqlite3.connect(path) as connection:
                connection.execute("INSERT INTO memory_item VALUES (1)")
            bad = audit_module.Audit()
            audit_module.audit_memory(bad, collection, [], "synthetic")
            self.assertTrue(any(not check["passed"] for check in bad.checks))


if __name__ == "__main__":
    unittest.main()
