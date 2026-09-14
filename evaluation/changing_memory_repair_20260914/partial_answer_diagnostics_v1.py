#!/usr/bin/env python3
"""Frozen-source diagnostic probes only; no inference, repair, or rescoring."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

BASE = Path(__file__).resolve().parent
TARGETS = {'cm01_correction_corrected_retained', 'cm01_correction_corrected_fresh'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def main():
    output = BASE / 'partial_answer_diagnostics_v1.json'
    assert not output.exists()
    freeze, analysis = BASE / 'frozen_v2', BASE / 'analysis_v1'
    fragment = BASE / 'run_v1/cm01_correction/initial'
    for directory in (freeze, analysis, analysis / 'frozen_votes', fragment.parent, fragment):
        for name, expected in read(directory / 'seal.json')['sha256'].items():
            assert sha(directory / name) == expected, (directory, name)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(freeze / 'source/src'))
    from oline_hri import conversation as c
    assert Path(c.__file__).resolve() == freeze / 'source/src/oline_hri/conversation.py'
    expected = {r['checkpoint_id']: r for r in read(freeze / 'expected_ledger.json')['checkpoints']}
    selected = [r for r in rows(analysis / 'reviewed_answers.jsonl') if r['checkpoint_id'] in TARGETS]
    assert len(selected) == 2
    agreement = read(analysis / 'review_agreement.json')
    assert agreement['resolved_before_diagnostics'] and agreement['disagreements'] == []
    votes = {}
    for reviewer in ('a', 'b'):
        p = analysis / f'frozen_votes/review_{reviewer}.json'
        assert sha(p) == agreement[f'review_{reviewer}_sha256']
        votes[reviewer] = read(p)
    evidence = []
    for reviewed in selected:
        row, ledger = reviewed['observed_record'], reviewed['expected']
        assert ledger == expected[row['checkpoint_id']]
        assert reviewed['judgment']['classification'] == 'partial'
        assert reviewed['judgment']['useful_correct'] is False and reviewed['judgment']['forbidden_disclosure'] is False
        judgments = {}
        for reviewer, document in votes.items():
            vote = next(v for v in document['judgments'] if v['blind_id'] == reviewed['blind_id'])
            assert vote['classification'] == 'partial' and vote['useful_correct'] is False
            assert vote['forbidden_disclosure'] is False
            judgments[reviewer] = vote
        gen = next(call for call in row['calls'] if call['purpose'] == 'generation')
        raw = json.loads(gen['raw_chat_payload']['message']['content'])['speech']
        assert raw == row['delivered_answer'] == reviewed['delivered_answer']
        assert len(row['supplied_records']) == 1
        assert row['supplied_records'][0]['canonical_text'] == ledger['permitted_evidence'][0]['canonical_text']
        assert len(row['snapshot_checks']) == 2 and all(s['current'] for s in row['snapshot_checks'])
        supplied = tuple(SimpleNamespace(memory=SimpleNamespace(**m)) for m in row['supplied_records'])
        ids = tuple(m.memory.id for m in supplied)
        response = SimpleNamespace(speech=raw, memory_used=ids)
        probes = {'verified_preference_answer': c._verified_preference_answer(supplied, ledger['question'], ids),
                  'verified_composed_answer': c._verified_composed_answer(supplied, ledger['question'], ids),
                  'negated_preference_pattern_matches': bool(c._NEGATED_PREFERENCE_PATTERN.search(raw)),
                  'negated_preference_pattern': c._NEGATED_PREFERENCE_PATTERN.pattern}
        for name, args in (
            ('_require_cited_memory_coverage', (response, supplied, ledger['question'])),
            ('_require_no_negated_grounded_fact', (response, supplied)),
            ('_require_human_user_perspective', (response,)),
        ):
            try:
                getattr(c, name)(*args)
            except Exception as error:
                probes[name] = {'accepted': False, 'error_type': type(error).__name__, 'error': str(error)}
            else:
                probes[name] = {'accepted': True}
        assert probes['verified_preference_answer'] is None and probes['verified_composed_answer'] is None
        assert all(probes[name]['accepted'] for name in probes if name.startswith('_require'))
        evidence.append({'checkpoint_id': row['checkpoint_id'], 'source': reviewed['diagnostics']['analysis_source'],
            'expected': ledger, 'original_frozen_judgments': judgments, 'generation_call': gen,
            'raw_speech': raw, 'delivered_speech': row['delivered_answer'], 'raw_delivered_exact_match': True,
            'supplied_records': row['supplied_records'], 'retrieval_calls': row['retrieval_calls'],
            'snapshot_checks': row['snapshot_checks'], 'route': row['route']['decision'],
            'generation_policy': row.get('generation_policy'), 'answer_constraint': row.get('answer_constraint'),
            'response_transform': row.get('response_transform'), 'validation_decision': row['validation_decision'],
            'validation_spans': [s for s in row['trace'] if s['name'] == 'validation'],
            'original_statement_present_in_history': row['original_disclosure_present_in_history'],
            'generation_message_count': len(gen['messages']),
            'speech_enum_present': 'enum' in gen['response_format']['properties']['speech'],
            'process': row['process'], 'database_identity': row['database_identity'], 'pure_function_probes': probes})
    assert evidence[0]['generation_call']['messages'] == evidence[1]['generation_call']['messages']
    inputs = [freeze / 'seal.json', freeze / 'expected_ledger.json', analysis / 'seal.json',
              analysis / 'reviewed_answers.jsonl', analysis / 'review_agreement.json',
              analysis / 'frozen_votes/review_a.json', analysis / 'frozen_votes/review_b.json',
              analysis / 'frozen_votes/seal.json', fragment.parent / 'seal.json', fragment / 'seal.json',
              fragment / 'answers.jsonl', fragment / 'events.jsonl', fragment / 'http.jsonl',
              freeze / 'source/src/oline_hri/conversation.py', freeze / 'source/src/oline_hri/grounded_composition.py']
    result = {'created_at': datetime.now(timezone.utc).isoformat(), 'review_type': 'unblinded assistant diagnosis; not rescoring',
        'inference_performed': False, 'production_changes': False, 'frozen_partial_judgments_unchanged': True,
        'human_validation': 'pending', 'script_sha256': sha(Path(__file__)),
        'command': [sys.executable, str(Path(__file__).resolve())], 'input_sha256': {str(p): sha(p) for p in inputs},
        'scope': 'Only two first-repair cm01 correction partial answers. No additional repair authorized or performed.',
        'identical_generation_messages_across_retained_fresh': True,
        'stage_diagnosis': {'storage': 'Current replacement available and eligible.',
            'retrieval_and_supply': 'Current replacement retrieved and supplied; both freshness checks pass.',
            'generation': 'Raw qwen3:0.6b speech supplies replacement then contradicts recall with unsupported ignorance.',
            'application_composition': 'No speech constraint or transform; bounded preference and general composition helpers both decline this input.',
            'validation': 'Accepted the contradiction; coverage finds factual anchors, while the negative-preference grammar does not match a claim of not knowing.',
            'history_or_cache_causality': 'No prior history in either actual generation request; identical current/evidence inputs. No cache-origin inference is established.'},
        'cases': evidence}
    output.write_text(json.dumps(result, indent=2) + '\n')
    output.chmod(0o400)
    print(json.dumps({'output': str(output), 'sha256': sha(output), 'cases': len(evidence),
                      'raw_delivered_exact_match': True, 'frozen_judgments_unchanged': True}, indent=2))


if __name__ == '__main__':
    main()
