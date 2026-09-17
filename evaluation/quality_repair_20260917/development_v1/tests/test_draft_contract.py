"""Source-bound editing constraints retain facts without claiming memory."""

import unittest

from oline_hri.draft_contract import draft_contract, draft_contract_issues, draft_instruction


class DraftContractTests(unittest.TestCase):
    def setUp(self):
        self.request = ("Shorten that announcement to no more than 16 words. "
                        "Keep the old and new weekdays, the time, and the room. "
                        "Return only the announcement.")
        self.source = ("Please note that our rehearsal has been moved from "
                       "Tuesday to Thursday at noon in Studio 3.")

    def test_omitted_facts_are_detected_even_when_word_limit_passes(self):
        contract = draft_contract(self.request, self.source)
        self.assertEqual(set(draft_contract_issues(contract, "Please note the change.")),
                         {"draft_weekdays", "draft_time", "draft_location", "draft_subject"})
        self.assertEqual(contract.weekday_move, ("Tuesday", "Thursday"))
        self.assertEqual(contract.max_words, 16)

    def test_concise_faithful_paraphrase_does_not_require_every_source_word(self):
        contract = draft_contract(self.request, self.source)
        for answer in (
            "Rehearsal moves from Tuesday to Thursday at noon in Studio 3.",
            "Rehearsal: Thursday instead of Tuesday, 12:00, Studio #3.",
            "Rehearsal now meets Thursday at midday in Studio 3, previously Tuesday.",
            "Rehearsal: Tue. → Thu., 12 p.m., Studio 3.",
        ):
            with self.subTest(answer=answer):
                self.assertEqual(draft_contract_issues(contract, answer), ())

    def test_reversed_move_changed_room_time_subject_and_extra_day_fail(self):
        contract = draft_contract(self.request, self.source)
        examples = {
            "draft_move_direction": "Rehearsal moves from Thursday to Tuesday at noon in Studio 3.",
            "draft_location": "Rehearsal moves from Tuesday to Thursday at noon in Studio 4.",
            "draft_time": "Rehearsal moves from Tuesday to Thursday at midnight in Studio 3.",
            "draft_subject": "Workshop moves from Tuesday to Thursday at noon in Studio 3.",
            "draft_weekdays": "Rehearsal moves Tuesday to Thursday, with Sunday practice at noon in Studio 3.",
        }
        for issue, answer in examples.items():
            with self.subTest(issue=issue):
                self.assertIn(issue, draft_contract_issues(contract, answer))
        self.assertIn("draft_move_direction", draft_contract_issues(
            contract, "Rehearsal moves to Tuesday from Thursday at noon in Studio 3."))

    def test_whitespace_word_limit_counts_the_delivered_artifact(self):
        contract = draft_contract(self.request, self.source)
        self.assertEqual(draft_contract_issues(contract, "\nRehearsal moves from Tuesday to Thursday at noon in Studio 3.\n"), ())
        self.assertIn("draft_word_limit", draft_contract_issues(
            contract, "Please note the following important announcement today: rehearsal has moved from Tuesday to Thursday at noon in Studio 3."))

    def test_constraints_are_source_derived_not_specific_to_one_event(self):
        source = "The pottery workshop is rescheduled from Monday to Friday at 2:45 p.m. in Room 27B."
        contract = draft_contract("Condense that announcement to at most twenty words.", source)
        self.assertEqual(contract.subject_terms, ("pottery", "workshop"))
        self.assertEqual(contract.times, ((14, 45),))
        self.assertEqual(contract.locations, (("room", "27b"),))
        self.assertEqual(draft_contract_issues(
            contract, "Pottery workshop: Friday rather than Monday, 14:45, room 27B."), ())
        self.assertIn("draft_subject", draft_contract_issues(
            contract, "Workshop: Friday rather than Monday, 14:45, room 27B."))

    def test_current_quoted_source_takes_precedence_over_previous_artifact(self):
        request = ('Rewrite this announcement in at most 18 words: '
                   '"The lecture starts Friday at 09:30 in Hall 8."')
        contract = draft_contract(request, self.source)
        self.assertEqual(contract.weekdays, ("Friday",))
        self.assertEqual(contract.subject_terms, ("lecture",))
        self.assertEqual(draft_contract_issues(contract, "Lecture: Friday, 9:30, Hall 8."), ())

    def test_multiple_quoted_sources_are_not_silently_resolved(self):
        request = ('Shorten the announcement: "The lecture starts Friday at 9:30." '
                   '"The workshop starts Monday at 14:00."')
        self.assertIsNone(draft_contract(request, self.source))

    def test_no_source_means_no_invented_contract_or_history_lookup(self):
        self.assertIsNone(draft_contract(self.request))
        self.assertEqual(draft_contract_issues(None, "Anything"), ())
        self.assertEqual(draft_instruction(None), "")

    def test_arbitrary_personal_history_and_assistant_guesses_are_rejected(self):
        for source in (
            "Your rehearsal moved from Tuesday to Thursday at noon in Studio 3.",
            "My birthday party starts Tuesday at noon in Room 3.",
            "I think the rehearsal moved from Tuesday to Thursday at noon in Studio 3.",
            "Perhaps the rehearsal moved from Tuesday to Thursday at noon in Studio 3.",
            "I guessed the rehearsal moved from Tuesday to Thursday at noon in Studio 3.",
        ):
            with self.subTest(source=source):
                self.assertIsNone(draft_contract(self.request, source))
        self.assertIsNone(draft_contract("Rewrite my earlier appointment details in at most 12 words.", self.source))
        self.assertIsNone(draft_contract("What day did I say the rehearsal moved to?", self.source))

    def test_requested_changes_do_not_require_old_category_values(self):
        changes = (
            ("Change Thursday to Friday.", "Rehearsal moves from Tuesday to Friday at noon in Studio 3."),
            ("Change the time to midnight.", "Rehearsal moves from Tuesday to Thursday at midnight in Studio 3."),
            ("Replace Studio 3 with Studio 4.", "Rehearsal moves from Tuesday to Thursday at noon in Studio 4."),
            ("Drop the room.", "Rehearsal moves from Tuesday to Thursday at noon."),
        )
        for change, answer in changes:
            with self.subTest(change=change):
                contract = draft_contract("Rewrite that announcement. " + change, self.source)
                self.assertEqual(draft_contract_issues(contract, answer), ())

    def test_changing_tone_still_preserves_facts_but_new_artifact_does_not(self):
        contract = draft_contract("Rewrite that announcement. Change its tone but keep the weekdays and room.", self.source)
        self.assertIn("draft_weekdays", draft_contract_issues(contract, "An announcement."))
        for request in (
            "Rewrite that announcement as a poem about stars.",
            "Rewrite that announcement about a different event.",
            "Rewrite that announcement. Change the subject to astronomy.",
        ):
            with self.subTest(request=request):
                self.assertIsNone(draft_contract(request, self.source))

    def test_negated_change_still_requires_the_original_facts(self):
        request = "Shorten that announcement. Do not change the time. Don't replace the room."
        contract = draft_contract(request, self.source)
        self.assertEqual(contract.times, ((12, 0),))
        self.assertEqual(contract.locations, (("studio", "3"),))
        self.assertIn("draft_time", draft_contract_issues(
            contract, "Rehearsal moves from Tuesday to Thursday at midnight in Studio 3."))

    def test_clock_equivalence_and_space_normalization(self):
        source = "The lecture starts Monday at 11\u00a0a.m. in Laboratory 6."
        contract = draft_contract("Shorten that announcement.", source)
        self.assertEqual(contract.times, ((11, 0),))
        self.assertEqual(draft_contract_issues(contract, "Lecture: Monday, 11:00, Lab 6."), ())

    def test_word_limit_variants_and_quoted_limits(self):
        for text, expected in (("at most sixteen", 16), ("under 17", 16),
                               ("no more than 16", 16), ("maximum of 16", 16),
                               ("<=16", 16)):
            with self.subTest(text=text):
                self.assertEqual(draft_contract(f"Shorten that announcement to {text} words.", self.source).max_words, expected)
        contract = draft_contract('Rewrite this note: "Use no more than 16 words when writing."')
        self.assertIsNone(contract)

    def test_plain_prose_does_not_require_copying_all_source_words(self):
        contract = draft_contract('Shorten "The bright little bird sings beautifully." to at most 8 words.')
        self.assertEqual(contract.subject_terms, ())
        self.assertEqual(draft_contract_issues(contract, "A small bird chirps."), ())

    def test_guidance_contains_actual_anchors_and_the_count(self):
        instruction = draft_instruction(draft_contract(self.request, self.source))
        for expected in ("16", "rehearsal", "FROM Tuesday TO Thursday", "12:00", "studio 3"):
            with self.subTest(expected=expected):
                self.assertIn(expected, instruction)


if __name__ == "__main__":
    unittest.main()
