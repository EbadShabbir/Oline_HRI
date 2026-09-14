"""Offline audit of the exact v2 run resumed after a zero-request thermal gate.

The recorded adapter supplies the exact frozen swap policy. This adapter keeps
the original resume audit and resolves only its legacy error-message mismatch
after independently verifying the rejected startup's saved measurements.
Existing analyzers, freezes, execution sources, and raw evidence are unchanged.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_v2_recorded as recorded

base, post = recorded.base, recorded.post
check = recorded.check
RECORDED_ADAPTER_SHA256 = "c254d3c9c44e8d1fffaf08454cc3081a8206296ec9510601ba360f2a28016fae"
LEGACY_FINDING = "excluded startup failure was not the declared temperature handoff rejection"
REVISED_MESSAGE = "revised startup temperature must be below 55 C"
inspect_recorded_session = recorded.inspect_recorded_session


def verify_rejected_startup(path, frozen):
    """Return provenance only after real recorded counters prove the exclusion."""
    policy = frozen["device_policy"]
    start, summary, finish = [base.read_json(path / name) for name in ("start.json", "summary.json", "finish.json")]
    check(summary.get("attempted") == 0 and summary.get("delivered") == 0
          and summary.get("planned") == 48 and summary.get("status") == "blocked_preflight"
          and summary.get("profile_id") == post.PROFILE_ID, "rejected startup has an unexpected summary")
    slots = {(arm, repetition) for _, arm, repetition in base.session_slots(post.frozen_arm_orders(frozen))}
    check((summary.get("arm"), summary.get("repetition")) in slots, "rejected startup is outside the frozen schedule")
    absent = ("manifest.json", "observations.jsonl", "http_calls.jsonl", "memory_setup.json", "memory.sqlite3")
    check(not any((path / name).exists() for name in absent), "rejected startup contains inference or setup artifacts")
    check(finish.get("failure") == {"type": "SafetyGateError", "message": REVISED_MESSAGE},
          "rejected startup is not the exact revised temperature error")
    check(finish.get("admitted") is False and finish.get("status") == "blocked_preflight"
          and finish.get("profile_id") == post.PROFILE_ID, "rejected startup was admitted or has an unknown status")
    check(finish.get("source_sha256") == frozen["source_sha256"]
          and all(finish.get(key) is True for key in
                  ("source_unchanged", "model_metadata_unchanged", "ollama_version_unchanged")),
          "rejected startup lacks unchanged source/model/server proof")
    check(finish.get("cleanup_errors") == [] and finish.get("guard_violation") is None
          and finish.get("telemetry_reader_error") is None, "rejected startup has unresolved cleanup or telemetry")
    temperatures = start.get("temperatures_c")
    check(isinstance(temperatures, dict) and temperatures and all(
        type(value) in (int, float) and math.isfinite(value) and value >= 0
        for value in temperatures.values()), "rejected startup lacks numeric temperature measurements")
    peak = max(temperatures.values())
    check(peak >= policy["max_start_temperature_c_exclusive"] == 55,
          "rejected startup did not record a temperature at or above 55 C")
    for snapshot in (start, finish):
        memory = snapshot.get("memory") or {}
        check(memory.get("swap_total_kib") == policy["expected_swap_total_kib"], "rejected startup swap capacity differs")
        check(snapshot.get("resident_models") == [] and type(snapshot.get("fan_pwm")) is int
              and snapshot["fan_pwm"] > 0, "rejected startup has resident models or no running fan")
        trips = snapshot.get("thermal_trip_events")
        check(isinstance(trips, dict) and trips and all(type(value) is int and value == 0 for value in trips.values()),
              "rejected startup has unavailable or nonzero thermal trips")
        check(snapshot.get("power_mode") == "NV Power Mode: 15W\n0", "rejected startup power mode differs")
    check(isinstance(start.get("boot_id"), str) and start["boot_id"]
          and all(finish.get(key) == start[key] for key in ("boot_id", "power_mode", "thermal_trip_events")),
          "rejected startup changed boot/power/trip state")
    memory = start["memory"]
    check(type(memory.get("mem_available_kib")) is int and memory["mem_available_kib"] >= policy["min_start_available_kib"]
          and type(memory.get("swap_used_kib")) is int and 0 <= memory["swap_used_kib"] <= policy["max_start_swap_used_kib"],
          "rejected startup did not meet the other memory admission gates")
    return {"path": str(path.resolve()), "measured_start_max_temperature_c": peak,
            "attempted_requests": 0, "delivered_requests": 0, "absence_checked": list(absent),
            "source_model_server_unchanged": True, "cleanup_empty": True,
            "failure": finish["failure"],
            "artifact_sha256": {name: base.file_hash(path / name) for name in ("start.json", "summary.json", "finish.json")}}


def resolve_resume_wording(report, freeze_path):
    """Preserve every other audit error and the original finding history."""
    frozen = recorded.validate_recorded_freeze(freeze_path)
    resume = report.get("resume_provenance")
    check(isinstance(resume, dict) and isinstance(resume.get("origin"), dict), "resumed analysis requires an audited origin")
    origin = resume["origin"]
    paths = [Path(origin["prior_startup_rejection"])]
    local = Path(report["run_root"]) / "startup_rejections"
    if local.is_dir():
        paths.extend(sorted(path for path in local.iterdir() if path.is_dir()))
    retained = origin["retained_complete_sessions"]
    slots = base.session_slots(post.frozen_arm_orders(frozen))
    check(0 < len(retained) < len(slots), "resume retained prefix is invalid")
    expected_rejection = Path(origin["prior_root"]) / slots[len(retained)][0]
    check(paths[0].resolve() == expected_rejection.resolve(), "prior rejection is not the first unattempted frozen slot")
    proofs = [verify_rejected_startup(path, frozen) for path in paths]
    check(len({proof["path"] for proof in proofs}) == len(proofs), "duplicate excluded rejection paths")
    original_errors = list(resume["errors"])
    check(original_errors.count(LEGACY_FINDING) == len(proofs), "legacy finding count differs from proven v2 rejections")
    check(report["integrity_errors"].count("resume: " + LEGACY_FINDING) == len(proofs),
          "top-level legacy finding count differs")
    resume["original_errors_before_wording_compatibility"] = original_errors
    resume["errors"] = [error for error in original_errors if error != LEGACY_FINDING]
    resume["valid"] = not resume["errors"]
    resume["revised_temperature_wording_proofs"] = proofs
    resume["resolved_legacy_finding"] = {"message": LEGACY_FINDING, "count": len(proofs),
                                         "reason": "Exact v2 wording and the measured zero-request startup rejection are independently proven."}
    report["integrity_errors"] = [error for error in report["integrity_errors"] if error != "resume: " + LEGACY_FINDING]
    report["integrity_valid"] = (not report["integrity_errors"] and all(
        session["valid"] for session in report["sessions"] if session["status"] != "missing"))
    report["complete"] = (report["integrity_valid"] and report["observed_attempts"] == 432
                           and all(session["complete"] for session in report["sessions"]))
    report["incomplete"] = not report["complete"]
    return proofs


def analyze(workload_path, freeze_path, run_root):
    check(base.file_hash(Path(recorded.__file__)) == RECORDED_ADAPTER_SHA256,
          "recorded-analysis compatibility dependency changed")
    freeze_path = Path(freeze_path)
    report, workload, rows, metrics = recorded.analyze(workload_path, freeze_path, run_root)
    proofs = resolve_resume_wording(report, freeze_path)
    swap_correction = dict(report["analysis_compatibility_correction"])
    swap_correction["original_adapter_archive_name"] = swap_correction["adapter_archive"]
    swap_correction["adapter_archive"] = "analysis_compatibility_recorded.py"
    report["analysis_compatibility_correction"] = {
        "schema_version": 1, "kind": "post_collection_resumed_analyzer_compatibility_correction",
        "adapter_path": str(Path(__file__).resolve()), "adapter_sha256": base.file_hash(Path(__file__)),
        "adapter_archive": "analysis_compatibility_adapter.py",
        "dependency_path": str(Path(recorded.__file__).resolve()),
        "dependency_sha256": RECORDED_ADAPTER_SHA256, "dependency_archive": "analysis_compatibility_recorded.py",
        "recorded_swap_compatibility": swap_correction,
        "resume_wording_scope": "Resolve only the frozen inspector's legacy temperature-message finding after stronger saved-evidence checks; preserve all other findings",
        "proven_zero_request_rejections": proofs,
        "other_artifact_and_telemetry_audits_retained": True, "runtime_or_generation_changes": False,
        "scoring_changes": False, "raw_artifacts_modified": False, "additional_module_bindings_changed": False,
    }
    return report, workload, rows, metrics


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", required=True, type=Path)
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--blind-seed")
    parser.add_argument("--blind-seed-from", type=Path)
    parser.add_argument("--reviews", action="append", default=[], type=Path)
    args = parser.parse_args(argv)
    if args.blind_seed and args.blind_seed_from:
        parser.error("choose --blind-seed or --blind-seed-from")
    report, workload, rows, metrics = analyze(args.workload, args.freeze, args.run_root)
    seed = args.blind_seed or (base.read_json(args.blind_seed_from)["private_blinding_seed"]
                              if args.blind_seed_from else secrets.token_hex(32))
    worksheet, mapping = base.make_blinded_review(workload, rows, seed)
    review = None
    if args.reviews:
        review = base.apply_reviews(report, workload, worksheet, mapping,
                                    [item for path in args.reviews for item in base.read_jsonl(path)])
        report["semantic_review_input_sha256"] = {str(path): base.file_hash(path) for path in args.reviews}
    curve = base.deadline_quality_curve(report, metrics, mapping)
    report["deadline_quality_curve"] = curve
    correction = report["analysis_compatibility_correction"]
    os.umask(0o077)
    args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, source, expected in ((correction["adapter_archive"], Path(__file__), correction["adapter_sha256"]),
                                   (correction["dependency_archive"], Path(recorded.__file__), RECORDED_ADAPTER_SHA256)):
        with (args.output_dir / name).open("xb") as stream:
            stream.write(source.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        check(base.file_hash(args.output_dir / name) == expected, "analysis adapter changed while archiving")
    base.write_new(args.output_dir / "analysis_compatibility_correction.json", correction)
    base.write_new(args.output_dir / "analysis.json", report)
    base.write_new(args.output_dir / "row_metrics.jsonl", metrics, lines=True)
    base.write_new(args.output_dir / "blinded_review.jsonl", worksheet, lines=True)
    base.write_new(args.output_dir / "blinded_mapping.jsonl", mapping, lines=True)
    if review is not None:
        base.write_new(args.output_dir / "semantic_review.json", review)
    if curve["status"] == "complete_descriptive_curve":
        base.write_new(args.output_dir / "deadline_quality_curve.json", curve)
    base.write_new(args.output_dir / "review_manifest.json", {
        "status": review["status"] if review else "pending_semantic_review",
        "unique_review_entries": len(worksheet), "mapped_raw_observations": len(rows),
        "private_blinding_seed": seed, "grouping_version": 2,
        "blinded_worksheet_sha256": base.file_hash(args.output_dir / "blinded_review.jsonl"),
        "mapping_sha256": base.file_hash(args.output_dir / "blinded_mapping.jsonl"),
        "analysis_compatibility_correction": correction,
        "grouping": "identical case, delivered response, and exact supplied-memory ID set; technical non-deliveries grouped per case",
        "reviewer_warning": "Keep the mapping and seed away from blinded raters. Assistant review is not independent human validation.",
        "submission_fields": ["review_id", "reviewer_type", "reviewer_id", "judgment",
                              "unsupported_personal_claim", "forbidden_or_stale_claim", "notes"],
    })
    markdown = base.render_markdown(report) + (
        "\nOffline compatibility corrections retain the exact frozen v2 swap policy and accept the revised "
        "startup-temperature wording only after measured zero-request rejection proof. Other provenance "
        "findings and scoring are unchanged. Both adapter sources and the original findings accompany this report. "
        f"Resumed adapter SHA-256: `{correction['adapter_sha256']}`.\n")
    with (args.output_dir / "report.md").open("x", encoding="utf-8") as stream:
        stream.write(markdown)
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({"complete": report["complete"], "integrity_valid": report["integrity_valid"],
                      "observed_attempts": report["observed_attempts"], "review_entries": len(worksheet),
                      "adapter_sha256": correction["adapter_sha256"],
                      "output_dir": str(args.output_dir.resolve())}), flush=True)
    return 0 if report["integrity_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
