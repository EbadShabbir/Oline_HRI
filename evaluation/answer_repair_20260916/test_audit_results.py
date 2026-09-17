"""Small synthetic audit checks: no models, production imports, or real cohorts."""
import copy
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("repair_measurement_audit", HERE / "audit_results.py")
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


def call(marker, content="sample"):
    result = {"model": "model", "content": content, "total_duration_ns": 20,
              "load_duration_ns": 5}
    return {"case_id": "example", "model": "model", "status": "ok", "wall_ns": 30,
            "options": {"response_format": {"properties": {marker: {"type": "string"}}}},
            "result": result}


class IndependentAuditTests(unittest.TestCase):
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
