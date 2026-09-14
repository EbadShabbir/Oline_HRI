"""Independent offline numerical audit; never prints or exports answer text.

This supplement is separate from the already frozen collector/analyzer. Its
source is copied and hashed into its own new sealed output directory. It reads
the original raw events directly and uses the frozen telemetry_metrics function
only for a cross-check against an independent prefix-integral calculation.
"""
from __future__ import annotations
import argparse
import ast
import base64
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import statistics

MODELS=('qwen3:0.6b','qwen3:1.7b')
CATEGORIES=('routine_general','constrained_general','personal_recall','personal_temporal')
SUCCESS={'complete','appropriate_abstention','appropriate_uncertainty'}

def unique(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError(f'duplicate JSON key: {key}')
        value[key]=item
    return value

def decode(raw):
    def reject(value):raise ValueError(f'nonstandard JSON constant: {value}')
    return json.loads(raw,object_pairs_hook=unique,parse_constant=reject)

def read(path):return decode(path.read_bytes())
def rows(path):return [decode(line) for line in path.read_bytes().splitlines() if line]
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def file_hash(path):return sha256(path.read_bytes()).hexdigest()
def require(value,message):
    if not value:raise ValueError(message)

def distribution(values):
    if not values:return {'n':0,'total':0,'mean':None,'median':None,'p95':None,'minimum':None,'maximum':None}
    ordered=sorted(values);rank=.95*(len(ordered)-1);low=int(rank)
    return dict(n=len(values),total=math.fsum(values),mean=statistics.mean(values),median=statistics.median(values),
                p95=ordered[low]+(ordered[min(low+1,len(ordered)-1)]-ordered[low])*(rank-low),
                minimum=ordered[0],maximum=ordered[-1])

def verify_directory(directory):
    manifest=read(directory/'seal.json')['sha256']
    actual={str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file() and p.name!='seal.json'}
    require(actual==set(manifest),'sealed artifact file set differs')
    for rel,expected in manifest.items():
        require(not Path(rel).is_absolute() and '..' not in Path(rel).parts,'unsafe seal member')
        require(file_hash(directory/rel)==expected,f'sealed hash differs: {rel}')
    return file_hash(directory/'seal.json')

def telemetry_function(freeze,frozen):
    rel='scripts/analyze_complete_system.py';path=freeze/'source'/rel
    require(file_hash(path)==frozen['source_sha256'][rel],'frozen telemetry helper differs')
    syntax=ast.parse(path.read_text())
    function=next(node for node in syntax.body if isinstance(node,ast.FunctionDef) and node.name=='telemetry_metrics')
    scope={'math':math,'nonnegative':lambda x:type(x) in (float,int) and math.isfinite(x) and x>=0,
           'distribution':distribution}
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(path),'exec'),scope)
    return scope['telemetry_metrics']

def integrate_power(samples,intervals):
    """Integrate a linear power trace via cumulative integrals, without extrapolation."""
    if len(samples)<2:return dict(energy_joules=0.0,covered_seconds=0.0)
    timestamps=[s['monotonic_ns'] for s in samples]
    watts=[s['vdd_in']['instant_mw']/1000 for s in samples]
    cumulative=[0.0]
    for i in range(len(timestamps)-1):
        require(timestamps[i+1]>timestamps[i],'nonmonotonic telemetry')
        cumulative.append(cumulative[-1]+(timestamps[i+1]-timestamps[i])/1e9*(watts[i]+watts[i+1])/2)
    def integral(time):
        if time<=timestamps[0]:return 0.0
        if time>=timestamps[-1]:return cumulative[-1]
        i=bisect_right(timestamps,time)-1
        seconds=(time-timestamps[i])/1e9
        slope=(watts[i+1]-watts[i])/((timestamps[i+1]-timestamps[i])/1e9)
        return cumulative[i]+watts[i]*seconds+slope*seconds*seconds/2
    energy=[];covered=[]
    for interval in intervals:
        start=max(interval['started_monotonic_ns'],timestamps[0])
        end=min(interval['finished_monotonic_ns'],timestamps[-1])
        if end>start:energy.append(integral(end)-integral(start));covered.append((end-start)/1e9)
    return dict(energy_joules=math.fsum(energy),covered_seconds=math.fsum(covered))

def verify_http(events):
    calls={};active=None
    for event in events:
        ident=event['call_id']
        if event['event']=='start':
            require(active is None and ident not in calls,'nonserialized or duplicate HTTP call')
            require(sha256(canonical(event['body'])).hexdigest()==event['body_sha256'],'HTTP body hash differs')
            calls[ident]={'start':event,'bytes':bytearray(),'finish':None};active=ident
            continue
        require(ident==active,'orphan HTTP event')
        call=calls[ident]
        require(all(event.get(k)==call['start'].get(k) for k in ('purpose','request_id')),'HTTP call identity differs')
        if event['event']=='chunk':call['bytes'].extend(base64.b64decode(event['bytes_base64'],validate=True))
        elif event['event']=='finish':
            require(bytes(call['bytes']).decode('utf-8',errors='replace')==event['raw_utf8'],'HTTP raw bytes differ')
            require(event['started_monotonic_ns']==call['start']['monotonic_ns'],'HTTP start clock differs')
            require(event['wall_ns']==event['finished_monotonic_ns']-event['started_monotonic_ns']>=0,'HTTP duration differs')
            call['finish']={k:v for k,v in event.items() if k!='event'};active=None
        else:raise ValueError('unexpected HTTP event')
    for call in calls.values():
        call['raw_sha256']=sha256(call.pop('bytes')).hexdigest()
    return calls

def swap_config(text):return [line.split()[:3]+line.split()[4:] for line in text.splitlines()]

def check_host(before,after):
    a,b=before['snapshot'],after['snapshot']
    require(not a['resident_models'] and not b['resident_models'],'host not empty before/after')
    for key in ('boot_id','thermal_trip_events','power_mode'):
        require(a[key]==b[key],f'host {key} changed')
    require(a['memory']['swap_total_kib']==b['memory']['swap_total_kib'],'swap capacity changed')
    require(swap_config(before['swaps'])==swap_config(after['swaps']),'swap device configuration changed')
    require(before['service']==after['service'],'Ollama service configuration changed')
    require(all(type(s.get('fan_pwm')) is int and s['fan_pwm']>0 for s in (a,b)),'fan absent or stopped')
    return dict(boot_unchanged=True,thermal_trip_counters_unchanged=True,power_mode_unchanged=True,
                swap_devices_capacity_priorities_unchanged=True,ollama_service_unchanged=True,
                fan_running=True,start_and_finish_models_empty=True,
                start_memory=a['memory'],finish_memory=b['memory'],power_mode=b['power_mode'])

def numeric_audit(freeze,run):
    freeze_seal=verify_directory(freeze);run_seal=verify_directory(run)
    f=read(freeze/'freeze.json');plan=read(run/'plan.json');finish=read(run/'finish.json')
    require(not plan['diagnostic_only'] and plan['primary_planned']==240,'not a primary capability collection')
    require(plan['schedule']==f['schedule'],'schedule differs')
    require(finish['status']=='complete' and finish['attempts']==finish['finished_attempts']==240,'primary collection incomplete')
    require(finish['verified_source_and_models'] and finish['swap_configuration_unchanged'],'final collector verification failed')
    project=Path(__file__).resolve().parents[1]
    for rel,expected in f['source_sha256'].items():
        require(file_hash(freeze/'source'/rel)==expected,f'frozen source differs: {rel}')
        require(file_hash(project/rel)==expected,f'current source differs: {rel}')
    require(set(f['models'])==set(MODELS),'unexpected model pair')
    require(file_hash(freeze/'dataset.json')==f['dataset_sha256'],'dataset differs')
    dataset=read(freeze/'dataset.json');dataset=dataset['cases'] if isinstance(dataset,dict) else dataset
    lookup={c['request_id']:c for c in dataset}
    prompt_lookup={p['request_id']:p['body_without_model'] for p in read(freeze/'prompts.json')}
    require(len(dataset)==len(lookup)==len(prompt_lookup)==120,'request coverage differs')
    require(Counter(c['category'] for c in dataset)==Counter({c:30 for c in CATEGORIES}),'category balance differs')
    telemetry=telemetry_function(freeze,f)
    observations=[];blocks=[];digests=defaultdict(list)
    for i,schedule in enumerate(f['schedule'],1):
        bd=run/f'{i:02d}_block{schedule["block"]}'
        require(read(bd/'block.json')==schedule,'block schedule differs')
        model=schedule['model'];events=rows(bd/'attempts.jsonl');http=verify_http(rows(bd/'http.jsonl'))
        starts=[e for e in events if e['event']=='attempt_start'];ends=[e for e in events if e['event']=='attempt_finish']
        require([r['request_id'] for r in starts]==schedule['request_ids'],'attempt order differs')
        require([r['request_id'] for r in ends]==schedule['request_ids'],'completion order differs')
        require(len(starts)==len(ends)==20,'block attempt coverage differs')
        require(Counter(c['start']['purpose'] for c in http.values())==Counter(primary=20,load=1,unload=1),'unexpected generator or fallback call')
        require(all(c['finish'] is not None for c in http.values()),'unfinished HTTP call')
        primary={c['start']['request_id']:c for c in http.values() if c['start']['purpose']=='primary'}
        for call in http.values():require(call['start']['body']['model']==model,'wrong model called')
        for purpose in ('load','unload'):
            call=next(c for c in http.values() if c['start']['purpose']==purpose)
            require(read(bd/(purpose+'.json'))==call['finish'],'model lifecycle archive differs')
            require(call['finish']['error'] is None,'model lifecycle transport failed')
            terminal=decode(call['finish']['raw_utf8'].splitlines()[-1])
            require(terminal['model']==model and terminal['done'] is True,'model lifecycle identity/terminal mismatch')
        selected=read(bd/'resident_loaded.json')['models']
        require(len(selected)==1,'multiple loaded models')
        resident=selected[0]
        require(resident['name']==model and resident['digest']==f['models'][model]['digest'] and resident['context_length']==2048,'loaded model identity differs')
        intervals=[]
        for start,end in zip(starts,ends):
            rid=end['request_id'];call=primary[rid];body=call['start']['body'];transport=call['finish']
            require(start['model']==end['model']==model,'attempt model differs')
            no_model={k:v for k,v in body.items() if k!='model'}
            require(no_model==prompt_lookup[rid],'generator input differs from frozen prompt')
            ih=sha256(canonical(no_model)).hexdigest()
            require(start['input_sha256']==end['input_sha256']==ih,'matched input digest differs')
            require(end['transport']==transport,'attempt/HTTP transport differs')
            require(end['total_wall_ns']==end['finished_monotonic_ns']-end['started_monotonic_ns']>=transport['wall_ns'],'total attempt interval differs')
            digests[rid].append(ih);intervals.append(transport)
            for field in ('resident_before','resident_after'):
                rr=end.get(field,[]);require(len(rr)==1,'missing sole residency check')
                require(rr[0]['name']==model and rr[0]['digest']==f['models'][model]['digest'] and rr[0]['context_length']==2048,'attempt residency differs')
            terminal={}
            if transport['error'] is None:
                chunks=[decode(line) for line in transport['raw_utf8'].splitlines() if line]
                require(chunks and chunks[-1].get('done') is True,'missing terminal generation')
                require(all(c.get('model')==model for c in chunks),'returned model identity differs')
                terminal=chunks[-1]
                require(not any(c.get('thinking') for c in chunks),'thinking was enabled')
                require(terminal.get('prompt_eval_count',2049)+192<=2048,'observed context exceeds budget')
                require(terminal.get('eval_count',0)<=192,'observed output exceeds cap')
                if 'stats' in end:require(end['stats']=={k:v for k,v in terminal.items() if k not in {'response','context'}},'stored token/timing stats differ')
                if end['status']=='ok':
                    content=''.join(c.get('response','') for c in chunks)
                    require(end['raw_answer']==content,'raw assistant output differs')
                    require(decode(content)=={'answer':end['answer']},'parsed assistant output differs')
            observations.append(dict(request_id=rid,model=model,category=lookup[rid]['category'],
                status=end['status'],primary_wall_seconds=transport['wall_ns']/1e9,
                attempt_wall_seconds=end['total_wall_ns']/1e9,
                backend={k:terminal[k] for k in ('load_duration','prompt_eval_duration','eval_duration','total_duration','prompt_eval_count','eval_count') if k in terminal},
                raw_http_sha256=call['raw_sha256']))
        require(all(a['finished_monotonic_ns']<=b['started_monotonic_ns'] for a,b in zip(intervals,intervals[1:])),'overlapping primary intervals')
        samples=rows(bd/'telemetry.jsonl');metrics=telemetry(samples,intervals)
        own=integrate_power(samples,intervals)
        require(math.isclose(own['energy_joules'],metrics['request_intervals_energy_joules'],rel_tol=1e-10,abs_tol=1e-7),'independent request energy differs')
        require(math.isclose(own['covered_seconds'],metrics['request_interval_covered_seconds'],abs_tol=1e-7),'energy coverage differs')
        summary=read(bd/'telemetry_summary.json')
        require(summary['sample_count']==len(samples),'telemetry sample count differs')
        require(math.isclose(summary['vdd_in_energy_joules'],metrics['whole_interval_energy_joules'],rel_tol=1e-10),'whole-device energy differs')
        policy=f['device_policy']
        require(all(s['ram']['total_mb']-s['ram']['used_mb']>=policy['min_runtime_available_kib']//1024 for s in samples),'sampled RAM floor crossed')
        require(metrics['peak_swap_used_mb']<=policy['max_runtime_swap_used_kib']//1024,'sampled swap ceiling crossed')
        require(metrics['peak_temperature_c']<policy['max_runtime_temperature_c_exclusive'],'sampled heat ceiling crossed')
        admitted=rows(bd/'admission.jsonl')[-1];last=read(bd/'finish.json')
        for key in ('boot_id','thermal_trip_events','power_mode'):require(admitted[key]==last[key],f'block {key} differs')
        require(not admitted['resident_models'] and not last['resident_models'],'block start/finish residency not empty')
        require(admitted['memory']['mem_available_kib']>=policy['min_start_available_kib'],'startup RAM floor crossed')
        require(admitted['memory']['swap_used_kib']<=policy['max_start_swap_used_kib'],'startup swap ceiling crossed')
        require(max(admitted['temperatures_c'].values())<policy['max_start_temperature_c_exclusive'],'startup heat ceiling crossed')
        load=read(bd/'load.json');unload=read(bd/'unload.json')
        for label,lifecycle in [('loading',load),('unloading',unload)]:
            phase=telemetry(samples,[lifecycle])
            metrics[label+'_covered_energy_joules']=phase['request_intervals_energy_joules']
            metrics[label+'_covered_seconds']=phase['request_interval_covered_seconds']
        metrics['request_coverage_fraction']=metrics['request_interval_covered_seconds']/metrics['request_interval_requested_seconds']
        blocks.append(dict(index=i,block=schedule['block'],model=model,load_wall_seconds=load['wall_ns']/1e9,
            unload_wall_seconds=unload['wall_ns']/1e9,telemetry=metrics,
            gpu_placement=dict(size_bytes=resident['size'],size_vram_bytes=resident['size_vram'],
                allocated_vram_fraction=resident['size_vram']/resident['size'],context_length=resident['context_length']),
            minimum_sampled_free_ram_mb=min(s['ram']['total_mb']-s['ram']['used_mb'] for s in samples),
            largest_telemetry_gap_seconds=max((b['monotonic_ns']-a['monotonic_ns'])/1e9 for a,b in zip(samples,samples[1:])),
            admitted_memory=admitted['memory'],finish_memory=last['memory']))
    require(len(observations)==240 and len({(o['request_id'],o['model']) for o in observations})==240,'primary uniqueness differs')
    require(all(len(v)==2 and len(set(v))==1 for v in digests.values()),'paired prompts differ')
    models={}
    for model in MODELS:
        rr=[o for o in observations if o['model']==model];bb=[b for b in blocks if b['model']==model]
        primary=distribution([o['primary_wall_seconds'] for o in rr]);loading=math.fsum(b['load_wall_seconds'] for b in bb)
        unloading=math.fsum(b['unload_wall_seconds'] for b in bb)
        energy_keys=('whole_interval_energy_joules','request_intervals_energy_joules','request_interval_covered_seconds',
                     'request_interval_requested_seconds','loading_covered_energy_joules','unloading_covered_energy_joules')
        energy={key:math.fsum(b['telemetry'][key] for b in bb) for key in energy_keys}
        energy['request_coverage_fraction']=energy['request_interval_covered_seconds']/energy['request_interval_requested_seconds']
        models[model]=dict(attempts=len(rr),technical_status=dict(Counter(o['status'] for o in rr)),
            primary_latency_seconds=primary,total_attempt_latency_seconds=distribution([o['attempt_wall_seconds'] for o in rr]),
            explicit_load_seconds=loading,explicit_unload_seconds=unloading,
            startup_amortized_mean_seconds=(primary['total']+loading)/len(rr),
            loading_and_cleanup_amortized_mean_seconds=(primary['total']+loading+unloading)/len(rr),
            backend_seconds={field:distribution([o['backend'][field]/1e9 for o in rr if field in o['backend']]) for field in ('load_duration','prompt_eval_duration','eval_duration','total_duration')},
            tokens={field:distribution([o['backend'][field] for o in rr if field in o['backend']]) for field in ('prompt_eval_count','eval_count')},
            energy=energy,peak_ram_used_mb=max(b['telemetry']['peak_ram_used_mb'] for b in bb),
            peak_swap_used_mb=max(b['telemetry']['peak_swap_used_mb'] for b in bb),
            peak_temperature_c=max(b['telemetry']['peak_temperature_c'] for b in bb))
    paired=defaultdict(dict)
    for o in observations:paired[o['request_id']][o['model']]=o['primary_wall_seconds']
    return dict(created_at=datetime.now(timezone.utc).isoformat(),audit_passed=True,attempts=240,
        freeze_seal_sha256=freeze_seal,run_seal_sha256=run_seal,source_copies_and_current_source_verified=True,
        actual_model_identity_and_residency_verified=True,serialized_http_and_identical_paired_inputs_verified=True,
        raw_http_bytes_and_response_metadata_verified=True,
        host=check_host(read(run/'host_start.json'),read(run/'host_finish.json')),
        models=models,blocks=blocks,observations=observations,
        paired_extra_primary_seconds=distribution([v[MODELS[1]]-v[MODELS[0]] for v in paired.values()]),
        energy_scope='Whole-device onboard VDD_IN estimate, including background activity; no idle subtraction. Request energy integrates only covered HTTP intervals; loading/unloading reported separately.',
        quality_review_loaded=False),observations,lookup

def self_test(freeze):
    f=read(freeze/'freeze.json');function=telemetry_function(freeze,f)
    samples=[dict(monotonic_ns=t*10**9,vdd_in={'instant_mw':p*1000},ram={'used_mb':1},swap={'used_mb':0},temperatures_c={'soc':30},gr3d_percent=0) for t,p in [(0,2),(1,4),(2,2)]]
    intervals=[dict(started_monotonic_ns=500_000_000,finished_monotonic_ns=1_500_000_000,wall_ns=10**9)]
    own=integrate_power(samples,intervals);reused=function(samples,intervals)
    require(math.isclose(own['energy_joules'],3.5),'synthetic energy integral wrong')
    require(own['energy_joules']==reused['request_intervals_energy_joules'],'frozen helper cross-check failed')
    require(own['covered_seconds']==1,'synthetic coverage wrong')
    print('PASS: independent integral and frozen telemetry helper agree on clipped triangular power trace; no inference or answers read.')

def write_new(path,value):
    with path.open('xb') as stream:stream.write(canonical(value)+b'\n')

def seal_output(directory):
    write_new(directory/'seal.json',{'sha256':{str(p.relative_to(directory)):file_hash(p) for p in directory.rglob('*') if p.is_file()}})
    for path in directory.rglob('*'):path.chmod(0o500 if path.is_dir() else 0o400)
    directory.chmod(0o500)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',type=Path,required=True);parser.add_argument('--run',type=Path)
    parser.add_argument('--output',type=Path);parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if args.self_test:return self_test(args.freeze)
    require(args.run is not None and args.output is not None,'--run and --output required')
    result,_,_=numeric_audit(args.freeze,args.run)
    os.mkdir(args.output,0o700)
    write_new(args.output/'resource_audit.json',result)
    (args.output/'audit_source.py').write_bytes(Path(__file__).read_bytes())
    write_new(args.output/'provenance.json',dict(freeze=str(args.freeze.resolve()),run=str(args.run.resolve()),
        audit_source_sha256=file_hash(Path(__file__)),separate_postfreeze_numerical_audit=True,answers_not_exported=True))
    seal_output(args.output)
    print(json.dumps({'audit_passed':True,'attempts':result['attempts'],'output':str(args.output)},sort_keys=True))

if __name__=='__main__':main()
