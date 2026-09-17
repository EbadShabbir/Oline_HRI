import unittest

from oline_hri.supplied_plan import supplied_plan, supplied_plan_instruction, supplied_plan_issues


class SuppliedPlanTests(unittest.TestCase):
    def setUp(self):
        self.request = (
            "Turn these allocations into a practical 13-minute setup plan: "
            "2 minutes to position a basket, 4 minutes to arrange seven painted figures, "
            "5 minutes to write and place one numbered card per figure, and "
            "2 minutes for a final check. I have the basket, figures, seven cards and a pen. "
            "Use four numbered steps and state the total time."
        )

    def test_preserves_source_order_actions_and_budget(self):
        plan = supplied_plan(self.request)
        self.assertEqual([part.minutes for part in plan.allocations], [2, 4, 5, 2])
        self.assertEqual(plan.allocations[2].action, "write and place one numbered card per figure")
        self.assertEqual(plan.total, 13)
        self.assertTrue(plan.total_requested)
        instruction = supplied_plan_instruction(self.request)
        self.assertIn('"action": "arrange seven painted figures"', instruction)
        self.assertIn("total of 13 minutes inside the last step", instruction)

    def test_written_numbers_and_separate_source_clauses(self):
        request = "Keep this plan: three minutes to sort papers; five minutes for filing. Show total time."
        plan = supplied_plan(request)
        self.assertEqual([part.minutes for part in plan.allocations], [3, 5])
        self.assertEqual(plan.allocations[-1].action, "filing")
        self.assertEqual(supplied_plan_issues(request, "3 minutes: sort.\n5 minutes: file. Total: 8 minutes."), ())

    def test_synonyms_and_implicit_object_references_are_not_rejected(self):
        answer = (
            "1. 2 minutes: Set the basket centrally.\n"
            "2. 4 minutes: Put all seven figures in order.\n"
            "3. 5 minutes: Number the cards and put one beside each figure.\n"
            "4. 2 minutes: Inspect everything. Total: 13 minutes."
        )
        self.assertEqual(supplied_plan_issues(self.request, answer), ())

    def test_order_missing_duplicate_or_redistributed_durations_fail(self):
        for answer in (
            "4 minutes: arrange. 2 minutes: position. 5 minutes: label. 2 minutes: check. Total: 13 minutes.",
            "2 minutes: position. 4 minutes: arrange. 7 minutes: label and check. Total: 13 minutes.",
            "2 minutes: position. 3 minutes: arrange. 6 minutes: label. 2 minutes: check. Total: 13 minutes.",
            "2 minutes: position. 4 minutes: arrange. 5 minutes: label. 2 minutes: check. 1 minute: rest. Total: 13 minutes.",
        ):
            with self.subTest(answer=answer):
                self.assertIn("supplied_plan_timing", supplied_plan_issues(self.request, answer))

    def test_total_is_required_only_when_requested_but_must_always_be_correct(self):
        answer = "2 minutes: position. 4 minutes: arrange. 5 minutes: label. 2 minutes: check."
        self.assertEqual(supplied_plan_issues(self.request, answer), ("supplied_plan_total",))
        self.assertEqual(supplied_plan_issues(self.request, answer + " Total time: 14 minutes."), ("supplied_plan_total",))
        self.assertEqual(supplied_plan_issues(self.request, answer + " 13 minutes in total."), ())
        self.assertEqual(supplied_plan_issues(self.request, answer + " Totaling 13 minutes."), ())
        self.assertEqual(supplied_plan_issues(self.request, answer + " Totalling 13 minutes."), ())
        self.assertIn("supplied_plan_total", supplied_plan_issues(self.request, answer + " Totaling 14 minutes."))
        request = self.request.replace(" and state the total time", "")
        self.assertEqual(supplied_plan_issues(request, answer), ())

    def test_contiguous_elapsed_ranges_are_equivalent_to_supplied_allocations(self):
        answer = "0–2 min: position.\n2–6 min: arrange.\n6–11 min: label.\n11–13 min: check. Total: 13 minutes."
        self.assertEqual(supplied_plan_issues(self.request, answer), ())
        self.assertIn("supplied_plan_timing", supplied_plan_issues(self.request, answer.replace("2–6", "3–7")))

    def test_ambiguous_example_negated_or_new_allocations_are_not_claimed(self):
        for request in (
            "Make a plan totaling 13 minutes for positioning, arranging, labeling and checking.",
            "Explain why 2 minutes to sort and 4 minutes to file could be a useful plan.",
            "Use this example plan: 2 minutes to sort, 4 minutes to file.",
            "Do not use 2 minutes to sort, 4 minutes to file in the plan.",
            'Use a plan based on "2 minutes to sort, 4 minutes to file".',
            "Use a plan: about 2 minutes to sort, 4 minutes to file.",
            "Use a plan: 2–3 minutes to sort, 4 minutes to file.",
            "Use a plan: 2 minutes to sort or file, 4 minutes to check.",
            "I have 10 minutes. Use this plan: 2 minutes to sort, 4 minutes to file.",
            "Use a plan: 2 minutes to sort, 4 minutes to file. Wait 3 minutes afterward.",
            "Use a plan: 2 minutes to sort, 4 minutes to file. Add 0.5 minutes as a buffer.",
            "Use a plan: 2 minutes to sort, 4 minutes to file, and 3 seconds to pause.",
            "Use a plan: 2 minutes to sort.",
            "Use a plan: 0 minutes to sort, 4 minutes to file.",
            "Use a plan: 100 minutes to sort, 100 minutes to file.",
            None,
        ):
            with self.subTest(request=request):
                self.assertIsNone(supplied_plan(request))
                self.assertEqual(supplied_plan_instruction(request), "")
                self.assertEqual(supplied_plan_issues(request, "anything"), ())


if __name__ == "__main__":
    unittest.main()
