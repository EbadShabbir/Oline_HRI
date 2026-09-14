#!/usr/bin/env python3
"""Bounded partial integrity review; no model requests or answer scoring."""
import ast
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import traceback

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[1]
AUDITOR = BASE / 'audit_repair_collection.py'
EXPECTED_AUDITOR_SHA256 = '9fa45da1bf11cbad582693c74dd12fc24be2254a309e3f13ae566a5c7b59d56f'
BRANCHES = ('cm01_correction', 'cm01_deletion')


def main():
    output = BASE / 'audit_method_review_v1.json'
    assert not output.exists(), 'preserve previous output'
    spec = importlib.util.spec_from_file_location('repair_auditor', AUDITOR)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.digest(AUDITOR) == EXPECTED_AUDITOR_SHA256
    freeze, run = BASE / 'frozen_v2', BASE / 'run_v1'
    audit = m.Audit()
    failure = None
    info = {}
    try:
        audit.seal(freeze)
        frozen = m.read_json(freeze / 'freeze.json')
        runtime = m.read_json(freeze / 'runtime.json')
        ledger = m.read_json(freeze / 'expected_ledger.json')
        counts = m.workload_counts(runtime, ledger)
        audit.check(counts['planned_checkpoints'] == 96 and counts['independent_databases'] == 12,
                    'full_frozen_workload_96_checkpoints_12_branches', freeze)
        baseline = REPO / 'evaluation/changing_memory_20260914/frozen_v1'
        baseline_frozen = m.read_json(baseline / 'freeze.json')
        baseline_expected = {r['checkpoint_id']: r for r in m.read_json(baseline / 'expected_ledger.json')['checkpoints']}
        baseline_branches = {b['branch_id']: b for b in m.read_json(baseline / 'runtime.json')['branches']}
        for entry in ledger['checkpoints']:
            audit.check(entry == baseline_expected[entry['checkpoint_id']], 'exact_original_expected_object', entry['checkpoint_id'])
        for branch in runtime['branches']:
            audit.check(branch == baseline_branches[branch['branch_id']], 'exact_original_branch_schedule', branch['branch_id'])
        matching = ('config', 'models', 'ollama_version', 'embedding_assets', 'packages', 'python',
                    'generation_seed', 'device_policy', 'routing_policy', 'retain_large_model', 'logical_clock')
        for name in matching:
            audit.check(frozen[name] == baseline_frozen[name], 'unchanged_non_source_runtime_condition', name)
        audit.check(frozen['source_sha256']['scripts/run_changing_memory.py'] ==
                    baseline_frozen['source_sha256']['scripts/run_changing_memory.py'],
                    'unchanged_collection_harness', freeze)
        info['full_planned_workload'] = counts
        info['matching_baseline_runtime_conditions'] = list(matching)
        info['changed_production_source'] = sorted(k for k, v in frozen['source_sha256'].items()
                                                 if baseline_frozen['source_sha256'].get(k) != v)
        tree = ast.parse(AUDITOR.read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'audit_collection')
        # Reuse the exact existing source checks and branch-audit statements.
        # Deliberately omit the global run seal/finish requirements: run is active.
        assert ast.unparse(fn.body[18]).startswith('(found_checkpoints, all_database_ids,')
        assert ast.unparse(fn.body[26]).startswith('finish_path =')
        chosen = {**runtime, 'branches': [b for b in runtime['branches'] if b['branch_id'] in BRANCHES]}
        planned = {r['checkpoint_id']: r for r in ledger['checkpoints']
                   if f"{r['scenario_id']}_{r['branch']}" in BRANCHES}
        assert len(chosen['branches']) == 2 and len(planned) == 17
        for branch in chosen['branches']:
            assert (run / branch['branch_id'] / 'seal.json').is_file(), 'only sealed branches may be inspected'
        env = dict(vars(m), audit=audit, frozen=frozen, runtime=chosen, planned=planned,
                   freeze_dir=freeze, run_dir=run, repository=REPO,
                   workload={'scheduled_segments': 4, 'independent_databases': 2})
        statements = fn.body[11:18] + fn.body[18:26] + [fn.body[28]]
        exec(compile(ast.Module(body=statements, type_ignores=[]), str(AUDITOR), 'exec'), env)
        info['subset_counts'] = dict(audit.counts)
        info['branches'] = audit.branches
        info['resource_fragments'] = audit.resources
        info['history_exposure_counts'] = {k: dict(v) for k, v in audit.history_counts.items()}
        info['actual_model_requests'] = [{'purpose': key[0], 'model': key[1], 'count': count}
                                        for key, count in sorted(audit.models.items())]
    except BaseException as error:
        failure = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    result = {'created_at': datetime.now(timezone.utc).isoformat(), 'partial': True,
              'scope': 'Sealed cm01 correction and deletion only; full 96-checkpoint final audit remains required.',
              'inference_performed': False, 'semantic_scoring_performed': False,
              'no_live_unsealed_branches_read': True, 'reviewer': 'assistant /root/runtime_audit',
              'command': [sys.executable, str(Path(__file__).resolve())],
              'script_sha256': m.digest(__file__), 'auditor_sha256': m.digest(AUDITOR),
              'input_seal_sha256': {str(p): m.digest(p) for p in [freeze / 'seal.json']
                                   + [run / b / 'seal.json' for b in BRANCHES]},
              'subset_integrity_pass': failure is None and not audit.violations,
              'exception': failure, 'integrity_checks': dict(audit.checks),
              'integrity_violations': audit.violations, 'system_observations': audit.observations,
              'findings': info,
              'method_limits': ['Targeted development regression selected after baseline failures, not held-out accuracy.',
                                'History remains available to routing but the repaired generator excludes prior turns on personal-memory requests.',
                                'Location extraction can constrain model speech; this must be reported separately from unconstrained generation.',
                                'Logical expiry, application-process restart, and text only; no power-loss or spoken-performance claim.',
                                'Human validation pending; no answer judgments made by this audit.']}
    output.write_text(json.dumps(result, indent=2) + '\n')
    output.chmod(0o400)
    print(json.dumps({'output': str(output), 'partial': True, 'subset_integrity_pass': result['subset_integrity_pass'],
                      'checks': sum(audit.checks.values()), 'violations': len(audit.violations),
                      'exception': failure, 'counts': info.get('subset_counts'),
                      'system_observations': audit.observations}, indent=2))
    return 0 if result['subset_integrity_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
