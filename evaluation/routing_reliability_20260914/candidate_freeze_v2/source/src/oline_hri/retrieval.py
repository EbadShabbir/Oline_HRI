"""Deterministic hybrid retrieval over verified personal-memory indexes."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from math import isfinite
from numbers import Real
from typing import ContextManager, Iterator, Optional, Protocol, Sequence

from .memory import (
    KeywordMatch,
    MemoryItem,
    MemoryStoreError,
    MemoryValidationError,
    SemanticMatch,
)
from .memory_evidence import evidence_order


RRF_K = 60
CANDIDATE_POOL_SIZE = 20
DEFAULT_RETRIEVAL_LIMIT = 3
MAX_RETRIEVAL_LIMIT = 5


class RetrievalError(MemoryStoreError):
    """Raised when retrieval sources return inconsistent or malformed data."""


class MemorySearchBackend(Protocol):
    """Memory operations required by the standalone hybrid retriever."""

    def search_semantic(
        self, query: str, *, limit: int = 5
    ) -> Sequence[SemanticMatch]:
        """Return semantic results ordered from best to worst."""

    def search_keywords(
        self, query: str, *, limit: int = 5
    ) -> Sequence[KeywordMatch]:
        """Return keyword results ordered from best to worst."""

    def retrieval_snapshot_is_current(
        self, items: Sequence[MemoryItem]
    ) -> bool:
        """Return whether all items are still current and retrievable."""

    def disclosure_guard(self, items: Sequence[MemoryItem]) -> ContextManager[None]:
        """Authorize a short disclosure while excluding record mutations."""


@dataclass(frozen=True)
class HybridMatch:
    """One fused result with per-source diagnostics preserved."""

    memory: MemoryItem
    fused_score: float
    keyword_rank: Optional[float]
    keyword_position: Optional[int]
    semantic_score: Optional[float]
    semantic_position: Optional[int]

    @property
    def sources(self) -> tuple[str, ...]:
        """Names of the indexes that returned this memory."""

        result = []
        if self.semantic_position is not None:
            result.append("semantic")
        if self.keyword_position is not None:
            result.append("keyword")
        return tuple(result)


@dataclass
class _Candidate:
    memory: MemoryItem
    keyword_rank: Optional[float] = None
    keyword_position: Optional[int] = None
    semantic_score: Optional[float] = None
    semantic_position: Optional[int] = None

    @property
    def fused_score(self) -> float:
        score = 0.0
        if self.semantic_position is not None:
            score += 1.0 / (RRF_K + self.semantic_position)
        if self.keyword_position is not None:
            score += 1.0 / (RRF_K + self.keyword_position)
        return score


class HybridRetriever:
    """Fuse keyword and semantic ranks without mixing incomparable raw scores."""

    def __init__(self, backend: MemorySearchBackend) -> None:
        self._backend = backend

    def retrieve(
        self, query: str, *, limit: int = DEFAULT_RETRIEVAL_LIMIT
    ) -> tuple[HybridMatch, ...]:
        """Return a deterministic, deduplicated hybrid ranking."""

        normalized_limit = _retrieval_limit(limit)

        # Semantic search is deliberately first and authoritative. Its normal
        # validation and complete-index checks must succeed before a lexical
        # result can be used.
        semantic_matches = self._backend.search_semantic(
            query, limit=CANDIDATE_POOL_SIZE
        )
        semantic_matches = _source_results(
            semantic_matches, SemanticMatch, source="semantic"
        )

        try:
            keyword_matches = self._backend.search_keywords(
                query, limit=CANDIDATE_POOL_SIZE
            )
        except MemoryValidationError:
            # A natural semantic query can legitimately be unusable by the
            # stricter FTS term parser. Semantic validation already succeeded.
            keyword_matches = ()
        keyword_matches = _source_results(
            keyword_matches, KeywordMatch, source="keyword"
        )

        candidates: dict[str, _Candidate] = {}
        for position, match in enumerate(semantic_matches, start=1):
            score = _finite_number(match.score, "semantic score")
            candidate = _candidate(candidates, match.memory)
            if candidate.semantic_position is None:
                candidate.semantic_position = position
                candidate.semantic_score = score

        for position, match in enumerate(keyword_matches, start=1):
            rank = _finite_number(match.rank, "keyword rank")
            candidate = _candidate(candidates, match.memory)
            if candidate.keyword_position is None:
                candidate.keyword_position = position
                candidate.keyword_rank = rank

        ordered = sorted(
            candidates.values(),
            key=lambda candidate: (
                -candidate.fused_score,
                candidate.keyword_position is None,
                (
                    candidate.keyword_position
                    if candidate.keyword_position is not None
                    else CANDIDATE_POOL_SIZE + 1
                ),
                (
                    candidate.semantic_position
                    if candidate.semantic_position is not None
                    else CANDIDATE_POOL_SIZE + 1
                ),
                candidate.memory.id,
            ),
        )
        # Reorder only the bounded, already-validated pool. Keep original RRF
        # scores and source positions as diagnostics rather than invent scores.
        order = evidence_order(query, [c.memory.canonical_text for c in ordered])
        ordered = [ordered[index] for index in order]
        return tuple(
            HybridMatch(
                memory=candidate.memory,
                fused_score=candidate.fused_score,
                keyword_rank=candidate.keyword_rank,
                keyword_position=candidate.keyword_position,
                semantic_score=candidate.semantic_score,
                semantic_position=candidate.semantic_position,
            )
            for candidate in ordered[:normalized_limit]
        )

    def is_current(self, matches: Sequence[HybridMatch]) -> bool:
        """Delegate final lifecycle/snapshot validation to the memory backend."""

        items = _snapshot_items(matches)
        if not items:
            return True
        current = self._backend.retrieval_snapshot_is_current(items)
        if not isinstance(current, bool):
            raise RetrievalError("memory backend returned an invalid snapshot status")
        return current

    @contextmanager
    def disclosure_guard(self, matches: Sequence[HybridMatch]) -> Iterator[None]:
        """Keep canonical records authorized during the caller's short write."""
        items = _snapshot_items(matches)
        if not items:
            yield
            return
        guard = getattr(self._backend, "disclosure_guard", None)
        if not callable(guard):
            raise RetrievalError("memory backend does not support guarded disclosure")
        with guard(items):
            yield


def _snapshot_items(matches: Sequence[HybridMatch]) -> tuple[MemoryItem, ...]:
    if isinstance(matches, (str, bytes)) or not isinstance(matches, Sequence):
        raise RetrievalError("retrieval matches must be a sequence")
    if len(matches) > MAX_RETRIEVAL_LIMIT:
        raise RetrievalError("retrieval snapshot contains too many memories")
    items = []
    seen_ids = set()
    for match in matches:
        if not isinstance(match, HybridMatch):
            raise RetrievalError("retrieval matches contain an invalid item")
        if not isinstance(match.memory, MemoryItem):
            raise RetrievalError("retrieval match contains an invalid memory item")
        if match.memory.id in seen_ids:
            raise RetrievalError("retrieval snapshot contains a duplicate memory")
        seen_ids.add(match.memory.id)
        items.append(match.memory)
    return tuple(items)


def _retrieval_limit(value: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= MAX_RETRIEVAL_LIMIT
    ):
        raise MemoryValidationError(
            f"retrieval limit must be an integer from 1 to {MAX_RETRIEVAL_LIMIT}"
        )
    return value


def _source_results(
    value: Sequence[object], expected_type: type, *, source: str
) -> tuple[object, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise RetrievalError(f"{source} search returned an invalid result sequence")
    results = tuple(value[:CANDIDATE_POOL_SIZE])
    if any(not isinstance(result, expected_type) for result in results):
        raise RetrievalError(f"{source} search returned an invalid result")
    return results


def _candidate(
    candidates: dict[str, _Candidate], memory: MemoryItem
) -> _Candidate:
    if not isinstance(memory, MemoryItem):
        raise RetrievalError("memory search returned an invalid memory item")
    candidate = candidates.get(memory.id)
    if candidate is None:
        candidate = _Candidate(memory=memory)
        candidates[memory.id] = candidate
    elif candidate.memory != memory:
        raise RetrievalError(
            "memory changed between retrieval sources; discard these results"
        )
    return candidate


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise RetrievalError(f"{field} is invalid")
    normalized = float(value)
    if not isfinite(normalized):
        raise RetrievalError(f"{field} is invalid")
    return normalized
