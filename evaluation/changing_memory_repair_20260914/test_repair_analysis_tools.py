"""Offline analysis regressions; fabricated answers are never live observations."""
import argparse
import ast
import contextlib
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest

DIRECTORY = Path(__file__).resolve().parent
ROOT = DIRECTORY.parents[1]
sys.path.insert(0, str(ROOT))
from tests import test_analysis_changing_memory as fixture_tests


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


analysis = module("repair_analysis", DIRECTORY / "analyze_repair.py")
auditor = module("repair_auditor", DIRECTORY / "audit_repair_collection.py")
tables = module("repair_tables", DIRECTORY / "render_repair_tables.py")
BASE = ROOT / "evaluation/changing_memory_20260914"


def authored(path):
    return tuple(json.loads((path / name).read_text()) for name in ("runtime.json", "expected_ledger.json"))


class RepairAnalysisTests(unittest.TestCase):
    def test_counts_derive_full_baseline_and_targeted_subset(self):
        for source, expected in ((BASE / "frozen_v1", (288, 12, 36, 72, 108, 108)),
                                 (DIRECTORY / "authored_v1", (96, 4, 12, 24, 36, 36))):
            runtime, ledger = authored(source)
            for tool in (analysis, auditor, tables):
                with self.subTest(source=source, tool=tool.__name__):
                    counts = tool.workload_counts(runtime, ledger)
                    self.assertEqual(tuple(counts[k] for k in ("planned_checkpoints", "scenario_count",
                        "independent_databases", "scheduled_segments", "history_pairs", "post_restart_checkpoints")), expected)
                    self.assertEqual(counts["stage_history_groups"], 24)

    def test_truncation_duplicate_and_ledger_drift_rejected(self):
        for mutation in ("drop_checkpoint", "duplicate_checkpoint", "drop_branch", "duplicate_branch",
                         "wrong_question", "wrong_time", "wrong_history", "wrong_restart", "duplicate_operation",
                         "no_restart", "forget_in_expiry"):
            runtime, ledger = authored(DIRECTORY / "authored_v1")
            first = ledger["checkpoints"][0]
            if mutation == "drop_checkpoint":
                ledger["checkpoints"].pop(); ledger["checkpoint_count"] -= 1
            elif mutation == "duplicate_checkpoint":
                ledger["checkpoints"].append(deepcopy(first)); ledger["checkpoint_count"] += 1
            elif mutation == "drop_branch":
                runtime["branches"].pop()
            elif mutation == "duplicate_branch":
                runtime["branches"].append(deepcopy(runtime["branches"][0]))
            elif mutation == "wrong_question":
                first["question"] = "A different authored request?"
            elif mutation == "wrong_time":
                first["logical_time"] = "2026-10-01T12:01:00+00:00"
            elif mutation == "wrong_history":
                first["history_mode"] = "fresh"
            elif mutation == "wrong_restart":
                first["after_restart"] = True
            elif mutation == "duplicate_operation":
                runtime["branches"][0]["operations"][1]["id"] = runtime["branches"][0]["operations"][0]["id"]
            elif mutation == "no_restart":
                runtime["branches"][0]["operations"] = [op for op in runtime["branches"][0]["operations"] if op["op"] != "restart"]
            else:
                expiry = next(b for b in runtime["branches"] if b["branch"] == "expiry")
                expiry["operations"].append({"id": "invalid-forget", "op": "forget"})
            for tool in (analysis, auditor, tables):
                with self.subTest(mutation=mutation, tool=tool.__name__), self.assertRaises(ValueError):
                    tool.workload_counts(runtime, ledger)

    def test_diagnostic_vote_and_aggregation_functions_unchanged(self):
        # Only workload admission, workload provenance and report text changed;
        # the old semantics/evidence parser/frozen vote handling remain identical.
        pairs = ((Path("scripts/analyze_changing_memory_v2.py"), DIRECTORY / "analyze_repair.py",
                  {"load_inputs", "prepare", "report", "resolve"}),
                 (BASE / "audit_collection.py", DIRECTORY / "audit_repair_collection.py", {"audit_collection"}),
                 (BASE / "render_report_tables.py", DIRECTORY / "render_repair_tables.py", {"load_inputs", "render"}))
        for old, new, changed in pairs:
            original = ast.parse((ROOT / old if not old.is_absolute() else old).read_text())
            revised = ast.parse(new.read_text())
            select = lambda tree: {node.name: ast.dump(node, include_attributes=False) for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name not in changed | {"workload_counts"}}
            self.assertEqual(select(original), select(revised), new.name)
        helpers = []
        for file in ("analyze_repair.py", "audit_repair_collection.py", "render_repair_tables.py"):
            tree = ast.parse((DIRECTORY / file).read_text())
            helpers.append(ast.dump(next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "workload_counts")))
        self.assertEqual(len(set(helpers)), 1)
        self.assertEqual(tables.ANALYZER_V2_SHA256, analysis.digest(DIRECTORY / "analyze_repair.py"))

    def final_fixture(self, subset):
        fixture = fixture_tests.ChangingMemoryAnalysisTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        if subset:
            selected = {"cm01", "cm04", "cm07", "cm09"}
            fixture.freeze.chmod(0o700)
            for path in fixture.freeze.iterdir():
                path.chmod(0o600)
            (fixture.freeze / "seal.json").unlink()
            for name in ("runtime.json", "expected_ledger.json"):
                (fixture.freeze / name).write_bytes((DIRECTORY / "authored_v1" / name).read_bytes())
            analysis.seal(fixture.freeze)
            fixture.rows = [r for r in fixture.rows if r["scenario_id"] in selected]
            fixture.replace_rows(fixture.rows)
        analysis.seal(fixture.run)
        prepared, reviews, final = (fixture.directory / name for name in ("prepared", "reviews", "final"))
        with contextlib.redirect_stdout(io.StringIO()):
            analysis.prepare(argparse.Namespace(freeze=fixture.freeze, run=[fixture.run], output=prepared, allow_partial=False))
            a, b = fixture.directory / "a.json", fixture.directory / "b.json"
            analysis.write(a, fixture.votes(prepared, "offline-A")); analysis.write(b, fixture.votes(prepared, "offline-B"))
            analysis.seal_reviews(argparse.Namespace(prepared=prepared, review_a=a, review_b=b, output=reviews))
            analysis.resolve(argparse.Namespace(prepared=prepared, reviews=reviews, output=final,
                                              adjudication=None, allow_partial=False))
        counts = analysis.workload_counts(*authored(fixture.freeze))
        audit = {"freeze_directory": str(fixture.freeze), "run_directory": str(fixture.run),
                 "freeze_seal_sha256": analysis.digest(fixture.freeze / "seal.json"),
                 "run_seal_sha256": analysis.digest(fixture.run / "seal.json"),
                 "integrity_pass": True, "integrity_violations": [],
                 "counts": {k: counts[k] for k in ("planned_checkpoints", "scheduled_segments", "independent_databases")}}
        audit["counts"]["unique_observed_checkpoints"] = counts["planned_checkpoints"]
        audit_path = fixture.directory / "audit.json"
        analysis.write(audit_path, audit)
        return fixture, prepared, final, audit_path, counts

    def test_full_and_subset_offline_pipeline_preserves_reviews_counts_and_labels(self):
        for subset in (False, True):
            fixture, prepared, final, audit_path, counts = self.final_fixture(subset)
            output = fixture.directory / "tables"
            with contextlib.redirect_stdout(io.StringIO()):
                tables.render(argparse.Namespace(analysis=final, audit=audit_path, output=output))
            for path in (prepared, final, output):
                analysis.verify_seal(path)
            metrics = json.loads((final / "metrics.json").read_text())
            self.assertEqual(metrics["all"]["planned"], counts["planned_checkpoints"])
            self.assertEqual(metrics["all"]["useful_correct"], counts["planned_checkpoints"])
            self.assertEqual(metrics["history_pairs"]["count"], counts["history_pairs"])
            self.assertEqual(metrics["workload"], counts)
            self.assertIn("not held-out", (final / "report.md").read_text())
            if subset:
                for name in ("report.md", "acknowledgments.md"):
                    self.assertNotIn("288", (final / name).read_text())
                self.assertNotIn("twelve scenarios", (output / "README.md").read_text())
            packets = analysis.read_lines(prepared / "public/packets.jsonl")
            self.assertTrue(all(set(p) == {"blind_id", "question", "authorized_state", "rubric", "delivered_answer"} for p in packets))

    def test_wrong_audit_denominator_and_binding_rejected(self):
        fixture, prepared, final, audit_path, counts = self.final_fixture(True)
        original = json.loads(audit_path.read_text())
        for mutation in ("count", "seal"):
            revised = deepcopy(original)
            if mutation == "count":
                revised["counts"]["planned_checkpoints"] = 288
            else:
                revised["run_seal_sha256"] = "bad"
            audit_path.write_text(json.dumps(revised))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                tables.load_inputs(final, audit_path)


if __name__ == "__main__":
    unittest.main()
