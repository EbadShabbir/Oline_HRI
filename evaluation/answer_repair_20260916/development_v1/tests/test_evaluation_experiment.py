from dataclasses import replace
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from oline_hri.config import load_config
from oline_hri.evaluation import load_evaluation_suite, materialize_memory_store
from oline_hri.evaluation_experiment import (
    ARTIFACT_NAMES,
    FIXED_EXPECTED,
    OBSERVATION_SCHEMA_VERSION,
    PRODUCTION_ADAPTIVE,
    SUMMARY_SCHEMA_VERSION,
    TemperatureArm,
    TemperatureExperimentError,
    load_experiment_plan,
    main,
    run_temperature_experiment,
    validate_experiment_plan,
)
from oline_hri.evaluation_runner import EvaluationRunError
from oline_hri.ollama import ChatResult, OllamaTimeoutError


FIXED_NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def _chat_result(
    model: str,
    content: str,
    *,
    citation_annotations_removed: int = 0,
) -> ChatResult:
    return ChatResult(
        model=model,
        content=content,
        done_reason="stop",
        total_duration_ns=100,
        load_duration_ns=10,
        prompt_eval_count=20,
        eval_count=8,
        eval_duration_ns=50_000_000,
        prompt_eval_duration_ns=20_000_000,
        citation_annotations_removed=citation_annotations_removed,
    )


class FakeBackend:
    """Record all calls and return grounded, schema-valid local responses."""

    def __init__(
        self,
        *,
        fail_generation_calls=(),
        invalid_generation_calls=(),
        citation_annotations_removed=(),
    ) -> None:
        self.calls = []
        self.generation_calls = 0
        self.fail_generation_calls = set(fail_generation_calls)
        self.invalid_generation_calls = set(invalid_generation_calls)
        self.citation_annotations_removed = tuple(
            citation_annotations_removed
        )

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
            request = " ".join(message.content for message in messages)
            return _chat_result(
                model,
                json.dumps(
                    {
                        "form": "request",
                        "memory_required": (
                            "timeline comparing" in request
                            or "preferred project-meeting" in request
                        )
                    },
                    separators=(",", ":"),
                ),
            )
        if purpose == "route_model_size":
            return _chat_result(model, '{"model_size":"large"}')

        self.generation_calls += 1
        if self.generation_calls in self.fail_generation_calls:
            raise RuntimeError("private fake-backend failure")
        annotations_removed = (
            self.citation_annotations_removed[self.generation_calls - 1]
            if self.generation_calls <= len(self.citation_annotations_removed)
            else 0
        )
        allowed = tuple(properties["memory_used"]["items"].get("enum", ()))
        if self.generation_calls in self.invalid_generation_calls:
            speech = "unsupported synthetic answer"
        elif allowed:
            # This mirrors every supplied canonical fact, which exercises the
            # real memory coverage and citation validators without a model.
            speech = "synthetic answer marker "
            for message in reversed(messages):
                marker = "PERSONAL_MEMORY_DATA="
                request_marker = "\nCURRENT_USER_REQUEST="
                if marker not in message.content:
                    continue
                encoded = message.content.split(marker, 1)[1]
                encoded = encoded.split(request_marker, 1)[0]
                records = json.loads(encoded)["records"]
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
                speech += " ".join(grounded_parts)
                break
        else:
            speech = (
                "Isolate the damaged database and preserve an untouched copy. "
                "Restore a verified backup or salvage into a clean database, "
                "then validate integrity before resuming service."
            )
        return _chat_result(
            model,
            json.dumps(
                {
                    "speech": speech,
                    "gesture_id": "NO_ACTION",
                    "memory_used": list(allowed),
                },
                separators=(",", ":"),
            ),
            citation_annotations_removed=annotations_removed,
        )


class TimeoutBackend(FakeBackend):
    def chat(self, *args, **kwargs):
        self.calls.append(
            {
                "purpose": "generation",
                "model": args[0],
                "messages": tuple(args[1]),
                "temperature": kwargs.get("temperature"),
                "seed": kwargs.get("seed"),
            }
        )
        raise OllamaTimeoutError("synthetic timeout")


def _records(path: Path):
    return tuple(
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    )


class TemperatureExperimentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.suite = load_evaluation_suite()
        self.config = load_config()
        self.plan = load_experiment_plan()

    def _private_output(self, root: str) -> Path:
        output = Path(root) / "private"
        output.mkdir(mode=0o700)
        return output

    def test_default_plan_is_the_declared_one_repetition_isolated_pilot(self):
        selected = validate_experiment_plan(self.plan, self.suite)

        self.assertEqual(
            self.plan.case_ids,
            ("route_large_no_memory_05", "memory_large_temporal"),
        )
        self.assertEqual(tuple(case.id for case in selected), self.plan.case_ids)
        self.assertEqual(self.plan.repetitions, 1)
        self.assertEqual(self.plan.base_seed, 42)
        self.assertEqual(self.plan.context_length, 2176)
        self.assertEqual(self.plan.max_output_tokens, 320)
        self.assertEqual(self.plan.routing_mode, FIXED_EXPECTED)
        self.assertEqual(
            tuple(arm.temperature for arm in self.plan.arms), (0.0, 0.2)
        )

    def test_run_is_paired_balanced_fixed_evidence_and_one_shared_backend(self):
        backend = FakeBackend()
        progress = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)
            with patch(
                "oline_hri.evaluation_experiment.materialize_memory_store",
                wraps=materialize_memory_store,
            ) as materialize:
                result = run_temperature_experiment(
                    self.suite,
                    self.config,
                    self.plan,
                    output,
                    backend=backend,
                    run_id="fixed-test-run",
                    utc_now=lambda: FIXED_NOW,
                    progress=progress,
                )
            observations = _records(result.observations_path)
            summary = _records(result.summary_path)[0]
            reviews = _records(result.paired_review_path)
            key = _records(result.pair_key_path)[0]
            artifact_modes = {
                name: stat.S_IMODE(os.stat(output / name).st_mode)
                for name in ARTIFACT_NAMES
            }

        self.assertEqual(materialize.call_count, 1)
        attempts = tuple(
            record
            for record in observations
            if record["record_type"] == "temperature_experiment_attempt"
        )
        self.assertEqual(observations[0]["schema_version"], OBSERVATION_SCHEMA_VERSION)
        self.assertTrue(
            all(
                record["schema_version"] == OBSERVATION_SCHEMA_VERSION
                for record in attempts
            )
        )
        self.assertEqual(summary["schema_version"], SUMMARY_SCHEMA_VERSION)
        self.assertEqual(result.attempts, 4)
        self.assertEqual(result.errors, 0)
        self.assertEqual(
            [record["arm"] for record in attempts],
            ["temp_0", "temp_0_2", "temp_0_2", "temp_0"],
        )
        self.assertEqual([record["seed"] for record in attempts], [42] * 4)
        self.assertEqual(
            [record["temperature"] for record in attempts],
            [0.0, 0.2, 0.2, 0.0],
        )
        self.assertEqual(len(backend.calls), 4)
        self.assertEqual({call["purpose"] for call in backend.calls}, {"generation"})
        self.assertEqual(
            [call["temperature"] for call in backend.calls],
            [0.0, 0.2, 0.2, 0.0],
        )
        self.assertEqual([call["seed"] for call in backend.calls], [42] * 4)
        # A fresh Conversation means no generated assistant turn is reused.
        self.assertTrue(
            all(
                all(message.role != "assistant" for message in call["messages"])
                for call in backend.calls
            )
        )

        memory_attempts = [
            record
            for record in attempts
            if record["case_id"] == "memory_large_temporal"
        ]
        required = list(
            next(
                case
                for case in self.suite.cases
                if case.id == "memory_large_temporal"
            ).retrieval_gold.required_ids
        )
        for record in memory_attempts:
            self.assertEqual(record["memory_diagnostics"]["retrieved_ids"], required)
            self.assertEqual(record["memory_diagnostics"]["supplied_ids"], required)
            self.assertEqual(record["memory_diagnostics"]["model_used_ids"], required)
        self.assertEqual(summary["answer_quality"]["status"], "pending_blinded_paired_review")
        self.assertEqual(summary["arms"]["temp_0"]["fixed_evidence_exact_rate"], 1.0)
        self.assertEqual(summary["arms"]["temp_0_2"]["fixed_evidence_exact_rate"], 1.0)
        self.assertEqual(summary["arms"]["temp_0"]["required_citation_exact_rate"], 1.0)
        self.assertEqual(summary["arms"]["temp_0_2"]["required_citation_exact_rate"], 1.0)
        for record in attempts:
            self.assertEqual(record["citation_annotations_removed"], 0)
            self.assertEqual(
                record["generation"]["citation_annotations_removed"], 0
            )
            generation_call = next(
                call
                for call in record["backend_calls"]
                if call["purpose"] == "generation"
            )
            self.assertEqual(
                generation_call["generation"]["citation_annotations_removed"],
                0,
            )
        for arm in ("temp_0", "temp_0_2"):
            self.assertEqual(
                summary["arms"][arm]["citation_annotations_removed"], 0
            )
            self.assertEqual(
                summary["arms"][arm][
                    "attempts_with_citation_annotations_removed"
                ],
                0,
            )
            self.assertEqual(
                summary["arms"][arm]["citation_annotation_removal_rate"],
                0.0,
            )
        self.assertEqual(len(reviews), 2)
        self.assertTrue(
            all(
                candidate["required_citation_exact"]
                for review in reviews
                for candidate in review["candidates"]
            )
        )
        self.assertEqual(len(key["mappings"]), 2)
        self.assertEqual(
            {mapping["candidate_1"] for mapping in key["mappings"]},
            {"temp_0", "temp_0_2"},
        )
        self.assertEqual(set(artifact_modes.values()), {0o600})
        self.assertIn("4/4", progress.getvalue())

    def test_progress_is_arm_opaque_when_outcomes_are_asymmetric(self):
        backend = FakeBackend(fail_generation_calls={1})
        progress = io.StringIO()
        one_case = replace(
            self.plan,
            case_ids=("route_large_no_memory_05",),
        )
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)
            result = run_temperature_experiment(
                self.suite,
                self.config,
                one_case,
                output,
                backend=backend,
                run_id="arm-opaque-progress-test",
                utc_now=lambda: FIXED_NOW,
                progress=progress,
            )
            attempts = tuple(
                record
                for record in _records(result.observations_path)
                if record["record_type"] == "temperature_experiment_attempt"
            )

        self.assertEqual(result.errors, 1)
        self.assertEqual(
            [record["status"] for record in attempts],
            ["error", "ok"],
        )
        self.assertEqual(
            progress.getvalue(),
            "temperature-ab 1/2 attempts completed\n"
            "temperature-ab 2/2 attempts completed\n",
        )
        for private_detail in (
            "route_large_no_memory_05",
            "temp_0",
            "temp_0_2",
            "0.0",
            "0.2",
            "status",
            "error",
            "ok",
            "ConversationError",
            "private fake-backend failure",
            "Isolate the damaged database",
        ):
            self.assertNotIn(private_detail, progress.getvalue())

    def test_citation_annotation_removals_are_persisted_and_summarized(self):
        backend = FakeBackend(citation_annotations_removed=(2, 0, 1, 0))
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)
            result = run_temperature_experiment(
                self.suite,
                self.config,
                self.plan,
                output,
                backend=backend,
                run_id="annotation-telemetry-test",
                utc_now=lambda: FIXED_NOW,
            )
            attempts = tuple(
                record
                for record in _records(result.observations_path)
                if record["record_type"] == "temperature_experiment_attempt"
            )
            summary = _records(result.summary_path)[0]

        self.assertEqual(
            [record["citation_annotations_removed"] for record in attempts],
            [2, 0, 1, 0],
        )
        for expected, record in zip((2, 0, 1, 0), attempts):
            self.assertEqual(
                record["generation"]["citation_annotations_removed"],
                expected,
            )
            generation_call = next(
                call
                for call in record["backend_calls"]
                if call["purpose"] == "generation"
            )
            self.assertEqual(
                generation_call["generation"]["citation_annotations_removed"],
                expected,
            )
        self.assertEqual(
            summary["arms"]["temp_0"]["citation_annotations_removed"], 2
        )
        self.assertEqual(
            summary["arms"]["temp_0_2"]["citation_annotations_removed"], 1
        )
        for arm in ("temp_0", "temp_0_2"):
            self.assertEqual(
                summary["arms"][arm][
                    "attempts_with_citation_annotations_removed"
                ],
                1,
            )
            self.assertEqual(
                summary["arms"][arm]["citation_annotation_removal_rate"],
                0.5,
            )

    def test_annotation_telemetry_survives_later_response_validation_failure(self):
        backend = FakeBackend(
            invalid_generation_calls={1},
            citation_annotations_removed=(2, 0),
        )
        one_case = replace(
            self.plan,
            case_ids=("memory_large_temporal",),
        )
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)
            result = run_temperature_experiment(
                self.suite,
                self.config,
                one_case,
                output,
                backend=backend,
                run_id="failed-annotation-telemetry-test",
                utc_now=lambda: FIXED_NOW,
            )
            attempts = tuple(
                record
                for record in _records(result.observations_path)
                if record["record_type"] == "temperature_experiment_attempt"
            )
            summary = _records(result.summary_path)[0]

        failed = attempts[0]
        self.assertEqual(failed["status"], "error")
        self.assertIsNone(failed["generation"])
        self.assertEqual(failed["citation_annotations_removed"], 2)
        self.assertEqual(
            failed["backend_calls"][0]["generation"][
                "citation_annotations_removed"
            ],
            2,
        )
        self.assertEqual(
            summary["arms"]["temp_0"]["citation_annotations_removed"], 2
        )
        self.assertEqual(
            summary["arms"]["temp_0"][
                "attempts_with_citation_annotations_removed"
            ],
            1,
        )
        self.assertEqual(
            summary["arms"]["temp_0"]["citation_annotation_removal_rate"],
            1.0,
        )

    def test_invalid_chat_result_annotation_telemetry_fails_closed(self):
        one_case = replace(
            self.plan,
            case_ids=("route_large_no_memory_05",),
        )
        for invalid in (True, -1):
            with (
                self.subTest(invalid=invalid),
                tempfile.TemporaryDirectory() as directory,
            ):
                output = self._private_output(directory)
                result = run_temperature_experiment(
                    self.suite,
                    self.config,
                    one_case,
                    output,
                    backend=FakeBackend(
                        citation_annotations_removed=(invalid, 0)
                    ),
                    run_id=f"invalid-annotation-telemetry-{invalid!s}",
                    utc_now=lambda: FIXED_NOW,
                )
                attempts = tuple(
                    record
                    for record in _records(result.observations_path)
                    if record["record_type"] == "temperature_experiment_attempt"
                )

            self.assertEqual(result.errors, 1)
            self.assertEqual(attempts[0]["status"], "error")
            self.assertEqual(attempts[0]["error_type"], "ConversationError")
            self.assertIsNone(attempts[0]["generation"])
            self.assertEqual(attempts[0]["citation_annotations_removed"], 0)
            self.assertEqual(attempts[0]["backend_calls"], [])
            self.assertEqual(attempts[1]["status"], "ok")

    def test_review_is_blinded_and_generation_never_receives_gold_answer(self):
        backend = FakeBackend()
        nonce = bytes(range(32))
        reference_answers = {case.answer_rubric.reference_answer for case in self.suite.cases}
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)
            result = run_temperature_experiment(
                self.suite,
                self.config,
                self.plan,
                output,
                backend=backend,
                run_id="blinding-test",
                utc_now=lambda: FIXED_NOW,
                _blinding_nonce=nonce,
            )
            review_text = result.paired_review_path.read_text(encoding="utf-8")
            key_text = result.pair_key_path.read_text(encoding="utf-8")
            observations_text = result.observations_path.read_text(encoding="utf-8")
            summary_text = result.summary_path.read_text(encoding="utf-8")

        self.assertNotIn('"temp_0"', review_text)
        self.assertNotIn('"temp_0_2"', review_text)
        self.assertNotIn("blinding_nonce", review_text)
        self.assertNotIn(nonce.hex(), review_text)
        self.assertNotIn(nonce.hex(), observations_text)
        self.assertNotIn(nonce.hex(), summary_text)
        self.assertIn('"temp_0"', key_text)
        self.assertIn('"temp_0_2"', key_text)
        self.assertIn(nonce.hex(), key_text)
        for call in backend.calls:
            request = "\n".join(message.content for message in call["messages"])
            self.assertTrue(all(answer not in request for answer in reference_answers))

    def test_secret_nonce_can_flip_same_public_header_and_stays_balanced(self):
        keys = []
        headers = []
        nonces = (bytes(32), bytes([1]) * 32)
        with tempfile.TemporaryDirectory() as directory:
            for index, nonce in enumerate(nonces):
                output = Path(directory) / f"private-{index}"
                output.mkdir(mode=0o700)
                result = run_temperature_experiment(
                    self.suite,
                    self.config,
                    self.plan,
                    output,
                    backend=FakeBackend(),
                    run_id="same-public-header",
                    utc_now=lambda: FIXED_NOW,
                    _blinding_nonce=nonce,
                )
                headers.append(_records(result.observations_path)[0])
                keys.append(_records(result.pair_key_path)[0])

        self.assertEqual(headers[0], headers[1])
        self.assertEqual(keys[0]["blinding_nonce"], nonces[0].hex())
        self.assertEqual(keys[1]["blinding_nonce"], nonces[1].hex())
        first_positions = [
            [mapping["candidate_1"] for mapping in key["mappings"]]
            for key in keys
        ]
        self.assertEqual(set(first_positions[0]), {"temp_0", "temp_0_2"})
        self.assertEqual(set(first_positions[1]), {"temp_0", "temp_0_2"})
        self.assertEqual(
            first_positions[0],
            list(reversed(first_positions[1])),
        )

    def test_injected_blinding_nonce_is_validated_and_canonicalized(self):
        backend = FakeBackend()
        uppercase = "AB" * 32
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)
            result = run_temperature_experiment(
                self.suite,
                self.config,
                self.plan,
                output,
                backend=backend,
                run_id="canonical-nonce-test",
                utc_now=lambda: FIXED_NOW,
                _blinding_nonce=uppercase,
            )
            key = _records(result.pair_key_path)[0]

        self.assertEqual(key["blinding_nonce"], uppercase.lower())

        invalid_backend = FakeBackend()
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)
            with self.assertRaises(TemperatureExperimentError):
                run_temperature_experiment(
                    self.suite,
                    self.config,
                    self.plan,
                    output,
                    backend=invalid_backend,
                    run_id="invalid-nonce-test",
                    utc_now=lambda: FIXED_NOW,
                    _blinding_nonce=b"too-short",
                )
        self.assertEqual(invalid_backend.calls, [])

    def test_adaptive_mode_keeps_router_sampling_fixed(self):
        backend = FakeBackend()
        adaptive = replace(self.plan, routing_mode=PRODUCTION_ADAPTIVE)
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)
            result = run_temperature_experiment(
                self.suite,
                self.config,
                adaptive,
                output,
                backend=backend,
                run_id="adaptive-test",
                utc_now=lambda: FIXED_NOW,
            )

        self.assertEqual(result.errors, 0)
        route_calls = [call for call in backend.calls if call["purpose"].startswith("route_")]
        generation_calls = [call for call in backend.calls if call["purpose"] == "generation"]
        self.assertEqual(len(route_calls), 8)
        self.assertTrue(
            all(call["temperature"] == 0.0 and call["seed"] == 42 for call in route_calls)
        )
        self.assertEqual(
            [call["temperature"] for call in generation_calls],
            [0.0, 0.2, 0.2, 0.0],
        )
        self.assertEqual([call["seed"] for call in generation_calls], [42] * 4)

    def test_api_revalidates_forged_dataclass(self):
        forged = replace(
            self.plan,
            arms=(
                TemperatureArm("temp_0", 0.0),
                TemperatureArm("temp_0_2", 0.0),
            ),
        )

        with self.assertRaises(TemperatureExperimentError):
            validate_experiment_plan(forged, self.suite)

    def test_preexisting_artifact_is_not_overwritten_or_inferred(self):
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)
            existing = output / "summary.json"
            existing.write_bytes(b"preserve-me")
            os.chmod(existing, 0o600)

            with self.assertRaises(EvaluationRunError):
                run_temperature_experiment(
                    self.suite,
                    self.config,
                    self.plan,
                    output,
                    backend=backend,
                    run_id="no-overwrite-test",
                    utc_now=lambda: FIXED_NOW,
                )

            self.assertEqual(existing.read_bytes(), b"preserve-me")
            self.assertEqual(backend.calls, [])

    def test_failed_attempt_is_recorded_without_private_exception_text(self):
        backend = FakeBackend(fail_generation_calls={2})
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)
            result = run_temperature_experiment(
                self.suite,
                self.config,
                self.plan,
                output,
                backend=backend,
                run_id="failure-test",
                utc_now=lambda: FIXED_NOW,
            )
            raw = result.observations_path.read_text(encoding="utf-8")
            attempts = tuple(
                record
                for record in _records(result.observations_path)
                if record["record_type"] == "temperature_experiment_attempt"
            )

        self.assertEqual(result.errors, 1)
        self.assertEqual(attempts[1]["status"], "error")
        self.assertEqual(attempts[1]["error_type"], "ConversationError")
        self.assertNotIn("private fake-backend failure", raw)

    def test_large_timeout_is_not_retried_or_counted_as_an_arm_response(self):
        backend = TimeoutBackend()
        one_case = replace(
            self.plan,
            case_ids=("route_large_no_memory_05",),
        )
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)
            result = run_temperature_experiment(
                self.suite,
                self.config,
                one_case,
                output,
                backend=backend,
                run_id="timeout-no-fallback-test",
                utc_now=lambda: FIXED_NOW,
            )
            attempts = tuple(
                record
                for record in _records(result.observations_path)
                if record["record_type"] == "temperature_experiment_attempt"
            )
            reviews = _records(result.paired_review_path)

        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.errors, 2)
        self.assertEqual(len(backend.calls), 2)
        self.assertTrue(all(item["status"] == "error" for item in attempts))
        self.assertTrue(
            all(
                candidate["response_status"] == "failed"
                for candidate in reviews[0]["candidates"]
            )
        )

    def test_artifacts_are_canonical_json_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self._private_output(directory)
            run_temperature_experiment(
                self.suite,
                self.config,
                self.plan,
                output,
                backend=FakeBackend(),
                run_id="canonical-test",
                utc_now=lambda: FIXED_NOW,
            )
            payloads = {name: (output / name).read_text(encoding="utf-8") for name in ARTIFACT_NAMES}

        for payload in payloads.values():
            self.assertTrue(payload.endswith("\n"))
            for line in payload.splitlines():
                self.assertEqual(
                    line,
                    json.dumps(
                        json.loads(line),
                        ensure_ascii=False,
                        allow_nan=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )

    def test_validate_cli_runs_no_backend(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = main(["validate"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertIn("plan valid", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
