"""Thin, fail-closed orchestration for the Step 16 Jetson benchmark.

Raw observations are written incrementally by :mod:`evaluation_runner`.  All
derived artifacts are assembled in memory and published only after that run
returns successfully.  Progress output never contains prompts or answers.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import importlib.metadata
from ipaddress import ip_address
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
import time
from typing import Mapping, Optional, Sequence, TextIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener

from .config import AppConfig, ConfigError, load_config
from .evaluation import EvaluationError, EvaluationSuite, load_evaluation_suite
from .embedding import MODEL_ID, MODEL_REVISION, REQUIRED_ASSET_SHA256
from .evaluation_runner import (
    CASCADE_STRATEGIES,
    EvaluationRunError,
    run_evaluation,
)
from .evaluation_scoring import (
    EvaluationScoringError,
    canonical_summary_json,
    emit_blinded_review_sheet,
    load_observation_jsonl,
    render_summary_markdown,
    score_observations,
)
from .evaluation_telemetry import (
    EvaluationTelemetryError,
    TegrastatsSampler,
    capture_runtime_baseline,
    diskstats_delta,
    read_diskstats,
    samples_jsonl,
)


OBSERVATIONS_NAME = "observations.jsonl"
TELEMETRY_NAME = "telemetry.jsonl"
TELEMETRY_SUMMARY_NAME = "telemetry_summary.json"
ENVIRONMENT_NAME = "environment.json"
SUMMARY_NAME = "summary.json"
REPORT_NAME = "report.md"
ANSWER_REVIEW_NAME = "answer_review.jsonl"
ARTIFACT_NAMES = (
    OBSERVATIONS_NAME,
    TELEMETRY_NAME,
    TELEMETRY_SUMMARY_NAME,
    ENVIRONMENT_NAME,
    SUMMARY_NAME,
    REPORT_NAME,
    ANSWER_REVIEW_NAME,
)
DERIVED_ARTIFACT_NAMES = ARTIFACT_NAMES[1:]
BENCHMARK_SCHEMA_VERSION = 1
MAX_DERIVED_ARTIFACT_BYTES = 128 * 1024 * 1024
MAX_ENVIRONMENT_FILE_BYTES = 2 * 1024 * 1024
MAX_EMBEDDING_ASSET_BYTES = 512 * 1024 * 1024
MAX_COMMAND_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_OLLAMA_METADATA_BYTES = 1024 * 1024
ENVIRONMENT_TIMEOUT_SECONDS = 3.0

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ALLOWLIST = (
    "src/oline_hri/config.py",
    "src/oline_hri/conversation.py",
    "src/oline_hri/embedding.py",
    "src/oline_hri/evaluation.py",
    "src/oline_hri/evaluation_runner.py",
    "src/oline_hri/evaluation_scoring.py",
    "src/oline_hri/evaluation_telemetry.py",
    "src/oline_hri/evaluation_benchmark.py",
    "src/oline_hri/memory.py",
    "src/oline_hri/ollama.py",
    "src/oline_hri/relationships.py",
    "src/oline_hri/response.py",
    "src/oline_hri/retrieval.py",
    "src/oline_hri/routing.py",
    "config/default.json",
    "evaluation/fictional_seven_day_v1.json",
)
_PYTHON_DEPENDENCIES = ("oline-hri", "numpy", "onnxruntime", "tokenizers")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_OLLAMA_DIGEST_PATTERN = re.compile(r"(?:sha256:)?[0-9a-f]{64}\Z")

_DEVICE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_THROTTLE_DOMAINS = ("cpu", "gpu", "cv0", "cv1", "cv2", "soc0", "soc1", "soc2")
_MAX_THROTTLE_COUNTER = (1 << 64) - 1
_MAX_SYSFS_VALUE_BYTES = 128


class EvaluationBenchmarkError(RuntimeError):
    """Raised when a benchmark cannot publish trustworthy artifacts."""


@dataclass(frozen=True)
class BenchmarkResult:
    """Paths and bounded counters returned by one completed benchmark."""

    run_id: str
    observations_path: Path
    telemetry_path: Path
    telemetry_summary_path: Path
    environment_path: Path
    summary_path: Path
    report_path: Path
    answer_review_path: Path
    telemetry_samples: int
    retrieval_errors: int
    cascade_errors: int


@dataclass(frozen=True)
class _CreatedFile:
    name: str
    device: int
    inode: int


@dataclass(frozen=True)
class _ThrottleSnapshot:
    monotonic_ns: int
    counters: tuple[tuple[str, int], ...]
    unavailable: tuple[str, ...]


class _PrivateOutputDirectory:
    """Hold and revalidate one private directory throughout a benchmark."""

    def __init__(self, value: str | Path) -> None:
        self.path = _output_directory_path(value)
        self._descriptor: Optional[int] = None
        self._device: Optional[int] = None
        self._inode: Optional[int] = None

    @property
    def descriptor(self) -> int:
        if self._descriptor is None:
            raise EvaluationBenchmarkError("benchmark output directory is not open")
        return self._descriptor

    def artifact(self, name: str) -> Path:
        if name not in ARTIFACT_NAMES:
            raise EvaluationBenchmarkError("benchmark artifact name is invalid")
        return self.path / name

    def __enter__(self) -> "_PrivateOutputDirectory":
        metadata = _validate_output_directory(self.path)
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.path, flags)
        except OSError:
            raise EvaluationBenchmarkError(
                "benchmark output directory could not be opened"
            ) from None
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or opened.st_dev != metadata.st_dev
                or opened.st_ino != metadata.st_ino
                or opened.st_uid != os.geteuid()
                or stat.S_IMODE(opened.st_mode) != 0o700
            ):
                raise EvaluationBenchmarkError(
                    "benchmark output directory identity changed"
                )
        except BaseException:
            try:
                os.close(descriptor)
            except BaseException:
                pass
            raise
        self._descriptor = descriptor
        self._device = opened.st_dev
        self._inode = opened.st_ino
        try:
            self.verify()
            self.require_all_absent()
        except BaseException:
            self._descriptor = None
            try:
                os.close(descriptor)
            except BaseException:
                pass
            raise
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        descriptor = self._descriptor
        self._descriptor = None
        if descriptor is not None:
            try:
                os.close(descriptor)
            except BaseException as close_error:
                if exc_type is not None:
                    return False
                if isinstance(close_error, (KeyboardInterrupt, SystemExit)):
                    raise
                raise EvaluationBenchmarkError(
                    "benchmark output directory close failed"
                ) from None
        return False

    def verify(self) -> None:
        descriptor = self.descriptor
        try:
            opened = os.fstat(descriptor)
            current = os.lstat(self.path)
        except OSError:
            raise EvaluationBenchmarkError(
                "benchmark output directory could not be revalidated"
            ) from None
        if (
            not stat.S_ISDIR(opened.st_mode)
            or not stat.S_ISDIR(current.st_mode)
            or opened.st_dev != self._device
            or opened.st_ino != self._inode
            or current.st_dev != self._device
            or current.st_ino != self._inode
            or opened.st_uid != os.geteuid()
            or current.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) != 0o700
            or stat.S_IMODE(current.st_mode) != 0o700
        ):
            raise EvaluationBenchmarkError(
                "benchmark output directory identity changed"
            )

    def require_all_absent(self) -> None:
        for name in ARTIFACT_NAMES:
            try:
                os.stat(name, dir_fd=self.descriptor, follow_symlinks=False)
            except FileNotFoundError:
                continue
            except OSError:
                raise EvaluationBenchmarkError(
                    "benchmark artifact path could not be inspected"
                ) from None
            raise EvaluationBenchmarkError("benchmark artifact already exists")

    def verify_observations(self) -> None:
        self.verify()
        try:
            relative = os.stat(
                OBSERVATIONS_NAME,
                dir_fd=self.descriptor,
                follow_symlinks=False,
            )
            absolute = os.lstat(self.artifact(OBSERVATIONS_NAME))
        except OSError:
            raise EvaluationBenchmarkError(
                "benchmark observations could not be verified"
            ) from None
        if (
            not stat.S_ISREG(relative.st_mode)
            or not stat.S_ISREG(absolute.st_mode)
            or relative.st_dev != absolute.st_dev
            or relative.st_ino != absolute.st_ino
            or relative.st_uid != os.geteuid()
            or stat.S_IMODE(relative.st_mode) != 0o600
        ):
            raise EvaluationBenchmarkError(
                "benchmark observations are not a private regular file"
            )

    def publish(self, artifacts: Mapping[str, bytes]) -> None:
        if tuple(artifacts) != DERIVED_ARTIFACT_NAMES:
            raise EvaluationBenchmarkError("derived artifact set is invalid")
        self.verify()
        created: list[_CreatedFile] = []
        try:
            for name, payload in artifacts.items():
                created.append(self._create(name, payload))
            os.fsync(self.descriptor)
            self.verify()
        except BaseException as error:
            try:
                cleanup_complete = self._cleanup(created)
            except BaseException as cleanup_error:
                if not isinstance(error, Exception):
                    raise error
                raise cleanup_error
            if not isinstance(error, Exception):
                raise
            if not cleanup_complete:
                raise EvaluationBenchmarkError(
                    "derived artifact publication failed and cleanup was incomplete"
                ) from None
            if isinstance(error, EvaluationBenchmarkError):
                raise
            raise EvaluationBenchmarkError(
                "derived artifact publication failed"
            ) from None

    def _create(self, name: str, payload: bytes) -> _CreatedFile:
        if name not in DERIVED_ARTIFACT_NAMES:
            raise EvaluationBenchmarkError("derived artifact name is invalid")
        if not isinstance(payload, bytes) or len(payload) > MAX_DERIVED_ARTIFACT_BYTES:
            raise EvaluationBenchmarkError("derived artifact payload is invalid")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(name, flags, 0o600, dir_fd=self.descriptor)
        except FileExistsError:
            raise EvaluationBenchmarkError(
                "benchmark artifact already exists"
            ) from None
        except OSError:
            raise EvaluationBenchmarkError(
                "derived artifact could not be created"
            ) from None

        identity: Optional[_CreatedFile] = None
        failure: Optional[BaseException] = None
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise OSError("artifact is not regular")
            identity = _CreatedFile(name, metadata.st_dev, metadata.st_ino)
            os.fchmod(descriptor, 0o600)
            remaining = memoryview(payload)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise OSError("short artifact write")
                remaining = remaining[written:]
            os.fsync(descriptor)
        except BaseException as error:
            failure = error
        try:
            os.close(descriptor)
        except BaseException as error:
            if failure is None:
                failure = error

        if failure is not None:
            try:
                cleanup_complete = (
                    False if identity is None else self._unlink_if_owned(identity)
                )
            except BaseException as cleanup_error:
                if not isinstance(failure, Exception):
                    raise failure
                raise cleanup_error
            if not isinstance(failure, Exception):
                raise failure
            if not cleanup_complete:
                raise EvaluationBenchmarkError(
                    "derived artifact write failed and cleanup was incomplete"
                ) from None
            raise EvaluationBenchmarkError("derived artifact write failed") from None

        assert identity is not None
        if not self._matches(identity):
            try:
                cleanup_complete = self._unlink_if_owned(identity)
            except BaseException:
                raise
            if not cleanup_complete:
                raise EvaluationBenchmarkError(
                    "derived artifact identity changed and cleanup was incomplete"
                ) from None
            raise EvaluationBenchmarkError(
                "derived artifact identity changed"
            ) from None
        return identity

    def _cleanup(self, created: Sequence[_CreatedFile]) -> bool:
        complete = True
        cancellation: Optional[BaseException] = None
        for identity in reversed(created):
            try:
                if not self._unlink_if_owned(identity):
                    complete = False
            except (KeyboardInterrupt, SystemExit) as error:
                if cancellation is None:
                    cancellation = error
                complete = False
            except Exception:
                complete = False
        try:
            os.fsync(self.descriptor)
        except (KeyboardInterrupt, SystemExit) as error:
            if cancellation is None:
                cancellation = error
            complete = False
        except Exception:
            complete = False
        if cancellation is not None:
            raise cancellation
        return complete

    def _matches(self, identity: _CreatedFile) -> bool:
        metadata = self._metadata_if_same_identity(identity)
        return bool(
            metadata is not None
            and metadata.st_uid == os.geteuid()
            and stat.S_IMODE(metadata.st_mode) == 0o600
        )

    def _metadata_if_same_identity(
        self, identity: _CreatedFile
    ) -> Optional[os.stat_result]:
        try:
            metadata = os.stat(
                identity.name,
                dir_fd=self.descriptor,
                follow_symlinks=False,
            )
        except OSError:
            return None
        if not (
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_dev == identity.device
            and metadata.st_ino == identity.inode
        ):
            return None
        return metadata

    def _unlink_if_owned(self, identity: _CreatedFile) -> bool:
        if self._metadata_if_same_identity(identity) is None:
            return False
        try:
            os.unlink(identity.name, dir_fd=self.descriptor)
        except OSError:
            return False
        return True


def run_benchmark(
    suite: EvaluationSuite,
    config: AppConfig,
    output_dir: str | Path,
    *,
    block_device: str,
    strategies: Sequence[str] = CASCADE_STRATEGIES,
    repetitions: int = 1,
    telemetry_interval_ms: int = 500,
    progress: Optional[TextIO] = None,
) -> BenchmarkResult:
    """Run, score, and securely publish one local Step 16 benchmark."""

    device = _block_device(block_device)
    selected_strategies = _strategies(strategies)
    with _PrivateOutputDirectory(output_dir) as destination:
        # Environment hashing and metadata queries deliberately precede all
        # measurement baselines so they do not inflate the benchmark deltas.
        environment_snapshot = _capture_environment(config, device)
        before_runtime = capture_runtime_baseline()
        before_disk = read_diskstats(device)
        before_throttle = _capture_throttle_snapshot()
        observations_path = destination.artifact(OBSERVATIONS_NAME)
        sampler = TegrastatsSampler(interval_ms=telemetry_interval_ms)
        run_summary = run_evaluation(
            suite,
            config,
            observations_path,
            strategies=selected_strategies,
            repetitions=repetitions,
            clock_ns=time.monotonic_ns,
            progress=progress,
            telemetry=sampler,
        )

        destination.verify_observations()
        after_throttle = _capture_throttle_snapshot()
        after_disk = read_diskstats(device)
        after_runtime = capture_runtime_baseline()
        disk_delta = diskstats_delta(before_disk, after_disk)
        telemetry_samples = sampler.samples
        tegrastats_summary = sampler.summary()
        if (
            not isinstance(tegrastats_summary, Mapping)
            or tegrastats_summary.get("sample_count") != len(telemetry_samples)
        ):
            raise EvaluationBenchmarkError("telemetry summary is inconsistent")
        telemetry_summary = {
            "block_device": device,
            "diskstats": disk_delta.to_record(),
            "record_type": "benchmark_telemetry_summary",
            "runtime_after": after_runtime,
            "runtime_before": before_runtime,
            "schema_version": BENCHMARK_SCHEMA_VERSION,
            "tegrastats": tegrastats_summary,
            "measurement_scope": {
                "diskstats": (
                    "brackets_run_evaluation_call_with_snapshot_and_"
                    "observation_verification_overhead"
                ),
                "energy": "first_to_last_tegrastats_sample_across_whole_run",
                "per_case_or_strategy_energy": "not_reported",
                "runtime_baselines": (
                    "bracket_disk_throttle_and_run_measurement_operations"
                ),
                "tegrastats": "runner_setup_retrieval_and_cascade_context",
                "throttling": (
                    "brackets_run_evaluation_call_and_observation_verification"
                ),
            },
            "throttling": _throttle_delta(before_throttle, after_throttle),
        }

        observations = load_observation_jsonl(observations_path)
        environment = _bind_environment(
            environment_snapshot,
            observations.header,
            run_summary.run_id,
        )
        objective_summary = score_observations(suite, observations)
        artifacts = {
            TELEMETRY_NAME: samples_jsonl(telemetry_samples).encode("utf-8"),
            TELEMETRY_SUMMARY_NAME: _canonical_json(telemetry_summary),
            ENVIRONMENT_NAME: _canonical_json(environment),
            SUMMARY_NAME: canonical_summary_json(objective_summary).encode("utf-8"),
            REPORT_NAME: _benchmark_report(
                render_summary_markdown(objective_summary),
                telemetry_summary,
            ).encode("utf-8"),
            ANSWER_REVIEW_NAME: emit_blinded_review_sheet(
                suite, observations
            ).encode("utf-8"),
        }
        destination.publish(artifacts)

        return BenchmarkResult(
            run_id=run_summary.run_id,
            observations_path=observations_path,
            telemetry_path=destination.artifact(TELEMETRY_NAME),
            telemetry_summary_path=destination.artifact(TELEMETRY_SUMMARY_NAME),
            environment_path=destination.artifact(ENVIRONMENT_NAME),
            summary_path=destination.artifact(SUMMARY_NAME),
            report_path=destination.artifact(REPORT_NAME),
            answer_review_path=destination.artifact(ANSWER_REVIEW_NAME),
            telemetry_samples=len(telemetry_samples),
            retrieval_errors=run_summary.retrieval_errors,
            cascade_errors=run_summary.cascade_errors,
        )


def _capture_environment(config: AppConfig, block_device: str) -> dict[str, object]:
    """Capture a bounded allowlist of non-secret runtime metadata."""

    if not isinstance(config, AppConfig):
        raise EvaluationBenchmarkError("benchmark config is invalid")
    started = time.monotonic_ns()
    source = _source_snapshot()
    embedding = _embedding_snapshot(config.embedding.model_directory)
    record = {
        "block_device": block_device,
        "dependencies": _dependency_versions(),
        "device": _device_snapshot(),
        "embedding": embedding,
        "git": _git_snapshot(),
        "ollama": _ollama_snapshot(
            config.ollama.base_url,
            config.ollama.small_model,
            config.ollama.large_model,
            general_large_model=config.ollama.general_large_model,
        ),
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
        "record_type": "benchmark_environment",
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "source": source,
        "capture_start_monotonic_ns": started,
        "capture_end_monotonic_ns": time.monotonic_ns(),
    }
    if record["capture_end_monotonic_ns"] < started:
        raise EvaluationBenchmarkError(
            "environment timestamps are not increasing"
        )
    return record


def _bind_environment(
    snapshot: Mapping[str, object],
    header: Mapping[str, object],
    run_id: str,
) -> dict[str, object]:
    """Bind the environment snapshot to semantic hashes from observations."""

    if not isinstance(snapshot, Mapping) or not isinstance(header, Mapping):
        raise EvaluationBenchmarkError("environment binding data is invalid")
    suite_hash = header.get("suite_sha256")
    config_hash = header.get("config_sha256")
    header_run_id = header.get("run_id")
    if (
        not isinstance(suite_hash, str)
        or _SHA256_PATTERN.fullmatch(suite_hash) is None
        or not isinstance(config_hash, str)
        or _SHA256_PATTERN.fullmatch(config_hash) is None
        or not isinstance(run_id, str)
        or not run_id
        or header_run_id != run_id
    ):
        raise EvaluationBenchmarkError("environment binding data is invalid")
    bound = dict(snapshot)
    bound["evaluation"] = {
        "config_sha256": config_hash,
        "run_id": run_id,
        "suite_sha256": suite_hash,
    }
    return bound


def _source_snapshot() -> dict[str, object]:
    """Hash exact bytes from the explicit runtime-source allowlist."""

    aggregate = sha256()
    files = []
    for relative in _SOURCE_ALLOWLIST:
        try:
            raw = _read_bounded_regular_file(
                _PROJECT_ROOT / relative,
                maximum_bytes=MAX_ENVIRONMENT_FILE_BYTES,
            )
        except (OSError, EvaluationBenchmarkError):
            raise EvaluationBenchmarkError(
                "allowlisted runtime source could not be hashed"
            ) from None
        relative_bytes = relative.encode("utf-8")
        aggregate.update(len(relative_bytes).to_bytes(4, "big"))
        aggregate.update(relative_bytes)
        aggregate.update(len(raw).to_bytes(8, "big"))
        aggregate.update(raw)
        files.append(
            {
                "path": relative,
                "sha256": sha256(raw).hexdigest(),
                "size_bytes": len(raw),
            }
        )
    return {
        "aggregate_algorithm": (
            "sha256-u32be-path-length-path-u64be-content-length-content-v1"
        ),
        "aggregate_sha256": aggregate.hexdigest(),
        "files": files,
        "status": "available",
    }


def _embedding_snapshot(model_directory: str) -> dict[str, object]:
    """Hash only the embedding assets required by the pinned runtime."""

    try:
        directory = Path(model_directory).expanduser()
    except (TypeError, ValueError, RuntimeError):
        directory = Path("/")
        path_valid = False
    else:
        path_valid = directory.is_absolute()
    assets = []
    complete = path_valid
    for relative, expected in sorted(REQUIRED_ASSET_SHA256.items()):
        actual: Optional[str] = None
        size: Optional[int] = None
        if path_valid:
            try:
                size, actual = _sha256_bounded_regular_file(
                    directory.joinpath(*relative.split("/")),
                    maximum_bytes=MAX_EMBEDDING_ASSET_BYTES,
                )
            except (OSError, EvaluationBenchmarkError):
                complete = False
        record: dict[str, object] = {
            "expected_sha256": expected,
            "path": relative,
            "status": "available" if actual is not None else "unavailable",
        }
        if actual is not None and size is not None:
            record.update(
                {
                    "actual_sha256": actual,
                    "size_bytes": size,
                    "verified": actual == expected,
                }
            )
            if actual != expected:
                complete = False
        assets.append(record)
    return {
        "assets": assets,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "status": "verified" if complete else "incomplete",
    }


def _dependency_versions() -> list[dict[str, object]]:
    records = []
    for package in _PYTHON_DEPENDENCIES:
        try:
            version = importlib.metadata.version(package)
        except Exception:
            records.append({"name": package, "status": "unavailable"})
        else:
            cleaned = (
                _decoded_metadata_text(version.encode("utf-8"))
                if isinstance(version, str)
                else None
            )
            if cleaned is None or not cleaned or len(cleaned) > 256:
                records.append({"name": package, "status": "unavailable"})
            else:
                records.append(
                    {"name": package, "status": "available", "version": cleaned}
                )
    return records


def _device_snapshot() -> dict[str, object]:
    try:
        os_release = platform.freedesktop_os_release()
    except OSError:
        operating_system: dict[str, object] = {"status": "unavailable"}
    else:
        operating_system = {
            "id": os_release.get("ID"),
            "pretty_name": os_release.get("PRETTY_NAME"),
            "status": "available",
            "version_id": os_release.get("VERSION_ID"),
        }
    return {
        "kernel": {
            "machine": platform.machine(),
            "release": platform.release(),
        },
        "model": _fixed_text_file(Path("/proc/device-tree/model"), 512),
        "nvidia": {
            "jetpack_package": _dpkg_package_version("nvidia-jetpack"),
            "l4t_core_package": _dpkg_package_version("nvidia-l4t-core"),
            "nv_tegra_release": _fixed_text_file(
                Path("/etc/nv_tegra_release"), 16 * 1024
            ),
        },
        "nvpmodel": _command_text(("/usr/sbin/nvpmodel", "-q")),
        "operating_system": operating_system,
    }


def _dpkg_package_version(package: str) -> dict[str, object]:
    raw = _run_bounded_command(
        ("/usr/bin/dpkg-query", "-W", "-f=${Version}", package),
        maximum_bytes=512,
    )
    if raw is None:
        return {"status": "unavailable"}
    value = _decoded_metadata_text(raw)
    if value is None or not value:
        return {"status": "unavailable"}
    return {"status": "available", "version": value}


def _git_snapshot() -> dict[str, object]:
    head_raw = _run_bounded_command(
        ("/usr/bin/git", "rev-parse", "--verify", "HEAD"),
        cwd=_PROJECT_ROOT,
        maximum_bytes=256,
    )
    status_raw = _run_bounded_command(
        (
            "/usr/bin/git",
            "-c",
            "core.fsmonitor=false",
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--ignore-submodules=none",
        ),
        cwd=_PROJECT_ROOT,
        maximum_bytes=MAX_COMMAND_OUTPUT_BYTES,
    )
    if head_raw is None or status_raw is None:
        return {"status": "unavailable"}
    head = _decoded_metadata_text(head_raw)
    if head is None or re.fullmatch(r"[0-9a-fA-F]{40,64}", head) is None:
        return {"status": "unavailable"}
    return {
        "dirty": bool(status_raw),
        "dirty_status_format": "porcelain_v1_z_untracked_all",
        "dirty_status_sha256": sha256(status_raw).hexdigest(),
        "head": head.lower(),
        "status": "available",
    }


def _ollama_snapshot(
    base_url: str,
    small_model: str,
    large_model: str,
    *,
    general_large_model: Optional[str] = None,
) -> dict[str, object]:
    roles = (
        (("small", small_model), ("large", large_model))
        if general_large_model is None
        else (
            ("small", small_model),
            ("general_large", general_large_model),
            ("large", large_model),
        )
    )
    try:
        local_url = _local_ollama_url(base_url)
        tags_payload = _read_local_ollama_json(local_url, "/api/tags")
        models = tags_payload.get("models")
        if not isinstance(models, list) or len(models) > 256:
            raise ValueError("invalid model inventory")
        digests: dict[str, str] = {}
        for model in models:
            if not isinstance(model, Mapping):
                raise ValueError("invalid model inventory")
            name = model.get("name")
            digest = model.get("digest")
            if (
                not isinstance(name, str)
                or not 1 <= len(name) <= 256
                or not isinstance(digest, str)
                or _OLLAMA_DIGEST_PATTERN.fullmatch(digest) is None
                or name in digests
            ):
                raise ValueError("invalid model inventory")
            digests[name] = digest
    except (OSError, ValueError, HTTPError, URLError, json.JSONDecodeError):
        return {
            "configured_models": [
                {"role": role, "tag": tag} for role, tag in roles
            ],
            "status": "unavailable",
            "version": _ollama_version(base_url),
        }
    configured = []
    for role, tag in roles:
        item: dict[str, object] = {
            "installed": tag in digests,
            "role": role,
            "tag": tag,
        }
        if tag in digests:
            item["digest"] = digests[tag]
        configured.append(item)
    return {
        "configured_models": configured,
        "status": "available",
        "version": _ollama_version(local_url),
    }


def _ollama_version(base_url: str) -> dict[str, object]:
    try:
        local_url = _local_ollama_url(base_url)
        payload = _read_local_ollama_json(local_url, "/api/version")
        version = payload.get("version")
        if not isinstance(version, str) or re.fullmatch(
            r"[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}", version
        ) is None:
            raise ValueError("invalid Ollama version")
    except (OSError, ValueError, HTTPError, URLError, json.JSONDecodeError):
        return {"status": "unavailable"}
    return {"status": "available", "value": version}


def _local_ollama_url(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Ollama URL is invalid")
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        raise ValueError("Ollama URL is invalid") from None
    local = False
    if hostname is not None:
        if hostname.casefold() == "localhost":
            local = True
        else:
            try:
                local = ip_address(hostname).is_loopback
            except ValueError:
                pass
    if (
        parsed.scheme not in {"http", "https"}
        or not local
        or parsed.username is not None
        or parsed.password is not None
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("Ollama URL is not local")
    return value.rstrip("/")


def _read_local_ollama_json(base_url: str, endpoint: str) -> Mapping[str, object]:
    request = Request(
        f"{base_url}{endpoint}",
        headers={"Accept": "application/json"},
        method="GET",
    )
    opener = build_opener(ProxyHandler({}))
    with opener.open(request, timeout=ENVIRONMENT_TIMEOUT_SECONDS) as response:
        raw = response.read(MAX_OLLAMA_METADATA_BYTES + 1)
    if len(raw) > MAX_OLLAMA_METADATA_BYTES:
        raise ValueError("Ollama metadata exceeds size limit")
    decoded = json.loads(raw)
    if not isinstance(decoded, Mapping):
        raise ValueError("Ollama metadata is invalid")
    return decoded


def _fixed_text_file(path: Path, maximum_bytes: int) -> dict[str, object]:
    try:
        raw = _read_bounded_regular_file(path, maximum_bytes=maximum_bytes)
    except (OSError, EvaluationBenchmarkError):
        return {"status": "unavailable"}
    value = _decoded_metadata_text(raw, strip_nul=True)
    if value is None or not value:
        return {"status": "unavailable"}
    return {"status": "available", "value": value}


def _command_text(argv: tuple[str, ...]) -> dict[str, object]:
    raw = _run_bounded_command(argv, maximum_bytes=16 * 1024)
    if raw is None:
        return {"status": "unavailable"}
    value = _decoded_metadata_text(raw)
    if value is None or not value:
        return {"status": "unavailable"}
    return {"status": "available", "value": value}


def _decoded_metadata_text(
    raw: bytes, *, strip_nul: bool = False
) -> Optional[str]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if strip_nul:
        text = text.rstrip("\x00")
    if "\x00" in text or any(
        ord(character) < 32 and character not in "\n\r\t" for character in text
    ):
        return None
    return text.strip()


def _run_bounded_command(
    argv: tuple[str, ...],
    *,
    cwd: Optional[Path] = None,
    maximum_bytes: int,
) -> Optional[bytes]:
    try:
        completed = subprocess.run(
            argv,
            cwd=None if cwd is None else str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=ENVIRONMENT_TIMEOUT_SECONDS,
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0 or len(completed.stdout) > maximum_bytes:
        return None
    return completed.stdout


def _read_bounded_regular_file(path: Path, *, maximum_bytes: int) -> bytes:
    descriptor = _open_bounded_regular_file(path, maximum_bytes)
    failure: Optional[BaseException] = None
    raw = b""
    before: Optional[os.stat_result] = None
    after: Optional[os.stat_result] = None
    try:
        before = os.fstat(descriptor)
        chunks = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum_bytes:
                raise EvaluationBenchmarkError(
                    "environment source file exceeds size limit"
                )
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
    except BaseException as error:
        failure = error
    try:
        os.close(descriptor)
    except BaseException as error:
        if failure is None:
            failure = error
    if failure is not None:
        raise failure
    assert before is not None and after is not None
    _same_file_state(before, after, len(raw))
    return raw


def _sha256_bounded_regular_file(
    path: Path, *, maximum_bytes: int
) -> tuple[int, str]:
    descriptor = _open_bounded_regular_file(path, maximum_bytes)
    failure: Optional[BaseException] = None
    digest = sha256()
    total = 0
    before: Optional[os.stat_result] = None
    after: Optional[os.stat_result] = None
    try:
        before = os.fstat(descriptor)
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum_bytes:
                raise EvaluationBenchmarkError(
                    "embedding asset exceeds size limit"
                )
            digest.update(chunk)
        after = os.fstat(descriptor)
    except BaseException as error:
        failure = error
    try:
        os.close(descriptor)
    except BaseException as error:
        if failure is None:
            failure = error
    if failure is not None:
        raise failure
    assert before is not None and after is not None
    _same_file_state(before, after, total)
    return total, digest.hexdigest()


def _open_bounded_regular_file(path: Path, maximum_bytes: int) -> int:
    if maximum_bytes < 1:
        raise EvaluationBenchmarkError("environment size bound is invalid")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size < 0
            or metadata.st_size > maximum_bytes
        ):
            raise EvaluationBenchmarkError(
                "environment source is not a bounded regular file"
            )
    except BaseException:
        try:
            os.close(descriptor)
        except BaseException:
            pass
        raise
    return descriptor


def _same_file_state(
    before: os.stat_result, after: os.stat_result, bytes_read: int
) -> None:
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ctime_ns != after.st_ctime_ns
        or bytes_read != after.st_size
    ):
        raise EvaluationBenchmarkError(
            "environment source changed while it was hashed"
        )


def _canonical_json(value: Mapping[str, object]) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        raise EvaluationBenchmarkError(
            "telemetry summary is not canonical JSON data"
        ) from None


def _capture_throttle_snapshot() -> _ThrottleSnapshot:
    counters = []
    unavailable = []
    for domain in _THROTTLE_DOMAINS:
        path = (
            Path("/sys/devices/platform")
            / f"{domain}-throttle-alert"
            / "thermal_trip_event"
        )
        try:
            raw = _read_nonblocking_sysfs(path)
            text = raw.decode("ascii").strip()
            if not text or not text.isdigit():
                raise ValueError("invalid counter")
            value = int(text)
            if value > _MAX_THROTTLE_COUNTER:
                raise ValueError("counter outside range")
        except (OSError, UnicodeDecodeError, ValueError):
            unavailable.append(domain)
        else:
            counters.append((domain, value))
    return _ThrottleSnapshot(
        monotonic_ns=time.monotonic_ns(),
        counters=tuple(counters),
        unavailable=tuple(unavailable),
    )


def _read_nonblocking_sysfs(path: Path) -> bytes:
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    failure: Optional[BaseException] = None
    raw = b""
    try:
        raw = os.read(descriptor, _MAX_SYSFS_VALUE_BYTES + 1)
    except BaseException as error:
        failure = error
    try:
        os.close(descriptor)
    except BaseException as error:
        if failure is None:
            failure = error
    if failure is not None:
        raise failure
    if len(raw) > _MAX_SYSFS_VALUE_BYTES:
        raise ValueError("sysfs counter exceeds size limit")
    return raw


def _throttle_delta(
    before: _ThrottleSnapshot, after: _ThrottleSnapshot
) -> dict[str, object]:
    _validate_throttle_snapshot(before)
    _validate_throttle_snapshot(after)
    if after.monotonic_ns <= before.monotonic_ns:
        raise EvaluationBenchmarkError(
            "throttle snapshot timestamps are not increasing"
        )
    first = dict(before.counters)
    second = dict(after.counters)
    common = tuple(
        domain
        for domain in _THROTTLE_DOMAINS
        if domain in first and domain in second
    )
    deltas = {}
    inconsistent = []
    for domain in common:
        if second[domain] < first[domain]:
            inconsistent.append(domain)
        else:
            deltas[domain] = second[domain] - first[domain]
    unavailable = tuple(
        domain
        for domain in _THROTTLE_DOMAINS
        if domain not in common or domain in inconsistent
    )
    if not deltas:
        status = "unavailable"
    elif unavailable:
        status = "partial"
    else:
        status = "available"
    record: dict[str, object] = {
        "counters_after": second,
        "counters_before": first,
        "counter_deltas": deltas,
        "end_monotonic_ns": after.monotonic_ns,
        "source": "jetson_thermal_trip_event_sysfs",
        "start_monotonic_ns": before.monotonic_ns,
        "status": status,
        "unavailable_domains": list(unavailable),
    }
    if status == "available":
        record["thermal_trip_events_observed"] = any(
            value > 0 for value in deltas.values()
        )
    return record


def _validate_throttle_snapshot(value: object) -> None:
    if type(value) is not _ThrottleSnapshot:
        raise EvaluationBenchmarkError("throttle snapshot is invalid")
    if (
        isinstance(value.monotonic_ns, bool)
        or not isinstance(value.monotonic_ns, int)
        or not 0 <= value.monotonic_ns <= _MAX_THROTTLE_COUNTER
    ):
        raise EvaluationBenchmarkError("throttle snapshot is invalid")
    if not isinstance(value.counters, tuple) or not isinstance(
        value.unavailable, tuple
    ):
        raise EvaluationBenchmarkError("throttle snapshot is invalid")
    parsed_counters: list[tuple[str, int]] = []
    for item in value.counters:
        if not isinstance(item, tuple) or len(item) != 2:
            raise EvaluationBenchmarkError("throttle snapshot is invalid")
        name, counter = item
        if (
            not isinstance(name, str)
            or name not in _THROTTLE_DOMAINS
            or isinstance(counter, bool)
            or not isinstance(counter, int)
            or not 0 <= counter <= _MAX_THROTTLE_COUNTER
        ):
            raise EvaluationBenchmarkError("throttle snapshot is invalid")
        parsed_counters.append((name, counter))
    if any(not isinstance(name, str) for name in value.unavailable):
        raise EvaluationBenchmarkError("throttle snapshot is invalid")
    names = tuple(name for name, _ in parsed_counters)
    if (
        len(names) != len(set(names))
        or any(name not in _THROTTLE_DOMAINS for name in value.unavailable)
        or len(value.unavailable) != len(set(value.unavailable))
        or set(names) & set(value.unavailable)
        or set(names) | set(value.unavailable) != set(_THROTTLE_DOMAINS)
    ):
        raise EvaluationBenchmarkError("throttle snapshot is invalid")


def _benchmark_report(
    objective_report: str, telemetry_summary: Mapping[str, object]
) -> str:
    tegrastats = telemetry_summary.get("tegrastats")
    energy: object = None
    if isinstance(tegrastats, Mapping):
        energy = tegrastats.get("vdd_in_energy_joules")
    throttling = telemetry_summary.get("throttling")
    throttle_status = (
        throttling.get("status") if isinstance(throttling, Mapping) else "unavailable"
    )
    block_device = telemetry_summary.get("block_device", "unavailable")
    energy_text = "unavailable" if energy is None else str(energy)
    return (
        objective_report.rstrip()
        + "\n\n## Device measurement scope\n\n"
        + "- Tegrastats covers the runner setup, retrieval, and cascade context.\n"
        + "- VDD_IN energy is a trapezoidal estimate over the first-to-last "
        + "telemetry sample for the whole run; it is not attributed to an "
        + "individual case or strategy.\n"
        + f"- Whole-run sample-window VDD_IN energy (J): `{energy_text}`.\n"
        + f"- Disk counters use the exact block device `{block_device}`.\n"
        + "- Thermal throttling uses Jetson thermal-trip event-counter deltas; "
        + "temperature alone is never treated as proof of no throttling.\n"
        + f"- Thermal-trip counter availability: `{throttle_status}`.\n"
    )


def _output_directory_path(value: object) -> Path:
    try:
        path = Path(value)
    except (TypeError, ValueError, RuntimeError):
        raise EvaluationBenchmarkError(
            "benchmark output directory is invalid"
        ) from None
    if (
        "\x00" in str(path)
        or not path.is_absolute()
        or ".." in path.parts
        or path.name in {"", ".", ".."}
    ):
        raise EvaluationBenchmarkError(
            "benchmark output directory must be an absolute directory"
        )
    return path


def _validate_output_directory(path: Path) -> os.stat_result:
    current = Path(path.anchor)
    try:
        root_uid = os.lstat(current).st_uid
    except OSError:
        raise EvaluationBenchmarkError(
            "benchmark output ancestry could not be inspected"
        ) from None
    final: Optional[os.stat_result] = None
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError:
            raise EvaluationBenchmarkError(
                "benchmark output directory must already exist"
            ) from None
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise EvaluationBenchmarkError(
                "benchmark output ancestry must be symlink-free directories"
            )
        permissions = stat.S_IMODE(metadata.st_mode)
        if current != path and permissions & 0o022:
            trusted_sticky = bool(permissions & stat.S_ISVTX) and metadata.st_uid in {
                0,
                root_uid,
            }
            if not trusted_sticky:
                raise EvaluationBenchmarkError(
                    "benchmark output has an untrusted writable ancestor"
                )
        final = metadata
    if final is None or final.st_uid != os.geteuid():
        raise EvaluationBenchmarkError(
            "benchmark output directory must be owned by this user"
        )
    if stat.S_IMODE(final.st_mode) != 0o700:
        raise EvaluationBenchmarkError(
            "benchmark output directory must have mode 0700"
        )
    return final


def _block_device(value: object) -> str:
    if not isinstance(value, str) or _DEVICE_PATTERN.fullmatch(value) is None:
        raise EvaluationBenchmarkError("block device name is invalid")
    return value


def _strategies(values: object) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise EvaluationBenchmarkError("strategies must be a sequence")
    selected = tuple(values)
    if not selected:
        raise EvaluationBenchmarkError("at least one strategy is required")
    if any(not isinstance(value, str) for value in selected):
        raise EvaluationBenchmarkError("strategy is unsupported")
    if len(selected) != len(set(selected)):
        raise EvaluationBenchmarkError("strategies must not contain duplicates")
    if any(value not in CASCADE_STRATEGIES for value in selected):
        raise EvaluationBenchmarkError("strategy is unsupported")
    return selected


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m oline_hri.evaluation_benchmark",
        description="Run and score the local Step 16 Jetson benchmark",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run and publish benchmark artifacts")
    run.add_argument("--dataset", type=Path, default=None)
    run.add_argument("--config", type=Path, default=None)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--block-device", required=True)
    run.add_argument(
        "--strategy",
        action="append",
        choices=CASCADE_STRATEGIES,
        dest="strategies",
        help="cascade strategy; repeat to select several (default: all)",
    )
    run.add_argument("--repetitions", type=int, default=1)
    run.add_argument("--telemetry-interval-ms", type=int, default=500)
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    """Run the benchmark CLI without printing any prompt or answer."""

    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    args = _build_parser().parse_args(argv)
    try:
        suite = load_evaluation_suite(args.dataset)
        config = load_config(args.config)
        result = run_benchmark(
            suite,
            config,
            args.output_dir,
            block_device=args.block_device,
            strategies=(
                CASCADE_STRATEGIES
                if args.strategies is None
                else tuple(args.strategies)
            ),
            repetitions=args.repetitions,
            telemetry_interval_ms=args.telemetry_interval_ms,
            progress=errors,
        )
    except (
        ConfigError,
        EvaluationError,
        EvaluationRunError,
        EvaluationScoringError,
        EvaluationTelemetryError,
        EvaluationBenchmarkError,
        ValueError,
    ):
        print(
            "evaluation benchmark error: request could not be completed safely",
            file=errors,
        )
        return 2

    print(
        f"evaluation benchmark complete: {result.run_id} "
        f"({result.telemetry_samples} telemetry samples)",
        file=output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
