"""Recall improvements and counterexamples beyond the original fixture."""

import unittest
from copy import deepcopy

from oline_hri.conversation import (
    _required_memory_ids, _request_may_need_multiple_memories,
)
from oline_hri.memory_evidence import (
    direct_subject_supported, evidence_order, relevance_stem,
    parse_subject_request, requested_subject_supported, subject_facet_supported,
)
from oline_hri.response import ResponseValidationError
from oline_hri.evaluation_scoring import _cascade, EvaluationScoringError
from test_evaluation_scoring import _raw_records, _find
from test_conversation_routed import (
    FakeBackend, FakeRetriever, FakeRouter, chat_result, hybrid_match,
    memory, routed_conversation, routing_result,
)


class MemoryEvidenceTests(unittest.TestCase):
    def test_requested_attribute_is_bound_to_subject_and_owner(self):
        cases = (
            ("What is the name of my telescope workshop project?",
             "Your telescope workshop project is called Aurora.", True),
            ("What is the name of my telescope workshop project?",
             "Your telescope workshop project partner is Noor.", False),
            ("What is the name of my telescope workshop project?",
             "Rina's telescope workshop project is called Aurora.", False),
            ("What is the name of my fern?",
             "Your fern sits beside a plant named Olive.", False),
            ("Where is my sewing kit?",
             "Your sewing kit is red. Your mug is in the cupboard.", False),
            ("Where is my sewing kit?",
             "Your sewing kit is stored inside a blue box.", True),
            ("Who is my telescope workshop partner?",
             "Noor is my telescope workshop partner.", True),
            ("Who is my telescope workshop partner?",
             "Rina's telescope workshop partner is Noor.", False),
            ("Remind me of my workshop badge preference.",
             "You have workshop badge cards and prefer lentil soup.", False),
            ("Remind me of my workshop lunch grain preference.",
             "You prefer barley for workshop lunch.", True),
            ("Remind me of my workshop lunch grain preference.",
             "You prefer barley for workshop dinner.", False),
            ("Remind me of my workshop lunch preference.",
             "You prefer barley for dinner.", False),
            ("Remind me of my materials budget.",
             "Your materials box contains 7 green cords.", False),
            ("Remind me of my materials budget.",
             "Your materials shopping budget is 31 credits.", True),
            ("Remind me of my seminar duration.",
             "Your seminar lasts 45 minutes.", True),
            ("Remind me of my seminar length.",
             "Your seminar starts at 15:00.", False),
        )
        for query, text, expected in cases:
            with self.subTest(query=query, text=text):
                self.assertIs(requested_subject_supported(query, text), expected)

    def test_complete_event_grammars_expose_every_requested_subject(self):
        cases = (
            ("Which did I complete later, the prism trial or the camera trial?", 2),
            ("How many hours passed between my prism submission and my camera trial?", 2),
            ("Which comes first, my prism trial or my camera trial? Give their dates and times, and the interval between them.", 2),
            ("Put my completed prism trial, camera trial, and completed radio trial in chronological order, giving each stored date and time.", 3),
        )
        for query, count in cases:
            with self.subTest(query=query):
                parsed = parse_subject_request(query)
                self.assertIsNotNone(parsed)
                self.assertEqual(parsed.mode, "events")
                self.assertEqual(len(parsed.facets), count)
        query = "How many hours passed between my prism submission and my camera trial?"
        self.assertIs(requested_subject_supported(query,
            "You submitted the prism on 3 October 2026 at 11:00."), True)
        self.assertIs(requested_subject_supported(query,
            "You completed the unrelated antenna trial on 3 October 2026 at 11:00."), False)

    def test_unsupported_extra_clauses_never_claim_complete_facets(self):
        for query in (
            "Put my prism trial, camera trial, radio trial, and lens trial in chronological order.",
            "Which comes first, my prism trial or my camera trial? Explain the weather.",
            "Which comes first, my prism trial or my camera trial and move my meeting?",
            "Tell me my prism trial and calculate the fare.",
            "What is the name of my project? Recommend a new name.",
            "Where is my sewing kit if I move it tomorrow?",
            "Using my materials budget, tell me Rina's birthplace.",
            "Using my card supply and badge preference, explain tomorrow's weather.",
            "Before you explain the weather, remind me of my badge preference.",
            "What grain do I prefer for workshop lunch and what is my budget?",
        ):
            with self.subTest(query=query):
                self.assertIsNone(parse_subject_request(query))
                self.assertIsNone(requested_subject_supported(query, "You prefer tea."))

    def test_dates_do_not_link_unrelated_subjects_or_replace_requested_date(self):
        query = "Which room is booked for my optics workshop on 8 October 2026?"
        for text, expected in (
            ("Your optics workshop on 8 October 2026 is in North Hall.", True),
            ("Your optics workshop on 8 October 2026 is in South Hall.", True),
            ("Your optics workshop on 9 October 2026 is in North Hall.", False),
            ("Your weaving workshop on 8 October 2026 is in North Hall.", False),
            ("Your optics workshop is in North Hall.", None),
        ):
            with self.subTest(text=text):
                self.assertIs(requested_subject_supported(query, text), expected)

    def test_event_predicate_does_not_donate_a_date_to_an_incidental_event(self):
        query = "Which did I complete later, the prism trial or the camera trial?"
        facets = parse_subject_request(query).facets
        text = ("You completed the camera trial on 3 October 2026 at 11:00 "
                "after reading a report about the prism trial.")
        self.assertIs(subject_facet_supported(facets[0], text), False)
        self.assertIs(subject_facet_supported(facets[1], text), True)
        self.assertIsNone(subject_facet_supported(facets[0],
            "The prism trial report mentions a meeting on 3 October 2026."))
        schedule = parse_subject_request(
            "Which comes first, my materials collection or my dress rehearsal?").facets
        self.assertIs(subject_facet_supported(schedule[0],
            "Your materials collection is on 2 October 2026 at 09:00."), True)

    def test_multi_resource_coverage_requires_distinct_attributes(self):
        query = ("Using my stored card supply and badge preference, "
                 "allocate 3 cards to labels and use the remaining cards for badges.")
        parsed = parse_subject_request(query)
        self.assertEqual(parsed.mode, "constraints")
        self.assertEqual(len(parsed.facets), 2)
        inventory = "You have eight cards available for labels and badges."
        preference = "You want only first names on badges."
        self.assertIs(subject_facet_supported(parsed.facets[0], inventory), True)
        self.assertIs(subject_facet_supported(parsed.facets[1], inventory), False)
        self.assertIs(subject_facet_supported(parsed.facets[1], preference), True)
        texts = (inventory, "You have ten cards available for badges.", preference)
        self.assertEqual(set(evidence_order(query, texts)[:2]), {0, 2})

    def test_direct_mixed_unknown_recall_has_two_explicit_fields(self):
        query = ("Before the workshop, remind me of both my lunch grain preference "
                 "and my display banner location. If either is not known, identify which one.")
        parsed = parse_subject_request(query)
        self.assertEqual(parsed.mode, "direct")
        self.assertEqual(len(parsed.facets), 2)
        self.assertEqual([f.attribute for f in parsed.facets], ["preference", "location"])

    def test_submission_availability_and_duration_aliases_are_explicit(self):
        for word in ("submit", "submitted", "submission"):
            self.assertEqual(relevance_stem(word), "submit")
        for word in ("available", "availability"):
            self.assertEqual(relevance_stem(word), "available")
        for word in ("duration", "length"):
            self.assertEqual(relevance_stem(word), "duration")

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
