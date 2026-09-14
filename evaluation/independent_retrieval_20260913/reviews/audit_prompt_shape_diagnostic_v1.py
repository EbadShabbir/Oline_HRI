"""Independent input-only diagnosis; never reads answers or review mappings."""
import ast
import collections
import datetime
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from typing import Optional

ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT / 'evaluation/independent_retrieval_20260913'
FREEZE = EXP / 'frozen_v1'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def main():
    freeze = read(FREEZE / 'freeze.json')
    source = ROOT / 'src/oline_hri/conversation.py'
    assert digest(source) == freeze['source_sha256']['src/oline_hri/conversation.py']
    needed = {
        '_HOW_DO_I_KNOW_PATTERN', '_DIRECT_RELATIONSHIP_PERSON',
        '_DIRECT_RELATIONSHIP_QUERY_PATTERNS', '_CHRONOLOGY_SOURCE_CUE_PATTERN',
        '_direct_relationship_query_person', '_memory_grounded_request',
    }
    nodes = []
    found = set()
    for node in ast.parse(source.read_text()).body:
        names = {node.name} if isinstance(node, ast.FunctionDef) else {
            target.id for target in node.targets if isinstance(target, ast.Name)
        } if isinstance(node, ast.Assign) else set()
        if names & needed:
            nodes.append(node)
            found.update(names & needed)
    assert found == needed
    namespace = dict(re=re, unicodedata=unicodedata, Optional=Optional)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
    normalize = namespace['_memory_grounded_request']
    finish = read(EXP / 'run_v9/batch_finish.json')
    shapes = collections.Counter()
    formats = collections.Counter()
    mismatches = []
    rewrites = []
    flagged = []
    seen = set()
    total = 0
    supplied_count = 0
    http_verified = 0
    for session in finish['sessions']:
        directory = Path(session['directory'])
        for line in (directory / 'observations.jsonl').read_text().splitlines():
            row = json.loads(line)
            key = (row['slot'], row['case']['id'])
            assert key not in seen
            seen.add(key)
            for call in row['calls']:
                if call['purpose'] != 'generation':
                    continue
                total += 1
                prompt = row['case']['prompt']
                messages = call['messages']
                roles = [m['role'] for m in messages]
                shapes[','.join(roles)] += 1
                assert roles in (['system', 'user'], ['system', 'system', 'user'])
                content = messages[-1]['content']
                supplied = row['adapter']['supplied_ids']
                supplied_count += bool(supplied)
                expected = normalize(prompt) if supplied else prompt
                if supplied:
                    assert content.count('\nCURRENT_USER_REQUEST=') == 1
                    current, tailpos = json.JSONDecoder().raw_decode(content.split('\nCURRENT_USER_REQUEST=', 1)[1])
                    assert content.split('\nCURRENT_USER_REQUEST=', 1)[1][tailpos:].startswith('\nRESPONSE_RULE=')
                    records, _ = json.JSONDecoder().raw_decode(content.split('\nPERSONAL_MEMORY_DATA=', 1)[1])
                    assert [r['id'] for r in records['records']] == supplied
                    formats['memory_envelope'] += 1
                elif content.startswith('APPLICATION_REQUEST='):
                    current, _ = json.JSONDecoder().raw_decode(content[len('APPLICATION_REQUEST='):])
                    formats['application_envelope'] += 1
                else:
                    current = content
                    formats['plain_request'] += 1
                if current != expected:
                    mismatches.append({'slot': row['slot'], 'case_id': row['case']['id'], 'observed': current, 'expected': expected})
                if prompt not in content:
                    flagged.append(f"slot_{row['slot']:02d}:{row['case']['id']}: generation contains prior history or unexpected message roles")
                if current != prompt:
                    rewrites.append({
                        'slot': row['slot'], 'case_id': row['case']['id'],
                        'model': row['model'], 'policy': row['policy'], 'repetition': row['repetition'],
                        'original_request': prompt, 'actual_current_request': current,
                        'roles': roles, 'supplied_ids': supplied,
                        'messages_sha256': hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest(),
                        'raw_artifact': str(directory / 'observations.jsonl'),
                    })
                wire_messages = json.loads(json.dumps(messages))
                for message in wire_messages:
                    for ordinal, identifier in enumerate(supplied, start=1):
                        message['content'] = message['content'].replace(identifier, f'memory_ref_{ordinal}')
                http = [h for h in row['http_calls'] if h['endpoint'] == '/api/chat' and h['body']['messages'] == wire_messages]
                assert len(http) == 1
                http_verified += 1
    old_audit = read(EXP / 'analysis_blind_v1/audit.json')
    assert sorted(flagged) == sorted(old_audit['errors'])
    assert len(seen) == total == http_verified == 864
    assert len(rewrites) == len(flagged) == 24
    assert not mismatches
    original_sources = {name: digest(ROOT / name) == value for name, value in freeze['source_sha256'].items()}
    assert len(original_sources) == 44 and all(original_sources.values())
    result = {
        'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'review_type': 'independent assistant input/provenance audit; no semantic grading; human validation pending',
        'finding': 'All 24 reported prompt-shape errors are caused solely by the original-prompt substring predicate rejecting exact frozen evidence-dependent current-request normalization. No prior conversation roles or current-request mismatches were found.',
        'frozen_conversation_sha256': digest(source),
        'frozen_adapter_sha256': digest(ROOT / 'scripts/independent_retrieval_adapter.py'),
        'diagnostic_source_sha256': digest(Path(__file__)),
        'analysis_v1_audit_sha256': digest(EXP / 'analysis_blind_v1/audit.json'),
        'final_run_seal_sha256': digest(EXP / 'run_v9/seal.json'),
        'original_sources_unchanged': original_sources,
        'attempts': len(seen), 'generation_inputs': total, 'matching_actual_http_inputs': http_verified,
        'message_role_counts': dict(shapes), 'request_format_counts': dict(formats),
        'generation_inputs_with_supplied_evidence': supplied_count,
        'http_verification_scope': 'Exact messages after the frozen Ollama client request-local ordered memory_ref_N pseudonym substitution; all roles and remaining content unchanged.',
        'exact_current_request_mismatches': mismatches,
        'evidence_dependent_current_request_rewrites': rewrites,
        'frozen_source_basis': [
            'independent_retrieval_adapter.py:269-285 constructs a fresh Conversation for each one-use adapter send.',
            'independent_retrieval_adapter.py:287-289 rejects nonempty routing history.',
            'conversation.py:1287-1291 builds CURRENT_USER_REQUEST from _memory_grounded_request(user_text) only when memory matches are supplied.',
            'conversation.py:2026-2051 normalizes bounded relationship strings, including these two possessive noun phrases, by title casing and appending to me.',
            'conversation.py:1380-1407 passes original user_text when no memory envelope exists.',
        ],
        'recommended_audit_correction': [
            'Keep fresh-role checks strict and separate from current-request fidelity checks.',
            'For supplied evidence, decode the single CURRENT_USER_REQUEST JSON string and require exact equality to the hash-verified frozen normalizer applied to the frozen prompt.',
            'For no evidence, require exact frozen prompt in the plain request or decoded APPLICATION_REQUEST string; do not permit normalization.',
            'Preserve analysis_blind_v1 and all runtime/collection artifacts. Regression-test unexpected roles, arbitrary changed current request, no-evidence rewrite, and frozen-source drift.',
            'Report the 24 evidence-dependent prompt rewrites separately. Their effect on semantic task quality is not determined by this control audit.',
        ],
        'limitations': 'Validating an exact frozen helper transformation establishes provenance and fresh-history control; it does not establish that the transformation preserves question meaning. Answers, rubrics, review judgments and private review mappings were not evaluated by this diagnostic.',
    }
    out = EXP / 'reviews/audit_prompt_shape_diagnostic_v1.json'
    with out.open('x') as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write('\n')
    out.chmod(0o444)
    print(json.dumps({'output': str(out), 'sha256': digest(out), 'role_counts': dict(shapes), 'format_counts': dict(formats), 'rewrites': len(rewrites)}, indent=2))


if __name__ == '__main__':
    main()
