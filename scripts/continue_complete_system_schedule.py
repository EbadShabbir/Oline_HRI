"""Continue untouched planned sessions, retaining terminal resource failures."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

from complete_system_device_guard import capture_safety_snapshot
from resume_complete_system_batch import await_ready, completed_session
from run_complete_system import ARM_ORDERS, load_workload, source_hashes


RECOVERABLE = {"available memory crossed the runtime floor", "telemetry RAM floor crossed"}


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write_new(path, data):
    with path.open("x") as stream:
        stream.write(json.dumps(data, indent=2) + "\n")


def terminal_session(path, frozen, cases, baseline, arm, repetition):
    finish = read(path / "finish.json")
    manifest = read(path / "manifest.json")
    rows = [json.loads(line) for line in (path / "observations.jsonl").read_text().splitlines()]
    if manifest["frozen"] != frozen or manifest["arm"] != arm or manifest["repetition"] != repetition:
        raise ValueError("session identity or freeze differs")
    if not rows or len(rows) > len(cases):
        raise ValueError("terminal session has invalid attempt count")
    for index, (row, case) in enumerate(zip(rows, cases), 1):
        if any(row[key] != case[key] for key in ("id", "prompt", "scenario_id", "stratum")):
            raise ValueError("session differs from frozen workload prefix")
        if row["index"] != index or row["arm"] != arm or row["repetition"] != repetition:
            raise ValueError("observation identity differs")
    for key in ("boot_id", "power_mode", "thermal_trip_events"):
        if finish.get(key) != baseline[key]:
            raise ValueError(f"device continuity changed: {key}")
    if (finish.get("cleanup_errors") != [] or finish.get("resident_models") != []
            or "telemetry_reader_error" not in finish or finish["telemetry_reader_error"] is not None):
        raise ValueError("session cleanup or telemetry unresolved")
    if not completed_session(path, frozen, cases):
        failure = finish.get("failure") or {}
        if (finish["status"] != "interrupted" or failure.get("type") != "SafetyGateError"
                or failure.get("message") not in RECOVERABLE
                or finish.get("guard_violation") not in RECOVERABLE):
            raise ValueError("session failure is outside the narrow RAM-guard continuation policy")
        if rows[-1]["status"] != "interrupted" or any(row["status"] not in {"ok", "error"} for row in rows[:-1]):
            raise ValueError("interrupted session has an unexpected observation shape")
    return {"directory": path.name, "arm": arm, "repetition": repetition,
            "status": finish["status"], "attempted": len(rows), "planned": len(cases),
            "unattempted": len(cases) - len(rows), "guard_violation": finish.get("guard_violation"),
            "artifact_sha256": {p.name: digest(p) for p in sorted(path.iterdir()) if p.is_file()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("workload", "freeze", "run-root"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    frozen, workload = read(args.freeze), load_workload(args.workload)
    if source_hashes() != frozen["source_sha256"] or digest(args.workload) != frozen["workload_sha256"]:
        raise ValueError("frozen execution source or workload changed")
    baseline = read(args.run_root / "before.json")
    slots = [(arm, rep) for rep, arms in enumerate(ARM_ORDERS, 1) for arm in arms]
    sessions = []
    for index, (arm, rep) in enumerate(slots, 1):
        path = args.run_root / f"{index:02d}_{arm}_r{rep}"
        if path.exists():
            if index != len(sessions) + 1:
                raise ValueError("existing sessions must form a terminal prefix")
            sessions.append(terminal_session(path, frozen, workload["execution_cases"], baseline, arm, rep))
    if not sessions or len(sessions) == 9:
        raise ValueError("expected retained terminal prefix and untouched slots")
    os.umask(0o077)
    launcher = args.run_root / "continued_schedule_launcher.py"
    with launcher.open("xb") as stream:
        stream.write(Path(__file__).read_bytes())
    write_new(args.run_root / "schedule_continuation_origin.json", {
        "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "reason": "Continue independent preplanned repetitions after a cleanly unloaded RAM-guard interruption; no partial session is retried or filled.",
        "freeze_sha256": digest(args.freeze), "launcher_sha256": digest(launcher),
        "dependency_sha256": {name: digest(Path(__file__).with_name(name)) for name in ("resume_complete_system_batch.py",)},
        "prior_batch_finish_sha256": digest(args.run_root / "batch_finish.json"),
        "retained_terminal_sessions": sessions,
        "remaining_slots": [{"index": i, "arm": arm, "repetition": rep} for i, (arm, rep) in enumerate(slots, 1) if i > len(sessions)],
        "recoverable_failure_messages": sorted(RECOVERABLE),
        "scheduler_handoff_temperature_c_exclusive": 54,
        "unchanged_arm_start_temperature_c_exclusive": 55,
    })
    status, failure = "incomplete", None
    try:
        for index, (arm, rep) in enumerate(slots[len(sessions):], len(sessions) + 1):
            for startup_try in range(1, 6):
                ready = await_ready(arm, rep)
                if any(ready[key] != baseline[key] for key in ("boot_id", "power_mode", "thermal_trip_events")):
                    raise RuntimeError("device continuity changed before next independent session")
                path = args.run_root / f"{index:02d}_{arm}_r{rep}"
                print(f"SESSION {index}/9 {arm} r{rep}", flush=True)
                result = subprocess.run([sys.executable, str(Path(__file__).with_name("run_complete_system.py")),
                    "--workload", str(args.workload.resolve()), "--freeze", str(args.freeze.resolve()),
                    "--output-dir", str(path.resolve()), "--arm", arm, "--repetition", str(rep)], check=False)
                finish, summary = read(path / "finish.json"), read(path / "summary.json")
                if (result.returncode and summary["attempted"] == 0 and not (path / "manifest.json").exists()
                        and (finish.get("failure") or {}).get("message") == "Stage 2 startup temperature must be below 55 C"
                        and not finish.get("cleanup_errors") and not finish.get("resident_models")):
                    rejected = args.run_root / "startup_rejections"
                    rejected.mkdir(mode=0o700, exist_ok=True)
                    path.rename(rejected / f"{path.name}_continuation_try{startup_try}")
                    print("Archived zero-inference startup temperature rejection.", flush=True)
                    continue
                item = terminal_session(path, frozen, workload["execution_cases"], baseline, arm, rep)
                item["exit_code"] = result.returncode
                sessions.append(item)
                with (args.run_root / "continued_schedule_progress.jsonl").open("a") as stream:
                    stream.write(json.dumps(item) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                if result.returncode:
                    print("Retained RAM-guard interruption; moving to the next independent planned session.", flush=True)
                break
            else:
                raise RuntimeError("five zero-inference temperature rejections; schedule stopped")
        status = "complete_schedule_with_session_failures" if any(s["unattempted"] or s["guard_violation"] for s in sessions) else "complete"
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        write_new(args.run_root / "continued_schedule_finish.json", {
            "status": status, "failure": failure, "sessions": sessions,
            "snapshot": capture_safety_snapshot(), "finished_at": datetime.now(timezone.utc).isoformat(),
        })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
