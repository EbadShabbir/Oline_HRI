"""Opt-in acceptance test for the provisioned Jetson embedding runtime."""

import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

import numpy as np

from oline_hri.config import load_config
from oline_hri.embedding import BgeOnnxEmbedder, EMBEDDING_DIMENSION
from oline_hri.memory import MemoryStore


@unittest.skipUnless(
    os.environ.get("OLINE_HRI_RUN_LIVE_EMBEDDING") == "1",
    "set OLINE_HRI_RUN_LIVE_EMBEDDING=1 to use the real local model",
)
class LiveEmbeddingTests(unittest.TestCase):
    def embedder(self) -> BgeOnnxEmbedder:
        config = load_config()
        return BgeOnnxEmbedder(
            Path(config.embedding.model_directory),
            config.embedding.intra_op_threads,
        )

    def test_cpu_model_produces_normalized_semantic_rankings(self) -> None:
        embedder = self.embedder()
        passages = embedder.embed_passages(
            (
                "The user prefers mint tea without sugar.",
                "The user's bicycle is red.",
                "The next meeting is on Tuesday afternoon.",
            )
        )
        query = embedder.embed_query("How does the user like their tea?")

        self.assertEqual(passages.shape, (3, EMBEDDING_DIMENSION))
        self.assertEqual(query.shape, (EMBEDDING_DIMENSION,))
        self.assertEqual(passages.dtype, np.float32)
        self.assertEqual(query.dtype, np.float32)
        np.testing.assert_allclose(
            np.linalg.norm(passages, axis=1), np.ones(3), atol=1e-5
        )
        self.assertAlmostEqual(float(np.linalg.norm(query)), 1.0, places=5)
        scores = passages @ query
        self.assertEqual(int(np.argmax(scores)), 0)
        self.assertEqual(embedder._session.get_providers(), ["CPUExecutionProvider"])

    def test_real_vectors_persist_and_drive_exact_memory_search(self) -> None:
        embedder = self.embedder()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "memory.sqlite3"
            plain_store = MemoryStore(database, profile_id="smoke_test")
            tea = plain_store.remember(
                "The user prefers mint tea without sugar.", kind="preference"
            )
            plain_store.remember("The user's bicycle is red.", kind="fact")
            plain_store.remember(
                "The next meeting is on Tuesday afternoon.", kind="event"
            )
            semantic_store = MemoryStore(
                database,
                profile_id="smoke_test",
                embedder=embedder,
            )

            before = semantic_store.embedding_index_status()
            after = semantic_store.rebuild_embeddings()
            matches = semantic_store.search_semantic(
                "How does the user like their tea?", limit=3
            )

            self.assertEqual((before.eligible, before.missing), (3, 3))
            self.assertTrue(after.complete)
            self.assertEqual(matches[0].memory.id, tea.id)
            with sqlite3.connect(database) as connection:
                lengths = connection.execute(
                    "SELECT length(vector_f32) FROM memory_embedding"
                ).fetchall()
            self.assertEqual(lengths, [(EMBEDDING_DIMENSION * 4,)] * 3)


if __name__ == "__main__":
    unittest.main()
