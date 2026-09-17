"""Offline checks for app-owned durations, not task feasibility or semantics."""

import json
import re
import unittest

from oline_hri.human_guidance import allocation_plan, guidance_schema, guidance_instruction, parse_guidance
from oline_hri.response import ResponseValidationError


class AllocationGuidanceTests(unittest.TestCase):
    def test_direct_plans_and_explicit_counts(self):
        for request, expected in (
            ("Give a timed plan totaling 11 minutes for arranging a shelf.", (11, None)),
            ("I have 9 minutes. Give three phases for preparing a display totaling 9 minutes.", (9, 3)),
            ("Give a four-step preparation plan totaling fourteen minutes.", (14, 4)),
            ("I have twelve minutes. Give a timed plan for packing a bag.", (12, None)),
            ("Help me pack a bag. Assign durations totaling 10 minutes.", (10, None)),
            ("Give an 18-minute plan for preparing a display in three phases, totaling 18 minutes.", (18, 3)),
            ("Give a 10-minute plan for arranging supplies, totaling 10 minutes.", (10, None)),
        ):
            with self.subTest(request=request):
                self.assertEqual(allocation_plan(request), expected)

    def test_discussion_ambiguous_fixed_or_mixed_contracts_are_excluded(self):
        for request in (
            "Explain why a plan totaling 11 minutes might help.",
            "A timed plan totaling 11 minutes was useful yesterday.",
            "Give a plan totaling 10 minutes. Spend 4 minutes checking the box.",
            "Give a plan totaling 10 minutes and 20 minutes.",
            "Give a timed plan within about 10 minutes.",
            "Give a plan totaling 10 minutes or so.",
            "Give a timed plan totaling 0 minutes.",
            "Give a timed plan totaling 121 minutes.",
            "Give five steps totaling 3 minutes.",
            "Give six steps totaling 12 minutes.",
            "Give three steps and four phases totaling 12 minutes.",
            "Give a plan totaling 10 minutes and write three clue cards.",
            "Give a plan totaling 10 minutes. Explain how it works.",
            "Give a timed plan using my saved schedule totaling 10 minutes.",
            "Give a timetable from 10:00 until 10:10 totaling 10 minutes.",
            "I have ten minutes. Help me pack a bag.",
            None,
        ):
            with self.subTest(request=request):
                self.assertIsNone(allocation_plan(request))

    def test_closed_schema_count_and_budget_bounds(self):
        array = guidance_schema(allocation_minutes=11, step_count=3)["properties"]["steps_for_user"]
        self.assertEqual((array["minItems"], array["maxItems"]), (3, 3))
        self.assertEqual(array["items"], {"type": "string", "minLength": 1, "maxLength": 240})
        self.assertEqual(guidance_schema(allocation_minutes=2)["properties"]["steps_for_user"]["maxItems"], 2)
        prompt = guidance_instruction(allocation_minutes=11, step_count=3)
        self.assertIn("exactly 3", prompt)
        self.assertIn("starting location and final destination", prompt)
        self.assertIn("finish before the main activity", prompt)

    def test_rendered_positive_durations_sum_to_budget_and_raw_stays_plain(self):
        raw = json.dumps({"steps_for_user": ["Gather the supplied materials.", "Arrange the materials.", "Check everything is ready."]})
        answer = parse_guidance(raw, allocation_minutes=11, step_count=3)
        self.assertEqual(answer.speech.splitlines(), [
            "1. 4 minutes: Gather the supplied materials.",
            "2. 4 minutes: Arrange the materials.",
            "3. 3 minutes: Check everything is ready.",
        ])
        self.assertEqual(sum(map(int, re.findall(r"(\d+) minutes", answer.speech))), 11)
        self.assertEqual(answer.memory_used, ())
        self.assertEqual(answer.gesture_id, "NO_ACTION")
        self.assertNotIn("minutes", raw)

    def test_invalid_parameters_count_or_model_timing_fail_closed(self):
        for kwargs in ({"minutes": 10, "allocation_minutes": 10}, {"allocation_minutes": 1},
                       {"allocation_minutes": True}, {"allocation_minutes": 10, "step_count": True},
                       {"allocation_minutes": 2, "step_count": 3}, {"step_count": 3}):
            for function in (guidance_schema, guidance_instruction):
                with self.subTest(kwargs=kwargs, function=function.__name__):
                    with self.assertRaises(ResponseValidationError):
                        function(**kwargs)
        for steps in (["Gather materials."], ["Gather materials."] * 4,
                      ["Gather materials for 3 minutes.", "Arrange them.", "Check them."]):
            with self.subTest(steps=steps):
                with self.assertRaises(ResponseValidationError):
                    parse_guidance(json.dumps({"steps_for_user": steps}), allocation_minutes=11, step_count=3)


if __name__ == "__main__":
    unittest.main()
