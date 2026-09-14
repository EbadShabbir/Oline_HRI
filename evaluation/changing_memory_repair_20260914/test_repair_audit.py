"""Independent synthetic tests for the artifact auditor; no CLARA imports."""
import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from audit_repair_collection import Audit, digest, eligible, history_exposure, HISTORY_EXPOSURE_LIMITATION


class CollectionAuditTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = dict(context_length=2048, max_output_tokens=192, temperature=0.0, thinking=False)
        self.schema = {"properties": {"speech": {"type": "string"},
                        "memory_used": {"items": {"enum": ["memory_ref_1"]}}}}
        self.response = {"model": "qwen3:0.6b", "message": {"role": "assistant", "content":
                         '{"speech":"You prefer mint.","memory_used":["memory_ref_1"]}'}, "done": True}
        self.body = dict(model="qwen3:0.6b", messages=[{"role": "user", "content": "Evidence memory_ref_1"}],
                         format=self.schema, options=dict(num_ctx=2048, num_predict=192, temperature=0.0, seed=42),
                         think=False, stream=False)

    def http_rows(self):
        data = json.dumps(self.response).encode()
        split = 31
        return [dict(event="http_start", endpoint="/api/chat", body=self.body),
                dict(event="http_received_bytes", offset=0, bytes_base64=base64.b64encode(data[:split]).decode()),
                dict(event="http_received_bytes", offset=split, bytes_base64=base64.b64encode(data[split:]).decode()),
                dict(endpoint="/api/chat", body=self.body, status="ok", response=self.response)]

    def parse_http(self, rows):
        path = self.root / "http.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        audit = Audit()
        requests = audit.http(path, {"qwen3:0.6b", "qwen3:1.7b"}, self.config)
        return audit, requests

    def test_exact_received_bytes_reassemble_and_link_without_model_or_http_calls(self):
        audit, requests = self.parse_http(self.http_rows())
        self.assertEqual(audit.violations, [])
        self.assertEqual(requests[0]["bytes_sha256"], sha256(json.dumps(self.response).encode()).hexdigest())
        self.assertEqual(requests[0]["received_bytes"], len(json.dumps(self.response).encode()))

    def test_modified_parsed_answer_and_missing_chunk_are_detected(self):
        for mutation in ("parsed_response", "offset", "options"):
            rows = deepcopy(self.http_rows())
            if mutation == "parsed_response":
                rows[-1]["response"]["message"]["content"] = "fabricated parsed answer"
            elif mutation == "offset":
                rows[2]["offset"] += 1
            else:
                rows[0]["body"]["options"]["num_predict"] = 256
                rows[-1]["body"]["options"]["num_predict"] = 256
            audit, _ = self.parse_http(rows)
            self.assertTrue(audit.violations, mutation)

    def test_call_link_handles_real_request_pseudonyms_and_prevents_reused_http_evidence(self):
        audit, requests = self.parse_http(self.http_rows())
        identifier = "mem_" + "a" * 32
        content = self.response["message"]["content"]
        generation = dict(content=content.replace("memory_ref_1", identifier), model="qwen3:0.6b")
        call = dict(purpose="generation", requested_model="qwen3:0.6b", status="ok",
                    response_format={"properties": {"speech": {"type": "string"},
                                     "memory_used": {"items": {"enum": [identifier]}}}},
                    messages=[{"role": "user", "content": "Evidence " + identifier}],
                    raw_generation={"content": content}, generation=generation,
                    raw_chat_payload=self.response)
        row = dict(checkpoint_id="synthetic", op={"id": "synthetic-op"}, status="delivered", calls=[call],
                   validation_decision="accepted", delivered_answer="You prefer mint.",
                   response={"speech": "You prefer mint."}, generation=generation, raw_model_answers=[content])
        consumed = set()
        audit.answer(row, None, requests, consumed, "synthetic")
        self.assertEqual(audit.violations, [])
        self.assertEqual(consumed, {0})
        audit.answer(row, None, requests, consumed, "duplicate")
        self.assertIn("model_call_has_http_request", [r["code"] for r in audit.violations])

    def test_withholding_is_an_observation_not_invented_success_or_integrity_failure(self):
        audit = Audit()
        audit.answer(dict(checkpoint_id="withheld", op={"id": "withheld-op"}, status="withheld", calls=[],
                          validation_decision="rejected_or_pipeline_failure", delivered_answer=None,
                          raw_model_answers=[], error="ResponseValidationError", message="rejected"),
                     None, [], set(), "synthetic")
        self.assertEqual(audit.violations, [])
        self.assertEqual(audit.observations[0]["code"], "withheld_or_interrupted_answer")
        self.assertEqual(audit.counts["answer_status_delivered"], 0)

    def test_expiry_boundary_uses_exclusive_logical_time_and_record_status(self):
        record = dict(status="active", consent_status="confirmed", valid_from="2026-10-01T00:00:00Z",
                      valid_until=None, retention_until="2026-10-08T00:00:00Z")
        self.assertTrue(eligible(record, "2026-10-07T23:59:59.999999Z"))
        self.assertFalse(eligible(record, "2026-10-08T00:00:00Z"))
        self.assertFalse(eligible(record, "2026-10-08T00:00:00.000001Z"))
        self.assertFalse(eligible({**record, "status": "superseded"}, "2026-10-02T00:00:00Z"))
        with self.assertRaises(ValueError):
            eligible(record, "2026-10-02T00:00:00")

    def test_readonly_seal_detects_byte_tampering_without_trusting_frozen_code(self):
        file = self.root / "trace.json"
        file.write_text('{"answer":"original"}')
        manifest = self.root / "seal.json"
        manifest.write_text(json.dumps({"sha256": {file.name: digest(file)}}))
        for path in (file, manifest):
            path.chmod(0o400)
        self.root.chmod(0o500)
        audit = Audit()
        audit.seal(self.root)
        self.assertEqual(audit.violations, [])
        file.chmod(0o600)
        file.write_text('{"answer":"tampered"}')
        file.chmod(0o400)
        audit = Audit()
        audit.seal(self.root)
        self.assertEqual([v["code"] for v in audit.violations], ["seal_file_hash"])

    def test_pre_inference_admission_does_not_require_unstarted_telemetry(self):
        snapshot = dict(boot_id="offline", power_mode="offline", thermal_trip_events={"cpu": 0},
                        memory={"swap_total_kib": 3901608}, resident_models=[])
        frozen = dict(host={"snapshot": snapshot}, device_policy={"max_runtime_temperature_c_exclusive": 68.0})
        (self.root / "start.json").write_text(json.dumps(snapshot))
        (self.root / "finish.json").write_text(json.dumps(dict(status="interrupted", snapshot=snapshot,
            cleanup_errors=[], guard_violation=None, error={"type": "SafetyGateError", "message": "admission temperature"})))
        audit = Audit()
        audit.resource(self.root, frozen, admission_only=True)
        self.assertEqual(audit.violations, [])
        self.assertEqual(audit.observations, [])
        self.assertTrue(audit.resources[0]["admission_only"])
        audit = Audit()
        audit.resource(self.root, frozen, admission_only=False)
        self.assertIn("artifact_exists", [v["code"] for v in audit.violations])

    def test_history_exposure_keeps_assistant_echo_after_original_statement_is_pruned(self):
        original = "My preferred tea is rooibos tea."
        history = [{"role": "system", "content": "System instructions"},
                   {"role": "user", "content": "What tea did we discuss?"},
                   {"role": "assistant", "content": '{"speech":"Your preference is rooibos tea."}'}]
        row = dict(checkpoint_id="synthetic", branch_id="synthetic_correction", history_before=history,
                   calls=[dict(purpose="generation", messages=[*history, {"role": "user", "content": "What about now?"}])])
        ledger = dict(original_subject_value="rooibos", history_mode="retained", after_restart=True, branch="correction")
        audit = Audit(); audit.history(row, ledger, original)
        result = audit.history_witnesses[0]
        self.assertFalse(result["exact_original_statement_present"])
        self.assertFalse(result["exact_original_statement_forwarded"])
        self.assertTrue(result["literal_original_value_present"])
        self.assertTrue(result["literal_original_value_forwarded"])
        self.assertTrue(result["literal_value_forwarded_without_exact_statement"])
        self.assertEqual(result["forwarded_history_witnesses"][0]["matching_history_before_indices"], [2])
        self.assertEqual(result["forwarded_history_witnesses"][0]["role"], "assistant")
        self.assertEqual(audit.history_counts["all_scored_checkpoints"]["literal_original_value_forwarded"], 1)
        self.assertEqual(audit.history_counts["after_restart"]["exact_original_statement_present"], 0)

    def test_history_exposure_excludes_system_current_request_and_evidence_tail(self):
        original = "My preferred tea is rooibos tea."
        prior = {"role": "user", "content": original}
        evidence = {"role": "user", "content": "PERSONAL_MEMORY_DATA=rooibos"}
        history = [{"role": "system", "content": original}, prior, evidence]
        row = dict(history_before=history, calls=[
            dict(purpose="memory_selector", messages=[prior]),
            dict(purpose="generation", messages=[{"role": "system", "content": original}, evidence, prior])])
        result = history_exposure(row, original, "rooibos")
        self.assertTrue(result["exact_original_statement_present"])
        self.assertTrue(result["literal_original_value_present"])
        self.assertFalse(result["exact_original_statement_forwarded"])
        self.assertFalse(result["literal_original_value_forwarded"])
        self.assertEqual(result["forwarded_history_witnesses"], [])
        row["calls"][-1]["messages"] = [history[0], prior, {"role": "user", "content": "What now?"}]
        result = history_exposure(row, original, "rooibos")
        self.assertTrue(result["exact_original_statement_forwarded"])
        self.assertEqual(result["forwarded_history_witnesses"][0]["generation_message_index"], 1)

    def test_history_literal_matches_are_only_a_lower_bound_and_require_history_intersection(self):
        original = "My appointment is at 09:00."
        alias = {"role": "assistant", "content": "Your appointment is at 9 AM."}
        row = dict(history_before=[alias], calls=[dict(purpose="generation", messages=[
            {"role": "system", "content": "Instructions"}, alias,
            {"role": "assistant", "content": "Your old time was 09:00."},
            {"role": "user", "content": "What time now?"}])])
        result = history_exposure(row, original, "09:00")
        self.assertFalse(result["literal_original_value_present"])
        self.assertFalse(result["literal_original_value_forwarded"])
        self.assertIn("lower bound", HISTORY_EXPOSURE_LIMITATION)
        self.assertIn("not evidence of semantic absence", HISTORY_EXPOSURE_LIMITATION)
        row["history_before"] = [{"role": "assistant", "content": "ROOIBOS tea"}]
        row["calls"] = []
        result = history_exposure(row, "My tea is rooibos.", "rooibos")
        self.assertTrue(result["literal_original_value_present"])
        self.assertFalse(result["literal_original_value_forwarded"])


if __name__ == "__main__":
    unittest.main()
