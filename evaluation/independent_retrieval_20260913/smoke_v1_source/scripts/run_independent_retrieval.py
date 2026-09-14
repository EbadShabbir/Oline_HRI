"""Prospectively frozen, serialized six-condition independent retrieval experiment."""
from __future__ import annotations

import argparse
import base64
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
from time import perf_counter, perf_counter_ns, sleep

from oline_hri import evaluation_model_pairs as pair
from oline_hri.config import load_config
from oline_hri.embedding import BgeOnnxEmbedder, REQUIRED_ASSET_SHA256
from oline_hri.evaluation_systems import single_model_config
from oline_hri.timing import TraceRecorder
from post_memory_device_guard import stage2_limits, require_ready, policy_dict
from run_post_memory_comparison import ComparisonClient, ComparisonBackend, cleanup_owned, package_versions
from run_pair_remediation_validation import GuardedSampler

ROOT = Path(__file__).resolve().parents[1]
MODELS = ('qwen3:0.6b', 'qwen3:1.7b')
POLICIES = ('OFF', 'ALWAYS', 'SELECTIVE')
ORDERS = (
    ((0, ('OFF','ALWAYS','SELECTIVE')), (1, ('SELECTIVE','ALWAYS','OFF'))),
    ((1, ('ALWAYS','OFF','SELECTIVE')), (0, ('SELECTIVE','OFF','ALWAYS'))),
    ((0, ('ALWAYS','SELECTIVE','OFF')), (1, ('OFF','SELECTIVE','ALWAYS'))),
)

def write(path, value):
    pair._write_new_json(path, value)

def file_hash(path):
    return sha256(path.read_bytes()).hexdigest()

def configuration():
    base = load_config()
    return replace(base, generation=replace(base.generation, context_length=2048,
                   max_output_tokens=192, temperature=0.0, thinking=False))

def sources():
    paths = list((ROOT/'src/oline_hri').glob('*.py'))
    paths += [ROOT/'config/default.json', ROOT/'src/oline_hri/default_config.json']
    paths += [ROOT/'scripts'/name for name in (
        'run_independent_retrieval.py','independent_retrieval_adapter.py','smoke_independent_retrieval.py',
        'run_post_memory_comparison.py','run_complete_system.py',
        'run_pair_remediation_validation.py','post_memory_device_guard.py',
        'complete_system_device_guard.py','run_arc_capability.py')
        if (ROOT/'scripts'/name).exists()]
    paths += list((ROOT/'tests').glob('test_independent_retrieval*.py'))
    return {str(p.relative_to(ROOT)):file_hash(p) for p in sorted(set(paths))}

def model_inventory():
    installed = pair._installed_models()
    return {m:pair._model_metadata(m, installed) for m in MODELS}

def schedule(runtime):
    result=[]
    for rep, groups in enumerate(ORDERS, 1):
        ids=[c['id'] for c in runtime['execution_cases']]
        random.Random(runtime['metadata']['execution_case_order_seeds'][rep-1]).shuffle(ids)
        for model_index, policies in groups:
            for policy in policies:
                result.append(dict(slot=len(result)+1, repetition=rep,
                    model=MODELS[model_index], policy=policy, request_ids=ids))
    return result

def seal(directory):
    manifest={str(p.relative_to(directory)):file_hash(p)
              for p in sorted(directory.rglob('*')) if p.is_file() and p!=directory/'seal.json'}
    write(directory/'seal.json', dict(sha256=manifest,
          created_at=datetime.now(timezone.utc).isoformat(),
          immutability='exclusive creation, SHA256 manifest, read-only permissions; not privileged WORM'))
    for p in directory.rglob('*'):
        p.chmod(0o500 if p.is_dir() else 0o400)
    directory.chmod(0o500)

def verify_seal(directory):
    manifest=json.loads((directory/'seal.json').read_text())['sha256']
    actual={str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file() and p!=directory/'seal.json'}
    if actual != set(manifest) or any(file_hash(directory/p)!=h for p,h in manifest.items()):
        raise ValueError('sealed artifact differs from manifest')

def host():
    def command(args):
        r=subprocess.run(args,capture_output=True,text=True,timeout=10)
        return dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
    return dict(snapshot=pair.capture_safety_snapshot(), swaps=Path('/proc/swaps').read_text(),
        storage=command(['findmnt','-T',str(ROOT)]), uname=command(['uname','-a']),
        background=command(['ps','-eo','pid,comm,%cpu,%mem','--sort=-%mem']),
        service=command(['systemctl','show','ollama','-p','Environment','-p','ExecStart']))

def require_exclusive():
    output=subprocess.run(['ps','-eo','pid,args'],capture_output=True,text=True,check=True).stdout
    conflicts=[]
    for line in output.splitlines():
        if any(name in line for name in ('scripts/run_', 'scripts/continue_', 'scripts/resume_')):
            if 'run_independent_retrieval.py' not in line and 'python' in line and 'ps -eo' not in line:
                conflicts.append(line.strip())
    if conflicts:
        raise pair.SafetyGateError('other experiment process present: '+repr(conflicts))

@contextmanager
def inference_lock():
    with ExitStack() as stack:
        for name in ('independent_retrieval_inference.lock','matched_evidence_inference.lock'):
            stream=stack.enter_context((ROOT/'evaluation'/name).open('a'))
            fcntl.flock(stream, fcntl.LOCK_EX|fcntl.LOCK_NB)
        require_exclusive()
        yield

@contextmanager
def batch_lock():
    with (ROOT/'evaluation/independent_retrieval_batch.lock').open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield

def initial_sample(backend, sampler):
    deadline=perf_counter()+5
    while not sampler.samples and perf_counter()<deadline:
        backend.check(); sleep(.05)
    if not sampler.samples:
        raise pair.SafetyGateError('no initial telemetry sample')
    backend.check()

def prepare(args):
    from independent_retrieval_adapter import materialize_snapshot
    runtime=json.loads(args.runtime.read_text())
    directory=pair._new_private_directory(args.output.absolute())
    config=configuration()
    status='failed'; sampler=None
    try:
        with inference_lock(), stage2_limits():
            start=pair.capture_safety_snapshot(); write(directory/'start.json',start)
            require_ready(start)
            with pair._DurableJsonlWriter(directory/'telemetry.jsonl') as telemetry:
                monitor=pair._StreamingSafetyMonitor(telemetry); sampler=GuardedSampler(monitor)
                backend=ComparisonBackend(None,start,sampler,MODELS)
                with sampler:
                    initial_sample(backend,sampler)
                    began=perf_counter_ns()
                    embedder=BgeOnnxEmbedder(config.embedding.model_directory,config.embedding.intra_op_threads)
                    store,setup=materialize_snapshot(directory/'memory.sqlite3',runtime['memory_seed'],embedder)
                    backend.check()
                    write(directory/'setup.json',dict(details=setup,wall_ns=perf_counter_ns()-began,
                          runtime_sha256=file_hash(args.runtime),device_policy=policy_dict()))
                    del store,embedder
            write(directory/'finish.json',pair.capture_safety_snapshot())
            status='complete'
    finally:
        write(directory/'status.json',dict(status=status,telemetry=sampler.summary() if sampler else None))
        seal(directory)
    print(directory,flush=True)

def freeze(args):
    directory=pair._new_private_directory(args.output.absolute())
    runtime=json.loads((args.draft/'runtime.json').read_text())
    references=json.loads((args.draft/'references.json').read_text())
    review=json.loads(args.review.read_text())
    if review.get('approved') is not True:
        raise ValueError('independent pre-inference approval required')
    for name in ('runtime.json','references.json','protocol.md'):
        if review['sha256'][name] != file_hash(args.draft/name):
            raise ValueError('reviewed inputs changed: '+name)
    if review.get('source_sha256') != sources():
        raise ValueError('source changed after independent harness review')
    if len(runtime['execution_cases'])!=48 or len({c['id'] for c in runtime['execution_cases']})!=48:
        raise ValueError('exactly 48 unique requests required')
    verify_seal(args.snapshot)
    if json.loads((args.snapshot/'status.json').read_text())['status']!='complete':
        raise ValueError('snapshot preparation incomplete')
    if json.loads((args.snapshot/'setup.json').read_text())['runtime_sha256']!=file_hash(args.draft/'runtime.json'):
        raise ValueError('snapshot runtime differs')
    for name in ('runtime.json','references.json','protocol.md'):
        shutil.copyfile(args.draft/name,directory/name)
    shutil.copyfile(args.review,directory/'independent_preflight_review.json')
    shutil.copytree(args.snapshot,directory/'prepared_snapshot')
    # Remove copied permissions so the outer seal can be generated normally.
    for p in (directory/'prepared_snapshot').rglob('*'):
        p.chmod(0o700 if p.is_dir() else 0o600)
    (directory/'prepared_snapshot').chmod(0o700)
    hashes=sources()
    for rel in hashes:
        dest=directory/'source'/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/rel,dest)
    prep=directory/'preparation';prep.mkdir()
    for name in ('developments.MD','results.md','evaluation/adaptive_selection_protocol_draft.md',
                 'evaluation/memory_pipeline_20260912/README.md','evaluation/post_memory_comparison_20260912/README.md'):
        dest=prep/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
    for p in args.draft.glob('*'):
        if p.is_file() and p.name not in ('runtime.json','references.json','protocol.md'):
            shutil.copyfile(p,prep/p.name)
    config=configuration()
    write(directory/'freeze.json',dict(created_at=datetime.now(timezone.utc).isoformat(),
        runtime_sha256=file_hash(directory/'runtime.json'),references_sha256=file_hash(directory/'references.json'),
        source_sha256=hashes,models=model_inventory(),ollama_version=pair._http_json('/api/version'),
        config=config.to_dict(),seed=42,embedding_asset_sha256=REQUIRED_ASSET_SHA256,
        packages=package_versions(),python=sys.version,device_policy=policy_dict(),schedule=schedule(runtime),
        planned_attempts=864,host=host()))
    shown={m:pair._http_json('/api/show',body={'model':m}) for m in MODELS}
    if any(shown[MODELS[0]].get(key)!=shown[MODELS[1]].get(key) for key in ('template','parameters')):
        raise ValueError('model default templates or decoding parameters differ')
    write(directory/'model_show.json',shown)
    seal(directory);print(directory,flush=True)

def verify_frozen(directory):
    if sys.flags.optimize: raise ValueError('nonoptimized Python required')
    verify_seal(directory)
    frozen=json.loads((directory/'freeze.json').read_text())
    runtime=json.loads((directory/'runtime.json').read_text())
    expected=(sources(),model_inventory(),pair._http_json('/api/version'),configuration().to_dict(),
              dict(REQUIRED_ASSET_SHA256),package_versions(),sys.version,policy_dict(),schedule(runtime))
    recorded=tuple(frozen[k] for k in ('source_sha256','models','ollama_version','config',
              'embedding_asset_sha256','packages','python','device_policy','schedule'))
    if expected!=recorded: raise ValueError('frozen source/models/runtime/configuration drift')
    return frozen,runtime

class DurableClient(ComparisonClient):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        original=self._opener
        def open_recorded(request,**options):
            response=original(request,**options)
            return RecordedResponse(response,self.http_writer)
        self._opener=open_recorded

    def _post_json(self,endpoint,body,**kwargs):
        self.http_writer.write(dict(event='http_start',endpoint=endpoint,body=body,
                                   started_monotonic_ns=perf_counter_ns()))
        return super()._post_json(endpoint,body,**kwargs)

class RecordedResponse:
    """Preserve received bytes before decoding, including partial failed bodies.

    The underlying non-streaming API, byte cap, response parsing and timeout
    stay unchanged. Only bytes actually received can be preserved; an abort
    before the server sends an output has no generated text available.
    """
    def __init__(self,response,writer):
        self.response,self.writer=response,writer
    def __enter__(self):
        self.response.__enter__();return self
    def __exit__(self,*args):
        return self.response.__exit__(*args)
    def read(self,limit):
        chunks=[];size=0
        read=getattr(self.response,'read1',self.response.read)
        while size<limit:
            chunk=read(min(4096,limit-size))
            if not chunk: break
            chunks.append(chunk);size+=len(chunk)
            self.writer.write(dict(event='http_received_bytes',offset=size-len(chunk),
                  bytes_base64=base64.b64encode(chunk).decode('ascii'),monotonic_ns=perf_counter_ns()))
        return b''.join(chunks)

def run_cases(cases,slot,config,backend,store,directory):
    from independent_retrieval_adapter import IndependentRetrievalAdapter
    records=[]
    with pair._DurableJsonlWriter(directory/'observations.jsonl') as writer, \
         pair._DurableJsonlWriter(directory/'events.jsonl') as events:
        for index,case in enumerate(cases,1):
            backend.check(); backend.transport_error=None
            adapter=IndependentRetrievalAdapter(backend,store,model=slot['model'],policy=slot['policy'].lower(),
                     consent_authorized=case['consent_authorized'],profile_id=case['profile_id'])
            row=dict(case=case,**{k:v for k,v in slot.items() if k!='request_ids'},index=index,status='error',
                     api_ps_before=list(pair._resident_models()))
            checkpoint=len(backend.calls);http_checkpoint=len(backend.client.http_calls)
            trace=TraceRecorder(sink=lambda e:events.write(dict(request_id=case['id'],**e)))
            reply=None; fatal=None;began=perf_counter_ns()
            row['started_monotonic_ns']=began
            events.write(dict(event='request_start',request_id=case['id'],monotonic_ns=began))
            try:
                with trace.activate(): reply=adapter.send(case['prompt'],config)
                row.update(status='ok',response=reply.response.to_dict(),generation=asdict(reply.generation),
                           memory=reply.memory_diagnostics.to_dict(),answer_constraint=reply.answer_constraint,
                           generation_policy=reply.generation_policy,response_transform=reply.response_transform,
                           reference_ids=list(reply.reference_ids),fallback_from_model=reply.fallback_from_model)
            except BaseException as error:
                row.update(error=type(error).__name__,message=str(error))
                if isinstance(error,(KeyboardInterrupt,SystemExit,pair.SafetyGateError)): fatal=error
                elif backend.transport_error is not None: fatal=backend.transport_error
            end=perf_counter_ns()
            row.update(finished_monotonic_ns=end,wall_ns=end-began,calls=backend.calls[checkpoint:],
                       http_calls=backend.client.http_calls[http_checkpoint:],trace=trace.events,
                       adapter=adapter.to_dict(reply))
            try:
                backend.check();row['api_ps_after']=list(pair._resident_models())
            except BaseException as error:
                fatal=error;row.update(post_check_error=type(error).__name__,post_check_message=str(error))
            if fatal is not None: row['status']='interrupted'
            writer.write(row);records.append(row)
            print(f"slot {slot['slot']:02} {slot['model']} {slot['policy']} r{slot['repetition']} "
                  f"{index}/{len(cases)} {case['id']} {row['status']} {row['wall_ns']/1e9:.3f}s",flush=True)
            if fatal is not None: raise fatal
    return records

def _session(args):
    from independent_retrieval_adapter import open_snapshot
    session_began=perf_counter_ns()
    frozen,runtime=verify_frozen(args.freeze)
    slot=frozen['schedule'][args.slot-1]
    config=single_model_config(configuration(),slot['model'])
    directory=pair._new_private_directory(args.output.absolute())
    write(directory/'manifest.json',dict(slot=slot,freeze_sha256=file_hash(args.freeze/'freeze.json'),
          config=config.to_dict(),device_policy=policy_dict()))
    status='incomplete'; failure=None;errors=[];sampler=backend=client=None;start=None
    path=None;before_hash=None
    with stage2_limits():
        try:
            require_exclusive()
            start=pair.capture_safety_snapshot();write(directory/'start.json',start);require_ready(start)
            with pair._DurableJsonlWriter(directory/'http_calls.jsonl') as http, \
                 pair._DurableJsonlWriter(directory/'telemetry.jsonl') as telemetry:
                client=DurableClient(config.ollama,config.generation,http_writer=http,retain_large_model=True)
                monitor=pair._StreamingSafetyMonitor(telemetry);sampler=GuardedSampler(monitor)
                backend=ComparisonBackend(client,start,sampler,(slot['model'],))
                with sampler:
                    try:
                        initial_sample(backend,sampler);began=perf_counter_ns()
                        embedder=BgeOnnxEmbedder(config.embedding.model_directory,config.embedding.intra_op_threads)
                        path=directory/'memory.sqlite3'
                        shutil.copyfile(args.freeze/'prepared_snapshot/memory.sqlite3',path);path.chmod(0o600)
                        before_hash=file_hash(path)
                        store=open_snapshot(path,runtime['memory_seed'],embedder)
                        write(directory/'setup.json',dict(wall_ns=perf_counter_ns()-began,snapshot_sha256=before_hash))
                        backend.check()
                        case_map={c['id']:c for c in runtime['execution_cases']}
                        rows=run_cases([case_map[i] for i in slot['request_ids']],slot,config,backend,store,directory)
                        status='complete' if all(r['status']=='ok' for r in rows) else 'complete_with_errors'
                        if before_hash!=file_hash(path): raise ValueError('prepared snapshot mutated')
                    finally:
                        cleanup_began=perf_counter_ns()
                        errors.extend(cleanup_owned(client,backend))
                        write(directory/'cleanup_timing.json',dict(wall_ns=perf_counter_ns()-cleanup_began))
        except BaseException as error:
            status='interrupted';failure=dict(type=type(error).__name__,message=str(error))
        finally:
            if path is not None and path.exists():
                after_hash=file_hash(path)
                write(directory/'snapshot_verification.json',dict(before=before_hash,after=after_hash,
                      unchanged=before_hash==after_hash))
                if before_hash!=after_hash: errors.append('prepared snapshot mutated')
            try:
                finish=pair.capture_safety_snapshot()
                if finish['resident_models']: errors.append('resident models after session')
                if start and any(finish[k]!=start[k] for k in ('boot_id','thermal_trip_events','power_mode')):
                    errors.append('boot/trips/power changed')
                if start and finish['memory']['swap_total_kib']!=start['memory']['swap_total_kib']:
                    errors.append('swap capacity changed')
            except BaseException as error:
                finish=dict(error=type(error).__name__,message=str(error));errors.append('missing final snapshot')
            write(directory/'finish.json',finish)
            if sampler: write(directory/'telemetry_summary.json',sampler.summary())
            try:
                verify_frozen(args.freeze)
            except BaseException as error: errors.append('final integrity: '+str(error))
            if errors: status='verification_failed'
            observations=directory/'observations.jsonl'
            attempted=sum(1 for _ in observations.open()) if observations.exists() else 0
            write(directory/'summary.json',dict(status=status,failure=failure,cleanup_errors=errors,
                  attempted=attempted,planned=48,session_wall_ns=perf_counter_ns()-session_began))
            seal(directory)
    return 0 if status.startswith('complete') else 1

def session(args):
    with inference_lock():
        return _session(args)

def collect(args):
    frozen,runtime=verify_frozen(args.freeze)
    directory=pair._new_private_directory(args.output.absolute())
    write(directory/'plan.json',dict(schedule=frozen['schedule'],planned_attempts=864,
          freeze_sha256=file_hash(args.freeze/'freeze.json'),continuation_from=str(args.resume) if args.resume else None))
    completed={};baseline=None;status='incomplete';failure=None
    if args.resume:
        previous=json.loads((args.resume/'batch_finish.json').read_text())
        if json.loads((args.resume/'plan.json').read_text())['freeze_sha256']!=file_hash(args.freeze/'freeze.json'):
            raise ValueError('continuation freeze differs from original collection')
        for entry in previous['sessions']:
            path=Path(entry['directory']);verify_seal(path)
            summary=json.loads((path/'summary.json').read_text())
            if summary['status'].startswith('complete') and summary['attempted']==48:
                completed[entry['slot']]=entry
            elif summary['attempted']:
                raise ValueError('partial answered session cannot be spliced or retried')
    entries=list(completed.values())
    try:
        with batch_lock():
            baseline=pair.capture_safety_snapshot();write(directory/'before.json',baseline)
            with pair._DurableJsonlWriter(directory/'startup_waits.jsonl') as waits:
                for slot in frozen['schedule']:
                    if slot['slot'] in completed: continue
                    admission_began=perf_counter_ns()
                    deadline=perf_counter()+600
                    while True:
                        state=pair.capture_safety_snapshot()
                        if any(state[k]!=baseline[k] for k in ('boot_id','thermal_trip_events','power_mode')):
                            raise pair.SafetyGateError('device state changed between sessions')
                        try:
                            with stage2_limits(): require_ready(state)
                            if max(state['temperatures_c'].values())>=54:
                                raise pair.SafetyGateError('scheduler cooldown to below 54 C')
                            break
                        except pair.SafetyGateError as error:
                            waits.write(dict(slot=slot['slot'],snapshot=state,error=str(error)))
                            if state['resident_models'] or perf_counter()>=deadline: raise
                            print(f"WAIT slot {slot['slot']} {error}",flush=True);sleep(20)
                    waits.write(dict(event='admission_complete',slot=slot['slot'],
                                     wall_ns=perf_counter_ns()-admission_began))
                    target=directory/f"session_{slot['slot']:02d}"
                    entry=dict(slot=slot['slot'],directory=str(target));entries.append(entry)
                    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'session',
                            '--freeze',str(args.freeze.resolve()),'--output',str(target),'--slot',str(slot['slot'])])
                    entry['exit_code']=result.returncode
                    if result.returncode: raise RuntimeError(f"session {slot['slot']} interrupted")
            status='complete'
    except BaseException as error:
        status='interrupted';failure=dict(type=type(error).__name__,message=str(error))
    finally:
        try: finish=host()
        except BaseException as error: finish=dict(error=type(error).__name__,message=str(error))
        write(directory/'batch_finish.json',dict(status=status,failure=failure,sessions=entries,finish=finish))
        # Sessions have their own seals; seal only terminal batch after all children exit.
        seal(directory)
    print(f"BATCH {status} {directory}",flush=True)
    return 0 if status=='complete' else 1

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare');a.add_argument('--runtime',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('freeze');a.add_argument('--draft',type=Path,required=True);a.add_argument('--snapshot',type=Path,required=True)
    a.add_argument('--review',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('session');a.add_argument('--slot',type=int,choices=range(1,19),required=True)
    a.add_argument('--freeze',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('collect');a.add_argument('--freeze',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a.add_argument('--resume',type=Path)
    args=p.parse_args();return globals()[args.command](args)

if __name__=='__main__': sys.exit(main())
