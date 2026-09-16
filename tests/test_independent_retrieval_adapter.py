"""Offline controls for the real independent-retrieval application boundary."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import independent_retrieval_adapter as adapter
from oline_hri.config import load_config
from oline_hri.conversation import ConversationError
from oline_hri.ollama import ChatResult, OllamaTimeoutError
from tests.test_complete_system_runner import FakeEmbedder, seed, memory_id


class Backend:
    def __init__(self, model, *, selected=True, failure=None, callback=None):
        self.resident_model = model
        self.selected, self.failure, self.callback = selected, failure, callback
        self.calls = []

    def chat(self, model, messages, **kwargs):
        self.calls.append((model, messages, kwargs))
        props = kwargs["response_format"]["properties"]
        if "memory_required" in props:
            content = json.dumps({"form": "request", "memory_required": self.selected})
        else:
            if self.failure:
                raise self.failure
            if self.callback:
                self.callback()
                self.callback = None
            identifiers = props["memory_used"]["items"].get("enum", [])
            speech = props["speech"].get("enum", [
                "Your favorite fruit is mango." if identifiers
                else "A thermometer measures temperature."])[0]
            content = json.dumps({"speech": speech, "gesture_id": "NO_ACTION", "memory_used": identifiers})
        return ChatResult(model, content, "stop", 1, 0, 1, 1, 1)


class IndependentRetrievalAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "snapshot.sqlite3"
        self.seed = seed()
        self.seed["retention_days"] = 30
        self.seed["other_profile_seeds"] = [{"profile_id": "other-fictional-profile", "events": [{
            "id": "other-profile", "at": "2026-09-09T12:00:00Z", "operation": "remember",
            "memory_id": memory_id(99), "canonical_text": "The user's bicycle brand is Marrow.", "kind": "fact"}]}]
        self.embedder = FakeEmbedder()
        self.store, self.setup = adapter.materialize_snapshot(self.path, self.seed, self.embedder)
        base = load_config()
        self.config = replace(base, generation=replace(base.generation,
            context_length=2048, max_output_tokens=192, temperature=0.0, thinking=False))

    def make(self, policy, model=adapter.SMALL, *, consent=True, profile=None, **kwargs):
        backend = Backend(model, **kwargs)
        run = adapter.IndependentRetrievalAdapter(backend, self.store, model=model,
            policy=policy, consent_authorized=consent, profile_id=profile or self.seed["profile_id"])
        return run, backend

    def test_all_six_conditions_keep_generator_and_trace_evidence(self):
        for model in (adapter.SMALL, adapter.LARGE):
            for policy in adapter.POLICIES:
                with self.subTest(model=model, policy=policy):
                    run, backend = self.make(policy, model)
                    reply = run.send("What is my favorite fruit?", self.config)
                    trace = run.to_dict(reply)
                    self.assertEqual({call[0] for call in backend.calls}, {model})
                    self.assertEqual(reply.generation.model, model)
                    self.assertEqual(trace["retrieval_attempts"], int(policy != "off"))
                    self.assertEqual(trace["selection"]["classifier_calls"], 0)
                    self.assertEqual(bool(trace["supplied_ids"]), policy != "off")
                    if policy == "off":
                        self.assertEqual(trace["inspected_ids"], [])
                        self.assertIn("do not have a verified", reply.response.speech)
                        self.assertNotIn("mango", json.dumps(trace["calls"]).lower())
                        self.assertNotIn("mem_", json.dumps(trace["calls"]))
                    else:
                        self.assertEqual(trace["supplied_ids"], [memory_id(7)])
                        self.assertEqual(trace["supplied_evidence"][0]["memory"]["canonical_text"],
                                         "The user's favorite fruit is mango.")
                        self.assertEqual(len(trace["freshness_calls"]), 2)
                        self.assertTrue(all(call["current"] for call in trace["freshness_calls"]))
                        self.assertEqual(reply.response.speech, "Your favorite fruit is mango.")

    def test_general_and_unknown_without_linked_evidence_have_identical_generation_inputs(self):
        for prompt in ("What does a thermometer measure?", "What is my bicycle brand?"):
            generation_inputs = []
            for policy in adapter.POLICIES:
                run, backend = self.make(policy)
                reply = run.send(prompt, self.config)
                trace = run.to_dict(reply)
                generation_inputs.append((backend.calls[-1][1], backend.calls[-1][2]))
                self.assertEqual(trace["supplied_ids"], [])
                if policy == "always":
                    self.assertEqual(trace["retrieval_attempts"], 1)
                    self.assertTrue(trace["retrieved_ids"])
                if "thermometer" in prompt:
                    self.assertFalse(trace["framing"]["memory_requested"])
                    self.assertEqual(reply.response.speech, "A thermometer measures temperature.")
            self.assertEqual(generation_inputs[0], generation_inputs[1])
            self.assertEqual(generation_inputs[0], generation_inputs[2])

    def test_logical_role_normalization_makes_cross_model_inputs_identical(self):
        for policy in adapter.POLICIES:
            for prompt in ("What does a thermometer measure?", "What is my favorite fruit?",
                           "Explain how rainbows form."):
                inputs = []
                for model in (adapter.SMALL, adapter.LARGE):
                    run, backend = self.make(policy, model)
                    run.send(prompt, self.config)
                    inputs.append([(messages, kwargs) for _, messages, kwargs in backend.calls])
                self.assertEqual(inputs[0], inputs[1])

    def test_ambiguous_selector_uses_sole_model_and_does_not_supply_response_intent(self):
        for model in (adapter.SMALL, adapter.LARGE):
            baseline, _ = self.make("off", model)
            baseline.send("Explain how rainbows form.", self.config)
            for selected in (True, False):
                run, backend = self.make("selective", model, selected=selected)
                reply = run.send("Explain how rainbows form.", self.config)
                trace = run.to_dict(reply)
                self.assertEqual(trace["selection"]["classifier_calls"], 1)
                self.assertEqual(len(backend.calls), 2)
                self.assertEqual({call[0] for call in backend.calls}, {model})
                self.assertIsNone(trace["framing"]["deterministic_intent"])
                self.assertFalse(trace["framing"]["memory_requested"])
                self.assertEqual(trace["retrieval_attempts"], int(selected))
                self.assertEqual(run.calls[-1]["messages"], baseline.calls[-1]["messages"])
                self.assertEqual(run.calls[-1]["options"], baseline.calls[-1]["options"])

    def test_authorization_denial_precedes_any_classifier_or_store_access(self):
        for policy in adapter.POLICIES:
            for kwargs, prompt in (({"consent": False}, "Explain how rainbows form."),
                                   ({"profile": "unrelated"}, "What is my favorite fruit?"),
                                   ({}, "What is my account password?")):
                with self.subTest(policy=policy, kwargs=kwargs):
                    run, backend = self.make(policy, **kwargs)
                    run.send(prompt, self.config)
                    trace = run.to_dict()
                    self.assertFalse(trace["authorization"]["authorized"])
                    self.assertEqual(trace["retrieval_attempts"], 0)
                    self.assertEqual(trace["selection"]["classifier_calls"], 0)
                    self.assertEqual(trace["inspected_ids"], [])
                    self.assertEqual(trace["supplied_ids"], [])
                    self.assertEqual(len(backend.calls), 1)

    def test_inspection_observes_all_eligible_records_and_lifecycle_filters(self):
        before = adapter.snapshot_digest(self.path)
        run, _ = self.make("always")
        reply = run.send("What does a thermometer measure?", self.config)
        trace = run.to_dict(reply)
        self.assertEqual(trace["inspected_ids"], [memory_id(2), memory_id(7)])
        semantic = [event for event in trace["inspection_events"] if event["stage"] == "semantic_eligible_snapshot"]
        self.assertEqual(len(semantic), 2)
        self.assertTrue(all(event["ids"] == [memory_id(2), memory_id(7)] for event in semantic))
        for excluded in (1, 3, 4, 5, 6, 99):
            self.assertNotIn(memory_id(excluded), trace["inspected_ids"])
        self.assertEqual([call["source"] for call in trace["search_calls"]], ["semantic", "keyword"])
        self.assertEqual(before, adapter.snapshot_digest(self.path))
        self.assertEqual(self.setup["logical_sha256"], before)
        self.assertEqual(self.setup["profiles"][0]["purged_retention_ids"], [memory_id(6)])
        with self.assertRaises(ValueError):
            adapter.materialize_snapshot(self.path, self.seed, self.embedder)

    def test_freshness_blocks_change_after_generation(self):
        run, _ = self.make("always", callback=lambda: self.store.forget(memory_id(7)))
        with self.assertRaisesRegex(ConversationError, "no longer current"):
            run.send("What is my favorite fruit?", self.config)
        trace = run.to_dict()
        self.assertEqual([call["current"] for call in trace["freshness_calls"]], [True, False])
        self.assertEqual(trace["supplied_ids"], [memory_id(7)])

    def test_timeout_has_no_cross_model_fallback_and_preserves_supplied_evidence(self):
        run, backend = self.make("always", adapter.LARGE, failure=OllamaTimeoutError("offline timeout"))
        with self.assertRaisesRegex(ConversationError, "fixed-generator request timed out"):
            run.send("What is my favorite fruit?", self.config)
        trace = run.to_dict()
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(backend.calls[0][0], adapter.LARGE)
        self.assertEqual(trace["supplied_ids"], [memory_id(7)])
        self.assertEqual(trace["calls"][0]["status"], "error")
        with self.assertRaisesRegex(RuntimeError, "fresh adapter"):
            run.send("What is my favorite fruit?", self.config)


if __name__ == "__main__":
    unittest.main()
