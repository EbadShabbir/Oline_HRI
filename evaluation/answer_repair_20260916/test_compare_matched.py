"""Synthetic paired accounting only; no model, real cohort or holdout access."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("matched_comparison", Path(__file__).with_name("compare_matched.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    cases = [{"id": name, "text": "Prompt " + name + ".", "category": "synthetic",
              "expected_modes": ["none"], "rubric": {"required_components": ["Complete the task."]}}
             for name in ("improves", "regresses", "setup")]

    def observation(identifier, seconds, *, error=False, final="none"):
        return {"id": identifier, "status": "error" if error else "ok", "wall_ns": int(seconds * 1e9),
                "delivered_text": "" if error else "Answer.",
                "route": None if error else {"dependency": {"mode": final}, "classifier_metadata": {
                    "whole_request": {"predicted_mode": "none", "mode": "none"}}},
                "reply": {"effective_mode": "none", "generation": None}}

    before = [observation("improves", 40), observation("regresses", 10), observation("setup", 0, error=True)]
    after = [observation("improves", 6, final="required"), observation("regresses", 3, error=True),
             observation("setup", 8)]
    old_judgments = {case["id"]: {"quality_pass": case["id"] == "regresses"} for case in cases}
    new_judgments = {case["id"]: {"quality_pass": True} for case in cases}
    return cases, before, old_judgments, deepcopy(cases), after, new_judgments


class MatchedComparisonTests(unittest.TestCase):
    def test_new_error_stays_matched_and_original_setup_is_reported_separately(self):
        report, rows = module.compare(*fixture())
        self.assertEqual(report["matched_count"], 2)
        self.assertEqual(report["matched_after"]["quality_pass"], {"count": 1, "denominator": 2, "rate": .5})
        self.assertEqual(report["matched_after"]["combined_pass"]["count"], 0)
        self.assertEqual(report["matched_after"]["statuses"], {"ok": 1, "error": 1})
        self.assertEqual(report["quality_transitions"]["fail_to_pass"]["ids"], ["improves"])
        self.assertEqual(report["quality_transitions"]["pass_to_fail"]["ids"], ["regresses"])
        self.assertEqual(report["original_setup_failures_excluded"]["count"], 1)
        self.assertEqual(report["final_full_cohort"]["quality_pass"]["count"], 2)
        self.assertEqual(report["final_full_cohort"]["planned"], 3)
        self.assertEqual(rows[0]["wall_delta_seconds"], -34)
        self.assertEqual(rows[1]["score_deltas"]["quality_pass"], -1)

    def test_linear_latency_includes_the_new_error_duration(self):
        report, _ = module.compare(*fixture())
        self.assertEqual(report["matched_before"]["wall_latency"]["p50_seconds"], 25)
        self.assertAlmostEqual(report["matched_before"]["wall_latency"]["p95_seconds"], 38.5)
        self.assertEqual(report["matched_after"]["wall_latency"]["p50_seconds"], 4.5)
        self.assertAlmostEqual(report["matched_after"]["wall_latency"]["p95_seconds"], 5.85)

    def test_missing_new_observation_is_rejected_instead_of_reducing_denominator(self):
        data = list(fixture())
        data[4] = data[4][1:]
        with self.assertRaisesRegex(ValueError, "cannot drop new failures"):
            module.compare(*data)

    def test_prompt_history_and_criteria_changes_prevent_a_matched_claim(self):
        for kind in ("prompt", "history", "rubric"):
            data = list(fixture())
            if kind == "prompt":
                data[3][0]["text"] += " "
            elif kind == "history":
                data[3][0]["prior_turns"] = [{"role": "user", "content": "Extra context."}]
            else:
                data[3][0]["rubric"] = {"required_components": ["An easier task."]}
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                module.compare(*data)


if __name__ == "__main__":
    unittest.main()
