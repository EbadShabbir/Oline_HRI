"""Offline validation of the explicit extra-arm startup amendment."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_arc_qwen25_retry as retry


def snapshot():
    return {
        "memory": {"mem_available_kib": 2621440, "swap_used_kib": 393216},
        "temperatures_c": {"cpu": 54.999, "gpu": 51}, "resident_models": [],
        "fan_pwm": 77, "thermal_trip_events": {"cpu": 0, "gpu": 0},
        "power_mode": "NV Power Mode: 15W\n0",
    }


class Qwen25RetryTests(unittest.TestCase):
    def test_permitted_boundary_uses_exact_counters_and_does_not_change_snapshot(self):
        value = snapshot()
        original = deepcopy(value)
        retry.require_retry_start_safe(value)
        self.assertEqual(value, original)
        with self.assertRaisesRegex(retry.arc.SafetyGateError, "128 MiB"):
            retry.arc._require_start_safe(value)

    def test_other_startup_guards_remain_strict(self):
        mutations = [
            ("memory", "mem_available_kib", 2621439),
            ("memory", "swap_used_kib", 393217),
            ("memory", "swap_used_kib", -1),
            ("memory", "swap_used_kib", True),
            ("temperatures_c", "cpu", 55),
            ("temperatures_c", "cpu", float("nan")),
            ("thermal_trip_events", "cpu", 1),
        ]
        for section, key, bad in mutations:
            with self.subTest(section=section, key=key, bad=bad):
                value = snapshot()
                value[section][key] = bad
                with self.assertRaises(retry.arc.SafetyGateError):
                    retry.require_retry_start_safe(value)
        for key, bad in (("resident_models", [{"name": "other:model"}]),
                         ("fan_pwm", 0), ("fan_pwm", None),
                         ("thermal_trip_events", {}), ("temperatures_c", {}),
                         ("power_mode", "NV Power Mode: 25W\n0"),
                         ("power_mode", "NV Power Mode: 15W\n1")):
            with self.subTest(key=key, bad=bad):
                value = snapshot()
                value[key] = bad
                with self.assertRaises(retry.arc.SafetyGateError):
                    retry.require_retry_start_safe(value)

    def test_provenance_is_archived_before_manifest_and_bindings_are_restored(self):
        launcher, protocol = b"exact launcher bytes\n", b"exact protocol bytes\n"
        amendment = retry.execution_amendment(launcher, protocol)
        before_gate, before_writer = retry.arc._require_start_safe, retry.arc._write_new_json
        before_source_hashes = retry.arc.source_hashes()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            start = snapshot()
            manifest = {"arm": "extra", "models": {retry.EXTRA_MODEL: {}},
                        "source_sha256": before_source_hashes}
            with retry.retry_bindings(amendment, launcher, protocol):
                self.assertIs(retry.arc._require_start_safe, retry.require_retry_start_safe)
                retry.arc._write_new_json(directory / "start.json", start)
                self.assertEqual(json.loads((directory / "start.json").read_text()), start)
                self.assertEqual((directory / "execution_launcher.py").read_bytes(), launcher)
                self.assertEqual((directory / "execution_amendment.md").read_bytes(), protocol)
                self.assertEqual(sha256(launcher).hexdigest(), amendment["launcher_sha256"])
                self.assertEqual(json.loads((directory / "execution_amendment.json").read_text()), amendment)
                retry.arc._write_new_json(directory / "manifest.json", manifest)
                saved = json.loads((directory / "manifest.json").read_text())
                self.assertEqual(saved["execution_amendment"], amendment)
                self.assertEqual(saved["source_sha256"], before_source_hashes)
                self.assertNotIn("execution_amendment", manifest)
            self.assertIs(retry.arc._require_start_safe, before_gate)
            self.assertIs(retry.arc._write_new_json, before_writer)
            self.assertEqual(retry.arc.source_hashes(), before_source_hashes)

    def test_bindings_restore_on_exception_and_no_unrecorded_manifest_is_allowed(self):
        gate, writer = retry.arc._require_start_safe, retry.arc._write_new_json
        amendment = retry.execution_amendment(b"launcher", b"protocol")
        with self.assertRaisesRegex(ValueError, "provenance"):
            with retry.retry_bindings(amendment, b"launcher", b"protocol"):
                retry.arc._write_new_json(Path("/not-created/manifest.json"), {})
        self.assertIs(retry.arc._require_start_safe, gate)
        self.assertIs(retry.arc._write_new_json, writer)

    def test_launcher_forwards_only_frozen_dataset_and_exact_extra_arm(self):
        gate, writer = retry.arc._require_start_safe, retry.arc._write_new_json
        def fake_main(argv):
            self.assertEqual(argv, ["--dataset", str(retry.DATASET), "--output-dir", "/tmp/fake-run",
                                    "--arm", "extra", "--extra-model", retry.EXTRA_MODEL])
            self.assertIs(retry.arc._require_start_safe, retry.require_retry_start_safe)
            return 7
        with patch.object(retry.arc, "main", side_effect=fake_main) as main:
            self.assertEqual(retry.main(["--output-dir", "/tmp/fake-run"]), 7)
            self.assertEqual(main.call_count, 1)
        self.assertIs(retry.arc._require_start_safe, gate)
        self.assertIs(retry.arc._write_new_json, writer)


if __name__ == "__main__":
    unittest.main()
