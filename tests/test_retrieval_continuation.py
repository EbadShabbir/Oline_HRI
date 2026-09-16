"""Prospective structural checks for suffix-only continuation orchestration."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import independent_retrieval_continuation as continuation


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.freeze=self.root/'freeze';self.freeze.mkdir()
        self.cases=[{'id':f'q{i:02d}','prompt':f'Fictional request {i}'} for i in range(48)]
        self.schedule=[dict(slot=i,repetition=(i-1)//6+1,model=('small' if (i-1)%6<3 else 'large'),
            policy=('OFF','ALWAYS','SELECTIVE')[(i-1)%3],request_ids=[c['id'] for c in self.cases]) for i in range(1,19)]
        self.frozen=dict(schedule=self.schedule,config={'ollama':dict(small_model='small',general_large_model='large',large_model='large',request_timeout_seconds=10,large_request_timeout_seconds=20)},device_policy={'guard':'unchanged'})
        continuation.write(self.freeze/'freeze.json',self.frozen)
        continuation.write(self.freeze/'runtime.json',{'execution_cases':self.cases})
        (self.freeze/'prepared_snapshot').mkdir();(self.freeze/'prepared_snapshot/memory.sqlite3').write_bytes(b'fixed snapshot')
        self.snapshot_hash=continuation.digest(self.freeze/'prepared_snapshot/memory.sqlite3')
        self.state=dict(boot_id='same',thermal_trip_events={'cpu':0},power_mode='same',memory={'swap_total_kib':1},resident_models=[])
        self.counter=0

    def fragment(self,slot_number,count,mutate=None):
        self.counter+=1;directory=self.root/f'fragment_{self.counter:02d}';directory.mkdir()
        slot=self.schedule[slot_number-1]
        manifest=dict(slot=slot,freeze_sha256=continuation.digest(self.freeze/'freeze.json'),config=continuation.expected_config(self.frozen,slot['model']),device_policy=self.frozen['device_policy'])
        rows=[]
        for index,case in enumerate(self.cases[:count],1):
            start=(slot_number*100+index)*10
            rows.append(dict(case=case,**{k:v for k,v in slot.items() if k!='request_ids'},index=index,
                status='interrupted' if count<48 and index==count else 'ok',started_monotonic_ns=start,finished_monotonic_ns=start+1,wall_ns=1))
        values={'manifest.json':manifest,'summary.json':dict(attempted=count,planned=48,status='complete' if count==48 else 'interrupted',cleanup_errors=[]),
            'start.json':deepcopy(self.state),'finish.json':deepcopy(self.state),
            'snapshot_verification.json':dict(unchanged=True,before=self.snapshot_hash,after=self.snapshot_hash),
            'setup.json':dict(snapshot_sha256=self.snapshot_hash),
            'observations.jsonl':rows,'events.jsonl':[dict(event='request_start',request_id=r['case']['id']) for r in rows]}
        if mutate:mutate(values)
        for name,value in values.items():
            if name.endswith('jsonl'):
                (directory/name).write_text(''.join(json.dumps(r)+'\n' for r in value))
            else:continuation.write(directory/name,value)
        (directory/'memory.sqlite3').write_bytes(b'fixed snapshot')
        continuation.seal(directory)
        return dict(slot=slot_number,directory=str(directory),exit_code=0 if count==48 else 1)

    def prefix(self,mutate=None):
        return [self.fragment(i,48) for i in range(1,4)]+[self.fragment(4,13,mutate)]

    def test_frozen157_prefix_yields_exact707_remaining(self):
        result=continuation.history(self.freeze,self.prefix())
        self.assertEqual((result['attempted'],result['remaining']),(157,707))
        self.assertEqual(result['offsets'][4],13)
        self.assertEqual(self.schedule[3]['request_ids'][13],'q13')
        self.assertEqual(sum(48-result['offsets'][slot['slot']] for slot in self.schedule),707)
        self.assertEqual(result['prior_attempts'][-1]['status'],'interrupted')

    def test_rejects_duplicated_skipped_and_out_of_order_fragments(self):
        entries=self.prefix()
        for candidate in (entries+[entries[-1]],entries[1:],list(reversed(entries))):
            with self.subTest(candidate=[e['slot'] for e in candidate]),self.assertRaises(ValueError):
                continuation.history(self.freeze,candidate)

    def test_rejects_missing_terminal_observation_and_changed_question(self):
        for mutate in (
            lambda d:d['events.jsonl'].append(dict(event='request_start',request_id='q13')),
            lambda d:d['observations.jsonl'][-1].update(case=dict(id='q12',prompt='changed')),
            lambda d:d['summary.json'].update(attempted=12),
            lambda d:d['observations.jsonl'][-1].update(index=1),
        ):
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):
                continuation.history(self.freeze,self.prefix(mutate))

    def test_rejects_configuration_snapshot_and_baseline_drift(self):
        mutations=(
            lambda d:d['manifest.json']['config']['ollama'].update(small_model='different'),
            lambda d:d['manifest.json'].update(freeze_sha256='changed'),
            lambda d:d['snapshot_verification.json'].update(after='changed'),
            lambda d:d['setup.json'].update(snapshot_sha256='changed'),
            lambda d:d['finish.json'].update(boot_id='different'),
            lambda d:d['finish.json'].update(resident_models=[{'name':'large'}]),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):
                continuation.history(self.freeze,self.prefix(mutate))

    def test_rejects_overlap_negative_time_and_postfatal_execution(self):
        for mutate in (
            lambda d:d['observations.jsonl'][0].update(started_monotonic_ns=1,finished_monotonic_ns=2),
            lambda d:d['observations.jsonl'][-1].update(wall_ns=-1),
            lambda d:d['observations.jsonl'][0].update(status='interrupted'),
        ):
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):
                continuation.history(self.freeze,self.prefix(mutate))

    def ledger_fixture(self,mutate=None):
        entries=self.prefix();audited=continuation.history(self.freeze,entries)
        plan=dict(**{k:v for k,v in audited.items() if k!='offsets'},freeze_sha256=continuation.digest(self.freeze/'freeze.json'),authorized_run_directory=str(self.root/'run'))
        cont=self.root/f'continuation_{self.counter}';cont.mkdir();continuation.write(cont/'continuation.json',{'dummy':'hash target'})
        run=self.root/'run';run.mkdir(exist_ok=True);ledger_dir=run/'ledger_04_13_admission_00';ledger_dir.mkdir()
        ledger=dict(continuation_sha256=continuation.digest(cont/'continuation.json'),freeze_sha256=plan['freeze_sha256'],slot=4,offset=13,
            request_ids=self.schedule[3]['request_ids'][13:],prior_sessions=audited['prior_sessions'],prior_attempts=audited['prior_attempts'],baseline=plan['baseline'],
            admission_index=0,admission_rejections=[],authorized_worker_directory=str(continuation.fragment_path(run,4,13,0)))
        if mutate:mutate(ledger)
        continuation.write(ledger_dir/'ledger.json',ledger);continuation.seal(ledger_dir)
        return plan,cont,ledger_dir

    def test_ledger_authorizes_only_next_exact_suffix(self):
        plan,cont,ledger=self.ledger_fixture()
        with patch.object(continuation,'verify_continuation',return_value=plan):
            actual=continuation.verify_ledger(self.freeze,cont,ledger,4,13)
            self.assertEqual(len(actual['request_ids']),35)
            for slot,offset in ((4,12),(4,14),(5,0)):
                with self.assertRaises(ValueError):continuation.verify_ledger(self.freeze,cont,ledger,slot,offset)

    def test_ledger_rejects_replayed_fatal_request(self):
        plan,cont,ledger=self.ledger_fixture(lambda d:d.update(offset=12,request_ids=self.schedule[3]['request_ids'][12:]))
        with patch.object(continuation,'verify_continuation',return_value=plan),self.assertRaises(ValueError):
            continuation.verify_ledger(self.freeze,cont,ledger,4,12)

    def test_ledger_rejects_output_rebinding(self):
        plan,cont,ledger=self.ledger_fixture(lambda d:d.update(authorized_worker_directory=str(self.root/'another_worker')))
        with patch.object(continuation,'verify_continuation',return_value=plan),self.assertRaises(ValueError):
            continuation.verify_ledger(self.freeze,cont,ledger,4,13)

    def test_ledger_requires_admission_retry_proof(self):
        plan,cont,ledger=self.ledger_fixture(lambda d:d.update(admission_index=1))
        with patch.object(continuation,'verify_continuation',return_value=plan),self.assertRaises(ValueError):
            continuation.verify_ledger(self.freeze,cont,ledger,4,13)

    def test_same_plan_cannot_rebind_or_recreate_collection_output(self):
        target=self.root/'only_authorized_run'
        plan={'authorized_run_directory':str(target)}
        args=SimpleNamespace(freeze=self.freeze,continuation=self.root,output=self.root/'other')
        with patch.object(continuation,'verify_continuation',return_value=plan):
            with self.assertRaises(ValueError):continuation._collect(args)
            target.mkdir();args.output=target
            with self.assertRaises(FileExistsError):continuation._collect(args)

    def test_continuation_chain_preserves_prefix_and_rejects_cycles(self):
        entries=self.prefix();first=self.root/'first';second=self.root/'second'
        for directory,prior,records in ((first,None,entries[:3]),(second,str(first),entries)):
            directory.mkdir()
            continuation.write(directory/'plan.json',dict(freeze_sha256=continuation.digest(self.freeze/'freeze.json'),schedule=self.schedule,continuation_from=prior))
            continuation.write(directory/'batch_finish.json',dict(source_unchanged=True,status='interrupted',sessions=records))
            continuation.seal(directory)
        self.assertEqual(continuation.collection_chain(second,self.freeze)['attempted'],157)
        one,two=self.root/'cycle_one',self.root/'cycle_two'
        for directory,prior in ((one,two),(two,one)):
            directory.mkdir()
            continuation.write(directory/'plan.json',dict(freeze_sha256=continuation.digest(self.freeze/'freeze.json'),schedule=self.schedule,continuation_from=str(prior)))
            continuation.write(directory/'batch_finish.json',dict(source_unchanged=True,status='interrupted',sessions=entries[:3]))
            continuation.seal(directory)
        with self.assertRaisesRegex(ValueError,'cyclic'):continuation.collection_chain(one,self.freeze)


    def real_plan_fixture(self):
        """Real seals and source/review verification; no provenance mocks."""
        from contextlib import redirect_stdout
        import io
        self.frozen['source_sha256']={}
        (self.freeze/'freeze.json').write_text(json.dumps(self.frozen))
        continuation.seal(self.freeze)
        entries=self.prefix();audited=continuation.history(self.freeze,entries)
        prior=self.root/'original_run';prior.mkdir()
        continuation.write(prior/'plan.json',dict(freeze_sha256=continuation.digest(self.freeze/'freeze.json'),schedule=self.schedule))
        continuation.write(prior/'batch_finish.json',dict(status='interrupted',source_unchanged=True,sessions=entries,rejected_sessions=[]))
        continuation.seal(prior)
        protocol=self.root/'amendment.md';protocol.write_text('Offline fixture: preserve attempted prefix and execute exact suffix.\n')
        source={name:continuation.digest(continuation.ROOT/name) for name in continuation.SUPPLEMENTAL_SOURCES}
        review=self.root/'review.json'
        cont=self.root/'real_continuation';run=self.root/'authorized_run'
        continuation.write(review,dict(approved=True,source_sha256=source,
            prior_run_seal_sha256=continuation.digest(prior/'seal.json'),protocol_sha256=continuation.digest(protocol),
            authorized_run_directory=str(run),continuation_directory=str(cont)))
        with redirect_stdout(io.StringIO()):
            continuation.freeze_plan(SimpleNamespace(freeze=self.freeze,prior=prior,review=review,
                protocol=protocol,output=cont,run_output=run))
        run.mkdir()
        return continuation.verify_continuation(self.freeze,cont),cont,run,audited

    def real_ledger(self,plan,cont,run,audited,slot,offset,rejected=()):
        retry=len(rejected);directory=run/f'ledger_{slot:02d}_{offset:02d}_admission_{retry:02d}'
        directory.mkdir()
        ledger=dict(continuation_sha256=continuation.digest(cont/'continuation.json'),
            freeze_sha256=plan['freeze_sha256'],slot=slot,offset=offset,
            request_ids=self.schedule[slot-1]['request_ids'][offset:],prior_sessions=audited['prior_sessions'],
            prior_attempts=audited['prior_attempts'],baseline=plan['baseline'],admission_index=retry,
            admission_rejections=list(rejected),authorized_worker_directory=str(continuation.fragment_path(run,slot,offset,retry)))
        continuation.write(directory/'ledger.json',ledger);continuation.seal(directory)
        return directory,ledger

    def real_suffix_fragment(self,cont,ledger_dir,ledger,count):
        import shutil
        offset=ledger['offset'];slot_number=ledger['slot'];suffix=ledger['request_ids']
        target=Path(ledger['authorized_worker_directory'])
        def mutate(values):
            values['manifest.json']['fragment']=dict(offset=offset,request_ids=suffix,planned=len(suffix),
                ledger_directory=str(ledger_dir),ledger_sha256=continuation.digest(ledger_dir/'ledger.json'),
                ledger_seal_sha256=continuation.digest(ledger_dir/'seal.json'),continuation_directory=str(cont),
                continuation_sha256=continuation.digest(cont/'continuation.json'),continuation_seal_sha256=continuation.digest(cont/'seal.json'),
                local_index_scope='one-based index within this physical cold-start fragment')
            values['summary.json'].update(planned=len(suffix),original_planned=48,fragment_offset=offset,
                status='complete' if count==len(suffix) else 'interrupted',session_wall_ns=100)
            if count<len(suffix):
                values['summary.json']['failure']=dict(type='SafetyGateError',message='available memory is below startup floor')
            for index,row in enumerate(values['observations.jsonl'],1):
                start=(slot_number*100+offset+index)*10
                row.update(case=self.cases[offset+index-1],status='interrupted' if count<len(suffix) and index==count else 'ok',
                    started_monotonic_ns=start,finished_monotonic_ns=start+1,wall_ns=1)
            values['events.jsonl']=[dict(event='request_start',request_id=row['case']['id']) for row in values['observations.jsonl']]
        entry=self.fragment(slot_number,count,mutate)
        shutil.copytree(Path(entry['directory']),target)
        return dict(slot=slot_number,directory=str(target),exit_code=0 if count==len(suffix) else 1,
                    seal_sha256=continuation.digest(target/'seal.json'))

    def test_real_sealed_plan_and_suffix_chain_authorize_next_slot(self):
        plan,cont,run,audited=self.real_plan_fixture()
        ledger_dir,ledger=self.real_ledger(plan,cont,run,audited,4,13)
        self.assertEqual(continuation.verify_ledger(self.freeze,cont,ledger_dir,4,13),ledger)
        suffix=self.real_suffix_fragment(cont,ledger_dir,ledger,35)
        result=continuation.history(self.freeze,audited['prior_sessions']+[suffix])
        self.assertEqual((result['attempted'],result['remaining'],result['offsets'][4]),(192,672,48))
        self.assertEqual(result['prior_attempts'][:157],plan['prior_attempts'])
        self.assertEqual(result['prior_attempts'][156]['status'],'interrupted')
        self.assertEqual(result['prior_attempts'][157]['case_id'],'q13')
        next_dir,next_ledger=self.real_ledger(plan,cont,run,result,5,0)
        self.assertEqual(continuation.verify_ledger(self.freeze,cont,next_dir,5,0),next_ledger)
        self.assertEqual(len(next_ledger['request_ids']),48)

    def test_real_nonzero_attempt_cannot_be_reused_as_admission_rejection(self):
        plan,cont,run,audited=self.real_plan_fixture()
        original_dir,original_ledger=self.real_ledger(plan,cont,run,audited,4,13)
        attempted=self.real_suffix_fragment(cont,original_dir,original_ledger,1)
        self.assertEqual(continuation.read(Path(attempted['directory'])/'summary.json')['attempted'],1)
        retry_dir,_=self.real_ledger(plan,cont,run,audited,4,13,[attempted])
        with self.assertRaisesRegex(ValueError,'attempted or unverified admission cannot be retried'):
            continuation.verify_ledger(self.freeze,cont,retry_dir,4,13)


if __name__=='__main__':unittest.main()
