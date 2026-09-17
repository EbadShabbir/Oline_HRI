"""Offline contract checks for bounded instructions to the human."""

import json
import unittest

from oline_hri.human_guidance import (
    guidance_instruction, guidance_requested, guidance_schema, guidance_time_budget, parse_guidance,
)
from oline_hri.response import ResponseValidationError


class HumanGuidanceTests(unittest.TestCase):
    def test_explicit_practical_help_and_planning_are_eligible(self):
        for request in (
            "Help me organize a folder.", "Can you help me repair a loose hinge?",
            "I have ten minutes. Help me pack a bag.", "How do I configure a text editor?",
            "How to assemble a shelf?", "Give me a simple checklist for packing a bag.",
            "Plan a short practice session.",
            "Give me a twenty-minute plan for packing a bag.",
        ):
            with self.subTest(request=request):
                self.assertTrue(guidance_requested(request))

    def test_other_answer_contracts_and_ambiguous_help_are_excluded(self):
        for request in (
            "Help me.", "Can you help me?", "Help me with that.", "I need help.",
            "What can you do?", "Describe your capabilities.", "Explain how a hinge works.",
            "How does a text editor work?", "Help me understand recursion.",
            "Write a story about organizing a folder.", "Make it shorter.",
            "What did I pack last time?", "Use my saved packing plan.",
            "What did I choose? Help me pack a bag.",
            "Ask me what you need before helping me organize a folder.",
            "Explain hinges. Help me repair a hinge.", "",
        ):
            with self.subTest(request=request):
                self.assertFalse(guidance_requested(request))
        self.assertFalse(guidance_requested(None))

    def test_folding_and_unpacking_are_practical_actions_with_or_without_time(self):
        for request in (
            "I have twenty minutes. Help me fold laundry.", "Help me fold laundry.",
            "How can I fold clothes in ten minutes?", "Help me unpack a bag.",
            "I have five minutes. Help me unpack a bag.",
        ):
            with self.subTest(request=request):
                self.assertTrue(guidance_requested(request))
        for request in (
            "What did I fold last time?", "Write a story about unpacking a bag.",
            "Explain why folding works.", "Help me with that.",
        ):
            with self.subTest(request=request):
                self.assertFalse(guidance_requested(request))

    def test_schema_is_closed_and_fresh(self):
        schema = guidance_schema()
        self.assertEqual(schema["required"], ["steps_for_user"])
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["properties"]), {"steps_for_user"})
        schema["properties"]["steps_for_user"]["maxItems"] = 100
        self.assertEqual(guidance_schema()["properties"]["steps_for_user"]["maxItems"], 5)
        self.assertIn("human", guidance_instruction())

    def test_explicit_minute_budget_grammar_supports_digits_and_basic_written_numbers(self):
        for request, expected in (
            ("I have twenty minutes. Help me pack a bag.", 20),
            ("We only have 12 minutes. Plan a practice session.", 12),
            ("Give me a twenty-five-minute plan.", 25),
            ("Make a forty two minute plan for practicing.", 42),
            ("Help me organize a folder in sixty minutes.", 60),
            ("Help me pack in 1 minute.", 1),
            ("Help me prepare within 120 minutes.", 120),
        ):
            with self.subTest(request=request):
                self.assertEqual(guidance_time_budget(request), expected)

    def test_ambiguous_or_unsupported_durations_stay_untimed(self):
        for request in (
            "I have ten or twenty minutes.", "I have 10 minutes or 20 minutes.",
            "I have 20 minutes or so.", "I have 20 minutes, give or take a few.",
            "I have about twenty minutes.", "Make an approximately 20-minute plan.",
            "Make a ten to twenty minute plan.", "Make a 10-20-minute plan.",
            "I have 2.5 minutes.", "I have -5 minutes.", "I have zero minutes.",
            "I have 121 minutes.", "I have two hours.", "I have twenty seconds.",
            "I have 20 minutes and one hour.", "Make a one hundred twenty minute plan.",
            "Make a sixty one minute plan.", "Make a minus twenty-minute plan.",
            "I have " + "9" * 5000 + " minutes.", "Help me pack.",
        ):
            with self.subTest(request=request[:80]):
                self.assertIsNone(guidance_time_budget(request))
        self.assertIsNone(guidance_time_budget(None))

    def test_timed_schema_and_prompt_keep_plain_steps_and_app_owned_timing(self):
        self.assertEqual(guidance_schema(minutes=20), guidance_schema())
        item = guidance_schema(minutes=20)["properties"]["steps_for_user"]["items"]
        self.assertEqual(item["type"], "string")
        self.assertIn("budget is 20 minutes", guidance_instruction(minutes=20))
        self.assertIn("application adds a timer and stop rule", guidance_instruction(minutes=20))
        for instruction in (guidance_instruction(), guidance_instruction(minutes=20)):
            self.assertNotIn("Open the folder", instruction)
            self.assertNotIn("Check the result", instruction)
            self.assertNotIn("Allocate exactly", instruction)

    def test_short_time_budgets_still_allow_up_to_five_quick_instructions(self):
        for minutes in (1, 2, 4, 5, 20, None):
            with self.subTest(minutes=minutes):
                array = guidance_schema(minutes=minutes)["properties"]["steps_for_user"]
                self.assertEqual(array["minItems"], 1)
                self.assertEqual(array["maxItems"], 5)
        response = parse_guidance(json.dumps({"steps_for_user": [
            "Pause.", "Look around.", "Choose one item.", "Put it away.", "Stop.",
        ]}), minutes=1)
        self.assertTrue(response.speech.startswith("Set a 1-minute timer."))

    def test_timer_and_stop_framing_use_only_the_supplied_budget(self):
        content = json.dumps({"steps_for_user": [
            "Gather the packing materials.", "Wrap each fragile item separately.",
        ]})
        response = parse_guidance(content, minutes=20)
        self.assertEqual(response.speech,
                         "Set a 20-minute timer. 1. Gather the packing materials. "
                         "2. Wrap each fragile item separately. Stop when it rings.")
        self.assertEqual(response.memory_used, ())
        self.assertEqual(response.gesture_id, "NO_ACTION")
        self.assertEqual(json.loads(content)["steps_for_user"], [
            "Gather the packing materials.", "Wrap each fragile item separately.",
        ])
        self.assertNotIn("timer", parse_guidance(content).speech)

    def test_timed_schema_rejects_old_duration_objects_and_wrong_step_types(self):
        for steps in (
            [{"minutes": 10, "instruction": "Gather the materials."}],
            [{"instruction": "Gather the materials."}],
            [10], [True], [None], [{}], [["Gather the materials."]],
        ):
            with self.subTest(steps=steps):
                with self.assertRaises(ResponseValidationError):
                    parse_guidance(json.dumps({"steps_for_user": steps}), minutes=10)

    def test_invalid_budget_arguments_fail_closed(self):
        for minutes in (True, False, 0, -1, 121, 10.0, "10", []):
            with self.subTest(minutes=minutes):
                for function in (guidance_schema, guidance_instruction):
                    with self.assertRaises(ResponseValidationError):
                        function(minutes=minutes)
                with self.assertRaises(ResponseValidationError):
                    parse_guidance('{"steps_for_user":["Gather supplies."]}', minutes=minutes)

    def test_model_authored_list_markers_are_rejected_in_both_formats(self):
        for instruction in ("1. Please provide more details.", "1) Open the box.",
                            "(1) Open the box.", "a. Open the box.", "ii) Open the box.",
                            "Step 1: Open the box.", "- Open the box.", "* Open the box.",
                            "• Open the box.", "— Open the box."):
            with self.subTest(instruction=instruction):
                for minutes, steps in ((None, [instruction]), (10, [instruction])):
                    with self.assertRaises(ResponseValidationError):
                        parse_guidance(json.dumps({"steps_for_user": steps}), minutes=minutes)

    def test_instructions_are_numbered_without_model_metadata_or_memory_authority(self):
        raw = json.dumps({"steps_for_user": [" Open the folder. ", "Group related files together."]})
        response = parse_guidance(raw)
        self.assertEqual(response.speech, "1. Open the folder. 2. Group related files together.")
        self.assertEqual(response.gesture_id, "NO_ACTION")
        self.assertEqual(response.memory_used, ())
        self.assertEqual(json.loads(raw)["steps_for_user"][0], " Open the folder. ")

    def test_parser_does_not_need_an_imperative_verb_whitelist(self):
        response = parse_guidance(json.dumps({"steps_for_user": [
            "Loosen the screw slightly.", "If it resists, stop and inspect the thread.",
            "Carefully align the two pieces.",
        ]}))
        self.assertIn("3. Carefully align", response.speech)

    def test_missing_extra_duplicate_and_nonstandard_fields_are_rejected(self):
        for content in (
            "[]", "{}", '{"speech":"Open the folder."}',
            '{"steps_for_user":["Open the folder."],"memory_used":[]}',
            '{"steps_for_user":[],"steps_for_user":["Open the folder."]}',
            '{"steps_for_user":NaN}', '{"steps_for_user":["Open the folder."]} trailing',
            '```json\n{"steps_for_user":["Open the folder."]}\n```', None, " " * 8193,
        ):
            with self.subTest(content=repr(content)[:90]):
                with self.assertRaises(ResponseValidationError):
                    parse_guidance(content)

    def test_steps_require_exact_types_and_one_to_five_short_values(self):
        for steps in (None, "Open the folder.", {}, [], [True], [1], [{}], [None], [" "],
                      ["a" * 241], ["Open the folder."] * 6):
            with self.subTest(steps=steps):
                with self.assertRaises(ResponseValidationError):
                    parse_guidance(json.dumps({"steps_for_user": steps}))

    def test_first_person_and_robot_actor_forms_are_rejected(self):
        for step in (
            "I'll open the folder.", "First, I will sort the files.", "We can check the result.",
            "I am gathering supplies.", "Then we'll arrange everything.",
            "Let's start by collecting everything.", "Let us do the work.",
            "The robot will open the box.", "The assistant can sort the items.",
            'Write the label "I will help".',
        ):
            with self.subTest(step=step):
                for minutes in (None, 20):
                    with self.assertRaises(ResponseValidationError):
                        parse_guidance(json.dumps({"steps_for_user": [step]}), minutes=minutes)

    def test_control_characters_and_internal_identifiers_are_rejected(self):
        for step in ("Open\nthe folder.", "Open\tthe folder.", "Open\x00the folder.",
                     "Open\u202ethe folder.", "Read mem_" + "0" * 32 + "."):
            with self.subTest(step=step):
                for minutes in (None, 20):
                    with self.assertRaises(ResponseValidationError):
                        parse_guidance(json.dumps({"steps_for_user": [step]}), minutes=minutes)

    def test_total_word_limit_includes_application_numbering(self):
        accepted = ["Go " * 19 + "now."] * 3 + ["Go " * 15 + "now."]
        response = parse_guidance(json.dumps({"steps_for_user": accepted}))
        self.assertEqual(len(response.speech.split()), 80)
        too_long = [*accepted[:3], accepted[3] + " Stop."]
        with self.assertRaises(ResponseValidationError):
            parse_guidance(json.dumps({"steps_for_user": too_long}))

    def test_timed_word_limit_includes_timer_stop_rule_and_numbering(self):
        steps = ["Go " * 12 + "now."] * 4 + ["Go " * 14 + "now."]
        response = parse_guidance(json.dumps({"steps_for_user": steps}), minutes=10)
        self.assertEqual(len(response.speech.split()), 80)
        steps[-1] += " Stop."
        with self.assertRaises(ResponseValidationError):
            parse_guidance(json.dumps({"steps_for_user": steps}), minutes=10)


if __name__ == "__main__":
    unittest.main()
