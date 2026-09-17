"""Keep diagnostic evidence counts distinct from delivery and correctness."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import summarize_complete_system_pipeline as diagnostic


class PipelineDiagnosticTests(unittest.TestCase):
    def test_missing_failed_reply_fields_remain_unknown_and_citations_use_deliveries_only(self):
        common = {"arm": "small", "repetition": 1, "stratum": "personal_recall", "calls": [],
                  "retrieval_calls": [{}], "route": {"decision": {"memory_required": True}}}
        rows = [{**common, "id": "one", "status": "ok", "reference_ids": [],
                 "answer_constraint": None, "response_transform": None},
                {**common, "id": "two", "status": "error", "error": "ResponseValidationError", "message": "withheld"}]
        metric_base = {"arm": "small", "repetition": 1, "forbidden_supplied_ids": [], "forbidden_cited_ids": []}
        metrics = [{**metric_base, "case_id": "one", "supplied_evidence_known": True, "supplied_ids": ["a", "b"],
                    "required_ids_missing_from_evidence": [], "required_ids_missing_from_citations": ["b"]},
                   {**metric_base, "case_id": "two", "supplied_evidence_known": False, "supplied_ids": None,
                    "required_ids_missing_from_evidence": None, "required_ids_missing_from_citations": ["a", "b"]}]
        rubrics = {name: {"required_memory_ids": ["a", "b"]} for name in ("one", "two")}
        result = diagnostic.summarize(rows, metrics, rubrics)
        self.assertEqual(result["status_counts"], {"ok": 1, "error": 1})
        self.assertEqual(result["required_evidence_unknown_attempts"], 1)
        self.assertEqual(result["all_required_ids_supplied_attempts"], 1)
        self.assertEqual(result["required_id_occurrences"], 4)
        self.assertEqual(result["required_id_occurrences_supplied"], 2)
        self.assertEqual(result["delivered_personal_missing_required_citation_occurrences"], 1)
        self.assertEqual(result["reference_ids_field"], {"empty": 1, "unrecorded": 1})
        self.assertEqual(result["answer_constraints"], {"none": 1, "unrecorded": 1})

    def test_empty_gold_requirements_do_not_count_as_successful_evidence_coverage(self):
        rows = [{"arm": "small", "repetition": 1, "id": "unknown", "status": "ok",
                 "stratum": "personal_recall", "calls": [], "retrieval_calls": []}]
        metrics = [{"arm": "small", "repetition": 1, "case_id": "unknown", "forbidden_supplied_ids": [],
                    "forbidden_cited_ids": [], "supplied_evidence_known": True, "supplied_ids": []}]
        result = diagnostic.summarize(rows, metrics, {"unknown": {"required_memory_ids": []}})
        self.assertEqual(result["personal_attempts"], 1)
        self.assertEqual(result["personal_attempts_with_required_ids"], 0)
        self.assertEqual(result["all_required_ids_supplied_attempts"], 0)


if __name__ == "__main__":
    unittest.main()
