"""Synthetic offline checks: no fresh corpus or collected outputs are read."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("fresh_analyze", Path(__file__).with_name("analyze.py"))
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def case(identifier):
    return {"id": identifier, "text": "Synthetic case.", "expected_modes": ["none"], "category": "synthetic"}


def observation(fixture, *, status="ok", final="none", seconds=4):
    return {"id": fixture["id"], "case": fixture, "stage": "conversation", "policy": "learned",
            "status": status, "wall_ns": int(seconds * 1e9), "delivered_text": "Synthetic answer.",
            "route": {"dependency": {"mode": final}, "classifier_metadata": {"whole_request": {
                "predicted_mode": "none", "mode": "none"}}},
            "reply": {"effective_mode": "none", "generation": None}, "calls": []}


class AnalysisTests(unittest.TestCase):
    def test_actual_mode_review_is_counted_without_inventing_a_compute_call(self):
        call = {"options": {"response_format": {"properties": {"mode": {"type": "string"}}}}}
        self.assertEqual(analysis.call_role(call), "dependency_review")

    def test_linear_quantiles(self):
        self.assertEqual(analysis.quantile([2, 4, 10, 20], .5), 7)
        self.assertAlmostEqual(analysis.quantile([2, 4, 10, 20], .95), 18.5)
        self.assertIsNone(analysis.quantile([], .95))

    def test_missing_and_error_remain_in_quality_and_deadline_denominators(self):
        cases = [case("success"), case("error"), case("missing")]
        observations = [observation(cases[0]), observation(cases[1], status="error", seconds=8)]
        judgments = analysis.normalize_judgments([{ "id": item["id"], "quality_pass": True, "flags": []}
                                                 for item in cases])
        rows = analysis.build(cases, observations, judgments)
        metrics = analysis.aggregate(rows)
        self.assertEqual(metrics["summary"]["quality_pass"], {"count": 1, "denominator": 3, "rate": 1 / 3})
        self.assertEqual(metrics["summary"]["final_match"]["count"], 1)
        self.assertEqual(metrics["quality_deadlines"]["5"]["denominator"], 3)
        self.assertEqual(metrics["quality_deadlines"]["5"]["count"], 1)
        self.assertEqual(metrics["latency"]["overall_observed"]["n"], 2)
        self.assertEqual(metrics["latency"]["overall_observed"]["missing_latency"], 1)

    def test_effective_fallback_cannot_rescue_wrong_final_route(self):
        fixture = case("fallback")
        rows = analysis.build([fixture], [observation(fixture, final="clarify")], {
            "fallback": {"id": "fallback", "quality_pass": True, "flags": []}})
        self.assertTrue(rows[0]["quality_pass"])
        self.assertEqual(rows[0]["effective_mode"], "none")
        self.assertFalse(rows[0]["final_match"])
        self.assertFalse(rows[0]["combined_pass"])

    def test_typed_human_guidance_counts_as_generation(self):
        def call(properties):
            return {"options": {"response_format": {"properties": {name: {} for name in properties}}}}
        self.assertEqual(analysis.call_role(call(["steps_for_user"])), "answer_generation")
        self.assertEqual(analysis.call_role(call(["answer_parts"])), "answer_generation")
        self.assertEqual(analysis.call_role(call(["speech"])), "answer_generation")
        self.assertEqual(analysis.call_role(call(["verdict"])), "answer_review")
        self.assertEqual(analysis.call_role(call(["needs_personal_facts"])), "dependency_review")

    def test_case_order_and_component_contradictions_fail(self):
        cases = [case("first"), case("second")]
        with self.assertRaisesRegex(ValueError, "case-order prefix"):
            analysis.build(cases, [observation(cases[1])], {})
        with self.assertRaisesRegex(ValueError, "contradicts"):
            analysis.normalize_judgments([{"id": "bad", "quality_pass": True,
                "required_components_pass": [{"component": "task", "pass": False}]}])


if __name__ == "__main__":
    unittest.main()
