"""Focused regressions for reviewed memory-grounded generation gaps."""

from dataclasses import replace
import unittest

from oline_hri.config import load_config
from oline_hri.conversation import Conversation, ConversationError
from oline_hri.response import ResponseValidationError
from tests.test_conversation_routed import (
    LARGE_MODEL,
    SMALL_MODEL,
    FakeBackend,
    FakeRetriever,
    FakeRouter,
    chat_result,
    decode_memory_envelope,
    hybrid_match,
    memory,
    routed_conversation,
    routing_result,
)


_DISTINCT_DATE_CHRONOLOGY_PROMPT = (
    "Create a chronological timeline comparing when I changed my tea "
    "preference and completed my navigation milestone, and say which came "
    "later."
)
_DISTINCT_DATE_CHRONOLOGY_SPEECH = (
    "1. Friday, August 7, 2026: you changed your tea preference to ginger "
    "without sugar. 2. Saturday, August 8, 2026: you completed the navigation "
    "milestone. Saturday follows Friday, so the milestone came later."
)


def _distinct_date_chronology_memories():
    corrected_tea = replace(
        memory(9, "The user now prefers ginger tea without sugar."),
        kind="preference",
        supersedes_id=memory(2).id,
        valid_from="2026-08-07T09:00:00.000000Z",
    )
    navigation = replace(
        memory(
            11,
            "The user completed the navigation milestone on Saturday, "
            "8 August 2026.",
        ),
        kind="event",
        event_time="2026-08-08T10:00:00.000000Z",
    )
    return corrected_tea, navigation


def _chronology_conversation(speech, first, second):
    memory_ids = (first.id, second.id)
    return routed_conversation(
        FakeBackend(
            (
                chat_result(
                    speech,
                    memory_used=memory_ids,
                    model=LARGE_MODEL,
                ),
            )
        ),
        FakeRouter((routing_result(True, "large"),)),
        FakeRetriever((hybrid_match(first, 1), hybrid_match(second, 2))),
        grounded_composition=False,  # Exercise unconstrained-answer validators.
    )


_RECENCY_COMPARISON_PROMPT = (
    "Compare my earlier and most recent completed project milestones, "
    "identify which is newer, and name my collaborator."
)
_RECENCY_COMPARISON_SPEECH = (
    "Your Luma kickoff milestone was Monday, August 3, 2026. Your navigation "
    "prototype milestone was Saturday, August 8, 2026, so navigation is "
    "newer. Theo is your collaborator."
)


def _recency_comparison_memories():
    navigation = replace(
        memory(
            11,
            "Mira completed the navigation prototype milestone on Saturday, "
            "8 August 2026.",
        ),
        kind="event",
        event_time="2026-08-08T10:00:00.000000Z",
    )
    kickoff = replace(
        memory(
            1,
            "Mira started a tabletop companion robot project named Luma by "
            "completing its kickoff milestone on Monday, 3 August 2026.",
        ),
        kind="event",
        event_time="2026-08-03T09:00:00.000000Z",
    )
    collaborator = replace(
        memory(4, "Mira's robotics project partner is Theo."),
        kind="relationship",
    )
    return navigation, kickoff, collaborator


def _recency_comparison_conversation(
    speech, memory_used, *, context_length=4096
):
    items = _recency_comparison_memories()
    backend = FakeBackend(
        (
            chat_result(
                speech,
                memory_used=memory_used,
                model=LARGE_MODEL,
            ),
        )
    )
    conversation = Conversation(
        backend,
        system_prompt=load_config().conversation.system_prompt,
        router=FakeRouter((routing_result(True, "large"),)),
        retriever=FakeRetriever(
            tuple(
                hybrid_match(item, position)
                for position, item in enumerate(items, start=1)
            )
        ),
        small_model=SMALL_MODEL,
        large_model=LARGE_MODEL,
        context_length=context_length,
        max_output_tokens=320,
        grounded_composition=False,  # Raw model paraphrase/omission coverage.
    )
    return conversation, backend, items


class MemoryGroundingReviewRegressionTests(unittest.TestCase):
    def test_legacy_question_record_is_not_used_as_factual_evidence(self) -> None:
        stored_question = replace(
            memory(1, "what is my preference regarding tea"),
            kind="preference",
        )
        backend = FakeBackend(
            (
                chat_result(
                    "I don't have personal preferences, but I can help choose tea.",
                    memory_used=(),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(stored_question),)),
        )

        reply = conversation.send("What kind of tea do I prefer?")

        self.assertEqual(
            reply.memory_diagnostics.retrieved_ids,
            (stored_question.id,),
        )
        self.assertEqual(reply.memory_diagnostics.supplied_ids, ())
        self.assertEqual(reply.response.memory_used, ())
        self.assertEqual(
            reply.response.speech,
            "I do not have a verified personal memory that answers that.",
        )

    def test_irrelevant_nearest_candidate_can_be_left_unused(self) -> None:
        unrelated = memory(1, "The user prefers jasmine tea without sugar.")
        backend = FakeBackend(
            (
                chat_result(
                    "No verified memory says what music you prefer.",
                    memory_used=(),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(unrelated),)),
        )

        reply = conversation.send("What is my favorite music?")

        self.assertEqual(reply.memory_diagnostics.retrieved_ids, (unrelated.id,))
        self.assertEqual(reply.memory_diagnostics.supplied_ids, ())
        self.assertEqual(reply.memory_diagnostics.model_used_ids, ())
        self.assertEqual(
            reply.response.speech,
            "I do not have a verified personal memory that answers that.",
        )
        supplied_text = "\n".join(message.content for message in backend.calls[0][1])
        self.assertNotIn(unrelated.canonical_text, supplied_text)
        self.assertNotIn(unrelated.id, supplied_text)
        self.assertEqual(len(conversation.messages), 1)

    def test_empty_citation_replaces_confident_model_claim_with_abstention(
        self,
    ) -> None:
        unrelated = memory(1, "The user prefers jasmine tea without sugar.")
        backend = FakeBackend(
            (
                chat_result(
                    "You prefer jazz, though I am not completely certain.",
                    memory_used=(),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(unrelated),)),
        )

        reply = conversation.send("What is my favorite music?")

        self.assertEqual(
            reply.response.speech,
            "I do not have a verified personal memory that answers that.",
        )
        self.assertNotIn("jazz", reply.response.speech.casefold())

    def test_unlinked_nonempty_citation_is_rejected_without_disclosure(
        self,
    ) -> None:
        unrelated = memory(
            1, "The user keeps a notebook for music projects."
        )
        backend = FakeBackend(
            (
                chat_result(
                    "You prefer jazz.",
                    memory_used=(unrelated.id,),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(unrelated),)),
        )

        with self.assertRaisesRegex(
            ResponseValidationError, "memory_used must be empty"
        ):
            conversation.send("What is my favorite music?")
        self.assertEqual(len(backend.calls), 1)
        memory_schema = backend.calls[0][2]["properties"]["memory_used"]
        self.assertEqual(memory_schema["maxItems"], 0)
        supplied_text = "\n".join(message.content for message in backend.calls[0][1])
        self.assertNotIn(unrelated.canonical_text, supplied_text)
        self.assertNotIn(unrelated.id, supplied_text)
        self.assertEqual(len(conversation.messages), 1)

    def test_linked_single_memory_still_requires_its_citation(self) -> None:
        preference = memory(1, "The user prefers jasmine tea without sugar.")
        backend = FakeBackend(
            (
                chat_result(
                    "You prefer jasmine tea without sugar.",
                    memory_used=(),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(preference),)),
        )

        with self.assertRaises(ResponseValidationError):
            conversation.send("How do I take my jasmine tea?")

    def test_linked_second_rank_candidate_displaces_irrelevant_first(self) -> None:
        unrelated = memory(1, "The user owns a blue notebook.")
        preference = memory(2, "The user prefers jasmine tea without sugar.")
        backend = FakeBackend(
            (
                chat_result(
                    "You prefer jasmine tea without sugar.",
                    memory_used=(preference.id,),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever(
                (hybrid_match(unrelated, 1), hybrid_match(preference, 2))
            ),
        )

        reply = conversation.send("How do I take my jasmine tea?")

        self.assertEqual(
            reply.memory_diagnostics.retrieved_ids,
            (unrelated.id, preference.id),
        )
        self.assertEqual(reply.memory_diagnostics.supplied_ids, (preference.id,))

    def test_required_records_are_packed_before_oversized_optional_record(
        self,
    ) -> None:
        oversized = memory(1, "Unrelated filler " + "x" * 2600)
        partner = memory(
            2, "Theo is the user's fictional robotics project partner."
        )
        meeting = memory(
            3,
            "The user prefers robotics project meetings on Tuesday mornings.",
        )
        required_ids = (partner.id, meeting.id)
        backend = FakeBackend(
            (
                chat_result(
                    "Theo is your robotics project partner, and you meet on "
                    "Tuesday mornings.",
                    memory_used=required_ids,
                    model=LARGE_MODEL,
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "large"),)),
            FakeRetriever(
                (
                    hybrid_match(oversized, 1),
                    hybrid_match(partner, 2),
                    hybrid_match(meeting, 3),
                )
            ),
            context_length=4096,
        )

        reply = conversation.send("Use Theo and Tuesday in a meeting plan.")

        self.assertEqual(reply.memory_diagnostics.supplied_ids, required_ids)

    def test_small_multi_fact_recall_supplies_and_uses_both_facts(self) -> None:
        partner = replace(
            memory(1, "Theo is the user's fictional robotics project partner."),
            kind="relationship",
        )
        meeting = replace(
            memory(
                2,
                "The user prefers robotics project meetings on Tuesday mornings.",
            ),
            kind="routine",
        )
        matches = (hybrid_match(partner, 1), hybrid_match(meeting, 2))
        expected_ids = (partner.id, meeting.id)
        backend = FakeBackend(
            (
                chat_result(
                    "Theo is your robotics project partner, and you prefer "
                    "meeting on Tuesday mornings.",
                    memory_used=expected_ids,
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever(matches),
        )

        reply = conversation.send("Who is Theo and when do we meet?")

        self.assertEqual(reply.memory_diagnostics.supplied_ids, expected_ids)
        self.assertEqual(reply.memory_diagnostics.model_used_ids, expected_ids)
        self.assertEqual(reply.response.memory_used, expected_ids)

    def test_separate_questions_retain_multi_memory_candidates(self) -> None:
        partner = memory(
            1, "Theo is the user's fictional robotics project partner."
        )
        meeting = memory(
            2,
            "The user prefers robotics project meetings on Tuesday mornings.",
        )
        expected_ids = (partner.id, meeting.id)
        backend = FakeBackend(
            (
                chat_result(
                    "Theo is your robotics project partner. You meet on "
                    "Tuesday mornings.",
                    memory_used=expected_ids,
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(partner, 1), hybrid_match(meeting, 2))),
        )

        reply = conversation.send("Who is Theo? When do we meet?")

        self.assertEqual(reply.memory_diagnostics.supplied_ids, expected_ids)
        self.assertEqual(reply.response.memory_used, expected_ids)

    def test_as_well_as_phrase_retains_multi_memory_candidates(self) -> None:
        partner = memory(
            1, "Theo is the user's fictional robotics project partner."
        )
        meeting = memory(
            2,
            "The user prefers robotics project meetings on Tuesday mornings.",
        )
        expected_ids = (partner.id, meeting.id)
        backend = FakeBackend(
            (
                chat_result(
                    "Theo is your robotics project partner, and you meet on "
                    "Tuesday mornings.",
                    memory_used=expected_ids,
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(partner, 1), hybrid_match(meeting, 2))),
        )

        reply = conversation.send(
            "Give me Theo's role as well as my meeting time."
        )

        self.assertEqual(reply.memory_diagnostics.supplied_ids, expected_ids)
        self.assertEqual(reply.response.memory_used, expected_ids)

    def test_evidence_cardinality_is_model_independent_and_does_not_force_distractor(
        self,
    ) -> None:
        partner = memory(
            1, "Theo is the user's fictional robotics project partner."
        )
        meeting = memory(
            2,
            "The user prefers robotics project meetings on Tuesday mornings.",
        )
        distractor = memory(
            3,
            "The user prefers project plans containing exactly three concise steps.",
        )
        matches = tuple(
            hybrid_match(item, position)
            for position, item in enumerate(
                (partner, meeting, distractor), start=1
            )
        )
        expected_ids = (partner.id, meeting.id)

        supplied_by_size = {}
        for size, model_name in (
            ("small", SMALL_MODEL),
            ("large", LARGE_MODEL),
        ):
            with self.subTest(size=size):
                backend = FakeBackend(
                    (
                        chat_result(
                            "Theo is your robotics project partner, and you "
                            "prefer meeting on Tuesday mornings.",
                            memory_used=expected_ids,
                            model=model_name,
                        ),
                    )
                )
                conversation = routed_conversation(
                    backend,
                    FakeRouter((routing_result(True, size),)),
                    FakeRetriever(matches),
                )

                reply = conversation.send(
                    "Who is Theo and when do we meet?"
                )
                supplied_by_size[size] = reply.memory_diagnostics.supplied_ids
                self.assertEqual(
                    reply.memory_diagnostics.retrieved_ids,
                    tuple(match.memory.id for match in matches),
                )
                self.assertNotIn(
                    distractor.id, reply.memory_diagnostics.supplied_ids
                )
                self.assertNotIn(
                    distractor.id, reply.memory_diagnostics.model_used_ids
                )

        self.assertEqual(supplied_by_size["small"], expected_ids)
        self.assertEqual(supplied_by_size["large"], expected_ids)

    def test_incidental_punctuation_does_not_expand_memory_candidates(
        self,
    ) -> None:
        partner = replace(
            memory(
                1,
                "Rina is the user's fictional sensor-calibration partner.",
            ),
            kind="relationship",
        )
        schedule = replace(
            memory(
                2,
                "The user prefers sensor-calibration sessions on Friday "
                "afternoons.",
            ),
            kind="routine",
        )
        plan_format = replace(
            memory(
                3,
                "The user prefers calibration plans containing exactly four "
                "short numbered steps.",
            ),
            kind="preference",
        )
        matches = tuple(
            hybrid_match(item, position)
            for position, item in enumerate(
                (partner, schedule, plan_format), start=1
            )
        )

        for request, expected_ids in (
            ("today i talked to rina, i am so stressed after talking to her", ()),
            ("Today I talked to Rina, afterward, I felt stressed.", (partner.id,)),
            ("Who is Rina; answer directly; keep it brief?", (partner.id,)),
        ):
            with self.subTest(request=request):
                backend = FakeBackend(
                    (
                        chat_result(
                            "Rina is your fictional sensor-calibration partner.",
                            memory_used=expected_ids,
                        ),
                    )
                )
                conversation = routed_conversation(
                    backend,
                    FakeRouter((routing_result(True, "small"),)),
                    FakeRetriever(matches),
                )

                reply = conversation.send(request)

                self.assertEqual(
                    reply.memory_diagnostics.retrieved_ids,
                    tuple(match.memory.id for match in matches),
                )
                self.assertEqual(
                    reply.memory_diagnostics.supplied_ids, expected_ids
                )
                supplied_text = "\n".join(message.content for message in backend.calls[0][1])
                for item in (partner, schedule, plan_format):
                    if item.id not in expected_ids:
                        self.assertNotIn(item.canonical_text, supplied_text)
                        self.assertNotIn(item.id, supplied_text)
                self.assertEqual(len(conversation.messages), 1)

    def test_explicit_delimited_list_still_supplies_all_memories(self) -> None:
        partner = replace(
            memory(
                1,
                "Rina is the user's fictional sensor-calibration partner.",
            ),
            kind="relationship",
        )
        schedule = replace(
            memory(
                2,
                "The user prefers sensor-calibration sessions on Friday "
                "afternoons.",
            ),
            kind="routine",
        )
        plan_format = replace(
            memory(
                3,
                "The user prefers calibration plans containing exactly four "
                "short numbered steps.",
            ),
            kind="preference",
        )
        items = (partner, schedule, plan_format)
        expected_ids = tuple(item.id for item in items)
        matches = tuple(
            hybrid_match(item, position)
            for position, item in enumerate(items, start=1)
        )

        for request in (
            "Use Rina's role, my sensor-calibration session preference for Friday "
            "afternoons, my calibration-plan preference for four short numbered steps.",
            "Use Rina's role; my sensor-calibration session preference for Friday "
            "afternoons; my calibration-plan preference for four short numbered steps.",
        ):
            with self.subTest(request=request):
                backend = FakeBackend(
                    (
                        chat_result(
                            "1. Meet Rina, your fictional sensor-calibration "
                            "partner. 2. Calibrate sensors Friday afternoon. "
                            "3. Record readings. 4. Review results.",
                            memory_used=expected_ids,
                        ),
                    )
                )
                conversation = routed_conversation(
                    backend,
                    FakeRouter((routing_result(True, "small"),)),
                    FakeRetriever(matches),
                )

                reply = conversation.send(request)

                self.assertEqual(
                    reply.memory_diagnostics.supplied_ids, expected_ids
                )
                self.assertEqual(
                    reply.memory_diagnostics.model_used_ids, expected_ids
                )

    def test_direct_meeting_time_selects_only_time_bearing_evidence(self) -> None:
        partner = memory(
            1, "Theo is the user's fictional robotics project partner."
        )
        meeting = memory(
            2,
            "The user prefers robotics project meetings on Tuesday mornings.",
        )
        plan_format = memory(
            3,
            "The user prefers project plans containing exactly three concise steps.",
        )
        backend = FakeBackend(
            (
                chat_result(
                    "You prefer robotics project meetings on Tuesday mornings.",
                    memory_used=(meeting.id,),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever(
                tuple(
                    hybrid_match(item, position)
                    for position, item in enumerate(
                        (partner, meeting, plan_format), start=1
                    )
                )
            ),
        )

        reply = conversation.send(
            "What is my preferred meeting time for the robotics project?"
        )

        self.assertEqual(reply.memory_diagnostics.supplied_ids, (meeting.id,))
        self.assertEqual(reply.memory_diagnostics.model_used_ids, (meeting.id,))

    def test_conflicting_topical_records_are_both_required(self) -> None:
        first = memory(
            1, "The user was told Monday's project review is in Lab A."
        )
        second = memory(
            2, "The user was told Monday's project review is in Lab B."
        )
        distractor = memory(3, "The user prefers jasmine tea.")
        matches = tuple(
            hybrid_match(item, position)
            for position, item in enumerate(
                (first, second, distractor), start=1
            )
        )
        required_ids = (first.id, second.id)
        backend = FakeBackend(
            (
                chat_result(
                    "The saved records conflict between Lab A and Lab B, so "
                    "the review location is uncertain.",
                    memory_used=required_ids,
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever(matches),
        )

        reply = conversation.send(
            "Was Monday's project review in Lab A or Lab B?"
        )

        self.assertEqual(
            reply.memory_diagnostics.supplied_ids,
            required_ids,
        )
        self.assertEqual(reply.memory_diagnostics.model_used_ids, required_ids)

    def test_conflicting_topical_record_cannot_be_omitted(self) -> None:
        first = memory(
            1, "The user was told Monday's project review is in Lab A."
        )
        second = memory(
            2, "The user was told Monday's project review is in Lab B."
        )
        backend = FakeBackend(
            (
                chat_result(
                    "One saved record says the review is in Lab A.",
                    memory_used=(first.id,),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(first, 1), hybrid_match(second, 2))),
        )

        with self.assertRaises(ResponseValidationError):
            conversation.send("Was Monday's project review in Lab A or Lab B?")

    def test_conflicting_records_require_explicit_uncertainty(self) -> None:
        first = memory(
            1, "The user was told Monday's project review is in Lab A."
        )
        second = memory(
            2, "The user was told Monday's project review is in Lab B."
        )
        ids = (first.id, second.id)
        backend = FakeBackend(
            (
                chat_result(
                    "The review is in Lab A, not Lab B.",
                    memory_used=ids,
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(first, 1), hybrid_match(second, 2))),
        )

        reply = conversation.send("Was Monday's project review in Lab A or Lab B?")
        self.assertEqual(reply.response_transform, "conflict_clarification")
        self.assertIn("records conflict between Lab A and Lab B", reply.response.speech)
        self.assertIn("Please confirm", reply.response.speech)
        self.assertEqual(reply.response.memory_used, ids)
        self.assertIn("The review is in Lab A, not Lab B.", reply.generation.content)

    def test_denial_of_detected_conflict_is_not_an_acknowledgement(self) -> None:
        first = memory(
            1, "The user was told Monday's project review is in Lab A."
        )
        second = memory(
            2, "The user was told Monday's project review is in Lab B."
        )
        ids = (first.id, second.id)
        conversation = routed_conversation(
            FakeBackend(
                (
                    chat_result(
                        "The records are not conflicting; the review is in Lab A, "
                        "not Lab B.",
                        memory_used=ids,
                    ),
                )
            ),
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(first, 1), hybrid_match(second, 2))),
        )

        reply = conversation.send("Was Monday's project review in Lab A or Lab B?")
        self.assertEqual(reply.response_transform, "conflict_clarification")
        self.assertNotIn("not conflicting", reply.response.speech)
        self.assertIn("not conflicting", reply.generation.content)
        self.assertEqual(reply.response.memory_used, ids)

    def test_conflict_is_detected_without_or_in_the_request(self) -> None:
        first = memory(
            1, "The user was told Monday's project review is in Lab A."
        )
        second = memory(
            2, "The user was told Monday's project review is in Lab B."
        )
        ids = (first.id, second.id)
        conversation = routed_conversation(
            FakeBackend(
                (
                    chat_result(
                        "The review is in Lab A, not Lab B.",
                        memory_used=ids,
                    ),
                )
            ),
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(first, 1), hybrid_match(second, 2))),
        )

        reply = conversation.send("Where is Monday's project review?")
        self.assertEqual(reply.response_transform, "conflict_clarification")
        self.assertIn("Please confirm", reply.response.speech)
        self.assertEqual(reply.response.memory_used, ids)

    def test_compatible_alternatives_are_not_misclassified_as_conflict(self) -> None:
        jasmine = memory(1, "The user prefers jasmine tea.")
        oolong = memory(2, "The user prefers oolong tea.")
        ids = (jasmine.id, oolong.id)
        conversation = routed_conversation(
            FakeBackend(
                (
                    chat_result(
                        "You prefer both jasmine and oolong tea.",
                        memory_used=ids,
                    ),
                )
            ),
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(jasmine, 1), hybrid_match(oolong, 2))),
        )

        reply = conversation.send("Do I prefer jasmine or oolong tea?")

        self.assertEqual(reply.response.memory_used, ids)

    def test_comprehensive_preference_request_does_not_require_distractor(
        self,
    ) -> None:
        preference = replace(
            memory(1, "The user prefers jasmine tea without sugar."),
            kind="preference",
        )
        distractor = replace(
            memory(2, "Theo is the user's robotics project partner."),
            kind="relationship",
        )
        backend = FakeBackend(
            (
                chat_result(
                    "You prefer jasmine tea without sugar.",
                    memory_used=(preference.id,),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever(
                (hybrid_match(preference, 1), hybrid_match(distractor, 2))
            ),
        )

        reply = conversation.send("Summarize all my preferences.")

        self.assertEqual(reply.response.memory_used, (preference.id,))

    def test_plural_preference_recall_requires_likes_and_enjoys_records(
        self,
    ) -> None:
        quiet = memory(1, "The user likes quiet rooms.")
        painting = memory(2, "The user enjoys watercolor painting.")
        distractor = memory(3, "Theo is the user's project partner.")
        matches = (
            hybrid_match(quiet, 1),
            hybrid_match(painting, 2),
            hybrid_match(distractor, 3),
        )

        incomplete = routed_conversation(
            FakeBackend(
                (
                    chat_result(
                        "You like quiet rooms.",
                        memory_used=(quiet.id,),
                    ),
                )
            ),
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever(matches),
        )
        with self.assertRaises(ResponseValidationError):
            incomplete.send("What are my preferences?")

        complete = routed_conversation(
            FakeBackend(
                (
                    chat_result(
                        "You like quiet rooms and enjoy watercolor painting.",
                        memory_used=(quiet.id, painting.id),
                    ),
                )
            ),
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever(matches),
        )
        reply = complete.send("What are my preferences?")

        self.assertEqual(
            reply.memory_diagnostics.model_used_ids,
            (quiet.id, painting.id),
        )

    def test_one_memory_planning_rule_is_not_unconditional_verbatim_recall(
        self,
    ) -> None:
        preference = memory(1, "The user prefers jasmine tea without sugar.")
        backend = FakeBackend(
            (
                chat_result(
                    "1. Add jasmine tea to the list. 2. Skip sugar.",
                    memory_used=(preference.id,),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(preference),)),
        )

        conversation.send("Turn my tea preference into a two-step shopping plan.")

        _, messages, _ = backend.calls[0]
        _, encoded_request = decode_memory_envelope(messages[-1])
        self.assertEqual(
            encoded_request,
            "Turn my tea preference into a two-step shopping plan.",
        )
        self.assertNotRegex(
            messages[-1].content,
            r"One record:\s*repeat the entire canonical_text",
        )

    def test_explicit_three_facet_request_rejects_one_citation(self) -> None:
        items = (
            memory(1, "Theo is the user's fictional robotics project partner."),
            memory(
                2,
                "The user prefers robotics project meetings on Tuesday mornings.",
            ),
            memory(
                3,
                "The user prefers project plans containing exactly three "
                "concise steps.",
            ),
        )
        matches = tuple(
            hybrid_match(item, position)
            for position, item in enumerate(items, start=1)
        )
        backend = FakeBackend(
            (
                chat_result(
                    "Theo is your robotics project partner.",
                    memory_used=(items[0].id,),
                    model=LARGE_MODEL,
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "large"),)),
            FakeRetriever(matches),
            context_length=4096,
        )

        with self.assertRaises(ResponseValidationError):
            conversation.send(
                "Using Theo's relationship to me, my meeting schedule, and my "
                "preferred plan format, create our next meeting plan."
            )

    def test_ordinal_three_step_plan_satisfies_numeric_memory_anchor(self) -> None:
        items = (
            memory(1, "Theo is the user's fictional robotics project partner."),
            memory(
                2,
                "The user prefers robotics project meetings on Tuesday mornings.",
            ),
            memory(
                3,
                "The user prefers project plans containing exactly three "
                "concise steps.",
            ),
        )
        ids = tuple(item.id for item in items)
        conversation = routed_conversation(
            FakeBackend(
                (
                    chat_result(
                        "First: Coordinate with Theo, your robotics project "
                        "partner. Second: Hold the robotics "
                        "project meeting Tuesday morning. Finally: Write a "
                        "concise plan.",
                        memory_used=ids,
                        model=LARGE_MODEL,
                    ),
                )
            ),
            FakeRouter((routing_result(True, "large"),)),
            FakeRetriever(
                tuple(
                    hybrid_match(item, position)
                    for position, item in enumerate(items, start=1)
                )
            ),
            context_length=4096,
        )

        reply = conversation.send(
            "Using what you remember about Theo, my robotics-project meeting "
            "schedule, and my preferred project-plan format, create a plan for "
            "our next meeting."
        )

        self.assertEqual(reply.response.memory_used, ids)

    def test_incidental_exactly_overlap_does_not_require_distractor(self) -> None:
        partner = memory(
            1, "Theo is the user's fictional robotics project partner."
        )
        distractor = memory(
            2,
            "The user prefers project plans containing exactly three concise steps.",
        )
        backend = FakeBackend(
            (
                chat_result(
                    "Theo is your fictional robotics project partner.",
                    memory_used=(partner.id,),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever(
                (hybrid_match(partner, 1), hybrid_match(distractor, 2))
            ),
        )

        reply = conversation.send("Who is Theo, exactly?")

        self.assertEqual(reply.response.memory_used, (partner.id,))

    def test_required_evidence_is_not_silently_pruned_for_context(self) -> None:
        items = (
            memory(1, "Theo is your partner. " + "x" * 850),
            memory(2, "Tuesday is your meeting day. " + "y" * 850),
            memory(3, "Jasmine is your preferred tea. " + "z" * 850),
        )
        matches = tuple(
            hybrid_match(item, position)
            for position, item in enumerate(items, start=1)
        )
        backend = FakeBackend()
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "large"),)),
            FakeRetriever(matches),
            context_length=4096,
        )

        with self.assertRaisesRegex(ConversationError, "context budget"):
            conversation.send(
                "Remind me of my partner Theo, my meeting day Tuesday, "
                "and my preferred Jasmine tea."
            )

        self.assertEqual(backend.calls, [])

    def test_bare_user_subject_is_rendered_in_second_person(self) -> None:
        preference = memory(1, "User prefers jasmine tea without sugar.")
        backend = FakeBackend(
            (
                chat_result(
                    "You prefer jasmine tea without sugar.",
                    memory_used=(preference.id,),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(preference),)),
        )

        conversation.send("How do I take my jasmine tea?")

        _, messages, _ = backend.calls[0]
        payload, _ = decode_memory_envelope(messages[-1])
        self.assertEqual(
            payload["records"][0]["canonical_text"],
            "You prefer jasmine tea without sugar.",
        )

    def test_time_explicitly_supplied_by_request_is_allowed(self) -> None:
        meeting = memory(
            1,
            "The user prefers robotics project meetings on Tuesday mornings.",
        )
        backend = FakeBackend(
            (
                chat_result(
                    "Tuesday mornings are your preference, so 10:00 works.",
                    memory_used=(meeting.id,),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(meeting),)),
        )

        reply = conversation.send("Can we meet Tuesday morning at 10:00?")

        self.assertIn("10:00", reply.response.speech)
        self.assertEqual(reply.response.memory_used, (meeting.id,))

    def test_uncited_candidate_does_not_authorize_temporal_detail(self) -> None:
        preference = memory(1, "The user prefers jasmine tea without sugar.")
        optional_schedule = memory(
            2, "The user attends a class on Tuesday at 10:00."
        )
        backend = FakeBackend(
            (
                chat_result(
                    "You prefer jasmine tea; schedule it Tuesday at 10:00.",
                    memory_used=(preference.id,),
                    model=LARGE_MODEL,
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "large"),)),
            FakeRetriever(
                (
                    hybrid_match(preference, 1),
                    hybrid_match(optional_schedule, 2),
                )
            ),
        )

        with self.assertRaises(ResponseValidationError):
            conversation.send("Turn my tea preference into a concise plan.")

    def test_single_cited_memory_must_cover_detectable_anchor(self) -> None:
        meeting = memory(
            1,
            "The user prefers robotics project meetings on Tuesday mornings.",
        )
        backend = FakeBackend(
            (
                chat_result(
                    "Your saved meeting preference is available.",
                    memory_used=(meeting.id,),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(meeting),)),
        )

        with self.assertRaises(ResponseValidationError):
            conversation.send("When do I prefer robotics project meetings?")

    def test_temporal_recall_cannot_omit_the_stored_daypart(self) -> None:
        meeting = memory(
            1,
            "The user prefers robotics project meetings on Tuesday mornings.",
        )
        backend = FakeBackend(
            (
                chat_result(
                    "You prefer robotics project meetings on Tuesday.",
                    memory_used=(meeting.id,),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(meeting),)),
        )

        with self.assertRaises(ResponseValidationError):
            conversation.send("When do I prefer robotics project meetings?")

    def test_temporal_recall_cannot_omit_correction_effective_time(self) -> None:
        corrected = replace(
            memory(2, "The user now prefers ginger tea without sugar."),
            kind="preference",
            supersedes_id=memory(1).id,
            valid_from="2026-08-07T09:00:00.000000Z",
        )
        conversation = routed_conversation(
            FakeBackend(
                (
                    chat_result(
                        "You now prefer ginger tea without sugar.",
                        memory_used=(corrected.id,),
                    ),
                )
            ),
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(corrected),)),
        )

        with self.assertRaises(ResponseValidationError):
            conversation.send("When did I change my tea preference?")

    def test_distinct_date_chronology_may_omit_metadata_clocks(self) -> None:
        corrected_tea, navigation = _distinct_date_chronology_memories()
        conversation = _chronology_conversation(
            _DISTINCT_DATE_CHRONOLOGY_SPEECH,
            corrected_tea,
            navigation,
        )

        reply = conversation.send(_DISTINCT_DATE_CHRONOLOGY_PROMPT)

        self.assertNotIn("09:00", reply.response.speech)
        self.assertNotIn("10:00", reply.response.speech)
        self.assertEqual(
            reply.response.memory_used,
            (corrected_tea.id, navigation.id),
        )

    def test_distinct_date_chronology_still_requires_exact_times(self) -> None:
        corrected_tea, navigation = _distinct_date_chronology_memories()
        conversation = _chronology_conversation(
            _DISTINCT_DATE_CHRONOLOGY_SPEECH,
            corrected_tea,
            navigation,
        )

        with self.assertRaises(ResponseValidationError):
            conversation.send(
                _DISTINCT_DATE_CHRONOLOGY_PROMPT
                + " Include the exact clock time for each entry."
            )

    def test_same_day_chronology_requires_metadata_clocks(self) -> None:
        corrected_tea = replace(
            memory(9, "The user now prefers ginger tea without sugar."),
            kind="preference",
            supersedes_id=memory(2).id,
            valid_from="2026-08-07T09:00:00.000000Z",
        )
        navigation = replace(
            memory(
                11,
                "The user completed the navigation milestone on Friday, "
                "7 August 2026.",
            ),
            kind="event",
            event_time="2026-08-07T10:00:00.000000Z",
        )
        conversation = _chronology_conversation(
            "1. Friday, August 7, 2026: you changed your tea preference to "
            "ginger without sugar. 2. Later that Friday, you completed the "
            "navigation milestone.",
            corrected_tea,
            navigation,
        )

        with self.assertRaises(ResponseValidationError):
            conversation.send(_DISTINCT_DATE_CHRONOLOGY_PROMPT)

    def test_chronology_cannot_omit_clock_from_canonical_text(self) -> None:
        corrected_tea, navigation = _distinct_date_chronology_memories()
        corrected_tea = replace(
            corrected_tea,
            canonical_text=(
                "The user changed her tea preference to ginger without sugar "
                "at 09:00 on Friday, 7 August 2026."
            ),
        )
        conversation = _chronology_conversation(
            _DISTINCT_DATE_CHRONOLOGY_SPEECH,
            corrected_tea,
            navigation,
        )

        with self.assertRaises(ResponseValidationError):
            conversation.send(_DISTINCT_DATE_CHRONOLOGY_PROMPT)

    def test_incomplete_or_ambiguous_dates_disable_clock_omission(self) -> None:
        _, navigation = _distinct_date_chronology_memories()
        missing_date = replace(
            memory(
                9,
                "The user changed her tea preference to ginger without sugar "
                "at 09:00.",
            ),
            kind="preference",
        )
        ambiguous_date = replace(
            memory(
                9,
                "The user's tea change was recorded for either Friday, "
                "7 August 2026 or Saturday, 8 August 2026.",
            ),
            kind="event",
            event_time="2026-08-07T09:00:00.000000Z",
        )
        cases = (
            (
                "missing",
                missing_date,
                "You changed your tea preference to ginger without sugar. "
                "You completed the navigation milestone on Saturday, August "
                "8, 2026, but the records do not establish their order.",
            ),
            (
                "ambiguous",
                ambiguous_date,
                "Your tea change was recorded for either Friday, August 7, "
                "2026 or Saturday, August 8, 2026. You completed the navigation "
                "milestone on Saturday, August 8, 2026, so their exact order "
                "is ambiguous.",
            ),
        )

        for label, first, speech in cases:
            with self.subTest(label=label):
                conversation = _chronology_conversation(
                    speech,
                    first,
                    navigation,
                )
                with self.assertRaises(ResponseValidationError):
                    conversation.send(_DISTINCT_DATE_CHRONOLOGY_PROMPT)

    def test_distinct_date_chronology_rejects_invented_clock(self) -> None:
        corrected_tea, navigation = _distinct_date_chronology_memories()
        conversation = _chronology_conversation(
            _DISTINCT_DATE_CHRONOLOGY_SPEECH.replace(
                "Friday, August 7, 2026:",
                "Friday, August 7, 2026 at 11:00:",
            ),
            corrected_tea,
            navigation,
        )

        with self.assertRaisesRegex(
            ResponseValidationError,
            "unsupported temporal precision",
        ):
            conversation.send(_DISTINCT_DATE_CHRONOLOGY_PROMPT)

    def test_distinct_date_chronology_requires_weekday_and_date(self) -> None:
        corrected_tea, navigation = _distinct_date_chronology_memories()
        incomplete_speeches = (
            _DISTINCT_DATE_CHRONOLOGY_SPEECH.replace("Friday, ", ""),
            _DISTINCT_DATE_CHRONOLOGY_SPEECH.replace(
                "August 7, 2026",
                "Friday",
            ),
        )

        for speech in incomplete_speeches:
            with self.subTest(speech=speech):
                conversation = _chronology_conversation(
                    speech,
                    corrected_tea,
                    navigation,
                )
                with self.assertRaises(ResponseValidationError):
                    conversation.send(_DISTINCT_DATE_CHRONOLOGY_PROMPT)

    def test_correction_effective_time_authorizes_only_entailed_detail(
        self,
    ) -> None:
        corrected = replace(
            memory(2, "The user now prefers ginger tea without sugar."),
            kind="preference",
            supersedes_id=memory(1).id,
            valid_from="2026-08-07T09:00:00.000000Z",
        )

        supported = routed_conversation(
            FakeBackend(
                (
                    chat_result(
                        "You now prefer ginger tea without sugar; the correction "
                        "became effective Friday, August 7, 2026 at 09:00.",
                        memory_used=(corrected.id,),
                    ),
                )
            ),
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(corrected),)),
        )
        reply = supported.send("Summarize my current ginger tea preference.")
        self.assertIn("Friday", reply.response.speech)

        invented = routed_conversation(
            FakeBackend(
                (
                    chat_result(
                        "You now prefer ginger tea without sugar; the correction "
                        "became effective Friday, August 7, 2026 at 10:00.",
                        memory_used=(corrected.id,),
                    ),
                )
            ),
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(corrected),)),
        )
        with self.assertRaises(ResponseValidationError):
            invented.send("Summarize my current ginger tea preference.")

    def test_invented_personal_relationship_is_rejected(self) -> None:
        meeting = memory(
            1,
            "The user prefers robotics project meetings on Tuesday mornings.",
        )
        backend = FakeBackend(
            (
                chat_result(
                    "You prefer Tuesday mornings, and Alice is your sister.",
                    memory_used=(meeting.id,),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(meeting),)),
        )

        with self.assertRaises(ResponseValidationError):
            conversation.send("When do I prefer robotics project meetings?")

    def test_invented_name_with_authorized_relationship_is_rejected(self) -> None:
        partner = memory(
            1, "Theo is the user's fictional robotics project partner."
        )
        backend = FakeBackend(
            (
                chat_result(
                    "Alice is your robotics project partner.",
                    memory_used=(partner.id,),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(partner),)),
        )

        with self.assertRaises(ResponseValidationError):
            conversation.send("Is Theo my robotics project partner?")

    def test_supported_name_with_sentence_leadin_is_accepted(self) -> None:
        partner = memory(
            1, "Theo is the user's fictional robotics project partner."
        )
        answers = (
            "Yes, Theo is your robotics project partner.",
            "Based on that memory, Theo is your robotics project partner.",
        )

        for speech in answers:
            with self.subTest(speech=speech):
                backend = FakeBackend(
                    (
                        chat_result(
                            speech,
                            memory_used=(partner.id,),
                        ),
                    )
                )
                conversation = routed_conversation(
                    backend,
                    FakeRouter((routing_result(True, "small"),)),
                    FakeRetriever((hybrid_match(partner),)),
                )

                reply = conversation.send(
                    "Is Theo my robotics project partner?"
                )

                self.assertEqual(reply.response.speech, speech)

    def test_question_does_not_authorize_proposed_relationship_as_fact(self) -> None:
        partner = memory(
            1, "Theo is the user's fictional robotics project partner."
        )
        conversation = routed_conversation(
            FakeBackend(
                (
                    chat_result(
                        "Theo is your brother.",
                        memory_used=(partner.id,),
                    ),
                )
            ),
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(partner),)),
        )

        with self.assertRaises(ResponseValidationError):
            conversation.send("Is Theo my brother?")

    def test_coordinated_relationship_and_unstated_attendee_are_rejected(
        self,
    ) -> None:
        partner = memory(
            1, "Theo is the user's fictional robotics project partner."
        )
        answers = (
            "You and Theo are friends.",
            "Theo is your robotics project partner. Alice joins the meeting.",
        )

        for speech in answers:
            with self.subTest(speech=speech):
                conversation = routed_conversation(
                    FakeBackend(
                        (
                            chat_result(
                                speech,
                                memory_used=(partner.id,),
                            ),
                        )
                    ),
                    FakeRouter((routing_result(True, "small"),)),
                    FakeRetriever((hybrid_match(partner),)),
                )

                with self.assertRaises(ResponseValidationError):
                    conversation.send("Who is Theo to me?")

    def test_client_server_term_is_not_a_personal_relationship(self) -> None:
        preference = memory(
            1, "The user prefers a client-server software architecture."
        )
        conversation = routed_conversation(
            FakeBackend(
                (
                    chat_result(
                        "You prefer a client-server software architecture.",
                        memory_used=(preference.id,),
                    ),
                )
            ),
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(preference),)),
        )

        reply = conversation.send("What software architecture do I prefer?")

        self.assertIn("client-server", reply.response.speech)

    def test_wrong_perspective_and_positive_fact_negation_are_rejected(self) -> None:
        partner = memory(
            1, "Theo is the user's fictional robotics project partner."
        )
        meeting = memory(
            2,
            "The user prefers robotics project meetings on Tuesday mornings.",
        )
        cases = (
            (
                partner,
                "Who is Theo to me?",
                "Theo is not your robotics project partner.",
            ),
            (
                partner,
                "Who is Theo to me?",
                "Theo isn't your robotics project partner.",
            ),
            (
                partner,
                "Who is Theo to me?",
                "Theo isn’t your robotics project partner.",
            ),
            (
                meeting,
                "When do I prefer robotics project meetings?",
                "You do not prefer Tuesday mornings.",
            ),
            (
                meeting,
                "When do I prefer robotics project meetings?",
                "You don’t prefer Tuesday mornings.",
            ),
            (
                meeting,
                "When do I prefer robotics project meetings?",
                "Tuesday mornings are not your preferred meeting time.",
            ),
            (
                meeting,
                "When do I prefer robotics project meetings?",
                "I prefer Tuesday mornings.",
            ),
            (
                meeting,
                "When do I prefer robotics project meetings?",
                "The user prefers Tuesday mornings.",
            ),
            (
                meeting,
                "When do I prefer robotics project meetings?",
                "My preference is Tuesday mornings.",
            ),
        )

        for item, request, speech in cases:
            with self.subTest(speech=speech):
                conversation = routed_conversation(
                    FakeBackend(
                        (
                            chat_result(
                                speech,
                                memory_used=(item.id,),
                            ),
                        )
                    ),
                    FakeRouter((routing_result(True, "small"),)),
                    FakeRetriever((hybrid_match(item),)),
                )

                with self.assertRaises(ResponseValidationError):
                    conversation.send(request)

    def test_exact_three_step_memory_rejects_two_step_output(self) -> None:
        plan_format = memory(
            1,
            "The user prefers project plans containing exactly three concise steps.",
        )
        conversation = routed_conversation(
            FakeBackend(
                (
                    chat_result(
                        "You prefer project plans containing exactly three concise "
                        "steps. 1. Draft. 2. Review.",
                        memory_used=(plan_format.id,),
                        model=LARGE_MODEL,
                    ),
                )
            ),
            FakeRouter((routing_result(True, "large"),)),
            FakeRetriever((hybrid_match(plan_format),)),
        )

        with self.assertRaises(ResponseValidationError):
            conversation.send("Create a project plan in my preferred format.")

    def test_iso_event_time_authorizes_only_its_date_and_clock(self) -> None:
        appointment = replace(
            memory(1, "The user has a dentist appointment."),
            event_time="2026-09-08T10:00:00.000000Z",
        )

        correct = routed_conversation(
            FakeBackend(
                (
                    chat_result(
                        "Your dentist appointment is September 8, 2026 at 10:00.",
                        memory_used=(appointment.id,),
                    ),
                )
            ),
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(appointment),)),
        )
        reply = correct.send("When is my dentist appointment?")
        self.assertIn("10:00", reply.response.speech)

        invented = routed_conversation(
            FakeBackend(
                (
                    chat_result(
                        "Your dentist appointment is September 8, 2026 at midnight.",
                        memory_used=(appointment.id,),
                    ),
                )
            ),
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(appointment),)),
        )
        with self.assertRaises(ResponseValidationError):
            invented.send("When is my dentist appointment?")

    def test_modal_may_and_non_temporal_this_are_not_dates_or_modifiers(
        self,
    ) -> None:
        meeting = memory(
            1,
            "The user prefers robotics project meetings on Tuesday mornings.",
        )
        backend = FakeBackend(
            (
                chat_result(
                    "You may use this concise plan for your Tuesday morning meeting.",
                    memory_used=(meeting.id,),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(meeting),)),
        )

        reply = conversation.send(
            "Give me a concise plan for my usual meeting time."
        )

        self.assertIn("Tuesday morning", reply.response.speech)

    def test_memory_identifier_in_speech_is_rejected(self) -> None:
        preference = memory(1, "The user prefers jasmine tea.")
        backend = FakeBackend(
            (
                chat_result(
                    f"According to {preference.id}, you prefer jasmine tea.",
                    memory_used=(preference.id,),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(preference),)),
        )

        with self.assertRaises(ResponseValidationError):
            conversation.send("What tea do I prefer?")

    def test_unsupported_temporal_qualifier_is_rejected(self) -> None:
        meeting = memory(
            1,
            "The user prefers robotics project meetings on Tuesday mornings.",
        )
        unsupported_answers = (
            "You prefer robotics project meetings on Tuesday evenings.",
            "Your next robotics project meeting is Tuesday morning.",
            "You prefer robotics project meetings Tuesday morning at 11:00.",
            "You prefer robotics project meetings Tuesday morning at ten o'clock.",
            "You prefer robotics project meetings Tuesday morning on September 9.",
        )

        for speech in unsupported_answers:
            with self.subTest(speech=speech):
                backend = FakeBackend(
                    (
                        chat_result(
                            speech,
                            memory_used=(meeting.id,),
                        ),
                    )
                )
                conversation = routed_conversation(
                    backend,
                    FakeRouter((routing_result(True, "small"),)),
                    FakeRetriever((hybrid_match(meeting),)),
                )

                with self.assertRaises(ResponseValidationError):
                    conversation.send(
                        "When do I prefer robotics project meetings?"
                    )

    def test_temporal_dayparts_cannot_be_swapped_between_weekdays(self) -> None:
        monday = memory(1, "The user meets on Monday mornings.")
        tuesday = memory(2, "The user meets on Tuesday evenings.")
        ids = (monday.id, tuesday.id)
        backend = FakeBackend(
            (
                chat_result(
                    "You meet Monday evening and Tuesday morning.",
                    memory_used=ids,
                    model=LARGE_MODEL,
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "large"),)),
            FakeRetriever((hybrid_match(monday, 1), hybrid_match(tuesday, 2))),
        )

        with self.assertRaises(ResponseValidationError):
            conversation.send("Summarize both meeting schedules.")

    def test_clock_times_cannot_be_swapped_between_weekdays(self) -> None:
        monday = memory(1, "The user meets on Monday at 10:00.")
        tuesday = memory(2, "The user meets on Tuesday at 11:00.")
        ids = (monday.id, tuesday.id)
        unsupported_answers = (
            "You meet Monday at 11:00 and Tuesday at 10:00.",
            "You meet Monday at 11:00. Tuesday at 10:00.",
        )
        for speech in unsupported_answers:
            with self.subTest(speech=speech):
                backend = FakeBackend(
                    (
                        chat_result(
                            speech,
                            memory_used=ids,
                            model=LARGE_MODEL,
                        ),
                    )
                )
                conversation = routed_conversation(
                    backend,
                    FakeRouter((routing_result(True, "large"),)),
                    FakeRetriever(
                        (hybrid_match(monday, 1), hybrid_match(tuesday, 2))
                    ),
                )

                with self.assertRaises(ResponseValidationError):
                    conversation.send("Summarize both meeting times.")

    def test_clock_times_cannot_be_swapped_between_dates(self) -> None:
        september = memory(1, "The user's review is September 9 at 10:00.")
        october = memory(2, "The user's review is October 10 at 11:00.")
        ids = (september.id, october.id)
        backend = FakeBackend(
            (
                chat_result(
                    "Your reviews are September 9 at 11:00 and October 10 "
                    "at 10:00.",
                    memory_used=ids,
                    model=LARGE_MODEL,
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "large"),)),
            FakeRetriever(
                (hybrid_match(september, 1), hybrid_match(october, 2))
            ),
        )

        with self.assertRaises(ResponseValidationError):
            conversation.send("Summarize both review dates and times.")

    def test_additional_common_clock_forms_are_rejected(self) -> None:
        meeting = memory(
            1,
            "The user prefers robotics project meetings on Tuesday mornings.",
        )
        unsupported_answers = (
            "You prefer robotics project meetings Tuesday morning at 10.",
            "You prefer robotics project meetings Tuesday at half past ten.",
            "You prefer robotics project meetings Tuesday at quarter to ten.",
            "You prefer Tuesday morning at 10 o'clock with the team.",
            "You prefer Tuesday morning at 10 in the morning.",
            "You prefer Tuesday morning on the 9th.",
            "Your Tuesday morning meeting is next week.",
        )

        for speech in unsupported_answers:
            with self.subTest(speech=speech):
                backend = FakeBackend(
                    (
                        chat_result(
                            speech,
                            memory_used=(meeting.id,),
                        ),
                    )
                )
                conversation = routed_conversation(
                    backend,
                    FakeRouter((routing_result(True, "small"),)),
                    FakeRetriever((hybrid_match(meeting),)),
                )

                with self.assertRaises(ResponseValidationError):
                    conversation.send(
                        "When do I prefer robotics project meetings?"
                    )

    def test_non_temporal_number_phrase_is_not_treated_as_a_clock(self) -> None:
        meeting = memory(
            1,
            "The user prefers robotics project meetings on Tuesday mornings.",
        )
        backend = FakeBackend(
            (
                chat_result(
                    "You prefer Tuesday mornings; order supplies from one "
                    "supplier.",
                    memory_used=(meeting.id,),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(meeting),)),
        )

        reply = conversation.send("Plan supplies for my usual meeting time.")

        self.assertIn("one supplier", reply.response.speech)

    def test_no_evidence_memory_answer_cannot_invent_a_clock_time(self) -> None:
        backend = FakeBackend(
            (
                chat_result(
                    "Your favorite music session is Tuesday at 10:00.",
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever(()),
        )

        reply = conversation.send("When do I listen to my favorite music?")

        self.assertEqual(
            reply.response.speech,
            "I do not have a verified personal memory that answers that.",
        )
        self.assertNotIn("10:00", reply.response.speech)

    def test_noon_is_allowed_as_a_paraphrase_of_twelve_hundred(self) -> None:
        appointment = memory(1, "The user's appointment is at 12:00.")
        backend = FakeBackend(
            (
                chat_result(
                    "Your appointment is at noon.",
                    memory_used=(appointment.id,),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(appointment),)),
        )

        reply = conversation.send("When is my appointment?")

        self.assertIn("noon", reply.response.speech)


class RecencyComparisonRegressionTests(unittest.TestCase):
    def test_declared_budget_supplies_and_allows_all_three_records(self) -> None:
        items = _recency_comparison_memories()
        memory_ids = tuple(item.id for item in items)
        conversation, backend, _ = _recency_comparison_conversation(
            _RECENCY_COMPARISON_SPEECH,
            memory_ids,
            context_length=2176,
        )

        reply = conversation.send(_RECENCY_COMPARISON_PROMPT)

        self.assertEqual(reply.memory_diagnostics.supplied_ids, memory_ids)
        self.assertEqual(reply.response.memory_used, memory_ids)
        _, messages, schema = backend.calls[0]
        payload, _ = decode_memory_envelope(messages[-1])
        self.assertEqual(
            tuple(record["id"] for record in payload["records"]),
            memory_ids,
        )
        self.assertEqual(
            tuple(schema["properties"]["memory_used"]["items"]["enum"]),
            memory_ids,
        )

    def test_collaborator_answer_and_citation_are_both_required(self) -> None:
        items = _recency_comparison_memories()
        memory_ids = tuple(item.id for item in items)
        milestone_ids = memory_ids[:2]
        milestones_only = (
            "Your Luma kickoff milestone was Monday, August 3, 2026. Your "
            "navigation prototype milestone was Saturday, August 8, 2026, so "
            "navigation is newer."
        )
        incomplete_answers = (
            (milestones_only, milestone_ids),
            (milestones_only, memory_ids),
            (_RECENCY_COMPARISON_SPEECH, milestone_ids),
            (
                milestones_only + " Theo is not your collaborator.",
                memory_ids,
            ),
            (
                milestones_only + " Theo is Alice's collaborator.",
                memory_ids,
            ),
        )

        for speech, cited_ids in incomplete_answers:
            with self.subTest(speech=speech, cited_ids=cited_ids):
                conversation, _, _ = _recency_comparison_conversation(
                    speech,
                    cited_ids,
                )
                with self.assertRaises(ResponseValidationError):
                    conversation.send(_RECENCY_COMPARISON_PROMPT)

    def test_collaborator_binding_accepts_positive_user_owned_forms(self) -> None:
        items = _recency_comparison_memories()
        memory_ids = tuple(item.id for item in items)
        milestone_speech = (
            "Your Luma kickoff milestone was Monday, August 3, 2026. Your "
            "navigation prototype milestone was Saturday, August 8, 2026, so "
            "navigation is newer. "
        )
        collaborator_forms = (
            "Theo is your collaborator.",
            "Theo, your robotics project partner, is the collaborator.",
            "Your robotics project partner is Theo.",
            "Theo works with you.",
        )

        for collaborator_form in collaborator_forms:
            with self.subTest(collaborator_form=collaborator_form):
                conversation, _, _ = _recency_comparison_conversation(
                    milestone_speech + collaborator_form,
                    memory_ids,
                )
                reply = conversation.send(_RECENCY_COMPARISON_PROMPT)
                self.assertEqual(reply.response.memory_used, memory_ids)


class RelationshipCompletenessRegressionTests(unittest.TestCase):
    """Citations must express the relationship, not just its person's name."""

    def conversation(self, texts, speech, *, model_size="large"):
        items = tuple(memory(index, text) for index, text in enumerate(texts, 1))
        model = LARGE_MODEL if model_size == "large" else SMALL_MODEL
        backend = FakeBackend((
            chat_result(
                speech, memory_used=tuple(item.id for item in items), model=model
            ),
        ))
        matches = tuple(
            hybrid_match(item, index) for index, item in enumerate(items, 1)
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, model_size),)),
            FakeRetriever(matches),
            context_length=4096,
        )
        return conversation, backend

    def test_three_memory_plan_rejects_missing_or_unbound_relationship(
        self,
    ) -> None:
        texts = (
            "Theo is the user's fictional robotics project partner.",
            "The user prefers robotics project meetings on Tuesday mornings.",
            "The user prefers project plans containing exactly three concise steps.",
        )
        bad_steps = (
            "Meet Theo on Tuesday mornings.",
            "Meet Theo, your partner, on Tuesday mornings.",
            "Meet Theo on Tuesday mornings with your robotics project partner.",
            "Meet Theo on Tuesday mornings. Your robotics project partner can help.",
            "Meet Theo on Tuesday mornings. Discuss your robotics project partner.",
        )
        for first_step in bad_steps:
            speech = (
                "1. " + first_step
                + " 2. Review your robotics project. 3. Plan your next tasks."
            )
            with self.subTest(first_step=first_step):
                conversation, backend = self.conversation(texts, speech)
                before = conversation.messages
                with self.assertRaisesRegex(
                    ResponseValidationError, "relationship"
                ) as caught:
                    conversation.send(
                        "Using what you remember about Theo, my robotics-project "
                        "meeting schedule, and my preferred project-plan format, "
                        "create a plan for our next meeting."
                    )
                self.assertEqual(conversation.messages, before)
                self.assertEqual(len(backend.calls), 1)
                self.assertNotIn("Theo", str(caught.exception))
                self.assertNotIn("mem_", str(caught.exception))

    def test_relationship_paraphrases_preserve_name_role_and_context(self) -> None:
        text = "Theo is the user's fictional robotics project partner."
        answers = (
            "Theo is your robotics project partner.",
            "Theo, your robotics-project partner, can review the agenda.",
            "Coordinate with your robotics project partner, Theo.",
            "Your partner on the robotics project is Theo.",
            "Meet Theo, your partner for the robotics project.",
            "You and Theo are robotics project partners.",
            "Theo and you are partners on the robotics project.",
        )
        for speech in answers:
            with self.subTest(speech=speech):
                conversation, _ = self.conversation(
                    (text,), speech, model_size="small"
                )
                reply = conversation.send("Who is Theo to me?")
                self.assertEqual(reply.response.speech, speech)

    def test_relationship_context_cannot_be_borrowed_from_other_sentences(
        self,
    ) -> None:
        text = "Theo is the user's fictional robotics project partner."
        answers = (
            "Theo is your partner. You work on a robotics project.",
            "Theo helps with robotics projects. Your partner joins you.",
            "Theo is your project partner. You like robotics.",
        )
        for speech in answers:
            with self.subTest(speech=speech):
                conversation, _ = self.conversation((text,), speech)
                with self.assertRaisesRegex(
                    ResponseValidationError, "relationship"
                ):
                    conversation.send("Summarize what you remember about Theo.")

    def test_two_known_people_cannot_exchange_relationships(self) -> None:
        texts = (
            "Theo is the user's robotics project partner.",
            "Mira is the user's sister.",
        )
        conversation, _ = self.conversation(
            texts, "Theo is your sister. Mira is your robotics project partner."
        )
        with self.assertRaisesRegex(ResponseValidationError, "relationship"):
            conversation.send("Who are Theo and Mira to me?")

    def test_non_fixture_relationship_is_checked_without_kind_metadata(
        self,
    ) -> None:
        text = "Mira is the user's older sister."
        for speech in ("Mira can help.", "Mira is your sister."):
            with self.subTest(speech=speech):
                conversation, _ = self.conversation((text,), speech)
                with self.assertRaisesRegex(
                    ResponseValidationError, "relationship"
                ):
                    conversation.send("Who is Mira to me?")
        conversation, _ = self.conversation(
            (text,), "Ask Mira, your older sister, to help."
        )
        self.assertIn(
            "older sister", conversation.send("Who is Mira to me?").response.speech
        )


if __name__ == "__main__":
    unittest.main()
