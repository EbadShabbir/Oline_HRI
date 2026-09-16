"""Offline report-table checks using fabricated judgments; no model inference."""

import argparse
import contextlib
from copy import deepcopy
import csv
import importlib.util
import io
import json
from pathlib import Path
import unittest

from tests import test_analysis_changing_memory as baseline_tests


ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


renderer = module("changing_memory_report_tables", "evaluation/changing_memory_20260914/render_report_tables.py")
analysis = module("changing_memory_report_analysis_v2", "scripts/analyze_changing_memory_v2.py")


def fabricated_reviewed_rows():
    ledger = json.loads((ROOT / "evaluation/changing_memory_20260914/authored_v2/expected_ledger.json").read_text())["checkpoints"]
    return [{"checkpoint_id": e["checkpoint_id"], "expected": e, "observed": True,
             "delivered_answer": "Fabricated offline text; labels are provided independently.",
             "judgment": {"classification": "appropriate_uncertainty" if e["expected_kind"] == "uncertainty" else "correct_recall",
                          "useful_correct": True, "forbidden_disclosure": False, "disclosed_forbidden_values": []},
             "diagnostics": {"status": "delivered"},
             "observed_record": {"calls": [{"purpose": "generation", "requested_model": "OFFLINE_FAKE",
                                            "actual_model": "OFFLINE_FAKE", "status": "ok"}]}}
            for e in ledger]


class ReportTableTests(unittest.TestCase):
    def test_stage_history_kind_restart_and_scenario_denominators(self):
        rows = fabricated_reviewed_rows()
        pairs = renderer.expected_pairs(rows)
        tables = renderer.build_tables(rows, pairs, {"integrity_pass": True, "integrity_violations": [], "counts": {}})
        self.assertEqual(len(tables["stage_history"]["rows"]), 24)
        self.assertTrue(all(r["planned"] == r["useful_correct"] == 12 for r in tables["stage_history"]["rows"]))
        for name in ("stage_history", "restart_history", "expected_kind_history", "expected_kind_restart_history",
                     "branch_restart_history", "scenarios"):
            self.assertEqual(sum(r["planned"] for r in tables[name]["rows"]), 288, name)
        self.assertEqual(len(tables["scenarios"]["rows"]), 12)
        self.assertTrue(all(r["planned"] == 24 and r["correction_useful_correct"] == 10
                            and r["deletion_useful_correct"] == r["expiry_useful_correct"] == 7
                            for r in tables["scenarios"]["rows"]))
        self.assertEqual(sum(r["planned"] for r in tables["restart_history"]["rows"] if r["restart_phase"] == "after"), 108)
        self.assertEqual(sum(r["planned"] for r in tables["expected_kind_history"]["rows"] if r["expected_kind"] == "uncertainty"), 144)

    def test_pair_success_and_disclosure_transitions_include_withholding(self):
        rows = fabricated_reviewed_rows()
        by_id = {r["checkpoint_id"]: r for r in rows}
        retained = by_id["cm01_correction_corrected_retained"]
        retained["judgment"].update(useful_correct=False, forbidden_disclosure=True, disclosed_forbidden_values=["rooibos"])
        fresh = by_id["cm04_correction_restart_fresh"]
        fresh["judgment"].update(useful_correct=False, classification="no_delivered_answer")
        fresh.update(delivered_answer=None, diagnostics={"status": "withheld"})
        pairs = renderer.expected_pairs(rows)
        aggregate, detail = renderer.pair_tables(rows, pairs)
        all_pairs = next(r for r in aggregate if r["branch"] == r["restart_phase"] == "all")
        self.assertEqual(all_pairs["pairs"], 108)
        self.assertEqual(all_pairs["success_both"], 106)
        self.assertEqual(all_pairs["success_retained_only"], 1)
        self.assertEqual(all_pairs["success_fresh_only"], 1)
        self.assertEqual(all_pairs["success_neither"], 0)
        self.assertEqual(all_pairs["disclosure_retained_only"], 1)
        self.assertEqual(all_pairs["revoked_subject_disclosure_retained_only"], 1)
        self.assertEqual(all_pairs["disclosure_neither"], 107)
        for branch, count in (("correction", 48), ("deletion", 24), ("expiry", 36)):
            group = next(r for r in aggregate if r["branch"] == branch and r["restart_phase"] == "all")
            self.assertEqual(group["pairs"], count)
            for prefix in ("success", "disclosure", "revoked_subject_disclosure"):
                self.assertEqual(sum(group[prefix + "_" + k] for k in ("both", "retained_only", "fresh_only", "neither")), count)
        self.assertEqual(renderer.basic(rows)["withheld"], 1)
        self.assertEqual(renderer.basic(rows)["useful_correct"], 286)
        self.assertEqual(len(detail), 108)

    def test_disclosure_scopes_use_judgments_and_keep_unstored_values_separate(self):
        rows = fabricated_reviewed_rows()
        expiry = next(r for r in rows if r["checkpoint_id"] == "cm01_expiry_at_retained")
        for value, expected in (("rooibos", (True, True, False)), ("Maple Pavilion", (False, True, False)),
                                ("jasmine", (False, False, True))):
            expiry["judgment"].update(forbidden_disclosure=True, disclosed_forbidden_values=[value])
            observed = tuple(renderer.disclosure_scope(expiry, scope)[1] for scope in
                             ("expired_subject", "any_expired_fact", "unstored_replacement_deletion_or_expiry"))
            self.assertEqual(observed, expected)
        historical = next(r for r in rows if r["checkpoint_id"] == "cm01_correction_historical_retained")
        historical["judgment"].update(forbidden_disclosure=True, disclosed_forbidden_values=["rooibos"])
        self.assertEqual(renderer.disclosure_scope(historical, "stale_subject_broad_correction"), (True, True))
        self.assertEqual(renderer.disclosure_scope(historical, "stale_subject_current_replacement"), (False, False))
        counts = {r["scope"]: r["eligible_planned"] for r in renderer.disclosure_tables(rows)
                  if r["history_mode"] == r["restart_phase"] == "all"}
        self.assertEqual(counts, {"all_forbidden": 288, "stale_subject_broad_correction": 96,
                                 "stale_subject_current_replacement": 48, "deleted_subject": 72,
                                 "expired_subject": 60, "any_expired_fact": 60,
                                 "unstored_replacement_deletion_or_expiry": 132})
        original = renderer.basic(rows)
        for row in rows:
            row["delivered_answer"] = "Entirely different arbitrary text, rooibos jasmine Maple Pavilion."
        self.assertEqual(renderer.basic(rows), original)
        self.assertEqual(counts, {r["scope"]: r["eligible_planned"] for r in renderer.disclosure_tables(rows)
                                 if r["history_mode"] == r["restart_phase"] == "all"})

    def test_actual_generation_calls_are_distinct_from_nominal_route_and_classifier(self):
        row = fabricated_reviewed_rows()[0]
        row["observed_record"] = {
            "route": {"policy": "legacy", "decision": {"memory_required": True, "model_size": "large"}},
            "generation_policy": "offline_fallback_fixture", "fallback_from_model": "OFFLINE_LARGE",
            "calls": [{"purpose": "memory_classifier", "requested_model": "OFFLINE_SMALL", "actual_model": "OFFLINE_SMALL"},
                      {"purpose": "generation", "requested_model": "OFFLINE_LARGE", "actual_model": None, "status": "error"},
                      {"purpose": "generation", "requested_model": "OFFLINE_SMALL", "actual_model": "OFFLINE_SMALL", "status": "ok"}]}
        details, calls, routes, aggregate = renderer.selection_tables([row])
        self.assertEqual(details[0]["nominal_model_size"], "large")
        self.assertEqual(details[0]["requested_generation_models"], ["OFFLINE_LARGE", "OFFLINE_SMALL"])
        self.assertEqual(details[0]["actual_generation_models"], [None, "OFFLINE_SMALL"])
        self.assertEqual(details[0]["generation_call_count"], 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(sum(r["calls"] for r in aggregate if r["branch"] == "all"), 2)
        self.assertEqual(routes[0]["checkpoints"], 1)

    def final_fixture(self):
        fixture = baseline_tests.ChangingMemoryAnalysisTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        analysis.seal(fixture.run)
        prepared, reviews = fixture.directory / "prepared", fixture.directory / "reviews"
        final = fixture.directory / "analysis_v2"
        with contextlib.redirect_stdout(io.StringIO()):
            analysis.prepare(argparse.Namespace(freeze=fixture.freeze, run=[fixture.run], output=prepared, allow_partial=False))
            a, b = fixture.directory / "a.json", fixture.directory / "b.json"
            analysis.write(a, fixture.votes(prepared, "offline-A")); analysis.write(b, fixture.votes(prepared, "offline-B"))
            analysis.seal_reviews(argparse.Namespace(prepared=prepared, review_a=a, review_b=b, output=reviews))
            analysis.resolve(argparse.Namespace(prepared=prepared, reviews=reviews, adjudication=None, output=final, allow_partial=False))
        audit = {"freeze_directory": str(fixture.freeze), "run_directory": str(fixture.run),
                 "freeze_seal_sha256": analysis.digest(fixture.freeze / "seal.json"),
                 "run_seal_sha256": analysis.digest(fixture.run / "seal.json"),
                 "integrity_pass": True, "integrity_violations": [],
                 "counts": {"planned_checkpoints": 288, "unique_observed_checkpoints": 288,
                            "scheduled_segments": 72, "independent_databases": 36},
                 "history_exposure": {"counts": {"all_scored_checkpoints": {"checkpoints": 288}}}}
        audit_path = fixture.directory / "collection_audit.json"
        analysis.write(audit_path, audit)
        return fixture, final, audit_path

    def test_final_sealed_tables_and_input_provenance(self):
        fixture, final, audit_path = self.final_fixture()
        before = {str(p): analysis.digest(p) for p in (final / "seal.json", audit_path)}
        output = fixture.directory / "tables"
        with contextlib.redirect_stdout(io.StringIO()):
            renderer.render(argparse.Namespace(analysis=final, audit=audit_path, output=output))
        renderer.verify_seal(output)
        provenance = json.loads((output / "provenance.json").read_text())
        self.assertEqual(provenance["input_sha256"], before)
        self.assertFalse(provenance["semantic_scoring_performed"])
        self.assertFalse(provenance["inference_performed"])
        self.assertEqual(provenance["table_rows"]["stage_history"], 24)
        self.assertEqual(provenance["table_rows"]["history_pair_details"], 108)
        self.assertEqual(provenance["table_rows"]["checkpoint_model_selections"], 288)
        with (output / "overall.csv").open() as stream:
            row = next(csv.DictReader(stream))
        self.assertEqual(row["useful_correct"], "288")
        self.assertEqual(output.stat().st_mode & 0o222, 0)
        self.assertEqual({str(p): analysis.digest(p) for p in (final / "seal.json", audit_path)}, before)
        with self.assertRaises(FileExistsError):
            renderer.render(argparse.Namespace(analysis=final, audit=audit_path, output=output))

    def test_partial_wrong_binding_and_tampered_inputs_rejected_but_audit_failure_preserved(self):
        fixture, final, audit_path = self.final_fixture()
        audit = json.loads(audit_path.read_text())
        bad = {**audit, "run_seal_sha256": "wrong"}
        audit_path.write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError, "does not bind"):
            renderer.load_inputs(final, audit_path)
        failed = {**audit, "integrity_pass": False, "integrity_violations": [{"code": "offline_fixture"}]}
        audit_path.write_text(json.dumps(failed))
        rows, pairs, _, loaded_audit = renderer.load_inputs(final, audit_path)
        self.assertFalse(renderer.build_tables(rows, pairs, loaded_audit)["collection_audit"]["rows"][0]["integrity_pass"])
        metrics_path = final / "metrics.json"
        metrics_path.chmod(0o600)
        metrics_path.write_text("{}")
        with self.assertRaisesRegex(ValueError, "Seal mismatch"):
            renderer.load_inputs(final, audit_path)

    def test_partial_preparation_cannot_be_labeled_final(self):
        fixture, final, audit_path = self.final_fixture()
        final.chmod(0o700)
        provenance_path = final / "provenance.json"
        provenance_path.chmod(0o600)
        provenance = json.loads(provenance_path.read_text())
        provenance["partial"] = True
        provenance_path.write_text(json.dumps(provenance))
        seal_path = final / "seal.json"
        seal_path.chmod(0o600); seal_path.unlink()
        analysis.seal(final)
        with self.assertRaisesRegex(ValueError, "partial analysis"):
            renderer.load_inputs(final, audit_path)


if __name__ == "__main__":
    unittest.main()
