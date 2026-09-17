"""Format repairs checked on alternate wording and adversarial payloads."""

import json
import unittest

from oline_hri.response import ResponseValidationError
from oline_hri.task_contract import task_contract_issues, requested_count, clarification_question
from oline_hri.task_parts import task_layout, parse_parts
from oline_hri.ollama import ChatMessage
from test_conversation_routed import FakeBackend, GENERAL_LARGE_MODEL, chat_result
from test_reliable_conversation import reliable, semantic_route


class FormatRepairTests(unittest.TestCase):
    def render(self, request, parts):
        return parse_parts(json.dumps({"answer_parts": parts}), task_layout(request)).speech

    def test_numbered_lines_and_user_prefixes_preserve_content(self):
        request = "Give exactly three numbered lines. Begin their text with First:, Next:, and Last: in that order."
        answer = self.render(request, ["Gather paper.", "Fold it.", "Open it."])
        self.assertEqual(answer, "1. First: Gather paper.\n2. Next: Fold it.\n3. Last: Open it.")
        self.assertEqual(task_contract_issues(request, answer), ())
        self.assertIn("requested_numbering", task_contract_issues(request, "Gather.\nFold.\nOpen."))

    def test_csv_header_comes_only_from_requested_header(self):
        for directive in ("The header must be zone,count.", "with header `zone,count`."):
            request = "Return CSV " + directive
            self.assertEqual(self.render(request, ["east,3", "west,8"]), "zone,count\neast,3\nwest,8")
            self.assertEqual(self.render(request, ["zone,count", "east,3"]), "zone,count\nzone,count\neast,3")
            self.assertIn("requested_csv", task_contract_issues(request, "place,count\neast,3"))
        self.assertIsNone(task_layout("Explain a header called zone,count."))

    def test_integer_output_does_not_admit_explanation_or_expression(self):
        request = "What is six times eight? Return only the whole number."
        self.assertEqual(self.render(request, ["48"]), "48")
        for value in ("The answer is 48", "6*8=48", "48 beads", "4.8", "48\nExtra"):
            with self.subTest(value=value), self.assertRaises(ResponseValidationError):
                self.render(request, [value])
        self.assertIsNone(task_layout("Explain why 48 is a whole number."))
        self.assertEqual(task_layout('Explain the instruction "Return only the integer" in two sentences.').kind, "sentences")
        self.assertIsNone(task_layout("Do not return only the integer; explain the reasoning."))
        self.assertEqual(self.render("Write two lines. Do not use labels First:, Last:.", ["Red", "Blue"]), "Red\nBlue")
        self.assertFalse(task_layout("Explain a numbered list in exactly two lines.").numbered)
        self.assertEqual(task_layout('Explain the syntax "labels First:, Last:" in exactly two lines.').prefixes, ())
        self.assertEqual(task_layout('Return CSV from the text "header old,value". Use header new,value.').header, "new,value")

    def test_names_on_separate_lines_excludes_extra_introduction(self):
        request = "Suggest two possible names for a fictional cafe. Return just the names on separate lines."
        self.assertEqual(self.render(request, ["Cloud Cup", "Saffron Sky"]), "Cloud Cup\nSaffron Sky")
        with self.assertRaises(ResponseValidationError):
            self.render(request, ["Here are names", "Cloud Cup", "Saffron Sky"])
        self.assertIsNone(task_layout("The two possible names are in a document. Explain naming."))

    def test_new_modifiers_keep_bounds_and_input_quantities_out(self):
        self.assertEqual(requested_count("Suggest one pen-and-paper activity.", "activity"), 1)
        self.assertEqual(requested_count("Use exactly five numbered steps.", "step"), 5)
        for request in ("Use at most five numbered steps.", "The source has five numbered steps.",
                        'Use the title "Five numbered steps".', "For each task, give five numbered steps."):
            self.assertIsNone(requested_count(request, "step"))

    def test_clarifications_target_the_missing_value(self):
        self.assertIn("unit", clarification_question("Convert the number 8 to the other unit."))
        self.assertIn("person", clarification_question("Replace they with the intended name."))
        self.assertIn("Which label", clarification_question("Rewrite the label."))

    def test_draft_omissions_retry_before_a_permissive_model_review(self):
        bad = chat_result("The workshop has changed. Please attend.", model=GENERAL_LARGE_MODEL)
        good = chat_result("Workshop moved from Monday to Friday at 14:00 in Hall 8.", model=GENERAL_LARGE_MODEL)
        backend = FakeBackend((bad, good))
        session, _, _, reviewer = reliable(backend, route=semantic_route(size="large"))
        session._messages.extend((
            ChatMessage("user", "Draft an announcement: the workshop moved from Monday to Friday at 14:00 in Hall 8."),
            ChatMessage("assistant", "The workshop moved from Monday to Friday at 14:00 in Hall 8."),
        ))
        reply = session.send("Shorten that announcement to no more than 16 words. Keep the weekdays, time and room.")
        self.assertEqual(reply.response.speech, "Workshop moved from Monday to Friday at 14:00 in Hall 8.")
        self.assertEqual(reply.attempts, (bad, good))
        self.assertIn("draft_location", reply.quality_issues)
        self.assertEqual(len(reviewer.calls), 1)
        self.assertNotIn(bad.content, repr(session.messages))

    def test_new_edit_does_not_inherit_an_unrelated_general_answer(self):
        answer = "The workshop starts Friday at 10:00 in Hall 7."
        backend = FakeBackend((chat_result(answer, model=GENERAL_LARGE_MODEL),))
        session, _, _, _ = reliable(backend, route=semantic_route(size="large"))
        session._messages.extend((
            ChatMessage("user", "Explain the schedule of a hypothetical lecture on Monday at 09:00 in Room 5."),
            ChatMessage("assistant", "The lecture starts Monday at 09:00 in Room 5."),
        ))
        reply = session.send("Rewrite a message: the workshop starts Friday at 10:00 in Hall 7.")
        self.assertEqual(reply.response.speech, answer)
        self.assertFalse(any(issue.startswith("draft_") for issue in reply.quality_issues))


if __name__ == "__main__":
    unittest.main()
