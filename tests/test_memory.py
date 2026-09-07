from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest

import numpy as np

from oline_hri.embedding import EMBEDDING_DIMENSION, MODEL_ID, MODEL_REVISION
from oline_hri.memory import (
    MAX_MEMORY_TEXT_LENGTH,
    MAX_SEARCH_QUERY_LENGTH,
    MAX_SEMANTIC_QUERY_LENGTH,
    MAX_SEARCH_TERMS,
    SCHEMA_VERSION,
    EmbeddingIndexStatus,
    MemoryConflictError,
    MemoryNotFoundError,
    MemoryStore,
    MemoryStoreError,
    MemoryValidationError,
)
from oline_hri.retrieval import HybridRetriever


def memory_id(number: int) -> str:
    return f"mem_{number:032x}"


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self) -> None:
        self.value += timedelta(seconds=1)


def unit_vector(index: int) -> np.ndarray:
    vector = np.zeros(EMBEDDING_DIMENSION, dtype=np.float32)
    vector[index] = 1.0
    return vector


class FakeEmbedder:
    model_id = MODEL_ID
    model_revision = MODEL_REVISION
    dimension = EMBEDDING_DIMENSION

    def __init__(self) -> None:
        self.passage_calls = []
        self.query_calls = []
        self.passage_vectors = {}
        self.query_vectors = {}
        self.passage_output = None
        self.query_output = None
        self.fail_passages = False
        self.fail_query = False
        self.on_passages = None
        self.on_query = None

    def vector_for(self, text: str) -> np.ndarray:
        if text in self.passage_vectors:
            return self.passage_vectors[text]
        index = int.from_bytes(sha256(text.encode("utf-8")).digest()[:2], "big")
        return unit_vector(index % EMBEDDING_DIMENSION)

    def embed_passages(self, passages):
        texts = tuple(passages)
        self.passage_calls.append(texts)
        if self.on_passages is not None:
            callback = self.on_passages
            self.on_passages = None
            callback()
        if self.fail_passages:
            raise RuntimeError("injected provider failure")
        if self.passage_output is not None:
            return self.passage_output
        return np.stack([self.vector_for(text) for text in texts])

    def embed_query(self, query):
        self.query_calls.append(query)
        if self.on_query is not None:
            callback = self.on_query
            self.on_query = None
            callback()
        if self.fail_query:
            raise RuntimeError("injected query failure")
        if self.query_output is not None:
            return self.query_output
        return self.query_vectors.get(query, self.vector_for(query))


class MemoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.database = Path(self.temporary_directory.name) / "memory.sqlite3"
        self.clock = MutableClock()
        self.ids = iter(memory_id(number) for number in range(1, 20))

    def store(self, profile_id: str = "alice", embedder=None) -> MemoryStore:
        return MemoryStore(
            self.database,
            profile_id=profile_id,
            clock=self.clock,
            memory_id_factory=lambda: next(self.ids),
            embedder=embedder,
        )

    def test_initialization_is_lazy_versioned_and_creates_fts_objects(self) -> None:
        store = self.store()
        self.assertFalse(self.database.exists())

        self.assertEqual(store.list_memories(), ())

        self.assertTrue(self.database.is_file())
        with sqlite3.connect(self.database) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            objects = connection.execute(
                "SELECT type, name, sql FROM sqlite_master ORDER BY name"
            ).fetchall()
        self.assertEqual(version, SCHEMA_VERSION)
        names = {row[1] for row in objects}
        self.assertIn("memory_item", names)
        self.assertIn("memory_audit", names)
        self.assertIn("memory_fts", names)
        self.assertIn("memory_item_fts_insert", names)
        self.assertIn("memory_item_fts_delete", names)
        self.assertIn("memory_item_fts_update", names)
        self.assertIn("memory_embedding", names)
        self.assertIn("memory_item_embedding_invalidate", names)
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(self.database.stat().st_mode), 0o600)

    def test_remember_round_trips_exact_text_and_metadata_after_reopen(self) -> None:
        text = "Café: Robert'); DROP TABLE memory_item;-- uses 50%_ cocoa."
        item = self.store().remember(
            text,
            kind="preference",
            sensitivity="sensitive",
            importance=5,
            event_time="2026-09-05T15:00:00+03:00",
            valid_until="2027-09-05T12:00:00Z",
        )

        reopened = MemoryStore(self.database, profile_id="alice")
        memories = reopened.list_memories()

        self.assertEqual(memories, (item,))
        self.assertEqual(item.canonical_text, text)
        self.assertEqual(item.event_time, "2026-09-05T12:00:00.000000Z")
        self.assertEqual(item.consent_status, "confirmed")
        self.assertEqual(item.confidence, 1.0)
        self.assertEqual(item.status, "active")
        with sqlite3.connect(self.database) as connection:
            audit = connection.execute(
                "SELECT memory_id, operation FROM memory_audit"
            ).fetchone()
        self.assertEqual(audit, (item.id, "remember"))

    def test_invalid_input_is_rejected_before_database_creation(self) -> None:
        cases = (
            {"canonical_text": " ", "kind": "fact"},
            {"canonical_text": "line\nbreak", "kind": "fact"},
            {
                "canonical_text": "x" * (MAX_MEMORY_TEXT_LENGTH + 1),
                "kind": "fact",
            },
            {"canonical_text": "text", "kind": "unsupported"},
            {
                "canonical_text": "text",
                "kind": "fact",
                "sensitivity": "secret",
            },
            {"canonical_text": "text", "kind": "fact", "importance": True},
            {
                "canonical_text": "text",
                "kind": "fact",
                "event_time": "2026-09-05T12:00:00",
            },
            {
                "canonical_text": "text",
                "kind": "fact",
                "valid_until": "2020-01-01T00:00:00Z",
            },
        )

        store = self.store()
        for arguments in cases:
            with self.subTest(arguments=arguments):
                with self.assertRaises(MemoryValidationError):
                    store.remember(**arguments)
        self.assertFalse(self.database.exists())

    def test_correction_creates_an_atomic_version_chain(self) -> None:
        store = self.store()
        first = store.remember("User prefers mint tea.", kind="preference")
        self.clock.advance()
        second = store.correct(first.id, "User prefers ginger tea.")
        self.clock.advance()
        third = store.correct(second.id, "User prefers green tea.")

        self.assertEqual(store.list_memories(), (third,))
        all_items = {
            item.id: item
            for item in store.list_memories(include_inactive=True)
        }
        self.assertEqual(all_items[first.id].status, "superseded")
        self.assertEqual(all_items[second.id].status, "superseded")
        self.assertEqual(all_items[third.id].status, "active")
        self.assertEqual(second.supersedes_id, first.id)
        self.assertEqual(third.supersedes_id, second.id)
        self.assertEqual(all_items[first.id].valid_until, second.valid_from)
        self.assertEqual(all_items[second.id].valid_until, third.valid_from)

        with self.assertRaises(MemoryNotFoundError):
            store.correct(first.id, "Cannot fork an old version.")
        with self.assertRaises(MemoryConflictError):
            store.correct(third.id, third.canonical_text)
        self.assertEqual(store.list_memories(), (third,))

    def test_failed_correction_rolls_back_original_status(self) -> None:
        store = self.store()
        original = store.remember("Original text.", kind="fact")
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                CREATE TRIGGER reject_test_correction
                BEFORE INSERT ON memory_item
                WHEN NEW.supersedes_id IS NOT NULL
                BEGIN
                    SELECT RAISE(ABORT, 'injected test failure');
                END
                """
            )

        with self.assertRaises(MemoryStoreError):
            store.correct(original.id, "Corrected text.")

        self.assertEqual(store.list_memories(), (original,))
        with sqlite3.connect(self.database) as connection:
            correction_audits = connection.execute(
                "SELECT count(*) FROM memory_audit WHERE operation = 'correct'"
            ).fetchone()[0]
        self.assertEqual(correction_audits, 0)

    def test_future_dated_memory_cannot_be_corrected_early(self) -> None:
        store = self.store()
        future = (self.clock.value + timedelta(days=1)).isoformat()
        original = store.remember(
            "A future-valid fact.", kind="fact", valid_from=future
        )

        with self.assertRaisesRegex(MemoryConflictError, "before its validity"):
            store.correct(original.id, "A premature correction.")

        self.assertEqual(store.list_memories(), (original,))

    def test_profiles_cannot_list_correct_or_forget_each_others_rows(self) -> None:
        alice = self.store("alice")
        bob = self.store("bob")
        alice_item = alice.remember("Alice likes mint tea.", kind="preference")
        bob_item = bob.remember("Bob likes mint tea.", kind="preference")

        self.assertEqual(alice.list_memories(), (alice_item,))
        self.assertEqual(bob.list_memories(), (bob_item,))
        with self.assertRaises(MemoryNotFoundError):
            alice.correct(bob_item.id, "Cross-profile edit.")
        with self.assertRaises(MemoryNotFoundError):
            alice.forget(bob_item.id)
        self.assertEqual(bob.list_memories(), (bob_item,))

    def test_forget_deletes_correction_chain_but_keeps_audit(self) -> None:
        store = self.store()
        first = store.remember("Version one.", kind="fact")
        self.clock.advance()
        second = store.correct(first.id, "Version two.")
        self.clock.advance()
        third = store.correct(second.id, "Version three.")

        forgotten = store.forget(third.id)

        self.assertEqual(forgotten, (third.id, second.id, first.id))
        self.assertEqual(store.list_memories(include_inactive=True), ())
        with sqlite3.connect(self.database) as connection:
            remaining = connection.execute(
                "SELECT count(*) FROM memory_item"
            ).fetchone()[0]
            forgotten_ids = {
                row[0]
                for row in connection.execute(
                    "SELECT memory_id FROM memory_audit WHERE operation = 'forget'"
                )
            }
            audit_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(memory_audit)")
            }
        self.assertEqual(remaining, 0)
        self.assertEqual(forgotten_ids, {first.id, second.id, third.id})
        self.assertNotIn("canonical_text", audit_columns)
        with self.assertRaises(MemoryNotFoundError):
            store.forget(third.id)

    def test_failed_mid_chain_forget_rolls_back_rows_and_audits(self) -> None:
        store = self.store()
        first = store.remember("Version one.", kind="fact")
        self.clock.advance()
        second = store.correct(first.id, "Version two.")
        self.clock.advance()
        third = store.correct(second.id, "Version three.")
        before = store.list_memories(include_inactive=True)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                f"""
                CREATE TRIGGER reject_test_mid_chain_delete
                BEFORE DELETE ON memory_item
                WHEN OLD.id = '{second.id}'
                BEGIN
                    SELECT RAISE(ABORT, 'injected test failure');
                END
                """
            )

        with self.assertRaises(MemoryStoreError):
            store.forget(third.id)

        self.assertEqual(store.list_memories(include_inactive=True), before)
        self.assertEqual(
            store.search_keywords("three")[0].memory.id, third.id
        )
        with sqlite3.connect(self.database) as connection:
            forget_audits = connection.execute(
                "SELECT count(*) FROM memory_audit WHERE operation = 'forget'"
            ).fetchone()[0]
        self.assertEqual(forget_audits, 0)

    def test_newer_database_schema_is_rejected(self) -> None:
        with sqlite3.connect(self.database) as connection:
            connection.execute("PRAGMA user_version = 99")

        with self.assertRaisesRegex(MemoryStoreError, "newer than supported"):
            self.store().list_memories()

    def test_keyword_search_is_literal_unicode_aware_and_ranked(self) -> None:
        store = self.store()
        strongest = store.remember(
            "Café mint tea tea is preferred on 2026-09-05.",
            kind="preference",
        )
        self.clock.advance()
        weaker = store.remember(
            "Mint tea is sometimes served.", kind="preference"
        )
        self.clock.advance()
        store.remember("Coffee is preferred in the evening.", kind="preference")
        named = store.remember(
            "O'Brien takes B12 on 2026-09-05.", kind="routine"
        )

        matches = store.search_keywords("MINT tea")
        cafe_match = store.search_keywords("cafe mint")
        named_match = store.search_keywords("O'Brien B12 2026-09-05")

        self.assertEqual(
            {match.memory.id for match in matches}, {strongest.id, weaker.id}
        )
        self.assertLessEqual(matches[0].rank, matches[1].rank)
        self.assertEqual(
            [match.memory.id for match in matches],
            [match.memory.id for match in store.search_keywords("MINT tea")],
        )
        self.assertEqual(cafe_match[0].memory.id, strongest.id)
        self.assertEqual(named_match[0].memory.id, named.id)
        self.assertEqual(store.search_keywords("beverage infusion"), ())
        self.assertEqual(len(store.search_keywords("mint tea", limit=1)), 1)

    def test_search_applies_profile_status_consent_and_time_filters(self) -> None:
        alice = self.store("alice")
        bob = self.store("bob")
        current = alice.remember("Common token for Alice.", kind="fact")
        bob.remember(
            "Common common common token for Bob.", kind="fact", importance=5
        )
        expired = alice.remember(
            "Boundary expired token.",
            kind="fact",
            valid_until=self.clock.value.isoformat(),
        )
        future = alice.remember(
            "Boundary future token.",
            kind="fact",
            valid_from=(self.clock.value + timedelta(days=1)).isoformat(),
        )
        retained = alice.remember(
            "Boundary retained token.",
            kind="fact",
            retention_until=(self.clock.value + timedelta(seconds=1)).isoformat(),
        )
        retention_expired = alice.remember(
            "Boundary retention-expired token.",
            kind="fact",
            retention_until=self.clock.value.isoformat(),
        )
        old = alice.remember("Legacy superseded token.", kind="fact")
        replacement = alice.correct(old.id, "Current replacement token.")

        common = alice.search_keywords("common", limit=1)
        boundary = alice.search_keywords("boundary")

        self.assertEqual([match.memory.id for match in common], [current.id])
        self.assertEqual(
            {match.memory.id for match in boundary}, {retained.id}
        )
        self.assertNotIn(expired.id, {match.memory.id for match in boundary})
        self.assertNotIn(future.id, {match.memory.id for match in boundary})
        self.assertNotIn(
            retention_expired.id, {match.memory.id for match in boundary}
        )
        self.assertEqual(alice.search_keywords("legacy"), ())
        self.assertEqual(
            alice.search_keywords("replacement")[0].memory.id, replacement.id
        )

        with sqlite3.connect(self.database) as connection:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute(
                "UPDATE memory_item SET consent_status = 'unconfirmed' WHERE id = ?",
                (current.id,),
            )
            connection.execute(
                """
                INSERT INTO memory_fts(memory_id, profile_id, canonical_text)
                VALUES (?, ?, ?)
                """,
                (current.id, "alice", current.canonical_text),
            )
        self.assertEqual(alice.search_keywords("common"), ())

    def test_correction_and_forget_keep_keyword_index_synchronized(self) -> None:
        store = self.store()
        original = store.remember("User prefers distinctive mint.", kind="preference")
        replacement = store.correct(
            original.id, "User prefers distinctive ginger."
        )

        self.assertEqual(store.search_keywords("mint"), ())
        self.assertEqual(
            store.search_keywords("ginger")[0].memory.id, replacement.id
        )
        with sqlite3.connect(self.database) as connection:
            indexed_ids = connection.execute(
                "SELECT memory_id FROM memory_fts"
            ).fetchall()
        self.assertEqual(indexed_ids, [(replacement.id,)])

        store.forget(replacement.id)

        self.assertEqual(store.search_keywords("ginger"), ())
        with sqlite3.connect(self.database) as connection:
            indexed_count = connection.execute(
                "SELECT count(*) FROM memory_fts"
            ).fetchone()[0]
        self.assertEqual(indexed_count, 0)

    def test_operator_like_search_input_cannot_broaden_or_damage_query(self) -> None:
        store = self.store()
        mint = store.remember("Mint tea is preferred.", kind="preference")
        store.remember("A separate private secret exists.", kind="fact")

        self.assertEqual(store.search_keywords("mint OR secret"), ())
        self.assertEqual(store.search_keywords("canonical_text:mint"), ())
        self.assertEqual(store.search_keywords("mint NOT tea"), ())
        self.assertEqual(store.search_keywords("mint (")[0].memory.id, mint.id)
        self.assertEqual(store.search_keywords("mint")[0].memory.id, mint.id)
        self.assertEqual(len(store.list_memories()), 2)

    def test_invalid_search_is_rejected_before_database_creation(self) -> None:
        store = self.store()
        invalid_queries = (
            "",
            "   ",
            "***",
            "line\nbreak",
            "x" * (MAX_SEARCH_QUERY_LENGTH + 1),
            " ".join(f"term{number}" for number in range(MAX_SEARCH_TERMS + 1)),
        )
        for query in invalid_queries:
            with self.subTest(query=query):
                with self.assertRaises(MemoryValidationError):
                    store.search_keywords(query)
        for limit in (True, 0, -1, 101, 1.5):
            with self.subTest(limit=limit):
                with self.assertRaises(MemoryValidationError):
                    store.search_keywords("valid", limit=limit)
        self.assertFalse(self.database.exists())

    def test_rebuild_repairs_all_profiles_without_changing_memory(self) -> None:
        alice = self.store("alice")
        bob = self.store("bob")
        alice_item = alice.remember("Alice remembers saffron.", kind="fact")
        bob_item = bob.remember("Bob remembers cardamom.", kind="fact")
        with sqlite3.connect(self.database) as connection:
            memory_count = connection.execute(
                "SELECT count(*) FROM memory_item"
            ).fetchone()[0]
            audit_count = connection.execute(
                "SELECT count(*) FROM memory_audit"
            ).fetchone()[0]
            connection.execute(
                "DELETE FROM memory_fts WHERE memory_id = ?", (alice_item.id,)
            )
            connection.execute(
                """
                INSERT INTO memory_fts(memory_id, profile_id, canonical_text)
                VALUES ('mem_ffffffffffffffffffffffffffffffff', 'alice', 'ghostword')
                """
            )
        self.assertEqual(alice.search_keywords("saffron"), ())

        alice.rebuild_keyword_index()
        alice.rebuild_keyword_index()

        self.assertEqual(
            alice.search_keywords("saffron")[0].memory.id, alice_item.id
        )
        self.assertEqual(
            bob.search_keywords("cardamom")[0].memory.id, bob_item.id
        )
        with sqlite3.connect(self.database) as connection:
            indexed_ids = {
                row[0] for row in connection.execute("SELECT memory_id FROM memory_fts")
            }
            after_memory_count = connection.execute(
                "SELECT count(*) FROM memory_item"
            ).fetchone()[0]
            after_audit_count = connection.execute(
                "SELECT count(*) FROM memory_audit"
            ).fetchone()[0]
        self.assertEqual(indexed_ids, {alice_item.id, bob_item.id})
        self.assertEqual(after_memory_count, memory_count)
        self.assertEqual(after_audit_count, audit_count)

    def test_vacuum_does_not_break_keyword_index_identity(self) -> None:
        store = self.store()
        removed = store.remember("Temporary rowid filler.", kind="fact")
        retained = store.remember("Stable amethyst memory.", kind="fact")
        store.forget(removed.id)
        with sqlite3.connect(self.database) as connection:
            connection.execute("VACUUM")

        match = store.search_keywords("amethyst")

        self.assertEqual(match[0].memory.id, retained.id)

    def test_schema_one_database_is_migrated_and_backfilled(self) -> None:
        store = self.store()
        original = store.remember("Old lavender preference.", kind="preference")
        replacement = store.correct(
            original.id, "Current rosemary preference."
        )
        with sqlite3.connect(self.database) as connection:
            before_items = connection.execute(
                "SELECT * FROM memory_item ORDER BY id"
            ).fetchall()
            before_audits = connection.execute(
                "SELECT * FROM memory_audit ORDER BY event_id"
            ).fetchall()
            connection.execute("DROP TRIGGER memory_item_fts_insert")
            connection.execute("DROP TRIGGER memory_item_fts_delete")
            connection.execute("DROP TRIGGER memory_item_fts_update")
            connection.execute("DROP TABLE memory_fts")
            connection.execute("DROP TRIGGER memory_item_embedding_invalidate")
            connection.execute("DROP TABLE memory_embedding")
            connection.execute("PRAGMA user_version = 1")

        migrated = self.store()
        match = migrated.search_keywords("rosemary")

        self.assertEqual(match[0].memory.id, replacement.id)
        self.assertEqual(migrated.search_keywords("lavender"), ())
        with sqlite3.connect(self.database) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            after_items = connection.execute(
                "SELECT * FROM memory_item ORDER BY id"
            ).fetchall()
            after_audits = connection.execute(
                "SELECT * FROM memory_audit ORDER BY event_id"
            ).fetchall()
        self.assertEqual(version, SCHEMA_VERSION)
        self.assertEqual(after_items, before_items)
        self.assertEqual(after_audits, before_audits)

    def test_failed_v1_migration_leaves_version_and_data_unchanged(self) -> None:
        store = self.store()
        item = store.remember("Migration-safe text.", kind="fact")
        with sqlite3.connect(self.database) as connection:
            connection.execute("DROP TRIGGER memory_item_fts_insert")
            connection.execute("DROP TRIGGER memory_item_fts_delete")
            connection.execute("DROP TRIGGER memory_item_fts_update")
            connection.execute("DROP TABLE memory_fts")
            connection.execute("CREATE TABLE memory_fts(blocker TEXT)")
            connection.execute("PRAGMA user_version = 1")

        with self.assertRaises(MemoryStoreError):
            self.store().list_memories()

        with sqlite3.connect(self.database) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            saved_text = connection.execute(
                "SELECT canonical_text FROM memory_item WHERE id = ?", (item.id,)
            ).fetchone()[0]
            partial_triggers = connection.execute(
                """
                SELECT count(*) FROM sqlite_master
                WHERE type = 'trigger' AND name LIKE 'memory_item_fts_%'
                """
            ).fetchone()[0]
        self.assertEqual(version, 1)
        self.assertEqual(saved_text, item.canonical_text)
        self.assertEqual(partial_triggers, 0)

    def test_v2_database_migrates_to_empty_embedding_index(self) -> None:
        item = self.store().remember("Existing migration text.", kind="fact")
        with sqlite3.connect(self.database) as connection:
            connection.execute("DROP TRIGGER memory_item_embedding_invalidate")
            connection.execute("DROP TABLE memory_embedding")
            connection.execute("PRAGMA user_version = 2")

        embedder = FakeEmbedder()
        migrated = self.store(embedder=embedder)
        status = migrated.embedding_index_status()

        self.assertEqual(status.eligible, 1)
        self.assertEqual(status.indexed, 0)
        self.assertEqual(status.missing, 1)
        self.assertEqual(status.invalid, 0)
        self.assertFalse(status.complete)
        self.assertEqual(migrated.list_memories(), (item,))
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_failed_v2_migration_is_transactional(self) -> None:
        item = self.store().remember("Keep this migration text.", kind="fact")
        with sqlite3.connect(self.database) as connection:
            connection.execute("DROP TRIGGER memory_item_embedding_invalidate")
            connection.execute("DROP TABLE memory_embedding")
            connection.execute("CREATE TABLE memory_embedding(blocker TEXT)")
            connection.execute("PRAGMA user_version = 2")

        with self.assertRaises(MemoryStoreError):
            self.store().list_memories()

        with sqlite3.connect(self.database) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            saved = connection.execute(
                "SELECT canonical_text FROM memory_item WHERE id = ?", (item.id,)
            ).fetchone()[0]
            invalidation_trigger = connection.execute(
                """
                SELECT count(*) FROM sqlite_master
                WHERE type = 'trigger'
                  AND name = 'memory_item_embedding_invalidate'
                """
            ).fetchone()[0]
        self.assertEqual(version, 2)
        self.assertEqual(saved, item.canonical_text)
        self.assertEqual(invalidation_trigger, 0)

    def test_remember_stores_exact_little_endian_vector_and_metadata(self) -> None:
        embedder = FakeEmbedder()
        text = "Café user prefers mint tea."
        embedder.passage_vectors[text] = np.arange(
            1, EMBEDDING_DIMENSION + 1, dtype=np.float32
        )

        item = self.store(embedder=embedder).remember(
            f"  {text}  ", kind="preference"
        )

        self.assertEqual(embedder.passage_calls, [(text,)])
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(
                """
                SELECT memory_id, model_id, model_revision, dimension,
                       normalized, content_sha256, vector_f32, created_at,
                       updated_at
                FROM memory_embedding
                """
            ).fetchone()
        self.assertEqual(row[0], item.id)
        self.assertEqual(row[1], MODEL_ID)
        self.assertEqual(row[2], MODEL_REVISION)
        self.assertEqual(row[3], EMBEDDING_DIMENSION)
        self.assertEqual(row[4], 1)
        self.assertEqual(row[5], sha256(text.encode("utf-8")).hexdigest())
        self.assertRegex(row[5], r"\A[0-9a-f]{64}\Z")
        self.assertEqual(len(row[6]), EMBEDDING_DIMENSION * 4)
        vector = np.frombuffer(row[6], dtype="<f4")
        self.assertEqual(vector.dtype.str, "<f4")
        self.assertTrue(np.isclose(np.linalg.norm(vector), 1.0))
        self.assertEqual(row[7], item.created_at)
        self.assertEqual(row[8], item.updated_at)

    def test_embedding_failures_do_not_leave_partial_memory_writes(self) -> None:
        embedder = FakeEmbedder()
        embedder.fail_passages = True
        store = self.store(embedder=embedder)

        with self.assertRaisesRegex(MemoryStoreError, "embedding failed"):
            store.remember("Provider failure text.", kind="fact")
        self.assertFalse(self.database.exists())

        embedder.fail_passages = False
        store.list_memories()
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                CREATE TRIGGER reject_test_embedding
                BEFORE INSERT ON memory_embedding
                BEGIN
                    SELECT RAISE(ABORT, 'injected embedding failure');
                END
                """
            )
        with self.assertRaises(MemoryStoreError):
            store.remember("Database failure text.", kind="fact")
        with sqlite3.connect(self.database) as connection:
            counts = tuple(
                connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in (
                    "memory_item",
                    "memory_audit",
                    "memory_fts",
                    "memory_embedding",
                )
            )
        self.assertEqual(counts, (0, 0, 0, 0))

    def test_crud_without_embedder_and_explicit_rebuild_remain_available(self) -> None:
        plain = self.store()
        item = plain.remember("A memory written without a model.", kind="fact")
        self.assertEqual(plain.list_memories(), (item,))

        with self.assertRaisesRegex(MemoryStoreError, "embedding provider"):
            plain.search_semantic("memory")
        embedder = FakeEmbedder()
        semantic = self.store(embedder=embedder)
        self.assertEqual(
            semantic.embedding_index_status(),
            EmbeddingIndexStatus(eligible=1, indexed=0, missing=1, invalid=0),
        )
        with self.assertRaisesRegex(MemoryStoreError, "rebuild-embeddings"):
            semantic.search_semantic("memory")

        rebuilt = semantic.rebuild_embeddings()

        self.assertTrue(rebuilt.complete)
        self.assertEqual(semantic.search_semantic("memory")[0].memory, item)

    def test_correction_and_forget_replace_then_cascade_embeddings(self) -> None:
        embedder = FakeEmbedder()
        store = self.store(embedder=embedder)
        original = store.remember("Original vector text.", kind="fact")
        replacement = store.correct(original.id, "Corrected vector text.")

        with sqlite3.connect(self.database) as connection:
            ids = connection.execute(
                "SELECT memory_id FROM memory_embedding ORDER BY memory_id"
            ).fetchall()
        self.assertEqual(ids, [(replacement.id,)])
        self.assertTrue(store.embedding_index_status().complete)

        store.forget(replacement.id)

        with sqlite3.connect(self.database) as connection:
            count = connection.execute(
                "SELECT count(*) FROM memory_embedding"
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_correction_embedding_failure_preserves_original_and_indexes(self) -> None:
        embedder = FakeEmbedder()
        store = self.store(embedder=embedder)
        original = store.remember("Unchanged original vector.", kind="fact")
        with sqlite3.connect(self.database) as connection:
            before_item = connection.execute(
                "SELECT * FROM memory_item WHERE id = ?", (original.id,)
            ).fetchone()
            before_embedding = connection.execute(
                "SELECT * FROM memory_embedding WHERE memory_id = ?", (original.id,)
            ).fetchone()
            before_fts = connection.execute(
                "SELECT * FROM memory_fts WHERE memory_id = ?", (original.id,)
            ).fetchone()
            before_audits = connection.execute(
                "SELECT count(*) FROM memory_audit"
            ).fetchone()[0]
        embedder.fail_passages = True

        with self.assertRaisesRegex(MemoryStoreError, "embedding failed"):
            store.correct(original.id, "This correction must not persist.")

        with sqlite3.connect(self.database) as connection:
            after_item = connection.execute(
                "SELECT * FROM memory_item WHERE id = ?", (original.id,)
            ).fetchone()
            after_embedding = connection.execute(
                "SELECT * FROM memory_embedding WHERE memory_id = ?", (original.id,)
            ).fetchone()
            after_fts = connection.execute(
                "SELECT * FROM memory_fts WHERE memory_id = ?", (original.id,)
            ).fetchone()
            after_audits = connection.execute(
                "SELECT count(*) FROM memory_audit"
            ).fetchone()[0]
        self.assertEqual(after_item, before_item)
        self.assertEqual(after_embedding, before_embedding)
        self.assertEqual(after_fts, before_fts)
        self.assertEqual(after_audits, before_audits)

    def test_authoritative_updates_invalidate_stale_embeddings(self) -> None:
        embedder = FakeEmbedder()
        store = self.store(embedder=embedder)
        item = store.remember("Hash-bound text.", kind="fact")

        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                UPDATE memory_item
                SET canonical_text = 'Changed outside MemoryStore.'
                WHERE id = ?
                """,
                (item.id,),
            )
            remaining = connection.execute(
                "SELECT count(*) FROM memory_embedding"
            ).fetchone()[0]

        self.assertEqual(remaining, 0)
        self.assertEqual(store.embedding_index_status().missing, 1)

    def test_semantic_search_filters_then_ranks_with_stable_ties(self) -> None:
        embedder = FakeEmbedder()
        query = "usual drink"
        embedder.query_vectors[query] = unit_vector(0)
        texts = {
            "Tie A.": unit_vector(0),
            "Tie B.": unit_vector(0),
            "Related.": np.array(
                [0.8, 0.6] + [0.0] * (EMBEDDING_DIMENSION - 2),
                dtype=np.float32,
            ),
            "Orthogonal.": unit_vector(1),
            "Future.": unit_vector(0),
            "Expired.": unit_vector(0),
            "Retention expired.": unit_vector(0),
            "Bob private.": unit_vector(0),
        }
        embedder.passage_vectors.update(texts)
        alice = self.store("alice", embedder)
        first = alice.remember("Tie A.", kind="fact")
        second = alice.remember("Tie B.", kind="fact")
        related = alice.remember("Related.", kind="fact")
        orthogonal = alice.remember("Orthogonal.", kind="fact")
        alice.remember(
            "Future.",
            kind="fact",
            valid_from=(self.clock.value + timedelta(days=1)).isoformat(),
        )
        alice.remember(
            "Expired.", kind="fact", valid_until=self.clock.value.isoformat()
        )
        alice.remember(
            "Retention expired.",
            kind="fact",
            retention_until=self.clock.value.isoformat(),
        )
        self.store("bob", embedder).remember("Bob private.", kind="fact")
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                UPDATE memory_embedding SET vector_f32 = zeroblob(?)
                WHERE memory_id IN (
                    SELECT id FROM memory_item
                    WHERE canonical_text IN (
                        'Future.', 'Expired.', 'Retention expired.'
                    )
                )
                """,
                (EMBEDDING_DIMENSION * 4,),
            )

        matches = alice.search_semantic(query, limit=10)

        self.assertEqual(embedder.query_calls, [query])
        self.assertEqual(
            [match.memory.id for match in matches],
            [first.id, second.id, related.id, orthogonal.id],
        )
        self.assertAlmostEqual(matches[0].score, 1.0, places=6)
        self.assertAlmostEqual(matches[2].score, 0.8, places=6)

    def test_semantic_search_rejects_missing_stale_and_corrupt_index(self) -> None:
        item = self.store().remember("Index integrity text.", kind="fact")
        embedder = FakeEmbedder()
        store = self.store(embedder=embedder)
        vector_blob = unit_vector(0).astype("<f4").tobytes()
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                INSERT INTO memory_embedding (
                    memory_id, model_id, model_revision, dimension,
                    normalized, content_sha256, vector_f32, created_at,
                    updated_at
                ) VALUES (?, ?, 'old-revision', ?, 1, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    MODEL_ID,
                    EMBEDDING_DIMENSION,
                    sha256(item.canonical_text.encode("utf-8")).hexdigest(),
                    vector_blob,
                    item.created_at,
                    item.updated_at,
                ),
            )
        self.assertEqual(store.embedding_index_status().missing, 1)
        with self.assertRaisesRegex(MemoryStoreError, "rebuild-embeddings"):
            store.search_semantic("integrity")
        self.assertEqual(embedder.query_calls, [])

        store.rebuild_embeddings()
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                UPDATE memory_embedding SET content_sha256 = ?
                WHERE memory_id = ? AND model_revision = ?
                """,
                ("0" * 64, item.id, MODEL_REVISION),
            )
        status = store.embedding_index_status()
        self.assertEqual((status.missing, status.invalid), (0, 1))
        with self.assertRaisesRegex(MemoryStoreError, "rebuild-embeddings"):
            store.search_semantic("integrity")

        store.rebuild_embeddings()
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                UPDATE memory_embedding SET vector_f32 = zeroblob(?)
                WHERE memory_id = ?
                """,
                (EMBEDDING_DIMENSION * 4, item.id),
            )
        self.assertEqual(store.embedding_index_status().invalid, 1)
        with self.assertRaisesRegex(MemoryStoreError, "rebuild-embeddings"):
            store.search_semantic("integrity")
        self.assertEqual(embedder.query_calls, [])

    def test_semantic_search_revalidates_after_query_inference(self) -> None:
        embedder = FakeEmbedder()
        store = self.store(embedder=embedder)
        item = store.remember("A concurrently forgotten memory.", kind="fact")
        external = MemoryStore(
            self.database,
            profile_id="alice",
            clock=self.clock,
        )
        embedder.on_query = lambda: external.forget(item.id)

        matches = store.search_semantic("concurrent forget")

        self.assertEqual(matches, ())
        self.assertEqual(embedder.query_calls, ["concurrent forget"])

    def test_semantic_and_hybrid_search_accept_conversation_length_queries(
        self,
    ) -> None:
        embedder = FakeEmbedder()
        store = self.store(embedder=embedder)
        item = store.remember("A verified personal memory.", kind="fact")
        hybrid_query = "q" * (MAX_SEARCH_QUERY_LENGTH + 1)
        maximum_query = "q" * MAX_SEMANTIC_QUERY_LENGTH

        with self.assertRaises(MemoryValidationError):
            store.search_keywords(hybrid_query)
        hybrid_matches = HybridRetriever(store).retrieve(hybrid_query)
        semantic_matches = store.search_semantic(maximum_query)

        self.assertEqual([match.memory for match in hybrid_matches], [item])
        self.assertEqual(hybrid_matches[0].sources, ("semantic",))
        self.assertEqual([match.memory for match in semantic_matches], [item])
        self.assertEqual(embedder.query_calls, [hybrid_query, maximum_query])

    def test_rebuild_is_idempotent_profile_scoped_and_cleans_old_revision(self) -> None:
        embedder = FakeEmbedder()
        alice = self.store("alice", embedder)
        bob = self.store("bob", embedder)
        alice_item = alice.remember("Alice vector.", kind="fact")
        bob_item = bob.remember("Bob vector.", kind="fact")
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                UPDATE memory_embedding SET model_revision = 'old'
                WHERE memory_id = ?
                """,
                (alice_item.id,),
            )
            bob_before = connection.execute(
                "SELECT * FROM memory_embedding WHERE memory_id = ?", (bob_item.id,)
            ).fetchone()
        embedder.passage_calls.clear()

        first_status = alice.rebuild_embeddings()
        with sqlite3.connect(self.database) as connection:
            alice_after_first = connection.execute(
                "SELECT * FROM memory_embedding WHERE memory_id = ?",
                (alice_item.id,),
            ).fetchone()
            bob_after = connection.execute(
                "SELECT * FROM memory_embedding WHERE memory_id = ?", (bob_item.id,)
            ).fetchone()
            old_count = connection.execute(
                "SELECT count(*) FROM memory_embedding WHERE model_revision = 'old'"
            ).fetchone()[0]
        second_status = alice.rebuild_embeddings()
        with sqlite3.connect(self.database) as connection:
            alice_after_second = connection.execute(
                "SELECT * FROM memory_embedding WHERE memory_id = ?",
                (alice_item.id,),
            ).fetchone()

        self.assertTrue(first_status.complete)
        self.assertEqual(first_status, second_status)
        self.assertEqual(embedder.passage_calls, [(alice_item.canonical_text,)] * 2)
        self.assertEqual(alice_after_first, alice_after_second)
        self.assertEqual(bob_before, bob_after)
        self.assertEqual(old_count, 0)

    def test_rebuild_detects_snapshot_change_without_partial_replacement(self) -> None:
        embedder = FakeEmbedder()
        store = self.store(embedder=embedder)
        existing = store.remember("Existing indexed text.", kind="fact")
        with sqlite3.connect(self.database) as connection:
            before = connection.execute(
                "SELECT * FROM memory_embedding WHERE memory_id = ?", (existing.id,)
            ).fetchone()
        external = MemoryStore(
            self.database,
            profile_id="alice",
            clock=self.clock,
            memory_id_factory=lambda: memory_id(99),
        )
        embedder.on_passages = lambda: external.remember(
            "Concurrent unindexed text.", kind="fact"
        )

        with self.assertRaisesRegex(MemoryConflictError, "changed during"):
            store.rebuild_embeddings()

        with sqlite3.connect(self.database) as connection:
            after = connection.execute(
                "SELECT * FROM memory_embedding WHERE memory_id = ?", (existing.id,)
            ).fetchone()
            embedding_count = connection.execute(
                "SELECT count(*) FROM memory_embedding"
            ).fetchone()[0]
        self.assertEqual(after, before)
        self.assertEqual(embedding_count, 1)
        self.assertEqual(store.embedding_index_status().missing, 1)

    def test_failed_rebuild_restores_the_previous_complete_index(self) -> None:
        embedder = FakeEmbedder()
        store = self.store(embedder=embedder)
        item = store.remember("Atomic rebuild vector.", kind="fact")
        with sqlite3.connect(self.database) as connection:
            before = connection.execute(
                "SELECT * FROM memory_embedding WHERE memory_id = ?", (item.id,)
            ).fetchone()
            connection.execute(
                """
                CREATE TRIGGER reject_test_rebuild_embedding
                BEFORE INSERT ON memory_embedding
                BEGIN
                    SELECT RAISE(ABORT, 'injected rebuild failure');
                END
                """
            )

        with self.assertRaises(MemoryStoreError):
            store.rebuild_embeddings()

        with sqlite3.connect(self.database) as connection:
            after = connection.execute(
                "SELECT * FROM memory_embedding WHERE memory_id = ?", (item.id,)
            ).fetchone()
        self.assertEqual(after, before)
        self.assertTrue(store.embedding_index_status().complete)

    def test_retrieval_snapshot_accepts_unchanged_records_up_to_five(self) -> None:
        store = self.store()
        items = tuple(
            store.remember(f"Snapshot memory {number}.", kind="fact")
            for number in range(5)
        )

        self.assertTrue(store.retrieval_snapshot_is_current(items))
        self.assertTrue(
            store.retrieval_snapshot_is_current(tuple(reversed(items)))
        )
        self.assertTrue(store.retrieval_snapshot_is_current(list(items)))

    def test_retrieval_snapshot_detects_correction_and_forget(self) -> None:
        store = self.store()
        original = store.remember("Original snapshot text.", kind="fact")
        self.assertTrue(store.retrieval_snapshot_is_current((original,)))

        replacement = store.correct(original.id, "Corrected snapshot text.")

        self.assertFalse(store.retrieval_snapshot_is_current((original,)))
        self.assertTrue(store.retrieval_snapshot_is_current((replacement,)))
        self.assertFalse(
            store.retrieval_snapshot_is_current((original, replacement))
        )

        store.forget(replacement.id)

        self.assertFalse(store.retrieval_snapshot_is_current((replacement,)))

    def test_retrieval_snapshot_observes_expiration_and_retention_boundaries(
        self,
    ) -> None:
        store = self.store()
        boundary = (self.clock.value + timedelta(seconds=1)).isoformat()
        validity_limited = store.remember(
            "Expires at the next clock tick.",
            kind="fact",
            valid_until=boundary,
        )
        retention_limited = store.remember(
            "Retention ends at the next clock tick.",
            kind="fact",
            retention_until=boundary,
        )
        future = store.remember(
            "Not valid until tomorrow.",
            kind="fact",
            valid_from=(self.clock.value + timedelta(days=1)).isoformat(),
        )

        self.assertTrue(
            store.retrieval_snapshot_is_current(
                (validity_limited, retention_limited)
            )
        )
        self.assertFalse(store.retrieval_snapshot_is_current((future,)))

        self.clock.advance()

        self.assertFalse(
            store.retrieval_snapshot_is_current((validity_limited,))
        )
        self.assertFalse(
            store.retrieval_snapshot_is_current((retention_limited,))
        )

    def test_retrieval_snapshot_is_strictly_profile_scoped(self) -> None:
        alice = self.store("alice")
        bob = self.store("bob")
        alice_item = alice.remember("Alice snapshot.", kind="fact")
        bob_item = bob.remember("Bob snapshot.", kind="fact")

        self.assertTrue(alice.retrieval_snapshot_is_current((alice_item,)))
        self.assertTrue(bob.retrieval_snapshot_is_current((bob_item,)))
        self.assertFalse(alice.retrieval_snapshot_is_current((bob_item,)))
        self.assertFalse(bob.retrieval_snapshot_is_current((alice_item,)))
        self.assertFalse(
            alice.retrieval_snapshot_is_current((alice_item, bob_item))
        )

    def test_retrieval_snapshot_rejects_invalid_types_duplicates_and_size(
        self,
    ) -> None:
        store = self.store()

        self.assertTrue(store.retrieval_snapshot_is_current(()))
        self.assertFalse(self.database.exists())
        for invalid in (
            "not items",
            b"not items",
            None,
            object(),
            (object(),),
            (None,),
            (item for item in ()),
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(MemoryValidationError):
                    store.retrieval_snapshot_is_current(invalid)
        self.assertFalse(self.database.exists())

        items = tuple(
            store.remember(f"Bounded snapshot {number}.", kind="fact")
            for number in range(6)
        )
        with self.assertRaisesRegex(MemoryValidationError, "duplicate"):
            store.retrieval_snapshot_is_current((items[0], items[0]))
        with self.assertRaisesRegex(MemoryValidationError, "more than 5"):
            store.retrieval_snapshot_is_current(items)

    def test_retrieval_snapshot_requires_exact_authoritative_item(self) -> None:
        store = self.store()
        item = store.remember("Exact authoritative snapshot.", kind="fact")
        mismatches = (
            replace(item, canonical_text="Stale text."),
            replace(item, importance=item.importance + 1),
            replace(item, updated_at="2026-09-06T00:00:00.000000Z"),
            replace(item, sensitivity="sensitive"),
        )

        self.assertTrue(store.retrieval_snapshot_is_current((item,)))
        for mismatch in mismatches:
            with self.subTest(field_difference=mismatch):
                self.assertFalse(
                    store.retrieval_snapshot_is_current((mismatch,))
                )

    def test_empty_semantic_index_avoids_model_inference(self) -> None:
        embedder = FakeEmbedder()
        store = self.store(embedder=embedder)

        status = store.rebuild_embeddings()
        results = store.search_semantic("anything")

        self.assertTrue(status.complete)
        self.assertEqual(status.eligible, 0)
        self.assertEqual(results, ())
        self.assertEqual(embedder.passage_calls, [])
        self.assertEqual(embedder.query_calls, [])

    def test_invalid_semantic_input_precedes_database_and_model_work(self) -> None:
        embedder = FakeEmbedder()
        store = self.store(embedder=embedder)
        for query in (
            "",
            "   ",
            "line\nbreak",
            "x" * (MAX_SEMANTIC_QUERY_LENGTH + 1),
        ):
            with self.subTest(query=query):
                with self.assertRaises(MemoryValidationError):
                    store.search_semantic(query)
        for limit in (True, 0, -1, 101, 1.5):
            with self.subTest(limit=limit):
                with self.assertRaises(MemoryValidationError):
                    store.search_semantic("valid", limit=limit)
        self.assertFalse(self.database.exists())
        self.assertEqual(embedder.query_calls, [])

    def test_constructor_rejects_unsafe_profile_id_and_relative_path(self) -> None:
        with self.assertRaises(MemoryValidationError):
            MemoryStore(self.database, profile_id="alice' OR 1=1 --")
        with self.assertRaises(MemoryValidationError):
            MemoryStore("relative.sqlite3", profile_id="alice")


if __name__ == "__main__":
    unittest.main()
