import copy
import json
from pathlib import Path
import tempfile
import unittest

from oline_hri.evaluation import load_evaluation_suite
from oline_hri.evaluation_scoring import (
    EvaluationScoringError,
    STRATEGIES,
    canonical_summary_json,
    emit_blinded_review_sheet,
    evaluation_suite_sha256,
    load_observation_jsonl,
    merge_observation_runs,
    parse_observation_jsonl,
    render_summary_markdown,
    score_observations,
)


SUITE_SHA = evaluation_suite_sha256(load_evaluation_suite())
CONFIG_SHA = "b" * 64
SMALL = "qwen3:0.6b"
LARGE = "qwen3:4b"


def _generation(model, content="{}"):
    return {
        "model": model,
        "content": content,
        "done_reason": "stop",
        "total_duration_ns": 2_000_000,
        "load_duration_ns": 100_000,
        "prompt_eval_count": 20,
        "prompt_eval_duration_ns": 500_000,
        "eval_count": 10,
        "eval_duration_ns": 1_000_000,
        "generation_tokens_per_second": 10_000.0,
    }


def _match(memory_id, position):
    return {
        "id": memory_id,
        "fused_score": 1.0 / (60 + position),
        "keyword_rank": None,
        "keyword_position": None,
        "semantic_score": 1.0 - position / 100.0,
        "semantic_position": position,
    }


def _route(strategy, case):
    if strategy == "adaptive":
        memory_required = case.expected_route.memory_required
        model_size = case.expected_route.model_size
        source = "model"
        wall_ns = 500_000
        memory_required_generation = _generation(
            SMALL,
            json.dumps(
                {"memory_required": memory_required},
                separators=(",", ":"),
            ),
        )
        model_size_generation = _generation(
            SMALL,
            json.dumps(
                {"model_size": model_size},
                separators=(",", ":"),
            ),
        )
    elif strategy == "always_small_no_rag":
        memory_required, model_size = False, "small"
        source, wall_ns = "strategy", None
        memory_required_generation = model_size_generation = None
    elif strategy == "always_large_no_rag":
        memory_required, model_size = False, "large"
        source, wall_ns = "strategy", None
        memory_required_generation = model_size_generation = None
    else:
        memory_required, model_size = True, "large"
        source, wall_ns = "strategy", None
        memory_required_generation = model_size_generation = None
    return {
        "source": source,
        "memory_required": memory_required,
        "model_size": model_size,
        "wall_ns": wall_ns,
        "memory_required_generation": memory_required_generation,
        "model_size_generation": model_size_generation,
    }


def _raw_records(
    *,
    run_id="run_perfect",
    strategies=STRATEGIES,
    repetitions=1,
    include_retrieval=True,
):
    suite = load_evaluation_suite()
    header = {
        "record_type": "header",
        "schema_version": 2,
        "run_id": run_id,
        "suite_id": suite.suite_id,
        "suite_sha256": SUITE_SHA,
        "annotation_status": suite.annotation_status,
        "config_sha256": CONFIG_SHA,
        "strategies": list(strategies),
        "retrieval_limit": 5,
        "repetitions": repetitions,
        "evaluation_temperature": 0.0,
        "evaluation_seed": 42,
        "started_at": "2026-09-07T00:00:00.000000Z",
        "runtime": {"python": "3.10.12", "offline": True},
    }
    setup = {
        "record_type": "setup",
        "schema_version": 2,
        "run_id": run_id,
        "suite_id": suite.suite_id,
        "suite_sha256": SUITE_SHA,
        "status": "ok",
        "error_type": None,
        "started_monotonic_ns": 9_000_000_000,
        "finished_monotonic_ns": 9_005_000_000,
        "wall_ns": 5_000_000,
        "materialization_wall_ns": 4_000_000,
        "passage_embedding_wall_ns": 3_000_000,
        "passage_embedding_calls": 14,
    }
    retrievals = []
    if include_retrieval:
        for repetition in range(1, repetitions + 1):
            for ordinal, case in enumerate(suite.cases, 1):
                if "rag" not in case.tags:
                    continue
                ids = list(case.retrieval_gold.relevant_ids)
                wall_ns = ordinal * 100_000
                started_ns = 10_000_000_000 + ordinal * 1_000_000
                retrievals.append(
                    {
                        "record_type": "retrieval",
                        "schema_version": 2,
                        "run_id": run_id,
                        "suite_id": suite.suite_id,
                        "suite_sha256": SUITE_SHA,
                        "repetition": repetition,
                        "ordinal": ordinal,
                        "case_id": case.id,
                        "status": "ok",
                        "error_type": None,
                        "started_monotonic_ns": started_ns,
                        "finished_monotonic_ns": started_ns + wall_ns,
                        "wall_ns": wall_ns,
                        "embedding_wall_ns": ordinal * 10_000,
                        "semantic_search_wall_ns": ordinal * 30_000,
                        "keyword_search_wall_ns": ordinal * 20_000,
                        "ranked": [
                            _match(memory_id, position)
                            for position, memory_id in enumerate(ids, 1)
                        ],
                    }
                )

    cases = []
    for strategy in strategies:
        for repetition in range(1, repetitions + 1):
            for ordinal, case in enumerate(suite.cases, 1):
                route = _route(strategy, case)
                retrieval_invoked = route["memory_required"]
                supplied = (
                    list(case.retrieval_gold.relevant_ids[:3])
                    if retrieval_invoked
                    else []
                )
                model = SMALL if route["model_size"] == "small" else LARGE
                generation = _generation(model)
                wall_ns = ordinal * 1_000_000
                started_ns = 20_000_000_000 + ordinal * 2_000_000
                cascade = {
                    "started_monotonic_ns": started_ns,
                    "finished_monotonic_ns": started_ns + wall_ns,
                    "wall_ns": wall_ns,
                    "retrieval_invoked": retrieval_invoked,
                    "retrieval_wall_ns": (
                        ordinal * 100_000 if retrieval_invoked else None
                    ),
                    "retrieval_embedding_wall_ns": (
                        ordinal * 10_000 if retrieval_invoked else None
                    ),
                    "retrieval_semantic_search_wall_ns": (
                        ordinal * 30_000 if retrieval_invoked else None
                    ),
                    "retrieval_keyword_search_wall_ns": (
                        ordinal * 20_000 if retrieval_invoked else None
                    ),
                    "retrieved_ranked": [
                        _match(memory_id, position)
                        for position, memory_id in enumerate(supplied, 1)
                    ],
                    "supplied_ids": supplied,
                    "requested_model": model,
                    "actual_model": model,
                    "fallback_from_model": None,
                    "response": {
                        "speech": case.answer_rubric.reference_answer,
                        "gesture_id": "NO_ACTION",
                        "memory_used": (
                            list(case.answer_rubric.required_citation_ids)
                            if retrieval_invoked
                            else []
                        ),
                    },
                    "generation": generation,
                    "backend_calls": (
                        [
                            {
                                "purpose": "route_memory_required",
                                "model": SMALL,
                                "wall_ns": 250_000,
                                "status": "ok",
                                "error_type": None,
                                "generation": route[
                                    "memory_required_generation"
                                ],
                            },
                            {
                                "purpose": "route_model_size",
                                "model": SMALL,
                                "wall_ns": 250_000,
                                "status": "ok",
                                "error_type": None,
                                "generation": route[
                                    "model_size_generation"
                                ],
                            }
                        ]
                        if strategy == "adaptive"
                        else []
                    )
                    + [
                        {
                            "purpose": "generation",
                            "model": model,
                            "wall_ns": ordinal * 900_000,
                            "status": "ok",
                            "error_type": None,
                            "generation": generation,
                        }
                    ],
                }
                cases.append(
                    {
                        "record_type": "case",
                        "schema_version": 2,
                        "run_id": run_id,
                        "suite_id": suite.suite_id,
                        "suite_sha256": SUITE_SHA,
                        "strategy": strategy,
                        "repetition": repetition,
                        "ordinal": ordinal,
                        "case_id": case.id,
                        "status": "ok",
                        "error_stage": None,
                        "error_type": None,
                        "route": route,
                        "cascade": cascade,
                    }
                )
    trailer = {
        "record_type": "trailer",
        "schema_version": 2,
        "run_id": run_id,
        "suite_id": suite.suite_id,
        "expected_retrieval_records": (
            16 * repetitions if include_retrieval else 0
        ),
        "written_retrieval_records": len(retrievals),
        "error_retrieval_records": 0,
        "expected_cascade_records": len(strategies) * 30 * repetitions,
        "written_cascade_records": len(cases),
        "error_cascade_records": 0,
        "completed": True,
        "finished_at": "2026-09-07T01:00:00.000000Z",
    }
    return [header, setup, *retrievals, *cases, trailer]


def _encode(records):
    return "".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    )


def _find(records, record_type, **fields):
    return next(
        record
        for record in records
        if record["record_type"] == record_type
        and all(record.get(key) == value for key, value in fields.items())
    )


def _refresh_trailer(records):
    trailer = records[-1]
    retrievals = [item for item in records if item["record_type"] == "retrieval"]
    cases = [item for item in records if item["record_type"] == "case"]
    trailer["written_retrieval_records"] = len(retrievals)
    trailer["error_retrieval_records"] = sum(
        item["status"] == "error" for item in retrievals
    )
    trailer["written_cascade_records"] = len(cases)
    trailer["error_cascade_records"] = sum(
        item["status"] == "error" for item in cases
    )


class ObservationParsingTests(unittest.TestCase):
    def test_supplied_candidate_can_be_nonprefix_and_uncited(self):
        records = _raw_records()
        case = _find(
            records,
            "case",
            strategy="adaptive",
            case_id="memory_absent",
        )
        first = "mem_00000000000000000000000000000001"
        second = "mem_00000000000000000000000000000002"
        case["cascade"]["retrieved_ranked"] = [
            _match(first, 1),
            _match(second, 2),
        ]
        case["cascade"]["supplied_ids"] = [second]
        case["cascade"]["response"]["memory_used"] = []

        observations = parse_observation_jsonl(_encode(records))
        normalized = next(
            item
            for item in observations.cases
            if item["strategy"] == "adaptive"
            and item["case_id"] == "memory_absent"
        )

        self.assertEqual(normalized["cascade"]["supplied_ids"], (second,))
        self.assertEqual(
            normalized["cascade"]["response"]["memory_used"],
            (),
        )

    def test_round_trip_strict_stream_and_file_loading(self):
        raw = _encode(_raw_records())
        parsed = parse_observation_jsonl(raw)

        self.assertEqual(len(parsed.retrievals), 16)
        self.assertEqual(len(parsed.cases), 120)
        self.assertEqual(parsed.header["strategies"], list(STRATEGIES))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            path.write_text(raw, encoding="utf-8")
            self.assertEqual(load_observation_jsonl(path), parsed)

            symlink = Path(directory) / "observations-link.jsonl"
            symlink.symlink_to(path)
            with self.assertRaises(EvaluationScoringError):
                load_observation_jsonl(symlink)

    def test_rejects_noncanonical_stream_shape_duplicates_and_unknown_fields(self):
        raw = _encode(_raw_records())
        with self.assertRaises(EvaluationScoringError):
            parse_observation_jsonl(raw.rstrip("\n"))
        with self.assertRaises(EvaluationScoringError):
            parse_observation_jsonl(raw.replace("\n", "\n\n", 1))

        duplicate = raw.replace(
            '"record_type":"header"',
            '"record_type":"header","record_type":"header"',
            1,
        )
        with self.assertRaises(EvaluationScoringError):
            parse_observation_jsonl(duplicate)

        records = _raw_records()
        records[0]["unexpected"] = True
        with self.assertRaises(EvaluationScoringError):
            parse_observation_jsonl(_encode(records))

        records = _raw_records()
        for record in records:
            record["schema_version"] = 1
        with self.assertRaisesRegex(
            EvaluationScoringError, "unsupported observation schema_version"
        ):
            parse_observation_jsonl(_encode(records))

    def test_rejects_inconsistent_nested_and_trailer_data(self):
        mutations = []

        def invented_citation(records):
            case = _find(
                records,
                "case",
                strategy="adaptive",
                case_id="memory_direct_fact",
            )
            case["cascade"]["response"]["memory_used"] = ["mem_" + "f" * 32]

        mutations.append(invented_citation)

        def route_strategy_mismatch(records):
            case = _find(
                records,
                "case",
                strategy="always_small_no_rag",
                case_id="route_small_no_memory_01",
            )
            case["route"]["model_size"] = "large"

        mutations.append(route_strategy_mismatch)

        def false_success(records):
            record = _find(
                records,
                "retrieval",
                case_id="memory_direct_fact",
            )
            record["wall_ns"] = None

        mutations.append(false_success)

        def bad_trailer(records):
            records[-1]["written_cascade_records"] += 1

        mutations.append(bad_trailer)

        def inconsistent_monotonic_bounds(records):
            record = _find(
                records,
                "retrieval",
                case_id="memory_direct_fact",
            )
            record["finished_monotonic_ns"] += 1

        mutations.append(inconsistent_monotonic_bounds)

        def successful_retrieval_without_bounds(records):
            record = _find(
                records,
                "retrieval",
                case_id="memory_direct_fact",
            )
            record["started_monotonic_ns"] = None
            record["finished_monotonic_ns"] = None
            record["wall_ns"] = None
            record["embedding_wall_ns"] = None
            record["semantic_search_wall_ns"] = None
            record["keyword_search_wall_ns"] = None

        mutations.append(successful_retrieval_without_bounds)

        def inconsistent_setup_bounds(records):
            records[1]["finished_monotonic_ns"] += 1

        mutations.append(inconsistent_setup_bounds)

        def missing_backend_purpose(records):
            case = _find(
                records,
                "case",
                strategy="always_small_no_rag",
                case_id="route_small_no_memory_01",
            )
            del case["cascade"]["backend_calls"][0]["purpose"]

        mutations.append(missing_backend_purpose)

        def component_source_timing_exceeds_parent(records):
            record = _find(
                records,
                "retrieval",
                case_id="memory_direct_fact",
            )
            record["semantic_search_wall_ns"] = record["wall_ns"] + 1

        mutations.append(component_source_timing_exceeds_parent)

        def component_embedding_exceeds_semantic(records):
            record = _find(
                records,
                "retrieval",
                case_id="memory_direct_fact",
            )
            record["semantic_search_wall_ns"] = (
                record["embedding_wall_ns"] - 1
            )

        mutations.append(component_embedding_exceeds_semantic)

        def non_retrieval_cascade_has_source_timing(records):
            case = _find(
                records,
                "case",
                strategy="always_small_no_rag",
                case_id="route_small_no_memory_01",
            )
            case["cascade"]["retrieval_keyword_search_wall_ns"] = 1

        mutations.append(non_retrieval_cascade_has_source_timing)

        def cascade_source_timing_exceeds_parent(records):
            case = _find(
                records,
                "case",
                strategy="always_large_with_rag",
                case_id="route_small_no_memory_01",
            )
            cascade = case["cascade"]
            cascade["retrieval_semantic_search_wall_ns"] = (
                cascade["retrieval_wall_ns"] + 1
            )

        mutations.append(cascade_source_timing_exceeds_parent)

        def cascade_embedding_exceeds_semantic(records):
            case = _find(
                records,
                "case",
                strategy="always_large_with_rag",
                case_id="route_small_no_memory_01",
            )
            cascade = case["cascade"]
            cascade["retrieval_embedding_wall_ns"] = (
                cascade["retrieval_semantic_search_wall_ns"] + 1
            )

        mutations.append(cascade_embedding_exceeds_semantic)

        def contradictory_memory_classifier_generation(records):
            case = _find(
                records,
                "case",
                strategy="adaptive",
                case_id="memory_direct_fact",
            )
            case["route"]["memory_required_generation"]["content"] = (
                '{"memory_required":false}'
            )

        mutations.append(contradictory_memory_classifier_generation)

        def swapped_router_backend_calls(records):
            case = _find(
                records,
                "case",
                strategy="adaptive",
                case_id="memory_direct_fact",
            )
            calls = case["cascade"]["backend_calls"]
            calls[0], calls[1] = calls[1], calls[0]

        mutations.append(swapped_router_backend_calls)

        def route_generation_disagrees_with_backend_call(records):
            case = _find(
                records,
                "case",
                strategy="adaptive",
                case_id="route_small_no_memory_01",
            )
            case["cascade"]["backend_calls"][0]["generation"] = _generation(
                SMALL, '{"memory_required":true}'
            )

        mutations.append(route_generation_disagrees_with_backend_call)

        def too_many_backend_calls(records):
            case = _find(
                records,
                "case",
                strategy="adaptive",
                case_id="route_small_no_memory_01",
            )
            calls = case["cascade"]["backend_calls"]
            calls.extend((copy.deepcopy(calls[-1]), copy.deepcopy(calls[-1])))

        mutations.append(too_many_backend_calls)

        for mutation in mutations:
            with self.subTest(mutation=mutation.__name__):
                records = _raw_records()
                mutation(records)
                with self.assertRaises(EvaluationScoringError):
                    parse_observation_jsonl(_encode(records))

    def test_error_observation_can_retain_safe_partial_state(self):
        records = _raw_records()
        case = _find(
            records,
            "case",
            strategy="adaptive",
            case_id="route_small_no_memory_01",
        )
        case.update(
            {
                "status": "error",
                "error_stage": "generation",
                "error_type": "ConversationError",
            }
        )
        case["cascade"] = None
        _refresh_trailer(records)

        parsed = parse_observation_jsonl(_encode(records))
        self.assertEqual(parsed.cases[-30]["status"], "error")

    def test_newline_safe_interrupted_artifact_remains_scoreable(self):
        records = _raw_records()
        partial = records[:2]
        partial.extend(
            record
            for record in records
            if record["record_type"] == "retrieval"
        )
        partial.append(
            _find(
                records,
                "case",
                strategy="always_small_no_rag",
                case_id="route_small_no_memory_01",
            )
        )

        observations = parse_observation_jsonl(_encode(partial))
        summary = score_observations(load_evaluation_suite(), observations)

        self.assertFalse(observations.trailer_present)
        self.assertFalse(summary["protocol"]["complete"])
        self.assertEqual(
            summary["protocol"]["cascade"]["missing_records"], 119
        )

    def test_interruption_before_first_retrieval_keeps_component_denominator(self):
        observations = parse_observation_jsonl(_encode(_raw_records()[:2]))
        summary = score_observations(load_evaluation_suite(), observations)
        component = summary["objective_metrics"]["component_retrieval"]

        self.assertFalse(summary["protocol"]["complete"])
        self.assertEqual(summary["protocol"]["retrieval"]["missing_records"], 16)
        self.assertEqual(component["expected_attempts"], 16)
        self.assertEqual(component["error_rate"]["numerator"], 16)
        self.assertEqual(component["latency"]["retrieval_wall_ns"]["samples"], 0)


class ObjectiveScoringTests(unittest.TestCase):
    def setUp(self):
        self.suite = load_evaluation_suite()

    def test_perfect_objective_run_scores_all_denominators(self):
        observations = parse_observation_jsonl(_encode(_raw_records()))
        summary = score_observations(self.suite, observations)
        objective = summary["objective_metrics"]
        setup = objective["setup"]
        router = objective["router"]
        retrieval = objective["component_retrieval"]

        self.assertTrue(summary["protocol"]["complete"])
        self.assertEqual(setup["passage_embedding_calls"], 14)
        self.assertEqual(setup["materialization_wall_ns"]["p50_ns"], 4_000_000)
        self.assertEqual(router["expected_attempts"], 30)
        self.assertEqual(router["memory_accuracy"]["value"], 1.0)
        self.assertEqual(router["model_accuracy"]["value"], 1.0)
        self.assertEqual(router["joint_accuracy"]["value"], 1.0)
        self.assertEqual(router["small_model_rate"]["numerator"], 19)
        self.assertEqual(router["large_model_rate"]["numerator"], 11)

        self.assertEqual(retrieval["answerable_attempts"], 11)
        self.assertEqual(retrieval["empty_gold_attempts"], 5)
        self.assertAlmostEqual(retrieval["recall_at_1"]["value"], 49 / 66)
        self.assertEqual(retrieval["recall_at_3"]["value"], 1.0)
        self.assertEqual(retrieval["recall_at_5"]["value"], 1.0)
        self.assertEqual(retrieval["mrr"]["value"], 1.0)
        self.assertEqual(
            retrieval["empty_gold_false_retrieval_rate"]["value"], 0.0
        )
        rag_ordinals = [
            ordinal
            for ordinal, case in enumerate(self.suite.cases, 1)
            if "rag" in case.tags
        ]
        semantic_samples = sorted(
            ordinal * 30_000 for ordinal in rag_ordinals
        )
        keyword_samples = sorted(
            ordinal * 20_000 for ordinal in rag_ordinals
        )
        self.assertEqual(
            retrieval["latency"]["semantic_search_wall_ns"],
            {
                "samples": len(semantic_samples),
                "p50_ns": semantic_samples[(len(semantic_samples) - 1) // 2],
                "p95_ns": semantic_samples[
                    (95 * len(semantic_samples) + 99) // 100 - 1
                ],
            },
        )
        self.assertEqual(
            retrieval["latency"]["keyword_search_wall_ns"],
            {
                "samples": len(keyword_samples),
                "p50_ns": keyword_samples[(len(keyword_samples) - 1) // 2],
                "p95_ns": keyword_samples[
                    (95 * len(keyword_samples) + 99) // 100 - 1
                ],
            },
        )

        adaptive = objective["strategies"]["adaptive"]
        self.assertEqual(adaptive["structured_success_rate"]["value"], 1.0)
        self.assertEqual(adaptive["supplied_memory"]["micro_precision"]["value"], 1.0)
        self.assertEqual(adaptive["citation"]["micro_precision"]["value"], 1.0)
        self.assertEqual(adaptive["citation"]["micro_recall"]["value"], 1.0)
        self.assertEqual(
            adaptive["latency"]["cascade_wall_ns"]["p50_ns"], 15_000_000
        )
        self.assertEqual(
            adaptive["latency"]["cascade_wall_ns"]["p95_ns"], 29_000_000
        )
        memory_ordinals = [
            ordinal
            for ordinal, case in enumerate(self.suite.cases, 1)
            if case.expected_route.memory_required
        ]
        for field, multiplier in (
            ("cascade_retrieval_embedding_wall_ns", 10_000),
            ("cascade_retrieval_semantic_search_wall_ns", 30_000),
            ("cascade_retrieval_keyword_search_wall_ns", 20_000),
        ):
            expected = sorted(
                ordinal * multiplier for ordinal in memory_ordinals
            )
            with self.subTest(field=field):
                self.assertEqual(
                    adaptive["latency"][field],
                    {
                        "samples": len(expected),
                        "p50_ns": expected[(len(expected) - 1) // 2],
                        "p95_ns": expected[
                            (95 * len(expected) + 99) // 100 - 1
                        ],
                    },
                )
        self.assertEqual(
            objective["strategies"]["always_small_no_rag"]["latency"][
                "cascade_retrieval_semantic_search_wall_ns"
            ]["samples"],
            0,
        )

        self.assertIn("general", objective["category_slices"])
        self.assertEqual(
            objective["category_slices"]["correction"]["case_count"], 1
        )
        self.assertIsNone(summary["answer_quality"]["free_text_answer_accuracy"])
        self.assertIsNone(summary["answer_quality"]["hallucination_rate"])

    def test_scoring_rejects_stream_bound_to_different_gold_hash(self):
        records = _raw_records()
        wrong_hash = "f" * 64
        records[0]["suite_sha256"] = wrong_hash
        records[1]["suite_sha256"] = wrong_hash
        for record in records:
            if record["record_type"] in {"retrieval", "case"}:
                record["suite_sha256"] = wrong_hash

        observations = parse_observation_jsonl(_encode(records))
        with self.assertRaisesRegex(EvaluationScoringError, "exact gold"):
            score_observations(self.suite, observations)

    def test_single_strategy_artifact_is_complete_for_declared_scope(self):
        observations = parse_observation_jsonl(
            _encode(
                _raw_records(
                    strategies=("always_small_no_rag",),
                    include_retrieval=True,
                )
            )
        )
        summary = score_observations(self.suite, observations)

        self.assertTrue(summary["protocol"]["complete"])
        self.assertFalse(summary["protocol"]["all_strategies_present"])
        self.assertEqual(
            tuple(summary["objective_metrics"]["strategies"]),
            ("always_small_no_rag",),
        )
        self.assertEqual(
            summary["objective_metrics"]["router"]["expected_attempts"], 0
        )
        self.assertIn("| `adaptive` | N/A |", render_summary_markdown(summary))

    def test_rank_errors_false_retrieval_and_forbidden_hits_are_scored(self):
        records = _raw_records()
        relevant = "mem_00000000000000000000000000000001"
        irrelevant = "mem_00000000000000000000000000000003"
        direct = _find(records, "retrieval", case_id="memory_direct_fact")
        direct["ranked"] = [_match(irrelevant, 1), _match(relevant, 2)]

        absent = _find(records, "retrieval", case_id="memory_absent")
        absent["ranked"] = [_match(irrelevant, 1)]

        correction = _find(records, "retrieval", case_id="memory_correction")
        old_tea = "mem_00000000000000000000000000000002"
        correction["ranked"].append(_match(old_tea, 2))

        observations = parse_observation_jsonl(_encode(records))
        metrics = score_observations(self.suite, observations)[
            "objective_metrics"
        ]["component_retrieval"]

        self.assertEqual(metrics["mrr"]["value"], 10.5 / 11)
        self.assertEqual(
            metrics["empty_gold_false_retrieval_rate"],
            {"numerator": 1, "denominator": 5, "value": 0.2},
        )
        self.assertEqual(metrics["forbidden_hit_rate"]["numerator"], 1)

    def test_precision_labels_separate_answerable_and_all_rag_cases(self):
        records = _raw_records()
        baseline = score_observations(
            self.suite, parse_observation_jsonl(_encode(records))
        )["objective_metrics"]["component_retrieval"]
        absent = _find(records, "retrieval", case_id="memory_absent")
        absent["ranked"] = [
            _match("mem_00000000000000000000000000000003", 1)
        ]
        changed = score_observations(
            self.suite, parse_observation_jsonl(_encode(records))
        )["objective_metrics"]["component_retrieval"]

        self.assertEqual(
            baseline["answerable_micro_precision_at_5"],
            changed["answerable_micro_precision_at_5"],
        )
        self.assertEqual(baseline["overall_macro_precision_at_5"]["value"], 1.0)
        self.assertEqual(changed["overall_macro_precision_at_5"]["value"], 15 / 16)
        self.assertEqual(
            changed["overall_micro_precision_at_5"]["denominator"],
            baseline["overall_micro_precision_at_5"]["denominator"] + 1,
        )

    def test_unattempted_retrieval_has_no_latency_sample(self):
        records = _raw_records()
        failed = _find(records, "retrieval", case_id="memory_direct_fact")
        failed.update(
            {
                "status": "error",
                "error_type": "SetupError",
                "started_monotonic_ns": None,
                "finished_monotonic_ns": None,
                "wall_ns": None,
                "embedding_wall_ns": None,
                "semantic_search_wall_ns": None,
                "keyword_search_wall_ns": None,
                "ranked": [],
            }
        )
        _refresh_trailer(records)

        metrics = score_observations(
            self.suite, parse_observation_jsonl(_encode(records))
        )["objective_metrics"]["component_retrieval"]
        self.assertEqual(metrics["error_rate"]["numerator"], 1)
        self.assertEqual(metrics["latency"]["retrieval_wall_ns"]["samples"], 15)
        self.assertEqual(metrics["latency"]["embedding_wall_ns"]["samples"], 15)
        self.assertEqual(
            metrics["latency"]["semantic_search_wall_ns"]["samples"], 15
        )
        self.assertEqual(
            metrics["latency"]["keyword_search_wall_ns"]["samples"], 15
        )

    def test_generation_invocation_rates_include_failed_large_call_only_once(self):
        records = _raw_records()
        case = _find(
            records,
            "case",
            strategy="adaptive",
            case_id="route_large_no_memory_01",
        )
        cascade = case["cascade"]
        fallback_generation = _generation(SMALL)
        cascade["backend_calls"] = [
            *cascade["backend_calls"][:2],
            {
                "purpose": "generation",
                "model": LARGE,
                "wall_ns": 9_000_000,
                "status": "error",
                "error_type": "OllamaTimeoutError",
                "generation": None,
            },
            {
                "purpose": "generation",
                "model": SMALL,
                "wall_ns": 3_000_000,
                "status": "ok",
                "error_type": None,
                "generation": fallback_generation,
            },
        ]
        cascade["actual_model"] = SMALL
        cascade["fallback_from_model"] = LARGE
        cascade["generation"] = fallback_generation

        metrics = score_observations(
            self.suite, parse_observation_jsonl(_encode(records))
        )["objective_metrics"]["strategies"]["adaptive"]
        self.assertEqual(metrics["large_model_invocation_rate"]["numerator"], 11)
        self.assertEqual(metrics["small_model_invocation_rate"]["numerator"], 20)
        self.assertEqual(metrics["actual_large_model_rate"]["numerator"], 10)
        self.assertEqual(metrics["actual_small_model_rate"]["numerator"], 20)
        self.assertEqual(
            metrics["latency"]["route_backend_call_wall_ns"]["samples"], 60
        )
        self.assertEqual(
            metrics["latency"][
                "route_memory_required_backend_call_wall_ns"
            ]["samples"],
            30,
        )
        self.assertEqual(
            metrics["latency"][
                "route_model_size_backend_call_wall_ns"
            ]["samples"],
            30,
        )
        self.assertEqual(
            metrics["latency"]["generation_backend_call_wall_ns"]["samples"], 31
        )

    def test_missing_duplicate_and_error_attempts_do_not_inflate_metrics(self):
        records = _raw_records()
        missing = _find(
            records,
            "case",
            strategy="adaptive",
            case_id="route_small_no_memory_01",
        )
        records.remove(missing)
        duplicate = copy.deepcopy(
            _find(
                records,
                "case",
                strategy="adaptive",
                case_id="route_small_no_memory_02",
            )
        )
        records.insert(-1, duplicate)

        failed = _find(records, "retrieval", case_id="memory_direct_fact")
        failed.update(
            {
                "status": "error",
                "error_type": "EmbeddingError",
                "finished_monotonic_ns": (
                    failed["started_monotonic_ns"] + 123
                ),
                "wall_ns": 123,
                "embedding_wall_ns": None,
                "semantic_search_wall_ns": None,
                "keyword_search_wall_ns": None,
                "ranked": [],
            }
        )
        records[-1]["completed"] = False
        _refresh_trailer(records)

        observations = parse_observation_jsonl(_encode(records))
        summary = score_observations(self.suite, observations)

        self.assertFalse(summary["protocol"]["complete"])
        self.assertEqual(summary["protocol"]["cascade"]["missing_records"], 1)
        self.assertEqual(summary["protocol"]["cascade"]["duplicate_records"], 1)
        router = summary["objective_metrics"]["router"]
        self.assertEqual(router["joint_accuracy"]["denominator"], 30)
        self.assertEqual(router["joint_accuracy"]["numerator"], 29)
        retrieval = summary["objective_metrics"]["component_retrieval"]
        self.assertEqual(retrieval["error_rate"]["numerator"], 1)
        self.assertEqual(retrieval["recall_at_5"]["samples"], 11)

    def test_supplied_and_citation_metrics_use_actual_cascade_ids(self):
        records = _raw_records()
        case = _find(
            records,
            "case",
            strategy="adaptive",
            case_id="memory_correction",
        )
        new_tea = "mem_00000000000000000000000000000009"
        old_tea = "mem_00000000000000000000000000000002"
        case["cascade"]["retrieved_ranked"] = [
            _match(new_tea, 1),
            _match(old_tea, 2),
        ]
        case["cascade"]["supplied_ids"] = [new_tea, old_tea]
        case["cascade"]["response"]["memory_used"] = [old_tea]

        observations = parse_observation_jsonl(_encode(records))
        metrics = score_observations(self.suite, observations)[
            "objective_metrics"
        ]["strategies"]["adaptive"]

        self.assertLess(
            metrics["supplied_memory"]["micro_precision"]["value"], 1.0
        )
        self.assertEqual(
            metrics["supplied_memory"]["forbidden_hit_rate"]["numerator"],
            1,
        )
        self.assertLess(metrics["citation"]["micro_recall"]["value"], 1.0)
        self.assertEqual(metrics["citation"]["forbidden_citation_rate"]["numerator"], 1)

    def test_summary_and_blinded_sheet_are_canonical_and_do_not_claim_quality(self):
        observations = parse_observation_jsonl(_encode(_raw_records()))
        summary = score_observations(self.suite, observations)

        encoded = canonical_summary_json(summary)
        self.assertEqual(encoded, canonical_summary_json(summary))
        self.assertEqual(json.loads(encoded), summary)

        sheet = emit_blinded_review_sheet(self.suite, observations)
        items = [json.loads(line) for line in sheet.splitlines()]
        self.assertEqual(len(items), 120)
        self.assertEqual(
            [item["review_id"] for item in items],
            sorted(item["review_id"] for item in items),
        )
        flattened = json.dumps(items)
        for hidden in ("strategy", "actual_model", "requested_model", "run_id"):
            self.assertNotIn(f'"{hidden}"', flattened)
        for hidden_value in (*STRATEGIES, SMALL, LARGE, "run_perfect"):
            self.assertNotIn(hidden_value, flattened)
        self.assertTrue(
            all(item["judgment"]["overall_correct"] is None for item in items)
        )
        self.assertTrue(
            all(item["response_status"] == "answered" for item in items)
        )
        self.assertEqual(sheet, emit_blinded_review_sheet(self.suite, observations))

        markdown = render_summary_markdown(summary)
        self.assertIn("pending_blinded_human_review", markdown)
        self.assertIn("No answer-accuracy", markdown)
        self.assertNotIn("100.00% answer accuracy", markdown)

    def test_review_sheet_keeps_failed_missing_and_duplicate_attempts(self):
        strategy = "always_small_no_rag"
        records = _raw_records(
            run_id="run_review_fail_closed",
            strategies=(strategy,),
        )
        missing_case, failed_case, duplicate_case = self.suite.cases[:3]

        missing = _find(
            records,
            "case",
            strategy=strategy,
            case_id=missing_case.id,
        )
        records.remove(missing)

        failed = _find(
            records,
            "case",
            strategy=strategy,
            case_id=failed_case.id,
        )
        failed.update(
            {
                "status": "error",
                "error_stage": "generation",
                "error_type": "ConversationError",
            }
        )

        duplicate = copy.deepcopy(
            _find(
                records,
                "case",
                strategy=strategy,
                case_id=duplicate_case.id,
            )
        )
        duplicate["cascade"]["response"]["speech"] = (
            "DUPLICATE RESPONSE MUST NOT ENTER THE REVIEW SHEET"
        )
        records.insert(-1, duplicate)
        records[-1]["completed"] = False
        _refresh_trailer(records)

        observations = parse_observation_jsonl(_encode(records))
        items = [
            json.loads(line)
            for line in emit_blinded_review_sheet(
                self.suite, observations
            ).splitlines()
        ]
        by_prompt = {item["prompt"]: item for item in items}

        self.assertEqual(len(items), 30)
        self.assertEqual(len({item["review_id"] for item in items}), 30)
        self.assertEqual(
            by_prompt[missing_case.prompt]["response_status"],
            "missing_observation",
        )
        self.assertEqual(
            by_prompt[failed_case.prompt]["response_status"],
            "failed_observation",
        )
        self.assertEqual(
            by_prompt[duplicate_case.prompt]["response_status"],
            "duplicate_observation",
        )
        for case in (missing_case, failed_case, duplicate_case):
            item = by_prompt[case.prompt]
            self.assertIsNone(item["response_speech"])
            self.assertFalse(item["judgment"]["overall_correct"])
            self.assertIn("Automatically incorrect", item["judgment"]["notes"])
        self.assertNotIn(
            "DUPLICATE RESPONSE MUST NOT ENTER THE REVIEW SHEET",
            json.dumps(items),
        )
        summary = score_observations(self.suite, observations)
        self.assertEqual(summary["answer_quality"]["review_items"], 30)

        complete = parse_observation_jsonl(
            _encode(
                _raw_records(
                    run_id="run_review_fail_closed",
                    strategies=(strategy,),
                )
            )
        )
        complete_ids = {
            item["review_id"]
            for item in (
                json.loads(line)
                for line in emit_blinded_review_sheet(
                    self.suite, complete
                ).splitlines()
            )
        }
        self.assertEqual(
            {item["review_id"] for item in items}, complete_ids
        )

    def test_interrupted_review_sheet_preserves_all_declared_slots(self):
        records = _raw_records(
            run_id="run_review_interrupted",
            strategies=STRATEGIES[:2],
            repetitions=2,
        )
        complete = parse_observation_jsonl(_encode(records))
        interrupted = parse_observation_jsonl(_encode(records[:2]))

        complete_items = [
            json.loads(line)
            for line in emit_blinded_review_sheet(
                self.suite, complete
            ).splitlines()
        ]
        interrupted_sheet = emit_blinded_review_sheet(self.suite, interrupted)
        interrupted_items = [
            json.loads(line) for line in interrupted_sheet.splitlines()
        ]

        self.assertEqual(len(interrupted_items), 2 * 2 * 30)
        self.assertEqual(
            {item["review_id"] for item in interrupted_items},
            {item["review_id"] for item in complete_items},
        )
        self.assertTrue(
            all(
                item["response_status"] == "missing_observation"
                and item["response_speech"] is None
                and item["judgment"]["overall_correct"] is False
                for item in interrupted_items
            )
        )
        self.assertEqual(
            interrupted_sheet,
            emit_blinded_review_sheet(self.suite, interrupted),
        )
        summary = score_observations(self.suite, interrupted)
        self.assertEqual(summary["answer_quality"]["review_items"], 120)


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.suite = load_evaluation_suite()

    def test_disjoint_strategy_runs_merge_into_complete_scoring_view(self):
        first_strategies = STRATEGIES[:2]
        second_strategies = STRATEGIES[2:]
        first = parse_observation_jsonl(
            _encode(
                _raw_records(
                    run_id="run_first",
                    strategies=first_strategies,
                    include_retrieval=True,
                )
            )
        )
        second = parse_observation_jsonl(
            _encode(
                _raw_records(
                    run_id="run_second",
                    strategies=second_strategies,
                    include_retrieval=False,
                )
            )
        )

        merged = merge_observation_runs((second, first))
        summary = score_observations(self.suite, merged)

        self.assertEqual(merged.header["strategies"], STRATEGIES)
        self.assertTrue(summary["protocol"]["complete"])
        self.assertEqual(len(merged.cases), 120)
        self.assertEqual(len(merged.retrievals), 16)
        self.assertEqual(
            merged.header["runtime"]["retrieval_source_run_id"], "run_first"
        )

    def test_merge_rejects_strategy_overlap_and_ambiguous_retrieval_source(self):
        first = parse_observation_jsonl(
            _encode(
                _raw_records(
                    run_id="run_one",
                    strategies=("always_small_no_rag",),
                    include_retrieval=True,
                )
            )
        )
        overlapping = parse_observation_jsonl(
            _encode(
                _raw_records(
                    run_id="run_two",
                    strategies=("always_small_no_rag",),
                    include_retrieval=False,
                )
            )
        )
        with self.assertRaisesRegex(EvaluationScoringError, "overlapping"):
            merge_observation_runs((first, overlapping))

        second = parse_observation_jsonl(
            _encode(
                _raw_records(
                    run_id="run_three",
                    strategies=("always_large_no_rag",),
                    include_retrieval=True,
                )
            )
        )
        with self.assertRaisesRegex(EvaluationScoringError, "retrieval_run_id"):
            merge_observation_runs((first, second))
        selected = merge_observation_runs(
            (first, second), retrieval_run_id="run_three"
        )
        self.assertEqual(
            selected.header["runtime"]["retrieval_source_run_id"], "run_three"
        )


if __name__ == "__main__":
    unittest.main()
