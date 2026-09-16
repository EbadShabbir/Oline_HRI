"""Render the final matched-evidence report from sealed numeric artifacts."""
import argparse
from collections import Counter,defaultdict
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import statistics

MODELS=('qwen3:0.6b','qwen3:1.7b')
CATS=('routine_general','constrained_general','personal_recall','personal_temporal')
NAMES=dict(zip(CATS,('Routine general','Several explicit constraints','Direct personal recall','Personal temporal / synthesis')))
LABELS=('complete','appropriate_abstention','appropriate_uncertainty','partial','incorrect','inappropriate_abstention','technical_failure')
OUTCOMES=('both_correct','only_small_correct','only_large_correct','neither_correct')
def read(p):return json.loads(p.read_text())
def rows(p):return [json.loads(s) for s in p.read_text().splitlines()]
def table(headers,values):return ['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |',*['| '+' | '.join(str(x) for x in r)+' |' for r in values],'']
def main():
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);a=p.parse_args();root=a.experiment
    x=read(root/'analysis_v1/analysis.json');res=read(root/'resource_audit_v1/resource_audit.json');f=read(root/'frozen_v1/freeze.json')
    scored=rows(root/'analysis_v1/scored_answers.jsonl');dataset=read(root/'frozen_v1/dataset.json');byid={c['request_id']:c for c in dataset}
    bykey={(r['request_id'],r['model']):r for r in scored};small,large=(x['models'][m] for m in MODELS)
    diff=large['correct']-small['correct'];extra=x['extra_latency_seconds']['mean'];ratio=large['latency_seconds']['mean']/small['latency_seconds']['mean']
    pc=x['pair_counts']['overall'];answerable_rescues=x['rescue_evidence_status'].get('answerable',0)
    lines=['# CLARA matched-evidence model-capability experiment','',
       f'**Completed: 120 fresh requests × two generators = 240 primary attempts.** '
       f'Assistant-reviewed full-rubric success was **{small["correct"]}/120 ({small["correct"]/1.2:.1f}%)** for `qwen3:0.6b` '
       f'and **{large["correct"]}/120 ({large["correct"]/1.2:.1f}%)** for `qwen3:1.7b`. '
       f'The larger model rescued **{pc["only_large_correct"]}** requests, including **{answerable_rescues} answerable** requests, '
       f'and lost **{pc["only_small_correct"]}** small-model successes. Its mean warm request cost was **+{extra:.3f} s ({ratio:.2f}×)**.','',
       '**These are two independent blinded assistant reviews with adjudication; independent human validation remains pending.** '
       'The experiment measures direct generator capability under matched evidence. It establishes no routing, retrieval, cascade, spoken-interaction, or deployment-requirement result.','',
       '## Paired correctness','']
    lines+=table(['Category','Both correct','Only small correct','Only large correct','Neither correct'],[[NAMES.get(cat,cat.title()),*[vals[o] for o in OUTCOMES]] for cat in ('overall',*CATS) for vals in [x['pair_counts'][cat]]])
    lo,hi=x['quality_difference_stratified_bootstrap_95']
    lines += [f'The observed large-minus-small quality difference is **{100*x["quality_difference"]:+.1f} percentage points** '
              f'({diff:+d} requests); the predeclared category-stratified paired bootstrap 95% interval is '
              f'**{100*lo:+.1f} to {100*hi:+.1f} points**. This is descriptive uncertainty over authored scenarios, '
              'not a population guarantee. All 120 scenarios occur once; there are no repeated quality trials.','']
    lines+=table(['Category','0.6B correct / 30','1.7B correct / 30'],[[NAMES[c],small['by_category'][c]['correct'],large['by_category'][c]['correct']] for c in CATS])
    lines+=table(['Evidence status','Requests / model','0.6B correct','1.7B correct','Only-large rescues'],[[s,small['by_evidence_status'][s]['attempts'],small['by_evidence_status'][s]['correct'],large['by_evidence_status'][s]['correct'],x['rescue_evidence_status'].get(s,0)] for s in ('answerable','unknown','conflicting')])
    lines+=['Correct abstention/uncertainty earns success only where the rubric calls for it and all requested known facts are also supplied. '
            'A partial answer receives no full-rubric credit. No quality floor, acceptable extra-cost threshold or response deadline was chosen.','',
            '## Partial answers, abstentions, unsupported claims and failures','']
    lines+=table(['Model',*[s.replace('_',' ') for s in LABELS],'Unsupported claim','Unsupported personal claim'],[[m,*[x['models'][m]['labels'].get(s,0) for s in LABELS],x['models'][m]['unsupported_claims'],x['models'][m]['unsupported_personal_claims']] for m in MODELS])
    lines+=['Flags overlap semantic labels; unsupported personal claims are a subset of unsupported claims. '
            'A schema-valid response can be semantically wrong. All **240/240** primary attempts completed with valid JSON, '
            'zero errors, timeouts, interruptions, truncations, retries or fallbacks. Four separately archived harness attempts '
            'are excluded from these counts; their harness pass concerned transport/identity/residency, not semantic accuracy.','']
    lines+=table(['Category / model',*[s.replace('_',' ') for s in LABELS],'Unsupported','Unsupported personal'],[[NAMES[c]+' / '+m,*[x['models'][m]['by_category'][c]['labels'].get(s,0) for s in LABELS],x['models'][m]['by_category'][c]['unsupported_claims'],x['models'][m]['by_category'][c]['unsupported_personal_claims']] for c in CATS for m in MODELS])
    lines+=['## Measured latency and loading','',
            'Seconds below retain every primary outcome. Warm HTTP latency runs from submission to complete streamed response, '
            'including durable raw-byte logging. Total attempt time additionally includes the recorded attempt bookkeeping and '
            'post-request guards; pre-request admission checks are outside it. Explicit model preloading precedes every twenty-request '
            'model block and is reported separately. No values are speech-start or first-token latency.','']
    lines+=table(['Model','Warm mean','Warm median','Warm p95','Total-attempt mean','Six preloads, total','Startup-amortized mean'],[[m,*[f'{res["models"][m]["primary_latency_seconds"][k]:.3f}' for k in ('mean','median','p95')],f'{res["models"][m]["total_attempt_latency_seconds"]["mean"]:.3f}',f'{res["models"][m]["explicit_load_seconds"]:.3f}',f'{res["models"][m]["startup_amortized_mean_seconds"]:.3f}'] for m in MODELS])
    lines+=table(['Model','Warm prefill mean','Warm decode mean','Warm load residual, total','Mean generated tokens','Explicit unload total'],[[m,f'{res["models"][m]["backend_seconds"]["prompt_eval_duration"]["mean"]:.3f}',f'{res["models"][m]["backend_seconds"]["eval_duration"]["mean"]:.3f}',f'{res["models"][m]["backend_seconds"]["load_duration"]["total"]:.3f}',f'{res["models"][m]["tokens"]["eval_count"]["mean"]:.2f}',f'{res["models"][m]["explicit_unload_seconds"]:.3f}'] for m in MODELS])
    rr=x['rescue_extra_latency_seconds']
    lines += [f'Across the {pc["only_large_correct"]} only-large successes, paired extra warm latency averaged **{rr["mean"]:.3f} s** '
              f'(median **{rr["median"]:.3f} s**). Across all requests it averaged **{extra:.3f} s**, and the larger model was slower '
              'on every matched request. Startup-amortized means allocate each block preload across its twenty requests. '
              'Backend loading/prefill/decode are overlapping components of measured wall time and must not be added to it again. '
              'The larger model also produced more tokens; this is measured request cost, not a controlled equal-token decode comparison.','']
    block_rows=[]
    for b in res['blocks']:
        attempt=[r for r in scored if r['block']==b['block'] and r['model']==b['model']]
        block_rows.append([b['index'],b['block'],b['model'],f'{statistics.mean(r["transport"]["wall_ns"] for r in attempt)/1e9:.3f}',f'{b["load_wall_seconds"]:.3f}',f'{b["gpu_placement"]["allocated_vram_fraction"]*100:.1f}%',f'{b["telemetry"]["peak_temperature_c"]:.3f}'])
    lines+=table(['Run order','Paired block','Model','Warm mean s','Preload s','GPU allocation / loaded allocation','Peak °C'],block_rows)
    lines += ['The large model used **73.6–78.6%** GPU allocation versus **100%** for small, with automatic CPU offload. '
              'These are memory-allocation ratios, not GPU utilization or fractions of computation. '
              'Placement varied by block and was not forced equal. Counterbalancing controls order only partially; '
              'timing reflects these installed artifacts, their output lengths, this desktop load and this runtime.','']
    # Report recorded startup waits without assigning them to a hypothetical router.
    wait_seconds=0;checks=0
    for pth in (root/'run_v1').glob('*/admission.jsonl'):
        ad=rows(pth);checks+=len(ad)-1
        wait_seconds+=(datetime.fromisoformat(ad[-1]['captured_at'])-datetime.fromisoformat(ad[0]['captured_at'])).total_seconds()
    hs=read(root/'run_v1/host_start.json');he=read(root/'run_v1/host_finish.json')
    elapsed=(datetime.fromisoformat(he['snapshot']['captured_at'])-datetime.fromisoformat(hs['snapshot']['captured_at'])).total_seconds()
    lines += [f'The complete primary collection spanned **{elapsed:.3f} s** of host wall time. '
              f'There were **{checks}** rejected startup checks followed by admission under unchanged guards, '
              f'covering **{wait_seconds:.3f} s** between first and successful snapshots. '
              'These are recorded scheduler/admission intervals, excluded from warm and preload-only amortized timing. '
              'They are not model generation failures or a prediction of an alternative workload’s switching cost.','',
              '## Device telemetry and energy','']
    lines+=table(['Model','Peak RAM MiB','Peak logical swap MiB','Peak °C','Sampled block energy kJ','Sampled request energy kJ','Request-time coverage'],[[m,res['models'][m]['peak_ram_used_mb'],res['models'][m]['peak_swap_used_mb'],f'{res["models"][m]["peak_temperature_c"]:.3f}',f'{res["models"][m]["energy"]["whole_interval_energy_joules"]/1000:.3f}',f'{res["models"][m]["energy"]["request_intervals_energy_joules"]/1000:.3f}',f'{res["models"][m]["energy"]["request_coverage_fraction"]*100:.3f}%'] for m in MODELS])
    lines += ['Energy integrates onboard VDD_IN over sampled model-block windows, with background activity and no idle subtraction. '
              'Cooldown/admission waits are outside these telemetry windows. Unsampled prefixes/tails are not extrapolated; '
              'millisecond cleanup calls have little or no sample overlap, so their apparent near-zero sampled energy is not a zero-energy claim. '
              'These are whole-device estimates, not model-only energy. Logical zram occupancy and physical RAM cannot be added together.','',
              'The Jetson Orin Nano 8 GB remained in **15W mode 0**, on SD-backed `/dev/mmcblk0p1`, with active cooling. '
              'Boot ID, zero thermal-trip counters, Ollama service configuration and swap devices/capacity/priorities were unchanged. '
              'No model was resident at collection start or finish. Startup available-RAM floor was 2 GiB and temperature ceiling '
              'strictly below 55°C; runtime floor was 768 MiB and ceiling 68°C. Both logical-swap ceilings reserved 256 MiB '
              'from the existing 3810.164 MiB capacity. No OS configuration was changed.','',
              '## Representative paired answers','',
              'Examples include every observed paired outcome. All 120 pairs, raw wording, evidence and review rationales remain in '
              '[the complete paired-answer table](analysis_v1/tables_and_answers.md). Selection below takes the first request ID '
              'within each observed outcome/category, one example per available category.','']
    for outcome in OUTCOMES:
        chosen=[]
        for cat in CATS:
            pp=sorted([p for p in x['pairs'] if p['outcome']==outcome and p['category']==cat],key=lambda p:p['request_id'])
            if pp:chosen.append(pp[0])
        if not chosen:continue
        lines += [f'### {outcome.replace("_"," ").capitalize()}','']
        for pair in chosen:
            c=byid[pair['request_id']]
            lines += [f'**{c["request_id"]} — {c["question"]}**','']
            if c['evidence']:lines += ['Evidence: '+'; '.join(c['evidence']),'']
            for m in MODELS:
                r=bykey[c['request_id'],m]
                lines += [f'**{m}:** {r.get("answer") or r.get("raw_answer") or "[No complete answer]"}', '',f'Review: {r["review"]["label"].replace("_"," ")} — {r["review"]["rationale"]}','']
    agreement=x['review_agreement'];n=agreement['exact_agreement']
    lines += ['## Review, validation and reproducibility','',
              f'The two independent assistant reviews initially agreed on the label and both flags for **{n}/240 ({n/2.4:.1f}%)** answers. '
              f'A third blinded assistant adjudicated all **{agreement["adjudicated"]}** disagreements before mapping disclosure. '
              'Initial files, SHA256 freezes, disagreement packets and adjudication records are retained. '
              'Reviewer contexts were separate and received independently randomized row orders. Blinding was procedural in a shared filesystem; '
              'assistant judgments may share systematic errors. Independent human question/rubric/answer validation is pending.','',
              '**Validation:** 24 focused runner/tokenizer/analysis tests and 31 reused guard/telemetry tests passed before primary collection. '
              'Four separately archived smoke attempts verified the live path. The main analyzer and separately authored numerical audit '
              'reconstructed raw HTTP chunks, checked all 240 unique model/request assignments, identical paired input bodies, actual response '
              'models, resident digests/context, sealed input/source hashes and final host state. Actual prompt counts were **93–174 tokens**, '
              'identical within every pair; no evidence was pruned. The conservative full budget maximum was 1,020/2,048.','',
              'The request settings were context 2048, output cap 192, temperature 0, seed 42, thinking disabled, with a shared free-string '
              'JSON schema. Exact sources, settings and model digests were sealed before inference. Ollama was **0.33.3**, and both artifacts '
              'were **Q4_K_M**. The installed metadata reports 751,632,384 and 2,031,739,904 parameters, respectively; nominal tag names are '
              'not exact measured parameter counts.','']
    lines+=table(['Installed generator','Frozen manifest digest'],[[m,'`'+f['models'][m]['digest']+'`'] for m in MODELS])
    lines += ['- [Frozen protocol](frozen_v1/protocol.md), [approved dataset](frozen_v1/dataset.json), [independent preflight review](frozen_v1/preflight_review.json).',
              '- [Freeze manifest and source hashes](frozen_v1/freeze.json), [tokenizer proof](frozen_v1/tokenizer_proof.json), [rendered model inputs](frozen_v1/prompts.json).',
              '- [Primary raw collection](run_v1/), [collector completion](run_v1/finish.json), [separate smoke collection](smoke_v1/).',
              '- [Blinded review packets](blinded_v1/), [frozen reviews and adjudication](reviews/), [initial agreement](disagreements_v1/agreement.json).',
              '- [Machine-readable reviewed analysis](analysis_v1/analysis.json), [every scored attempt](analysis_v1/scored_answers.jsonl), [independent resource audit](resource_audit_v1/resource_audit.json).',
              '- [Methods and limitations](methods.md), [reproducible shell commands](commands.sh), [PNG figure](figures_v1/paired_capability.png), [PDF figure](figures_v1/paired_capability.pdf), [plot data](figures_v1/attempt_latency.csv).','',
              '## Interpretation','',
              f'On this frozen workload, **1.7B rescues {pc["only_large_correct"]} requests**, of which **{answerable_rescues}** require a supported answer '
              f'rather than uncertainty alone. It also loses **{pc["only_small_correct"]}** requests that 0.6B gets right. '
              f'The net gain is **{diff:+d}/120**, with **+{extra:.3f} seconds** average warm request time and higher sampled device energy. '
              'These observations establish the pair’s measured complementarity and cost on this component test. '
              'No acceptable extra-cost threshold was specified, and no selector was evaluated. '
              'The results therefore do not establish that a cascade is preferable, that a router can identify the rescues, '
              'or that either model meets an HRI deployment requirement.','',
              'The larger model still fails 44/120 full rubrics, and both models fail 40 requests. Unresolved conflicting evidence is a particular weakness: only 1/18 small and 3/18 large answers satisfy those rubrics. The capability gain does not imply reliable general conflict resolution or uniformly strong temporal reasoning.','',
              'The balanced assistant-authored workload, short evidence packets, single temperature/seed run, automatic CPU/GPU placement '
              'and assistant-only scoring limit generalization. Both model answers were ordinary generation with identical evidence; '
              'results cannot be pooled with prior application experiments that used different evidence or answer helpers. '
              'All previous experiments are preserved. No deployment or routing policy was changed.','']
    with (root/'README.md').open('x') as s:s.write('\n'.join(lines))
    with (root/'report_generation.json').open('x') as s:json.dump({'source_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),'inputs':['analysis_v1','resource_audit_v1','frozen_v1','run_v1'],'scope':'postfreeze rendering from frozen reviewed results'},s,indent=2)
    print(root/'README.md')
if __name__=='__main__':main()
