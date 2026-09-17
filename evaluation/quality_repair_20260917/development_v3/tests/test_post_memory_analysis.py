"""Offline integrity checks for the new comparison's real-call contract."""

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_complete_system as base
import analyze_post_memory_comparison as post
import test_complete_system_analysis as legacy
from oline_hri.routing import MEMORY_REQUIRED_SCHEMA


def post_record(case, arm="small", repetition=1, index=1, *, classifier=False):
    row = legacy.record(case, arm, repetition, index)
    model = base.SMALL if arm == "small" else base.LARGE
    generation = legacy.generation(model)
    purposes = (["memory_selector"] if classifier else []) + ["generation"]
    calls, http = [], []
    for ordinal, purpose in enumerate(purposes):
        result = deepcopy(generation)
        if purpose == "memory_selector":
            result["content"] = '{"form":"question","memory_required":false}'
        schema = {"properties": {"speech": {}}} if purpose == "generation" else deepcopy(MEMORY_REQUIRED_SCHEMA)
        calls.append({"purpose": purpose, "requested_model": model, "actual_model": model,
                      "seed": 42, "status": "ok", "generation": result,
                      "wall_ns": 100_000_000, "response_format": schema})
        http.append({"endpoint": "/api/chat", "started_monotonic_ns": row["started_monotonic_ns"] + ordinal * 110_000_000,
                     "wall_ns": 100_000_000, "status": "ok", "body": {
                         "model": model, "messages": [{"role": "user", "content": case["prompt"]}],
                         "format": schema, "keep_alive": -1, "stream": False, "think": False,
                         "options": {"num_ctx": 2048, "num_predict": 192, "temperature": 0.0, "seed": 42}}})
    row.update(profile_id=post.PROFILE_ID, calls=calls, http_calls=http,
               resident_hint_before=None, resident_hint_after=model,
               api_ps_before=[], api_ps_after=[{"name": model}], post_snapshot_attempted=True,
               generation=generation)
    row["route"] = {
        "decision": {"memory_required": False, "model_size": "large" if arm == "cascade" else arm},
        "memory_required_generation": deepcopy(calls[0]["generation"]) if classifier else None,
        "model_size_generation": None,
        "memory_decision_source": ("resident_model" if arm == "cascade" else "fixed_model") if classifier else "policy_general",
        "model_size_decision_source": "lightweight_large" if arm == "cascade" else "fixed_generator",
        "policy": "lightweight_v1" if arm == "cascade" else "fixed_memory_v1",
        "fixed_generator_model": None if arm == "cascade" else model,
        "resident_model": model if classifier else None,
    }
    return row


class PostMemoryAnalysisTests(unittest.TestCase):
    def setUp(self):
        legacy.CompleteSystemAnalysisTests.setUp(self)
        self.frozen.update(profile_id=post.PROFILE_ID,
                           counterbalanced_arm_orders=base.ARM_ORDERS,
                           execution_policies={arm: post.execution_policy(arm) for arm in base.ALLOWED},
                           source_sha256={path: "a" * 64 for path in post.SOURCE_REQUIREMENTS})
        self.freeze_path.write_bytes(base.canonical_bytes(self.frozen))

    def write_session(self, slot, *, status="complete", count=48):
        path, _ = legacy.CompleteSystemAnalysisTests.write_session(self, slot, status=status, count=count)
        _, arm, repetition = slot
        manifest = base.read_json(path / "manifest.json")
        manifest.update(profile_id=post.PROFILE_ID, execution_policy=post.execution_policy(arm))
        (path / "manifest.json").write_bytes(base.canonical_bytes(manifest))
        if status is not None:
            finish = base.read_json(path / "finish.json")
            finish.update(source_sha256=self.frozen["source_sha256"], source_unchanged=True,
                          model_metadata_unchanged=True, ollama_version_unchanged=True)
            (path / "finish.json").write_bytes(base.canonical_bytes(finish))
        rows = [post_record(case, arm, repetition, index, classifier=index % 2 == 0)
                for index, case in enumerate(self.cases[:count], 1)]
        self.write_rows(path, rows)
        return path, rows

    @staticmethod
    def write_rows(path, rows):
        (path / "observations.jsonl").write_bytes(b"".join(base.canonical_bytes(row) for row in rows))
        (path / "http_calls.jsonl").write_bytes(b"".join(base.canonical_bytes(item) for row in rows for item in row["http_calls"]))

    def validate(self, row):
        return base.validate_row(row, self.cases[row["index"] - 1], row["index"], row["arm"],
                                 row["repetition"], comparison_profile=post.PROFILE_ID)

    def test_real_zero_and_one_classifier_routes_validate_for_all_arms(self):
        for arm in base.ALLOWED:
            for classifier in (False, True):
                with self.subTest(arm=arm, classifier=classifier):
                    self.assertEqual(self.validate(post_record(self.cases[0], arm, classifier=classifier)), [])

    def test_original_row_contract_remains_strict_and_cannot_silently_select_profile(self):
        row = post_record(self.cases[0], "cascade")
        errors = base.validate_row(row, self.cases[0], 1, "cascade", 1)
        self.assertIn("delivered request needs one memory selection", errors)
        self.assertIn("unexpected compute selection count", errors)
        self.assertEqual(base.validate_row(legacy.record(self.cases[0], "cascade"), self.cases[0], 1, "cascade", 1), [])
        with self.assertRaisesRegex(ValueError, "explicit comparison profile"):
            base.analyze(self.workload_path, self.freeze_path, self.run_root)

    def test_fabricated_classifier_metadata_and_classifier_decision_mismatch_rejected(self):
        row = post_record(self.cases[0], classifier=True)
        row["route"]["memory_required_generation"]["load_duration_ns"] += 1
        self.assertTrue(any("metadata differs" in message for message in self.validate(row)))
        row = post_record(self.cases[0], classifier=True)
        row["route"]["decision"]["memory_required"] = True
        self.assertTrue(any("actual classifier output" in message for message in self.validate(row)))
        row = post_record(self.cases[0])
        row["route"]["memory_required_generation"] = legacy.generation(base.SMALL)
        self.assertTrue(any("fabricated" in message for message in self.validate(row)))

    def test_classifier_current_form_contract_rejects_missing_or_invalid_form(self):
        for content in ('{"memory_required":false}', '{"form":"other","memory_required":false}',
                        '{"form":"question","memory_required":false,"memory_required":false}',
                        '{"form":[],"memory_required":false}'):
            row = post_record(self.cases[0], classifier=True)
            row["route"]["memory_required_generation"]["content"] = content
            row["calls"][0]["generation"]["content"] = content
            self.assertTrue(any("actual classifier output" in message for message in self.validate(row)))

    def test_compute_call_and_fake_optimized_policy_are_rejected_even_on_failed_rows(self):
        row = post_record(self.cases[0], "cascade")
        row["status"] = "error"
        row["calls"].append({**row["calls"][0], "purpose": "compute_selector"})
        self.assertTrue(any("compute-classifier" in message for message in self.validate(row)))
        row = post_record(self.cases[0], "cascade")
        row["route"]["policy"] = "legacy"
        self.assertTrue(any("declared lightweight" in message for message in self.validate(row)))

    def test_fixed_controls_cannot_call_peer_or_forge_fixed_tag(self):
        row = post_record(self.cases[0], "large", classifier=True)
        row["calls"][0]["requested_model"] = base.SMALL
        row["route"]["fixed_generator_model"] = base.SMALL
        errors = self.validate(row)
        self.assertTrue(any("outside the arm" in message for message in errors))
        self.assertTrue(any("optimized fixed-memory" in message for message in errors))

    def test_privacy_policy_has_true_memory_intent_and_no_fake_classifier(self):
        row = post_record(self.cases[0])
        row["route"]["memory_decision_source"] = "policy_privacy"
        row["route"]["decision"]["memory_required"] = True
        self.assertEqual(self.validate(row), [])

    def test_simultaneous_residency_or_nonresident_classifier_is_rejected(self):
        row = post_record(self.cases[0], "cascade", classifier=True)
        row["resident_hint_before"] = base.SMALL
        row["api_ps_after"].append({"name": base.SMALL})
        errors = self.validate(row)
        self.assertTrue(any("simultaneous" in message for message in errors))
        self.assertTrue(any("resident or selected" in message for message in errors))

    def test_guard_interruption_without_post_snapshot_is_preserved_and_disclosed(self):
        row = post_record(self.cases[0])
        row.update(status="interrupted", error="SafetyGateError", message="telemetry RAM floor crossed")
        row.update(api_ps_after=None, post_snapshot_error={"error": "ModelPairEvaluationError", "message": "cannot reach local Ollama"})
        self.assertEqual(self.validate(row), [])
        report = {}
        post.decorate_report(report, [row])
        self.assertEqual(len(report["routing_contract"]["interrupted_without_post_request_residency_snapshot"]), 1)
        row["status"] = "ok"
        self.assertTrue(any("resident snapshot is absent" in message for message in self.validate(row)))

    def test_actual_runner_fake_http_records_pass_row_manifest_and_transport_analysis(self):
        # Exercise real Conversation, OptimizedMemoryOnlyRouter/LightweightRouter,
        # ComparisonBackend and OllamaClient through a fake HTTP opener. This
        # catches schema drift that manually authored observation fixtures miss.
        import test_post_memory_comparison as integration
        helper = integration.PostMemoryComparisonTests()
        for arm in base.ALLOWED:
            with self.subTest(arm=arm), integration.tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                result, rows, finish, _, _ = helper.run_offline(
                    root, arm, (integration.HARD, integration.EASY, integration.AMBIGUOUS))
                self.assertEqual(result, 0)
                cases = base.read_json(root / "workload.json")["execution_cases"]
                for index, (case, row) in enumerate(zip(cases, rows), 1):
                    self.assertEqual(base.validate_row(row, case, index, arm, 1,
                                                      comparison_profile=post.PROFILE_ID), [])
                path = root / "output"
                manifest, frozen = base.read_json(path / "manifest.json"), base.read_json(root / "freeze.json")
                self.assertEqual(post.validate_manifest_contract(manifest, frozen, arm), [])
                session = {"status": finish["status"], "artifact_sha256": {}, "arm": arm}
                self.assertEqual(post.validate_session_contract(path, rows, manifest, finish, frozen, session), [])

    def test_partial_missing_and_failed_attempts_survive_blinding_and_denominators(self):
        self.write_session(base.session_slots()[0])
        path, rows = self.write_session(base.session_slots()[1], status=None, count=2)
        rows[0].update(status="error", response=None)
        self.write_rows(path, rows)
        report, workload, raw, metrics = post.analyze(self.workload_path, self.freeze_path, self.run_root)
        self.assertTrue(report["integrity_valid"], report)
        self.assertFalse(report["complete"])
        self.assertEqual(report["observed_attempts"], 50)
        self.assertEqual(report["arms"]["cascade"]["unattempted"], 144)
        self.assertEqual(report["arms"]["large"]["attempted"], 2)
        worksheet, mapping = base.make_blinded_review(workload, raw, "ab" * 32)
        self.assertEqual(sum(len(group["observations"]) for group in mapping), 50)
        self.assertTrue(any(entry["delivered_response"] is None for entry in worksheet))
        encoded = base.canonical_bytes(worksheet).decode()
        for text in ('"arm"', '"repetition"', "lightweight_v1", "fixed_memory_v1", "resident_hint", "qwen3:"):
            self.assertNotIn(text, encoded)
        self.assertIsNone(base.deadline_quality_curve(report, metrics, mapping)["arms"])

    def test_wrong_profile_source_or_execution_policy_is_rejected(self):
        for change in ({"profile_id": "legacy"}, {"source_sha256": {}}, {"execution_policies": {}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                post.validate_freeze_contract({**self.frozen, **change})
        path, _ = self.write_session(base.session_slots()[0])
        finish = base.read_json(path / "finish.json")
        finish["source_unchanged"] = False
        (path / "finish.json").write_bytes(base.canonical_bytes(finish))
        report, _, _, _ = post.analyze(self.workload_path, self.freeze_path, self.run_root)
        self.assertFalse(report["integrity_valid"])
        self.assertTrue(any("terminal execution source" in message for message in report["sessions"][0]["errors"]))

    def test_actual_transport_options_and_durable_slice_tampering_fail(self):
        path, rows = self.write_session(base.session_slots()[0])
        http = base.read_jsonl(path / "http_calls.jsonl")
        http[0]["body"]["keep_alive"] = 0
        (path / "http_calls.jsonl").write_bytes(b"".join(base.canonical_bytes(item) for item in http))
        report, _, _, _ = post.analyze(self.workload_path, self.freeze_path, self.run_root)
        errors = report["sessions"][0]["errors"]
        self.assertFalse(report["integrity_valid"])
        self.assertTrue(any("residency flags" in message for message in errors))
        self.assertTrue(any("slice differs" in message for message in errors))

    def test_full_new_profile_has_432_attempts_without_automatic_quality_claim(self):
        for slot in base.session_slots():
            self.write_session(slot)
        report, _, rows, _ = post.analyze(self.workload_path, self.freeze_path, self.run_root)
        self.assertTrue(report["complete"], report)
        self.assertEqual(len(rows), 432)
        self.assertEqual(report["routing_contract"]["observed_call_purposes"],
                         {"memory_selector": 216, "generation": 432})
        self.assertIsNone(report["arms"]["cascade"]["semantic_correctness_rate"])
        self.assertTrue(base.render_markdown(report).startswith("# Post-memory"))

    def test_rotated_frozen_schedule_preserves_432_and_legacy_defaults(self):
        legacy_slots = base.session_slots()
        orders = (("large", "cascade", "small"),
                  ("cascade", "small", "large"),
                  ("small", "large", "cascade"))
        self.frozen["counterbalanced_arm_orders"] = orders
        self.freeze_path.write_bytes(base.canonical_bytes(self.frozen))
        slots = base.session_slots(orders)
        for slot in slots:
            self.write_session(slot)
        snapshot = base.read_json(self.run_root / slots[0][0] / "start.json")
        (self.run_root / "batch_finish.json").write_bytes(base.canonical_bytes({
            "snapshot": snapshot, "sessions": [
                {"arm": arm, "repetition": repetition} for _, arm, repetition in slots]}))
        report, workload, rows, _ = post.analyze(self.workload_path, self.freeze_path, self.run_root)
        self.assertTrue(report["complete"], report)
        self.assertEqual(report["observed_attempts"], 432)
        self.assertEqual(report["counterbalanced_arm_orders"], [list(row) for row in orders])
        self.assertEqual([(row["arm"], row["repetition"]) for row in rows[::48]],
                         [(arm, repetition) for _, arm, repetition in slots])
        self.assertEqual(base.session_slots(), legacy_slots)
        worksheet, mapping = base.make_blinded_review(workload, rows, "ab" * 32)
        reversed_worksheet, _ = base.make_blinded_review(workload, list(reversed(rows)), "ab" * 32)
        self.assertEqual(worksheet, reversed_worksheet)
        self.assertEqual(sum(len(group["observations"]) for group in mapping), 432)
        with self.assertRaisesRegex(ValueError, "differs from the frozen"):
            base.analyze(self.workload_path, self.freeze_path, self.run_root,
                         comparison_profile=post.PROFILE_ID, arm_orders=base.ARM_ORDERS)

    def test_frozen_schedule_rejects_missing_repeated_or_unbalanced_arms(self):
        for orders in (None, [], [["large", "cascade", "small"]] * 3,
                       [["large", "large", "small"]] * 3,
                       [["large", {}, "small"]] * 3):
            with self.subTest(orders=orders), self.assertRaisesRegex(ValueError, "counterbalance"):
                post.validate_freeze_contract({**self.frozen, "counterbalanced_arm_orders": orders})


if __name__ == "__main__":
    unittest.main()
