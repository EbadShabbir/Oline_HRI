#!/usr/bin/env python3
"""Standalone, stdlib-only audit; imports no experiment/analyzer implementation.

Run this file with Python 3. It reads the sibling frozen artifacts and writes
numeric_agreement.json, numeric_agreement.md, and independently_joined_answers.jsonl
in this directory. Frozen inputs and judgments are never modified. Exact categorical
comparisons and numeric comparisons with 1e-9 absolute / 1e-10 relative tolerance
are performed only AFTER independently constructing the corresponding results.
After sealing this directory, use --output /tmp/final_numeric_recheck to rerun.
"""
import argparse
import base64
import collections
import datetime
import hashlib
import json
import math
import pathlib
import random
import statistics

HERE = pathlib.Path(__file__).resolve().parent
BASE = HERE.parent
REPO = BASE.parent.parent
SMALL, LARGE = 'qwen3:0.6b', 'qwen3:1.7b'
CATS = ['routine_general', 'constrained_general', 'personal_recall', 'personal_temporal']
SUCCESS = {'complete', 'appropriate_abstention', 'appropriate_uncertainty'}
OUTCOMES = ['both_correct', 'only_small_correct', 'only_large_correct', 'neither_correct']
FIELDS = ['label', 'unsupported_claim', 'unsupported_personal_claim']
CHECKS = []
READS = set()


def read(path):
    path = pathlib.Path(path)
    if not path.is_absolute():
        path = BASE / path
    READS.add(path)
    return path.read_bytes()


def js(path):
    return json.loads(read(path))


def lines(path):
    return [json.loads(x) for x in read(path).splitlines() if x.strip()]


def digest(path):
    return hashlib.sha256(read(path)).hexdigest()


def check(name, condition):
    CHECKS.append({'name': name, 'passed': bool(condition)})
    if not condition:
        raise AssertionError(name)


def same(name, actual, expected):
    if isinstance(actual, dict):
        check(name + ': keys', actual.keys() == expected.keys())
        for key in actual:
            same(name + '/' + str(key), actual[key], expected[key])
    elif isinstance(actual, list):
        check(name + ': length', len(actual) == len(expected))
        for i, (x, y) in enumerate(zip(actual, expected)):
            same(name + '/' + str(i), x, y)
    elif isinstance(actual, float):
        check(name, math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-9))
    else:
        check(name, actual == expected)


def stats(values, extended=False):
    values = sorted(values)
    n = len(values)
    if not n:
        return {'n': 0}
    h = (n - 1) * .95
    lo = math.floor(h)
    hi = math.ceil(h)
    out = dict(n=n, mean=math.fsum(values)/n, median=statistics.median(values),
               p95=values[lo] + (values[hi]-values[lo])*(h-lo), total=math.fsum(values))
    if extended:
        out.update(minimum=values[0], maximum=values[-1])
    return out


def unique(rows, field, name):
    result = {row[field]: row for row in rows}
    check(name + ': no duplicate IDs', len(result) == len(rows))
    return result


def counts(rows):
    observed = collections.Counter(r['outcome'] for r in rows)
    return {key: observed[key] for key in OUTCOMES}


def summary(rows):
    return dict(attempts=len(rows), correct=sum(r['correct'] for r in rows),
                labels=dict(collections.Counter(r['review']['label'] for r in rows)),
                unsupported_claims=sum(r['review']['unsupported_claim'] for r in rows),
                unsupported_personal_claims=sum(r['review']['unsupported_personal_claim'] for r in rows),
                technical_status=dict(collections.Counter(r['status'] for r in rows)),
                latency_seconds=stats([r['primary_seconds'] for r in rows]))


def integrate(samples, start, end):
    """Piecewise linear power over intersections with observed sample intervals."""
    energy = []
    covered_ns = 0
    for a, b in zip(samples, samples[1:]):
        ta, tb = a['monotonic_ns'], b['monotonic_ns']
        left, right = max(ta, start), min(tb, end)
        if right <= left:
            continue
        pa, pb = a['vdd_in']['instant_mw'], b['vdd_in']['instant_mw']
        pl = pa + (pb-pa)*(left-ta)/(tb-ta)
        pr = pa + (pb-pa)*(right-ta)/(tb-ta)
        energy.append((pl+pr)*.5*(right-left)/1e12)
        covered_ns += right-left
    return math.fsum(energy), covered_ns/1e9


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=pathlib.Path, default=HERE)
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sealed = ['frozen_v1', 'run_v1', 'blinded_v1', 'reviews', 'disagreements_v1', 'analysis_v1', 'resource_audit_v1']
    seal_counts = {}
    for folder in sealed:
        seal = js(folder + '/seal.json')
        for name, expected in seal['sha256'].items():
            check('sealed SHA256 ' + folder + '/' + name, digest(folder + '/' + name) == expected)
            check('sealed file is read-only ' + folder + '/' + name,
                  (BASE/folder/name).stat().st_mode & 0o222 == 0)
        seal_counts[folder] = len(seal['sha256'])
    frozen = js('frozen_v1/freeze.json')
    for name, expected in frozen['source_sha256'].items():
        check('current source SHA256 ' + name, digest(REPO/name) == expected)
        check('frozen source SHA256 ' + name, digest('frozen_v1/source/' + name) == expected)
    for name, key in [('dataset.json', 'dataset_sha256'), ('protocol.md', 'protocol_sha256'),
                      ('tokenizer_proof.json', 'tokenizer_proof_sha256')]:
        check('freeze reference ' + key, digest('frozen_v1/' + name) == frozen[key])
    for name, expected in js('reporting_source/manifest.json')['sha256'].items():
        check('reporting source SHA256 ' + name, digest('reporting_source/' + name) == expected)

    cases = js('frozen_v1/dataset.json')
    case_by_id = unique(cases, 'request_id', 'cases')
    prompts = unique(js('frozen_v1/prompts.json'), 'request_id', 'prompts')
    check('120 cases, 30/category', len(cases) == 120 and collections.Counter(c['category'] for c in cases) == dict.fromkeys(CATS, 30))
    check('120 independent scenario IDs', len({c['scenario_id'] for c in cases}) == 120)
    check('empty histories', all(c['history'] == [] for c in cases))
    mapping = unique(js('blinded_v1/mapping.json'), 'answer_id', 'mapping')
    packet_a = unique(lines('blinded_v1/packet_a.jsonl'), 'answer_id', 'packet A')
    packet_b = unique(lines('blinded_v1/packet_b.jsonl'), 'answer_id', 'packet B')
    reviewer_a = unique(lines('reviews/reviewer_a.jsonl'), 'answer_id', 'reviewer A')
    reviewer_b = unique(lines('reviews/reviewer_b.jsonl'), 'answer_id', 'reviewer B')
    adjudication = unique(lines('reviews/adjudication.jsonl'), 'answer_id', 'adjudication')
    for name, rows in [('packet A', packet_a), ('packet B', packet_b), ('reviewer A', reviewer_a), ('reviewer B', reviewer_b)]:
        check(name + ': exact complete mapping join', rows.keys() == mapping.keys() and len(rows) == 240)
    check('both packets have identical complete answer rows', packet_a == packet_b)
    check('packets have no model/request/timing/category fields', all(set(r) == {'answer_id', 'question', 'evidence', 'rubric', 'answer', 'response_complete'} for r in packet_a.values()))
    disagreements = {aid for aid in mapping if any(reviewer_a[aid][f] != reviewer_b[aid][f] for f in FIELDS)}
    check('eight exact label/flag disagreements covered once', len(disagreements) == 8 and disagreements == adjudication.keys())
    check('exported disagreement packet coverage', {r['answer_id'] for r in lines('disagreements_v1/disagreements.jsonl')} == disagreements)
    resolved = {aid: adjudication[aid] if aid in disagreements else reviewer_a[aid] for aid in mapping}
    check('resolved reviews reproduce byte-equivalent parsed records', resolved == js('analysis_v1/resolved_reviews.json'))
    review_freeze = js('reviews/independent_review_freeze.json')
    adjudication_freeze = js('reviews/adjudication_freeze.json')
    unblind = js('unblinding.json')
    for letter in ('a', 'b'):
        record = review_freeze['reviewers'][letter]
        check('review freeze hash ' + letter, record['sha256'] == digest('reviews/reviewer_' + letter + '.jsonl'))
        check('review packet hash ' + letter, record['packet_sha256'] == digest('blinded_v1/packet_' + letter + '.jsonl'))
    check('adjudication freeze hash', adjudication_freeze['sha256'] == digest('reviews/adjudication.jsonl'))
    check('unblinding review seal hash and authorization', unblind['all_two_reviews_and_adjudication_frozen'] is True and unblind['review_seal_sha256'] == digest('reviews/seal.json'))
    chronology = {
        'input_freeze': js('frozen_v1/seal.json')['created_at'],
        'run_start': js('run_v1/plan.json')['started_at'],
        'run_seal': js('run_v1/seal.json')['created_at'],
        'blind_packets': js('blinded_v1/provenance.json')['created_at'],
        'independent_reviews_frozen': review_freeze['recorded_at'],
        'disagreements_exported': js('disagreements_v1/agreement.json')['created_at'],
        'adjudication_frozen': adjudication_freeze['recorded_at'],
        'review_seal': js('reviews/seal.json')['created_at'],
        'unblinding': unblind['recorded_at'],
        'analysis_created': js('analysis_v1/provenance.json')['created_at'],
    }
    timestamps = [datetime.datetime.fromisoformat(x) for x in chronology.values()]
    check('freeze/review/adjudication/unblinding chronology', timestamps == sorted(timestamps))
    check('human validation pending throughout', all(x['human_validation'] == 'pending' for x in [review_freeze, adjudication_freeze, js('blinded_v1/provenance.json')]))

    rows, block_resources, all_http = [], [], []
    schedule = frozen['schedule']
    block_dirs = sorted((BASE/'run_v1').glob('*_block*'))
    check('12 model blocks', len(block_dirs) == len(schedule) == 12)
    for i, (directory, planned) in enumerate(zip(block_dirs, schedule), 1):
        block = js(directory/'block.json')
        check('block schedule ' + directory.name, block == planned)
        model = block['model']
        events = lines(directory/'attempts.jsonl')
        starts = [r for r in events if r['event'] == 'attempt_start']
        finishes = [r for r in events if r['event'] == 'attempt_finish']
        check('exact starts/finishes ' + directory.name, len(events) == 40 and [r['request_id'] for r in starts] == [r['request_id'] for r in finishes] == planned['request_ids'])
        http = lines(directory/'http.jsonl')
        calls = collections.defaultdict(list)
        for event in http:
            calls[event['call_id']].append(event)
        check('22 calls per block ' + directory.name, len(calls) == 22)
        primary = {}
        for call_id, records in calls.items():
            begin, end = records[0], records[-1]
            check('HTTP start/finish framing ' + directory.name + '/' + str(call_id), begin['event'] == 'start' and end['event'] == 'finish')
            check('HTTP wall duration ' + directory.name + '/' + str(call_id), end['wall_ns'] == end['finished_monotonic_ns']-begin['monotonic_ns'])
            chunks = b''.join(base64.b64decode(e['bytes_base64']) for e in records if e['event'] == 'chunk')
            check('raw HTTP chunks ' + directory.name + '/' + str(call_id), chunks.decode('utf-8') == end['raw_utf8'])
            body_bytes = json.dumps(begin['body'], sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
            check('HTTP body SHA256 ' + directory.name + '/' + str(call_id), hashlib.sha256(body_bytes).hexdigest() == begin['body_sha256'])
            all_http.append((begin['monotonic_ns'], end['finished_monotonic_ns']))
            if begin['purpose'] == 'primary':
                rid = begin['request_id']
                body = dict(begin['body'])
                check('actual selector ' + model + '/' + rid, body.pop('model') == model)
                check('identical frozen input ' + model + '/' + rid, body == prompts[rid]['body_without_model'])
                check('no duplicate primary ' + model + '/' + rid, rid not in primary)
                primary[rid] = (begin, end)
        check('one primary per planned request ' + directory.name, list(primary) == planned['request_ids'])
        for attempt in finishes:
            rid = attempt['request_id']
            begin, end = primary[rid]
            transport = attempt['transport']
            check('transport equals HTTP finish ' + model + '/' + rid, transport == {k:v for k,v in end.items() if k != 'event'})
            check('technical success ' + model + '/' + rid, attempt['status'] == 'ok' and end['http_status'] == 200 and not end['error'])
            frames = [json.loads(line) for line in end['raw_utf8'].splitlines()]
            check('model identity in all response frames ' + model + '/' + rid, all(frame['model'] == model for frame in frames))
            check('complete raw response ' + model + '/' + rid, frames[-1]['done'] is True and frames[-1]['done_reason'] == 'stop')
            raw_answer = ''.join(frame.get('response', '') for frame in frames)
            check('raw answer reconstruction ' + model + '/' + rid, raw_answer == attempt['raw_answer'])
            check('JSON answer preserved ' + model + '/' + rid, json.loads(raw_answer) == {'answer': attempt['answer']})
            check('thinking absent ' + model + '/' + rid, attempt['thinking'] == '' and not any(frame.get('thinking') for frame in frames))
            check('actual prompt fits complete budget ' + model + '/' + rid, attempt['stats']['prompt_eval_count'] + 192 + 64 <= frozen['options']['num_ctx'])
            for phase in ['resident_before', 'resident_after']:
                resident = attempt[phase]
                check(phase + ' identity ' + model + '/' + rid, len(resident) == 1 and resident[0]['name'] == model and resident[0]['digest'] == frozen['models'][model]['digest'] and resident[0]['context_length'] == 2048)
            for key, value in attempt['stats'].items():
                check('backend metadata ' + model + '/' + rid + '/' + key, frames[-1].get(key) == value)
            input_bytes = json.dumps(prompts[rid]['body_without_model'], sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
            check('input SHA256 ' + model + '/' + rid, hashlib.sha256(input_bytes).hexdigest() == attempt['input_sha256'])
            rows.append(dict(attempt, primary_seconds=end['wall_ns']/1e9, category=case_by_id[rid]['category'], evidence_status=case_by_id[rid]['evidence_status']))
        samples = lines(directory/'telemetry.jsonl')
        load, unload = js(directory/'load.json'), js(directory/'unload.json')
        loaded = js(directory/'resident_loaded.json')['models'][0]
        admitted = lines(directory/'admission.jsonl')[-1]
        finished = js(directory/'finish.json')
        energy, covered, requested = [], [], []
        for begin, end in primary.values():
            e, c = integrate(samples, begin['monotonic_ns'], end['finished_monotonic_ns'])
            energy.append(e); covered.append(c); requested.append(end['wall_ns']/1e9)
        total_energy, total_span = integrate(samples, samples[0]['monotonic_ns'], samples[-1]['monotonic_ns'])
        load_energy, load_covered = integrate(samples, load['started_monotonic_ns'], load['finished_monotonic_ns'])
        unload_energy, unload_covered = integrate(samples, unload['started_monotonic_ns'], unload['finished_monotonic_ns'])
        resource = dict(index=i, model=model, block=block['block'],
            load_wall_seconds=load['wall_ns']/1e9, unload_wall_seconds=unload['wall_ns']/1e9,
            telemetry=dict(sample_count=len(samples), duration_seconds=total_span,
                whole_interval_energy_joules=total_energy,
                request_intervals_energy_joules=math.fsum(energy),
                request_interval_covered_seconds=math.fsum(covered),
                request_interval_requested_seconds=math.fsum(requested),
                request_coverage_fraction=math.fsum(covered)/math.fsum(requested),
                loading_covered_energy_joules=load_energy, loading_covered_seconds=load_covered,
                unloading_covered_energy_joules=unload_energy, unloading_covered_seconds=unload_covered,
                peak_ram_used_mb=max(s['ram']['used_mb'] for s in samples),
                peak_swap_used_mb=max(s['swap']['used_mb'] for s in samples),
                peak_temperature_c=max(v for s in samples for v in s['temperatures_c'].values()),
                gpu_activity_percent=stats([s['gr3d_percent'] for s in samples], True)),
            largest_telemetry_gap_seconds=max((b['monotonic_ns']-a['monotonic_ns'])/1e9 for a,b in zip(samples,samples[1:])),
            minimum_sampled_free_ram_mb=min(s['ram']['total_mb']-s['ram']['used_mb'] for s in samples),
            admitted_memory=admitted['memory'], finish_memory=finished['memory'],
            gpu_placement=dict(context_length=loaded['context_length'], size_bytes=loaded['size'],
                               size_vram_bytes=loaded['size_vram'],allocated_vram_fraction=loaded['size_vram']/loaded['size']))
        block_resources.append(resource)
    check('all HTTP calls serialized', all(end <= next_start for (_,end),(next_start,_) in zip(sorted(all_http),sorted(all_http)[1:])))
    check('240 unique model/request pairs', len(rows) == len({(r['model'],r['request_id']) for r in rows}) == 240)
    by_key = {(r['model'], r['request_id']):r for r in rows}
    check('mapping exact bijection to primary attempts', len({(m['model'],m['request_id']) for m in mapping.values()}) == 240 and {(m['model'],m['request_id']) for m in mapping.values()} == by_key.keys())
    for aid, mapped in mapping.items():
        row = by_key[mapped['model'], mapped['request_id']]
        case = case_by_id[mapped['request_id']]
        packet = packet_a[aid]
        check('blinded answer/raw join ' + aid, packet['answer'] == row['answer'] and packet['response_complete'] is True)
        check('blinded full evidence/rubric join ' + aid, all(packet[k] == case[k] for k in ['question','evidence','rubric']))
        row.update(answer_id=aid, review=resolved[aid], correct=row['status'] == 'ok' and resolved[aid]['label'] in SUCCESS)
    pairs = []
    for case in cases:
        small, large = (by_key[m,case['request_id']] for m in [SMALL,LARGE])
        pair_index = {(True,True):0, (True,False):1, (False,True):2, (False,False):3}[small['correct'],large['correct']]
        check('paired runtime prompt token counts ' + case['request_id'], small['stats']['prompt_eval_count'] == large['stats']['prompt_eval_count'])
        pairs.append(dict(request_id=case['request_id'], category=case['category'], evidence_status=case['evidence_status'],
                          outcome=OUTCOMES[pair_index], large_minus_small_seconds=(large['transport']['wall_ns']-small['transport']['wall_ns'])/1e9))
    pair_counts = {'overall': counts(pairs), **{cat:counts([p for p in pairs if p['category'] == cat]) for cat in CATS}}
    rescues = [p for p in pairs if p['outcome'] == 'only_large_correct']
    models = {}
    for model in [SMALL,LARGE]:
        rr = [r for r in rows if r['model'] == model]
        bb = [b for b in block_resources if b['model'] == model]
        result = summary(rr)
        result.update(by_category={cat:summary([r for r in rr if r['category'] == cat]) for cat in CATS},
            by_evidence_status={ev:dict(attempts=sum(r['evidence_status'] == ev for r in rr),correct=sum(r['correct'] for r in rr if r['evidence_status'] == ev)) for ev in ['answerable','conflicting','unknown']},
            backend_seconds={key:stats([r['stats'][key]/1e9 for r in rr]) for key in ['eval_duration','load_duration','prompt_eval_duration','total_duration']},
            total_attempt_seconds=stats([r['total_wall_ns']/1e9 for r in rr]),
            explicit_loading_seconds=stats([b['load_wall_seconds'] for b in bb]),
            explicit_unloading_seconds=math.fsum(b['unload_wall_seconds'] for b in bb),
            measured_unload_count=len(bb), missing_request_latency_count=0)
        result['startup_amortized_mean_seconds'] = (result['latency_seconds']['total']+result['explicit_loading_seconds']['total'])/len(rr)
        result['loading_and_cleanup_amortized_mean_seconds'] = (result['latency_seconds']['total']+result['explicit_loading_seconds']['total']+result['explicit_unloading_seconds'])/len(rr)
        models[model] = result
    rng = random.Random(42121)
    differences = [[int(by_key[LARGE,c['request_id']]['correct'])-int(by_key[SMALL,c['request_id']]['correct']) for c in cases if c['category'] == cat] for cat in CATS]
    bootstrap = sorted(sum(group[rng.randrange(len(group))] for group in differences for _ in range(len(group)))/len(cases) for _ in range(10000))
    computed = dict(models=models, pair_counts=pair_counts, pairs=pairs,
                    extra_latency_seconds=stats([p['large_minus_small_seconds'] for p in pairs]),
                    rescue_extra_latency_seconds=stats([p['large_minus_small_seconds'] for p in rescues]),
                    rescue_evidence_status=dict(collections.Counter(p['evidence_status'] for p in rescues)),
                    quality_difference=(models[LARGE]['correct']-models[SMALL]['correct'])/120,
                    quality_difference_stratified_bootstrap_95=[bootstrap[249],bootstrap[9749]],
                    review_agreement=dict(total=240,exact_agreement=240-len(disagreements),adjudicated=len(adjudication)))
    # Published output is a comparison target only; no values feed the computations.
    published = js('analysis_v1/analysis.json')
    for key, value in computed.items():
        same('analysis agreement/' + key, value, published[key])
    published_rows = unique(lines('analysis_v1/scored_answers.jsonl'),'answer_id','published scored answers')
    for row in rows:
        original = {k:v for k,v in row.items() if k not in ['primary_seconds']}
        target = published_rows[row['answer_id']]
        check('complete scored answer join ' + row['answer_id'], all(target[k] == v for k,v in original.items()))
    ap = js('analysis_v1/provenance.json')
    for key, path in [('analyzer_sha256','frozen_v1/source/scripts/analyze_matched_evidence.py'), ('review_a_sha256','reviews/reviewer_a.jsonl'), ('review_b_sha256','reviews/reviewer_b.jsonl'), ('adjudication_sha256','reviews/adjudication.jsonl')]:
        check('analysis provenance ' + key, ap[key] == digest(path))
    resource = js('resource_audit_v1/resource_audit.json')
    same('resource audit paired extra', stats([p['large_minus_small_seconds'] for p in pairs], True), resource['paired_extra_primary_seconds'])
    for block, existing in zip(block_resources, resource['blocks']):
        for key,value in block.items():
            if key == 'telemetry':
                for metric,number in value.items():
                    same('resource block ' + str(block['index']) + '/' + metric,number,existing[key][metric])
            else:
                same('resource block ' + str(block['index']) + '/' + key,value,existing[key])
    for model in [SMALL,LARGE]:
        rr = [r for r in rows if r['model'] == model]
        bb = [b for b in block_resources if b['model'] == model]
        existing = resource['models'][model]
        for actual, target in [('latency_seconds','primary_latency_seconds'),('total_attempt_seconds','total_attempt_latency_seconds')]:
            values = [r['primary_seconds'] if actual == 'latency_seconds' else r['total_wall_ns']/1e9 for r in rr]
            same('resource ' + model + '/' + target,stats(values,True),existing[target])
        for metric in models[model]['backend_seconds']:
            same('resource backend ' + model + '/' + metric, stats([r['stats'][metric]/1e9 for r in rr],True),existing['backend_seconds'][metric])
        for metric in ['eval_count','prompt_eval_count']:
            same('resource tokens ' + model + '/' + metric, stats([r['stats'][metric] for r in rr],True),existing['tokens'][metric])
        for metric in ['startup_amortized_mean_seconds','loading_and_cleanup_amortized_mean_seconds']:
            same('resource amortization ' + model + '/' + metric,models[model][metric],existing[metric])
        same('resource load sum ' + model,models[model]['explicit_loading_seconds']['total'],existing['explicit_load_seconds'])
        same('resource unload sum ' + model,models[model]['explicit_unloading_seconds'],existing['explicit_unload_seconds'])
        for metric in ['peak_ram_used_mb','peak_swap_used_mb','peak_temperature_c']:
            same('resource peak ' + model + '/' + metric,max(b['telemetry'][metric] for b in bb),existing[metric])
        energy = {k:math.fsum(b['telemetry'][k] for b in bb) for k in existing['energy'] if k != 'request_coverage_fraction'}
        energy['request_coverage_fraction'] = energy['request_interval_covered_seconds']/energy['request_interval_requested_seconds']
        same('resource energy ' + model,energy,existing['energy'])
    rp = js('resource_audit_v1/provenance.json')
    check('resource auditor source hash',rp['audit_source_sha256'] == digest('resource_audit_v1/audit_source.py'))
    check('resource freeze seal reference',resource['freeze_seal_sha256'] == digest('frozen_v1/seal.json'))
    check('resource run seal reference',resource['run_seal_sha256'] == digest('run_v1/seal.json'))
    check('analysis scope and human validation', published['scope'] == 'assistant-reviewed matched-evidence direct generator capability only' and published['human_validation'] == 'pending')
    report = dict(created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        result='PASS', methodology=__doc__, independent_computations=computed,
        additional_rescue_costs={status:stats([p['large_minus_small_seconds'] for p in rescues if p['evidence_status'] == status]) for status in ['answerable','conflicting','unknown']},
        independently_integrated_blocks=block_resources,
        source_files_verified=len(frozen['source_sha256']), sealed_files_verified=seal_counts,
        review_disagreement_ids=sorted(disagreements), chronology=chronology,
        human_validation='pending', scope='assistant-reviewed matched-evidence direct generator component capability only',
        limitations=['Hash and read-only checks are application-level integrity, not privileged WORM.',
                     'Recorded chronology supports the procedural sequence; shared filesystem access was not independently enforced.',
                     'Numeric agreement validates frozen-judgment arithmetic, not the correctness of every shared assistant judgment.',
                     'Whole-device sampled energy includes background activity and interpolates only within observed sample intervals.',
                     'No inference, router/cascade test, latency threshold, or new human validation was performed.'],
        input_sha256={str(p.relative_to(BASE)) if p.is_relative_to(BASE) else str(p):digest(p) for p in sorted(READS)},
        check_count=len(CHECKS), checks=CHECKS)
    (output/'numeric_agreement.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    export_keys=['answer_id','request_id','model','category','evidence_status','answer','review','correct','primary_seconds']
    (output/'independently_joined_answers.jsonl').write_text(''.join(json.dumps({k:r[k] for k in export_keys},sort_keys=True)+'\n' for r in sorted(rows,key=lambda r:(r['request_id'],r['model']))))
    md = ['# Independent final numerical audit', '',
          f'PASS: {len(CHECKS):,} checks. This standalone script imports no experiment/analyzer code. It reconstructs 240 scored answers from 240 raw primary attempts, two complete review files, eight adjudications, and the post-review model mapping.', '',
          'Human validation remains pending. Findings concern direct generator component capability on the fixed fictional workload.', '',
          '| Stratum | Both correct | Only 0.6B | Only 1.7B | Neither |', '|---|---:|---:|---:|---:|']
    for cat, count in pair_counts.items():
        md.append('| '+cat+' | '+' | '.join(str(count[k]) for k in OUTCOMES)+' |')
    md += ['', '| Model | Correct | Mean request s | Median s | P95 s | Startup amortized s |', '|---|---:|---:|---:|---:|---:|']
    for model, metric in models.items():
        lat=metric['latency_seconds']
        md.append(f"| {model} | {metric['correct']}/120 | {lat['mean']:.9f} | {lat['median']:.9f} | {lat['p95']:.9f} | {metric['startup_amortized_mean_seconds']:.9f} |")
    md += ['', f"Observed rescues: {len(rescues)}; evidence strata: {computed['rescue_evidence_status']}. All category counts, labels, flags, evidence strata, means/medians/linear P95s, paired differences, rescue differences, startup/cleanup amortization, and the 10,000-resample bootstrap interval agree with analysis_v1.", '',
           f"Overall extra latency (mean/median/P95): {computed['extra_latency_seconds']}. Rescue extra latency: {computed['rescue_extra_latency_seconds']}.", '',
           f"Verified {sum(seal_counts.values())} sealed artifact hashes across {len(seal_counts)} directories and {len(frozen['source_sha256'])} current source files against frozen hashes. All sealed listed artifacts are read-only. Reporting and resource-auditor source hashes match their provenance records.", '',
           'The resource audit also agrees with independent piecewise linear integration of raw VDD_IN telemetry, primary-call coverage, load/unload energy, resource peaks, backend durations, token statistics, and primary/attempt timings.', '',
           'Review chronology (UTC):', '']
    md += ['- '+key+': '+value for key,value in chronology.items()]
    md += ['', 'This audit checks arithmetic and joins. A separate spot-check note records any concrete grading concerns without changing the frozen judgments. Full human validation remains pending.', '']
    (output/'numeric_agreement.md').write_text('\n'.join(md))
    print(json.dumps({'result':'PASS','check_count':len(CHECKS),'pair_counts':pair_counts,
                      'correct':{m:s['correct'] for m,s in models.items()},'rescues':computed['rescue_evidence_status'],
                      'hash_count':sum(seal_counts.values()),'source_files':len(frozen['source_sha256'])},indent=2))


if __name__ == '__main__':
    main()
