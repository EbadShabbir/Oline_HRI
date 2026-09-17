"""Explicit exploratory valid-input view; never pool the two sessions' latency."""
from hashlib import sha256
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def main():
    primary_path = BASE/'per_case.jsonl'
    followup_path = BASE/'whitespace_analysis/per_case.jsonl'
    original, followup = read_rows(primary_path), read_rows(followup_path)
    corrections = {row['id']: row for row in followup}
    eligible = {item['id'] for item in json.loads((BASE/'whitespace_eligibility.json').read_text())['checks'] if item['eligible']}
    assert set(corrections) == eligible and len(original) == 48 and len(followup) == 5
    joined, provenance = [], []
    for row in original:
        replacement = corrections.get(row['id'])
        if replacement:
            assert row['status'] == 'error' and not row['calls']
            assert replacement['status'] == 'ok'
        joined.append(replacement or row)
        provenance.append({'id': row['id'], 'cohort': 'whitespace_followup' if replacement else 'original',
                           'original_error_preserved': bool(replacement)})
    value = {
        'scope': 'Exploratory corrected-input view only:43 original valid-input rows plus5 normalized follow-up rows. Not the original preregistered result; no pooled latency.',
        'logical_cases': 48, 'original_attempts_preserved': 48, 'followup_attempts_preserved': 5,
        'latency_pooled': False, 'source_cohort_by_case': provenance,
        'counts': {field: sum(row[field] for row in joined) for field in ('raw_match','final_match','quality_pass','combined_pass')},
        'per_mode': {},
        'source_sha256': {str(path.relative_to(BASE)):sha256(path.read_bytes()).hexdigest() for path in (primary_path,followup_path)},
    }
    for mode in ('none','optional','required','clarify'):
        rows = [row for row in joined if row['expected_modes'] == [mode]]
        value['per_mode'][mode] = {'count':len(rows), **{field:sum(row[field] for row in rows) for field in ('raw_match','final_match','quality_pass','combined_pass')}}
    (BASE/'exploratory_corrected_input.json').write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(value['counts']))


if __name__ == '__main__':
    main()
