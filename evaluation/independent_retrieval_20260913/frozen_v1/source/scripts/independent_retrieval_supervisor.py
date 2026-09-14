"""Standard-library-only supervisor; model/embedding imports live in workers.

Each worker retains the existing guard and inference lock. Failed admission
directories remain immutable; only proven zero-attempt resource rejections
may be retried, within a bounded ten-minute window per scheduled session.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from time import monotonic, monotonic_ns, sleep

ROOT=Path(__file__).resolve().parents[1]

def read(path): return json.loads(path.read_text())
def digest(path): return sha256(path.read_bytes()).hexdigest()
def write(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,sort_keys=True,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
def append(path,value):
    with path.open('a') as stream:
        stream.write(json.dumps(value,sort_keys=True)+'\n');stream.flush();os.fsync(stream.fileno())
def verify(directory):
    hashes=read(directory/'seal.json')['sha256']
    names={str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file() and p!=directory/'seal.json'}
    if names!=set(hashes) or any(digest(directory/p)!=h for p,h in hashes.items()):
        raise ValueError('sealed artifact integrity failure')
def seal(directory):
    write(directory/'seal.json',dict(created_at=datetime.now(timezone.utc).isoformat(),
          sha256={str(p.relative_to(directory)):digest(p) for p in sorted(directory.rglob('*')) if p.is_file()},
          immutability='exclusive creation, SHA256 manifests, read-only permissions; not privileged WORM'))
    for p in directory.rglob('*'): p.chmod(0o500 if p.is_dir() else 0o400)
    directory.chmod(0o500)

@contextmanager
def lock():
    with (ROOT/'evaluation/independent_retrieval_batch.lock').open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB);yield

def recoverable(summary,directory):
    failure=summary.get('failure') or {}
    state=read(directory/'finish.json')
    return (summary.get('attempted')==0 and summary.get('status')=='interrupted'
            and not summary.get('cleanup_errors') and failure.get('type')=='SafetyGateError'
            and any(word in failure.get('message','') for word in
                    ('available memory is below','swap use exceeds','startup temperature'))
            and state.get('resident_models')==[])

def worker(arguments):
    process=subprocess.Popen(arguments)
    try:
        return process.wait()
    except BaseException:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            process.wait()  # Worker must finish guarded cleanup before sealing.
        raise

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--resume',type=Path)
    args=parser.parse_args(argv)
    frozen_dir=args.freeze.resolve();verify(frozen_dir)
    frozen=read(frozen_dir/'freeze.json')
    if any(digest(ROOT/p)!=h for p,h in frozen['source_sha256'].items()):
        raise ValueError('source differs before collection')
    directory=args.output.absolute();directory.mkdir(parents=True,mode=0o700,exist_ok=False)
    write(directory/'plan.json',dict(schedule=frozen['schedule'],planned_attempts=864,
          freeze_sha256=digest(frozen_dir/'freeze.json'),continuation_from=str(args.resume) if args.resume else None,
          supervisor='stdlib-only parent; fresh guarded model worker process',
          recovery='up to600seconds per slot; only preserved zero-attempt resource admission failures'))
    sessions=[];rejected=[];completed={};baseline=None;status='incomplete';failure=None
    if args.resume:
        verify(args.resume)
        old=read(args.resume/'batch_finish.json')
        if read(args.resume/'plan.json')['freeze_sha256']!=digest(frozen_dir/'freeze.json'):
            raise ValueError('continuation freeze differs')
        for entry in old['sessions']:
            path=Path(entry['directory']);verify(path);summary=read(path/'summary.json')
            if summary['attempted']==48 and summary['status'].startswith('complete'):
                completed[entry['slot']]=entry;sessions.append(entry)
                if baseline is None: baseline=path/'start.json'
            elif summary['attempted']:
                raise ValueError('answered partial sessions cannot be spliced or retried')
            else: rejected.append(entry)
        rejected.extend(old.get('rejected_sessions',[]))
    try:
        with lock():
            for slot in frozen['schedule']:
                if slot['slot'] in completed: continue
                began=monotonic_ns();deadline=monotonic()+600;retry=0
                while True:
                    name=f"session_{slot['slot']:02d}"+(f"_admission_retry_{retry:02d}" if retry else '')
                    path=directory/name
                    entry=dict(slot=slot['slot'],directory=str(path))
                    arguments=[sys.executable,str(ROOT/'scripts/run_independent_retrieval.py'),'session',
                               '--freeze',str(frozen_dir),'--output',str(path),'--slot',str(slot['slot'])]
                    if baseline is not None: arguments+=['--baseline',str(baseline)]
                    print(f"SESSION {slot['slot']}/18 {slot['model']} {slot['policy']} admission {retry+1}",flush=True)
                    entry['exit_code']=worker(arguments)
                    summary_path=path/'summary.json'
                    if not summary_path.exists():
                        sessions.append(entry);raise RuntimeError('worker failed before terminal artifact')
                    verify(path);summary=read(summary_path)
                    if baseline is None:
                        baseline=path/'start.json'
                        if baseline.exists(): write(directory/'before.json',read(baseline))
                    if entry['exit_code']==0 and summary['attempted']==48 and summary['status'].startswith('complete'):
                        sessions.append(entry)
                        append(directory/'startup_waits.jsonl',dict(event='admission_complete',slot=slot['slot'],
                            wall_ns=monotonic_ns()-began-summary.get('session_wall_ns',0),
                            includes_rejected_worker_checks=True,rejected_launches=retry))
                        break
                    if recoverable(summary,path) and monotonic()<deadline:
                        rejected.append(entry)
                        append(directory/'startup_waits.jsonl',dict(event='resource_admission_rejection',
                               slot=slot['slot'],directory=str(path),failure=summary['failure'],snapshot=read(path/'finish.json')))
                        print(f"WAIT {slot['slot']}: {summary['failure']['message']}",flush=True)
                        sleep(20);retry+=1;continue
                    sessions.append(entry);raise RuntimeError(f"session {slot['slot']} interrupted")
            status='complete'
    except BaseException as error:
        status='interrupted';failure=dict(type=type(error).__name__,message=str(error))
    finally:
        last=sessions[-1] if sessions else rejected[-1] if rejected else None
        last_path=Path(last['directory'])/'finish.json' if last else None
        final=read(last_path) if last_path and last_path.exists() else None
        current={p:digest(ROOT/p) for p in frozen['source_sha256']}
        if current!=frozen['source_sha256']: status='source_verification_failed'
        write(directory/'batch_finish.json',dict(status=status,failure=failure,sessions=sessions,
              rejected_sessions=rejected,finish={'snapshot':final},source_unchanged=current==frozen['source_sha256'],
              parent_os_thread_count=len(list(Path('/proc/self/task').iterdir())),
              parent_peak_rss_kib=__import__('resource').getrusage(__import__('resource').RUSAGE_SELF).ru_maxrss))
        seal(directory)
    print(f"BATCH {status} {directory}",flush=True)
    return 0 if status=='complete' else 1

if __name__=='__main__':sys.exit(main())
