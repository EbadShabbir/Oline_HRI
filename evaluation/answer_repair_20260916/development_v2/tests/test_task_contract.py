"""User-requested formats survive delivery and are checked before review."""

import json
import unittest

from oline_hri.conversation import _user_text
from oline_hri.response import RobotResponse, ResponseValidationError, parse_robot_response
from oline_hri.task_contract import (
    allocation_budget, clarification_question, missing_detail_reply,
    requested_count, csv_output_requested, task_contract_issues, task_instruction,
)
from test_conversation_routed import FakeBackend, GENERAL_LARGE_MODEL, chat_result
from test_reliable_conversation import reliable, semantic_route


class TaskContractTests(unittest.TestCase):
    def test_nonexact_or_source_counts_do_not_become_global_output_counts(self):
        requests = (
            "Use at most three sentences.", "Give at least two sentences.",
            "Answer in no more than three sentences.", "Use up to three sentences.",
            "Use a minimum of two sentences.", "Write around three sentences.",
            "Use three sentences at most.", "Write two sentences or fewer.",
            "Use three sentences maximum.", "Write under three sentences.",
            "Use between two and four sentences.", "Write 2-4 sentences.",
            "Write two or three sentences.", "Write two and three sentences.",
            "Keep the answer to three sentences.",
            "The passage has three sentences. Summarize it.",
            "Summarize the following three sentences.", "Explain three sentences from the passage.",
            "Give two examples, one sentence each.", "For each example, write one sentence.",
            "Write one sentence per example.", 'Use the title "Three sentences".',
            "Do not write three sentences.", "Describe a passage with three sentences.",
        )
        for request in requests:
            with self.subTest(request=request):
                self.assertIsNone(requested_count(request, "sentence"))
                self.assertNotIn("requested_sentence_count", task_contract_issues(request, "A short answer."))
                self.assertNotIn("Exactly", task_instruction(request))
        self.assertIsNone(requested_count("Use the following three sentences and two equations as examples.",
                                          "equation"))

    def test_explicit_output_counts_still_reject_the_wrong_deliverable(self):
        for request in ("Use exactly two sentences.", "Explain this in two sentences.",
                        "Write a two-sentence explanation.", "Exactly two sentences.",
                        "Write a polite two-sentence invitation.",
                        "Your answer must contain two sentences.",
                        "The passage has three sentences. Summarize it in two sentences."):
            with self.subTest(request=request):
                self.assertEqual(requested_count(request, "sentence"), 2)
                self.assertEqual(task_contract_issues(request, "One statement. Another statement."), ())
                self.assertIn("requested_sentence_count", task_contract_issues(request, "Only one."))

    def test_format_guidance_reaches_actual_reliable_generator(self):
        backend = FakeBackend((chat_result("- Four sides.\n- Three sides.", model=GENERAL_LARGE_MODEL),))
        session, _, _, _ = reliable(backend, route=semantic_route(size="large"))
        reply = session.send("Explain quadrilaterals and triangles in exactly two bullet points.")
        self.assertIsNotNone(reply.generation)
        prompt = " ".join(message.content for message in backend.calls[0][1])
        self.assertIn("Exactly 2 bullet points", prompt)
        self.assertIn("line breaks", prompt)

    def test_csv_mentions_and_informational_conversion_questions_allow_prose(self):
        requests = (
            "Explain CSV in two sentences.", "Explain CSV format.",
            "Describe why CSV is useful.", "What is CSV?",
            "How do I convert a table to CSV?", "Compare JSON to CSV.",
            "Could you explain how to convert a table to CSV?",
            "Please explain how to convert a table to CSV.",
            "The exporter can convert tables to CSV. Describe its purpose.",
            "Do not output CSV; explain the idea.", 'Explain the instruction "return only CSV".',
            "The input is CSV text. Explain what its columns mean.",
        )
        for request in requests:
            with self.subTest(request=request):
                self.assertFalse(csv_output_requested(request))
                self.assertNotIn("requested_csv", task_contract_issues(request, "CSV stores tabular data. Commas separate fields."))
                self.assertNotIn("Speech contains only CSV", task_instruction(request))

    def test_explicit_csv_output_directives_share_instruction_and_validation(self):
        for request in ("Return only CSV.", "Convert pear,2; plum,6 to CSV.",
                        "Format this table as CSV.", "Reply in plain CSV.",
                        "Please output valid CSV.", "Could you convert the rows to CSV?", "CSV only."):
            with self.subTest(request=request):
                self.assertTrue(csv_output_requested(request))
                self.assertIn("Speech contains only CSV", task_instruction(request))
                self.assertIn("requested_csv", task_contract_issues(request, "Here is the table."))
                self.assertNotIn("requested_csv", task_contract_issues(request, "fruit,count\npear,2"))

    def test_conjoined_output_units_keep_their_distinct_counts(self):
        request = "Answer with one equation and two short sentences."
        self.assertEqual(requested_count(request, "equation"), 1)
        self.assertEqual(requested_count(request, "sentence"), 2)
        self.assertEqual(task_contract_issues(request, "2 + 2 = 4. Four remain. None are lost."), ())
        self.assertIn("requested_sentence_count", task_contract_issues(request, "2 + 2 = 4. Four remain."))

    def test_requested_multiline_output_survives_json_and_input_boundaries(self):
        text = "shape,count\ntriangles,4\ncircles,7"
        response = RobotResponse(text, "NO_ACTION", ())
        self.assertEqual(parse_robot_response(response.to_json()).speech, text)
        self.assertEqual(_user_text(text), text)
        for control in ("\x00", "\x1b", "\r", "\u202e", "\u200b", "\ud800"):
            with self.subTest(control=repr(control)), self.assertRaises(ResponseValidationError):
                RobotResponse("a" + control + "b", "NO_ACTION", ())
        with self.assertRaises(ResponseValidationError):
            RobotResponse("mem_\n" + "0" * 32, "NO_ACTION", ())

    def test_format_checks_catch_missing_content_even_with_a_permissive_reviewer(self):
        request = "Convert pear, 2; plum, 6 to CSV with header fruit,count. Return only CSV text."
        bad = chat_result("Here is your converted fruit list.", model=GENERAL_LARGE_MODEL)
        good = chat_result("fruit,count\npear,2\nplum,6", model=GENERAL_LARGE_MODEL)
        backend = FakeBackend((bad, good))
        session, _, _, reviewer = reliable(backend, route=semantic_route(size="large"))
        reply = session.send(request)
        self.assertEqual(reply.response.speech, "fruit,count\npear,2\nplum,6")
        self.assertEqual(reply.attempts, (bad, good))
        self.assertEqual(reply.attempted_models, (GENERAL_LARGE_MODEL, GENERAL_LARGE_MODEL))
        self.assertIsNone(reply.fallback_from_model)
        self.assertEqual(len(reviewer.calls), 1)
        self.assertIn("requested_csv", reply.quality_issues)
        self.assertNotIn(bad.content, repr(session.messages))

    def test_two_failed_large_attempts_are_withheld_without_third_generation(self):
        backend = FakeBackend((chat_result("Only one sentence.", model=GENERAL_LARGE_MODEL),
                               chat_result("Still one sentence.", model=GENERAL_LARGE_MODEL)))
        session, _, _, reviewer = reliable(backend, route=semantic_route(size="large"))
        reply = session.send("Write exactly two sentences about an imaginary lighthouse.")
        self.assertIsNone(reply.generation)
        self.assertEqual(len(backend.calls), 2)
        self.assertEqual(reviewer.calls, [])
        self.assertNotIn("Still one", reply.response.speech)

    def test_sentence_count_handles_decimals_abbreviations_and_separate_equation(self):
        cases = (
            ("Use two sentences.", "Meet at 3 p.m. Bring 2.5 litres of water.", ()),
            ("Answer with one equation and one short sentence.", "10 + 4 - 3 = 11. Eleven remain.", ()),
            ("Use one sentence.", "Yes. Here is more.", ("requested_sentence_count",)),
            ("Explain why one sentence can be ambiguous.", "A pronoun can lack a clear referent. Several interpretations may fit.", ()),
        )
        for request, answer, expected in cases:
            with self.subTest(request=request):
                self.assertEqual(task_contract_issues(request, answer), expected)

    def test_lines_and_bullets_are_not_counted_by_topic_alone(self):
        self.assertEqual(task_contract_issues("Write a three-line poem.", "Rain falls\nLeaves shine\nClouds drift"), ())
        self.assertIn("requested_line_count", task_contract_issues("Write a three-line poem.", "Rain falls. Leaves shine. Clouds drift."))
        self.assertEqual(task_contract_issues("Use exactly two bullet points.", "- One fact.\n- Another fact."), ())
        self.assertIn("requested_bullet_count", task_contract_issues("Use exactly two bullet points.", "One fact. Another fact."))

    def test_allocations_must_add_up_and_timer_is_not_a_step_plan(self):
        request = "Give timed steps totaling 11 minutes to arrange supplies."
        self.assertEqual(allocation_budget(request), 11)
        self.assertEqual(task_contract_issues(request, "2 minutes: sort. 5 minutes: arrange. 4 minutes: check. Total: 11 minutes."), ())
        for text in ("Set an 11-minute timer. Arrange supplies.", "2 minutes: sort. 5 minutes: arrange. 5 minutes: check."):
            self.assertIn("requested_time_allocations", task_contract_issues(request, text))
        self.assertIsNone(allocation_budget("The bus takes 11 minutes. Explain why buses stop."))

    def test_missing_recall_acknowledges_absence_without_repeating_an_assistant_guess(self):
        request = 'An assistant guessed your usual instrument is a flute. What instrument did I say I play?'
        text = missing_detail_reply(request)
        self.assertIn("don't have", text)
        self.assertIn("instrument", text)
        self.assertIn("guess does not establish", text)
        self.assertNotIn("flute", text)
        self.assertNotIn("you play", text)

    def test_named_relationship_question_asks_for_relationship_not_supplied_name(self):
        for request, name in (("Who is Neris in relation to me?", "Neris"),
                              ("Who is Amara Chen to me?", "Amara Chen")):
            with self.subTest(request=request):
                text = missing_detail_reply(request, "personal relationship")
                self.assertIn("don't have", text)
                self.assertIn(name, text)
                self.assertIn("related to you", text)
                self.assertNotIn("person's name", text)
                self.assertNotRegex(text, r"\b(?:cousin|sister|brother|partner|friend)\b")
                self.assertEqual(text.count("?"), 1)
        # A question that actually omits the person's identity still asks for it.
        self.assertIn("person's name", missing_detail_reply("Who is my hiking partner?"))

    def test_clarification_targets_missing_operation_or_referent(self):
        self.assertIn("calculation", clarification_question("The numbers are 2 and 7. Work it out."))
        self.assertIn("Which message", clarification_question("Two messages are supplied. Shorten the message."))
        self.assertIn("full name", clarification_question("Draft a reply to Robin."))
        self.assertIn("what purpose", clarification_question("Would five be enough?"))


if __name__ == "__main__":
    unittest.main()
