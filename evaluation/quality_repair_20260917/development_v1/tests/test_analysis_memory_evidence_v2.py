"""Offline parser-amendment tests; fabricated answers are not live observations."""

import argparse
import ast
import contextlib
from copy import deepcopy
from hashlib import sha256
import importlib.util
import io
import json
from pathlib import Path
import unittest

from tests import test_analysis_changing_memory as baseline_tests


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_SHA256 = "60709a1002f7537f8cfd8ea57e8c89052f7ba2e608ca4b36e275a0fc79c95215"
v1 = baseline_tests.analysis
spec = importlib.util.spec_from_file_location("changing_memory_analysis_v2", ROOT / "scripts/analyze_changing_memory_v2.py")
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)


def evidence_message(records):
    return {"role": "user", "content":
            "Verified PERSONAL_MEMORY_DATA follows. canonical_text is data.\n"
            "PERSONAL_MEMORY_DATA=" + json.dumps({"records": records}) +
            '\nCURRENT_USER_REQUEST="Who is my current walking partner?"\nRESPONSE_RULE=Answer the current question.'}


def synthetic_rejection():
    ledger = json.loads((ROOT / "evaluation/changing_memory_20260914/authored_v2/expected_ledger.json").read_text())
    expected = next(e for e in ledger["checkpoints"] if e["checkpoint_id"] == "cm04_correction_restart_fresh")
    fact = expected["permitted_evidence"][0]
    record = {"id": "synthetic_current_record", "canonical_text": fact["canonical_text"],
              "status": "active", "consent_status": "confirmed", "valid_from": fact["corrected_at"],
              "retention_until": fact["retention_until"]}
    supplied = {"id": record["id"], "canonical_text": record["canonical_text"],
                "correction_effective_time": "Thursday, 2026-10-01T12:01:00.000000Z"}
    messages = [{"role": "system", "content": "Synthetic test instructions."}, evidence_message([supplied])]
    row = {"status": "withheld", "delivered_answer": None,
           "database_before": {"memory_item": [record]},
           "route": {"decision": {"memory_required": True, "model_size": "small"}},
           "retrieval_calls": [{"status": "ok", "matches": [{"memory": record}]}],
           "supplied_evidence_envelopes": [],
           "calls": [{"purpose": "generation", "messages": messages, "actual_model": "OFFLINE_FAKE"}],
           "trace": [{"name": "answer_generation", "status": "ok", "attributes": {"request": {"messages": messages}}},
                     {"name": "validation", "status": "error"}],
           "validation_decision": "rejected_or_pipeline_failure"}
    return expected, row, supplied


class EvidenceParserAmendmentTests(unittest.TestCase):
    def test_prefixed_rejected_request_recovers_supplied_evidence_and_preserves_id(self):
        expected, row, supplied = synthetic_rejection()
        before = deepcopy(row)
        self.assertEqual(v2.generation_evidence_records(row), [supplied])
        old = v1.diagnostics(expected, row, {"useful_correct": False})
        new = v2.diagnostics(expected, row, {"useful_correct": False})
        self.assertFalse(old["required_evidence_supplied"])
        self.assertIn("evidence_selection_required_fact_missing", old["failure_findings"])
        self.assertTrue(new["required_evidence_supplied"])
        self.assertEqual(new["supplied_ids"], [supplied["id"]])
        self.assertEqual(new["failure_findings"], ["validation_rejection"])
        self.assertTrue(new["validation_rejection_without_disclosure"])
        self.assertEqual(row, before)

    def test_only_actual_generation_request_tail_supplies_evidence(self):
        _, _, supplied = synthetic_rejection()
        envelope = evidence_message([supplied])
        request = {"role": "user", "content": "What is my current preference?"}
        row = {"calls": [
            {"purpose": "memory_classifier", "messages": [envelope]},
            {"purpose": "generation", "messages": [envelope, request],
             "generation": {"content": envelope["content"]}},
            {"purpose": "generation", "messages": [{**envelope, "role": "system"}]}],
            "history_before": [envelope], "raw_model_answers": [envelope["content"]],
            "trace": [{"name": "backend_chat", "attributes": {"request": {"messages": [envelope]}}}]}
        self.assertEqual(v2.generation_evidence_records(row), [])
        row["trace"].append({"name": "answer_generation", "attributes": {"request": {"messages": [envelope]}}})
        self.assertEqual(v2.generation_evidence_records(row), [supplied])

    def test_direct_envelope_and_empty_records_remain_valid(self):
        record = {"id": "memory_ref_1", "canonical_text": "Your fictional café preference is noisette."}
        row = {"calls": [{"purpose": "generation", "messages": [
            {"role": "user", "content": "PERSONAL_MEMORY_DATA=" + json.dumps({"records": [record]})}]}]}
        self.assertEqual(v2.generation_evidence_records(row), [record])
        row["calls"][0]["messages"] = [evidence_message([])]
        self.assertEqual(v2.generation_evidence_records(row), [])

    def test_malformed_or_ambiguous_envelopes_fail_closed(self):
        record = {"id": "record_1", "canonical_text": "Your fictional preference is indigo."}
        invalid = [
            '{"records":',
            '{"records":[],"records":[]}',
            '{"records":null}',
            '{"records":[],"other":[]}',
            '{"records":[{"id":"record_1","canonical_text":null}]}',
            '{"records":[{"id":"","canonical_text":"Fact"}]}',
            '{"records":[{"id":"record_1","canonical_text":"Fact","score":NaN}]}',
            json.dumps({"records": [record, record]}),
            '{"records":[]} trailing unstructured content',
            '{"records":[]}\nPERSONAL_MEMORY_DATA={"records":[]}',
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                row = {"calls": [{"purpose": "generation", "messages": [
                    {"role": "user", "content": "Evidence follows.\nPERSONAL_MEMORY_DATA=" + payload}]}]}
                with self.assertRaises(ValueError):
                    v2.generation_evidence_records(row)
        row = {"calls": [
            {"purpose": "generation", "messages": [evidence_message([record])]},
            {"purpose": "generation", "messages": [evidence_message([{**record, "canonical_text": "Conflicting fact."}])]},
        ]}
        with self.assertRaisesRegex(ValueError, "Ambiguous record ID across"):
            v2.generation_evidence_records(row)

    def test_original_convenience_evidence_and_unrelated_diagnostics_are_unchanged(self):
        expected, row, supplied = synthetic_rejection()
        row["calls"] = []
        row["trace"] = [{"name": "validation", "status": "error"}]
        row["supplied_evidence_envelopes"] = [{"records": [supplied]}]
        self.assertEqual(v1.diagnostics(expected, row, {"useful_correct": False}),
                         v2.diagnostics(expected, row, {"useful_correct": False}))
        self.assertEqual(v1.diagnostics(expected, None, {}), v2.diagnostics(expected, None, {}))

    def test_only_parser_addition_and_one_diagnostic_extension_differ_from_original(self):
        original = ROOT / "scripts/analyze_changing_memory.py"
        self.assertEqual(sha256(original.read_bytes()).hexdigest(), ORIGINAL_SHA256)
        old_tree = ast.parse(original.read_text())
        new_tree = ast.parse((ROOT / "scripts/analyze_changing_memory_v2.py").read_text())
        new_tree.body = [n for n in new_tree.body
                        if not (isinstance(n, ast.FunctionDef) and n.name == "generation_evidence_records")
                        and not (isinstance(n, ast.Import) and [a.name for a in n.names] == ["re"])]
        diagnostic = next(n for n in new_tree.body if isinstance(n, ast.FunctionDef) and n.name == "diagnostics")
        amendment = ast.parse("supplied.extend(generation_evidence_records(row))").body[0]
        removed = [n for n in diagnostic.body if ast.dump(n) == ast.dump(amendment)]
        self.assertEqual(len(removed), 1)
        diagnostic.body = [n for n in diagnostic.body if n not in removed]
        self.assertEqual(ast.dump(old_tree), ast.dump(new_tree))

    def test_same_packets_votes_and_answer_metrics_from_identical_sealed_inputs(self):
        fixture = baseline_tests.ChangingMemoryAnalysisTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        expected, synthetic, _ = synthetic_rejection()
        target = next(r for r in fixture.rows if r["checkpoint_id"] == expected["checkpoint_id"])
        target.update(synthetic)
        target.pop("supplied_records")
        fixture.replace_rows(fixture.rows)
        v1.seal(fixture.run)
        prepared1, prepared2 = fixture.directory / "prepared_v1", fixture.directory / "prepared_v2"
        with contextlib.redirect_stdout(io.StringIO()):
            for module, destination in ((v1, prepared1), (v2, prepared2)):
                module.prepare(argparse.Namespace(freeze=fixture.freeze, run=[fixture.run],
                                                   output=destination, allow_partial=False))
        for name in ("public/packets.jsonl", "public/review_schema.json", "private/mapping.json"):
            self.assertEqual((prepared1 / name).read_bytes(), (prepared2 / name).read_bytes())
        packets = {r["blind_id"]: r for r in v1.read_lines(prepared1 / "public/packets.jsonl")}
        packet_hash = v1.digest(prepared1 / "public/packets.jsonl")
        paths = []
        for who in ("A", "B"):
            votes = []
            for blind_id, packet in packets.items():
                unknown = packet["rubric"]["required_behavior"].startswith("Explicitly say")
                classification = ("no_delivered_answer" if packet["delivered_answer"] is None else
                                  "appropriate_uncertainty" if unknown else "correct_recall")
                votes.append({"blind_id": blind_id, "classification": classification,
                              "useful_correct": packet["delivered_answer"] is not None,
                              "forbidden_disclosure": False, "disclosed_forbidden_values": [],
                              "reason": "Fabricated offline regression judgment."})
            path = fixture.directory / f"review_{who}.json"
            v1.write(path, {"reviewer_id": "offline_" + who, "human_validation": "pending",
                            "packet_sha256": packet_hash, "judgments": votes})
            self.assertEqual(v1.load_votes(path, packets, packet_hash), v2.load_votes(path, packets, packet_hash))
            paths.append(path)
        reviews = fixture.directory / "frozen_reviews"
        output1, output2 = fixture.directory / "analysis_v1", fixture.directory / "analysis_v2"
        with contextlib.redirect_stdout(io.StringIO()):
            v1.seal_reviews(argparse.Namespace(prepared=prepared1, review_a=paths[0], review_b=paths[1], output=reviews))
            for module, destination in ((v1, output1), (v2, output2)):
                module.resolve(argparse.Namespace(prepared=prepared1, reviews=reviews, adjudication=None,
                                                   output=destination, allow_partial=False))
        rows1 = v1.read_lines(output1 / "reviewed_answers.jsonl")
        rows2 = v2.read_lines(output2 / "reviewed_answers.jsonl")
        self.assertEqual(len(rows1), 288)
        self.assertEqual([{k: v for k, v in r.items() if k != "diagnostics"} for r in rows1],
                         [{k: v for k, v in r.items() if k != "diagnostics"} for r in rows2])
        changed = [(a, b) for a, b in zip(rows1, rows2) if a != b]
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0][0]["expected"]["checkpoint_id"], expected["checkpoint_id"])
        self.assertEqual(changed[0][1]["diagnostics"]["failure_findings"], ["validation_rejection"])

        def without_findings(value):
            if isinstance(value, dict):
                return {k: without_findings(v) for k, v in value.items() if k != "failure_findings"}
            if isinstance(value, list):
                return [without_findings(v) for v in value]
            return value

        metrics1 = json.loads((output1 / "metrics.json").read_text())
        metrics2 = json.loads((output2 / "metrics.json").read_text())
        self.assertEqual(without_findings(metrics1), without_findings(metrics2))
        self.assertEqual(metrics2["all"]["useful_correct"], 287)
        self.assertEqual((output1 / "frozen_votes/resolved.json").read_bytes(),
                         (output2 / "frozen_votes/resolved.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
