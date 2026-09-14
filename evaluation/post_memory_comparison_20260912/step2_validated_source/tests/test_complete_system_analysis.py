"""Offline checks for artifact auditing, timing accounting, and honest blinding."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import sys
import shutil
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_complete_system as analysis


def rubric():
    return {"mode": "supported", "reference_answer": "45 tokens.",
            "required_claims": ["45 tokens"], "forbidden_claims": [],
            "required_memory_ids": [], "forbidden_memory_ids": [],
            "automated_checks": {"kind": "lexical_signals_only",
                                 "required_groups": [{"claim": "45 tokens", "any": [r"\b45\b"]}],
                                 "forbidden_presence_patterns": [r"\bcedar\b"]}}


def generation(model):
    return {"model": model, "content": "raw", "done_reason": "stop",
            "total_duration_ns": 100_000_000, "load_duration_ns": 20_000_000,
            "prompt_eval_duration_ns": 30_000_000, "eval_duration_ns": 50_000_000}


def record(case, arm="small", repetition=1, index=1):
    model = analysis.SMALL if arm == "small" else analysis.LARGE
    selector = analysis.SMALL if arm == "cascade" else model
    purposes = [("memory_selector", selector)]
    if arm == "cascade":
        purposes.append(("compute_selector", selector))
    purposes.append(("generation", model))
    calls = [{"purpose": purpose, "requested_model": tag, "actual_model": tag,
              "seed": 42, "status": "ok", "generation": generation(tag),
              "wall_ns": 100_000_000} for purpose, tag in purposes]
    return {**case, "arm": arm, "repetition": repetition, "index": index, "status": "ok",
            "started_monotonic_ns": index * 1_000_000_000,
            "finished_monotonic_ns": index * 1_000_000_000 + 500_000_000,
            "wall_ns": 500_000_000, "routing_wall_ns": 100_000_000 * (len(calls) - 1),
            "calls": calls, "retrieval_calls": [],
            "response": {"speech": "45 tokens.", "gesture_id": "NO_ACTION", "memory_used": []},
            "generation": generation(model),
            "route": {"model_size_generation": generation(selector) if arm == "cascade" else None,
                      "model_size_decision_source": "model" if arm == "cascade" else "fixed_generator"},
            "memory": {"supplied_ids": [], "model_used_ids": []},
            "generation_policy": None if arm == "cascade" else "fixed_generator",
            "fallback_from_model": None}


class CompleteSystemAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.run_root = self.root / "runs"
        self.run_root.mkdir()
        self.cases = [{"id": f"case-{index}", "prompt": f"Question {index}?", "stratum": f"stratum-{index % 4}",
                       "scenario_id": f"scenario-{index // 2}"} for index in range(48)]
        self.workload = {"execution_cases": self.cases,
                         "rubrics": {case["id"]: rubric() for case in self.cases},
                         "memory_seed": {"profile_id": "offline-synthetic-profile", "retention_days": 7,
                                         "evaluation_at": "2026-09-20T18:00:00Z", "events": [],
                                         "expected_state": {"eligible_current_memory_ids": []}}}
        self.workload_path = self.root / "workload.json"
        self.workload_path.write_bytes(analysis.canonical_bytes(self.workload))
        self.frozen = {"workload_sha256": analysis.file_hash(self.workload_path),
                       "source_sha256": {"frozen_source.py": "a" * 64},
                       "models": {model: {"digest": model + "-digest"} for model in (analysis.SMALL, analysis.LARGE)},
                       "ollama_version": {"version": "test"}}
        self.freeze_path = self.root / "freeze.json"
        self.freeze_path.write_bytes(analysis.canonical_bytes(self.frozen))

    def write_session(self, slot, *, status="complete", count=48):
        directory, arm, repetition = slot
        path = self.run_root / directory
        path.mkdir()
        models = analysis.ALLOWED[arm]
        sole = next(iter(models)) if len(models) == 1 else None
        manifest = {
            "arm": arm, "repetition": repetition, "frozen": self.frozen,
            "models": {model: self.frozen["models"][model] for model in models},
            "ollama_version": self.frozen["ollama_version"], "generation_seed": 42,
            "config": {"generation": {"context_length": 2048, "max_output_tokens": 192,
                                       "temperature": 0.0, "thinking": False},
                       "ollama": {"small_model": sole or analysis.SMALL,
                                  "general_large_model": sole or analysis.LARGE, "large_model": sole or analysis.LARGE}},
            "device_policy": analysis.EXPECTED_LIMITS,
        }
        snapshot = {"memory": {"mem_available_kib": 3 * 1024 * 1024, "swap_used_kib": 100 * 1024},
                    "temperatures_c": {"cpu": 40}, "resident_models": [], "fan_pwm": 77,
                    "thermal_trip_events": {"cpu": 0}, "power_mode": "NV Power Mode: 15W\n0", "boot_id": "same-boot"}
        values = {"manifest.json": manifest, "workload.json": self.workload, "start.json": snapshot,
                  "memory_setup.json": {"snapshot": [], "snapshot_sha256": sha256(analysis.canonical_bytes([])).hexdigest(),
                                        "wall_ns": 100_000_000}, "summary.json": {"status": status}}
        if status is not None:
            values["finish.json"] = {**snapshot, "status": status, "cleanup_errors": [],
                                     "guard_violation": None, "telemetry_reader_error": None}
        for name, value in values.items():
            (path / name).write_bytes(analysis.canonical_bytes(value))
        rows = [record(case, arm, repetition, index) for index, case in enumerate(self.cases[:count], 1)]
        (path / "observations.jsonl").write_bytes(b"".join(analysis.canonical_bytes(row) for row in rows))
        samples = [{"monotonic_ns": index * 500_000_000, "ram": {"used_mb": 5000, "total_mb": 8000},
                    "swap": {"used_mb": 100}, "temperatures_c": {"cpu": 40}, "gr3d_percent": 50,
                    "vdd_in": {"instant_mw": 10000}} for index in range(100)]
        (path / "telemetry.jsonl").write_bytes(b"".join(analysis.canonical_bytes(sample) for sample in samples))
        return path, rows

    def test_all_nine_slots_produce_432_unique_attempts_without_quality_claim(self):
        for slot in analysis.session_slots():
            self.write_session(slot)
        report, _, rows, metrics = analysis.analyze(self.workload_path, self.freeze_path, self.run_root)
        self.assertTrue(report["integrity_valid"], report)
        self.assertTrue(report["complete"])
        self.assertEqual(len(rows), 432)
        self.assertEqual(len(metrics), 432)
        self.assertEqual(report["distinct_scenarios"], 24)
        for arm in report["arms"].values():
            self.assertEqual(arm["planned"], 144)
            self.assertEqual(arm["delivered"], 144)
            self.assertIsNone(arm["semantic_correctness_rate"])
        self.assertEqual(report["paired_latency"][0]["paired_distinct_cases"], 48)

    def test_partial_run_is_explicit_and_never_merged_into_completion(self):
        self.write_session(analysis.session_slots()[0])
        self.write_session(analysis.session_slots()[1], status=None, count=2)
        report, _, rows, _ = analysis.analyze(self.workload_path, self.freeze_path, self.run_root)
        self.assertTrue(report["integrity_valid"], report)
        self.assertFalse(report["complete"])
        self.assertTrue(report["incomplete"])
        self.assertEqual(len(rows), 50)
        self.assertEqual(report["arms"]["cascade"]["unattempted"], 144)

    def test_duplicate_rows_and_changed_model_digest_fail_integrity(self):
        path, rows = self.write_session(analysis.session_slots()[0])
        rows[1] = rows[0]
        (path / "observations.jsonl").write_bytes(b"".join(analysis.canonical_bytes(row) for row in rows))
        manifest = analysis.read_json(path / "manifest.json")
        manifest["models"][analysis.SMALL]["digest"] = "different"
        (path / "manifest.json").write_bytes(analysis.canonical_bytes(manifest))
        report, _, _, _ = analysis.analyze(self.workload_path, self.freeze_path, self.run_root)
        self.assertFalse(report["integrity_valid"])
        self.assertFalse(report["complete"])
        self.assertTrue(any("duplicate" in message for message in report["integrity_errors"]))

    def test_lexical_matches_never_become_semantic_success_or_abstention(self):
        row = record(self.cases[0])
        row["response"]["speech"] = "It is not 45. It is not Cedar."
        signals = analysis.lexical_signals(row, rubric())
        self.assertTrue(signals["all_required_groups_matched"])
        self.assertTrue(signals["forbidden_presence_patterns_matched"])
        self.assertIsNone(signals["semantic_correctness"])
        empty = rubric()
        empty["mode"] = "abstain"
        empty["automated_checks"]["required_groups"] = []
        self.assertIsNone(analysis.lexical_signals(row, empty)["all_required_groups_matched"])
        row["status"] = "error"
        self.assertEqual(analysis.lexical_signals(row, empty)["status"], "not_evaluated_no_delivery")

    def test_rejected_raw_generations_keep_timing_but_not_delivery(self):
        row = record(self.cases[0])
        row["status"] = "error"
        last = row["calls"][-1]
        last["raw_generation"] = last.pop("generation")
        last["status"] = "error"
        row.pop("response")
        metrics = analysis.row_metrics(row, rubric())
        self.assertFalse(metrics["delivered"])
        self.assertEqual(metrics["calls_with_reported_duration_metadata"], 2)
        self.assertAlmostEqual(metrics["ollama_load_seconds"], .04)
        self.assertAlmostEqual(metrics["generation_call_wall_seconds"], .1)

    def test_failed_generation_recovers_supplied_evidence_and_preserves_unknown_state(self):
        row = record(self.cases[0])
        row["status"] = "error"
        row.pop("memory")
        row.pop("response")
        expected = rubric()
        expected["forbidden_memory_ids"] = ["forbidden_memory"]
        row["calls"][-1]["response_format"] = {"properties": {"memory_used": {
            "items": {"enum": ["forbidden_memory"]}, "maxItems": 1}}}
        metrics = analysis.row_metrics(row, expected)
        self.assertEqual(metrics["supplied_evidence_source"], "generation_response_schema")
        self.assertEqual(metrics["forbidden_supplied_ids"], ["forbidden_memory"])
        row["calls"] = row["calls"][:1]
        unknown = analysis.row_metrics(row, expected)
        self.assertFalse(unknown["supplied_evidence_known"])
        self.assertIsNone(unknown["forbidden_supplied_ids"])

    def test_blinding_is_reproducible_hides_arm_counts_and_preserves_mapping(self):
        rows = [record(self.cases[0], arm, repetition) for arm in analysis.ALLOWED for repetition in (1, 2, 3)]
        seed = "ab" * 32
        worksheet, mapping = analysis.make_blinded_review(self.workload, rows, seed)
        self.assertEqual(len(worksheet), 1)
        self.assertEqual(len(mapping[0]["observations"]), 9)
        self.assertEqual((worksheet, mapping), analysis.make_blinded_review(self.workload, rows, seed))
        self.assertNotEqual(worksheet[0]["review_id"], analysis.make_blinded_review(self.workload, rows, "cd" * 32)[0][0]["review_id"])
        serialized = analysis.canonical_bytes(worksheet).decode()
        for forbidden in ('"arm"', '"repetition"', '"count"', '"seed"', '"wall_ns"', 'qwen3:'):
            self.assertNotIn(forbidden, serialized)

    def test_blind_evidence_includes_extra_current_facts_and_never_labels_stale_as_current(self):
        workload = deepcopy(self.workload)
        workload["memory_seed"] = {
            "events": [{"operation": "remember", "memory_id": name, "canonical_text": name + " fact"}
                       for name in ("required", "extra-a", "extra-b", "stale")],
            "expected_state": {"eligible_current_memory_ids": ["required", "extra-a", "extra-b"]},
        }
        workload["rubrics"][self.cases[0]["id"]]["required_memory_ids"] = ["required"]
        workload["rubrics"][self.cases[0]["id"]]["forbidden_memory_ids"] = ["reference-only"]
        first, second = record(self.cases[0]), record(self.cases[0], "large")
        first["memory"]["supplied_ids"] = ["extra-a", "stale"]
        second["memory"]["supplied_ids"] = ["extra-b"]
        for row in (first, second):
            row["response"]["memory_used"] = ["extra-a", "unknown"]
        worksheet, _ = analysis.make_blinded_review(workload, [first, second], "ab" * 32)
        self.assertEqual(len(worksheet), 2)
        by_supplied = {tuple(entry["actually_supplied_memory_ids"]): entry for entry in worksheet}
        a, b = by_supplied[("extra-a", "stale")], by_supplied[("extra-b",)]
        self.assertEqual([item["memory_id"] for item in a["required_gold_current_evidence"]], ["required"])
        self.assertEqual([item["memory_id"] for item in a["actually_supplied_current_evidence"]], ["extra-a"])
        self.assertEqual([item["memory_id"] for item in b["actually_supplied_current_evidence"]], ["extra-b"])
        self.assertEqual([item["memory_id"] for item in b["cited_current_facts_not_supplied"]], ["extra-a"])
        self.assertEqual(a["noncurrent_or_unknown_memory_ids"], ["reference-only", "stale", "unknown"])
        self.assertEqual(a["actual_noncurrent_supplied_or_cited_ids"], ["stale", "unknown"])
        self.assertNotIn("reference-only", b["actual_noncurrent_supplied_or_cited_ids"])
        self.assertIn("does not establish exposure", a["noncurrent_or_unknown_memory_ids_scope"])
        self.assertNotIn("stale fact", analysis.canonical_bytes(worksheet).decode())

    def test_blind_identity_depends_on_exact_evidence_but_not_arm_or_repetition(self):
        first, second = record(self.cases[0]), record(self.cases[0], "large")
        first["memory"]["supplied_ids"] = ["a", "b"]
        second["memory"]["supplied_ids"] = ["a"]
        repeated = deepcopy(first)
        repeated.update(arm="cascade", repetition=3)
        repeated["memory"]["supplied_ids"] = ["b", "a"]
        worksheet, mapping = analysis.make_blinded_review(self.workload, [first, second, repeated], "ab" * 32)
        self.assertEqual(len(worksheet), 2)
        self.assertEqual(sorted(len(group["observations"]) for group in mapping), [1, 2])
        self.assertEqual(analysis.make_blinded_review(self.workload, [first], "ab" * 32)[0][0]["review_id"],
                         analysis.make_blinded_review(self.workload, [repeated], "ab" * 32)[0][0]["review_id"])
        self.assertNotEqual(analysis.make_blinded_review(self.workload, [first], "ab" * 32)[0][0]["review_id"],
                            analysis.make_blinded_review(self.workload, [second], "ab" * 32)[0][0]["review_id"])
        for row in (first, second):
            row.update(status="error", response=None)
        failures, _ = analysis.make_blinded_review(self.workload, [first, second], "ab" * 32)
        self.assertEqual(len(failures), 1)
        self.assertIsNone(failures[0]["actually_supplied_current_evidence"])

    def test_request_energy_clips_intervals_without_extrapolating(self):
        samples = [{"monotonic_ns": time, "ram": {"used_mb": 5000}, "swap": {"used_mb": 100},
                    "temperatures_c": {"cpu": 40}, "gr3d_percent": 0, "vdd_in": {"instant_mw": 10000}}
                   for time in (1_000_000_000, 3_000_000_000)]
        rows = [{"started_monotonic_ns": 0, "finished_monotonic_ns": 2_000_000_000, "wall_ns": 2_000_000_000}]
        metrics = analysis.telemetry_metrics(samples, rows)
        self.assertEqual(metrics["whole_interval_energy_joules"], 20)
        self.assertEqual(metrics["request_intervals_energy_joules"], 10)
        self.assertEqual(metrics["request_interval_covered_seconds"], 1)

    def test_semantic_review_requires_mode_alignment_and_keeps_unreviewed_pending(self):
        rows = [record(self.cases[0])]
        worksheet, mapping = analysis.make_blinded_review(self.workload, rows, "ab" * 32)
        review = {"review_id": worksheet[0]["review_id"], "reviewer_type": "assistant",
                  "reviewer_id": "test-reviewer", "judgment": "complete", "notes": "Returns the required 45 tokens.",
                  "unsupported_personal_claim": False, "forbidden_or_stale_claim": False}
        report = {}
        result = analysis.apply_reviews(report, self.workload, worksheet, mapping, [review])
        self.assertEqual(result["resolved_unique_outputs"], 1)
        self.assertFalse(result["human_validation_complete"])
        self.assertEqual(result["arms"]["small"]["correct_reviewed"], 1)
        self.assertIsNone(result["arms"]["small"]["correctness_rate"])
        self.assertEqual(result["arms"]["small"]["pending_or_unattempted"], 143)
        self.assertEqual(result["arms"]["small"]["observed_correctness_rate"], 1)
        self.assertEqual(result["arms"]["small"]["conservative_correct_deliveries_per_planned"], 1 / 144)
        self.assertEqual(result["arms"]["small"]["unattempted_planned_requests"], 143)
        self.assertEqual(result["arms"]["small"]["review_status"], "fully_graded_observed_incomplete_coverage")
        with self.assertRaisesRegex(ValueError, "rubric mode"):
            analysis.apply_reviews({}, self.workload, worksheet, mapping,
                                   [{**review, "judgment": "appropriate_abstention"}])
        with self.assertRaisesRegex(ValueError, "technical-failure"):
            analysis.apply_reviews({}, self.workload, worksheet, mapping,
                                   [{**review, "judgment": "technical_failure"}])
        extra_worksheet, extra_mapping = analysis.make_blinded_review(self.workload, rows + [record(self.cases[1], index=2)], "ab" * 32)
        pending = analysis.apply_reviews({}, self.workload, extra_worksheet, extra_mapping, [review])["arms"]["small"]
        self.assertEqual(pending["observed_attempts"], 2)
        self.assertEqual(pending["pending_observed_reviews"], 1)
        self.assertIsNone(pending["observed_correctness_rate"])
        self.assertIsNone(pending["conservative_correct_deliveries_per_planned"])

    def test_conflicting_reviews_remain_pending_instead_of_selecting_a_winner(self):
        rows = [record(self.cases[0])]
        worksheet, mapping = analysis.make_blinded_review(self.workload, rows, "ab" * 32)
        review = {"review_id": worksheet[0]["review_id"], "reviewer_type": "assistant",
                  "reviewer_id": "one", "judgment": "complete", "notes": "The requested result appears.",
                  "unsupported_personal_claim": False, "forbidden_or_stale_claim": False}
        conflicting = {**review, "reviewer_id": "two", "judgment": "partial", "notes": "A required condition is missing."}
        result = analysis.apply_reviews({}, self.workload, worksheet, mapping, [review, conflicting])
        self.assertEqual(result["resolved_unique_outputs"], 0)
        self.assertEqual(result["conflicting_review_ids"], [review["review_id"]])

    def deadline_fixture(self):
        rows = [record(case, arm, repetition, index)
                for _, arm, repetition in analysis.session_slots()
                for index, case in enumerate(self.cases, 1)]
        for row in rows:
            row["wall_ns"] = 2_000_000_000
        rows[0]["wall_ns"] = rows[1]["wall_ns"] = 1_000_000_000
        rows[1].update(status="error", response=None)
        rows[2].update(wall_ns=4_000_000_000,
                       response={"speech": "Wrong answer.", "gesture_id": "NO_ACTION", "memory_used": []})
        worksheet, mapping = analysis.make_blinded_review(self.workload, rows, "ab" * 32)
        reviews = [{"review_id": entry["review_id"], "reviewer_type": "assistant", "reviewer_id": "test-reviewer",
                    "judgment": "technical_failure" if entry["delivered_response"] is None else
                                "incorrect" if entry["delivered_response"]["speech"] == "Wrong answer." else "complete",
                    "unsupported_personal_claim": False, "forbidden_or_stale_claim": False,
                    "notes": "Synthetic rubric judgment for the delivered response or absent delivery."}
                   for entry in worksheet]
        report = {"complete": True, "integrity_valid": True}
        analysis.apply_reviews(report, self.workload, worksheet, mapping, reviews)
        metrics = [{"arm": row["arm"], "repetition": row["repetition"], "case_id": row["id"],
                    "delivered": row["status"] == "ok", "wall_seconds": row["wall_ns"] / 1e9} for row in rows]
        return report, metrics, mapping

    def test_deadline_curve_has_exact_steps_and_keeps_failed_requests_in_denominator(self):
        report, metrics, mapping = self.deadline_fixture()
        curve = analysis.deadline_quality_curve(report, metrics, mapping)
        self.assertEqual(curve["status"], "complete_descriptive_curve")
        self.assertEqual(curve["max_observed_seconds"], 4)
        self.assertFalse(curve["human_validation_complete"])
        small = curve["arms"]["small"]
        self.assertEqual(small["planned_denominator"], 144)
        self.assertEqual([point["deadline_seconds"] for point in small["points"]], [0, 1, 2, 4])
        self.assertEqual([point["correct_delivered_count"] for point in small["points"]], [0, 1, 142, 142])
        self.assertEqual(small["points"][-1]["fraction_of_planned"], 142 / 144)
        self.assertEqual(curve["arms"]["large"]["points"][-1]["fraction_of_planned"], 1)
        with self.assertRaisesRegex(ValueError, "duplicated"):
            analysis.deadline_quality_curve(report, metrics, mapping + [mapping[0]])

    def test_deadline_curve_is_withheld_for_partial_unreviewed_or_invalid_collection(self):
        report, metrics, mapping = self.deadline_fixture()
        for patch in ({"complete": False}, {"integrity_valid": False}, {"semantic_review": None}):
            curve = analysis.deadline_quality_curve({**report, **patch}, metrics, mapping)
            self.assertIsNone(curve["arms"])
            self.assertTrue(curve["status"].startswith("pending"))
        report["semantic_review"]["arms"]["small"]["reviewed_attempts"] = 143
        self.assertIsNone(analysis.deadline_quality_curve(report, metrics, mapping)["arms"])

    def test_resume_requires_unchanged_complete_prefix_and_zero_request_rejection(self):
        directory = analysis.session_slots()[0][0]
        original, _ = self.write_session(analysis.session_slots()[0])
        before = analysis.read_json(original / "start.json")
        (self.run_root / "before.json").write_bytes(analysis.canonical_bytes(before))
        batch = {"status": "incomplete", "sessions": [{"arm": "small", "repetition": 1}], "snapshot": before}
        (self.run_root / "batch_finish.json").write_bytes(analysis.canonical_bytes(batch))
        rejected = self.run_root / "02_large_r1"
        rejected.mkdir()
        (rejected / "summary.json").write_bytes(analysis.canonical_bytes({"attempted": 0}))
        (rejected / "finish.json").write_bytes(analysis.canonical_bytes({
            "failure": {"message": "Stage 2 startup temperature must be below 55 C"},
            "resident_models": [], "cleanup_errors": [],
        }))
        prior = self.root / "prior"
        self.run_root.rename(prior)
        self.run_root.mkdir()
        (self.run_root / directory).symlink_to(prior / directory, target_is_directory=True)
        (self.run_root / "before.json").write_bytes((prior / "before.json").read_bytes())
        launcher = Path(analysis.__file__).with_name("resume_complete_system_batch.py").read_bytes()
        (self.run_root / "resume_launcher.py").write_bytes(launcher)
        origin = {
            "schema_version": 1, "prior_root": str(prior), "freeze_sha256": analysis.file_hash(self.freeze_path),
            "resume_script_sha256": sha256(launcher).hexdigest(),
            "scheduler_handoff_temperature_c_exclusive": 54,
            "unchanged_arm_start_temperature_c_exclusive": 55,
            "retained_complete_sessions": [{"directory": directory, "source": str(prior / directory),
                "observations_sha256": analysis.file_hash(prior / directory / "observations.jsonl"),
                "finish_sha256": analysis.file_hash(prior / directory / "finish.json")}],
            "prior_batch_finish_sha256": analysis.file_hash(prior / "batch_finish.json"),
            "prior_startup_rejection": str(prior / "02_large_r1"),
        }
        (self.run_root / "resume_origin.json").write_bytes(analysis.canonical_bytes(origin))
        report, _, rows, _ = analysis.analyze(self.workload_path, self.freeze_path, self.run_root)
        self.assertTrue(report["integrity_valid"], report)
        self.assertEqual(len(rows), 48)
        self.assertEqual(report["resume_provenance"]["retained_complete_session_count"], 1)
        self.assertTrue(report["resume_provenance"]["launcher_archived"])
        (prior / "02_large_r1" / "observations.jsonl").write_text('{"already_attempted":true}\n')
        invalid, _, _, _ = analysis.analyze(self.workload_path, self.freeze_path, self.run_root)
        self.assertFalse(invalid["integrity_valid"])
        self.assertTrue(any("attempted inference" in error for error in invalid["integrity_errors"]))

    def test_undeclared_link_is_reported_without_report_rendering_failure(self):
        directory = analysis.session_slots()[0][0]
        original, _ = self.write_session(analysis.session_slots()[0])
        retained = self.root / "retained"
        original.rename(retained)
        original.symlink_to(retained, target_is_directory=True)
        report, _, _, _ = analysis.analyze(self.workload_path, self.freeze_path, self.run_root)
        self.assertFalse(report["integrity_valid"])
        self.assertIn("linked sessions lack resume_origin.json", analysis.render_markdown(report))

    def test_actual_memory_scope_uses_synthetic_seed_and_rejects_foreign_snapshot_profile(self):
        path, _ = self.write_session(analysis.session_slots()[0])
        manifest = analysis.read_json(path / "manifest.json")
        manifest["config"]["memory"] = {"database_path": "/unused/application-memory.sqlite3",
                                           "profile_id": "unused-app-profile", "retention_days": 30}
        (path / "manifest.json").write_bytes(analysis.canonical_bytes(manifest))
        report, _, _, _ = analysis.analyze(self.workload_path, self.freeze_path, self.run_root)
        self.assertTrue(report["integrity_valid"])
        scope = report["sessions"][0]["memory_execution_scope"]
        self.assertEqual(scope["profile_id"], "offline-synthetic-profile")
        self.assertEqual(scope["retention_days"], 7)
        self.assertEqual(scope["database_path"], str(path / "memory.sqlite3"))
        self.assertEqual(report["memory_execution"]["observed_setup_sessions"], 1)
        setup = analysis.read_json(path / "memory_setup.json")
        setup["snapshot"] = [{"profile_id": "foreign-profile"}]
        setup["snapshot_sha256"] = sha256(analysis.canonical_bytes(setup["snapshot"])).hexdigest()
        (path / "memory_setup.json").write_bytes(analysis.canonical_bytes(setup))
        invalid, _, _, _ = analysis.analyze(self.workload_path, self.freeze_path, self.run_root)
        self.assertFalse(invalid["integrity_valid"])
        self.assertTrue(any("outside the synthetic" in error for error in invalid["sessions"][0]["errors"]))

    def test_continued_schedule_preserves_interrupted_tail_and_does_not_claim_full_coverage(self):
        paths = []
        for index, slot in enumerate(analysis.session_slots()):
            path, _ = self.write_session(slot, status="interrupted" if index == 2 else "complete",
                                         count=40 if index == 2 else 48)
            paths.append(path)
        interrupted = paths[2]
        finish = analysis.read_json(interrupted / "finish.json")
        message = "available memory crossed the runtime floor"
        finish.update(guard_violation=message, failure={"type": "SafetyGateError", "message": message})
        (interrupted / "finish.json").write_bytes(analysis.canonical_bytes(finish))
        rows = analysis.read_jsonl(interrupted / "observations.jsonl")
        rows[-1]["status"] = "interrupted"
        (interrupted / "observations.jsonl").write_bytes(b"".join(analysis.canonical_bytes(row) for row in rows))
        baseline = analysis.read_json(paths[0] / "start.json")
        (self.run_root / "before.json").write_bytes(analysis.canonical_bytes(baseline))
        batch = {"status": "incomplete", "sessions": [{"arm": arm, "repetition": repetition}
                 for _, arm, repetition in analysis.session_slots()[:2]], "snapshot": baseline}
        (self.run_root / "batch_finish.json").write_bytes(analysis.canonical_bytes(batch))
        items = []
        for path, (_, arm, repetition) in zip(paths, analysis.session_slots()):
            saved_finish = analysis.read_json(path / "finish.json")
            count = len(analysis.read_jsonl(path / "observations.jsonl"))
            items.append({"directory": path.name, "arm": arm, "repetition": repetition,
                          "status": saved_finish["status"], "attempted": count, "planned": 48,
                          "unattempted": 48 - count, "guard_violation": saved_finish["guard_violation"],
                          "artifact_sha256": {p.name: analysis.file_hash(p) for p in path.iterdir() if p.is_file()}})
        for name in ("continued_schedule_launcher.py", "resume_launcher.py"):
            (self.run_root / name).write_bytes(b"archived test launcher\n")
        origin = {"schema_version": 1, "freeze_sha256": analysis.file_hash(self.freeze_path),
                  "launcher_sha256": analysis.file_hash(self.run_root / "continued_schedule_launcher.py"),
                  "dependency_sha256": {"resume_complete_system_batch.py": analysis.file_hash(self.run_root / "resume_launcher.py")},
                  "prior_batch_finish_sha256": analysis.file_hash(self.run_root / "batch_finish.json"),
                  "recoverable_failure_messages": [message, "telemetry RAM floor crossed"],
                  "scheduler_handoff_temperature_c_exclusive": 54, "unchanged_arm_start_temperature_c_exclusive": 55,
                  "retained_terminal_sessions": items[:3],
                  "remaining_slots": [{"index": i, "arm": arm, "repetition": rep}
                                      for i, (_, arm, rep) in enumerate(analysis.session_slots(), 1) if i > 3]}
        (self.run_root / "schedule_continuation_origin.json").write_bytes(analysis.canonical_bytes(origin))
        (self.run_root / "continued_schedule_progress.jsonl").write_bytes(b"".join(analysis.canonical_bytes(item) for item in items[3:]))
        (self.run_root / "continued_schedule_finish.json").write_bytes(analysis.canonical_bytes({
            "status": "complete_schedule_with_session_failures", "failure": None, "sessions": items, "snapshot": baseline}))
        report, _, _, _ = analysis.analyze(self.workload_path, self.freeze_path, self.run_root)
        self.assertTrue(report["integrity_valid"], report)
        self.assertFalse(report["complete"])
        self.assertEqual(report["observed_attempts"], 424)
        continuation = report["schedule_continuation_provenance"]
        self.assertTrue(continuation["schedule_terminal"])
        self.assertEqual(continuation["resource_interrupted_sessions"][0]["unattempted"], 8)
        for path in paths[4:]:
            shutil.rmtree(path)
        (self.run_root / "continued_schedule_progress.jsonl").write_bytes(analysis.canonical_bytes(items[3]))
        (self.run_root / "continued_schedule_finish.json").write_bytes(analysis.canonical_bytes({
            "status": "incomplete", "failure": {"type": "SafetyGateError", "message": "startup swap gate remains exceeded"},
            "sessions": items[:4], "snapshot": baseline}))
        blocked, _, _, _ = analysis.analyze(self.workload_path, self.freeze_path, self.run_root)
        self.assertTrue(blocked["integrity_valid"], blocked)
        self.assertEqual(blocked["observed_attempts"], 184)
        self.assertEqual(blocked["arms"]["cascade"]["distinct_observed_cases"], 40)
        self.assertEqual(blocked["arms"]["large"]["distinct_observed_cases"], 48)
        self.assertFalse(blocked["complete"])
        stopped = blocked["schedule_continuation_provenance"]
        self.assertTrue(stopped["orchestration_finished"])
        self.assertFalse(stopped["schedule_terminal"])
        self.assertEqual(len(stopped["unattempted_slots"]), 5)
        self.assertIn("startup swap gate remains exceeded", analysis.render_markdown(blocked))
        (interrupted / "summary.json").write_bytes(analysis.canonical_bytes({"status": "rewritten"}))
        invalid, _, _, _ = analysis.analyze(self.workload_path, self.freeze_path, self.run_root)
        self.assertFalse(invalid["integrity_valid"])
        self.assertTrue(any("terminal artifact changed" in error for error in invalid["integrity_errors"]))


if __name__ == "__main__":
    unittest.main()
