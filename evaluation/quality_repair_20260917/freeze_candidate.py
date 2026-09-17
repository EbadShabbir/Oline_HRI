"""Archive a reviewable candidate before any cohort is dispatched."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--cases", type=Path)
    args = parser.parse_args()
    target = args.output_dir.resolve()
    target.mkdir(parents=True, exist_ok=False)
    paths = [*sorted((ROOT / "src/oline_hri").glob("*.py")),
             *sorted((ROOT / "src/oline_hri").glob("*.json")),
             ROOT / "scripts/run_routing_reliability.py",
             ROOT / "scripts/run_pair_remediation_validation.py",
             ROOT / "scripts/complete_system_device_guard.py", BASE / "run_guarded.py"]
    hashes = {}
    for path in paths:
        relative = path.relative_to(ROOT)
        archived = target / "candidate_source" / relative
        archived.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, archived)
        hashes[str(relative)] = digest(path)
        assert digest(archived) == hashes[str(relative)]
    tests = {}
    for path in sorted((ROOT / "tests").glob("*.py")):
        archived = target / "tests" / path.name
        archived.parent.mkdir(exist_ok=True)
        shutil.copyfile(path, archived)
        tests[path.name] = digest(path)
    (target / "working_changes.diff").write_bytes(subprocess.check_output(
        ["git", "diff", "--", "src", "scripts", "tests"], cwd=ROOT))
    value = {"created_at": datetime.now(timezone.utc).isoformat(),
             "source_sha256": hashes, "tests_sha256": tests,
             "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
             "scope": "Exact working/archived runtime and test candidate; no inference by this command.",
             "working_diff_sha256": digest(target / "working_changes.diff")}
    if args.cases:
        shutil.copyfile(args.cases, target / "cases.json")
        value["cases_sha256"] = digest(target / "cases.json")
    (target / "candidate_freeze.json").write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps({"candidate": str(target), "source_files": len(hashes),
                      "test_files": len(tests), "cases_opened": bool(args.cases)}, indent=2))


if __name__ == "__main__":
    main()
