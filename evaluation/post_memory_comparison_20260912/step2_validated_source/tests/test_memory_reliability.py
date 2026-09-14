"""Bounded answer constraints, recall wording, and their negative controls."""

from copy import deepcopy
from dataclasses import replace
import json
import unittest

from oline_hri.conversation import (
    _chronology_metadata_clocks_are_optional, _require_cited_memory_coverage,
    _verified_preference_answer, _memory_grounded_request, ConversationError,
)
from oline_hri.config import load_config
from oline_hri.ollama import OllamaClient, ChatMessage, _robot_memory_pseudonyms
from oline_hri.evaluation_scoring import _cascade, EvaluationScoringError
from oline_hri.memory_evidence import direct_subject_supported, relevance_stem
from oline_hri.response import RobotResponse, ResponseValidationError, build_robot_response_schema
from oline_hri.routing import memory_intent_policy
from test_conversation_routed import (
    FakeBackend, FakeRetriever, FakeRouter, chat_result, hybrid_match, memory,
    routed_conversation, routing_result,
)
from test_evaluation_scoring import _raw_records, _find
from test_ollama import FakeResponse, successful_chat, successful_unload


class MemoryReliabilityTests(unittest.TestCase):
    def test_conflict_clarification_cannot_bypass_missing_or_stale_evidence(self):
        items = (memory(1, "Your Monday project review is in Lab A."),
                 memory(2, "Your Monday project review is in Lab B."))
        ids = tuple(item.id for item in items)
        for cited, snapshots, error in (
            (ids[:1], (True,), ResponseValidationError),
            (ids, (True, False), ConversationError),
        ):
            backend = FakeBackend((chat_result("The review is in Lab A, not Lab B.",
                                               memory_used=cited),))
            convo = routed_conversation(backend, FakeRouter((routing_result(True),)),
                FakeRetriever(tuple(hybrid_match(item) for item in items),
                              snapshot_outcomes=snapshots))
            with self.assertRaises(error):
                convo.send("Where is my Monday project review?")

    def test_conflict_transform_provenance_is_bounded_to_cited_records(self):
        cascade = _find(_raw_records(strategies=("adaptive",)), "case",
                        case_id="memory_direct_fact")["cascade"]
        cascade["response_transform"] = "conflict_clarification"
        with self.assertRaises(EvaluationScoringError):
            _cascade(cascade)
        second = memory(999).id
        cascade["retrieved_ranked"].append({
            **cascade["retrieved_ranked"][0], "id": second, "semantic_position": 2,
        })
        cascade["supplied_ids"].append(second)
        cascade["response"]["memory_used"].append(second)
        self.assertEqual(_cascade(cascade)["response_transform"], "conflict_clarification")
        cascade["response"]["memory_used"].pop()
        with self.assertRaises(EvaluationScoringError):
            _cascade(cascade)

    def test_new_constraints_keep_ids_aliased_at_transport_boundary(self):
        for count, constrained in ((1, True), (2, False), (3, False), (2, True), (3, True)):
            ids = tuple(memory(i).id for i in range(1, count + 1))
            schema = build_robot_response_schema(ids, require_citation=True)
            schema["properties"]["memory_used"]["minItems"] = count
            if constrained:
                schema["properties"]["speech"]["enum"] = ["You prefer mint tea."]
            original = deepcopy(schema)
            payloads = []

            def opener(request, timeout):
                body = json.loads(request.data)
                if request.full_url.endswith("/api/generate"):
                    return FakeResponse(successful_unload(body["model"]))
                payloads.append(body)
                return FakeResponse(successful_chat(content=json.dumps({
                    "speech": "You prefer mint tea.", "gesture_id": "NO_ACTION",
                    "memory_used": [f"memory_ref_{i}" for i in range(1, count + 1)],
                })))

            config = load_config()
            client = OllamaClient(config.ollama, config.generation, opener=opener)
            result = client.chat(config.ollama.small_model,
                                 [ChatMessage(role="user", content=" ".join(ids))],
                                 response_format=schema)
            self.assertEqual(json.loads(result.content)["memory_used"], list(ids))
            self.assertEqual(payloads[0]["format"]["properties"]["memory_used"]["minItems"], count)
            self.assertNotIn(ids[0], json.dumps(payloads))
            self.assertEqual(schema, original)

    def test_schema_variants_still_reject_unrecognized_or_loose_constraints(self):
        base = build_robot_response_schema((memory(1).id,), require_citation=True)
        for enum in ([], ["a", "b"], [1], [""], "a"):
            schema = deepcopy(base)
            schema["properties"]["speech"]["enum"] = enum
            self.assertIsNone(_robot_memory_pseudonyms(schema))
        for minimum in (True, 0, 2, 1.0):
            schema = deepcopy(base)
            schema["properties"]["memory_used"]["minItems"] = minimum
            self.assertIsNone(_robot_memory_pseudonyms(schema))
        base["properties"]["speech"]["description"] = "Unrecognized variant"
        self.assertIsNone(_robot_memory_pseudonyms(base))

    def test_completion_request_normalization_does_not_change_future_tasks(self):
        self.assertEqual(_memory_grounded_request("Remind me what test I finished."),
                         "What test did I complete?")
        for query in ("Remind me to finish my test.", "Why did I finish my test?"):
            self.assertEqual(_memory_grounded_request(query), query)

    def test_finished_and_completed_share_evidence(self):
        for word in ("finish", "finished", "finishing", "completed", "completion"):
            self.assertEqual(relevance_stem(word), "complete")

    def test_recall_is_not_future_reminder_or_generic_instruction(self):
        for query in ("Remind me what test I finished.",
                      "Please remind me which project I completed.",
                      "Could you remind me where my meeting is?"):
            self.assertEqual(memory_intent_policy(query), (True, "policy_personal"))
        for query in ("Remind me to water my fern tomorrow.",
                      "Remind me how to make tea."):
            self.assertNotEqual(memory_intent_policy(query)[0], True)

    def test_explicit_object_recall_does_not_answer_missing_attributes(self):
        for query, source, expected in (
            ("What do you remember about my scooter?", "I own a yellow scooter.", True),
            ("Remind me what you recall about my scooter.", "I own a yellow scooter.", True),
            ("What do you remember about my scooter?", "My bicycle is yellow.", False),
            ("What do you remember about my office scooter?", "I own a scooter.", False),
            ("What color is my scooter?", "I own a scooter.", False),
        ):
            with self.subTest(query=query, source=source):
                self.assertIs(direct_subject_supported(query, source), expected)

    def test_preference_decoding_preserves_full_source_and_is_audited(self):
        item = memory(1, "I prefer replies under two sentences.")
        speech = "You prefer replies under two sentences."
        backend = FakeBackend((chat_result(speech, memory_used=(item.id,)),))
        convo = routed_conversation(backend, FakeRouter((routing_result(True),)),
                                    FakeRetriever((hybrid_match(item),)))
        reply = convo.send("Do I prefer brief or lengthy replies?")
        self.assertEqual(reply.answer_constraint, "verified_preference")
        self.assertIsNone(reply.response_transform)
        self.assertEqual(backend.calls[0][2]["properties"]["speech"]["enum"], [speech])
        self.assertEqual(reply.response.speech, speech)
        self.assertIn(speech, reply.generation.content)

    def test_backend_ignoring_preference_constraint_is_rejected(self):
        item = memory(1, "I prefer replies under two sentences.")
        for speech in ("You prefer brief replies.", "You prefer lengthy replies."):
            backend = FakeBackend((chat_result(speech, memory_used=(item.id,)),))
            convo = routed_conversation(backend, FakeRouter((routing_result(True),)),
                                        FakeRetriever((hybrid_match(item),)))
            with self.assertRaisesRegex(ResponseValidationError, "verified preference"):
                convo.send("Do I prefer brief or lengthy replies?")

    def test_preference_constraint_does_not_infer_identity_or_reasons(self):
        for source, query in (
            ("Nora prefers mint tea.", "Which tea do I prefer?"),
            ("I prefer mint tea.", "Why do I prefer mint tea?"),
            ("I prefer mint tea.", "Explain my tea preference."),
            ('I prefer the phrase "I like robots".', "Which phrase do I prefer?"),
            ("I prefer mint tea. I also like coffee.", "Which tea do I prefer?"),
            ("I prefer mint tea.", "Plan my trip and use my tea preference."),
        ):
            item = memory(1, source)
            with self.subTest(source=source, query=query):
                self.assertIsNone(_verified_preference_answer(
                    (hybrid_match(item),), query, (item.id,)))

    def test_date_only_detail_does_not_require_distinct_day_metadata_clocks(self):
        items = (
            replace(memory(1, "I visited the aquarium."), event_time="2026-08-04T09:00:00Z"),
            replace(memory(2, "I visited the library."), event_time="2026-08-06T10:00:00Z"),
        )
        matches = tuple(hybrid_match(item) for item in items)
        response = RobotResponse(
            speech="You visited the aquarium on August 4, 2026 and the library on August 6, 2026.",
            gesture_id="NO_ACTION", memory_used=tuple(item.id for item in items),
            allowed_memory_ids=tuple(item.id for item in items),
        )
        _require_cited_memory_coverage(response, matches, "List the dates of my aquarium and library visits.")
        with self.assertRaises(ResponseValidationError):
            _require_cited_memory_coverage(response, matches, "List the dates and exact times of my visits.")
        same_day = (matches[0], hybrid_match(replace(items[1], event_time="2026-08-04T10:00:00Z")))
        self.assertFalse(_chronology_metadata_clocks_are_optional(same_day, "List the dates of my visits."))
        explicit_clock = (hybrid_match(replace(items[0], canonical_text="I visited the aquarium at 09:00.")), matches[1])
        with self.assertRaises(ResponseValidationError):
            _require_cited_memory_coverage(response, explicit_clock, "List the dates of my visits.")

    def test_constraint_provenance_requires_single_cited_retrieved_source(self):
        cascade = _find(_raw_records(strategies=("adaptive",)), "case",
                        case_id="memory_direct_fact")["cascade"]
        cascade["answer_constraint"] = "verified_preference"
        self.assertEqual(_cascade(cascade)["answer_constraint"], "verified_preference")
        for changes in ({"answer_constraint": "arbitrary"}, {"retrieval_invoked": False},
                        {"supplied_ids": []}, {"response": None}, {"privacy_gate": True}):
            candidate = deepcopy(cascade)
            candidate.update(changes)
            with self.assertRaises(EvaluationScoringError):
                _cascade(candidate)


if __name__ == "__main__":
    unittest.main()
