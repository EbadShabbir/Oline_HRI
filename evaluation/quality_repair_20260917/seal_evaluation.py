"""Seal one prepared cohort before inference; never overwrite an earlier seal.

Example:
  python3 seal_evaluation.py --cohort-dir development_v2 \
    --scope 'Known development iteration, not fresh validation.' \
    --artifact ../protocol.md --artifact ../review_a/review_plan.md \
    --artifact ../review_b/review_plan.md

Prepare candidate_freeze.json, candidate_source, and cases.json first. Mandatory
corpus/candidate hashes are included automatically. Add every additional
preregistered artifact explicitly, relative to the cohort directory.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seal(cohort, scope, artifacts):
    cohort = Path(cohort).resolve()
    target = cohort / "evaluation_freeze.json"
    if target.exists():
        raise ValueError("evaluation freeze already exists; use a new cohort directory")
    if (cohort / "collection").exists():
        raise ValueError("collection already exists; refusing a post-inference freeze")
    candidate_path = cohort / "candidate_freeze.json"
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    cases_hash = sha(cohort / "cases.json")
    if candidate.get("cases_sha256") != cases_hash:
        raise ValueError("candidate manifest does not freeze these exact case bytes")
    sources = candidate["source_sha256"]
    if not sources:
        raise ValueError("candidate source manifest is empty")
    for relative, expected in sources.items():
        for base in (ROOT, cohort / "candidate_source"):
            path = base / relative
            if not path.is_file() or sha(path) != expected:
                raise ValueError("candidate source differs: " + str(path))
    files = dict.fromkeys(["cases.json", "candidate_freeze.json", *artifacts])
    hashes = {}
    for relative in files:
        path = cohort / relative
        if not path.is_file():
            raise ValueError("missing preregistered artifact: " + str(path))
        hashes[relative] = sha(path)
    value = {"created_at": datetime.now(timezone.utc).isoformat(), "source_sha256": sources,
             "cases_sha256": cases_hash, "artifact_sha256": hashes, "scope": scope,
             "inference_started": False}
    with target.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return target, value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-dir", type=Path, required=True)
    parser.add_argument("--scope", required=True, help="Explicit known-development/replay or fresh-holdout scope")
    parser.add_argument("--artifact", action="append", default=[],
                        help="Additional artifact path relative to cohort; repeat as needed")
    args = parser.parse_args(argv)
    if not args.scope.strip():
        parser.error("scope must be nonempty")
    try:
        path, value = seal(args.cohort_dir, args.scope, args.artifact)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, "SEAL FAILED: " + str(error) + "\n")
    print(json.dumps({"evaluation_freeze": str(path), "cases_sha256": value["cases_sha256"],
                      "source_files": len(value["source_sha256"]),
                      "preregistered_artifacts": len(value["artifact_sha256"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
