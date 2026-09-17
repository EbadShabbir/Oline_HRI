"""Temporary SQLite disclosure authorization; no user database or inference."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
import sqlite3
import tempfile
from threading import Event, Thread
import unittest

import numpy as np

from oline_hri.embedding import EMBEDDING_DIMENSION, MODEL_ID, MODEL_REVISION
from oline_hri.memory import MemoryStore, MemoryStoreError
from oline_hri.retrieval import HybridMatch, HybridRetriever, RetrievalError


class FakeEmbedder:
    model_id, model_revision, dimension = MODEL_ID, MODEL_REVISION, EMBEDDING_DIMENSION

    def __init__(self):
        self.calls = 0

    def embed_passages(self, passages):
        self.calls += 1
        vectors = np.zeros((len(passages), self.dimension), dtype=np.float32)
        vectors[:, 0] = 1.0
        return vectors


class ObservedStore(MemoryStore):
    """Signal SQLite's real lock attempt, before it can acquire the lock."""

    def __init__(self, *args, begin_event, **kwargs):
        super().__init__(*args, **kwargs)
        self.begin_event = begin_event

    @contextmanager
    def _connection(self):
        with super()._connection() as connection:
            connection.set_trace_callback(
                lambda statement: self.begin_event.set()
                if statement == "BEGIN IMMEDIATE" else None
            )
            yield connection


def match(item):
    return HybridMatch(item, 0.02, -1.0, 1, None, None)


class MemoryDisclosureGuardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "synthetic.sqlite3"
        self.now = datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)
        self.embedder = FakeEmbedder()
        self.store = self.make_store()

    def make_store(self, *, profile="fictional-user", begin_event=None):
        options = {
            "profile_id": profile, "clock": lambda: self.now,
            "embedder": self.embedder,
        }
        if begin_event is not None:
            return ObservedStore(self.path, begin_event=begin_event, **options)
        return MemoryStore(self.path, **options)

    def remember(self, **kwargs):
        return self.store.remember("Your camera is in the ochre cabinet.", kind="fact", **kwargs)

    def assert_withheld(self, store, snapshot):
        written = []
        with self.assertRaises(MemoryStoreError):
            with store.disclosure_guard(snapshot):
                written.append("must not be delivered")
        self.assertEqual(written, [])

    def test_current_snapshot_authorizes_only_the_supplied_output_window(self):
        item = self.remember()
        output = StringIO()
        calls = self.embedder.calls
        with self.store.disclosure_guard((item,)):
            output.write(item.canonical_text)
        self.assertEqual(output.getvalue(), item.canonical_text)
        self.assertEqual(self.embedder.calls, calls)
        self.assertTrue(self.store.retrieval_snapshot_is_current((item,)))

    def test_corrected_deleted_or_mismatched_records_never_enter_output_body(self):
        original = self.remember()
        for stale in (
            replace(original, canonical_text="Your camera is in a different cabinet."),
            replace(original, consent_status="unconfirmed"),
            replace(original, importance=original.importance + 1),
        ):
            with self.subTest(stale=stale):
                self.assert_withheld(self.store, (stale,))
        self.assert_withheld(self.make_store(profile="other-fictional-user"), (original,))
        self.now += timedelta(seconds=1)
        replacement = self.store.correct(original.id, "Your camera is in the silver drawer.")
        self.assert_withheld(self.store, (original,))
        with self.store.disclosure_guard((replacement,)):
            pass
        self.store.forget(replacement.id)
        self.assert_withheld(self.store, (replacement,))

    def test_exact_validity_and_retention_boundaries_are_checked(self):
        boundary = self.now + timedelta(minutes=1)
        valid = self.remember(valid_until=boundary.isoformat())
        retained = self.remember(retention_until=boundary.isoformat())
        future = self.remember(valid_from=boundary.isoformat())
        self.assert_withheld(self.store, (future,))
        self.now = boundary - timedelta(microseconds=1)
        with self.store.disclosure_guard((valid, retained)):
            pass
        self.now = boundary
        self.assert_withheld(self.store, (valid,))
        self.assert_withheld(self.store, (retained,))
        with self.store.disclosure_guard((future,)):
            pass

    def test_empty_snapshot_does_not_open_or_create_a_database(self):
        self.assertFalse(self.path.exists())
        with self.store.disclosure_guard(()):
            self.assertFalse(self.path.exists())
        with HybridRetriever(self.store).disclosure_guard(()):
            self.assertFalse(self.path.exists())

    def test_competing_deletion_waits_for_disclosure_then_proceeds(self):
        item = self.remember()
        attempted, finished = Event(), Event()
        writer = self.make_store(begin_event=attempted)
        outcome = []

        def delete():
            try:
                outcome.append(writer.forget(item.id))
            except BaseException as error:
                outcome.append(error)
            finally:
                finished.set()

        thread = Thread(target=delete, daemon=True)
        try:
            with HybridRetriever(self.store).disclosure_guard((match(item),)):
                thread.start()
                self.assertTrue(attempted.wait(2), "writer never attempted its transaction")
                self.assertFalse(finished.wait(0.15), "deletion escaped the disclosure lock")
            self.assertTrue(finished.wait(2), "deletion did not continue after disclosure")
        finally:
            thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(outcome, [(item.id,)])
        self.assertFalse(self.store.retrieval_snapshot_is_current((item,)))

    def test_expiry_is_checked_after_waiting_for_the_lock(self):
        boundary = self.now + timedelta(minutes=1)
        item = self.remember(valid_until=boundary.isoformat())
        attempted, finished = Event(), Event()
        reader = self.make_store(begin_event=attempted)
        outcome = []

        def disclose():
            try:
                with reader.disclosure_guard((item,)):
                    outcome.append("delivered")
            except BaseException as error:
                outcome.append(error)
            finally:
                finished.set()

        thread = Thread(target=disclose, daemon=True)
        connection = sqlite3.connect(self.path, isolation_level=None)
        try:
            connection.execute("BEGIN IMMEDIATE")
            thread.start()
            self.assertTrue(attempted.wait(2), "guard never attempted its transaction")
            self.assertFalse(finished.wait(0.15))
            self.now = boundary
            connection.commit()
            self.assertTrue(finished.wait(2))
        finally:
            connection.rollback()
            connection.close()
            thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(outcome), 1)
        self.assertIsInstance(outcome[0], MemoryStoreError)

    def test_output_failure_releases_the_transaction_and_preserves_the_error(self):
        item = self.remember()
        with self.assertRaisesRegex(RuntimeError, "synthetic output failure"):
            with self.store.disclosure_guard((item,)):
                raise RuntimeError("synthetic output failure")
        self.assertEqual(self.make_store().forget(item.id), (item.id,))

    def test_retriever_passes_exact_canonical_items_and_rejects_missing_support(self):
        item = self.remember()
        observed = []

        class Backend:
            @contextmanager
            def disclosure_guard(self, items):
                observed.append(items)
                yield
                observed.append("released")

        with HybridRetriever(Backend()).disclosure_guard((match(item),)):
            self.assertEqual(observed, [(item,)])
            self.assertIs(observed[0][0], item)
        self.assertEqual(observed, [(item,), "released"])
        with self.assertRaises(RetrievalError):
            with HybridRetriever(object()).disclosure_guard((match(item),)):
                self.fail("an unsupported backend authorized disclosure")
        for invalid in ("invalid", [object()], [match(item), match(item)]):
            with self.subTest(invalid=invalid), self.assertRaises(RetrievalError):
                with HybridRetriever(Backend()).disclosure_guard(invalid):
                    self.fail("invalid snapshot authorized disclosure")


if __name__ == "__main__":
    unittest.main()
