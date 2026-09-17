"""Offline checks for benchmark scoring, fairness, and abort semantics."""

from dataclasses import replace
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import run_arc_capability as arc

from oline_hri.config import load_config
from oline_hri.ollama import ChatResult, OllamaClient, OllamaError, OllamaTimeoutError
from oline_hri.routing import MEMORY_REQUIRED_SCHEMA, MODEL_SIZE_SCHEMA


CASE = {
    "id": "test-item", "subset": "ARC-Challenge",
    "question": "Which object floats?", "choices": [
        {"label": "A", "text": "A stone"}, {"label": "B", "text": "A cork"}],
    "answerKey": "B",
}


class FakeClient:
    def __init__(self, *, size="large", answer='{"answer":"B"}', failure=None):
        self.requests = []
        self.size, self.answer, self.failure = size, answer, failure

    def chat(self, model, messages, **kwargs):
        self.requests.append((model, messages, kwargs))
        if self.failure is not None:
            error, self.failure = self.failure, None
            raise error
        schema = kwargs.get("response_format")
        if schema == MEMORY_REQUIRED_SCHEMA:
            content = '{"form":"request","memory_required":true}'
        elif schema == MODEL_SIZE_SCHEMA:
            content = json.dumps({"model_size": self.size})
        else:
            content = self.answer
        return ChatResult(model, content, "stop", 20, 2, 8, 5, 10, 3)


class Writer:
    def __init__(self):
        self.records = []

    def write(self, record):
        self.records.append(record)


class ArcCapabilityTests(unittest.TestCase):
    def config(self, arm):
        return arc.arm_config(load_config(), arm, "qwen2.5:3b-instruct-q3_K_S")

    def backend(self, client, arm):
        config = self.config(arm)
        sampler = SimpleNamespace(monitor=SimpleNamespace(violation=None))
        backend = arc.BenchmarkBackend(
            client, {}, sampler, (config.ollama.small_model, config.ollama.large_model))
        def check():
            if sampler.monitor.violation:
                raise arc.SafetyGateError(sampler.monitor.violation)
        backend.check = check
        return backend

    def run_cases(self, cases, arm, client):
        backend, writer, records = self.backend(client, arm), Writer(), []
        with patch("sys.stdout", new=io.StringIO()):
            arc.run_cases(cases, arm, self.config(arm), backend, writer, records)
        self.assertEqual(writer.records, records)
        return records, backend

    def test_strict_answer_scoring_rejects_common_invalid_outputs(self):
        self.assertEqual(arc.parse_answer(' {"answer": "B"} ', ["A", "B"]), "B")
        for invalid in ('B', '```json\n{"answer":"B"}\n```',
                        '{"answer":"b"}', '{"answer":" B "}',
                        '{"answer":"C"}', '{"answer":2}', '{"answer":true}',
                        '{"answer":"A","answer":"B"}',
                        '{"answer":"B","explanation":"cork"}',
                        '{"answer":NaN}', '["B"]'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                arc.parse_answer(invalid, ["A", "B"])

    def test_native_numeric_labels_are_preserved(self):
        self.assertEqual(arc.parse_answer('{"answer":"2"}', ["1", "2"]), "2")
        with self.assertRaises(ValueError):
            arc.parse_answer('{"answer":2}', ["1", "2"])

    def test_gold_and_case_metadata_never_change_model_input(self):
        changed = {**CASE, "answerKey": "A", "id": "secret-id", "subset": "secret-subset"}
        self.assertEqual(arc.generation_messages(CASE), arc.generation_messages(changed))
        self.assertEqual(arc.answer_schema(CASE), arc.answer_schema(changed))
        self.assertEqual(arc.question_text(CASE), arc.question_text(changed))
        client = FakeClient()
        self.run_cases([changed], "cascade", client)
        messages = json.dumps([[m.to_dict() for m in call[1]] for call in client.requests])
        for forbidden in ("secret-id", "secret-subset", "answerKey"):
            self.assertNotIn(forbidden, messages)
        self.assertTrue(all("A stone" in call[1][-1].content
                            and "B. A cork" in call[1][-1].content
                            for call in client.requests))

    def test_all_single_arms_call_only_the_selected_model(self):
        for arm, expected in (("small", arc.SMALL_MODEL), ("large", arc.LARGE_MODEL),
                              ("extra", "qwen2.5:3b-instruct-q3_K_S")):
            with self.subTest(arm=arm):
                config = self.config(arm)
                self.assertEqual({config.ollama.small_model, config.ollama.large_model,
                                  config.ollama.general_large_model}, {expected})
                self.assertEqual(config.generation.context_length, 2048)
                self.assertEqual(config.generation.max_output_tokens, 192)
                self.assertFalse(config.generation.thinking)
                client = FakeClient()
                records, backend = self.run_cases([CASE], arm, client)
                self.assertEqual([call[0] for call in client.requests], [expected])
                self.assertTrue(records[0]["correct"])
                self.assertEqual(records[0]["selected_model"], expected)
                self.assertEqual(backend.calls[0]["purpose"], "generation")
                self.assertEqual(backend.calls[0]["actual_model"], expected)
                self.assertEqual(client.requests[0][2]["seed"], 42)

    def test_production_router_runs_both_classifiers_then_selected_generator(self):
        for size, selected in (("small", arc.SMALL_MODEL), ("large", arc.LARGE_MODEL)):
            with self.subTest(size=size):
                client = FakeClient(size=size)
                records, backend = self.run_cases([CASE], "cascade", client)
                self.assertEqual([call[0] for call in client.requests],
                                 [arc.SMALL_MODEL, arc.SMALL_MODEL, selected])
                self.assertEqual([call["purpose"] for call in backend.calls],
                                 ["classifier", "classifier", "generation"])
                self.assertTrue(records[0]["route"]["decision"]["memory_required"])
                self.assertEqual(records[0]["selected_model"], selected)
                self.assertTrue(records[0]["correct"])

    def test_invalid_answers_and_request_failures_remain_in_denominator(self):
        cases = [CASE, {**CASE, "id": "second"}]
        records, _ = self.run_cases(cases, "large", FakeClient(failure=RuntimeError("failed")))
        summary = arc.summarize(cases, records, "complete_with_errors")
        self.assertEqual(summary["attempted"], 2)
        self.assertEqual(summary["correct"], 1)
        self.assertEqual(summary["accuracy"], .5)
        self.assertEqual(summary["errors"], 1)
        invalid, _ = self.run_cases([CASE], "small", FakeClient(answer="B"))
        self.assertEqual(arc.summarize([CASE], invalid, "complete_with_errors")["accuracy"], 0)
        self.assertIn("generation", invalid[0])
        self.assertEqual(invalid[0]["generation"]["content"], "B")

    def test_safety_failure_cannot_be_swallowed_by_router(self):
        backend = self.backend(FakeClient(failure=arc.SafetyGateError("swap ceiling")), "cascade")
        writer, records = Writer(), []
        with patch("sys.stdout", new=io.StringIO()), self.assertRaises(arc.SafetyGateError):
            arc.run_cases([CASE, {**CASE, "id": "never-run"}], "cascade", self.config("cascade"),
                          backend, writer, records)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "interrupted")
        self.assertEqual(records[0]["calls"][0]["error"], "SafetyGateError")
        summary = arc.summarize([CASE, CASE], records, "interrupted")
        self.assertEqual(summary["unattempted"], 1)
        self.assertEqual(summary["accuracy"], 0)

    def test_real_client_keeps_single_large_model_resident_without_peer_calls(self):
        requests = []
        def opener(request, timeout):
            body = json.loads(request.data)
            requests.append(body)
            if request.full_url.endswith("/api/generate"):
                payload = {"model": body["model"], "response": "", "done": True,
                           "done_reason": "unload"}
            else:
                payload = {"model": body["model"], "message": {
                    "role": "assistant", "content": '{"answer":"B"}'},
                    "done": True, "done_reason": "stop"}
            return io.BytesIO(json.dumps(payload).encode())
        config = self.config("large")
        client = OllamaClient(config.ollama, config.generation, opener=opener)
        for _ in range(2):
            client.chat(arc.LARGE_MODEL, arc.generation_messages(CASE),
                        response_format=arc.answer_schema(CASE), temperature=0.0, seed=42)
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(body["model"] == arc.LARGE_MODEL and body["keep_alive"] == -1
                            for body in requests))
        self.assertEqual(requests[0]["options"], {
            "num_ctx": 2048, "num_predict": 192, "temperature": 0.0, "seed": 42})
        self.assertFalse(requests[0]["think"])
        client.unload_all()
        self.assertEqual(len(requests), 3)
        self.assertEqual(requests[-1]["model"], arc.LARGE_MODEL)
        self.assertEqual(requests[-1]["keep_alive"], 0)

    def test_transport_failure_is_saved_and_aborts_direct_and_routed_arms(self):
        for arm in ("large", "cascade"):
            for error_type in (OllamaError, OllamaTimeoutError):
                with self.subTest(arm=arm, error_type=error_type):
                    client = FakeClient(failure=error_type("transport failed"))
                    backend, writer, records = self.backend(client, arm), Writer(), []
                    with patch("sys.stdout", new=io.StringIO()), self.assertRaises(error_type):
                        arc.run_cases([CASE, {**CASE, "id": "never-run"}], arm,
                                      self.config(arm), backend, writer, records)
                    self.assertEqual(len(client.requests), 1)
                    self.assertEqual(writer.records, records)
                    self.assertEqual(len(records), 1)
                    self.assertEqual(records[0]["status"], "error")
                    self.assertEqual(records[0]["error"], error_type.__name__)
                    self.assertFalse(records[0]["correct"])

    def test_dataset_validation_and_digest(self):
        from hashlib import sha256
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.json"
            raw = json.dumps({"metadata": {"split": "test"}, "cases": [CASE]}).encode()
            path.write_bytes(raw)
            dataset, digest = arc.load_dataset(path)
            self.assertEqual(dataset["cases"], [CASE])
            self.assertEqual(digest, sha256(raw).hexdigest())
            path.write_text(json.dumps({"metadata": {}, "cases": [CASE, CASE]}))
            with self.assertRaisesRegex(ValueError, "duplicate case"):
                arc.load_dataset(path)


if __name__ == "__main__":
    unittest.main()
