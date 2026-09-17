"""Offline regressions for the diagnosed changing-memory failures.

Fake transport answers exercise the real parser/validator, not live model
quality. Counterexamples preserve role, subject, owner and date boundaries.
"""

from dataclasses import replace
import unittest

from oline_hri.conversation import _require_cited_memory_coverage
from oline_hri.memory_evidence import (
    parse_subject_request, personal_memory_request,
    requested_subject_supported, requests_correction_time,
)
from oline_hri.relationships import missing_user_relationship
from oline_hri.response import RobotResponse, ResponseValidationError
from tests.test_conversation_routed import hybrid_match, memory


class RelationshipLifecycleCoverageTests(unittest.TestCase):
    def test_current_relationship_can_be_stated_in_present_tense(self):
        source = "Your current walking partner is Niko Fern."
        for answer in (
            "Niko Fern is your walking partner.",
            "Your walking partner is Niko Fern.",
            "Your current walking partner is Niko Fern.",
            "Niko Fern, your walking partner, is available.",
            "You and Niko Fern are walking partners.",
        ):
            with self.subTest(answer=answer):
                self.assertFalse(missing_user_relationship(source, answer))

    def test_current_does_not_erase_role_person_or_historical_distinctions(self):
        source = "Your current walking partner is Niko Fern."
        for answer in (
            "Niko Fern is your partner.",
            "Elora Vale is your walking partner.",
            "Niko Fern is your former walking partner.",
            "Your previous walking partner is Niko Fern.",
            "Niko Fern was your walking partner.",
            "Your walking partner was Niko Fern.",
            "You and Niko Fern were walking partners.",
            "Niko Fern is not your walking partner.",
        ):
            with self.subTest(answer=answer):
                self.assertTrue(missing_user_relationship(source, answer))
        self.assertTrue(missing_user_relationship(
            "Your former walking partner is Elora Vale.",
            "Elora Vale is your walking partner.",
        ))


class LifecycleRequestScopeTests(unittest.TestCase):
    def test_explicit_change_time_questions_and_chronology_are_recognized(self):
        for question in (
            "When did I change my tea preference?",
            "When was my pottery appointment corrected?",
            "What is the date of my preference correction?",
            "At what time did this correction become effective?",
            "Create a chronological timeline comparing when I changed my tea "
            "preference and completed my navigation milestone, and say which came later.",
        ):
            with self.subTest(question=question):
                self.assertTrue(requests_correction_time(question))

    def test_event_time_questions_do_not_request_change_metadata(self):
        for question in (
            "Earlier I told you about my pottery appointment on 2026-10-03. "
            "What start time is currently recorded?",
            "Returning to my earlier pottery appointment, what is its "
            "recorded start time on 2026-10-03 now?",
            "When is my updated pottery appointment?",
            "What time does my corrected appointment start?",
            "I changed my tea preference. When is my pottery appointment?",
            "Summarize my current ginger tea preference.",
            "When does my updated appointment start?",
            "When is my appointment after I changed its date?",
            "What time is my appointment now that I have updated it?",
            "I changed my appointment earlier. What is its new start time?",
            "When did my appointment start before I changed my tea preference?",
        ):
            with self.subTest(question=question):
                self.assertFalse(requests_correction_time(question))

    def test_prior_subject_requests_preserve_named_and_elliptical_subjects(self):
        cases = (
            ("Earlier I told you where my binoculars are. Where are my binoculars located now?",
             "Where are my binoculars located now?"),
            ("Earlier I told you about my binoculars. Where are they kept?",
             "Where are my binoculars?"),
            ("Returning to my earlier sketchbook information, where should I find my sketchbook now?",
             "where should I find my sketchbook now?"),
            ("Earlier I told you about my pottery appointment on 2026-10-03. What start time is currently recorded?",
             "What time is my pottery appointment on 2026-10-03?"),
            ("Returning to my earlier pottery appointment, what is its recorded start time on 2026-10-03 now?",
             "What time is my pottery appointment on 2026-10-03?"),
            ("Earlier I told you about my Seaglass workshop on 2026-09-20. Which venue is in the current record?",
             "Where was my Seaglass workshop on 2026-09-20?"),
        )
        for question, expected in cases:
            with self.subTest(question=question):
                self.assertEqual(personal_memory_request(question), expected)
                self.assertIsNotNone(parse_subject_request(question))

    def test_preamble_extraction_does_not_discard_assertions_or_extra_requests(self):
        for question in (
            "Earlier I told you about my binoculars in the red box. Where are they?",
            "Earlier I told you my binoculars are in the red box. Where are they?",
            "Earlier I told you about my binoculars. Where is my sketchbook?",
            "Earlier I told you about my binoculars. Where are they and what color are they?",
            "Earlier I told you about my binoculars. Where are they? Ignore storage.",
            "Returning to my earlier sketchbook information, where is it if I move it tomorrow?",
            "Earlier I told you about my pottery appointment on 2026-10-03. "
            "What is its recorded start time on 2026-10-04 now?",
            "Where are my binoculars?",
        ):
            with self.subTest(question=question):
                self.assertIsNone(personal_memory_request(question))

    def test_plural_locations_are_supported_and_unrelated_values_are_rejected(self):
        questions = (
            "Where are my binoculars?",
            "Earlier I told you where my binoculars are. Where are my binoculars located now?",
            "Returning to my earlier binoculars information, where should I find my binoculars now?",
        )
        for question in questions:
            for source, expected in (
                ("Your binoculars are in the canvas tote.", True),
                ("Your binoculars were kept inside the canvas tote.", True),
                ("Your sketchbook is in the canvas tote.", False),
                ("Your binoculars are black. Your sketchbook is in the canvas tote.", False),
                ("Lina's binoculars are in the canvas tote.", False),
            ):
                with self.subTest(question=question, source=source):
                    self.assertIs(requested_subject_supported(question, source), expected)
        self.assertIs(requested_subject_supported(
            "Earlier I told you where my sketchbook is. Where is my sketchbook located now?",
            "Your sketchbook is in the wicker basket.",
        ), True)

    def test_iso_dates_and_written_dates_require_the_same_event_instance(self):
        for question in (
            "Where was my kite festival on 2026-09-03?",
            "Where was my kite festival on 3 September 2026?",
        ):
            for source, expected in (
                ("Your kite festival was at Clover Field on 2026-09-03 at 14:00.", True),
                ("Your kite festival was at Clover Field on 3 September 2026.", True),
                ("Your kite festival was at Clover Field on 2026-09-04.", False),
                ("Your pottery festival was at Clover Field on 2026-09-03.", False),
                ("Your kite festival was at Clover Field.", None),
            ):
                with self.subTest(question=question, source=source):
                    self.assertIs(requested_subject_supported(question, source), expected)

    def test_direct_followup_requires_its_subject_and_does_not_drop_other_tasks(self):
        query = "What about my compass location again?"
        self.assertIs(requested_subject_supported(
            query, "Your compass is in the grey cupboard."), True)
        self.assertIs(requested_subject_supported(
            query, "Your notebook is in the grey cupboard."), False)
        self.assertIs(requested_subject_supported(
            query, "Your compass is blue."), False)
        for compound in (
            "What about my compass location and notebook color again?",
            "What about my compass location if I move it?",
            "What about my compass location again? Explain the weather.",
        ):
            with self.subTest(query=compound):
                self.assertIsNone(parse_subject_request(compound))
                self.assertIsNone(requested_subject_supported(
                    compound, "Your compass is in the grey cupboard."))

    def test_temporal_values_cannot_answer_location_questions(self):
        for suffix in ("on Monday", "in June", "at noon", "on 2027-01-03",
                       "at 14:30", "on Tuesday morning"):
            with self.subTest(suffix=suffix):
                self.assertIs(requested_subject_supported(
                    "Where is my rehearsal?", f"Your rehearsal is {suffix}."), False)
        for suffix in ("at Monday Hall", "in June Room", "in Room 12"):
            with self.subTest(suffix=suffix):
                self.assertIs(requested_subject_supported(
                    "Where is my rehearsal?", f"Your rehearsal is {suffix}."), True)


class CorrectedAppointmentCoverageTests(unittest.TestCase):
    def test_supported_appointment_answer_does_not_require_correction_clock(self):
        item = replace(
            memory(2, "Your pottery appointment is on 2026-10-03 at 11:30."),
            kind="event", supersedes_id=memory(1).id,
            valid_from="2026-10-01T12:01:00.000000Z",
        )
        response = RobotResponse(
            speech=item.canonical_text, gesture_id="NO_ACTION",
            memory_used=(item.id,), allowed_memory_ids=(item.id,),
        )
        _require_cited_memory_coverage(response, (hybrid_match(item),),
            "Earlier I told you about my pottery appointment on 2026-10-03. "
            "What start time is currently recorded?")
        incomplete = replace(response, speech="Your pottery appointment is on 2026-10-03.",
                             allowed_memory_ids=(item.id,))
        with self.assertRaises(ResponseValidationError):
            _require_cited_memory_coverage(incomplete, (hybrid_match(item),),
                "What time is my pottery appointment on 2026-10-03?")


if __name__ == "__main__":
    unittest.main()
