"""Validated fixtures for the fictional seven-day evaluation suite.

This module deliberately prepares evaluation inputs only.  It does not run a
model, score an answer, or collect performance and device measurements.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from importlib import resources
import json
from math import isfinite
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Iterable, Optional, Sequence, TextIO
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .embedding import EmbeddingProvider
from .memory import (
    MAX_MEMORY_TEXT_LENGTH,
    MEMORY_KINDS,
    MEMORY_SENSITIVITIES,
    MemoryItem,
    MemoryStore,
)


DEFAULT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[2]
    / "evaluation"
    / "fictional_seven_day_v1.json"
)
MAX_MANIFEST_BYTES = 1_048_576
MAX_EVENTS = 128
MAX_CASES = 512
SCHEMA_VERSION = 1
ANNOTATION_STATUS = "author_gold_pending_independent_review"
PACKAGED_MANIFEST_NAME = "fictional_seven_day_v1.json"

_MEMORY_ID_PATTERN = re.compile(r"mem_[0-9a-f]{32}\Z")
_PROFILE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_IDENTIFIER_PATTERN = re.compile(r"[a-z][a-z0-9_.-]{0,127}\Z")
_MODEL_SIZES = frozenset({"small", "large"})
_OPERATIONS = frozenset({"remember", "correct", "forget"})
_WITHHELD_CATEGORIES = frozenset(
    {
        "prohibited_secret",
        "third_party_private_information",
        "unconfirmed_inference",
    }
)
_CASE_CATEGORIES = frozenset(
    {
        "general",
        "direct_fact",
        "preference",
        "temporal",
        "correction",
        "contradiction",
        "recency",
        "expiration",
        "forgetting",
        "absent",
        "privacy",
        "synthesis",
    }
)
_RUBRIC_MODES = frozenset({"supported", "abstain", "uncertain"})
_TRACKS = frozenset({"all", "router", "rag"})

_TOP_FIELDS = frozenset(
    {
        "schema_version",
        "suite_id",
        "title",
        "fictional",
        "contains_human_participant_data",
        "annotation_status",
        "profile_id",
        "timezone",
        "week_start",
        "week_end",
        "evaluation_at",
        "description",
        "withheld_topics",
        "memory_events",
        "cases",
    }
)
_RECORD_FIELDS = frozenset(
    {
        "id",
        "profile_id",
        "kind",
        "canonical_text",
        "source_turn_id",
        "event_time",
        "sensitivity",
        "consent_status",
        "confidence",
        "importance",
        "status",
        "supersedes_id",
        "valid_from",
        "valid_until",
        "retention_until",
        "created_at",
        "updated_at",
    }
)


class EvaluationError(RuntimeError):
    """Base error for evaluation fixture operations."""


class EvaluationValidationError(EvaluationError):
    """Raised when an evaluation manifest violates its fixed contract."""


class EvaluationReplayError(EvaluationError):
    """Raised when a validated fixture cannot be replayed exactly."""


@dataclass(frozen=True)
class WithheldTopic:
    id: str
    category: str
    description: str
    value_included: bool


@dataclass(frozen=True)
class MemoryEvent:
    id: str
    day: int
    timestamp: str
    operation: str
    record: Optional[MemoryItem] = None
    target_id: Optional[str] = None


@dataclass(frozen=True)
class ExpectedRoute:
    memory_required: bool
    model_size: str


@dataclass(frozen=True)
class RetrievalGold:
    relevant_ids: tuple[str, ...]
    required_ids: tuple[str, ...]
    forbidden_ids: tuple[str, ...]
    top_id: Optional[str]


@dataclass(frozen=True)
class AnswerRubric:
    mode: str
    reference_answer: str
    required_claims: tuple[str, ...]
    forbidden_claims: tuple[str, ...]
    required_citation_ids: tuple[str, ...]


@dataclass(frozen=True)
class EvaluationCase:
    id: str
    category: str
    prompt: str
    expected_route: ExpectedRoute
    retrieval_gold: RetrievalGold
    answer_rubric: AnswerRubric
    tags: tuple[str, ...]


@dataclass(frozen=True)
class EvaluationSuite:
    schema_version: int
    suite_id: str
    title: str
    fictional: bool
    contains_human_participant_data: bool
    annotation_status: str
    profile_id: str
    timezone: str
    week_start: str
    week_end: str
    evaluation_at: str
    description: str
    withheld_topics: tuple[WithheldTopic, ...]
    memory_events: tuple[MemoryEvent, ...]
    cases: tuple[EvaluationCase, ...]


def load_evaluation_suite(
    path: str | Path | None = None,
) -> EvaluationSuite:
    """Load and strictly validate one version-one evaluation manifest."""

    raw = (
        _default_manifest_text()
        if path is None
        else _manifest_file_text(_manifest_path(path))
    )

    try:
        decoded = json.loads(
            raw,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_nonstandard_constant,
        )
    except EvaluationValidationError:
        raise
    except (ValueError, OverflowError, RecursionError):
        raise EvaluationValidationError(
            "evaluation manifest is not valid JSON"
        ) from None
    return _parse_suite(decoded)


def prompt_records(
    suite: EvaluationSuite, *, track: str = "all"
) -> tuple[dict[str, object], ...]:
    """Return canonical prompt records in the manifest's stable case order."""

    _validated_suite_instance(suite)
    selected_track = _track(track)
    selected = (
        suite.cases
        if selected_track == "all"
        else tuple(case for case in suite.cases if selected_track in case.tags)
    )
    return tuple(_prompt_record(suite, case) for case in selected)


def emit_prompts(suite: EvaluationSuite, *, track: str = "all") -> str:
    """Emit deterministic UTF-8 JSON Lines without executing any prompt."""

    records = prompt_records(suite, track=track)
    if not records:
        return ""
    return "".join(
        json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
        for record in records
    )


def materialize_memory_store(
    suite: EvaluationSuite,
    database_path: str | Path,
    *,
    embedder: Optional[EmbeddingProvider] = None,
) -> MemoryStore:
    """Replay the fictional timeline into a new, isolated SQLite database.

    The destination must be an absolute path that does not already exist, below
    an owner-only, symlink-free parent directory.  The returned store retains a
    clock fixed at ``suite.evaluation_at``.
    """

    _validated_suite_instance(suite)
    destination = _new_database_path(database_path)
    created_destination = False
    destination_identity: Optional[tuple[int, int]] = None
    ownership_descriptor: Optional[int] = None
    try:
        try:
            _validate_private_database_parent(destination.parent)
            _new_database_path(destination)
            ownership_descriptor = os.open(
                destination,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            created_destination = True
            metadata = os.fstat(ownership_descriptor)
            destination_identity = (metadata.st_dev, metadata.st_ino)
        except FileExistsError:
            raise EvaluationReplayError(
                "evaluation database path already exists"
            ) from None
        except OSError:
            raise EvaluationReplayError(
                "evaluation database path could not be created"
            ) from None

        clock = _ReplayClock(
            _parse_timestamp(suite.memory_events[0].timestamp, "event")
        )
        generated_ids = iter(
            event.record.id
            for event in suite.memory_events
            if event.record is not None
        )
        store = MemoryStore(
            destination,
            profile_id=suite.profile_id,
            clock=clock,
            memory_id_factory=lambda: next(generated_ids),
            embedder=embedder,
        )
        for event in suite.memory_events:
            _require_database_identity(destination, destination_identity)
            clock.value = _parse_timestamp(event.timestamp, "event timestamp")
            if event.operation == "remember":
                expected = _required_record(event)
                actual = store.remember(
                    expected.canonical_text,
                    kind=expected.kind,
                    sensitivity=expected.sensitivity,
                    importance=expected.importance,
                    source_turn_id=expected.source_turn_id,
                    event_time=expected.event_time,
                    valid_from=expected.valid_from,
                    valid_until=expected.valid_until,
                    retention_until=expected.retention_until,
                )
                if actual != expected:
                    raise EvaluationReplayError(
                        f"memory event {event.id} did not replay exactly"
                    )
            elif event.operation == "correct":
                expected = _required_record(event)
                actual = store.correct(_required_target(event), expected.canonical_text)
                if actual != expected:
                    raise EvaluationReplayError(
                        f"memory event {event.id} did not replay exactly"
                    )
            else:
                expected_chain = _forget_chain(suite.memory_events, event)
                actual_chain = store.forget(_required_target(event))
                if actual_chain != expected_chain:
                    raise EvaluationReplayError(
                        f"memory event {event.id} did not replay exactly"
                    )
            _require_database_identity(destination, destination_identity)
        try:
            next(generated_ids)
        except StopIteration:
            pass
        else:
            raise EvaluationReplayError("memory ID replay did not finish exactly")
        clock.value = _parse_timestamp(suite.evaluation_at, "evaluation_at")
        _require_database_identity(destination, destination_identity)
        os.close(ownership_descriptor)
        ownership_descriptor = None
        return MemoryStore(
            destination,
            profile_id=suite.profile_id,
            clock=clock,
            embedder=embedder,
        )
    except BaseException as exc:
        cleanup_complete = (
            not created_destination
            or _remove_partial_database(
                destination,
                destination_identity,
            )
        )
        descriptor_closed = True
        if ownership_descriptor is not None:
            try:
                os.close(ownership_descriptor)
            except OSError:
                descriptor_closed = False
        if not isinstance(exc, Exception):
            raise
        if created_destination and (not cleanup_complete or not descriptor_closed):
            raise EvaluationReplayError(
                "evaluation memory replay failed and cleanup was incomplete"
            ) from None
        if isinstance(exc, EvaluationReplayError):
            raise
        raise EvaluationReplayError("evaluation memory replay failed") from None


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    """Validate or emit prompts when run as ``python -m oline_hri.evaluation``."""

    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    parser = argparse.ArgumentParser(
        prog="python -m oline_hri.evaluation",
        description="Inspect the fictional seven-day evaluation fixture",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate the manifest")
    validate.add_argument("--dataset", type=Path, default=None)
    prompts = commands.add_parser(
        "prompts", help="emit deterministic prompt JSON Lines"
    )
    prompts.add_argument("--dataset", type=Path, default=None)
    prompts.add_argument("--track", choices=sorted(_TRACKS), default="all")
    args = parser.parse_args(argv)

    try:
        suite = load_evaluation_suite(args.dataset)
        if args.command == "validate":
            print(
                f"evaluation suite valid: {suite.suite_id} "
                f"({len(suite.memory_events)} events, {len(suite.cases)} cases)",
                file=output,
            )
        else:
            output.write(emit_prompts(suite, track=args.track))
        return 0
    except EvaluationError as exc:
        print(f"evaluation error: {exc}", file=errors)
        return 2


def _parse_suite(value: object) -> EvaluationSuite:
    data = _exact_object(value, _TOP_FIELDS, "evaluation manifest")
    schema_version = _integer(
        data["schema_version"], "schema_version", 0, 2_147_483_647
    )
    if schema_version != SCHEMA_VERSION:
        raise EvaluationValidationError(
            f"unsupported evaluation schema_version: {schema_version}"
        )
    suite_id = _identifier(data["suite_id"], "suite_id")
    title = _text(data["title"], "title", 1, 200)
    fictional = _boolean(data["fictional"], "fictional")
    if fictional is not True:
        raise EvaluationValidationError("fictional must be true")
    human_data = _boolean(
        data["contains_human_participant_data"],
        "contains_human_participant_data",
    )
    if human_data is not False:
        raise EvaluationValidationError(
            "contains_human_participant_data must be false"
        )
    annotation_status = _text(
        data["annotation_status"], "annotation_status", 1, 128
    )
    if annotation_status != ANNOTATION_STATUS:
        raise EvaluationValidationError(
            f"annotation_status must be {ANNOTATION_STATUS}"
        )
    profile_id = _profile_id(data["profile_id"])
    timezone_name = _text(data["timezone"], "timezone", 1, 128)
    try:
        local_zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise EvaluationValidationError("timezone is not recognized") from None
    week_start = _date_text(data["week_start"], "week_start")
    week_end = _date_text(data["week_end"], "week_end")
    if date.fromisoformat(week_end) - date.fromisoformat(
        week_start
    ) != timedelta(days=6):
        raise EvaluationValidationError("week_start and week_end must span seven days")
    evaluation_at = _timestamp_text(data["evaluation_at"], "evaluation_at")
    description = _text(data["description"], "description", 1, 4000)

    withheld_values = _array(data["withheld_topics"], "withheld_topics", 1, 64)
    withheld = tuple(_parse_withheld(item) for item in withheld_values)
    event_values = _array(data["memory_events"], "memory_events", 7, MAX_EVENTS)
    events = tuple(_parse_event(item, profile_id) for item in event_values)
    case_values = _array(data["cases"], "cases", 4, MAX_CASES)
    cases = tuple(_parse_case(item) for item in case_values)

    suite = EvaluationSuite(
        schema_version=schema_version,
        suite_id=suite_id,
        title=title,
        fictional=fictional,
        contains_human_participant_data=human_data,
        annotation_status=annotation_status,
        profile_id=profile_id,
        timezone=timezone_name,
        week_start=week_start,
        week_end=week_end,
        evaluation_at=evaluation_at,
        description=description,
        withheld_topics=withheld,
        memory_events=events,
        cases=cases,
    )
    _validate_semantics(suite, local_zone)
    return suite


def _parse_withheld(value: object) -> WithheldTopic:
    fields = frozenset({"id", "category", "description", "value_included"})
    data = _exact_object(value, fields, "withheld topic")
    category = _choice(data["category"], "withheld category", _WITHHELD_CATEGORIES)
    included = _boolean(data["value_included"], "value_included")
    if included:
        raise EvaluationValidationError("withheld topic value_included must be false")
    return WithheldTopic(
        id=_identifier(data["id"], "withheld topic id"),
        category=category,
        description=_text(data["description"], "withheld description", 1, 500),
        value_included=included,
    )


def _parse_event(value: object, profile_id: str) -> MemoryEvent:
    if not isinstance(value, dict):
        raise EvaluationValidationError("memory event must be an object")
    operation = _choice(value.get("operation"), "memory operation", _OPERATIONS)
    common = {"id", "day", "timestamp", "operation"}
    fields = common | (
        {"record"}
        if operation == "remember"
        else {"target_id", "record"}
        if operation == "correct"
        else {"target_id"}
    )
    data = _exact_object(value, frozenset(fields), "memory event")
    record = (
        _parse_record(data["record"], profile_id)
        if "record" in data
        else None
    )
    return MemoryEvent(
        id=_identifier(data["id"], "memory event id"),
        day=_integer(data["day"], "memory event day", 1, 7),
        timestamp=_timestamp_text(data["timestamp"], "memory event timestamp"),
        operation=operation,
        record=record,
        target_id=(
            _memory_id(data["target_id"], "target_id")
            if "target_id" in data
            else None
        ),
    )


def _parse_record(value: object, profile_id: str) -> MemoryItem:
    data = _exact_object(value, _RECORD_FIELDS, "memory record")
    record_profile = _profile_id(data["profile_id"])
    if record_profile != profile_id:
        raise EvaluationValidationError("memory record profile_id does not match suite")
    consent = _text(data["consent_status"], "consent_status", 1, 32)
    if consent != "confirmed":
        raise EvaluationValidationError(
            "memory record consent_status must be confirmed"
        )
    status = _text(data["status"], "memory status", 1, 32)
    if status != "active":
        raise EvaluationValidationError("memory event records must be active")
    confidence = _number(data["confidence"], "confidence", 0.0, 1.0)
    if confidence != 1.0:
        raise EvaluationValidationError("memory record confidence must be 1.0")
    return MemoryItem(
        id=_memory_id(data["id"], "memory record id"),
        profile_id=record_profile,
        kind=_choice(data["kind"], "memory kind", frozenset(MEMORY_KINDS)),
        canonical_text=_text(
            data["canonical_text"], "canonical_text", 1, MAX_MEMORY_TEXT_LENGTH
        ),
        source_turn_id=_optional_text(data["source_turn_id"], "source_turn_id", 128),
        event_time=_optional_timestamp(data["event_time"], "event_time"),
        sensitivity=_choice(
            data["sensitivity"],
            "memory sensitivity",
            frozenset(MEMORY_SENSITIVITIES),
        ),
        consent_status=consent,
        confidence=confidence,
        importance=_integer(data["importance"], "importance", 1, 5),
        status=status,
        supersedes_id=(
            None
            if data["supersedes_id"] is None
            else _memory_id(data["supersedes_id"], "supersedes_id")
        ),
        valid_from=_timestamp_text(data["valid_from"], "valid_from"),
        valid_until=_optional_timestamp(data["valid_until"], "valid_until"),
        retention_until=_optional_timestamp(
            data["retention_until"], "retention_until"
        ),
        created_at=_timestamp_text(data["created_at"], "created_at"),
        updated_at=_timestamp_text(data["updated_at"], "updated_at"),
    )


def _parse_case(value: object) -> EvaluationCase:
    fields = frozenset(
        {
            "id",
            "category",
            "prompt",
            "expected_route",
            "retrieval_gold",
            "answer_rubric",
            "tags",
        }
    )
    data = _exact_object(value, fields, "evaluation case")
    route_data = _exact_object(
        data["expected_route"],
        frozenset({"memory_required", "model_size"}),
        "expected_route",
    )
    route = ExpectedRoute(
        memory_required=_boolean(route_data["memory_required"], "memory_required"),
        model_size=_choice(route_data["model_size"], "model_size", _MODEL_SIZES),
    )
    gold_data = _exact_object(
        data["retrieval_gold"],
        frozenset({"relevant_ids", "required_ids", "forbidden_ids", "top_id"}),
        "retrieval_gold",
    )
    gold = RetrievalGold(
        relevant_ids=_memory_id_array(gold_data["relevant_ids"], "relevant_ids"),
        required_ids=_memory_id_array(gold_data["required_ids"], "required_ids"),
        forbidden_ids=_memory_id_array(gold_data["forbidden_ids"], "forbidden_ids"),
        top_id=(
            None
            if gold_data["top_id"] is None
            else _memory_id(gold_data["top_id"], "top_id")
        ),
    )
    rubric_data = _exact_object(
        data["answer_rubric"],
        frozenset(
            {
                "mode",
                "reference_answer",
                "required_claims",
                "forbidden_claims",
                "required_citation_ids",
            }
        ),
        "answer_rubric",
    )
    rubric = AnswerRubric(
        mode=_choice(rubric_data["mode"], "rubric mode", _RUBRIC_MODES),
        reference_answer=_text(
            rubric_data["reference_answer"], "reference_answer", 1, 1000
        ),
        required_claims=_text_array(
            rubric_data["required_claims"],
            "required_claims",
            500,
            minimum=1,
        ),
        forbidden_claims=_text_array(
            rubric_data["forbidden_claims"],
            "forbidden_claims",
            500,
        ),
        required_citation_ids=_memory_id_array(
            rubric_data["required_citation_ids"], "required_citation_ids"
        ),
    )
    tags = tuple(
        _identifier(item, "case tag")
        for item in _array(data["tags"], "tags", 1, 32)
    )
    _unique(tags, "case tags")
    return EvaluationCase(
        id=_identifier(data["id"], "case id"),
        category=_choice(data["category"], "case category", _CASE_CATEGORIES),
        prompt=_text(data["prompt"], "prompt", 1, 1000),
        expected_route=route,
        retrieval_gold=gold,
        answer_rubric=rubric,
        tags=tags,
    )


def _validate_semantics(suite: EvaluationSuite, local_zone: ZoneInfo) -> None:
    if date.fromisoformat(suite.week_start).weekday() != 0:
        raise EvaluationValidationError("week_start must be a Monday")
    start = date.fromisoformat(suite.week_start)
    end = date.fromisoformat(suite.week_end)
    evaluation_time = _parse_timestamp(suite.evaluation_at, "evaluation_at")
    if evaluation_time.astimezone(local_zone).date() != end:
        raise EvaluationValidationError(
            "evaluation_at must fall on week_end in the suite timezone"
        )
    event_ids = tuple(event.id for event in suite.memory_events)
    case_ids = tuple(case.id for case in suite.cases)
    topic_ids = tuple(topic.id for topic in suite.withheld_topics)
    _unique(event_ids, "memory event ids")
    _unique(case_ids, "case ids")
    _unique((case.prompt for case in suite.cases), "case prompts")
    _unique(topic_ids, "withheld topic ids")
    topic_categories = tuple(topic.category for topic in suite.withheld_topics)
    _unique(topic_categories, "withheld topic categories")
    if set(topic_categories) != _WITHHELD_CATEGORIES:
        raise EvaluationValidationError(
            "withheld topics must cover all privacy categories"
        )

    prior_time: Optional[datetime] = None
    days = set()
    operations = set()
    records: dict[str, MemoryItem] = {}
    active: set[str] = set()
    parents: dict[str, Optional[str]] = {}
    deleted: set[str] = set()
    for event in suite.memory_events:
        timestamp = _parse_timestamp(event.timestamp, "memory event timestamp")
        if prior_time is not None and timestamp <= prior_time:
            raise EvaluationValidationError(
                "memory events must be strictly chronological"
            )
        prior_time = timestamp
        local_day = timestamp.astimezone(local_zone).date()
        expected_day = start + timedelta(days=event.day - 1)
        if local_day != expected_day or not start <= local_day <= end:
            raise EvaluationValidationError(
                "memory event day does not match its timestamp"
            )
        if timestamp > evaluation_time:
            raise EvaluationValidationError("memory event occurs after evaluation_at")
        days.add(event.day)
        operations.add(event.operation)
        if event.operation == "remember":
            record = _required_record(event)
            _validate_event_record(record, event, correct=False)
            if record.id in records or record.supersedes_id is not None:
                raise EvaluationValidationError(
                    "remember event has an invalid record ID or lineage"
                )
            records[record.id] = record
            parents[record.id] = None
            active.add(record.id)
        elif event.operation == "correct":
            target = _required_target(event)
            record = _required_record(event)
            if target not in active or record.id in records:
                raise EvaluationValidationError(
                    "correction target is not uniquely active"
                )
            previous = records[target]
            _validate_event_record(record, event, correct=True)
            if record.supersedes_id != target:
                raise EvaluationValidationError(
                    "correction record must supersede target_id"
                )
            inherited = (
                "profile_id",
                "kind",
                "event_time",
                "sensitivity",
                "importance",
                "valid_until",
                "retention_until",
            )
            if any(
                getattr(record, field) != getattr(previous, field)
                for field in inherited
            ):
                raise EvaluationValidationError(
                    "correction record changed inherited fields"
                )
            if (
                record.source_turn_id is not None
                or record.canonical_text == previous.canonical_text
            ):
                raise EvaluationValidationError(
                    "correction record is not a valid replacement"
                )
            if not _eligible_at(previous, timestamp):
                raise EvaluationValidationError(
                    "correction target is not current at correction time"
                )
            active.remove(target)
            active.add(record.id)
            records[record.id] = record
            parents[record.id] = target
        else:
            target = _required_target(event)
            if target not in active:
                raise EvaluationValidationError("forget target is not active")
            if not _eligible_at(records[target], timestamp):
                raise EvaluationValidationError(
                    "forget target is not current at forget time"
                )
            current: Optional[str] = target
            while current is not None:
                if current in deleted:
                    raise EvaluationValidationError("forget lineage is invalid")
                active.discard(current)
                deleted.add(current)
                current = parents[current]

    if days != set(range(1, 8)):
        raise EvaluationValidationError("memory events must cover all seven days")
    if operations != _OPERATIONS:
        raise EvaluationValidationError(
            "memory events must include remember, correct, and forget"
        )
    retrievable = {
        identifier
        for identifier in active
        if _eligible_at(records[identifier], evaluation_time)
    }

    routes = set()
    categories = set()
    for case in suite.cases:
        routes.add(
            (
                case.expected_route.memory_required,
                case.expected_route.model_size,
            )
        )
        categories.add(case.category)
        if "router" not in case.tags:
            raise EvaluationValidationError("every case must include the router tag")
        has_rag_tag = "rag" in case.tags
        if has_rag_tag != case.expected_route.memory_required:
            raise EvaluationValidationError("rag tag must match memory_required")
        gold = case.retrieval_gold
        relevant = set(gold.relevant_ids)
        required = set(gold.required_ids)
        forbidden = set(gold.forbidden_ids)
        citations = set(case.answer_rubric.required_citation_ids)
        if not required <= relevant or not citations <= relevant:
            raise EvaluationValidationError(
                "required retrieval and citation IDs must be relevant"
            )
        if required != citations:
            raise EvaluationValidationError(
                "required retrieval and citation IDs must match"
            )
        if relevant & forbidden:
            raise EvaluationValidationError(
                "relevant and forbidden IDs must be disjoint"
            )
        if not (relevant | forbidden) <= set(records):
            raise EvaluationValidationError("case refers to an unknown memory ID")
        if not relevant <= retrievable:
            raise EvaluationValidationError(
                "relevant memory ID is not retrievable at evaluation_at"
            )
        if forbidden & retrievable:
            raise EvaluationValidationError(
                "forbidden memory ID is still retrievable at evaluation_at"
            )
        if gold.top_id is not None and gold.top_id not in relevant:
            raise EvaluationValidationError("top_id must be one of relevant_ids")
        if not case.expected_route.memory_required and (
            relevant or required or forbidden or citations or gold.top_id is not None
        ):
            raise EvaluationValidationError(
                "no-memory route cannot have retrieval gold"
            )
        if case.answer_rubric.mode == "abstain" and (
            relevant or required or citations or gold.top_id is not None
        ):
            raise EvaluationValidationError(
                "abstention case cannot require memory evidence"
            )
        if (
            case.answer_rubric.mode == "supported"
            and case.expected_route.memory_required
            and (not required or not citations)
        ):
            raise EvaluationValidationError(
                "supported memory case requires evidence and citations"
            )
        if case.answer_rubric.mode == "uncertain" and (
            case.category != "contradiction"
            or not case.expected_route.memory_required
            or len(required) < 2
            or gold.top_id is not None
        ):
            raise EvaluationValidationError(
                "uncertainty case requires conflicting evidence without one top ID"
            )
        if case.category == "recency" and (
            case.answer_rubric.mode != "supported"
            or not case.expected_route.memory_required
            or len(relevant) < 2
            or len(required) < 2
            or gold.top_id not in required
            or "recency_comparison" not in case.tags
        ):
            raise EvaluationValidationError(
                "recency case must distinguish newer evidence from older context"
            )
        if case.category == "recency":
            dated_required = {
                identifier: _parse_timestamp(
                    records[identifier].event_time,
                    "event_time",
                )
                for identifier in required
                if records[identifier].event_time is not None
            }
            if (
                len(set(dated_required.values())) < 2
                or gold.top_id not in dated_required
                or dated_required[gold.top_id] != max(dated_required.values())
            ):
                raise EvaluationValidationError(
                    "recency top ID must be the newest required dated record"
                )

    if routes != {(False, "small"), (False, "large"), (True, "small"), (True, "large")}:
        raise EvaluationValidationError("cases must cover all four route combinations")
    required_categories = {
        "general",
        "direct_fact",
        "preference",
        "temporal",
        "correction",
        "contradiction",
        "recency",
        "expiration",
        "forgetting",
        "absent",
        "privacy",
        "synthesis",
    }
    if not required_categories <= categories:
        raise EvaluationValidationError(
            "cases do not cover the required scenario categories"
        )
    if not any(case.answer_rubric.mode == "abstain" for case in suite.cases):
        raise EvaluationValidationError("cases must include an abstention rubric")
    privacy_tags = {
        tag
        for case in suite.cases
        if case.category == "privacy"
        for tag in case.tags
    }
    if not _WITHHELD_CATEGORIES <= privacy_tags:
        raise EvaluationValidationError(
            "privacy cases must cover every withheld topic category"
        )


def _validate_event_record(
    record: MemoryItem,
    event: MemoryEvent,
    *,
    correct: bool,
) -> None:
    if record.created_at != event.timestamp or record.updated_at != event.timestamp:
        raise EvaluationValidationError("memory record timestamps must match its event")
    if correct and record.valid_from != event.timestamp:
        raise EvaluationValidationError("correction valid_from must match its event")
    valid_from = _parse_timestamp(record.valid_from, "valid_from")
    for label, value in (
        ("valid_until", record.valid_until),
        ("retention_until", record.retention_until),
    ):
        if value is not None and _parse_timestamp(value, label) < valid_from:
            raise EvaluationValidationError(f"{label} cannot precede valid_from")
    if (
        record.valid_until is not None
        and record.retention_until is not None
        and _parse_timestamp(record.retention_until, "retention_until")
        < _parse_timestamp(record.valid_until, "valid_until")
    ):
        raise EvaluationValidationError(
            "retention_until cannot precede valid_until"
        )


def _eligible_at(record: MemoryItem, instant: datetime) -> bool:
    return (
        _parse_timestamp(record.valid_from, "valid_from") <= instant
        and (
            record.valid_until is None
            or _parse_timestamp(record.valid_until, "valid_until") > instant
        )
        and (
            record.retention_until is None
            or _parse_timestamp(record.retention_until, "retention_until")
            > instant
        )
    )


def _forget_chain(
    events: Sequence[MemoryEvent],
    forget_event: MemoryEvent,
) -> tuple[str, ...]:
    target = _required_target(forget_event)
    parents = {
        event.record.id: event.record.supersedes_id
        for event in events
        if event.record is not None
    }
    result = []
    current: Optional[str] = target
    while current is not None:
        result.append(current)
        current = parents[current]
    return tuple(result)


def _prompt_record(suite: EvaluationSuite, case: EvaluationCase) -> dict[str, object]:
    return {
        "schema_version": suite.schema_version,
        "suite_id": suite.suite_id,
        "fictional": suite.fictional,
        "contains_human_participant_data": suite.contains_human_participant_data,
        "annotation_status": suite.annotation_status,
        "profile_id": suite.profile_id,
        "evaluation_at": suite.evaluation_at,
        "case_id": case.id,
        "category": case.category,
        "prompt": case.prompt,
        "expected_route": {
            "memory_required": case.expected_route.memory_required,
            "model_size": case.expected_route.model_size,
        },
        "retrieval_gold": {
            "relevant_ids": list(case.retrieval_gold.relevant_ids),
            "required_ids": list(case.retrieval_gold.required_ids),
            "forbidden_ids": list(case.retrieval_gold.forbidden_ids),
            "top_id": case.retrieval_gold.top_id,
        },
        "answer_rubric": {
            "mode": case.answer_rubric.mode,
            "reference_answer": case.answer_rubric.reference_answer,
            "required_claims": list(case.answer_rubric.required_claims),
            "forbidden_claims": list(case.answer_rubric.forbidden_claims),
            "required_citation_ids": list(case.answer_rubric.required_citation_ids),
        },
        "tags": list(case.tags),
    }


def _validated_suite_instance(value: object) -> None:
    if not isinstance(value, EvaluationSuite):
        raise EvaluationValidationError("suite must be an EvaluationSuite")
    try:
        manifest_value = json.loads(
            json.dumps(
                asdict(value),
                ensure_ascii=False,
                allow_nan=False,
            )
        )
        for event in manifest_value.get("memory_events", ()):
            if not isinstance(event, dict):
                continue
            if event.get("operation") == "remember":
                event.pop("target_id", None)
            elif event.get("operation") == "forget":
                event.pop("record", None)
    except (TypeError, ValueError, RecursionError):
        raise EvaluationValidationError(
            "suite must contain valid evaluation data"
        ) from None
    if _parse_suite(manifest_value) != value:
        raise EvaluationValidationError(
            "suite does not match its validated representation"
        )


def _required_record(event: MemoryEvent) -> MemoryItem:
    if event.record is None:
        raise EvaluationValidationError("memory event record is missing")
    return event.record


def _required_target(event: MemoryEvent) -> str:
    if event.target_id is None:
        raise EvaluationValidationError("memory event target_id is missing")
    return event.target_id


@dataclass
class _ReplayClock:
    value: datetime

    def __call__(self) -> datetime:
        return self.value


def _new_database_path(value: str | Path) -> Path:
    if not isinstance(value, (str, Path)):
        raise EvaluationReplayError("evaluation database path must be a path")
    if "\x00" in str(value):
        raise EvaluationReplayError(
            "evaluation database path must be an absolute file"
        )
    try:
        path = Path(value)
    except (TypeError, ValueError):
        raise EvaluationReplayError("evaluation database path must be a path") from None
    if not path.is_absolute() or not path.name:
        raise EvaluationReplayError("evaluation database path must be an absolute file")
    if any(os.path.lexists(candidate) for candidate in _database_artifacts(path)):
        raise EvaluationReplayError(
            "evaluation database path or sidecar already exists"
        )
    return path


def _database_artifacts(path: Path) -> tuple[Path, ...]:
    return (
        path,
        Path(f"{path}-wal"),
        Path(f"{path}-shm"),
        Path(f"{path}-journal"),
    )


def _validate_private_database_parent(path: Path) -> None:
    try:
        if path.resolve(strict=True) != path:
            raise EvaluationReplayError(
                "evaluation database parent must not use symlinks"
            )
        effective_user = os.geteuid()
        current = path
        child: Optional[Path] = None
        immediate = True
        while True:
            metadata = current.lstat()
            if not stat.S_ISDIR(metadata.st_mode):
                raise EvaluationReplayError(
                    "evaluation database ancestry must contain only directories"
                )
            permissions = stat.S_IMODE(metadata.st_mode)
            if immediate:
                if metadata.st_uid != effective_user or permissions & 0o077:
                    raise EvaluationReplayError(
                        "evaluation database parent must be an owner-only directory"
                    )
            elif permissions & 0o022:
                child_metadata = child.lstat() if child is not None else None
                if (
                    not permissions & stat.S_ISVTX
                    or child_metadata is None
                    or child_metadata.st_uid != effective_user
                ):
                    raise EvaluationReplayError(
                        "evaluation database ancestry is writable by another user"
                    )
            if current.parent == current:
                break
            child = current
            current = current.parent
            immediate = False
    except EvaluationReplayError:
        raise
    except (OSError, RuntimeError):
        raise EvaluationReplayError(
            "evaluation database parent could not be validated"
        ) from None


def _require_database_identity(
    path: Path,
    expected: Optional[tuple[int, int]],
) -> None:
    try:
        metadata = path.lstat()
    except OSError:
        raise EvaluationReplayError(
            "evaluation database identity changed during replay"
        ) from None
    if (
        expected is None
        or not stat.S_ISREG(metadata.st_mode)
        or (metadata.st_dev, metadata.st_ino) != expected
    ):
        raise EvaluationReplayError(
            "evaluation database identity changed during replay"
        )


def _remove_partial_database(
    path: Path,
    expected_identity: Optional[tuple[int, int]],
) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    if (
        expected_identity is None
        or not stat.S_ISREG(metadata.st_mode)
        or (metadata.st_dev, metadata.st_ino) != expected_identity
    ):
        return False
    if any(
        os.path.lexists(candidate)
        for candidate in _database_artifacts(path)[1:]
    ):
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True


def _manifest_path(value: str | Path) -> Path:
    if (
        not isinstance(value, (str, Path))
        or not str(value).strip()
        or "\x00" in str(value)
    ):
        raise EvaluationValidationError(
            "evaluation manifest path must be a non-empty path"
        )
    return Path(value)


def _default_manifest_text() -> str:
    if DEFAULT_MANIFEST_PATH.is_file():
        return _manifest_file_text(DEFAULT_MANIFEST_PATH)
    try:
        resource = resources.files("oline_hri").joinpath(
            PACKAGED_MANIFEST_NAME
        )
        with resource.open("rb") as stream:
            payload = stream.read(MAX_MANIFEST_BYTES + 1)
    except (FileNotFoundError, OSError):
        raise EvaluationError("evaluation manifest could not be read") from None
    return _manifest_bytes_text(payload)


def _manifest_file_text(path: Path) -> str:
    descriptor: Optional[int] = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
        flags |= getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(path, flags)
        stream = os.fdopen(descriptor, "rb")
        descriptor = None
        with stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise EvaluationValidationError(
                    "evaluation manifest must be a regular file"
                )
            payload = stream.read(MAX_MANIFEST_BYTES + 1)
    except EvaluationError:
        raise
    except (OSError, ValueError):
        raise EvaluationError("evaluation manifest could not be read") from None
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
    return _manifest_bytes_text(payload)


def _manifest_bytes_text(payload: bytes) -> str:
    if len(payload) > MAX_MANIFEST_BYTES:
        raise EvaluationValidationError("evaluation manifest exceeds size limit")
    try:
        return payload.decode("utf-8")
    except UnicodeError:
        raise EvaluationError("evaluation manifest could not be read") from None


def _exact_object(
    value: object,
    fields: frozenset[str],
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvaluationValidationError(f"{label} must be an object")
    missing = fields - set(value)
    unknown = set(value) - fields
    if missing:
        raise EvaluationValidationError(
            f"{label} is missing fields: {', '.join(sorted(missing))}"
        )
    if unknown:
        raise EvaluationValidationError(f"{label} contains unknown fields")
    return value


def _array(value: object, label: str, minimum: int, maximum: int) -> list[Any]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise EvaluationValidationError(
            f"{label} must contain {minimum}-{maximum} items"
        )
    return value


def _text(value: object, label: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str):
        raise EvaluationValidationError(f"{label} must be a string")
    if value != value.strip() or value != unicodedata.normalize("NFC", value):
        raise EvaluationValidationError(f"{label} must be canonical text")
    if not minimum <= len(value) <= maximum:
        raise EvaluationValidationError(f"{label} length is invalid")
    if any(
        unicodedata.category(character) in {"Cc", "Cs", "Zl", "Zp"}
        for character in value
    ):
        raise EvaluationValidationError(
            f"{label} contains control or surrogate characters"
        )
    return value


def _optional_text(value: object, label: str, maximum: int) -> Optional[str]:
    return None if value is None else _text(value, label, 1, maximum)


def _boolean(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise EvaluationValidationError(f"{label} must be a boolean")
    return value


def _integer(value: object, label: str, minimum: int, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise EvaluationValidationError(
            f"{label} must be an integer from {minimum} to {maximum}"
        )
    return value


def _number(value: object, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationValidationError(f"{label} must be a number")
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise EvaluationValidationError(
            f"{label} must be a finite number"
        ) from None
    if not isfinite(result) or not minimum <= result <= maximum:
        raise EvaluationValidationError(f"{label} is outside its allowed range")
    return result


def _choice(value: object, label: str, choices: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise EvaluationValidationError(f"{label} has an invalid value")
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise EvaluationValidationError(f"{label} has an invalid format")
    return value


def _profile_id(value: object) -> str:
    if not isinstance(value, str) or _PROFILE_ID_PATTERN.fullmatch(value) is None:
        raise EvaluationValidationError("profile_id has an invalid format")
    return value


def _memory_id(value: object, label: str) -> str:
    if not isinstance(value, str) or _MEMORY_ID_PATTERN.fullmatch(value) is None:
        raise EvaluationValidationError(f"{label} has an invalid format")
    return value


def _memory_id_array(value: object, label: str) -> tuple[str, ...]:
    items = _array(value, label, 0, 128)
    result = tuple(_memory_id(item, label) for item in items)
    _unique(result, label)
    return result


def _text_array(
    value: object,
    label: str,
    maximum_length: int,
    *,
    minimum: int = 0,
) -> tuple[str, ...]:
    items = _array(value, label, minimum, 64)
    result = tuple(_text(item, label, 1, maximum_length) for item in items)
    _unique(result, label)
    return result


def _track(value: object) -> str:
    return _choice(value, "track", _TRACKS)


def _unique(values: Iterable[str], label: str) -> None:
    values_tuple = tuple(values)
    if len(set(values_tuple)) != len(values_tuple):
        raise EvaluationValidationError(f"{label} must be unique")


def _date_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise EvaluationValidationError(f"{label} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise EvaluationValidationError(f"{label} must be a valid ISO date") from None
    if parsed.isoformat() != value:
        raise EvaluationValidationError(f"{label} must be a canonical ISO date")
    return value


def _timestamp_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise EvaluationValidationError(f"{label} must be a timestamp")
    parsed = _parse_timestamp(value, label)
    canonical = (
        parsed.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
    if value != canonical:
        raise EvaluationValidationError(f"{label} must be a canonical UTC timestamp")
    return value


def _optional_timestamp(value: object, label: str) -> Optional[str]:
    return None if value is None else _timestamp_text(value, label)


def _parse_timestamp(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise EvaluationValidationError(f"{label} must be a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError:
        raise EvaluationValidationError(f"{label} must be a valid timestamp") from None
    if parsed.tzinfo is None:
        raise EvaluationValidationError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvaluationValidationError(
                "evaluation manifest contains a duplicate field"
            )
        result[key] = value
    return result


def _reject_nonstandard_constant(value: str) -> None:
    raise EvaluationValidationError("evaluation manifest contains a nonstandard number")


if __name__ == "__main__":
    raise SystemExit(main())
