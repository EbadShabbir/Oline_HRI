"""Offline fairness and complete-pipeline checks for fixed-generator systems."""

from dataclasses import replace
import io
import json
import unittest

from oline_hri.config import load_config
from oline_hri.conversation import Conversation, ConversationError
from oline_hri.evaluation import load_evaluation_suite
from oline_hri.evaluation_systems import MemoryOnlyRouter, single_model_config
from oline_hri.ollama import ChatMessage, ChatResult, OllamaClient, OllamaTimeoutError
from oline_hri.response import ResponseValidationError
from oline_hri.routing import (
    ConversationRouter, MEMORY_REQUIRED_SCHEMA, MODEL_SIZE_SCHEMA,
    RoutingError,
)
from test_conversation_routed import FakeRetriever, FakeRouter, hybrid_match, routing_result


class Backend:
    def __init__(self, *, memory_required=False, timeout=False, omit_citations=False):
        self.calls = []
        self.memory_required = memory_required
        self.timeout = timeout
        self.omit_citations = omit_citations

    def chat(self, model, messages, **kwargs):
        self.calls.append((model, tuple(messages), kwargs))
        schema = kwargs.get("response_format")
        if schema == MEMORY_REQUIRED_SCHEMA:
            content = json.dumps({"form": "question", "memory_required": self.memory_required})
        elif schema == MODEL_SIZE_SCHEMA:
            content = '{"model_size":"large"}'
        else:
            if self.timeout:
                raise OllamaTimeoutError("test timeout")
            properties = schema["properties"]
            speech = properties["speech"].get("enum", ["Hello."])[0]
            ids = properties["memory_used"]["items"].get("enum", [])
            content = json.dumps({"speech": speech, "gesture_id": "NO_ACTION",
                                  "memory_used": [] if self.omit_citations else ids})
        return ChatResult(model, content, "stop", 20, 2, 8, 5, 10, 3)


class CompleteSystemAdaptersTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.small = self.config.ollama.small_model
        self.large = self.config.ollama.large_model

    def conversation(self, backend, model, *, retriever=None, router=None):
        return Conversation(
            backend, system_prompt=self.config.conversation.system_prompt,
            router=router or MemoryOnlyRouter(backend, model=model,
                                              fixed_model_size="small" if model == self.small else "large"),
            retriever=retriever or FakeRetriever(), small_model=self.small,
            general_large_model=self.config.ollama.general_large_model, large_model=self.large,
            context_length=2048, max_output_tokens=192, fixed_generator_model=model,
        )

    def personal_case(self):
        suite = load_evaluation_suite()
        case = next(case for case in suite.cases if case.id == "memory_large_temporal")
        records = {event.record.id: event.record for event in suite.memory_events if event.record}
        matches = tuple(hybrid_match(records[identifier], index)
                        for index, identifier in enumerate(case.retrieval_gold.required_ids, 1))
        return case, matches

    def test_memory_only_router_uses_identical_production_input_and_one_real_call(self):
        history = (ChatMessage("user", "I chose the blue mug."),
                   ChatMessage("assistant", "Okay."))
        for prompt in ("What is photosynthesis ?", "What about that?", "What did I choose?"):
            with self.subTest(prompt=prompt):
                adaptive_backend, fixed_backend = Backend(), Backend()
                adaptive = ConversationRouter(adaptive_backend, model=self.small).route(prompt, history=history)
                fixed = MemoryOnlyRouter(fixed_backend, model=self.large,
                                         fixed_model_size="large").route(prompt, history=history)
                self.assertEqual(len(adaptive_backend.calls), 2)
                self.assertEqual(len(fixed_backend.calls), 1)
                self.assertEqual(adaptive_backend.calls[0][1:], fixed_backend.calls[0][1:])
                self.assertEqual(fixed_backend.calls[0][0], self.large)
                self.assertEqual(fixed.decision.memory_required, adaptive.decision.memory_required)
                self.assertEqual(fixed.memory_decision_source, adaptive.memory_decision_source)
                self.assertIsNone(fixed.model_size_generation)
                self.assertEqual(fixed.model_size_decision_source, "fixed_generator")
                self.assertEqual(fixed_backend.calls[0][2]["seed"], 42)
                self.assertEqual(fixed_backend.calls[0][2]["temperature"], 0.0)

    def test_classifier_must_return_actual_selected_model_and_complete_schema(self):
        for result in (
            ChatResult(self.small, '{"form":"question","memory_required":false}', "stop", 1, 0, 1, 1, 1),
            ChatResult(self.large, '{"memory_required":false}', "stop", 1, 0, 1, 1, 1),
            ChatResult(self.large, '{"form":"question","memory_required":false}', "length", 1, 0, 1, 1, 1),
        ):
            class InvalidBackend:
                def chat(self, *args, **kwargs):
                    return result
            with self.subTest(result=result), self.assertRaises(RoutingError):
                MemoryOnlyRouter(InvalidBackend(), model=self.large,
                                 fixed_model_size="large").route("Hello")

    def test_true_single_systems_retain_retrieval_composition_and_snapshot_checks(self):
        case, matches = self.personal_case()
        delivered = []
        for model in (self.small, self.large):
            with self.subTest(model=model):
                backend = Backend(memory_required=True)
                retriever = FakeRetriever(matches)
                reply = self.conversation(backend, model, retriever=retriever).send(case.prompt)
                self.assertEqual([call[0] for call in backend.calls], [model, model])
                self.assertEqual(len(retriever.retrieve_calls), 1)
                self.assertEqual(len(retriever.current_calls), 2)
                self.assertEqual(reply.generation.model, model)
                self.assertIsNone(reply.fallback_from_model)
                self.assertEqual(reply.answer_constraint, "verified_timeline")
                self.assertEqual(reply.generation_policy, "fixed_generator_verified_constraint")
                self.assertEqual(set(reply.response.memory_used), set(case.retrieval_gold.required_ids))
                delivered.append(reply.response.speech)
        self.assertEqual(delivered[0], delivered[1])

    def test_fixed_generator_overrides_logical_route_without_peer_timeout_fallback(self):
        for model in (self.small, self.large):
            with self.subTest(model=model):
                backend = Backend()
                opposite = "large" if model == self.small else "small"
                router = FakeRouter(default=routing_result(False, opposite))
                reply = self.conversation(backend, model, router=router).send("Hello")
                self.assertEqual(backend.calls[0][0], model)
                self.assertEqual(reply.generation_policy, "fixed_generator")
                timed_out = Backend(timeout=True)
                with self.assertRaisesRegex(ConversationError, "fixed-generator request timed out"):
                    self.conversation(timed_out, model, router=router).send("Hello")
                self.assertEqual([call[0] for call in timed_out.calls], [model])

    def test_fixed_generator_keeps_stale_evidence_and_citation_validation(self):
        case, matches = self.personal_case()
        for snapshots in ((False,), (True, False)):
            with self.subTest(snapshots=snapshots), self.assertRaises(ConversationError):
                self.conversation(Backend(memory_required=True), self.large,
                                  retriever=FakeRetriever(matches, snapshot_outcomes=snapshots)).send(case.prompt)
        with self.assertRaises(ResponseValidationError):
            self.conversation(Backend(memory_required=True, omit_citations=True), self.large,
                              retriever=FakeRetriever(matches)).send(case.prompt)

    def test_unmarked_missing_compute_result_is_still_rejected(self):
        invalid = replace(routing_result(), model_size_generation=None)
        backend = Backend()
        with self.assertRaisesRegex(ConversationError, "invalid route"):
            self.conversation(backend, self.small, router=FakeRouter(default=invalid)).send("Hello")
        self.assertEqual(backend.calls, [])

    def test_actual_client_keeps_sole_large_resident_and_never_calls_peer(self):
        configured = single_model_config(self.config, self.large)
        self.assertEqual(configured.generation, self.config.generation)
        self.assertEqual({configured.ollama.small_model, configured.ollama.general_large_model,
                          configured.ollama.large_model}, {self.large})
        requests = []
        def opener(request, timeout):
            body = json.loads(request.data)
            requests.append((body, timeout))
            if request.full_url.endswith("/api/generate"):
                payload = {"model": body["model"], "response": "", "done": True, "done_reason": "unload"}
            else:
                fields = body["format"]["properties"]
                content = ('{"form":"question","memory_required":false}' if "memory_required" in fields
                           else '{"speech":"Hello.","gesture_id":"NO_ACTION","memory_used":[]}')
                payload = {"model": body["model"], "done": True, "done_reason": "stop",
                           "message": {"role": "assistant", "content": content}}
            return io.BytesIO(json.dumps(payload).encode())
        client = OllamaClient(configured.ollama, configured.generation, opener=opener)
        # Fresh question state, retained model residency across requests.
        for _ in range(2):
            self.conversation(client, self.large).send("Hello")
        self.assertEqual(len(requests), 4)
        self.assertTrue(all(body["model"] == self.large and body["keep_alive"] == -1
                            for body, _ in requests))
        self.assertTrue(all(timeout == self.config.ollama.large_request_timeout_seconds
                            for _, timeout in requests))
        with self.assertRaises(ValueError):
            client.chat(self.small, [ChatMessage("user", "Forbidden peer")])
        self.assertEqual(len(requests), 4)
        client.unload_all()
        self.assertEqual(len(requests), 5)
        self.assertEqual(requests[-1][0]["model"], self.large)
        self.assertEqual(requests[-1][0]["keep_alive"], 0)


if __name__ == "__main__":
    unittest.main()
