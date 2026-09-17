"""Merge preserved independent judgments using explicit root resolutions only."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def load(path):
    return json.loads(path.read_text())


def judgments(paths):
    result = {}
    for path in paths:
        payload = load(path)
        if isinstance(payload, dict):
            payload = payload['judgments']
        for row in payload:
            assert row['id'] not in result, ('duplicate', path, row['id'])
            result[row['id']] = row
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--supplement', action='store_true')
    args = parser.parse_args()
    cases_path = BASE / ('whitespace_followup_cases.json' if args.supplement else 'cases.json')
    cases = load(cases_path)['cases']
    pattern = 'whitespace_followup.json' if args.supplement else 'batch_*.json'
    ap = sorted((BASE / 'review_a').glob(pattern))
    bp = sorted((BASE / 'review_b').glob(pattern))
    a, b = judgments(ap), judgments(bp)
    ids = {c['id'] for c in cases}
    assert set(a) == set(b) == ids, ('review coverage', len(a), len(b), len(ids))
    resolutions_path = BASE / ('whitespace_adjudication_notes.json' if args.supplement else 'adjudication_notes.json')
    resolutions = load(resolutions_path)['cases'] if resolutions_path.exists() else {}
    final, differences = [], []
    for case in cases:
        identifier = case['id']
        x, y = a[identifier], b[identifier]
        resolved = resolutions.get(identifier, {})
        row = dict(x)
        row['review_a'] = x
        row['review_b'] = y
        row['review_basis'] = 'Two separate assistant reviewers, blinded to model identity, routes, latency and runtime review verdicts; root adjudication. Not human validation.'
        for field in ('quality_pass', 'useful_general_help'):
            if x.get(field) != y.get(field):
                assert resolved.get('field') == field or field in resolved.get('overrides', {}), ('unresolved', identifier, field, x.get(field), y.get(field))
                value = (resolved['resolved'] if resolved.get('field') == field else resolved['overrides'][field])
                row[field] = value
                differences.append({'id': identifier, 'field': field, 'review_a': x.get(field),
                                    'review_b': y.get(field), 'resolved': value, 'reason': resolved['reason']})
        # Root can record an independently identified issue while retaining both originals.
        if resolved.get('field') == 'flags':
            row['flags'] = list(dict.fromkeys([*row['flags'], *resolved.get('add', [])]))
        for field, value in resolved.get('overrides', {}).items():
            row[field] = value
        if resolved:
            row['root_resolution'] = resolved
        if not args.supplement and identifier in {'fresh_035','fresh_036','fresh_044','fresh_046','fresh_047'}:
            assert not row['quality_pass'] and row['primary_outcome'] == 'execution_error'
            row['flags'] = list(dict.fromkeys([*row['flags'], 'setup_input_error']))
        final.append(row)
    prefix = 'whitespace_' if args.supplement else ''
    out = BASE / (prefix + 'adjudicated_judgments.json')
    out.write_text(json.dumps(final, indent=2, ensure_ascii=False)+'\n')
    files = ap + bp + [cases_path]
    if resolutions_path.exists():
        files.append(resolutions_path)
    audit = {'created_at': datetime.now(timezone.utc).isoformat(), 'cases': len(cases),
             'quality_agreements': sum(a[i]['quality_pass'] == b[i]['quality_pass'] for i in ids),
             'useful_general_agreements': sum(a[i].get('useful_general_help') == b[i].get('useful_general_help') for i in ids),
             'adjudicated_differences': differences,
             'root_notes': resolutions,
             'reviewer_independence': 'Separate assistant contexts; no access to each other\'s judgments. Reviewer A audited labels before inference; neither authored the cases or changed the candidate.',
             'source_sha256': {str(p.relative_to(BASE)): sha256(p.read_bytes()).hexdigest() for p in files},
             'adjudicated_sha256': sha256(out.read_bytes()).hexdigest()}
    (BASE / (prefix + 'review_agreement.json')).write_text(json.dumps(audit, indent=2)+'\n')
    print(json.dumps({k: v for k, v in audit.items() if k not in {'source_sha256', 'root_notes'}}))


if __name__ == '__main__':
    main()
