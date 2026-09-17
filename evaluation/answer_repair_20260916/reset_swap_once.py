"""User-authorized, one-shot cycling of existing zram swap, with restoration.

Run only via the normal administrator authorization mechanism. Does not change
swap size, priority, persistence, power/fan configuration, or evaluation limits.
JSONL stdout is the durable action record; no credentials are read by this code.
"""
from contextlib import ExitStack
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def emit(event, **data):
    print(json.dumps({"at": datetime.now(timezone.utc).isoformat(),
                      "event": event, **data}), flush=True)


def swaps():
    result = []
    for line in Path('/proc/swaps').read_text().splitlines()[1:]:
        name, kind, size, used, priority = line.split()
        result.append(dict(name=name, kind=kind, size_kib=int(size),
                           used_kib=int(used), priority=int(priority)))
    return result


def memory():
    values = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        name, value = line.split(':', 1)
        if name in ('MemAvailable', 'SwapTotal', 'SwapFree'):
            values[name] = int(value.split()[0])
    return values


def restore(original):
    failures = []
    active = {row['name'] for row in swaps()}
    for row in original:
        if row['name'] not in active:
            result = subprocess.run(['/usr/sbin/swapon', '--priority',
                                     str(row['priority']), row['name']],
                                    capture_output=True, text=True)
            emit('restore', device=row['name'], returncode=result.returncode,
                 stderr=result.stderr)
            if result.returncode:
                failures.append(row['name'])
    return failures


def cycle(original):
    try:
        for row in original:
            current = {item['name']: item for item in swaps()}
            if set(current) != {item['name'] for item in original}:
                raise RuntimeError('Swap inventory changed during cleanup')
            if memory()['MemAvailable'] < current[row['name']]['used_kib'] + 1024 * 1024:
                raise RuntimeError('Insufficient measured RAM headroom to drain this device')
            emit('before_swapoff', device=row['name'], memory=memory())
            try:
                subprocess.run(['/usr/sbin/swapoff', row['name']], check=True)
                emit('disabled', device=row['name'], memory=memory())
            finally:
                failures = restore(original)
                if failures:
                    raise RuntimeError('Failed to restore swap: ' + repr(failures))
            emit('cycled', device=row['name'], memory=memory(), swaps=swaps())
    finally:
        # Recheck restoration even if a command or signal interrupted the loop.
        failures = restore(original)
        if failures:
            raise RuntimeError('Final swap restoration failed: ' + repr(failures))


def main():
    if os.geteuid() != 0:
        raise PermissionError('Administrator authorization is required')
    def interrupted(signum, frame):
        raise InterruptedError('Cleanup interrupted by signal ' + str(signum))
    for name in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(name, interrupted)
    with ExitStack() as stack:
        for name in ('/tmp/clara-jetson-inference.lock',
                     ROOT / 'evaluation/independent_retrieval_inference.lock',
                     ROOT / 'evaluation/matched_evidence_inference.lock'):
            stream = stack.enter_context(open(name, 'r+'))
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with urllib.request.urlopen('http://127.0.0.1:11434/api/ps', timeout=10) as response:
            resident = json.load(response).get('models')
        if resident != []:
            raise RuntimeError('Model residency is not confirmed empty')
        original = swaps()
        if not original or not all(re.fullmatch(r'/dev/zram[0-9]+', row['name'])
                                   and row['kind'] == 'partition' for row in original):
            raise RuntimeError('Only the existing zram swap devices are authorized')
        if memory()['MemAvailable'] < sum(row['used_kib'] for row in original) + 1024 * 1024:
            raise RuntimeError('Insufficient RAM to drain swap with a 1 GiB reserve')
        emit('start', swaps=original, memory=memory(), resident_models=resident)
        cycle(original)
        final = swaps()
        identity = lambda rows: sorted((r['name'], r['kind'], r['size_kib'], r['priority'])
                                       for r in rows)
        if identity(final) != identity(original):
            raise RuntimeError('Final swap inventory/size/priority differs')
        emit('complete', swaps=final, memory=memory(), persistent_settings_changed=False)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        emit('error', type=type(error).__name__, message=str(error),
             swaps=swaps(), memory=memory())
        raise
