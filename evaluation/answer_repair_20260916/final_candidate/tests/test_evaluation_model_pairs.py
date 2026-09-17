"""Offline unit tests for the sequential model-pair evaluator."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import unittest

from oline_hri.evaluation import load_evaluation_suite
from oline_hri.evaluation_model_pairs import (
    GENERATION_CASE_IDS,
    ModelPairEvaluationError,
    SafetyGateError,
    _CandidateRouter,
    _DurableJsonlWriter,
    _RecordingBackend,
    _StreamingSafetyMonitor,
    _memory_snapshot,
    _model_metadata,
    _model_name,
    _read_text,
    _require_start_safe,
    summarize_records,
)
from oline_hri.ollama import ChatResult


def _result(model: str, content: str) -> ChatResult:
    return ChatResult(
        model=model,
        content=content,
        done_reason="stop",
        total_duration_ns=10,
        load_duration_ns=1,
        prompt_eval_count=4,
        eval_count=2,
        eval_duration_ns=2,
        prompt_eval_duration_ns=3,
    )


class _RoutingBackend:
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
        if "memory_required" in properties:
            content = json.dumps(
                {"form": "question", "memory_required": False}
            )
        else:
            content = json.dumps({"model_size": "small"})
        return _result(model, content)


class _TelemetryWriter:
    def __init__(self) -> None:
        self.records = []

    def write(self, record) -> None:
        self.records.append(record)


def _safe_start_snapshot() -> dict[str, object]:
    return {
        "fan_pwm": 76,
        "memory": {
            "mem_available_kib": 3_000_000,
            "swap_used_kib": 0,
        },
        "power_mode": "NV Power Mode: 15W\n0",
        "resident_models": [],
        "temperatures_c": {"gpu": 50.0},
        "thermal_trip_events": {"gpu": 0},
    }


class ModelPairEvaluationTests(unittest.TestCase):
    def test_exact_model_name_is_required(self) -> None:
        self.assertEqual(
            _model_name("family:model-q4_K_M"),
            "family:model-q4_K_M",
        )
        for invalid in ("", "latest", " model:tag", "model:tag ", "model:"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ModelPairEvaluationError):
                    _model_name(invalid)

    def test_memory_snapshot_derives_swap_use(self) -> None:
        snapshot = _memory_snapshot(
            "MemTotal: 8000 kB\nMemAvailable: 4000 kB\n"
            "SwapTotal: 2000 kB\nSwapFree: 1750 kB\n"
        )
        self.assertEqual(snapshot["mem_available_kib"], 4000)
        self.assertEqual(snapshot["swap_used_kib"], 250)

    def test_memory_snapshot_rejects_missing_fields(self) -> None:
        with self.assertRaisesRegex(Exception, "missing required"):
            _memory_snapshot("MemTotal: 8000 kB\n")

    def test_sysfs_none_read_is_reported_as_unavailable(self) -> None:
        stream = unittest.mock.MagicMock()
        stream.__enter__.return_value.read.return_value = None
        with patch.object(Path, "open", return_value=stream):
            with self.assertRaisesRegex(Exception, "cannot read"):
                _read_text(Path("/sys/fake"), 128)

    def test_durable_writer_accepts_private_parent_and_fsyncs_jsonl(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary) / "run"
            parent.mkdir(mode=0o700)
            path = parent / "observations.jsonl"
            with _DurableJsonlWriter(path) as writer:
                writer.write({"z": 1, "a": 2})
            self.assertEqual(path.read_text(), '{"a":2,"z":1}\n')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_durable_writer_rejects_nonprivate_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary) / "run"
            parent.mkdir(mode=0o750)
            with self.assertRaisesRegex(Exception, "mode-0700"):
                with _DurableJsonlWriter(parent / "observations.jsonl"):
                    pass

    def test_candidate_router_uses_production_contract_with_other_tag(
        self,
    ) -> None:
        router = _CandidateRouter(_RoutingBackend(), model="llama3.2:test")
        result = router.route("What is SQLite FTS5?")
        self.assertEqual(result.decision.memory_required, False)
        self.assertEqual(result.decision.model_size, "small")
        self.assertEqual(
            result.memory_required_generation.model,
            "llama3.2:test",
        )

    def test_recording_backend_keeps_successful_raw_generation(self) -> None:
        backend = _RecordingBackend(_RoutingBackend())
        result = backend.chat(
            "llama3.2:test",
            [],
            response_format={"properties": {"model_size": {}}},
        )
        self.assertEqual(result.model, "llama3.2:test")
        calls = backend.calls_since(0)
        self.assertEqual(calls[0]["status"], "ok")
        self.assertEqual(calls[0]["purpose"], "model_size")
        self.assertIsNotNone(calls[0]["generation"])

    def test_streaming_monitor_persists_then_interrupts_on_pressure(
        self,
    ) -> None:
        writer = _TelemetryWriter()
        monitor = _StreamingSafetyMonitor(writer)
        record = {
            "ram": {"total_mb": 7620, "used_mb": 7000},
            "swap": {"used_mb": 10},
            "temperatures_c": {"gpu": 50.0},
        }
        with patch(
            "oline_hri.evaluation_model_pairs._thread.interrupt_main"
        ) as interrupt:
            monitor(record)
        self.assertEqual(writer.records, [record])
        self.assertEqual(monitor.violation, "telemetry RAM floor crossed")
        interrupt.assert_called_once_with()

    def test_start_gate_requires_15w_mode_zero(self) -> None:
        snapshot = _safe_start_snapshot()
        snapshot["power_mode"] = "NV Power Mode: MAXN_SUPER\n2"
        with self.assertRaisesRegex(SafetyGateError, "15W"):
            _require_start_safe(snapshot)

    def test_model_metadata_requires_completion_capability(self) -> None:
        installed = {
            "model:test": {
                "digest": "a" * 64,
                "name": "model:test",
                "size": 1_000,
            }
        }
        shown = {
            "capabilities": ["embedding"],
            "details": {
                "family": "test",
                "format": "gguf",
                "parameter_size": "1B",
                "quantization_level": "Q4_K_M",
            },
            "model_info": {"general.parameter_count": 1_000_000_000},
        }
        with patch(
            "oline_hri.evaluation_model_pairs._http_json",
            return_value=shown,
        ):
            with self.assertRaisesRegex(SafetyGateError, "completion"):
                _model_metadata("model:test", installed)

    def test_screen_spans_all_four_routes(self) -> None:
        suite = load_evaluation_suite()
        cases = {case.id: case for case in suite.cases}
        routes = {
            (
                cases[case_id].expected_route.memory_required,
                cases[case_id].expected_route.model_size,
            )
            for case_id in GENERATION_CASE_IDS
        }
        self.assertEqual(
            routes,
            {
                (False, "small"),
                (False, "large"),
                (True, "small"),
                (True, "large"),
            },
        )

    def test_summary_keeps_routing_and_generation_separate(self) -> None:
        records = [
            {
                "record_type": "model_pair_route_case",
                "status": "ok",
                "joint_correct": True,
                "memory_correct": True,
                "model_correct": False,
                "wall_ns": 2_000_000_000,
            },
            {
                "record_type": "model_pair_answer_case",
                "status": "ok",
                "expected_model_size": "large",
                "expected_required_citation_ids": [],
                "memory_diagnostics": {"model_used_ids": []},
                "generation": {"generation_tokens_per_second": 4.0},
                "wall_ns": 3_000_000_000,
            },
        ]
        summary = summarize_records(
            records,
            router_model="router:test",
            generator_model="generator:test",
        )
        self.assertEqual(summary["router"]["joint_correct"], 1)
        self.assertEqual(summary["router"]["model_size_correct"], 0)
        self.assertEqual(summary["answer_screen"]["structured_success"], 1)
        self.assertEqual(summary["answer_screen"]["citation_exact"], 1)


if __name__ == "__main__":
    unittest.main()
