"""Prepare only unseen blinded variants from a validated completed session prefix."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'src'))
import analyze_complete_system as base
import analyze_v2_recorded as recorded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', type=int, required=True)
    parser.add_argument('--completed-prefix', type=int, required=True)
    args = parser.parse_args()
    if not 2 <= args.cohort <= 9 or not 3 <= args.completed_prefix <= 9:
        raise ValueError('invalid cohort or prefix')
    directory = Path(__file__).resolve().parent
    reviews = directory / 'reviews_v2'
    freeze_path = directory / 'frozen_v2/freeze.json'
    workload_path = directory / 'frozen_v2/workload.json'
    frozen = recorded.validate_recorded_freeze(freeze_path)
    slots = base.session_slots(frozen['counterbalanced_arm_orders'])
    all_rows, sessions = [], []
    for name, arm, repetition in slots[:args.completed_prefix]:
        session, rows = recorded.inspect_recorded_session(
            workload_path, freeze_path, directory / 'run_v2_resumed', name)
        if not session['valid'] or not session['complete']:
            raise ValueError(f'incomplete or invalid session: {name}: {session["errors"]}')
        all_rows.extend(rows)
        sessions.append({key: session[key] for key in
                         ('directory', 'valid', 'complete', 'attempted', 'delivered', 'artifact_sha256')})
    seed = base.read_json(reviews / 'private_seed.json')['private_blinding_seed']
    worksheet, mapping = base.make_blinded_review(base.read_json(workload_path), all_rows, seed)
    prior = set()
    for index in range(1, args.cohort):
        for row in base.read_jsonl(reviews / f'cohort_{index}.jsonl'):
            if row['review_id'] in prior:
                raise ValueError('earlier review cohorts overlap')
            prior.add(row['review_id'])
    observed = {row['review_id'] for row in worksheet}
    if not prior.issubset(observed):
        raise ValueError('prior reviewed variants missing from completed prefix')
    fresh = [row for row in worksheet if row['review_id'] not in prior]
    fresh_ids = {row['review_id'] for row in fresh}
    fresh_mapping = [row for row in mapping if row['review_id'] in fresh_ids]
    base.write_new(reviews / f'cohort_{args.cohort}.jsonl', fresh, lines=True)
    base.write_new(reviews / f'private_mapping_{args.cohort}.jsonl', fresh_mapping, lines=True)
    base.write_new(reviews / f'cohort_{args.cohort}_provenance.json', {
        'recorded_at': datetime.now(timezone.utc).isoformat(),
        'completed_prefix': args.completed_prefix, 'observed_attempts': len(all_rows),
        'all_unique_entries': len(worksheet), 'already_assigned_entries': len(prior),
        'new_unique_entries': len(fresh), 'completed_sessions': sessions,
        'builder_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope': 'Only completed sessions inspected; unseen exact response/evidence identities only. No scoring or raw-data mutation.'})
    print(json.dumps({'cohort': args.cohort, 'completed_attempts': len(all_rows),
                      'new_review_entries': len(fresh), 'all_unique_entries': len(worksheet)}))


if __name__ == '__main__':
    main()
