"""Read-only final status, archive-preservation and manifest consistency audit.

Never traverses or reads the new holdout_authoring directory. Historical seals
use existing immutable document snapshots when repository index bytes changed.
No production imports, inference, network, process or administrator operations.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
checks = []


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    if HERE / "holdout_authoring" in path.resolve().parents:
        raise ValueError("new holdout authoring content must remain unopened")
    return sha256(path.read_bytes()).hexdigest()


def check(label, condition, detail=None):
    checks.append({"check": label, "passed": bool(condition), "detail": detail})


status = read(HERE / "completion_status.json")
manifest = read(HERE / "artifact_manifest.json")
for field in ("latest_candidate_clean_device_run", "fresh_holdout_completed", "github_pushed", "requested_work_complete"):
    check(field + " remains explicitly false", status[field] is False)
v1 = read(HERE / "development_v1/metrics.json")
v2 = read(HERE / "development_v2/metrics.json")
check("best measured known cohort is complete v1 with 12/16 quality and 16/16 routes",
      status["best_measured_known_case_result"]["cohort"] == "development_v1"
      and v1["summary"]["planned"] == 16 and v1["summary"]["quality_pass"]["count"] == 12
      and v1["summary"]["final_match"]["count"] == 16 and v1["operational_success"] is True)
check("v2 preserves 12 observed, one error, four missing and 9/16 quality",
      v2["summary"]["planned"] == 16 and v2["summary"]["observed"] == 12
      and v2["summary"]["errors"] == 1 and v2["summary"]["missing"] == 4
      and v2["summary"]["quality_pass"]["count"] == 9
      and v2["operational_success"] is False and v2["evaluation_complete"] is False)
check("latest candidate has no collection or live score", not (HERE / "development_v3/collection").exists()
      and status["latest_candidate"]["live_quality_score"] is None
      and status["latest_candidate"]["recorded_cases"] == 0)
check("no final holdout freeze, opening record or dispatched cohort exists",
      not any((HERE / name).exists() for name in ("final_candidate", "holdout_opening.json", "fresh_holdout")))
suite = read(HERE / "full_offline_checks_v4.status.json")
log = (HERE / "full_offline_checks_v4.log").read_text()
counts = re.findall(r"Ran (\d+) tests in ([\d.]+)s", log)
skips = re.findall(r"OK \(skipped=(\d+)\)", log)
check("offline totals distinguish 1515 run, 26 skipped and 1489 passed", counts[-1][0] == "1515"
      and skips[-1] == "26" and suite["exit_code"] == 0
      and status["latest_offline_tests"]["tests_run"] == 1515
      and status["latest_offline_tests"]["skipped"] == 26
      and status["latest_offline_tests"]["passed"] == 1489
      and status["latest_offline_tests"]["failures"] == status["latest_offline_tests"]["errors"] == 0)
drift = [name for name, expected in suite["sha256"].items() if digest(ROOT / name) != expected]
check("latest tested production/test bytes remain unchanged", suite["source_and_tests_unchanged"] is True
      and suite["live_opt_ins_disabled"] is True and not drift, drift)
updater = read(HERE / "updater_pause_v1_final_status.json")
attempt = [json.loads(line) for line in (HERE / "development_v3/updater_pause.jsonl").read_text().splitlines()]
check("updater authorization timed out before evaluation", len(attempt) == 2
      and attempt[0]["event"] == "before" and attempt[1]["type"] == "TimeoutExpired")
check("final saved updater state is active/running with no pkexec process",
      updater["fwupd"]["ActiveState"] == "active" and updater["fwupd"]["SubState"] == "running"
      and updater["remaining_pkexec_processes"] == [] and updater["read_only"] is True)
check("captured final RAM remains below unchanged admission floor", updater["memory_kib"]["MemAvailable"] < 2097152
      and status["device_status"]["captured_available_memory_kib"] == updater["memory_kib"]["MemAvailable"])
publication = read(HERE / "publication/publication_validation.json")
check("original GitHub push was rejected before execution", publication["push"]["executed"] is False
      and publication["push"]["succeeded"] is False
      and publication["push"]["ordinary_nonforce_push_attempts_rejected_before_execution"] == 2)
helper_log = (HERE / "updater_pause_v2_offline_checks.log").read_text()
check("later updater helper has 12 offline checks and no claimed live result",
      "Ran 12 tests" in helper_log and re.search(r"\nOK\s*$", helper_log)
      and status["updater_helper_v2"]["offline_tests_passed"] == 12
      and status["updater_helper_v2"]["live_validated"] is False)

snapshots = []
for name in ("evaluation/answer_repair_20260916/pre_completion_snapshot/manifest.json",
             "evaluation/answer_repair_20260916/pre_recovery_completion_snapshot/manifest.json",
             "evaluation/quality_repair_20260917/baseline_snapshot/manifest.json"):
    snapshot = read(ROOT / name)
    for original, record in snapshot["documents"].items():
        snapshots.append((original, record["sha256"], ROOT / record["snapshot_path"]))
snapshots.append(("results.md", "34b6438ceedd36b1f0ef91e1d68494e05a9ae787522e986855cc6801a123a55e",
                  ROOT / "evaluation/answer_repair_20260916/baseline_results_snapshot.md"))
check("all explicit immutable document snapshots match recorded hashes",
      all(digest(path) == expected for _, expected, path in snapshots))
historical = []
for name in ("evaluation/fresh_routing_20260916/completion_manifest.json",
             "evaluation/answer_repair_20260916/progress_manifest.json",
             "evaluation/answer_repair_20260916/fresh_attempt_manifest.json",
             "evaluation/answer_repair_20260916/completion_manifest.json"):
    old = read(ROOT / name)
    mismatches, mapped = [], []
    for relative, expected in old["artifact_sha256"].items():
        path = ROOT / relative
        if path.is_file() and digest(path) == expected:
            continue
        match = next((snapshot for original, frozen, snapshot in snapshots
                      if original == relative and frozen == expected and digest(snapshot) == expected), None)
        if match:
            mapped.append({"original": relative, "snapshot": str(match.relative_to(ROOT))})
        else:
            mismatches.append(relative)
    check("historical seal preserved: " + name, len(old["artifact_sha256"]) == old["artifact_count"] and not mismatches, mismatches)
    historical.append({"manifest": name, "sha256": digest(ROOT / name), "artifact_count": old["artifact_count"], "mapped_documents": mapped})

for name in ("development_v1", "development_v2", "development_v3"):
    cohort = HERE / name
    candidate, seal = read(cohort / "candidate_freeze.json"), read(cohort / "evaluation_freeze.json")
    mismatch = [relative for relative, expected in seal["artifact_sha256"].items()
                if digest(cohort / relative) != expected]
    check(name + " preregistered artifacts unchanged", not mismatch, mismatch)
    mismatch = [relative for relative, expected in candidate["source_sha256"].items()
                if digest(cohort / "candidate_source" / relative) != expected]
    mismatch += ["tests/" + relative for relative, expected in candidate["tests_sha256"].items()
                 if digest(cohort / "tests" / relative) != expected]
    check(name + " exact runtime and test archive preserved", not mismatch, mismatch)
    if (cohort / "collection/artifact_sha256.json").exists():
        raw = read(cohort / "collection/artifact_sha256.json")
        mismatch = [relative for relative, expected in raw.items() if digest(cohort / "collection" / relative) != expected]
        check(name + " all collected artifacts preserved", not mismatch, mismatch)

mismatch = [relative for relative, expected in manifest["artifact_sha256"].items()
            if digest(ROOT / relative) != expected]
check("current-cycle manifest hashes and declared artifact count agree",
      len(manifest["artifact_sha256"]) == manifest["artifact_count"] and not mismatch, mismatch)
actual = set()
for directory, subdirectories, files in os.walk(HERE):
    subdirectories[:] = [name for name in subdirectories if name not in {"holdout_authoring", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}]
    for name in files:
        path = Path(directory) / name
        if path == HERE / "artifact_manifest.json" or path == HERE / "final_status_verification.json" or path.suffix in {".pyc", ".pyo", ".lock"}:
            continue
        actual.add(str(path.relative_to(ROOT)))
check("manifest covers every eligible current-cycle artifact without opening holdout", actual == set(manifest["artifact_sha256"]),
      {"missing": sorted(actual - set(manifest["artifact_sha256"])), "extra": sorted(set(manifest["artifact_sha256"]) - actual)})
check("manifest excludes its own output, verification result and unopened holdout",
      not any("/holdout_authoring/" in name or name.endswith("/artifact_manifest.json") or name.endswith("/final_status_verification.json")
              for name in manifest["artifact_sha256"]))
check("final mutable repository documents match manifest snapshot",
      all(digest(ROOT / relative) == expected for relative, expected in manifest["external_document_sha256"].items()))
result = {"created_at": datetime.now(timezone.utc).isoformat(), "scope": __doc__,
          "checks": checks, "checks_passed": sum(row["passed"] for row in checks),
          "checks_failed": sum(not row["passed"] for row in checks), "passed": all(row["passed"] for row in checks),
          "current_cycle_manifest_sha256": digest(HERE / "artifact_manifest.json"),
          "completion_status_sha256": digest(HERE / "completion_status.json"),
          "auditor_sha256": digest(Path(__file__)), "historical_manifest_preservation": historical,
          "interpretation": "Passing status/integrity checks verify an honest incomplete state. They do not turn failed device attempts, unmeasured latest code, unopened holdout or unexecuted GitHub publication into completed work."}
with (HERE / "final_status_verification.json").open("x", encoding="utf-8") as stream:
    json.dump(result, stream, indent=2, ensure_ascii=False)
    stream.write("\n")
print(json.dumps({key: result[key] for key in ("passed", "checks_passed", "checks_failed")}, indent=2))
for row in checks:
    if not row["passed"]:
        print(json.dumps(row))
raise SystemExit(0 if result["passed"] else 1)
