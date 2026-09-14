#!/usr/bin/env python3
"""Unblinded diagnosis after frozen reviews; no model calls or rescoring."""
import ast
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

BASE = Path(__file__).resolve().parent
FREEZE = BASE / 'frozen_v2'
TARGETS = ('cm04_correction_restart_retained', 'cm04_correction_restart_fresh')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def verify_seal(directory):
    for relative, expected in read(directory / 'seal.json')['sha256'].items():
        assert sha(directory / relative) == expected, (directory, relative)


def main():
    out = BASE / 'withheld_diagnostics_v1.json'
    assert not out.exists()
    source = FREEZE / 'source/src'
    sys.path.insert(0, str(source))
    from oline_hri import conversation as c
    from oline_hri.relationships import missing_user_relationship
    assert Path(c.__file__).resolve() == source / 'oline_hri/conversation.py'
    spec = importlib.util.spec_from_file_location('repair_analysis_diagnostic', BASE / 'analyze_repair.py')
    analysis = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analysis)
    branch = BASE / 'run_v1/cm04_correction'
    fragment = branch / 'restart'
    batch = BASE / 'review_batches/batch_01'
    for directory in (FREEZE, branch, fragment, batch):
        verify_seal(directory)
    receipt_path = BASE / 'review_receipts/batch_01.json'
    receipt = read(receipt_path)
    assert receipt['original_judgments_frozen_before_diagnostics'] is True
    assert receipt['semantic_disagreements'] == []
    packet_path = batch / 'public/packets.jsonl'
    assert sha(packet_path) == receipt['packet_sha256']
    mapping_path = batch / 'private/mapping.json'
    mapping = next(m for m in read(mapping_path) if set(m['checkpoint_ids']) == set(TARGETS))
    packet = next(p for p in lines(packet_path) if p['blind_id'] == mapping['blind_id'])
    reviews = {}
    inputs = [FREEZE / 'seal.json', FREEZE / 'expected_ledger.json', branch / 'seal.json',
              fragment / 'seal.json', fragment / 'answers.jsonl', fragment / 'http.jsonl',
              fragment / 'events.jsonl', fragment / 'process.json', packet_path, mapping_path,
              batch / 'seal.json', receipt_path, BASE / 'analyze_repair.py',
              source / 'oline_hri/conversation.py', source / 'oline_hri/relationships.py',
              source / 'oline_hri/routing.py', source / 'oline_hri/grounded_composition.py']
    for reviewer in ('a', 'b'):
        path = BASE / f'reviewer_{reviewer}/batch_01.json'
        assert sha(path) == receipt['review_sha256'][reviewer]
        document = read(path)
        assert document['packet_sha256'] == receipt['packet_sha256']
        vote = next(v for v in document['judgments'] if v['blind_id'] == mapping['blind_id'])
        assert vote['classification'] == 'no_delivered_answer'
        assert vote['useful_correct'] is False and vote['forbidden_disclosure'] is False
        reviews[reviewer] = {'reviewer_id': document['reviewer_id'], 'judgment': vote}
        inputs.append(path)
    expected = {r['checkpoint_id']: r for r in read(FREEZE / 'expected_ledger.json')['checkpoints']}
    evidence = []
    for number, row in enumerate(lines(fragment / 'answers.jsonl'), 1):
        if row['checkpoint_id'] not in TARGETS:
            continue
        ledger = expected[row['checkpoint_id']]
        assert row['status'] == 'withheld' and row['delivered_answer'] is None
        calls = [call for call in row['calls'] if call['purpose'] == 'generation']
        assert len(calls) == 1
        generation = calls[0]
        raw = generation['raw_chat_payload']['message']['content']
        speech = json.loads(raw)['speech']
        supplied = analysis.generation_evidence_records(row)
        assert len(supplied) == 1 and supplied[0]['canonical_text'] == ledger['permitted_evidence'][0]['canonical_text']
        assert len(row['snapshot_checks']) == 2 and all(s['current'] for s in row['snapshot_checks'])
        assert all(s['logical_time'] == ledger['logical_time'] for s in row['snapshot_checks'])
        canonical, memory_id = supplied[0]['canonical_text'], supplied[0]['id']
        response = SimpleNamespace(speech=speech, memory_used=(memory_id,))
        supplied_objects = (SimpleNamespace(memory=SimpleNamespace(id=memory_id, canonical_text=canonical)),)
        question = ledger['question']
        probes = {}
        for label, query in (('authored_question', question), ('diagnostic_word_removal_only', question.replace('current ', ''))):
            try:
                c._require_requested_named_collaborator(response, supplied_objects, query)
            except Exception as error:
                probes[label] = {'accepted_by_specific_function': False, 'error_type': type(error).__name__, 'error': str(error)}
            else:
                probes[label] = {'accepted_by_specific_function': True}
            probes[label]['request_link'] = c._collaborator_request_link(query, canonical)
        assert probes['authored_question']['accepted_by_specific_function'] is False
        assert probes['diagnostic_word_removal_only']['accepted_by_specific_function'] is True
        evidence.append({'checkpoint_id': row['checkpoint_id'],
            'source': {'path': str(fragment / 'answers.jsonl'), 'line': number},
            'expected': ledger, 'generation_call': generation,
            'raw_speech': speech, 'delivered_answer': None,
            'status': row['status'], 'validation_decision': row['validation_decision'],
            'validation_failures': [s for s in row['trace'] if s.get('status') == 'error'],
            'actual_supplied_evidence': supplied, 'retrieval_calls': row['retrieval_calls'],
            'snapshot_checks': row['snapshot_checks'], 'route': row['route']['decision'],
            'process': row['process'], 'database_identity': row['database_identity'],
            'speech_schema_has_enum_constraint': 'enum' in generation['response_format']['properties']['speech'],
            'generation_message_count': len(generation['messages']),
            'pure_function_probes': probes,
            'qualifier_terms': sorted(c.topic_terms('current walking')),
            'canonical_terms': sorted(c.topic_terms(canonical)),
            'missing_user_relationship': missing_user_relationship(canonical, speech),
            'unblinded_diagnostic_assessment': 'Useful supported raw current-replacement answer rejected unnecessarily by request-link validator. Delivered no-answer score remains unchanged.'})
    assert len(evidence) == 2
    names = ('_require_requested_named_collaborator', '_collaborator_request_link')
    def functions(path):
        return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(path.read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name in names}
    baseline_path = BASE.parent / 'changing_memory_20260914/frozen_v1/source/src/oline_hri/conversation.py'
    unchanged = functions(baseline_path) == functions(source / 'oline_hri/conversation.py')
    assert unchanged
    inputs.append(baseline_path)
    result = {'created_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'Only the two cm04 correction restart withheld answers after batch01 original blinded judgments were frozen. No batch02 answers inspected.',
        'review_type': 'unblinded assistant diagnostic assessment, not answer rescoring',
        'inference_performed': False, 'runtime_changes': False, 'delivered_judgments_unchanged': True,
        'human_validation': 'pending', 'script_sha256': sha(Path(__file__)),
        'command': [sys.executable, str(Path(__file__).resolve())],
        'input_sha256': {str(p): sha(p) for p in inputs},
        'blind_packet': packet, 'original_frozen_judgments': reviews,
        'unchanged_baseline_validator_function_asts': unchanged,
        'cause': 'The collaborator request-link requires lexical query qualifier current to occur in canonical text. Present-tense current authorized replacement lacks that word, so the validator reports absent evidence despite actual evidence being supplied.',
        'probe_limit': 'Removing current in an offline function-only probe isolates the lexical gate; it is not a changed experimental question, rerun, inference result, or new score.',
        'cases': evidence}
    out.write_text(json.dumps(result, indent=2) + '\n')
    out.chmod(0o400)
    print(json.dumps({'output': str(out), 'sha256': sha(out), 'cases': len(evidence),
                      'original_judgments_frozen': True, 'unnecessary_validator_rejection': 2}, indent=2))


if __name__ == '__main__':
    main()
