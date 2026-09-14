"""Audit, blind, and report the frozen matched-evidence component experiment."""
from __future__ import annotations
import argparse
import base64
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import random
import statistics
import uuid
from datetime import datetime, timezone
from run_matched_evidence import (MODELS,CATEGORIES,ROOT,OPTIONS,SCHEMA,SYSTEM,
    canonical,digest,request_body,seal,verify_seal,write,parse_generation,strict_answer)
from oline_hri.evaluation_model_pairs import _new_private_directory

SUCCESS={'complete','appropriate_abstention','appropriate_uncertainty'}
LABELS=SUCCESS|{'partial','incorrect','inappropriate_abstention','technical_failure'}

def jsonl(path): return [json.loads(s) for s in path.read_text().splitlines() if s]

def dist(x):
    if not x:return dict(n=0,mean=None,median=None,p95=None,total=0)
    y=sorted(x);p=(len(y)-1)*.95;i=int(p)
    return dict(n=len(x),mean=statistics.mean(x),median=statistics.median(x),
                p95=y[i]+(y[min(i+1,len(y)-1)]-y[i])*(p-i),total=sum(x))

def verify_artifact(directory):
    """Require the seal to cover exactly the files consumed by analysis."""
    verify_seal(directory)
    sealed=json.loads((directory/'seal.json').read_text())['sha256']
    actual={str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file() and p.name!='seal.json'}
    assert set(sealed)==actual,'seal does not cover exact artifact file set'
    for name in sealed:
        assert not Path(name).is_absolute() and '..' not in Path(name).parts,'unsafe seal path'

def audit_http(events):
    """Reconstruct every response from durable byte chunks before trusting rows."""
    calls={};active=None
    for event in events:
        ident=event['call_id'];kind=event['event']
        if kind=='start':
            assert ident not in calls and active is None,'duplicate or concurrent HTTP call'
            assert event['purpose'] in {'load','primary','unload'},'unexpected inference path'
            assert event['body_sha256']==digest(event['body']),'HTTP request digest mismatch'
            calls[ident]={'start':event,'chunks':bytearray(),'finish':None};active=ident
        else:
            assert ident==active and ident in calls,'orphan or out-of-order HTTP event'
            call=calls[ident];start=call['start']
            assert all(event.get(k)==start.get(k) for k in ('purpose','request_id')),'HTTP identity changed'
            if kind=='chunk':
                assert event['monotonic_ns']>=start['monotonic_ns']
                call['chunks'].extend(base64.b64decode(event['bytes_base64'],validate=True))
            elif kind=='finish':
                assert event['started_monotonic_ns']==start['monotonic_ns']
                assert event['finished_monotonic_ns']>=start['monotonic_ns']
                assert event['wall_ns']==event['finished_monotonic_ns']-event['started_monotonic_ns']
                assert event['raw_utf8']==bytes(call['chunks']).decode('utf-8',errors='replace'),'raw chunk/finish mismatch'
                call['finish']={k:v for k,v in event.items() if k!='event'};active=None
            else:raise ValueError('unknown HTTP event')
    for call in calls.values():
        call['raw_utf8']=bytes(call.pop('chunks')).decode('utf-8',errors='replace')
    return calls

def answer_for_review(row):
    answer=row.get('answer')
    if answer is not None:return answer
    if row.get('raw_answer'):return row['raw_answer']
    raw=row.get('transport',{}).get('raw_utf8','')
    try:return ''.join(json.loads(line).get('response','') for line in raw.splitlines())
    except (ValueError,TypeError,AttributeError):return raw

def validate_blind(directory, rows=None, cases=None):
    verify_artifact(directory)
    a=jsonl(directory/'packet_a.jsonl');b=jsonl(directory/'packet_b.jsonl')
    allowed={'answer_id','question','evidence','rubric','answer','response_complete'}
    assert all(set(r)==allowed for r in a+b),'blind packet has forbidden or missing fields'
    def index(packet):
        assert len({r['answer_id'] for r in packet})==len(packet),'duplicate blind answer ID'
        return {r['answer_id']:r for r in packet}
    ai,bi=index(a),index(b)
    assert ai==bi,'reviewers received different answer sets'
    mapping=json.loads((directory/'mapping.json').read_text())
    assert len(mapping)==len(a) and {m['answer_id'] for m in mapping}==set(ai)
    assert len({(m['request_id'],m['model']) for m in mapping})==len(mapping),'mapping is not one-to-one'
    assert all(set(m)=={'answer_id','request_id','model'} and m['model'] in MODELS for m in mapping)
    if rows is not None:
        bykey={(r['request_id'],r['model']):r for r in rows};lookup={c['request_id']:c for c in cases}
        assert {(m['request_id'],m['model']) for m in mapping}==set(bykey),'blind mapping does not cover attempts'
        for m in mapping:
            r=bykey[m['request_id'],m['model']];c=lookup[m['request_id']]
            expected=dict(answer_id=m['answer_id'],question=c['question'],evidence=c['evidence'],rubric=c['rubric'],
                          answer=answer_for_review(r),response_complete=r['status']=='ok')
            assert ai[m['answer_id']]==expected,'blind packet differs from raw answer or rubric'
    return a,mapping

def inputs(frozen,run):
    verify_artifact(frozen);verify_artifact(run)
    f=json.loads((frozen/'freeze.json').read_text())
    for rel,expected in f['source_sha256'].items():
        assert sha256((frozen/'source'/rel).read_bytes()).hexdigest()==expected,'frozen source copy mismatch'
        assert sha256((ROOT/rel).read_bytes()).hexdigest()==expected,'analysis execution source differs from freeze'
    assert set(f['models'])==set(MODELS)
    assert (f['options'],f['schema'],f['system'])==(OPTIONS,SCHEMA,SYSTEM)
    assert sha256((frozen/'dataset.json').read_bytes()).hexdigest()==f['dataset_sha256']
    assert sha256((frozen/'protocol.md').read_bytes()).hexdigest()==f['protocol_sha256']
    cases=json.loads((frozen/'dataset.json').read_text())
    if isinstance(cases,dict):cases=cases['cases']
    lookup={c['request_id']:c for c in cases}
    assert len(lookup)==len(cases)==120
    prompts=json.loads((frozen/'prompts.json').read_text())
    assert len(prompts)==120 and len({p['request_id'] for p in prompts})==120
    for prompt in prompts:
        assert prompt['body_without_model']=={k:v for k,v in request_body(lookup[prompt['request_id']],MODELS[0]).items() if k!='model'}
    plan=json.loads((run/'plan.json').read_text())
    assert plan['diagnostic_only'] is False and plan['schedule']==f['schedule']
    rows=[];audit=[]
    for i,block in enumerate(f['schedule'],1):
        bd=run/f'{i:02d}_block{block["block"]}'
        if not bd.exists():continue
        events=jsonl(bd/'attempts.jsonl') if (bd/'attempts.jsonl').exists() else []
        assert all(e['event'] in {'attempt_start','attempt_finish'} for e in events)
        starts=[e for e in events if e['event']=='attempt_start']
        ends=[e for e in events if e['event']=='attempt_finish']
        assert [e['request_id'] for e in starts]==block['request_ids'][:len(starts)]
        assert all(e['model']==block['model'] for e in starts)
        assert len({e['request_id'] for e in ends})==len(ends),'duplicate attempt finish'
        assert {e['request_id'] for e in ends}<={e['request_id'] for e in starts},'orphan attempt finish'
        http=jsonl(bd/'http.jsonl') if (bd/'http.jsonl').exists() else []
        http_calls=audit_http(http)
        calls=[c['start'] for c in http_calls.values() if c['start']['purpose']=='primary']
        assert len(calls)<=len(starts)
        assert [c['request_id'] for c in calls]==[s['request_id'] for s in starts][:len(calls)]
        for call in http_calls.values():
            assert call['start']['body']['model']==block['model'],'other-model HTTP request'
            if call['start']['purpose'] in {'load','unload'}:
                side=bd/(call['start']['purpose']+'.json')
                if side.exists():assert json.loads(side.read_text())==call['finish'],'load/unload transport mismatch'
        for event in calls:
            c=lookup[event['request_id']]
            assert event['body']==request_body(c,block['model'])
            assert event['body_sha256']==digest(event['body'])
        emap={e['request_id']:e for e in ends}
        cmap={c['start']['request_id']:c for c in http_calls.values() if c['start']['purpose']=='primary'}
        for s in starts:
            rid=s['request_id'];c=lookup[rid]
            body=request_body(c,block['model']);expected=digest({k:v for k,v in body.items() if k!='model'})
            assert s['input_sha256']==expected
            r=emap.get(rid)
            call=cmap.get(rid)
            if r is None:
                transport={} if call is None else (call['finish'] or {'raw_utf8':call['raw_utf8']})
                r=dict(event='attempt_finish',request_id=rid,model=block['model'],status='interrupted',answer=None,input_sha256=expected,transport=transport,raw_answer='',dangling_start=True)
            else:
                assert r['input_sha256']==expected and r['model']==block['model']
                assert call is not None and call['finish'] is not None,'completed attempt lacks completed transport'
                assert r['transport']==call['finish'],'attempt transport differs from HTTP archive'
                assert r['status'] in {'ok','error','truncated','interrupted'}
                assert r['total_wall_ns']==r['finished_monotonic_ns']-r['started_monotonic_ns']>=0
                assert r['started_monotonic_ns']==s['monotonic_ns']
                if not r['transport']['error']:
                    try:raw,thinking,stats=parse_generation(r['transport']['raw_utf8'],block['model'])
                    except Exception:assert r['status'] in {'error','interrupted'}
                    else:
                        if 'raw_answer' in r:assert r['raw_answer']==raw
                        if 'thinking' in r:assert r['thinking']==thinking
                        if 'stats' in r:assert r['stats']==stats
                if r['status']=='ok':
                    assert not r['transport']['error'] and r['transport']['http_status']==200
                    assert r['answer']==strict_answer(raw)['answer'],'recorded answer differs from raw generation'
                    assert r['stats']['model']==block['model'] and not r['thinking']
                    assert r['stats']['prompt_eval_count']+192<=2048
                    assert r['stats']['done_reason']!='length'
                    assert 'resident_before' in r and 'resident_after' in r
                for field in ('resident_before','resident_after'):
                    if field in r:
                        assert len(r[field])==1
                        resident=r[field][0]
                        assert resident['name']==block['model'] and resident['digest']==f['models'][block['model']]['digest'] and resident['context_length']==2048
            rows.append({**r,'block_path':str(bd),'block':block['block'],'category':c['category'],'evidence_status':c['evidence_status']})
        audit.append({'block':block,'starts':len(starts),'finishes':len(ends),'actual_http_primary_calls':len(calls)})
    assert len({(r['request_id'],r['model']) for r in rows})==len(rows)
    paired=defaultdict(list)
    for r in rows:paired[r['request_id']].append(r['input_sha256'])
    assert all(len(set(v))==1 for v in paired.values())
    return f,cases,rows,{'attempts':len(rows),'planned':240,'completed_pairs':sum(len(v)==2 for v in paired.values()),'identical_paired_inputs':True,'raw_http_chunks_verified':True,'frozen_source_verified':True,'blocks':audit}

def blind(args):
    f,cases,rows,audit=inputs(args.freeze,args.run)
    assert len(rows)==240,'complete primary collection required for this export'
    d=_new_private_directory(args.output.absolute());lookup={c['request_id']:c for c in cases}
    packet=[];mapping=[]
    for r in rows:
        aid=uuid.uuid4().hex;c=lookup[r['request_id']]
        answer=answer_for_review(r)
        packet.append(dict(answer_id=aid,question=c['question'],evidence=c['evidence'],rubric=c['rubric'],
                           answer=answer,response_complete=r['status']=='ok'))
        mapping.append(dict(answer_id=aid,request_id=r['request_id'],model=r['model']))
    for who in ('a','b'):
        ordered=packet.copy();random.SystemRandom().shuffle(ordered)
        with (d/f'packet_{who}.jsonl').open('x') as stream:
            for r in ordered:stream.write(canonical(r).decode()+'\n')
    write(d/'mapping.json',mapping);write(d/'input_audit.json',audit)
    write(d/'provenance.json',{'created_at':datetime.now(timezone.utc).isoformat(),
          'freeze':str(args.freeze.resolve()),'run':str(args.run.resolve()),
          'blinding':'random UUID IDs, independently shuffled complete rows, no model/timing/block/mapping supplied to reviewers; procedural shared-filesystem isolation',
          'human_validation':'pending'})
    seal(d);print(d)

def review_map(path,ids):
    rows=jsonl(path);assert len(rows)==len(ids)
    assert {r['answer_id'] for r in rows}==ids
    for r in rows:
        assert set(r)=={'answer_id','label','unsupported_claim','unsupported_personal_claim','rationale'},'unexpected review fields'
        assert r['label'] in LABELS and type(r['unsupported_claim']) is bool and type(r['unsupported_personal_claim']) is bool
        assert isinstance(r['rationale'],str) and r['rationale']
        assert not r['unsupported_personal_claim'] or r['unsupported_claim'],'personal unsupported claim must also count as unsupported'
    return {r['answer_id']:r for r in rows}

def disagreement(args):
    packet,_=validate_blind(args.blind);ids={r['answer_id'] for r in packet}
    a=review_map(args.review_a,ids);b=review_map(args.review_b,ids)
    key=lambda r:(r['label'],r['unsupported_claim'],r['unsupported_personal_claim'])
    out=[]
    for r in packet:
        aid=r['answer_id']
        if key(a[aid])!=key(b[aid]):
            out.append({**r,'review_a':a[aid],'review_b':b[aid]})
    d=_new_private_directory(args.output.absolute())
    with (d/'disagreements.jsonl').open('x') as s:
        for r in out:s.write(canonical(r).decode()+'\n')
    write(d/'agreement.json',{'total':len(ids),'exact_agreements':len(ids)-len(out),'disagreements':len(out),
          'review_a_sha256':sha256(args.review_a.read_bytes()).hexdigest(),'review_b_sha256':sha256(args.review_b.read_bytes()).hexdigest(),
          'created_at':datetime.now(timezone.utc).isoformat(),'human_validation':'pending'})
    seal(d);print(len(out))

def resource_summary(bd):
    ts=json.loads((bd/'telemetry_summary.json').read_text()) if (bd/'telemetry_summary.json').exists() else {}
    samples=jsonl(bd/'telemetry.jsonl') if (bd/'telemetry.jsonl').exists() else []
    return {'summary':ts,'samples':samples}

def analyze(args):
    f,cases,rows,audit=inputs(args.freeze,args.run)
    assert len(rows)==240
    packet,mapping=validate_blind(args.blind,rows,cases);ids={r['answer_id'] for r in packet}
    a=review_map(args.review_a,ids);b=review_map(args.review_b,ids)
    key=lambda r:(r['label'],r['unsupported_claim'],r['unsupported_personal_claim'])
    disputed={aid for aid in ids if key(a[aid])!=key(b[aid])}
    assert not disputed or args.adjudication is not None,'adjudication required for disagreements'
    adj=review_map(args.adjudication,disputed) if disputed else {}
    resolved={aid:adj[aid] if aid in disputed else a[aid] for aid in ids}
    bykey={(r['request_id'],r['model']):r for r in rows}
    for m in mapping:
        r=bykey[m['request_id'],m['model']];judgment=resolved[m['answer_id']]
        r['review']=judgment;r['answer_id']=m['answer_id']
        r['correct']=r['status']=='ok' and judgment['label'] in SUCCESS
        assert r['status']=='ok' or judgment['label']=='technical_failure'
    lookup={c['request_id']:c for c in cases}
    pairs=[]
    for c in cases:
        s,l=(bykey[c['request_id'],m] for m in MODELS)
        outcome=('both_correct' if s['correct'] and l['correct'] else 'only_small_correct' if s['correct'] else 'only_large_correct' if l['correct'] else 'neither_correct')
        pairs.append(dict(request_id=c['request_id'],category=c['category'],evidence_status=c['evidence_status'],outcome=outcome,
                          large_minus_small_seconds=(l['transport']['wall_ns']-s['transport']['wall_ns'])/1e9
                          if all('wall_ns' in r['transport'] for r in (s,l)) else None))
    counts=lambda p:{k:sum(x['outcome']==k for x in p) for k in ('both_correct','only_small_correct','only_large_correct','neither_correct')}
    pc={'overall':counts(pairs),**{cat:counts([p for p in pairs if p['category']==cat]) for cat in CATEGORIES}}
    # Resample whole authored scenarios within each fixed equal-size category.
    rng=random.Random(42121);deltas=[]
    groups=[[int(bykey[c['request_id'],MODELS[1]]['correct'])-int(bykey[c['request_id'],MODELS[0]]['correct']) for c in cases if c['category']==cat] for cat in CATEGORIES]
    for _ in range(10000):deltas.append(sum(rng.choice(g) for g in groups for _ in g)/120)
    deltas.sort()
    model_stats={}
    block_stats=[]
    for m in MODELS:
        rr=[r for r in rows if r['model']==m]
        bs=[]
        for bd in sorted(args.run.glob('*_block*')):
            if not (bd/'block.json').exists():continue
            block=json.loads((bd/'block.json').read_text())
            if block['model']!=m:continue
            load=json.loads((bd/'load.json').read_text()) if (bd/'load.json').exists() else {}
            unload=json.loads((bd/'unload.json').read_text()) if (bd/'unload.json').exists() else {}
            res=resource_summary(bd)
            bs.append({'model':m,'block':block['block'],'load_wall_seconds':load['wall_ns']/1e9 if 'wall_ns' in load else None,
                       'unload_wall_seconds':unload['wall_ns']/1e9 if 'wall_ns' in unload else None,'resources':res['summary'],
                       'resident':json.loads((bd/'resident_loaded.json').read_text())['models'][0] if (bd/'resident_loaded.json').exists() else None})
        block_stats+=bs
        totals={field:dist([r['stats'][field]/1e9 for r in rr if 'stats' in r and field in r['stats']]) for field in ('load_duration','prompt_eval_duration','eval_duration','total_duration')}
        latency=dist([r['transport']['wall_ns']/1e9 for r in rr if 'wall_ns' in r['transport']])
        load_costs=[z['load_wall_seconds'] for z in bs if z['load_wall_seconds'] is not None]
        unload_costs=[z['unload_wall_seconds'] for z in bs if z['unload_wall_seconds'] is not None]
        loading=sum(load_costs);unloading=sum(unload_costs)
        complete_costs=latency['n']==len(rr) and len(load_costs)==6
        model_stats[m]=dict(correct=sum(r['correct'] for r in rr),attempts=len(rr),labels=dict(Counter(r['review']['label'] for r in rr)),
             unsupported_claims=sum(r['review']['unsupported_claim'] for r in rr),unsupported_personal_claims=sum(r['review']['unsupported_personal_claim'] for r in rr),
             technical_status=dict(Counter(r['status'] for r in rr)),latency_seconds=latency,
             total_attempt_seconds=dist([r['total_wall_ns']/1e9 for r in rr if 'total_wall_ns' in r]),backend_seconds=totals,
             explicit_loading_seconds=dist(load_costs),explicit_unloading_seconds=unloading,
             measured_unload_count=len(unload_costs),missing_request_latency_count=len(rr)-latency['n'],
             startup_amortized_mean_seconds=(latency['total']+loading)/len(rr) if complete_costs else None,
             loading_and_cleanup_amortized_mean_seconds=(latency['total']+loading+unloading)/len(rr) if complete_costs and len(unload_costs)==6 else None,
             by_category={cat:dict(attempts=sum(r['category']==cat for r in rr),
                 correct=sum(r['correct'] for r in rr if r['category']==cat),
                 latency_seconds=dist([r['transport']['wall_ns']/1e9 for r in rr if r['category']==cat and 'wall_ns' in r['transport']]),
                 labels=dict(Counter(r['review']['label'] for r in rr if r['category']==cat)),
                 unsupported_claims=sum(r['review']['unsupported_claim'] for r in rr if r['category']==cat),
                 unsupported_personal_claims=sum(r['review']['unsupported_personal_claim'] for r in rr if r['category']==cat),
                 technical_status=dict(Counter(r['status'] for r in rr if r['category']==cat))) for cat in CATEGORIES},
             by_evidence_status={status:dict(correct=sum(r['correct'] for r in rr if r['evidence_status']==status),attempts=sum(r['evidence_status']==status for r in rr)) for status in ('answerable','unknown','conflicting')})
    result=dict(audit=audit,pair_counts=pc,models=model_stats,blocks=block_stats,pairs=pairs,
          quality_difference=(model_stats[MODELS[1]]['correct']-model_stats[MODELS[0]]['correct'])/120,
          quality_difference_stratified_bootstrap_95=[deltas[249],deltas[9749]],
          extra_latency_seconds=dist([p['large_minus_small_seconds'] for p in pairs if p['large_minus_small_seconds'] is not None]),
          rescue_extra_latency_seconds=dist([p['large_minus_small_seconds'] for p in pairs if p['outcome']=='only_large_correct' and p['large_minus_small_seconds'] is not None]),
          rescue_evidence_status=dict(Counter(p['evidence_status'] for p in pairs if p['outcome']=='only_large_correct')),
          review_agreement=dict(total=240,exact_agreement=240-len(disputed),adjudicated=len(disputed)),
          human_validation='pending',scope='assistant-reviewed matched-evidence direct generator capability only')
    d=_new_private_directory(args.output.absolute());write(d/'analysis.json',result);write(d/'resolved_reviews.json',resolved)
    with (d/'scored_answers.jsonl').open('x') as s:
        for r in rows:s.write(canonical(r).decode()+'\n')
    lines=['# Matched-evidence paired generator results','',f'240 primary attempts; two independent blinded assistant reviews, {len(disputed)} adjudications. Independent human validation pending.','',
           '| Category | Both correct | Only small | Only large | Neither |','| --- | ---: | ---: | ---: | ---: |']
    for cat,v in pc.items():lines.append('| '+cat+' | '+' | '.join(str(z) for z in v.values())+' |')
    lines+=['','| Model | Correct / 120 | Mean s | Median s | p95 s | Preloading total s | Startup-amortized mean s |','| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for m,z in model_stats.items():
        fmt=lambda value:'unavailable' if value is None else f'{value:.3f}'
        t=z['latency_seconds'];lines.append(f'| {m} | {z["correct"]} | {fmt(t["mean"])} | {fmt(t["median"])} | {fmt(t["p95"])} | {z["explicit_loading_seconds"]["total"]:.3f} | {fmt(z["startup_amortized_mean_seconds"])} |')
    lines+=['','## All paired answers','']
    for p in sorted(pairs,key=lambda x:(x['outcome'],x['request_id'])):
        c=lookup[p['request_id']];lines += [f'### {p["request_id"]}: {p["outcome"]}','',c['question'],'','Evidence: '+json.dumps(c['evidence'],ensure_ascii=False),'']
        for m in MODELS:
            r=bykey[p['request_id'],m];lines += [f'**{m} — {r["review"]["label"]}**', '',r.get('answer') or r.get('raw_answer') or '[No complete answer]','',r['review']['rationale'],'']
    (d/'tables_and_answers.md').write_text('\n'.join(lines))
    write(d/'provenance.json',dict(freeze=str(args.freeze),run=str(args.run),blind=str(args.blind),
          review_a_sha256=sha256(args.review_a.read_bytes()).hexdigest(),review_b_sha256=sha256(args.review_b.read_bytes()).hexdigest(),
          adjudication_sha256=sha256(args.adjudication.read_bytes()).hexdigest() if args.adjudication else None,
          analyzer_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),created_at=datetime.now(timezone.utc).isoformat()))
    seal(d);print(json.dumps({k:v for k,v in result.items() if k in ('pair_counts','quality_difference','quality_difference_stratified_bootstrap_95','extra_latency_seconds','rescue_evidence_status','review_agreement')},indent=2))

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    for name in ('blind','disagreements','analyze'):
        q=sub.add_parser(name);q.add_argument('--output',type=Path,required=True)
        if name!='disagreements':
            q.add_argument('--freeze',type=Path,required=True);q.add_argument('--run',type=Path,required=True)
        if name!='blind':
            q.add_argument('--blind',type=Path,required=True);q.add_argument('--review-a',type=Path,required=True);q.add_argument('--review-b',type=Path,required=True)
        if name=='analyze':q.add_argument('--adjudication',type=Path)
    args=p.parse_args();return {'blind':blind,'disagreements':disagreement,'analyze':analyze}[args.command](args)
if __name__=='__main__':main()
