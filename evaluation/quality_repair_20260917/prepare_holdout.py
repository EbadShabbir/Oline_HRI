"""Bind independently authored cases only after checking a final source freeze.

Do not invoke this command until development is finished. It performs the first
semantic case read, records that opening, and never overwrites an earlier
opening or cohort. Merely displaying --help opens no candidate or author files.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
EXPECTED_COUNTS = {"none": 10, "optional": 3, "required": 3, "clarify": 4}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def save_new(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def verified_candidate(directory):
    """Verify the candidate before touching authoring files, including bytes."""
    manifest_path = directory / "candidate_freeze.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if "cases_sha256" in manifest or (directory / "cases.json").exists():
        raise ValueError("final candidate must be frozen without opening any cases")
    sources = manifest["source_sha256"]
    expected_runtime = {
        str(path.relative_to(ROOT))
        for path in [*sorted((ROOT / "src/oline_hri").glob("*.py")),
                     *sorted((ROOT / "src/oline_hri").glob("*.json")),
                     ROOT / "scripts/run_routing_reliability.py",
                     ROOT / "scripts/run_pair_remediation_validation.py",
                     ROOT / "scripts/complete_system_device_guard.py",
                     HERE / "run_guarded.py"]
    }
    if set(sources) != expected_runtime:
        raise ValueError("runtime file set differs from final freeze")
    for relative, expected in sources.items():
        for base in (ROOT, directory / "candidate_source"):
            if digest(base / relative) != expected:
                raise ValueError("candidate source drift: " + str(base / relative))
    tests = manifest["tests_sha256"]
    if set(tests) != {path.name for path in (ROOT / "tests").glob("*.py")}:
        raise ValueError("test file set differs from final freeze")
    for relative, expected in tests.items():
        for base in (ROOT / "tests", directory / "tests"):
            if digest(base / relative) != expected:
                raise ValueError("candidate test drift: " + str(base / relative))
    if digest(directory / "working_changes.diff") != manifest["working_diff_sha256"]:
        raise ValueError("candidate working diff drift")
    return manifest


def prepare(args):
    final = args.final_candidate.resolve()
    output = args.output_dir.resolve()
    opening_path = args.opening_record.resolve()
    if output.exists() or opening_path.exists():
        raise ValueError("output cohort or opening record already exists")
    for value in (args.cases_sha256, args.notes_sha256):
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("author hashes must be exact lowercase SHA256 strings")
    candidate = verified_candidate(final)
    cases_path = args.authoring_dir / "cases.json"
    notes_path = args.authoring_dir / "authoring_notes.md"
    # Hash bytes only after the final source and tests verify. No semantic read
    # occurs until both supplied author hashes match.
    cases_bytes = cases_path.read_bytes()
    notes_bytes = notes_path.read_bytes()
    if sha256(cases_bytes).hexdigest() != args.cases_sha256:
        raise ValueError("authored case hash differs from independently supplied hash")
    if sha256(notes_bytes).hexdigest() != args.notes_sha256:
        raise ValueError("authored notes hash differs from independently supplied hash")
    opened_at = datetime.now(timezone.utc).isoformat()
    save_new(opening_path, {
        "created_at": opened_at,
        "event": "First semantic read starts after final source/test verification.",
        "final_candidate": str(final),
        "final_candidate_manifest_sha256": digest(final / "candidate_freeze.json"),
        "candidate_frozen_at": candidate["created_at"],
        "author_cases_sha256": args.cases_sha256,
        "author_notes_sha256": args.notes_sha256,
        "candidate_source_and_tests_verified_before_authoring_read": True,
        "inference_started": False,
        "failure_policy": "An opening remains recorded even if later validation fails; do not erase or reclassify it.",
    })
    cases = json.loads(cases_bytes)
    if not isinstance(cases, list) or len(cases) != 20:
        raise ValueError("authored holdout must be a plain list of twenty cases")
    modes = []
    identifiers = []
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("text"), str) or not case["text"].strip():
            raise ValueError("invalid holdout request")
        identifiers.append(case["id"])
        expected = case["expected_modes"]
        if not isinstance(expected, list) or len(expected) != 1 or expected[0] not in EXPECTED_COUNTS:
            raise ValueError("holdout case must have one declared dependency mode")
        modes.append(expected[0])
        rubric = case["rubric"]
        for field in ("required_components", "forbidden"):
            if not isinstance(rubric[field], list) or not all(isinstance(item, str) for item in rubric[field]):
                raise ValueError("invalid holdout rubric components")
        if not rubric["required_components"]:
            raise ValueError("holdout case requires explicit grading components")
        for field in ("clarification_expected", "general_component_expected"):
            if type(rubric[field]) is not bool:
                raise ValueError("holdout rubric flags must be boolean")
    if identifiers != [f"quality_holdout_{index:03d}" for index in range(1, 21)]:
        raise ValueError("holdout IDs or frozen order differ from author contract")
    if dict(Counter(modes)) != EXPECTED_COUNTS:
        raise ValueError("holdout mode counts differ from protocol")
    shutil.copytree(final, output)
    shutil.copyfile(output / "candidate_freeze.json", output / "preopening_candidate_freeze.json")
    (output / "cases.json").write_bytes(cases_bytes)
    (output / "authoring_notes.md").write_bytes(notes_bytes)
    candidate.update({"cases_sha256": args.cases_sha256, "cases_bound_at": opened_at,
                      "preopening_candidate_manifest_sha256": digest(final / "candidate_freeze.json")})
    # This cohort copy is newly created; the original final freeze is untouched.
    (output / "candidate_freeze.json").write_text(json.dumps(candidate, indent=2) + "\n")
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "case_count": len(cases),
              "mode_counts": dict(Counter(modes)), "case_ids": identifiers,
              "opening_record": str(opening_path), "opening_record_sha256": digest(opening_path),
              "parent_final_candidate": str(final),
              "parent_final_manifest_sha256": digest(final / "candidate_freeze.json"),
              "source_sha256_unchanged": candidate["source_sha256"],
              "tests_sha256_unchanged": candidate["tests_sha256"],
              "author_cases_sha256": args.cases_sha256,
              "author_notes_sha256": args.notes_sha256,
              "inference_started": False}
    save_new(output / "holdout_preparation.json", report)
    return {"cohort": str(output), "case_count": len(cases),
            "mode_counts": report["mode_counts"], "opening_record": str(opening_path)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final-candidate", required=True, type=Path)
    parser.add_argument("--authoring-dir", required=True, type=Path)
    parser.add_argument("--cases-sha256", required=True)
    parser.add_argument("--notes-sha256", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--opening-record", type=Path, default=HERE / "holdout_opening.json")
    args = parser.parse_args(argv)
    try:
        result = prepare(args)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, "HOLDOUT PREPARATION FAILED: " + str(error) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
