"""Offline checks that development budgets fail before device or output access."""
import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("development_guard", Path(__file__).with_name("run_guarded.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class DevelopmentBudgetTests(unittest.TestCase):
    def test_over_budget_fails_before_artifacts_or_inference(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            cases = base / "cases.json"
            cases.write_text(json.dumps([{"id": str(index), "text": "Synthetic offline request.",
                                         "expected_modes": ["none"]} for index in range(13)]))
            args = argparse.Namespace(cases=cases, output_dir=base / "output", max_cases=12)
            with patch.object(guard.runner, "main", side_effect=AssertionError("inference called")), \
                    patch.object(guard, "local_integrity", side_effect=AssertionError("freeze read before budget")):
                with self.assertRaisesRegex(ValueError, "exceeds declared cap 12"):
                    guard.collect(args)
            self.assertFalse(args.output_dir.exists())

    def test_invalid_budget_cannot_bypass_absolute_64_case_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            cases = base / "cases.json"
            cases.write_text(json.dumps([{"id": "one", "text": "Synthetic request.", "expected_modes": ["none"]}]))
            for limit in (0, -1, 65, 10000):
                with self.subTest(limit=limit):
                    args = argparse.Namespace(cases=cases, output_dir=base / "output", max_cases=limit)
                    with self.assertRaisesRegex(ValueError, "between 1 and 64"):
                        guard.collect(args)
                    self.assertFalse(args.output_dir.exists())


if __name__ == "__main__":
    unittest.main()
