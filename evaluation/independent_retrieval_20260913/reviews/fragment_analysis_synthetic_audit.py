"""Extract only three stdlib functions; never import NumPy or collected data."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
TREE = ast.parse((ROOT / "scripts/analyze_independent_retrieval.py").read_text())
NAMES = {"fragment_layout", "audit_prefix", "fragment_overhead"}
GLOBALS = {"Path": Path,
           "check": lambda condition, message, errors: None if condition else errors.append(message),
           "observe_key": lambda row: f"slot_{row['slot']:02d}:{row['case']['id']}"}
exec(compile(ast.Module(body=[node for node in TREE.body if isinstance(node, ast.FunctionDef)
                             and node.name in NAMES], type_ignores=[]), "audited_source_subset", "exec"), GLOBALS)


class FragmentAnalysisChecks(unittest.TestCase):
    def test_suffix_local_index_is_distinct_from_frozen_position(self):
        slot = {"slot": 4, "request_ids": [f"q{i}" for i in range(48)]}
        manifest = {"fragment": {"offset": 13, "request_ids": slot["request_ids"][13:], "planned": 35}}
        rows = [{"case": {"id": f"q{i}"}, "index": i - 12} for i in range(13, 48)]
        summary = {"fragment_offset": 13, "original_planned": 48, "planned": 35,
                   "attempted": 35, "status": "complete"}
        errors = []
        self.assertEqual(GLOBALS["fragment_layout"](manifest, slot, summary, rows, errors), (13, 35))
        self.assertEqual(errors, [])
        rows[0]["index"] = 14
        GLOBALS["fragment_layout"](manifest, slot, summary, rows, errors)
        self.assertIn("fragment local indices differ", errors)

    def test_failed_attempt_remains_in_pair_identity_and_cannot_be_repeated(self):
        schedule = [{"slot": 4, "request_ids": ["a", "b", "c"]}]
        rows = [{"slot": 4, "case": {"id": name}, "status": status}
                for name, status in (("a", "ok"), ("b", "interrupted"), ("c", "ok"))]
        errors = []
        GLOBALS["audit_prefix"](rows, schedule, errors)
        self.assertEqual(errors, [])
        GLOBALS["audit_prefix"](rows[:2] + [rows[1]], schedule, errors)
        self.assertTrue(errors)

    def test_fragment_overhead_is_directory_specific_and_missing_is_unknown(self):
        slot = {"slot": 4}
        events = [{"event": "admission_complete", "slot": 4, "wall_ns": 9_000_000_000},
                  {"event": "fragment_terminal_overhead", "slot": 4,
                   "directory": "/synthetic/later", "wall_ns": 2_000_000_000}]
        errors = []
        function = GLOBALS["fragment_overhead"]
        self.assertEqual(function(Path("/synthetic/original"), slot, {}, events, errors), 9)
        self.assertIsNone(function(Path("/synthetic/missing"), slot, {"fragment": {}}, events, errors))
        self.assertEqual(function(Path("/synthetic/later"), slot, {"fragment": {}}, events, errors), 2)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
