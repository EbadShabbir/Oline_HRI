"""Prospectively sealed continuation of an exact, already-attempted prefix.

Only orchestration changes. The original inference implementation and its
44-file freeze stay untouched. Every fatal request stops this collection;
another continuation requires another explicit sealed plan.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
from time import monotonic, monotonic_ns, sleep

from independent_retrieval_supervisor import (ROOT, append, digest, lock,
    read, recoverable, seal, verify, worker, write)

SUPPLEMENTAL_SOURCES = (
    'scripts/independent_retrieval_continuation.py',
    'scripts/independent_retrieval_fragment_worker.py',
    'tests/test_retrieval_continuation.py',
    'tests/test_retrieval_fragment_worker.py',
)


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def expected_config(frozen, model):
    result = deepcopy(frozen['config']); config = result['ollama']
    timeout = config['request_timeout_seconds'] if model == config['small_model'] else config['large_request_timeout_seconds']
    for key in ('small_model', 'general_large_model', 'large_model'):
        config[key] = model
    config['request_timeout_seconds'] = timeout
    return result


def frozen_checks(directory):
    verify(directory); frozen = read(directory/'freeze.json')
    if any(digest(ROOT/name) != value for name, value in frozen['source_sha256'].items()):
        raise ValueError('original frozen execution source changed')
    return frozen


def history(freeze, entries):
    """Validate raw immutable chronology without reading scoring references."""
    frozen = read(freeze/'freeze.json')
    runtime = read(freeze/'runtime.json')
    cases = {case['id']: case for case in runtime['execution_cases']}
    schedule = {slot['slot']: slot for slot in frozen['schedule']}
    expected = [(slot['slot'], case) for slot in frozen['schedule'] for case in slot['request_ids']]
    observed = []; identities = []; directories = set(); normalized = []; baseline = None
    offsets = {slot: 0 for slot in schedule}; previous_end = None
    for entry in entries:
        directory = Path(entry['directory']).resolve()
        if directory in directories:
            raise ValueError('duplicate physical fragment')
        directories.add(directory); verify(directory)
        artifact_hash = digest(directory/'seal.json')
        if entry.get('seal_sha256', artifact_hash) != artifact_hash:
            raise ValueError('physical fragment seal changed')
        manifest, summary = read(directory/'manifest.json'), read(directory/'summary.json')
        slot = schedule[entry['slot']]
        if manifest['slot'] != slot or manifest['freeze_sha256'] != digest(freeze/'freeze.json'):
            raise ValueError('prior slot or freeze differs')
        if manifest['config'] != expected_config(frozen, slot['model']) or manifest['device_policy'] != frozen['device_policy']:
            raise ValueError('prior configuration or resource limits differ')
        offset = manifest.get('fragment', {}).get('offset', 0)
        if offset != offsets[slot['slot']]:
            raise ValueError('prior fragment does not start at its exact unattempted suffix')
        remaining = slot['request_ids'][offset:]
        if 'fragment' in manifest and manifest['fragment']['request_ids'] != remaining:
            raise ValueError('prior fragment request list differs')
        if 'fragment' in manifest:
            fragment=manifest['fragment']; ledger_dir=Path(fragment['ledger_directory']); continuation_dir=Path(fragment['continuation_directory'])
            verify(ledger_dir); verify(continuation_dir)
            ledger=read(ledger_dir/'ledger.json'); continuation=checked_plan_artifacts(continuation_dir)
            if fragment['ledger_sha256']!=digest(ledger_dir/'ledger.json') or fragment['ledger_seal_sha256']!=digest(ledger_dir/'seal.json') or fragment['continuation_sha256']!=digest(continuation_dir/'continuation.json') or fragment['continuation_seal_sha256']!=digest(continuation_dir/'seal.json'):
                raise ValueError('prior fragment ledger or continuation seal changed')
            if ledger['prior_attempts']!=identities or ledger['prior_sessions']!=normalized or ledger['slot']!=slot['slot'] or ledger['offset']!=offset or ledger['request_ids']!=remaining:
                raise ValueError('prior fragment ledger does not preserve preceding history')
            if ledger['continuation_sha256']!=digest(continuation_dir/'continuation.json') or ledger['freeze_sha256']!=digest(freeze/'freeze.json') or ledger['authorized_worker_directory']!=str(directory):
                raise ValueError('prior fragment ledger authorization differs')
            if Path(continuation['authorized_run_directory'])!=directory.parent or continuation['prior_attempts']!=identities[:continuation['attempted']]:
                raise ValueError('prior fragment was not authorized by its continuation')
        rows = jsonl(directory/'observations.jsonl')
        starts = [item['request_id'] for item in jsonl(directory/'events.jsonl') if item.get('event') == 'request_start']
        if starts != [row['case']['id'] for row in rows]:
            raise ValueError('durable request starts and terminal observations differ')
        if summary['attempted'] != len(rows) or summary['planned'] != len(remaining):
            raise ValueError('prior attempt accounting differs')
        if not rows or len(rows) > len(remaining):
            raise ValueError('history must contain request-bearing fragments only')
        if summary.get('cleanup_errors') or summary['status'] not in ('complete', 'complete_with_errors', 'interrupted'):
            raise ValueError('prior fragment cleanup or integrity failed')
        if summary['status'].startswith('complete') and len(rows) != len(remaining):
            raise ValueError('complete fragment is missing requests')
        start, finish = read(directory/'start.json'), read(directory/'finish.json')
        if baseline is None:
            baseline = directory/'start.json'
        original = read(baseline)
        for state in (start, finish):
            if state.get('resident_models') != []:
                raise ValueError('resident model at prior fragment boundary')
            if any(state[k] != original[k] for k in ('boot_id', 'thermal_trip_events', 'power_mode')) or state['memory']['swap_total_kib'] != original['memory']['swap_total_kib']:
                raise ValueError('original device baseline changed')
        snapshot = read(directory/'snapshot_verification.json')
        expected_snapshot = digest(freeze/'prepared_snapshot/memory.sqlite3')
        if not snapshot['unchanged'] or snapshot['before'] != expected_snapshot or snapshot['after'] != expected_snapshot:
            raise ValueError('prior prepared snapshot changed')
        if digest(directory/'memory.sqlite3')!=expected_snapshot or read(directory/'setup.json')['snapshot_sha256']!=expected_snapshot:
            raise ValueError('actual prior snapshot or setup differs')
        for index, row in enumerate(rows, 1):
            identifier = remaining[index-1]
            if row['case'] != cases[identifier] or row['index'] != index or any(row[k] != slot[k] for k in ('slot', 'model', 'policy', 'repetition')):
                raise ValueError('prior request identity or local ordering differs')
            if previous_end is not None and row['started_monotonic_ns'] < previous_end:
                raise ValueError('prior requests overlap')
            if row['finished_monotonic_ns'] < row['started_monotonic_ns'] or row['wall_ns'] != row['finished_monotonic_ns']-row['started_monotonic_ns']:
                raise ValueError('prior request timing differs')
            previous_end = row['finished_monotonic_ns']
            if row['status'] == 'interrupted' and index != len(rows):
                raise ValueError('requests followed a fatal interruption in one fragment')
            observed.append((slot['slot'], identifier))
            identities.append({'slot': slot['slot'], 'case_id': identifier, 'status': row['status']})
        offsets[slot['slot']] += len(rows)
        normalized.append({**entry, 'directory': str(directory), 'seal_sha256': artifact_hash})
    if observed != expected[:len(observed)] or len(set(observed)) != len(observed):
        raise ValueError('attempted history is not the unique strict frozen prefix')
    return dict(prior_sessions=normalized, prior_attempts=identities, offsets=offsets,
                attempted=len(observed), remaining=864-len(observed), baseline=str(baseline) if baseline else None)


def collection_chain(directory, freeze, visited=None):
    directory = Path(directory).resolve(); visited = set() if visited is None else visited
    if directory in visited:
        raise ValueError('cyclic continuation ancestry')
    visited.add(directory); verify(directory)
    plan, finish = read(directory/'plan.json'), read(directory/'batch_finish.json')
    frozen = read(freeze/'freeze.json')
    if plan['freeze_sha256'] != digest(freeze/'freeze.json') or plan['schedule'] != frozen['schedule'] or not finish['source_unchanged'] or finish.get('supplemental_source_unchanged',True) is not True or finish['status'] not in ('complete','interrupted'):
        raise ValueError('collection ancestry changed its frozen controls')
    current = history(freeze, finish['sessions'])
    if plan.get('continuation_from'):
        prior = collection_chain(Path(plan['continuation_from']), freeze, visited)
        if current['prior_sessions'][:len(prior['prior_sessions'])] != prior['prior_sessions'] or current['prior_attempts'][:prior['attempted']] != prior['prior_attempts']:
            raise ValueError('continuation ancestry replaced prior observations')
    return current


def checked_plan_artifacts(directory):
    plan=read(directory/'continuation.json'); review=read(directory/'independent_review.json')
    if digest(directory/'independent_review.json')!=plan['review_sha256'] or digest(directory/'protocol_amendment.md')!=plan['protocol_sha256']:
        raise ValueError('continuation review or protocol hash differs')
    if review.get('approved') is not True or review.get('source_sha256')!=plan['source_sha256'] or review.get('prior_run_seal_sha256')!=plan['prior_run_seal_sha256'] or review.get('protocol_sha256')!=plan['protocol_sha256']:
        raise ValueError('continuation independent review does not bind its execution')
    if review.get('authorized_run_directory')!=plan['authorized_run_directory'] or review.get('continuation_directory')!=str(directory.resolve()) or plan.get('continuation_directory')!=str(directory.resolve()):
        raise ValueError('independent review cannot authorize another continuation or run directory')
    if set(plan['source_sha256'])!=set(SUPPLEMENTAL_SOURCES) or any(digest(directory/'source'/name)!=value for name,value in plan['source_sha256'].items()):
        raise ValueError('continuation archived source differs')
    return plan


def verify_continuation(freeze_dir, continuation_dir):
    freeze_dir, continuation_dir = Path(freeze_dir).resolve(), Path(continuation_dir).resolve()
    frozen_checks(freeze_dir); verify(continuation_dir)
    plan = checked_plan_artifacts(continuation_dir)
    if plan['freeze_sha256'] != digest(freeze_dir/'freeze.json') or plan['freeze_seal_sha256'] != digest(freeze_dir/'seal.json'):
        raise ValueError('continuation changes the original freeze')
    if set(plan['source_sha256']) != set(SUPPLEMENTAL_SOURCES):
        raise ValueError('supplemental source inventory differs')
    for name, value in plan['source_sha256'].items():
        if digest(ROOT/name) != value or digest(continuation_dir/'source'/name) != value:
            raise ValueError('supplemental execution source changed')
    prior = Path(plan['prior_run']); verify(prior)
    if digest(prior/'seal.json') != plan['prior_run_seal_sha256']:
        raise ValueError('prior collection seal changed')
    audited = collection_chain(prior, freeze_dir)
    for key in ('prior_sessions', 'prior_attempts', 'attempted', 'remaining', 'baseline'):
        if audited[key] != plan[key]:
            raise ValueError('continuation does not preserve prior collection: '+key)
    if plan['prior_rejected_sessions']!=read(prior/'batch_finish.json').get('rejected_sessions',[]):
        raise ValueError('continuation replaces rejected admission records')
    return plan


def verify_ledger(freeze_dir, continuation_dir, ledger_dir, slot_id, offset):
    plan = verify_continuation(freeze_dir, continuation_dir)
    ledger_dir = Path(ledger_dir).resolve(); verify(ledger_dir); ledger = read(ledger_dir/'ledger.json')
    if ledger['continuation_sha256'] != digest(Path(continuation_dir)/'continuation.json') or ledger['freeze_sha256'] != plan['freeze_sha256']:
        raise ValueError('ledger provenance differs')
    audited = history(Path(freeze_dir), ledger['prior_sessions'])
    if audited['prior_attempts'][:plan['attempted']] != plan['prior_attempts'] or audited['prior_sessions'][:len(plan['prior_sessions'])] != plan['prior_sessions']:
        raise ValueError('ledger replaces previous observations')
    if ledger['prior_attempts'] != audited['prior_attempts'] or ledger['baseline'] != plan['baseline']:
        raise ValueError('ledger prefix or baseline differs')
    frozen = read(Path(freeze_dir)/'freeze.json')
    remaining_slots = [s for s in frozen['schedule'] if audited['offsets'][s['slot']] < 48]
    if not remaining_slots or remaining_slots[0]['slot'] != slot_id:
        raise ValueError('ledger skips the next scheduled slot')
    slot = remaining_slots[0]; expected_offset = audited['offsets'][slot_id]
    if ledger['slot'] != slot_id or ledger['offset'] != offset or offset != expected_offset or ledger['request_ids'] != slot['request_ids'][offset:]:
        raise ValueError('ledger is not the exact remaining suffix')
    run_directory = Path(plan['authorized_run_directory'])
    retry = ledger['admission_index']
    if type(retry) is not int or retry < 0:
        raise ValueError('invalid admission index')
    expected_ledger = run_directory/f'ledger_{slot_id:02d}_{offset:02d}_admission_{retry:02d}'
    expected_worker = fragment_path(run_directory, slot_id, offset, retry)
    if ledger_dir != expected_ledger or Path(ledger['authorized_worker_directory']) != expected_worker:
        raise ValueError('ledger or physical worker output was not authorized')
    rejected = ledger['admission_rejections']
    if len(rejected) != retry:
        raise ValueError('missing prior zero-attempt admission proof')
    for index, entry in enumerate(rejected):
        target = fragment_path(run_directory, slot_id, offset, index)
        if Path(entry['directory']) != target:
            raise ValueError('admission retries are not contiguous')
        verify(target)
        if entry['seal_sha256'] != digest(target/'seal.json') or not recoverable(read(target/'summary.json'), target):
            raise ValueError('attempted or unverified admission cannot be retried')
        manifest=read(target/'manifest.json'); initial=read(target/'start.json'); final=read(target/'finish.json')
        if manifest['slot']!=slot or manifest['freeze_sha256']!=plan['freeze_sha256'] or manifest['config']!=expected_config(frozen,slot['model']) or manifest['device_policy']!=frozen['device_policy']:
            raise ValueError('rejected admission changed its frozen controls')
        if manifest.get('fragment',{}).get('offset')!=offset or manifest['fragment']['request_ids']!=slot['request_ids'][offset:]:
            raise ValueError('rejected admission belonged to a different suffix')
        baseline=read(Path(plan['baseline']))
        if any(state.get('resident_models')!=[] or any(state[k]!=baseline[k] for k in ('boot_id','thermal_trip_events','power_mode')) or state['memory']['swap_total_kib']!=baseline['memory']['swap_total_kib'] for state in (initial,final)):
            raise ValueError('rejected admission changed the device baseline')
        if jsonl(target/'observations.jsonl') or jsonl(target/'events.jsonl') or jsonl(target/'http_calls.jsonl'):
            raise ValueError('admission retry would replace an attempted request or call')
    return ledger


def fragment_path(directory, slot, offset, retry):
    name=f"session_{slot:02d}_from_{offset+1:02d}"+(f"_admission_retry_{retry:02d}" if retry else '')
    return directory/name


def freeze_plan(args):
    frozen = frozen_checks(args.freeze); verify(args.prior)
    old_plan, old_finish = read(args.prior/'plan.json'), read(args.prior/'batch_finish.json')
    if old_plan['freeze_sha256'] != digest(args.freeze/'freeze.json') or old_plan['schedule'] != frozen['schedule'] or not old_finish['source_unchanged']:
        raise ValueError('prior collection freeze or integrity differs')
    audited = collection_chain(args.prior, args.freeze)
    if audited['remaining'] <= 0:
        raise ValueError('no unattempted requests remain')
    source = {name:digest(ROOT/name) for name in SUPPLEMENTAL_SOURCES}
    review = read(args.review)
    if review.get('approved') is not True or review.get('source_sha256') != source or review.get('prior_run_seal_sha256') != digest(args.prior/'seal.json') or review.get('protocol_sha256') != digest(args.protocol) or review.get('authorized_run_directory')!=str(args.run_output.absolute()) or review.get('continuation_directory')!=str(args.output.absolute()):
        raise ValueError('independent review does not bind this prospective continuation')
    directory = args.output.absolute(); directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    for name in source:
        destination = directory/'source'/name; destination.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT/name, destination)
    shutil.copyfile(args.review, directory/'independent_review.json'); shutil.copyfile(args.protocol, directory/'protocol_amendment.md')
    write(directory/'continuation.json', dict(created_at=datetime.now(timezone.utc).isoformat(),
        freeze_sha256=digest(args.freeze/'freeze.json'), freeze_seal_sha256=digest(args.freeze/'seal.json'),
        prior_run=str(args.prior.resolve()), prior_run_seal_sha256=digest(args.prior/'seal.json'),
        authorized_run_directory=str(args.run_output.absolute()),
        continuation_directory=str(directory),
        source_sha256=source, protocol_sha256=digest(args.protocol), review_sha256=digest(args.review),
        prior_rejected_sessions=old_finish.get('rejected_sessions', []),
        rule='preserve every attempted request; exact remaining suffix; no retries or planned chunking; fatal fragment stops collection',
        **{k:v for k,v in audited.items() if k != 'offsets'}))
    seal(directory); print(f"CONTINUATION SEALED {audited['attempted']} retained; {audited['remaining']} remaining: {directory}", flush=True)


def collect(args):
    with lock():
        return _collect(args)


def _collect(args):
    supervisor_began=monotonic_ns(); supervisor_started_at=datetime.now(timezone.utc).isoformat()
    frozen_dir, continuation_dir = args.freeze.resolve(), args.continuation.resolve()
    plan = verify_continuation(frozen_dir, continuation_dir); frozen = read(frozen_dir/'freeze.json')
    directory = args.output.absolute()
    if directory != Path(plan['authorized_run_directory']):
        raise ValueError('continuation is bound to a different collection output')
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    write(directory/'plan.json', dict(schedule=frozen['schedule'], planned_attempts=864,
        freeze_sha256=plan['freeze_sha256'], continuation_from=plan['prior_run'],
        continuation_directory=str(continuation_dir), continuation_sha256=digest(continuation_dir/'continuation.json'),
        retained_attempts=plan['attempted'], new_planned_attempts=plan['remaining'],
        supervisor='stdlib-only; exact suffix continuation; original guarded workers',
        supervisor_started_monotonic_ns=supervisor_began, supervisor_started_at=supervisor_started_at,
        previous_run_seal_created_at=read(Path(plan['prior_run'])/'seal.json').get('created_at'),
        recovery='only zero-attempt resource admission rejections within600seconds; every fatal request stops collection'))
    sessions = list(plan['prior_sessions']); rejected = list(plan['prior_rejected_sessions'])
    status = 'incomplete'; failure = None; last_worker = None
    try:
        for slot in frozen['schedule']:
            audited = history(frozen_dir, sessions); offset = audited['offsets'][slot['slot']]
            if offset == 48:
                continue
            began=monotonic_ns(); deadline=monotonic()+600; retry=0; admission_rejections=[]
            while True:
                path=fragment_path(directory,slot['slot'],offset,retry)
                ledger_dir=directory/f"ledger_{slot['slot']:02d}_{offset:02d}_admission_{retry:02d}"
                ledger_dir.mkdir(mode=0o700)
                write(ledger_dir/'ledger.json', dict(freeze_sha256=plan['freeze_sha256'],
                    continuation_sha256=digest(continuation_dir/'continuation.json'),
                    slot=slot['slot'],offset=offset,request_ids=slot['request_ids'][offset:],
                    prior_sessions=audited['prior_sessions'],prior_attempts=audited['prior_attempts'],baseline=plan['baseline'],
                    admission_index=retry,admission_rejections=admission_rejections,authorized_worker_directory=str(path)))
                seal(ledger_dir);verify_ledger(frozen_dir,continuation_dir,ledger_dir,slot['slot'],offset)
                entry=dict(slot=slot['slot'], directory=str(path))
                last_worker=entry
                arguments=[sys.executable,str(ROOT/'scripts/independent_retrieval_fragment_worker.py'),
                    '--freeze',str(frozen_dir),'--continuation',str(continuation_dir),'--ledger',str(ledger_dir),
                    '--slot',str(slot['slot']),'--offset',str(offset),'--output',str(path),'--baseline',plan['baseline']]
                print(f"SESSION {slot['slot']}/18 {slot['model']} {slot['policy']} suffix{offset+1}–48 admission{retry+1}",flush=True)
                entry['exit_code']=worker(arguments)
                if not (path/'summary.json').exists():
                    sessions.append(entry); raise RuntimeError('worker failed without terminal artifacts')
                verify(path); summary=read(path/'summary.json'); entry['seal_sha256']=digest(path/'seal.json')
                if recoverable(summary,path) and monotonic()<deadline:
                    rejected.append(entry);admission_rejections.append(entry)
                    append(directory/'startup_waits.jsonl',dict(event='resource_admission_rejection',slot=slot['slot'],
                        directory=str(path),failure=summary['failure'],snapshot=read(path/'finish.json')))
                    print(f"WAIT {slot['slot']}: {summary['failure']['message']}",flush=True)
                    sleep(20); retry+=1; continue
                append(directory/'startup_waits.jsonl',dict(event='fragment_terminal_overhead',slot=slot['slot'],
                    directory=str(path),wall_ns=monotonic_ns()-began-summary.get('session_wall_ns',0),
                    includes_rejected_worker_checks=True,rejected_launches=retry,status=summary['status']))
                if summary['attempted']:
                    sessions.append(entry)
                else:
                    rejected.append(entry)
                if entry['exit_code']==0 and summary['attempted']==48-offset and summary['status'].startswith('complete'):
                    break
                raise RuntimeError(f"session {slot['slot']} interrupted; another explicit continuation is required")
        if history(frozen_dir,sessions)['attempted'] != 864:
            raise ValueError('collection is missing attempted coverage')
        status='complete'
    except BaseException as error:
        status='interrupted'; failure=dict(type=type(error).__name__,message=str(error))
    finally:
        last=last_worker if last_worker is not None else sessions[-1] if sessions else None
        final=read(Path(last['directory'])/'finish.json') if last and (Path(last['directory'])/'finish.json').exists() else None
        original_unchanged=all(digest(ROOT/name)==value for name,value in frozen['source_sha256'].items())
        supplemental_unchanged=all(digest(ROOT/name)==value for name,value in plan['source_sha256'].items())
        if not original_unchanged or not supplemental_unchanged:
            status='source_verification_failed'
        write(directory/'batch_finish.json',dict(status=status,failure=failure,sessions=sessions,rejected_sessions=rejected,
            finish={'snapshot':final},source_unchanged=original_unchanged,supplemental_source_unchanged=supplemental_unchanged,
            parent_os_thread_count=len(list(Path('/proc/self/task').iterdir())),
            parent_peak_rss_kib=__import__('resource').getrusage(__import__('resource').RUSAGE_SELF).ru_maxrss,
            supervisor_wall_ns=monotonic_ns()-supervisor_began))
        seal(directory)
    print(f"BATCH {status} {directory}",flush=True)
    return 0 if status=='complete' else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('freeze');p.add_argument('--prior',type=Path,required=True);p.add_argument('--review',type=Path,required=True);p.add_argument('--protocol',type=Path,required=True);p.add_argument('--run-output',type=Path,required=True)
    c=sub.add_parser('collect');c.add_argument('--continuation',type=Path,required=True)
    for command in (p,c):
        command.add_argument('--freeze',type=Path,required=True);command.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();return freeze_plan(args) if args.command=='freeze' else collect(args)


if __name__=='__main__':
    sys.exit(main())
