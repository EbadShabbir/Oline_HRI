"""Execute the nine frozen Stage 2 sessions in separate, sequential processes."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic, sleep

from complete_system_device_guard import stage2_limits, require_ready, capture_safety_snapshot
from run_complete_system import ARM_ORDERS, source_hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", required=True, type=Path)
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    args.output_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    freeze = json.loads(args.freeze.read_text())
    if source_hashes() != freeze["source_sha256"]:
        raise ValueError("source differs from freeze")
    baseline = capture_safety_snapshot()
    (args.output_root / "before.json").write_text(json.dumps(baseline, indent=2) + "\n")
    sessions = []
    status = "incomplete"
    try:
        for repetition, arms in enumerate(ARM_ORDERS, 1):
            for arm in arms:
                deadline = monotonic() + 600
                while True:
                    state = capture_safety_snapshot()
                    try:
                        with stage2_limits():
                            require_ready(state)
                        break
                    except Exception as error:
                        # Waiting can cool a device or let the prior process
                        # release memory. It never changes settings or closes apps.
                        if state.get("resident_models") or monotonic() >= deadline:
                            raise
                        print(f"PREFLIGHT WAIT {arm} r{repetition}: {error}", flush=True)
                        sleep(20)
                number = len(sessions) + 1
                directory = args.output_root / f"{number:02d}_{arm}_r{repetition}"
                print(f"SESSION {number}/9 {arm} r{repetition}", flush=True)
                started = datetime.now(timezone.utc).isoformat()
                result = subprocess.run([
                    sys.executable, str(Path(__file__).with_name("run_complete_system.py")),
                    "--workload", str(args.workload.resolve()),
                    "--freeze", str(args.freeze.resolve()),
                    "--output-dir", str(directory.resolve()),
                    "--arm", arm, "--repetition", str(repetition),
                ], check=False)
                sessions.append({"arm": arm, "repetition": repetition, "path": str(directory),
                                 "started_at": started, "exit_code": result.returncode})
                if result.returncode:
                    raise RuntimeError(f"session {number} stopped with exit code {result.returncode}")
        status = "complete"
    finally:
        finish = capture_safety_snapshot()
        (args.output_root / "batch_finish.json").write_text(json.dumps({
            "status": status, "sessions": sessions, "snapshot": finish,
        }, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
