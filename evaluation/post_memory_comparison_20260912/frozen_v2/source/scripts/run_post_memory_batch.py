"""Run nine frozen post-memory sessions serially, preserving any interruption."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import monotonic, sleep

from oline_hri.evaluation_model_pairs import (
    SafetyGateError, _new_private_directory, _write_new_json,
)
from post_memory_device_guard import stage2_limits, require_ready, capture_safety_snapshot
from run_post_memory_comparison import ARM_ORDERS, source_hashes


def session_slots():
    return [(f"{index:02d}_{arm}_r{repetition}", arm, repetition)
            for index, (repetition, arm) in enumerate(
                ((rep, arm) for rep, arms in enumerate(ARM_ORDERS, 1) for arm in arms), 1)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", required=True, type=Path)
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args(argv)
    frozen = json.loads(args.freeze.read_text())
    if frozen.get("profile_id") != "post_memory_comparison_v1":
        raise ValueError("incorrect comparison profile")
    if frozen.get("counterbalanced_arm_orders") != [list(arms) for arms in ARM_ORDERS]:
        raise ValueError("session order differs from freeze")
    if source_hashes() != frozen["source_sha256"]:
        raise ValueError("source differs from freeze")
    if sha256(args.workload.read_bytes()).hexdigest() != frozen["workload_sha256"]:
        raise ValueError("workload differs from freeze")
    directory = _new_private_directory(args.output_root.absolute())
    slots = session_slots()
    _write_new_json(directory / "batch_plan.json", {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "profile_id": frozen["profile_id"],
        "freeze_sha256": sha256(args.freeze.read_bytes()).hexdigest(),
        "planned_attempts": frozen["planned_attempts"],
        "sessions": [{"directory": name, "arm": arm, "repetition": rep} for name, arm, rep in slots],
        "startup_wait_seconds_per_session": 600,
        "failure_policy": "stop the batch on a blocked startup or failed session; no tail stitching",
    })
    sessions, waits = [], []
    status, failure = "incomplete", None
    baseline = None
    try:
        baseline = capture_safety_snapshot()
        _write_new_json(directory / "before.json", baseline)
        for name, arm, repetition in slots:
            deadline = monotonic() + 600
            while True:
                state = capture_safety_snapshot()
                # A restart or thermal trip cannot be resolved by waiting.
                if state.get("boot_id") != baseline.get("boot_id") or state.get("thermal_trip_events") != baseline.get("thermal_trip_events"):
                    raise SafetyGateError("device boot or thermal trip counters changed between sessions")
                try:
                    with stage2_limits():
                        require_ready(state)
                    break
                except SafetyGateError as error:
                    waits.append({"at": datetime.now(timezone.utc).isoformat(),
                                  "session": name, "reason": str(error), "snapshot": state})
                    if state.get("resident_models") or monotonic() >= deadline:
                        raise
                    print(f"PREFLIGHT WAIT {name}: {error}", flush=True)
                    sleep(20)
            if source_hashes() != frozen["source_sha256"]:
                raise ValueError("source changed between sessions")
            target = directory / name
            session = {"directory": name, "arm": arm, "repetition": repetition,
                       "started_at": datetime.now(timezone.utc).isoformat(), "exit_code": None}
            sessions.append(session)
            print(f"SESSION {len(sessions)}/{len(slots)} {arm} r{repetition}", flush=True)
            result = subprocess.run([
                sys.executable, str(Path(__file__).with_name("run_post_memory_comparison.py")),
                "--workload", str(args.workload.resolve()), "--freeze", str(args.freeze.resolve()),
                "--output-dir", str(target.resolve()), "--arm", arm,
                "--repetition", str(repetition),
            ], check=False)
            session["exit_code"] = result.returncode
            if result.returncode:
                raise RuntimeError(f"{name} stopped with exit code {result.returncode}")
        status = "complete"
    except BaseException as error:
        status = "interrupted"
        failure = {"type": type(error).__name__, "message": str(error)}
    finally:
        try:
            finish = capture_safety_snapshot()
        except BaseException as error:
            finish = {"snapshot_error": type(error).__name__, "message": str(error)}
            status = "finish_snapshot_failed"
        _write_new_json(directory / "startup_waits.json", waits)
        _write_new_json(directory / "batch_finish.json", {
            "status": status, "failure": failure, "sessions": sessions,
            "sessions_not_launched": [name for name, _, _ in slots if name not in {s["directory"] for s in sessions}],
            "snapshot": finish,
        })
    print(f"BATCH {directory} status={status}", flush=True)
    return 0 if status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
