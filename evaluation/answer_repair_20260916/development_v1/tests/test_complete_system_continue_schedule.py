"""Offline retention checks for independent sessions after a RAM interruption."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import continue_complete_system_schedule as schedule


class ContinueCompleteSystemScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "03_cascade_r1"
        self.path.mkdir()
        self.frozen = {"source_sha256": {"source": "unchanged"}}
        self.baseline = {"boot_id": "original-boot", "power_mode": "15W", "thermal_trip_events": {"cpu": 0}}
        self.cases = [{"id": str(index), "prompt": f"case {index}", "scenario_id": "scenario", "stratum": "stratum"}
                      for index in range(3)]
        self.rows = [{**case, "index": index, "arm": "cascade", "repetition": 1, "status": status}
                     for index, (case, status) in enumerate(zip(self.cases, ("ok", "interrupted")), 1)]
        self.finish = {**self.baseline, "status": "interrupted", "resident_models": [], "cleanup_errors": [],
                       "telemetry_reader_error": None, "guard_violation": "available memory crossed the runtime floor",
                       "failure": {"type": "SafetyGateError", "message": "available memory crossed the runtime floor"}}
        self.write()

    def write(self):
        (self.path / "manifest.json").write_text(json.dumps({"frozen": self.frozen, "arm": "cascade", "repetition": 1}))
        (self.path / "finish.json").write_text(json.dumps(self.finish))
        (self.path / "observations.jsonl").write_text("".join(json.dumps(row) + "\n" for row in self.rows))

    def inspect(self):
        return schedule.terminal_session(self.path, self.frozen, self.cases, self.baseline, "cascade", 1)

    def test_ram_interruption_is_retained_without_filling_missing_case_or_mutating_files(self):
        before = {path.name: path.read_bytes() for path in self.path.iterdir()}
        result = self.inspect()
        self.assertEqual(result["attempted"], 2)
        self.assertEqual(result["unattempted"], 1)
        self.assertEqual(result["status"], "interrupted")
        self.assertEqual({path.name: path.read_bytes() for path in self.path.iterdir()}, before)
        self.assertEqual(result["artifact_sha256"]["observations.jsonl"], schedule.digest(self.path / "observations.jsonl"))

    def test_original_boot_and_clean_unload_are_required(self):
        for patch in ({"boot_id": "changed-boot"}, {"power_mode": "different-mode"},
                      {"thermal_trip_events": {"cpu": 1}}, {"resident_models": ["model"]},
                      {"cleanup_errors": ["failed unload"]}, {"telemetry_reader_error": "reader died"}):
            with self.subTest(patch=patch):
                original = deepcopy(self.finish)
                self.finish.update(patch)
                self.write()
                with self.assertRaises(ValueError):
                    self.inspect()
                self.finish = original

    def test_non_ram_failure_and_malformed_partial_rows_are_rejected(self):
        self.finish["failure"]["message"] = "temperature crossed limit"
        self.finish["guard_violation"] = "temperature crossed limit"
        self.write()
        with self.assertRaisesRegex(ValueError, "narrow RAM-guard"):
            self.inspect()
        self.finish["failure"]["message"] = self.finish["guard_violation"] = "available memory crossed the runtime floor"
        self.rows[-1]["status"] = "ok"
        self.write()
        with self.assertRaisesRegex(ValueError, "unexpected observation shape"):
            self.inspect()
        self.rows[-1]["status"] = "interrupted"
        self.rows[-1]["id"] = "wrong-id"
        self.write()
        with self.assertRaisesRegex(ValueError, "workload prefix"):
            self.inspect()


if __name__ == "__main__":
    unittest.main()
