"""Audit text duplication against available local development/evaluation JSON.

This checks wording, not conceptual novelty or unknown model pretraining data.
It never runs a classifier or model on the new cases.
"""
from collections import Counter
import argparse
from difflib import SequenceMatcher
from hashlib import sha256
import json
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]


def normalize(value):
    return ' '.join(re.findall(r"\w+", value.lower()))


def prompts(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {'text', 'prompt', 'user_text', 'request'} and isinstance(child, str):
                yield child
            elif isinstance(child, (dict, list)):
                yield from prompts(child)
    elif isinstance(value, list):
        for child in value:
            yield from prompts(child)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', type=Path, default=BASE / 'authoring/cases.json')
    parser.add_argument('--output', type=Path, default=BASE / 'novelty_audit.json')
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text())['cases']
    previous = {}
    files = {}
    errors = []
    for area in ('evaluation', 'tmp', 'src/oline_hri'):
        for path in (ROOT / area).rglob('*.json'):
            if BASE in path.parents or path.stat().st_size > 20_000_000:
                continue
            if not any(word in path.name.lower() for word in
                       ('case', 'corpus', 'training', 'development', 'regression',
                        'workload', 'suite', 'fictional', 'paraphrase')):
                continue
            try:
                data = path.read_bytes()
                values = list(prompts(json.loads(data)))
            except (ValueError, OSError) as exc:
                errors.append({'path': str(path.relative_to(ROOT)), 'error': str(exc)})
                continue
            if values:
                files[str(path.relative_to(ROOT))] = sha256(data).hexdigest()
            for text in values:
                normalized = normalize(text)
                previous.setdefault(normalized, set()).add(str(path.relative_to(ROOT)))
    rows = []
    for case in cases:
        normalized = normalize(case['text'])
        best, best_score = None, 0.0
        for text in previous:
            # Impossible to exceed the reporting threshold at this length ratio.
            if min(len(text), len(normalized)) / max(len(text), len(normalized), 1) < .65:
                continue
            score = SequenceMatcher(None, normalized, text, autojunk=False).ratio()
            if score > best_score:
                best, best_score = text, score
        rows.append({'id': case['id'], 'exact_match': normalized in previous,
                     'maximum_character_similarity': best_score,
                     'nearest_normalized_text': best,
                     'nearest_source_files': sorted(previous.get(best, [])),
                     'near_match_for_manual_review': best_score >= .85})
    result = {'scope': 'Available named case/training/workload JSON wording audit; not a semantic or pretraining novelty guarantee.',
              'corpus_sha256': sha256(args.cases.read_bytes()).hexdigest(),
              'case_count': len(cases), 'expected_modes': dict(Counter(c['expected_modes'][0] for c in cases)),
              'within_corpus_unique_normalized_texts': len({normalize(c['text']) for c in cases}),
              'prior_unique_prompts': len(previous), 'prior_file_sha256': files,
              'read_errors': errors, 'rows': rows}
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k not in {'rows', 'prior_file_sha256'}}))
    print(json.dumps({'flagged': [r for r in rows if r['exact_match'] or r['near_match_for_manual_review']]}))


if __name__ == '__main__':
    main()
