"""Retain completed sessions and run untouched slots after a startup-only rejection."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from time import monotonic, sleep

from complete_system_device_guard import stage2_limits, require_ready, capture_safety_snapshot
from run_complete_system import ARM_ORDERS, load_workload, source_hashes


def completed_session(path, frozen, cases):
    """A retained session must already contain every original item exactly once."""
    if not (path / "finish.json").exists():
        return False
    finish = json.loads((path / "finish.json").read_text())
    if finish["status"] not in {"complete", "complete_with_errors"}:
        return False
    manifest = json.loads((path / "manifest.json").read_text())
    rows = [json.loads(line) for line in (path / "observations.jsonl").read_text().splitlines()]
    if manifest["frozen"] != frozen or len(rows) != len(cases):
        raise ValueError("retained session has different source or missing attempts")
    for index, (row, case) in enumerate(zip(rows, cases), 1):
        if any(row[key] != case[key] for key in ("id", "prompt", "scenario_id", "stratum")):
            raise ValueError("retained session differs from frozen workload order")
        if row["index"] != index or row["status"] not in {"ok", "error"}:
            raise ValueError("retained session contains an incomplete slot")
    if finish["resident_models"] or finish["cleanup_errors"] or finish["guard_violation"]:
        raise ValueError("retained session has an unresolved cleanup or guard failure")
    return True


def await_ready(arm, repetition):
    deadline = monotonic() + 900
    while True:
        snapshot = capture_safety_snapshot()
        try:
            with stage2_limits():
                require_ready(snapshot)
            if max(snapshot["temperatures_c"].values()) >= 54:
                raise RuntimeError("waiting for below-54 C scheduler handoff margin; arm gate remains 55 C")
            return snapshot
        except Exception as error:
            if snapshot.get("resident_models") or monotonic() >= deadline:
                raise
            print(f"PREFLIGHT WAIT {arm} r{repetition}: {error}", flush=True)
            sleep(20)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", required=True, type=Path)
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--prior-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    frozen = json.loads(args.freeze.read_text())
    workload = load_workload(args.workload)
    if source_hashes() != frozen["source_sha256"]:
        raise ValueError("frozen runner source changed")
    if sha256(args.workload.read_bytes()).hexdigest() != frozen["workload_sha256"]:
        raise ValueError("frozen workload changed")
    slots = [(arm, repetition) for repetition, arms in enumerate(ARM_ORDERS, 1) for arm in arms]
    retained = []
    for index, (arm, repetition) in enumerate(slots, 1):
        path = args.prior_root / f"{index:02d}_{arm}_r{repetition}"
        if path.exists() and completed_session(path, frozen, workload["execution_cases"]):
            if index != len(retained) + 1:
                raise ValueError("only a contiguous complete-session prefix can be retained")
            retained.append(path)
        elif (path / "observations.jsonl").exists() and (path / "observations.jsonl").stat().st_size:
            raise ValueError("refusing to replace an already attempted partial session")
    if not retained or len(retained) == 9:
        raise ValueError("resume expects a nonempty completed prefix and unattempted remaining sessions")
    os.umask(0o077)
    args.output_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    for path in retained:
        (args.output_root / path.name).symlink_to(path.resolve(), target_is_directory=True)
    shutil.copyfile(args.prior_root / "before.json", args.output_root / "before.json")
    origin = {
        "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "prior_root": str(args.prior_root.resolve()), "freeze_path": str(args.freeze.resolve()),
        "freeze_sha256": sha256(args.freeze.read_bytes()).hexdigest(),
        "resume_script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "reason": "startup temperature handoff jitter before any large-only request; no quality-based retry",
        "scheduler_handoff_temperature_c_exclusive": 54,
        "unchanged_arm_start_temperature_c_exclusive": 55,
        "retained_complete_sessions": [{"directory": path.name, "source": str(path.resolve()),
             "observations_sha256": sha256((path / "observations.jsonl").read_bytes()).hexdigest(),
             "finish_sha256": sha256((path / "finish.json").read_bytes()).hexdigest()}
             for path in retained],
        "prior_batch_finish_sha256": sha256((args.prior_root / "batch_finish.json").read_bytes()).hexdigest(),
        "prior_startup_rejection": str((args.prior_root / "02_large_r1").resolve()),
    }
    (args.output_root / "resume_origin.json").write_text(json.dumps(origin, indent=2) + "\n")
    sessions = [{"arm": slots[i][0], "repetition": slots[i][1], "path": str(path),
                 "retained_complete": True, "exit_code": 0} for i, path in enumerate(retained)]
    status = "incomplete"
    try:
        for index, (arm, repetition) in enumerate(slots[len(retained):], len(retained) + 1):
            for startup_try in range(1, 6):
                await_ready(arm, repetition)
                directory = args.output_root / f"{index:02d}_{arm}_r{repetition}"
                print(f"SESSION {index}/9 {arm} r{repetition}", flush=True)
                started = datetime.now(timezone.utc).isoformat()
                result = subprocess.run([
                    sys.executable, str(Path(__file__).with_name("run_complete_system.py")),
                    "--workload", str(args.workload.resolve()), "--freeze", str(args.freeze.resolve()),
                    "--output-dir", str(directory.resolve()), "--arm", arm, "--repetition", str(repetition),
                ], check=False)
                if result.returncode:
                    finish = json.loads((directory / "finish.json").read_text())
                    summary = json.loads((directory / "summary.json").read_text())
                    startup_only = (summary["attempted"] == 0 and not (directory / "manifest.json").exists()
                                    and (finish.get("failure") or {}).get("message") ==
                                    "Stage 2 startup temperature must be below 55 C")
                    if startup_only:
                        rejected = args.output_root / "startup_rejections"
                        rejected.mkdir(mode=0o700, exist_ok=True)
                        directory.rename(rejected / f"{directory.name}_try{startup_try}")
                        print("Startup-only temperature rejection archived; no request retried.", flush=True)
                        continue
                    raise RuntimeError(f"session {index} stopped; retaining every observed request")
                sessions.append({"arm": arm, "repetition": repetition, "path": str(directory),
                                 "started_at": started, "exit_code": result.returncode})
                break
            else:
                raise RuntimeError("startup temperature remained unstable across five unattempted launches")
        status = "complete"
    finally:
        finish = capture_safety_snapshot()
        (args.output_root / "batch_finish.json").write_text(json.dumps({
            "status": status, "sessions": sessions, "snapshot": finish,
        }, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
