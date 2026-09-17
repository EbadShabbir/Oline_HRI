"""Crash-conscious, sequential two-model evaluation for the Jetson target.

The production configuration deliberately pins its Qwen cascade.  This module
keeps that contract unchanged: candidate model names exist only in an in-memory
configuration used by this evaluation runner.

One pair means one router/small-response model and one model used for both
large response routes.  The router is measured on the complete fictional
30-case route matrix.  Response generation is measured separately with fixed
gold routes and fixed required evidence, so routing errors cannot conceal a
capable generator (or vice versa).
"""

from __future__ import annotations

import argparse
import _thread
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from threading import Lock
from time import perf_counter_ns, sleep
from typing import Any, Mapping, Optional, Sequence, TextIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

from .config import AppConfig, load_config
from .conversation import Conversation
from .evaluation import (
    EvaluationCase,
    load_evaluation_suite,
    materialize_memory_store,
)
from .evaluation_experiment import _ExpectedRouter, _FixedRequiredRetriever
from .evaluation_scoring import evaluation_suite_sha256
from .evaluation_telemetry import TegrastatsSampler
from .ollama import ChatResult, OllamaClient
from .routing import ConversationRouter, RouteDecision, RoutingResult


SCHEMA_VERSION = 1
CONTEXT_LENGTH = 2048
MAX_OUTPUT_TOKENS = 128
MODEL_SIZE_LIMIT_BYTES = 1_610_612_736  # 1.5 GiB
PARAMETER_LIMIT = 4_000_000_000
MIN_START_AVAILABLE_KIB = 2_621_440  # 2.5 GiB
MAX_START_SWAP_USED_KIB = 131_072
MAX_START_TEMPERATURE_C = 55.0
MIN_RUNTIME_AVAILABLE_KIB = 786_432
MAX_RUNTIME_SWAP_USED_KIB = 524_288
MAX_RUNTIME_TEMPERATURE_C = 68.0
DEFAULT_SETTLE_SECONDS = 5
OLLAMA_TIMEOUT_SECONDS = 5
OLLAMA_BASE_URL = "http://127.0.0.1:11434"

OBSERVATIONS_NAME = "observations.jsonl"
TELEMETRY_NAME = "telemetry.jsonl"
TELEMETRY_SUMMARY_NAME = "telemetry_summary.json"
SUMMARY_NAME = "summary.json"
MANIFEST_NAME = "manifest.json"
COMPLETE_NAME = "COMPLETE.json"
FAILURE_NAME = "FAILURE.json"

GENERATION_CASE_IDS = (
    "route_small_no_memory_01",
    "memory_relationship",
    "memory_correction",
    "memory_absent",
    "route_large_no_memory_05",
    "memory_large_personal_plan",
    "memory_large_temporal",
    "memory_large_recency",
)

_MODEL_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}:"
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z"
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_THROTTLE_DOMAINS = ("cpu", "gpu", "cv0", "cv1", "cv2", "soc0", "soc1", "soc2")


class ModelPairEvaluationError(RuntimeError):
    """Raised when a pair cannot be evaluated safely or trustworthily."""


class SafetyGateError(ModelPairEvaluationError):
    """Raised when the Jetson start/runtime safety envelope is violated."""


class _CandidateRouter(ConversationRouter):
    """Production-identical routing with an evaluation-only model override.

    ``ConversationRouter`` intentionally rejects non-production model IDs in
    its public constructor.  Inheriting its complete route implementation and
    setting the same two private fields keeps candidate prompts, schemas,
    parsing, temperature, and seed identical without relaxing production.
    """

    def __init__(self, backend: Any, *, model: str) -> None:
        self._backend = backend
        self._model = _model_name(model)


class _RecordingBackend:
    """Record every completed or failed Ollama boundary call."""

    def __init__(self, delegate: OllamaClient) -> None:
        self._delegate = delegate
        self._calls: list[dict[str, object]] = []

    def checkpoint(self) -> int:
        return len(self._calls)

    def calls_since(self, checkpoint: int) -> list[dict[str, object]]:
        return [dict(item) for item in self._calls[checkpoint:]]

    def chat(
        self,
        model: str,
        messages: Sequence[Any],
        *,
        response_format: Optional[Mapping[str, Any]] = None,
        temperature: Optional[float] = None,
        seed: Optional[int] = None,
    ) -> ChatResult:
        purpose = "generation"
        if isinstance(response_format, Mapping):
            properties = response_format.get("properties")
            if isinstance(properties, Mapping):
                if "memory_required" in properties:
                    purpose = "memory_required"
                elif "model_size" in properties:
                    purpose = "model_size"
        started = perf_counter_ns()
        try:
            result = self._delegate.chat(
                model,
                messages,
                response_format=response_format,
                temperature=temperature,
                seed=seed,
            )
        except BaseException as exc:
            self._calls.append(
                {
                    "error_type": type(exc).__name__,
                    "generation": None,
                    "model": model,
                    "purpose": purpose,
                    "status": "error",
                    "wall_ns": perf_counter_ns() - started,
                }
            )
            raise
        self._calls.append(
            {
                "error_type": None,
                "generation": _generation_record(result),
                "model": model,
                "purpose": purpose,
                "status": "ok",
                "wall_ns": perf_counter_ns() - started,
            }
        )
        return result

    def unload_all(self) -> None:
        self._delegate.unload_all()


class _StreamingSafetyMonitor:
    """Persist telemetry, then interrupt inference on a critical sample."""

    def __init__(self, writer: _DurableJsonlWriter) -> None:
        self._writer = writer
        self.violation: Optional[str] = None

    def __call__(self, record: dict[str, object]) -> None:
        self._writer.write(record)
        if self.violation is not None:
            return
        try:
            ram = record["ram"]
            swap = record["swap"]
            temperatures = record["temperatures_c"]
            free_mb = int(ram["total_mb"]) - int(ram["used_mb"])
            swap_used_mb = int(swap["used_mb"])
            maximum_temperature = max(
                float(value) for value in temperatures.values()
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            self.violation = "telemetry sample was malformed"
        else:
            if free_mb < MIN_RUNTIME_AVAILABLE_KIB // 1024:
                self.violation = "telemetry RAM floor crossed"
            elif swap_used_mb > MAX_RUNTIME_SWAP_USED_KIB // 1024:
                self.violation = "telemetry swap ceiling crossed"
            elif maximum_temperature >= MAX_RUNTIME_TEMPERATURE_C:
                self.violation = "telemetry temperature ceiling crossed"
        if self.violation is not None:
            _thread.interrupt_main()


class _DurableJsonlWriter:
    """Write durable records inside one owned mode-0700 directory."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._descriptor: Optional[int] = None
        self._parent_identity: Optional[tuple[int, int]] = None
        self._lock = Lock()

    def __enter__(self) -> "_DurableJsonlWriter":
        try:
            parent = self.path.parent.lstat()
        except OSError:
            raise ModelPairEvaluationError(
                "artifact parent is unavailable"
            ) from None
        if (
            not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) != 0o700
        ):
            raise ModelPairEvaluationError(
                "artifact parent must be an owned mode-0700 directory"
            )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.path, flags, 0o600)
        except FileExistsError:
            raise ModelPairEvaluationError(
                f"artifact already exists: {self.path.name}"
            ) from None
        except OSError:
            raise ModelPairEvaluationError(
                f"artifact could not be created: {self.path.name}"
            ) from None
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            os.close(descriptor)
            raise ModelPairEvaluationError("artifact is not a regular file")
        self._descriptor = descriptor
        self._parent_identity = (parent.st_dev, parent.st_ino)
        _fsync_directory(self.path.parent)
        return self

    def _verify_parent(self) -> None:
        try:
            parent = self.path.parent.lstat()
        except OSError:
            raise ModelPairEvaluationError(
                "artifact parent identity changed"
            ) from None
        if (
            self._parent_identity != (parent.st_dev, parent.st_ino)
            or not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) != 0o700
        ):
            raise ModelPairEvaluationError(
                "artifact parent identity changed"
            )

    def write(self, value: Mapping[str, object]) -> None:
        payload = memoryview(_canonical_bytes(value))
        with self._lock:
            if self._descriptor is None:
                raise ModelPairEvaluationError("artifact writer is closed")
            self._verify_parent()
            try:
                while payload:
                    written = os.write(self._descriptor, payload)
                    if written <= 0:
                        raise OSError("short write")
                    payload = payload[written:]
                os.fsync(self._descriptor)
            except OSError:
                raise ModelPairEvaluationError(
                    "artifact write failed"
                ) from None

    def __exit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> bool:
        with self._lock:
            descriptor = self._descriptor
            self._descriptor = None
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                if exc is None:
                    raise ModelPairEvaluationError(
                        "artifact close failed"
                    ) from None
        return False


def _model_name(value: object) -> str:
    if not isinstance(value, str) or _MODEL_PATTERN.fullmatch(value) is None:
        raise ModelPairEvaluationError("model must be an exact name:tag")
    return value


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise ModelPairEvaluationError(
            "artifact directory could not be opened"
        ) from None
    try:
        os.fsync(descriptor)
    except OSError:
        raise ModelPairEvaluationError(
            "artifact directory could not be synchronized"
        ) from None
    finally:
        os.close(descriptor)


def _canonical_bytes(value: Mapping[str, object]) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        raise ModelPairEvaluationError(
            "artifact could not be encoded"
        ) from None


def _write_new_json(path: Path, value: Mapping[str, object]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        raise ModelPairEvaluationError(
            f"artifact already exists: {path.name}"
        ) from None
    except OSError:
        raise ModelPairEvaluationError(
            f"artifact could not be created: {path.name}"
        ) from None
    try:
        payload = memoryview(_canonical_bytes(value))
        while payload:
            written = os.write(descriptor, payload)
            if written <= 0:
                raise OSError("short write")
            payload = payload[written:]
        os.fsync(descriptor)
    except BaseException:
        try:
            os.close(descriptor)
        finally:
            try:
                path.unlink()
            except OSError:
                pass
        raise
    os.close(descriptor)


def _new_private_directory(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ModelPairEvaluationError("output directory must be absolute")
    try:
        parent = path.parent.resolve(strict=True)
        parent_metadata = parent.stat()
    except (OSError, RuntimeError):
        raise ModelPairEvaluationError(
            "output parent is unavailable"
        ) from None
    if not stat.S_ISDIR(parent_metadata.st_mode):
        raise ModelPairEvaluationError("output parent is not a directory")
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        raise ModelPairEvaluationError(
            "output directory already exists"
        ) from None
    except OSError:
        raise ModelPairEvaluationError(
            "output directory could not be created"
        ) from None
    metadata = path.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or path.parent.resolve(strict=True) != parent
    ):
        raise ModelPairEvaluationError("output directory is not private")
    _fsync_directory(path)
    _fsync_directory(path.parent)
    return path


def _read_text(path: Path, maximum: int = 1_048_576) -> str:
    try:
        with path.open("rb") as stream:
            raw = stream.read(maximum + 1)
    except OSError:
        raise SafetyGateError(f"cannot read {path}") from None
    # A few Tegra thermal zones return ``EAGAIN`` through ``cat`` and ``None``
    # through Python's buffered sysfs read. Treat those sensors as
    # unavailable;
    # callers that can tolerate a partial sensor set already skip this error.
    if raw is None:
        raise SafetyGateError(f"cannot read {path}")
    if len(raw) > maximum:
        raise SafetyGateError(f"safety source is too large: {path}")
    try:
        return raw.decode("ascii").strip()
    except UnicodeDecodeError:
        raise SafetyGateError(f"safety source is not ASCII: {path}") from None


def _memory_snapshot(raw: Optional[str] = None) -> dict[str, int]:
    text = _read_text(Path("/proc/meminfo")) if raw is None else raw
    values: dict[str, int] = {}
    for line in text.splitlines():
        fields = line.split()
        if (
            len(fields) >= 2
            and fields[0].endswith(":")
            and fields[1].isdigit()
        ):
            values[fields[0][:-1]] = int(fields[1])
    required = ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree")
    if any(name not in values for name in required):
        raise SafetyGateError("meminfo is missing required fields")
    if values["SwapFree"] > values["SwapTotal"]:
        raise SafetyGateError("meminfo swap counters are invalid")
    return {
        "mem_total_kib": values["MemTotal"],
        "mem_available_kib": values["MemAvailable"],
        "swap_total_kib": values["SwapTotal"],
        "swap_free_kib": values["SwapFree"],
        "swap_used_kib": values["SwapTotal"] - values["SwapFree"],
    }


def _temperature_snapshot(
    root: Path = Path("/sys/class/thermal"),
) -> dict[str, float]:
    values: dict[str, float] = {}
    try:
        zones = tuple(sorted(root.glob("thermal_zone*")))
    except OSError:
        zones = ()
    for zone in zones:
        try:
            name = _read_text(zone / "type", 128)
            raw = _read_text(zone / "temp", 128)
            milli = int(raw)
        except (SafetyGateError, ValueError):
            continue
        value = milli / 1000.0
        if -40.0 <= value <= 150.0:
            values[name] = value
    if not values:
        raise SafetyGateError("no readable Jetson temperature sensor")
    return dict(sorted(values.items()))


def _throttle_snapshot() -> dict[str, int]:
    result: dict[str, int] = {}
    for domain in _THROTTLE_DOMAINS:
        path = Path(
            f"/sys/devices/platform/{domain}-throttle-alert/"
            "thermal_trip_event"
        )
        try:
            value = int(_read_text(path, 128))
        except (SafetyGateError, ValueError):
            continue
        if value < 0:
            raise SafetyGateError("thermal throttle counter is invalid")
        result[domain] = value
    return result


def _boot_id() -> str:
    value = _read_text(Path("/proc/sys/kernel/random/boot_id"), 128)
    if not re.fullmatch(r"[0-9a-f-]{36}", value):
        raise SafetyGateError("boot ID is invalid")
    return value


def _reset_reason() -> Optional[str]:
    path = Path("/sys/devices/platform/bus@0/c360000.pmc/reset_reason")
    try:
        return _read_text(path, 128)
    except SafetyGateError:
        return None


def _fan_pwm() -> Optional[int]:
    candidates = sorted(Path("/sys/class/hwmon").glob("hwmon*/pwm1"))
    for path in candidates:
        try:
            return int(_read_text(path, 32))
        except (SafetyGateError, ValueError):
            continue
    return None


def _power_mode() -> Optional[str]:
    executable = "/usr/sbin/nvpmodel"
    if not Path(executable).exists():
        executable = "/usr/bin/nvpmodel"
    if not Path(executable).exists():
        return None
    try:
        completed = subprocess.run(
            (executable, "-q"),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=3,
            check=False,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = completed.stdout.strip()
    return output[:512] if output else None


def _http_json(
    endpoint: str,
    *,
    body: Optional[Mapping[str, object]] = None,
    timeout: int = OLLAMA_TIMEOUT_SECONDS,
) -> Mapping[str, object]:
    parsed = urlparse(OLLAMA_BASE_URL)
    if parsed.scheme != "http" or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
    }:
        raise ModelPairEvaluationError("Ollama endpoint must be loopback HTTP")
    data = (
        None
        if body is None
        else json.dumps(body, separators=(",", ":")).encode("utf-8")
    )
    request = Request(
        OLLAMA_BASE_URL + endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if data is None else "POST",
    )
    try:
        with build_opener(ProxyHandler({})).open(
            request, timeout=timeout
        ) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
    except HTTPError as exc:
        raise ModelPairEvaluationError(f"Ollama HTTP {exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise ModelPairEvaluationError("cannot reach local Ollama") from None
    if len(raw) > 4 * 1024 * 1024:
        raise ModelPairEvaluationError("Ollama metadata response is too large")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise ModelPairEvaluationError(
            "Ollama metadata is invalid JSON"
        ) from None
    if not isinstance(value, dict):
        raise ModelPairEvaluationError("Ollama metadata is not an object")
    return value


def _installed_models() -> dict[str, dict[str, object]]:
    payload = _http_json("/api/tags")
    models = payload.get("models")
    if not isinstance(models, list):
        raise ModelPairEvaluationError("Ollama tag listing is malformed")
    result: dict[str, dict[str, object]] = {}
    for item in models:
        if not isinstance(item, dict):
            raise ModelPairEvaluationError("Ollama tag entry is malformed")
        name = item.get("name")
        size = item.get("size")
        digest = item.get("digest")
        if (
            not isinstance(name, str)
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
            or not isinstance(digest, str)
            or _SHA256_PATTERN.fullmatch(digest) is None
        ):
            raise ModelPairEvaluationError("Ollama tag metadata is malformed")
        result[name] = {
            "name": name,
            "size": size,
            "digest": digest,
            "details": item.get("details"),
        }
    return result


def _resident_models() -> tuple[dict[str, object], ...]:
    payload = _http_json("/api/ps")
    models = payload.get("models")
    if not isinstance(models, list) or any(
        not isinstance(item, dict) for item in models
    ):
        raise SafetyGateError("Ollama residency metadata is malformed")
    return tuple(dict(item) for item in models)


def _model_metadata(
    model: str,
    installed: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    try:
        tag = dict(installed[model])
    except KeyError:
        raise ModelPairEvaluationError(
            f"model is not installed: {model}"
        ) from None
    size = tag["size"]
    if not isinstance(size, int) or size > MODEL_SIZE_LIMIT_BYTES:
        raise SafetyGateError(
            f"model exceeds {MODEL_SIZE_LIMIT_BYTES} byte Jetson cap: {model}"
        )
    shown = _http_json("/api/show", body={"model": model, "verbose": False})
    details = shown.get("details")
    info = shown.get("model_info")
    if not isinstance(details, dict) or not isinstance(info, dict):
        raise ModelPairEvaluationError(
            f"model metadata is incomplete: {model}"
        )
    parameter_count = info.get("general.parameter_count")
    if (
        isinstance(parameter_count, bool)
        or not isinstance(parameter_count, int)
        or parameter_count <= 0
        or parameter_count >= PARAMETER_LIMIT
    ):
        raise SafetyGateError(
            f"model is not strictly below 4B parameters: {model}"
        )
    if details.get("format") != "gguf":
        raise SafetyGateError(f"model is not a GGUF artifact: {model}")
    quantization = details.get("quantization_level")
    if not isinstance(quantization, str) or not quantization:
        raise SafetyGateError(f"model quantization is unknown: {model}")
    capabilities = shown.get("capabilities")
    if (
        not isinstance(capabilities, list)
        or "completion" not in capabilities
    ):
        raise SafetyGateError(
            f"model does not advertise chat completion support: {model}"
        )
    tag.update(
        {
            "family": details.get("family"),
            "format": details.get("format"),
            "parameter_count": parameter_count,
            "parameter_size": details.get("parameter_size"),
            "quantization_level": quantization,
            "capabilities": capabilities,
        }
    )
    return tag


def capture_safety_snapshot() -> dict[str, object]:
    temperatures = _temperature_snapshot()
    memory = _memory_snapshot()
    return {
        "boot_id": _boot_id(),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "fan_pwm": _fan_pwm(),
        "memory": memory,
        "power_mode": _power_mode(),
        "reset_reason": _reset_reason(),
        "resident_models": list(_resident_models()),
        "temperatures_c": temperatures,
        "thermal_trip_events": _throttle_snapshot(),
    }


def _require_start_safe(snapshot: Mapping[str, object]) -> None:
    memory = snapshot.get("memory")
    temperatures = snapshot.get("temperatures_c")
    resident = snapshot.get("resident_models")
    fan_pwm = snapshot.get("fan_pwm")
    if not isinstance(memory, dict) or not isinstance(temperatures, dict):
        raise SafetyGateError("start snapshot is incomplete")
    if memory.get("mem_available_kib", 0) < MIN_START_AVAILABLE_KIB:
        raise SafetyGateError(
            "available memory is below the 2.5 GiB start gate"
        )
    if (
        memory.get("swap_used_kib", MAX_START_SWAP_USED_KIB + 1)
        > MAX_START_SWAP_USED_KIB
    ):
        raise SafetyGateError("swap use exceeds the 128 MiB start gate")
    if (
        max(float(value) for value in temperatures.values())
        > MAX_START_TEMPERATURE_C
    ):
        raise SafetyGateError("temperature exceeds the 55 C start gate")
    if not isinstance(resident, list) or resident:
        raise SafetyGateError("an Ollama model is already resident")
    if fan_pwm is not None and (not isinstance(fan_pwm, int) or fan_pwm <= 0):
        raise SafetyGateError("Jetson fan is not running")
    trips = snapshot.get("thermal_trip_events")
    if isinstance(trips, dict) and any(value != 0 for value in trips.values()):
        raise SafetyGateError("a thermal trip counter is nonzero")
    power_mode = snapshot.get("power_mode")
    if not isinstance(power_mode, str) or not re.search(
        r"NV Power Mode:\s*15W\s*\n0\s*\Z",
        power_mode,
    ):
        raise SafetyGateError("Jetson is not in the expected 15W mode 0")


def _require_runtime_safe(
    *, boot_id: str, initial_trip_events: Mapping[str, int]
) -> dict[str, object]:
    memory = _memory_snapshot()
    temperatures = _temperature_snapshot()
    if _boot_id() != boot_id:
        raise SafetyGateError("host boot ID changed during evaluation")
    if memory["mem_available_kib"] < MIN_RUNTIME_AVAILABLE_KIB:
        raise SafetyGateError("available memory crossed the runtime floor")
    if memory["swap_used_kib"] > MAX_RUNTIME_SWAP_USED_KIB:
        raise SafetyGateError("swap use crossed the runtime ceiling")
    if max(temperatures.values()) >= MAX_RUNTIME_TEMPERATURE_C:
        raise SafetyGateError("temperature crossed the runtime ceiling")
    current_trips = _throttle_snapshot()
    for name, initial in initial_trip_events.items():
        if current_trips.get(name) != initial:
            raise SafetyGateError("thermal throttle counter changed")
    residents = _resident_models()
    if len(residents) > 1:
        raise SafetyGateError("more than one Ollama model is resident")
    return {
        "memory": memory,
        "resident_model_count": len(residents),
        "temperatures_c": temperatures,
        "thermal_trip_events": current_trips,
    }


def _settle(seconds: int) -> None:
    if (
        isinstance(seconds, bool)
        or not isinstance(seconds, int)
        or not 0 <= seconds <= 120
    ):
        raise ModelPairEvaluationError(
            "settle seconds must be between 0 and 120"
        )
    for _ in range(seconds):
        sleep(1)


def _generation_record(result: ChatResult) -> dict[str, object]:
    return {
        "citation_annotations_removed": result.citation_annotations_removed,
        "content": result.content,
        "done_reason": result.done_reason,
        "eval_count": result.eval_count,
        "eval_duration_ns": result.eval_duration_ns,
        "generation_tokens_per_second": result.generation_tokens_per_second,
        "load_duration_ns": result.load_duration_ns,
        "model": result.model,
        "prompt_eval_count": result.prompt_eval_count,
        "prompt_eval_duration_ns": result.prompt_eval_duration_ns,
        "total_duration_ns": result.total_duration_ns,
    }


def _has_backend_failure(
    calls: Sequence[Mapping[str, object]],
) -> bool:
    return any(call.get("status") == "error" for call in calls)


def _force_unload(models: Sequence[str]) -> tuple[str, ...]:
    """Best-effort independent unloads followed by an empty-state check."""

    errors: list[str] = []
    for model in dict.fromkeys(models):
        try:
            payload = _http_json(
                "/api/generate",
                body={
                    "keep_alive": 0,
                    "model": model,
                    "prompt": "",
                    "stream": False,
                },
                timeout=30,
            )
            if payload.get("done") is not True:
                errors.append(f"{model}:invalid_unload_response")
        except BaseException as exc:
            errors.append(f"{model}:{type(exc).__name__}")
    try:
        deadline = perf_counter_ns() + 30_000_000_000
        while _resident_models() and perf_counter_ns() < deadline:
            sleep(1)
        if _resident_models():
            errors.append("resident_models_remain")
    except BaseException as exc:
        errors.append(f"residency_check:{type(exc).__name__}")
    return tuple(errors)


def _telemetry_summary(
    telemetry_records: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    ram_values: list[int] = []
    swap_values: list[int] = []
    maximum_temperatures: list[float] = []
    try:
        for item in telemetry_records:
            ram = item["ram"]
            swap = item["swap"]
            temperatures = item["temperatures_c"]
            if (
                not isinstance(ram, Mapping)
                or not isinstance(swap, Mapping)
                or not isinstance(temperatures, Mapping)
                or not temperatures
            ):
                raise TypeError
            ram_values.append(int(ram["used_mb"]))
            swap_values.append(int(swap["used_mb"]))
            maximum_temperatures.append(
                max(float(value) for value in temperatures.values())
            )
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ModelPairEvaluationError(
            "completed telemetry has an invalid record"
        ) from None
    return {
        "max_ram_used_mb": max(ram_values) if ram_values else None,
        "max_swap_used_mb": max(swap_values) if swap_values else None,
        "max_temperature_c": (
            max(maximum_temperatures) if maximum_temperatures else None
        ),
        "record_type": "model_pair_telemetry_summary",
        "sample_count": len(telemetry_records),
        "schema_version": SCHEMA_VERSION,
    }


def _route_record(
    case: EvaluationCase,
    result: Optional[RoutingResult],
    *,
    ordinal: int,
    wall_ns: int,
    error: Optional[BaseException],
    runtime: Mapping[str, object],
    backend_calls: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    expected = {
        "memory_required": case.expected_route.memory_required,
        "model_size": case.expected_route.model_size,
    }
    predicted = None
    memory_generation = None
    size_generation = None
    if isinstance(result, RoutingResult):
        predicted = {
            "memory_required": result.decision.memory_required,
            "model_size": result.decision.model_size,
        }
        memory_generation = _generation_record(
            result.memory_required_generation
        )
        size_generation = _generation_record(result.model_size_generation)
    return {
        "backend_calls": [dict(call) for call in backend_calls],
        "case_id": case.id,
        "error_type": None if error is None else type(error).__name__,
        "expected": expected,
        "joint_correct": predicted == expected,
        "memory_correct": (
            predicted is not None
            and predicted["memory_required"] == expected["memory_required"]
        ),
        "memory_required_generation": memory_generation,
        "model_correct": (
            predicted is not None
            and predicted["model_size"] == expected["model_size"]
        ),
        "model_size_generation": size_generation,
        "ordinal": ordinal,
        "predicted": predicted,
        "decision_sources": (
            {
                "memory_required": result.memory_decision_source,
                "model_size": result.model_size_decision_source,
            } if result is not None else None
        ),
        "record_type": "model_pair_route_case",
        "runtime_after": dict(runtime),
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if error is None else "error",
        "wall_ns": wall_ns,
    }


def _answer_record(
    case: EvaluationCase,
    reply: Optional[Any],
    *,
    ordinal: int,
    wall_ns: int,
    error: Optional[BaseException],
    runtime: Mapping[str, object],
    backend_calls: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    if reply is None:
        response = generation = diagnostics = selected_model = None
        fallback_from_model = None
    else:
        response = reply.response.to_dict()
        generation = _generation_record(reply.generation)
        diagnostics = reply.memory_diagnostics.to_dict()
        selected_model = reply.generation.model
        fallback_from_model = reply.fallback_from_model
    return {
        "backend_calls": [dict(call) for call in backend_calls],
        "case_id": case.id,
        "error_type": None if error is None else type(error).__name__,
        "expected_model_size": case.expected_route.model_size,
        "expected_required_citation_ids": list(
            case.answer_rubric.required_citation_ids
        ),
        "fallback_from_model": fallback_from_model,
        "generation": generation,
        "memory_diagnostics": diagnostics,
        "ordinal": ordinal,
        "record_type": "model_pair_answer_case",
        "response": response,
        "runtime_after": dict(runtime),
        "schema_version": SCHEMA_VERSION,
        "selected_model": selected_model,
        "status": "ok" if error is None else "error",
        "wall_ns": wall_ns,
    }


def _distribution(values: Sequence[int | float]) -> dict[str, Optional[float]]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return {
            "count": 0,
            "max": None,
            "mean": None,
            "median": None,
            "min": None,
        }
    middle = len(ordered) // 2
    median = (
        ordered[middle]
        if len(ordered) % 2
        else (ordered[middle - 1] + ordered[middle]) / 2.0
    )
    return {
        "count": len(ordered),
        "max": ordered[-1],
        "mean": sum(ordered) / len(ordered),
        "median": median,
        "min": ordered[0],
    }


def summarize_records(
    records: Sequence[Mapping[str, object]],
    *,
    router_model: str,
    generator_model: str,
) -> dict[str, object]:
    routes = [
        record
        for record in records
        if record.get("record_type") == "model_pair_route_case"
    ]
    answers = [
        record
        for record in records
        if record.get("record_type") == "model_pair_answer_case"
    ]
    successful_answers = [
        record for record in answers if record.get("status") == "ok"
    ]
    citation_exact = 0
    small_success = 0
    large_success = 0
    rates: list[float] = []
    for record in successful_answers:
        diagnostics = record.get("memory_diagnostics")
        expected = record.get("expected_required_citation_ids")
        if (
            isinstance(diagnostics, dict)
            and diagnostics.get("model_used_ids") == expected
        ):
            citation_exact += 1
        if record.get("expected_model_size") == "small":
            small_success += 1
        else:
            large_success += 1
        generation = record.get("generation")
        if isinstance(generation, dict):
            rate = generation.get("generation_tokens_per_second")
            if isinstance(rate, (int, float)) and not isinstance(rate, bool):
                rates.append(float(rate))
    return {
        "answer_screen": {
            "attempted": len(answers),
            "citation_exact": citation_exact,
            "large_success": large_success,
            "semantic_review_status": "pending_rubric_review",
            "small_success": small_success,
            "structured_success": len(successful_answers),
            "tokens_per_second": _distribution(rates),
            "wall_seconds": _distribution(
                [int(record["wall_ns"]) / 1e9 for record in answers]
            ),
        },
        "all_cases_attempted": (
            len(routes) == 30
            and len(answers) == len(GENERATION_CASE_IDS)
        ),
        "all_cases_succeeded": (
            len(routes) == 30
            and len(answers) == len(GENERATION_CASE_IDS)
            and all(record.get("status") == "ok" for record in routes)
            and all(record.get("status") == "ok" for record in answers)
        ),
        "execution_completed": True,
        "models": {"generator": generator_model, "router_small": router_model},
        "record_type": "model_pair_summary",
        "router": {
            "attempted": len(routes),
            "joint_correct": sum(
                record.get("joint_correct") is True for record in routes
            ),
            "memory_correct": sum(
                record.get("memory_correct") is True for record in routes
            ),
            "model_size_correct": sum(
                record.get("model_correct") is True for record in routes
            ),
            "successful": sum(
                record.get("status") == "ok" for record in routes
            ),
            "wall_seconds": _distribution(
                [int(record["wall_ns"]) / 1e9 for record in routes]
            ),
        },
        "schema_version": SCHEMA_VERSION,
    }


def _configured_pair(
    base: AppConfig,
    router_model: str,
    generator_model: str,
) -> AppConfig:
    return replace(
        base,
        ollama=replace(
            base.ollama,
            base_url=OLLAMA_BASE_URL,
            small_model=router_model,
            general_large_model=generator_model,
            large_model=generator_model,
            request_timeout_seconds=120,
            large_request_timeout_seconds=120,
            unload_timeout_seconds=30,
        ),
        generation=replace(
            base.generation,
            context_length=CONTEXT_LENGTH,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            temperature=0.0,
            thinking=False,
        ),
    )


def run_model_pair_evaluation(
    router_model: str,
    generator_model: str,
    output_dir: str | Path,
    *,
    settle_seconds: int = DEFAULT_SETTLE_SECONDS,
    progress: Optional[TextIO] = None,
) -> Path:
    """Run one pair and return its private, completed result directory."""

    router = _model_name(router_model)
    generator = _model_name(generator_model)
    if router == generator:
        raise ModelPairEvaluationError(
            "router and generator models must differ"
        )
    _settle(settle_seconds)
    installed = _installed_models()
    models = {
        "router_small": _model_metadata(router, installed),
        "generator": _model_metadata(generator, installed),
    }
    start_snapshot = capture_safety_snapshot()
    _require_start_safe(start_snapshot)
    boot_id = str(start_snapshot["boot_id"])
    initial_trips = start_snapshot.get("thermal_trip_events")
    if not isinstance(initial_trips, dict):
        initial_trips = {}

    suite = load_evaluation_suite()
    route_cases = tuple(case for case in suite.cases if "router" in case.tags)
    if len(route_cases) != 30:
        raise ModelPairEvaluationError("expected exactly 30 router cases")
    by_id = {case.id: case for case in suite.cases}
    try:
        answer_cases = tuple(by_id[case_id] for case_id in GENERATION_CASE_IDS)
    except KeyError:
        raise ModelPairEvaluationError(
            "answer screen case is absent"
        ) from None

    directory = _new_private_directory(output_dir)
    run_id = uuid4().hex
    observations_path = directory / OBSERVATIONS_NAME
    telemetry_path = directory / TELEMETRY_NAME
    records: list[dict[str, object]] = []
    base_config = load_config()
    config = _configured_pair(base_config, router, generator)
    raw_backend = OllamaClient(config.ollama, config.generation)
    backend = _RecordingBackend(raw_backend)
    header = {
        "configuration": {
            "context_length": CONTEXT_LENGTH,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "seed": 42,
            "temperature": 0.0,
            "thinking": False,
        },
        "generation_case_ids": list(GENERATION_CASE_IDS),
        "models": models,
        "record_type": "model_pair_header",
        "run_id": run_id,
        "safety_limits": {
            "max_model_bytes": MODEL_SIZE_LIMIT_BYTES,
            "max_parameters_exclusive": PARAMETER_LIMIT,
            "max_runtime_swap_used_kib": MAX_RUNTIME_SWAP_USED_KIB,
            "max_runtime_temperature_c": MAX_RUNTIME_TEMPERATURE_C,
            "min_runtime_available_kib": MIN_RUNTIME_AVAILABLE_KIB,
            "min_start_available_kib": MIN_START_AVAILABLE_KIB,
        },
        "schema_version": SCHEMA_VERSION,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "start_snapshot": start_snapshot,
        "suite_id": suite.suite_id,
        "suite_sha256": evaluation_suite_sha256(suite),
    }

    completed = False
    failure: Optional[BaseException] = None
    monitor: Optional[_StreamingSafetyMonitor] = None
    try:
        with _DurableJsonlWriter(
            observations_path
        ) as observations, _DurableJsonlWriter(
            telemetry_path
        ) as telemetry:
            observations.write(header)
            monitor = _StreamingSafetyMonitor(telemetry)
            with TegrastatsSampler(
                interval_ms=1000,
                on_sample=monitor,
            ):
                backend.unload_all()
                candidate_router = _CandidateRouter(backend, model=router)
                for ordinal, case in enumerate(route_cases, start=1):
                    _require_runtime_safe(
                        boot_id=boot_id,
                        initial_trip_events=initial_trips,
                    )
                    started = perf_counter_ns()
                    checkpoint = backend.checkpoint()
                    result: Optional[RoutingResult] = None
                    error: Optional[BaseException] = None
                    try:
                        result = candidate_router.route(case.prompt)
                    except Exception as exc:
                        error = exc
                    wall_ns = perf_counter_ns() - started
                    runtime = _require_runtime_safe(
                        boot_id=boot_id,
                        initial_trip_events=initial_trips,
                    )
                    backend_calls = backend.calls_since(checkpoint)
                    record = _route_record(
                        case,
                        result,
                        ordinal=ordinal,
                        wall_ns=wall_ns,
                        error=error,
                        runtime=runtime,
                        backend_calls=backend_calls,
                    )
                    records.append(record)
                    observations.write(record)
                    if progress is not None:
                        print(
                            f"route {ordinal}/{len(route_cases)} "
                            f"{case.id}: {record['status']}",
                            file=progress,
                            flush=True,
                        )
                    if _has_backend_failure(backend_calls):
                        raise ModelPairEvaluationError(
                            "Ollama transport failed during router evaluation"
                        )

                backend.unload_all()
                _require_runtime_safe(
                    boot_id=boot_id,
                    initial_trip_events=initial_trips,
                )
                # The production replay validator rejects this repository's
                # group-writable development ancestors. A system temporary
                # directory is mode 0700 beneath the sticky /tmp boundary and
                # satisfies the same anti-symlink/ownership checks.
                with tempfile.TemporaryDirectory(
                    prefix="oline-hri-model-pair-memory-",
                ) as temporary:
                    store = materialize_memory_store(
                        suite,
                        Path(temporary) / "memory.sqlite3",
                    )
                    items = {
                        item.id: item
                        for item in store.list_memories(
                            include_inactive=True
                        )
                    }
                    for ordinal, case in enumerate(answer_cases, start=1):
                        _require_runtime_safe(
                            boot_id=boot_id,
                            initial_trip_events=initial_trips,
                        )
                        expected = RouteDecision(
                            case.expected_route.memory_required,
                            case.expected_route.model_size,
                        )
                        conversation = Conversation(
                            backend,
                            system_prompt=config.conversation.system_prompt,
                            router=_ExpectedRouter(expected, model=router),
                            retriever=_FixedRequiredRetriever(
                                store,
                                case,
                                items,
                            ),
                            small_model=router,
                            general_large_model=generator,
                            large_model=generator,
                            context_length=CONTEXT_LENGTH,
                            max_output_tokens=MAX_OUTPUT_TOKENS,
                        )
                        started = perf_counter_ns()
                        checkpoint = backend.checkpoint()
                        reply = None
                        error = None
                        try:
                            reply = conversation.send(case.prompt)
                        except Exception as exc:
                            error = exc
                        wall_ns = perf_counter_ns() - started
                        runtime = _require_runtime_safe(
                            boot_id=boot_id,
                            initial_trip_events=initial_trips,
                        )
                        backend_calls = backend.calls_since(checkpoint)
                        record = _answer_record(
                            case,
                            reply,
                            ordinal=ordinal,
                            wall_ns=wall_ns,
                            error=error,
                            runtime=runtime,
                            backend_calls=backend_calls,
                        )
                        records.append(record)
                        observations.write(record)
                        if progress is not None:
                            print(
                                f"answer {ordinal}/{len(answer_cases)} "
                                f"{case.id}: {record['status']}",
                                file=progress,
                                flush=True,
                            )
                        if _has_backend_failure(backend_calls):
                            raise ModelPairEvaluationError(
                                "Ollama transport failed during answer screen"
                            )

                backend.unload_all()
                if _resident_models():
                    raise SafetyGateError(
                        "Ollama model remained resident after unload"
                    )
                end_snapshot = capture_safety_snapshot()
                observations.write(
                    {
                        "completed": True,
                        "end_snapshot": end_snapshot,
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                        "record_type": "model_pair_trailer",
                        "run_id": run_id,
                        "schema_version": SCHEMA_VERSION,
                    }
                )
            if monitor.violation is not None:
                raise SafetyGateError(monitor.violation)
            completed = True
    except BaseException as exc:
        failure = exc
    finally:
        cleanup_errors: list[str] = []
        try:
            backend.unload_all()
        except BaseException as exc:
            cleanup_errors.append(f"normal_unload:{type(exc).__name__}")
        if failure is not None or cleanup_errors:
            cleanup_errors.extend(_force_unload((router, generator)))
        else:
            try:
                if _resident_models():
                    cleanup_errors.extend(_force_unload((router, generator)))
            except BaseException as exc:
                cleanup_errors.append(
                    f"residency_check:{type(exc).__name__}"
                )
        if cleanup_errors and failure is None:
            failure = SafetyGateError("final model cleanup failed")

    if not completed or failure is not None:
        primary = failure or ModelPairEvaluationError(
            "model-pair evaluation did not complete"
        )
        try:
            _write_new_json(
                directory / FAILURE_NAME,
                {
                    "cleanup_errors": cleanup_errors,
                    "error": str(primary)[:500],
                    "error_type": type(primary).__name__,
                    "record_type": "model_pair_failure",
                    "run_id": run_id,
                    "schema_version": SCHEMA_VERSION,
                },
            )
            _fsync_directory(directory)
        except BaseException:
            pass
        detail = type(primary).__name__
        if monitor is not None and monitor.violation is not None:
            detail = monitor.violation
        if cleanup_errors:
            detail += "; cleanup=" + ",".join(cleanup_errors)
        raise ModelPairEvaluationError(
            f"model-pair evaluation stopped: {detail}"
        ) from None

    # The telemetry stream is already durable. Derived files are published only
    # after every expected observation and the final empty-residency check.
    telemetry_records = []
    try:
        for line in telemetry_path.read_text(encoding="utf-8").splitlines():
            telemetry_records.append(json.loads(line))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        raise ModelPairEvaluationError(
            "completed telemetry could not be read"
        ) from None
    telemetry_summary = _telemetry_summary(telemetry_records)
    summary = summarize_records(
        records,
        router_model=router,
        generator_model=generator,
    )
    summary = {**summary, "run_id": run_id, "telemetry": telemetry_summary}
    _write_new_json(directory / TELEMETRY_SUMMARY_NAME, telemetry_summary)
    _write_new_json(directory / SUMMARY_NAME, summary)
    artifact_names = (
        OBSERVATIONS_NAME,
        TELEMETRY_NAME,
        TELEMETRY_SUMMARY_NAME,
        SUMMARY_NAME,
    )
    manifest = {
        "artifacts_sha256": {
            name: sha256((directory / name).read_bytes()).hexdigest()
            for name in artifact_names
        },
        "record_type": "model_pair_manifest",
        "run_id": run_id,
        "schema_version": SCHEMA_VERSION,
    }
    _write_new_json(directory / MANIFEST_NAME, manifest)
    _write_new_json(
        directory / COMPLETE_NAME,
        {
            "completed": True,
            "manifest_sha256": sha256(
                (directory / MANIFEST_NAME).read_bytes()
            ).hexdigest(),
            "record_type": "model_pair_complete",
            "run_id": run_id,
            "schema_version": SCHEMA_VERSION,
        },
    )
    descriptor = os.open(
        directory,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return directory


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one sequential Jetson model-pair evaluation"
    )
    parser.add_argument(
        "--router",
        required=True,
        help="exact router/small model name:tag",
    )
    parser.add_argument(
        "--generator",
        required=True,
        help="exact large-generator model name:tag",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="new absolute result directory",
    )
    parser.add_argument(
        "--settle-seconds",
        type=int,
        default=DEFAULT_SETTLE_SECONDS,
    )
    args = parser.parse_args(argv)
    try:
        result = run_model_pair_evaluation(
            args.router,
            args.generator,
            args.output,
            settle_seconds=args.settle_seconds,
            progress=(
                None
                if os.environ.get("OLINE_HRI_QUIET") == "1"
                else sys.stderr
            ),
        )
    except ModelPairEvaluationError as exc:
        print(f"model-pair evaluation error: {exc}", file=sys.stderr)
        return 2
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
