from contextlib import contextmanager
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import oline_hri.evaluation_benchmark as benchmark
from oline_hri.evaluation_benchmark import (
    ANSWER_REVIEW_NAME,
    ARTIFACT_NAMES,
    ENVIRONMENT_NAME,
    OBSERVATIONS_NAME,
    REPORT_NAME,
    SUMMARY_NAME,
    TELEMETRY_NAME,
    TELEMETRY_SUMMARY_NAME,
    EvaluationBenchmarkError,
    main,
    run_benchmark,
)
from oline_hri.evaluation_scoring import EvaluationScoringError
from oline_hri.evaluation_telemetry import (
    DiskStatsSnapshot,
    parse_tegrastats_line,
)


TELEMETRY_LINE = (
    b"RAM 100/7620MB SWAP 20/3810MB CPU [10%@1000,20%@1000] "
    b"GR3D_FREQ 30% cpu@40.0C gpu@41.0C VDD_IN 2000mW/1900mW\n"
)
TELEMETRY_SAMPLE = parse_tegrastats_line(
    TELEMETRY_LINE,
    monotonic_ns=2_000_000_000,
)
TELEMETRY_SAMPLE_2 = replace(
    TELEMETRY_SAMPLE,
    monotonic_ns=3_000_000_000,
    vdd_in_mw=3_000,
)


def _disk_snapshot(timestamp: int, increment: int = 0) -> DiskStatsSnapshot:
    return DiskStatsSnapshot(
        monotonic_ns=timestamp,
        device="mmcblk0",
        reads_completed=10 + increment,
        reads_merged=2 + increment,
        sectors_read=100 + increment,
        read_time_ms=7 + increment,
        writes_completed=20 + increment,
        writes_merged=3 + increment,
        sectors_written=200 + increment,
        write_time_ms=9 + increment,
        ios_in_progress=0,
        io_time_ms=11 + increment,
        weighted_io_time_ms=13 + increment,
    )


def _create_private_file(path: Path, payload: bytes = b"observation\n") -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class _FakeSampler:
    instances = []

    def __init__(self, *, interval_ms: int) -> None:
        self.interval_ms = interval_ms
        self.samples = (TELEMETRY_SAMPLE, TELEMETRY_SAMPLE_2)
        self.enter_calls = 0
        self.exit_calls = 0
        type(self).instances.append(self)

    def __enter__(self):
        self.enter_calls += 1
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.exit_calls += 1
        return False

    def summary(self):
        return {
            "record_type": "jetson_telemetry_summary",
            "sample_count": 2,
            "schema_version": 1,
            "vdd_in_energy_joules": 2.5,
        }


class BenchmarkTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeSampler.instances.clear()
        self.suite = object()
        self.config = object()
        self.observations = SimpleNamespace(
            header={
                "config_sha256": "b" * 64,
                "run_id": "benchmark_run",
                "suite_sha256": "a" * 64,
            }
        )
        self.environment_snapshot = {
            "record_type": "benchmark_environment",
            "schema_version": 1,
            "source": {"aggregate_sha256": "c" * 64},
        }
        self.objective = {
            "schema_version": 1,
            "run_id": "benchmark_run",
            "protocol": {"complete": True},
        }
        self.before_disk = _disk_snapshot(1_000_000_000)
        self.after_disk = _disk_snapshot(4_000_000_000, increment=5)
        self.before_throttle = benchmark._ThrottleSnapshot(
            monotonic_ns=1_100_000_000,
            counters=tuple((name, 0) for name in benchmark._THROTTLE_DOMAINS),
            unavailable=(),
        )
        self.after_throttle = benchmark._ThrottleSnapshot(
            monotonic_ns=3_900_000_000,
            counters=tuple(
                (name, 1 if name == "gpu" else 0)
                for name in benchmark._THROTTLE_DOMAINS
            ),
            unavailable=(),
        )

    def _private_directory(self, root: str, name: str = "results") -> Path:
        path = Path(root) / name
        path.mkdir(mode=0o700)
        path.chmod(0o700)
        return path

    def _runner(self, suite, config, output_path, **kwargs):
        self.assertIs(suite, self.suite)
        self.assertIs(config, self.config)
        _create_private_file(Path(output_path))
        with kwargs["telemetry"]:
            if kwargs["progress"] is not None:
                print("safe benchmark progress", file=kwargs["progress"])
        return SimpleNamespace(
            run_id="benchmark_run",
            output_path=Path(output_path),
            retrieval_records=16,
            retrieval_errors=1,
            cascade_records=60,
            cascade_errors=2,
        )

    @contextmanager
    def _pipeline(self, *, runner=None, report_side_effect=None):
        run_mock = Mock(side_effect=self._runner if runner is None else runner)
        report_mock = Mock(
            return_value="# Objective report\n",
            side_effect=report_side_effect,
        )
        patches = (
            patch.object(benchmark, "TegrastatsSampler", _FakeSampler),
            patch.object(benchmark, "run_evaluation", run_mock),
            patch.object(
                benchmark,
                "capture_runtime_baseline",
                side_effect=(
                    {"record_type": "runtime_baseline", "monotonic_ns": 1},
                    {"record_type": "runtime_baseline", "monotonic_ns": 4},
                ),
            ),
            patch.object(
                benchmark,
                "read_diskstats",
                side_effect=(self.before_disk, self.after_disk),
            ),
            patch.object(
                benchmark,
                "_capture_throttle_snapshot",
                side_effect=(self.before_throttle, self.after_throttle),
            ),
            patch.object(
                benchmark,
                "_capture_environment",
                return_value=self.environment_snapshot,
            ),
            patch.object(
                benchmark,
                "load_observation_jsonl",
                return_value=self.observations,
            ),
            patch.object(
                benchmark,
                "score_observations",
                return_value=self.objective,
            ),
            patch.object(
                benchmark,
                "canonical_summary_json",
                return_value='{"objective":true}\n',
            ),
            patch.object(benchmark, "render_summary_markdown", report_mock),
            patch.object(
                benchmark,
                "emit_blinded_review_sheet",
                return_value='{"review":true}\n',
            ),
        )
        entered = []
        try:
            for selected in patches:
                entered.append(selected.start())
            yield SimpleNamespace(run=run_mock, report=report_mock)
        finally:
            for selected in reversed(patches):
                selected.stop()

    def test_success_publishes_complete_private_bundle_without_network(self) -> None:
        progress = io.StringIO()
        with tempfile.TemporaryDirectory() as root:
            output = self._private_directory(root)
            with self._pipeline() as mocks:
                result = run_benchmark(
                    self.suite,
                    self.config,
                    output,
                    block_device="mmcblk0",
                    strategies=("always_small_no_rag", "adaptive"),
                    repetitions=2,
                    telemetry_interval_ms=250,
                    progress=progress,
                )

            self.assertEqual(
                set(path.name for path in output.iterdir()), set(ARTIFACT_NAMES)
            )
            for path in output.iterdir():
                metadata = path.lstat()
                self.assertTrue(stat.S_ISREG(metadata.st_mode))
                self.assertEqual(stat.S_IMODE(metadata.st_mode), 0o600)
                self.assertEqual(metadata.st_uid, os.geteuid())

            telemetry = (output / TELEMETRY_NAME).read_text(encoding="utf-8")
            records = [json.loads(line) for line in telemetry.splitlines()]
            self.assertEqual(
                records,
                [TELEMETRY_SAMPLE.to_record(), TELEMETRY_SAMPLE_2.to_record()],
            )
            device_summary = json.loads(
                (output / TELEMETRY_SUMMARY_NAME).read_text(encoding="utf-8")
            )
            self.assertEqual(device_summary["block_device"], "mmcblk0")
            self.assertEqual(device_summary["diskstats"]["read_bytes"], 5 * 512)
            self.assertEqual(
                device_summary["throttling"]["counter_deltas"]["gpu"], 1
            )
            self.assertTrue(
                device_summary["throttling"]["thermal_trip_events_observed"]
            )
            self.assertEqual(
                device_summary["measurement_scope"]["per_case_or_strategy_energy"],
                "not_reported",
            )
            self.assertEqual(
                (output / SUMMARY_NAME).read_text(encoding="utf-8"),
                '{"objective":true}\n',
            )
            environment = json.loads(
                (output / ENVIRONMENT_NAME).read_text(encoding="utf-8")
            )
            self.assertEqual(environment["evaluation"]["run_id"], "benchmark_run")
            self.assertEqual(
                environment["evaluation"]["suite_sha256"], "a" * 64
            )
            report = (output / REPORT_NAME).read_text(encoding="utf-8")
            self.assertIn("# Objective report", report)
            self.assertIn("Whole-run sample-window VDD_IN energy", report)
            self.assertIn("`2.5`", report)
            self.assertEqual(
                (output / ANSWER_REVIEW_NAME).read_text(encoding="utf-8"),
                '{"review":true}\n',
            )

        sampler = _FakeSampler.instances[0]
        self.assertEqual(sampler.interval_ms, 250)
        self.assertEqual((sampler.enter_calls, sampler.exit_calls), (1, 1))
        call = mocks.run.call_args
        self.assertEqual(call.args[2], output / OBSERVATIONS_NAME)
        self.assertEqual(
            call.kwargs["strategies"],
            ("always_small_no_rag", "adaptive"),
        )
        self.assertEqual(call.kwargs["repetitions"], 2)
        self.assertIs(call.kwargs["telemetry"], sampler)
        self.assertIs(call.kwargs["clock_ns"], benchmark.time.monotonic_ns)
        self.assertNotIn("prompt", progress.getvalue().lower())
        self.assertEqual(result.run_id, "benchmark_run")
        self.assertEqual(result.telemetry_samples, 2)
        self.assertEqual(result.environment_path, output / ENVIRONMENT_NAME)
        self.assertEqual((result.retrieval_errors, result.cascade_errors), (1, 2))

    def test_preexisting_artifact_aborts_before_runtime_work_and_is_preserved(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as root:
            output = self._private_directory(root)
            existing = output / SUMMARY_NAME
            _create_private_file(existing, b"sentinel")
            with patch.object(benchmark, "run_evaluation") as run, patch.object(
                benchmark, "read_diskstats"
            ) as disk:
                with self.assertRaisesRegex(
                    EvaluationBenchmarkError, "already exists"
                ):
                    run_benchmark(
                        self.suite,
                        self.config,
                        output,
                        block_device="mmcblk0",
                    )
            self.assertEqual(existing.read_bytes(), b"sentinel")
            run.assert_not_called()
            disk.assert_not_called()

    def test_directory_must_be_absolute_private_owned_and_symlink_free(self) -> None:
        with self.assertRaises(EvaluationBenchmarkError):
            run_benchmark(
                self.suite,
                self.config,
                Path("relative"),
                block_device="mmcblk0",
            )

        with tempfile.TemporaryDirectory() as root:
            shared = self._private_directory(root, "shared")
            shared.chmod(0o750)
            link = Path(root) / "link"
            link.symlink_to(shared, target_is_directory=True)
            for path in (shared, link, Path(root) / "missing"):
                with self.subTest(path=path), self.assertRaises(
                    EvaluationBenchmarkError
                ):
                    run_benchmark(
                        self.suite,
                        self.config,
                        path,
                        block_device="mmcblk0",
                    )

            owned = self._private_directory(root, "owned")
            with patch.object(benchmark.os, "geteuid", return_value=os.geteuid() + 1):
                with self.assertRaises(EvaluationBenchmarkError):
                    run_benchmark(
                        self.suite,
                        self.config,
                        owned,
                        block_device="mmcblk0",
                    )

    def test_invalid_device_and_strategy_fail_before_runner(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            output = self._private_directory(root)
            with patch.object(benchmark, "run_evaluation") as run:
                invalid = (
                    {"block_device": "/dev/mmcblk0"},
                    {"block_device": "../mmcblk0"},
                    {"block_device": "mmcblk0", "strategies": ()},
                    {
                        "block_device": "mmcblk0",
                        "strategies": ("adaptive", "adaptive"),
                    },
                    {"block_device": "mmcblk0", "strategies": ("unknown",)},
                    {"block_device": "mmcblk0", "strategies": (object(),)},
                )
                for kwargs in invalid:
                    with self.subTest(kwargs=kwargs), self.assertRaises(
                        EvaluationBenchmarkError
                    ):
                        run_benchmark(
                            self.suite,
                            self.config,
                            output,
                            **kwargs,
                        )
            run.assert_not_called()

    def test_cancellation_preserves_raw_partial_observations_only(self) -> None:
        for cancellation in (KeyboardInterrupt(), SystemExit(7)):
            with self.subTest(cancellation=type(cancellation).__name__):
                with tempfile.TemporaryDirectory() as root:
                    output = self._private_directory(root)

                    def interrupted(suite, config, output_path, **kwargs):
                        _create_private_file(Path(output_path), b'\n{"partial":true}\n')
                        with kwargs["telemetry"]:
                            raise cancellation

                    with self._pipeline(runner=interrupted):
                        with self.assertRaises(type(cancellation)) as caught:
                            run_benchmark(
                                self.suite,
                                self.config,
                                output,
                                block_device="mmcblk0",
                            )
                    if isinstance(cancellation, SystemExit):
                        self.assertEqual(caught.exception.code, 7)
                    self.assertEqual(
                        (output / OBSERVATIONS_NAME).read_bytes(),
                        b'\n{"partial":true}\n',
                    )
                    self.assertEqual(
                        set(path.name for path in output.iterdir()),
                        {OBSERVATIONS_NAME},
                    )

    def test_scoring_failure_preserves_observations_and_publishes_no_derivatives(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as root:
            output = self._private_directory(root)
            with self._pipeline(), patch.object(
                benchmark,
                "load_observation_jsonl",
                side_effect=EvaluationScoringError("private answer"),
            ):
                with self.assertRaises(EvaluationScoringError):
                    run_benchmark(
                        self.suite,
                        self.config,
                        output,
                        block_device="mmcblk0",
                    )
            self.assertEqual(
                set(path.name for path in output.iterdir()),
                {OBSERVATIONS_NAME},
            )

    def test_publication_race_cleans_owned_derivatives_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            output = self._private_directory(root)
            raced = output / REPORT_NAME

            def create_racer(summary):
                _create_private_file(raced, b"racer sentinel")
                return "# report\n"

            with self._pipeline(report_side_effect=create_racer):
                with self.assertRaisesRegex(
                    EvaluationBenchmarkError, "already exists"
                ):
                    run_benchmark(
                        self.suite,
                        self.config,
                        output,
                        block_device="mmcblk0",
                    )

            self.assertEqual(raced.read_bytes(), b"racer sentinel")
            self.assertEqual(
                set(path.name for path in output.iterdir()),
                {OBSERVATIONS_NAME, REPORT_NAME},
            )


class ThrottleCaptureTests(unittest.TestCase):
    def test_capture_reads_only_fixed_nonblocking_event_counter_paths(self) -> None:
        paths = []

        def reader(path):
            paths.append(path)
            if "cv2-throttle-alert" in str(path):
                raise OSError("unavailable")
            return b"12\n"

        with patch.object(
            benchmark, "_read_nonblocking_sysfs", side_effect=reader
        ), patch.object(benchmark.time, "monotonic_ns", return_value=99):
            snapshot = benchmark._capture_throttle_snapshot()

        self.assertEqual(snapshot.monotonic_ns, 99)
        self.assertEqual(snapshot.unavailable, ("cv2",))
        self.assertEqual(len(snapshot.counters), 7)
        self.assertEqual(len(paths), 8)
        for path in paths:
            self.assertEqual(path.name, "thermal_trip_event")
            self.assertNotIn("thermal_trip_event_block", str(path))

    def test_throttle_delta_reports_evidence_without_temperature_inference(
        self,
    ) -> None:
        domains = benchmark._THROTTLE_DOMAINS
        before = benchmark._ThrottleSnapshot(
            1, tuple((name, 5) for name in domains), ()
        )
        after = benchmark._ThrottleSnapshot(
            2,
            tuple((name, 6 if name == "cpu" else 5) for name in domains),
            (),
        )
        available = benchmark._throttle_delta(before, after)
        self.assertEqual(available["status"], "available")
        self.assertTrue(available["thermal_trip_events_observed"])

        partial_after = benchmark._ThrottleSnapshot(
            2,
            tuple((name, 5) for name in domains if name != "gpu"),
            ("gpu",),
        )
        partial = benchmark._throttle_delta(before, partial_after)
        self.assertEqual(partial["status"], "partial")
        self.assertNotIn("thermal_trip_events_observed", partial)
        self.assertNotIn("temperature", json.dumps(partial).lower())

    def test_throttle_delta_reports_unavailable_and_rejects_resets(self) -> None:
        domains = benchmark._THROTTLE_DOMAINS
        unavailable_before = benchmark._ThrottleSnapshot(1, (), domains)
        unavailable_after = benchmark._ThrottleSnapshot(2, (), domains)
        unavailable = benchmark._throttle_delta(
            unavailable_before, unavailable_after
        )
        self.assertEqual(unavailable["status"], "unavailable")
        self.assertNotIn("thermal_trip_events_observed", unavailable)

        before = benchmark._ThrottleSnapshot(
            1, tuple((name, 5) for name in domains), ()
        )
        after = benchmark._ThrottleSnapshot(
            2,
            tuple((name, 4 if name == "cpu" else 5) for name in domains),
            (),
        )
        reset = benchmark._throttle_delta(before, after)
        self.assertEqual(reset["status"], "partial")
        self.assertIn("cpu", reset["unavailable_domains"])
        self.assertNotIn("cpu", reset["counter_deltas"])
        self.assertNotIn("thermal_trip_events_observed", reset)

    def test_throttle_delta_rejects_bad_timestamps_and_shapes(self) -> None:
        domains = benchmark._THROTTLE_DOMAINS
        valid = benchmark._ThrottleSnapshot(
            2, tuple((name, 0) for name in domains), ()
        )
        with self.assertRaises(EvaluationBenchmarkError):
            benchmark._throttle_delta(valid, valid)
        malformed = benchmark._ThrottleSnapshot(
            1,
            (("cpu", 0, 1),),
            tuple(name for name in domains if name != "cpu"),
        )
        with self.assertRaises(EvaluationBenchmarkError):
            benchmark._throttle_delta(malformed, valid)


class EnvironmentCaptureTests(unittest.TestCase):
    def test_source_snapshot_includes_relationship_grounding_code(self) -> None:
        self.assertIn(
            "src/oline_hri/relationships.py",
            benchmark._SOURCE_ALLOWLIST,
        )

    def test_source_snapshot_hashes_exact_allowlisted_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            project = Path(root)
            first = project / "one.py"
            second = project / "config" / "two.json"
            second.parent.mkdir()
            first.write_bytes(b"one\n")
            second.write_bytes(b'{"two":2}\n')
            with patch.object(benchmark, "_PROJECT_ROOT", project), patch.object(
                benchmark,
                "_SOURCE_ALLOWLIST",
                ("one.py", "config/two.json"),
            ):
                snapshot = benchmark._source_snapshot()

        aggregate = benchmark.sha256()
        for relative, raw in (
            ("one.py", b"one\n"),
            ("config/two.json", b'{"two":2}\n'),
        ):
            name = relative.encode("utf-8")
            aggregate.update(len(name).to_bytes(4, "big"))
            aggregate.update(name)
            aggregate.update(len(raw).to_bytes(8, "big"))
            aggregate.update(raw)
        self.assertEqual(snapshot["aggregate_sha256"], aggregate.hexdigest())
        self.assertEqual(
            [item["path"] for item in snapshot["files"]],
            ["one.py", "config/two.json"],
        )
        self.assertNotIn("one\n", json.dumps(snapshot))

    def test_ollama_inventory_uses_only_configured_tags_and_exact_digests(
        self,
    ) -> None:
        digest = "d" * 64

        def response(base_url, endpoint):
            self.assertEqual(base_url, "http://127.0.0.1:11434")
            if endpoint == "/api/version":
                return {"version": "0.33.3"}
            return {
                "models": [
                    {
                        "name": "qwen3:0.6b",
                        "digest": f"sha256:{digest}",
                        "details": {"private": "ignored"},
                    },
                    {"name": "unselected:latest", "digest": "e" * 64},
                ]
            }

        with patch.object(
            benchmark, "_read_local_ollama_json", side_effect=response
        ):
            snapshot = benchmark._ollama_snapshot(
                "http://127.0.0.1:11434",
                "qwen3:0.6b",
                "qwen3:4b",
                general_large_model="qwen3:1.7b",
            )

        self.assertEqual(snapshot["status"], "available")
        self.assertEqual(snapshot["version"]["value"], "0.33.3")
        self.assertEqual(
            snapshot["configured_models"][0]["digest"], f"sha256:{digest}"
        )
        self.assertFalse(snapshot["configured_models"][1]["installed"])
        self.assertFalse(snapshot["configured_models"][2]["installed"])
        self.assertNotIn("unselected", json.dumps(snapshot))
        self.assertNotIn("private", json.dumps(snapshot))

        with patch.object(benchmark, "_read_local_ollama_json") as request:
            unavailable = benchmark._ollama_snapshot(
                "https://example.com",
                "qwen3:0.6b",
                "qwen3:4b",
                general_large_model="qwen3:1.7b",
            )
        self.assertEqual(unavailable["status"], "unavailable")
        request.assert_not_called()

    def test_environment_binding_requires_exact_observation_hashes(self) -> None:
        snapshot = {"record_type": "benchmark_environment"}
        header = {
            "config_sha256": "1" * 64,
            "run_id": "run_1",
            "suite_sha256": "2" * 64,
        }
        bound = benchmark._bind_environment(snapshot, header, "run_1")
        self.assertEqual(bound["evaluation"]["config_sha256"], "1" * 64)
        with self.assertRaises(EvaluationBenchmarkError):
            benchmark._bind_environment(snapshot, header, "different")


class BenchmarkCliTests(unittest.TestCase):
    def test_cli_forwards_repeated_strategies_and_prints_only_progress(self) -> None:
        result = SimpleNamespace(run_id="safe_run", telemetry_samples=4)
        stdout = io.StringIO()
        stderr = io.StringIO()
        suite = object()
        config = object()
        with patch.object(
            benchmark, "load_evaluation_suite", return_value=suite
        ), patch.object(benchmark, "load_config", return_value=config), patch.object(
            benchmark, "run_benchmark", return_value=result
        ) as execute:
            code = main(
                (
                    "run",
                    "--output-dir",
                    "/private/results",
                    "--block-device",
                    "mmcblk0",
                    "--strategy",
                    "adaptive",
                    "--strategy",
                    "always_small_no_rag",
                    "--repetitions",
                    "2",
                    "--telemetry-interval-ms",
                    "250",
                ),
                stdout=stdout,
                stderr=stderr,
            )
        self.assertEqual(code, 0)
        self.assertIs(execute.call_args.args[0], suite)
        self.assertIs(execute.call_args.args[1], config)
        self.assertEqual(
            execute.call_args.kwargs["strategies"],
            ("adaptive", "always_small_no_rag"),
        )
        self.assertEqual(execute.call_args.kwargs["repetitions"], 2)
        self.assertEqual(execute.call_args.kwargs["telemetry_interval_ms"], 250)
        self.assertIs(execute.call_args.kwargs["progress"], stderr)
        self.assertIn("safe_run", stdout.getvalue())
        self.assertNotIn("prompt", stdout.getvalue().lower())
        self.assertEqual(stderr.getvalue(), "")

    def test_cli_sanitizes_expected_errors_but_preserves_cancellation(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        args = (
            "run",
            "--output-dir",
            "/private/results",
            "--block-device",
            "mmcblk0",
        )
        with patch.object(
            benchmark, "load_evaluation_suite", return_value=object()
        ), patch.object(benchmark, "load_config", return_value=object()), patch.object(
            benchmark,
            "run_benchmark",
            side_effect=EvaluationBenchmarkError("secret prompt and answer"),
        ):
            self.assertEqual(main(args, stdout=stdout, stderr=stderr), 2)
        self.assertNotIn("secret", stderr.getvalue())
        self.assertNotIn("answer", stderr.getvalue())

        with patch.object(
            benchmark, "load_evaluation_suite", return_value=object()
        ), patch.object(benchmark, "load_config", return_value=object()), patch.object(
            benchmark, "run_benchmark", side_effect=KeyboardInterrupt()
        ):
            with self.assertRaises(KeyboardInterrupt):
                main(args, stdout=io.StringIO(), stderr=io.StringIO())


if __name__ == "__main__":
    unittest.main()
