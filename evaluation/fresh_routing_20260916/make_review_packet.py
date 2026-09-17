"""Seal a completed-row snapshot with routing/model/timing/self-review blinded."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=int, required=True)
    parser.add_argument('--stop', type=int, required=True)
    parser.add_argument('--supplement', action='store_true')
    args = parser.parse_args()
    collection = 'collection_whitespace' if args.supplement else 'collection'
    cases_path = BASE / ('whitespace_followup_cases.json' if args.supplement else 'cases.json')
    data = (BASE / collection / 'run/observations.jsonl').read_bytes()
    rows = []
    for line in data.splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # A live trailing write is not a completed observation.
            break
    cases = json.loads(cases_path.read_text())['cases']
    assert 0 <= args.start < args.stop <= len(rows)
    assert [r['id'] for r in rows] == [c['id'] for c in cases[:len(rows)]]
    packet = []
    for row, case in zip(rows[args.start:args.stop], cases[args.start:args.stop]):
        assert row['case'] == case
        packet.append({'id': row['id'], 'text': case['text'],
                       'declared_prior_turns': case.get('prior_turns', []),
                       'rubric': case['rubric'], 'status': row['status'],
                       'delivered_text': row.get('delivered_text', ''),
                       'execution_failed': row['status'] != 'ok'})
    out = BASE / 'review_packets'
    out.mkdir(exist_ok=True)
    target = out / ('whitespace_followup.json' if args.supplement else f'batch_{args.start:03d}_{args.stop:03d}.json')
    value = {'created_at': datetime.now(timezone.utc).isoformat(),
             'frozen_cases_sha256': sha256(cases_path.read_bytes()).hexdigest(),
             'scope': 'Final delivered answer review. Models, timings, routes, internal review verdicts and raw rejected attempts withheld.',
             'evidence_contract': 'Empty personal store. Current assertions and benign nonpersonal context may support answers; prior personal-value history and assistant guesses do not authorize personal facts. Quoted fictional text may be edited without endorsing it.',
             'rubric_conventions': json.loads(cases_path.read_text())['rubric_conventions'],
             'cases': packet}
    with target.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(target, len(packet), sha256(target.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
