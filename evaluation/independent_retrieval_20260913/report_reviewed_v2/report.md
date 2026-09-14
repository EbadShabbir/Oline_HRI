# CLARA independent personal-memory retrieval experiment

Completed **864/864 planned attempts**, with 856 delivered answers and 8 retained failures. The 48 fictional requests were tested under OFF, ALWAYS PERMITTED and SELECTIVE for each fixed generator, with three timing repetitions. Answer quality is assistant-reviewed; independent human validation remains pending.

The question is whether selective retrieval retains useful personalization while reducing unnecessary access and complete request time after paying selection costs.

**qwen3:0.6b.** ALWAYS and SELECTIVE had equal observed known-authorized success totals (53/78 each). Across distinct known requests, SELECTIVE had higher mean success on 0, lower on 0, and equal on 26; OFF achieved 0/78 known-fact task successes. SELECTIVE avoided 18 unnecessary retrieval attempts (6/24 versus 24/24 authorized no-memory tasks). SELECTIVE added an observed 0.089 seconds per attempted request on average, including its selection costs (SELECTIVE−ALWAYS: +0.089 [+0.023, +0.147] seconds; descriptive 95% scenario-bootstrap interval).

**qwen3:1.7b.** SELECTIVE lost known-authorized success relative to ALWAYS: 52/78 versus 53/78. Across distinct known requests, SELECTIVE had higher mean success on 1, lower on 2, and equal on 23; OFF achieved 0/78 known-fact task successes. SELECTIVE avoided 21 unnecessary retrieval attempts (3/24 versus 24/24 authorized no-memory tasks). SELECTIVE saved an observed 1.342 seconds per attempted request on average, including its selection costs (SELECTIVE−ALWAYS: -1.342 [-2.071, -0.614] seconds; descriptive 95% scenario-bootstrap interval).

Equal observed totals do not establish equivalent quality. Paired losses and rescues are retained below; no noninferiority margin or acceptance deadline was declared.

| Generator | Policy | Task success | Known-fact success | Known misses with abstention | Unnecessary retrieval | Mean s | Median s | p95 s | Failures |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 51/144 | 0/78 | 75 | 0/24 | 1.577 | 1.333 | 2.003 | 0 |
| qwen3:0.6b | ALWAYS | 93/144 | 53/78 | 18 | 24/24 | 1.941 | 1.700 | 2.375 | 0 |
| qwen3:0.6b | SELECTIVE | 91/144 | 53/78 | 18 | 6/24 | 2.030 | 1.715 | 2.710 | 0 |
| qwen3:1.7b | OFF | 63/144 | 0/78 | 74 | 0/24 | 7.380 | 6.177 | 13.709 | 1 |
| qwen3:1.7b | ALWAYS | 86/144 | 53/78 | 14 | 24/24 | 10.460 | 9.033 | 20.657 | 3 |
| qwen3:1.7b | SELECTIVE | 89/144 | 52/78 | 15 | 3/24 | 9.117 | 6.760 | 30.457 | 4 |

Known-authorized recall uses the same rubric in every condition. A cautious OFF abstention is a missed personalization task. Unknown, conflicting and restricted facts succeed through the frozen uncertainty/refusal rubric. Unsupported claims and the subset of cautious misses without unsupported or forbidden claims are reported separately in [the detailed tables](tables.md).

## Category comparison

Each cell is task successes / repeated attempts, followed by mean complete request seconds. Each category contains eight distinct requests repeated three times.

| Generator | Category | OFF | ALWAYS | SELECTIVE |
| --- | --- | --- | --- | --- |
| qwen3:0.6b | Direct recall | 0/24; 1.668 s | 21/24; 2.099 s | 21/24; 2.195 s |
| qwen3:0.6b | Paraphrased recall | 0/24; 1.783 s | 6/24; 2.067 s | 6/24; 2.193 s |
| qwen3:0.6b | Multi-fact personal | 0/24; 1.506 s | 23/24; 2.163 s | 23/24; 2.201 s |
| qwen3:0.6b | General without memory need | 12/24; 1.343 s | 13/24; 1.677 s | 11/24; 1.787 s |
| qwen3:0.6b | Unknown or conflicting | 21/24; 1.282 s | 9/24; 1.623 s | 9/24; 1.724 s |
| qwen3:0.6b | Lifecycle or authorization | 18/24; 1.876 s | 21/24; 2.019 s | 21/24; 2.082 s |
| qwen3:1.7b | Direct recall | 0/24; 7.371 s | 21/24; 10.750 s | 21/24; 5.877 s |
| qwen3:1.7b | Paraphrased recall | 0/24; 8.337 s | 6/24; 10.666 s | 6/24; 11.833 s |
| qwen3:1.7b | Multi-fact personal | 0/24; 7.937 s | 23/24; 13.489 s | 23/24; 8.737 s |
| qwen3:1.7b | General without memory need | 22/24; 6.175 s | 12/24; 8.841 s | 17/24; 12.114 s |
| qwen3:1.7b | Unknown or conflicting | 23/24; 5.917 s | 6/24; 8.034 s | 6/24; 7.638 s |
| qwen3:1.7b | Lifecycle or authorization | 18/24; 8.544 s | 18/24; 10.977 s | 16/24; 8.504 s |

## Paired quality and time

| Generator | Left−right | Success Δ, pp [95%] | Request Δ, s [95%] | Requests: left higher / right higher / equal |
| --- | --- | --- | --- | --- |
| qwen3:0.6b | SELECTIVE-ALWAYS | -1.4 [-6.9, +3.5] | +0.089 [+0.023, +0.147] | 1 / 2 / 45 |
| qwen3:0.6b | SELECTIVE-OFF | +27.8 [+17.4, +38.2] | +0.454 [+0.346, +0.581] | 19 / 6 / 23 |
| qwen3:0.6b | ALWAYS-OFF | +29.2 [+15.3, +43.8] | +0.365 [+0.269, +0.468] | 21 / 6 / 21 |
| qwen3:1.7b | SELECTIVE-ALWAYS | +2.1 [-2.8, +7.6] | -1.342 [-2.071, -0.614] | 3 / 3 / 42 |
| qwen3:1.7b | SELECTIVE-OFF | +18.1 [+7.6, +27.8] | +1.737 [+0.974, +2.323] | 19 / 11 / 18 |
| qwen3:1.7b | ALWAYS-OFF | +16.0 [+2.1, +29.2] | +3.079 [+2.171, +4.072] | 19 / 11 / 18 |

The analyzer first averages paired repetitions within a request, then resamples all eight whole scenario clusters with replacement, retaining their questions and conditions. The 10,000 replicates use seed 2026091399. These descriptive intervals have only eight fictional clusters behind them. Category-specific contrasts and repeated paired wins/losses are in [tables.md](tables.md).

## What was measured

| Generator | Policy | Classifier calls | Selection mean s | Retrievals | Retrieval mean s | Relevant evidence supplied | Irrelevant inspected | Irrelevant supplied | Unsupported | Personal unsupported |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 0 | 0.012 | 0 | 0.000 | 0.0% | 0 | 0 | 12 | 3 |
| qwen3:0.6b | ALWAYS | 0 | 0.010 | 138 | 0.098 | 76.3% | 3060 | 48 | 24 | 19 |
| qwen3:0.6b | SELECTIVE | 21 | 0.107 | 114 | 0.096 | 76.3% | 2514 | 36 | 29 | 19 |
| qwen3:1.7b | OFF | 0 | 0.011 | 0 | 0.000 | 0.0% | 0 | 0 | 1 | 1 |
| qwen3:1.7b | ALWAYS | 0 | 0.010 | 138 | 0.134 | 76.3% | 3060 | 48 | 18 | 17 |
| qwen3:1.7b | SELECTIVE | 21 | 0.696 | 111 | 0.146 | 76.3% | 2445 | 36 | 18 | 16 |

Unnecessary retrieval uses authorized no-memory requests as its denominator. Legitimate unknown-fact lookups still need memory even when their relevant-ID set is empty; empty sets have undefined evidence coverage. Reported coverage divides relevant evidence occurrences supplied by all frozen relevant-ID occurrences, rather than averaging per-question coverage. Denied consent and prohibited-data requests are counted separately as authorization checks. Inspected records are the unique eligible records materialized during exact semantic scans plus lexical results; supplied records are the bounded evidence actually passed to generation. Counts sum unique IDs within each attempt, including repeated inspection across requests. Bounded search candidates are a separate metric.

Complete request latency includes selection, retrieval, generation, validation, in-request checks and cold first loads, including failed attempts. Model load/prefill/decode values are nested diagnostics. Setup, cleanup, admission overhead, warm timing, repetitions, helper use, placement, power and telemetry gaps are shown separately in the detailed tables. Stage means use all attempted requests, including zeros when a stage was not invoked. Selection accuracy excludes unresolved and unauthorized decisions. Evidence-dependent helpers and output lengths can change complete-system timing; the comparison does not isolate raw generator capability.

Unsupported-claim judgments use the common full authorized truth context, not actual runtime evidence. The detailed known-fact table separately identifies correct task answers with no supplied evidence; those outcomes do not establish memory-grounded recall.

The frozen evidence helper rewrote the current question in 24 calls covering 2 distinct questions. It interpreted possessive relationship phrases as person names, title-cased them and added 'to me'. OFF retained the original question. These recorded rewrites are evidence-dependent helper behavior; semantic neutrality is not established. The initial offline audit incorrectly required the original wording as a substring. Its failed artifact is preserved; the corrected audit verifies fresh roles and the exact source-hash-verified helper transformation. No runtime source, observation, reference, judgment rule or statistical rule was changed. Exact original and submitted questions are retained in the integrity audit's generation_request_rewrites.

## Controls, review and retained evidence

The approved protocol crossed the same three retrieval policies with fixed Qwen3 0.6B and 1.7B generators at context 2048, output cap 192, temperature 0, seed 42 and thinking disabled. Sole-model classification/rendering, fresh conversations, shared prompts and helpers, and fixed prepared memory snapshots were audited before and after collection. Consent, profile, prohibited-data, correction/deletion, expiry and freshness checks remained active. ALWAYS bypassed memory-need selection while retaining authorization and bounded evidence selection. OFF received no personal evidence. This tests already-applied lifecycle changes; live propagation remains separate.

The supplied analysis contains frozen assistant judgments for all 159/159 distinct question/outcome groups. Blinded packets hid explicit model, policy, timing, repetition, actual supplied evidence and the private mapping. Identical outputs were grouped only within their question. [All delivered answers and failures](answers.md) retain the outcome-to-repetition mapping.

Independent review provenance is preserved in [review_provenance.json](review_provenance.json): 159 reviewed groups; 147 initial agreements; 12 initial disagreements; 12 adjudications. Human validation remains pending.

Failure classes: KeyboardInterrupt: 8. There were 50 request/condition groups with different delivered outcomes across repetitions. Rejected outputs are not scored as delivered text.

Collection terminal status: **complete**. Completed attempt coverage counts every scheduled terminal observation, including failures.

The original 18 logical schedule slots completed across 26 physical request-bearing fragments. Every attempted request, including guarded interruptions, remains once at its frozen position; continuation runs cover only never-started suffixes. Each new physical fragment contributes another cold first load and separate setup/cleanup. These realized timing differences are retained. Supervisor overhead is unavailable for 1 physical fragments and is not imputed as zero.

The collection retained 35 rejected admission records. Their startup checks and waiting are separate from the 864 requested-task latencies; see the sealed admission audit and detailed fragment costs. The final collection inherited 35 and added 0 such records.

## Limits and reproduction

This is an assistant-authored fictional coverage experiment with 48 questions nested in eight shared-topic scenarios. Repeated timing runs are dependent, and the balanced categories do not estimate household request frequencies. Policies occupy each within-model position once; three rounds leave a 2:1 model-order asymmetry. Thermal/cache state, measured CPU/GPU placement, output lengths, helpers and cold-start allocation can affect timing. No population equivalence, safety guarantee, live-memory propagation claim or spoken/HRI deadline follows from this text experiment. Null and unfavorable results are retained.

Source artifacts: [reviewed numeric analysis](../analysis_reviewed_v1/analysis.json); [collection integrity audit](../analysis_reviewed_v1/audit.json); [all measured attempts](../analysis_reviewed_v1/attempts.csv); [paired request means](../analysis_reviewed_v1/paired_request_means.csv); [analysis provenance](../analysis_reviewed_v1/provenance.json); [analysis reproduction command](../analysis_reviewed_v1/commands.sh); [raw collection traces, evidence, requests, outputs and telemetry](../run_v9); [approved protocol, source, models and prepared snapshot](../frozen_v1). This renderer's inputs and source are hashed in [provenance.json](provenance.json); [commands.sh](commands.sh) regenerates these tables into a new directory.
