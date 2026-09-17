"""Retain offline-suite output and before/after source/test hashes."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
target = Path(sys.argv[1])
target.parent.mkdir(parents=True, exist_ok=True)


def hashes():
    return {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest()
            for folder in (ROOT / 'src/oline_hri', ROOT / 'tests')
            for p in sorted(folder.glob('*.py'))}


before = hashes()
environment = os.environ.copy()
environment['PYTHONPATH'] = os.pathsep.join(str(ROOT / folder) for folder in ('src', 'scripts', 'tests'))
for key in list(environment):
    if key.startswith('OLINE_HRI_RUN_LIVE'):
        environment.pop(key)
start = perf_counter()
with target.with_suffix('.log').open('x') as output:
    result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests'],
                            cwd=ROOT, env=environment, stdout=output, stderr=subprocess.STDOUT)
status = {'exit_code': result.returncode, 'elapsed_seconds': perf_counter() - start,
          'live_opt_ins_disabled': True, 'source_and_tests_unchanged': before == hashes(),
          'sha256': before}
target.with_suffix('.status.json').write_text(json.dumps(status, indent=2) + '\n')
print(json.dumps({k: v for k, v in status.items() if k != 'sha256'}), flush=True)
raise SystemExit(result.returncode)
