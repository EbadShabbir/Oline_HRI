"""Synthetic comparison/figure integrity tests; no live answers or inference."""
import argparse
import ast
import contextlib
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

DIRECTORY = Path(__file__).resolve().parent
BASE = DIRECTORY.parent / "changing_memory_20260914"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


comparison = module("matched_comparison_test", DIRECTORY / "compare_matched.py")
figure = module("repair_figure_test", DIRECTORY / "render_repair_figure.py")
original_figure = module("original_figure_test", BASE / "render_checkpoint_figure.py")


def fabricated_rows():
    ledger = json.loads((BASE / "frozen_v1/expected_ledger.json").read_text())["checkpoints"]
    rows = []
    for index, expected in enumerate(ledger):
        bid = f"offline-{index}"
        vote = {"blind_id": bid,
                "classification": "appropriate_uncertainty" if expected["expected_kind"] == "uncertainty" else "correct_recall",
                "useful_correct": True, "forbidden_disclosure": False, "disclosed_forbidden_values": [],
                "reason": "Fabricated fixture judgment; not a live answer review."}
        rows.append({"checkpoint_id": expected["checkpoint_id"], "blind_id": bid, "expected": expected,
                     "judgment": vote, "observed": True, "diagnostics": {"status": "delivered"},
                     "delivered_answer": "Fabricated test answer.", "observed_record": {}})
    return rows


class MatchedComparisonTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="clara-matched-comparison-offline-"))
        self.addCleanup(self.cleanup)
        self.baseline = fabricated_rows()
        self.repair = [deepcopy(row) for row in self.baseline if row["expected"]["scenario_id"] in
                       {"cm01", "cm04", "cm07", "cm09"}]

    def cleanup(self):
        for p in self.root.rglob("*"):
            p.chmod(0o700 if p.is_dir() else 0o600)
        self.root.chmod(0o700)
        shutil.rmtree(self.root)

    def fixture(self, name, rows, *, partial=False):
        path = self.root / name
        (path / "frozen_votes").mkdir(parents=True)
        comparison.write_json(path / "provenance.json", {"partial": partial, "human_validation": "pending"})
        comparison.write_json(path / "metrics.json", {"partial": partial, "all": {"planned": len(rows)}})
        comparison.write_json(path / "review_agreement.json", {"resolved_before_diagnostics": True})
        comparison.write_json(path / "frozen_votes/resolved.json", {r["blind_id"]: r["judgment"] for r in rows})
        (path / "reviewed_answers.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
        comparison.seal(path)
        return path

    def test_exact_subset_binding_and_expected_mismatches(self):
        pairs = comparison.bind_rows(self.baseline, self.repair)
        self.assertEqual(len(pairs), 96)
        for key in ("question", "logical_time", "history_mode", "after_restart", "rubric", "authorized_state", "forbidden_values"):
            changed = deepcopy(self.repair)
            e = changed[1]["expected"]
            if key == "rubric":
                e[key]["useful_correct_response"] = "Changed scoring rule."
            elif key == "authorized_state":
                e[key][0]["canonical_text"] = "Different authorized state."
            elif key == "forbidden_values":
                e[key].append("Another forbidden value")
            elif key == "after_restart":
                e[key] = not e[key]
            else:
                e[key] = "changed"
            with self.subTest(field=key), self.assertRaisesRegex(ValueError, "differs"):
                comparison.bind_rows(self.baseline, changed)

    def test_duplicate_unmatched_wrong_count_and_incomplete_scenarios_rejected(self):
        cases = [self.repair[:-1], self.repair + [self.repair[0]], self.repair[1:] + [self.repair[1]]]
        changed = deepcopy(self.repair)
        changed[0]["checkpoint_id"] = "unmatched"
        cases.append(changed)
        for rows in cases:
            with self.assertRaises(ValueError):
                comparison.bind_rows(self.baseline, rows)
        with self.assertRaisesRegex(ValueError, "24 checkpoints"):
            comparison.bind_rows(self.baseline, self.repair[:-1], 95)

    def test_success_disclosure_withholding_transitions_use_frozen_judgments(self):
        stale = next(r for r in self.baseline if r["checkpoint_id"] == "cm01_correction_corrected_retained")
        stale["judgment"].update(classification="incorrect", useful_correct=False,
                                 forbidden_disclosure=True, disclosed_forbidden_values=["rooibos"])
        withheld = next(r for r in self.repair if r["checkpoint_id"] == "cm04_correction_restart_fresh")
        withheld["judgment"].update(classification="no_delivered_answer", useful_correct=False)
        withheld.update(delivered_answer=None, diagnostics={"status": "withheld"})
        pairs = comparison.bind_rows(self.baseline, self.repair)
        overall = comparison.aggregate(pairs)[0]
        self.assertEqual((overall["baseline_planned"], overall["repair_planned"]), (96, 96))
        self.assertEqual((overall["baseline_useful_correct"], overall["repair_useful_correct"]), (95, 95))
        self.assertEqual(overall["delta_forbidden_disclosure"], -1)
        self.assertEqual(overall["delta_withheld"], 1)
        rows = comparison.checkpoint_table(pairs)
        self.assertEqual(sum(r["usefulness_transition"] == "gained_usefulness" for r in rows), 1)
        self.assertEqual(sum(r["usefulness_transition"] == "lost_usefulness" for r in rows), 1)
        self.assertEqual(sum(r["disclosure_transition"] == "disclosure_eliminated" for r in rows), 1)
        for before, after in pairs:
            if before["delivered_answer"] is not None:
                before["delivered_answer"] = "Arbitrary different string containing rooibos."
            if after["delivered_answer"] is not None:
                after["delivered_answer"] = "Another arbitrary string."
        self.assertEqual(comparison.aggregate(pairs)[0], overall)

    def test_recorded_repair_metadata_only_and_nulls_are_not_guessed(self):
        self.repair[0]["observed_record"]["answer_constraint"] = "verified_location"
        self.repair[0]["diagnostics"].update(generation_policy="recorded_policy", actual_generator_models=["OFFLINE_FAKE"],
            route={"policy": "recorded_router", "decision": {"model_size": "small", "memory_required": True}})
        rows, summary = comparison.diagnostic_tables(self.repair)
        self.assertEqual(rows[0]["answer_constraint"], "verified_location")
        self.assertEqual(rows[0]["constraint_source"], "observed_record.answer_constraint")
        self.assertEqual(rows[0]["actual_generator_models"], ["OFFLINE_FAKE"])
        self.assertIsNone(rows[1]["answer_constraint"])
        self.assertFalse(rows[1]["constraint_field_present"])
        self.assertIsNone(rows[1]["nominal_model_size"])
        self.assertEqual(sum(r["checkpoints"] for r in summary if r["field"] == "answer_constraint"), 96)

    def test_wall_latency_scopes_quantiles_and_missing_timing_are_explicit(self):
        pairs = comparison.bind_rows(self.baseline, self.repair)
        for index, (old, new) in enumerate(pairs[:20], 1):
            for row, seconds in ((old, index), (new, 2 * index)):
                row["observed_record"]["wall_ns"] = seconds * 1_000_000_000
                row["diagnostics"]["wall_seconds"] = float(seconds)
        pairs[0][0]["diagnostics"]["status"] = "withheld"
        # A missing wall_ns appears as diagnostic zero in the source analyzer;
        # comparison must retain this as missing, never a zero-latency sample.
        pairs[-1][0]["diagnostics"]["wall_seconds"] = 0.0
        rows = [r for r in comparison.latency_table(pairs) if r["dimensions"] == "all"]
        attempts = next(r for r in rows if r["scope"] == "all_attempts")
        delivered = next(r for r in rows if r["scope"] == "delivered_only")
        self.assertEqual(attempts["baseline_eligible_attempts"], 96)
        self.assertEqual(attempts["baseline_timed_attempts"], 20)
        self.assertEqual(attempts["baseline_missing_timing"], 76)
        self.assertEqual(attempts["baseline_median_seconds"], 10.5)
        self.assertEqual(attempts["baseline_p95_seconds"], 19)
        self.assertEqual(attempts["repair_median_seconds"], 21)
        self.assertEqual(delivered["baseline_eligible_attempts"], 95)
        self.assertEqual(delivered["repair_eligible_attempts"], 96)
        self.assertEqual(delivered["baseline_timed_attempts"], 19)
        with self.assertRaisesRegex(ValueError, "contradicts"):
            broken = deepcopy(pairs[1][1]); broken["diagnostics"]["wall_seconds"] += 1
            comparison.recorded_wall_seconds(broken)

    def test_actual_generators_count_returned_calls_without_route_inference(self):
        pairs = comparison.bind_rows(self.baseline, self.repair)
        pairs[0][0]["diagnostics"].update(actual_generator_models=["SMALL", "LARGE"])
        pairs[0][1]["diagnostics"].update(actual_generator_models=["SMALL"],
                                         route={"decision": {"model_size": "large"}})
        pairs[1][1]["diagnostics"]["actual_generator_models"] = []
        result = [r for r in comparison.generator_counts_table(pairs) if r["dimensions"] == "all"]
        old = next(r for r in result if r["system"] == "baseline")
        new = next(r for r in result if r["system"] == "repair")
        self.assertEqual(old["actual_generator_calls"], 2)
        self.assertEqual(new["actual_generator_calls"], 1)
        self.assertEqual(new["actual_generator_model_calls"], {"SMALL": 1})
        self.assertEqual(new["model_metadata_missing"], 94)
        self.assertEqual(new["checkpoints_with_no_returned_generator_model"], 1)

    def test_sealed_comparison_writes_complete_artifacts_and_does_not_mutate_inputs(self):
        baseline, repair = self.fixture("baseline", self.baseline), self.fixture("repair", self.repair)
        inputs = {str(p): comparison.digest(p / "seal.json") for p in (baseline, repair)}
        args = argparse.Namespace(baseline=baseline, repair=repair, output=self.root / "comparison", expected_checkpoints=96)
        with contextlib.redirect_stdout(io.StringIO()):
            comparison.compare(args)
        comparison.verify_seal(args.output)
        summary = comparison.read_json(args.output / "comparison.json")
        self.assertEqual(summary["matched_checkpoints"], 96)
        self.assertEqual(summary["baseline_full_checkpoints_context_only"], 288)
        self.assertFalse(summary["new_semantic_scoring"])
        self.assertFalse(summary["inference"])
        self.assertIn("not held-out", (args.output / "README.md").read_text())
        self.assertEqual({str(p): comparison.digest(p / "seal.json") for p in (baseline, repair)}, inputs)
        with self.assertRaises(FileExistsError):
            comparison.compare(args)

    def test_partial_unfrozen_vote_and_tampered_analysis_rejected(self):
        partial = self.fixture("partial", self.repair, partial=True)
        with self.assertRaisesRegex(ValueError, "final assistant"):
            comparison.load_analysis(partial)
        path = self.fixture("tampered", self.repair)
        rowpath = path / "reviewed_answers.jsonl"
        rowpath.chmod(0o600)
        rowpath.write_text(rowpath.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "Seal mismatch"):
            comparison.load_analysis(path)
        mismatched = deepcopy(self.repair)
        mismatched[0]["blind_id"] = "absent-vote"
        path = self.fixture("wrongvote", mismatched)
        # The fixture binds votes by row ID, so introduce a different sealed
        # resolved vote while preserving all other final-analysis structure.
        path.chmod(0o700); (path / "seal.json").chmod(0o600); (path / "seal.json").unlink()
        votes = path / "frozen_votes/resolved.json"; votes.chmod(0o600)
        value = comparison.read_json(votes); value["absent-vote"]["reason"] = "Changed frozen vote"
        votes.write_text(json.dumps(value)); comparison.seal(path)
        with self.assertRaisesRegex(ValueError, "bind its frozen"):
            comparison.load_analysis(path)

    def test_figure_mapping_and_stage_positions_match_original_with_96_and_288(self):
        self.assertEqual(figure.STAGES, original_figure.STAGES)
        self.assertEqual(figure.COLORS, original_figure.COLORS)
        select = lambda path: ast.dump(next(n for n in ast.parse(path.read_text()).body
            if isinstance(n, ast.FunctionDef) and n.name == "figure_code"), include_attributes=False)
        self.assertEqual(select(DIRECTORY / "render_repair_figure.py"), select(BASE / "render_checkpoint_figure.py"))
        for name, rows, count in (("figure96", self.repair, 96), ("figure288", self.baseline, 288)):
            cells, scenarios = figure.load_cells(self.fixture(name, rows))
            self.assertEqual(len(cells), count)
            self.assertEqual(len(scenarios), count // 24)
            self.assertEqual({r["checkpoint_id"] for r in rows}, {c["checkpoint_id"] for c in cells})
            self.assertEqual([c["column"] for c in cells[:24]], list(range(1, 25)))

    def test_figure_refuses_duplicate_incomplete_and_misbound_stages(self):
        for name, rows in (("figure_missing", self.repair[:-1]),
                           ("figure_duplicate", self.repair[:-1] + [self.repair[0]])):
            with self.assertRaises(ValueError):
                figure.load_cells(self.fixture(name, rows))
        changed = deepcopy(self.repair)
        changed[0]["expected"]["branch"] = "expiry"
        with self.assertRaisesRegex(ValueError, "Stage identity"):
            figure.load_cells(self.fixture("figure_misbound", changed))


if __name__ == "__main__":
    unittest.main()
