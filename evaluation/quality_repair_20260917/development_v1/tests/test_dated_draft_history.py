"""Calendar ranges remain editable artifacts without admitting private turns."""

import unittest

from oline_hri.reply_guard import safe_history_pair


class DatedDraftHistoryTests(unittest.TestCase):
    def test_supplied_public_event_date_range_is_admitted(self):
        for old, new, event, room in (
            ("Tuesday", "Thursday", "rehearsal", "Studio 3"),
            ("Monday", "Friday", "workshop", "Room 8"),
            ("Wednesday", "Saturday", "lecture", "Hall 21"),
        ):
            with self.subTest(old=old, new=new):
                request = f"Draft a short announcement that our {event} has moved from {old} to {new} at noon in {room}."
                answer = f"Please note that our {event} has been moved from {old} to {new} at noon in {room}."
                self.assertTrue(safe_history_pair(request, answer, drafting=True))
                edit = "Shorten that announcement and keep the weekdays, time, and room."
                shortened = f"Our {event} moves from {old} to {new} at noon in {room}."
                self.assertTrue(safe_history_pair(
                    edit, shortened, drafting=True,
                    artifact_context=request + "\n" + answer))

    def test_actual_named_recipient_is_not_hidden_by_a_calendar_range(self):
        for name in ("Alice", "Rafi", "Tuesday"):
            with self.subTest(name=name):
                request = f"Draft an invitation to {name} for a rehearsal moved from Monday to Friday at noon in Studio 3."
                answer = f"Join the rehearsal moved from Monday to Friday at noon in Studio 3."
                self.assertFalse(safe_history_pair(request, answer, drafting=True))

    def test_named_sender_is_not_hidden_by_a_calendar_range(self):
        request = "Draft an announcement from Morgan about a rehearsal moved from Monday to Friday at noon in Studio 3."
        answer = "The rehearsal moves from Monday to Friday at noon in Studio 3."
        self.assertFalse(safe_history_pair(request, answer, drafting=True))

    def test_weekday_shaped_names_in_an_unrelated_letter_are_not_exempt(self):
        self.assertFalse(safe_history_pair(
            "Write a letter from Monday to Friday thanking them for attending.",
            "Thank you for attending.", drafting=True))

    def test_personal_details_and_recalled_values_stay_withheld(self):
        requests = (
            "Draft an announcement that my appointment moved from Monday to Friday at noon in Room 3.",
            "Draft an announcement that our friend's appointment moved from Monday to Friday at noon in Room 3.",
            "Draft an announcement about the rehearsal I told you moved from Monday to Friday at noon in Room 3.",
            "I moved my appointment from Monday to Friday at noon in Room 3.",
        )
        for request in requests:
            with self.subTest(request=request):
                self.assertFalse(safe_history_pair(
                    request, "The appointment moved from Monday to Friday at noon in Room 3.", drafting=True))

    def test_public_event_still_rejects_invented_location_and_private_answer(self):
        request = "Draft an announcement that our rehearsal moved from Monday to Friday at noon in Studio 3."
        for answer in (
            "Our rehearsal moved from Monday to Friday at noon in Studio 4.",
            "Your rehearsal moved from Monday to Friday at noon in Studio 3.",
            "Our rehearsal moved from Monday to Friday at noon in Studio 3, where Alice lives.",
        ):
            with self.subTest(answer=answer):
                self.assertFalse(safe_history_pair(request, answer, drafting=True))


if __name__ == "__main__":
    unittest.main()
