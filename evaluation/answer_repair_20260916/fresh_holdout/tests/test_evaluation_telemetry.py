from dataclasses import replace
import io
import json
from pathlib import Path
import subprocess
import tempfile
from threading import Event
import unittest
from unittest.mock import Mock, patch

from oline_hri.evaluation_telemetry import (
    MAX_TEGRASTATS_LINE_BYTES,
    DiskStatsSnapshot,
    EvaluationTelemetryError,
    TegrastatsSampler,
    TelemetryParseError,
    TelemetryStateError,
    TelemetryUnavailableError,
    capture_runtime_baseline,
    diskstats_delta,
    parse_diskstats,
    parse_tegrastats_line,
    read_diskstats,
    samples_jsonl,
    summarize_samples,
)


VALID_LINE = (
    b"09-07-2026 10:00:14 RAM 4796/7620MB (lfb 242x1MB) "
    b"SWAP 2509/3810MB (cached 7MB) "
    b"CPU [45%@1728,off,0%@729] GR3D_FREQ 56%@[1020,0] "
    b"cpu@50.687C gpu@51.281C VDD_IN 6444mW/6272mW "
    b"VDD_CPU_GPU_CV 2079mW/1923mW\n"
)


class _BlockingStdout:
    def __init__(self, lines=()) -> None:
        self._lines = list(lines)
        self._eof = Event()
        self.closed = False

    def readline(self, limit: int) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        self._eof.wait(2)
        return b""

    def finish(self) -> None:
        self._eof.set()

    def close(self) -> None:
        self.closed = True
        self.finish()


class _FakeProcess:
    def __init__(self, lines=(), *, timeout_on_wait: bool = False) -> None:
        self.stdout = _BlockingStdout(lines)
        self.returncode = None
        self.timeout_on_wait = timeout_on_wait
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = 0

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1
        if not self.timeout_on_wait:
            self.returncode = -15
            self.stdout.finish()

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9
        self.stdout.finish()

    def wait(self, timeout=None):
        self.wait_calls += 1
        if self.returncode is None:
            raise subprocess.TimeoutExpired("/usr/bin/tegrastats", timeout)
        return self.returncode


class _FailingCleanupProcess(_FakeProcess):
    def terminate(self) -> None:
        self.terminate_calls += 1
        self.returncode = -15
        self.stdout.finish()
        raise OSError("private cleanup detail")


class _SignallingOutput(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.written = Event()
        self.flush_calls = 0

    def write(self, value: str) -> int:
        result = super().write(value)
        self.written.set()
        return result

    def flush(self) -> None:
        self.flush_calls += 1
        super().flush()


class TegrastatsParserTests(unittest.TestCase):
    def test_valid_line_is_strictly_parsed_and_canonicalized(self) -> None:
        sample = parse_tegrastats_line(VALID_LINE, monotonic_ns=123456)

        self.assertEqual(sample.monotonic_ns, 123456)
        self.assertEqual((sample.ram_used_mb, sample.ram_total_mb), (4796, 7620))
        self.assertEqual(
            (sample.swap_used_mb, sample.swap_total_mb), (2509, 3810)
        )
        self.assertEqual(len(sample.cpu_cores), 3)
        self.assertEqual(sample.cpu_cores[0].utilization_percent, 45)
        self.assertFalse(sample.cpu_cores[1].online)
        self.assertEqual(sample.gr3d_percent, 56)
        self.assertEqual(
            sample.temperatures_c,
            (("cpu", 50.687), ("gpu", 51.281)),
        )
        self.assertEqual((sample.vdd_in_mw, sample.vdd_in_average_mw), (6444, 6272))

        output = samples_jsonl((sample,))
        self.assertTrue(output.endswith("\n"))
        record = json.loads(output)
        self.assertEqual(record, sample.to_record())
        self.assertEqual(
            output,
            json.dumps(
                record,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n",
        )
        lowered = output.lower()
        for prohibited in ("prompt", "answer", "gold", "memory_used", "case_id"):
            self.assertNotIn(prohibited, lowered)
        self.assertNotIn("throttl", lowered)

    def test_optional_gr3d_frequencies_and_crlf_are_accepted(self) -> None:
        sample = parse_tegrastats_line(
            VALID_LINE.replace(b"56%@[1020,0]", b"56%").replace(b"\n", b"\r\n"),
            monotonic_ns=1,
        )
        self.assertEqual(sample.gr3d_percent, 56)

    def test_malformed_and_out_of_range_lines_are_rejected(self) -> None:
        mutations = (
            b"",
            VALID_LINE + b"RAM 1/2MB",
            VALID_LINE + b"GR3D_FREQ malformed",
            VALID_LINE.replace(b"RAM 4796/7620MB ", b""),
            VALID_LINE.replace(b"4796/7620", b"7621/7620"),
            VALID_LINE.replace(b"2509/3810", b"3811/3810"),
            VALID_LINE.replace(b"45%@1728", b"101%@1728"),
            VALID_LINE.replace(b"45%@1728", b"45%1728"),
            VALID_LINE.replace(b"CPU [45%@1728,off,0%@729]", b"CPU [off]"),
            VALID_LINE.replace(b"GR3D_FREQ 56%@[1020,0]", b"GR3D_FREQ 56%@junk"),
            VALID_LINE.replace(b"GR3D_FREQ 56%@[1020,0] ", b""),
            VALID_LINE.replace(b"cpu@50.687C gpu@51.281C ", b""),
            VALID_LINE.replace(b"gpu@51.281C", b"cpu@51.281C"),
            VALID_LINE.replace(b"cpu@50.687C", b"cpu@999C"),
            VALID_LINE.replace(b"VDD_IN 6444mW/6272mW ", b""),
            VALID_LINE.replace(b"6444mW", b"1000001mW"),
            VALID_LINE.replace(b" RAM", b"\x00RAM", 1),
            VALID_LINE.replace(b"RAM", b"R\xffM", 1),
            b"x" * (MAX_TEGRASTATS_LINE_BYTES + 1),
        )
        for value in mutations:
            with self.subTest(value=value[:60]):
                with self.assertRaises(TelemetryParseError):
                    parse_tegrastats_line(value, monotonic_ns=1)

    def test_invalid_monotonic_timestamps_are_rejected(self) -> None:
        for value in (-1, True, 1.5, 1 << 65):
            with self.subTest(value=value):
                with self.assertRaises(TelemetryParseError):
                    parse_tegrastats_line(VALID_LINE, monotonic_ns=value)


class TelemetrySummaryTests(unittest.TestCase):
    def test_summary_has_nearest_rank_percentiles_and_trapezoidal_energy(
        self,
    ) -> None:
        first = parse_tegrastats_line(VALID_LINE, monotonic_ns=0)
        first = replace(first, vdd_in_mw=1000, gr3d_percent=10)
        second = replace(
            first,
            monotonic_ns=1_000_000_000,
            vdd_in_mw=3000,
            gr3d_percent=30,
        )
        third = replace(
            first,
            monotonic_ns=3_000_000_000,
            vdd_in_mw=5000,
            gr3d_percent=50,
        )

        summary = summarize_samples((first, second, third))

        self.assertEqual(summary["sample_count"], 3)
        self.assertEqual(summary["duration_seconds"], 3.0)
        self.assertEqual(summary["vdd_in_energy_joules"], 10.0)
        power = summary["metrics"]["vdd_in_mw"]
        self.assertEqual(power, {"max": 5000, "p50": 3000, "p95": 5000})
        self.assertEqual(summary["metrics"]["gr3d_percent"]["p50"], 30)
        self.assertEqual(summary["temperatures_c"]["gpu"]["sample_count"], 3)
        json.dumps(summary, allow_nan=False)

    def test_empty_and_single_sample_summaries_do_not_invent_energy(self) -> None:
        empty = summarize_samples(())
        self.assertEqual(empty["sample_count"], 0)
        self.assertNotIn("metrics", empty)

        sample = parse_tegrastats_line(VALID_LINE, monotonic_ns=1)
        single = summarize_samples((sample,))
        self.assertNotIn("duration_seconds", single)
        self.assertNotIn("vdd_in_energy_joules", single)

    def test_nonincreasing_or_invalid_samples_are_rejected(self) -> None:
        sample = parse_tegrastats_line(VALID_LINE, monotonic_ns=2)
        with self.assertRaises(TelemetryStateError):
            summarize_samples((sample, replace(sample, monotonic_ns=2)))
        with self.assertRaises(TelemetryStateError):
            summarize_samples((sample, object()))


class DiskStatsTests(unittest.TestCase):
    BEFORE = "179 0 mmcblk0 10 2 100 7 20 3 200 9 1 11 13 4 5 6 7 8 9\n"
    AFTER = "179 0 mmcblk0 12 3 110 9 24 4 230 15 2 18 22 5 6 10 8 10 12\n"

    def test_parse_and_delta_include_only_available_kernel_counters(self) -> None:
        before = parse_diskstats(self.BEFORE, "mmcblk0", monotonic_ns=1_000)
        after = parse_diskstats(self.AFTER, "mmcblk0", monotonic_ns=2_001_000)
        delta = diskstats_delta(before, after)
        record = delta.to_record()

        self.assertEqual(delta.read_bytes, 10 * 512)
        self.assertEqual(delta.write_bytes, 30 * 512)
        self.assertEqual(delta.discard_bytes, 4 * 512)
        self.assertEqual(delta.discards_merged, 1)
        self.assertEqual(delta.flushes_completed, 2)
        self.assertEqual(record["elapsed_seconds"], 0.002)
        self.assertNotIn("throttling", record)
        json.dumps(record, allow_nan=False)

        legacy = parse_diskstats(
            "179 0 mmcblk0 1 2 3 4 5 6 7 8 0 9 10\n",
            "mmcblk0",
            monotonic_ns=3,
        )
        self.assertIsNone(legacy.discards_completed)

    def test_read_diskstats_uses_bounded_fixed_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diskstats"
            path.write_text(self.BEFORE, encoding="ascii")
            with patch(
                "oline_hri.evaluation_telemetry.DISKSTATS_PATH", path
            ), patch(
                "oline_hri.evaluation_telemetry.time.monotonic_ns",
                return_value=42,
            ):
                snapshot = read_diskstats("mmcblk0")
        self.assertEqual(snapshot.monotonic_ns, 42)
        self.assertEqual(snapshot.device, "mmcblk0")

    def test_device_names_and_malformed_sources_are_rejected(self) -> None:
        invalid_names = ("", "../mmcblk0", "/dev/mmcblk0", "mmc.blk0", "é", "x" * 65)
        for name in invalid_names:
            with self.subTest(name=name):
                with self.assertRaises(TelemetryParseError):
                    parse_diskstats(self.BEFORE, name, monotonic_ns=1)

        malformed = (
            "179 0 sda 1 2 3 4 5 6 7 8 0 9 10\n",
            self.BEFORE + self.BEFORE,
            "179 0 mmcblk0 1 2 3\n",
            "179 0 mmcblk0 1 2 -3 4 5 6 7 8 0 9 10\n",
            "179 0 mmcblk0 1 2 3 4 5 6 7 8 0 9 18446744073709551616\n",
            self.BEFORE.replace(" 10 ", " \x00 ", 1),
        )
        for raw in malformed:
            with self.subTest(raw=raw[:60]):
                with self.assertRaises(TelemetryParseError):
                    parse_diskstats(raw, "mmcblk0", monotonic_ns=1)

    def test_incompatible_or_decreasing_snapshots_are_rejected(self) -> None:
        before = parse_diskstats(self.BEFORE, "mmcblk0", monotonic_ns=10)
        after = parse_diskstats(self.AFTER, "mmcblk0", monotonic_ns=20)
        with self.assertRaises(TelemetryStateError):
            diskstats_delta(before, replace(after, device="sda"))
        with self.assertRaises(TelemetryStateError):
            diskstats_delta(before, replace(after, monotonic_ns=10))
        with self.assertRaises(TelemetryStateError):
            diskstats_delta(before, replace(after, reads_completed=9))
        with self.assertRaises(TelemetryStateError):
            diskstats_delta(before, replace(after, discards_merged=None))
        with self.assertRaises(TelemetryStateError):
            diskstats_delta(before, object())


class TegrastatsSamplerTests(unittest.TestCase):
    def test_sampler_uses_fixed_argv_emits_callback_and_terminates_child(self) -> None:
        process = _FakeProcess((VALID_LINE,))
        received = []
        delivered = Event()

        def callback(record) -> None:
            received.append(record)
            delivered.set()

        with patch(
            "oline_hri.evaluation_telemetry.subprocess.Popen",
            return_value=process,
        ) as popen, patch(
            "oline_hri.evaluation_telemetry.time.monotonic_ns",
            return_value=123,
        ), patch("oline_hri.evaluation_telemetry.os.kill") as os_kill:
            with TegrastatsSampler(interval_ms=250, on_sample=callback) as sampler:
                self.assertTrue(delivered.wait(1))

        popen.assert_called_once_with(
            ("/usr/bin/tegrastats", "--interval", "250"),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
            close_fds=True,
        )
        os_kill.assert_not_called()
        self.assertEqual(process.terminate_calls, 1)
        self.assertEqual(process.kill_calls, 0)
        self.assertTrue(process.stdout.closed)
        self.assertEqual(received, [sampler.samples[0].to_record()])
        self.assertEqual(sampler.summary()["sample_count"], 1)

    def test_sampler_writes_and_flushes_canonical_jsonl(self) -> None:
        process = _FakeProcess((VALID_LINE,))
        output = _SignallingOutput()
        with patch(
            "oline_hri.evaluation_telemetry.subprocess.Popen",
            return_value=process,
        ), patch(
            "oline_hri.evaluation_telemetry.time.monotonic_ns",
            return_value=456,
        ):
            with TegrastatsSampler(output=output) as sampler:
                self.assertTrue(output.written.wait(1))
        self.assertEqual(output.getvalue(), samples_jsonl(sampler.samples))
        self.assertGreaterEqual(output.flush_calls, 1)

    def test_timeout_kills_only_the_owned_child(self) -> None:
        process = _FakeProcess(timeout_on_wait=True)
        with patch(
            "oline_hri.evaluation_telemetry.subprocess.Popen",
            return_value=process,
        ), patch("oline_hri.evaluation_telemetry.os.kill") as os_kill:
            with TegrastatsSampler():
                pass
        self.assertEqual(process.terminate_calls, 1)
        self.assertEqual(process.kill_calls, 1)
        os_kill.assert_not_called()

    def test_body_cancellation_is_not_replaced_by_cleanup_failure(self) -> None:
        for cancellation in (KeyboardInterrupt(), SystemExit(9)):
            process = _FailingCleanupProcess()
            with self.subTest(cancellation=type(cancellation).__name__), patch(
                "oline_hri.evaluation_telemetry.subprocess.Popen",
                return_value=process,
            ):
                with self.assertRaises(type(cancellation)) as caught:
                    with TegrastatsSampler():
                        raise cancellation
                if isinstance(cancellation, SystemExit):
                    self.assertEqual(caught.exception.code, 9)

    def test_callback_cancellation_and_error_are_reported(self) -> None:
        for error, expected in (
            (KeyboardInterrupt(), KeyboardInterrupt),
            (ValueError("private"), EvaluationTelemetryError),
        ):
            delivered = Event()

            def callback(record, selected=error) -> None:
                delivered.set()
                raise selected

            process = _FakeProcess((VALID_LINE,))
            with self.subTest(error=type(error).__name__), patch(
                "oline_hri.evaluation_telemetry.subprocess.Popen",
                return_value=process,
            ), patch(
                "oline_hri.evaluation_telemetry.time.monotonic_ns",
                return_value=123,
            ):
                with self.assertRaises(expected):
                    with TegrastatsSampler(on_sample=callback):
                        self.assertTrue(delivered.wait(1))

    def test_unexpected_eof_and_oversized_lines_are_reported(self) -> None:
        sources = ((), (b"x" * (MAX_TEGRASTATS_LINE_BYTES + 1),))
        for lines in sources:
            process = _FakeProcess(lines)
            process.stdout.finish()
            with self.subTest(lines=bool(lines)), patch(
                "oline_hri.evaluation_telemetry.subprocess.Popen",
                return_value=process,
            ):
                with self.assertRaises(EvaluationTelemetryError):
                    with TegrastatsSampler():
                        pass

    def test_invalid_construction_start_failure_and_reuse_are_safe(self) -> None:
        invalid_intervals = (True, 1.5, 249, 60_001)
        for interval in invalid_intervals:
            with self.subTest(interval=interval):
                with self.assertRaises(ValueError):
                    TegrastatsSampler(interval_ms=interval)
        with self.assertRaises(TypeError):
            TegrastatsSampler(on_sample="bad")
        with self.assertRaises(TypeError):
            TegrastatsSampler(output=object())
        with self.assertRaises(ValueError):
            TegrastatsSampler(on_sample=lambda record: None, output=io.StringIO())

        with patch(
            "oline_hri.evaluation_telemetry.subprocess.Popen",
            side_effect=OSError("private"),
        ):
            with self.assertRaisesRegex(
                TelemetryUnavailableError, "tegrastats could not be started"
            ):
                with TegrastatsSampler():
                    pass

        process = _FakeProcess()
        with patch(
            "oline_hri.evaluation_telemetry.subprocess.Popen",
            return_value=process,
        ):
            sampler = TegrastatsSampler()
            with sampler:
                pass
            with self.assertRaises(TelemetryStateError):
                sampler.__enter__()


class RuntimeBaselineTests(unittest.TestCase):
    def test_baseline_is_json_safe_and_omits_unavailable_fields(self) -> None:
        usage = Mock(ru_nivcsw=2, ru_maxrss=100, ru_nvcsw=3)
        with patch(
            "oline_hri.evaluation_telemetry.resource.getrusage",
            return_value=usage,
        ), patch(
            "oline_hri.evaluation_telemetry.time.monotonic_ns", return_value=10
        ), patch(
            "oline_hri.evaluation_telemetry.time.process_time_ns", return_value=20
        ), patch(
            "oline_hri.evaluation_telemetry.os.cpu_count", return_value=6
        ), patch(
            "oline_hri.evaluation_telemetry.os.getloadavg",
            return_value=(1.0, 2.0, 3.0),
        ):
            record = capture_runtime_baseline()
        self.assertEqual(record["logical_cpu_count"], 6)
        self.assertEqual(record["load_average"]["5m"], 2.0)
        self.assertEqual(record["process"]["max_rss_kib"], 100)
        json.dumps(record, allow_nan=False)

        with patch(
            "oline_hri.evaluation_telemetry.os.getloadavg",
            side_effect=OSError,
        ):
            unavailable = capture_runtime_baseline()
        self.assertNotIn("load_average", unavailable)


if __name__ == "__main__":
    unittest.main()
