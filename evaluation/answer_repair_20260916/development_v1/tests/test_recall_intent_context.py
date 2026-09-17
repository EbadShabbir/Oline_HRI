"""Bounded intent contrasts: first-person language is not a recall decision."""

import unittest

from oline_hri.memory_evidence import parse_subject_request
from oline_hri.reply_guard import (
    current_assertions, has_personal_record_question, has_unstated_recall_intent, inspect_reply,
)


class RecallIntentContextTests(unittest.TestCase):
    def test_first_person_and_possessives_alone_do_not_request_memory(self):
        for text in (
            "Can you help me plan my day?", "How can I organize my desk?",
            "I feel tired. Suggest a simple activity.", "I could use some help.",
            "What do I need to do to learn guitar?",
            "What can I improve in my previous essay?",
        ):
            with self.subTest(text=text):
                self.assertFalse(has_unstated_recall_intent(text))

    def test_inverted_obligation_is_distinct_from_a_past_event(self):
        for text in ("What have I got to do to learn guitar?",
                     "What have I to do before I start?",
                     "What had I better do if my screen freezes?"):
            with self.subTest(text=text):
                self.assertFalse(has_personal_record_question(text))
                self.assertFalse(has_unstated_recall_intent(text))
        for text in ("What have I done to prepare for the trip?",
                     "What had I chosen before the change?"):
            with self.subTest(text=text):
                self.assertTrue(has_unstated_recall_intent(text))

    def test_error_analysis_uses_the_work_supplied_in_the_question(self):
        for text in (
            "What did I spell wrong in the word recieve?",
            "What did I do wrong in 8 + 4 = 13?",
            'What did I write wrong in the sentence "She walk home"?',
            "What have I left after spending 20 from a total of 100?",
        ):
            with self.subTest(text=text):
                self.assertFalse(has_personal_record_question(text))
                self.assertFalse(has_unstated_recall_intent(text))
        for text in ("What did I do wrong in my exam?",
                     "What did I spell wrong in the previous letter?",
                     "What did I tell you about the word recieve?",
                     "What have I left after moving out of my flat?"):
            with self.subTest(text=text):
                self.assertTrue(has_unstated_recall_intent(text))

    def test_procedural_location_does_not_force_a_stored_location(self):
        for text in ("Where can I find my settings in Android?",
                     "Where should I find my downloaded files?"):
            with self.subTest(text=text):
                # Retrieval interpretation remains available to historical
                # callers; it does not establish dependency by itself.
                self.assertIsNotNone(parse_subject_request(text))
                self.assertFalse(has_unstated_recall_intent(text))

    def test_actual_unstated_values_do_not_need_remember_keyword(self):
        for text in (
            "Where are my keys?", "What time is my appointment?",
            "Which fabric did I choose for the bag?",
            "Who is Rowan in relation to me?",
            "What is the current saved time after the correction?",
            "What did I tell you about my appointment last time?",
            "What is my previous decision?", "Show me my saved address.",
            "What does the previous record say?",
            "Who led my previous lesson?", "Use my saved itinerary.",
        ):
            with self.subTest(text=text):
                self.assertTrue(has_unstated_recall_intent(text))

    def test_stored_input_reference_is_not_a_supplied_value(self):
        for text in ("Use my saved itinerary.", "Retrieve my recorded preference."):
            with self.subTest(text=text):
                self.assertEqual(current_assertions(text), ())
                self.assertTrue(has_unstated_recall_intent(text))

    def test_current_values_can_answer_the_following_request(self):
        for text in (
            "My camera is in the drawer. Where is my camera?",
            "I chose linen. Which fabric did I choose for the bag?",
            "Rowan is my cousin. Who is Rowan in relation to me?",
            "My appointment starts at 3 PM. What time is my appointment?",
        ):
            with self.subTest(text=text):
                self.assertFalse(has_unstated_recall_intent(text))

    def test_unsupplied_answers_still_need_independent_evidence(self):
        for text, reply in (("Where are my keys?", "Your keys are in the drawer."),
                            ("Which fabric did I choose for the bag?", "Linen."),
                            ("Who is Rowan in relation to me?", "Your cousin.")):
            with self.subTest(text=text):
                self.assertIn("unsupported_personal_claim", inspect_reply(text, reply))


if __name__ == "__main__":
    unittest.main()
