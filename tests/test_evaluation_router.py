from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest

from oline_hri.config import load_config
from oline_hri.evaluation import load_evaluation_suite
from oline_hri.evaluation_router import (
    ROUTER_OBSERVATION_SCHEMA_VERSION, _RouterBackend, run_router_evaluation,
    score_router_observations,
)
from oline_hri.evaluation_runner import EvaluationRunError
from oline_hri.ollama import ChatMessage, ChatResult
from oline_hri.routing import (
    MEMORY_REQUIRED_DEMONSTRATION_MESSAGES, MEMORY_REQUIRED_SCHEMA,
    MEMORY_REQUIRED_SYSTEM_PROMPT, MODEL_SIZE_SCHEMA, MODEL_SIZE_SYSTEM_PROMPT,
    ROUTER_SEED, ROUTER_TEMPERATURE,
)


class Backend:
    def __init__(self, failure_at=None, invalid_at=None, interrupt_at=None,
                 memory=False, model="small"):
        self.calls = []
        self.failure_at = failure_at
        self.invalid_at = invalid_at
        self.interrupt_at = interrupt_at
        self.memory = memory
        self.model = model

    def chat(self, model, messages, **kwargs):
        self.calls.append((model, messages, kwargs))
        index = len(self.calls)
        if index == self.failure_at:
            raise RuntimeError("private backend failure details")
        if index == self.interrupt_at:
            raise KeyboardInterrupt()
        if kwargs.get("response_format") == MEMORY_REQUIRED_SCHEMA:
            response = {"memory_required": self.memory}
        elif kwargs.get("response_format") == MODEL_SIZE_SCHEMA:
            response = {"model_size": self.model}
        else:
            raise AssertionError("unexpected routing schema")
        content = "malformed" if index == self.invalid_at else json.dumps(response)
        return ChatResult(
            model, content, "stop", 50_000_000, 10_000_000, 9, 7, 30_000_000
        )


class RouterEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.suite = load_evaluation_suite()
        self.config = load_config()
        self.backend = Backend()

    def run_eval(self):
        ticks = iter(range(0, 100_000_000, 1_000_000))
        return run_router_evaluation(
            self.suite, self.config, output_dir=self.output, backend=self.backend,
            clock_ns=lambda: next(ticks),
            now=lambda: datetime(2026, 9, 7, tzinfo=timezone.utc), progress=io.StringIO(),
        )

    def records(self):
        return [json.loads(line) for line in
                (self.output / "observations.jsonl").read_text().splitlines()]

    def test_all_slots_only_production_routing_no_gold_or_history(self):
        summary = self.run_eval()
        self.assertEqual(len(self.backend.calls), 60)
        for index, case in enumerate(self.suite.cases):
            calls = self.backend.calls[index * 2:index * 2 + 2]
            self.assertEqual(len(calls), 2)
            for (model, messages, kwargs), prompt, schema in zip(
                calls,
                (MEMORY_REQUIRED_SYSTEM_PROMPT, MODEL_SIZE_SYSTEM_PROMPT),
                (MEMORY_REQUIRED_SCHEMA, MODEL_SIZE_SCHEMA),
            ):
                self.assertEqual(model, "qwen3:0.6b")
                self.assertEqual(messages[0].content, prompt)
                if schema == MEMORY_REQUIRED_SCHEMA:
                    self.assertEqual(
                        messages[1:-1],
                        MEMORY_REQUIRED_DEMONSTRATION_MESSAGES,
                    )
                else:
                    self.assertEqual(len(messages), 2)
                envelope = json.loads(messages[-1].content.split("\n", 1)[1])
                self.assertEqual(
                    envelope, {"prior_turns": [], "current_user_text": case.prompt}
                )
                self.assertEqual(
                    kwargs,
                    {
                        "response_format": schema,
                        "temperature": ROUTER_TEMPERATURE,
                        "seed": ROUTER_SEED,
                    },
                )
            self.assertEqual(calls[0][1][-1], calls[1][1][-1])
        records = self.records()
        serialized = json.dumps(records)
        for prohibited in ("expected_route", "answer_rubric", "retrieval_gold",
                           "reference_answer", "required_claims"):
            self.assertNotIn(prohibited, serialized)
        self.assertEqual(records[0]["schema_version"], ROUTER_OBSERVATION_SCHEMA_VERSION)
        self.assertEqual(records[0]["classifier_order"], ["memory_required", "model_size"])
        self.assertNotIn("router_system_prompt_sha256", records[0])
        memory_prefix = (
            ChatMessage("system", MEMORY_REQUIRED_SYSTEM_PROMPT),
            *MEMORY_REQUIRED_DEMONSTRATION_MESSAGES,
        )
        expected_prefix_hash = sha256(
            json.dumps(
                [message.to_dict() for message in memory_prefix],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        self.assertEqual(
            records[0]["memory_required_message_prefix_sha256"],
            expected_prefix_hash,
        )
        self.assertEqual(records[1]["classifier_calls_attempted"], 2)
        self.assertIsNotNone(records[1]["memory_required_generation"])
        self.assertIsNotNone(records[1]["model_size_generation"])
        self.assertNotIn("generation", records[1])
        self.assertEqual(summary["memory_accuracy"], 14 / 30)
        self.assertEqual(summary["model_accuracy"], 19 / 30)
        self.assertEqual(summary["joint_accuracy"], 7 / 30)
        self.assertEqual(summary["incorrect_non_escalations"], 11)
        self.assertEqual(summary["classifier_calls_attempted"], 60)
        self.assertEqual(summary["memory_required_calls_attempted"], 30)
        self.assertEqual(summary["model_size_calls_attempted"], 30)
        self.assertEqual(summary["large_inference_calls"], 0)
        self.assertEqual(summary["answer_generation_calls"], 0)
        self.assertEqual(summary["wall_latency_ms_all_attempts"]["p95"], 1)
        self.assertAlmostEqual(
            summary["ollama_total_duration_ms_reported"]["total"], 3000
        )
        self.assertAlmostEqual(
            summary["memory_required_ollama_total_duration_ms_reported"]["total"],
            1500,
        )
        self.assertAlmostEqual(
            summary["model_size_ollama_total_duration_ms_reported"]["total"], 1500
        )
        self.assertEqual(summary["prompt_tokens_reported"]["count"], 30)
        self.assertEqual(summary["prompt_tokens_reported"]["total"], 540)
        self.assertEqual(summary["output_tokens_reported"]["total"], 420)
        self.assertEqual(summary["memory_required_prompt_tokens_reported"]["total"], 270)
        self.assertEqual(summary["model_size_prompt_tokens_reported"]["total"], 270)
        for name in ("observations.jsonl", "summary.json"):
            self.assertEqual(stat.S_IMODE((self.output / name).stat().st_mode), 0o600)

    def test_failure_and_invalid_route_kept_in_denominators_and_metadata(self):
        self.backend = Backend(failure_at=1, invalid_at=3)
        summary = self.run_eval()
        records = self.records()
        self.assertEqual(summary["accuracy_denominator"], 30)
        self.assertEqual(summary["failed_slots"], 2)
        self.assertEqual(summary["memory_accuracy"], 12 / 30)
        self.assertEqual(summary["joint_accuracy"], 5 / 30)
        self.assertEqual(summary["classifier_calls_attempted"], 59)
        self.assertEqual(summary["wall_latency_ms_all_attempts"]["count"], 30)
        self.assertEqual(summary["prompt_tokens_reported"]["count"], 29)
        self.assertEqual(summary["prompt_tokens_reported"]["total"], 522)
        self.assertEqual(records[1]["backend_error_type"], "RuntimeError")
        self.assertEqual(records[1]["backend_error_stage"], "memory_required")
        self.assertEqual(records[1]["error_type"], "RoutingError")
        self.assertEqual(records[1]["classifier_calls_attempted"], 1)
        self.assertIsNone(records[1]["memory_required_generation"])
        self.assertIsNone(records[1]["model_size_generation"])
        self.assertEqual(records[2]["classifier_calls_attempted"], 2)
        self.assertIsNotNone(records[2]["memory_required_generation"])
        self.assertEqual(records[2]["model_size_generation"]["content"], "malformed")
        self.assertNotIn("private backend", json.dumps(records))

    def test_large_decisions_score_escalation_but_never_call_large(self):
        self.backend = Backend(memory=True, model="large")
        summary = self.run_eval()
        self.assertEqual(summary["selected_large_routes"], 30)
        self.assertEqual(summary["incorrect_escalations"], 19)
        self.assertEqual(summary["joint_accuracy"], 4 / 30)
        self.assertEqual(summary["incorrect_non_escalations"], 0)
        self.assertTrue(all(call[0] == "qwen3:0.6b" for call in self.backend.calls))

    def test_interrupt_preserves_current_slot_and_partial_denominators(self):
        self.backend = Backend(interrupt_at=3)
        with self.assertRaises(KeyboardInterrupt):
            self.run_eval()
        records = self.records()
        self.assertEqual(len(records), 3)
        self.assertEqual(records[-1]["error_type"], "KeyboardInterrupt")
        self.assertEqual(records[-1]["backend_error_type"], "KeyboardInterrupt")
        self.assertEqual(records[-1]["backend_error_stage"], "memory_required")
        summary = score_router_observations(self.suite, records)
        self.assertEqual(summary["observed_slots"], 2)
        self.assertEqual(summary["failed_slots"], 1)
        self.assertEqual(summary["missing_slots"], 28)
        self.assertEqual(summary["classifier_calls_attempted"], 3)
        self.assertEqual(summary["accuracy_denominator"], 30)
        self.assertFalse((self.output / "summary.json").exists())

    def test_no_overwrite_or_model_calls_on_existing_artifact(self):
        self.run_eval()
        self.backend.calls.clear()
        with self.assertRaises(EvaluationRunError):
            self.run_eval()
        self.assertEqual(self.backend.calls, [])

    def test_private_directory_and_symlink_required(self):
        self.output.chmod(0o755)
        with self.assertRaises(EvaluationRunError):
            self.run_eval()
        self.output.chmod(0o700)
        (self.output / "summary.json").symlink_to(self.output / "target")
        with self.assertRaises(EvaluationRunError):
            self.run_eval()
        self.assertEqual(self.backend.calls, [])

    def test_scorer_rejects_changed_suite_and_duplicate_slots(self):
        self.run_eval()
        records = self.records()
        changed = replace(self.suite, title=self.suite.title + " edited")
        with self.assertRaises(EvaluationRunError):
            score_router_observations(changed, records)
        with self.assertRaises(EvaluationRunError):
            score_router_observations(self.suite, records + [records[1]])
        records[1]["model_size_generation"] = None
        with self.assertRaisesRegex(EvaluationRunError, "both classifier generations"):
            score_router_observations(self.suite, records)

    def test_guard_blocks_large_and_answer_generation(self):
        messages = (
            ChatMessage("system", MEMORY_REQUIRED_SYSTEM_PROMPT),
            *MEMORY_REQUIRED_DEMONSTRATION_MESSAGES,
            ChatMessage("user", "x"),
        )
        for model, schema in (
            ("qwen3:4b", MEMORY_REQUIRED_SCHEMA),
            ("qwen3:0.6b", {"type": "object"}),
        ):
            guard = _RouterBackend(self.backend)
            with self.assertRaises(EvaluationRunError):
                guard.chat(model, messages, response_format=schema,
                           temperature=ROUTER_TEMPERATURE, seed=ROUTER_SEED)
        guard = _RouterBackend(self.backend)
        model_messages = (
            ChatMessage("system", MODEL_SIZE_SYSTEM_PROMPT),
            ChatMessage("user", "x"),
        )
        with self.assertRaises(EvaluationRunError):
            guard.chat(
                "qwen3:0.6b", model_messages, response_format=MODEL_SIZE_SCHEMA,
                temperature=ROUTER_TEMPERATURE, seed=ROUTER_SEED,
            )
        tampered_messages = list(messages)
        tampered_messages[1] = ChatMessage("user", "altered demonstration")
        guard = _RouterBackend(self.backend)
        with self.assertRaises(EvaluationRunError):
            guard.chat(
                "qwen3:0.6b", tampered_messages,
                response_format=MEMORY_REQUIRED_SCHEMA,
                temperature=ROUTER_TEMPERATURE, seed=ROUTER_SEED,
            )
        self.assertEqual(self.backend.calls, [])

    def test_guard_requires_the_same_runtime_input_for_both_axes(self):
        guard = _RouterBackend(self.backend)
        memory_messages = (
            ChatMessage("system", MEMORY_REQUIRED_SYSTEM_PROMPT),
            *MEMORY_REQUIRED_DEMONSTRATION_MESSAGES,
            ChatMessage("user", "original envelope"),
        )
        guard.chat(
            "qwen3:0.6b", memory_messages,
            response_format=MEMORY_REQUIRED_SCHEMA,
            temperature=ROUTER_TEMPERATURE, seed=ROUTER_SEED,
        )
        model_messages = (
            ChatMessage("system", MODEL_SIZE_SYSTEM_PROMPT),
            ChatMessage("user", "altered envelope"),
        )
        with self.assertRaises(EvaluationRunError):
            guard.chat(
                "qwen3:0.6b", model_messages,
                response_format=MODEL_SIZE_SCHEMA,
                temperature=ROUTER_TEMPERATURE, seed=ROUTER_SEED,
            )
        self.assertEqual(len(self.backend.calls), 1)

    def test_backwards_clock_fails_without_fabricating_zero_latency(self):
        ticks = iter((2, 1))
        with self.assertRaisesRegex(EvaluationRunError, "clock moved backwards"):
            run_router_evaluation(
                self.suite, self.config, output_dir=self.output, backend=self.backend,
                clock_ns=lambda: next(ticks),
            )
        self.assertEqual(len(self.records()), 1)
        self.assertFalse((self.output / "summary.json").exists())


if __name__ == "__main__":
    unittest.main()
