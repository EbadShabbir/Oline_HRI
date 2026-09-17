"""Real SQLite lifecycle visibility across separate processes, with no models."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from oline_hri.embedding import EMBEDDING_DIMENSION, MODEL_ID, MODEL_REVISION
from oline_hri.memory import MemoryStore
from oline_hri.retrieval import HybridRetriever


def identifier(number):
    return f"mem_{number:032x}"


class DeterministicEmbedder:
    """Small deterministic vectors satisfy the real embedding-index contract."""

    model_id, model_revision, dimension = MODEL_ID, MODEL_REVISION, EMBEDDING_DIMENSION

    @staticmethod
    def vector(text):
        value = np.zeros(EMBEDDING_DIMENSION, dtype=np.float32)
        index = int.from_bytes(sha256(text.encode()).digest()[:2], "big") % EMBEDDING_DIMENSION
        value[index] = 1.0
        return value

    def embed_passages(self, passages):
        return np.stack([self.vector(text) for text in passages])

    def embed_query(self, query):
        return self.vector(query)


def worker(parameters):
    now = datetime.fromisoformat(parameters["now"])
    store = MemoryStore(parameters["database"], profile_id=parameters["profile"],
                        clock=lambda: now, embedder=DeterministicEmbedder(), retention_days=7,
                        memory_id_factory=lambda: parameters["new_id"])
    try:
        operation = parameters["operation"]
        if operation == "correct":
            result = store.correct(parameters["target"], parameters["text"]).to_dict()
        elif operation == "forget":
            result = list(store.forget(parameters["target"]))
        elif operation == "recall":
            result = [{"id": match.memory.id, "text": match.memory.canonical_text}
                      for match in HybridRetriever(store).retrieve(parameters["query"], limit=5)]
        else:
            raise ValueError("unknown offline worker operation")
        return {"pid": os.getpid(), "status": "ok", "result": result}
    except Exception as error:
        return {"pid": os.getpid(), "status": "error", "error": type(error).__name__}


class MemoryLifecycleProcessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / "synthetic-memory.sqlite3"
        self.now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
        self.clock = [self.now]
        self.ids = iter(identifier(i) for i in range(1, 50))
        self.alpha = self.store("fictional-alpha")
        self.beta = self.store("fictional-beta")

    def store(self, profile):
        return MemoryStore(self.database, profile_id=profile, clock=lambda: self.clock[0],
                           embedder=DeterministicEmbedder(), memory_id_factory=lambda: next(self.ids),
                           retention_days=7)

    def external(self, operation, *, profile="fictional-alpha", now=None, **kwargs):
        parameters = {"database": str(self.database), "profile": profile,
                      "operation": operation, "now": (now or self.clock[0]).isoformat(), **kwargs}
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--offline-worker"],
                                input=json.dumps(parameters), text=True, capture_output=True,
                                timeout=20, check=True, env=env)
        value = json.loads(result.stdout)
        self.assertNotEqual(value["pid"], os.getpid())
        return value

    def test_external_correction_is_visible_to_existing_reader_and_fresh_process(self):
        original = self.alpha.remember("Your bicycle is blue.", kind="fact")
        other = self.beta.remember("Your bicycle is green.", kind="fact")
        self.clock[0] += timedelta(seconds=1)
        corrected = self.external("correct", target=original.id, new_id=identifier(100),
                                  text="Your bicycle is red.")
        self.assertEqual(corrected["status"], "ok")
        self.assertFalse(self.alpha.retrieval_snapshot_is_current((original,)))
        self.assertEqual([m.memory.id for m in self.alpha.search_keywords("bicycle")], [identifier(100)])
        self.assertEqual([m.memory.id for m in self.alpha.search_semantic("bicycle")], [identifier(100)])
        recalled = self.external("recall", query="What color is my bicycle?")
        self.assertEqual(recalled["result"], [{"id": identifier(100), "text": "Your bicycle is red."}])
        self.assertEqual(self.external("recall", profile="fictional-beta", query="bicycle")["result"],
                         [{"id": other.id, "text": "Your bicycle is green."}])
        self.assertEqual(corrected["result"]["retention_until"], original.retention_until)
        self.assertTrue(self.alpha.embedding_index_status().complete)

    def test_external_forget_removes_entire_chain_but_preserves_other_profile(self):
        original = self.alpha.remember("Your bicycle is blue.", kind="fact")
        other = self.beta.remember("Your bicycle is green.", kind="fact")
        self.clock[0] += timedelta(seconds=1)
        replacement = self.alpha.correct(original.id, "Your bicycle is red.")
        forgotten = self.external("forget", target=replacement.id)
        self.assertEqual(forgotten["status"], "ok")
        self.assertEqual(set(forgotten["result"]), {original.id, replacement.id})
        self.assertFalse(self.alpha.retrieval_snapshot_is_current((replacement,)))
        self.assertEqual(self.alpha.list_memories(include_inactive=True), ())
        self.assertEqual(self.alpha.search_keywords("bicycle"), ())
        self.assertEqual(self.alpha.search_semantic("bicycle"), ())
        self.assertEqual(self.external("recall", query="bicycle")["result"], [])
        self.assertEqual(self.external("recall", profile="fictional-beta", query="bicycle")["result"],
                         [{"id": other.id, "text": "Your bicycle is green."}])
        self.assertTrue(self.alpha.embedding_index_status().complete)

    def test_separate_process_observes_exact_validity_and_retention_expiry(self):
        boundary = self.now + timedelta(minutes=1)
        valid = self.alpha.remember("Your bicycle locker is blue.", kind="fact",
                                    valid_until=boundary.isoformat())
        retained = self.alpha.remember("Your bicycle token is silver.", kind="fact",
                                       retention_until=boundary.isoformat())
        other = self.beta.remember("Your bicycle is green.", kind="fact")
        before = self.external("recall", now=boundary - timedelta(microseconds=1), query="bicycle")
        self.assertEqual({r["id"] for r in before["result"]}, {valid.id, retained.id})
        self.assertEqual(self.external("recall", now=boundary, query="bicycle")["result"], [])
        self.clock[0] = boundary
        self.assertFalse(self.alpha.retrieval_snapshot_is_current((valid,)))
        self.assertFalse(self.alpha.retrieval_snapshot_is_current((retained,)))
        self.assertEqual(self.alpha.search_semantic("bicycle"), ())
        self.assertEqual(self.external("recall", profile="fictional-beta", query="bicycle")["result"],
                         [{"id": other.id, "text": "Your bicycle is green."}])

    def test_external_wrong_profile_cannot_correct_or_forget_another_profiles_row(self):
        original = self.alpha.remember("Your bicycle is blue.", kind="fact")
        for operation in ("correct", "forget"):
            with self.subTest(operation=operation):
                value = self.external(operation, profile="fictional-beta", target=original.id,
                                      new_id=identifier(100), text="Your bicycle is red.")
                self.assertEqual(value["status"], "error")
                self.assertTrue(self.alpha.retrieval_snapshot_is_current((original,)))
                self.assertEqual(self.beta.list_memories(include_inactive=True), ())

    def test_external_forget_between_retrieval_and_generation_prevents_model_call(self):
        from oline_hri.conversation import ConversationError
        from test_conversation_routed import FakeBackend, FakeRouter, routed_conversation, routing_result

        original = self.alpha.remember("Your bicycle is blue.", kind="fact")
        delegate, external = HybridRetriever(self.alpha), self.external

        class ForgetAfterRetrieval:
            def retrieve(self, query, *, limit=3):
                matches = delegate.retrieve(query, limit=limit)
                result = external("forget", target=original.id)
                if result["status"] != "ok":
                    raise AssertionError(result)
                return matches

            def is_current(self, matches):
                return delegate.is_current(matches)

        backend = FakeBackend()
        conversation = routed_conversation(backend, FakeRouter(default=routing_result(True)),
                                           ForgetAfterRetrieval())
        before = conversation.messages
        with self.assertRaisesRegex(ConversationError, "no longer current"):
            conversation.send("What color is my bicycle?")
        self.assertEqual(backend.calls, [])
        self.assertEqual(conversation.messages, before)

    def test_external_correction_during_generation_withholds_stale_answer_and_history(self):
        from oline_hri.conversation import ConversationError
        from test_conversation_routed import FakeBackend, FakeRouter, chat_result, routed_conversation, routing_result

        original = self.alpha.remember("Your bicycle is blue.", kind="fact")
        self.clock[0] += timedelta(seconds=1)
        external = self.external

        class CorrectDuringGeneration(FakeBackend):
            def chat(self, model, messages, **kwargs):
                self.calls.append((model, tuple(messages), kwargs))
                result = external("correct", target=original.id, new_id=identifier(100),
                                  text="Your bicycle is red.")
                if result["status"] != "ok":
                    raise AssertionError(result)
                return chat_result("Your bicycle is blue.", memory_used=(original.id,), model=model)

        backend = CorrectDuringGeneration()
        conversation = routed_conversation(backend, FakeRouter(default=routing_result(True)),
                                           HybridRetriever(self.alpha))
        before = conversation.messages
        with self.assertRaisesRegex(ConversationError, "no longer current"):
            conversation.send("What color is my bicycle?")
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(conversation.messages, before)
        self.assertEqual(self.external("recall", query="bicycle")["result"],
                         [{"id": identifier(100), "text": "Your bicycle is red."}])


if __name__ == "__main__":
    if sys.argv[1:] == ["--offline-worker"]:
        print(json.dumps(worker(json.loads(sys.stdin.read()))))
    else:
        unittest.main()
