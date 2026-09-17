import io
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import oline_hri.evaluation_merge as merge
from oline_hri.evaluation_merge import (
    ANSWER_REVIEW_NAME,
    ENVIRONMENT_NAME,
    MANIFEST_NAME,
    OBSERVATIONS_NAME,
    OUTPUT_NAMES,
    REPORT_NAME,
    SUMMARY_NAME,
    EvaluationMergeError,
    main,
    merge_bundles,
)
from oline_hri.evaluation_runner import CASCADE_STRATEGIES
from oline_hri.evaluation_scoring import ObservationRun


SUITE_SHA = "a" * 64
CONFIG_SHA = "b" * 64
SOURCE_SHA = "c" * 64
GIT_HEAD = "d" * 40


class SourceCoverageTests(unittest.TestCase):
    def test_merge_requires_relationship_grounding_source(self) -> None:
        self.assertIn("src/oline_hri/relationships.py", merge._SOURCE_PATHS)


def _private_directory(parent: Path, name: str) -> Path:
    path = parent / name
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def _private_file(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _run(strategy: str, ordinal: int, *, completed: bool = True) -> ObservationRun:
    run_id = f"run_{ordinal}"
    return ObservationRun(
        header={
            "annotation_status": "pending",
            "config_sha256": CONFIG_SHA,
            "evaluation_seed": 42,
            "evaluation_temperature": 0.0,
            "repetitions": 1,
            "retrieval_limit": 5,
            "run_id": run_id,
            "runtime": {
                "embedding_model_id": "BAAI/bge-small-en-v1.5",
                "embedding_model_revision": "revision",
                "general_large_model": "qwen3:1.7b",
                "large_model": "qwen3:4b",
                "machine": "aarch64",
                "python_version": "3.10.12",
                "small_model": "qwen3:0.6b",
            },
            "started_at": f"2026-09-0{ordinal}T00:00:00Z",
            "strategies": (strategy,),
            "suite_id": "suite_v1",
            "suite_sha256": SUITE_SHA,
        },
        setups=(),
        retrievals=({"slot": ordinal},),
        cases=(),
        trailer={"completed": completed},
        trailer_present=True,
    )


def _environment(run: ObservationRun, ordinal: int) -> dict[str, object]:
    expected = "e" * 64
    source_files = [
        {"path": path, "sha256": str(index % 10) * 64, "size_bytes": index}
        for index, path in enumerate(merge._SOURCE_PATHS, start=1)
    ]
    return {
        "block_device": "mmcblk0",
        "capture_end_monotonic_ns": 200 + ordinal,
        "capture_start_monotonic_ns": 100 + ordinal,
        "dependencies": [
            {"name": "oline-hri", "status": "available", "version": "0.1.0"},
            {"name": "numpy", "status": "available", "version": "2.2.6"},
            {
                "name": "onnxruntime",
                "status": "available",
                "version": "1.23.2",
            },
            {
                "name": "tokenizers",
                "status": "available",
                "version": "0.23.2",
            },
        ],
        "device": {
            "kernel": {"machine": "aarch64", "release": "5.15.136-tegra"},
            "model": {"status": "available", "value": "Jetson Orin Nano"},
            "nvidia": {
                "jetpack_package": {"status": "unavailable"},
                "l4t_core_package": {
                    "status": "available",
                    "version": "36.3.0",
                },
                "nv_tegra_release": {
                    "status": "available",
                    "value": "# R36, REVISION: 3.0",
                },
            },
            "nvpmodel": {"status": "available", "value": "15W\n0"},
            "operating_system": {
                "id": "ubuntu",
                "pretty_name": "Ubuntu 22.04.5 LTS",
                "status": "available",
                "version_id": "22.04",
            },
        },
        "embedding": {
            "assets": [
                {
                    "actual_sha256": expected,
                    "expected_sha256": expected,
                    "path": "onnx/model.onnx",
                    "size_bytes": 100,
                    "status": "available",
                    "verified": True,
                }
            ],
            "model_id": "BAAI/bge-small-en-v1.5",
            "model_revision": "revision",
            "status": "verified",
        },
        "evaluation": {
            "config_sha256": CONFIG_SHA,
            "run_id": run.header["run_id"],
            "suite_sha256": SUITE_SHA,
        },
        "git": {
            "dirty": bool(ordinal % 2),
            "dirty_status_format": "porcelain_v1_z_untracked_all",
            "dirty_status_sha256": str(ordinal) * 64,
            "head": GIT_HEAD,
            "status": "available",
        },
        "ollama": {
            "configured_models": [
                {
                    "digest": "f" * 64,
                    "installed": True,
                    "role": "small",
                    "tag": "qwen3:0.6b",
                },
                {
                    "digest": "a" * 64,
                    "installed": True,
                    "role": "general_large",
                    "tag": "qwen3:1.7b",
                },
                {
                    "digest": "1" * 64,
                    "installed": True,
                    "role": "large",
                    "tag": "qwen3:4b",
                },
            ],
            "status": "available",
            "version": {"status": "available", "value": "0.33.3"},
        },
        "python": {"implementation": "CPython", "version": "3.10.12"},
        "record_type": "benchmark_environment",
        "schema_version": 1,
        "source": {
            "aggregate_algorithm": (
                "sha256-u32be-path-length-path-u64be-content-length-content-v1"
            ),
            "aggregate_sha256": SOURCE_SHA,
            "files": source_files,
            "status": "available",
        },
    }


def _environment_bytes(environment: dict[str, object]) -> bytes:
    return (
        json.dumps(
            environment,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


class MergeBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.suite = object()
        self.runs = tuple(
            _run(strategy, index)
            for index, strategy in enumerate(CASCADE_STRATEGIES, start=1)
        )
        self.merged = ObservationRun(
            header={
                **self.runs[0].header,
                "run_id": "merged_0123456789abcdef01234567",
                "strategies": CASCADE_STRATEGIES,
            },
            setups=(),
            retrievals=(),
            cases=(),
            trailer={"completed": True},
            trailer_present=True,
        )

    def _bundles(
        self,
        root: Path,
        *,
        environments: tuple[dict[str, object], ...] | None = None,
    ) -> tuple[Path, ...]:
        values = (
            tuple(_environment(run, index) for index, run in enumerate(self.runs, 1))
            if environments is None
            else environments
        )
        paths = []
        for index, environment in enumerate(values, start=1):
            path = _private_directory(root, f"bundle_{index}")
            _private_file(path / OBSERVATIONS_NAME, f"run {index}\n".encode())
            _private_file(path / ENVIRONMENT_NAME, _environment_bytes(environment))
            paths.append(path)
        return tuple(paths)

    def _pipeline(self, paths: tuple[Path, ...]):
        load = patch.object(
            merge,
            "parse_observation_jsonl",
            side_effect=lambda text: self.runs[int(text.split()[1]) - 1],
        )
        combine = patch.object(
            merge, "merge_observation_runs", return_value=self.merged
        )
        score = patch.object(
            merge, "score_observations", return_value={"run_id": "merged"}
        )
        summary = patch.object(
            merge, "canonical_summary_json", return_value='{"summary":true}\n'
        )
        report = patch.object(
            merge, "render_summary_markdown", return_value="# Combined report\n"
        )
        review = patch.object(
            merge, "emit_blinded_review_sheet", return_value='{"review":true}\n'
        )
        return [load, combine, score, summary, report, review]

    def test_success_is_deterministic_private_and_uses_declared_retrieval_source(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self._bundles(root)
            output = _private_directory(root, "combined")
            patches = self._pipeline(paths)
            started = [item.start() for item in patches]
            try:
                result = merge_bundles(
                    self.suite,
                    tuple(reversed(paths)),
                    output,
                )
            finally:
                for item in reversed(patches):
                    item.stop()

            self.assertEqual(
                set(path.name for path in output.iterdir()), set(OUTPUT_NAMES)
            )
            for path in output.iterdir():
                metadata = path.lstat()
                self.assertTrue(stat.S_ISREG(metadata.st_mode))
                self.assertEqual(stat.S_IMODE(metadata.st_mode), 0o600)
            self.assertEqual(
                (output / SUMMARY_NAME).read_text(), '{"summary":true}\n'
            )
            report = (output / REPORT_NAME).read_text()
            self.assertIn("# Combined report", report)
            self.assertIn("always_small_no_rag", report)
            self.assertNotIn("prompt", report.lower())
            manifest = json.loads((output / MANIFEST_NAME).read_text())
            self.assertEqual(
                [item["strategy"] for item in manifest["source_bundles"]],
                list(CASCADE_STRATEGIES),
            )
            self.assertEqual(
                manifest["retrieval_source"]["run_id"], self.runs[0].header["run_id"]
            )
            self.assertEqual(
                manifest["source_bundles"][0]["observations_sha256"],
                sha256(b"run 1\n").hexdigest(),
            )
            self.assertEqual(manifest["provenance"]["git"]["head"], GIT_HEAD)
            self.assertNotIn("dirty", manifest["provenance"]["git"])
            self.assertEqual(
                (output / ANSWER_REVIEW_NAME).read_text(), '{"review":true}\n'
            )

        combine = started[1]
        parser = started[0]
        self.assertEqual(
            [call.args[0] for call in parser.call_args_list],
            ["run 4\n", "run 3\n", "run 2\n", "run 1\n"],
        )
        ordered_runs = combine.call_args.args[0]
        self.assertEqual(
            tuple(run.header["strategies"][0] for run in ordered_runs),
            CASCADE_STRATEGIES,
        )
        self.assertEqual(
            combine.call_args.kwargs["retrieval_run_id"], self.runs[0].header["run_id"]
        )
        self.assertEqual(result.merged_run_id, self.merged.header["run_id"])
        self.assertEqual(result.summary_path, output / SUMMARY_NAME)

    def test_provenance_mismatch_fails_before_merge_and_publishes_nothing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environments = tuple(
                _environment(run, index) for index, run in enumerate(self.runs, 1)
            )
            environments[3]["device"]["kernel"]["release"] = "different"
            paths = self._bundles(root, environments=environments)
            output = _private_directory(root, "combined")
            patches = self._pipeline(paths)
            started = [item.start() for item in patches]
            try:
                with self.assertRaisesRegex(EvaluationMergeError, "provenance"):
                    merge_bundles(self.suite, paths, output)
            finally:
                for item in reversed(patches):
                    item.stop()
            self.assertEqual(list(output.iterdir()), [])
            started[1].assert_not_called()

    def test_requires_exactly_four_distinct_single_strategy_complete_runs(self) -> None:
        with self.assertRaisesRegex(EvaluationMergeError, "exactly four"):
            merge_bundles(self.suite, (), "/does/not/matter")

        scenarios = (
            tuple([self.runs[0], self.runs[0], *self.runs[2:]]),
            tuple([_run(CASCADE_STRATEGIES[0], 1, completed=False), *self.runs[1:]]),
            tuple(
                [
                    ObservationRun(
                        header={
                            **self.runs[0].header,
                            "strategies": CASCADE_STRATEGIES[:2],
                        },
                        setups=(),
                        retrievals=({"slot": 1},),
                        cases=(),
                        trailer={"completed": True},
                        trailer_present=True,
                    ),
                    *self.runs[1:],
                ]
            ),
        )
        for index, runs in enumerate(scenarios):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                paths = self._bundles(root)
                output = _private_directory(root, "combined")
                with patch.object(
                    merge,
                    "parse_observation_jsonl",
                    side_effect=lambda text: runs[int(text.split()[1]) - 1],
                ), patch.object(merge, "merge_observation_runs") as combine:
                    with self.assertRaises(EvaluationMergeError):
                        merge_bundles(self.suite, paths, output)
                combine.assert_not_called()

    def test_environment_must_bind_to_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environments = tuple(
                _environment(run, index) for index, run in enumerate(self.runs, 1)
            )
            environments[1]["evaluation"]["run_id"] = "wrong"
            paths = self._bundles(root, environments=environments)
            output = _private_directory(root, "combined")
            patches = self._pipeline(paths)
            started = [item.start() for item in patches]
            try:
                with self.assertRaisesRegex(EvaluationMergeError, "observations"):
                    merge_bundles(self.suite, paths, output)
            finally:
                for item in reversed(patches):
                    item.stop()
            started[1].assert_not_called()

    def test_preexisting_output_aborts_before_source_load_without_overwrite(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self._bundles(root)
            output = _private_directory(root, "combined")
            _private_file(output / MANIFEST_NAME, b"sentinel")
            with patch.object(merge, "parse_observation_jsonl") as load:
                with self.assertRaisesRegex(EvaluationMergeError, "already exists"):
                    merge_bundles(self.suite, paths, output)
            load.assert_not_called()
            self.assertEqual((output / MANIFEST_NAME).read_bytes(), b"sentinel")

    def test_publication_race_cleans_owned_files_and_preserves_racer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self._bundles(root)
            output = _private_directory(root, "combined")
            racer = output / REPORT_NAME
            patches = self._pipeline(paths)

            def race(summary):
                _private_file(racer, b"racer")
                return "# report\n"

            patches[4] = patch.object(
                merge, "render_summary_markdown", side_effect=race
            )
            started = [item.start() for item in patches]
            try:
                with self.assertRaisesRegex(EvaluationMergeError, "already exists"):
                    merge_bundles(self.suite, paths, output)
            finally:
                for item in reversed(patches):
                    item.stop()
            self.assertEqual(racer.read_bytes(), b"racer")
            self.assertEqual(
                set(path.name for path in output.iterdir()), {REPORT_NAME}
            )

    def test_cancellation_is_preserved_and_leaves_output_empty(self) -> None:
        for cancellation in (KeyboardInterrupt(), SystemExit(9)):
            with self.subTest(kind=type(cancellation).__name__):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    paths = self._bundles(root)
                    output = _private_directory(root, "combined")
                    with patch.object(
                        merge,
                        "parse_observation_jsonl",
                        side_effect=cancellation,
                    ):
                        with self.assertRaises(type(cancellation)) as caught:
                            merge_bundles(self.suite, paths, output)
                    if isinstance(cancellation, SystemExit):
                        self.assertEqual(caught.exception.code, 9)
                    self.assertEqual(list(output.iterdir()), [])


class MergeInputSafetyTests(unittest.TestCase):
    def test_environment_rejects_duplicate_noncanonical_and_symlinked_files(
        self,
    ) -> None:
        duplicate = b'{"a":1,"a":2}\n'
        with self.assertRaises(EvaluationMergeError):
            merge._parse_environment(duplicate)

        run = _run(CASCADE_STRATEGIES[0], 1)
        pretty = json.dumps(_environment(run, 1), indent=2).encode() + b"\n"
        with self.assertRaisesRegex(EvaluationMergeError, "canonical"):
            merge._parse_environment(pretty)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = _private_directory(root, "bundle")
            target = root / "target"
            _private_file(target, _environment_bytes(_environment(run, 1)))
            (bundle / ENVIRONMENT_NAME).symlink_to(target)
            _private_file(bundle / OBSERVATIONS_NAME, b"observation\n")
            with patch.object(merge, "parse_observation_jsonl", return_value=run):
                with self.assertRaises(EvaluationMergeError):
                    merge._load_bundle(bundle)

    def test_directories_must_be_absolute_private_owned_and_symlink_free(self) -> None:
        with self.assertRaises(EvaluationMergeError):
            merge._directory_path(Path("relative"), "output")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = _private_directory(root, "private")
            shared = _private_directory(root, "shared")
            shared.chmod(0o750)
            link = root / "link"
            link.symlink_to(private, target_is_directory=True)
            for path in (shared, link, root / "missing"):
                with self.subTest(path=path), self.assertRaises(
                    EvaluationMergeError
                ):
                    with merge._PrivateDirectory(path, label="bundle"):
                        pass


class MergeCliTests(unittest.TestCase):
    def test_cli_loads_selected_suite_and_forwards_exact_four_paths(self) -> None:
        paths = tuple(Path(f"/private/bundle-{index}") for index in range(4))
        result = SimpleNamespace(merged_run_id="merged_safe")
        stdout = io.StringIO()
        stderr = io.StringIO()
        suite = object()
        arguments = ["merge", "--dataset", "/fixture.json", "--output-dir", "/out"]
        for path in paths:
            arguments.extend(("--bundle-dir", str(path)))
        with patch.object(
            merge, "load_evaluation_suite", return_value=suite
        ) as load, patch.object(
            merge, "merge_bundles", return_value=result
        ) as execute:
            code = main(arguments, stdout=stdout, stderr=stderr)
        self.assertEqual(code, 0)
        load.assert_called_once_with(Path("/fixture.json"))
        self.assertIs(execute.call_args.args[0], suite)
        self.assertEqual(execute.call_args.args[1], paths)
        self.assertEqual(execute.call_args.args[2], Path("/out"))
        self.assertIn("merged_safe", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_cli_sanitizes_errors_and_preserves_cancellation(self) -> None:
        arguments = ["merge", "--output-dir", "/out"]
        for index in range(4):
            arguments.extend(("--bundle-dir", f"/bundle-{index}"))
        with patch.object(
            merge, "load_evaluation_suite", return_value=object()
        ), patch.object(
            merge,
            "merge_bundles",
            side_effect=EvaluationMergeError("secret prompt answer"),
        ):
            stdout = io.StringIO()
            stderr = io.StringIO()
            self.assertEqual(main(arguments, stdout=stdout, stderr=stderr), 2)
        self.assertNotIn("secret", stderr.getvalue())
        self.assertNotIn("prompt", stderr.getvalue())

        with patch.object(
            merge, "load_evaluation_suite", return_value=object()
        ), patch.object(
            merge, "merge_bundles", side_effect=KeyboardInterrupt()
        ):
            with self.assertRaises(KeyboardInterrupt):
                main(arguments, stdout=io.StringIO(), stderr=io.StringIO())


if __name__ == "__main__":
    unittest.main()
