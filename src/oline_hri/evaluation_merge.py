"""Offline, provenance-checked merge of four Step 16 benchmark bundles."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import re
import stat
import sys
from typing import Mapping, Optional, Sequence, TextIO

from .evaluation import EvaluationError, EvaluationSuite, load_evaluation_suite
from .evaluation_runner import ALWAYS_SMALL_NO_RAG, CASCADE_STRATEGIES
from .evaluation_scoring import (
    MAX_OBSERVATION_BYTES,
    EvaluationScoringError,
    ObservationRun,
    canonical_summary_json,
    emit_blinded_review_sheet,
    merge_observation_runs,
    parse_observation_jsonl,
    render_summary_markdown,
    score_observations,
)


BUNDLE_COUNT = 4
OBSERVATIONS_NAME = "observations.jsonl"
ENVIRONMENT_NAME = "environment.json"
SUMMARY_NAME = "summary.json"
REPORT_NAME = "report.md"
ANSWER_REVIEW_NAME = "answer_review.jsonl"
MANIFEST_NAME = "manifest.json"
OUTPUT_NAMES = (SUMMARY_NAME, REPORT_NAME, ANSWER_REVIEW_NAME, MANIFEST_NAME)
MERGE_SCHEMA_VERSION = 1
MAX_ENVIRONMENT_BYTES = 4 * 1024 * 1024
MAX_OUTPUT_BYTES = 128 * 1024 * 1024
MAX_PATH_CHARACTERS = 4096

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_GIT_HEAD_PATTERN = re.compile(r"[0-9a-f]{40,64}\Z")
_DEVICE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_SOURCE_PATHS = (
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
    "src/oline_hri/response.py",
    "src/oline_hri/retrieval.py",
    "src/oline_hri/routing.py",
    "config/default.json",
    "evaluation/fictional_seven_day_v1.json",
)
_DEPENDENCY_NAMES = ("oline-hri", "numpy", "onnxruntime", "tokenizers")


class EvaluationMergeError(RuntimeError):
    """Raised when source bundles cannot be merged without ambiguity."""


@dataclass(frozen=True)
class MergeResult:
    """Paths produced by one completed offline merge."""

    merged_run_id: str
    summary_path: Path
    report_path: Path
    answer_review_path: Path
    manifest_path: Path
    source_run_ids: tuple[str, ...]
    retrieval_source_run_id: str


@dataclass(frozen=True)
class _ArtifactIdentity:
    name: str
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True)
class _Bundle:
    path: Path
    directory_device: int
    directory_inode: int
    observations: ObservationRun
    observations_identity: _ArtifactIdentity
    observations_sha256: str
    environment: Mapping[str, object]
    environment_identity: _ArtifactIdentity
    environment_sha256: str
    provenance: Mapping[str, object]


@dataclass(frozen=True)
class _CreatedFile:
    name: str
    device: int
    inode: int


class _PrivateDirectory:
    """Hold one absolute, private, symlink-free directory by descriptor."""

    def __init__(self, value: str | Path, *, label: str) -> None:
        self.path = _directory_path(value, label)
        self.label = label
        self._descriptor: Optional[int] = None
        self._device: Optional[int] = None
        self._inode: Optional[int] = None

    @property
    def descriptor(self) -> int:
        if self._descriptor is None:
            raise EvaluationMergeError(f"{self.label} directory is not open")
        return self._descriptor

    @property
    def identity(self) -> tuple[int, int]:
        if self._device is None or self._inode is None:
            raise EvaluationMergeError(f"{self.label} directory is not open")
        return self._device, self._inode

    def __enter__(self) -> "_PrivateDirectory":
        expected = _validate_private_directory(self.path, self.label)
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.path, flags)
        except OSError:
            raise EvaluationMergeError(
                f"{self.label} directory could not be opened"
            ) from None
        try:
            opened = os.fstat(descriptor)
            if not _same_private_directory(opened, expected):
                raise EvaluationMergeError(
                    f"{self.label} directory identity changed"
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
            except BaseException as error:
                if exc_type is not None:
                    return False
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    raise
                raise EvaluationMergeError(
                    f"{self.label} directory close failed"
                ) from None
        return False

    def verify(self) -> None:
        try:
            opened = os.fstat(self.descriptor)
            current = os.lstat(self.path)
        except OSError:
            raise EvaluationMergeError(
                f"{self.label} directory could not be revalidated"
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
            raise EvaluationMergeError(
                f"{self.label} directory identity changed"
            )

    def read_private_file(
        self, name: str, *, maximum_bytes: int
    ) -> tuple[bytes, _ArtifactIdentity]:
        if name not in {OBSERVATIONS_NAME, ENVIRONMENT_NAME}:
            raise EvaluationMergeError("source artifact name is invalid")
        self.verify()
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(name, flags, dir_fd=self.descriptor)
        except OSError:
            raise EvaluationMergeError("source artifact could not be opened") from None
        failure: Optional[BaseException] = None
        before: Optional[os.stat_result] = None
        after: Optional[os.stat_result] = None
        raw = b""
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o600
                or before.st_size < 0
                or before.st_size > maximum_bytes
            ):
                raise EvaluationMergeError(
                    "source artifact is not a bounded private regular file"
                )
            chunks = []
            total = 0
            while True:
                remaining = maximum_bytes + 1 - total
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > maximum_bytes:
                    raise EvaluationMergeError(
                        "source artifact exceeds size limit"
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
        identity = _ArtifactIdentity(
            name=name,
            device=before.st_dev,
            inode=before.st_ino,
            size=len(raw),
            modified_ns=before.st_mtime_ns,
            changed_ns=before.st_ctime_ns,
        )
        if not _same_artifact_state(before, after, identity):
            raise EvaluationMergeError("source artifact changed while being read")
        self.verify_file(identity)
        return raw, identity

    def verify_file(self, identity: _ArtifactIdentity) -> None:
        self.verify()
        try:
            relative = os.stat(
                identity.name,
                dir_fd=self.descriptor,
                follow_symlinks=False,
            )
            absolute = os.lstat(self.path / identity.name)
        except OSError:
            raise EvaluationMergeError(
                "source artifact could not be revalidated"
            ) from None
        if (
            not _same_artifact_state(relative, absolute, identity)
            or relative.st_uid != os.geteuid()
            or stat.S_IMODE(relative.st_mode) != 0o600
        ):
            raise EvaluationMergeError("source artifact identity changed")


class _OutputDirectory(_PrivateDirectory):
    """Publish the fixed merged artifact set without overwriting names."""

    def __init__(self, value: str | Path) -> None:
        super().__init__(value, label="output")

    def __enter__(self) -> "_OutputDirectory":
        super().__enter__()
        try:
            self.require_absent()
        except BaseException:
            super().__exit__(*sys.exc_info())
            raise
        return self

    def require_absent(self) -> None:
        for name in OUTPUT_NAMES:
            try:
                os.stat(name, dir_fd=self.descriptor, follow_symlinks=False)
            except FileNotFoundError:
                continue
            except OSError:
                raise EvaluationMergeError(
                    "output artifact path could not be inspected"
                ) from None
            raise EvaluationMergeError("output artifact already exists")

    def publish(self, artifacts: Mapping[str, bytes]) -> None:
        if tuple(artifacts) != OUTPUT_NAMES:
            raise EvaluationMergeError("output artifact set is invalid")
        self.verify()
        created: list[_CreatedFile] = []
        try:
            for name, payload in artifacts.items():
                created.append(self._create(name, payload))
            os.fsync(self.descriptor)
            self.verify()
        except BaseException as error:
            try:
                clean = self._cleanup(created)
            except BaseException as cleanup_error:
                if not isinstance(error, Exception):
                    raise error
                raise cleanup_error
            if not isinstance(error, Exception):
                raise
            if not clean:
                raise EvaluationMergeError(
                    "output publication failed and cleanup was incomplete"
                ) from None
            if isinstance(error, EvaluationMergeError):
                raise
            raise EvaluationMergeError("output publication failed") from None

    def _create(self, name: str, payload: bytes) -> _CreatedFile:
        if name not in OUTPUT_NAMES:
            raise EvaluationMergeError("output artifact name is invalid")
        if not isinstance(payload, bytes) or len(payload) > MAX_OUTPUT_BYTES:
            raise EvaluationMergeError("output artifact payload is invalid")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(name, flags, 0o600, dir_fd=self.descriptor)
        except FileExistsError:
            raise EvaluationMergeError("output artifact already exists") from None
        except OSError:
            raise EvaluationMergeError("output artifact could not be created") from None

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
                clean = (
                    False if identity is None else self._unlink_if_same(identity)
                )
            except BaseException as cleanup_error:
                if not isinstance(failure, Exception):
                    raise failure
                raise cleanup_error
            if not isinstance(failure, Exception):
                raise failure
            if not clean:
                raise EvaluationMergeError(
                    "output write failed and cleanup was incomplete"
                ) from None
            raise EvaluationMergeError("output artifact write failed") from None
        assert identity is not None
        if not self._matches(identity):
            clean = self._unlink_if_same(identity)
            if not clean:
                raise EvaluationMergeError(
                    "output identity changed and cleanup was incomplete"
                ) from None
            raise EvaluationMergeError("output artifact identity changed") from None
        return identity

    def _matches(self, identity: _CreatedFile) -> bool:
        metadata = self._metadata_if_same(identity)
        return bool(
            metadata is not None
            and metadata.st_uid == os.geteuid()
            and stat.S_IMODE(metadata.st_mode) == 0o600
        )

    def _metadata_if_same(
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
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_dev != identity.device
            or metadata.st_ino != identity.inode
        ):
            return None
        return metadata

    def _unlink_if_same(self, identity: _CreatedFile) -> bool:
        if self._metadata_if_same(identity) is None:
            return False
        try:
            os.unlink(identity.name, dir_fd=self.descriptor)
        except OSError:
            return False
        return True

    def _cleanup(self, created: Sequence[_CreatedFile]) -> bool:
        complete = True
        cancellation: Optional[BaseException] = None
        for identity in reversed(created):
            try:
                if not self._unlink_if_same(identity):
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


def merge_bundles(
    suite: EvaluationSuite,
    bundle_dirs: Sequence[str | Path],
    output_dir: str | Path,
) -> MergeResult:
    """Validate, merge, score, and publish four offline Step 16 bundles."""

    source_paths = _bundle_paths(bundle_dirs)
    with _OutputDirectory(output_dir) as output:
        bundles = tuple(_load_bundle(path) for path in source_paths)
        identities = tuple(
            (bundle.directory_device, bundle.directory_inode) for bundle in bundles
        )
        if len(identities) != len(set(identities)):
            raise EvaluationMergeError("bundle directories must be distinct")
        if output.identity in set(identities):
            raise EvaluationMergeError("output directory must differ from bundles")

        ordered, retrieval_run_id = _validated_strategy_order(bundles)
        provenance = _common_provenance(ordered)
        merged = merge_observation_runs(
            tuple(bundle.observations for bundle in ordered),
            retrieval_run_id=retrieval_run_id,
        )
        objective = score_observations(suite, merged)
        summary_bytes = canonical_summary_json(objective).encode("utf-8")
        report_bytes = _merged_report(
            render_summary_markdown(objective),
            retrieval_run_id,
            _canonical_sha256(provenance),
        ).encode("utf-8")
        review_bytes = emit_blinded_review_sheet(suite, merged).encode("utf-8")
        manifest = _manifest(
            ordered,
            merged,
            retrieval_run_id,
            provenance,
            {
                SUMMARY_NAME: summary_bytes,
                REPORT_NAME: report_bytes,
                ANSWER_REVIEW_NAME: review_bytes,
            },
        )
        artifacts = {
            SUMMARY_NAME: summary_bytes,
            REPORT_NAME: report_bytes,
            ANSWER_REVIEW_NAME: review_bytes,
            MANIFEST_NAME: _canonical_json(manifest),
        }
        for bundle in ordered:
            _revalidate_bundle(bundle)
        output.publish(artifacts)
        run_ids = tuple(str(bundle.observations.header["run_id"]) for bundle in ordered)
        return MergeResult(
            merged_run_id=str(merged.header["run_id"]),
            summary_path=output.path / SUMMARY_NAME,
            report_path=output.path / REPORT_NAME,
            answer_review_path=output.path / ANSWER_REVIEW_NAME,
            manifest_path=output.path / MANIFEST_NAME,
            source_run_ids=run_ids,
            retrieval_source_run_id=retrieval_run_id,
        )


def _load_bundle(path: Path) -> _Bundle:
    with _PrivateDirectory(path, label="bundle") as directory:
        observations_raw, observations_identity = directory.read_private_file(
            OBSERVATIONS_NAME,
            maximum_bytes=MAX_OBSERVATION_BYTES,
        )
        try:
            observations_text = observations_raw.decode("utf-8")
        except UnicodeDecodeError:
            raise EvaluationMergeError(
                "observations artifact is not UTF-8"
            ) from None
        observations = parse_observation_jsonl(observations_text)
        directory.verify_file(observations_identity)
        environment_raw, environment_identity = directory.read_private_file(
            ENVIRONMENT_NAME,
            maximum_bytes=MAX_ENVIRONMENT_BYTES,
        )
        directory_device, directory_inode = directory.identity
    environment = _parse_environment(environment_raw)
    _bind_environment(environment, observations)
    provenance = _provenance(environment)
    return _Bundle(
        path=path,
        directory_device=directory_device,
        directory_inode=directory_inode,
        observations=observations,
        observations_identity=observations_identity,
        observations_sha256=sha256(observations_raw).hexdigest(),
        environment=environment,
        environment_identity=environment_identity,
        environment_sha256=sha256(environment_raw).hexdigest(),
        provenance=provenance,
    )


def _revalidate_bundle(bundle: _Bundle) -> None:
    with _PrivateDirectory(bundle.path, label="bundle") as directory:
        if directory.identity != (
            bundle.directory_device,
            bundle.directory_inode,
        ):
            raise EvaluationMergeError("bundle directory identity changed")
        directory.verify_file(bundle.observations_identity)
        directory.verify_file(bundle.environment_identity)


def _validated_strategy_order(
    bundles: Sequence[_Bundle],
) -> tuple[tuple[_Bundle, ...], str]:
    if len(bundles) != BUNDLE_COUNT:
        raise EvaluationMergeError("exactly four bundles are required")
    owners: dict[str, _Bundle] = {}
    run_ids = []
    for bundle in bundles:
        run = bundle.observations
        if not run.trailer_present or run.trailer.get("completed") is not True:
            raise EvaluationMergeError("source benchmark run is incomplete")
        strategies = tuple(run.header["strategies"])
        if len(strategies) != 1:
            raise EvaluationMergeError(
                "each source bundle must contain exactly one strategy"
            )
        strategy = str(strategies[0])
        if strategy not in CASCADE_STRATEGIES or strategy in owners:
            raise EvaluationMergeError(
                "source strategies must be disjoint and complete"
            )
        owners[strategy] = bundle
        run_id = str(run.header["run_id"])
        if _RUN_ID_PATTERN.fullmatch(run_id) is None or run_id in run_ids:
            raise EvaluationMergeError("source run IDs must be valid and distinct")
        run_ids.append(run_id)
    if set(owners) != set(CASCADE_STRATEGIES):
        raise EvaluationMergeError(
            "source strategies must be disjoint and complete"
        )
    ordered = tuple(owners[strategy] for strategy in CASCADE_STRATEGIES)
    retrieval = owners[ALWAYS_SMALL_NO_RAG].observations
    if not retrieval.retrievals:
        raise EvaluationMergeError(
            "always_small_no_rag must provide component retrieval observations"
        )
    return ordered, str(retrieval.header["run_id"])


def _common_provenance(bundles: Sequence[_Bundle]) -> Mapping[str, object]:
    if not bundles:
        raise EvaluationMergeError("source provenance is missing")
    first = bundles[0].provenance
    expected = _canonical_json(first)
    for bundle in bundles[1:]:
        if _canonical_json(bundle.provenance) != expected:
            raise EvaluationMergeError("source bundle provenance does not match")
    return first


def _parse_environment(raw: bytes) -> Mapping[str, object]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise EvaluationMergeError("environment artifact is not UTF-8") from None
    if not text or not text.endswith("\n") or "\x00" in text:
        raise EvaluationMergeError("environment artifact framing is invalid")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_json_constant,
            parse_int=_bounded_json_int,
            parse_float=_bounded_json_float,
        )
    except EvaluationMergeError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError, OverflowError):
        raise EvaluationMergeError("environment artifact is invalid JSON") from None
    if not isinstance(value, Mapping):
        raise EvaluationMergeError("environment artifact must be an object")
    _validate_json_value(value)
    if _canonical_json(value) != raw:
        raise EvaluationMergeError("environment artifact is not canonical JSON")
    _validate_environment(value)
    return value


def _validate_environment(value: Mapping[str, object]) -> None:
    required = {
        "block_device",
        "capture_end_monotonic_ns",
        "capture_start_monotonic_ns",
        "dependencies",
        "device",
        "embedding",
        "evaluation",
        "git",
        "ollama",
        "python",
        "record_type",
        "schema_version",
        "source",
    }
    if set(value) != required:
        raise EvaluationMergeError("environment artifact fields are invalid")
    if value["record_type"] != "benchmark_environment":
        raise EvaluationMergeError("environment record type is invalid")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise EvaluationMergeError("environment schema version is invalid")
    device = value["block_device"]
    if not isinstance(device, str) or _DEVICE_PATTERN.fullmatch(device) is None:
        raise EvaluationMergeError("environment block device is invalid")
    started = value["capture_start_monotonic_ns"]
    finished = value["capture_end_monotonic_ns"]
    if (
        type(started) is not int
        or type(finished) is not int
        or not 0 <= started <= finished <= 2**63 - 1
    ):
        raise EvaluationMergeError("environment timestamps are invalid")
    for field in ("device", "embedding", "evaluation", "git", "ollama", "python"):
        if not isinstance(value[field], Mapping):
            raise EvaluationMergeError(f"environment {field} is invalid")
    if not isinstance(value["dependencies"], list):
        raise EvaluationMergeError("environment dependencies are invalid")
    _validate_source(value["source"])
    _validate_embedding(value["embedding"])
    _validate_ollama(value["ollama"])
    _validate_device(value["device"])
    _validate_python(value["python"], value["dependencies"])
    _git_stable(value["git"])


def _validate_source(value: object) -> None:
    source = _mapping(value, "source")
    required = {"aggregate_algorithm", "aggregate_sha256", "files", "status"}
    if set(source) != required or source["status"] != "available":
        raise EvaluationMergeError("environment source provenance is invalid")
    if (
        source["aggregate_algorithm"]
        != "sha256-u32be-path-length-path-u64be-content-length-content-v1"
        or not _sha(source["aggregate_sha256"])
    ):
        raise EvaluationMergeError("environment source provenance is invalid")
    files = source["files"]
    if not isinstance(files, list) or len(files) != len(_SOURCE_PATHS):
        raise EvaluationMergeError("environment source file hashes are invalid")
    paths = []
    for item in files:
        record = _mapping(item, "source file")
        if set(record) != {"path", "sha256", "size_bytes"}:
            raise EvaluationMergeError("environment source file hash is invalid")
        path = record["path"]
        size = record["size_bytes"]
        if (
            not isinstance(path, str)
            or not _sha(record["sha256"])
            or type(size) is not int
            or not 0 <= size <= 2 * 1024 * 1024
        ):
            raise EvaluationMergeError("environment source file hash is invalid")
        paths.append(path)
    if tuple(paths) != _SOURCE_PATHS:
        raise EvaluationMergeError("environment source allowlist is invalid")


def _validate_embedding(value: object) -> None:
    embedding = _mapping(value, "embedding")
    if set(embedding) != {"assets", "model_id", "model_revision", "status"}:
        raise EvaluationMergeError("environment embedding provenance is invalid")
    if not _text(embedding["model_id"], 256) or not _text(
        embedding["model_revision"], 256
    ):
        raise EvaluationMergeError("environment embedding identity is invalid")
    if embedding["status"] not in {"verified", "incomplete"}:
        raise EvaluationMergeError("environment embedding status is invalid")
    assets = embedding["assets"]
    if not isinstance(assets, list) or not 1 <= len(assets) <= 32:
        raise EvaluationMergeError("environment embedding assets are invalid")
    paths = []
    all_verified = True
    for item in assets:
        asset = _mapping(item, "embedding asset")
        if not {"expected_sha256", "path", "status"}.issubset(asset):
            raise EvaluationMergeError("environment embedding asset is invalid")
        if not _sha(asset["expected_sha256"]):
            raise EvaluationMergeError("environment embedding hash is invalid")
        path = asset["path"]
        if not isinstance(path, str) or not _text(path, 256) or path in paths:
            raise EvaluationMergeError("environment embedding path is invalid")
        paths.append(path)
        status = asset["status"]
        if status == "available":
            if set(asset) != {
                "actual_sha256",
                "expected_sha256",
                "path",
                "size_bytes",
                "status",
                "verified",
            }:
                raise EvaluationMergeError("environment embedding asset is invalid")
            matches = asset["actual_sha256"] == asset["expected_sha256"]
            if (
                not _sha(asset["actual_sha256"])
                or type(asset["size_bytes"]) is not int
                or not 0 <= asset["size_bytes"] <= 512 * 1024 * 1024
                or type(asset["verified"]) is not bool
                or asset["verified"] is not matches
            ):
                raise EvaluationMergeError("environment embedding asset is invalid")
            all_verified = all_verified and matches
        elif status == "unavailable":
            if set(asset) != {"expected_sha256", "path", "status"}:
                raise EvaluationMergeError("environment embedding asset is invalid")
            all_verified = False
        else:
            raise EvaluationMergeError("environment embedding status is invalid")
    if (embedding["status"] == "verified") is not all_verified:
        raise EvaluationMergeError("environment embedding status is inconsistent")


def _validate_ollama(value: object) -> None:
    ollama = _mapping(value, "Ollama")
    if set(ollama) != {"configured_models", "status", "version"}:
        raise EvaluationMergeError("environment Ollama provenance is invalid")
    if ollama["status"] not in {"available", "unavailable"}:
        raise EvaluationMergeError("environment Ollama status is invalid")
    models = ollama["configured_models"]
    if not isinstance(models, list) or len(models) != 2:
        raise EvaluationMergeError("environment Ollama models are invalid")
    roles = []
    for item in models:
        model = _mapping(item, "Ollama model")
        if not {"role", "tag"}.issubset(model):
            raise EvaluationMergeError("environment Ollama model is invalid")
        role = model["role"]
        if role not in {"small", "large"} or role in roles:
            raise EvaluationMergeError("environment Ollama model role is invalid")
        roles.append(role)
        if not _text(model["tag"], 256):
            raise EvaluationMergeError("environment Ollama model tag is invalid")
        if ollama["status"] == "available":
            allowed = {"installed", "role", "tag", "digest"}
            if not set(model).issubset(allowed) or "installed" not in model:
                raise EvaluationMergeError("environment Ollama model is invalid")
            if type(model["installed"]) is not bool:
                raise EvaluationMergeError("environment Ollama model is invalid")
            if model["installed"]:
                digest = model.get("digest")
                if not isinstance(digest, str) or re.fullmatch(
                    r"(?:sha256:)?[0-9a-f]{64}", digest
                ) is None:
                    raise EvaluationMergeError("environment Ollama digest is invalid")
            elif "digest" in model:
                raise EvaluationMergeError("environment Ollama digest is invalid")
        elif set(model) != {"role", "tag"}:
            raise EvaluationMergeError("environment Ollama model is invalid")
    if roles != ["small", "large"]:
        raise EvaluationMergeError("environment Ollama model order is invalid")
    version = _mapping(ollama["version"], "Ollama version")
    if version.get("status") == "available":
        if set(version) != {"status", "value"} or not _text(
            version["value"], 64
        ):
            raise EvaluationMergeError("environment Ollama version is invalid")
    elif version != {"status": "unavailable"}:
        raise EvaluationMergeError("environment Ollama version is invalid")


def _validate_device(value: object) -> None:
    device = _mapping(value, "device")
    if set(device) != {
        "kernel",
        "model",
        "nvidia",
        "nvpmodel",
        "operating_system",
    }:
        raise EvaluationMergeError("environment device provenance is invalid")
    kernel = _mapping(device["kernel"], "kernel")
    if set(kernel) != {"machine", "release"} or not _text(
        kernel["machine"], 256
    ) or not _text(kernel["release"], 256):
        raise EvaluationMergeError("environment kernel provenance is invalid")
    nvidia = _mapping(device["nvidia"], "NVIDIA")
    if set(nvidia) != {
        "jetpack_package",
        "l4t_core_package",
        "nv_tegra_release",
    }:
        raise EvaluationMergeError("environment NVIDIA provenance is invalid")
    _status_text(device["model"], "model", "value", 1024)
    _status_text(device["nvpmodel"], "nvpmodel", "value", 16_384)
    _status_text(
        nvidia["nv_tegra_release"], "nv_tegra_release", "value", 16_384
    )
    _status_text(
        nvidia["jetpack_package"], "JetPack package", "version", 256
    )
    _status_text(
        nvidia["l4t_core_package"], "L4T core package", "version", 256
    )
    operating_system = _mapping(device["operating_system"], "operating system")
    if operating_system.get("status") == "available":
        if set(operating_system) != {
            "id",
            "pretty_name",
            "status",
            "version_id",
        } or any(
            not _text(operating_system[field], 1024)
            for field in ("id", "pretty_name", "version_id")
        ):
            raise EvaluationMergeError("environment operating system is invalid")
    elif operating_system != {"status": "unavailable"}:
        raise EvaluationMergeError("environment operating system is invalid")


def _validate_python(value: object, dependencies: object) -> None:
    python = _mapping(value, "Python")
    if set(python) != {"implementation", "version"} or not _text(
        python["implementation"], 128
    ) or not _text(python["version"], 128):
        raise EvaluationMergeError("environment Python provenance is invalid")
    if not isinstance(dependencies, list) or not dependencies:
        raise EvaluationMergeError("environment dependencies are invalid")
    names = []
    for item in dependencies:
        dependency = _mapping(item, "dependency")
        if dependency.get("status") == "available":
            if set(dependency) != {"name", "status", "version"} or not _text(
                dependency["version"], 256
            ):
                raise EvaluationMergeError("environment dependency is invalid")
        elif dependency != {
            "name": dependency.get("name"),
            "status": "unavailable",
        }:
            raise EvaluationMergeError("environment dependency is invalid")
        name = dependency.get("name")
        if not isinstance(name, str) or not _text(name, 128) or name in names:
            raise EvaluationMergeError("environment dependency name is invalid")
        names.append(name)
    if tuple(names) != _DEPENDENCY_NAMES:
        raise EvaluationMergeError("environment dependency allowlist is invalid")


def _bind_environment(
    environment: Mapping[str, object], observations: ObservationRun
) -> None:
    evaluation = _mapping(environment["evaluation"], "environment evaluation")
    if set(evaluation) != {"config_sha256", "run_id", "suite_sha256"}:
        raise EvaluationMergeError("environment evaluation binding is invalid")
    if (
        evaluation["run_id"] != observations.header["run_id"]
        or evaluation["suite_sha256"] != observations.header["suite_sha256"]
        or evaluation["config_sha256"] != observations.header["config_sha256"]
        or not _sha(evaluation["suite_sha256"])
        or not _sha(evaluation["config_sha256"])
    ):
        raise EvaluationMergeError("environment does not match observations")
    runtime = _mapping(observations.header.get("runtime"), "observation runtime")
    ollama = _mapping(environment["ollama"], "Ollama")
    models = ollama["configured_models"]
    assert isinstance(models, list)
    model_tags = {
        str(item["role"]): item["tag"]
        for item in models
        if isinstance(item, Mapping)
    }
    embedding = _mapping(environment["embedding"], "embedding")
    python = _mapping(environment["python"], "Python")
    device = _mapping(environment["device"], "device")
    kernel = _mapping(device["kernel"], "kernel")
    if (
        runtime.get("small_model") != model_tags.get("small")
        or runtime.get("large_model") != model_tags.get("large")
        or runtime.get("embedding_model_id") != embedding["model_id"]
        or runtime.get("embedding_model_revision") != embedding["model_revision"]
        or runtime.get("python_version") != python["version"]
        or runtime.get("machine") != kernel["machine"]
    ):
        raise EvaluationMergeError(
            "environment runtime provenance does not match observations"
        )


def _provenance(environment: Mapping[str, object]) -> Mapping[str, object]:
    return {
        "block_device": environment["block_device"],
        "dependencies": environment["dependencies"],
        "device": environment["device"],
        "embedding": environment["embedding"],
        "git": _git_stable(environment["git"]),
        "ollama": environment["ollama"],
        "python": environment["python"],
        "source": environment["source"],
    }


def _git_stable(value: object) -> Mapping[str, object]:
    git = _mapping(value, "git")
    if git.get("status") == "available":
        required = {
            "dirty",
            "dirty_status_format",
            "dirty_status_sha256",
            "head",
            "status",
        }
        if (
            set(git) != required
            or type(git["dirty"]) is not bool
            or git["dirty_status_format"] != "porcelain_v1_z_untracked_all"
            or not _sha(git["dirty_status_sha256"])
            or not isinstance(git["head"], str)
            or _GIT_HEAD_PATTERN.fullmatch(git["head"]) is None
        ):
            raise EvaluationMergeError("environment git provenance is invalid")
        return {"head": git["head"], "status": "available"}
    if git != {"status": "unavailable"}:
        raise EvaluationMergeError("environment git provenance is invalid")
    return {"status": "unavailable"}


def _manifest(
    bundles: Sequence[_Bundle],
    merged: ObservationRun,
    retrieval_run_id: str,
    provenance: Mapping[str, object],
    outputs: Mapping[str, bytes],
) -> Mapping[str, object]:
    sources = []
    for bundle in bundles:
        run = bundle.observations
        sources.append(
            {
                "environment_sha256": bundle.environment_sha256,
                "observations_sha256": bundle.observations_sha256,
                "path": str(bundle.path),
                "run_id": run.header["run_id"],
                "strategy": run.header["strategies"][0],
            }
        )
    return {
        "config_sha256": merged.header["config_sha256"],
        "merged_run_id": merged.header["run_id"],
        "output_sha256": {
            name: sha256(payload).hexdigest() for name, payload in outputs.items()
        },
        "provenance": provenance,
        "provenance_sha256": _canonical_sha256(provenance),
        "record_type": "evaluation_merge_manifest",
        "retrieval_source": {
            "run_id": retrieval_run_id,
            "strategy": ALWAYS_SMALL_NO_RAG,
        },
        "schema_version": MERGE_SCHEMA_VERSION,
        "source_bundles": sources,
        "suite_id": merged.header["suite_id"],
        "suite_sha256": merged.header["suite_sha256"],
    }


def _merged_report(report: str, retrieval_run_id: str, provenance_hash: str) -> str:
    return (
        report.rstrip()
        + "\n\n## Offline merge provenance\n\n"
        + f"- Source bundles: `{BUNDLE_COUNT}`.\n"
        + "- Component retrieval source strategy: "
        + f"`{ALWAYS_SMALL_NO_RAG}`.\n"
        + f"- Component retrieval source run: `{retrieval_run_id}`.\n"
        + f"- Invariant provenance SHA-256: `{provenance_hash}`.\n"
    )


def _canonical_sha256(value: Mapping[str, object]) -> str:
    return sha256(_canonical_json(value)).hexdigest()


def _canonical_json(value: Mapping[str, object]) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        raise EvaluationMergeError("merge metadata is not canonical JSON") from None


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvaluationMergeError("environment contains duplicate fields")
        result[key] = value
    return result


def _invalid_json_constant(value: str) -> object:
    raise EvaluationMergeError("environment contains a non-finite number")


def _bounded_json_int(value: str) -> int:
    if len(value) > 20:
        raise EvaluationMergeError("environment integer is outside bounds")
    parsed = int(value)
    if not -(2**63) <= parsed <= 2**63 - 1:
        raise EvaluationMergeError("environment integer is outside bounds")
    return parsed


def _bounded_json_float(value: str) -> float:
    if len(value) > 64:
        raise EvaluationMergeError("environment number is outside bounds")
    parsed = float(value)
    if not isfinite(parsed) or not -1e300 <= parsed <= 1e300:
        raise EvaluationMergeError("environment number is outside bounds")
    return parsed


def _validate_json_value(value: object, *, depth: int = 0) -> None:
    if depth > 16:
        raise EvaluationMergeError("environment metadata is nested too deeply")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        if len(value) > 16_384 or "\x00" in value:
            raise EvaluationMergeError("environment string is invalid")
        return
    if isinstance(value, int) and not isinstance(value, bool):
        if not -(2**63) <= value <= 2**63 - 1:
            raise EvaluationMergeError("environment integer is outside bounds")
        return
    if isinstance(value, float):
        if not isfinite(value) or not -1e300 <= value <= 1e300:
            raise EvaluationMergeError("environment number is outside bounds")
        return
    if isinstance(value, Mapping):
        if len(value) > 512:
            raise EvaluationMergeError("environment object has too many fields")
        for key, item in value.items():
            if not isinstance(key, str) or not 1 <= len(key) <= 128:
                raise EvaluationMergeError("environment field name is invalid")
            _validate_json_value(item, depth=depth + 1)
        return
    if isinstance(value, list):
        if len(value) > 10_000:
            raise EvaluationMergeError("environment array is too large")
        for item in value:
            _validate_json_value(item, depth=depth + 1)
        return
    raise EvaluationMergeError("environment contains an unsupported value")


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise EvaluationMergeError(f"environment {field} is invalid")
    return value


def _status_text(
    value: object,
    field: str,
    value_field: str,
    maximum: int,
) -> None:
    record = _mapping(value, field)
    if record.get("status") == "available":
        if set(record) != {"status", value_field} or not _text(
            record[value_field], maximum
        ):
            raise EvaluationMergeError(f"environment {field} is invalid")
    elif record != {"status": "unavailable"}:
        raise EvaluationMergeError(f"environment {field} is invalid")


def _sha(value: object) -> bool:
    return isinstance(value, str) and _SHA256_PATTERN.fullmatch(value) is not None


def _text(value: object, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= maximum
        and "\x00" not in value
    )


def _bundle_paths(values: object) -> tuple[Path, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise EvaluationMergeError("bundle directories must be a sequence")
    if len(values) != BUNDLE_COUNT:
        raise EvaluationMergeError("exactly four bundle directories are required")
    return tuple(_directory_path(value, "bundle") for value in values)


def _directory_path(value: object, label: str) -> Path:
    try:
        path = Path(value)
    except (TypeError, ValueError, RuntimeError):
        raise EvaluationMergeError(f"{label} directory path is invalid") from None
    rendered = str(path)
    if (
        not path.is_absolute()
        or "\x00" in rendered
        or len(rendered) > MAX_PATH_CHARACTERS
        or ".." in path.parts
        or path.name in {"", ".", ".."}
    ):
        raise EvaluationMergeError(f"{label} directory must be absolute")
    return path


def _validate_private_directory(path: Path, label: str) -> os.stat_result:
    current = Path(path.anchor)
    final: Optional[os.stat_result] = None
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError:
            raise EvaluationMergeError(
                f"{label} directory must already exist"
            ) from None
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise EvaluationMergeError(
                f"{label} directory ancestry must be symlink-free"
            )
        final = metadata
    if final is None or final.st_uid != os.geteuid():
        raise EvaluationMergeError(
            f"{label} directory must be owned by this user"
        )
    if stat.S_IMODE(final.st_mode) != 0o700:
        raise EvaluationMergeError(f"{label} directory must have mode 0700")
    return final


def _same_private_directory(
    first: os.stat_result, second: os.stat_result
) -> bool:
    return bool(
        stat.S_ISDIR(first.st_mode)
        and stat.S_ISDIR(second.st_mode)
        and first.st_dev == second.st_dev
        and first.st_ino == second.st_ino
        and first.st_uid == os.geteuid()
        and second.st_uid == os.geteuid()
        and stat.S_IMODE(first.st_mode) == 0o700
        and stat.S_IMODE(second.st_mode) == 0o700
    )


def _same_artifact_state(
    first: os.stat_result,
    second: os.stat_result,
    identity: _ArtifactIdentity,
) -> bool:
    return bool(
        stat.S_ISREG(first.st_mode)
        and stat.S_ISREG(second.st_mode)
        and first.st_dev == identity.device == second.st_dev
        and first.st_ino == identity.inode == second.st_ino
        and first.st_size == identity.size == second.st_size
        and first.st_mtime_ns == identity.modified_ns == second.st_mtime_ns
        and first.st_ctime_ns == identity.changed_ns == second.st_ctime_ns
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m oline_hri.evaluation_merge",
        description="Merge four offline Step 16 benchmark bundles",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    merge = commands.add_parser("merge", help="merge and publish offline reports")
    merge.add_argument(
        "--bundle-dir",
        action="append",
        required=True,
        dest="bundle_dirs",
        type=Path,
        help="private Step 16 bundle directory; provide exactly four",
    )
    merge.add_argument("--output-dir", required=True, type=Path)
    merge.add_argument("--dataset", default=None, type=Path)
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    """Run the offline merge CLI without printing prompt or answer content."""

    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    args = _build_parser().parse_args(argv)
    try:
        suite = load_evaluation_suite(args.dataset)
        result = merge_bundles(suite, tuple(args.bundle_dirs), args.output_dir)
    except (EvaluationError, EvaluationScoringError, EvaluationMergeError):
        print(
            "evaluation merge error: request could not be completed safely",
            file=errors,
        )
        return 2
    print(f"evaluation merge complete: {result.merged_run_id}", file=output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
