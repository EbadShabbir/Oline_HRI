from dataclasses import fields
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from oline_hri.config import load_config
from oline_hri.evaluation import load_evaluation_suite
from oline_hri.evaluation_runner import (
    ADAPTIVE,
    ALWAYS_LARGE_NO_RAG,
    ALWAYS_LARGE_WITH_RAG,
    ALWAYS_SMALL_NO_RAG,
    CASCADE_STRATEGIES,
    EVALUATION_SEED,
    EVALUATION_TEMPERATURE,
    EvaluationRunError,
    EvaluationRunSummary,
    ExecutionCase,
    _RecordingRetriever,
    _TimedSearchBackend,
    _chat_result_record,
    _ranked_records,
    evaluation_suite_sha256,
    execution_cases,
    main,
    run_evaluation,
)
from oline_hri.evaluation_scoring import (
    load_observation_jsonl,
    score_observations,
)
from oline_hri.ollama import ChatResult, OllamaTimeoutError
from oline_hri.embedding import EMBEDDING_DIMENSION, MODEL_ID, MODEL_REVISION
from oline_hri.retrieval import HybridMatch, HybridRetriever


FIXED_NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def _chat_result(model: str, content: str) -> ChatResult:
    return ChatResult(
        model=model,
        content=content,
        done_reason="stop",
        total_duration_ns=100,
        load_duration_ns=10,
        prompt_eval_count=7,
        eval_count=5,
        eval_duration_ns=50_000_000,
    )


def _active_match() -> HybridMatch:
    suite = load_evaluation_suite()
    item = next(
        event.record
        for event in suite.memory_events
        if event.record is not None
        and event.record.id == "mem_00000000000000000000000000000001"
    )
    return HybridMatch(
        memory=item,
        fused_score=1.0 / 61.0,
        keyword_rank=-1.0,
        keyword_position=1,
        semantic_score=0.9,
        semantic_position=1,
    )


class FakeRetriever:
    def __init__(self, *, fail_calls=()) -> None:
        self.calls = []
        self.current_calls = []
        self._fail_calls = set(fail_calls)
        self._match = _active_match()

    def retrieve(self, query, *, limit=3):
        self.calls.append((query, limit))
        if len(self.calls) in self._fail_calls:
            raise RuntimeError("private retrieval detail")
        return (self._match,)

    def is_current(self, matches):
        self.current_calls.append(tuple(matches))
        return True


class FakeEmbedder:
    model_id = MODEL_ID
    model_revision = MODEL_REVISION
    dimension = EMBEDDING_DIMENSION

    def __init__(self, *, fail_passages=False) -> None:
        self.fail_passages = fail_passages
        self.passage_calls = []
        self.query_calls = []

    def _vector(self, text):
        vector = np.zeros(EMBEDDING_DIMENSION, dtype=np.float32)
        index = int.from_bytes(
            sha256(text.encode("utf-8")).digest()[:2], "big"
        )
        vector[index % EMBEDDING_DIMENSION] = 1.0
        return vector

    def embed_passages(self, passages):
        values = tuple(passages)
        self.passage_calls.append(values)
        if self.fail_passages:
            raise RuntimeError("private passage failure")
        return np.stack([self._vector(value) for value in values])

    def embed_query(self, query):
        self.query_calls.append(query)
        return self._vector(query)


class FakeBackend:
    def __init__(
        self,
        *,
        route_memory=True,
        route_size="small",
        fail_route_calls=(),
        fail_generation_calls=(),
        timeout_generation_calls=(),
        invalid_generation_calls=(),
        interrupt_generation_call=None,
    ) -> None:
        self.route_memory = route_memory
        self.route_size = route_size
        self.fail_route_calls = set(fail_route_calls)
        self.fail_generation_calls = set(fail_generation_calls)
        self.timeout_generation_calls = set(timeout_generation_calls)
        self.invalid_generation_calls = set(invalid_generation_calls)
        self.interrupt_generation_call = interrupt_generation_call
        self.calls = []
        self.route_calls = 0
        self.generation_calls = 0

    def chat(
        self,
        model,
        messages,
        *,
        response_format=None,
        temperature=None,
        seed=None,
    ):
        properties = response_format["properties"]
        fields = set(properties)
        if fields == {"form", "memory_required"}:
            purpose = "route_memory_required"
        elif fields == {"model_size"}:
            purpose = "route_model_size"
        else:
            purpose = "generation"
        self.calls.append(
            {
                "purpose": purpose,
                "model": model,
                "messages": tuple(messages),
                "temperature": temperature,
                "seed": seed,
            }
        )
        if purpose == "route_memory_required":
            self.route_calls += 1
            if self.route_calls in self.fail_route_calls:
                raise RuntimeError("private route detail")
            content = json.dumps(
                {"form": "question", "memory_required": self.route_memory},
                separators=(",", ":"),
            )
            return _chat_result(model, content)
        if purpose == "route_model_size":
            self.route_calls += 1
            if self.route_calls in self.fail_route_calls:
                raise RuntimeError("private route detail")
            content = json.dumps(
                {"model_size": self.route_size},
                separators=(",", ":"),
            )
            return _chat_result(model, content)

        self.generation_calls += 1
        if self.generation_calls == self.interrupt_generation_call:
            raise KeyboardInterrupt()
        if self.generation_calls in self.timeout_generation_calls:
            raise OllamaTimeoutError("private timeout detail")
        if self.generation_calls in self.fail_generation_calls:
            raise RuntimeError("private generation detail")
        if self.generation_calls in self.invalid_generation_calls:
            return _chat_result(model, "not-json-secret-output")
        allowed = tuple(
            properties["memory_used"]["items"].get("enum", ())
        )
        cited = allowed
        speech = "synthetic answer marker"
        for message in reversed(messages):
            marker = "PERSONAL_MEMORY_DATA="
            request_marker = "\nCURRENT_USER_REQUEST="
            if marker not in message.content:
                continue
            encoded = message.content.split(marker, 1)[1]
            encoded_records = encoded.split(request_marker, 1)[0]
            records = json.loads(encoded_records)["records"]
            grounded_parts = []
            for record in records:
                grounded_parts.append(record["canonical_text"])
                if record.get("event_time") is not None:
                    grounded_parts.append("Event time: " + record["event_time"])
                if record.get("correction_effective_time") is not None:
                    grounded_parts.append(
                        "Correction effective time: "
                        + record["correction_effective_time"]
                    )
            speech += " " + " ".join(grounded_parts)
            break
        content = json.dumps(
            {
                "speech": speech,
                "gesture_id": "NO_ACTION",
                "memory_used": list(cited),
            },
            separators=(",", ":"),
        )
        return _chat_result(model, content)


class RecordingTelemetry:
    def __init__(self) -> None:
        self.entered = 0
        self.exited = 0
        self.exception_type = None
        self.active = False

    def __enter__(self):
        self.entered += 1
        self.active = True
        return self

    def __exit__(self, exception_type, exception, traceback):
        self.exited += 1
        self.exception_type = exception_type
        self.active = False
        return False


def _records(path: Path):
    return tuple(
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    )


class EvaluationRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.suite = load_evaluation_suite()
        self.config = load_config()

    def _private_output(self, root: str, name: str = "run.jsonl") -> Path:
        private = Path(root) / "private"
        private.mkdir(mode=0o700)
        return private / name

    def test_execution_projection_contains_only_case_id_and_prompt(self) -> None:
        projected = execution_cases(self.suite)

        self.assertEqual(
            tuple(field.name for field in fields(ExecutionCase)),
            ("case_id", "prompt"),
        )
        self.assertEqual(len(projected), 30)
        self.assertEqual(len(execution_cases(self.suite, track="rag")), 16)
        self.assertEqual(
            tuple(item.case_id for item in projected),
            tuple(case.id for case in self.suite.cases),
        )
        for item in projected:
            self.assertEqual(set(item.__dict__), {"case_id", "prompt"})
        self.assertEqual(
            evaluation_suite_sha256(self.suite),
            evaluation_suite_sha256(self.suite),
        )

    def test_artifact_validators_match_strict_scorer_bounds(self) -> None:
        match = _active_match()
        invalid_fused = HybridMatch(
            memory=match.memory,
            fused_score=1.000001,
            keyword_rank=match.keyword_rank,
            keyword_position=match.keyword_position,
            semantic_score=match.semantic_score,
            semantic_position=match.semantic_position,
        )

        with self.assertRaises(EvaluationRunError):
            _ranked_records((invalid_fused,))
        self.assertIsNone(
            _chat_result_record(_chat_result("qwen3:0.6b", " padded "))
        )
        self.assertIsNone(
            _chat_result_record(_chat_result("qwen3:0.6b", "bad\x00content"))
        )

    def test_all_strategies_write_gold_free_canonical_complete_artifact(self) -> None:
        backend = FakeBackend(route_memory=True, route_size="small")
        retriever = FakeRetriever()
        progress = io.StringIO()
        telemetry = RecordingTelemetry()
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)

            summary = run_evaluation(
                self.suite,
                self.config,
                output,
                backend=backend,
                retriever=retriever,
                run_id="fixed-run",
                utc_now=lambda: FIXED_NOW,
                progress=progress,
                telemetry=telemetry,
            )

            raw = output.read_text(encoding="utf-8")
            records = _records(output)
            metadata = os.stat(output)
            observations = load_observation_jsonl(output)
            scored = score_observations(self.suite, observations)

        self.assertEqual(stat.S_IMODE(metadata.st_mode), 0o600)
        self.assertEqual(summary.retrieval_records, 16)
        self.assertEqual(summary.cascade_records, 120)
        self.assertEqual(summary.retrieval_errors, 0)
        # The one-record fake lacks the collaborator requested by recency.
        # Both retrieval-enabled strategies must now withhold that partial answer.
        self.assertEqual(summary.cascade_errors, 2)
        self.assertEqual(len(records), 139)
        header, trailer = records[0], records[-1]
        setup = next(item for item in records if item["record_type"] == "setup")
        retrieval_records = tuple(
            item for item in records if item["record_type"] == "retrieval"
        )
        case_records = tuple(
            item for item in records if item["record_type"] == "case"
        )
        self.assertEqual({r['case_id'] for r in case_records if r['status'] == 'error'},
                         {'memory_large_recency'})

        self.assertEqual(header["record_type"], "header")
        self.assertEqual(setup["status"], "ok")
        self.assertEqual(setup["materialization_wall_ns"], 0)
        self.assertEqual(setup["passage_embedding_wall_ns"], 0)
        self.assertEqual(setup["passage_embedding_calls"], 0)
        self.assertEqual(
            setup["finished_monotonic_ns"] - setup["started_monotonic_ns"],
            setup["wall_ns"],
        )
        self.assertEqual(header["strategies"], list(CASCADE_STRATEGIES))
        self.assertEqual(header["retrieval_limit"], 5)
        self.assertEqual(trailer["record_type"], "trailer")
        self.assertTrue(trailer["completed"])
        self.assertEqual(trailer["written_retrieval_records"], 16)
        self.assertEqual(trailer["written_cascade_records"], 120)
        self.assertEqual(len(retrieval_records), 16)
        self.assertEqual(len(case_records), 120)
        self.assertTrue(
            all(
                item["semantic_search_wall_ns"] is None
                and item["keyword_search_wall_ns"] is None
                for item in retrieval_records
            )
        )
        self.assertTrue(
            all(
                item["cascade"]["retrieval_embedding_wall_ns"] is None
                and item["cascade"]["retrieval_semantic_search_wall_ns"]
                is None
                and item["cascade"]["retrieval_keyword_search_wall_ns"]
                is None
                for item in case_records
            )
        )
        self.assertTrue(scored["protocol"]["complete"])
        self.assertTrue(
            all(
                item["finished_monotonic_ns"]
                - item["started_monotonic_ns"]
                == item["wall_ns"]
                for item in retrieval_records
            )
        )
        self.assertEqual(
            {item["strategy"] for item in case_records},
            set(CASCADE_STRATEGIES),
        )
        self.assertEqual(
            len(
                {
                    (item["repetition"], item["strategy"], item["case_id"])
                    for item in case_records
                }
            ),
            120,
        )

        forbidden_names = (
            "expected_route",
            "retrieval_gold",
            "answer_rubric",
            "reference_answer",
            "required_claims",
            "Hello there.",
        )
        for forbidden in forbidden_names:
            self.assertNotIn(forbidden, raw)
        for line in raw.splitlines():
            decoded = json.loads(line)
            self.assertEqual(
                line,
                json.dumps(
                    decoded,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )

        self.assertEqual(
            [limit for _, limit in retriever.calls[:16]],
            [5] * 16,
        )
        self.assertEqual(
            sum(limit == 3 for _, limit in retriever.calls[16:]),
            48,
        )
        routes = {
            strategy: next(
                item["route"]
                for item in case_records
                if item["strategy"] == strategy
            )
            for strategy in CASCADE_STRATEGIES
        }
        self.assertEqual(
            (routes[ALWAYS_SMALL_NO_RAG]["memory_required"],
             routes[ALWAYS_SMALL_NO_RAG]["model_size"]),
            (False, "small"),
        )
        self.assertEqual(
            (routes[ALWAYS_LARGE_NO_RAG]["memory_required"],
             routes[ALWAYS_LARGE_NO_RAG]["model_size"]),
            (False, "large"),
        )
        self.assertEqual(
            (routes[ALWAYS_LARGE_WITH_RAG]["memory_required"],
             routes[ALWAYS_LARGE_WITH_RAG]["model_size"]),
            (True, "large"),
        )
        self.assertEqual(
            (routes[ADAPTIVE]["memory_required"],
             routes[ADAPTIVE]["model_size"]),
            (True, "small"),
        )
        self.assertIsInstance(routes[ADAPTIVE]["wall_ns"], int)
        self.assertIsNotNone(
            routes[ADAPTIVE]["memory_required_generation"]
        )
        self.assertIsNotNone(routes[ADAPTIVE]["model_size_generation"])
        for strategy in (
            ALWAYS_SMALL_NO_RAG,
            ALWAYS_LARGE_NO_RAG,
            ALWAYS_LARGE_WITH_RAG,
        ):
            self.assertIsNone(routes[strategy]["memory_required_generation"])
            self.assertIsNone(routes[strategy]["model_size_generation"])
        artifact_backend_calls = tuple(
            call
            for item in case_records
            for call in item["cascade"]["backend_calls"]
        )
        self.assertEqual(
            {call["purpose"] for call in artifact_backend_calls},
            {
                "route_memory_required",
                "route_model_size",
                "generation",
            },
        )
        self.assertTrue(
            all(call["temperature"] == EVALUATION_TEMPERATURE for call in backend.calls)
        )
        self.assertTrue(all(call["seed"] == EVALUATION_SEED for call in backend.calls))
        generation_calls = (
            call for call in backend.calls if call["purpose"] == "generation"
        )
        self.assertTrue(
            all(
                not any(message.role == "assistant" for message in call["messages"])
                for call in generation_calls
            )
        )
        self.assertEqual(telemetry.entered, 1)
        self.assertEqual(telemetry.exited, 1)
        self.assertIsNone(telemetry.exception_type)
        self.assertNotIn("synthetic answer marker", progress.getvalue())
        self.assertNotIn("Hello there.", progress.getvalue())

    def test_case_failures_are_recorded_and_later_cases_continue(self) -> None:
        backend = FakeBackend(fail_generation_calls=(1,))
        retriever = FakeRetriever(fail_calls=(1,))
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)

            summary = run_evaluation(
                self.suite,
                self.config,
                output,
                strategies=(ALWAYS_SMALL_NO_RAG,),
                backend=backend,
                retriever=retriever,
                run_id="failure-run",
                utc_now=lambda: FIXED_NOW,
            )
            records = _records(output)

        retrieval_records = tuple(
            item for item in records if item["record_type"] == "retrieval"
        )
        case_records = tuple(
            item for item in records if item["record_type"] == "case"
        )
        self.assertEqual(summary.retrieval_records, 16)
        self.assertEqual(summary.retrieval_errors, 1)
        self.assertEqual(summary.cascade_records, 30)
        self.assertEqual(summary.cascade_errors, 1)
        self.assertEqual(retrieval_records[0]["status"], "error")
        self.assertEqual(retrieval_records[0]["error_type"], "RuntimeError")
        self.assertTrue(all(item["status"] == "ok" for item in retrieval_records[1:]))
        self.assertEqual(case_records[0]["status"], "error")
        self.assertEqual(case_records[0]["error_stage"], "generation")
        self.assertEqual(case_records[0]["error_type"], "ConversationError")
        self.assertTrue(all(item["status"] == "ok" for item in case_records[1:]))
        self.assertTrue(records[-1]["completed"])
        self.assertEqual(records[-1]["error_retrieval_records"], 1)
        self.assertEqual(records[-1]["error_cascade_records"], 1)

    def test_second_classifier_failure_retains_both_route_attempts(self) -> None:
        backend = FakeBackend(fail_route_calls=(2,))
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)

            summary = run_evaluation(
                self.suite,
                self.config,
                output,
                strategies=(ADAPTIVE,),
                backend=backend,
                retriever=FakeRetriever(),
                run_id="route-failure-run",
                utc_now=lambda: FIXED_NOW,
            )
            records = _records(output)
            observations = load_observation_jsonl(output)

        cases = tuple(
            item for item in records if item["record_type"] == "case"
        )
        first = cases[0]
        self.assertEqual(summary.cascade_errors, 2)  # Classifier + absent collaborator.
        self.assertEqual(first["status"], "error")
        self.assertEqual(first["error_stage"], "route")
        self.assertIsNone(first["route"])
        self.assertEqual(
            [
                (call["purpose"], call["status"])
                for call in first["cascade"]["backend_calls"]
            ],
            [
                ("route_memory_required", "ok"),
                ("route_model_size", "error"),
            ],
        )
        self.assertEqual(observations.cases[0]["status"], "error")
        self.assertEqual(cases[1]["status"], "ok")

    def test_real_memory_replay_records_setup_embedding_timings(self) -> None:
        backend = FakeBackend()
        telemetry = RecordingTelemetry()
        telemetry_states = []

        class ObservedFakeEmbedder(FakeEmbedder):
            def embed_passages(self, passages):
                telemetry_states.append(telemetry.active)
                return super().embed_passages(passages)

            def embed_query(self, query):
                telemetry_states.append(telemetry.active)
                return super().embed_query(query)

        embedder = ObservedFakeEmbedder()
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)

            summary = run_evaluation(
                self.suite,
                self.config,
                output,
                strategies=(ALWAYS_LARGE_WITH_RAG,),
                backend=backend,
                embedder=embedder,
                run_id="materialized-run",
                utc_now=lambda: FIXED_NOW,
                telemetry=telemetry,
            )
            records = _records(output)
            remaining = tuple(output.parent.iterdir())

        setup = next(item for item in records if item["record_type"] == "setup")
        retrievals = tuple(
            item for item in records if item["record_type"] == "retrieval"
        )
        self.assertEqual(setup["status"], "ok")
        self.assertEqual(
            setup["finished_monotonic_ns"] - setup["started_monotonic_ns"],
            setup["wall_ns"],
        )
        self.assertGreaterEqual(setup["materialization_wall_ns"], 0)
        self.assertGreaterEqual(setup["passage_embedding_wall_ns"], 0)
        self.assertEqual(setup["passage_embedding_calls"], 14)
        self.assertEqual(len(embedder.passage_calls), 14)
        self.assertEqual(len(embedder.query_calls), 43)
        self.assertTrue(telemetry_states)
        self.assertTrue(all(telemetry_states))
        self.assertTrue(
            all(item["embedding_wall_ns"] is not None for item in retrievals)
        )
        self.assertTrue(
            all(
                item["semantic_search_wall_ns"] is not None
                and item["keyword_search_wall_ns"] is not None
                and item["embedding_wall_ns"]
                <= item["semantic_search_wall_ns"]
                <= item["wall_ns"]
                and item["keyword_search_wall_ns"] <= item["wall_ns"]
                for item in retrievals
            )
        )
        cascades = tuple(
            item["cascade"]
            for item in records
            if item["record_type"] == "case"
        )
        self.assertEqual(len(cascades), 30)
        self.assertTrue(
            all(
                item["retrieval_invoked"]
                and item["retrieval_embedding_wall_ns"] is not None
                and item["retrieval_semantic_search_wall_ns"] is not None
                and item["retrieval_keyword_search_wall_ns"] is not None
                and item["retrieval_embedding_wall_ns"]
                <= item["retrieval_semantic_search_wall_ns"]
                <= item["retrieval_wall_ns"]
                and item["retrieval_keyword_search_wall_ns"]
                <= item["retrieval_wall_ns"]
                for item in cascades if not item.get("privacy_gate")
            )
        )
        self.assertEqual(summary.retrieval_errors, 0)
        # This test exercises real replay/index timing with a deliberately
        # content-agnostic fake embedder and generator. Stricter response
        # grounding may reject those synthetic answers; the summary must still
        # account for every such case consistently.
        self.assertEqual(
            summary.cascade_errors,
            sum(item["response"] is None for item in cascades),
        )
        self.assertEqual(remaining, (output,))

    def test_source_timing_keeps_error_leg_and_nulls_unattempted_leg(self) -> None:
        class SemanticFailureBackend:
            def search_semantic(self, query, *, limit=5):
                raise RuntimeError("private semantic detail")

            def search_keywords(self, query, *, limit=5):
                raise AssertionError("keyword search must not be attempted")

            def retrieval_snapshot_is_current(self, items):
                return True

        ticks = iter((100, 110, 140, 160))
        clock = lambda: next(ticks)
        search = _TimedSearchBackend(SemanticFailureBackend(), clock)
        retriever = _RecordingRetriever(
            HybridRetriever(search), clock, None, search
        )

        with self.assertRaises(RuntimeError):
            retriever.retrieve("valid question", limit=5)

        self.assertEqual(len(retriever.retrieve_calls), 1)
        observation = retriever.retrieve_calls[0]
        self.assertEqual(observation["status"], "error")
        self.assertEqual(observation["wall_ns"], 60)
        self.assertIsNone(observation["embedding_wall_ns"])
        self.assertEqual(observation["semantic_search_wall_ns"], 30)
        self.assertIsNone(observation["keyword_search_wall_ns"])

    def test_setup_failure_is_recorded_for_every_expected_slot(self) -> None:
        backend = FakeBackend()
        embedder = FakeEmbedder(fail_passages=True)
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)

            summary = run_evaluation(
                self.suite,
                self.config,
                output,
                strategies=(ALWAYS_SMALL_NO_RAG,),
                backend=backend,
                embedder=embedder,
                run_id="setup-failure-run",
                utc_now=lambda: FIXED_NOW,
            )
            records = _records(output)

        setup = next(item for item in records if item["record_type"] == "setup")
        retrievals = tuple(
            item for item in records if item["record_type"] == "retrieval"
        )
        cases = tuple(
            item for item in records if item["record_type"] == "case"
        )
        self.assertEqual(setup["status"], "error")
        self.assertEqual(setup["error_type"], "EvaluationReplayError")
        self.assertEqual(setup["passage_embedding_calls"], 1)
        self.assertEqual(
            setup["finished_monotonic_ns"] - setup["started_monotonic_ns"],
            setup["wall_ns"],
        )
        self.assertEqual(summary.retrieval_errors, 16)
        self.assertEqual(summary.cascade_errors, 30)
        self.assertTrue(all(item["status"] == "error" for item in retrievals))
        self.assertTrue(
            all(
                item["started_monotonic_ns"] is None
                and item["finished_monotonic_ns"] is None
                and item["wall_ns"] is None
                and item["embedding_wall_ns"] is None
                and item["semantic_search_wall_ns"] is None
                and item["keyword_search_wall_ns"] is None
                for item in retrievals
            )
        )
        self.assertTrue(all(item["status"] == "error" for item in cases))
        self.assertTrue(records[-1]["completed"])

    def test_unattempted_setup_stages_have_null_latency(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)
            with patch(
                "oline_hri.evaluation_runner.BgeOnnxEmbedder",
                side_effect=RuntimeError("private constructor failure"),
            ):
                run_evaluation(
                    self.suite,
                    self.config,
                    output,
                    strategies=(ALWAYS_SMALL_NO_RAG,),
                    backend=FakeBackend(),
                    run_id="unattempted-setup-run",
                    utc_now=lambda: FIXED_NOW,
                )
            records = _records(output)
            observations = load_observation_jsonl(output)

        setup = records[1]
        self.assertEqual(setup["status"], "error")
        self.assertIsNone(setup["materialization_wall_ns"])
        self.assertIsNone(setup["passage_embedding_wall_ns"])
        self.assertEqual(setup["passage_embedding_calls"], 0)
        self.assertTrue(
            all(item["wall_ns"] is None for item in observations.retrievals)
        )

    def test_raw_chat_result_survives_response_validation_failure(self) -> None:
        backend = FakeBackend(invalid_generation_calls=(1,))
        retriever = FakeRetriever()
        progress = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)

            run_evaluation(
                self.suite,
                self.config,
                output,
                strategies=(ALWAYS_SMALL_NO_RAG,),
                backend=backend,
                retriever=retriever,
                run_id="invalid-response-run",
                utc_now=lambda: FIXED_NOW,
                progress=progress,
            )
            records = _records(output)

        first = next(item for item in records if item["record_type"] == "case")
        self.assertEqual(first["status"], "error")
        self.assertEqual(first["error_stage"], "response")
        self.assertIsNone(first["cascade"]["response"])
        self.assertEqual(
            first["cascade"]["generation"]["content"],
            "not-json-secret-output",
        )
        self.assertEqual(
            first["cascade"]["backend_calls"][0]["generation"]["content"],
            "not-json-secret-output",
        )
        self.assertNotIn("not-json-secret-output", progress.getvalue())

    def test_failed_grounded_generation_retains_exact_supplied_ids(self) -> None:
        backend = FakeBackend(fail_generation_calls=(1,))
        retriever = FakeRetriever()
        expected_id = _active_match().memory.id
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)

            run_evaluation(
                self.suite,
                self.config,
                output,
                strategies=(ALWAYS_LARGE_WITH_RAG,),
                backend=backend,
                retriever=retriever,
                run_id="grounded-failure-run",
                utc_now=lambda: FIXED_NOW,
            )
            records = _records(output)
            observations = load_observation_jsonl(output)

        first = next(item for item in records if item["record_type"] == "case")
        self.assertEqual(first["status"], "error")
        self.assertEqual(first["cascade"]["supplied_ids"], [expected_id])
        self.assertEqual(
            first["cascade"]["retrieved_ranked"][0]["id"], expected_id
        )
        self.assertEqual(
            first["cascade"]["backend_calls"][0]["purpose"], "generation"
        )
        self.assertEqual(
            observations.cases[0]["cascade"]["supplied_ids"], (expected_id,)
        )

    def test_fixed_large_rag_timeout_never_invokes_small_fallback(self) -> None:
        backend = FakeBackend(timeout_generation_calls=(1,))
        retriever = FakeRetriever()
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)

            summary = run_evaluation(
                self.suite,
                self.config,
                output,
                strategies=(ALWAYS_LARGE_WITH_RAG,),
                backend=backend,
                retriever=retriever,
                run_id="fixed-large-timeout-run",
                utc_now=lambda: FIXED_NOW,
            )
            records = _records(output)

        cases = tuple(
            item for item in records if item["record_type"] == "case"
        )
        first = cases[0]
        generator_calls = tuple(
            call for call in backend.calls if call["purpose"] == "generation"
        )
        self.assertEqual(summary.cascade_errors, 2)  # Timeout + absent collaborator.
        self.assertEqual(len(generator_calls), 30)
        self.assertEqual(first["status"], "error")
        self.assertEqual(first["error_stage"], "generation")
        self.assertEqual(first["error_type"], "ConversationError")
        self.assertIsNone(first["cascade"]["actual_model"])
        self.assertIsNone(first["cascade"]["fallback_from_model"])
        self.assertEqual(
            [call["model"] for call in first["cascade"]["backend_calls"]],
            [self.config.ollama.large_model],
        )
        self.assertEqual(
            first["cascade"]["backend_calls"][0]["error_type"],
            "OllamaTimeoutError",
        )
        self.assertFalse(
            any(
                call["model"] == self.config.ollama.small_model
                for call in first["cascade"]["backend_calls"]
            )
        )

    def test_adaptive_large_timeout_retains_small_fallback(self) -> None:
        backend = FakeBackend(
            route_memory=True,
            route_size="large",
            timeout_generation_calls=(1,),
        )
        retriever = FakeRetriever()
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)

            summary = run_evaluation(
                self.suite,
                self.config,
                output,
                strategies=(ADAPTIVE,),
                backend=backend,
                retriever=retriever,
                run_id="adaptive-timeout-run",
                utc_now=lambda: FIXED_NOW,
            )
            records = _records(output)

        first = next(
            item for item in records if item["record_type"] == "case"
        )
        calls = first["cascade"]["backend_calls"]
        self.assertEqual(summary.cascade_errors, 1)  # Only the absent collaborator.
        self.assertEqual(first["status"], "ok")
        self.assertEqual(
            [call["purpose"] for call in calls],
            [
                "route_memory_required",
                "route_model_size",
                "generation",
                "generation",
            ],
        )
        self.assertEqual(
            [call["model"] for call in calls[2:]],
            [
                self.config.ollama.large_model,
                self.config.ollama.small_model,
            ],
        )
        self.assertEqual(calls[2]["error_type"], "OllamaTimeoutError")
        self.assertEqual(
            first["cascade"]["requested_model"],
            self.config.ollama.large_model,
        )
        self.assertEqual(
            first["cascade"]["actual_model"],
            self.config.ollama.small_model,
        )
        self.assertEqual(
            first["cascade"]["fallback_from_model"],
            self.config.ollama.large_model,
        )

    def test_interrupt_leaves_parseable_fsynced_partial_artifact(self) -> None:
        backend = FakeBackend(interrupt_generation_call=1)
        retriever = FakeRetriever()
        telemetry = RecordingTelemetry()
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)

            with self.assertRaises(KeyboardInterrupt):
                run_evaluation(
                    self.suite,
                    self.config,
                    output,
                    strategies=(ALWAYS_SMALL_NO_RAG,),
                    backend=backend,
                    retriever=retriever,
                    run_id="interrupted-run",
                    utc_now=lambda: FIXED_NOW,
                    telemetry=telemetry,
                )
            records = _records(output)

        self.assertEqual(records[0]["record_type"], "header")
        self.assertEqual(
            sum(item["record_type"] == "retrieval" for item in records),
            16,
        )
        self.assertFalse(any(item["record_type"] == "trailer" for item in records))
        self.assertEqual(telemetry.entered, 1)
        self.assertEqual(telemetry.exited, 1)
        self.assertIs(telemetry.exception_type, KeyboardInterrupt)

    def test_interrupted_record_write_rolls_back_to_last_complete_line(self) -> None:
        backend = FakeBackend()
        retriever = FakeRetriever()
        real_write = os.write
        calls = 0

        def interrupted_write(descriptor, payload):
            nonlocal calls
            calls += 1
            if calls == 2:
                return real_write(
                    descriptor,
                    payload[: max(1, len(payload) // 2)],
                )
            if calls == 3:
                raise KeyboardInterrupt()
            return real_write(descriptor, payload)

        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)

            with patch("oline_hri.evaluation_runner.os.write", interrupted_write):
                with self.assertRaises(KeyboardInterrupt):
                    run_evaluation(
                        self.suite,
                        self.config,
                        output,
                        strategies=(ALWAYS_SMALL_NO_RAG,),
                        backend=backend,
                        retriever=retriever,
                        run_id="write-interrupted-run",
                        utc_now=lambda: FIXED_NOW,
                    )
            records = _records(output)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["record_type"], "header")

    def test_output_requires_new_file_in_private_symlink_free_parent(self) -> None:
        backend = FakeBackend()
        retriever = FakeRetriever()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / "private"
            private.mkdir(mode=0o700)
            existing = private / "existing.jsonl"
            existing.write_bytes(b"sentinel")
            with self.assertRaises(EvaluationRunError):
                run_evaluation(
                    self.suite,
                    self.config,
                    existing,
                    strategies=(ALWAYS_SMALL_NO_RAG,),
                    backend=backend,
                    retriever=retriever,
                )
            self.assertEqual(existing.read_bytes(), b"sentinel")

            public = root / "public"
            public.mkdir(mode=0o755)
            with self.assertRaises(EvaluationRunError):
                run_evaluation(
                    self.suite,
                    self.config,
                    public / "run.jsonl",
                    strategies=(ALWAYS_SMALL_NO_RAG,),
                    backend=backend,
                    retriever=retriever,
                )

            link = root / "link"
            link.symlink_to(private, target_is_directory=True)
            with self.assertRaises(EvaluationRunError):
                run_evaluation(
                    self.suite,
                    self.config,
                    link / "run.jsonl",
                    strategies=(ALWAYS_SMALL_NO_RAG,),
                    backend=backend,
                    retriever=retriever,
                )

            self.assertFalse((private / "run.jsonl").exists())

    def test_cli_selects_multiple_strategies_without_printing_case_data(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        expected = EvaluationRunSummary(
            run_id="cli-run",
            output_path=Path("/private/run.jsonl"),
            retrieval_records=16,
            retrieval_errors=0,
            cascade_records=60,
            cascade_errors=0,
        )
        with (
            patch(
                "oline_hri.evaluation_runner.load_evaluation_suite",
                return_value=self.suite,
            ),
            patch(
                "oline_hri.evaluation_runner.load_config",
                return_value=self.config,
            ),
            patch(
                "oline_hri.evaluation_runner.run_evaluation",
                return_value=expected,
            ) as execute,
        ):
            status = main(
                (
                    "run",
                    "--output",
                    "/private/run.jsonl",
                    "--strategy",
                    ALWAYS_SMALL_NO_RAG,
                    "--strategy",
                    ADAPTIVE,
                    "--repetitions",
                    "2",
                ),
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(status, 0)
        self.assertEqual(
            execute.call_args.kwargs["strategies"],
            (ALWAYS_SMALL_NO_RAG, ADAPTIVE),
        )
        self.assertEqual(execute.call_args.kwargs["repetitions"], 2)
        self.assertIs(execute.call_args.kwargs["progress"], stderr)
        self.assertIn("cli-run", stdout.getvalue())
        self.assertNotIn("Hello there.", stdout.getvalue() + stderr.getvalue())
        self.assertNotIn(
            "synthetic answer marker", stdout.getvalue() + stderr.getvalue()
        )


if __name__ == "__main__":
    unittest.main()
