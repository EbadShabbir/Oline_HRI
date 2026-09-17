"""Explicit, profile-scoped personal-memory storage in SQLite."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
from pathlib import Path
import re
import sqlite3
from typing import Callable, Iterator, Optional, Sequence
import unicodedata
from uuid import uuid4

import numpy as np

from .embedding import EMBEDDING_DIMENSION, EmbeddingProvider


SCHEMA_VERSION = 3
MAX_MEMORY_TEXT_LENGTH = 1000
MAX_SEARCH_QUERY_LENGTH = 200
MAX_SEMANTIC_QUERY_LENGTH = 1000
MAX_SEARCH_TERMS = 16
MAX_RETENTION_DAYS = 3650
MEMORY_KINDS = ("event", "fact", "preference", "relationship", "routine")
MEMORY_SENSITIVITIES = ("normal", "sensitive")
MEMORY_STATUSES = ("active", "superseded", "retracted")

_PROFILE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_MEMORY_ID_PATTERN = re.compile(r"mem_[0-9a-f]{32}\Z")
_CONTENT_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_QUESTION_SHAPED_MEMORY_PATTERN = re.compile(
    r"\A\s*(?:(?:what|who|when|where|why|how)\s+"
    r"(?:am|are|can|could|did|do|does|had|has|have|is|should|was|were|will|would)\b|"
    r"(?:am|are|can|could|did|do|does|had|has|have|is|shall|should|was|were|would)"
    r"\s+(?:i|you|we|they|he|she|it|my|your|our|the)\b)",
    re.IGNORECASE,
)
_EMBEDDING_VECTOR_BYTES = EMBEDDING_DIMENSION * np.dtype("<f4").itemsize
_EMBEDDING_LABEL_MAX_LENGTH = 255
_MEMORY_COLUMNS = """
    id, profile_id, kind, canonical_text, source_turn_id, event_time,
    sensitivity, consent_status, confidence, importance, status,
    supersedes_id, valid_from, valid_until, retention_until, created_at,
    updated_at
"""
_SEARCH_MEMORY_COLUMNS = """
    item.id AS id, item.profile_id AS profile_id, item.kind AS kind,
    item.canonical_text AS canonical_text,
    item.source_turn_id AS source_turn_id, item.event_time AS event_time,
    item.sensitivity AS sensitivity,
    item.consent_status AS consent_status, item.confidence AS confidence,
    item.importance AS importance, item.status AS status,
    item.supersedes_id AS supersedes_id, item.valid_from AS valid_from,
    item.valid_until AS valid_until,
    item.retention_until AS retention_until, item.created_at AS created_at,
    item.updated_at AS updated_at
"""

_MIGRATION_1_STATEMENTS = (
    """
    CREATE TABLE memory_item (
        id TEXT PRIMARY KEY,
        profile_id TEXT NOT NULL
            CHECK(length(profile_id) BETWEEN 1 AND 64),
        kind TEXT NOT NULL
            CHECK(kind IN ('event', 'fact', 'preference', 'relationship', 'routine')),
        canonical_text TEXT NOT NULL
            CHECK(length(trim(canonical_text)) BETWEEN 1 AND 1000),
        source_turn_id TEXT,
        event_time TEXT,
        sensitivity TEXT NOT NULL
            CHECK(sensitivity IN ('normal', 'sensitive')),
        consent_status TEXT NOT NULL
            CHECK(consent_status = 'confirmed'),
        confidence REAL NOT NULL
            CHECK(confidence >= 0.0 AND confidence <= 1.0),
        importance INTEGER NOT NULL
            CHECK(typeof(importance) = 'integer' AND importance BETWEEN 1 AND 5),
        status TEXT NOT NULL
            CHECK(status IN ('active', 'superseded', 'retracted')),
        supersedes_id TEXT
            REFERENCES memory_item(id) ON DELETE SET NULL,
        valid_from TEXT NOT NULL,
        valid_until TEXT,
        retention_until TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK(status != 'active' OR consent_status = 'confirmed'),
        CHECK(valid_until IS NULL OR valid_until >= valid_from),
        CHECK(retention_until IS NULL OR retention_until >= valid_from)
    )
    """,
    """
    CREATE INDEX memory_item_profile_status_created
    ON memory_item(profile_id, status, created_at, id)
    """,
    """
    CREATE UNIQUE INDEX memory_item_single_correction
    ON memory_item(supersedes_id)
    WHERE supersedes_id IS NOT NULL
    """,
    """
    CREATE TABLE memory_audit (
        event_id TEXT PRIMARY KEY,
        memory_id TEXT NOT NULL,
        related_memory_id TEXT,
        profile_id TEXT NOT NULL,
        operation TEXT NOT NULL
            CHECK(operation IN ('remember', 'correct', 'forget')),
        occurred_at TEXT NOT NULL
    )
    """,
)

_MIGRATION_2_STATEMENTS = (
    """
    CREATE VIRTUAL TABLE memory_fts USING fts5(
        memory_id UNINDEXED,
        profile_id UNINDEXED,
        canonical_text,
        tokenize = 'unicode61 remove_diacritics 2'
    )
    """,
    """
    CREATE TRIGGER memory_item_fts_insert
    AFTER INSERT ON memory_item
    WHEN new.status = 'active' AND new.consent_status = 'confirmed'
    BEGIN
        INSERT INTO memory_fts(memory_id, profile_id, canonical_text)
        VALUES (new.id, new.profile_id, new.canonical_text);
    END
    """,
    """
    CREATE TRIGGER memory_item_fts_delete
    AFTER DELETE ON memory_item
    BEGIN
        DELETE FROM memory_fts WHERE memory_id = old.id;
    END
    """,
    """
    CREATE TRIGGER memory_item_fts_update
    AFTER UPDATE OF id, profile_id, canonical_text, status, consent_status
    ON memory_item
    BEGIN
        DELETE FROM memory_fts WHERE memory_id = old.id;
        INSERT INTO memory_fts(memory_id, profile_id, canonical_text)
        SELECT new.id, new.profile_id, new.canonical_text
        WHERE new.status = 'active' AND new.consent_status = 'confirmed';
    END
    """,
    """
    INSERT INTO memory_fts(memory_id, profile_id, canonical_text)
    SELECT id, profile_id, canonical_text
    FROM memory_item
    WHERE status = 'active' AND consent_status = 'confirmed'
    """,
)

_MIGRATION_3_STATEMENTS = (
    f"""
    CREATE TABLE memory_embedding (
        memory_id TEXT NOT NULL
            REFERENCES memory_item(id) ON DELETE CASCADE,
        model_id TEXT NOT NULL
            CHECK(length(model_id) BETWEEN 1 AND {_EMBEDDING_LABEL_MAX_LENGTH}),
        model_revision TEXT NOT NULL
            CHECK(length(model_revision) BETWEEN 1 AND {_EMBEDDING_LABEL_MAX_LENGTH}),
        dimension INTEGER NOT NULL
            CHECK(typeof(dimension) = 'integer' AND dimension = {EMBEDDING_DIMENSION}),
        normalized INTEGER NOT NULL
            CHECK(typeof(normalized) = 'integer' AND normalized = 1),
        content_sha256 TEXT NOT NULL
            CHECK(
                length(content_sha256) = 64
                AND content_sha256 = lower(content_sha256)
                AND content_sha256 NOT GLOB '*[^0-9a-f]*'
            ),
        vector_f32 BLOB NOT NULL
            CHECK(
                typeof(vector_f32) = 'blob'
                AND length(vector_f32) = {_EMBEDDING_VECTOR_BYTES}
            ),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (memory_id, model_id, model_revision)
    )
    """,
    """
    CREATE TRIGGER memory_item_embedding_invalidate
    AFTER UPDATE OF id, profile_id, canonical_text, status, consent_status
    ON memory_item
    BEGIN
        DELETE FROM memory_embedding
        WHERE memory_id = old.id OR memory_id = new.id;
    END
    """,
)

_MIGRATIONS = {
    1: _MIGRATION_1_STATEMENTS,
    2: _MIGRATION_2_STATEMENTS,
    3: _MIGRATION_3_STATEMENTS,
}


class MemoryStoreError(RuntimeError):
    """Base error for memory storage and lifecycle operations."""


class MemoryValidationError(MemoryStoreError):
    """Raised before storage when memory input is invalid."""


class MemoryNotFoundError(MemoryStoreError):
    """Raised when an active memory is absent from the current profile."""


class MemoryConflictError(MemoryStoreError):
    """Raised when a requested memory transition is not valid."""


@dataclass(frozen=True)
class MemoryItem:
    id: str
    profile_id: str
    kind: str
    canonical_text: str
    source_turn_id: Optional[str]
    event_time: Optional[str]
    sensitivity: str
    consent_status: str
    confidence: float
    importance: int
    status: str
    supersedes_id: Optional[str]
    valid_from: str
    valid_until: Optional[str]
    retention_until: Optional[str]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class KeywordMatch:
    """One FTS5 result; lower BM25 rank values are more relevant."""

    memory: MemoryItem
    rank: float


@dataclass(frozen=True)
class SemanticMatch:
    """One exact cosine-similarity result over a verified memory vector."""

    memory: MemoryItem
    score: float


@dataclass(frozen=True)
class EmbeddingIndexStatus:
    """Completeness counts for the current profile and embedding model."""

    eligible: int
    indexed: int
    missing: int
    invalid: int

    @property
    def complete(self) -> bool:
        return (
            self.indexed == self.eligible
            and self.missing == 0
            and self.invalid == 0
        )


@dataclass(frozen=True)
class _EmbeddingIdentity:
    model_id: str
    model_revision: str


@dataclass(frozen=True)
class _PreparedEmbedding:
    memory_id: str
    content_sha256: str
    vector_f32: bytes


@dataclass(frozen=True)
class _EmbeddingSource:
    memory_id: str
    canonical_text: str
    content_sha256: str


@dataclass(frozen=True)
class _EmbeddingRows:
    items: tuple[MemoryItem, ...]
    vectors: tuple[np.ndarray, ...]
    status: EmbeddingIndexStatus


class MemoryStore:
    """Persist explicitly supplied personal memories for one logical profile."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        profile_id: str,
        clock: Optional[Callable[[], datetime]] = None,
        memory_id_factory: Optional[Callable[[], str]] = None,
        embedder: Optional[EmbeddingProvider] = None,
        retention_days: Optional[int] = None,
    ) -> None:
        self._path = _database_path(database_path)
        self._profile_id = _profile_id(profile_id)
        self._clock = clock if clock is not None else _utc_now
        self._memory_id_factory = (
            memory_id_factory if memory_id_factory is not None else _new_memory_id
        )
        self._embedder = embedder
        self._retention_days = _retention_days(retention_days)

    @property
    def database_path(self) -> Path:
        return self._path

    @property
    def profile_id(self) -> str:
        return self._profile_id

    @property
    def retention_days(self) -> Optional[int]:
        return self._retention_days

    def remember(
        self,
        canonical_text: str,
        *,
        kind: str,
        sensitivity: str = "normal",
        importance: int = 3,
        source_turn_id: Optional[str] = None,
        event_time: Optional[str] = None,
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
        retention_until: Optional[str] = None,
    ) -> MemoryItem:
        """Store one explicitly confirmed canonical memory."""

        text = _canonical_text(canonical_text)
        normalized_kind = _choice(kind, "kind", MEMORY_KINDS)
        normalized_sensitivity = _choice(
            sensitivity, "sensitivity", MEMORY_SENSITIVITIES
        )
        normalized_importance = _importance(importance)
        normalized_source = _optional_short_text(source_turn_id, "source_turn_id")
        normalized_event = _optional_timestamp(event_time, "event_time")
        clock_now = self._clock()
        now = _timestamp(clock_now, "clock")
        normalized_valid_from = (
            _timestamp_text(valid_from, "valid_from")
            if valid_from is not None
            else now
        )
        normalized_valid_until = _optional_timestamp(valid_until, "valid_until")
        normalized_retention = _optional_timestamp(
            retention_until, "retention_until"
        )
        if self._retention_days is not None:
            try:
                policy_retention = _timestamp(
                    clock_now + timedelta(days=self._retention_days),
                    "retention policy",
                )
            except OverflowError as exc:
                raise MemoryValidationError(
                    "retention policy produced an invalid deadline"
                ) from exc
            if normalized_retention is None:
                normalized_retention = policy_retention
            elif normalized_retention > policy_retention:
                raise MemoryValidationError(
                    "retention_until cannot exceed the configured retention policy"
                )
        _validate_time_range(
            normalized_valid_from,
            normalized_valid_until,
            normalized_retention,
        )

        memory_id = _memory_id(self._memory_id_factory())
        item = MemoryItem(
            id=memory_id,
            profile_id=self._profile_id,
            kind=normalized_kind,
            canonical_text=text,
            source_turn_id=normalized_source,
            event_time=normalized_event,
            sensitivity=normalized_sensitivity,
            consent_status="confirmed",
            confidence=1.0,
            importance=normalized_importance,
            status="active",
            supersedes_id=None,
            valid_from=normalized_valid_from,
            valid_until=normalized_valid_until,
            retention_until=normalized_retention,
            created_at=now,
            updated_at=now,
        )
        prepared_embedding = (
            self._prepare_passage_embeddings(((item.id, item.canonical_text),))
            if self._embedder is not None
            else None
        )

        with self._connection() as connection:
            with _write_transaction(connection):
                self._insert_item(connection, item)
                if prepared_embedding is not None:
                    identity, embeddings = prepared_embedding
                    self._insert_embeddings(
                        connection, identity, embeddings, timestamp=now
                    )
                self._insert_audit(
                    connection,
                    memory_id=item.id,
                    related_memory_id=None,
                    operation="remember",
                    occurred_at=now,
                )
        return item

    def list_memories(
        self, *, include_inactive: bool = False
    ) -> tuple[MemoryItem, ...]:
        """List current-profile memories in deterministic newest-first order."""

        if not isinstance(include_inactive, bool):
            raise MemoryValidationError("include_inactive must be true or false")
        where = "profile_id = ?"
        parameters: tuple[object, ...] = (self._profile_id,)
        if not include_inactive:
            where += " AND status = 'active'"

        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT {_MEMORY_COLUMNS}
                FROM memory_item
                WHERE {where}
                ORDER BY created_at DESC, id DESC
                """,
                parameters,
            ).fetchall()
        return tuple(_row_to_item(row) for row in rows)

    def purge_expired(self) -> tuple[str, ...]:
        """Hard-delete current-profile records past their retention deadline."""

        clock_now = self._clock()
        reference_time = _timestamp(clock_now, "clock")
        policy_boundary: Optional[str] = None
        if self._retention_days is not None:
            try:
                policy_boundary = _timestamp(
                    clock_now - timedelta(days=self._retention_days),
                    "retention policy",
                )
            except OverflowError as exc:
                raise MemoryValidationError(
                    "retention policy produced an invalid boundary"
                ) from exc

        with self._connection() as connection:
            with _write_transaction(connection):
                if policy_boundary is None:
                    rows = connection.execute(
                        """
                        SELECT id FROM memory_item
                        WHERE profile_id = ?
                          AND retention_until IS NOT NULL
                          AND retention_until <= ?
                        ORDER BY id ASC
                        """,
                        (self._profile_id, reference_time),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        """
                        SELECT id FROM memory_item
                        WHERE profile_id = ?
                          AND (
                              (retention_until IS NOT NULL
                               AND retention_until <= ?)
                              OR created_at <= ?
                          )
                        ORDER BY id ASC
                        """,
                        (self._profile_id, reference_time, policy_boundary),
                    ).fetchall()
                identifiers = tuple(row["id"] for row in rows)
                for memory_id in identifiers:
                    deleted = connection.execute(
                        "DELETE FROM memory_item WHERE id = ? AND profile_id = ?",
                        (memory_id, self._profile_id),
                    ).rowcount
                    if deleted != 1:
                        raise MemoryConflictError(
                            "memory changed during expiry cleanup"
                        )
        return identifiers

    def search_keywords(
        self,
        query: str,
        *,
        limit: int = 5,
        as_of: Optional[str] = None,
    ) -> tuple[KeywordMatch, ...]:
        """Find active, consented, unexpired memories using literal terms."""

        expression = _keyword_expression(query)
        normalized_limit = _search_limit(limit)
        reference_time = (
            _timestamp_text(as_of, "as_of")
            if as_of is not None
            else _timestamp(self._clock(), "clock")
        )

        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT {_SEARCH_MEMORY_COLUMNS}, bm25(memory_fts) AS fts_rank
                FROM memory_fts
                JOIN memory_item AS item
                  ON item.id = memory_fts.memory_id
                 AND item.profile_id = memory_fts.profile_id
                WHERE memory_fts MATCH ?
                  AND item.profile_id = ?
                  AND item.status = 'active'
                  AND item.consent_status = 'confirmed'
                  AND item.valid_from <= ?
                  AND (item.valid_until IS NULL OR item.valid_until > ?)
                  AND (
                      item.retention_until IS NULL
                      OR item.retention_until > ?
                  )
                ORDER BY fts_rank ASC, item.created_at DESC, item.id ASC
                LIMIT ?
                """,
                (
                    expression,
                    self._profile_id,
                    reference_time,
                    reference_time,
                    reference_time,
                    normalized_limit,
                ),
            ).fetchall()
        return tuple(
            KeywordMatch(memory=_row_to_item(row), rank=float(row["fts_rank"]))
            for row in rows
        )

    def rebuild_keyword_index(self) -> None:
        """Rebuild the derived FTS5 index from authoritative memory rows."""

        with self._connection() as connection:
            with _write_transaction(connection):
                connection.execute("DELETE FROM memory_fts")
                connection.execute(
                    """
                    INSERT INTO memory_fts(memory_id, profile_id, canonical_text)
                    SELECT id, profile_id, canonical_text
                    FROM memory_item
                    WHERE status = 'active' AND consent_status = 'confirmed'
                    """
                )

    def embedding_index_status(self) -> EmbeddingIndexStatus:
        """Report semantic-index completeness for currently retrievable memories."""

        _, identity = self._embedder_and_identity()
        reference_time = _timestamp(self._clock(), "clock")
        with self._connection() as connection:
            return self._embedding_rows(
                connection, identity, reference_time=reference_time
            ).status

    def rebuild_embeddings(self) -> EmbeddingIndexStatus:
        """Atomically rebuild this profile's vectors for the configured model."""

        _, identity = self._embedder_and_identity()
        with self._connection() as connection:
            snapshot = self._embedding_source_snapshot(connection)

        prepared = self._prepare_passage_embeddings(
            tuple((item.memory_id, item.canonical_text) for item in snapshot)
        )
        prepared_identity, embeddings = prepared
        if prepared_identity != identity:
            raise MemoryStoreError("embedding provider identity changed during rebuild")
        timestamp = _timestamp(self._clock(), "clock")

        with self._connection() as connection:
            with _write_transaction(connection):
                authoritative = self._embedding_source_snapshot(connection)
                if authoritative != snapshot:
                    raise MemoryConflictError(
                        "memories changed during embedding rebuild; "
                        "no index was changed"
                    )
                connection.execute(
                    """
                    DELETE FROM memory_embedding
                    WHERE memory_id IN (
                        SELECT id FROM memory_item WHERE profile_id = ?
                    )
                    """,
                    (self._profile_id,),
                )
                self._insert_embeddings(
                    connection, identity, embeddings, timestamp=timestamp
                )

        return self.embedding_index_status()

    def search_semantic(
        self, query: str, *, limit: int = 5
    ) -> tuple[SemanticMatch, ...]:
        """Search current verified memories by exact cosine similarity."""

        normalized_query = _semantic_query(query)
        normalized_limit = _search_limit(limit)
        if self._retention_days is not None:
            self.purge_expired()
        embedder, identity = self._embedder_and_identity()
        reference_time = _timestamp(self._clock(), "clock")

        with self._connection() as connection:
            rows = self._embedding_rows(
                connection, identity, reference_time=reference_time
            )
        if not rows.status.complete:
            raise MemoryStoreError(
                "semantic memory index is incomplete or invalid; "
                "run 'oline-hri memory rebuild-embeddings' before searching"
            )
        if not rows.items:
            return ()

        query_vector = _embed_query(
            embedder, normalized_query, expected_identity=identity
        )

        # Query inference can be slow enough for a correction, forget, or expiry
        # to occur. Reload after inference, then hold a short read transaction
        # through scoring so returned records are valid at one final snapshot.
        reference_time = _timestamp(self._clock(), "clock")
        with self._connection() as connection:
            with _read_transaction(connection):
                rows = self._embedding_rows(
                    connection, identity, reference_time=reference_time
                )
                if not rows.status.complete:
                    raise MemoryStoreError(
                        "semantic memory index is incomplete or invalid; "
                        "run 'oline-hri memory rebuild-embeddings' before searching"
                    )
                if not rows.items:
                    return ()

                matrix = np.ascontiguousarray(
                    np.stack(rows.vectors), dtype=np.float32
                )
                if matrix.shape != (len(rows.items), EMBEDDING_DIMENSION):
                    raise MemoryStoreError("semantic memory index matrix is invalid")
                scores = matrix @ query_vector
                if scores.shape != (len(rows.items),) or not np.all(
                    np.isfinite(scores)
                ):
                    raise MemoryStoreError(
                        "semantic similarity calculation failed"
                    )

                ordered = sorted(
                    range(len(rows.items)),
                    key=lambda index: (
                        -float(scores[index]),
                        rows.items[index].id,
                    ),
                )
                return tuple(
                    SemanticMatch(
                        memory=rows.items[index], score=float(scores[index])
                    )
                    for index in ordered[:normalized_limit]
                )

    def retrieval_snapshot_is_current(
        self, items: Sequence[MemoryItem]
    ) -> bool:
        """Return whether retrieved records remain eligible and unchanged."""

        snapshot = self._snapshot_items(items)
        if not snapshot:
            return True
        if any(item.profile_id != self._profile_id for item in snapshot):
            return False
        with self._connection() as connection:
            with _read_transaction(connection):
                return self._snapshot_is_current(connection, snapshot)

    @contextmanager
    def disclosure_guard(self, items: Sequence[MemoryItem]) -> Iterator[None]:
        """Authorize a short output write while excluding concurrent mutations.

        Generate and review the response before entering this context. The
        immediate transaction serializes correction, forgetting and pruning
        against disclosure. Expiry is checked after acquiring the lock; time
        itself cannot be locked, so callers must yield only for the final short
        write, never inference, diagnostics or an interactive operation.
        """
        snapshot = self._snapshot_items(items)
        if not snapshot:
            yield
            return
        if any(item.profile_id != self._profile_id for item in snapshot):
            raise MemoryStoreError("personal-memory disclosure is no longer authorized")
        with self._connection() as connection:
            with _write_transaction(connection):
                if not self._snapshot_is_current(connection, snapshot):
                    raise MemoryStoreError("personal-memory disclosure is no longer authorized")
                yield

    @staticmethod
    def _snapshot_items(items: Sequence[MemoryItem]) -> tuple[MemoryItem, ...]:
        """Validate one bounded snapshot without opening a database."""
        if isinstance(items, (str, bytes)) or not isinstance(items, Sequence):
            raise MemoryValidationError(
                "retrieval snapshot must be a sequence of memory items"
            )
        snapshot = tuple(items)
        if len(snapshot) > 5:
            raise MemoryValidationError(
                "retrieval snapshot cannot contain more than 5 memories"
            )
        if any(not isinstance(item, MemoryItem) for item in snapshot):
            raise MemoryValidationError(
                "retrieval snapshot must contain only memory items"
            )
        identifiers = tuple(item.id for item in snapshot)
        if len(set(identifiers)) != len(identifiers):
            raise MemoryValidationError(
                "retrieval snapshot cannot contain duplicate memories"
            )
        return snapshot

    def _snapshot_is_current(
        self, connection: sqlite3.Connection, snapshot: Sequence[MemoryItem]
    ) -> bool:
        """Check exact authorized rows using the caller's established transaction."""
        if any(item.profile_id != self._profile_id for item in snapshot):
            return False
        reference_time = _timestamp(self._clock(), "clock")
        identifiers = tuple(item.id for item in snapshot)
        placeholders = ", ".join("?" for _ in identifiers)
        rows = connection.execute(
            f"""
            SELECT {_MEMORY_COLUMNS}
            FROM memory_item
            WHERE id IN ({placeholders})
              AND profile_id = ?
              AND status = 'active'
              AND consent_status = 'confirmed'
              AND valid_from <= ?
              AND (valid_until IS NULL OR valid_until > ?)
              AND (
                  retention_until IS NULL
                  OR retention_until > ?
              )
            """,
            (
                *identifiers,
                self._profile_id,
                reference_time,
                reference_time,
                reference_time,
            ),
        ).fetchall()
        current = {row["id"]: _row_to_item(row) for row in rows}
        return all(current.get(item.id) == item for item in snapshot)

    def correct(self, memory_id: str, canonical_text: str) -> MemoryItem:
        """Atomically supersede one active memory with corrected text."""

        target_id = _memory_id(memory_id)
        text = _canonical_text(canonical_text)
        now = _timestamp(self._clock(), "clock")
        replacement_id = _memory_id(self._memory_id_factory())

        with self._connection() as connection:
            previous = _row_to_item(self._active_row(connection, target_id))
        _validate_correction(previous, text, now)
        replacement_retention = previous.retention_until
        if self._retention_days is not None:
            try:
                policy_retention = _timestamp(
                    datetime.fromisoformat(
                        previous.created_at.replace("Z", "+00:00")
                    )
                    + timedelta(days=self._retention_days),
                    "retention policy",
                )
            except (OverflowError, ValueError) as exc:
                raise MemoryStoreError(
                    "stored memory has an invalid retention boundary"
                ) from exc
            if policy_retention <= now:
                raise MemoryConflictError(
                    "cannot correct a memory past its retention policy"
                )
            if (
                replacement_retention is None
                or replacement_retention > policy_retention
            ):
                replacement_retention = policy_retention

        replacement = MemoryItem(
            id=replacement_id,
            profile_id=self._profile_id,
            kind=previous.kind,
            canonical_text=text,
            source_turn_id=None,
            event_time=previous.event_time,
            sensitivity=previous.sensitivity,
            consent_status="confirmed",
            confidence=1.0,
            importance=previous.importance,
            status="active",
            supersedes_id=previous.id,
            valid_from=now,
            valid_until=previous.valid_until,
            retention_until=replacement_retention,
            created_at=now,
            updated_at=now,
        )
        prepared_embedding = (
            self._prepare_passage_embeddings(
                ((replacement.id, replacement.canonical_text),)
            )
            if self._embedder is not None
            else None
        )

        with self._connection() as connection:
            with _write_transaction(connection):
                locked_row = connection.execute(
                    f"""
                    SELECT {_MEMORY_COLUMNS}
                    FROM memory_item
                    WHERE id = ? AND profile_id = ?
                    """,
                    (target_id, self._profile_id),
                ).fetchone()
                if locked_row is None or _row_to_item(locked_row) != previous:
                    raise MemoryConflictError(
                        "memory changed during correction; no correction was saved"
                    )
                self._insert_item(connection, replacement)
                if prepared_embedding is not None:
                    identity, embeddings = prepared_embedding
                    self._insert_embeddings(
                        connection, identity, embeddings, timestamp=now
                    )
                changed = connection.execute(
                    """
                    UPDATE memory_item
                    SET status = 'superseded', valid_until = ?, updated_at = ?
                    WHERE id = ? AND profile_id = ? AND status = 'active'
                    """,
                    (now, now, previous.id, self._profile_id),
                ).rowcount
                if changed != 1:
                    raise MemoryConflictError(
                        "memory changed during correction; no correction was saved"
                    )
                self._insert_audit(
                    connection,
                    memory_id=replacement.id,
                    related_memory_id=previous.id,
                    operation="correct",
                    occurred_at=now,
                )
        return replacement

    def forget(self, memory_id: str) -> tuple[str, ...]:
        """Hard-delete an active memory and all superseded ancestors."""

        target_id = _memory_id(memory_id)
        now = _timestamp(self._clock(), "clock")

        with self._connection() as connection:
            with _write_transaction(connection):
                row = self._active_row(connection, target_id)
                revision_ids = self._revision_chain(connection, row)
                for revision_id in revision_ids:
                    self._insert_audit(
                        connection,
                        memory_id=revision_id,
                        related_memory_id=target_id,
                        operation="forget",
                        occurred_at=now,
                    )
                    deleted = connection.execute(
                        "DELETE FROM memory_item WHERE id = ? AND profile_id = ?",
                        (revision_id, self._profile_id),
                    ).rowcount
                    if deleted != 1:
                        raise MemoryConflictError(
                            "memory changed during forget; nothing was forgotten"
                        )
        return revision_ids

    def _active_row(
        self, connection: sqlite3.Connection, memory_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            f"""
            SELECT {_MEMORY_COLUMNS}
            FROM memory_item
            WHERE id = ? AND profile_id = ? AND status = 'active'
            """,
            (memory_id, self._profile_id),
        ).fetchone()
        if row is None:
            raise MemoryNotFoundError(
                f"active memory not found for this profile: {memory_id}"
            )
        return row

    def _revision_chain(
        self, connection: sqlite3.Connection, active_row: sqlite3.Row
    ) -> tuple[str, ...]:
        revision_ids = []
        seen = set()
        row: Optional[sqlite3.Row] = active_row
        while row is not None:
            revision_id = row["id"]
            if revision_id in seen:
                raise MemoryStoreError("memory correction lineage contains a cycle")
            seen.add(revision_id)
            revision_ids.append(revision_id)
            parent_id = row["supersedes_id"]
            if parent_id is None:
                break
            row = connection.execute(
                """
                SELECT id, supersedes_id
                FROM memory_item
                WHERE id = ? AND profile_id = ?
                """,
                (parent_id, self._profile_id),
            ).fetchone()
            if row is None:
                raise MemoryStoreError("memory correction lineage is incomplete")
        return tuple(revision_ids)

    def _embedding_source_snapshot(
        self, connection: sqlite3.Connection
    ) -> tuple[_EmbeddingSource, ...]:
        rows = connection.execute(
            """
            SELECT id, canonical_text
            FROM memory_item
            WHERE profile_id = ?
              AND status = 'active'
              AND consent_status = 'confirmed'
            ORDER BY id ASC
            """,
            (self._profile_id,),
        ).fetchall()
        return tuple(
            _EmbeddingSource(
                memory_id=row["id"],
                canonical_text=row["canonical_text"],
                content_sha256=_content_sha256(row["canonical_text"]),
            )
            for row in rows
        )

    def _embedding_rows(
        self,
        connection: sqlite3.Connection,
        identity: _EmbeddingIdentity,
        *,
        reference_time: str,
    ) -> _EmbeddingRows:
        rows = connection.execute(
            f"""
            SELECT {_SEARCH_MEMORY_COLUMNS},
                   embedding.memory_id AS embedding_memory_id,
                   embedding.model_id AS embedding_model_id,
                   embedding.model_revision AS embedding_model_revision,
                   embedding.dimension AS embedding_dimension,
                   embedding.normalized AS embedding_normalized,
                   embedding.content_sha256 AS embedding_content_sha256,
                   embedding.vector_f32 AS embedding_vector_f32,
                   embedding.created_at AS embedding_created_at,
                   embedding.updated_at AS embedding_updated_at
            FROM memory_item AS item
            LEFT JOIN memory_embedding AS embedding
              ON embedding.memory_id = item.id
             AND embedding.model_id = ?
             AND embedding.model_revision = ?
            WHERE item.profile_id = ?
              AND item.status = 'active'
              AND item.consent_status = 'confirmed'
              AND item.valid_from <= ?
              AND (item.valid_until IS NULL OR item.valid_until > ?)
              AND (
                  item.retention_until IS NULL
                  OR item.retention_until > ?
              )
            ORDER BY item.id ASC
            """,
            (
                identity.model_id,
                identity.model_revision,
                self._profile_id,
                reference_time,
                reference_time,
                reference_time,
            ),
        ).fetchall()

        indexed_items = []
        vectors = []
        missing = 0
        invalid = 0
        for row in rows:
            item = _row_to_item(row)
            if row["embedding_memory_id"] is None:
                missing += 1
                continue
            vector = _decode_embedding(row, item, identity)
            if vector is None:
                invalid += 1
                continue
            indexed_items.append(item)
            vectors.append(vector)

        status = EmbeddingIndexStatus(
            eligible=len(rows),
            indexed=len(indexed_items),
            missing=missing,
            invalid=invalid,
        )
        return _EmbeddingRows(
            items=tuple(indexed_items), vectors=tuple(vectors), status=status
        )

    def _embedder_and_identity(
        self,
    ) -> tuple[EmbeddingProvider, _EmbeddingIdentity]:
        if self._embedder is None:
            raise MemoryStoreError(
                "semantic memory requires a configured local embedding provider"
            )
        return self._embedder, _provider_identity(self._embedder)

    def _prepare_passage_embeddings(
        self, entries: Sequence[tuple[str, str]]
    ) -> tuple[_EmbeddingIdentity, tuple[_PreparedEmbedding, ...]]:
        embedder, identity = self._embedder_and_identity()
        if not entries:
            return identity, ()
        texts = tuple(text for _, text in entries)
        try:
            output = embedder.embed_passages(texts)
        except Exception as exc:
            raise MemoryStoreError("personal-memory embedding failed") from exc
        matrix = _normalized_passage_matrix(output, expected_rows=len(entries))
        if _provider_identity(embedder) != identity:
            raise MemoryStoreError(
                "embedding provider identity changed during inference"
            )
        prepared = tuple(
            _PreparedEmbedding(
                memory_id=memory_id,
                content_sha256=_content_sha256(text),
                vector_f32=_vector_bytes(matrix[index]),
            )
            for index, (memory_id, text) in enumerate(entries)
        )
        return identity, prepared

    def _insert_embeddings(
        self,
        connection: sqlite3.Connection,
        identity: _EmbeddingIdentity,
        embeddings: Sequence[_PreparedEmbedding],
        *,
        timestamp: str,
    ) -> None:
        for embedding in embeddings:
            connection.execute(
                """
                INSERT INTO memory_embedding (
                    memory_id, model_id, model_revision, dimension,
                    normalized, content_sha256, vector_f32, created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                """,
                (
                    embedding.memory_id,
                    identity.model_id,
                    identity.model_revision,
                    EMBEDDING_DIMENSION,
                    embedding.content_sha256,
                    sqlite3.Binary(embedding.vector_f32),
                    timestamp,
                    timestamp,
                ),
            )

    def _insert_item(
        self, connection: sqlite3.Connection, item: MemoryItem
    ) -> None:
        connection.execute(
            """
            INSERT INTO memory_item (
                id, profile_id, kind, canonical_text, source_turn_id,
                event_time, sensitivity, consent_status, confidence,
                importance, status, supersedes_id, valid_from, valid_until,
                retention_until, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.id,
                item.profile_id,
                item.kind,
                item.canonical_text,
                item.source_turn_id,
                item.event_time,
                item.sensitivity,
                item.consent_status,
                item.confidence,
                item.importance,
                item.status,
                item.supersedes_id,
                item.valid_from,
                item.valid_until,
                item.retention_until,
                item.created_at,
                item.updated_at,
            ),
        )

    def _insert_audit(
        self,
        connection: sqlite3.Connection,
        *,
        memory_id: str,
        related_memory_id: Optional[str],
        operation: str,
        occurred_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO memory_audit (
                event_id, memory_id, related_memory_id, profile_id,
                operation, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"audit_{uuid4().hex}",
                memory_id,
                related_memory_id,
                self._profile_id,
                operation,
                occurred_at,
            ),
        )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        parent_existed = self._path.parent.exists()
        connection: Optional[sqlite3.Connection] = None
        try:
            self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if os.name == "posix" and not parent_existed:
                os.chmod(self._path.parent, 0o700)
            connection = sqlite3.connect(
                str(self._path), timeout=5.0, isolation_level=None
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA secure_delete = ON")
            if os.name == "posix":
                os.chmod(self._path, 0o600)
            _initialize_schema(connection)
            yield connection
        except MemoryStoreError:
            raise
        except (OSError, sqlite3.Error) as exc:
            if "no such module: fts5" in str(exc).lower():
                raise MemoryStoreError(
                    "SQLite FTS5 support is required for personal-memory search"
                ) from exc
            raise MemoryStoreError("personal-memory database operation failed") from exc
        finally:
            if connection is not None:
                connection.close()


@contextmanager
def _write_transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()


@contextmanager
def _read_transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN")
    try:
        yield
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()


def _initialize_schema(connection: sqlite3.Connection) -> None:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise MemoryStoreError(
            f"memory database schema {version} is newer than supported schema "
            f"{SCHEMA_VERSION}"
        )
    if version < SCHEMA_VERSION:
        with _write_transaction(connection):
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise MemoryStoreError(
                    f"memory database schema {version} is newer than supported "
                    f"schema {SCHEMA_VERSION}"
                )
            if version == 0:
                existing_tables = {
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT name FROM sqlite_master
                        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                        """
                    )
                }
                if existing_tables:
                    raise MemoryStoreError(
                        "memory database has an unversioned schema"
                    )
            while version < SCHEMA_VERSION:
                next_version = version + 1
                statements = _MIGRATIONS.get(next_version)
                if statements is None:
                    raise MemoryStoreError(
                        f"memory database schema {version} requires an "
                        "unavailable migration"
                    )
                for statement in statements:
                    connection.execute(statement)
                connection.execute(f"PRAGMA user_version = {next_version}")
                version = next_version

    expected = {
        "memory_item",
        "memory_audit",
        "memory_fts",
        "memory_embedding",
    }
    actual = {
        row[0]
        for row in connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table'
              AND name IN (
                  'memory_item', 'memory_audit', 'memory_fts',
                  'memory_embedding'
              )
            """
        )
    }
    if actual != expected:
        raise MemoryStoreError("memory database schema is incomplete")

    fts_sql_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'memory_fts'"
    ).fetchone()
    if (
        fts_sql_row is None
        or not isinstance(fts_sql_row[0], str)
        or "using fts5" not in fts_sql_row[0].lower()
    ):
        raise MemoryStoreError("memory keyword index schema is invalid")

    expected_triggers = {
        "memory_item_fts_insert",
        "memory_item_fts_delete",
        "memory_item_fts_update",
    }
    actual_triggers = {
        row[0]
        for row in connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'trigger' AND name LIKE 'memory_item_fts_%'
            """
        )
    }
    if actual_triggers != expected_triggers:
        raise MemoryStoreError("memory keyword index triggers are incomplete")

    embedding_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(memory_embedding)")
    }
    if embedding_columns != {
        "memory_id",
        "model_id",
        "model_revision",
        "dimension",
        "normalized",
        "content_sha256",
        "vector_f32",
        "created_at",
        "updated_at",
    }:
        raise MemoryStoreError("memory embedding index schema is invalid")
    foreign_keys = connection.execute(
        "PRAGMA foreign_key_list(memory_embedding)"
    ).fetchall()
    if not any(
        row[2] == "memory_item"
        and row[3] == "memory_id"
        and row[4] == "id"
        and str(row[6]).upper() == "CASCADE"
        for row in foreign_keys
    ):
        raise MemoryStoreError("memory embedding cascade is missing")
    embedding_triggers = {
        row[0]
        for row in connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'trigger'
              AND name = 'memory_item_embedding_invalidate'
            """
        )
    }
    if embedding_triggers != {"memory_item_embedding_invalidate"}:
        raise MemoryStoreError("memory embedding invalidation trigger is missing")


def _row_to_item(row: sqlite3.Row) -> MemoryItem:
    values = {
        field: row[field] for field in MemoryItem.__dataclass_fields__
    }
    return MemoryItem(**values)


def _provider_identity(provider: EmbeddingProvider) -> _EmbeddingIdentity:
    try:
        model_id = provider.model_id
        model_revision = provider.model_revision
        dimension = provider.dimension
    except Exception as exc:
        raise MemoryStoreError("embedding provider metadata is unavailable") from exc
    validated_model_id = _embedding_label(model_id, "model_id")
    validated_revision = _embedding_label(model_revision, "model_revision")
    if (
        isinstance(dimension, bool)
        or not isinstance(dimension, int)
        or dimension != EMBEDDING_DIMENSION
    ):
        raise MemoryStoreError(
            f"embedding provider dimension must be {EMBEDDING_DIMENSION}"
        )
    return _EmbeddingIdentity(validated_model_id, validated_revision)


def _embedding_label(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > _EMBEDDING_LABEL_MAX_LENGTH
        or any(unicodedata.category(character) == "Cc" for character in value)
    ):
        raise MemoryStoreError(f"embedding provider {field} is invalid")
    return value


def _normalized_passage_matrix(
    output: object, *, expected_rows: int
) -> np.ndarray:
    try:
        matrix = np.asarray(output, dtype=np.float32)
    except (TypeError, ValueError, OverflowError) as exc:
        raise MemoryStoreError(
            "embedding provider returned malformed passages"
        ) from exc
    if matrix.shape != (expected_rows, EMBEDDING_DIMENSION):
        raise MemoryStoreError(
            "embedding provider returned an unexpected passage shape"
        )
    return _normalize_matrix(matrix, field="passage")


def _embed_query(
    provider: EmbeddingProvider,
    query: str,
    *,
    expected_identity: _EmbeddingIdentity,
) -> np.ndarray:
    if _provider_identity(provider) != expected_identity:
        raise MemoryStoreError("embedding provider identity changed before query")
    try:
        output = provider.embed_query(query)
    except Exception as exc:
        raise MemoryStoreError("personal-memory query embedding failed") from exc
    try:
        vector = np.asarray(output, dtype=np.float32)
    except (TypeError, ValueError, OverflowError) as exc:
        raise MemoryStoreError("embedding provider returned a malformed query") from exc
    if vector.shape != (EMBEDDING_DIMENSION,):
        raise MemoryStoreError("embedding provider returned an unexpected query shape")
    normalized = _normalize_matrix(vector.reshape(1, -1), field="query")[0]
    if _provider_identity(provider) != expected_identity:
        raise MemoryStoreError("embedding provider identity changed during query")
    return np.ascontiguousarray(normalized, dtype=np.float32)


def _normalize_matrix(matrix: np.ndarray, *, field: str) -> np.ndarray:
    if not np.all(np.isfinite(matrix)):
        raise MemoryStoreError(f"embedding provider returned non-finite {field} values")
    precise = np.asarray(matrix, dtype=np.float64)
    norms = np.linalg.norm(precise, axis=1)
    if not np.all(np.isfinite(norms)) or np.any(norms <= 0.0):
        raise MemoryStoreError(f"embedding provider returned a zero-length {field}")
    normalized = np.ascontiguousarray(
        precise / norms[:, np.newaxis], dtype=np.float32
    )
    normalized_norms = np.linalg.norm(
        np.asarray(normalized, dtype=np.float64), axis=1
    )
    if (
        not np.all(np.isfinite(normalized_norms))
        or not np.allclose(normalized_norms, 1.0, rtol=1e-5, atol=1e-6)
    ):
        raise MemoryStoreError(f"embedding {field} normalization failed")
    return normalized


def _vector_bytes(vector: np.ndarray) -> bytes:
    raw = np.ascontiguousarray(vector, dtype="<f4").tobytes(order="C")
    if len(raw) != _EMBEDDING_VECTOR_BYTES:
        raise MemoryStoreError("embedding vector has an invalid byte length")
    return raw


def _content_sha256(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _decode_embedding(
    row: sqlite3.Row,
    item: MemoryItem,
    identity: _EmbeddingIdentity,
) -> Optional[np.ndarray]:
    try:
        content_hash = row["embedding_content_sha256"]
        vector_blob = row["embedding_vector_f32"]
        if (
            row["embedding_memory_id"] != item.id
            or row["embedding_model_id"] != identity.model_id
            or row["embedding_model_revision"] != identity.model_revision
            or row["embedding_dimension"] != EMBEDDING_DIMENSION
            or row["embedding_normalized"] != 1
            or not isinstance(content_hash, str)
            or _CONTENT_SHA256_PATTERN.fullmatch(content_hash) is None
            or content_hash != _content_sha256(item.canonical_text)
            or not isinstance(vector_blob, (bytes, bytearray, memoryview))
            or len(vector_blob) != _EMBEDDING_VECTOR_BYTES
        ):
            return None
        created_at = _timestamp_text(row["embedding_created_at"], "created_at")
        updated_at = _timestamp_text(row["embedding_updated_at"], "updated_at")
        if updated_at < created_at:
            return None
        vector = np.frombuffer(bytes(vector_blob), dtype="<f4")
        if vector.shape != (EMBEDDING_DIMENSION,) or not np.all(np.isfinite(vector)):
            return None
        norm = float(np.linalg.norm(np.asarray(vector, dtype=np.float64)))
        if not np.isfinite(norm) or not np.isclose(
            norm, 1.0, rtol=1e-5, atol=1e-6
        ):
            return None
        return np.ascontiguousarray(vector, dtype=np.float32)
    except (MemoryStoreError, TypeError, ValueError, OverflowError):
        return None


def _validate_correction(previous: MemoryItem, text: str, now: str) -> None:
    if text == previous.canonical_text:
        raise MemoryConflictError("corrected text must differ from the active memory")
    if previous.valid_from > now:
        raise MemoryConflictError("cannot correct a memory before its validity time")
    if previous.valid_until is not None and previous.valid_until <= now:
        raise MemoryConflictError("cannot correct an expired memory")
    if previous.retention_until is not None and previous.retention_until <= now:
        raise MemoryConflictError("cannot correct a memory past its retention time")


def _database_path(value: str | Path) -> Path:
    raw = str(value)
    if not raw.strip() or "\x00" in raw:
        raise MemoryValidationError("database path must be a non-empty path")
    try:
        path = Path(raw).expanduser()
    except RuntimeError as exc:
        raise MemoryValidationError("database path cannot be expanded") from exc
    if not path.is_absolute() or not path.name:
        raise MemoryValidationError("database path must resolve to an absolute file")
    return path


def _profile_id(value: str) -> str:
    if not isinstance(value, str) or _PROFILE_PATTERN.fullmatch(value) is None:
        raise MemoryValidationError(
            "profile_id must be 1-64 letters, numbers, dots, underscores, or hyphens"
        )
    return value


def _retention_days(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise MemoryValidationError("retention_days must be an integer or null")
    if not 1 <= value <= MAX_RETENTION_DAYS:
        raise MemoryValidationError(
            f"retention_days must be between 1 and {MAX_RETENTION_DAYS}"
        )
    return value


def _memory_id(value: str) -> str:
    if not isinstance(value, str) or _MEMORY_ID_PATTERN.fullmatch(value) is None:
        raise MemoryValidationError("memory ID has an invalid format")
    return value


def _canonical_text(value: str) -> str:
    if not isinstance(value, str):
        raise MemoryValidationError("memory text must be a string")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized:
        raise MemoryValidationError("memory text cannot be empty")
    if len(normalized) > MAX_MEMORY_TEXT_LENGTH:
        raise MemoryValidationError(
            f"memory text cannot exceed {MAX_MEMORY_TEXT_LENGTH} characters"
        )
    if any(unicodedata.category(character) == "Cc" for character in normalized):
        raise MemoryValidationError("memory text cannot contain control characters")
    if is_question_shaped_memory(normalized):
        raise MemoryValidationError(
            "memory text must state a fact or preference, not ask a question"
        )
    return normalized


def is_question_shaped_memory(value: str) -> bool:
    """Return whether text looks like a query rather than memory evidence."""

    if not isinstance(value, str):
        return False
    normalized = unicodedata.normalize("NFKC", value).strip()
    return normalized.endswith(("?", "？")) or (
        _QUESTION_SHAPED_MEMORY_PATTERN.search(normalized) is not None
    )


def _keyword_expression(value: str) -> str:
    if not isinstance(value, str):
        raise MemoryValidationError("search query must be a string")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized:
        raise MemoryValidationError("search query cannot be empty")
    if len(normalized) > MAX_SEARCH_QUERY_LENGTH:
        raise MemoryValidationError(
            f"search query cannot exceed {MAX_SEARCH_QUERY_LENGTH} characters"
        )
    if any(unicodedata.category(character) == "Cc" for character in normalized):
        raise MemoryValidationError("search query cannot contain control characters")

    terms = re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
    unique_terms = []
    seen = set()
    for term in terms:
        key = term.casefold()
        if key not in seen:
            seen.add(key)
            unique_terms.append(term)
    if not unique_terms:
        raise MemoryValidationError("search query must contain a letter or number")
    if len(unique_terms) > MAX_SEARCH_TERMS:
        raise MemoryValidationError(
            f"search query cannot exceed {MAX_SEARCH_TERMS} unique terms"
        )
    return " AND ".join(f'"{term}"' for term in unique_terms)


def _semantic_query(value: str) -> str:
    if not isinstance(value, str):
        raise MemoryValidationError("search query must be a string")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized:
        raise MemoryValidationError("search query cannot be empty")
    if len(normalized) > MAX_SEMANTIC_QUERY_LENGTH:
        raise MemoryValidationError(
            "semantic search query cannot exceed "
            f"{MAX_SEMANTIC_QUERY_LENGTH} characters"
        )
    if any(unicodedata.category(character) == "Cc" for character in normalized):
        raise MemoryValidationError("search query cannot contain control characters")
    return normalized


def _search_limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
        raise MemoryValidationError("search limit must be an integer from 1 to 100")
    return value


def _choice(value: str, field: str, choices: tuple[str, ...]) -> str:
    if not isinstance(value, str):
        raise MemoryValidationError(f"{field} must be a string")
    normalized = value.strip().lower()
    if normalized not in choices:
        raise MemoryValidationError(
            f"{field} must be one of: {', '.join(choices)}"
        )
    return normalized


def _importance(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise MemoryValidationError("importance must be an integer from 1 to 5")
    return value


def _optional_short_text(value: Optional[str], field: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 128:
        raise MemoryValidationError(f"{field} must be 1-128 characters")
    normalized = value.strip()
    if any(unicodedata.category(character) == "Cc" for character in normalized):
        raise MemoryValidationError(f"{field} cannot contain control characters")
    return normalized


def _optional_timestamp(value: Optional[str], field: str) -> Optional[str]:
    return None if value is None else _timestamp_text(value, field)


def _timestamp_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MemoryValidationError(f"{field} must be an ISO-8601 timestamp")
    raw = value.strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise MemoryValidationError(
            f"{field} must be a valid ISO-8601 timestamp"
        ) from exc
    return _timestamp(parsed, field)


def _timestamp(value: datetime, field: str) -> str:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise MemoryValidationError(f"{field} timestamp must include a timezone")
    try:
        utc_value = value.astimezone(timezone.utc)
    except (OverflowError, ValueError) as exc:
        raise MemoryValidationError(
            f"{field} timestamp is outside the valid range"
        ) from exc
    return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _validate_time_range(
    valid_from: str,
    valid_until: Optional[str],
    retention_until: Optional[str],
) -> None:
    if valid_until is not None and valid_until < valid_from:
        raise MemoryValidationError("valid_until cannot be before valid_from")
    if retention_until is not None and retention_until < valid_from:
        raise MemoryValidationError("retention_until cannot be before valid_from")
    if (
        valid_until is not None
        and retention_until is not None
        and retention_until < valid_until
    ):
        raise MemoryValidationError(
            "retention_until cannot be before valid_until"
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_memory_id() -> str:
    return f"mem_{uuid4().hex}"
