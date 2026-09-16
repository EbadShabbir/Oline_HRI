"""Second-repair regressions: current relationship witnesses, no inference."""

import unittest

from oline_hri.conversation import (
    ConversationError, _collaborator_request_link,
    _require_requested_named_collaborator,
)
from oline_hri.relationships import has_named_user_relationship
from oline_hri.response import RobotResponse, ResponseValidationError
from tests.test_conversation_routed import (
    FakeBackend, FakeRetriever, FakeRouter, chat_result, hybrid_match, memory,
    routed_conversation, routing_result,
)


QUERY = (
    "Returning to my earlier walking partner information, "
    "who is my current walking partner?"
)
SOURCE = "Your walking partner is Niko Fern."


class CurrentRelationshipWitnessTests(unittest.TestCase):
    def test_optional_filters_preserve_existing_historical_lookup(self):
        self.assertTrue(has_named_user_relationship(
            "Niko Fern was your former walking partner.", "Niko Fern"))
        self.assertFalse(has_named_user_relationship(
            "Niko Fern was your former walking partner.", "Niko Fern",
            current_only=True))

    def test_current_source_and_addressed_speech_are_bound_to_one_witness(self):
        for text in (
            SOURCE, "Niko Fern is your walking partner.",
            "Niko Fern is your current walking partner.",
            "Niko Fern, your walking partner, can help.",
            "You and Niko Fern are walking partners.",
        ):
            for addressed in (False, True):
                with self.subTest(text=text, addressed=addressed):
                    self.assertTrue(has_named_user_relationship(
                        text, "Niko Fern", current_only=True, role="partner",
                        qualifiers=frozenset({"walking"}),
                        addressed_to_user=addressed))
        self.assertTrue(has_named_user_relationship(
            "My walking partner is Niko Fern.", "Niko Fern", current_only=True,
            role="partner", qualifiers=frozenset({"walking"})))
        self.assertFalse(has_named_user_relationship(
            "My walking partner is Niko Fern.", "Niko Fern", current_only=True,
            role="partner", qualifiers=frozenset({"walking"}),
            addressed_to_user=True))

    def test_current_lookup_rejects_past_former_negative_and_other_person(self):
        for text in (
            "Niko Fern was your walking partner.",
            "Your walking partner was Niko Fern.",
            "You and Niko Fern were walking partners.",
            "Niko Fern was your current walking partner.",
            "Niko Fern is your former walking partner.",
            "Niko Fern is your previous walking partner.",
            "Niko Fern is your past walking partner.",
            "Niko Fern is your old walking partner.",
            "Niko Fern is not your walking partner.",
            "Maybe Niko Fern is your walking partner.",
            "Niko Fern is Lina's walking partner.",
            "Elora Vale is your walking partner.",
            "Niko Fern is your chess partner. You enjoy walking.",
            "Niko Fern is your walking friend. Your partner is Elora Vale.",
        ):
            with self.subTest(text=text):
                self.assertFalse(has_named_user_relationship(
                    text, "Niko Fern", current_only=True, role="partner",
                    qualifiers=frozenset({"walking"})))

    def test_query_link_accepts_present_tense_without_literal_current(self):
        for query, source in (
            (QUERY, SOURCE),
            ("Who is my current walking partner?", "Niko Fern is your walking partner."),
            ("Who is my current garden project partner?", "Your garden project partner is Rina Moss."),
            ("Identify my current garden-project partner.", "Rina Moss is your partner on the garden project."),
        ):
            with self.subTest(query=query, source=source):
                self.assertTrue(_collaborator_request_link(query, source))

    def test_query_link_cannot_borrow_role_domain_or_named_owner(self):
        for source in (
            "Niko Fern was your walking partner.",
            "Your current walking partner was Niko Fern.",
            "Niko Fern is your former walking partner.",
            "Your walking partner is Niko Fern. Current ideas are available.",
            "Niko Fern is your friend. Your current walking partner is unknown.",
            "Niko Fern is your chess partner. Your current walking routine is pleasant.",
            "Niko Fern is Lina's current walking partner.",
        ):
            # The unrelated 'current ideas' sentence must not affect an
            # otherwise valid positive relationship witness.
            expected = source.startswith("Your walking partner is Niko Fern.")
            with self.subTest(source=source):
                self.assertIs(_collaborator_request_link(QUERY, source), expected)

    def test_noncurrent_relationship_query_keeps_legacy_behavior(self):
        self.assertTrue(_collaborator_request_link(
            "Who is my former walking partner?",
            "Niko Fern was your former walking partner."))


class CurrentRelationshipDeliveryTests(unittest.TestCase):
    def test_current_delivery_requires_the_same_present_person_role_and_domain(self):
        item = memory(2, SOURCE)
        for speech, passes in (
            (SOURCE, True),
            ("Niko Fern is your walking partner.", True),
            ("Niko Fern was your walking partner.", False),
            ("Your walking partner was Niko Fern.", False),
            ("Niko Fern is your former walking partner.", False),
            ("Your walking partner is Elora Vale.", False),
            ("Niko Fern is your partner.", False),
            ("Niko Fern is your chess partner. You enjoy walking.", False),
            ("Niko Fern is not your walking partner.", False),
            ("Niko Fern is my walking partner.", False),
            ("Niko Fern is Lina's walking partner.", False),
        ):
            response = RobotResponse(speech=speech, gesture_id="NO_ACTION",
                memory_used=(item.id,), allowed_memory_ids=(item.id,))
            with self.subTest(speech=speech):
                if passes:
                    _require_requested_named_collaborator(response, (hybrid_match(item),), QUERY)
                else:
                    with self.assertRaises(ResponseValidationError):
                        _require_requested_named_collaborator(response, (hybrid_match(item),), QUERY)

    def test_multiple_cited_current_people_cannot_silently_lose_one(self):
        items = (memory(1, SOURCE), memory(2, "Elora Vale is your walking partner."))
        response = RobotResponse(speech=SOURCE, gesture_id="NO_ACTION",
            memory_used=tuple(item.id for item in items),
            allowed_memory_ids=tuple(item.id for item in items))
        with self.assertRaises(ResponseValidationError):
            _require_requested_named_collaborator(response,
                tuple(hybrid_match(item) for item in items), QUERY)

    def test_conversation_delivers_supported_replacement_with_real_validators(self):
        item = memory(2, SOURCE)
        for composed in (False, True):
            backend = FakeBackend((chat_result(SOURCE, memory_used=(item.id,)),))
            retriever = FakeRetriever((hybrid_match(item),), snapshot_outcomes=(True, True))
            conversation = routed_conversation(backend, FakeRouter((routing_result(True),)),
                retriever, grounded_composition=composed)
            reply = conversation.send(QUERY)
            self.assertEqual(reply.response.speech, SOURCE)
            self.assertEqual(reply.response.memory_used, (item.id,))
            self.assertEqual(len(backend.calls), 1)
            self.assertEqual(len(retriever.current_calls), 2)

    def test_conversation_rejects_past_or_wrong_person_without_composition(self):
        item = memory(2, SOURCE)
        for speech in ("Niko Fern was your walking partner.",
                       "Elora Vale is your walking partner."):
            with self.subTest(speech=speech):
                conversation = routed_conversation(
                    FakeBackend((chat_result(speech, memory_used=(item.id,)),)),
                    FakeRouter((routing_result(True),)),
                    FakeRetriever((hybrid_match(item),)), grounded_composition=False)
                with self.assertRaises(ResponseValidationError):
                    conversation.send(QUERY)

    def test_snapshot_change_still_withholds_and_missing_record_still_abstains(self):
        item = memory(2, SOURCE)
        for outcomes in ((False,), (True, False)):
            conversation = routed_conversation(
                FakeBackend((chat_result(SOURCE, memory_used=(item.id,)),)),
                FakeRouter((routing_result(True),)),
                FakeRetriever((hybrid_match(item),), snapshot_outcomes=outcomes))
            with self.assertRaises(ConversationError):
                conversation.send(QUERY)
        conversation = routed_conversation(
            FakeBackend((chat_result("I don't have that information."),)),
            FakeRouter((routing_result(True),)), FakeRetriever())
        reply = conversation.send(QUERY)
        self.assertEqual(reply.response.memory_used, ())
        self.assertNotIn("Niko", reply.response.speech)


if __name__ == "__main__":
    unittest.main()
