"""Offline orchestration controls; no model or device access."""
import json
import base64
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_independent_retrieval as runner


class RunnerTests(unittest.TestCase):
    def runtime(self):
        return dict(metadata={'execution_case_order_seeds':[2026091301,2026091302,2026091303]},
                    execution_cases=[{'id':str(i)} for i in range(48)])

    def test_counterbalance_and_complete_pairing(self):
        schedule=runner.schedule(self.runtime())
        self.assertEqual(len(schedule),18)
        self.assertEqual(sum(len(s['request_ids']) for s in schedule),864)
        self.assertEqual(len({(s['repetition'],s['model'],s['policy']) for s in schedule}),18)
        for rep in (1,2,3):
            orders=[s['request_ids'] for s in schedule if s['repetition']==rep]
            self.assertTrue(all(ids==orders[0] for ids in orders))
            self.assertEqual(set(orders[0]),set(map(str,range(48))))
        for model in runner.MODELS:
            for policy in runner.POLICIES:
                positions=[]
                for rep in (1,2,3):
                    block=[s for s in schedule if s['model']==model and s['repetition']==rep]
                    positions.append(next(i for i,s in enumerate(block) if s['policy']==policy))
                self.assertEqual(sorted(positions),[0,1,2])

    def test_seals_cover_nested_manifests_and_detect_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'root';root.mkdir()
            child=root/'child';child.mkdir();(child/'data.json').write_text('{}')
            runner.seal(child);runner.seal(root);runner.verify_seal(root)
            manifest=json.loads((root/'seal.json').read_text())['sha256']
            self.assertIn('child/seal.json',manifest)
            data=child/'data.json';data.chmod(0o600);data.write_text('{"changed":true}')
            with self.assertRaises(ValueError): runner.verify_seal(root)
            root.chmod(0o700);child.chmod(0o700)

    def test_seals_reject_extra_unrecorded_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'root';root.mkdir();(root/'a').write_text('a')
            runner.seal(root);root.chmod(0o700);(root/'extra').write_text('b')
            with self.assertRaises(ValueError): runner.verify_seal(root)

    def test_frozen_configuration_enforces_requested_decoding(self):
        config=runner.configuration()
        self.assertEqual(config.generation.context_length,2048)
        self.assertEqual(config.generation.max_output_tokens,192)
        self.assertEqual(config.generation.temperature,0)
        self.assertFalse(config.generation.thinking)

    def test_durable_http_start_is_saved_when_transport_fails(self):
        class Writer:
            def __init__(self): self.rows=[]
            def write(self,row): self.rows.append(row)
        config=runner.configuration();writer=Writer()
        client=runner.DurableClient(config.ollama,config.generation,http_writer=writer)
        with patch.object(runner.ComparisonClient,'_post_json',side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):
                client._post_json('/api/chat',{'model':'qwen3:0.6b','messages':[]})
        self.assertEqual(writer.rows[0]['event'],'http_start')
        self.assertEqual(writer.rows[0]['body']['model'],'qwen3:0.6b')

    def test_raw_body_preserved_before_decode_and_on_interrupted_read(self):
        class Writer:
            def __init__(self): self.rows=[]
            def write(self,row): self.rows.append(row)
        class Response:
            def __init__(self): self.calls=0
            def read(self,limit):
                self.calls+=1
                if self.calls==1: return b'\xffpartial'
                raise TimeoutError('interrupted socket')
        writer=Writer()
        with self.assertRaises(TimeoutError):
            runner.RecordedResponse(Response(),writer).read(65537)
        self.assertEqual(base64.b64decode(writer.rows[0]['bytes_base64']),b'\xffpartial')

    def test_interrupted_request_keeps_observation_and_start(self):
        class Adapter:
            def __init__(self,*args,**kwargs): pass
            def send(self,*args): raise KeyboardInterrupt('simulated guard')
            def to_dict(self,*args): return {'retrieval_attempts':0}
        backend=SimpleNamespace(check=lambda:None,transport_error=None,calls=[],
                                client=SimpleNamespace(http_calls=[]))
        case=dict(id='request',prompt='Question',profile_id='fixture',consent_authorized=True)
        slot=dict(slot=1,model=runner.MODELS[0],policy='OFF',repetition=1)
        with tempfile.TemporaryDirectory() as temp, \
             patch('independent_retrieval_adapter.IndependentRetrievalAdapter',Adapter), \
             patch.object(runner.pair,'_resident_models',return_value=[]):
            directory=Path(temp)
            with self.assertRaises(KeyboardInterrupt):
                runner.run_cases([case,dict(case,id='unattempted')],slot,None,backend,None,directory)
            rows=[json.loads(s) for s in (directory/'observations.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['status'],'interrupted')
            self.assertEqual(rows[0]['error'],'KeyboardInterrupt')
            events=[json.loads(s) for s in (directory/'events.jsonl').read_text().splitlines()]
            self.assertEqual(events[0]['event'],'request_start')


if __name__=='__main__': unittest.main()
