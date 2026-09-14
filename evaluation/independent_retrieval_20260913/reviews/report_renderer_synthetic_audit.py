"""Independent stdlib-only report checks. Contains no collected model outputs."""
import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "independent_report_under_review", ROOT / "scripts/report_independent_retrieval.py")
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


def row(policy, success, *, case="case-a", abstained=False, unsupported=False,
        forbidden=False, failure=False):
    return {"model": "qwen3:0.6b", "policy": policy, "case_id": case,
            "answerability": "known_authorized", "task_success": success,
            "known_fact_cautious_miss": abstained and not success,
            "abstained": abstained, "unsupported_claim": unsupported,
            "unsupported_personal_claim": unsupported,
            "forbidden_disclosure": forbidden, "failure": failure}


def paired(delta=-2):
    return {"differences": {"request_s_difference": {
        "mean": delta, "bootstrap_95_low": delta - 1,
        "bootstrap_95_high": delta + 1}}}


class IndependentReportChecks(unittest.TestCase):
    def test_interval_sign_units_and_undefined(self):
        self.assertEqual(report.interval(paired(), "request_s"),
                         "-2.000 [-3.000, -1.000]")
        quality = {"differences": {"task_success_difference": {
            "mean": .125, "bootstrap_95_low": -.125, "bootstrap_95_high": .375}}}
        self.assertEqual(report.interval(quality, "task_success", percent_points=True),
                         "+12.5 [-12.5, +37.5]")
        self.assertEqual(report.interval(paired(), "supplied_coverage"), "n/a")
        self.assertEqual(report.percent(None), "n/a")
        self.assertEqual(report.fraction(0, 0), "n/a")

    def test_known_caution_is_not_success_and_forbidden_is_not_clean_caution(self):
        rows = [row("OFF", False, abstained=True),
                row("OFF", False, abstained=True, unsupported=True),
                row("OFF", False, abstained=True, forbidden=True),
                row("OFF", False, failure=True), row("OFF", True)]
        group = report.subgroup(rows, "qwen3:0.6b", "OFF", "known_authorized")
        self.assertEqual(group["attempts"], 5)
        self.assertEqual(group["success"], 1)
        self.assertEqual(group["cautious_misses"], 3)
        self.assertEqual(group["cautious_misses_without_unsupported_or_forbidden_claims"], 1)
        self.assertEqual(group["failures"], 1)

    def test_distinct_request_wins_do_not_count_repeats_as_independent(self):
        rows = []
        for policy, results in (("ALWAYS", [True, True, False]),
                                ("SELECTIVE", [True, False, False])):
            rows.extend(row(policy, value) for value in results)
            rows.extend(row(policy, True, case="case-b") for _ in range(3))
        self.assertEqual(report.known_pairs(rows, "qwen3:0.6b"),
                         {"always_higher": 1, "equal": 1})

    def test_correct_without_runtime_evidence_remains_separate_diagnostic(self):
        rows = [row("OFF", True), row("OFF", False, abstained=True)]
        rows[0]["posthoc_known_answer_without_supplied_evidence"] = True
        rows[1]["posthoc_known_answer_without_supplied_evidence"] = False
        group = report.subgroup(rows, "qwen3:0.6b", "OFF", "known_authorized")
        self.assertEqual(group["success"], 1)
        self.assertEqual(group["known_success_without_runtime_evidence"], 1)
        self.assertEqual(group["cautious_misses"], 1)

    def test_unfavorable_and_null_results_are_reported_directly(self):
        model = "qwen3:0.6b"
        overall = {(model, "ALWAYS"): {"unnecessary_retrievals": 24,
                    "no_memory_needed_authorized": 24},
                   (model, "SELECTIVE"): {"unnecessary_retrievals": 0,
                    "no_memory_needed_authorized": 24}}
        pairs = {(model, "SELECTIVE-ALWAYS", "overall"): paired(2)}
        rows = [row("ALWAYS", True), row("SELECTIVE", False, abstained=True),
                row("OFF", False, abstained=True)]
        text = report.interpret(model, overall, pairs, rows)
        self.assertIn("lost known-authorized success", text)
        self.assertIn("added an observed 2.000 seconds", text)
        self.assertIn("avoided 24 unnecessary retrieval attempts", text)
        self.assertIn("including its selection costs", text)
        rows[0] = row("ALWAYS", False, abstained=True)
        text = report.interpret(model, overall, pairs, rows)
        self.assertIn("useful personalization was not demonstrated", text)

    def test_csv_booleans_zero_and_missing_values_remain_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "attempts.csv"
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["task_success", "failure",
                    "known_fact_cautious_miss", "selection_decision", "request_s",
                    "loading_s", "retrieval_attempts", "inspected_ids", "supplied_ids"])
                writer.writeheader()
                writer.writerow({"task_success": False, "failure": False,
                    "known_fact_cautious_miss": True, "selection_decision": "",
                    "request_s": 0.5, "loading_s": 0, "retrieval_attempts": 0,
                    "inspected_ids": "[]", "supplied_ids": "[]"})
            result = report.decode_csv(path)[0]
        self.assertIs(result["task_success"], False)
        self.assertIs(result["known_fact_cautious_miss"], True)
        self.assertIsNone(result["selection_decision"])
        self.assertEqual(result["loading_s"], 0.0)
        self.assertEqual(result["retrieval_attempts"], 0)
        self.assertEqual(result["inspected_ids"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
