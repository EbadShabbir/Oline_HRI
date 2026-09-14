"""Synthetic audit tests; no live model answers or inference required."""
from copy import deepcopy
import base64
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import analyze_matched_evidence as analyze
import run_matched_evidence as runner


def dump(path,value): path.write_text(json.dumps(value))
def lines(path,rows):path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
def seal(path):
    dump(path/'seal.json',{'sha256':{str(p.relative_to(path)):sha256(p.read_bytes()).hexdigest()
         for p in path.rglob('*') if p.is_file() and p.name!='seal.json'}})
def review(aid,label='complete',**kwargs):
    return dict(answer_id=aid,label=label,unsupported_claim=False,
                unsupported_personal_claim=False,rationale='Synthetic rubric judgment.',**kwargs)
def cases():
    return [dict(request_id=f'q{i}',scenario_id=f's{i}',category=runner.CATEGORIES[i//30],
        evidence_status='answerable',question=f'Question {i}?',evidence=[],history=[],
        rubric={'required':['Answer correctly.'],'reference_answer':'yes'}) for i in range(120)]


class AuditTests(unittest.TestCase):
    def http(self,raw=b'raw bytes',purpose='primary',rid='q0'):
        body=runner.request_body(cases()[0],runner.MODELS[0])
        start=dict(event='start',call_id=1,purpose=purpose,request_id=rid,monotonic_ns=10,
                   body=body,body_sha256=runner.digest(body))
        finish=dict(event='finish',call_id=1,purpose=purpose,request_id=rid,http_status=200,
                    started_monotonic_ns=10,finished_monotonic_ns=30,wall_ns=20,
                    raw_utf8=raw.decode(errors='replace'),error=None)
        return [start,dict(event='chunk',call_id=1,purpose=purpose,request_id=rid,
                monotonic_ns=20,bytes_base64=base64.b64encode(raw).decode()),finish]

    def test_raw_chunks_are_authoritative_and_call_order_is_serial(self):
        events=self.http(b'raw\xff\x00')
        result=analyze.audit_http(events)
        self.assertEqual(result[1]['raw_utf8'],'raw\ufffd\x00')
        variants=[]
        bad=deepcopy(events);bad[-1]['raw_utf8']='rewritten';variants.append(bad)
        bad=deepcopy(events);bad[1]['bytes_base64']='%%%';variants.append(bad)
        bad=deepcopy(events);bad[-1]['wall_ns']=1;variants.append(bad)
        bad=deepcopy(events);bad[0]['body']['model']='other';variants.append(bad)
        variants.extend([events+events,events[1:],events[:1]+events[:1]])
        for bad in variants:
            with self.assertRaises((AssertionError,ValueError)):analyze.audit_http(bad)
        incomplete=analyze.audit_http(events[:-1])
        self.assertIsNone(incomplete[1]['finish'])
        self.assertEqual(incomplete[1]['raw_utf8'],'raw\ufffd\x00')

    def test_review_join_rejects_missing_duplicate_invalid_or_leaking_fields(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'review.jsonl'
            valid=[review('a'),review('b')]
            lines(path,valid);self.assertEqual(set(analyze.review_map(path,{'a','b'})),{'a','b'})
            variants=[valid[:1],[review('a'),review('a')],[review('a'),review('c')],
                      [review('a',label='unknown'),review('b')],
                      [{**review('a'),'model':'small'},review('b')],
                      [{**review('a'),'unsupported_personal_claim':True},review('b')]]
            for invalid in variants:
                lines(path,invalid)
                with self.assertRaises(AssertionError):analyze.review_map(path,{'a','b'})

    def test_packet_identity_bijection_and_exact_immutable_file_set(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)
            packet=[dict(answer_id='anon',question='Question?',evidence=[],rubric={},answer='yes',response_complete=True)]
            lines(path/'packet_a.jsonl',packet);lines(path/'packet_b.jsonl',packet)
            dump(path/'mapping.json',[dict(answer_id='anon',request_id='q0',model=runner.MODELS[0])]);seal(path)
            self.assertEqual(analyze.validate_blind(path)[0],packet)
            (path/'extra.txt').write_text('unsealed')
            with self.assertRaises(AssertionError):analyze.validate_blind(path)
            (path/'extra.txt').unlink()
            lines(path/'packet_b.jsonl',[{**packet[0],'answer':'changed'}]);seal(path)
            with self.assertRaises(AssertionError):analyze.validate_blind(path)
            lines(path/'packet_b.jsonl',packet)
            lines(path/'packet_a.jsonl',[{**packet[0],'model':'hidden leakage'}]);seal(path)
            with self.assertRaises(AssertionError):analyze.validate_blind(path)

    def fixture(self,root):
        frozen=root/'frozen';run=root/'run';frozen.mkdir();run.mkdir()
        source=root/'source_root';(source/'scripts').mkdir(parents=True)
        (source/'scripts/run_matched_evidence.py').write_bytes(b'frozen execution source')
        (frozen/'source/scripts').mkdir(parents=True)
        (frozen/'source/scripts/run_matched_evidence.py').write_bytes(b'frozen execution source')
        cc=cases();schedule=runner.schedule(cc);model=schedule[0]['model'];rid=schedule[0]['request_ids'][0]
        lookup={c['request_id']:c for c in cc};c=lookup[rid]
        dump(frozen/'dataset.json',cc);(frozen/'protocol.md').write_text('protocol')
        prompts=[dict(request_id=c['request_id'],body_without_model={k:v for k,v in runner.request_body(c,model).items() if k!='model'}) for c in cc]
        dump(frozen/'prompts.json',prompts)
        f=dict(source_sha256={'scripts/run_matched_evidence.py':sha256(b'frozen execution source').hexdigest()},
               models={m:{'digest':m+'-digest'} for m in runner.MODELS},options=runner.OPTIONS,schema=runner.SCHEMA,system=runner.SYSTEM,
               dataset_sha256=sha256((frozen/'dataset.json').read_bytes()).hexdigest(),
               protocol_sha256=sha256((frozen/'protocol.md').read_bytes()).hexdigest(),schedule=schedule)
        dump(frozen/'freeze.json',f);dump(run/'plan.json',dict(diagnostic_only=False,schedule=schedule))
        bd=run/'01_block1';bd.mkdir()
        raw=json.dumps(dict(model=model,response='{"answer":"yes"}',done=True,done_reason='stop',prompt_eval_count=100)).encode()+b'\n'
        events=self.http(raw,rid=rid);events[0]['body']=runner.request_body(c,model);events[0]['body_sha256']=runner.digest(events[0]['body'])
        lines(bd/'http.jsonl',events)
        ih=runner.digest({k:v for k,v in events[0]['body'].items() if k!='model'})
        start=dict(event='attempt_start',request_id=rid,model=model,monotonic_ns=1,input_sha256=ih)
        answer,thinking,stats=runner.parse_generation(raw.decode(),model)
        resident=[dict(name=model,digest=model+'-digest',context_length=2048)]
        end=dict(event='attempt_finish',request_id=rid,model=model,input_sha256=ih,status='ok',answer='yes',
            raw_answer=answer,thinking=thinking,stats=stats,transport={k:v for k,v in events[-1].items() if k!='event'},
            resident_before=resident,resident_after=resident,started_monotonic_ns=1,finished_monotonic_ns=40,total_wall_ns=39)
        lines(bd/'attempts.jsonl',[start,end]);seal(frozen);seal(run)
        return frozen,run,source,bd,start,end

    def test_input_audit_recomputes_answer_sources_and_retains_dangling_starts(self):
        with tempfile.TemporaryDirectory() as td:
            frozen,run,source,bd,start,end=self.fixture(Path(td))
            with patch.object(analyze,'ROOT',source):
                f,cc,rows,audit=analyze.inputs(frozen,run)
                self.assertEqual(rows[0]['answer'],'yes');self.assertTrue(audit['raw_http_chunks_verified'])
                lines(bd/'attempts.jsonl',[start,{**end,'answer':'rewritten'}]);seal(run)
                with self.assertRaises(AssertionError):analyze.inputs(frozen,run)
                lines(bd/'attempts.jsonl',[start]);seal(run)
                _,_,rows,_=analyze.inputs(frozen,run)
                self.assertEqual(rows[0]['status'],'interrupted');self.assertTrue(rows[0]['dangling_start'])
                self.assertEqual(rows[0]['transport']['wall_ns'],20)
                (source/'scripts/run_matched_evidence.py').write_text('source drift')
                with self.assertRaises(AssertionError):analyze.inputs(frozen,run)


class MathematicsTests(unittest.TestCase):
    def test_distribution_handles_fractional_percentile_and_empty_costs(self):
        self.assertEqual(analyze.dist([1,3])['p95'],2.9)
        self.assertEqual(analyze.dist([1,2,3])['mean'],2)
        self.assertIsNone(analyze.dist([])['mean'])
        self.assertEqual(analyze.dist([])['n'],0)

    def test_all_paired_cells_denominators_and_loading_costs(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);run=root/'run';run.mkdir();cc=cases();rows=[];mapping=[];packet=[];reviews=[]
            for i,c in enumerate(cc):
                for j,m in enumerate(runner.MODELS):
                    aid=f'{i}-{j}'
                    correct=(i%4==0 or i%4==1 and j==0 or i%4==2 and j==1)
                    status='error' if i%4==3 else 'ok'
                    rows.append(dict(request_id=c['request_id'],model=m,status=status,category=c['category'],
                        evidence_status='answerable',answer='synthetic',transport={'wall_ns':(j+1)*10**9},total_wall_ns=(j+1)*10**9))
                    mapping.append(dict(answer_id=aid,request_id=c['request_id'],model=m));packet.append({'answer_id':aid})
                    reviews.append(review(aid,'technical_failure' if status!='ok' else 'complete' if correct else 'partial'))
            for i,block in enumerate(runner.schedule(cc),1):
                bd=run/f'{i:02d}_block{block["block"]}';bd.mkdir();dump(bd/'block.json',block)
                dump(bd/'load.json',{'wall_ns':2*10**9});dump(bd/'unload.json',{'wall_ns':10**9})
            for name in ('a','b'):lines(root/f'{name}.jsonl',reviews)
            args=SimpleNamespace(freeze=root/'frozen',run=run,blind=root/'blind',review_a=root/'a.jsonl',
                review_b=root/'b.jsonl',adjudication=None,output=root/'analysis')
            with patch.object(analyze,'inputs',return_value=({},cc,rows,{'attempts':240})), \
                 patch.object(analyze,'validate_blind',return_value=(packet,mapping)), \
                 patch.object(analyze,'seal',side_effect=seal),patch('sys.stdout',new=io.StringIO()):
                analyze.analyze(args)
            out=json.loads((args.output/'analysis.json').read_text())
            self.assertEqual(out['pair_counts']['overall'],{'both_correct':30,'only_small_correct':30,'only_large_correct':30,'neither_correct':30})
            for model in runner.MODELS:
                stats=out['models'][model]
                self.assertEqual(stats['attempts'],120);self.assertEqual(stats['correct'],60)
                self.assertEqual(stats['labels']['technical_failure'],30)
                self.assertEqual(stats['explicit_loading_seconds']['total'],12)
            self.assertEqual(out['models'][runner.MODELS[0]]['startup_amortized_mean_seconds'],1.1)
            self.assertEqual(out['models'][runner.MODELS[1]]['loading_and_cleanup_amortized_mean_seconds'],2.15)
            self.assertEqual(out['extra_latency_seconds']['mean'],1)
            self.assertEqual(out['rescue_extra_latency_seconds']['n'],30)
            self.assertEqual(out['quality_difference'],0)
            self.assertEqual(out['human_validation'],'pending')
            self.assertEqual(out['models'][runner.MODELS[0]]['by_category']['routine_general']['attempts'],30)
            self.assertEqual(out['models'][runner.MODELS[0]]['by_category']['routine_general']['unsupported_claims'],0)
            # A killed attempt still counts, while its unknown duration is never
            # silently converted to zero or used in an amortized mean.
            rows[-1]['transport']={};rows[-1].pop('total_wall_ns');args.output=root/'missing_cost'
            with patch.object(analyze,'inputs',return_value=({},cc,rows,{'attempts':240})), \
                 patch.object(analyze,'validate_blind',return_value=(packet,mapping)), \
                 patch.object(analyze,'seal',side_effect=seal),patch('sys.stdout',new=io.StringIO()):
                analyze.analyze(args)
            out=json.loads((args.output/'analysis.json').read_text())
            self.assertEqual(out['models'][runner.MODELS[1]]['attempts'],120)
            self.assertEqual(out['models'][runner.MODELS[1]]['missing_request_latency_count'],1)
            self.assertIsNone(out['models'][runner.MODELS[1]]['startup_amortized_mean_seconds'])
            self.assertEqual(out['extra_latency_seconds']['n'],119)


if __name__=='__main__':unittest.main()
