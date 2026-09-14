"""Deterministic objective scoring for Step 16 evaluation observations.

Free-text answer correctness is intentionally outside this module.  The scorer
uses the versioned Step 15 gold annotations for objective routing, retrieval,
memory-supply, citation, structured-output, and latency measurements, and it
emits a strategy-blinded worksheet for later human answer review.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
from math import ceil, isfinite
import os
from pathlib import Path
import re
import stat
from typing import Any, Iterable, Mapping, Optional, Sequence
import unicodedata

from .evaluation import EvaluationCase, EvaluationSuite, prompt_records
from .answer_guidance import REFERENCE_IDS
from .operational_planning import OPERATIONAL_CONSTRAINTS


OBSERVATION_SCHEMA_VERSION = 2
SCORING_SCHEMA_VERSION = 2
RETRIEVAL_LIMIT = 5
MAX_OBSERVATION_BYTES = 64 * 1024 * 1024
MAX_REPETITIONS = 100

STRATEGIES = (
    "always_small_no_rag",
    "always_large_no_rag",
    "always_large_with_rag",
    "adaptive",
)

_MEMORY_ID_PATTERN = re.compile(r"mem_[0-9a-f]{32}\Z")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_MODEL_SIZES = frozenset({"small", "large"})
_UTTERANCE_FORMS = frozenset({"question", "statement", "request"})
_STATUSES = frozenset({"ok", "error"})
_ROUTE_PURPOSES = (
    "route_memory_required",
    "route_model_size",
)
_BACKEND_PURPOSES = frozenset((*_ROUTE_PURPOSES, "generation"))
_ERROR_STAGES = frozenset(
    {"route", "retrieval", "generation", "response", "runner"}
)

_HEADER_FIELDS = frozenset(
    {
        "record_type",
        "schema_version",
        "run_id",
        "suite_id",
        "suite_sha256",
        "annotation_status",
        "config_sha256",
        "strategies",
        "retrieval_limit",
        "repetitions",
        "evaluation_temperature",
        "evaluation_seed",
        "started_at",
        "runtime",
    }
)
_SETUP_FIELDS = frozenset(
    {
        "record_type",
        "schema_version",
        "run_id",
        "suite_id",
        "suite_sha256",
        "status",
        "error_type",
        "started_monotonic_ns",
        "finished_monotonic_ns",
        "wall_ns",
        "materialization_wall_ns",
        "passage_embedding_wall_ns",
        "passage_embedding_calls",
    }
)
_RETRIEVAL_FIELDS = frozenset(
    {
        "record_type",
        "schema_version",
        "run_id",
        "suite_id",
        "suite_sha256",
        "repetition",
        "ordinal",
        "case_id",
        "status",
        "error_type",
        "started_monotonic_ns",
        "finished_monotonic_ns",
        "wall_ns",
        "embedding_wall_ns",
        "semantic_search_wall_ns",
        "keyword_search_wall_ns",
        "ranked",
    }
)
_CASE_FIELDS = frozenset(
    {
        "record_type",
        "schema_version",
        "run_id",
        "suite_id",
        "suite_sha256",
        "strategy",
        "repetition",
        "ordinal",
        "case_id",
        "status",
        "error_stage",
        "error_type",
        "route",
        "cascade",
    }
)
_TRAILER_FIELDS = frozenset(
    {
        "record_type",
        "schema_version",
        "run_id",
        "suite_id",
        "expected_retrieval_records",
        "written_retrieval_records",
        "error_retrieval_records",
        "expected_cascade_records",
        "written_cascade_records",
        "error_cascade_records",
        "completed",
        "finished_at",
    }
)
_MATCH_FIELDS = frozenset(
    {
        "id",
        "fused_score",
        "keyword_rank",
        "keyword_position",
        "semantic_score",
        "semantic_position",
    }
)
_GENERATION_FIELDS = frozenset(
    {
        "model",
        "content",
        "done_reason",
        "total_duration_ns",
        "load_duration_ns",
        "prompt_eval_count",
        "prompt_eval_duration_ns",
        "eval_count",
        "eval_duration_ns",
        "generation_tokens_per_second",
    }
)
_ROUTE_FIELDS = frozenset(
    {
        "source",
        "memory_required",
        "model_size",
        "wall_ns",
        "memory_required_generation",
        "model_size_generation",
    }
)
_CASCADE_FIELDS = frozenset(
    {
        "started_monotonic_ns",
        "finished_monotonic_ns",
        "wall_ns",
        "retrieval_invoked",
        "retrieval_wall_ns",
        "retrieval_embedding_wall_ns",
        "retrieval_semantic_search_wall_ns",
        "retrieval_keyword_search_wall_ns",
        "retrieved_ranked",
        "supplied_ids",
        "requested_model",
        "actual_model",
        "fallback_from_model",
        "response",
        "generation",
        "backend_calls",
    }
)
_RESPONSE_FIELDS = frozenset({"speech", "gesture_id", "memory_used"})
_BACKEND_CALL_FIELDS = frozenset(
    {"purpose", "model", "wall_ns", "status", "error_type", "generation"}
)


class EvaluationScoringError(RuntimeError):
    """Raised when an observation stream violates the scoring contract."""


@dataclass(frozen=True)
class ObservationRun:
    """One validated header/body/trailer observation stream."""

    header: Mapping[str, object]
    setups: tuple[Mapping[str, object], ...]
    retrievals: tuple[Mapping[str, object], ...]
    cases: tuple[Mapping[str, object], ...]
    trailer: Mapping[str, object]
    trailer_present: bool = True


def load_observation_jsonl(path: str | Path) -> ObservationRun:
    """Read and strictly validate a bounded regular UTF-8 JSONL file."""

    try:
        source = Path(path)
    except (TypeError, ValueError, RuntimeError):
        raise EvaluationScoringError("observation path is invalid") from None
    descriptor: Optional[int] = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(source, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise EvaluationScoringError("observation path is not a regular file")
        if metadata.st_size > MAX_OBSERVATION_BYTES:
            raise EvaluationScoringError("observation file exceeds size limit")
        chunks = []
        remaining = MAX_OBSERVATION_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    except EvaluationScoringError:
        raise
    except OSError:
        raise EvaluationScoringError(
            "observation file could not be read"
        ) from None
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
    if len(raw) > MAX_OBSERVATION_BYTES:
        raise EvaluationScoringError("observation file exceeds size limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise EvaluationScoringError("observation file is not UTF-8") from None
    return parse_observation_jsonl(text)


def parse_observation_jsonl(text: str) -> ObservationRun:
    """Parse strict JSON Lines while preserving every valid body observation."""

    if not isinstance(text, str):
        raise EvaluationScoringError("observation JSONL must be text")
    if len(text.encode("utf-8")) > MAX_OBSERVATION_BYTES:
        raise EvaluationScoringError("observation JSONL exceeds size limit")
    if not text or not text.endswith("\n"):
        raise EvaluationScoringError(
            "observation JSONL must be non-empty and newline terminated"
        )
    lines = text.splitlines()
    if any(not line for line in lines):
        raise EvaluationScoringError("observation JSONL contains a blank line")

    decoded = tuple(_json_line(line, number) for number, line in enumerate(lines, 1))
    if len(decoded) < 2:
        raise EvaluationScoringError(
            "observation JSONL needs a header and setup observation"
        )
    if decoded[0].get("record_type") != "header":
        raise EvaluationScoringError("first observation record must be the header")
    if decoded[1].get("record_type") != "setup":
        raise EvaluationScoringError(
            "second observation record must be the setup observation"
        )

    header = _header(decoded[0])
    setup = _setup(decoded[1], header)
    retrievals: list[Mapping[str, object]] = []
    cases: list[Mapping[str, object]] = []
    trailer_present = decoded[-1].get("record_type") == "trailer"
    body = decoded[2:-1] if trailer_present else decoded[2:]
    for record in body:
        record_type = record.get("record_type")
        if record_type == "retrieval":
            retrievals.append(_retrieval(record, header))
        elif record_type == "case":
            cases.append(_case(record, header))
        else:
            raise EvaluationScoringError(
                "body observation record_type must be retrieval or case"
            )
    trailer = (
        _trailer(decoded[-1], header, retrievals, cases)
        if trailer_present
        else _partial_trailer(header, retrievals, cases)
    )
    return ObservationRun(
        header=header,
        setups=(setup,),
        retrievals=tuple(retrievals),
        cases=tuple(cases),
        trailer=trailer,
        trailer_present=trailer_present,
    )


def merge_observation_runs(
    runs: Sequence[ObservationRun],
    *,
    retrieval_run_id: Optional[str] = None,
) -> ObservationRun:
    """Merge disjoint strategy artifacts into one deterministic scoring view.

    Every source run remains unchanged.  Strategy sets must be disjoint.  When
    more than one source contains the independent component-retrieval phase,
    ``retrieval_run_id`` is required so repeated measurements are not silently
    collapsed or misrepresented as duplicate protocol slots.
    """

    if isinstance(runs, (str, bytes)) or not isinstance(runs, Sequence) or not runs:
        raise EvaluationScoringError(
            "runs must be a non-empty sequence of ObservationRun values"
        )
    validated = tuple(runs)
    if any(not isinstance(run, ObservationRun) for run in validated):
        raise EvaluationScoringError("runs contains an invalid observation run")

    first = validated[0]
    invariant_fields = (
        "suite_id",
        "suite_sha256",
        "annotation_status",
        "config_sha256",
        "retrieval_limit",
        "repetitions",
        "evaluation_temperature",
        "evaluation_seed",
    )
    for run in validated[1:]:
        for field in invariant_fields:
            if run.header[field] != first.header[field]:
                raise EvaluationScoringError(
                    f"cannot merge runs with different {field}"
                )

    run_ids = tuple(str(run.header["run_id"]) for run in validated)
    if len(run_ids) != len(set(run_ids)):
        raise EvaluationScoringError("cannot merge duplicate run_id values")
    strategy_owner: dict[str, ObservationRun] = {}
    for run in validated:
        for strategy in run.header["strategies"]:
            if strategy in strategy_owner:
                raise EvaluationScoringError(
                    "cannot merge overlapping strategy observations"
                )
            strategy_owner[str(strategy)] = run
    merged_strategies = tuple(
        strategy for strategy in STRATEGIES if strategy in strategy_owner
    )

    retrieval_sources = tuple(run for run in validated if run.retrievals)
    if retrieval_run_id is None:
        if len(retrieval_sources) > 1:
            raise EvaluationScoringError(
                "retrieval_run_id is required when multiple runs contain "
                "component retrieval observations"
            )
        retrieval_source = retrieval_sources[0] if retrieval_sources else None
    else:
        matches = tuple(
            run
            for run in retrieval_sources
            if run.header["run_id"] == retrieval_run_id
        )
        if len(matches) != 1:
            raise EvaluationScoringError(
                "retrieval_run_id does not select exactly one retrieval source"
            )
        retrieval_source = matches[0]

    digest_material = json.dumps(
        sorted(run_ids), ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")
    merged_run_id = "merged_" + sha256(digest_material).hexdigest()[:24]
    selected_retrievals = (
        () if retrieval_source is None else retrieval_source.retrievals
    )

    def normalized(record: Mapping[str, object]) -> Mapping[str, object]:
        item = dict(record)
        item["run_id"] = merged_run_id
        return item

    merged_cases = tuple(
        normalized(record)
        for run in validated
        for record in run.cases
    )
    merged_retrievals = tuple(normalized(record) for record in selected_retrievals)
    merged_setups = tuple(
        normalized(setup) for run in validated for setup in run.setups
    )
    header = dict(first.header)
    header.update(
        {
            "run_id": merged_run_id,
            "strategies": merged_strategies,
            "started_at": min(str(run.header["started_at"]) for run in validated),
            "runtime": {
                "merged_run_ids": sorted(run_ids),
                "retrieval_source_run_id": (
                    None
                    if retrieval_source is None
                    else retrieval_source.header["run_id"]
                ),
                "source_runtime": [
                    {
                        "run_id": run.header["run_id"],
                        "runtime": run.header["runtime"],
                    }
                    for run in sorted(
                        validated, key=lambda item: str(item.header["run_id"])
                    )
                ],
            },
        }
    )
    trailer = {
        "record_type": "trailer",
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "run_id": merged_run_id,
        "suite_id": first.header["suite_id"],
        "expected_retrieval_records": (
            0
            if retrieval_source is None
            else retrieval_source.trailer["expected_retrieval_records"]
        ),
        "written_retrieval_records": len(merged_retrievals),
        "error_retrieval_records": sum(
            item["status"] == "error" for item in merged_retrievals
        ),
        "expected_cascade_records": sum(
            int(run.trailer["expected_cascade_records"]) for run in validated
        ),
        "written_cascade_records": len(merged_cases),
        "error_cascade_records": sum(
            item["status"] == "error" for item in merged_cases
        ),
        "completed": all(bool(run.trailer["completed"]) for run in validated),
        "finished_at": max(
            str(run.trailer["finished_at"]) for run in validated
        ),
    }
    return ObservationRun(
        header=header,
        setups=merged_setups,
        retrievals=merged_retrievals,
        cases=merged_cases,
        trailer=trailer,
        trailer_present=all(run.trailer_present for run in validated),
    )


def score_observations(
    suite: EvaluationSuite, observations: ObservationRun
) -> dict[str, object]:
    """Return a deterministic, objective summary for one observation run."""

    if not isinstance(observations, ObservationRun):
        raise EvaluationScoringError("observations must be an ObservationRun")
    try:
        prompt_records(suite)
    except Exception:
        raise EvaluationScoringError("evaluation suite is invalid") from None
    if observations.header["suite_id"] != suite.suite_id:
        raise EvaluationScoringError("observation suite_id does not match gold suite")
    if observations.header["annotation_status"] != suite.annotation_status:
        raise EvaluationScoringError(
            "observation annotation_status does not match gold suite"
        )
    if observations.header["suite_sha256"] != evaluation_suite_sha256(suite):
        raise EvaluationScoringError(
            "observation suite_sha256 does not match exact gold suite"
        )

    repetitions = int(observations.header["repetitions"])
    selected_strategies = tuple(observations.header["strategies"])
    cases = {case.id: case for case in suite.cases}
    case_order = {case.id: index for index, case in enumerate(suite.cases, 1)}
    rag_cases = tuple(case for case in suite.cases if "rag" in case.tags)

    # Component retrieval is a mandatory phase of every runner artifact,
    # independent of the selected cascade strategies.  In particular, an
    # interruption before the first retrieval record must expose all expected
    # retrieval slots as missing instead of silently disabling this metric.
    retrieval_enabled = True
    scored_retrieval_cases = rag_cases
    retrieval_slots, retrieval_protocol = _primary_slots(
        observations.retrievals,
        expected_keys=(
            (repetition, case.id)
            for repetition in range(1, repetitions + 1)
            for case in scored_retrieval_cases
        ),
        key_fields=("repetition", "case_id"),
        cases=cases,
        case_order=case_order,
    )
    case_slots, case_protocol = _primary_slots(
        observations.cases,
        expected_keys=(
            (strategy, repetition, case.id)
            for strategy in selected_strategies
            for repetition in range(1, repetitions + 1)
            for case in suite.cases
        ),
        key_fields=("strategy", "repetition", "case_id"),
        cases=cases,
        case_order=case_order,
    )

    trailer = observations.trailer
    expected_retrieval_records = len(scored_retrieval_cases) * repetitions
    expected_cascade_records = (
        len(suite.cases) * repetitions * len(selected_strategies)
    )
    trailer_counts_match = bool(
        trailer["expected_retrieval_records"] == expected_retrieval_records
        and trailer["expected_cascade_records"] == expected_cascade_records
    )
    protocol = {
        "complete": bool(
            observations.trailer_present
            and trailer["completed"]
            and trailer_counts_match
            and retrieval_protocol["missing_records"] == 0
            and retrieval_protocol["duplicate_records"] == 0
            and retrieval_protocol["unexpected_records"] == 0
            and retrieval_protocol["ordinal_mismatches"] == 0
            and case_protocol["missing_records"] == 0
            and case_protocol["duplicate_records"] == 0
            and case_protocol["unexpected_records"] == 0
            and case_protocol["ordinal_mismatches"] == 0
        ),
        "retrieval": retrieval_protocol,
        "cascade": case_protocol,
        "trailer_completed": trailer["completed"],
        "trailer_present": observations.trailer_present,
        "trailer_expected_counts_match": trailer_counts_match,
        "all_strategies_present": (
            selected_strategies == STRATEGIES
        ),
    }

    adaptive_enabled = "adaptive" in selected_strategies
    adaptive_slots = {
        (repetition, case.id): case_slots.get(("adaptive", repetition, case.id))
        for repetition in range(1, repetitions + 1)
        for case in suite.cases
    }
    router = _score_router(
        suite.cases if adaptive_enabled else (), repetitions, adaptive_slots
    )
    retrieval = _score_component_retrieval(
        scored_retrieval_cases, repetitions, retrieval_slots
    )
    setup = _score_setups(observations.setups)
    strategies = {
        strategy: _score_strategy(
            strategy, suite.cases, repetitions, case_slots
        )
        for strategy in selected_strategies
    }
    categories = {
        category: _score_category(
            category,
            tuple(case for case in suite.cases if case.category == category),
            repetitions,
            retrieval_slots,
            case_slots,
            selected_strategies=selected_strategies,
            retrieval_enabled=retrieval_enabled,
        )
        for category in sorted({case.category for case in suite.cases})
    }
    review_count = len(blinded_review_records(suite, observations))

    return {
        "schema_version": SCORING_SCHEMA_VERSION,
        "suite_id": suite.suite_id,
        "suite_sha256": observations.header["suite_sha256"],
        "annotation_status": suite.annotation_status,
        "run_id": observations.header["run_id"],
        "config_sha256": observations.header["config_sha256"],
        "repetitions": repetitions,
        "protocol": protocol,
        "objective_metrics": {
            "setup": setup,
            "router": router,
            "component_retrieval": retrieval,
            "strategies": strategies,
            "category_slices": categories,
        },
        "answer_quality": {
            "status": "pending_blinded_human_review",
            "review_items": review_count,
            "free_text_answer_accuracy": None,
            "hallucination_rate": None,
            "note": (
                "Free-text correctness and hallucination are not inferred by "
                "this objective scorer. Complete the blinded review sheet."
            ),
        },
        "definitions": {
            "failed_or_missing_attempts": (
                "Failed or missing expected slots remain in objective metric "
                "denominators; duplicate slots never inflate primary metrics."
            ),
            "recall_at_k": (
                "Macro mean of relevant IDs retrieved in the first k divided "
                "by all relevant IDs, over non-empty-gold RAG cases."
            ),
            "mrr": (
                "Mean reciprocal rank of the first relevant ID over "
                "non-empty-gold RAG cases."
            ),
            "answerable_precision_at_5": (
                "Precision among returned top-five IDs for the 11 non-empty-"
                "gold RAG cases only."
            ),
            "overall_micro_precision_at_5": (
                "Relevant returned IDs divided by all returned IDs across all "
                "16 RAG cases, including returns for the five empty-gold cases."
            ),
            "overall_macro_precision_at_5": (
                "Per-case precision across all 16 RAG cases. A successful empty "
                "result for empty gold scores one; a missing/error attempt or an "
                "empty result for non-empty gold scores zero."
            ),
            "percentile": (
                "Nearest-rank percentile: sorted sample at ceil(p*n), with "
                "one-based ranks. Only present non-negative timing samples count."
            ),
            "small_model_rate": (
                "Fraction of expected adaptive attempts routed to the small "
                "generator; the two separate small-model classifier calls are "
                "not counted."
            ),
            "actual_model_rate": (
                "Fraction of expected attempts whose final successful generator "
                "was that model; failed invocations have no successful actual model."
            ),
            "model_invocation_rate": (
                "Fraction of expected attempts with at least one generator call "
                "to that model, including failed calls. A large-to-small fallback "
                "counts in both model invocation rates. Router calls are excluded."
            ),
            "purpose_latency": (
                "Backend and Ollama duration distributions distinguish the "
                "memory-required classifier, model-size classifier, and answer "
                "generation. Aggregate route distributions include both "
                "classifier calls."
            ),
        },
    }


def evaluation_suite_sha256(suite: EvaluationSuite) -> str:
    """Hash the exact validated gold semantics independently of file layout."""

    try:
        prompt_records(suite)
        encoded = json.dumps(
            asdict(suite),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except Exception:
        raise EvaluationScoringError("evaluation suite is invalid") from None
    return sha256(encoded).hexdigest()


def canonical_summary_json(summary: Mapping[str, object]) -> str:
    """Serialize a scoring summary as canonical, newline-terminated JSON."""

    _json_metadata(summary, "summary")
    try:
        return (
            json.dumps(
                summary,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
    except (TypeError, ValueError, OverflowError):
        raise EvaluationScoringError("summary is not canonical JSON data") from None


def blinded_review_records(
    suite: EvaluationSuite, observations: ObservationRun
) -> tuple[dict[str, object], ...]:
    """Build one blinded answer-review item for every expected case slot.

    Missing, failed, and duplicate observations are represented as explicit
    non-answers and marked automatically incorrect.  This keeps the human
    review denominator equal to the declared protocol denominator instead of
    silently dropping attempts that did not produce a response.
    """

    try:
        prompt_records(suite)
    except Exception:
        raise EvaluationScoringError("evaluation suite is invalid") from None
    if not isinstance(observations, ObservationRun):
        raise EvaluationScoringError("observations must be an ObservationRun")

    selected_strategies = tuple(observations.header["strategies"])
    repetitions = int(observations.header["repetitions"])
    expected_keys = {
        (strategy, repetition, case.id)
        for strategy in selected_strategies
        for repetition in range(1, repetitions + 1)
        for case in suite.cases
    }
    grouped: defaultdict[
        tuple[str, int, str], list[Mapping[str, object]]
    ] = defaultdict(list)
    for observation in observations.cases:
        key = (
            str(observation["strategy"]),
            int(observation["repetition"]),
            str(observation["case_id"]),
        )
        if key in expected_keys:
            grouped[key].append(observation)

    records = []
    run_id = str(observations.header["run_id"])
    for strategy in selected_strategies:
        for repetition in range(1, repetitions + 1):
            for case in suite.cases:
                key = (strategy, repetition, case.id)
                candidates = grouped.get(key, [])
                response_status = "answered"
                response_speech: Optional[str] = None
                automatic_note: Optional[str] = None
                if not candidates:
                    response_status = "missing_observation"
                    automatic_note = (
                        "Automatically incorrect: the expected attempt "
                        "observation is missing."
                    )
                elif len(candidates) > 1:
                    response_status = "duplicate_observation"
                    automatic_note = (
                        "Automatically incorrect: duplicate observations make "
                        "the expected attempt ambiguous."
                    )
                elif candidates[0]["status"] != "ok":
                    response_status = "failed_observation"
                    automatic_note = (
                        "Automatically incorrect: execution failed before a "
                        "reviewable answer was recorded."
                    )
                else:
                    cascade = candidates[0]["cascade"]
                    response = (
                        cascade.get("response")
                        if isinstance(cascade, Mapping)
                        else None
                    )
                    speech = (
                        response.get("speech")
                        if isinstance(response, Mapping)
                        else None
                    )
                    if isinstance(speech, str) and speech:
                        response_speech = speech
                    else:
                        response_status = "failed_observation"
                        automatic_note = (
                            "Automatically incorrect: execution did not record "
                            "a reviewable answer."
                        )

                opaque = json.dumps(
                    [run_id, strategy, repetition, case.id],
                    ensure_ascii=True,
                    separators=(",", ":"),
                )
                review_id = (
                    "review_"
                    + sha256(opaque.encode("utf-8")).hexdigest()[:24]
                )
                automatically_incorrect = response_status != "answered"
                records.append(
                    {
                        "schema_version": SCORING_SCHEMA_VERSION,
                        "review_id": review_id,
                        "prompt": case.prompt,
                        "response_status": response_status,
                        "response_speech": response_speech,
                        "rubric": {
                            "mode": case.answer_rubric.mode,
                            "reference_answer": (
                                case.answer_rubric.reference_answer
                            ),
                            "required_claims": list(
                                case.answer_rubric.required_claims
                            ),
                            "forbidden_claims": list(
                                case.answer_rubric.forbidden_claims
                            ),
                        },
                        "judgment": {
                            "required_claims_met": (
                                False if automatically_incorrect else None
                            ),
                            "forbidden_claim_present": (
                                False if automatically_incorrect else None
                            ),
                            "unsupported_factual_claim_present": (
                                False if automatically_incorrect else None
                            ),
                            "overall_correct": (
                                False if automatically_incorrect else None
                            ),
                            "notes": automatic_note,
                        },
                    }
                )
    return tuple(sorted(records, key=lambda item: str(item["review_id"])))


def emit_blinded_review_sheet(
    suite: EvaluationSuite, observations: ObservationRun
) -> str:
    """Emit the strategy-blinded answer worksheet as canonical JSON Lines."""

    return "".join(
        json.dumps(
            record,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
        for record in blinded_review_records(suite, observations)
    )


def render_summary_markdown(summary: Mapping[str, object]) -> str:
    """Render the objective summary without inventing free-text quality claims."""

    _json_metadata(summary, "summary")
    objective = _mapping(summary.get("objective_metrics"), "objective_metrics")
    setup = _mapping(objective.get("setup"), "setup metrics")
    router = _mapping(objective.get("router"), "router metrics")
    retrieval = _mapping(
        objective.get("component_retrieval"), "component retrieval metrics"
    )
    strategies = _mapping(objective.get("strategies"), "strategy metrics")
    protocol = _mapping(summary.get("protocol"), "protocol")
    answer_quality = _mapping(summary.get("answer_quality"), "answer_quality")

    lines = [
        "# Step 16 objective evaluation summary",
        "",
        f"- Run: `{_md(summary.get('run_id'))}`",
        f"- Suite: `{_md(summary.get('suite_id'))}`",
        f"- Protocol complete: `{str(bool(protocol.get('complete'))).lower()}`",
        f"- Gold annotation status: `{_md(summary.get('annotation_status'))}`",
        "",
        "## Setup and materialization",
        "",
        "| Metric | Result |",
        "| --- | ---: |",
        f"| Setup error rate | {_ratio_md(setup.get('error_rate'))} |",
        f"| Setup wall p50 | {_percentile_md(setup.get('wall_ns'), 'p50_ns')} |",
        "| Materialization wall p50 | "
        f"{_percentile_md(setup.get('materialization_wall_ns'), 'p50_ns')} |",
        "| Passage embedding wall p50 | "
        f"{_percentile_md(setup.get('passage_embedding_wall_ns'), 'p50_ns')} |",
        "| Passage embedding calls | "
        f"{int(setup.get('passage_embedding_calls', 0))} |",
        "",
        "## Router",
        "",
        "| Metric | Result |",
        "| --- | ---: |",
        "| Memory decision accuracy | "
        f"{_ratio_md(router.get('memory_accuracy'))} |",
        f"| Model-size accuracy | {_ratio_md(router.get('model_accuracy'))} |",
        f"| Joint route accuracy | {_ratio_md(router.get('joint_accuracy'))} |",
        "| Small-generator route rate | "
        f"{_ratio_md(router.get('small_model_rate'))} |",
        "| Incorrect escalations | "
        f"{_ratio_md(router.get('incorrect_escalation_rate'))} |",
        "| Incorrect non-escalations | "
        f"{_ratio_md(router.get('incorrect_non_escalation_rate'))} |",
        f"| Attempt errors | {_ratio_md(router.get('attempt_error_rate'))} |",
        f"| Generation fallback | {_ratio_md(router.get('fallback_rate'))} |",
        "",
        "## Component retrieval",
        "",
        "| Metric | Result |",
        "| --- | ---: |",
        f"| Recall@1 | {_mean_md(retrieval.get('recall_at_1'))} |",
        f"| Recall@3 | {_mean_md(retrieval.get('recall_at_3'))} |",
        f"| Recall@5 | {_mean_md(retrieval.get('recall_at_5'))} |",
        f"| Mean reciprocal rank | {_mean_md(retrieval.get('mrr'))} |",
        "| Required-ID coverage@5 | "
        f"{_mean_md(retrieval.get('required_coverage_at_5'))} |",
        "| Answerable-only micro precision@5 | "
        f"{_ratio_md(retrieval.get('answerable_micro_precision_at_5'))} |",
        "| Overall micro precision@5 (all 16 RAG cases) | "
        f"{_ratio_md(retrieval.get('overall_micro_precision_at_5'))} |",
        "| Overall macro precision@5 (all 16 RAG cases) | "
        f"{_mean_md(retrieval.get('overall_macro_precision_at_5'))} |",
        "| Empty-gold false retrieval | "
        f"{_ratio_md(retrieval.get('empty_gold_false_retrieval_rate'))} |",
        "| Forbidden-ID hit rate | "
        f"{_ratio_md(retrieval.get('forbidden_hit_rate'))} |",
        "",
        "## Cascade strategies",
        "",
        "| Strategy | Structured success | Supplied-memory precision | "
        "Citation precision | Citation recall | Error rate | Fallback rate | "
        "E2E p50 | E2E p95 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for strategy in STRATEGIES:
        raw_metrics = strategies.get(strategy)
        if not isinstance(raw_metrics, Mapping):
            lines.append(
                f"| `{strategy}` | N/A | N/A | N/A | N/A | N/A | N/A | "
                "N/A | N/A |"
            )
            continue
        metrics = raw_metrics
        latency = _mapping(metrics.get("latency"), "strategy latency")
        supplied_metrics = _mapping(
            metrics.get("supplied_memory"), "supplied-memory metrics"
        )
        citation_metrics = _mapping(
            metrics.get("citation"), "citation metrics"
        )
        cascade_latency = latency.get("cascade_wall_ns")
        lines.append(
            "| "
            + " | ".join(
                (
                    f"`{strategy}`",
                    _ratio_md(metrics.get("structured_success_rate")),
                    _ratio_md(supplied_metrics.get("micro_precision")),
                    _ratio_md(citation_metrics.get("micro_precision")),
                    _ratio_md(citation_metrics.get("micro_recall")),
                    _ratio_md(metrics.get("attempt_error_rate")),
                    _ratio_md(metrics.get("fallback_rate")),
                    _percentile_md(cascade_latency, "p50_ns"),
                    _percentile_md(cascade_latency, "p95_ns"),
                )
            )
            + " |"
        )

    lines.extend(
        (
            "",
            "## Generator invocation exposure",
            "",
            "These rates count attempted generator calls, including failures. A "
            "large-to-small fallback appears in both columns; router calls are excluded.",
            "",
            "| Strategy | Small generator invoked | Large generator invoked |",
            "| --- | ---: | ---: |",
        )
    )
    for strategy in STRATEGIES:
        raw_metrics = strategies.get(strategy)
        if not isinstance(raw_metrics, Mapping):
            lines.append(f"| `{strategy}` | N/A | N/A |")
            continue
        lines.append(
            f"| `{strategy}` | "
            f"{_ratio_md(raw_metrics.get('small_model_invocation_rate'))} | "
            f"{_ratio_md(raw_metrics.get('large_model_invocation_rate'))} |"
        )

    lines.extend(
        (
            "",
            "## Free-text answer review",
            "",
            f"Status: `{_md(answer_quality.get('status'))}`. ",
            "",
            str(answer_quality.get("note", "")),
            "",
            "No answer-accuracy or hallucination result is reported until the "
            "blinded human review sheet is completed.",
            "",
        )
    )
    return "\n".join(lines)


def _score_setups(
    setups: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    return {
        "observations": len(setups),
        "error_rate": _ratio(
            sum(setup["status"] == "error" for setup in setups), len(setups)
        ),
        "passage_embedding_calls": sum(
            int(setup["passage_embedding_calls"]) for setup in setups
        ),
        "wall_ns": _percentiles(
            [int(setup["wall_ns"]) for setup in setups]
        ),
        "materialization_wall_ns": _percentiles(
            [
                int(setup["materialization_wall_ns"])
                for setup in setups
                if isinstance(setup["materialization_wall_ns"], int)
            ]
        ),
        "passage_embedding_wall_ns": _percentiles(
            [
                int(setup["passage_embedding_wall_ns"])
                for setup in setups
                if isinstance(setup["passage_embedding_wall_ns"], int)
            ]
        ),
    }


def _score_router(
    suite_cases: Sequence[EvaluationCase],
    repetitions: int,
    slots: Mapping[tuple[int, str], Optional[Mapping[str, object]]],
) -> dict[str, object]:
    total = len(suite_cases) * repetitions
    memory_correct = 0
    model_correct = 0
    joint_correct = 0
    small = 0
    large = 0
    route_errors = 0
    attempt_errors = 0
    fallbacks = 0
    escalations = 0
    non_escalations = 0
    memory_confusion = {
        "not_required": {"not_required": 0, "required": 0, "error": 0},
        "required": {"not_required": 0, "required": 0, "error": 0},
    }
    model_confusion = {
        "small": {"small": 0, "large": 0, "error": 0},
        "large": {"small": 0, "large": 0, "error": 0},
    }

    for repetition in range(1, repetitions + 1):
        for case in suite_cases:
            observation = slots.get((repetition, case.id))
            if observation is None or observation["status"] == "error":
                attempt_errors += 1
            route = None if observation is None else observation["route"]
            expected_memory = (
                "required" if case.expected_route.memory_required else "not_required"
            )
            expected_model = case.expected_route.model_size
            if not isinstance(route, Mapping):
                route_errors += 1
                memory_confusion[expected_memory]["error"] += 1
                model_confusion[expected_model]["error"] += 1
            else:
                predicted_memory = (
                    "required" if route["memory_required"] else "not_required"
                )
                predicted_model = str(route["model_size"])
                memory_confusion[expected_memory][predicted_memory] += 1
                model_confusion[expected_model][predicted_model] += 1
                memory_match = (
                    bool(route["memory_required"])
                    == case.expected_route.memory_required
                )
                model_match = predicted_model == expected_model
                memory_correct += int(memory_match)
                model_correct += int(model_match)
                joint_correct += int(memory_match and model_match)
                small += int(predicted_model == "small")
                large += int(predicted_model == "large")
                escalations += int(
                    expected_model == "small" and predicted_model == "large"
                )
                non_escalations += int(
                    expected_model == "large" and predicted_model == "small"
                )
            cascade = None if observation is None else observation["cascade"]
            if isinstance(cascade, Mapping):
                fallbacks += int(cascade["fallback_from_model"] is not None)

    expected_small = repetitions * sum(
        case.expected_route.model_size == "small" for case in suite_cases
    )
    expected_large = total - expected_small
    return {
        "expected_attempts": total,
        "route_error_count": route_errors,
        "memory_accuracy": _ratio(memory_correct, total),
        "model_accuracy": _ratio(model_correct, total),
        "joint_accuracy": _ratio(joint_correct, total),
        "small_model_rate": _ratio(small, total),
        "large_model_rate": _ratio(large, total),
        "attempt_error_rate": _ratio(attempt_errors, total),
        "fallback_rate": _ratio(fallbacks, total),
        "incorrect_escalation_rate": _ratio(escalations, expected_small),
        "incorrect_non_escalation_rate": _ratio(
            non_escalations, expected_large
        ),
        "memory_confusion": memory_confusion,
        "model_confusion": model_confusion,
    }


def _score_component_retrieval(
    suite_cases: Sequence[EvaluationCase],
    repetitions: int,
    slots: Mapping[tuple[int, str], Optional[Mapping[str, object]]],
) -> dict[str, object]:
    answerable = tuple(
        case for case in suite_cases if case.retrieval_gold.relevant_ids
    )
    empty_gold = tuple(
        case for case in suite_cases if not case.retrieval_gold.relevant_ids
    )
    recalls: dict[int, list[float]] = {1: [], 3: [], 5: []}
    reciprocal_ranks: list[float] = []
    required_coverage: list[float] = []
    answerable_precisions: list[float] = []
    answerable_micro_relevant = 0
    answerable_micro_returned = 0
    overall_precisions: list[float] = []
    overall_micro_relevant = 0
    overall_micro_returned = 0
    top_correct = 0
    top_denominator = 0
    forbidden_cases = 0
    false_empty = 0
    errors = 0
    wall_samples: list[int] = []
    embedding_samples: list[int] = []
    semantic_search_samples: list[int] = []
    keyword_search_samples: list[int] = []

    for repetition in range(1, repetitions + 1):
        for case in suite_cases:
            observation = slots.get((repetition, case.id))
            if observation is None or observation["status"] == "error":
                errors += 1
                ids: tuple[str, ...] = ()
            else:
                ranked = observation["ranked"]
                assert isinstance(ranked, tuple)
                ids = tuple(str(match["id"]) for match in ranked)
            if (
                observation is not None
                and isinstance(observation["started_monotonic_ns"], int)
                and isinstance(observation["finished_monotonic_ns"], int)
                and isinstance(observation["wall_ns"], int)
            ):
                wall_samples.append(int(observation["wall_ns"]))
                if isinstance(observation["embedding_wall_ns"], int):
                    embedding_samples.append(int(observation["embedding_wall_ns"]))
                if isinstance(observation["semantic_search_wall_ns"], int):
                    semantic_search_samples.append(
                        int(observation["semantic_search_wall_ns"])
                    )
                if isinstance(observation["keyword_search_wall_ns"], int):
                    keyword_search_samples.append(
                        int(observation["keyword_search_wall_ns"])
                    )

            relevant = set(case.retrieval_gold.relevant_ids)
            required = set(case.retrieval_gold.required_ids)
            forbidden = set(case.retrieval_gold.forbidden_ids)
            relevant_returned = len(set(ids[:5]) & relevant)
            overall_micro_relevant += relevant_returned
            overall_micro_returned += len(ids[:5])
            if ids[:5]:
                overall_precisions.append(relevant_returned / len(ids[:5]))
            else:
                # A successful abstention is exact for an empty-gold query;
                # failed/missing attempts remain zero in this case macro.
                overall_precisions.append(
                    1.0
                    if (
                        not relevant
                        and observation is not None
                        and observation["status"] == "ok"
                    )
                    else 0.0
                )
            if relevant:
                for limit in recalls:
                    recalls[limit].append(
                        len(set(ids[:limit]) & relevant) / len(relevant)
                    )
                first = next(
                    (
                        index
                        for index, memory_id in enumerate(ids, 1)
                        if memory_id in relevant
                    ),
                    None,
                )
                reciprocal_ranks.append(0.0 if first is None else 1.0 / first)
                required_coverage.append(
                    len(set(ids[:5]) & required) / len(required)
                )
                answerable_precisions.append(
                    relevant_returned / len(ids[:5]) if ids[:5] else 0.0
                )
                answerable_micro_relevant += relevant_returned
                answerable_micro_returned += len(ids[:5])
            else:
                false_empty += int(bool(ids))
            if case.retrieval_gold.top_id is not None:
                top_denominator += 1
                top_correct += int(
                    bool(ids) and ids[0] == case.retrieval_gold.top_id
                )
            forbidden_cases += int(bool(set(ids[:5]) & forbidden))

    return {
        "expected_attempts": len(suite_cases) * repetitions,
        "answerable_attempts": len(answerable) * repetitions,
        "empty_gold_attempts": len(empty_gold) * repetitions,
        "error_rate": _ratio(errors, len(suite_cases) * repetitions),
        "recall_at_1": _mean(recalls[1]),
        "recall_at_3": _mean(recalls[3]),
        "recall_at_5": _mean(recalls[5]),
        "mrr": _mean(reciprocal_ranks),
        "required_coverage_at_5": _mean(required_coverage),
        "answerable_macro_precision_at_5": _mean(answerable_precisions),
        "answerable_micro_precision_at_5": _ratio(
            answerable_micro_relevant, answerable_micro_returned
        ),
        "overall_macro_precision_at_5": _mean(overall_precisions),
        "overall_micro_precision_at_5": _ratio(
            overall_micro_relevant, overall_micro_returned
        ),
        "top_id_accuracy": _ratio(top_correct, top_denominator),
        "empty_gold_false_retrieval_rate": _ratio(
            false_empty, len(empty_gold) * repetitions
        ),
        "forbidden_hit_rate": _ratio(
            forbidden_cases, len(suite_cases) * repetitions
        ),
        "latency": {
            "embedding_wall_ns": _percentiles(embedding_samples),
            "semantic_search_wall_ns": _percentiles(
                semantic_search_samples
            ),
            "keyword_search_wall_ns": _percentiles(keyword_search_samples),
            "retrieval_wall_ns": _percentiles(wall_samples),
        },
    }


def _score_strategy(
    strategy: str,
    suite_cases: Sequence[EvaluationCase],
    repetitions: int,
    slots: Mapping[tuple[str, int, str], Optional[Mapping[str, object]]],
) -> dict[str, object]:
    total = len(suite_cases) * repetitions
    errors = 0
    structured = 0
    fallbacks = 0
    actual_small = 0
    actual_large = 0
    small_invocation_attempts = 0
    large_invocation_attempts = 0
    supplied_relevant = 0
    supplied_total = 0
    supplied_macro: list[float] = []
    supplied_required: list[float] = []
    supplied_forbidden = 0
    empty_false = 0
    rag_empty_false = 0
    empty_denominator = 0
    rag_empty_denominator = 0
    cited_relevant = 0
    cited_total = 0
    cited_required = 0
    required_citation_total = 0
    citation_macro_precision: list[float] = []
    citation_macro_recall: list[float] = []
    forbidden_citations = 0
    unexpected_citation_cases = 0
    cascade_wall: list[int] = []
    route_wall: list[int] = []
    retrieval_wall: list[int] = []
    retrieval_embedding_wall: list[int] = []
    retrieval_semantic_search_wall: list[int] = []
    retrieval_keyword_search_wall: list[int] = []
    backend_wall: dict[str, list[int]] = {
        purpose: [] for purpose in _BACKEND_PURPOSES
    }
    ollama_total: dict[str, list[int]] = {
        purpose: [] for purpose in _BACKEND_PURPOSES
    }
    ollama_load: dict[str, list[int]] = {
        purpose: [] for purpose in _BACKEND_PURPOSES
    }
    ollama_prompt_eval: dict[str, list[int]] = {
        purpose: [] for purpose in _BACKEND_PURPOSES
    }
    ollama_eval: dict[str, list[int]] = {
        purpose: [] for purpose in _BACKEND_PURPOSES
    }

    for repetition in range(1, repetitions + 1):
        for case in suite_cases:
            observation = slots.get((strategy, repetition, case.id))
            if observation is None or observation["status"] == "error":
                errors += 1
            route = None if observation is None else observation["route"]
            if isinstance(route, Mapping) and isinstance(route["wall_ns"], int):
                route_wall.append(int(route["wall_ns"]))
            cascade = None if observation is None else observation["cascade"]
            supplied: tuple[str, ...] = ()
            citations: tuple[str, ...] = ()
            if isinstance(cascade, Mapping):
                if isinstance(cascade["wall_ns"], int):
                    cascade_wall.append(int(cascade["wall_ns"]))
                if isinstance(cascade["retrieval_wall_ns"], int):
                    retrieval_wall.append(int(cascade["retrieval_wall_ns"]))
                if isinstance(cascade["retrieval_embedding_wall_ns"], int):
                    retrieval_embedding_wall.append(
                        int(cascade["retrieval_embedding_wall_ns"])
                    )
                if isinstance(
                    cascade["retrieval_semantic_search_wall_ns"], int
                ):
                    retrieval_semantic_search_wall.append(
                        int(cascade["retrieval_semantic_search_wall_ns"])
                    )
                if isinstance(
                    cascade["retrieval_keyword_search_wall_ns"], int
                ):
                    retrieval_keyword_search_wall.append(
                        int(cascade["retrieval_keyword_search_wall_ns"])
                    )
                supplied = tuple(str(item) for item in cascade["supplied_ids"])
                actual = cascade["actual_model"]
                actual_small += int(actual == "qwen3:0.6b")
                actual_large += int(actual in {"qwen3:1.7b", "qwen3:4b"})
                fallbacks += int(cascade["fallback_from_model"] is not None)
                response = cascade["response"]
                if (
                    observation is not None
                    and observation["status"] == "ok"
                    and isinstance(response, Mapping)
                ):
                    structured += 1
                if isinstance(response, Mapping):
                    citations = tuple(str(item) for item in response["memory_used"])
                generation_calls = tuple(
                    call
                    for call in cascade["backend_calls"]
                    if call["purpose"] == "generation"
                )
                small_invocation_attempts += int(
                    any(call["model"] == "qwen3:0.6b" for call in generation_calls)
                )
                large_invocation_attempts += int(
                    any(
                        call["model"] in {"qwen3:1.7b", "qwen3:4b"}
                        for call in generation_calls
                    )
                )
                for call in cascade["backend_calls"]:
                    purpose = str(call["purpose"])
                    if isinstance(call["wall_ns"], int):
                        backend_wall[purpose].append(int(call["wall_ns"]))
                    generation = call["generation"]
                    if isinstance(generation, Mapping):
                        ollama_total[purpose].append(
                            int(generation["total_duration_ns"])
                        )
                        ollama_load[purpose].append(
                            int(generation["load_duration_ns"])
                        )
                        ollama_prompt_eval[purpose].append(
                            int(generation["prompt_eval_duration_ns"])
                        )
                        ollama_eval[purpose].append(
                            int(generation["eval_duration_ns"])
                        )

            relevant = set(case.retrieval_gold.relevant_ids)
            required = set(case.retrieval_gold.required_ids)
            forbidden = set(case.retrieval_gold.forbidden_ids)
            supplied_hits = len(set(supplied) & relevant)
            supplied_relevant += supplied_hits
            supplied_total += len(supplied)
            if relevant or supplied:
                supplied_macro.append(
                    supplied_hits / len(supplied) if supplied else 0.0
                )
            if required:
                supplied_required.append(
                    len(set(supplied) & required) / len(required)
                )
            supplied_forbidden += int(bool(set(supplied) & forbidden))
            if not relevant:
                empty_denominator += 1
                empty_false += int(bool(supplied))
                if "rag" in case.tags:
                    rag_empty_denominator += 1
                    rag_empty_false += int(bool(supplied))

            required_citations = set(case.answer_rubric.required_citation_ids)
            citation_relevant_hits = len(set(citations) & relevant)
            cited_relevant += citation_relevant_hits
            cited_total += len(citations)
            cited_required += len(set(citations) & required_citations)
            required_citation_total += len(required_citations)
            if relevant or citations:
                citation_macro_precision.append(
                    citation_relevant_hits / len(citations) if citations else 0.0
                )
            if required_citations:
                citation_macro_recall.append(
                    len(set(citations) & required_citations)
                    / len(required_citations)
                )
            forbidden_citations += int(bool(set(citations) & forbidden))
            unexpected_citation_cases += int(not relevant and bool(citations))

    return {
        "expected_attempts": total,
        "attempt_error_rate": _ratio(errors, total),
        "structured_success_rate": _ratio(structured, total),
        "fallback_rate": _ratio(fallbacks, total),
        "actual_small_model_rate": _ratio(actual_small, total),
        "actual_large_model_rate": _ratio(actual_large, total),
        "small_model_invocation_rate": _ratio(
            small_invocation_attempts, total
        ),
        "large_model_invocation_rate": _ratio(
            large_invocation_attempts, total
        ),
        "supplied_memory": {
            "micro_precision": _ratio(supplied_relevant, supplied_total),
            "macro_precision": _mean(supplied_macro),
            "required_coverage": _mean(supplied_required),
            "forbidden_hit_rate": _ratio(supplied_forbidden, total),
            "empty_gold_false_retrieval_rate": _ratio(
                empty_false, empty_denominator
            ),
            "rag_empty_gold_false_retrieval_rate": _ratio(
                rag_empty_false, rag_empty_denominator
            ),
        },
        "citation": {
            "micro_precision": _ratio(cited_relevant, cited_total),
            "macro_precision": _mean(citation_macro_precision),
            "micro_recall": _ratio(cited_required, required_citation_total),
            "macro_recall": _mean(citation_macro_recall),
            "forbidden_citation_rate": _ratio(forbidden_citations, total),
            "unexpected_citation_rate": _ratio(
                unexpected_citation_cases, empty_denominator
            ),
        },
        "latency": {
            "route_wall_ns": _percentiles(route_wall),
            "cascade_wall_ns": _percentiles(cascade_wall),
            "cascade_retrieval_wall_ns": _percentiles(retrieval_wall),
            "cascade_retrieval_embedding_wall_ns": _percentiles(
                retrieval_embedding_wall
            ),
            "cascade_retrieval_semantic_search_wall_ns": _percentiles(
                retrieval_semantic_search_wall
            ),
            "cascade_retrieval_keyword_search_wall_ns": _percentiles(
                retrieval_keyword_search_wall
            ),
            "route_backend_call_wall_ns": _percentiles(
                [
                    *backend_wall["route_memory_required"],
                    *backend_wall["route_model_size"],
                ]
            ),
            "route_memory_required_backend_call_wall_ns": _percentiles(
                backend_wall["route_memory_required"]
            ),
            "route_model_size_backend_call_wall_ns": _percentiles(
                backend_wall["route_model_size"]
            ),
            "generation_backend_call_wall_ns": _percentiles(
                backend_wall["generation"]
            ),
            "route_ollama_total_duration_ns": _percentiles(
                [
                    *ollama_total["route_memory_required"],
                    *ollama_total["route_model_size"],
                ]
            ),
            "route_memory_required_ollama_total_duration_ns": _percentiles(
                ollama_total["route_memory_required"]
            ),
            "route_model_size_ollama_total_duration_ns": _percentiles(
                ollama_total["route_model_size"]
            ),
            "generation_ollama_total_duration_ns": _percentiles(
                ollama_total["generation"]
            ),
            "route_ollama_load_duration_ns": _percentiles(
                [
                    *ollama_load["route_memory_required"],
                    *ollama_load["route_model_size"],
                ]
            ),
            "route_memory_required_ollama_load_duration_ns": _percentiles(
                ollama_load["route_memory_required"]
            ),
            "route_model_size_ollama_load_duration_ns": _percentiles(
                ollama_load["route_model_size"]
            ),
            "generation_ollama_load_duration_ns": _percentiles(
                ollama_load["generation"]
            ),
            "route_ollama_prompt_eval_duration_ns": _percentiles(
                [
                    *ollama_prompt_eval["route_memory_required"],
                    *ollama_prompt_eval["route_model_size"],
                ]
            ),
            "route_memory_required_ollama_prompt_eval_duration_ns": (
                _percentiles(ollama_prompt_eval["route_memory_required"])
            ),
            "route_model_size_ollama_prompt_eval_duration_ns": _percentiles(
                ollama_prompt_eval["route_model_size"]
            ),
            "generation_ollama_prompt_eval_duration_ns": _percentiles(
                ollama_prompt_eval["generation"]
            ),
            "route_ollama_eval_duration_ns": _percentiles(
                [
                    *ollama_eval["route_memory_required"],
                    *ollama_eval["route_model_size"],
                ]
            ),
            "route_memory_required_ollama_eval_duration_ns": _percentiles(
                ollama_eval["route_memory_required"]
            ),
            "route_model_size_ollama_eval_duration_ns": _percentiles(
                ollama_eval["route_model_size"]
            ),
            "generation_ollama_eval_duration_ns": _percentiles(
                ollama_eval["generation"]
            ),
        },
    }


def _score_category(
    category: str,
    suite_cases: Sequence[EvaluationCase],
    repetitions: int,
    retrieval_slots: Mapping[
        tuple[int, str], Optional[Mapping[str, object]]
    ],
    case_slots: Mapping[
        tuple[str, int, str], Optional[Mapping[str, object]]
    ],
    *,
    selected_strategies: tuple[str, ...],
    retrieval_enabled: bool,
) -> dict[str, object]:
    adaptive_enabled = "adaptive" in selected_strategies
    adaptive = {
        (repetition, case.id): case_slots.get(
            ("adaptive", repetition, case.id)
        )
        for repetition in range(1, repetitions + 1)
        for case in suite_cases
    }
    rag_cases = tuple(case for case in suite_cases if "rag" in case.tags)
    return {
        "category": category,
        "case_count": len(suite_cases),
        "router": _score_router(
            suite_cases if adaptive_enabled else (), repetitions, adaptive
        ),
        "component_retrieval": (
            _score_component_retrieval(rag_cases, repetitions, retrieval_slots)
            if rag_cases and retrieval_enabled
            else None
        ),
        "strategies": {
            strategy: _score_strategy(
                strategy, suite_cases, repetitions, case_slots
            )
            for strategy in selected_strategies
        },
    }


def _primary_slots(
    observations: Sequence[Mapping[str, object]],
    *,
    expected_keys: Iterable[tuple[object, ...]],
    key_fields: tuple[str, ...],
    cases: Mapping[str, EvaluationCase],
    case_order: Mapping[str, int],
) -> tuple[
    dict[tuple[object, ...], Optional[Mapping[str, object]]],
    dict[str, object],
]:
    expected = tuple(expected_keys)
    expected_set = set(expected)
    grouped: defaultdict[
        tuple[object, ...], list[Mapping[str, object]]
    ] = defaultdict(list)
    unexpected = 0
    ordinal_mismatches = 0
    for observation in observations:
        key = tuple(observation[field] for field in key_fields)
        if key not in expected_set:
            unexpected += 1
            continue
        grouped[key].append(observation)
        case_id = str(observation["case_id"])
        if case_id not in cases or observation["ordinal"] != case_order.get(case_id):
            ordinal_mismatches += 1
    slots = {
        key: (grouped[key][0] if grouped.get(key) else None)
        for key in expected
    }
    missing = sum(value is None for value in slots.values())
    duplicates = sum(max(0, len(values) - 1) for values in grouped.values())
    errors = sum(
        value is not None and value["status"] == "error"
        for value in slots.values()
    )
    return slots, {
        "expected_records": len(expected),
        "observed_records": len(observations),
        "primary_records": len(expected) - missing,
        "missing_records": missing,
        "duplicate_records": duplicates,
        "unexpected_records": unexpected,
        "ordinal_mismatches": ordinal_mismatches,
        "error_records": errors,
    }


def _header(value: Mapping[str, object]) -> Mapping[str, object]:
    data = _exact(value, _HEADER_FIELDS, "header")
    _record_identity(data, "header")
    if data["record_type"] != "header":
        raise EvaluationScoringError("header record_type is invalid")
    _sha(data["config_sha256"], "config_sha256")
    strategies = _string_array(data["strategies"], "strategies", maximum=8)
    expected_order = tuple(
        strategy for strategy in STRATEGIES if strategy in set(strategies)
    )
    if not strategies or strategies != expected_order:
        raise EvaluationScoringError(
            "header strategies must be a non-empty subset in fixed Step 16 order"
        )
    if _integer(data["retrieval_limit"], "retrieval_limit", 1, 5) != RETRIEVAL_LIMIT:
        raise EvaluationScoringError("header retrieval_limit must be 5")
    _integer(data["repetitions"], "repetitions", 1, MAX_REPETITIONS)
    temperature = _number(
        data["evaluation_temperature"], "evaluation_temperature", 0.0, 2.0
    )
    if temperature != 0.0:
        raise EvaluationScoringError("evaluation_temperature must be 0.0")
    if _integer(data["evaluation_seed"], "evaluation_seed", 0, 2**63 - 1) != 42:
        raise EvaluationScoringError("evaluation_seed must be 42")
    _timestamp(data["started_at"], "started_at")
    _text(data["annotation_status"], "annotation_status", 1, 128)
    _json_metadata(data["runtime"], "runtime")
    return data


def _setup(
    value: Mapping[str, object], header: Mapping[str, object]
) -> Mapping[str, object]:
    data = _exact(value, _SETUP_FIELDS, "setup observation")
    _body_identity(data, header, "setup observation")
    if data["record_type"] != "setup":
        raise EvaluationScoringError("setup record_type is invalid")
    status = _choice(data["status"], "setup status", _STATUSES)
    _error_type(data["error_type"], status=status)
    wall = _integer(data["wall_ns"], "setup wall_ns", 0, 2**63 - 1)
    started = _integer(
        data["started_monotonic_ns"],
        "setup started_monotonic_ns",
        0,
        2**63 - 1,
    )
    finished = _integer(
        data["finished_monotonic_ns"],
        "setup finished_monotonic_ns",
        0,
        2**63 - 1,
    )
    _timing_bounds(started, finished, wall, "setup")
    materialization = _optional_ns(
        data["materialization_wall_ns"], "materialization_wall_ns"
    )
    passage = _optional_ns(
        data["passage_embedding_wall_ns"], "passage_embedding_wall_ns"
    )
    calls = _integer(
        data["passage_embedding_calls"],
        "passage_embedding_calls",
        0,
        1_000_000,
    )
    if status == "ok" and (materialization is None or passage is None):
        raise EvaluationScoringError(
            "successful setup needs materialization and passage timings"
        )
    if passage is None and calls != 0:
        raise EvaluationScoringError(
            "setup without passage timing cannot report passage calls"
        )
    if materialization is not None and materialization > wall:
        raise EvaluationScoringError(
            "materialization_wall_ns cannot exceed setup wall_ns"
        )
    if (
        passage is not None
        and materialization is not None
        and passage > materialization
    ):
        raise EvaluationScoringError(
            "passage embedding time cannot exceed materialization time"
        )
    return data


def _retrieval(
    value: Mapping[str, object], header: Mapping[str, object]
) -> Mapping[str, object]:
    data = _exact(value, _RETRIEVAL_FIELDS, "retrieval observation")
    _body_identity(data, header, "retrieval observation")
    _integer(data["repetition"], "repetition", 1, int(header["repetitions"]))
    _integer(data["ordinal"], "ordinal", 1, 512)
    _identifier(data["case_id"], "case_id")
    status = _choice(data["status"], "status", _STATUSES)
    _error_type(data["error_type"], status=status)
    wall = _optional_ns(data["wall_ns"], "wall_ns")
    started = _optional_ns(data["started_monotonic_ns"], "started_monotonic_ns")
    finished = _optional_ns(
        data["finished_monotonic_ns"], "finished_monotonic_ns"
    )
    timing = (started, finished, wall)
    if any(item is None for item in timing):
        if not all(item is None for item in timing):
            raise EvaluationScoringError(
                "retrieval timing must be complete or entirely absent"
            )
        if status == "ok":
            raise EvaluationScoringError(
                "successful retrieval needs monotonic timing bounds"
            )
    else:
        _timing_bounds(started, finished, wall, "retrieval")
    embedding_wall = _optional_ns(
        data["embedding_wall_ns"], "embedding_wall_ns"
    )
    semantic_wall = _optional_ns(
        data["semantic_search_wall_ns"], "semantic_search_wall_ns"
    )
    keyword_wall = _optional_ns(
        data["keyword_search_wall_ns"], "keyword_search_wall_ns"
    )
    source_timings = {
        "embedding": embedding_wall,
        "semantic search": semantic_wall,
        "keyword search": keyword_wall,
    }
    if wall is None and any(value is not None for value in source_timings.values()):
        raise EvaluationScoringError(
            "unattempted retrieval cannot contain source timing"
        )
    for label, source_wall in source_timings.items():
        if source_wall is not None and wall is not None and source_wall > wall:
            raise EvaluationScoringError(
                f"retrieval {label} time cannot exceed retrieval wall_ns"
            )
    if (
        embedding_wall is not None
        and semantic_wall is not None
        and embedding_wall > semantic_wall
    ):
        raise EvaluationScoringError(
            "retrieval embedding time cannot exceed semantic search time"
        )
    ranked = _matches(data["ranked"], maximum=RETRIEVAL_LIMIT)
    normalized = dict(data)
    normalized["ranked"] = ranked
    return normalized


def _case(
    value: Mapping[str, object], header: Mapping[str, object]
) -> Mapping[str, object]:
    data = _exact(value, _CASE_FIELDS, "case observation")
    _body_identity(data, header, "case observation")
    strategy = _choice(
        data["strategy"], "strategy", frozenset(header["strategies"])
    )
    _integer(data["repetition"], "repetition", 1, int(header["repetitions"]))
    _integer(data["ordinal"], "ordinal", 1, 512)
    _identifier(data["case_id"], "case_id")
    status = _choice(data["status"], "status", _STATUSES)
    if status == "ok":
        if data["error_stage"] is not None or data["error_type"] is not None:
            raise EvaluationScoringError(
                "successful case cannot contain error metadata"
            )
    else:
        _choice(data["error_stage"], "error_stage", _ERROR_STAGES)
        _text(data["error_type"], "error_type", 1, 128)
    route = None if data["route"] is None else _route(data["route"], strategy)
    cascade = (
        None if data["cascade"] is None else _cascade(data["cascade"])
    )
    if status == "ok" and (route is None or cascade is None):
        raise EvaluationScoringError("successful case needs route and cascade")
    if status == "ok" and isinstance(cascade, Mapping):
        if (
            cascade["response"] is None
            or cascade["generation"] is None
            or cascade["requested_model"] is None
            or cascade["actual_model"] is None
            or not cascade["backend_calls"]
        ):
            raise EvaluationScoringError(
                "successful case has incomplete cascade results"
            )
        if (
            cascade["retrieval_invoked"]
            and cascade["retrieval_wall_ns"] is None
        ):
            raise EvaluationScoringError(
                "successful retrieval cascade needs retrieval_wall_ns"
            )
    if route is not None and cascade is not None:
        runtime = header.get("runtime")
        if route["model_size"] == "small":
            expected_model = "qwen3:0.6b"
        elif route["memory_required"]:
            expected_model = (
                runtime.get("large_model", "qwen3:4b")
                if isinstance(runtime, Mapping)
                else "qwen3:4b"
            )
        else:
            expected_model = (
                runtime.get("general_large_model", "qwen3:4b")
                if isinstance(runtime, Mapping)
                else "qwen3:4b"
            )
        if cascade["requested_model"] != expected_model:
            raise EvaluationScoringError(
                "cascade requested_model does not match its route"
            )
        expected_retrieval = route["memory_required"] and not cascade.get("privacy_gate", False)
        if cascade["retrieval_invoked"] != expected_retrieval:
            raise EvaluationScoringError(
                "cascade retrieval_invoked does not match its route"
            )
    if cascade is not None:
        backend_calls = cascade["backend_calls"]
        route_call_positions = tuple(
            index
            for index, call in enumerate(backend_calls)
            if call["purpose"] in _ROUTE_PURPOSES
        )
        route_calls = tuple(
            backend_calls[index] for index in route_call_positions
        )
        route_purposes = tuple(call["purpose"] for call in route_calls)
        if strategy != "adaptive" and route_call_positions:
            raise EvaluationScoringError(
                "fixed strategy cannot contain a router backend call"
            )
        if (
            route_call_positions != tuple(range(len(route_call_positions)))
            or route_purposes != _ROUTE_PURPOSES[: len(route_purposes)]
        ):
            raise EvaluationScoringError(
                "router backend calls must be an ordered leading prefix"
            )
        if (
            isinstance(route, Mapping)
            and route["source"] in {"model", "hybrid"}
            and route_purposes != _ROUTE_PURPOSES
        ):
            raise EvaluationScoringError(
                "model route needs both router backend calls"
            )
        if (
            strategy == "adaptive"
            and any(call["purpose"] == "generation" for call in backend_calls)
            and route_purposes != _ROUTE_PURPOSES
        ):
            raise EvaluationScoringError(
                "adaptive generation needs both router backend calls"
            )
        if isinstance(route, Mapping) and route["source"] in {"model", "hybrid"}:
            route_generation_fields = (
                "memory_required_generation",
                "model_size_generation",
            )
            for call, field in zip(route_calls, route_generation_fields):
                if call["status"] != "ok" or call["generation"] != route[field]:
                    raise EvaluationScoringError(
                        "route generation does not match its backend call"
                    )
        if status == "ok" and not any(
            call["purpose"] == "generation" for call in backend_calls
        ):
            raise EvaluationScoringError(
                "successful case needs a generator backend call"
            )
    normalized = dict(data)
    normalized["route"] = route
    normalized["cascade"] = cascade
    return normalized


def _trailer(
    value: Mapping[str, object],
    header: Mapping[str, object],
    retrievals: Sequence[Mapping[str, object]],
    cases: Sequence[Mapping[str, object]],
) -> Mapping[str, object]:
    data = _exact(value, _TRAILER_FIELDS, "trailer")
    if data["record_type"] != "trailer":
        raise EvaluationScoringError("trailer record_type is invalid")
    _schema(data["schema_version"])
    if data["run_id"] != header["run_id"] or data["suite_id"] != header["suite_id"]:
        raise EvaluationScoringError("trailer identity does not match header")
    for field in (
        "expected_retrieval_records",
        "written_retrieval_records",
        "error_retrieval_records",
        "expected_cascade_records",
        "written_cascade_records",
        "error_cascade_records",
    ):
        _integer(data[field], field, 0, 1_000_000)
    if data["written_retrieval_records"] != len(retrievals):
        raise EvaluationScoringError("trailer retrieval count is inconsistent")
    if data["error_retrieval_records"] != sum(
        item["status"] == "error" for item in retrievals
    ):
        raise EvaluationScoringError(
            "trailer retrieval error count is inconsistent"
        )
    if data["written_cascade_records"] != len(cases):
        raise EvaluationScoringError("trailer cascade count is inconsistent")
    if data["error_cascade_records"] != sum(
        item["status"] == "error" for item in cases
    ):
        raise EvaluationScoringError(
            "trailer cascade error count is inconsistent"
        )
    if not isinstance(data["completed"], bool):
        raise EvaluationScoringError("trailer completed must be a boolean")
    _timestamp(data["finished_at"], "finished_at")
    return data


def _partial_trailer(
    header: Mapping[str, object],
    retrievals: Sequence[Mapping[str, object]],
    cases: Sequence[Mapping[str, object]],
) -> Mapping[str, object]:
    """Represent a newline-safe interrupted artifact without hiding its gaps."""

    return {
        "record_type": "trailer",
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "run_id": header["run_id"],
        "suite_id": header["suite_id"],
        "expected_retrieval_records": 0,
        "written_retrieval_records": len(retrievals),
        "error_retrieval_records": sum(
            item["status"] == "error" for item in retrievals
        ),
        "expected_cascade_records": 0,
        "written_cascade_records": len(cases),
        "error_cascade_records": sum(
            item["status"] == "error" for item in cases
        ),
        "completed": False,
        "finished_at": header["started_at"],
    }


def _route(value: object, strategy: str) -> Mapping[str, object]:
    hybrid = isinstance(value, Mapping) and value.get("source") == "hybrid"
    fields = _ROUTE_FIELDS | {"decision_sources"} if hybrid else _ROUTE_FIELDS
    data = _exact(value, fields, "route observation")
    source = _choice(
        data["source"], "route source", frozenset({"model", "hybrid", "strategy"})
    )
    if (strategy == "adaptive") != (source in {"model", "hybrid"}):
        raise EvaluationScoringError("route source does not match strategy")
    memory_required = data["memory_required"]
    if type(memory_required) is not bool:
        raise EvaluationScoringError("route memory_required must be a boolean")
    model_size = _choice(data["model_size"], "route model_size", _MODEL_SIZES)
    wall = _optional_ns(data["wall_ns"], "route wall_ns")
    memory_generation = (
        None
        if data["memory_required_generation"] is None
        else _generation(data["memory_required_generation"])
    )
    model_size_generation = (
        None
        if data["model_size_generation"] is None
        else _generation(data["model_size_generation"])
    )
    if source in {"model", "hybrid"} and (
        memory_generation is None
        or model_size_generation is None
        or wall is None
    ):
        raise EvaluationScoringError(
            "model route needs wall timing and both generation records"
        )
    if source == "strategy" and (
        memory_generation is not None
        or model_size_generation is not None
        or wall is not None
    ):
        raise EvaluationScoringError(
            "fixed-strategy route cannot contain model timing or generations"
        )
    if source in {"model", "hybrid"}:
        assert memory_generation is not None
        assert model_size_generation is not None
        if (
            memory_generation["model"] != "qwen3:0.6b"
            or model_size_generation["model"] != "qwen3:0.6b"
        ):
            raise EvaluationScoringError(
                "route classifier generation model is inconsistent"
            )
        decision_sources = (
            _exact(data["decision_sources"], frozenset({"memory_required", "model_size"}),
                   "decision sources")
            if hybrid else {"memory_required": "model", "model_size": "model"}
        )
        memory_source = _choice(
            decision_sources["memory_required"], "memory decision source",
            frozenset({"model", "policy_general", "policy_personal", "policy_privacy"}),
        )
        size_source = _choice(
            decision_sources["model_size"], "size decision source",
            frozenset({"model", "policy_complex"}),
        )
        raw_memory = _route_generation_value(memory_generation, "memory_required")
        raw_size = _route_generation_value(model_size_generation, "model_size")
        expected_memory = (
            raw_memory if memory_source == "model"
            else memory_source != "policy_general"
        )
        if expected_memory != memory_required:
            raise EvaluationScoringError(
                "memory-required generation contradicts route decision"
            )
        if (raw_size if size_source == "model" else "large") != model_size:
            raise EvaluationScoringError(
                "model-size generation contradicts route decision"
            )
    forced = {
        "always_small_no_rag": (False, "small"),
        "always_large_no_rag": (False, "large"),
        "always_large_with_rag": (True, "large"),
    }
    if strategy in forced and (memory_required, model_size) != forced[strategy]:
        raise EvaluationScoringError("forced route does not match strategy")
    normalized = dict(data)
    normalized["memory_required_generation"] = memory_generation
    normalized["model_size_generation"] = model_size_generation
    return normalized


def _route_generation_value(
    generation: Mapping[str, object], field: str
) -> object:
    """Parse one classifier payload without exposing generated text in errors."""

    try:
        decoded = json.loads(
            str(generation["content"]),
            object_pairs_hook=_unique_object,
            parse_constant=_nonstandard_number,
        )
    except EvaluationScoringError:
        raise
    except (json.JSONDecodeError, OverflowError, RecursionError):
        raise EvaluationScoringError(
            "route classifier generation is not valid JSON"
        ) from None
    # Preserve historical boolean-only observations while validating the
    # current form-first classifier payload exactly as recorded. The added
    # form is metadata, not an application override of the model's decision.
    allowed_fields = ({field},)
    if field == "memory_required":
        allowed_fields += ({"form", "memory_required"},)
    if not isinstance(decoded, dict) or set(decoded) not in allowed_fields:
        raise EvaluationScoringError(
            "route classifier generation has invalid fields"
        )
    decision = decoded[field]
    if field == "memory_required":
        if "form" in decoded:
            _choice(
                decoded["form"], "memory-required generation form", _UTTERANCE_FORMS
            )
        if type(decision) is not bool:
            raise EvaluationScoringError(
                "memory-required generation has an invalid decision"
            )
        return decision
    if field == "model_size":
        return _choice(decision, "model-size generation", _MODEL_SIZES)
    raise EvaluationScoringError("route classifier field is unsupported")


def _cascade(value: object) -> Mapping[str, object]:
    has_privacy_gate = isinstance(value, Mapping) and "privacy_gate" in value
    fields = _CASCADE_FIELDS | {"privacy_gate"} if has_privacy_gate else _CASCADE_FIELDS
    has_transform = isinstance(value, Mapping) and "response_transform" in value
    if has_transform:
        fields = fields | {"response_transform"}
    has_constraint = isinstance(value, Mapping) and "answer_constraint" in value
    if has_constraint:
        fields = fields | {"answer_constraint"}
    has_generation_policy = isinstance(value, Mapping) and "generation_policy" in value
    if has_generation_policy:
        fields = fields | {"generation_policy"}
    has_references = isinstance(value, Mapping) and "reference_ids" in value
    if has_references:
        fields = fields | {"reference_ids"}
    data = _exact(value, fields, "cascade observation")
    if has_references and not (
        isinstance(data["reference_ids"], list)
        and 1 <= len(data["reference_ids"]) <= 2
        and all(isinstance(item, str) and item in REFERENCE_IDS
                for item in data["reference_ids"])
        and len(set(data["reference_ids"])) == len(data["reference_ids"])
        and not data["retrieval_invoked"] and not has_privacy_gate
        and isinstance(data["response"], Mapping)
        and data["response"].get("memory_used") == []
    ):
        raise EvaluationScoringError("invalid non-personal reference notes")
    transform_bounds = {
        "verified_memory_perspective": (1, 1),
        "conflict_clarification": (2, 3),
    }
    bounds = transform_bounds.get(str(data.get("response_transform")))
    if has_transform and (
        bounds is None
        or has_privacy_gate or not data["retrieval_invoked"]
        or not isinstance(data["supplied_ids"], list)
        or not bounds[0] <= len(data["supplied_ids"]) <= bounds[1]
        or not isinstance(data["response"], Mapping)
        or data["response"].get("memory_used") != data["supplied_ids"]
    ):
        raise EvaluationScoringError("invalid verified-memory response transform")
    constraint_bounds = {
        "verified_preference": (1, 1), "verified_named_relationship": (1, 1),
        "verified_user_relationship": (1, 1),
        "verified_location": (1, 1),
        "verified_timeline": (2, 2), "verified_milestone_comparison": (2, 3),
        "verified_event_order": (2, 3), "verified_event_interval": (2, 2),
        "verified_partial_recall": (1, 2),
        "verified_presentation_plan": (2, 3), "verified_travel_checklist": (2, 2),
        **{name: (0, 0) for name in OPERATIONAL_CONSTRAINTS},
    }
    bounds = constraint_bounds.get(str(data.get("answer_constraint")))
    if has_constraint and (
        bounds is None
        or has_privacy_gate
        or bool(data["retrieval_invoked"]) == (data.get("answer_constraint") in OPERATIONAL_CONSTRAINTS)
        or not isinstance(data["supplied_ids"], list)
        or not bounds[0] <= len(data["supplied_ids"]) <= bounds[1]
        or not isinstance(data["response"], Mapping)
        or not isinstance(data["response"].get("memory_used"), list)
        or not all(isinstance(value, str) for value in data["response"]["memory_used"])
        or not all(isinstance(value, str) for value in data["supplied_ids"])
        or set(data["response"]["memory_used"]) != set(data["supplied_ids"])
    ):
        raise EvaluationScoringError("invalid verified-answer constraint")
    if has_privacy_gate and data["privacy_gate"] is not True:
        raise EvaluationScoringError("privacy_gate must be true when present")
    if has_privacy_gate and (data["retrieval_invoked"] or data["supplied_ids"]):
        raise EvaluationScoringError("privacy gate must block memory access")
    wall = _optional_ns(data["wall_ns"], "cascade wall_ns")
    started = _optional_ns(
        data["started_monotonic_ns"], "cascade started_monotonic_ns"
    )
    finished = _optional_ns(
        data["finished_monotonic_ns"], "cascade finished_monotonic_ns"
    )
    if wall is None or started is None or finished is None:
        raise EvaluationScoringError(
            "cascade observation needs complete monotonic timing bounds"
        )
    _timing_bounds(started, finished, wall, "cascade")
    if type(data["retrieval_invoked"]) is not bool:
        raise EvaluationScoringError("retrieval_invoked must be a boolean")
    retrieval_wall = _optional_ns(
        data["retrieval_wall_ns"], "retrieval_wall_ns"
    )
    retrieval_embedding_wall = _optional_ns(
        data["retrieval_embedding_wall_ns"],
        "retrieval_embedding_wall_ns",
    )
    retrieval_semantic_wall = _optional_ns(
        data["retrieval_semantic_search_wall_ns"],
        "retrieval_semantic_search_wall_ns",
    )
    retrieval_keyword_wall = _optional_ns(
        data["retrieval_keyword_search_wall_ns"],
        "retrieval_keyword_search_wall_ns",
    )
    source_timings = {
        "embedding": retrieval_embedding_wall,
        "semantic search": retrieval_semantic_wall,
        "keyword search": retrieval_keyword_wall,
    }
    if retrieval_wall is None and any(
        value is not None for value in source_timings.values()
    ):
        raise EvaluationScoringError(
            "cascade without retrieval wall time cannot contain source timing"
        )
    for label, source_wall in source_timings.items():
        if (
            source_wall is not None
            and retrieval_wall is not None
            and source_wall > retrieval_wall
        ):
            raise EvaluationScoringError(
                f"cascade retrieval {label} time cannot exceed retrieval_wall_ns"
            )
    if (
        retrieval_embedding_wall is not None
        and retrieval_semantic_wall is not None
        and retrieval_embedding_wall > retrieval_semantic_wall
    ):
        raise EvaluationScoringError(
            "cascade retrieval embedding time cannot exceed semantic search time"
        )
    ranked = _matches(data["retrieved_ranked"], maximum=3)
    supplied = _memory_ids(data["supplied_ids"], "supplied_ids", maximum=3)
    if not data["retrieval_invoked"] and (
        retrieval_wall is not None
        or any(value is not None for value in source_timings.values())
        or ranked
        or supplied
    ):
        raise EvaluationScoringError(
            "non-retrieval cascade contains retrieval observations"
        )
    requested = _optional_model(data["requested_model"], "requested_model")
    actual = _optional_model(data["actual_model"], "actual_model")
    fallback = _optional_model(
        data["fallback_from_model"], "fallback_from_model"
    )
    if has_generation_policy and not (
        data["generation_policy"] == "verified_constraint_small"
        and has_constraint and data["answer_constraint"] != "verified_preference"
        and requested in {"qwen3:1.7b", "qwen3:4b"}
        and actual == "qwen3:0.6b" and fallback is None
    ):
        raise EvaluationScoringError("invalid constrained generation policy")
    if fallback is not None and not (
        fallback in {"qwen3:1.7b", "qwen3:4b"}
        and actual == "qwen3:0.6b"
    ):
        raise EvaluationScoringError("fallback model metadata is inconsistent")
    response = None if data["response"] is None else _response(data["response"])
    if response is not None and not set(response["memory_used"]).issubset(supplied):
        raise EvaluationScoringError("response cites memory that was not supplied")
    ranked_ids = tuple(str(match["id"]) for match in ranked)
    if not set(supplied).issubset(ranked_ids):
        raise EvaluationScoringError(
            "supplied_ids must come from retrieved_ranked"
        )
    generation = (
        None if data["generation"] is None else _generation(data["generation"])
    )
    if generation is not None and actual != generation["model"]:
        raise EvaluationScoringError("cascade generation model is inconsistent")
    calls = _backend_calls(data["backend_calls"])
    normalized = dict(data)
    normalized["retrieved_ranked"] = ranked
    normalized["supplied_ids"] = supplied
    normalized["response"] = response
    normalized["generation"] = generation
    normalized["backend_calls"] = calls
    normalized["requested_model"] = requested
    normalized["actual_model"] = actual
    normalized["fallback_from_model"] = fallback
    return normalized


def _response(value: object) -> Mapping[str, object]:
    data = _exact(value, _RESPONSE_FIELDS, "response observation")
    speech = _text(data["speech"], "response speech", 1, 16_384)
    gesture = _text(data["gesture_id"], "gesture_id", 1, 64)
    if gesture != "NO_ACTION":
        raise EvaluationScoringError("evaluation response gesture_id must be NO_ACTION")
    used = _memory_ids(data["memory_used"], "memory_used", maximum=3)
    return {"speech": speech, "gesture_id": gesture, "memory_used": used}


def _backend_calls(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list) or len(value) > 4:
        raise EvaluationScoringError("backend_calls must be an array of at most 4")
    result = []
    for raw in value:
        data = _exact(raw, _BACKEND_CALL_FIELDS, "backend call")
        _choice(
            data["purpose"],
            "backend call purpose",
            _BACKEND_PURPOSES,
        )
        model = _optional_model(
            data["model"], "backend call model", required=True
        )
        if data["purpose"] in _ROUTE_PURPOSES and model != "qwen3:0.6b":
            raise EvaluationScoringError(
                "router backend call must use qwen3:0.6b"
            )
        if _optional_ns(data["wall_ns"], "backend call wall_ns") is None:
            raise EvaluationScoringError("backend call needs wall_ns")
        status = _choice(data["status"], "backend call status", _STATUSES)
        _error_type(data["error_type"], status=status)
        generation = (
            None if data["generation"] is None else _generation(data["generation"])
        )
        if status == "ok" and generation is None:
            raise EvaluationScoringError(
                "successful backend call needs generation metadata"
            )
        if generation is not None and generation["model"] != data["model"]:
            raise EvaluationScoringError(
                "backend call generation model is inconsistent"
            )
        normalized = dict(data)
        normalized["generation"] = generation
        result.append(normalized)
    return tuple(result)


def _generation(value: object) -> Mapping[str, object]:
    data = _exact(value, _GENERATION_FIELDS, "generation metadata")
    _optional_model(data["model"], "generation model", required=True)
    _raw_content(data["content"])
    _text(data["done_reason"], "done_reason", 1, 64)
    for field in (
        "total_duration_ns",
        "load_duration_ns",
        "prompt_eval_count",
        "prompt_eval_duration_ns",
        "eval_count",
        "eval_duration_ns",
    ):
        _integer(data[field], field, 0, 2**63 - 1)
    tps = data["generation_tokens_per_second"]
    if tps is not None:
        _number(tps, "generation_tokens_per_second", 0.0, 1_000_000.0)
    return data


def _matches(value: object, *, maximum: int) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise EvaluationScoringError(
            f"ranked matches must be an array of at most {maximum}"
        )
    result = []
    identifiers = []
    for raw in value:
        data = _exact(raw, _MATCH_FIELDS, "ranked match")
        identifiers.append(_memory_id(data["id"], "ranked match id"))
        _number(data["fused_score"], "fused_score", 0.0, 1.0)
        for field in ("keyword_rank", "semantic_score"):
            if data[field] is not None:
                _number(data[field], field, -1_000_000_000.0, 1_000_000_000.0)
        for field in ("keyword_position", "semantic_position"):
            if data[field] is not None:
                _integer(data[field], field, 1, 20)
        if data["keyword_position"] is None and data["semantic_position"] is None:
            raise EvaluationScoringError("ranked match has no retrieval source")
        result.append(data)
    if len(identifiers) != len(set(identifiers)):
        raise EvaluationScoringError("ranked matches contain duplicate IDs")
    return tuple(result)


def _record_identity(data: Mapping[str, object], label: str) -> None:
    _schema(data["schema_version"])
    _identifier(data["run_id"], f"{label} run_id")
    _identifier(data["suite_id"], f"{label} suite_id")
    _sha(data["suite_sha256"], "suite_sha256")


def _body_identity(
    data: Mapping[str, object], header: Mapping[str, object], label: str
) -> None:
    _schema(data["schema_version"])
    if (
        data["run_id"] != header["run_id"]
        or data["suite_id"] != header["suite_id"]
        or data["suite_sha256"] != header["suite_sha256"]
    ):
        raise EvaluationScoringError(f"{label} identity does not match header")


def _schema(value: object) -> None:
    if _integer(value, "schema_version", 0, 2**31 - 1) != OBSERVATION_SCHEMA_VERSION:
        raise EvaluationScoringError("unsupported observation schema_version")


def _json_line(line: str, number: int) -> dict[str, object]:
    try:
        value = json.loads(
            line,
            object_pairs_hook=_unique_object,
            parse_constant=_nonstandard_number,
        )
    except EvaluationScoringError:
        raise
    except (json.JSONDecodeError, OverflowError, RecursionError):
        raise EvaluationScoringError(
            f"observation line {number} is not valid JSON"
        ) from None
    if not isinstance(value, dict):
        raise EvaluationScoringError(
            f"observation line {number} must be a JSON object"
        )
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise EvaluationScoringError(
                "observation JSON contains a duplicate field"
            )
        result[key] = value
    return result


def _nonstandard_number(value: str) -> None:
    raise EvaluationScoringError("observation JSON contains a nonstandard number")


def _exact(
    value: object, fields: frozenset[str], label: str
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise EvaluationScoringError(f"{label} must be an object")
    keys = set(value)
    if keys != fields:
        missing = sorted(fields - keys)
        unknown = sorted(keys - fields)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unknown:
            details.append("unknown fields present")
        raise EvaluationScoringError(
            f"{label} has invalid fields ({'; '.join(details)})"
        )
    return dict(value)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise EvaluationScoringError(f"{label} must be an object")
    return value


def _identifier(value: object, field: str) -> str:
    text = _text(value, field, 1, 128)
    if _IDENTIFIER_PATTERN.fullmatch(text) is None:
        raise EvaluationScoringError(f"{field} is invalid")
    return text


def _sha(value: object, field: str) -> str:
    text = _text(value, field, 64, 64)
    if _SHA256_PATTERN.fullmatch(text) is None:
        raise EvaluationScoringError(f"{field} must be lowercase SHA-256")
    return text


def _memory_id(value: object, field: str) -> str:
    text = _text(value, field, 36, 36)
    if _MEMORY_ID_PATTERN.fullmatch(text) is None:
        raise EvaluationScoringError(f"{field} is invalid")
    return text


def _memory_ids(
    value: object, field: str, *, maximum: int
) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise EvaluationScoringError(
            f"{field} must be an array of at most {maximum} IDs"
        )
    result = tuple(_memory_id(item, field) for item in value)
    if len(result) != len(set(result)):
        raise EvaluationScoringError(f"{field} contains duplicate IDs")
    return result


def _string_array(
    value: object, field: str, *, maximum: int
) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise EvaluationScoringError(f"{field} must be a bounded string array")
    result = tuple(_text(item, field, 1, 128) for item in value)
    if len(result) != len(set(result)):
        raise EvaluationScoringError(f"{field} contains duplicates")
    return result


def _text(
    value: object, field: str, minimum: int, maximum: int
) -> str:
    if not isinstance(value, str):
        raise EvaluationScoringError(f"{field} must be a string")
    if not minimum <= len(value) <= maximum or value != value.strip():
        raise EvaluationScoringError(f"{field} has invalid length or whitespace")
    if any(
        unicodedata.category(character) in {"Cc", "Cs"}
        or character in {"\u2028", "\u2029"}
        for character in value
    ):
        raise EvaluationScoringError(f"{field} contains unsafe characters")
    return value


def _raw_content(value: object) -> str:
    """Validate bounded model text while permitting ordinary JSON whitespace."""

    if not isinstance(value, str) or not value or len(value) > 64 * 1024:
        raise EvaluationScoringError(
            "generation content must be non-empty bounded text"
        )
    if value != value.strip():
        raise EvaluationScoringError(
            "generation content cannot have outer whitespace"
        )
    if any(
        (
            unicodedata.category(character) in {"Cc", "Cs"}
            and character not in {"\t", "\n", "\r"}
        )
        or character in {"\u2028", "\u2029"}
        for character in value
    ):
        raise EvaluationScoringError(
            "generation content contains unsafe characters"
        )
    return value


def _integer(value: object, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvaluationScoringError(f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise EvaluationScoringError(f"{field} is outside its allowed range")
    return value


def _number(value: object, field: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationScoringError(f"{field} must be a number")
    normalized = float(value)
    if not isfinite(normalized) or not minimum <= normalized <= maximum:
        raise EvaluationScoringError(f"{field} is outside its allowed range")
    return normalized


def _choice(value: object, field: str, choices: frozenset[str]) -> str:
    text = _text(value, field, 1, 128)
    if text not in choices:
        raise EvaluationScoringError(f"{field} has an unsupported value")
    return text


def _optional_ns(value: object, field: str) -> Optional[int]:
    if value is None:
        return None
    return _integer(value, field, 0, 2**63 - 1)


def _timing_bounds(
    started: Optional[int],
    finished: Optional[int],
    wall: Optional[int],
    label: str,
) -> None:
    if started is None or finished is None:
        if started is not None or finished is not None:
            raise EvaluationScoringError(
                f"{label} monotonic bounds must both be present or absent"
            )
        if wall not in {None, 0}:
            raise EvaluationScoringError(
                f"{label} without monotonic bounds must have zero wall_ns"
            )
        return
    if finished < started or wall != finished - started:
        raise EvaluationScoringError(
            f"{label} monotonic bounds do not match wall_ns"
        )


def _optional_model(
    value: object, field: str, *, required: bool = False
) -> Optional[str]:
    if value is None:
        if required:
            raise EvaluationScoringError(f"{field} is required")
        return None
    model = _text(value, field, 1, 128)
    if model not in {"qwen3:0.6b", "qwen3:1.7b", "qwen3:4b"}:
        raise EvaluationScoringError(f"{field} is not a configured model")
    return model


def _error_type(value: object, *, status: str) -> None:
    if status == "ok":
        if value is not None:
            raise EvaluationScoringError(
                "successful observation cannot contain error_type"
            )
    else:
        _text(value, "error_type", 1, 128)


def _timestamp(value: object, field: str) -> str:
    text = _text(value, field, 1, 64)
    if not text.endswith("Z"):
        raise EvaluationScoringError(f"{field} must be UTC and end in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError:
        raise EvaluationScoringError(f"{field} is not an ISO timestamp") from None
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise EvaluationScoringError(f"{field} must be UTC")
    return text


def _json_metadata(value: object, field: str, *, depth: int = 0) -> None:
    if depth > 8:
        raise EvaluationScoringError(f"{field} is nested too deeply")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        _text(value, field, 0, 16_384)
        return
    if isinstance(value, int) and not isinstance(value, bool):
        _integer(value, field, -(2**63), 2**63 - 1)
        return
    if isinstance(value, float):
        _number(value, field, -1e300, 1e300)
        return
    if isinstance(value, Mapping):
        if len(value) > 512:
            raise EvaluationScoringError(f"{field} has too many fields")
        for key, item in value.items():
            _text(key, f"{field} key", 1, 128)
            _json_metadata(item, field, depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        if len(value) > 10_000:
            raise EvaluationScoringError(f"{field} array is too large")
        for item in value:
            _json_metadata(item, field, depth=depth + 1)
        return
    raise EvaluationScoringError(f"{field} contains unsupported data")


def _ratio(numerator: int, denominator: int) -> dict[str, object]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": None if denominator == 0 else numerator / denominator,
    }


def _mean(values: Sequence[float]) -> dict[str, object]:
    return {
        "samples": len(values),
        "value": None if not values else sum(values) / len(values),
    }


def _percentiles(values: Sequence[int]) -> dict[str, object]:
    ordered = sorted(values)
    if not ordered:
        return {"samples": 0, "p50_ns": None, "p95_ns": None}
    return {
        "samples": len(ordered),
        "p50_ns": ordered[ceil(0.50 * len(ordered)) - 1],
        "p95_ns": ordered[ceil(0.95 * len(ordered)) - 1],
    }


def _md(value: object) -> str:
    return str(value).replace("`", "\\`").replace("|", "\\|")


def _ratio_md(value: object) -> str:
    if not isinstance(value, Mapping) or value.get("value") is None:
        return "N/A"
    return (
        f"{100 * float(value['value']):.2f}% "
        f"({int(value['numerator'])}/{int(value['denominator'])})"
    )


def _mean_md(value: object) -> str:
    if not isinstance(value, Mapping) or value.get("value") is None:
        return "N/A"
    return f"{float(value['value']):.4f} (n={int(value['samples'])})"


def _percentile_md(value: object, field: str) -> str:
    if not isinstance(value, Mapping) or value.get(field) is None:
        return "N/A"
    return f"{int(value[field]) / 1_000_000:.2f} ms"


__all__ = [
    "EvaluationScoringError",
    "MAX_OBSERVATION_BYTES",
    "OBSERVATION_SCHEMA_VERSION",
    "ObservationRun",
    "RETRIEVAL_LIMIT",
    "SCORING_SCHEMA_VERSION",
    "STRATEGIES",
    "blinded_review_records",
    "canonical_summary_json",
    "emit_blinded_review_sheet",
    "evaluation_suite_sha256",
    "load_observation_jsonl",
    "merge_observation_runs",
    "parse_observation_jsonl",
    "render_summary_markdown",
    "score_observations",
]
