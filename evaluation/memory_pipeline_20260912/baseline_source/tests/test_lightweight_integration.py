"""Offline request-path and residency checks for opt-in lightweight routing.

The real client parses every fake HTTP response. Policy shortcuts never use
fabricated classifier ChatResults, and no Ollama service is contacted.
"""

from collections import deque
from dataclasses import replace
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import URLError

from oline_hri.config import load_config
from oline_hri.conversation import Conversation, ConversationError
from oline_hri.lightweight_routing import LightweightRouter
from oline_hri.memory import MemoryStore
from oline_hri.ollama import OllamaClient
from oline_hri.response import ResponseValidationError
from oline_hri.retrieval import HybridMatch
from oline_hri.routing import RouteDecision, RoutingResult


HARD = "Compare violet and amber decorations in general."
EASY = "What is granite?"
AMBIGUOUS = "Arrange an exhibition."
PERSONAL = "Who is my paper sculpture partner?"


class RecordingTransport:
    """Minimal HTTP server model, including explicit eviction requirements."""

    def __init__(self):
        self.requests = []
        self.resident = set()
        self.memory_answers = deque()
        self.speeches = deque()
        self.omit_citations = False
        self.after_generation = None
        self.fail_next_generation = False
        self.timeout_next_generation = False

    @property
    def chats(self):
        return [r for r in self.requests if r["endpoint"] == "chat"]

    @property
    def generations(self):
        return [r for r in self.chats if "speech" in r["body"]["format"]["properties"]]

    @property
    def classifiers(self):
        return [r for r in self.chats if "speech" not in r["body"]["format"]["properties"]]

    def __call__(self, request, timeout):
        body = json.loads(request.data)
        endpoint = request.full_url.rsplit("/", 1)[-1]
        self.requests.append({"endpoint": endpoint, "body": body, "timeout": timeout})
        model = body["model"]
        if endpoint == "generate":
            if body.get("keep_alive") != 0 or body.get("prompt") != "":
                raise AssertionError("only explicit unload requests are expected here")
            self.resident.discard(model)
            payload = {"model": model, "response": "", "done": True, "done_reason": "unload"}
        elif endpoint == "chat":
            if self.resident - {model}:
                raise AssertionError("client loaded a peer before unloading the resident model")
            self.resident.add(model)
            properties = body["format"]["properties"]
            if "memory_required" in properties:
                content = (self.memory_answers.popleft() if self.memory_answers else
                           {"form": "request", "memory_required": False})
            elif "model_size" in properties:
                raise AssertionError("lightweight compute routing must not call an LLM")
            else:
                if self.timeout_next_generation:
                    self.timeout_next_generation = False
                    # Preserve possible server residency across a timeout;
                    # recovery must evict it before the peer's fallback call.
                    raise TimeoutError("offline simulated generation timeout")
                if self.fail_next_generation:
                    self.fail_next_generation = False
                    # The server may retain the model even after the client
                    # fails. The next client request must recover residency.
                    raise URLError("offline simulated transport failure")
                speech = properties["speech"].get("enum")
                speech = (speech[0] if speech else self.speeches.popleft()
                          if self.speeches else "A concise answer.")
                allowed = properties["memory_used"]["items"].get("enum", [])
                content = {"speech": speech, "gesture_id": "NO_ACTION",
                           "memory_used": [] if self.omit_citations else list(allowed)}
                if self.after_generation is not None:
                    self.after_generation()
            payload = {
                "model": model, "done": True, "done_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(content)},
                "total_duration": 1_000_000, "load_duration": 100_000,
                "prompt_eval_count": 20, "prompt_eval_duration": 300_000,
                "eval_count": 8, "eval_duration": 600_000,
            }
            if body["keep_alive"] == 0:
                self.resident.discard(model)
        else:
            raise AssertionError(f"unexpected endpoint: {endpoint}")
        return io.BytesIO(json.dumps(payload).encode())


class SnapshotRetriever:
    """Controlled candidates with the real store's lifecycle validation."""

    def __init__(self, store=None, items=()):
        self.store = store
        self.matches = tuple(
            HybridMatch(item, 1 / (60 + i), -1.0, i, None, None)
            for i, item in enumerate(items, 1)
        )
        self.retrieve_calls = []
        self.current_calls = []
        self.after_retrieve = None

    def retrieve(self, query, *, limit=3):
        self.retrieve_calls.append((query, limit))
        if self.after_retrieve is not None:
            self.after_retrieve()
        return self.matches[:limit]

    def is_current(self, matches):
        self.current_calls.append(tuple(matches))
        return (self.store.retrieval_snapshot_is_current([m.memory for m in matches])
                if self.store is not None else True)


class StaticRouter:
    def __init__(self, result):
        self.result = result

    def route(self, user_text, *, history=()):
        return self.result


class LightweightIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.small = self.config.ollama.small_model
        self.large = self.config.ollama.large_model

    def pipeline(self, *, retain=True, retriever=None, router=None):
        transport = RecordingTransport()
        client = OllamaClient(self.config.ollama, self.config.generation,
                              opener=transport, retain_large_model=retain)
        router = router or LightweightRouter(client, small_model=self.small, large_model=self.large)
        retriever = retriever if retriever is not None else SnapshotRetriever()
        conversation = Conversation(
            client, system_prompt=self.config.conversation.system_prompt,
            router=router, retriever=retriever, small_model=self.small,
            general_large_model=self.config.ollama.general_large_model,
            large_model=self.large, context_length=2048, max_output_tokens=192,
        )
        return conversation, client, transport, retriever

    def relationship(self):
        directory = tempfile.TemporaryDirectory(prefix="lightweight-integration-")
        self.addCleanup(directory.cleanup)
        ids = iter((f"mem_{n:032x}" for n in (0x301, 0x302)))
        store = MemoryStore(
            Path(directory.name) / "memory.sqlite3", profile_id="fictional_test",
            clock=lambda: datetime(2026, 9, 12, tzinfo=timezone.utc),
            memory_id_factory=lambda: next(ids), retention_days=7,
        )
        item = store.remember("Your paper sculpture partner is Nerin.", kind="relationship")
        return store, item, SnapshotRetriever(store, (item,))

    def assert_shortcut(self, reply, memory_source="policy_general"):
        self.assertEqual(reply.route.policy, "lightweight_v1")
        self.assertEqual(reply.route.memory_decision_source, memory_source)
        self.assertIsNone(reply.route.memory_required_generation)
        self.assertIsNone(reply.route.model_size_generation)

    def test_cold_large_stays_resident_then_two_easy_requests_switch_once(self):
        conversation, client, transport, retriever = self.pipeline()
        replies = [conversation.send(prompt) for prompt in (HARD, HARD, EASY, EASY)]
        self.assertEqual([r.generation.model for r in replies],
                         [self.large, self.large, self.large, self.small])
        for reply in replies:
            self.assert_shortcut(reply)
        self.assertEqual(replies[2].route.model_size_decision_source, "lightweight_resident")
        self.assertEqual(replies[3].route.model_size_decision_source, "lightweight_small")
        self.assertEqual(transport.classifiers, [])
        self.assertEqual(retriever.retrieve_calls, [])
        self.assertTrue(all(r["body"]["keep_alive"] == -1 for r in transport.chats))
        self.assertEqual([(r["endpoint"], r["body"]["model"]) for r in transport.requests], [
            ("generate", self.small), ("chat", self.large), ("chat", self.large),
            ("chat", self.large), ("generate", self.large), ("chat", self.small),
        ])
        self.assertEqual(client.resident_model, self.small)
        self.assertEqual(transport.resident, {self.small})

    def test_intervening_complex_request_resets_the_easy_streak(self):
        conversation, client, transport, _ = self.pipeline()
        replies = [conversation.send(prompt) for prompt in (HARD, EASY, HARD, EASY, EASY)]
        self.assertEqual([r.generation.model for r in replies],
                         [self.large, self.large, self.large, self.large, self.small])
        self.assertEqual(transport.classifiers, [])
        self.assertEqual(client.resident_model, self.small)

    def test_explicit_unload_clears_residency_and_easy_streak_context(self):
        conversation, client, transport, _ = self.pipeline()
        conversation.send(HARD)
        conversation.send(EASY)
        client.unload_all()
        self.assertIsNone(client.resident_model)
        self.assertEqual(transport.resident, set())
        reply = conversation.send(EASY)
        self.assertEqual(reply.generation.model, self.small)
        self.assertEqual(reply.route.model_size_decision_source, "lightweight_small")
        client.unload_all()
        self.assertEqual(transport.resident, set())

    def test_opt_out_preserves_large_expiry(self):
        conversation, client, transport, _ = self.pipeline(retain=False)
        replies = [conversation.send(HARD), conversation.send(HARD)]
        self.assertEqual([r.generation.model for r in replies], [self.large, self.large])
        self.assertTrue(all(r["body"]["keep_alive"] == 0 for r in transport.chats))
        self.assertEqual(transport.resident, set())
        self.assertIsNone(client.resident_model)

    def test_ambiguous_cold_request_classifies_and_generates_on_large(self):
        conversation, client, transport, _ = self.pipeline()
        reply = conversation.send(AMBIGUOUS)
        self.assertEqual([r["body"]["model"] for r in transport.chats], [self.large, self.large])
        self.assertEqual(len(transport.classifiers), 1)
        self.assertEqual(len(transport.generations), 1)
        self.assertIsNone(reply.route.model_size_generation)
        self.assertEqual(reply.route.memory_decision_source, "resident_model")
        self.assertEqual(reply.route.memory_required_generation.model, self.large)
        self.assertEqual(reply.route.memory_required_generation.total_duration_ns, 1_000_000)
        self.assertEqual(reply.route.resident_model, self.large)
        options = transport.classifiers[0]["body"]["options"]
        self.assertEqual((options["temperature"], options["seed"]), (0, 42))
        self.assertEqual(client.resident_model, self.large)

    def test_incomplete_real_classifier_response_fails_without_generation(self):
        conversation, _, transport, _ = self.pipeline()
        transport.memory_answers.append({"memory_required": False})
        with self.assertRaisesRegex(ConversationError, "route classification failed"):
            conversation.send(AMBIGUOUS)
        self.assertEqual(len(transport.classifiers), 1)
        self.assertEqual(transport.generations, [])

    def test_composition_keeps_large_and_round_trips_actual_citations(self):
        store, item, retriever = self.relationship()
        conversation, client, transport, _ = self.pipeline(retriever=retriever)
        conversation.send(HARD)
        before = len(transport.requests)
        reply = conversation.send(PERSONAL)
        self.assert_shortcut(reply, "policy_personal")
        self.assertEqual(reply.generation.model, self.large)
        self.assertEqual(reply.generation_policy, "verified_constraint_resident")
        self.assertEqual(reply.answer_constraint, "verified_user_relationship")
        self.assertEqual(reply.response.speech, item.canonical_text)
        self.assertEqual(reply.response.memory_used, (item.id,))
        self.assertEqual(len(retriever.current_calls), 2)
        self.assertTrue(store.retrieval_snapshot_is_current((item,)))
        self.assertEqual(len(transport.requests) - before, 1)
        self.assertEqual(transport.requests[-1]["endpoint"], "chat")
        body = transport.generations[-1]["body"]
        self.assertEqual(body["format"]["properties"]["speech"]["enum"], [item.canonical_text])
        self.assertEqual(body["format"]["properties"]["memory_used"]["items"]["enum"], ["memory_ref_1"])
        self.assertNotIn(item.id, json.dumps(body))
        self.assertEqual(client.resident_model, self.large)

    def test_composition_does_not_bypass_required_citations(self):
        _, _, retriever = self.relationship()
        conversation, _, transport, _ = self.pipeline(retriever=retriever)
        conversation.send(HARD)
        transport.omit_citations = True
        with self.assertRaises(ResponseValidationError):
            conversation.send(PERSONAL)
        self.assertEqual(transport.generations[-1]["body"]["model"], self.large)

    def test_resident_composition_timeout_reports_small_fallback_and_valid_evidence(self):
        store, item, retriever = self.relationship()
        conversation, client, transport, _ = self.pipeline(retriever=retriever)
        conversation.send(HARD)
        before = len(transport.requests)
        transport.timeout_next_generation = True
        reply = conversation.send(PERSONAL)

        self.assert_shortcut(reply, "policy_personal")
        self.assertEqual(reply.route.decision.model_size, "large")
        self.assertEqual(reply.route.resident_model, self.large)
        self.assertEqual(reply.fallback_from_model, self.large)
        self.assertEqual(reply.generation.model, self.small)
        self.assertEqual(reply.generation_policy, "verified_constraint_small")
        self.assertEqual(reply.answer_constraint, "verified_user_relationship")
        self.assertEqual(reply.response.speech, item.canonical_text)
        self.assertEqual(reply.response.memory_used, (item.id,))
        self.assertEqual(len(retriever.current_calls), 3)
        self.assertTrue(store.retrieval_snapshot_is_current((item,)))

        calls = transport.requests[before:]
        self.assertEqual([(r["endpoint"], r["body"]["model"]) for r in calls], [
            ("chat", self.large), ("generate", self.large), ("chat", self.small),
        ])
        self.assertEqual(calls[0]["body"]["format"], calls[2]["body"]["format"])
        self.assertEqual(calls[0]["body"]["messages"], calls[2]["body"]["messages"])
        self.assertEqual(calls[2]["body"]["format"]["properties"]["memory_used"]["items"]["enum"],
                         ["memory_ref_1"])
        self.assertNotIn(item.id, json.dumps(calls))
        self.assertEqual(client.resident_model, self.small)
        self.assertEqual(transport.resident, {self.small})
        self.assertEqual(transport.classifiers, [])

    def test_real_store_deletion_before_or_after_generation_blocks_delivery(self):
        for phase in ("before", "after"):
            with self.subTest(phase=phase):
                store, item, retriever = self.relationship()
                conversation, _, transport, _ = self.pipeline(retriever=retriever)
                conversation.send(HARD)
                before = len(transport.generations)
                forget = lambda: store.forget(item.id)
                if phase == "before":
                    retriever.after_retrieve = forget
                else:
                    transport.after_generation = forget
                with self.assertRaises(ConversationError):
                    conversation.send(PERSONAL)
                self.assertEqual(len(transport.generations) - before, 0 if phase == "before" else 1)
                self.assertFalse(store.retrieval_snapshot_is_current((item,)))

    def test_unknown_or_unattributed_missing_metadata_rejected_without_http(self):
        base = RoutingResult(RouteDecision(False, "small"), None, None)
        bad_results = [
            base,
            replace(base, policy="unknown"),
            replace(base, policy="lightweight_v1", model_size_decision_source="lightweight_small"),
            replace(base, policy="lightweight_v1", memory_decision_source="policy_general"),
            replace(base, policy="lightweight_v1", decision=RouteDecision(False, "large"),
                    memory_decision_source="policy_general", model_size_decision_source="lightweight_resident"),
        ]
        for result in bad_results:
            with self.subTest(result=result):
                conversation, _, transport, _ = self.pipeline(router=StaticRouter(result))
                with self.assertRaises(ConversationError):
                    conversation.send(EASY)
                self.assertEqual(transport.requests, [])

    def test_clear_removes_prior_fact_from_classifier_and_generation_inputs(self):
        conversation, _, transport, retriever = self.pipeline()
        transport.memory_answers.extend([
            {"form": "statement", "memory_required": False},
            {"form": "question", "memory_required": False},
        ])
        transport.speeches.extend(["You chose the copper ribbon.", "The copper ribbon."])
        conversation.send("I chose the copper ribbon.")
        conversation.send("What did I choose?")
        self.assertEqual(len(transport.classifiers), 2)
        envelope = json.loads(transport.classifiers[-1]["body"]["messages"][-1]["content"].split("\n", 1)[1])
        self.assertIn("I chose the copper ribbon.", [m["content"] for m in envelope["prior_turns"]])
        self.assertEqual(retriever.retrieve_calls, [])
        conversation.clear()
        self.assertEqual(len(conversation.messages), 1)
        before = len(transport.requests)
        reply = conversation.send("What did I choose?")
        self.assert_shortcut(reply, "policy_personal")
        self.assertNotIn("copper ribbon", json.dumps(transport.requests[before:]))
        self.assertNotIn("copper ribbon", reply.response.speech)
        self.assertEqual(reply.response.memory_used, ())
        self.assertEqual(len(retriever.retrieve_calls), 1)

    def test_privacy_shortcut_never_retrieves_or_invents_classifier_metadata(self):
        conversation, _, transport, retriever = self.pipeline()
        reply = conversation.send("What is my account password?")
        self.assert_shortcut(reply, "policy_privacy")
        self.assertEqual(retriever.retrieve_calls, [])
        self.assertEqual(transport.classifiers, [])
        self.assertEqual(reply.response.memory_used, ())
        self.assertIn("do not store or provide", reply.response.speech)

    def test_transport_error_invalidates_hint_then_recovers_without_overlap(self):
        conversation, client, transport, _ = self.pipeline()
        conversation.send(HARD)
        transport.fail_next_generation = True
        with self.assertRaises(ConversationError):
            conversation.send(EASY)
        self.assertIsNone(client.resident_model)
        self.assertEqual(transport.resident, {self.large})
        reply = conversation.send(EASY)
        self.assertEqual(reply.generation.model, self.small)
        self.assertEqual(client.resident_model, self.small)
        self.assertEqual(transport.resident, {self.small})
        self.assertEqual(transport.classifiers, [])


if __name__ == "__main__":
    unittest.main()
