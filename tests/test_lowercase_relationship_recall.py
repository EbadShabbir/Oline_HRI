"""Regressions for bounded lowercase-name relationship recall."""

import unittest

from oline_hri.relationships import has_named_user_relationship
from tests.test_conversation_routed import (
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


class LowercaseRelationshipRecallTests(unittest.TestCase):
    def test_lowercase_name_and_transposed_know_require_relationship(self) -> None:
        unrelated = memory(1, "The user prefers Friday afternoons.")
        rina = memory(
            2, "Rina is the user's fictional sensor-calibration partner."
        )
        backend = FakeBackend(
            (
                chat_result(
                    "Rina is your sensor-calibration partner.",
                    memory_used=(rina.id,),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(unrelated, 1), hybrid_match(rina, 2))),
        )

        reply = conversation.send("do you knwo who rina is")

        payload, request = decode_memory_envelope(backend.calls[0][1][-1])
        memory_schema = backend.calls[0][2]["properties"]["memory_used"]
        self.assertEqual(request, "Who is Rina to me?")
        self.assertEqual(
            [record["id"] for record in payload["records"]], [rina.id]
        )
        self.assertEqual(
            reply.memory_diagnostics.retrieved_ids,
            (unrelated.id, rina.id),
        )
        self.assertEqual(reply.memory_diagnostics.supplied_ids, (rina.id,))
        self.assertEqual(reply.memory_diagnostics.model_used_ids, (rina.id,))
        self.assertEqual(memory_schema["items"]["enum"], [rina.id])
        self.assertEqual(memory_schema["minItems"], 1)

    def test_direct_recall_omits_unrelated_generation_history_without_erasing_it(
        self,
    ) -> None:
        rina = memory(
            1, "Rina is the user's fictional sensor-calibration partner."
        )
        stress_prompt = (
            "today i talked to rina , i am so stressed after talking to her "
        )
        backend = FakeBackend(
            (
                chat_result(
                    "I'm sorry you're feeling stressed after talking with "
                    "Rina. Take a slow breath and give yourself a moment."
                ),
                chat_result(
                    "Rina is your fictional sensor-calibration partner.",
                    memory_used=(rina.id,),
                ),
            )
        )
        conversation = routed_conversation(
            backend,
            FakeRouter(
                (
                    routing_result(False, "small"),
                    routing_result(True, "small"),
                )
            ),
            FakeRetriever((hybrid_match(rina),)),
        )

        conversation.send(stress_prompt)
        history_before_recall = conversation.messages
        reply = conversation.send("do you knwo who rina is")

        recall_messages = backend.calls[1][1]
        self.assertEqual(
            [message.role for message in recall_messages],
            ["system", "user"],
        )
        self.assertNotIn(
            stress_prompt.strip(),
            "\n".join(message.content for message in recall_messages),
        )
        self.assertEqual(
            reply.memory_diagnostics.model_used_ids, (rina.id,)
        )
        self.assertEqual(conversation.messages, history_before_recall)

    def test_bounded_direct_relationship_phrasings_accept_lowercase_name(
        self,
    ) -> None:
        requests = (
            "who is rina?",
            "who is rina to me?",
            "how do i know rina?",
            "do you know who rina is?",
        )
        for request in requests:
            with self.subTest(request=request):
                rina = memory(
                    1, "Rina is the user's sensor-calibration partner."
                )
                conversation = routed_conversation(
                    FakeBackend(
                        (
                            chat_result(
                                "Rina is your sensor-calibration partner.",
                                memory_used=(rina.id,),
                            ),
                        )
                    ),
                    FakeRouter((routing_result(True, "small"),)),
                    FakeRetriever((hybrid_match(rina),)),
                )

                reply = conversation.send(request)

                self.assertEqual(
                    reply.memory_diagnostics.supplied_ids, (rina.id,)
                )
                self.assertEqual(
                    reply.memory_diagnostics.model_used_ids, (rina.id,)
                )

    def test_same_lowercase_token_does_not_authorize_unrelated_records(
        self,
    ) -> None:
        records = (
            "The user keeps Rina notes in a local folder.",
            "Mira is the user's Rina research partner.",
            "Rina is Alice's sensor-calibration partner.",
        )
        for index, canonical_text in enumerate(records, 1):
            with self.subTest(canonical_text=canonical_text):
                candidate = memory(index, canonical_text)
                backend = FakeBackend(
                    (
                        chat_result(
                            "A candidate mentions Rina.",
                            memory_used=(candidate.id,),
                        ),
                    )
                )
                conversation = routed_conversation(
                    backend,
                    FakeRouter((routing_result(True, "small"),)),
                    FakeRetriever((hybrid_match(candidate),)),
                )

                reply = conversation.send("do you know who rina is?")

                self.assertEqual(
                    reply.memory_diagnostics.supplied_ids, (candidate.id,)
                )
                self.assertEqual(reply.memory_diagnostics.model_used_ids, ())
                self.assertEqual(
                    reply.response.speech,
                    "I do not have a verified personal memory that answers that.",
                )
                memory_schema = backend.calls[0][2]["properties"]["memory_used"]
                self.assertNotIn("minItems", memory_schema)

    def test_lowercase_name_outside_direct_relationship_shape_is_not_promoted(
        self,
    ) -> None:
        rina = memory(1, "Rina is the user's sensor-calibration partner.")
        conversation = routed_conversation(
            FakeBackend(
                (
                    chat_result(
                        "Rina is your sensor-calibration partner.",
                        memory_used=(rina.id,),
                    ),
                )
            ),
            FakeRouter((routing_result(True, "small"),)),
            FakeRetriever((hybrid_match(rina),)),
        )

        reply = conversation.send("what did rina say?")

        self.assertEqual(reply.memory_diagnostics.model_used_ids, ())
        self.assertEqual(
            reply.response.speech,
            "I do not have a verified personal memory that answers that.",
        )


class NamedUserRelationshipTests(unittest.TestCase):
    def test_exact_person_must_be_bound_to_the_user(self) -> None:
        self.assertTrue(
            has_named_user_relationship(
                "Rina is the user's sensor-calibration partner.", "rina"
            )
        )
        for canonical_text in (
            "The user keeps Rina notes in a local folder.",
            "Mira is the user's Rina research partner.",
            "Rina is Alice's sensor-calibration partner.",
        ):
            with self.subTest(canonical_text=canonical_text):
                self.assertFalse(
                    has_named_user_relationship(canonical_text, "rina")
                )


if __name__ == "__main__":
    unittest.main()
