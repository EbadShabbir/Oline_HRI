"""Offline tests for honest, separate recovery of unfinished ARC questions."""

from hashlib import sha256
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_arc_qwen25_continue as continuation


class Qwen25ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.parent = self.root / "parent"
        self.parent.mkdir()
        self.dataset_path = self.root / "frozen.json"
        self.dataset = {"metadata": {"split": "test"}, "cases": [
            {"id": f"case-{index}", "subset": "ARC-Easy", "question": f"Question {index}?",
             "choices": [{"label": "A", "text": "Option A"}, {"label": "B", "text": "Option B"}],
             "answerKey": "A"} for index in range(1, 101)
        ]}
        self.dataset_path.write_text(json.dumps(self.dataset, indent=2))
        full_digest = sha256(self.dataset_path.read_bytes()).hexdigest()
        self.rows = [{"case_id": f"case-{index}", "index": index,
                      "status": "ok" if index < 84 else "interrupted",
                      "correct": index % 2 == 0,
                      "answer": "A"} for index in range(1, 85)]
        row_bytes = b"".join(continuation.arc._canonical_bytes(row) for row in self.rows)
        retry_bytes = Path(continuation.retry.__file__).read_bytes()
        protocol_bytes = b"The archived startup amendment.\n"
        amendment = continuation.retry.execution_amendment(retry_bytes, protocol_bytes)
        amendment["dataset_sha256"] = full_digest
        archived_dataset = continuation.arc._canonical_bytes(self.dataset)
        self.manifest = {
            "arm": "extra", "models": {continuation.retry.EXTRA_MODEL: {"digest": "fixed-artifact"}},
            "dataset_sha256": full_digest,
            "artifact_dataset_sha256": sha256(archived_dataset).hexdigest(),
            "execution_amendment": amendment, "source_sha256": continuation.arc.source_hashes(),
            "config": {"generation": "unchanged"}, "system_prompt": "unchanged prompt",
            "generation_seed": 42, "residency_policy": "sole_model_resident",
        }
        files = {
            "manifest.json": continuation.arc._canonical_bytes(self.manifest),
            "observations.jsonl": row_bytes,
            "finish.json": continuation.arc._canonical_bytes({"status": "interrupted", "cleanup_errors": []}),
            "dataset.json": archived_dataset,
            "execution_amendment.json": continuation.arc._canonical_bytes(amendment),
            "execution_launcher.py": retry_bytes,
            "execution_amendment.md": protocol_bytes,
        }
        for name, raw in files.items():
            (self.parent / name).write_bytes(raw)
        for target, name, value in (
            (continuation.retry, "DATASET", self.dataset_path),
            (continuation.retry, "DATASET_SHA256", full_digest),
            (continuation, "PARENT_OBSERVATIONS_SHA256", sha256(row_bytes).hexdigest()),
        ):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_only_unfinished_cases_are_selected_regardless_of_answer_correctness(self):
        plan = continuation.prepare(self.parent)
        self.assertEqual([case["id"] for case in plan["dataset"]["cases"]],
                         [f"case-{index}" for index in range(84, 101)])
        self.assertEqual(plan["provenance"]["accepted_parent_case_ids"],
                         [f"case-{index}" for index in range(1, 84)])
        self.assertEqual(plan["provenance"]["local_to_original_index"]["1"], 84)
        self.assertTrue(self.rows[-1]["correct"])
        self.assertEqual(plan["dataset"]["cases"][0]["id"], self.rows[-1]["case_id"])
        self.assertEqual(plan["dataset"]["cases"], self.dataset["cases"][83:])
        self.assertNotEqual(plan["provenance"]["derived_dataset_sha256"],
                            plan["provenance"]["full_dataset_sha256"])

    def test_parent_evidence_is_archived_unchanged_with_separate_segment_manifest(self):
        plan = continuation.prepare(self.parent)
        output = self.root / "continuation"
        output.mkdir()
        gate, writer = continuation.arc._require_start_safe, continuation.arc._write_new_json
        manifest = {**self.manifest, "dataset_sha256": plan["provenance"]["derived_dataset_sha256"]}
        with continuation.continuation_bindings(plan):
            continuation.arc._write_new_json(output / "start.json", {"real_counter": 123})
            continuation.arc._write_new_json(output / "manifest.json", manifest)
        saved = json.loads((output / "manifest.json").read_text())
        self.assertEqual(saved["continuation"], plan["provenance"])
        self.assertEqual(saved["execution_amendment"], self.manifest["execution_amendment"])
        for name, raw in plan["parent_files"].items():
            self.assertEqual((output / ("parent_" + name)).read_bytes(), raw)
            self.assertEqual((self.parent / name).read_bytes(), raw)
        self.assertEqual((output / "execution_launcher.py").read_bytes(), plan["retry_bytes"])
        self.assertEqual((output / "continuation_launcher.py").read_bytes(), plan["launcher_bytes"])
        self.assertIs(continuation.arc._require_start_safe, gate)
        self.assertIs(continuation.arc._write_new_json, writer)

    def test_check_only_and_unready_run_do_not_create_output_or_call_inference(self):
        output = self.root / "not-created"
        state = {"ready": False, "snapshot": {"memory": "actual"}, "error": {"message": "startup gate"}}
        for extra_args in (["--check-only"], []):
            with self.subTest(extra_args=extra_args), patch.object(continuation, "readiness", return_value=state), \
                    patch.object(continuation.arc, "main") as main, patch("sys.stdout", new=io.StringIO()):
                result = continuation.main(["--parent-run", str(self.parent), "--output-dir", str(output), *extra_args])
                self.assertEqual(result, 1)
                self.assertFalse(output.exists())
                main.assert_not_called()

    def test_manifest_changes_are_rejected_before_inference_and_bindings_restore(self):
        plan = continuation.prepare(self.parent)
        output = self.root / "reject"
        output.mkdir()
        gate, writer = continuation.arc._require_start_safe, continuation.arc._write_new_json
        changed = {**self.manifest, "models": {continuation.retry.EXTRA_MODEL: {"digest": "different"}},
                   "dataset_sha256": plan["provenance"]["derived_dataset_sha256"]}
        with self.assertRaisesRegex(ValueError, "parent field: models"):
            with continuation.continuation_bindings(plan):
                continuation.arc._write_new_json(output / "start.json", {})
                continuation.arc._write_new_json(output / "manifest.json", changed)
        self.assertFalse((output / "manifest.json").exists())
        self.assertIs(continuation.arc._require_start_safe, gate)
        self.assertIs(continuation.arc._write_new_json, writer)

    def test_diagnostic_policy_checks_real_boundaries_in_both_runtime_guards(self):
        value = {"memory": {"mem_available_kib": 2359296, "swap_used_kib": 786432},
                 "temperatures_c": {"cpu": 54}, "resident_models": [], "fan_pwm": 77,
                 "thermal_trip_events": {"cpu": 0}, "power_mode": "NV Power Mode: 15W\n0"}
        original = json.dumps(value, sort_keys=True)
        continuation.require_diagnostic_start_safe(value)
        self.assertEqual(json.dumps(value, sort_keys=True), original)
        with self.assertRaises(continuation.arc.SafetyGateError):
            continuation.retry.require_retry_start_safe(value)
        for section, key, bad in (("memory", "mem_available_kib", 2359295),
                                  ("memory", "swap_used_kib", 786433),
                                  ("temperatures_c", "cpu", 55),
                                  ("thermal_trip_events", "cpu", 1)):
            changed = json.loads(original)
            changed[section][key] = bad
            with self.subTest(section=section, key=key), self.assertRaises(continuation.arc.SafetyGateError):
                continuation.require_diagnostic_start_safe(changed)
        plan = continuation.prepare(self.parent, diagnostic=True)
        safety = continuation.safety
        old_runtime_limit = safety.MAX_RUNTIME_SWAP_USED_KIB
        memory = {"mem_available_kib": 786432, "swap_used_kib": 900 * 1024}
        with continuation.continuation_bindings(plan), \
                patch.object(safety, "_memory_snapshot", return_value=memory), \
                patch.object(safety, "_temperature_snapshot", return_value={"cpu": 60}), \
                patch.object(safety, "_boot_id", return_value="boot"), \
                patch.object(safety, "_throttle_snapshot", return_value={"cpu": 0}), \
                patch.object(safety, "_resident_models", return_value=()):
            self.assertEqual(safety.MAX_RUNTIME_SWAP_USED_KIB, 1048576)
            safety._require_runtime_safe(boot_id="boot", initial_trip_events={"cpu": 0})
            memory["swap_used_kib"] = 1048577
            with self.assertRaisesRegex(continuation.arc.SafetyGateError, "swap"):
                safety._require_runtime_safe(boot_id="boot", initial_trip_events={"cpu": 0})
            writer = type("Writer", (), {"write": lambda self, record: None})()
            monitor = safety._StreamingSafetyMonitor(writer)
            sample = {"ram": {"total_mb": 8000, "used_mb": 7000},
                      "swap": {"used_mb": 900}, "temperatures_c": {"cpu": 60}}
            monitor(sample)
            self.assertIsNone(monitor.violation)
            sample["swap"]["used_mb"] = 1025
            with patch.object(safety._thread, "interrupt_main") as interrupt:
                monitor(sample)
                interrupt.assert_called_once()
                self.assertIn("swap", monitor.violation)
        self.assertEqual(safety.MAX_RUNTIME_SWAP_USED_KIB, old_runtime_limit)

    def test_diagnostic_archives_distinct_effective_policy_and_restores_on_error(self):
        plan = continuation.prepare(self.parent, diagnostic=True)
        effective = plan["amendment"]
        self.assertFalse(effective["runtime_guards_unchanged"])
        self.assertTrue(effective["parent_feasibility_failure_preserved"])
        self.assertEqual(effective["runtime_limits"]["max_swap_used_kib"], 1048576)
        self.assertEqual(effective["runtime_limits"]["min_available_ram_kib"], 786432)
        self.assertEqual(effective["runtime_limits"]["max_temperature_c_exclusive"], 68)
        output = self.root / "diagnostic"
        output.mkdir()
        gate, writer = continuation.arc._require_start_safe, continuation.arc._write_new_json
        runtime = continuation.safety.MAX_RUNTIME_SWAP_USED_KIB
        manifest = {**self.manifest, "dataset_sha256": plan["provenance"]["derived_dataset_sha256"]}
        with self.assertRaisesRegex(RuntimeError, "test cancellation"):
            with continuation.continuation_bindings(plan):
                continuation.arc._write_new_json(output / "start.json", {"real_counter": 456})
                continuation.arc._write_new_json(output / "manifest.json", manifest)
                raise RuntimeError("test cancellation")
        saved = json.loads((output / "manifest.json").read_text())
        self.assertEqual(saved["execution_amendment"], effective)
        self.assertEqual(json.loads((output / "parent_execution_amendment.json").read_text()),
                         self.manifest["execution_amendment"])
        self.assertEqual((output / "execution_launcher.py").read_bytes(), plan["launcher_bytes"])
        self.assertEqual((output / "parent_execution_launcher.py").read_bytes(), plan["retry_bytes"])
        self.assertIs(continuation.arc._require_start_safe, gate)
        self.assertIs(continuation.arc._write_new_json, writer)
        self.assertEqual(continuation.safety.MAX_RUNTIME_SWAP_USED_KIB, runtime)


if __name__ == "__main__":
    unittest.main()
