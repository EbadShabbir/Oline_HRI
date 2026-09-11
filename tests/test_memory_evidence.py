"""Recall improvements and counterexamples beyond the original fixture."""

import unittest
from copy import deepcopy

from oline_hri.conversation import (
    _required_memory_ids, _request_may_need_multiple_memories,
)
from oline_hri.memory_evidence import (
    direct_subject_supported, evidence_order, relevance_stem,
)
from oline_hri.response import ResponseValidationError
from oline_hri.evaluation_scoring import _cascade, EvaluationScoringError
from test_evaluation_scoring import _raw_records, _find
from test_conversation_routed import (
    FakeBackend, FakeRetriever, FakeRouter, chat_result, hybrid_match,
    memory, routed_conversation, routing_result,
)


class MemoryEvidenceTests(unittest.TestCase):
    def test_transform_provenance_is_explicit_and_bounded(self):
        record = _find(
            _raw_records(strategies=("adaptive",)), "case",
            case_id="memory_direct_fact",
        )["cascade"]
        record["response_transform"] = "verified_memory_perspective"
        self.assertEqual(
            _cascade(record)["response_transform"],
            "verified_memory_perspective",
        )
        for changes in (
            {"response_transform": "arbitrary_rewrite"},
            {"retrieval_invoked": False},
            {"supplied_ids": []},
            {"response": None},
            {"privacy_gate": True},
        ):
            candidate = deepcopy(record)
            candidate.update(changes)
            with self.subTest(changes=changes):
                with self.assertRaises(EvaluationScoringError):
                    _cascade(candidate)

    def test_verbatim_human_event_copy_is_normalized_and_audited(self):
        item = memory(1, "I completed an acoustic sensor test.")
        backend = FakeBackend((chat_result(
            item.canonical_text, memory_used=(item.id,),
        ),))
        convo = routed_conversation(
            backend, FakeRouter((routing_result(True),)),
            FakeRetriever((hybrid_match(item),)),
        )
        result = convo.send("What test did I complete?")
        self.assertEqual(result.response.speech, "You completed an acoustic sensor test.")
        self.assertEqual(result.response_transform, "verified_memory_perspective")
        self.assertIn("I completed", result.generation.content)

    def test_nonverbatim_first_person_fabrication_is_not_repaired(self):
        item = memory(1, "I completed an acoustic sensor test.")
        backend = FakeBackend((chat_result(
            "I completed a camera calibration test.", memory_used=(item.id,),
        ),))
        convo = routed_conversation(
            backend, FakeRouter((routing_result(True),)),
            FakeRetriever((hybrid_match(item),)),
        )
        with self.assertRaises(ResponseValidationError):
            convo.send("What test did I complete?")

    def test_temporal_facets_do_not_force_adjacent_milestone(self):
        items = (
            memory(1, "I completed the acoustic prototype milestone on Friday."),
            memory(2, "I changed my tea preference to chamomile on Thursday."),
            memory(3, "I completed the kickoff milestone on Monday."),
        )
        matches = tuple(hybrid_match(item, i) for i, item in enumerate(items, 1))
        ids = _required_memory_ids(matches,
            "Compare when I changed my tea preference with when I completed "
            "the acoustic milestone, and explain which came later.")
        self.assertEqual(ids, (items[0].id, items[1].id))

    def test_plant_is_not_planning(self):
        self.assertFalse(_request_may_need_multiple_memories(
            "What is my desk plant's name?"
        ))
        self.assertFalse(_request_may_need_multiple_memories(
            "What is my planetary telescope called?"
        ))
        self.assertTrue(_request_may_need_multiple_memories(
            "Plan my next visit."
        ))

    def test_completion_forms_share_one_stem(self):
        for word in ("complete", "completed", "completing", "completion"):
            self.assertEqual(relevance_stem(word), "complete")

    def test_direct_attribute_needs_object_and_value(self):
        cases = (
            ("What color is my bike?", "I own a red bicycle.", True),
            ("What color is my bike?", "I own a bicycle.", False),
            ("What color is my bike?", "My helmet is red.", False),
            ("What color is my bike?", "I own a bicycle and a red helmet.", False),
            ("What is my fern's name?", "My fern is called Fernanda.", True),
            ("What is my fern's name?", "My fern needs water.", False),
            ("What is my dog's name?", "My plant is named Olive.", False),
            ("Which notebook do I need for the lab review?",
             "The lab review is in Lab A.", False),
        )
        for query, text, expected in cases:
            with self.subTest(query=query, text=text):
                self.assertIs(direct_subject_supported(query, text), expected)

    def test_short_evidence_links_without_incidental_neighbors(self):
        cases = (
            ("What color is my bike?", "I own a red bicycle."),
            ("What test did I complete?", "I completed an acoustic sensor test."),
            ("What is my fern's name?", "My fern is called Fernanda."),
        )
        for query, text in cases:
            relevant = memory(1, text)
            unrelated = memory(2, "I prefer long answers.")
            matches = (hybrid_match(unrelated), hybrid_match(relevant, 2))
            with self.subTest(query=query):
                self.assertEqual(_required_memory_ids(matches, query), (relevant.id,))

    def test_multi_part_prompt_and_schema_exclude_optional_citations(self):
        relevant = memory(1, "I prefer short answers.")
        unrelated = memory(2, "I prefer green tea.")
        backend = FakeBackend((chat_result(
            "You prefer short answers.", memory_used=(relevant.id,),
        ),))
        convo = routed_conversation(
            backend, FakeRouter((routing_result(True),)),
            FakeRetriever((hybrid_match(relevant), hybrid_match(unrelated, 2))),
        )
        result = convo.send("Do I prefer short or long answers?")
        self.assertEqual(result.memory_diagnostics.supplied_ids, (relevant.id,))
        self.assertNotIn(unrelated.id, str(backend.calls))

    def test_reranking_covers_separate_requested_topics(self):
        texts = (
            "The laboratory demonstration is next week.",
            "The laboratory demonstration needs slides.",
            "I completed the acoustic prototype.",
            "I prefer meetings on Friday afternoons.",
            "I prefer answers under two sentences.",
        )
        order = evidence_order(
            "Prepare my completed acoustic prototype during my preferred "
            "meeting window and note my answer-length preference.", texts,
        )
        self.assertEqual(set(order[:3]), {2, 3, 4})

    def test_no_lexical_evidence_preserves_rrf_order(self):
        self.assertEqual(evidence_order("something else", ("tea", "coffee")), (0, 1))

    def test_direct_conflicting_candidates_are_not_deduplicated(self):
        texts = (
            "Your review is in Lab A on Friday.",
            "Your review is in Lab B on Friday.",
            "You prefer tea.",
        )
        self.assertEqual(evidence_order("Which lab is Friday's review in?", texts)[:2], (0, 1))


if __name__ == "__main__":
    unittest.main()
