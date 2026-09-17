"""Temporarily pause an idle updater using ordinary administrator authorization.

This revision avoids a second authorization prompt when a failed stop leaves the
service active. Restoration is attempted even if evaluation cleanup fails. No
service disabling, masking, timer changes, credentials or guard changes occur.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
SERVICE = "fwupd.service"


def service_state():
    """Query systemd without activating the updater's D-Bus service."""
    result = subprocess.run(
        ["systemctl", "show", SERVICE, "--property=ActiveState", "--value"],
        check=True, text=True, capture_output=True, timeout=15,
    )
    value = result.stdout.strip()
    if value not in {"active", "inactive", "failed", "activating", "deactivating", "reloading"}:
        raise RuntimeError("Unrecognized firmware updater service state")
    return value


def admin_service_action(action):
    return subprocess.run(
        ["pkexec", "--disable-internal-agent", "/usr/bin/systemctl", action, SERVICE],
        check=True, timeout=90,
    )


def restore_if_needed(emit):
    try:
        state = service_state()
    except BaseException as error:
        # Initial state was active and a stop was attempted. If status cannot be
        # read, preserve that initial state with the ordinary start operation.
        emit("restoration_state_check_error", type=type(error).__name__, message=str(error))
        state = "unknown"
    if state == "active":
        emit("restoration_not_needed", active=state, administrator_action=False,
             persistent_settings_changed=False)
        return
    emit("restoration_attempt", active=state, administrator_action=True)
    try:
        result = admin_service_action("start")
        state = service_state()
        emit("restored", exit_code=result.returncode, active=state,
             persistent_settings_changed=False)
        if state != "active":
            raise RuntimeError("Updater restoration did not reach active state")
    except BaseException as error:
        emit("restoration_error", type=type(error).__name__, message=str(error))
        raise


def run_paused(cohort, max_cases, emit):
    child = None
    initial_active = False
    stop_attempted = False
    try:
        active = service_state()
        initial_active = active == "active"
        if not initial_active:
            emit("before", active=active)
            raise RuntimeError("Firmware updater must initially be active")
        # Query D-Bus only before the stop; querying a stopped service could
        # itself activate it and defeat the intended bounded pause.
        def read_property(name):
            return subprocess.check_output(
                ["busctl", "get-property", "org.freedesktop.fwupd", "/",
                 "org.freedesktop.fwupd", name], text=True, timeout=15,
            ).strip()

        status, progress = read_property("Status"), read_property("Percentage")
        emit("before", active=active, status=status, percentage=progress)
        if (status, progress) != ("u 1", "u 0"):
            raise RuntimeError("Firmware updater is not confirmed idle")
        stop_attempted = True
        admin_service_action("stop")
        stopped = service_state()
        if stopped != "inactive":
            raise RuntimeError("Updater did not stop")
        emit("paused", active=stopped, persistent_settings_changed=False)
        command = [
            sys.executable, str(BASE / "run_guarded.py"), "--cases", str(cohort / "cases.json"),
            "--candidate-manifest", str(cohort / "candidate_freeze.json"),
            "--max-cases", str(max_cases), "--output-dir", str(cohort / "collection"),
        ]
        child = subprocess.Popen(command, cwd=ROOT)
        code = child.wait()
        emit("evaluation_finished", exit_code=code)
        return code
    except BaseException as error:
        emit("error", type=type(error).__name__, message=str(error))
        raise
    finally:
        # Do not let an interrupted/failed child cleanup skip service recovery.
        try:
            try:
                if child is not None and child.poll() is None:
                    emit("child_cleanup_attempt")
                    child.send_signal(signal.SIGINT)
                    child.wait(timeout=90)
                    emit("child_cleanup_finished", exit_code=child.returncode)
            except BaseException as error:
                emit("child_cleanup_error", type=type(error).__name__, message=str(error))
                raise
        finally:
            if initial_active and stop_attempted:
                restore_if_needed(emit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-dir", type=Path, required=True)
    parser.add_argument("--max-cases", type=int, required=True)
    args = parser.parse_args()
    cohort = args.cohort_dir.resolve()
    if BASE not in cohort.parents or not (cohort / "candidate_freeze.json").is_file():
        raise ValueError("A prepared local cohort is required")
    if args.max_cases < 1:
        raise ValueError("max-cases must be positive")
    record = cohort / "updater_pause_v2.jsonl"

    def interrupted(signum, frame):
        raise KeyboardInterrupt("Evaluation controller interrupted")

    previous_handlers = {}
    with record.open("x") as output:
        def emit(event, **data):
            output.write(json.dumps(dict(at=datetime.now(timezone.utc).isoformat(),
                                         event=event, **data)) + "\n")
            output.flush()
        try:
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                previous_handlers[sig] = signal.signal(sig, interrupted)
            return run_paused(cohort, args.max_cases, emit)
        finally:
            for sig, previous in previous_handlers.items():
                signal.signal(sig, previous)


if __name__ == "__main__":
    raise SystemExit(main())
