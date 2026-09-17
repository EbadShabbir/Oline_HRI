"""Temporarily pause an idle updater around one guarded cohort, then restore it.

No disabling, masking, timer changes, credential access or guard changes. The
administrator operations use ordinary pkexec authorization. Active updater
status, any failed check, and incomplete restoration are explicit failures.
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cohort-dir', type=Path, required=True)
    parser.add_argument('--max-cases', type=int, required=True)
    args = parser.parse_args()
    cohort = args.cohort_dir.resolve()
    if BASE not in cohort.parents or not (cohort / 'candidate_freeze.json').is_file():
        raise ValueError('A prepared local cohort is required')
    record = cohort / 'updater_pause.jsonl'
    child = None
    paused = False
    code = 1
    with record.open('x') as output:
        def emit(event, **data):
            output.write(json.dumps(dict(at=datetime.now(timezone.utc).isoformat(), event=event, **data)) + '\n')
            output.flush()

        def read(command):
            return subprocess.check_output(command, text=True, timeout=15).strip()

        def interrupted(signum, frame):
            raise KeyboardInterrupt('Evaluation controller interrupted')

        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, interrupted)
        try:
            active = read(['systemctl', 'is-active', 'fwupd.service'])
            status = read(['busctl', 'get-property', 'org.freedesktop.fwupd', '/', 'org.freedesktop.fwupd', 'Status'])
            progress = read(['busctl', 'get-property', 'org.freedesktop.fwupd', '/', 'org.freedesktop.fwupd', 'Percentage'])
            emit('before', active=active, status=status, percentage=progress)
            if (active, status, progress) != ('active', 'u 1', 'u 0'):
                raise RuntimeError('Firmware updater is not confirmed active and idle')
            # Record intention before the privileged operation: restoration
            # still runs if interrupted just after systemctl completed.
            paused = True
            subprocess.run(['pkexec', '--disable-internal-agent', '/usr/bin/systemctl', 'stop', 'fwupd.service'], check=True, timeout=90)
            stopped = subprocess.run(['systemctl', 'is-active', 'fwupd.service'], text=True, capture_output=True, timeout=15)
            if stopped.stdout.strip() != 'inactive':
                raise RuntimeError('Updater did not stop')
            emit('paused', active=stopped.stdout.strip(), persistent_settings_changed=False)
            command = [sys.executable, str(BASE / 'run_guarded.py'), '--cases', str(cohort / 'cases.json'),
                       '--candidate-manifest', str(cohort / 'candidate_freeze.json'),
                       '--max-cases', str(args.max_cases), '--output-dir', str(cohort / 'collection')]
            child = subprocess.Popen(command, cwd=ROOT)
            code = child.wait()
            emit('evaluation_finished', exit_code=code)
        except BaseException as error:
            emit('error', type=type(error).__name__, message=str(error))
            raise
        finally:
            if child is not None and child.poll() is None:
                child.send_signal(signal.SIGINT)
                child.wait(timeout=90)
            if paused:
                restored = subprocess.run(['pkexec', '--disable-internal-agent', '/usr/bin/systemctl', 'start', 'fwupd.service'], timeout=90)
                active = read(['systemctl', 'is-active', 'fwupd.service'])
                emit('restored', exit_code=restored.returncode, active=active,
                     persistent_settings_changed=False)
                if restored.returncode or active != 'active':
                    raise RuntimeError('Updater restoration failed')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
