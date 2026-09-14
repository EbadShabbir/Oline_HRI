"""Bounded, gold-free Jetson telemetry helpers for local evaluation.

The sampler owns exactly one ``tegrastats`` child and never invokes a shell.
It intentionally does not inspect evaluation prompts, answers, or gold labels.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from math import ceil, fsum, isfinite
import os
from pathlib import Path
import re
import resource
import subprocess
from threading import Event, Lock, Thread
import time
from typing import Callable, Optional, Sequence, TextIO


SCHEMA_VERSION = 1
TEGRASTATS_EXECUTABLE = "/usr/bin/tegrastats"
DISKSTATS_PATH = Path("/proc/diskstats")
MIN_INTERVAL_MS = 250
MAX_INTERVAL_MS = 60_000
MAX_TEGRASTATS_LINE_BYTES = 4_096
MAX_DISKSTATS_BYTES = 262_144
MAX_SAMPLES = 100_000
_CHILD_STOP_TIMEOUT_SECONDS = 2.0
_MAX_COUNTER = (1 << 64) - 1
_MAX_MEMORY_MB = 1_048_576
_MAX_FREQUENCY_MHZ = 100_000
_MAX_POWER_MW = 1_000_000

_DEVICE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_RAM_PATTERN = re.compile(r"(?:^|\s)RAM (\d{1,7})/(\d{1,7})MB(?=\s|$)")
_SWAP_PATTERN = re.compile(r"(?:^|\s)SWAP (\d{1,7})/(\d{1,7})MB(?=\s|$)")
_CPU_PATTERN = re.compile(r"(?:^|\s)CPU \[([^\]]{1,1024})\](?=\s|$)")
_CPU_CORE_PATTERN = re.compile(r"(\d{1,3})%@(\d{1,6})(?:MHz)?\Z")
_GR3D_PATTERN = re.compile(
    r"(?:^|\s)GR3D_FREQ (\d{1,3})%"
    r"(?:@\[\d{1,7}(?:,\d{1,7}){0,15}\])?(?=\s|$)"
)
_TEMPERATURE_PATTERN = re.compile(
    r"(?:^|\s)([A-Za-z][A-Za-z0-9_-]{0,31})@"
    r"(-?(?:\d{1,3})(?:\.\d{1,3})?)C(?=\s|$)"
)
_VDD_IN_PATTERN = re.compile(
    r"(?:^|\s)VDD_IN (\d{1,7})mW/(\d{1,7})mW(?=\s|$)"
)


class EvaluationTelemetryError(RuntimeError):
    """Base error for evaluation telemetry."""


class TelemetryParseError(EvaluationTelemetryError):
    """Raised when a telemetry source violates its bounded format."""


class TelemetryStateError(EvaluationTelemetryError):
    """Raised for an invalid sampler lifecycle or counter transition."""


class TelemetryUnavailableError(EvaluationTelemetryError):
    """Raised when the local telemetry process cannot be started or stopped."""


@dataclass(frozen=True)
class CpuCoreSample:
    """One logical CPU's state in a ``tegrastats`` sample."""

    online: bool
    utilization_percent: Optional[int]
    frequency_mhz: Optional[int]

    def to_record(self) -> dict[str, object]:
        if not self.online:
            return {"online": False}
        return {
            "frequency_mhz": self.frequency_mhz,
            "online": True,
            "utilization_percent": self.utilization_percent,
        }


@dataclass(frozen=True)
class TelemetrySample:
    """One strictly parsed, monotonic Jetson sample."""

    monotonic_ns: int
    ram_used_mb: int
    ram_total_mb: int
    swap_used_mb: int
    swap_total_mb: int
    cpu_cores: tuple[CpuCoreSample, ...]
    gr3d_percent: int
    temperatures_c: tuple[tuple[str, float], ...]
    vdd_in_mw: int
    vdd_in_average_mw: int

    def to_record(self) -> dict[str, object]:
        _validate_sample(self)
        return {
            "cpu": [core.to_record() for core in self.cpu_cores],
            "gr3d_percent": self.gr3d_percent,
            "monotonic_ns": self.monotonic_ns,
            "ram": {
                "total_mb": self.ram_total_mb,
                "used_mb": self.ram_used_mb,
            },
            "record_type": "jetson_telemetry",
            "schema_version": SCHEMA_VERSION,
            "swap": {
                "total_mb": self.swap_total_mb,
                "used_mb": self.swap_used_mb,
            },
            "temperatures_c": dict(self.temperatures_c),
            "vdd_in": {
                "average_mw": self.vdd_in_average_mw,
                "instant_mw": self.vdd_in_mw,
            },
        }


@dataclass(frozen=True)
class DiskStatsSnapshot:
    """Selected cumulative Linux block counters at one monotonic instant."""

    monotonic_ns: int
    device: str
    reads_completed: int
    reads_merged: int
    sectors_read: int
    read_time_ms: int
    writes_completed: int
    writes_merged: int
    sectors_written: int
    write_time_ms: int
    ios_in_progress: int
    io_time_ms: int
    weighted_io_time_ms: int
    discards_completed: Optional[int] = None
    discards_merged: Optional[int] = None
    sectors_discarded: Optional[int] = None
    discard_time_ms: Optional[int] = None
    flushes_completed: Optional[int] = None
    flush_time_ms: Optional[int] = None


@dataclass(frozen=True)
class DiskStatsDelta:
    """Non-negative disk-counter changes over a monotonic interval."""

    device: str
    start_monotonic_ns: int
    end_monotonic_ns: int
    reads_completed: int
    reads_merged: int
    read_bytes: int
    read_time_ms: int
    writes_completed: int
    writes_merged: int
    write_bytes: int
    write_time_ms: int
    end_ios_in_progress: int
    io_time_ms: int
    weighted_io_time_ms: int
    discards_completed: Optional[int] = None
    discards_merged: Optional[int] = None
    discard_bytes: Optional[int] = None
    discard_time_ms: Optional[int] = None
    flushes_completed: Optional[int] = None
    flush_time_ms: Optional[int] = None

    def to_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "device": self.device,
            "elapsed_seconds": (
                self.end_monotonic_ns - self.start_monotonic_ns
            )
            / 1_000_000_000,
            "end_ios_in_progress": self.end_ios_in_progress,
            "end_monotonic_ns": self.end_monotonic_ns,
            "io_time_ms": self.io_time_ms,
            "read_bytes": self.read_bytes,
            "read_time_ms": self.read_time_ms,
            "reads_completed": self.reads_completed,
            "reads_merged": self.reads_merged,
            "record_type": "diskstats_delta",
            "schema_version": SCHEMA_VERSION,
            "start_monotonic_ns": self.start_monotonic_ns,
            "weighted_io_time_ms": self.weighted_io_time_ms,
            "write_bytes": self.write_bytes,
            "write_time_ms": self.write_time_ms,
            "writes_completed": self.writes_completed,
            "writes_merged": self.writes_merged,
        }
        optional = {
            "discard_bytes": self.discard_bytes,
            "discard_time_ms": self.discard_time_ms,
            "discards_completed": self.discards_completed,
            "discards_merged": self.discards_merged,
            "flush_time_ms": self.flush_time_ms,
            "flushes_completed": self.flushes_completed,
        }
        record.update(
            {key: value for key, value in optional.items() if value is not None}
        )
        return record


def parse_tegrastats_line(
    line: str | bytes, *, monotonic_ns: int
) -> TelemetrySample:
    """Strictly parse one bounded ``tegrastats`` output line."""

    timestamp = _monotonic_timestamp(monotonic_ns)
    text = _bounded_ascii_line(line)
    ram_used, ram_total = _memory_pair(text, _RAM_PATTERN, "RAM")
    swap_used, swap_total = _memory_pair(text, _SWAP_PATTERN, "SWAP")

    cpu_match = _single_match(_CPU_PATTERN, text, "CPU")
    cpu_cores = tuple(_cpu_core(value) for value in cpu_match.group(1).split(","))
    if not 1 <= len(cpu_cores) <= 64:
        raise TelemetryParseError("CPU core count is outside the supported range")
    if not any(core.online for core in cpu_cores):
        raise TelemetryParseError("CPU sample contains no online core")

    gr3d_percent = _bounded_percent(
        _single_match(_GR3D_PATTERN, text, "GR3D_FREQ").group(1),
        "GR3D_FREQ",
    )
    power_match = _single_match(_VDD_IN_PATTERN, text, "VDD_IN")
    vdd_in_mw = _bounded_integer(
        power_match.group(1), "VDD_IN", maximum=_MAX_POWER_MW
    )
    vdd_in_average_mw = _bounded_integer(
        power_match.group(2), "VDD_IN average", maximum=_MAX_POWER_MW
    )

    temperature_matches = tuple(_TEMPERATURE_PATTERN.finditer(text))
    if not temperature_matches:
        raise TelemetryParseError("temperature data is missing")
    if len(temperature_matches) > 32:
        raise TelemetryParseError("too many temperature sensors")
    temperatures: dict[str, float] = {}
    for match in temperature_matches:
        name = match.group(1)
        if name in temperatures:
            raise TelemetryParseError("temperature sensor is duplicated")
        value = float(match.group(2))
        if not isfinite(value) or not -100.0 <= value <= 250.0:
            raise TelemetryParseError("temperature is outside the supported range")
        temperatures[name] = value

    return TelemetrySample(
        monotonic_ns=timestamp,
        ram_used_mb=ram_used,
        ram_total_mb=ram_total,
        swap_used_mb=swap_used,
        swap_total_mb=swap_total,
        cpu_cores=cpu_cores,
        gr3d_percent=gr3d_percent,
        temperatures_c=tuple(sorted(temperatures.items())),
        vdd_in_mw=vdd_in_mw,
        vdd_in_average_mw=vdd_in_average_mw,
    )


def samples_jsonl(samples: Sequence[TelemetrySample]) -> str:
    """Return canonical JSON Lines containing telemetry and no evaluation gold."""

    values = tuple(samples)
    for sample in values:
        _validate_sample(sample)
    return "".join(_canonical_line(sample.to_record()) for sample in values)


def summarize_samples(samples: Sequence[TelemetrySample]) -> dict[str, object]:
    """Summarize p50, p95, maxima, and measured input energy."""

    values = tuple(samples)
    summary: dict[str, object] = {
        "record_type": "jetson_telemetry_summary",
        "sample_count": len(values),
        "schema_version": SCHEMA_VERSION,
    }
    if not values:
        return summary

    _strict_sample_timestamps(values)
    cpu_means = []
    for sample in values:
        online = [
            core.utilization_percent
            for core in sample.cpu_cores
            if core.online and core.utilization_percent is not None
        ]
        if not online:
            raise TelemetryStateError("sample contains no online CPU utilization")
        cpu_means.append(fsum(online) / len(online))

    summary["metrics"] = {
        "cpu_mean_percent": _summary_stats(cpu_means),
        "gr3d_percent": _summary_stats(
            [sample.gr3d_percent for sample in values]
        ),
        "ram_used_mb": _summary_stats(
            [sample.ram_used_mb for sample in values]
        ),
        "swap_used_mb": _summary_stats(
            [sample.swap_used_mb for sample in values]
        ),
        "vdd_in_average_mw": _summary_stats(
            [sample.vdd_in_average_mw for sample in values]
        ),
        "vdd_in_mw": _summary_stats([sample.vdd_in_mw for sample in values]),
    }

    sensor_values: dict[str, list[float]] = {}
    for sample in values:
        for name, value in sample.temperatures_c:
            sensor_values.setdefault(name, []).append(value)
    summary["temperatures_c"] = {
        name: {
            "sample_count": len(sensor_samples),
            **_summary_stats(sensor_samples),
        }
        for name, sensor_samples in sorted(sensor_values.items())
    }

    if len(values) >= 2:
        summary["duration_seconds"] = (
            values[-1].monotonic_ns - values[0].monotonic_ns
        ) / 1_000_000_000
        intervals = (
            (
                (right.vdd_in_mw + left.vdd_in_mw) / 2_000,
                (right.monotonic_ns - left.monotonic_ns) / 1_000_000_000,
            )
            for left, right in zip(values, values[1:])
        )
        summary["vdd_in_energy_joules"] = fsum(
            watts * seconds for watts, seconds in intervals
        )
    return summary


def read_diskstats(device: str) -> DiskStatsSnapshot:
    """Read one exact simple block-device entry from ``/proc/diskstats``."""

    name = _device_name(device)
    raw = _read_bounded_file(DISKSTATS_PATH, MAX_DISKSTATS_BYTES)
    return parse_diskstats(raw, name, monotonic_ns=time.monotonic_ns())


def parse_diskstats(
    raw: str | bytes, device: str, *, monotonic_ns: int
) -> DiskStatsSnapshot:
    """Parse one device snapshot from bounded ``/proc/diskstats`` text."""

    name = _device_name(device)
    timestamp = _monotonic_timestamp(monotonic_ns)
    text = _bounded_ascii_text(raw, MAX_DISKSTATS_BYTES, "diskstats")
    matches = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[2] == name:
            matches.append(fields)
    if len(matches) != 1:
        message = "device is absent" if not matches else "device is duplicated"
        raise TelemetryParseError(f"diskstats {message}")

    fields = matches[0]
    if len(fields) < 3:
        raise TelemetryParseError("diskstats device line is malformed")
    _bounded_integer(fields[0], "diskstats major", maximum=(1 << 32) - 1)
    _bounded_integer(fields[1], "diskstats minor", maximum=(1 << 32) - 1)
    counters = fields[3:]
    if len(counters) not in {11, 15, 17}:
        raise TelemetryParseError("diskstats counter count is unsupported")
    parsed = tuple(
        _bounded_integer(value, "diskstats counter", maximum=_MAX_COUNTER)
        for value in counters
    )
    optional: dict[str, Optional[int]] = {
        "discards_completed": None,
        "discards_merged": None,
        "sectors_discarded": None,
        "discard_time_ms": None,
        "flushes_completed": None,
        "flush_time_ms": None,
    }
    if len(parsed) >= 15:
        optional.update(
            {
                "discards_completed": parsed[11],
                "discards_merged": parsed[12],
                "sectors_discarded": parsed[13],
                "discard_time_ms": parsed[14],
            }
        )
    if len(parsed) == 17:
        optional.update(
            {
                "flushes_completed": parsed[15],
                "flush_time_ms": parsed[16],
            }
        )
    return DiskStatsSnapshot(
        monotonic_ns=timestamp,
        device=name,
        reads_completed=parsed[0],
        reads_merged=parsed[1],
        sectors_read=parsed[2],
        read_time_ms=parsed[3],
        writes_completed=parsed[4],
        writes_merged=parsed[5],
        sectors_written=parsed[6],
        write_time_ms=parsed[7],
        ios_in_progress=parsed[8],
        io_time_ms=parsed[9],
        weighted_io_time_ms=parsed[10],
        **optional,
    )


def diskstats_delta(
    before: DiskStatsSnapshot, after: DiskStatsSnapshot
) -> DiskStatsDelta:
    """Calculate non-negative I/O changes between compatible snapshots."""

    _validate_disk_snapshot(before)
    _validate_disk_snapshot(after)
    if before.device != after.device:
        raise TelemetryStateError("diskstats devices do not match")
    if after.monotonic_ns <= before.monotonic_ns:
        raise TelemetryStateError("diskstats timestamps are not increasing")

    required_names = (
        "reads_completed",
        "reads_merged",
        "sectors_read",
        "read_time_ms",
        "writes_completed",
        "writes_merged",
        "sectors_written",
        "write_time_ms",
        "io_time_ms",
        "weighted_io_time_ms",
    )
    changes = {
        name: _counter_delta(getattr(before, name), getattr(after, name), name)
        for name in required_names
    }

    optional_changes: dict[str, Optional[int]] = {}
    for name in (
        "discards_completed",
        "discards_merged",
        "sectors_discarded",
        "discard_time_ms",
        "flushes_completed",
        "flush_time_ms",
    ):
        first = getattr(before, name)
        second = getattr(after, name)
        if (first is None) != (second is None):
            raise TelemetryStateError("diskstats optional counter sets do not match")
        optional_changes[name] = (
            None if first is None else _counter_delta(first, second, name)
        )

    return DiskStatsDelta(
        device=before.device,
        start_monotonic_ns=before.monotonic_ns,
        end_monotonic_ns=after.monotonic_ns,
        reads_completed=changes["reads_completed"],
        reads_merged=changes["reads_merged"],
        read_bytes=changes["sectors_read"] * 512,
        read_time_ms=changes["read_time_ms"],
        writes_completed=changes["writes_completed"],
        writes_merged=changes["writes_merged"],
        write_bytes=changes["sectors_written"] * 512,
        write_time_ms=changes["write_time_ms"],
        end_ios_in_progress=after.ios_in_progress,
        io_time_ms=changes["io_time_ms"],
        weighted_io_time_ms=changes["weighted_io_time_ms"],
        discards_completed=optional_changes["discards_completed"],
        discards_merged=optional_changes["discards_merged"],
        discard_bytes=(
            None
            if optional_changes["sectors_discarded"] is None
            else optional_changes["sectors_discarded"] * 512
        ),
        discard_time_ms=optional_changes["discard_time_ms"],
        flushes_completed=optional_changes["flushes_completed"],
        flush_time_ms=optional_changes["flush_time_ms"],
    )


def capture_runtime_baseline() -> dict[str, object]:
    """Capture a small JSON-safe CPU/process baseline without prompt data."""

    usage = resource.getrusage(resource.RUSAGE_SELF)
    record: dict[str, object] = {
        "monotonic_ns": time.monotonic_ns(),
        "process": {
            "cpu_time_ns": time.process_time_ns(),
            "involuntary_context_switches": int(usage.ru_nivcsw),
            "max_rss_kib": int(usage.ru_maxrss),
            "voluntary_context_switches": int(usage.ru_nvcsw),
        },
        "record_type": "runtime_baseline",
        "schema_version": SCHEMA_VERSION,
    }
    cpu_count = os.cpu_count()
    if cpu_count is not None:
        record["logical_cpu_count"] = cpu_count
    try:
        loads = os.getloadavg()
    except OSError:
        pass
    else:
        if all(isfinite(value) and value >= 0 for value in loads):
            record["load_average"] = {
                "1m": loads[0],
                "5m": loads[1],
                "15m": loads[2],
            }
    return record


class TegrastatsSampler:
    """Context-managed asynchronous sampler for one owned ``tegrastats`` child."""

    def __init__(
        self,
        *,
        interval_ms: int = 500,
        on_sample: Optional[Callable[[dict[str, object]], None]] = None,
        output: Optional[TextIO] = None,
    ) -> None:
        if isinstance(interval_ms, bool) or not isinstance(interval_ms, int):
            raise ValueError("interval_ms must be an integer")
        if not MIN_INTERVAL_MS <= interval_ms <= MAX_INTERVAL_MS:
            raise ValueError(
                f"interval_ms must be between {MIN_INTERVAL_MS} and "
                f"{MAX_INTERVAL_MS}"
            )
        if on_sample is not None and not callable(on_sample):
            raise TypeError("on_sample must be callable")
        if output is not None and not callable(getattr(output, "write", None)):
            raise TypeError("output must be a writable text stream")
        if on_sample is not None and output is not None:
            raise ValueError("choose either on_sample or output")

        self.interval_ms = interval_ms
        self._on_sample = on_sample
        self._output = output
        self._process: Optional[subprocess.Popen[bytes]] = None
        self._thread: Optional[Thread] = None
        self._stopping = Event()
        self._lock = Lock()
        self._samples: list[TelemetrySample] = []
        self._reader_error: Optional[BaseException] = None
        self._cleanup_error: Optional[BaseException] = None
        self._entered = False
        self._closed = False

    @property
    def samples(self) -> tuple[TelemetrySample, ...]:
        with self._lock:
            return tuple(self._samples)

    @property
    def cleanup_error(self) -> Optional[BaseException]:
        return self._cleanup_error

    def summary(self) -> dict[str, object]:
        return summarize_samples(self.samples)

    def __enter__(self) -> "TegrastatsSampler":
        if self._entered or self._closed:
            raise TelemetryStateError("telemetry sampler cannot be reused")
        self._entered = True
        argv = (
            TEGRASTATS_EXECUTABLE,
            "--interval",
            str(self.interval_ms),
        )
        try:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
                close_fds=True,
            )
        except (KeyboardInterrupt, SystemExit):
            self._closed = True
            raise
        except OSError:
            self._closed = True
            raise TelemetryUnavailableError("tegrastats could not be started") from None

        self._process = process
        if process.stdout is None:
            self._closed = True
            cleanup_error = self._stop_owned_child()
            if isinstance(cleanup_error, (KeyboardInterrupt, SystemExit)):
                raise cleanup_error
            raise TelemetryUnavailableError("tegrastats stdout is unavailable")
        try:
            thread = Thread(
                target=self._read_samples,
                name="oline-hri-tegrastats",
                daemon=True,
            )
            self._thread = thread
            thread.start()
        except BaseException:
            self._stopping.set()
            self._stop_owned_child()
            self._closed = True
            raise
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self._stopping.set()
        cleanup_error = self._stop_owned_child()
        self._cleanup_error = cleanup_error
        self._closed = True

        # Never replace an exception or cancellation raised by the benchmark.
        if exc_type is not None:
            return False
        reader_error = self._reader_error
        if reader_error is not None:
            if isinstance(reader_error, (KeyboardInterrupt, SystemExit)):
                raise reader_error
            if isinstance(reader_error, EvaluationTelemetryError):
                raise reader_error
            raise EvaluationTelemetryError("telemetry consumer failed") from None
        if cleanup_error is not None:
            if isinstance(cleanup_error, (KeyboardInterrupt, SystemExit)):
                raise cleanup_error
            raise TelemetryUnavailableError(
                "tegrastats child cleanup failed"
            ) from None
        return False

    def _read_samples(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            self._set_reader_error(TelemetryStateError("sampler was not started"))
            return
        previous_timestamp: Optional[int] = None
        try:
            while not self._stopping.is_set():
                raw = process.stdout.readline(MAX_TEGRASTATS_LINE_BYTES + 1)
                if raw == b"":
                    if not self._stopping.is_set():
                        raise TelemetryUnavailableError(
                            "tegrastats ended unexpectedly"
                        )
                    return
                if len(raw) > MAX_TEGRASTATS_LINE_BYTES:
                    raise TelemetryParseError("tegrastats line exceeds size limit")
                timestamp = time.monotonic_ns()
                if previous_timestamp is not None and timestamp <= previous_timestamp:
                    raise TelemetryStateError(
                        "telemetry timestamps are not increasing"
                    )
                sample = parse_tegrastats_line(raw, monotonic_ns=timestamp)
                previous_timestamp = timestamp
                with self._lock:
                    if len(self._samples) >= MAX_SAMPLES:
                        raise TelemetryStateError("telemetry sample limit exceeded")
                    self._samples.append(sample)
                record = sample.to_record()
                if self._on_sample is not None:
                    self._on_sample(record)
                elif self._output is not None:
                    self._output.write(_canonical_line(record))
                    flush = getattr(self._output, "flush", None)
                    if callable(flush):
                        flush()
        except BaseException as error:
            self._set_reader_error(error)

    def _set_reader_error(self, error: BaseException) -> None:
        with self._lock:
            if self._reader_error is None:
                self._reader_error = error

    def _stop_owned_child(self) -> Optional[BaseException]:
        process = self._process
        if process is None:
            return None
        errors: list[BaseException] = []
        try:
            if process.poll() is None:
                process.terminate()
        except BaseException as error:
            errors.append(error)
        needs_kill = False
        try:
            process.wait(timeout=_CHILD_STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            needs_kill = True
        except BaseException as error:
            errors.append(error)
            try:
                needs_kill = process.poll() is None
            except BaseException as error:
                errors.append(error)

        if needs_kill:
            try:
                process.kill()
            except BaseException as error:
                errors.append(error)
            else:
                try:
                    process.wait(timeout=_CHILD_STOP_TIMEOUT_SECONDS)
                except BaseException as error:
                    errors.append(error)

        stdout = process.stdout
        if stdout is not None:
            try:
                stdout.close()
            except BaseException as error:
                errors.append(error)
        thread = self._thread
        if thread is not None:
            try:
                thread.join(timeout=_CHILD_STOP_TIMEOUT_SECONDS)
                if thread.is_alive():
                    errors.append(
                        TelemetryUnavailableError(
                            "tegrastats reader thread did not stop"
                        )
                    )
            except BaseException as error:
                errors.append(error)
        return errors[0] if errors else None


def _bounded_ascii_line(value: str | bytes) -> str:
    text = _bounded_ascii_text(value, MAX_TEGRASTATS_LINE_BYTES, "tegrastats line")
    if text.endswith("\r\n"):
        text = text[:-2]
    elif text.endswith("\n"):
        text = text[:-1]
    if not text or any(
        ord(character) < 32 or ord(character) == 127 for character in text
    ):
        raise TelemetryParseError("tegrastats line contains control characters")
    return text


def _bounded_ascii_text(value: str | bytes, maximum: int, label: str) -> str:
    if isinstance(value, bytes):
        raw = value
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError:
            raise TelemetryParseError(f"{label} is not ASCII") from None
    elif isinstance(value, str):
        text = value
        try:
            raw = text.encode("ascii")
        except UnicodeEncodeError:
            raise TelemetryParseError(f"{label} is not ASCII") from None
    else:
        raise TelemetryParseError(f"{label} must be text or bytes")
    if len(raw) > maximum:
        raise TelemetryParseError(f"{label} exceeds size limit")
    if label == "diskstats" and any(
        (ord(character) < 32 and character not in "\t\n\r")
        or ord(character) == 127
        for character in text
    ):
        raise TelemetryParseError("diskstats contains control characters")
    return text


def _single_match(pattern: re.Pattern[str], text: str, label: str) -> re.Match[str]:
    token_count = len(
        re.findall(rf"(?:^|\s){re.escape(label)}(?=\s)", text)
    )
    if token_count != 1:
        state = "missing" if token_count == 0 else "duplicated"
        raise TelemetryParseError(f"{label} field is {state}")
    matches = tuple(pattern.finditer(text))
    if len(matches) != 1:
        state = "missing" if not matches else "duplicated"
        raise TelemetryParseError(f"{label} field is {state}")
    return matches[0]


def _memory_pair(
    text: str, pattern: re.Pattern[str], label: str
) -> tuple[int, int]:
    match = _single_match(pattern, text, label)
    used = _bounded_integer(match.group(1), f"{label} used", maximum=_MAX_MEMORY_MB)
    total = _bounded_integer(
        match.group(2), f"{label} total", maximum=_MAX_MEMORY_MB
    )
    if total == 0 or used > total:
        raise TelemetryParseError(f"{label} values are inconsistent")
    return used, total


def _cpu_core(value: str) -> CpuCoreSample:
    if value == "off":
        return CpuCoreSample(False, None, None)
    match = _CPU_CORE_PATTERN.fullmatch(value)
    if match is None:
        raise TelemetryParseError("CPU core entry is malformed")
    utilization = _bounded_percent(match.group(1), "CPU utilization")
    frequency = _bounded_integer(
        match.group(2), "CPU frequency", maximum=_MAX_FREQUENCY_MHZ
    )
    if frequency == 0:
        raise TelemetryParseError("CPU frequency must be positive")
    return CpuCoreSample(True, utilization, frequency)


def _bounded_percent(value: str, label: str) -> int:
    return _bounded_integer(value, label, maximum=100)


def _bounded_integer(value: object, label: str, *, maximum: int) -> int:
    if (
        not isinstance(value, str)
        or not value
        or not value.isascii()
        or not value.isdigit()
    ):
        raise TelemetryParseError(f"{label} must be an unsigned integer")
    parsed = int(value)
    if parsed > maximum:
        raise TelemetryParseError(f"{label} is outside the supported range")
    return parsed


def _monotonic_timestamp(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= _MAX_COUNTER
    ):
        raise TelemetryParseError("monotonic_ns is outside the supported range")
    return value


def _summary_stats(values: Sequence[float | int]) -> dict[str, float | int]:
    if not values:
        raise TelemetryStateError("cannot summarize an empty metric")
    ordered = sorted(values)
    if any(not isfinite(float(value)) for value in ordered):
        raise TelemetryStateError("metric contains a non-finite value")
    return {
        "max": ordered[-1],
        "p50": _percentile(ordered, 0.50),
        "p95": _percentile(ordered, 0.95),
    }


def _percentile(values: Sequence[float | int], quantile: float) -> float | int:
    index = ceil(quantile * len(values)) - 1
    index = max(0, min(index, len(values) - 1))
    return values[index]


def _strict_sample_timestamps(samples: Sequence[TelemetrySample]) -> None:
    previous: Optional[int] = None
    for sample in samples:
        _validate_sample(sample)
        if previous is not None and sample.monotonic_ns <= previous:
            raise TelemetryStateError("sample timestamps are not increasing")
        previous = sample.monotonic_ns


def _canonical_line(record: dict[str, object]) -> str:
    try:
        encoded = json.dumps(
            record,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, OverflowError):
        raise TelemetryStateError("telemetry record is not JSON-safe") from None
    return f"{encoded}\n"


def _device_name(value: object) -> str:
    if not isinstance(value, str) or _DEVICE_PATTERN.fullmatch(value) is None:
        raise TelemetryParseError("block device name is invalid")
    return value


def _read_bounded_file(path: Path, maximum: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise TelemetryUnavailableError(
            "telemetry source could not be opened"
        ) from None
    chunks = []
    remaining = maximum + 1
    read_error: Optional[BaseException] = None
    try:
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    except BaseException as error:
        read_error = error
    try:
        os.close(descriptor)
    except BaseException as error:
        if read_error is None:
            read_error = error
    if read_error is not None:
        if isinstance(read_error, (KeyboardInterrupt, SystemExit)):
            raise read_error
        if isinstance(read_error, OSError):
            raise TelemetryUnavailableError(
                "telemetry source could not be read"
            ) from None
        raise read_error
    raw = b"".join(chunks)
    if len(raw) > maximum:
        raise TelemetryParseError("telemetry source exceeds size limit")
    return raw


def _counter_delta(before: int, after: int, label: str) -> int:
    if after < before:
        raise TelemetryStateError(f"diskstats counter decreased: {label}")
    return after - before


def _validate_disk_snapshot(value: object) -> None:
    if type(value) is not DiskStatsSnapshot:
        raise TelemetryStateError("diskstats snapshot is invalid")
    try:
        _device_name(value.device)
        _monotonic_timestamp(value.monotonic_ns)
    except TelemetryParseError:
        raise TelemetryStateError("diskstats snapshot is invalid") from None
    required = (
        value.reads_completed,
        value.reads_merged,
        value.sectors_read,
        value.read_time_ms,
        value.writes_completed,
        value.writes_merged,
        value.sectors_written,
        value.write_time_ms,
        value.ios_in_progress,
        value.io_time_ms,
        value.weighted_io_time_ms,
    )
    if any(
        isinstance(counter, bool)
        or not isinstance(counter, int)
        or not 0 <= counter <= _MAX_COUNTER
        for counter in required
    ):
        raise TelemetryStateError("diskstats snapshot is invalid")
    discard = (
        value.discards_completed,
        value.discards_merged,
        value.sectors_discarded,
        value.discard_time_ms,
    )
    flush = (value.flushes_completed, value.flush_time_ms)
    for group in (discard, flush):
        present = tuple(counter is not None for counter in group)
        if any(present) and not all(present):
            raise TelemetryStateError("diskstats optional counter set is incomplete")
        if any(
            counter is not None
            and (
                isinstance(counter, bool)
                or not isinstance(counter, int)
                or not 0 <= counter <= _MAX_COUNTER
            )
            for counter in group
        ):
            raise TelemetryStateError("diskstats snapshot is invalid")


def _validate_sample(value: object) -> None:
    if type(value) is not TelemetrySample:
        raise TelemetryStateError("telemetry sample is invalid")
    try:
        _monotonic_timestamp(value.monotonic_ns)
    except TelemetryParseError:
        raise TelemetryStateError("telemetry sample is invalid") from None

    memory_values = (
        (value.ram_used_mb, value.ram_total_mb),
        (value.swap_used_mb, value.swap_total_mb),
    )
    for used, total in memory_values:
        if (
            isinstance(used, bool)
            or not isinstance(used, int)
            or isinstance(total, bool)
            or not isinstance(total, int)
            or not 0 <= used <= total <= _MAX_MEMORY_MB
            or total == 0
        ):
            raise TelemetryStateError("telemetry sample is invalid")

    if not isinstance(value.cpu_cores, tuple) or not 1 <= len(value.cpu_cores) <= 64:
        raise TelemetryStateError("telemetry sample is invalid")
    online_count = 0
    for core in value.cpu_cores:
        if type(core) is not CpuCoreSample or type(core.online) is not bool:
            raise TelemetryStateError("telemetry sample is invalid")
        if core.online:
            online_count += 1
            if (
                isinstance(core.utilization_percent, bool)
                or not isinstance(core.utilization_percent, int)
                or not 0 <= core.utilization_percent <= 100
                or isinstance(core.frequency_mhz, bool)
                or not isinstance(core.frequency_mhz, int)
                or not 1 <= core.frequency_mhz <= _MAX_FREQUENCY_MHZ
            ):
                raise TelemetryStateError("telemetry sample is invalid")
        elif core.utilization_percent is not None or core.frequency_mhz is not None:
            raise TelemetryStateError("telemetry sample is invalid")
    if online_count == 0:
        raise TelemetryStateError("telemetry sample is invalid")

    if (
        isinstance(value.gr3d_percent, bool)
        or not isinstance(value.gr3d_percent, int)
        or not 0 <= value.gr3d_percent <= 100
    ):
        raise TelemetryStateError("telemetry sample is invalid")
    for power in (value.vdd_in_mw, value.vdd_in_average_mw):
        if (
            isinstance(power, bool)
            or not isinstance(power, int)
            or not 0 <= power <= _MAX_POWER_MW
        ):
            raise TelemetryStateError("telemetry sample is invalid")

    if (
        not isinstance(value.temperatures_c, tuple)
        or not 1 <= len(value.temperatures_c) <= 32
    ):
        raise TelemetryStateError("telemetry sample is invalid")
    names = []
    for item in value.temperatures_c:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TelemetryStateError("telemetry sample is invalid")
        name, temperature = item
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", name) is None
            or isinstance(temperature, bool)
            or not isinstance(temperature, (float, int))
            or not isfinite(float(temperature))
            or not -100.0 <= temperature <= 250.0
        ):
            raise TelemetryStateError("telemetry sample is invalid")
        names.append(name)
    if names != sorted(set(names)):
        raise TelemetryStateError("telemetry sample is invalid")
