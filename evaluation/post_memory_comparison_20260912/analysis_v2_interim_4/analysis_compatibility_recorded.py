"""Offline compatibility adapter for the exact recorded amended v2 experiment.

The frozen analyzer retained the older swap-policy constants although the
runner and freeze recorded the amended policy before inference. This adapter
changes only those two analysis checks, within a finally-restored scope. It
does not install runtime guards, change data, run inference, or change scoring.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import analyze_complete_system as base
import analyze_post_memory_comparison as post
import post_memory_device_guard as guard


KNOWN_FREEZE_SHA256 = "6497504cb7a3fd29c2b3b3740aa26f1a77dad8d626cbf0fedcabed997bfc7783"
LEGACY_LIMITS = {
    "min_start_available_kib": 2097152, "max_start_swap_used_kib": 786432,
    "max_start_temperature_c_exclusive": 55.0,
    "min_runtime_available_kib": 786432, "max_runtime_swap_used_kib": 1048576,
    "max_runtime_temperature_c_exclusive": 68.0,
}
SWAP_OVERRIDES = {"max_start_swap_used_kib": 3639464, "max_runtime_swap_used_kib": 3639464}
DEPENDENCIES = ("scripts/analyze_complete_system.py", "scripts/analyze_post_memory_comparison.py",
                "scripts/analyze_arc_capability.py", "scripts/post_memory_device_guard.py")


def check(condition, message):
    if not condition:
        raise ValueError(message)


def validate_recorded_freeze(freeze_path):
    check(base.file_hash(freeze_path) == KNOWN_FREEZE_SHA256, "adapter accepts only the exact known v2 freeze")
    frozen = base.read_json(freeze_path)
    post.validate_freeze_contract(frozen)
    policy = guard.policy_dict()
    check(frozen.get("device_policy") == policy, "recorded v2 device policy differs from the frozen guard")
    check(policy.get("policy_id") == "post_memory_existing_swap_reserve_v2"
          and policy.get("expected_swap_total_kib") == 3901608
          and policy.get("logical_swap_reserve_kib") == 262144,
          "unknown swap-capacity amendment")
    check(all(policy[key] == value for key, value in SWAP_OVERRIDES.items()), "unexpected amended swap limits")
    check(all(policy[key] == value for key, value in LEGACY_LIMITS.items() if key not in SWAP_OVERRIDES),
          "compatibility adapter cannot change a non-swap limit")
    for relative in DEPENDENCIES:
        expected = frozen["source_sha256"][relative]
        check(base.file_hash(ROOT / relative) == expected, f"analysis dependency differs from freeze: {relative}")
        archived = freeze_path.parent / "source" / relative
        check(archived.is_file() and base.file_hash(archived) == expected,
              f"archived analysis dependency differs: {relative}")
    protocol = freeze_path.parent / "protocol.md"
    check(base.file_hash(protocol) == frozen["protocol_sha256"], "archived amendment protocol differs")
    return frozen


def validate_manifest_policy(session_path, frozen):
    path = session_path / "manifest.json"
    if not path.is_file():
        return
    manifest = base.read_json(path)
    check(manifest.get("frozen") == frozen, "session manifest differs from the exact v2 freeze")
    check(manifest.get("device_policy") == frozen["device_policy"], "session device policy differs from v2 freeze")
    for name in ("start.json", "finish.json"):
        snapshot_path = session_path / name
        if snapshot_path.is_file():
            snapshot = base.read_json(snapshot_path)
            check((snapshot.get("memory") or {}).get("swap_total_kib")
                  == frozen["device_policy"]["expected_swap_total_kib"],
                  f"recorded swap capacity differs: {session_path.name}/{name}")


@contextmanager
def analysis_swap_limits():
    """Single-process analysis scope; preserve dict identity and all other keys."""
    check(base.EXPECTED_LIMITS == LEGACY_LIMITS, "base analysis limits were already altered")
    original = dict(base.EXPECTED_LIMITS)
    try:
        for key, value in SWAP_OVERRIDES.items():
            base.EXPECTED_LIMITS[key] = value
        yield
    finally:
        for key in SWAP_OVERRIDES:
            base.EXPECTED_LIMITS[key] = original[key]


def correction_metadata(freeze_path):
    return {
        "schema_version": 1,
        "kind": "post_collection_analyzer_compatibility_correction",
        "reason": "Frozen analyzer retained older swap comparison constants while the pre-inference v2 freeze and runtime guard used the documented amended limits.",
        "adapter_path": str(Path(__file__).resolve()), "adapter_sha256": base.file_hash(Path(__file__)),
        "adapter_archive": "analysis_compatibility_adapter.py",
        "known_freeze_sha256": KNOWN_FREEZE_SHA256,
        "protocol_sha256": base.file_hash(freeze_path.parent / "protocol.md"),
        "changed_binding": "analyze_complete_system.EXPECTED_LIMITS (two dictionary entries only)",
        "old_swap_limits_kib": {key: LEGACY_LIMITS[key] for key in SWAP_OVERRIDES},
        "recorded_swap_limits_kib": dict(SWAP_OVERRIDES),
        "non_swap_limits_unchanged": True, "other_artifact_and_telemetry_audits_retained": True,
        "runtime_or_generation_changes": False, "scoring_changes": False, "raw_artifacts_modified": False,
        "module_bindings_restored_after_analysis": True,
        "scope": "Compatibility with the exact existing recorded experiment, not a new resource-policy decision or feasibility result",
    }


def analyze(workload_path, freeze_path, run_root):
    workload_path, freeze_path, run_root = map(Path, (workload_path, freeze_path, run_root))
    frozen = validate_recorded_freeze(freeze_path)
    for directory, _, _ in base.session_slots(post.frozen_arm_orders(frozen)):
        validate_manifest_policy(run_root / directory, frozen)
    with analysis_swap_limits():
        report, workload, rows, metrics = post.analyze(workload_path, freeze_path, run_root)
    report["analysis_compatibility_correction"] = correction_metadata(freeze_path)
    return report, workload, rows, metrics


def inspect_recorded_session(workload_path, freeze_path, run_root, directory):
    """Audit one terminal session without reading any active session's outputs."""
    workload_path, freeze_path, run_root = map(Path, (workload_path, freeze_path, run_root))
    frozen = validate_recorded_freeze(freeze_path)
    slots = {name: (arm, repetition) for name, arm, repetition in base.session_slots(post.frozen_arm_orders(frozen))}
    check(directory in slots, "session is outside the frozen schedule")
    check(base.file_hash(workload_path) == frozen["workload_sha256"], "workload differs from freeze")
    check((run_root / directory / "finish.json").is_file(), "single-session inspection requires a terminal artifact")
    workload = base.read_json(workload_path)
    base.validate_workload(workload)
    validate_manifest_policy(run_root / directory, frozen)
    arm, repetition = slots[directory]
    with analysis_swap_limits():
        session, rows = base.inspect_session(run_root, directory, arm, repetition, workload, frozen,
                                            comparison_profile=post.PROFILE_ID)
    session["analysis_compatibility_correction"] = correction_metadata(freeze_path)
    return session, rows


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
    with (args.output_dir / correction["adapter_archive"]).open("xb") as stream:
        stream.write(Path(__file__).read_bytes())
        stream.flush()
        os.fsync(stream.fileno())
    check(base.file_hash(args.output_dir / correction["adapter_archive"]) == correction["adapter_sha256"],
          "adapter changed while archiving")
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
        "\nOffline analyzer compatibility correction: only the two swap-limit comparisons were aligned "
        "with the exact pre-inference v2 freeze (3,639,464 KiB each). Other audits and scoring are unchanged. "
        f"Adapter SHA-256: `{correction['adapter_sha256']}`. The archived adapter and correction metadata accompany this report.\n")
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
