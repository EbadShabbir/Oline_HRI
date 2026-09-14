#!/usr/bin/env python3
"""Derive method counts from the sealed run; no answer scoring or inference."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def counts(counter, names):
    return [{**dict(zip(names, key)), 'count': value} for key, value in sorted(counter.items())]


def main():
    output = BASE / 'collection_audit_findings_v1.json'
    assert not output.exists()
    audit = read(BASE / 'collection_audit_v1.json')
    receipt = read(BASE / 'collection_audit_v1_command.json')
    assert audit['integrity_pass'] and not audit['integrity_violations']
    assert audit['integrity_checks']['current_source_hash'] == audit['integrity_checks']['frozen_source_hash'] == 41
    statuses, models, routes, constraints, cached, snapshot_results, probes = (Counter() for _ in range(7))
    telemetry, cache_probes = [], []
    for fragment in audit['resource_fragments']:
        directory = Path(fragment['fragment'])
        telemetry.extend(rows(directory / 'telemetry.jsonl'))
        for row in rows(directory / 'answers.jsonl'):
            scope = 'scored' if row['checkpoint_id'] else 'setup'
            statuses[scope, row['status']] += 1
            if scope == 'scored':
                route = row['route']['decision']
                routes[route['memory_required'], route['model_size']] += 1
                constraints[str(row.get('answer_constraint'))] += 1
            for check in row['snapshot_checks']:
                snapshot_results[check['current']] += 1
            for call in row['calls']:
                cached[call['purpose'], bool(call.get('raw_chat_payload', {}).get('prompt_eval_cached_count'))] += 1
                if call['purpose'] == 'generation':
                    models[scope, call['requested_model'], call['actual_model']] += 1
        for event in rows(directory / 'events.jsonl'):
            if event.get('event') == 'operation' and event['op']['op'] in ('cache_probe', 'snapshot_probe'):
                probes[event['op']['op'], event['snapshot_current']] += 1
                if event['op']['op'] == 'cache_probe':
                    cache_probes.append({'operation_id': event['op']['id'],
                        'recorded_cache_implementation': event['existing_retrieval_cache'],
                        'first_second_results_equal': event['first'] == event['second'],
                        'retained_snapshot_records': len(event['retained_snapshot'])})
    frozen = read(BASE / 'frozen_v2/freeze.json')
    result = {'created_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'Full first-repair integrity/method findings; no semantic scoring or inference.',
        'command': [sys.executable, str(Path(__file__).resolve())], 'script_sha256': sha(Path(__file__)),
        'input_sha256': {str(BASE / name): sha(BASE / name) for name in
                        ('collection_audit_v1.json', 'collection_audit_v1_command.json', 'run_v1/seal.json', 'frozen_v2/seal.json')},
        'source_certificate': {'verified_at': receipt['finished_at'], 'current_runtime_files_matched': 41,
            'frozen_runtime_files_matched': 41, 'all_match_before_subsequent_source_change': True,
            'frozen_source_sha256': frozen['source_sha256'],
            'note': 'This certifies the completed audit time, before root was notified that a second repair could proceed. Later source changes do not alter this sealed first-run evidence.'},
        'integrity_check_total': sum(audit['integrity_checks'].values()),
        'integrity_check_kinds': len(audit['integrity_checks']), 'integrity_violations': audit['integrity_violations'],
        'counts': audit['counts'], 'workload': audit['workload'], 'branches': audit['branches'],
        'system_observations': audit['observed_system_failures'],
        'answer_status_counts': counts(statuses, ('scope', 'status')),
        'actual_generation_counts': counts(models, ('scope', 'requested_model', 'actual_model')),
        'scored_route_counts': counts(routes, ('memory_required', 'model_size')),
        'recorded_answer_constraint_counts': dict(constraints),
        'answer_snapshot_checks': {str(k): v for k, v in snapshot_results.items()},
        'authored_probe_results': counts(probes, ('operation', 'snapshot_current')),
        'cache_probes': cache_probes,
        'backend_prompt_cache_activity': counts(cached, ('purpose', 'positive_cached_token_count')),
        'history_exposure_counts': audit['history_exposure']['counts'],
        'history_exposure_interpretation': audit['history_exposure']['interpretation'],
        'resources': {'fragments': len(audit['resource_fragments']), 'telemetry_samples': len(telemetry),
            'max_sampled_temperature_c': max(max(s['temperatures_c'].values()) for s in telemetry),
            'max_sampled_ram_used_mb': max(s['ram']['used_mb'] for s in telemetry),
            'ram_total_mb': sorted({s['ram']['total_mb'] for s in telemetry}),
            'max_sampled_swap_used_mb': max(s['swap']['used_mb'] for s in telemetry),
            'runtime_guard_or_cleanup_observations': [o for o in audit['observed_system_failures'] if o['stage'] == 'resource'],
            'limits': 'Sampled RAM use is not MemAvailable. Resource checks do not prove unobserved instantaneous values.'},
        'limits': ['Targeted four-scenario matched development regression, not held-out accuracy.',
                   'Snapshot freshness probes retain old results but do not inject them into production generation.',
                   'Production rebuilds retrieval matrices; no persistent vector cache exists. Backend cached-token counts show activity, not source causality.',
                   'Explicit location/relationship constraints remain distinct from unconstrained generation.',
                   'Process restart and controlled logical expiry; no OS/Ollama restart, power-loss, or spoken-performance claim.',
                   'Blinded answer judgment and human validation remain separate from integrity; no reviewer contacted.']}
    output.write_text(json.dumps(result, indent=2) + '\n')
    output.chmod(0o400)
    print(json.dumps({'output': str(output), 'sha256': sha(output),
                      'current_source_files_certified': 41, 'checks': result['integrity_check_total'],
                      'cache_repeat_results_all_equal': all(p['first_second_results_equal'] for p in cache_probes)}, indent=2))


if __name__ == '__main__':
    main()
