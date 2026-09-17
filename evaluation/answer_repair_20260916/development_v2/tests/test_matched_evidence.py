"""Offline fairness, artifact, failure-path, and tokenizer proof validation."""
from copy import deepcopy
from collections import Counter
from hashlib import sha256
import io
import json
from pathlib import Path
import signal
import struct
import sys
import tempfile
from time import perf_counter, sleep
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import run_matched_evidence as run
import matched_evidence_tokenizer as tokenizer


def case(index=0, category='routine_general'):
    return dict(request_id=f'q{index}', scenario_id=f's{index}', category=category,
                evidence_status='answerable', question=f'What is two plus {index}?',
                evidence=[], history=[], rubric=dict(required=['correct arithmetic'],
                reference_answer=f'{index + 2}'))


def dataset():
    return [case(i * 30 + j, category) for i, category in enumerate(run.CATEGORIES)
            for j in range(30)]


def response(model=run.MODELS[0], content='{"answer":"Four."}', reason='stop', **extra):
    return '\n'.join(json.dumps(row) for row in [
        dict(model=model, response=content[:5], done=False),
        dict(model=model, response=content[5:], done=True, done_reason=reason,
             prompt_eval_count=100, eval_count=10, **extra)]) + '\n'


class Writer:
    def __init__(self): self.records = []
    def write(self, row): self.records.append(deepcopy(row))


class FakeResponse(io.BytesIO):
    code = 200


class MatchedEvidenceTests(unittest.TestCase):
    def test_120_unique_cases_and_exact_counterbalance(self):
        cases = dataset()
        self.assertEqual(len(run.validate_dataset(cases)), 120)
        blocks = run.schedule(cases)
        self.assertEqual(len(blocks), 12)
        lookup = {c['request_id']: c for c in cases}
        attempts = Counter((rid, block['model']) for block in blocks for rid in block['request_ids'])
        self.assertEqual(len(attempts), 240)
        self.assertEqual(set(attempts.values()), {1})
        self.assertEqual(Counter(blocks[i]['model'] for i in range(0, 12, 2)),
                         Counter({model: 3 for model in run.MODELS}))
        for first, second in zip(blocks[::2], blocks[1::2]):
            self.assertEqual(first['request_ids'], second['request_ids'])
            self.assertEqual(Counter(lookup[rid]['category'] for rid in first['request_ids']),
                             Counter({category: 5 for category in run.CATEGORIES}))
        self.assertEqual(blocks, run.schedule(cases))

    def test_inputs_equal_and_reference_annotations_never_rendered(self):
        original = case()
        changed = deepcopy(original)
        changed.update(request_id='SECRET_ID', scenario_id='SECRET_SCENARIO',
                       category='SECRET_CATEGORY', evidence_status='unknown',
                       rubric={'required':['SECRET_REQUIRED'], 'reference_answer':'SECRET_GOLD'})
        self.assertEqual(run.rendered(original), run.rendered(changed))
        small, large = [run.request_body(original, model) for model in run.MODELS]
        del small['model']; del large['model']
        self.assertEqual(run.canonical(small), run.canonical(large))
        self.assertTrue(small['raw']); self.assertTrue(small['stream'])
        self.assertIs(small['think'], False)
        for key, value in {'num_ctx':2048, 'num_predict':192, 'temperature':0, 'seed':42}.items():
            self.assertEqual(small['options'][key], value)
        self.assertEqual(small['format']['properties'], {'answer':{'type':'string'}})
        self.assertNotIn('enum', json.dumps(small['format']))
        self.assertNotIn('SECRET', run.rendered(changed))
        with self.assertRaises(ValueError): run.request_body(original, 'qwen3:8b')

    def test_complete_evidence_unicode_budget_and_no_history(self):
        c = case()
        c['evidence'] = ['A fictional note: caf\u00e9 \U0001f916.', 'A second complete note.']
        for evidence in c['evidence']: self.assertIn(evidence, run.rendered(c))
        expected = tokenizer.prompt_budget(run.rendered(c))
        actual = run.budget(c)
        self.assertEqual({k: actual[k] for k in expected}, expected)
        c['evidence'] = ['x' * 2048]
        self.assertFalse(run.budget(c)['fits'])
        cases = dataset(); cases[0] = c
        with self.assertRaises((AssertionError, ValueError)): run.validate_dataset(cases)
        c = case(); c['history'] = [{'role':'user', 'content':'Earlier.'}]
        with self.assertRaises(ValueError): run.rendered(c)

    def test_duplicate_and_missing_cases_rejected(self):
        for cases in (dataset()[:-1], dataset()[:-1] + [dataset()[0]]):
            with self.assertRaises((AssertionError, ValueError)): run.validate_dataset(cases)

    def test_parse_preserves_exact_output_and_rejects_wrong_identity(self):
        raw = ' {"answer":"Four.  "} \n'
        parsed, thinking, stats = run.parse_generation(response(content=raw), run.MODELS[0])
        self.assertEqual(parsed, raw); self.assertEqual(thinking, '')
        self.assertEqual(stats['prompt_eval_count'], 100)
        for malformed in ('', '{', json.dumps({'model':run.MODELS[0], 'response':'unfinished'}),
                          response(model=run.MODELS[1])):
            with self.assertRaises((ValueError, TypeError, run.pair.SafetyGateError)):
                run.parse_generation(malformed, run.MODELS[0])

    def test_strict_answer_rejects_duplicate_nonfinite_and_nonobject_json(self):
        self.assertEqual(run.strict_answer(' {"answer":"Four."} '), {'answer':'Four.'})
        for raw in ('{"answer":"one","answer":"two"}', '{"answer":NaN}',
                    '["answer"]', 'null', '"answer"', '{"answer":2}',
                    '{"answer":"four","extra":false}'):
            with self.assertRaises(ValueError): run.strict_answer(raw)

    def test_residency_checks_name_digest_and_context(self):
        model = run.MODELS[0]
        frozen = {'models':{model:{'digest':'frozen'}}}
        correct = {'name':model, 'digest':'frozen', 'context_length':2048}
        for bad in ([], [correct, correct], [{**correct, 'name':run.MODELS[1]}],
                    [{**correct, 'digest':'changed'}], [{**correct, 'context_length':4096}]):
            with patch.object(run.pair, '_resident_models', return_value=bad):
                with self.assertRaises((AssertionError, ValueError)): run.assert_resident(model, frozen)
        with patch.object(run.pair, '_resident_models', return_value=[correct]):
            self.assertEqual(run.assert_resident(model, frozen), [correct])

    def attempt(self, raw, *, error=None, fatal=None):
        writer = Writer()
        transport = SimpleNamespace(call=lambda *args: (
            dict(raw_utf8=raw, error=error, wall_ns=100), fatal))
        backend = SimpleNamespace(check=lambda: None)
        with patch.object(run, 'assert_resident', return_value=[{'name':run.MODELS[0]}]), \
                patch('sys.stdout', new=io.StringIO()):
            try:
                result = run.run_attempt(case(), run.MODELS[0], {}, transport, backend, writer)
            except BaseException as exc:
                return writer, exc
        return writer, result

    def test_attempts_preserve_truncation_invalid_answers_and_errors(self):
        for raw, expected in ((response(), 'ok'), (response(reason='length'), 'truncated'),
                              (response(content='not JSON'), 'error'),
                              (response(content='{"speech":"wrong schema"}'), 'error')):
            with self.subTest(expected=expected, raw=raw):
                writer, result = self.attempt(raw)
                self.assertIsInstance(result, dict)
                self.assertEqual(result['status'], expected)
                self.assertEqual(result['transport']['raw_utf8'], raw)
                self.assertEqual(writer.records[0]['event'], 'attempt_start')
                self.assertEqual(writer.records[-1]['event'], 'attempt_finish')
        writer, result = self.attempt('partial bytes', error={'type':'TimeoutError', 'message':'expired'})
        self.assertEqual(writer.records[-1]['transport']['raw_utf8'], 'partial bytes')
        self.assertIn(writer.records[-1]['status'], {'error', 'interrupted'})

    def test_thinking_and_observed_budget_violation_are_fatal(self):
        for raw in (response(thinking='unexpected reasoning'),
                    response().replace('"prompt_eval_count": 100', '"prompt_eval_count": 2048')):
            writer, failure = self.attempt(raw)
            self.assertIsInstance(failure, run.pair.SafetyGateError)
            self.assertEqual(writer.records[-1]['status'], 'interrupted')
            self.assertEqual(writer.records[-1]['transport']['raw_utf8'], raw)

    def test_interruption_retains_attempt_before_propagating(self):
        interrupted = KeyboardInterrupt('stop')
        writer, result = self.attempt('partial', error={'message':'stop'}, fatal=interrupted)
        self.assertIs(result, interrupted)
        self.assertEqual(writer.records[-1]['status'], 'interrupted')
        self.assertEqual(writer.records[-1]['transport']['raw_utf8'], 'partial')

    def transport(self, opener):
        writer = Writer()
        with patch.object(run, 'build_opener', return_value=SimpleNamespace(open=opener)):
            result, fatal = run.Transport(writer, None).call(run.request_body(case(), run.MODELS[0]), 'primary', 'q0')
        return writer, result, fatal

    def test_transport_archives_real_bytes_and_http_error_body(self):
        payload = b'not json\xff\x00\n'
        writer, result, fatal = self.transport(lambda *a, **k: FakeResponse(payload))
        import base64
        recorded = b''.join(base64.b64decode(r['bytes_base64']) for r in writer.records if r['event']=='chunk')
        self.assertEqual(recorded, payload)
        self.assertIsNone(fatal)
        def http_error(*args, **kwargs):
            raise HTTPError('http://127.0.0.1:11434/api/generate', 503, 'unavailable', {}, io.BytesIO(b'backend failure details'))
        writer, result, fatal = self.transport(http_error)
        self.assertEqual(result['http_status'], 503)
        self.assertEqual(result['raw_utf8'], 'backend failure details')
        self.assertIsNotNone(result['error'])
        self.assertIsInstance(fatal, RuntimeError)
        self.assertEqual(writer.records[0]['event'], 'start')
        self.assertEqual(writer.records[-1]['event'], 'finish')

    def test_active_deadline_and_stalled_telemetry_interrupt_blocking_call(self):
        prior = signal.getsignal(signal.SIGALRM)
        start = perf_counter()
        with self.assertRaises(TimeoutError):
            with run.alarm_guard(None, .01): sleep(2)
        self.assertLess(perf_counter() - start, 1)
        self.assertEqual(signal.getsignal(signal.SIGALRM), prior)
        sampler = SimpleNamespace(last_sample=perf_counter()-10,
                                  monitor=SimpleNamespace(violation=None))
        with self.assertRaises(run.pair.SafetyGateError):
            with run.alarm_guard(sampler, 10): sleep(2)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_exclusive_creation_and_frozen_source_drift(self):
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td)
            target = run.pair._new_private_directory(parent/'fresh')
            with self.assertRaises(run.pair.ModelPairEvaluationError):
                run.pair._new_private_directory(target)
            run.write(target/'record.json', {'original':True})
            with self.assertRaises(run.pair.ModelPairEvaluationError):
                run.write(target/'record.json', {'original':False})
            self.assertEqual(json.loads((target/'record.json').read_text()), {'original':True})
            (target/'freeze.json').write_text(json.dumps({'source_sha256':{'a':'old'}}))
            with patch.object(run, 'verify_seal'), patch.object(run, 'source_hashes', return_value={'a':'changed'}):
                with self.assertRaises((AssertionError, ValueError)): run.verify_frozen(target)


class TokenizerProofTests(unittest.TestCase):
    def metadata(self):
        tokens = list(tokenizer.byte_alphabet().values())
        return {'tokenizer.ggml.model':'gpt2', 'tokenizer.ggml.pre':'qwen2',
                'tokenizer.ggml.tokens':tokens, 'tokenizer.ggml.token_type':[1]*256,
                'tokenizer.ggml.merges':['! !'], 'tokenizer.ggml.add_bos_token':False,
                'tokenizer.ggml.bos_token_id':0, 'tokenizer.ggml.eos_token_id':1}

    def encode(self, metadata):
        def string(value):
            raw=value.encode(); return struct.pack('<Q', len(raw)) + raw
        def value(value):
            if isinstance(value, bool): return 7, struct.pack('<?', value)
            if isinstance(value, int): return 4, struct.pack('<I', value)
            if isinstance(value, str): return 8, string(value)
            kind = 8 if isinstance(value[0], str) else 4
            return 9, struct.pack('<IQ', kind, len(value)) + b''.join(value_payload(v) for v in value)
        def value_payload(v): return value(v)[1]
        raw = b'GGUF' + struct.pack('<IQQ', 3, 0, len(metadata))
        for key, val in metadata.items():
            kind, payload = value(val)
            raw += string(key) + struct.pack('<I', kind) + payload
        return raw

    def test_byte_alphabet_coverage_and_utf8_budget(self):
        alphabet = tokenizer.byte_alphabet()
        self.assertEqual(len(alphabet), 256)
        self.assertEqual(len(set(alphabet.values())), 256)
        self.assertEqual(alphabet[32], '\u0120')
        self.assertEqual(alphabet[10], '\u010a')
        self.assertEqual(tokenizer.prompt_budget('\U0001f916')['prompt_utf8_bytes'], 4)
        self.assertTrue(tokenizer.prompt_budget('x'*1790)['fits'])
        self.assertFalse(tokenizer.prompt_budget('x'*1791)['fits'])

    def test_gguf_reader_excludes_weights_and_rejects_truncation(self):
        expected=self.metadata(); raw=self.encode(expected)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'model.gguf'; path.write_bytes(raw+b'UNREAD WEIGHTS')
            actual, details = tokenizer.read_gguf_metadata(path)
            self.assertEqual(actual, expected)
            self.assertEqual(details['metadata_prefix_bytes'], len(raw))
            self.assertEqual(details['metadata_prefix_sha256'], sha256(raw).hexdigest())
            path.write_bytes(raw[:-1])
            with self.assertRaises(ValueError): tokenizer.read_gguf_metadata(path)

    def test_incomplete_bytes_and_wrong_tokenizer_rejected(self):
        valid = self.metadata()
        _, ids = tokenizer._validate_tokenizer(valid)
        self.assertEqual(len(ids), 256)
        mutations = []
        for key, val in [('tokenizer.ggml.model','llama'), ('tokenizer.ggml.pre','unknown'),
                         ('tokenizer.ggml.add_bos_token',True)]:
            invalid=deepcopy(valid);invalid[key]=val;mutations.append(invalid)
        invalid=deepcopy(valid);invalid['tokenizer.ggml.token_type'][0]=3;mutations.append(invalid)
        invalid=deepcopy(valid);invalid['tokenizer.ggml.tokens'][0]='missing_byte';mutations.append(invalid)
        for invalid in mutations:
            with self.assertRaises(ValueError): tokenizer._validate_tokenizer(invalid)

    def test_different_model_tokenizer_metadata_cannot_be_certified(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            manifests=root/'manifests/registry.ollama.ai/library/qwen3'
            manifests.mkdir(parents=True);(root/'blobs').mkdir()
            for index, model in enumerate(tokenizer.MODELS):
                metadata=self.metadata()
                metadata['tokenizer.ggml.eos_token_id']=index+1
                raw=self.encode(metadata)
                blob_hash=sha256(raw).hexdigest()
                (root/'blobs'/f'sha256-{blob_hash}').write_bytes(raw)
                manifest={'layers':[{'mediaType':'application/vnd.ollama.image.model',
                                    'digest':f'sha256:{blob_hash}', 'size':len(raw)}]}
                (manifests/model.split(':')[1]).write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'different tokenizer metadata'):
                tokenizer.tokenizer_proof(root)

    @unittest.skipUnless(tokenizer.MODEL_ROOT.exists(), 'installed GGUF metadata unavailable')
    def test_installed_pair_has_identical_complete_byte_bpe_without_inference(self):
        proof=tokenizer.tokenizer_proof()
        self.assertTrue(proof['identical_tokenizer_metadata'])
        self.assertFalse(proof['inference_performed'])
        models=proof['models']
        self.assertEqual(set(models), set(run.MODELS))
        self.assertEqual(len({m['tokenizer_metadata_sha256'] for m in models.values()}), 1)
        self.assertTrue(all(m['complete_ordinary_byte_coverage'] for m in models.values()))


if __name__ == '__main__': unittest.main()
