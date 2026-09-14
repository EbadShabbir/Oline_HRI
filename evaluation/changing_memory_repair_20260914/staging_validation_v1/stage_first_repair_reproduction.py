#!/usr/bin/env python3
"""Stage/verify the first repaired source without running any experiment.

The printed command performs live inference only if a user subsequently runs it.
The full evaluation directory and all real lease files are shared with the repo.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[1]
FREEZE = BASE / 'frozen_v2'
FREEZE_SEAL_SHA256 = '0b9b8e04dda46462ef1dd2682065d731439885723b2ff7ec723c18b79cf7660b'
REPRODUCER = BASE / 'reproduce_collection.sh'
REPRODUCER_SHA256 = '089651c105c8f1e19c26a163bf5e86107d9d5a4d3d09a630042b7885035961d6'
ROOT_DOCS = ('developments.MD', 'results.md')
EVALUATION_DOCS = ('evaluation/adaptive_selection_protocol_draft.md',
    'evaluation/memory_pipeline_20260912/README.md',
    'evaluation/independent_retrieval_20260913/README.md',
    'evaluation/independent_retrieval_20260913/report_reviewed_v3/report.md',
    'evaluation/routing_overhead_20260912/README.md')
LOCKS = ('independent_retrieval_inference.lock', 'matched_evidence_inference.lock',
         'independent_retrieval_batch.lock')


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(path.read_text())


def verify_frozen_inputs():
    if sha(FREEZE / 'seal.json') != FREEZE_SEAL_SHA256:
        raise ValueError('first repaired freeze seal changed')
    manifest = read(FREEZE / 'seal.json')['sha256']
    actual = {str(p.relative_to(FREEZE)) for p in FREEZE.rglob('*')
              if p.is_file() and p != FREEZE / 'seal.json'}
    if actual != set(manifest):
        raise ValueError('frozen input file set changed')
    for name, digest in manifest.items():
        if sha(FREEZE / name) != digest:
            raise ValueError('frozen input hash changed: ' + name)
    if sha(REPRODUCER) != REPRODUCER_SHA256:
        raise ValueError('existing reproduction script changed; review staging integration again')
    pairs = [(REPO / name, FREEZE / 'preparation' / name) for name in EVALUATION_DOCS]
    pairs += [(BASE / 'authored_v1' / name, FREEZE / name)
              for name in ('runtime.json', 'expected_ledger.json', 'protocol.md')]
    pairs += [(BASE / 'preflight_review_v1.json', FREEZE / 'preflight_review.json')]
    pairs += [(BASE / name, FREEZE / 'preparation' / name)
              for name in ('scenarios.json', 'author_ledger.py', 'authoring_v2_changes.md')]
    prior_validation = FREEZE / 'preparation/offline_validation'
    current_validation = BASE / 'offline_validation_v1'
    prior_files = {str(p.relative_to(prior_validation)) for p in prior_validation.rglob('*') if p.is_file()}
    current_files = {str(p.relative_to(current_validation)) for p in current_validation.rglob('*') if p.is_file()}
    if prior_files != current_files:
        raise ValueError('shared offline-validation input file set changed')
    pairs += [(current_validation / name, prior_validation / name) for name in sorted(prior_files)]
    shared = {str(REPRODUCER): sha(REPRODUCER)}
    for current, frozen in pairs:
        if not current.is_file() or sha(current) != sha(frozen):
            raise ValueError('shared preparation/authoring input drift: ' + str(current))
        shared[str(current)] = sha(current)
    return read(FREEZE / 'freeze.json'), shared


def checked_paths(stage, output):
    stage = stage.absolute()
    if stage != stage.resolve() or Path('/tmp') not in stage.parents:
        raise ValueError('stage must be a direct canonical path below /tmp, without symlink parents')
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('new collection output must not already exist')
    if output == stage or stage in output.parents:
        raise ValueError('collection output must be outside the source stage')
    return stage, output


def identity(path):
    # Read-only open/stat: no lock acquisition, lockfile creation, or write.
    with path.open('rb') as stream:
        value = os.fstat(stream.fileno())
    return {'resolved_path': str(path.resolve()), 'device': value.st_dev, 'inode': value.st_ino}


def shared_lock_identities(stage):
    if not (stage / 'evaluation').is_symlink() or (stage / 'evaluation').resolve() != REPO / 'evaluation':
        raise ValueError('stage must share the real repository evaluation directory; isolated leases forbidden')
    if not (stage / '.venv').is_symlink() or (stage / '.venv').resolve() != REPO / '.venv':
        raise ValueError('stage must use the existing repository virtual environment')
    result = []
    for name in LOCKS:
        real, staged = REPO / 'evaluation' / name, stage / 'evaluation' / name
        a, b = identity(real), identity(staged)
        if a != b:
            raise ValueError('lease identity mismatch: ' + name)
        result.append({'lease': name, 'real': a, 'staged': b})
    global_lock = Path('/tmp/clara-jetson-inference.lock')
    result.append({'lease': str(global_lock), 'real': identity(global_lock), 'staged': identity(global_lock)})
    return result


SMOKE = r'''
import hashlib, json, pathlib, sys
sys.dont_write_bytecode = True
def no_external_calls(event, args):
    if event in ('socket.connect', 'socket.connect_ex', 'socket.getaddrinfo', 'subprocess.Popen', 'os.system'):
        raise RuntimeError('offline smoke forbids network/process calls: ' + event)
sys.addaudithook(no_external_calls)
stage, freeze = map(pathlib.Path, sys.argv[1:])
import run_changing_memory as runner
import run_independent_retrieval as retrieval
from oline_hri import config, conversation, embedding
expected = json.loads((freeze/'freeze.json').read_text())
assert runner.ROOT == retrieval.ROOT == stage
assert runner.sources() == expected['source_sha256']
assert len(runner.sources()) == 41
assert config.load_config().to_dict() == expected['config']
assert runner.package_versions() == expected['packages']
assert sys.version == expected['python']
assert runner.policy_dict() == expected['device_policy']
assert embedding.REQUIRED_ASSET_SHA256 == expected['embedding_assets']
loaded = {}
for name, module in tuple(sys.modules.items()):
    if name.startswith('oline_hri') or name in {p.stem for p in (stage/'scripts').glob('*.py')}:
        filename = getattr(module, '__file__', None)
        if filename:
            path = pathlib.Path(filename).resolve()
            assert stage in path.parents, (name, str(path))
            loaded[name] = str(path)
assets = pathlib.Path(config.load_config().embedding.model_directory).expanduser()
asset_hashes = {}
for name, expected_hash in expected['embedding_assets'].items():
    digest = hashlib.sha256()
    with (assets/name).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): digest.update(block)
    assert digest.hexdigest() == expected_hash
    asset_hashes[name] = digest.hexdigest()
print(json.dumps({'source_count': 41, 'source_sha256': runner.sources(), 'loaded_local_modules': loaded,
                  'runner_root': str(runner.ROOT), 'retrieval_runner_root': str(retrieval.ROOT),
                  'config_matches': True, 'packages_match': True, 'python_matches': True,
                  'device_policy_matches': True, 'embedding_asset_sha256': asset_hashes,
                  'network_process_audit_guard': 'enabled; no external call made',
                  'freeze_worker_collect_or_inference_called': False}))
'''


def smoke(stage):
    env = dict(os.environ, PYTHONPATH=str(stage / 'src') + ':' + str(stage / 'scripts'),
               PYTHONDONTWRITEBYTECODE='1')
    command = [str(stage / '.venv/bin/python'), '-c', SMOKE, str(stage), str(FREEZE)]
    result = subprocess.run(command, cwd=stage, env=env, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError('offline frozen-source import smoke failed: ' + result.stderr)
    return json.loads(result.stdout)


def verify_stage(stage, output):
    frozen, shared = verify_frozen_inputs()
    locks = shared_lock_identities(stage)
    for name, digest in frozen['source_sha256'].items():
        path = stage / name
        if path.is_symlink() or not path.is_file() or sha(path) != digest:
            raise ValueError('staged source differs: ' + name)
    for name in ROOT_DOCS:
        if sha(stage / name) != sha(FREEZE / 'preparation' / name):
            raise ValueError('staged root preparation document differs: ' + name)
    result = smoke(stage)
    return {'stage': str(stage), 'new_output': str(output), 'frozen_source_count': 41,
            'frozen_seal_sha256': FREEZE_SEAL_SHA256, 'shared_input_sha256': shared,
            'shared_lock_identities': locks, 'offline_smoke': result}


def guarded_command(stage, output):
    # The verifier is rerun immediately before the unchanged live reproducer.
    # shlex.join/quote preserve spaces and literal shell metacharacters in paths.
    check = shlex.join([str(REPO / '.venv/bin/python'), str(Path(__file__).resolve()),
                        'verify', '--stage', str(stage), '--output', str(output)])
    live = shlex.join(['bash', 'evaluation/changing_memory_repair_20260914/reproduce_collection.sh', str(output)])
    body = check + ' && cd -- ' + shlex.quote(str(stage)) + ' && PYTHONDONTWRITEBYTECODE=1 ' + live
    return shlex.join(['bash', '-c', body])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('stage', 'verify'))
    parser.add_argument('--stage', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    stage, output = checked_paths(args.stage, args.output)
    if args.action == 'stage':
        if stage.exists() or stage.is_symlink():
            raise ValueError('source stage must not exist; preserve earlier staging artifacts')
        frozen, _ = verify_frozen_inputs()
        stage.mkdir(mode=0o700)
        try:
            for name, digest in frozen['source_sha256'].items():
                destination = stage / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(FREEZE / 'source' / name, destination)
                destination.chmod(0o400)
            for name in ROOT_DOCS:
                shutil.copyfile(FREEZE / 'preparation' / name, stage / name)
                (stage / name).chmod(0o400)
            (stage / 'evaluation').symlink_to(REPO / 'evaluation', target_is_directory=True)
            (stage / '.venv').symlink_to(REPO / '.venv', target_is_directory=True)
            proof = verify_stage(stage, output)
            proof.update(created_at=datetime.now(timezone.utc).isoformat(), helper_sha256=sha(Path(__file__)),
                executed_action='offline staging and verification only',
                live_reproduction_command_not_executed=guarded_command(stage, output),
                new_answers_require_new_blinded_reviews=True,
                limitations='No installed model HTTP/digest verification performed offline; unchanged reproducer re-freezes and compares model/runtime conditions before collection. Shared inputs/leases remain tied to this repository; do not copy the evaluation directory or run concurrently.')
            receipt = stage / 'staging_receipt.json'
            receipt.write_text(json.dumps(proof, indent=2) + '\n')
            receipt.chmod(0o400)
            # Never traverse or chmod either shared symlink target.
            for name in ('src', 'scripts', 'config', 'tests'):
                for directory in sorted((p for p in (stage/name).rglob('*') if p.is_dir()), reverse=True):
                    directory.chmod(0o500)
                (stage/name).chmod(0o500)
            stage.chmod(0o500)
        except BaseException as error:
            # Preserve partial stages; never silently delete a failed attempt.
            (stage / 'staging_failure.json').write_text(json.dumps({'error_type': type(error).__name__, 'error': str(error)}, indent=2) + '\n')
            raise
        print(json.dumps({'offline_staging_passed': True, 'stage': str(stage),
                          'receipt_sha256': sha(receipt), 'source_count': 41,
                          'live_command_not_executed': proof['live_reproduction_command_not_executed']}, indent=2))
    else:
        verify_stage(stage, output)
        print(json.dumps({'offline_verification_passed': True, 'source_count': 41,
                          'shared_real_evaluation_leases': True, 'stage': str(stage)}))


if __name__ == '__main__':
    main()
