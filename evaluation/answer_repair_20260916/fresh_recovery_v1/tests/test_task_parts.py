"""Closed task-layout parsing, raw provenance and existing evidence boundaries."""

import json
import unittest

from oline_hri.response import ResponseValidationError
from oline_hri.task_contract import task_contract_issues
from oline_hri.task_parts import TaskLayout, task_layout, parts_schema, parse_parts
from test_conversation_routed import FakeBackend, GENERAL_LARGE_MODEL, chat_result
from test_reliable_conversation import reliable, semantic_route


def result(parts):
    return chat_result(raw=json.dumps({"answer_parts": parts}), model=GENERAL_LARGE_MODEL)


class TaskPartsTests(unittest.TestCase):
    def test_rendering_changes_only_layout(self):
        for kind, expected in (("lines", "North glows\nSouth rests"),
                               ("bullets", "- North glows\n- South rests"),
                               ("items", "- North glows\n- South rests"),
                               ("sentences", "North glows South rests")):
            layout = TaskLayout(kind, 2)
            raw = json.dumps({"answer_parts": ["North glows", "South rests"]})
            response = parse_parts(raw, layout)
            self.assertEqual(response.speech, expected)
            self.assertEqual(response.memory_used, ())
            self.assertEqual(response.gesture_id, "NO_ACTION")
            self.assertEqual(parts_schema(layout)["properties"]["answer_parts"]["minItems"], 2)

    def test_only_explicit_supported_formats_select_parts(self):
        self.assertEqual(task_layout("Write a brief three-line verse."), TaskLayout("lines", 3))
        self.assertEqual(task_layout("Give a four-item checklist."), TaskLayout("items", 4))
        self.assertEqual(task_layout("Return CSV."), TaskLayout("csv"))
        for request in ("Explain CSV.", "Use at most two sentences.", "The passage has two lines.",
                        "Write one sentence per example.", "Write thirteen lines."):
            self.assertIsNone(task_layout(request))

    def test_invalid_payloads_and_hidden_authority_fail(self):
        for raw in ('{"answer_parts":["a"]}', '{"answer_parts":["a",4]}',
                    '{"answer_parts":["a","b"],"memory_used":[]}',
                    '{"answer_parts":["a","b"],"answer_parts":["c","d"]}',
                    '{"answer_parts":["a\\nb","c"]}',
                    json.dumps({"answer_parts": ["mem_" + "0" * 32, "Other"]}),
                    json.dumps({"answer_parts": ["abc\u202edef", "Other"]})):
            with self.subTest(raw=raw), self.assertRaises(ResponseValidationError):
                parse_parts(raw, TaskLayout("lines", 2))
        with self.assertRaises(ResponseValidationError):
            parse_parts('{"answer_parts":["- Already numbered","Other"]}', TaskLayout("bullets", 2))

    def test_delivered_format_and_raw_payload_are_distinct(self):
        generated = result(["Cold stars brighten", "Quiet fields listen"])
        backend = FakeBackend((generated,))
        session, _, _, reviewer = reliable(backend, route=semantic_route(size="large"))
        reply = session.send("Write a two-line poem about a winter night.")
        self.assertIs(reply.generation, generated)
        self.assertEqual(reply.response.speech, "Cold stars brighten\nQuiet fields listen")
        self.assertEqual(reply.response_transform, "task_parts_v1")
        self.assertEqual(reviewer.calls[0]["answer"], reply.response.speech)
        self.assertEqual(reply.attempted_models, (GENERAL_LARGE_MODEL,))

    def test_exact_words_are_checked_across_all_parts(self):
        request = "Write a two-line poem. Include the word 'comet' exactly once."
        self.assertEqual(task_contract_issues(request, "A comet travels\nDark skies listen"), ())
        self.assertIn("requested_word_count", task_contract_issues(request, "A comet travels\nThe comet glows"))
        self.assertNotIn("requested_word_count", task_contract_issues("Do not use the word 'comet' exactly once.", "Clouds."))

    def test_personal_claim_guard_remains_active_for_typed_general_output(self):
        backend = FakeBackend((result(["Your sister is an architect.", "Your sister lives in Rome."]),
                               result(["Your sister is a pilot.", "Your sister lives in Paris."])))
        session, _, _, reviewer = reliable(backend, route=semantic_route(size="large"))
        reply = session.send("Use two sentences to explain the idea of a family tree.")
        self.assertIsNone(reply.generation)
        self.assertIn("unsupported_personal_claim", reply.quality_issues)
        self.assertEqual(len(reply.attempts), 2)
        self.assertEqual(reviewer.calls, [])

    def test_mixed_missing_recall_keeps_general_format_and_prefix_separate(self):
        fragment = "Give a three-item generic office checklist."
        backend = FakeBackend((result(["Paper", "Pens", "Folders"]),))
        session, _, _, _ = reliable(backend, route=semantic_route("required", size="large", fragment=fragment))
        reply = session.send("What color did I say my notebook is? " + fragment)
        self.assertIn("don't have", reply.response.speech)
        self.assertIn("- Paper\n- Pens\n- Folders", reply.response.speech)
        self.assertEqual(reply.response.memory_used, ())


if __name__ == "__main__":
    unittest.main()
