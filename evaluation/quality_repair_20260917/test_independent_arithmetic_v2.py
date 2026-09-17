"""Synthetic independent arithmetic audit checks; no production imports."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("arithmetic_audit_checks", Path(__file__).with_name("independent_arithmetic_v2.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class IndependentArithmeticTests(unittest.TestCase):
    def test_exact_operations_and_fraction_intermediates(self):
        examples = [("9*5-2", "Five containers hold nine counters; remove two.", "43"),
                    ("(12+8)/4", "Share twelve plus eight among four.", "5"),
                    ("(10/3)*3", "Use 10 and 3.", "10"),
                    ("-8+3", "Change -8 by 3.", "-5"),
                    ("0*5", "Multiply zero by five.", "0")]
        for expression, request, expected in examples:
            self.assertEqual(module.compute_expression(expression, request), expected)

    def test_cardinals_are_whole_operands_and_conjunctions_split_only_when_needed(self):
        for text, expected in [("twenty-one and four", {21, 4}),
                ("one hundred and twenty-three, plus seven", {123, 7}),
                ("two thousand and fifteen, plus five", {2015, 5}),
                ("1,200 plus 30", {1200, 30}), ("one million minus one", {1000000, 1})]:
            self.assertEqual(module.supplied_magnitudes(text), expected)

    def test_decimal_scientific_malformed_and_large_values_are_not_partial_operands(self):
        for text in ("2.5 plus 3.5", "2e3", "0x10", "1,20", "one billion", "two million"):
            self.assertEqual(module.supplied_magnitudes(text), frozenset())

    def test_unsupported_code_operators_unsupplied_values_and_nonintegers_fail(self):
        for expression in ("abs(-8)", "8**3", "8//3", "8%3", "8<<3", "8e0+3", "8.0+3",
                           "8\n+3", "8+1", "11", "8/3", "8/(3-3)"):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                module.compute_expression(expression, "Use 8 and 3.")

    def test_length_depth_node_intermediate_and_result_bounds(self):
        for expression, request in [("8+"*100+"8", "Use 8."), ("8+"*30+"8", "Use 8."),
                ("-"*20+"8", "Use 8."), ("1000001+1", "Use 1000001 and 1."),
                ("1000000*1000000", "Use one million."),
                ("1000000*1000000*1000000", "Use one million.")]:
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                module.compute_expression(expression, request)

    def test_arithmetic_selection_rejects_quoted_intent_conversions_and_missing_values(self):
        self.assertTrue(module.arithmetic_directive("Calculate 8 divided by 2."))
        for request in ('Explain "calculate 8 plus 2".', "Convert 8 meters into 2 other units.",
                        "How many sides does a triangle have?", "Write a note about 8 and 2."):
            self.assertFalse(module.arithmetic_directive(request))


if __name__ == "__main__":
    unittest.main()
