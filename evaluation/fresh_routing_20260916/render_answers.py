"""Render final adjudicated deliveries without rerunning inference or scoring."""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def cohort(title, cases_path, rows_path):
    cases = {c['id']: c for c in json.loads(cases_path.read_text())['cases']}
    rows = [json.loads(line) for line in rows_path.read_text().splitlines()]
    out = [f'## {title}', '',
           '| Case | Expected | Raw | Final | Quality | Combined | Seconds |',
           '| --- | --- | --- | --- | ---: | ---: | ---: |']
    for row in rows:
        seconds = f"{row['wall_seconds']:.3f}" if row['wall_seconds'] is not None else '—'
        out.append(f"| {row['id']} | {row['expected_modes'][0]} | {row['raw_mode'] or '—'} | {row['final_mode'] or '—'} | {'pass' if row['quality_pass'] else 'fail'} | {'pass' if row['combined_pass'] else 'fail'} | {seconds} |")
    for row in rows:
        case, judgment = cases[row['id']], row['judgment']
        out.extend(['', f"### {row['id']}", '', '**Request:** ' + case['text'], ''])
        for item in case.get('prior_turns', []):
            out.append(f"Declared prior {item['role']}: {item['content']}")
            out.append('')
        out.append('**Delivered text:**')
        out.append('')
        if row['delivered_text']:
            out.extend('> ' + line for line in row['delivered_text'].splitlines())
        else:
            out.append('*No delivered text.*')
        out.extend(['', f"**Adjudicated quality:** {'pass' if row['quality_pass'] else 'fail'}. {judgment['reason']}", ''])
        if row.get('error'):
            out.append('Recorded error: `' + json.dumps(row['error'], ensure_ascii=False) + '`')
            out.append('')
        out.append('Frozen required components:')
        out.append('')
        out.extend('- ' + component for component in case['rubric']['required_components'])
        if judgment.get('root_resolution'):
            out.extend(['', 'Root resolution: ' + judgment['root_resolution']['reason']])
        out.extend(['', f"Reviewer A quality: {judgment['review_a']['quality_pass']}; reviewer B quality: {judgment['review_b']['quality_pass']}."])
    return out


def main():
    out = ['# Every delivered answer and judgment', '',
           'The original 48 attempts remain separate from the five whitespace-only follow-up attempts. '
           'Quality and final-route agreement are separate; combined requires both. '
           'Times include instrumented complete text-turn processing. Original input errors have no model calls. '
           'Reviewers are separate assistant contexts, not human participants.', '']
    out += cohort('Original frozen collection', BASE/'cases.json', BASE/'per_case.jsonl')
    out += ['', *cohort('Whitespace-only follow-up', BASE/'whitespace_followup_cases.json', BASE/'whitespace_analysis/per_case.jsonl')]
    (BASE/'answers.md').write_text('\n'.join(out)+'\n')
    print('Wrote answers.md with 53 preserved attempts')


if __name__ == '__main__':
    main()
