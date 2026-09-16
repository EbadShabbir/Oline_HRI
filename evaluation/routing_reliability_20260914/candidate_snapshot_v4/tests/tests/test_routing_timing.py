"""Offline timing-accounting tests; fake HTTP durations are not measurements."""

from copy import deepcopy
from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from oline_hri.config import load_config
from oline_hri.conversation import Conversation
from oline_hri.evaluation_systems import OptimizedMemoryOnlyRouter
from oline_hri.lightweight_routing import LightweightRouter
from oline_hri.ollama import ChatMessage, OllamaClient
from oline_hri.response import ResponseValidationError
from oline_hri.routing import ConversationRouter
from oline_hri.timing import TraceRecorder, generation_call, trace_span


SMALL, LARGE = "qwen3:0.6b", "qwen3:1.7b"


class Response:
    def __init__(self, value):
        self.data = json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, size):
        return self.data[:size]


class FakeServer:
    def __init__(self):
        self.requests = []
        self.resident = None
        self.bad_answer = False

    def __call__(self, request, timeout):
        body = json.loads(request.data)
        self.requests.append(body)
        model = body["model"]
        if request.full_url.endswith("/api/generate"):
            if self.resident == model:
                self.resident = None
            return Response(dict(model=model, response="", done=True, done_reason="unload"))
        self.resident = model
        properties = body.get("format", {}).get("properties", {})
        if "memory_required" in properties:
            content = '{"form":"question","memory_required":false}'
        elif "model_size" in properties:
            content = '{"model_size":"small"}'
        elif self.bad_answer:
            content = "invalid JSON"
        else:
            content = '{"speech":"Hello.","gesture_id":"NO_ACTION","memory_used":[]}'
        return Response(dict(model=model, message=dict(role="assistant", content=content),
                             done=True, done_reason="stop", total_duration=90,
                             load_duration=20, prompt_eval_duration=30, eval_duration=40,
                             prompt_eval_count=5, eval_count=6))


class Retriever:
    def retrieve(self, query, *, limit):
        return ()

    def is_current(self, matches):
        return True


class TimingTests(unittest.TestCase):
    def client(self, server):
        config = load_config()
        config = replace(config, ollama=replace(config.ollama, small_model=SMALL,
                         general_large_model=LARGE, large_model=LARGE))
        return OllamaClient(config.ollama, config.generation, opener=server,
                            retain_large_model=True)

    def test_monotonic_nesting_and_durable_interrupted_start(self):
        stream = []
        recorder = TraceRecorder(sink=stream.append)
        with patch("oline_hri.timing.time.monotonic_ns", side_effect=[10, 20, 30, 40]):
            with self.assertRaises(KeyboardInterrupt):
                with recorder.activate(), trace_span("outer"):
                    with trace_span("inner"):
                        raise KeyboardInterrupt("synthetic stop")
        outer, inner = recorder.events
        self.assertEqual((outer["wall_ns"], inner["wall_ns"]), (30, 10))
        self.assertEqual(inner["parent_id"], outer["id"])
        self.assertEqual([item["event"] for item in stream],
                         ["span_start", "span_start", "span_end", "span_end"])
        self.assertEqual(stream[0]["status"], "running")
        self.assertIsNone(stream[0]["end_ns"])
        self.assertEqual(outer["status"], "interrupted")
        self.assertEqual(inner["status"], "interrupted")
        with trace_span("disabled"):
            pass
        self.assertEqual(len(recorder.events), 2)

    def test_actual_client_transition_eviction_and_backend_overlap(self):
        server = FakeServer()
        client = self.client(server)
        verified = []
        def verify(model):
            self.assertNotEqual(server.resident, model)
            verified.append(model)
            return {"models": []}
        recorder = TraceRecorder(eviction_verifier=verify)
        with recorder.activate():
            generation_call(client, SMALL, [ChatMessage("user", "Hi")], seed=42)
            generation_call(client, LARGE, [ChatMessage("user", "Hi")], seed=42)
            generation_call(client, SMALL, [ChatMessage("user", "Hi")], seed=42)
        self.assertEqual(server.resident, SMALL)
        self.assertEqual(verified, [LARGE, SMALL, LARGE])
        backend = [s for s in recorder.events if s["name"] == "backend_chat"]
        self.assertEqual(len(backend), 3)
        self.assertEqual(backend[0]["attributes"]["backend_load_duration_ns"], 20)
        self.assertEqual(backend[0]["attributes"]["backend_total_duration_ns"], 90)
        self.assertFalse(any(s["name"] == "backend_load" for s in recorder.events))
        for span in recorder.events:
            self.assertEqual(span["wall_ns"], span["end_ns"] - span["start_ns"])
            if span["parent_id"] is not None:
                parent = recorder.events[span["parent_id"] - 1]
                self.assertLessEqual(parent["start_ns"], span["start_ns"])
                self.assertGreaterEqual(parent["end_ns"], span["end_ns"])
        request = deepcopy(next(s for s in recorder.events if s["name"] == "answer_generation")["attributes"]["request"])
        replay_server = FakeServer()
        replay_client = self.client(replay_server)
        replay_client.chat(request.pop("model"),
                           [ChatMessage(**m) for m in request.pop("messages")], **request)
        self.assertEqual(replay_server.requests[-1], server.requests[1])

    def test_failed_eviction_aborts_generation_and_residency_is_unknown(self):
        server = FakeServer()
        client = self.client(server)
        def reject(model):
            raise RuntimeError("eviction was not verified")
        recorder = TraceRecorder(eviction_verifier=reject)
        with self.assertRaisesRegex(RuntimeError, "eviction"):
            with recorder.activate():
                client.chat(SMALL, [ChatMessage("user", "Hi")])
        self.assertEqual(len(server.requests), 1)
        self.assertIsNone(client.resident_model)
        self.assertEqual(next(s for s in recorder.events if s["name"] == "eviction_verification")["status"], "error")

    def test_complete_turn_contains_classification_generation_validation(self):
        server = FakeServer()
        client = self.client(server)
        router = LightweightRouter(client, small_model=SMALL, large_model=LARGE)
        conversation = Conversation(client, system_prompt="Speak briefly.", router=router,
                                    retriever=Retriever(), small_model=SMALL,
                                    general_large_model=LARGE, large_model=LARGE)
        recorder = TraceRecorder()
        with recorder.activate():
            conversation.send("Hello")
            conversation.send("What is my favorite tea?")
        names = [s["name"] for s in recorder.events]
        self.assertEqual(names.count("complete_request"), 2)
        self.assertEqual(names.count("memory_classifier"), 1)
        self.assertEqual(names.count("compute_classifier"), 0)
        self.assertEqual(names.count("answer_generation"), 2)
        self.assertEqual(names.count("retrieval"), 1)
        self.assertEqual(names.count("validation"), 2)
        self.assertEqual(names.count("deterministic_routing"), 4)
        server.bad_answer = True
        with self.assertRaises(ResponseValidationError):
            with recorder.activate():
                conversation.send("What is gravity?")
        self.assertEqual([s["status"] for s in recorder.events if s["name"] == "complete_request"][-1], "error")
        self.assertEqual([s["status"] for s in recorder.events if s["name"] == "validation"][-1], "error")

    def test_fixed_and_llm_classifier_calls_are_named(self):
        server = FakeServer()
        client = self.client(server)
        recorder = TraceRecorder()
        fixed = OptimizedMemoryOnlyRouter(client, model=SMALL, fixed_model_size="small")
        legacy = ConversationRouter(client, model=SMALL)
        with recorder.activate():
            fixed.route("Hello")
            legacy.route("Hello")
        names = [s["name"] for s in recorder.events]
        self.assertEqual(names.count("memory_classifier"), 2)
        self.assertEqual(names.count("compute_classifier"), 1)
        self.assertEqual(names.count("backend_chat"), 3)


if __name__ == "__main__":
    unittest.main()
