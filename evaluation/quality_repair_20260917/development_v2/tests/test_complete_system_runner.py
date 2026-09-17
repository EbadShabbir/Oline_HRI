"""Offline checks at the actual Stage 2 lifecycle and model-call boundaries."""

from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from urllib.error import URLError

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_complete_system as runner
from oline_hri.config import load_config
from oline_hri.embedding import EMBEDDING_DIMENSION, MODEL_ID, MODEL_REVISION
from oline_hri.memory import MemoryStore
from oline_hri.ollama import ChatMessage, ChatResult, OllamaError, OllamaTimeoutError
from oline_hri.response import build_robot_response_schema


def memory_id(number):
    return f"mem_{number:032x}"


def seed():
    def remember(number, text, **extra):
        return {"id": f"event-{number}", "operation": "remember",
                "at": "2026-09-09T12:00:00Z", "memory_id": memory_id(number),
                "canonical_text": text, "kind": "fact", **extra}
    return {
        "profile_id": "stage2-offline-test", "evaluation_at": "2026-09-11T12:00:00Z",
        "events": [
            remember(1, "The user's chosen instrument is the violin."),
            {"id": "correct-1", "operation": "correct", "at": "2026-09-10T12:00:00Z",
             "target_id": memory_id(1), "memory_id": memory_id(2),
             "canonical_text": "The user's chosen instrument is the piano."},
            remember(3, "The user keeps a cedar notebook."),
            {"id": "correct-3", "operation": "correct", "at": "2026-09-10T12:00:00Z",
             "target_id": memory_id(3), "memory_id": memory_id(4),
             "canonical_text": "The user keeps a birch notebook."},
            {"id": "forget-chain", "operation": "forget", "at": "2026-09-10T13:00:00Z",
             "target_id": memory_id(4)},
            remember(5, "The user's temporary locker is number forty.",
                     valid_until="2026-09-10T12:00:00Z"),
            remember(6, "The user's temporary appointment is at noon.",
                     retention_until="2026-09-10T12:00:00Z"),
            remember(7, "The user's favorite fruit is mango."),
        ],
    }


class FakeEmbedder:
    model_id, model_revision, dimension = MODEL_ID, MODEL_REVISION, EMBEDDING_DIMENSION

    @staticmethod
    def vector():
        value = np.zeros(EMBEDDING_DIMENSION, dtype=np.float32)
        value[0] = 1.0
        return value

    def embed_passages(self, passages):
        return np.stack([self.vector() for _ in passages])

    def embed_query(self, query):
        return self.vector()


class FakeClient:
    def __init__(self, failure=None, invalid_first_generation=False):
        self.failure = failure
        self.invalid_first_generation = invalid_first_generation
        self.calls = []

    def chat(self, model, messages, **kwargs):
        self.calls.append((model, [message.to_dict() for message in messages], kwargs))
        if self.failure is not None:
            raise self.failure
        fields = kwargs["response_format"]["properties"]
        if "memory_required" in fields:
            content = '{"form":"question","memory_required":false}'
        elif "model_size" in fields:
            content = '{"model_size":"small"}'
        elif self.invalid_first_generation:
            self.invalid_first_generation = False
            content = "invalid JSON response"
        else:
            content = '{"speech":"Hello.","gesture_id":"NO_ACTION","memory_used":[]}'
        return ChatResult(model, content, "stop", 20, 2, 8, 5, 10, 3)


class OfflineBackend(runner.SystemBackend):
    """Use the real logging/error wrapper; replace only hardware inspection."""

    def __init__(self, client):
        sampler = SimpleNamespace(monitor=SimpleNamespace(violation=None))
        super().__init__(client, {}, sampler, (runner.SMALL, runner.LARGE))

    def check(self):
        if self.sampler.monitor.violation:
            raise runner.SafetyGateError(self.sampler.monitor.violation)
        return {}


def cases():
    return [
        {"id": "CASE_METADATA_SENTINEL_A", "stratum": "STRATUM_SENTINEL",
         "scenario_id": "SCENARIO_SENTINEL", "prompt": "Hello"},
        {"id": "CASE_METADATA_SENTINEL_B", "stratum": "STRATUM_SENTINEL",
         "scenario_id": "SCENARIO_SENTINEL", "prompt": "Hello"},
    ]


class CompleteSystemRunnerTests(unittest.TestCase):
    def test_seed_correction_forget_and_expiry_replay_through_real_indexes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "memory.sqlite3"
            store, events = runner.materialize_seed(seed(), path, FakeEmbedder())
            self.assertEqual(store.database_path, path)
            self.assertEqual(store.retention_days, 7)
            records = {item.id: item for item in store.list_memories(include_inactive=True)}
            self.assertEqual(records[memory_id(1)].status, "superseded")
            self.assertEqual(records[memory_id(2)].supersedes_id, memory_id(1))
            self.assertEqual(datetime.fromisoformat(records[memory_id(2)].created_at.replace("Z", "+00:00")),
                             datetime.fromisoformat("2026-09-10T12:00:00+00:00"))
            self.assertNotIn(memory_id(3), records)
            self.assertNotIn(memory_id(4), records)
            forgotten = next(event["result"] for event in events if event["event_id"] == "forget-chain")
            self.assertEqual(set(forgotten), {memory_id(3), memory_id(4)})
            self.assertFalse(store.search_keywords("violin"))
            self.assertEqual([match.memory.id for match in store.search_keywords("piano")], [memory_id(2)])
            self.assertFalse(store.search_keywords("locker"))
            self.assertFalse(store.search_keywords("appointment"))
            self.assertEqual({match.memory.id for match in store.search_semantic("current facts")},
                             {memory_id(2), memory_id(7)})
            self.assertTrue(store.embedding_index_status().complete)
            # A separate database connection sees the same lifecycle outcome.
            restored = MemoryStore(path, profile_id=store.profile_id,
                                   clock=lambda: datetime.fromisoformat("2026-09-11T12:00:00+00:00"),
                                   embedder=FakeEmbedder(), retention_days=7)
            self.assertEqual({match.memory.id for match in restored.search_semantic("current facts")},
                             {memory_id(2), memory_id(7)})

    def test_seed_refuses_existing_database_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "memory.sqlite3"
            path.write_bytes(b"existing user content")
            with self.assertRaisesRegex(ValueError, "overwrite"):
                runner.materialize_seed(seed(), path, FakeEmbedder())
            self.assertEqual(path.read_bytes(), b"existing user content")

    def test_separate_seed_replays_do_not_share_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            first, _ = runner.materialize_seed(seed(), Path(temporary) / "first.sqlite3", FakeEmbedder())
            second, _ = runner.materialize_seed(seed(), Path(temporary) / "second.sqlite3", FakeEmbedder())
            first.forget(memory_id(7))
            self.assertFalse(first.search_keywords("mango"))
            self.assertEqual([match.memory.id for match in second.search_keywords("mango")], [memory_id(7)])

    def run_offline(self, temporary, client, records, *, arm="small"):
        directory = Path(temporary)
        directory.chmod(0o700)
        backend = OfflineBackend(client)
        store, _ = runner.materialize_seed(seed(), directory / "memory.sqlite3", FakeEmbedder())
        with runner._DurableJsonlWriter(directory / "observations.jsonl") as writer, redirect_stdout(io.StringIO()):
            runner.run_cases(cases(), arm, 1, load_config(), backend, store, writer, records)
        return backend

    def test_model_messages_only_contain_prompt_not_case_metadata_or_rubrics(self):
        with tempfile.TemporaryDirectory() as temporary:
            records, client = [], FakeClient()
            backend = self.run_offline(temporary, client, records)
            self.assertEqual([row["index"] for row in records], [1, 2])
            self.assertEqual([row["status"] for row in records], ["ok", "ok"])
            self.assertEqual(len(client.calls), 4)
            serialized = json.dumps(client.calls)
            for secret_metadata in ("CASE_METADATA_SENTINEL", "STRATUM_SENTINEL", "SCENARIO_SENTINEL"):
                self.assertNotIn(secret_metadata, serialized)
            self.assertEqual(client.calls[:2], client.calls[2:])
            self.assertEqual([call["purpose"] for call in backend.calls],
                             ["memory_selector", "generation"] * 2)
            self.assertTrue(all(call[0] == runner.SMALL for call in client.calls))
            self.assertTrue(all(call["actual_model"] == runner.SMALL for call in backend.calls))
            self.assertEqual([len(row["calls"]) for row in records], [2, 2])
            saved = [json.loads(line) for line in (Path(temporary) / "observations.jsonl").read_text().splitlines()]
            self.assertEqual(saved, records)

    def test_invalid_answer_stays_in_denominator_and_next_case_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            records, client = [], FakeClient(invalid_first_generation=True)
            self.run_offline(temporary, client, records)
            self.assertEqual([row["status"] for row in records], ["error", "ok"])
            self.assertEqual([row["index"] for row in records], [1, 2])
            self.assertIn("error", records[0])
            self.assertEqual(len(client.calls), 4)

    def test_transport_error_is_durably_saved_then_aborts_before_second_case(self):
        with tempfile.TemporaryDirectory() as temporary:
            records, client = [], FakeClient(failure=OllamaTimeoutError("offline timeout"))
            with self.assertRaises(OllamaTimeoutError):
                self.run_offline(temporary, client, records)
            self.assertEqual(len(client.calls), 1)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["status"], "interrupted")
            self.assertEqual(records[0]["calls"][0]["status"], "error")
            saved = [json.loads(line) for line in (Path(temporary) / "observations.jsonl").read_text().splitlines()]
            self.assertEqual(saved, records)

    def test_safety_error_cannot_be_masked_by_router_exception_wrapping(self):
        with tempfile.TemporaryDirectory() as temporary:
            records, client = [], FakeClient(failure=runner.SafetyGateError("offline safety boundary"))
            with self.assertRaises(runner.SafetyGateError):
                self.run_offline(temporary, client, records)
            self.assertEqual(len(client.calls), 1)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["status"], "interrupted")
            saved = json.loads((Path(temporary) / "observations.jsonl").read_text())
            self.assertEqual(saved, records[0])

    def test_rejected_output_is_failed_not_delivered_and_next_case_still_runs(self):
        import analyze_complete_system as analysis
        for message in runner.OUTPUT_VALIDATION_ERRORS:
            class RejectFirstGeneration(FakeClient):
                rejected = False

                def chat(self, model, messages, **kwargs):
                    result = super().chat(model, messages, **kwargs)
                    if "speech" in kwargs["response_format"]["properties"] and not self.rejected:
                        self.rejected = True
                        raise OllamaError(message)
                    return result

            with self.subTest(message=message), tempfile.TemporaryDirectory() as temporary:
                records, client = [], RejectFirstGeneration()
                backend = self.run_offline(temporary, client, records)
                self.assertEqual([row["status"] for row in records], ["error", "ok"])
                self.assertNotIn("response", records[0])
                self.assertEqual(records[0]["calls"][-1]["message"], message)
                self.assertEqual(records[0]["calls"][-1]["status"], "error")
                self.assertIsNotNone(records[0]["route"])
                self.assertIsNone(backend.transport_error)
                self.assertEqual(len(client.calls), 4)
                scores = analysis.lexical_signals(records[0], {"automated_checks": {
                    "required_groups": [{"any": ["Hello"]}], "forbidden_presence_patterns": []}})
                self.assertEqual(scores["status"], "not_evaluated_no_delivery")
                self.assertIsNone(scores["semantic_correctness"])

    def test_real_http_output_validation_retains_raw_payload_and_generation_metadata(self):
        config = runner.single_model_config(load_config(), runner.SMALL)
        for content, error in (
            ({"speech": "memory_ref_1 says hello", "gesture_id": "NO_ACTION",
              "memory_used": ["memory_ref_1"]},
             "Ollama assistant speech contains a reserved memory reference"),
            ({"speech": "Hello.", "gesture_id": "NO_ACTION",
              "memory_used": [memory_id(7)]},
             "Ollama assistant returned an internal memory ID"),
        ):
            payload = {"model": runner.SMALL, "done": True, "done_reason": "stop",
                       "message": {"role": "assistant", "content": json.dumps(content)},
                       "total_duration": 101, "load_duration": 11,
                       "prompt_eval_count": 17, "eval_count": 9, "eval_duration": 40}
            requests = []

            def opener(request, timeout):
                requests.append(json.loads(request.data))
                return io.BytesIO(json.dumps(payload).encode())

            with self.subTest(error=error):
                client = runner.RecordingOllamaClient(config.ollama, config.generation, opener=opener)
                backend = OfflineBackend(client)
                with self.assertRaisesRegex(OllamaError, error):
                    backend.chat(runner.SMALL, [ChatMessage("user", "Use the supplied memory.")],
                                 response_format=build_robot_response_schema((memory_id(7),)))
                self.assertEqual(len(requests), 1)
                self.assertEqual(requests[0]["format"]["properties"]["memory_used"]["items"]["enum"],
                                 ["memory_ref_1"])
                self.assertEqual(client.raw_chat_payloads, [payload])
                self.assertEqual(backend.calls[0]["raw_chat_payload"], payload)
                self.assertEqual(backend.calls[0]["raw_generation"]["content"], json.dumps(content))
                self.assertEqual(backend.calls[0]["raw_generation"]["eval_count"], 9)
                self.assertEqual(backend.calls[0]["raw_generation"]["load_duration_ns"], 11)
                self.assertEqual(backend.calls[0]["actual_model"], runner.SMALL)
                self.assertEqual(backend.calls[0]["status"], "error")
                self.assertNotIn("generation", backend.calls[0])
                self.assertIsNone(backend.transport_error)

    def test_real_network_error_still_aborts_and_is_not_mistaken_for_output_rejection(self):
        config = runner.single_model_config(load_config(), runner.SMALL)
        requests = []

        def opener(request, timeout):
            requests.append(request.full_url)
            raise URLError("offline simulated connection refusal")

        client = runner.RecordingOllamaClient(config.ollama, config.generation, opener=opener)
        with tempfile.TemporaryDirectory() as temporary:
            records = []
            with self.assertRaisesRegex(OllamaError, "cannot reach Ollama"):
                self.run_offline(temporary, client, records)
            self.assertEqual(len(requests), 1)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["status"], "interrupted")
            self.assertEqual(client.raw_chat_payloads, [])
            self.assertNotIn("raw_chat_payload", records[0]["calls"][0])


if __name__ == "__main__":
    unittest.main()
