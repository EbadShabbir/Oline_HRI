"""Independent report checks; no renderer imports or semantic answer grading."""
import datetime
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT / 'evaluation/independent_retrieval_20260913'
CATEGORIES = dict(zip(
    ('Direct recall', 'Paraphrased recall', 'Multi-fact personal', 'General without memory need',
     'Unknown or conflicting', 'Lifecycle or authorization', 'Overall'),
    ('direct_personal_recall', 'paraphrased_personal_recall', 'multi_fact_personal', 'general_no_memory',
     'unknown_or_conflicting', 'lifecycle_or_authorization', 'overall')))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def seal_check(directory):
    seal = read(directory / 'seal.json')['sha256']
    actual = {str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file() and p.name != 'seal.json'}
    assert set(seal) == actual
    for name, value in seal.items():
        assert sha(directory / name) == value


def tables(text):
    heading = ''
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith('## '):
            heading = line[3:]
        if line.startswith('| ') and i + 1 < len(lines) and lines[i + 1].startswith('| ---'):
            header = [v.strip() for v in line.strip('|').split('|')]
            rows = []
            for row in lines[i + 2:]:
                if not row.startswith('| '):
                    break
                rows.append([v.strip() for v in row.strip('|').split('|')])
            yield heading, header, rows


def interval(group, metric, factor=1, decimals=3):
    v = group['differences'][metric + '_difference']
    return (f"{factor*v['mean']:+.{decimals}f} "
            f"[{factor*v['bootstrap_95_low']:+.{decimals}f}, {factor*v['bootstrap_95_high']:+.{decimals}f}]")


def main():
    report_dir = EXP / 'report_reviewed_v3'
    analysis_dir = EXP / 'analysis_reviewed_v1'
    numeric_dir = EXP / 'numeric_audit_v1'
    for directory in (report_dir, EXP / 'report_reviewed_v1', EXP / 'report_reviewed_v2', analysis_dir, numeric_dir):
        seal_check(directory)
    old = (EXP / 'report_reviewed_v1/failed_renderer_source.py').read_bytes()
    v2 = (EXP / 'report_reviewed_v2/report_source.py').read_bytes()
    new = (report_dir / 'report_source.py').read_bytes()
    before = b'    rewrites = audit.get("generation_request_rewrites", [])'
    after = b'    rewrites = summary["audit"].get("generation_request_rewrites", [])'
    assert old.count(before) == 1 and old.replace(before, after) == v2
    start = new.index(b'    stop_causes = Counter(')
    end = new.index(b'    audit = summary["audit"]', start)
    assert new[:start] + new[end:] == v2
    assert hashlib.sha256(old).hexdigest() == '4a870e2bd887d06679772e9879d8e6e2275a506d2297439084e6f47d859183bc'
    assert new == (ROOT / 'scripts/report_independent_retrieval.py').read_bytes()
    analysis = read(analysis_dir / 'analysis.json')
    numeric = read(numeric_dir / 'numeric_audit.json')
    assert numeric['passed'] and numeric['checks'] == 99319 and not numeric['errors']
    assert numeric['provenance']['analysis_seal_sha256'] == sha(analysis_dir / 'seal.json')
    overall = {(r['model'], r['policy']): r for r in analysis['overall']}
    category = {(r['model'], r['category'], r['policy']): r for r in analysis['by_category']}
    pairs = {(r['model'], r['category'], r['comparison']): r for r in analysis['paired']}
    known = {(r['model'], r['policy']): r for r in numeric['known_personalization']}
    report = (report_dir / 'report.md').read_text()
    detail = (report_dir / 'tables.md').read_text()
    checks = 0
    checked_rows = {}

    def equal(actual, expected):
        nonlocal checks
        checks += 1
        assert actual == expected, (actual, expected)

    for heading, header, rows in tables(report):
        if header[0:3] == ['Generator', 'Policy', 'Task success']:
            for values in rows:
                model, policy = values[:2]
                g = overall[model, policy]; k = known[model, policy]
                expected = [model, policy, f"{g['task_success']}/{g['attempts']}",
                            f"{k['success']}/{k['attempts']}", str(k['cautious_misses']),
                            f"{g['unnecessary_retrievals']}/{g['no_memory_needed_authorized']}",
                            *[f"{g['timing']['request_s'][v]:.3f}" for v in ('mean', 'median', 'p95')], str(g['failures'])]
                equal(values, expected)
            checked_rows['overall_summary'] = len(rows)
        elif header[:2] == ['Generator', 'Category']:
            for values in rows:
                model, label = values[:2]
                expected = [model, label]
                for policy in ('OFF', 'ALWAYS', 'SELECTIVE'):
                    g = category[model, CATEGORIES[label], policy]
                    expected.append(f"{g['task_success']}/{g['attempts']}; {g['timing']['request_s']['mean']:.3f} s")
                equal(values, expected)
            checked_rows['category_summary'] = len(rows)
        elif header[:2] == ['Generator', 'Left−right']:
            for values in rows:
                g = pairs[values[0], 'overall', values[1]]
                d = g['request_mean_success_direction']
                equal(values[2:], [interval(g, 'task_success', 100, 1), interval(g, 'request_s'),
                    f"{d.get('left_higher',0)} / {d.get('right_higher',0)} / {d.get('equal',0)}"])
            checked_rows['overall_paired'] = len(rows)
        elif header[:3] == ['Generator', 'Policy', 'Classifier calls']:
            for values in rows:
                g = overall[values[0], values[1]]
                expected = [str(g['classifier_calls']), f"{g['timing']['selection_s']['mean']:.3f}",
                    str(g['retrieval_attempts']), f"{g['timing']['retrieval_s']['mean']:.3f}",
                    f"{g['supplied_evidence_coverage']*100:.1f}%", *[str(g[k]) for k in
                    ('irrelevant_inspected', 'irrelevant_supplied', 'unsupported_claim', 'unsupported_personal_claim')]]
                equal(values[2:], expected)
            checked_rows['overall_retrieval'] = len(rows)
    for heading, header, rows in tables(detail):
        if not heading.startswith('qwen3:'):
            continue
        model = heading.split(': ', 1)[0]
        if header[:3] == ['Category', 'Policy', 'Success']:
            for values in rows:
                g = category[model, CATEGORIES[values[0]], values[1]]
                equal(values[2:], [f"{g['task_success']}/{g['attempts']}",
                    *[str(g[k]) for k in ('unsupported_claim', 'unsupported_personal_claim', 'abstained', 'failures')],
                    *[f"{g['timing']['request_s'][k]:.3f}" for k in ('mean','median','p95')]])
            checked_rows[heading] = len(rows)
        elif header[:2] == ['Category', 'Left−right']:
            for values in rows:
                g = pairs[model, CATEGORIES[values[0]], values[1]]
                equal(values[2:], [f"{g['paired_requests']} / {g['paired_attempts']}",
                    interval(g, 'task_success', 100, 1), interval(g, 'request_s'), interval(g, 'unnecessary_retrievals'),
                    f"{g['quality_pairs'].get('left_only',0)} / {g['quality_pairs'].get('right_only',0)}"])
            checked_rows[heading] = len(rows)
        elif header[:3] == ['Category', 'Policy', 'Retrievals']:
            for values in rows:
                g = category[model, CATEGORIES[values[0]], values[1]]
                percentages = [('n/a' if g[k] is None else f"{g[k]*100:.1f}%") for k in ('retrieved_evidence_coverage','supplied_evidence_coverage')]
                eligible = g['no_memory_needed_authorized']
                equal(values[2:], [str(g['retrieval_attempts']), f"{g['unnecessary_retrievals']}/{eligible}" if eligible else 'n/a',
                    *percentages, *[str(g[k]) for k in ('irrelevant_inspected','irrelevant_source_candidates','irrelevant_supplied')]])
            checked_rows[heading] = len(rows)
    equal(checked_rows['overall_summary'],6); equal(checked_rows['category_summary'],12)
    equal(checked_rows['overall_paired'],6); equal(checked_rows['overall_retrieval'],6)
    for model in ('qwen3:0.6b','qwen3:1.7b'):
        equal(checked_rows[f'{model}: answer quality and complete request time'],18)
        equal(checked_rows[f'{model}: paired differences'],21)
        equal(checked_rows[f'{model}: retrieval, relevance and disclosure by category'],18)
    for phrase in ('864/864', '856 delivered answers and 8 retained failures', '24 calls covering 2 distinct questions',
                   'semantic neutrality is not established', 'Human validation remains pending',
                   'Equal observed totals do not establish equivalent quality', 'eight fictional clusters',
                   '26 physical request-bearing fragments', '35 rejected admission records',
                   'Failure classes: KeyboardInterrupt: 8', 'including its selection costs',
                   'SafetyGateError: available memory crossed the runtime floor (8)',
                   'It is distinct from audited authorization violations'):
        equal(phrase in report,True)
    for name, text in (('report.md',report),('tables.md',detail)):
        for _, target in re.findall(r'\[([^\]]+)\]\(([^)]+)\)', text):
            if not target.startswith(('http:','https:','#')):
                equal((report_dir / target.split('#')[0]).exists(),True)
    result = {
        'approved':True, 'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'reviewer':'independent assistant /root/audit_design', 'human_validation':'pending',
        'scope':'Final rendered metric tables and interpretation against independently audited analysis; no new semantic grading.',
        'checks':checks, 'table_rows_verified':checked_rows, 'errors':[],
        'renderer_change':'From retained failed v1 to successful v2, exactly one line replaces an unbound local audit with summary["audit"] in the approved helper-disclosure paragraph. From v2 to final v3, one contiguous insertion counts sealed session guard causes and clarifies the forbidden_disclosure flag. No other code changed; no metric, scoring, grouping, or statistical logic changed.',
        'interpretation_findings':[
            'Small generator preserves observed known-authorized success totals but adds mean request time; no equivalence claim is made.',
            'Large generator saves observed mean time with one fewer known success; broader task success and category results remain separately reported.',
            'Large SELECTIVE p95 is worse (30.457 versus20.657 seconds); category tables retain paraphrased recall6/24 and unknown/conflict SELECTIVE9/24 small and6/24 large versus OFF21/24 and23/24.',
            'All attempts include eight interruptions; physical-fragment cold starts and rejected-admission costs are explicitly distinguished.',
            'Repeated attempts are dependent; paired category contrasts use frozen whole-scenario bootstrap intervals without noninferiority/equivalence inference.',
            'Evidence-dependent helper rewrites and possible timing/semantic effects are disclosed; unsupported truth judgments remain distinct from runtime grounding.',
        ],
        'documentation_clarification':'The final report faithfully reproduces request-row KeyboardInterrupt labels and explains the corresponding session SafetyGateError available-memory-floor cause. It distinguishes rubric-prohibited content from actual authorization violations.',
        'hashes': {str(p.relative_to(ROOT)):sha(p) for p in (
            Path(__file__), report_dir/'seal.json', report_dir/'report.md', report_dir/'tables.md',report_dir/'report_source.py',
            report_dir/'review_provenance.json', EXP/'report_reviewed_v1/seal.json', EXP/'report_reviewed_v2/seal.json',
            analysis_dir/'seal.json',analysis_dir/'analysis.json',numeric_dir/'seal.json',numeric_dir/'numeric_audit.json')},
    }
    output=EXP/'reviews/final_report_review_v1.json'
    with output.open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
    output.chmod(0o444)
    print(json.dumps({'approved':True,'checks':checks,'path':str(output),'sha256':sha(output)}))


if __name__ == '__main__':
    main()
