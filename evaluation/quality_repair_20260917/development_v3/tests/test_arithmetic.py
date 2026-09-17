"""Exact arithmetic is bounded and uses only current supplied operands."""

import unittest

from oline_hri.arithmetic import (
    arithmetic_request, evaluate_integer_expression, expression_instruction, supplied_integer_operands,
)
from oline_hri.response import ResponseValidationError


class ArithmeticTests(unittest.TestCase):
    def test_varied_operations_compute_instead_of_guessing_the_result(self):
        examples = (
            ("7*4+3", "Seven counters in each of four bags, plus three extra counters.", "31"),
            ("9*5-2", "Five boxes each hold nine tiles; remove two tiles.", "43"),
            ("(12+8)/4", "Share twelve red and eight blue tokens among four groups.", "5"),
            ("24/6", "Divide 24 equally among 6 people.", "4"),
            ("-8+3", "The starting value is -8; increase it by 3.", "-5"),
            ("(10-4)*3", "Take 4 from 10 and multiply the difference by 3.", "18"),
            ("0*5", "Multiply zero by five.", "0"),
        )
        for expression, request, expected in examples:
            with self.subTest(expression=expression):
                self.assertEqual(evaluate_integer_expression(expression, request), expected)

    def test_fraction_intermediates_remain_exact(self):
        self.assertEqual(evaluate_integer_expression("(10/3)*3", "Divide 10 by 3, then multiply by 3."), "10")
        self.assertEqual(evaluate_integer_expression("(7/2)+(7/2)", "Add two copies of 7 divided by 2."), "7")

    def test_cardinal_words_and_grouped_digits_are_whole_operands(self):
        examples = (
            ("twenty-one and four", {21, 4}),
            ("one hundred and twenty-three, plus seven", {123, 7}),
            ("two thousand and fifteen, plus five", {2015, 5}),
            ("1,200 plus 30", {1200, 30}),
            ("one million minus one", {1000000, 1}),
        )
        for request, expected in examples:
            with self.subTest(request=request):
                self.assertEqual(supplied_integer_operands(request), frozenset(expected))
        self.assertEqual(evaluate_integer_expression("123-7", "Subtract seven from one hundred and twenty-three."), "116")

    def test_absent_constants_and_guessed_answers_are_rejected(self):
        request = "Multiply 7 by 4, then add 3. Return only the integer."
        for expression in ("23", "31", "7", "7*4+1", "7*4+0", "7*4+8"):
            with self.subTest(expression=expression), self.assertRaises(ResponseValidationError):
                evaluate_integer_expression(expression, request)
        # Constants are permitted only when actually supplied, not by convention.
        self.assertEqual(evaluate_integer_expression("7+0", "Add zero to seven."), "7")

    def test_bare_operand_is_allowed_only_when_there_is_one_distinct_value(self):
        self.assertEqual(evaluate_integer_expression(" 8 ", "Return the integer eight."), "8")
        with self.assertRaises(ResponseValidationError):
            evaluate_integer_expression("8", "There are 8 red tokens and 3 blue tokens.")

    def test_code_execution_and_unapproved_operators_are_rejected(self):
        for expression in (
            "__import__('os').system('true')", "abs(-8)", "sum([8,3])",
            "8**3", "8//3", "8%3", "8<<3", "8^3", "8 and 3",
            "[8,3]", "(8,3)", "{'value':8}", "x+3", "True+3",
            "8;3", "8=3", "8\n+3", "8\t+3", "８+3", "8×3",
            "0x8+3", "8e0+3", "8.0+3", "8_000+3",
        ):
            with self.subTest(expression=expression), self.assertRaises(ResponseValidationError):
                evaluate_integer_expression(expression, "Use 8 and 3.")

    def test_division_by_zero_and_non_integer_results_are_rejected(self):
        for expression, request in (
            ("8/0", "Divide eight by zero."),
            ("8/(3-3)", "Use eight and three."),
            ("8/3", "Divide eight by three."),
        ):
            with self.subTest(expression=expression), self.assertRaises(ResponseValidationError):
                evaluate_integer_expression(expression, request)

    def test_length_node_depth_and_magnitude_limits(self):
        examples = (
            ("8+" * 100 + "8", "Use eight."),
            ("8+" * 30 + "8", "Use eight."),
            ("-" * 20 + "8", "Use eight."),
            ("1000001+1", "Use 1000001 and 1."),
            ("1000000*1000000*1000000", "Multiply one million by itself."),
            ("1000000*1000000", "Multiply one million by itself."),
        )
        for expression, request in examples:
            with self.subTest(expression=expression), self.assertRaises(ResponseValidationError):
                evaluate_integer_expression(expression, request)

    def test_decimal_scientific_and_malformed_digit_groups_do_not_supply_partial_integers(self):
        for request in ("2.5 plus 3.5", "2e3", "0x10", "1,20", "one billion", "two million"):
            with self.subTest(request=request):
                self.assertEqual(supplied_integer_operands(request), frozenset())
                with self.assertRaises(ResponseValidationError):
                    evaluate_integer_expression("2+3", request)

    def test_no_history_memory_or_implicit_general_knowledge_operands(self):
        for request in ("What total did I mention before?", "How many sides does a triangle have?", ""):
            with self.subTest(request=request), self.assertRaises(ResponseValidationError):
                evaluate_integer_expression("3", request)
        for expression in (None, 8, "", "()", "8+"):
            with self.subTest(expression=expression), self.assertRaises(ResponseValidationError):
                evaluate_integer_expression(expression, "Use eight and three.")

    def test_instruction_requests_an_expression_and_exposes_only_supplied_numbers(self):
        instruction = expression_instruction("Multiply nine by four, then add two.")
        self.assertIn("2, 4, 9", instruction)
        self.assertIn("not a guessed result", instruction)
        self.assertIn("application computes", instruction)

    def test_selection_requires_arithmetic_intent_and_supplied_quantities(self):
        for request in ("How many tokens are in four packs of seven, plus three extras?",
                        "Calculate 8 divided by 2.", "What is twenty-one plus four?"):
            with self.subTest(request=request):
                self.assertTrue(arithmetic_request(request))
        for request in ("How many sides does a triangle have?", "Return the integer eight.",
                        "Write a note mentioning 8 and 3.", "Convert 8 meters into 3 other units.",
                        'Explain the instruction "calculate 8 plus 3".'):
            with self.subTest(request=request):
                self.assertFalse(arithmetic_request(request))


if __name__ == "__main__":
    unittest.main()
