"""Offline regressions for history authorization and scoped location recall."""

from dataclasses import replace
from copy import deepcopy
import unittest

from oline_hri.conversation import (
    _ACKNOWLEDGMENT_RULE, _DIRECT_MEMORY_RESPONSE_RULE, _verified_composed_answer,
)
from oline_hri.grounded_composition import AnswerFact, compose_verified_location
from oline_hri.evaluation_scoring import _cascade, EvaluationScoringError
from oline_hri.ollama import ChatMessage
from oline_hri.response import ResponseValidationError
from test_conversation_routed import (
    FakeBackend, FakeRetriever, FakeRouter, chat_result, hybrid_match, memory,
    routed_conversation, routing_result,
)
from test_evaluation_scoring import _find, _raw_records


class LifecycleHistoryRepairTests(unittest.TestCase):
    def conversation(self, matches, answer, *, personal=True):
        backend = FakeBackend((answer,))
        router = FakeRouter(default=routing_result(personal))
        retriever = FakeRetriever(matches)
        conversation = routed_conversation(backend, router, retriever)
        conversation._messages.extend((
            ChatMessage(role="user", content="My compass is in the orange satchel."),
            ChatMessage(role="assistant", content=chat_result(
                "Your compass is in the orange satchel.").content),
        ))
        return conversation, backend, router, retriever

    def test_corrected_followup_uses_current_evidence_without_old_statement_or_echo(self):
        item = memory(2, "Your compass is in the grey cupboard.")
        conversation, backend, router, retriever = self.conversation(
            (hybrid_match(item),),
            chat_result("Your compass is in the grey cupboard.", memory_used=(item.id,)),
        )
        retained = conversation.messages
        reply = conversation.send("What about my compass location again?")
        self.assertEqual(reply.response.memory_used, (item.id,))
        self.assertNotIn("orange satchel", str(backend.calls[0][1]))
        self.assertIn("grey cupboard", str(backend.calls[0][1]))
        self.assertEqual(router.calls[0][1], retained[1:])
        self.assertEqual(conversation.messages, retained)
        self.assertEqual(len(retriever.current_calls), 2)

    def test_absent_personal_memory_cannot_be_reauthorized_by_historical_question(self):
        for question in (
            "What compass location did I tell you earlier, before I asked you to forget it?",
            "Returning to my earlier compass information, where is it now?",
        ):
            with self.subTest(question=question):
                conversation, backend, _, _ = self.conversation((), chat_result(
                    "Your compass is in the orange satchel."))
                retained = conversation.messages
                reply = conversation.send(question)
                self.assertEqual(reply.response.speech,
                                 "I do not have a verified personal memory that answers that.")
                self.assertEqual(reply.response.memory_used, ())
                self.assertNotIn("orange satchel", str(backend.calls[0][1]))
                self.assertEqual(conversation.messages, retained)

    def test_general_followup_still_receives_conversation_context(self):
        conversation, backend, _, _ = self.conversation((), chat_result("A compass shows direction."),
                                                       personal=False)
        conversation._messages[1:] = [
            ChatMessage(role="user", content="Explain how a compass works."),
            ChatMessage(role="assistant", content=chat_result("It follows a magnetic field.").content),
        ]
        retained = conversation.messages
        conversation.send("Explain that more simply.")
        self.assertEqual(backend.calls[0][1][1:-1], retained[1:])

    def test_generation_instructions_do_not_supply_example_personal_facts(self):
        instructions = _ACKNOWLEDGMENT_RULE + _DIRECT_MEMORY_RESPONSE_RULE
        for value in ("jasmine", "Sam", "Tuesdays", "without sugar"):
            self.assertNotIn(value, instructions)

    def test_location_only_request_constrains_speech_without_event_clock(self):
        item = replace(memory(3, "Your Orchid rehearsal was at Rowan Hall on 2026-09-02 at 18:30."),
                       event_time="2026-09-02T18:30:00+00:00")
        conversation, backend, _, _ = self.conversation((hybrid_match(item),), chat_result(
            "Your Orchid rehearsal was at Rowan Hall.", memory_used=(item.id,)))
        reply = conversation.send("Where was my Orchid rehearsal on 2026-09-02?")
        self.assertEqual(reply.answer_constraint, "verified_location")
        self.assertEqual(backend.calls[0][2]["properties"]["speech"]["enum"],
                         ["Your Orchid rehearsal was at Rowan Hall."])
        self.assertNotIn("18:30", reply.response.speech)

    def test_location_constraint_rejects_extra_time_instead_of_silently_rewriting(self):
        text = "Your Orchid rehearsal was at Rowan Hall on 2026-09-02 at 18:30."
        item = memory(3, text)
        conversation, _, _, _ = self.conversation((hybrid_match(item),),
                                                chat_result(text, memory_used=(item.id,)))
        with self.assertRaisesRegex(ResponseValidationError, "verified composition"):
            conversation.send("Where was my Orchid rehearsal on 2026-09-02?")

    def test_location_extraction_does_not_drop_unsupported_clauses_or_dates(self):
        valid = AnswerFact("Your Orchid rehearsal was at Rowan Hall on 2026-09-02 at 18:30.")
        for query, fact in (
            ("Where was my Orchid rehearsal on 2026-09-03?", valid),
            ("Where was my Violet rehearsal on 2026-09-02?", valid),
            ("Where was my Orchid rehearsal and what time did it begin?", valid),
            ("Where is my compass?", AnswerFact("Your compass is not in the satchel.")),
            ("Where is my compass?", AnswerFact("Your compass is in the satchel or the cupboard.")),
            ("Where is my compass?", AnswerFact("Your compass is in the satchel until tomorrow.")),
            ("Where is my compass now?", AnswerFact("Your compass was in the satchel on 2025-01-01.")),
            ("Where is my compass?", AnswerFact("Your compass is in the satchel on 2025-01-01.")),
            ("Where is my compass?", AnswerFact("Your compass is in the satchel unless you moved it.")),
            ("Where is my compass?", AnswerFact("Your compass is in the satchel except on Monday.")),
        ):
            with self.subTest(query=query, fact=fact):
                self.assertIsNone(compose_verified_location((fact,), query))

    def test_conflicting_event_metadata_does_not_enter_location_composition(self):
        item = replace(memory(3, "Your Orchid rehearsal was at Rowan Hall on 2026-09-02 at 18:30."),
                       event_time="2026-09-03T18:30:00+00:00")
        self.assertIsNone(_verified_composed_answer(
            (hybrid_match(item),), "Where was my Orchid rehearsal on 2026-09-02?", (item.id,),
        ))

    def test_evaluation_accepts_location_constraint_only_with_one_cited_record(self):
        observation = _find(_raw_records(strategies=("adaptive",)), "case",
                            case_id="memory_direct_fact")["cascade"]
        observation["answer_constraint"] = "verified_location"
        self.assertEqual(_cascade(observation)["answer_constraint"], "verified_location")
        for changes in ({"retrieval_invoked": False}, {"supplied_ids": []},
                        {"supplied_ids": [memory(998).id, memory(999).id]},
                        {"answer_constraint": "unrecognized_location"}):
            with self.subTest(changes=changes):
                invalid = deepcopy(observation)
                invalid.update(changes)
                with self.assertRaises(EvaluationScoringError):
                    _cascade(invalid)


if __name__ == "__main__":
    unittest.main()
