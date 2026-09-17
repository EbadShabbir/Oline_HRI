"""Offline analysis integrity tests; fabricated answers are not observations."""

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("changing_memory_analysis", ROOT / "scripts/analyze_changing_memory.py")
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


class ChangingMemoryAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="clara-changing-analysis-offline-"))
        self.addCleanup(self.remove_temporary)
        self.freeze = self.directory / "freeze"
        self.freeze.mkdir()
        authored = ROOT / "evaluation/changing_memory_20260914/authored_v2"
        for name in ("runtime.json", "expected_ledger.json"):
            shutil.copyfile(authored / name, self.freeze / name)
        self.ledger = json.loads((self.freeze / "expected_ledger.json").read_text())["checkpoints"]
        runtime = json.loads((self.freeze / "runtime.json").read_text())
        operations = {op["checkpoint_id"]: op for b in runtime["branches"] for op in b["operations"] if op["op"] == "ask"}
        analysis.seal(self.freeze)
        self.run = self.directory / "run"; self.run.mkdir()
        self.rows = []
        for e in self.ledger:
            records = [{**r, "id": r["record_key"], "status": "active", "consent_status": "confirmed",
                        "valid_from": r["stored_at"]} for r in e["authorized_state"]]
            required = [r for r in records if r["record_key"] in e["required_record_keys"]]
            self.rows.append({"checkpoint_id": e["checkpoint_id"], "op": operations[e["checkpoint_id"]],
                "logical_time": e["logical_time"], "branch_id": e["scenario_id"] + "_" + e["branch"],
                "scenario_id": e["scenario_id"], "branch": e["branch"],
                "process": {"pid": 102 if e["after_restart"] else 101, "boot_id": "offline", "process_start_ticks": "102" if e["after_restart"] else "101"},
                "database_identity": {"path": e["scenario_id"] + "_" + e["branch"] + ".db", "device": 1,
                                      "inode": int(e["scenario_id"][2:]) * 3 + {"correction": 0, "deletion": 1, "expiry": 2}[e["branch"]]},
                "status": "delivered", "delivered_answer": e["expected_value"] or "I do not know that information.",
                "database_before": {"memory_item": records}, "supplied_records": required,
                "retrieval_calls": [{"status": "ok", "matches": [{"memory": r} for r in required]}],
                "calls": [{"purpose": "generation", "actual_model": "OFFLINE_FAKE", "requested_model": "OFFLINE_FAKE"}],
                "original_disclosure_present_in_history": e["history_mode"] == "retained"})
        analysis.write_lines(self.run / "answers.jsonl", self.rows)

    def remove_temporary(self):
        for path in self.directory.rglob("*"):
            path.chmod(0o700 if path.is_dir() else 0o600)
        self.directory.chmod(0o700)
        shutil.rmtree(self.directory)

    def prepare(self, *, partial=False):
        output = self.directory / "prepared"
        if not (self.run / "seal.json").exists():
            analysis.seal(self.run)
        analysis.prepare(argparse.Namespace(freeze=self.freeze, run=[self.run], output=output, allow_partial=partial))
        return output

    def replace_rows(self, rows):
        self.run.chmod(0o700)
        for path in self.run.iterdir():
            path.chmod(0o600); path.unlink()
        analysis.write_lines(self.run / "answers.jsonl", rows)

    def votes(self, prepared, reviewer_id):
        packets = analysis.read_lines(prepared / "public/packets.jsonl")
        rows = []
        for p in packets:
            unknown = "Explicitly say" in p["rubric"]["required_behavior"]
            rows.append({"blind_id": p["blind_id"], "classification": "appropriate_uncertainty" if unknown else "correct_recall",
                         "useful_correct": True, "forbidden_disclosure": False, "disclosed_forbidden_values": [],
                         "reason": "Offline fabricated answer exactly meets the authored expectation."})
        return {"reviewer_id": reviewer_id, "human_validation": "pending",
                "packet_sha256": analysis.digest(prepared / "public/packets.jsonl"), "judgments": rows}

    def test_prepare_blinds_diagnostics_and_pairs_equal_packets(self):
        prepared = self.prepare()
        packets = analysis.read_lines(prepared / "public/packets.jsonl")
        for packet in packets:
            self.assertEqual(set(packet), {"blind_id", "question", "authorized_state", "rubric", "delivered_answer"})
        self.assertNotIn("OFFLINE_FAKE", (prepared / "public/packets.jsonl").read_text())
        self.assertLess(len(packets), 288)
        mapping = json.loads((prepared / "private/mapping.json").read_text())
        self.assertEqual(sum(len(r["checkpoint_ids"]) for r in mapping), 288)
        analysis.verify_seal(prepared)

    def test_duplicate_attempt_rejected_and_missing_requires_partial(self):
        self.replace_rows(self.rows + [self.rows[0]])
        with self.assertRaisesRegex(ValueError, "more than once"):
            self.prepare()
        self.replace_rows(self.rows[:-1])
        with self.assertRaisesRegex(ValueError, "missing explicit"):
            self.prepare()
        prepared = self.prepare(partial=True)
        self.assertEqual(len(json.loads((prepared / "private/provenance.json").read_text())["missing_checkpoints"]), 1)

    def test_resolution_seals_votes_and_counts_all_288(self):
        prepared = self.prepare()
        a, b = self.directory / "a.json", self.directory / "b.json"
        analysis.write(a, self.votes(prepared, "offline-A")); analysis.write(b, self.votes(prepared, "offline-B"))
        reviews = self.directory / "reviews"
        analysis.seal_reviews(argparse.Namespace(prepared=prepared, review_a=a, review_b=b, output=reviews))
        output = self.directory / "analysis"
        analysis.resolve(argparse.Namespace(prepared=prepared, reviews=reviews, adjudication=None,
                                            output=output, allow_partial=False))
        metrics = json.loads((output / "metrics.json").read_text())
        self.assertEqual(metrics["all"]["useful_correct"], 288)
        self.assertEqual(metrics["all"]["original"]["successful"], 48)
        self.assertEqual(metrics["all"]["uncertainty"]["successful"], 144)
        self.assertEqual(metrics["history_pairs"]["count"], 108)
        self.assertEqual(metrics["all"]["actual_generator_models"], {"OFFLINE_FAKE": 288})
        self.assertEqual(metrics["all"]["failure_findings"], {})
        analysis.verify_seal(output / "frozen_votes"); analysis.verify_seal(output)

    def test_disagreement_requires_third_review_before_diagnostics(self):
        prepared = self.prepare()
        av, bv = self.votes(prepared, "offline-A"), self.votes(prepared, "offline-B")
        bv["judgments"][0].update(classification="incorrect", useful_correct=False, reason="Offline disagreement fixture.")
        a, b = self.directory / "a.json", self.directory / "b.json"
        analysis.write(a, av); analysis.write(b, bv)
        reviews = self.directory / "reviews"
        analysis.seal_reviews(argparse.Namespace(prepared=prepared, review_a=a, review_b=b, output=reviews))
        with self.assertRaisesRegex(ValueError, "third independent"):
            analysis.resolve(argparse.Namespace(prepared=prepared, reviews=reviews, adjudication=None,
                                                output=self.directory / "analysis", allow_partial=False))
        self.assertFalse((self.directory / "analysis").exists())

    def test_rejected_answer_uses_supplied_envelope_and_validation_trace(self):
        expected = next(r for r in self.ledger if r["expected_kind"] == "replacement")
        row = next(r for r in self.rows if r["checkpoint_id"] == expected["checkpoint_id"])
        row = {**row, "status": "withheld", "delivered_answer": None,
               "supplied_evidence_envelopes": [{"records": row["supplied_records"]}],
               "trace": [{"name": "validation", "status": "error"}]}
        del row["supplied_records"]
        result = analysis.diagnostics(expected, row, {"useful_correct": False})
        self.assertTrue(result["required_evidence_supplied"])
        self.assertEqual(result["failure_findings"], ["validation_rejection"])
        self.assertTrue(result["validation_rejection_without_disclosure"])

    def test_required_retrieval_skipped_and_not_reached_are_not_search_failures(self):
        expected = next(r for r in self.ledger if r["expected_kind"] == "replacement")
        row = next(r for r in self.rows if r["checkpoint_id"] == expected["checkpoint_id"])
        row = {**row, "retrieval_calls": [], "supplied_records": [],
               "route": {"decision": {"memory_required": False}}}
        result = analysis.diagnostics(expected, row, {"useful_correct": False})
        self.assertIn("retrieval_skipped_by_memory_policy", result["failure_findings"])
        self.assertNotIn("retrieval_required_fact_missing", result["failure_findings"])
        row.update(status="withheld", delivered_answer=None, route=None,
                   trace=[{"name": "routing", "status": "error"}])
        result = analysis.diagnostics(expected, row, {"useful_correct": False})
        self.assertIn("retrieval_not_reached_after_routing_failure", result["failure_findings"])
        self.assertNotIn("retrieval_required_fact_missing", result["failure_findings"])

    def test_client_rejection_and_forwarded_history_are_recorded(self):
        expected = next(r for r in self.ledger if r["expected_kind"] == "replacement")
        row = next(r for r in self.rows if r["checkpoint_id"] == expected["checkpoint_id"])
        statement = {"role": "user", "content": "My preferred tea is rooibos tea."}
        row = {**row, "status": "withheld", "delivered_answer": None,
               "history_before": [statement], "trace": [{"name": "answer_generation", "status": "error"}],
               "calls": [{"purpose": "generation", "error": "OllamaError",
                          "message": "Ollama assistant returned an internal memory ID", "messages": [statement]}]}
        result = analysis.diagnostics(expected, row, {"useful_correct": False})
        self.assertIn("client_output_validation_rejection", result["failure_findings"])
        self.assertNotIn("generation_transport_or_call_failure", result["failure_findings"])
        self.assertTrue(result["client_output_validation_without_disclosure"])
        self.assertTrue(result["original_history_forwarded_to_generation"])

    def test_sealed_inputs_and_process_restart_identity_are_enforced(self):
        with self.assertRaisesRegex(ValueError, "sealed run root"):
            analysis.load_inputs(self.freeze, [self.run])
        tampered = [dict(r) for r in self.rows]
        for row in tampered:
            row["process"] = {"pid": 101, "boot_id": "offline", "process_start_ticks": "101"}
        self.replace_rows(tampered)
        with self.assertRaisesRegex(ValueError, "Process/database identity audit failed"):
            self.prepare()

    def test_vote_classification_matches_rubric_and_answer_availability(self):
        prepared = self.prepare()
        packets = {p["blind_id"]: p for p in analysis.read_lines(prepared / "public/packets.jsonl")}
        votes = self.votes(prepared, "offline-A")
        known = next(r for r in votes["judgments"] if r["classification"] == "correct_recall")
        known["classification"] = "appropriate_uncertainty"
        path = self.directory / "bad-votes.json"; analysis.write(path, votes)
        with self.assertRaisesRegex(ValueError, "Known-value task"):
            analysis.load_votes(path, packets, votes["packet_sha256"])


if __name__ == "__main__":
    unittest.main()
