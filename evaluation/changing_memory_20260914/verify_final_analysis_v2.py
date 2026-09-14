#!/usr/bin/env python3
"""Independent read-only comparison and mechanical diagnosis of sealed analyses.

No models, inference, semantic rescoring, or changes to analyzed files.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def verified_seal(directory):
    seal = read(directory / 'seal.json')
    for relative, expected in seal['sha256'].items():
        assert sha(directory / relative) == expected, (directory, relative)
    return sha(directory / 'seal.json')


def differences(a, b, path=''):
    if type(a) is not type(b):
        return [path]
    if isinstance(a, dict):
        return (sorted(f'{path}/{k}' for k in a.keys() ^ b.keys())
                + [p for k in sorted(a.keys() & b.keys())
                   for p in differences(a[k], b[k], f'{path}/{k}')])
    return [] if a == b else [path]


def without_findings(value):
    if isinstance(value, dict):
        return {k: without_findings(v) for k, v in value.items() if k != 'failure_findings'}
    if isinstance(value, list):
        return [without_findings(v) for v in value]
    return value


def counter_rows(counter, names):
    return [dict(zip(names, key), count=count) for key, count in sorted(counter.items())]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    base = args.experiment.resolve()
    assert not args.output.exists(), 'preserve earlier outputs'
    v1, v2 = base / 'analysis_v1', base / 'analysis_v2'
    seals = {p.name: verified_seal(p) for p in (v1, v2)}
    before, after = rows(v1 / 'reviewed_answers.jsonl'), rows(v2 / 'reviewed_answers.jsonl')
    assert len(before) == len(after) == 288
    assert [r['checkpoint_id'] for r in before] == [r['checkpoint_id'] for r in after]
    changed = []
    for old, new in zip(before, after):
        assert {k: v for k, v in old.items() if k != 'diagnostics'} == {
            k: v for k, v in new.items() if k != 'diagnostics'}
        if old['diagnostics'] != new['diagnostics']:
            changed.append({'checkpoint_id': new['checkpoint_id'],
                            'changed_diagnostic_fields': differences(old['diagnostics'], new['diagnostics']),
                            'v1_findings': old['diagnostics']['failure_findings'],
                            'v2_findings': new['diagnostics']['failure_findings']})
    vote_hashes = {}
    for name in ('review_a.json', 'review_b.json', 'resolved.json'):
        assert (v1 / 'frozen_votes' / name).read_bytes() == (v2 / 'frozen_votes' / name).read_bytes()
        vote_hashes[name] = sha(v2 / 'frozen_votes' / name)
    metric1, metric2 = read(v1 / 'metrics.json'), read(v2 / 'metrics.json')
    assert without_findings(metric1) == without_findings(metric2)
    unchanged_files = ('history_pairs.jsonl', 'process_audit.json', 'acknowledgments.jsonl',
                       'audit_events.jsonl', 'diagnostic_answers.jsonl')
    for name in unchanged_files:
        assert (v1 / name).read_bytes() == (v2 / name).read_bytes(), name

    failures, transforms, selection, prompt_examples = [], [], [], []
    all_generation, all_status, cache = Counter(), Counter(), Counter()
    for p in sorted((base / 'run_v2').glob('**/answers.jsonl')):
        for observed in rows(p):
            group = 'scored' if observed['checkpoint_id'] else 'setup'
            all_status[group, observed['status']] += 1
            for call in observed['calls']:
                cached = call.get('raw_chat_payload', {}).get('prompt_eval_cached_count', 0)
                cache[call['purpose'], 'nonzero' if cached else 'zero'] += 1
                if call['purpose'] == 'generation':
                    all_generation[group, call['requested_model'], call['actual_model']] += 1
    for row in after:
        observed = row['observed_record']
        calls = [c for c in observed['calls'] if c['purpose'] == 'generation']
        assert len(calls) == 1
        call = calls[0]
        raw = json.loads(call['raw_chat_payload']['message']['content'])['speech']
        delivered = row['delivered_answer']
        findings = row['diagnostics']['failure_findings']
        witness = {'checkpoint_id': row['checkpoint_id'],
                   'source': row['diagnostics']['analysis_source'],
                   'expected_kind': row['expected']['expected_kind'],
                   'required_fact_count': len(row['expected']['permitted_evidence']),
                   'raw_speech': raw, 'delivered_speech': delivered,
                   'exact_speech_match': raw == delivered,
                   'recorded_response_transform': observed.get('response_transform')}
        if 'delivered_semantic_failure_with_sufficient_evidence' in findings:
            failures.append(witness)
        if observed['status'] == 'delivered' and raw != delivered:
            transforms.append(witness)
        if 'evidence_selection_required_fact_missing' in findings:
            assert not any('PERSONAL_MEMORY_DATA' in m['content'] for m in call['messages'])
            assert observed['memory']['supplied_ids'] == []
            assert row['diagnostics']['required_evidence_retrieved'] is True
            assert row['diagnostics']['required_evidence_in_store'] is True
            selection.append({**witness, 'question': row['expected']['question'],
                'permitted_evidence': row['expected']['permitted_evidence'],
                'retrieval_calls': observed['retrieval_calls'],
                'actual_generation_messages': call['messages'], 'memory': observed['memory'],
                'route': observed['route']['decision'],
                'diagnosis': 'Required eligible fact retrieved; actual production generation request supplied no evidence. This is not an analysis extraction gap.'})
        if row['checkpoint_id'] in ('cm01_deletion_restart_fresh', 'cm01_expiry_restart_fresh'):
            hits = [{'purpose': c['purpose'], 'message_index': i, 'role': m['role'], 'content': m['content']}
                    for c in observed['calls'] for i, m in enumerate(c['messages'])
                    if 'jasmine' in m['content'].casefold()]
            prompt_examples.append({**witness, 'question': row['expected']['question'],
                'original_subject_value': row['expected']['original_subject_value'],
                'replacement_subject_value': row['expected']['replacement_subject_value'],
                'history_before_length': len(observed['history_before']),
                'route': observed['route']['decision'], 'memory': observed['memory'],
                'prompt_matches': hits,
                'interpretation': 'Jasmine is explicitly present in the actual generation system demonstration. It is a forbidden never-stored replacement in this branch, not disclosure of the deleted/expired original rooibos. No cache-origin or cross-database inference is established.'})
    assert len(failures) == 131 and all(r['exact_speech_match'] for r in failures)
    assert len(selection) == 4 and len(prompt_examples) == 2
    assert all(r['recorded_response_transform'] is None for r in failures)
    assert all(r['delivered_speech'] == 'I do not have a verified personal memory that answers that.' for r in transforms)

    audit = read(base / 'collection_audit_v1.json')
    telemetry = [s for p in (base / 'run_v2').glob('**/telemetry.jsonl') for s in rows(p)]
    starts = [read(p) for p in (base / 'run_v2').glob('**/start.json')]
    finishes = [read(p) for p in (base / 'run_v2').glob('**/finish.json')]
    resource_summary = {
        'telemetry_samples': len(telemetry),
        'sampled_temperature_max_c': max(max(s['temperatures_c'].values()) for s in telemetry),
        'sampled_ram_used_mb_min': min(s['ram']['used_mb'] for s in telemetry),
        'sampled_ram_used_mb_max': max(s['ram']['used_mb'] for s in telemetry),
        'sampled_ram_total_mb': sorted({s['ram']['total_mb'] for s in telemetry}),
        'sampled_swap_used_mb_min': min(s['swap']['used_mb'] for s in telemetry),
        'sampled_swap_used_mb_max': max(s['swap']['used_mb'] for s in telemetry),
        'start_capture_count': len(starts), 'finish_capture_count': len(finishes),
        'runtime_guard_violations': [f.get('guard_violation') for f in finishes if f.get('guard_violation')],
        'cleanup_errors': [f.get('cleanup_errors') for f in finishes if f.get('cleanup_errors')],
        'boundary_mem_available_kib_min': min(s['memory']['mem_available_kib'] for s in starts + [f['snapshot'] for f in finishes]),
        'limitations': 'Telemetry RAM used is not Linux MemAvailable. Boundary captures and recorded runtime-guard outcomes do not prove unobserved instantaneous resource values. Ollama cached token counts show cache activity, not a source of answer content.'}
    result = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'command': shlex.join([sys.executable, *sys.argv]), 'cwd': str(Path.cwd()),
        'script_sha256': sha(Path(__file__)),
        'input_seal_sha256': seals, 'audit_sha256': sha(base / 'collection_audit_v1.json'),
        'scope': 'Independent mechanical verification after both original blinded reviews were frozen. No inference, rescoring, or runtime change.',
        'comparison': {'non_diagnostic_rows_exactly_equal': 288, 'frozen_vote_file_hashes': vote_hashes,
            'answer_metrics_exactly_equal': True,
            'only_metric_difference_paths': differences(metric1, metric2),
            'other_exactly_equal_files': list(unchanged_files), 'diagnostic_changes': changed},
        'scored_and_setup_status': counter_rows(all_status, ('scope', 'status')),
        'actual_generation_requests': counter_rows(all_generation, ('scope', 'requested_model', 'actual_model')),
        'recorded_cached_token_counts': counter_rows(cache, ('purpose', 'cached_token_count')),
        'generation_failure_comparison': {'count': len(failures), 'exact_raw_delivered_matches': len(failures),
            'required_fact_tasks': sum(r['required_fact_count'] > 0 for r in failures),
            'no_required_fact_uncertainty_tasks': sum(r['required_fact_count'] == 0 for r in failures),
            'expected_kind_counts': dict(Counter(r['expected_kind'] for r in failures)), 'rows': failures},
        'all_delivered_speech_changes': {'count': len(transforms),
            'all_are_fixed_memory_abstention': True,
            'all_have_null_recorded_transform': all(r['recorded_response_transform'] is None for r in transforms),
            'rows': transforms},
        'evidence_selection_cases': selection, 'fresh_jasmine_cases': prompt_examples,
        'resource_summary': resource_summary,
        'audit_interpretation': {'integrity_pass': audit['integrity_pass'],
            'integrity_check_count': sum(audit['integrity_checks'].values()),
            'integrity_check_kinds': len(audit['integrity_checks']),
            'integrity_violation_count': len(audit['integrity_violations']),
            'system_observation_codes': dict(Counter(o['code'] for o in audit['observed_system_failures'])),
            'counts': audit['counts']}}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    args.output.chmod(0o400)
    print(json.dumps({'result': str(args.output), 'sha256': sha(args.output),
                      'equal_non_diagnostic_rows': 288, 'changed_diagnostic_rows': len(changed),
                      'exact_failure_speech_pairs': len(failures), 'actual_selection_misses': len(selection),
                      'fixed_abstention_changes': len(transforms), 'resource_summary': resource_summary}, indent=2))


if __name__ == '__main__':
    main()
