"""Gold-free execution harness for the fictional evaluation suite.

The runner deliberately separates execution from scoring.  It sends only an
``ExecutionCase`` prompt to the system under test and writes observations that
contain no expected route, retrieval gold, reference answer, or rubric.
"""

from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isfinite
from numbers import Real
import os
from pathlib import Path
import platform
import re
import stat
import sys
import tempfile
from threading import Lock
from time import perf_counter_ns
from typing import (
    Any,
    Callable,
    ContextManager,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    TextIO,
)
import unicodedata
from uuid import uuid4

from . import __version__
from .config import AppConfig, ConfigError, load_config
from .conversation import (
    Conversation,
    ConversationError,
    ConversationReply,
    MAX_RETRIEVED_MEMORIES,
)
from .embedding import (
    BgeOnnxEmbedder,
    EmbeddingProvider,
    MODEL_ID as EMBEDDING_MODEL_ID,
    MODEL_REVISION as EMBEDDING_MODEL_REVISION,
)
from .evaluation import (
    EvaluationError,
    EvaluationSuite,
    load_evaluation_suite,
    materialize_memory_store,
    prompt_records,
)
from .evaluation_scoring import evaluation_suite_sha256
from .ollama import (
    ChatMessage,
    ChatResult,
    MAX_OLLAMA_RESPONSE_BYTES,
    OllamaClient,
    OllamaTimeoutError,
)
from .response import ResponseValidationError
from .retrieval import HybridMatch, HybridRetriever
from .routing import ConversationRouter, RouteDecision, RoutingResult, privacy_abstention


RUN_SCHEMA_VERSION = 2
EVALUATION_TEMPERATURE = 0.0
EVALUATION_SEED = 42
COMPONENT_RETRIEVAL_LIMIT = 5
MAX_REPETITIONS = 100

ALWAYS_SMALL_NO_RAG = "always_small_no_rag"
ALWAYS_LARGE_NO_RAG = "always_large_no_rag"
ALWAYS_LARGE_WITH_RAG = "always_large_with_rag"
ADAPTIVE = "adaptive"
CASCADE_STRATEGIES = (
    ALWAYS_SMALL_NO_RAG,
    ALWAYS_LARGE_NO_RAG,
    ALWAYS_LARGE_WITH_RAG,
    ADAPTIVE,
)

_CASE_ID_PATTERN = re.compile(r"[a-z][a-z0-9_.-]{0,127}\Z")
_RUN_ID_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}\Z")
_ERROR_TYPE_PATTERN = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]{0,127}\Z")
_MEMORY_ID_PATTERN = re.compile(r"mem_[0-9a-f]{32}\Z")


class EvaluationRunError(RuntimeError):
    """Raised when a run cannot create a trustworthy observation artifact."""


class _ChatBackend(Protocol):
    def chat(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        *,
        response_format: Optional[Mapping[str, Any]] = None,
        temperature: Optional[float] = None,
        seed: Optional[int] = None,
    ) -> ChatResult:
        """Return one local chat result."""


class _Retriever(Protocol):
    def retrieve(
        self, query: str, *, limit: int = MAX_RETRIEVED_MEMORIES
    ) -> Sequence[HybridMatch]:
        """Return ranked memory matches."""

    def is_current(self, matches: Sequence[HybridMatch]) -> bool:
        """Return whether a supplied snapshot is still current."""


@dataclass(frozen=True)
class ExecutionCase:
    """The complete data allowed to cross from annotations into execution."""

    case_id: str
    prompt: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.case_id, str)
            or _CASE_ID_PATTERN.fullmatch(self.case_id) is None
        ):
            raise EvaluationRunError("execution case ID is invalid")
        if (
            not isinstance(self.prompt, str)
            or not self.prompt.strip()
            or len(self.prompt) > 1000
        ):
            raise EvaluationRunError("execution case prompt is invalid")


@dataclass(frozen=True)
class EvaluationRunSummary:
    """Safe aggregate returned after every expected slot was recorded."""

    run_id: str
    output_path: Path
    retrieval_records: int
    retrieval_errors: int
    cascade_records: int
    cascade_errors: int


@dataclass(frozen=True)
class _EmbeddingCall:
    operation: str
    wall_ns: int
    status: str


@dataclass(frozen=True)
class _SearchCall:
    operation: str
    wall_ns: int
    status: str


class _TimedEmbeddingProvider:
    """Preserve the provider contract while timing exact public calls."""

    def __init__(
        self,
        delegate: EmbeddingProvider,
        clock_ns: Callable[[], int],
    ) -> None:
        self._delegate = delegate
        self._clock_ns = clock_ns
        self._calls: list[_EmbeddingCall] = []
        self._lock = Lock()
        self.model_id = delegate.model_id
        self.model_revision = delegate.model_revision
        self.dimension = delegate.dimension

    def checkpoint(self) -> int:
        with self._lock:
            return len(self._calls)

    def query_wall_since(self, checkpoint: int) -> Optional[int]:
        return self._wall_since(checkpoint, operation="query")

    def passage_stats_since(self, checkpoint: int) -> tuple[int, int]:
        with self._lock:
            selected = tuple(self._calls[checkpoint:])
        passage_calls = tuple(
            call for call in selected if call.operation == "passages"
        )
        return (
            len(passage_calls),
            sum(call.wall_ns for call in passage_calls),
        )

    def _wall_since(self, checkpoint: int, *, operation: str) -> Optional[int]:
        with self._lock:
            selected = tuple(self._calls[checkpoint:])
        query_calls = tuple(
            call for call in selected if call.operation == operation
        )
        if not query_calls:
            return None
        return sum(call.wall_ns for call in query_calls)

    def embed_passages(self, passages: Sequence[str]) -> Any:
        return self._timed("passages", self._delegate.embed_passages, passages)

    def embed_query(self, query: str) -> Any:
        return self._timed("query", self._delegate.embed_query, query)

    def _timed(self, operation: str, function: Callable[..., Any], value: Any) -> Any:
        started = self._clock_ns()
        status = "ok"
        try:
            return function(value)
        except BaseException:
            status = "error"
            raise
        finally:
            elapsed = _elapsed_ns(started, self._clock_ns())
            with self._lock:
                self._calls.append(
                    _EmbeddingCall(
                        operation=operation,
                        wall_ns=elapsed,
                        status=status,
                    )
                )


class _TimedSearchBackend:
    """Time the exact semantic and keyword store calls used by hybrid search."""

    def __init__(
        self,
        delegate: Any,
        clock_ns: Callable[[], int],
    ) -> None:
        self._delegate = delegate
        self._clock_ns = clock_ns
        self._calls: list[_SearchCall] = []
        self._lock = Lock()

    def checkpoint(self) -> int:
        with self._lock:
            return len(self._calls)

    def wall_since(self, checkpoint: int, *, operation: str) -> Optional[int]:
        with self._lock:
            selected = tuple(self._calls[checkpoint:])
        calls = tuple(
            call for call in selected if call.operation == operation
        )
        if not calls:
            return None
        return sum(call.wall_ns for call in calls)

    def search_semantic(self, query: str, *, limit: int = 5) -> Any:
        return self._timed(
            "semantic",
            self._delegate.search_semantic,
            query,
            limit=limit,
        )

    def search_keywords(self, query: str, *, limit: int = 5) -> Any:
        return self._timed(
            "keyword",
            self._delegate.search_keywords,
            query,
            limit=limit,
        )

    def retrieval_snapshot_is_current(self, items: Sequence[Any]) -> bool:
        return self._delegate.retrieval_snapshot_is_current(items)

    def _timed(
        self,
        operation: str,
        function: Callable[..., Any],
        query: str,
        *,
        limit: int,
    ) -> Any:
        started = self._clock_ns()
        status = "ok"
        try:
            return function(query, limit=limit)
        except BaseException:
            status = "error"
            raise
        finally:
            elapsed = _elapsed_ns(started, self._clock_ns())
            with self._lock:
                self._calls.append(
                    _SearchCall(
                        operation=operation,
                        wall_ns=elapsed,
                        status=status,
                    )
                )


class _NoTimeoutFallbackBackend:
    """Keep a fixed large-model baseline to exactly one generator attempt."""

    def __init__(self, delegate: _EvaluationBackend) -> None:
        self._delegate = delegate

    def chat(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        *,
        response_format: Optional[Mapping[str, Any]] = None,
        temperature: Optional[float] = None,
        seed: Optional[int] = None,
    ) -> ChatResult:
        try:
            return self._delegate.chat(
                model,
                messages,
                response_format=response_format,
                temperature=temperature,
                seed=seed,
            )
        except OllamaTimeoutError:
            # Conversation only falls back on this exact exception type.  The
            # delegate has already retained the original timeout observation.
            raise EvaluationRunError(
                "fixed large-model baseline generation timed out"
            ) from None


class _EvaluationBackend:
    """Apply fixed evaluation sampling and retain bounded call observations."""

    def __init__(
        self,
        delegate: _ChatBackend,
        clock_ns: Callable[[], int],
    ) -> None:
        self._delegate = delegate
        self._clock_ns = clock_ns
        self._calls: list[dict[str, object]] = []
        self._lock = Lock()

    def checkpoint(self) -> int:
        with self._lock:
            return len(self._calls)

    def calls_since(self, checkpoint: int) -> list[dict[str, object]]:
        with self._lock:
            return [dict(item) for item in self._calls[checkpoint:]]

    def chat(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        *,
        response_format: Optional[Mapping[str, Any]] = None,
        temperature: Optional[float] = None,
        seed: Optional[int] = None,
    ) -> ChatResult:
        effective_temperature = (
            EVALUATION_TEMPERATURE if temperature is None else temperature
        )
        effective_seed = EVALUATION_SEED if seed is None else seed
        purpose = _chat_purpose(response_format)
        supplied_ids = _schema_supplied_ids(response_format, purpose=purpose)
        started = self._clock_ns()
        try:
            result = self._delegate.chat(
                model,
                messages,
                response_format=response_format,
                temperature=effective_temperature,
                seed=effective_seed,
            )
        except BaseException as exc:
            self._append_call(
                {
                    "purpose": purpose,
                    "supplied_ids": supplied_ids,
                    "model": model,
                    "temperature": effective_temperature,
                    "seed": effective_seed,
                    "wall_ns": _elapsed_ns(started, self._clock_ns()),
                    "status": "error",
                    "error_type": _error_type(exc),
                    "generation": None,
                }
            )
            raise

        generation = _chat_result_record(result)
        self._append_call(
            {
                "purpose": purpose,
                "supplied_ids": supplied_ids,
                "model": model,
                "temperature": effective_temperature,
                "seed": effective_seed,
                "wall_ns": _elapsed_ns(started, self._clock_ns()),
                "status": "ok" if generation is not None else "error",
                "error_type": None if generation is not None else "InvalidChatResult",
                "generation": generation,
            }
        )
        if generation is None:
            raise EvaluationRunError(
                "chat backend returned malformed generation metadata"
            )
        return result

    def _append_call(self, value: dict[str, object]) -> None:
        with self._lock:
            self._calls.append(value)


class _RecordingRetriever:
    """Record the exact top-k result returned to Conversation."""

    def __init__(
        self,
        delegate: _Retriever,
        clock_ns: Callable[[], int],
        embedding: Optional[_TimedEmbeddingProvider],
        search: Optional[_TimedSearchBackend],
    ) -> None:
        self._delegate = delegate
        self._clock_ns = clock_ns
        self._embedding = embedding
        self._search = search
        self.retrieve_calls: list[dict[str, object]] = []
        self.freshness_error = False

    def retrieve(
        self, query: str, *, limit: int = MAX_RETRIEVED_MEMORIES
    ) -> Sequence[HybridMatch]:
        embedding_checkpoint = (
            None if self._embedding is None else self._embedding.checkpoint()
        )
        search_checkpoint = (
            None if self._search is None else self._search.checkpoint()
        )
        started = self._clock_ns()
        try:
            result = self._delegate.retrieve(query, limit=limit)
        except BaseException as exc:
            self.retrieve_calls.append(
                {
                    "status": "error",
                    "error_type": _error_type(exc),
                    "wall_ns": _elapsed_ns(started, self._clock_ns()),
                    "embedding_wall_ns": _embedding_elapsed(
                        self._embedding, embedding_checkpoint
                    ),
                    "semantic_search_wall_ns": _search_elapsed(
                        self._search, search_checkpoint, operation="semantic"
                    ),
                    "keyword_search_wall_ns": _search_elapsed(
                        self._search, search_checkpoint, operation="keyword"
                    ),
                    "ranked": [],
                }
            )
            raise
        try:
            ranked = _ranked_records(result)
        except Exception as exc:
            self.retrieve_calls.append(
                {
                    "status": "error",
                    "error_type": _error_type(exc),
                    "wall_ns": _elapsed_ns(started, self._clock_ns()),
                    "embedding_wall_ns": _embedding_elapsed(
                        self._embedding, embedding_checkpoint
                    ),
                    "semantic_search_wall_ns": _search_elapsed(
                        self._search, search_checkpoint, operation="semantic"
                    ),
                    "keyword_search_wall_ns": _search_elapsed(
                        self._search, search_checkpoint, operation="keyword"
                    ),
                    "ranked": [],
                }
            )
            raise
        self.retrieve_calls.append(
            {
                "status": "ok",
                "error_type": None,
                "wall_ns": _elapsed_ns(started, self._clock_ns()),
                "embedding_wall_ns": _embedding_elapsed(
                    self._embedding, embedding_checkpoint
                ),
                "semantic_search_wall_ns": _search_elapsed(
                    self._search, search_checkpoint, operation="semantic"
                ),
                "keyword_search_wall_ns": _search_elapsed(
                    self._search, search_checkpoint, operation="keyword"
                ),
                "ranked": ranked,
            }
        )
        return result

    def is_current(self, matches: Sequence[HybridMatch]) -> bool:
        try:
            return self._delegate.is_current(matches)
        except BaseException:
            self.freshness_error = True
            raise


class _StaticRouter:
    """Route a baseline through Conversation without another model call."""

    def __init__(
        self,
        *,
        memory_required: bool,
        model_size: str,
        router_model: str,
    ) -> None:
        decision = RouteDecision(memory_required, model_size)
        memory_required_generation = ChatResult(
            model=router_model,
            content=json.dumps(
                {"memory_required": memory_required},
                separators=(",", ":"),
            ),
            done_reason="fixed_strategy",
            total_duration_ns=0,
            load_duration_ns=0,
            prompt_eval_count=0,
            eval_count=0,
            eval_duration_ns=0,
        )
        model_size_generation = ChatResult(
            model=router_model,
            content=json.dumps(
                {"model_size": model_size},
                separators=(",", ":"),
            ),
            done_reason="fixed_strategy",
            total_duration_ns=0,
            load_duration_ns=0,
            prompt_eval_count=0,
            eval_count=0,
            eval_duration_ns=0,
        )
        self._result = RoutingResult(
            decision=decision,
            memory_required_generation=memory_required_generation,
            model_size_generation=model_size_generation,
        )

    def route(
        self,
        user_text: str,
        *,
        history: Sequence[ChatMessage] = (),
    ) -> RoutingResult:
        return self._result


class _RecordingRouter:
    def __init__(self, delegate: Any, clock_ns: Callable[[], int]) -> None:
        self._delegate = delegate
        self._clock_ns = clock_ns
        self.last_wall_ns: Optional[int] = None
        self.last_result: Optional[RoutingResult] = None
        self.error_type: Optional[str] = None

    def route(
        self,
        user_text: str,
        *,
        history: Sequence[ChatMessage] = (),
    ) -> RoutingResult:
        started = self._clock_ns()
        try:
            result = self._delegate.route(user_text, history=history)
        except BaseException as exc:
            self.error_type = _error_type(exc)
            self.last_wall_ns = _elapsed_ns(started, self._clock_ns())
            raise
        self.last_wall_ns = _elapsed_ns(started, self._clock_ns())
        if isinstance(result, RoutingResult):
            self.last_result = result
        return result


class _CanonicalJsonlWriter:
    def __init__(self, path: str | Path) -> None:
        self.path = _new_private_output_path(path)
        self._descriptor: Optional[int] = None

    def __enter__(self) -> "_CanonicalJsonlWriter":
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        try:
            descriptor = os.open(self.path, flags, 0o600)
        except FileExistsError:
            raise EvaluationRunError("evaluation output already exists") from None
        except OSError:
            raise EvaluationRunError(
                "evaluation output could not be created"
            ) from None
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise OSError("not a regular file")
            os.fchmod(descriptor, 0o600)
            self._descriptor = descriptor
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise EvaluationRunError(
                "evaluation output could not be opened safely"
            ) from None
        return self

    def write(self, record: Mapping[str, object]) -> None:
        if self._descriptor is None:
            raise EvaluationRunError("evaluation output is not open")
        try:
            payload = (
                json.dumps(
                    record,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                + "\n"
            ).encode("utf-8")
        except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
            raise EvaluationRunError("evaluation output encoding failed") from None

        descriptor = self._descriptor
        try:
            checkpoint = os.lseek(descriptor, 0, os.SEEK_CUR)
        except OSError:
            raise EvaluationRunError("evaluation output write failed") from None
        try:
            remaining = memoryview(payload)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise OSError("short output write")
                remaining = remaining[written:]
            os.fsync(descriptor)
        except BaseException as exc:
            rollback_complete = True
            try:
                os.ftruncate(descriptor, checkpoint)
                os.lseek(descriptor, checkpoint, os.SEEK_SET)
                os.fsync(descriptor)
            except OSError:
                rollback_complete = False
            if not isinstance(exc, Exception):
                raise
            if not rollback_complete:
                raise EvaluationRunError(
                    "evaluation output write failed and checkpoint rollback failed"
                ) from None
            raise EvaluationRunError("evaluation output write failed") from None

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        descriptor = self._descriptor
        self._descriptor = None
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                if exc is None:
                    raise EvaluationRunError(
                        "evaluation output close failed"
                    ) from None
        return False


def execution_cases(
    suite: EvaluationSuite, *, track: str = "all"
) -> tuple[ExecutionCase, ...]:
    """Return a validated prompt-only projection in stable manifest order."""

    # The public Step 15 helper revalidates even hand-constructed dataclasses.
    prompt_records(suite, track=track)
    selected = (
        suite.cases
        if track == "all"
        else tuple(case for case in suite.cases if track in case.tags)
    )
    return tuple(ExecutionCase(case.id, case.prompt) for case in selected)


def run_evaluation(
    suite: EvaluationSuite,
    config: AppConfig,
    output_path: str | Path,
    *,
    strategies: Sequence[str] = CASCADE_STRATEGIES,
    repetitions: int = 1,
    backend: Optional[_ChatBackend] = None,
    retriever: Optional[_Retriever] = None,
    embedder: Optional[EmbeddingProvider] = None,
    run_id: Optional[str] = None,
    clock_ns: Callable[[], int] = perf_counter_ns,
    utc_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    progress: Optional[TextIO] = None,
    telemetry: Optional[ContextManager[object]] = None,
) -> EvaluationRunSummary:
    """Execute retrieval and stateless cascades into a new gold-free JSONL file.

    Passing ``backend`` and ``retriever`` is intended for deterministic tests.
    Normal execution constructs the real local Ollama, BGE, MemoryStore, and
    HybridRetriever stack.  A telemetry context manager may sample alongside
    case execution and remains responsible for its own artifact.
    """

    if not isinstance(config, AppConfig):
        raise EvaluationRunError("config must be a validated AppConfig")
    selected_strategies = _strategies(strategies)
    repeat_count = _repetitions(repetitions)
    normalized_run_id = _run_id(run_id)
    all_cases = execution_cases(suite)
    retrieval_cases = execution_cases(suite, track="rag")
    case_ordinals = {
        case.case_id: ordinal for ordinal, case in enumerate(all_cases, start=1)
    }
    suite_digest = evaluation_suite_sha256(suite)
    config_digest = _config_sha256(config)
    started_at = _timestamp(utc_now())
    output = progress

    expected_retrieval = repeat_count * len(retrieval_cases)
    expected_cascade = (
        repeat_count * len(selected_strategies) * len(all_cases)
    )
    written_retrieval = 0
    error_retrieval = 0
    written_cascade = 0
    error_cascade = 0

    header = {
        "record_type": "header",
        "schema_version": RUN_SCHEMA_VERSION,
        "run_id": normalized_run_id,
        "suite_id": suite.suite_id,
        "suite_sha256": suite_digest,
        "annotation_status": suite.annotation_status,
        "config_sha256": config_digest,
        "strategies": list(selected_strategies),
        "retrieval_limit": COMPONENT_RETRIEVAL_LIMIT,
        "repetitions": repeat_count,
        "evaluation_temperature": EVALUATION_TEMPERATURE,
        "evaluation_seed": EVALUATION_SEED,
        "started_at": started_at,
        "runtime": {
            "oline_hri_version": __version__,
            "python_version": platform.python_version(),
            "machine": platform.machine(),
            "small_model": config.ollama.small_model,
            "general_large_model": config.ollama.general_large_model,
            "large_model": config.ollama.large_model,
            "embedding_model_id": EMBEDDING_MODEL_ID,
            "embedding_model_revision": EMBEDDING_MODEL_REVISION,
        },
    }

    telemetry_context = telemetry if telemetry is not None else nullcontext()
    with telemetry_context, _CanonicalJsonlWriter(output_path) as writer:
        writer.write(header)
        _progress(
            output,
            f"evaluation {normalized_run_id} started: "
            f"{expected_retrieval} retrieval and {expected_cascade} cascade records",
        )

        temporary_directory: Optional[tempfile.TemporaryDirectory[str]] = None
        timed_embedding: Optional[_TimedEmbeddingProvider] = None
        timed_search: Optional[_TimedSearchBackend] = None
        setup_error: Optional[Exception] = None
        evaluation_backend: Optional[_EvaluationBackend] = None
        base_retriever: Optional[_Retriever] = None
        setup_started = clock_ns()
        materialization_wall_ns: Optional[int] = None
        passage_embedding_calls: Optional[int] = 0
        passage_embedding_wall_ns: Optional[int] = None
        try:
            raw_backend = backend
            if raw_backend is None:
                raw_backend = OllamaClient(config.ollama, config.generation)
            evaluation_backend = _EvaluationBackend(raw_backend, clock_ns)

            if retriever is not None:
                base_retriever = retriever
                materialization_wall_ns = 0
                passage_embedding_wall_ns = 0
            else:
                raw_embedder = embedder
                if raw_embedder is None:
                    raw_embedder = BgeOnnxEmbedder(
                        config.embedding.model_directory,
                        config.embedding.intra_op_threads,
                    )
                timed_embedding = _TimedEmbeddingProvider(raw_embedder, clock_ns)
                passage_checkpoint = timed_embedding.checkpoint()
                temporary_directory = tempfile.TemporaryDirectory(
                    prefix=".oline-hri-evaluation-",
                    dir=str(Path(output_path).expanduser().parent),
                )
                database = Path(temporary_directory.name) / "memory.sqlite3"
                materialization_started = clock_ns()
                try:
                    store = materialize_memory_store(
                        suite,
                        database,
                        embedder=timed_embedding,
                    )
                finally:
                    materialization_wall_ns = _elapsed_ns(
                        materialization_started, clock_ns()
                    )
                    passage_calls, passage_wall = (
                        timed_embedding.passage_stats_since(passage_checkpoint)
                    )
                    passage_embedding_calls = passage_calls
                    passage_embedding_wall_ns = (
                        passage_wall if passage_calls else None
                    )
                timed_search = _TimedSearchBackend(store, clock_ns)
                base_retriever = HybridRetriever(timed_search)
        except BaseException as exc:
            setup_finished = clock_ns()
            setup_wall_ns = _elapsed_ns(setup_started, setup_finished)
            if not isinstance(exc, Exception):
                writer.write(
                    _setup_record(
                        normalized_run_id,
                        suite.suite_id,
                        suite_digest,
                        status="error",
                        error=exc,
                        started_monotonic_ns=setup_started,
                        finished_monotonic_ns=setup_finished,
                        wall_ns=setup_wall_ns,
                        materialization_wall_ns=materialization_wall_ns,
                        passage_embedding_wall_ns=passage_embedding_wall_ns,
                        passage_embedding_calls=passage_embedding_calls,
                    )
                )
                if temporary_directory is not None:
                    try:
                        temporary_directory.cleanup()
                    except Exception:
                        pass
                raise
            setup_error = exc
        setup_finished = clock_ns()
        setup_wall_ns = _elapsed_ns(setup_started, setup_finished)
        writer.write(
            _setup_record(
                normalized_run_id,
                suite.suite_id,
                suite_digest,
                status="error" if setup_error is not None else "ok",
                error=setup_error,
                started_monotonic_ns=setup_started,
                finished_monotonic_ns=setup_finished,
                wall_ns=setup_wall_ns,
                materialization_wall_ns=materialization_wall_ns,
                passage_embedding_wall_ns=passage_embedding_wall_ns,
                passage_embedding_calls=passage_embedding_calls,
            )
        )

        try:
            for repetition in range(1, repeat_count + 1):
                for case in retrieval_cases:
                    retrieval_ordinal = case_ordinals[case.case_id]
                    if setup_error is not None or base_retriever is None:
                        record = _retrieval_error_record(
                            normalized_run_id,
                            suite.suite_id,
                            suite_digest,
                            repetition,
                            retrieval_ordinal,
                            case.case_id,
                            setup_error or EvaluationRunError("setup failed"),
                        )
                    else:
                        try:
                            record = _run_component_retrieval(
                                base_retriever,
                                timed_embedding,
                                timed_search,
                                case,
                                run_id=normalized_run_id,
                                suite_id=suite.suite_id,
                                suite_sha256=suite_digest,
                                repetition=repetition,
                                ordinal=retrieval_ordinal,
                                clock_ns=clock_ns,
                            )
                        except Exception as exc:
                            record = _retrieval_error_record(
                                normalized_run_id,
                                suite.suite_id,
                                suite_digest,
                                repetition,
                                retrieval_ordinal,
                                case.case_id,
                                exc,
                            )
                    writer.write(record)
                    written_retrieval += 1
                    if record["status"] == "error":
                        error_retrieval += 1
                    _progress(
                        output,
                        f"retrieval {written_retrieval}/{expected_retrieval} "
                        f"{case.case_id}: {record['status']}",
                    )

            for repetition in range(1, repeat_count + 1):
                for strategy in selected_strategies:
                    for cascade_ordinal, case in enumerate(
                        all_cases, start=1
                    ):
                        if (
                            setup_error is not None
                            or evaluation_backend is None
                            or base_retriever is None
                        ):
                            record = _cascade_setup_error_record(
                                normalized_run_id,
                                suite.suite_id,
                                suite_digest,
                                strategy,
                                repetition,
                                cascade_ordinal,
                                case.case_id,
                                setup_error
                                or EvaluationRunError("setup failed"),
                            )
                        else:
                            try:
                                record = _run_cascade_case(
                                    case,
                                    strategy,
                                    config,
                                    evaluation_backend,
                                    base_retriever,
                                    timed_embedding,
                                    timed_search,
                                    run_id=normalized_run_id,
                                    suite_id=suite.suite_id,
                                    suite_sha256=suite_digest,
                                    repetition=repetition,
                                    ordinal=cascade_ordinal,
                                    clock_ns=clock_ns,
                                )
                            except Exception as exc:
                                record = _cascade_setup_error_record(
                                    normalized_run_id,
                                    suite.suite_id,
                                    suite_digest,
                                    strategy,
                                    repetition,
                                    cascade_ordinal,
                                    case.case_id,
                                    exc,
                                )
                        writer.write(record)
                        written_cascade += 1
                        if record["status"] == "error":
                            error_cascade += 1
                        _progress(
                            output,
                            f"cascade {written_cascade}/{expected_cascade} "
                            f"{strategy} {case.case_id}: {record['status']}",
                        )
        finally:
            if temporary_directory is not None:
                active_exception = sys.exc_info()[0] is not None
                try:
                    temporary_directory.cleanup()
                except Exception:
                    if not active_exception:
                        raise EvaluationRunError(
                            "evaluation temporary database cleanup failed"
                        ) from None

        trailer = {
            "record_type": "trailer",
            "schema_version": RUN_SCHEMA_VERSION,
            "run_id": normalized_run_id,
            "suite_id": suite.suite_id,
            "expected_retrieval_records": expected_retrieval,
            "written_retrieval_records": written_retrieval,
            "error_retrieval_records": error_retrieval,
            "expected_cascade_records": expected_cascade,
            "written_cascade_records": written_cascade,
            "error_cascade_records": error_cascade,
            "completed": (
                written_retrieval == expected_retrieval
                and written_cascade == expected_cascade
            ),
            "finished_at": _timestamp(utc_now()),
        }
        writer.write(trailer)

    _progress(
        output,
        f"evaluation {normalized_run_id} complete: "
        f"{error_retrieval + error_cascade} error records",
    )
    return EvaluationRunSummary(
        run_id=normalized_run_id,
        output_path=Path(output_path).expanduser(),
        retrieval_records=written_retrieval,
        retrieval_errors=error_retrieval,
        cascade_records=written_cascade,
        cascade_errors=error_cascade,
    )


def _run_component_retrieval(
    retriever: _Retriever,
    embedding: Optional[_TimedEmbeddingProvider],
    search: Optional[_TimedSearchBackend],
    case: ExecutionCase,
    *,
    run_id: str,
    suite_id: str,
    suite_sha256: str,
    repetition: int,
    ordinal: int,
    clock_ns: Callable[[], int],
) -> dict[str, object]:
    embedding_checkpoint = None if embedding is None else embedding.checkpoint()
    search_checkpoint = None if search is None else search.checkpoint()
    started = clock_ns()
    try:
        matches = retriever.retrieve(
            case.prompt,
            limit=COMPONENT_RETRIEVAL_LIMIT,
        )
        ranked = _ranked_records(matches)
        if len(ranked) > COMPONENT_RETRIEVAL_LIMIT:
            raise EvaluationRunError("component retriever returned too many matches")
    except Exception as exc:
        finished = clock_ns()
        return {
            "record_type": "retrieval",
            "schema_version": RUN_SCHEMA_VERSION,
            "run_id": run_id,
            "suite_id": suite_id,
            "suite_sha256": suite_sha256,
            "repetition": repetition,
            "ordinal": ordinal,
            "case_id": case.case_id,
            "status": "error",
            "error_type": _error_type(exc),
            "started_monotonic_ns": started,
            "finished_monotonic_ns": finished,
            "wall_ns": _elapsed_ns(started, finished),
            "embedding_wall_ns": _embedding_elapsed(
                embedding, embedding_checkpoint
            ),
            "semantic_search_wall_ns": _search_elapsed(
                search, search_checkpoint, operation="semantic"
            ),
            "keyword_search_wall_ns": _search_elapsed(
                search, search_checkpoint, operation="keyword"
            ),
            "ranked": [],
        }
    finished = clock_ns()
    return {
        "record_type": "retrieval",
        "schema_version": RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "suite_id": suite_id,
        "suite_sha256": suite_sha256,
        "repetition": repetition,
        "ordinal": ordinal,
        "case_id": case.case_id,
        "status": "ok",
        "error_type": None,
        "started_monotonic_ns": started,
        "finished_monotonic_ns": finished,
        "wall_ns": _elapsed_ns(started, finished),
        "embedding_wall_ns": _embedding_elapsed(embedding, embedding_checkpoint),
        "semantic_search_wall_ns": _search_elapsed(
            search, search_checkpoint, operation="semantic"
        ),
        "keyword_search_wall_ns": _search_elapsed(
            search, search_checkpoint, operation="keyword"
        ),
        "ranked": ranked,
    }


def _run_cascade_case(
    case: ExecutionCase,
    strategy: str,
    config: AppConfig,
    backend: _EvaluationBackend,
    retriever: _Retriever,
    embedding: Optional[_TimedEmbeddingProvider],
    search: Optional[_TimedSearchBackend],
    *,
    run_id: str,
    suite_id: str,
    suite_sha256: str,
    repetition: int,
    ordinal: int,
    clock_ns: Callable[[], int],
) -> dict[str, object]:
    backend_checkpoint = backend.checkpoint()
    recording_retriever = _RecordingRetriever(
        retriever, clock_ns, embedding, search
    )
    recording_router: Optional[_RecordingRouter] = None
    fixed_route = _strategy_route(strategy)

    if strategy == ALWAYS_SMALL_NO_RAG:
        conversation = Conversation(
            backend,
            system_prompt=config.conversation.system_prompt,
            model=config.ollama.small_model,
            context_length=config.generation.context_length,
            max_output_tokens=config.generation.max_output_tokens,
        )
    elif strategy == ALWAYS_LARGE_NO_RAG:
        conversation = Conversation(
            backend,
            system_prompt=config.conversation.system_prompt,
            model=config.ollama.general_large_model,
            context_length=config.generation.context_length,
            max_output_tokens=config.generation.max_output_tokens,
        )
    else:
        if strategy == ALWAYS_LARGE_WITH_RAG:
            raw_router: Any = _StaticRouter(
                memory_required=True,
                model_size="large",
                router_model=config.ollama.small_model,
            )
        else:
            raw_router = ConversationRouter(
                backend,
                model=config.ollama.small_model,
            )
        recording_router = _RecordingRouter(raw_router, clock_ns)
        conversation_backend: _ChatBackend = backend
        if strategy == ALWAYS_LARGE_WITH_RAG:
            conversation_backend = _NoTimeoutFallbackBackend(backend)
        conversation = Conversation(
            conversation_backend,
            system_prompt=config.conversation.system_prompt,
            router=recording_router,
            retriever=recording_retriever,
            small_model=config.ollama.small_model,
            general_large_model=config.ollama.general_large_model,
            large_model=config.ollama.large_model,
            context_length=config.generation.context_length,
            max_output_tokens=config.generation.max_output_tokens,
        )

    started = clock_ns()
    reply: Optional[ConversationReply] = None
    failure: Optional[Exception] = None
    try:
        reply = conversation.send(case.prompt)
    except Exception as exc:
        failure = exc
    finished = clock_ns()
    wall_ns = _elapsed_ns(started, finished)
    backend_calls = backend.calls_since(backend_checkpoint)

    if fixed_route is None and recording_router is not None:
        route_record = _route_record(recording_router, source="model")
    else:
        assert fixed_route is not None
        route_record = {
            "source": "strategy",
            "memory_required": fixed_route[0],
            "model_size": fixed_route[1],
            "wall_ns": None,
            "memory_required_generation": None,
            "model_size_generation": None,
        }

    selected_model = _selected_model(route_record, config)
    generator_calls = tuple(
        item for item in backend_calls if item.get("purpose") == "generation"
    )
    successful_generator = next(
        (
            item
            for item in reversed(generator_calls)
            if item.get("status") == "ok"
        ),
        None,
    )
    actual_model = (
        None
        if successful_generator is None
        else successful_generator.get("model")
    )
    generation = (
        None
        if successful_generator is None
        else successful_generator.get("generation")
    )
    inferred_fallback = _fallback_model(generator_calls, selected_model)
    attempted_supplied_ids = _generator_supplied_ids(generator_calls)

    retrieval_call = (
        recording_retriever.retrieve_calls[-1]
        if recording_retriever.retrieve_calls
        else None
    )
    cascade = {
        **({"privacy_gate": True} if privacy_abstention(case.prompt) else {}),
        **({"response_transform": reply.response_transform}
           if reply is not None and reply.response_transform is not None else {}),
        **({"answer_constraint": reply.answer_constraint}
           if reply is not None and reply.answer_constraint is not None else {}),
        **({"generation_policy": reply.generation_policy}
           if reply is not None and reply.generation_policy is not None else {}),
        **({"reference_ids": list(reply.reference_ids)}
           if reply is not None and reply.reference_ids else {}),
        "started_monotonic_ns": started,
        "finished_monotonic_ns": finished,
        "wall_ns": wall_ns,
        "retrieval_invoked": retrieval_call is not None,
        "retrieval_wall_ns": (
            None if retrieval_call is None else retrieval_call["wall_ns"]
        ),
        "retrieval_embedding_wall_ns": (
            None
            if retrieval_call is None
            else retrieval_call["embedding_wall_ns"]
        ),
        "retrieval_semantic_search_wall_ns": (
            None
            if retrieval_call is None
            else retrieval_call["semantic_search_wall_ns"]
        ),
        "retrieval_keyword_search_wall_ns": (
            None
            if retrieval_call is None
            else retrieval_call["keyword_search_wall_ns"]
        ),
        "retrieved_ranked": (
            [] if retrieval_call is None else retrieval_call["ranked"]
        ),
        "supplied_ids": (
            attempted_supplied_ids
            if reply is None
            else [match.memory.id for match in reply.retrieval]
        ),
        "requested_model": selected_model,
        "actual_model": (
            reply.generation.model if reply is not None else actual_model
        ),
        "fallback_from_model": (
            reply.fallback_from_model
            if reply is not None
            else inferred_fallback
        ),
        "response": (
            None if reply is None else reply.response.to_dict()
        ),
        "generation": (
            _chat_result_record(reply.generation)
            if reply is not None
            else generation
        ),
        "backend_calls": [
            _backend_call_record(item) for item in backend_calls
        ],
    }

    if failure is None:
        status = "ok"
        error_stage = None
        error_type = None
    else:
        status = "error"
        error_stage = _cascade_error_stage(
            failure,
            recording_router,
            recording_retriever,
            generator_calls,
        )
        error_type = _error_type(failure)

    return {
        "record_type": "case",
        "schema_version": RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "suite_id": suite_id,
        "suite_sha256": suite_sha256,
        "strategy": strategy,
        "repetition": repetition,
        "ordinal": ordinal,
        "case_id": case.case_id,
        "status": status,
        "error_stage": error_stage,
        "error_type": error_type,
        "route": route_record,
        "cascade": cascade,
    }


def _setup_record(
    run_id: str,
    suite_id: str,
    suite_sha256: str,
    *,
    status: str,
    error: Optional[BaseException],
    started_monotonic_ns: int,
    finished_monotonic_ns: int,
    wall_ns: int,
    materialization_wall_ns: Optional[int],
    passage_embedding_wall_ns: Optional[int],
    passage_embedding_calls: Optional[int],
) -> dict[str, object]:
    return {
        "record_type": "setup",
        "schema_version": RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "suite_id": suite_id,
        "suite_sha256": suite_sha256,
        "status": status,
        "error_type": None if error is None else _error_type(error),
        "started_monotonic_ns": started_monotonic_ns,
        "finished_monotonic_ns": finished_monotonic_ns,
        "wall_ns": wall_ns,
        "materialization_wall_ns": materialization_wall_ns,
        "passage_embedding_wall_ns": passage_embedding_wall_ns,
        "passage_embedding_calls": passage_embedding_calls,
    }


def _retrieval_error_record(
    run_id: str,
    suite_id: str,
    suite_sha256: str,
    repetition: int,
    ordinal: int,
    case_id: str,
    error: BaseException,
) -> dict[str, object]:
    return {
        "record_type": "retrieval",
        "schema_version": RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "suite_id": suite_id,
        "suite_sha256": suite_sha256,
        "repetition": repetition,
        "ordinal": ordinal,
        "case_id": case_id,
        "status": "error",
        "error_type": _error_type(error),
        "started_monotonic_ns": None,
        "finished_monotonic_ns": None,
        "wall_ns": None,
        "embedding_wall_ns": None,
        "semantic_search_wall_ns": None,
        "keyword_search_wall_ns": None,
        "ranked": [],
    }


def _cascade_setup_error_record(
    run_id: str,
    suite_id: str,
    suite_sha256: str,
    strategy: str,
    repetition: int,
    ordinal: int,
    case_id: str,
    error: BaseException,
) -> dict[str, object]:
    fixed_route = _strategy_route(strategy)
    route = (
        None
        if fixed_route is None
        else {
            "source": "strategy",
            "memory_required": fixed_route[0],
            "model_size": fixed_route[1],
            "wall_ns": None,
            "memory_required_generation": None,
            "model_size_generation": None,
        }
    )
    return {
        "record_type": "case",
        "schema_version": RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "suite_id": suite_id,
        "suite_sha256": suite_sha256,
        "strategy": strategy,
        "repetition": repetition,
        "ordinal": ordinal,
        "case_id": case_id,
        "status": "error",
        "error_stage": "runner",
        "error_type": _error_type(error),
        "route": route,
        "cascade": None,
    }


def _route_record(
    recorder: _RecordingRouter, *, source: str
) -> Optional[dict[str, object]]:
    result = recorder.last_result
    if result is None:
        return None
    policy_sources = {
        "memory_required": result.memory_decision_source,
        "model_size": result.model_size_decision_source,
    }
    hybrid = source == "model" and any(
        value != "model" for value in policy_sources.values()
    )
    return {
        **({"decision_sources": policy_sources} if hybrid else {}),
        "source": "hybrid" if hybrid else source,
        "memory_required": result.decision.memory_required,
        "model_size": result.decision.model_size,
        "wall_ns": recorder.last_wall_ns,
        "memory_required_generation": _chat_result_record(
            result.memory_required_generation
        ),
        "model_size_generation": _chat_result_record(
            result.model_size_generation
        ),
    }


def _strategy_route(strategy: str) -> Optional[tuple[bool, str]]:
    if strategy == ALWAYS_SMALL_NO_RAG:
        return False, "small"
    if strategy == ALWAYS_LARGE_NO_RAG:
        return False, "large"
    if strategy == ALWAYS_LARGE_WITH_RAG:
        return True, "large"
    return None


def _selected_model(
    route: Optional[Mapping[str, object]], config: AppConfig
) -> Optional[str]:
    if route is None:
        return None
    size = route.get("model_size")
    if size == "small":
        return config.ollama.small_model
    if size == "large":
        return (
            config.ollama.large_model
            if route.get("memory_required") is True
            else config.ollama.general_large_model
        )
    return None


def _fallback_model(
    generator_calls: Sequence[Mapping[str, object]],
    requested_model: Optional[str],
) -> Optional[str]:
    if (
        requested_model is not None
        and len(generator_calls) >= 2
        and generator_calls[0].get("model") == requested_model
        and any(
            call.get("model") != requested_model
            for call in generator_calls[1:]
        )
    ):
        return requested_model
    return None


def _cascade_error_stage(
    error: Exception,
    router: Optional[_RecordingRouter],
    retriever: _RecordingRetriever,
    generator_calls: Sequence[Mapping[str, object]],
) -> str:
    if router is not None and router.error_type is not None:
        return "route"
    if (
        retriever.freshness_error
        or any(call.get("status") == "error" for call in retriever.retrieve_calls)
    ):
        return "retrieval"
    if any(call.get("status") == "error" for call in generator_calls):
        return "generation"
    if isinstance(error, ResponseValidationError):
        return "response"
    if generator_calls:
        return "response"
    if isinstance(error, ConversationError):
        return "runner"
    return "runner"


def _ranked_records(value: object) -> list[dict[str, object]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise EvaluationRunError("retriever returned an invalid result sequence")
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, HybridMatch):
            raise EvaluationRunError("retriever returned an invalid match")
        identifier = item.memory.id
        if identifier in seen:
            raise EvaluationRunError("retriever returned duplicate memory IDs")
        seen.add(identifier)
        result.append(
            {
                "id": identifier,
                "fused_score": _finite_metric(
                    item.fused_score,
                    "fused_score",
                    minimum=0.0,
                    maximum=1.0,
                ),
                "keyword_rank": _optional_metric(
                    item.keyword_rank, "keyword_rank"
                ),
                "keyword_position": _optional_position(
                    item.keyword_position, "keyword_position"
                ),
                "semantic_score": _optional_metric(
                    item.semantic_score, "semantic_score"
                ),
                "semantic_position": _optional_position(
                    item.semantic_position, "semantic_position"
                ),
            }
        )
    return result


def _chat_result_record(value: object) -> Optional[dict[str, object]]:
    if not isinstance(value, ChatResult):
        return None
    if (
        not isinstance(value.model, str)
        or not value.model
        or not isinstance(value.content, str)
        or not value.content
        or value.content != value.content.strip()
        or not isinstance(value.done_reason, str)
        or not value.done_reason
        or len(value.done_reason) > 64
    ):
        return None
    try:
        if len(value.content.encode("utf-8")) > MAX_OLLAMA_RESPONSE_BYTES:
            return None
    except UnicodeEncodeError:
        return None
    if any(
        (
            unicodedata.category(character) in {"Cc", "Cs"}
            and character not in {"\t", "\n", "\r"}
        )
        or character in {"\u2028", "\u2029"}
        for character in value.content
    ):
        return None
    numeric_fields = (
        value.total_duration_ns,
        value.load_duration_ns,
        value.prompt_eval_count,
        value.prompt_eval_duration_ns,
        value.eval_count,
        value.eval_duration_ns,
    )
    if any(
        isinstance(item, bool)
        or not isinstance(item, int)
        or not 0 <= item <= 2**63 - 1
        for item in numeric_fields
    ):
        return None
    tokens_per_second = value.generation_tokens_per_second
    if tokens_per_second is not None and (
        not isinstance(tokens_per_second, Real)
        or isinstance(tokens_per_second, bool)
        or not isfinite(float(tokens_per_second))
        or not 0.0 <= float(tokens_per_second) <= 1_000_000.0
    ):
        return None
    return {
        "model": value.model,
        "content": value.content,
        "done_reason": value.done_reason,
        "total_duration_ns": value.total_duration_ns,
        "load_duration_ns": value.load_duration_ns,
        "prompt_eval_count": value.prompt_eval_count,
        "prompt_eval_duration_ns": value.prompt_eval_duration_ns,
        "eval_count": value.eval_count,
        "eval_duration_ns": value.eval_duration_ns,
        "generation_tokens_per_second": tokens_per_second,
    }


def _backend_call_record(value: Mapping[str, object]) -> dict[str, object]:
    """Drop execution-only call annotations from the public artifact."""

    return {
        "purpose": value.get("purpose"),
        "model": value.get("model"),
        "wall_ns": value.get("wall_ns"),
        "status": value.get("status"),
        "error_type": value.get("error_type"),
        "generation": value.get("generation"),
    }


def _finite_metric(
    value: object,
    field: str,
    *,
    minimum: float = -1_000_000_000.0,
    maximum: float = 1_000_000_000.0,
) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise EvaluationRunError(f"retrieval {field} is invalid")
    normalized = float(value)
    if (
        not isfinite(normalized)
        or not minimum <= normalized <= maximum
    ):
        raise EvaluationRunError(f"retrieval {field} is invalid")
    return normalized


def _optional_metric(value: object, field: str) -> Optional[float]:
    if value is None:
        return None
    return _finite_metric(value, field)


def _optional_position(value: object, field: str) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 20:
        raise EvaluationRunError(f"retrieval {field} is invalid")
    return value


def _chat_purpose(response_format: Optional[Mapping[str, Any]]) -> str:
    if isinstance(response_format, Mapping):
        if "oneOf" in response_format:
            from .semantic_routing import SEMANTIC_REVIEW_SCHEMA

            if response_format == SEMANTIC_REVIEW_SCHEMA:
                return "route_memory_required"
            raise EvaluationRunError("chat call has an unsupported response schema")
        properties = response_format.get("properties")
        if isinstance(properties, Mapping):
            fields = frozenset(properties)
            if fields in ({"memory_required"}, {"form", "memory_required"}):
                return "route_memory_required"
            if fields == {"needs_personal_facts"}:
                from .dependency_review import DEPENDENCY_REVIEW_SCHEMA

                if response_format == DEPENDENCY_REVIEW_SCHEMA:
                    return "route_dependency_review"
            if fields == {"form", "mode"}:
                from .semantic_routing import SEMANTIC_MODE_SCHEMA

                if response_format == SEMANTIC_MODE_SCHEMA:
                    return "route_memory_required"
            if fields == {"answer_source"}:
                from .semantic_routing import ANSWERABILITY_SCHEMA

                if response_format == ANSWERABILITY_SCHEMA:
                    return "route_answerability"
            if fields == {"form", "mode", "missing_fact", "general_request", "uncertain"}:
                from .semantic_routing import SEMANTIC_MEMORY_SCHEMA

                if response_format == SEMANTIC_MEMORY_SCHEMA:
                    return "route_memory_required"
            if fields == {"model_size"}:
                return "route_model_size"
            if fields == {"speech", "gesture_id", "memory_used"}:
                return "generation"
    raise EvaluationRunError("chat call has an unsupported response schema")


def _schema_supplied_ids(
    response_format: Optional[Mapping[str, Any]], *, purpose: str
) -> Optional[tuple[str, ...]]:
    """Extract the exact post-pruning memory allowlist sent to generation."""

    if purpose in {"route_memory_required", "route_model_size", "route_answerability",
                   "route_dependency_review"}:
        return None
    try:
        assert isinstance(response_format, Mapping)
        properties = response_format["properties"]
        assert isinstance(properties, Mapping)
        memory_used = properties["memory_used"]
        assert isinstance(memory_used, Mapping)
        items = memory_used["items"]
        assert isinstance(items, Mapping)
        raw_ids = items.get("enum", [])
    except (AssertionError, KeyError, TypeError):
        raise EvaluationRunError(
            "generation response schema has no trustworthy memory allowlist"
        ) from None
    if not isinstance(raw_ids, list):
        raise EvaluationRunError(
            "generation response schema has an invalid memory allowlist"
        )
    supplied = tuple(raw_ids)
    if (
        len(supplied) > MAX_RETRIEVED_MEMORIES
        or any(
            not isinstance(identifier, str)
            or _MEMORY_ID_PATTERN.fullmatch(identifier) is None
            for identifier in supplied
        )
        or len(supplied) != len(set(supplied))
    ):
        raise EvaluationRunError(
            "generation response schema has an invalid memory allowlist"
        )
    return supplied


def _generator_supplied_ids(
    calls: Sequence[Mapping[str, object]],
) -> list[str]:
    """Return the allowlist used by attempted generation, including failures."""

    observed = tuple(
        value
        for call in calls
        for value in (call.get("supplied_ids"),)
        if isinstance(value, tuple)
    )
    if not observed:
        return []
    # A timeout fallback reuses the identical prompt and response schema.  Treat
    # disagreement as untrustworthy rather than guessing which list was sent.
    if any(value != observed[0] for value in observed[1:]):
        return []
    return list(observed[0])


def _embedding_elapsed(
    embedding: Optional[_TimedEmbeddingProvider],
    checkpoint: Optional[int],
) -> Optional[int]:
    if embedding is None or checkpoint is None:
        return None
    return embedding.query_wall_since(checkpoint)


def _search_elapsed(
    search: Optional[_TimedSearchBackend],
    checkpoint: Optional[int],
    *,
    operation: str,
) -> Optional[int]:
    if search is None or checkpoint is None:
        return None
    return search.wall_since(checkpoint, operation=operation)


def _elapsed_ns(started: int, finished: int) -> int:
    elapsed = finished - started
    return elapsed if elapsed >= 0 else 0


def _strategies(value: Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise EvaluationRunError("strategies must be a sequence")
    selected = tuple(value)
    if not selected:
        raise EvaluationRunError("at least one strategy is required")
    if len(set(selected)) != len(selected):
        raise EvaluationRunError("strategies cannot contain duplicates")
    if any(strategy not in CASCADE_STRATEGIES for strategy in selected):
        raise EvaluationRunError("strategy is not supported")
    selected_set = frozenset(selected)
    return tuple(
        strategy for strategy in CASCADE_STRATEGIES if strategy in selected_set
    )


def _repetitions(value: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= MAX_REPETITIONS
    ):
        raise EvaluationRunError(
            f"repetitions must be an integer from 1 to {MAX_REPETITIONS}"
        )
    return value


def _run_id(value: Optional[str]) -> str:
    candidate = uuid4().hex if value is None else value
    if (
        not isinstance(candidate, str)
        or _RUN_ID_PATTERN.fullmatch(candidate) is None
    ):
        raise EvaluationRunError("run ID is invalid")
    return candidate


def _config_sha256(config: AppConfig) -> str:
    try:
        encoded = json.dumps(
            config.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError):
        raise EvaluationRunError("configuration could not be fingerprinted") from None
    return sha256(encoded).hexdigest()


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise EvaluationRunError("run clock must return a timezone-aware datetime")
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _error_type(error: BaseException) -> str:
    candidate = type(error).__name__
    if _ERROR_TYPE_PATTERN.fullmatch(candidate) is None:
        return "Exception"
    return candidate


def _progress(output: Optional[TextIO], message: str) -> None:
    if output is not None:
        print(message, file=output, flush=True)


def _new_private_output_path(value: str | Path) -> Path:
    try:
        path = Path(value).expanduser()
    except (TypeError, ValueError, RuntimeError):
        raise EvaluationRunError("evaluation output path is invalid") from None
    if "\x00" in str(path) or not path.is_absolute() or path.name in {"", ".", ".."}:
        raise EvaluationRunError("evaluation output path must be absolute")
    if ".." in path.parts:
        raise EvaluationRunError("evaluation output path cannot contain '..'")

    parent = path.parent
    try:
        parent_metadata = os.lstat(parent)
    except OSError:
        raise EvaluationRunError(
            "evaluation output parent must already exist"
        ) from None
    if not stat.S_ISDIR(parent_metadata.st_mode):
        raise EvaluationRunError("evaluation output parent must be a directory")
    if stat.S_IMODE(parent_metadata.st_mode) != 0o700:
        raise EvaluationRunError("evaluation output parent must have mode 0700")
    if parent_metadata.st_uid != os.geteuid():
        raise EvaluationRunError("evaluation output parent must be owned by this user")

    current = Path(path.anchor)
    try:
        filesystem_root_uid = os.lstat(current).st_uid
    except OSError:
        raise EvaluationRunError(
            "evaluation output ancestry could not be inspected"
        ) from None
    for part in parent.parts[1:]:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError:
            raise EvaluationRunError(
                "evaluation output ancestry could not be inspected"
            ) from None
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise EvaluationRunError(
                "evaluation output ancestry must be symlink-free directories"
            )
        permissions = stat.S_IMODE(metadata.st_mode)
        if permissions & 0o022:
            sticky_root = (
                bool(permissions & stat.S_ISVTX)
                and metadata.st_uid in {0, filesystem_root_uid}
            )
            if not sticky_root and current != parent:
                raise EvaluationRunError(
                    "evaluation output has an untrusted writable ancestor"
                )
    try:
        os.lstat(path)
    except FileNotFoundError:
        return path
    except OSError:
        raise EvaluationRunError(
            "evaluation output path could not be inspected"
        ) from None
    raise EvaluationRunError("evaluation output already exists")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m oline_hri.evaluation_runner",
        description="Run the gold-free local evaluation harness",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="execute and record the evaluation")
    run.add_argument("--dataset", type=Path, default=None)
    run.add_argument("--config", type=Path, default=None)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument(
        "--strategy",
        action="append",
        choices=CASCADE_STRATEGIES,
        dest="strategies",
        help="cascade strategy; repeat to select several (default: all)",
    )
    run.add_argument("--repetitions", type=int, default=1)
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    """Run the command-line harness without printing prompts or responses."""

    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    args = _build_parser().parse_args(argv)
    try:
        suite = load_evaluation_suite(args.dataset)
        config = load_config(args.config)
        summary = run_evaluation(
            suite,
            config,
            args.output,
            strategies=(
                CASCADE_STRATEGIES
                if args.strategies is None
                else tuple(args.strategies)
            ),
            repetitions=args.repetitions,
            progress=errors,
        )
    except (ConfigError, EvaluationError, EvaluationRunError, ValueError):
        print(
            "evaluation run error: request could not be completed safely",
            file=errors,
        )
        return 2

    print(
        f"evaluation run complete: {summary.run_id} "
        f"({summary.retrieval_records} retrieval, "
        f"{summary.cascade_records} cascade records)",
        file=output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
