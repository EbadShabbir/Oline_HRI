# CLARA evaluation results

Latest completed evaluation: [changing-memory repairs, 14 September 2026](evaluation/changing_memory_repair_20260914/README.md). The first repair improved useful delivery from 39/96 to 92/96 on matched checkpoints, with forbidden disclosures falling from 30 to zero. A separately amended relationship follow-up passed 24/24. Human validation is pending.

## Changing-memory repairs — 14 September 2026

Implemented memory revalidation across retained conversation, fresh-evidence
generation, bounded evidence parsing, correction-time and relationship validation,
and guarded location composition. The original 288-checkpoint experiment remains
unchanged. These are selected development regressions after known failures,
not held-out accuracy.

| Matched evaluation | Earlier useful delivery | Repaired useful delivery | Repaired forbidden disclosures | Repaired withholds |
| --- | ---: | ---: | ---: | ---: |
| First repair, four scenarios | 39/96 | 92/96 | 0/96 | 2/96 |
| Separate final relationship amendment | 22/24 under first repair | 24/24 | 0/24 | 0/24 |

The first repair completed all 96 checkpoints across 12 independent databases
and 12 real worker restarts. Original recall passed 16/16, replacement recall
12/16, authorized historical recall 16/16 and appropriate uncertainty 48/48.
Retained/fresh usefulness was 58/60 and 34/36; both histories passed in 34/36
matched pairs. Post-restart useful delivery passed 34/36. Old-value disclosure
after correction was 0/16, deleted-subject disclosure 0/24 and expired-fact
disclosure 0/20. All denominators retain withheld answers.

Four first-run failures remain preserved: two tea responses gave the correct
replacement then contradicted it with uncertainty, and two supported relationship
answers were withheld by a remaining qualifier check. The latter motivated the
separate amendment and complete 24-checkpoint relationship rerun: three new
databases, three real restarts, 24 useful deliveries, zero disclosures, and zero
withheld, interrupted or missing answers. All nine post-restart queries passed.
The tea contradictions remain unresolved. **The final amendment was tested live
on 24 checkpoints; its results are not pooled into the earlier 96.**

Independent integrity audits passed 10,541 and 2,811 checks with zero violations.
Actual scored generators were 89 small/seven large in the first repair and 24
small in the follow-up. The first run preserved one startup rejection before any
inference; the follow-up had none. Independent blinded assistant pairs agreed
on all 47 first-run and 11 follow-up answer groups. Human validation is pending.

The [report](evaluation/changing_memory_repair_20260914/README.md) links the final
patch, frozen traces, reviewed answers, comparisons, figures and reproducible
commands. Both runs concern text, **process restart and controlled logical-time
expiry**, not power-loss recovery or spoken performance.

## Changing memory: correction, deletion, expiry and restart — 14 September 2026

**Completed 12 fictional scenarios × three independent branches: 288/288 live
checkpoints, 283 delivered answers, five withheld responses and zero missing
checkpoints.** Full-rubric useful responses occurred in **118/288 (41.0%)**.
Original recall passed 36/48; replacement recall passed 13/48, comprising
**0/24 retained-history and 13/24 fresh-history** answers. All 12 pre-store
uncertainty questions passed.

| Revoked original value | Disclosures / relevant checkpoints | Retained history | Fresh history |
| --- | ---: | ---: | ---: |
| Old value after correction, current-value queries | 21/48 | 21/24 | 0/24 |
| Deleted subject, including questions about its former statement | 39/72 | 39/48 | 0/24 |
| Expired subject, at/after boundary and restart | 27/60 | 27/36 | 0/24 |

All 87 revoked-original disclosures occurred with retained history. Two fresh
post-restart answers instead matched a never-stored jasmine preference present
in a generator prompt example; they do not establish resurrection of the deleted
rooibos fact or cache contamination. Appropriate uncertainty passed 67/144.
Historical controls named the correct venue in all 48 cases, but 46 added an
unrequested time, leaving only 2/48 full-rubric successes. These partial answers
must not be mistaken for lost historical memory.

Across 108 matched history pairs, both passed in 13, retained alone in three,
fresh alone in 53, and neither in 39. After actual process restart, old-value
disclosure persisted in 11/24 correction, 21/36 deletion and 9/24 expiry queries.
All five withheld answers had supported requested replacements in their raw
speech, according to separate unblinded diagnostic review; **none counts as
successful delivered recall**.

The independent integrity audit passed 31,342 checks with zero violations:
36 isolated persistent databases, 36 real process restarts, 72 confirmed writes,
12 corrections, 12 forgetting operations and 24 records purged by retention.
All 96 snapshot probes matched the frozen boundary semantics. Thirteen
startup-temperature admission failures are preserved; none attempted inference
or repeated a checkpoint. Actual scored generations selected 0.6B 254 times
and 1.7B 34 times under the CLI-default LLM router and frozen runtime.

Two independent blinded assistants agreed on all 214 distinct answer packets;
no third adjudication was needed. Human validation is pending. The separate
analysis-parser amendment changes only evidence diagnosis for five withheld
rows; original answers, judgments and scores are unchanged. No production
repair or live rerun was performed.

The [full report](evaluation/changing_memory_20260914/README.md),
[all reviewed answers](evaluation/changing_memory_20260914/analysis_v2/answers.md),
[tables](evaluation/changing_memory_20260914/tables_v1/README.md),
[figure](evaluation/changing_memory_20260914/figures_v2/checkpoint_heatmap.pdf),
and [commands](evaluation/changing_memory_20260914/commands.sh) preserve the
experiment. Scope is text interaction, **process restart and controlled
logical-time expiry**, not power-loss recovery or spoken performance. The
previous [independent retrieval experiment](evaluation/independent_retrieval_20260913/README.md)
remains separate.

## Matched-evidence generator capability, 12 September 2026

**Completed all 240 primary attempts: 120 fresh requests on each of the two
installed generators.** With identical supplied evidence and ordinary direct
generation, assistant-reviewed full-rubric success was **43/120 (35.8%)** for
`qwen3:0.6b` and **76/120 (63.3%)** for `qwen3:1.7b`. The larger model rescued
37 requests, including 26 answerable requests, while losing four small-model
successes. This establishes an observed capability gain on this workload,
with a substantial measured extra cost. Independent human validation remains pending.

| Category | Both correct | Only small correct | Only large correct | Neither correct |
| --- | ---: | ---: | ---: | ---: |
| Overall, 120 pairs | 39 | 4 | 37 | 40 |
| Routine general, 30 pairs | 11 | 1 | 11 | 7 |
| Several explicit constraints, 30 pairs | 1 | 2 | 15 | 12 |
| Direct personal recall, 30 pairs | 19 | 0 | 5 | 6 |
| Personal temporal / synthesis, 30 pairs | 8 | 1 | 6 | 15 |

The net difference is **+33 requests / +27.5 percentage points**. The
predeclared category-stratified paired bootstrap 95% interval is +18.3 to
+36.7 points; this is descriptive uncertainty over assistant-authored scenarios,
not a household-population guarantee. Of the 37 large-only successes, 26 were
answerable, nine unknown and two conflicting. Unresolved conflicts remain a
major weakness: only **1/18 small and 3/18 large** answers satisfy those rubrics.
The larger model still fails 44 of the 120 full rubrics.

| Generator | Warm mean, s | Warm median, s | Warm p95, s | Six preloads, total s | Mean with block preload amortized, s |
| --- | ---: | ---: | ---: | ---: | ---: |
| `qwen3:0.6b` | 0.767 | 0.725 | 1.586 | 54.128 | 1.218 |
| `qwen3:1.7b` | 3.932 | 2.909 | 9.144 | 132.060 | 5.032 |

The larger model costs **+3.165 seconds per warm request (5.13×)** overall
and +3.498 seconds on its 37 rescued requests. Warm HTTP latency includes
complete streamed output and raw-byte logging; loading is separate. Total
attempt means including bookkeeping/post-checks are 0.786 and 3.954 seconds.
Eighteen startup rejections followed by admission under unchanged guards span
360.728 seconds of logged waiting, excluded from these warm/preload figures.
The large model's GPU allocation was 73.6–78.6% of loaded allocation, versus
100% for small; automatic CPU offload and differing output lengths affect cost.
These allocation ratios are not utilization or fractions of computation.

Small/large semantic labels were respectively 37/59 complete answers,
5/14 appropriate abstentions, 1/3 appropriate uncertainties, 26/19 partial,
50/25 incorrect and 1/0 inappropriate abstentions. Unsupported claims occurred
in 46/28 answers, including 25/20 unsupported personal claims. All 240 attempts
were schema-valid, with **zero errors, timeouts, interruptions, truncations,
retries or fallbacks**. Valid JSON is not semantic correctness.

The 120 scenarios were authored fresh and independently assistant-reviewed
before inference. They include 84 answerable, 18 unknown and 18 conflicting
cases. Two fresh assistant contexts reviewed randomized answer IDs with model,
timing and mapping hidden; they agreed on labels and both flags for 232/240
answers (96.7%). A third blinded assistant adjudicated eight disagreements
before unblinding. All original judgments remain frozen; human validation is pending.

The dataset, protocol, source, model digests and settings were frozen before
collection. Both models received identical raw rendered prompts, complete
evidence, empty history, unrestricted answer-string schema and settings:
2048 context, 192 output cap, temperature 0, seed 42, thinking disabled.
Actual prompt counts matched in every pair (93–174 tokens); conservative
full-budget checks passed for every unpruned evidence set. Direct Ollama calls
bypassed routing, live retrieval, composers, literal-answer constraints,
solution hints, rewriting and cross-model fallbacks. Six paired twenty-request
blocks used AB/BA/AB/BA/AB/BA order with sole-model residency.

The existing resource guards and telemetry were retained without OS changes.
Peak small/large RAM was 5656/6406 MiB, logical swap 1741/1742 MiB and temperature
57.906/59.468°C. Sampled block energy was 1.672/6.364 kJ, including background
activity with no idle subtraction and excluding scheduler waits. Boot, power,
thermal-trip counters, service and swap configuration remained unchanged;
cleanup left no model resident. Validation passed 24 focused and 31 reused
infrastructure tests, plus four excluded live harness attempts. Raw chunk,
input, identity and resource audits passed for all 240 primary attempts.

**Scope:** this matched-evidence component result supports useful observed
1.7B rescues and quantifies their cost. It does not establish that an adaptive
selector finds them, that a cascade is preferable, or that either model meets
spoken/HRI requirements. No acceptable-cost threshold was selected. Prior
application experiments used different evidence/helpers and are not pooled here.

The [full report and representative pairs](evaluation/matched_evidence_20260912/README.md),
[all 120 paired answers](evaluation/matched_evidence_20260912/analysis_v1/tables_and_answers.md),
[reviewed numeric analysis](evaluation/matched_evidence_20260912/analysis_v1/analysis.json),
[resource audit](evaluation/matched_evidence_20260912/resource_audit_v1/resource_audit.json),
[figure](evaluation/matched_evidence_20260912/figures_v1/paired_capability.pdf),
and [reproducible commands](evaluation/matched_evidence_20260912/commands.sh)
preserve the complete experiment. Previous experiments remain unchanged.

## Model capability: ARC pilot, 11 September 2026

The same 100 frozen questions were evaluated in the requested order: Qwen3
0.6B alone, Qwen3 1.7B alone, CLARA generator selection, then Qwen2.5 3B.
The first three conditions completed in single runs. The 3B result combines
83 accepted answers from an interrupted run with the explicitly requested
17-question continuation. Its original interruption remains part of the result.

### Accuracy

| System | Result type | Correct / 100 | Overall accuracy | Overall Wilson 95% CI | ARC-Easy, correct / 50 | ARC-Challenge, correct / 50 |
| --- | --- | ---: | ---: | --- | ---: | ---: |
| Qwen3 0.6B alone | Completed single run | 64 | 64% | 54.2–72.7% | 40 (80%) | 24 (48%) |
| Qwen3 1.7B alone | Completed single run | 79 | 79% | 70.0–85.8% | 43 (86%) | 36 (72%) |
| CLARA cascade: 0.6B / 1.7B | Completed single run | 79 | 79% | 70.0–85.8% | 43 (86%) | 36 (72%) |
| Qwen2.5 3B Q3_K_S | Diagnostic composite, two segments | 71 | 71% | 61.5–79.0% | 38 (76%) | 33 (66%) |

The 3B composite is 59 correct among the original 83 successful requests plus
12 correct among the 17 continuation requests. Question 84 was interrupted
in the original run and retried in the continuation; it contributes only its
designated continuation answer to the composite. No earlier successful
answer was replayed or replaced, including incorrect answers.

Intervals are descriptive; the pooled Wilson interval is approximate for the
equal-sized Easy/Challenge sample. Equal large/cascade totals do not establish
equivalent quality, and this pilot does not establish a statistically reliable
quality difference between 1.7B and the 3B composite.

### Timing

All values below are seconds. Each segment's mean, median, and p95 include its
first request. "Later mean" excludes only that first request; it does not imply
that the cascade retained a loaded model. The original 3B timing row includes
the interrupted request as an observed attempt.

| System / segment | Attempts | Successful requests | First request | Mean | Median | p95 | Later mean | Total request time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3 0.6B alone | 100 | 100 | 12.851 | 0.400 | 0.274 | 0.313 | 0.275 | 40.035 |
| Qwen3 1.7B alone | 100 | 100 | 20.101 | 0.624 | 0.423 | 0.493 | 0.427 | 62.399 |
| CLARA cascade | 100 | 100 | 31.970 | 29.824 | 30.226 | 37.362 | 29.803 | 2982.423 |
| Qwen2.5 3B: original, interrupted | 84 | 83 | 25.423 | 1.093 | 0.789 | 0.925 | 0.800 | 91.818 |
| Qwen2.5 3B: remaining questions 84–100 | 17 | 17 | 30.070 | 3.520 | 1.382 | 10.993 | 1.860 | 59.836 |

The two 3B segments used **101 attempts and 151.655 seconds of measured request
execution**, including the interrupted attempt and both initial model loads.
This excludes preparation, checks outside request timers, and the gap between
segments. Request timing includes checks performed inside the timed requests;
cascade timing also includes routing and model switches. The sum is not an
uninterrupted end-to-end completion latency. Segment timings are kept separate
because their operating limits and GPU/CPU placement differ.

### Whole-device resource peaks

These are sampled peaks for the whole Jetson, including desktop activity and
cleanup, at 500 ms intervals. RAM and swap values are MiB. Used swap denotes
logical swapped data; it is not the physical size of compressed zram storage.

| System / segment | Peak RAM used | Peak swap used | Peak temperature, °C | Runtime swap limit | Execution outcome |
| --- | ---: | ---: | ---: | ---: | --- |
| Qwen3 0.6B alone | 5761 | 160 | 56.562 | 512 MiB | Completed |
| Qwen3 1.7B alone | 6470 | 280 | 59.250 | 512 MiB | Completed |
| CLARA cascade | 6544 | 277 | 55.593 | 512 MiB | Completed |
| Qwen2.5 3B: original | 6426 | 546 | 60.531 | 512 MiB | Interrupted during request 84 at swap limit |
| Qwen2.5 3B: continuation | 6297 | 546 | 56.343 | 1024 MiB | Completed all 17 remaining requests |

The continuation used a documented diagnostic startup requirement of at least
2.25 GiB available RAM and at most 768 MiB swap, followed by a 1 GiB runtime
swap ceiling. Its physical runtime RAM floor remained 768 MiB and its
temperature ceiling remained 68°C. The original 3B attempt had a 2.5 GiB
startup RAM floor, 384 MiB startup swap ceiling, and 512 MiB runtime swap
ceiling. The original full run therefore remains a failure to finish under
that earlier operating criterion; completing item coverage does not erase it.

### Qwen2.5 execution placement

| Segment | Layers on GPU | CPU / GPU KV cache, MiB | Available device memory reported by fitter, MiB |
| --- | ---: | ---: | ---: |
| Original 3B attempt | 37 / 37 | 0 / 72 | 2692 |
| 17-question continuation | 30 / 37 | 14 / 58 | 2337 |

Ollama automatically moved some layers onto the CPU for the continuation to
retain its 1024 MiB free-device-memory target. Both segments used context 2048
and batch size 512. The [curated backend logs](evaluation/arc_capability_20260911/qwen25_3b_offload_logs.json)
establish the placement change; they do not quantify how much of the timing
difference it caused. The composite score also combines answers across these
two execution placements.

### Cascade behavior and paired outcomes

| Measurement | Observed result |
| --- | --- |
| Requests selecting 0.6B / 1.7B | 5 / 95 |
| Routing classifier calls / generator calls | 200 / 100 |
| Memory intent classified true | 28 requests; retrieval disabled for this experiment |
| Standalone 1.7B correct where 0.6B was incorrect | 18 questions |
| Standalone 0.6B correct where 1.7B was incorrect | 3 questions |
| Large-only successes retained by the live cascade | 17 / 18 |
| Small-only successes retained by the live cascade | 0 / 3 |
| Replay of routing choices against standalone answers | 78 / 100 |
| Live cascade score | 79 / 100 |
| Model loading as a share of cascade request time | Approximately 91% |
| Cascade / resident 1.7B mean request-time ratio | Approximately 47.8× |

One 1.7B answer differed between its standalone and cascade invocation despite
identical generation messages and settings. The extra live correct answer
must not be attributed to routing. Exact paired tests are descriptive and
unadjusted: small versus large p = 0.00149; large versus cascade p = 1.0;
large versus the 3B diagnostic composite p = 0.1153. A nonsignificant difference
does not establish equivalence.

### Setup and interpretation

| Item | Configuration |
| --- | --- |
| Device | Jetson Orin Nano 8 GB; 15 W mode 0; active cooling |
| Storage | SD-backed `/dev/mmcblk0p1` |
| Benchmark | Official ARC test splits: 50 Easy + 50 Challenge; deterministic sample and order, seed 42 |
| Small generator | `qwen3:0.6b`, Q4_K_M |
| Large generator | `qwen3:1.7b`, Q4_K_M |
| Additional generator | `qwen2.5:3b-instruct-q3_K_S`, Q3_K_S |
| Context / output ceiling | 2048 / 192 tokens |
| Generation | Temperature 0, seed 42, thinking disabled; JSON answer label constrained to offered choices |
| Single-model residency | Sole generator retained within each run; unloaded afterward |
| Cascade | Production two-call router; existing serial model eviction/loading; common benchmark generation adapter |
| Excluded components | Personal-memory retrieval, history, authored answers, STT, and TTS |
| Scoring | Exact published answer key; no best-of-output selection |

Qwen3 1.7B achieved the highest observed standalone score in this pilot. The
cascade matched its aggregate score but incurred substantially more latency;
this workload supplies no measured cascade efficiency benefit. The extra 3B
artifact did not improve the observed score. Model family, quantization,
execution placement, and initial device state differ, so parameter count alone
does not explain these results.

This is a 100-question public-benchmark subset using generated answer labels,
not a full ARC leaderboard result or a conversational/HRI evaluation. Public
questions may occur in training data. Fixed run order, lack of repetitions,
uncontrolled desktop activity, and the amended 3B continuation limit causal
timing comparisons. No claim of improved personal-memory correctness follows
from this experiment.

All model cleanup checks passed after termination or completion. The original
swap-device configuration, power mode, boot ID, and thermal-trip counters were
preserved; no model remained resident. Swap occupancy remained about 546 MiB
after the continuation and was not cleared. No 4B benchmark score exists; the
4B artifact was removed from Ollama at the user's request.

### Evidence and reproducibility

- [Evaluation overview](evaluation/arc_capability_20260911/README.md).
- [Original four-arm audit and detailed model digests](evaluation/arc_capability_20260911/results_four_arm_reviewed/report.md).
- [Final composite and placement audit](evaluation/arc_capability_20260911/results_continuation_placement_reviewed/report.md),
  [machine-readable analysis](evaluation/arc_capability_20260911/results_continuation_placement_reviewed/analysis.json),
  and [all 100 attributed 3B answers](evaluation/arc_capability_20260911/results_continuation_placement_reviewed/composite_answers.jsonl).
- [Frozen protocol](evaluation/arc_capability_20260911/protocol.md),
  [first startup amendment](evaluation/arc_capability_20260911/extra_startup_amendment.md),
  and [remaining-question continuation protocol](evaluation/arc_capability_20260911/continuation_protocol.md).
- [Frozen dataset](evaluation/arc_capability_20260911/dataset.json) and
  [source revision, download URLs, and hashes](evaluation/arc_capability_20260911/source/manifest.json).

Dataset attribution: Allen Institute for AI, Clark et al. (2018),
[AI2 ARC](https://huggingface.co/datasets/allenai/ai2_arc), CC-BY-SA-4.0.
Raw run artifacts remain under
`/home/b2jetson/.local/share/oline-hri/evaluation-runs/arc-capability-20260911/`.

## Complete-system comparison: text pipeline pilot, 11 September 2026

**The comparison produced useful evidence but did not complete its planned
three-round collection.** On the same 40 first-round requests, assistant
rubric review scored small-only at 16 correct, large-only at 21, and CLARA at
19. Small-only was fastest. CLARA had a lower median than large-only in that
round, a worse p95, and a RAM-guard interruption. This does not demonstrate
that the current cascade provides a useful overall advantage.

The primary collection contains **184 of 432 planned attempts**: 166 validated
responses, 17 outputs withheld by application checks, and one RAM interruption.
Three sessions completed all 48 requests, one stopped at 40, and five never
started. All 110 distinct response/evidence review entries were assessed with
system identities hidden; identical entries share judgments while every
observed attempt retains its own score and timing. This is assistant review;
independent human validation remains pending.

The experiment compares the complete **text request pipeline**, including
memory selection, real retrieval, generation, serial model loading, answer
constraints, and validation. It excludes microphone input, STT, TTS, playback,
robot motion, automatic memory capture, and changes arriving during an answer.
The 48 application-specific requests are newly authored, equally divided into
four categories. They complement the public ARC benchmark above; they are
not another established public benchmark.

### Observed coverage and answer quality

**The single-large system is the row “Qwen3 1.7B alone.”** It uses 1.7B for
both memory-need classification and every generated answer, retains that model
within each session, and makes no 0.6B or compute-selection calls. The common
embedding/retrieval and validation components remain active. Its two completed
48-request sessions scored 24/48 and 22/48 under assistant rubric review;
the planned third session did not start.

Correctness is assistant-assessed full-rubric success, including appropriate abstention or uncertainty only when the rubric calls for it. Technical failures count as unsuccessful attempted requests. These are observed rates with unequal coverage, not complete three-round scores or independent samples.

| System | Attempts / planned | Distinct items observed | Validated / attempted | Correct / attempted | Unattempted requests |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qwen3 0.6B alone | 48/144 | 48 | 42/48 (87.5%) | 18/48 (37.5%) | 96 |
| Qwen3 1.7B alone | 96/144 | 48 | 90/96 (93.8%) | 46/96 (47.9%) | 48 |
| CLARA cascade | 40/144 | 40 | 34/40 (85.0%) | 19/40 (47.5%) | 104 |

### Same observed requests across all three systems

This comparison uses the same 40 first-round requests observed in every arm, including interrupted or withheld responses as failures. The subset ends at the cascade stop; it is not a separately sampled benchmark. All latency values are seconds and include the initial cold request.

| System | Correct / common items | Validated / common items | Mean all | Median all | p95 all | Median delivered | p95 delivered |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3 0.6B alone | 16/40 (40.0%) | 35/40 | 2.554 | 2.216 | 3.519 | 2.044 | 3.517 |
| Qwen3 1.7B alone | 21/40 (52.5%) | 39/40 | 21.740 | 19.699 | 40.315 | 19.656 | 40.447 |
| CLARA cascade | 19/40 (47.5%) | 34/40 | 19.959 | 12.135 | 53.773 | 11.826 | 54.457 |

The backend placement differs between arms and sessions. Matched prompts control item coverage, but do not isolate the effect of routing from CPU/GPU placement or device state.

### Correctness by request category

Cells are correct / observed attempts; achieved repetition counts differ between arms. Each category had 36 planned attempts per arm.

| Category | Qwen3 0.6B alone | Qwen3 1.7B alone | CLARA cascade |
| --- | ---: | ---: | ---: |
| Routine general | 8/12 (66.7%) | 21/24 (87.5%) | 6/10 (60.0%) |
| General, multiple constraints | 2/12 (16.7%) | 5/24 (20.8%) | 4/10 (40.0%) |
| Direct personal recall | 8/12 (66.7%) | 18/24 (75.0%) | 8/10 (80.0%) |
| Personal temporal / synthesis | 0/12 (0.0%) | 2/24 (8.3%) | 1/10 (10.0%) |

### Session outcomes and timing

All timing is in seconds, from text-request entry to full validated delivery or failure. Mean, median and p95 here include failed attempts and the initial request. Setup is reported separately below. No request in an interrupted session is replaced.

| Session | Outcome | Attempts / 48 | Validated | Correct | First | Mean all | Median all | p95 all | Total request time |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01_small_r1 | Completed with withheld outputs | 48/48 | 42 | 18 | 11.960 | 2.509 | 2.216 | 3.442 | 120.443 |
| 02_large_r1 | Completed with withheld outputs | 48/48 | 46 | 24 | 38.628 | 20.740 | 18.998 | 39.795 | 995.536 |
| 03_cascade_r1 | RAM-floor interruption | 40/48 | 34 | 19 | 13.299 | 19.959 | 12.135 | 53.773 | 798.377 |
| 04_large_r2 | Completed with withheld outputs | 48/48 | 44 | 22 | 22.936 | 4.970 | 4.475 | 7.458 | 238.568 |
| 05_cascade_r2 | Not started | 0/48 | 0 | — | — | — | — | — | — |
| 06_small_r2 | Not started | 0/48 | 0 | — | — | — | — | — | — |
| 07_cascade_r3 | Not started | 0/48 | 0 | — | — | — | — | — | — |
| 08_small_r3 | Not started | 0/48 | 0 | — | — | — | — | — | — |
| 09_large_r3 | Not started | 0/48 | 0 | — | — | — | — | — | — |

### Delivered-response and failed-attempt latency

These pooled values describe the observed population, whose coverage and placement vary. Validated delivery does not imply a correct answer.

| System | Delivered count | Delivered mean / median / p95, s | Failed count | Failed mean / median / p95, s |
| --- | ---: | ---: | ---: | ---: |
| Qwen3 0.6B alone | 42 | 2.467 / 2.091 / 3.336 | 6 | 2.803 / 2.776 / 3.409 |
| Qwen3 1.7B alone | 90 | 13.136 / 7.417 / 37.058 | 6 | 8.645 / 5.934 / 20.129 |
| CLARA cascade | 34 | 21.013 / 11.826 / 54.457 | 6 | 13.987 / 12.984 / 32.020 |

### Pipeline calls and loading cost

Counts and totals cover observed attempts, including failures. Routing includes loading needed by classifiers. Backend loading time is already contained in request/call time; do not add it again.

| System | Memory / compute / generation calls | Actual 0.6B / 1.7B generator calls | Total routing, s | Total retrieval, s | Total backend loading, s | Loading / total request time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3 0.6B alone | 48 / 0 / 48 | 48 / 0 | 33.268 | 1.269 | 9.672 | 8.0% |
| Qwen3 1.7B alone | 96 / 0 / 96 | 0 / 96 | 306.421 | 2.078 | 43.854 | 3.6% |
| CLARA cascade | 40 / 40 / 40 | 26 / 14 | 170.800 | 1.220 | 463.244 | 58.0% |

### Whole-device resources and setup

RAM and logical swap are MiB; energy is kJ. Peaks and total energy include embedding/database setup and model cleanup. Energy integrates onboard VDD_IN samples without idle subtraction and includes desktop activity; it is not calibrated model-only energy.

| Session | Setup, s | Peak RAM | Peak swap | Peak temperature, °C | Observed interval, s | Whole-interval energy, kJ | Request-interval energy, kJ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01_small_r1 | 2.697 | 5845 | 483 | 61.593 | 124.861 | 1.706 | 1.661 |
| 02_large_r1 | 2.143 | 6467 | 706 | 57.687 | 999.382 | 9.048 | 9.015 |
| 03_cascade_r1 | 3.228 | 6571 | 719 | 59.062 | 802.787 | 7.275 | 7.236 |
| 04_large_r2 | 3.559 | 6416 | 834 | 63.437 | 243.697 | 3.407 | 3.358 |

Request-energy integration covers only sampled overlap. 03_cascade_r1 covers 798.225 of 798.377 request seconds; uncovered intervals are not extrapolated. Scheduler waits and gaps between sessions are outside these intervals.

### Semantic judgment breakdown

Counts retain repeated observations; these are not counts of independent questions. The forbidden-claim flag follows each whole rubric, including general-task constraints, and is not a personal-data disclosure count.

| System | Complete | Appropriate abstention | Appropriate uncertainty | Partial | Incorrect | Inappropriate abstention | Technical failure | Unsupported personal claim | Forbidden / stale rubric claim |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3 0.6B alone | 15 | 3 | 0 | 3 | 18 | 3 | 6 | 2 | 1 |
| Qwen3 1.7B alone | 40 | 6 | 0 | 5 | 35 | 4 | 6 | 3 | 2 |
| CLARA cascade | 16 | 3 | 0 | 3 | 10 | 2 | 6 | 1 | 1 |

### Hardware placement and resource outcomes

| Observed load / session | Qwen3 1.7B layers on GPU | Context / batch | Evidence |
| --- | ---: | ---: | --- |
| Large-only round 1 | 18/29 | 2048 / 512 | [Backend log](evaluation/complete_system_20260911/large_r1_v2_ollama_placement.json) |
| First three large loads in cascade round 1 | 21/29, 21/29, 20/29 | 2048 / 512 | [Bounded initial-load log](evaluation/complete_system_20260911/cascade_r1_initial_ollama_placement.json) |
| Large-only round 2 | 29/29 | 2048 / 512 | [Backend log](evaluation/complete_system_20260911/large_r2_v2_ollama_placement.json) |

Ollama selected these placements automatically; no offload configuration was
changed between sessions. Large-only's 48-request mean was 20.740 seconds in
round 1 and 4.970 seconds in round 2. This variation prevents attributing timing
differences solely to routing or parameter count. The cascade log covers its
initial loads, not every subsequent placement. Both sole-model controls retain
their model within a session; the cascade preserves its deployed serial
switching policy. No concurrent model inference was requested.

Cascade round 1 crossed the **768 MiB available-RAM runtime floor** during
request 40. The monitor stopped the session and cleanup unloaded the models.
The exact instantaneous available-memory reading was not saved; 500 ms sampled
RAM use cannot reconstruct the magnitude of that crossing. The eight remaining
requests in that session were not retried or filled from a new session.
This is a feasibility failure under the stated resource policy, not a claim
that the hardware crashed or that no other deployment policy could work.

The untouched large-only round 2 then completed under the same limits. Its
logical swap occupancy ended at 833.75 MiB, below the 1 GiB runtime ceiling but
above the next session's 768 MiB startup ceiling. The scheduler waited its
900-second allowance and stopped at 15:45:49 UTC, still above that gate
(830.5 MiB at the final scheduler snapshot). Sessions 5–9 never initialized a
model or attempted a request. They are unattempted slots after a carry-over
admission block, not five additional runtime failures. No limits were relaxed,
and no user application, service, swap device, or power setting was changed.

All executed sessions ended with no resident model and no cleanup error.
Boot ID, 15 W mode, and zero thermal-trip counters were preserved. Swap
occupancy was not cleared. See the [resource continuation record](evaluation/complete_system_20260911/resource_failure_continuation.md)
and [device audit](evaluation/complete_system_20260911/final_device_audit.json).

### What the pipeline diagnostics show

There were 74 retrieval calls. Among 80 personal requests whose rubric required
specific memory IDs, all required evidence reached generation on 51 attempts;
29 lacked at least one required record. Among 66 delivered personal answers
requiring citations, 32 omitted at least one required citation. These are
mechanical evidence-coverage counts, not semantic accuracy estimates, and
include repeated questions. They help explain why a larger generator alone
cannot repair the complete pipeline's omissions.

A concrete example is the self-contained timer question: start at 10:35 and
run for 20 minutes. Every executed session retrieved irrelevant personal facts
and required two irrelevant citations in its output schema; the temporal-memory
validator then withheld the candidate. The small-only and cascade candidates
contained the correct 10:55 time; both large-only candidates said 11:15.
None earned credit because no validated answer was delivered. This implicates
the combined retrieval, citation, generation, and validation path; it does not
establish a validator-only false positive.

The prepared memories had the same verified snapshot in every executed
session: 25 remember operations, one correction, and one forget operation
left 23 eligible current records under a seven-day retention window. No
rubric-forbidden memory ID was observed in supplied evidence or delivered
citations. This limited snapshot check does not establish reliable live
correction, forgetting, conflict resolution, or memory capture. Personal
temporal/synthesis full-rubric success was low in every observed arm.

Recorded reference IDs were empty in all 166 delivered replies. An explicit
verified-relationship answer constraint appeared once per executed session;
no response transformation was recorded on delivered replies. These fields
are unrecorded on the 18 failed/interrupted attempts, so their absence there
is not evidence that a helper did not execute. The common application includes
helpers and answer constraints, but their presence must not be credited as
unconstrained model reasoning. Full [pipeline diagnostics](evaluation/complete_system_20260911/results_reviewed/pipeline_diagnostics.json)
retain the source hashes and timer example.

### Configuration and interpretation limits

| Item | Controlled configuration / scope |
| --- | --- |
| Device | Jetson Orin Nano 8 GB; 15 W mode 0; active fan; SD-backed root storage |
| LLMs | `qwen3:0.6b` and `qwen3:1.7b`, both Q4_K_M; exact digests in `freeze_v2.json` |
| Inference | Ollama 0.33.3; context 2048; output ceiling 192; temperature 0; seed 42; thinking disabled |
| Single-model controls | One own-model memory classifier; fixed sole generator even for composed answers; no compute classifier or peer-model fallback |
| Cascade | Production two-classifier routing, helper overrides, and serial loading/unloading |
| Shared memory path | BGE-small-en-v1.5 on CPU; equivalent isolated SQLite stores; hybrid retrieval; top-three candidates; common filtering/schema/validators |
| History / lifecycle | Fresh history per request; natural model residency within a session; lifecycle operations completed before queries |
| Workload | 48 authored items, 12 per category; same order in each session; three counterbalanced rounds planned |
| Startup policy | At least 2 GiB available RAM; swap at most 768 MiB; temperature below 55°C; no model resident |
| Runtime policy | At least 768 MiB available RAM; swap at most 1 GiB; temperature below 68°C; live telemetry and at most one resident model |
| Latency boundary | Entry to `Conversation.send` through complete validated text response or failure; not first token or speech-start latency |
| Quality assessment | Frozen claim/citation rubrics; assistant review with system identities hidden; human validation pending |

The same 40-request comparison is the deterministic interrupted first-round
prefix, with ten items per category. Balance does not make the missing tail
random or restore full coverage. The large-only pooled result contains two
repetitions; small-only has one, and cascade has one incomplete repetition.
The near-equal pooled large/cascade percentages are not evidence of equivalent
quality. Shared profile/scenario dependencies and repeated prompts preclude
treating observed attempts as independent quality samples. No completed
three-repetition paired latency interval or complete correct-by-deadline curve
is available; neither is presented as a completed result.

These are reasonable current-system controls, not an equal-budget optimization
search establishing each system's best achievable performance. The selector
LLM, effective route-dependent answer guidance, supplied evidence, timeout
policy, and CPU/GPU placement can differ across arms. Whole-device measurements
also include background activity. A matched-evidence generator comparison,
separate retrieval-policy ablation, stable-placement replication, live-memory
tests, and spoken-system timing remain separate work.

No user-approved quality floor or responsiveness deadline was set. The result
therefore does not prove the strongest hypothesis that optimized small-only
fails quality, optimized large-only fails responsiveness, and adaptive selection
meets both. It supplies a reproducible pilot showing current quality gaps,
loading overhead, and resource-admission limitations. It does not justify a
claim that two generators are necessary for CLARA on this workload.

### Evidence and reproducibility

- [Stage 2 overview](evaluation/complete_system_20260911/README.md),
  [frozen protocol](evaluation/complete_system_20260911/protocol.md),
  [workload and prewritten rubrics](evaluation/complete_system_20260911/workload.json),
  and [source/model freeze](evaluation/complete_system_20260911/freeze_v2.json).
- [Final detailed report](evaluation/complete_system_20260911/results_reviewed/report.md),
  [machine-readable analysis](evaluation/complete_system_20260911/results_reviewed/analysis.json),
  [semantic review](evaluation/complete_system_20260911/results_reviewed/semantic_review.json),
  and [final artifact verification](evaluation/complete_system_20260911/results_reviewed/final_snapshot_verification.json).
- [Reproducible tables](evaluation/complete_system_20260911/results_tables/tables.md),
  [same-request metrics](evaluation/complete_system_20260911/results_tables/matched_first_round.json),
  [numerical audit](evaluation/complete_system_20260911/numerical_audit.md),
  and [methodology review](evaluation/complete_system_20260911/methodology_review.md).
- [Runner accounting amendment](evaluation/complete_system_20260911/runner_revision_v2.md),
  [zero-request startup resume](evaluation/complete_system_20260911/session_resume.md),
  and [resource-failure continuation](evaluation/complete_system_20260911/resource_failure_continuation.md).

The initial 12-attempt runner diagnostic is excluded from the primary score
and preserved separately. Its narrow output-error accounting correction did
not tune the prompts, model settings, workload, or rubric; no favorable answer
was selected from the repeated invocations. Existing complete and interrupted
primary observations were preserved unchanged. The 34 frozen execution files
still matched after collection. The regression/evaluation suite passed 122
tests, with two additional focused pipeline-diagnostic tests passing.

Primary raw artifacts remain under
`/home/b2jetson/.local/share/oline-hri/evaluation-runs/complete-system-20260911-v2-resumed/`.
The original diagnostic and zero-inference startup rejection retain their own
sibling directories. The frozen workload uses fictional memories; the live
personal-memory database was not used or changed.

### Subsequent implementation: lightweight routing (2026-09-12)

Step 1, reducing routing and switching overhead, is implemented as opt-in
`chat --routing-policy lightweight`. It removes the compute-classifier LLM
call, makes zero or one memory-classifier call, retains the active generator,
and defers switching away from large until a second consecutive easy request.
This is an untrained policy; answer-quality and efficiency improvements have
not been measured. Offline tests verify routing, model lifecycle, cleanup,
citations, freshness, privacy, and existing-mode compatibility.
Final offline discovery: 783 passed, 26 skipped, zero failures or errors;
live tests were disabled. This is implementation validation, not an accuracy
or speed benchmark.

| New-policy device validation | Outcome |
| --- | --- |
| Original-policy diagnostic preflight | Blocked: 812.5 MiB swap exceeds 768 MiB startup gate |
| Lightweight-policy diagnostic preflight | Blocked: 812.5 MiB swap exceeds 768 MiB startup gate |
| Inference attempted | 0 requests; no new latency or correctness measurements |
| Device configuration | No swap, power, service, or model changes; no models resident at final preflight |

The [implementation record](evaluation/lightweight_routing_20260912/README.md)
contains source, tests, diagnostic commands, and machine-readable preflight
evidence. The existing result tables remain results for the earlier code.
All 34 files in the Stage 2 execution freeze were verified and copied into
[frozen_source_v2](evaluation/complete_system_20260911/frozen_source_v2/archive_manifest.json)
before the change. The working tree now intentionally differs from that freeze;
new-policy measurements require a new freeze and separate result artifacts.

### Subsequent implementation: shared memory pipeline (2026-09-12)

Step 2 is implemented across the shared small-only, large-only, and adaptive
memory path. It improves personal-intent detection, subject/attribute matching,
coverage of requested fields, and conflict preservation. Unlinked candidate
text is no longer supplied to generation. Bounded direct recall can explicitly
mark unknown fields; bounded event comparisons compute from consistent stored
timestamps while preserving citation, context, and freshness checks.

The following are **offline development checks**, not new model benchmark
results. The earlier authored prompts are development data for these fixes.

| Check | Before | After |
| --- | ---: | ---: |
| Explicit correct personal-memory intent | 16/24 prompts | 24/24 prompts |
| Explicit correct general/no-memory intent | 1/24 prompts | 2/24 prompts |
| Unresolved intent, deferred to classifier | 31/48 prompts | 22/48 prompts |
| All required facts selected from identical recorded candidates | 47/56 attempts | 54/56 attempts |
| Required fact occurrences selected | 63/75 | 73/75 |

Both intent policies have zero explicit wrong decisions on these prompts;
no classifier was rerun for unresolved cases. Selection covers only the 74
historical attempts with recorded candidates, of which 56 require particular
facts. The other 110 attempts are unassessed for selection. All 73 required
fact occurrences actually present in those lists were selected after the
change; two badge-preference occurrences were absent. No required-ID selection
regressions occurred on the replayed candidates. Repetitions are dependent.

These counts differ from the historical 51/80 complete supplied-evidence figure:
they replay a linking function on a smaller population, while the old full
Conversation could supply an unlinked first neighbor. They do not establish
new retrieval recall, answer accuracy, latency, or cascade superiority.

Final offline regression discovery: **828 passed, 26 skipped, zero failures or
errors** (854 tests reported), with all live-test flags disabled. The
[validation record](evaluation/memory_pipeline_20260912/offline_validation.json)
preserves the command and file hashes.

The [implementation and validation record](evaluation/memory_pipeline_20260912/README.md),
[final replay](evaluation/memory_pipeline_20260912/offline_replay_v2/report.md),
and [historical failure inventory](evaluation/memory_pipeline_20260912/failure_inventory.md)
preserve the stages and denominators. Source snapshots, earlier results, and
raw observations remain intact. No real model, embedding, or personal-database
experiment ran for this step. Independent quality testing on new cases remains
necessary before claiming a system-level improvement.

### Step 3: completed post-fix comparison with revised swap allowance (2026-09-12)

**All nine sessions and 432 planned attempts are complete:** 144 per system,
using the same 48 requests in three rounds. The first round ran large-only,
cascade, then small-only as requested; later rounds rotated the order. This
revised experiment is separate from the earlier restricted-swap attempts below.
The [frozen protocol and artifacts](evaluation/post_memory_comparison_20260912/frozen_v2/freeze.json)
preserve the unchanged application, memory pipeline, workload and generation
settings. This is an exploratory repeat of the partly observed assistant-authored
application pilot, not a new public benchmark or independent confirmatory test.

Hardware was the 8 GB Jetson Orin Nano in 15 W mode, running Ollama 0.33.3.
All arms used Q4_K_M artifacts, 2048-token context, a 192-token output cap,
temperature zero, seed 42, thinking disabled, and CPU BGE-small-en-v1.5
embeddings. The installed metadata reports 751.63M and 2.0B parameters for
the `qwen3:0.6b` and `qwen3:1.7b` tags respectively; the tag names alone are
not exact parameter measurements. Only one generator model was resident at a time.

| System | Attempts | Validated delivery | Full-rubric success | Mean, s | Median, s | p95, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `qwen3:0.6b` alone | 144/144 | 135/144 | 42/144 (29.2%) | 2.314 | 2.090 | 3.270 |
| `qwen3:1.7b` alone | 144/144 | 139/144 | 44/144 (30.6%) | 11.255 | 8.955 | 25.430 |
| CLARA lightweight cascade | 144/144 | 140/144 | 46/144 (31.9%) | 8.916 | 7.749 | 18.772 |

Time runs from text-request entry through complete validated response or
failure, including memory selection, retrieval, generation and model loading.
The table retains every failure and each cold first request. Delivered-answer
mean/median/p95 were 2.276/2.021/3.281 seconds for small-only,
11.242/8.984/25.836 for large-only, and 8.962/7.827/19.060 for cascade.
There were respectively nine, five and four technical failures. Neither these
text timings nor a successful delivery establishes spoken responsiveness or
semantic correctness. No quality or response-time acceptance threshold was
selected, so no requirement-level pass/fail claim is made.

| Request category | Small-only success | Large-only success | Cascade success |
| --- | ---: | ---: | ---: |
| Routine general | 12/36 (33.3%) | 19/36 (52.8%) | 18/36 (50.0%) |
| General with multiple constraints | 3/36 (8.3%) | 8/36 (22.2%) | 11/36 (30.6%) |
| Personal recall | 27/36 (75.0%) | 17/36 (47.2%) | 17/36 (47.2%) |
| Personal temporal / synthesis | 0/36 (0.0%) | 0/36 (0.0%) | 0/36 (0.0%) |

The larger-model systems did better on the general categories, while small-only
did better on personal recall. All three still failed every full temporal /
synthesis rubric. These are complete-system outcomes: ambiguous memory decisions
use each system's available model and can produce different supplied evidence.
They do not isolate generator capability. Memories were fictional, changed
through lifecycle APIs before the questions, and then evaluated as a fixed
snapshot; this does not measure live update propagation. Speech input/output,
automatic memory capture and robot motion were excluded.

| System | Successes in rounds 1 / 2 / 3, each out of 48 | Mean seconds in rounds 1 / 2 / 3 |
| --- | --- | --- |
| Small-only | 14 / 14 / 14 | 2.335 / 2.336 / 2.271 |
| Large-only | 13 / 15 / 16 | 17.448 / 7.957 / 8.359 |
| Cascade | 14 / 16 / 16 | 7.288 / 10.372 / 9.087 |

The cascade's pooled mean was 20.8% lower than large-only, but **large-only was
faster in rounds 2 and 3**. Ollama placement differed: the first large-only
session reported 61.5% GPU allocation versus 83.6–86.2% for the large model in
the first cascade session. These allocation ratios are not utilization or a
fraction of computation. They confound attribution of the pooled timing
difference to routing.

The cascade actually generated on small **3/144** times and large **141/144**
times. Its narrow easy-request rules and two-consecutive-easy switching rule
selected small only once per round. This is not evidence that 141 requests
needed the larger model. All arms made 99 memory-classifier calls, zero
compute-classifier calls and 144 generator calls, with zero fallbacks.
Recorded backend loading totaled 28.363 seconds for small-only, 72.821 for
large-only and 166.549 for cascade; those times are already included in request
latency. The current cascade therefore demonstrates neither frequent useful
small-model selection nor lower loading cost.

Quality was scored by two assistant reviewers working separately without
system labels, timing, repetition or frequency. They initially agreed on the
judgment and both disclosure flags for **142/145 unique output groups (97.9%)**.
A third blinded assistant resolved three flag disagreements and one additional
shared grounding error found during audit. All 145 groups now map to all 432
attempts without pending or conflicting scores. Success includes appropriate
abstention only when the rubric calls for it. Repeated answers reuse a judgment
only for the same request and supplied-evidence set. The 144 attempts per arm
are **48 dependent requests repeated three times**, with additional shared
scenario/profile dependencies; they are not 144 independent quality samples.
Independent human validation remains pending. The
[review record](evaluation/post_memory_comparison_20260912/reviews_v2/review_agreement_v2.json)
preserves initial judgments, adjudications and the shared-error correction.

For this test only, both swap-use ceilings were raised to **3554.164 MiB**,
reserving 256 MiB from the existing **3810.164 MiB** logical capacity. No swap
device was resized. Startup RAM/temperature and runtime RAM/temperature guards
remained in force. Peak recorded logical swap across the nine sessions was
1666 MiB; peak whole-device RAM was 6530 MiB and temperature 62.031°C.
Existing zram stores compressed pages in physical RAM: logical swap occupancy
cannot be added to physical RAM capacity or usage and is not a measure of
active swapping. Jetson CPU and GPU allocations share physical memory.

One zero-request temperature rejection interrupted the first launch sequence
after its first two completed sessions. The continuation retained those exact
sessions and completed the remaining seven, waiting below 54°C before handoff
to the unchanged below-55°C startup gate. No answered request was retried or
spliced into a session. Two separately archived offline compatibility corrections
let the analyzer recognize the frozen revised swap policy and the proven
zero-request rejection's revised error wording; they changed no runtime,
answers, rubrics or scoring. The
[audited analysis](evaluation/post_memory_comparison_20260912/analysis_v2_reviewed/analysis.json)
reports complete collection and valid artifact integrity, preserving the
original findings and correction proofs.

The device remained in 15 W mode with unchanged boot and zero thermal-trip
counters. Every session cleaned up successfully. The
[final host audit](evaluation/post_memory_comparison_20260912/final_state_v2.json)
confirms no resident model, unchanged swap devices/capacity, source, model
metadata and Ollama version, and preservation of the original experiment
limits. The revised allowance ended with its experiment processes; live RAM
and swap usage need not equal their starting values. Pre-freeze offline
validation reported **871 passed, 26 skipped, zero failures/errors** (897 tests).

**Interpretation:** this pilot does not yet justify the cascade over a single
model. It gained only two full-rubric successes over large-only across 144
dependent attempts, and four over small-only while taking 3.85 times its mean
request time. Its pooled speed advantage over large-only is confounded by
placement and reverses in two rounds. The general-task improvements and
personal-recall regressions identify a tradeoff to investigate, not demonstrated
adaptive-selection superiority or satisfaction of deployment requirements.

The [complete tables](evaluation/post_memory_comparison_20260912/report_v2/tables.md)
include every session, cold/later distributions, semantic failure categories,
actual calls, placement, RAM, logical swap and sampled whole-device energy.
Energy includes background activity and excludes scheduler waits; it is not
model-only energy. The [collection record](evaluation/post_memory_comparison_20260912/README.md)
links raw observations, frozen sources, review evidence and reproducible analysis.
Earlier ARC results and restricted-swap attempts remain separate and unchanged.

#### Earlier restricted-swap comparison — historical incomplete attempt

The new experiment uses policy-first small-only and large-only controls and
the lightweight cascade, sharing the updated memory pipeline. The
[source, workload and protocol were frozen](evaluation/post_memory_comparison_20260912/frozen_v1/freeze.json)
before inference. The 48 new assistant-authored requests cover four strata;
three counterbalanced rounds planned 432 attempts. This is an application
pilot, not a public benchmark or an independent confirmatory test.

**Only the first small-only session ran.** It finished all 48 requests with
three withheld outputs. After 31 recovery checks spanning 600.946 seconds,
swap still exceeded the unchanged startup limit, so the batch stopped before
large-only. Eight sessions and 384 requests remain unattempted.

| System | Attempts / planned | Validated delivery | Correct / attempted | Mean, s | Median, s | p95, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3 0.6B alone | 48/144 | 45/48 | 14/48 (29.2%) | 2.416 | 2.159 | 3.322 |
| Qwen3 1.7B alone | 0/144 | Not attempted | Not measured | — | — | — |
| Lightweight cascade | 0/144 | Not attempted | Not measured | — | — | — |

Correctness is full-rubric success assessed by two assistant reviewers in
fresh contexts using a worksheet without system labels. They agreed on all
48 judgments and disclosure flags. Independent human review remains pending.
The 14 successes are 11 complete answers and three appropriate abstentions;
the remaining outcomes are six partial, 22 incorrect, three inappropriate
abstentions and three technical failures. Withheld text earns no success credit.

| Request category | Small-only correct / attempted | Large-only | Cascade |
| --- | ---: | ---: | ---: |
| Routine general | 4/12 | Not attempted | Not attempted |
| General with multiple constraints | 1/12 | Not attempted | Not attempted |
| Personal recall | 9/12 | Not attempted | Not attempted |
| Personal temporal / synthesis | 0/12 | Not attempted | Not attempted |

Timing includes the cold first request and failures. The first request took
13.468 seconds; the later 47 averaged 2.180 seconds. There were 33 actual
memory-classifier calls, zero compute-classifier calls and 48 generator calls,
all on 0.6B. All 48 post-request snapshots reported its full loaded model
allocation in VRAM. No delivered answer recorded a literal composition.
Peak whole-device RAM/swap were 5837/997 MiB and temperature 61.656°C.

The fresh workload still exposed memory and reasoning failures: nine of 24
personal requests were routed without memory, and only 11 of 20 requests
requiring specific facts received all required IDs. Review identified 11
outputs with unsupported personal claims. Two violated explicit forbidden-claim
rubrics: an invented departure time and a wrong-person ticket assignment;
these are not two forgotten/expired-memory disclosures. The frozen code and
workload were not changed in response.

At the batch stop, available RAM was 2390.996 MiB, swap 988.5 MiB against the
768 MiB startup ceiling, and maximum temperature 52.437°C. Model cleanup
passed; no models remained resident, with unchanged boot, power mode and
thermal-trip counters. No system configuration was changed. This establishes
a collection block under these desktop conditions, not intrinsic 1.7B
infeasibility. There is no measured large/cascade result or common all-arm
sample, so no cascade advantage or improvement over older workloads can be
claimed. Completing the comparison requires device state within the declared
limits and separately preserved collection.

The [full tables and detailed timings](evaluation/post_memory_comparison_20260912/results_reviewed/tables.md),
[reviewed analysis](evaluation/post_memory_comparison_20260912/results_reviewed/analysis.json),
[review agreement](evaluation/post_memory_comparison_20260912/reviews/review_agreement.json),
[pipeline diagnostics](evaluation/post_memory_comparison_20260912/small_r1_pipeline_diagnostics.json),
and [terminal batch record](evaluation/post_memory_comparison_20260912/run_v1/batch_finish.json)
preserve the evidence. Implementation validation passed 862 tests with 26
skipped (888 reported); observed-run artifact integrity passed. Earlier
benchmark results and source archives remain unchanged.

#### Subsequent large-only attempt (2026-09-12)

The user-requested separate large-only session used the same frozen source,
models, workload and settings. It was blocked before inference: startup swap
was **988 MiB**, above the unchanged **768 MiB** ceiling. Available RAM
(2391.012 MiB) and maximum temperature (51.281°C) passed their limits.
The runner attempted **0/48 requests**, so no large-model quality or latency
result can be added. Source/model/server checks passed; no model remained
resident and no system configuration changed. The earlier small-only results
and interrupted batch are preserved. The [attempt record and evidence](evaluation/post_memory_comparison_20260912/large_only_20260912T120926Z/README.md)
document this separately from the original collection.

### Step 4: final quality, latency and cost analysis (2026-09-12)

The final analysis and paper figures are complete for the existing Step 3
comparison. This adds no inference, new test cases or answer judgments. It
joins the 432 attempts to all 145 resolved blinded review groups and checks
the complete deadline curves against those request-level judgments. The saved
`row_metrics.semantic_quality` placeholder is not a score; the resolved review
and blinded mapping are the authoritative quality sources. Independent
recalculation agrees with the counts, timings, paired outcomes and energy sums.

Correct answers delivered within a deadline are divided by **all 144 attempts
per system**, including withheld and failed answers:

| Descriptive deadline | Small-only | Large-only | Cascade |
| --- | ---: | ---: | ---: |
| 5 seconds | 42/144 (29.2%) | 11/144 (7.6%) | 20/144 (13.9%) |
| 10 seconds | 42/144 (29.2%) | 32/144 (22.2%) | 43/144 (29.9%) |
| 15 seconds | 42/144 (29.2%) | 39/144 (27.1%) | 46/144 (31.9%) |
| 30 seconds | 42/144 (29.2%) | 44/144 (30.6%) | 46/144 (31.9%) |

These are post-collection reading points, not selected application requirements.
The [full empirical curves](evaluation/final_tradeoff_analysis_20260912/artifacts_v2/deadline_curves.pdf)
show every observed deadline and separate full-rubric correctness from validated
delivery. Small-only delivers all its correct answers within five seconds;
cascade reaches its slightly higher total by fifteen seconds. Validated delivery
alone greatly exceeds semantic success and must not be presented as accuracy.

![Correct and validated delivery over time](evaluation/final_tradeoff_analysis_20260912/artifacts_v2/deadline_curves.png)

| System | Whole sampled energy, kJ | Joules / attempted task | Total joules / full success | Backend loading total, s |
| --- | ---: | ---: | ---: | ---: |
| Small-only | 4.662 | 32.4 | 111.0 | 28.363 |
| Large-only | 16.736 | 116.2 | 380.4 | 72.821 |
| Cascade | 14.291 | 99.2 | 310.7 | 166.549 |

Energy sums sampled whole-device VDD_IN over the three sessions for each arm,
including setup, cleanup and background activity, with no idle subtraction.
Scheduler waits are excluded. Dividing total energy by full successes retains
the cost of every wrong or failed request; it is not energy measured only on
correct requests. Request-window energy coverage was 99.741%, 99.944% and
99.973% for small, large and cascade respectively; separate request-window
totals are preserved in the numeric report. These are onboard estimates, not
isolated model energy. Loading is already included and must not be added again.

The [quality/time and repetition figure](evaluation/final_tradeoff_analysis_20260912/artifacts_v2/quality_latency_rounds.pdf)
shows the pooled comparison beside all three rounds. Large-only was slower
than cascade in round 1 but faster in rounds 2 and 3. Different CPU/GPU
allocation confounds the pooled advantage. The cascade used small on only
3/144 generations and incurred more backend loading than either fixed system.
Small-only had shorter request time on every matched attempt against both
other systems in this pilot.

Paired results show limited complementarity: large-only succeeds where
small-only fails on 4, 6 and 7 cases in the three rounds, but small-only succeeds
where large-only fails on five cases in every round. These are complete-system
outcomes with potentially different supplied memories, not a pure generator
capability test or a deployable routing oracle. No alternative router's latency
is inferred from these runs.

**Conclusion:** a quality/time tradeoff is observed, but a useful causal benefit
from the current adaptive selector is not established. Small-only is much faster
and uses less sampled energy; cascade adds four full successes across 144
dependent attempts. No quality/deadline requirement, equivalence margin or
independent-sample significance claim is introduced. All three systems still
score zero on the full temporal/synthesis rubrics. The 48 repeated items share
41 scenarios, and the judgments remain assistant-only pending human validation.

The [complete Step 4 analysis](evaluation/final_tradeoff_analysis_20260912/README.md)
provides PNG/PDF/SVG figures, CSV plot data, paired results, source/input hashes,
and an independent arithmetic check. The analysis preserves Step 3's raw
records and uses an isolated plotting environment. Retrieval-policy ablations,
live changing-memory evaluation and integrated speech testing remain separate
unfinished experiments; this reporting step does not complete them.

### Completed routing-overhead experiment (2026-09-12)

The new four-turn experiment is complete: **144 sequence attempts and 576
turns**, comprising 432 main-system turns and 144 diagnostic replay turns.
There were 546 validated deliveries and 30 technical failures, all retained.
**Adaptive routing recovered its measured costs relative to large-only on the
pooled workload, chiefly on the easy-only sequences; it did not recover its
costs relative to small-only, and no quality–latency dominance was established.**
This is a new retained-history, cold-sequence experiment, separate from the
previous 48-request post-memory sessions and their reported results above.

Each of 12 four-turn sequences ran three times with counterbalanced main-system
order, followed by a diagnostic replay. Every sequence began with no LLM
resident and a new CPU embedder; OS caches remained intact. All systems used
`qwen3:0.6b`/`qwen3:1.7b`, context 2048, output cap 192, temperature 0, seed 42
and thinking disabled, with shared memory and answer helpers. Startup below
begins at BGE initialization and includes prepared memory, router and
Conversation setup. Sequence latency includes that startup, the four request
attempts and measured intervening work; admission/client setup, cleanup and
scheduler waits are reported separately.

| System | Delivered / attempted | Fully correct / attempted | Mean startup, s | Mean request, s | Mean four-turn sequence, s |
| --- | ---: | ---: | ---: | ---: | ---: |
| Small-only | 135/144 | 66/144 (45.8%) | 2.820 | 4.279 | 20.115 |
| Large-only | 139/144 | 97/144 (67.4%) | 2.607 | 18.916 | 78.454 |
| Lightweight adaptive | 136/144 | 77/144 (53.5%) | 2.891 | 15.656 | 65.694 |
| Diagnostic routing-bypass replay | 136/144 | 77/144 (53.5%) | 2.714 | 13.636 | 57.434 |

Adaptive took **45.579 seconds more than small-only**, **12.760 seconds less
than large-only**, and **8.261 seconds more than its replay** per four-turn
sequence on average. The replay bypassed selection while restoring exact
adaptive history and requiring identical generation models, messages, schemas
and HTTP options. It retained shared retrieval and validation. It is a
diagnostic requiring an already observed trace, not a deployable routing policy.

The following paired differences are **adaptive minus comparator**; negative
values mean measured adaptive savings. Each pattern has three authored variants,
each averaged across three dependent timing repetitions.

| Pattern | Versus small-only, s | Versus large-only, s | Versus replay, s | Interpretation |
| --- | ---: | ---: | ---: | --- |
| EEEE | +0.831 | −50.912 | +2.626 | Clear saving against large-only; small-only still faster on average |
| DDDD | +65.954 | −3.682 | +4.347 | All adaptive generations used large; the small observed difference cannot be credited to choosing a smaller generator |
| EDED | +51.095 | −2.003 | +5.965 | Small, variable pooled saving against large-only; no stable mixed-pattern advantage |
| DDEE | +64.436 | +5.558 | +20.104 | Returning to small did not pay back within the measured four turns |

All nine adaptive DDEE repetitions actually selected and generated
large/large/large/small: the first easy request stayed large and the second
returned to small. These returns occurred on turn four, so **there is no
observed fifth-turn benefit after returning to small**. Adaptive generated
54 answers on small and 90 on large. Each main system made 93 memory-classifier
calls and zero compute-classifier calls; replay made zero selection calls.
Monotonic instrumentation separates routing/bookkeeping, classifier, retrieval,
unload and verified eviction, generation, validation and complete requests.
Backend loading remains nested inside its actual caller's wall span. A cold
classifier can pay a model load that the replay instead pays during generation;
adding those loads again would overstate selection cost.

Correctness was assessed against frozen rubrics and actual evidence by two
blinded assistant contexts. They agreed on 145/146 distinct output groups;
one disagreement was adjudicated, covering every attempt. Independent human
review remains pending. Adaptive added 11 correct answers relative to small-only
but was much slower, and lost 20 correct answers relative to large-only while
saving time. Matching aggregate adaptive/replay correctness does not imply
identical answers. Fast rejected responses receive no useful-answer credit.

Placement, output length and chronology limit causal attribution. Small-model
allocations were fully reported in VRAM; large-model GPU allocation fractions
varied across systems and repetitions. Those fractions describe allocated
bytes, not the proportion of computation performed on GPU. Even with identical
replay requests, adaptive and replay generated 6,346 and 6,632 tokens respectively
across all attempts. Replay always ran last in its block; allocator/cache state,
temperature and the collection pause can contribute to paired differences.
The 12 authored sequences share task forms, social prompts and a fictional
profile. Neither the 576 turns nor the three timing repetitions are independent
samples; descriptive cluster intervals do not establish population superiority.

A documented v1 harness error treated an ordinary final-turn
`ResponseValidationError` as fatal. Its complete four-turn sequence and all
88 original attempts were preserved unchanged. A prospective v2 amendment fixed
failure handling before the remaining 488 attempts; no answer was retried and
no partial sequence was spliced. Models, workload, application behavior,
settings, guards and timing boundaries stayed unchanged. Offline validation
reported **946 tests: 920 passed, 26 skipped, zero failures/errors**. The
[corrected final collection-integrity audit](evaluation/routing_overhead_20260912/final_collection_audit_v2_corrected/summary.json)
passed; its [audit-only correction](evaluation/routing_overhead_20260912/final_collection_audit_correction.json)
retains the preceding audit and changes no raw observations. This audit concerns
recorded controls/accounting and does not replace semantic or human review.

The [completed experiment report and commands](evaluation/routing_overhead_20260912/README.md),
[reviewed tables](evaluation/routing_overhead_20260912/report_reviewed_v2/report.md),
[sequence-latency figure](evaluation/routing_overhead_20260912/report_reviewed_v2/sequence_latency.pdf),
[component figure](evaluation/routing_overhead_20260912/report_reviewed_v2/components.pdf),
[paired component tables](evaluation/routing_overhead_20260912/report_details_final_v2/paired_sequence_components.csv),
[following-turn details](evaluation/routing_overhead_20260912/report_details_final_v2/cold_transition_following.csv),
and [review provenance](evaluation/routing_overhead_20260912/reviews_final_v2/review_agreement.json)
preserve the complete evidence. Earlier evaluations remain unchanged. The
measured easy-only saving supports a narrow routing benefit against large-only;
a general useful-answer advantage, an optimal hysteresis threshold and the
post-return fifth-turn saving remain unestablished.


## Independent personal-memory retrieval — 13 September 2026

Completed **864/864 attempts**: 48 fresh fictional requests × two fixed
Qwen3 generators × OFF/ALWAYS PERMITTED/SELECTIVE × three timing repetitions.
All 856 delivered answers and eight resource-guard interruptions are retained.
The [completed report](evaluation/independent_retrieval_20260913/report_reviewed_v3/report.md)
and [category, paired and component tables](evaluation/independent_retrieval_20260913/report_reviewed_v3/tables.md)
show a model-dependent tradeoff: selective retrieval reduces unnecessary
memory access, but does not establish a general quality-and-speed win.

| Generator | Policy | Task success | Known recall | Unnecessary retrieval | Mean complete request, s | Failures |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 51/144 | 0/78 | 0/24 | 1.577 | 0 |
| qwen3:0.6b | ALWAYS PERMITTED | 93/144 | 53/78 | 24/24 | 1.941 | 0 |
| qwen3:0.6b | SELECTIVE | 91/144 | 53/78 | 6/24 | 2.030 | 0 |
| qwen3:1.7b | OFF | 63/144 | 0/78 | 0/24 | 7.380 | 1 |
| qwen3:1.7b | ALWAYS PERMITTED | 86/144 | 53/78 | 24/24 | 10.460 | 3 |
| qwen3:1.7b | SELECTIVE | 89/144 | 52/78 | 3/24 | 9.117 | 4 |

For 0.6B, SELECTIVE preserves the same per-request mean known-recall success
on all 26 known questions while cutting unnecessary retrieval by **75%**.
It loses two overall successes and adds **0.089 s** per attempted request
(descriptive 95% scenario interval +0.023 to +0.147 s), about 4.6% slower.
For 1.7B, SELECTIVE cuts unnecessary retrieval by **87.5%** and saves
**1.342 s** per request (−2.071 to −0.614 s), about 12.8%, after selection
costs. It loses one known-recall success; one known question improves and two
worsen across repetitions. Although overall success increases by three,
p95 latency worsens from **20.657 to 30.457 s**. These findings do not establish
noninferiority or consistently faster responses.

Direct and multi-fact recall reach 21/24 and 23/24 successes under both
retrieval policies and generators, but paraphrased recall reaches only
**6/24**. On unknown/conflicting information, SELECTIVE reaches 9/24 for
0.6B and 6/24 for 1.7B, versus OFF's 21/24 and 23/24. No evidence condition
produces reviewed explicit conflict handling. Cautious abstention on a known
authorized fact receives no personalization credit; caution and unsupported
claims are reported separately. All four evidence conditions supply 76.3%
of relevant fact occurrences. SELECTIVE reduces irrelevant records inspected
and supplied, but does not eliminate unnecessary retrieval or disclosure.

Authorization remains separate from relevance selection. Consent, profile,
prohibited-data, correction/deletion, expiry and freshness checks stay active;
audited authorization violations were zero. Each request has fresh history,
and OFF receives no personal facts through prompts or helpers. Models,
prompts, applicable helper configuration, validators and prepared snapshots
are fixed. Settings are context 2048, output cap 192, temperature 0, seed 42,
thinking disabled. Every generation and required classifier call uses the
condition's sole physical model. Lifecycle events were applied before
collection; live memory propagation remains separate.

Eight unchanged available-memory-floor interruptions required independently
approved continuations of only never-attempted suffixes. No failed request
was retried. The 18 logical blocks span **26 physical fragments**, with
**35 rejected zero-request admissions** preserved. Cold starts, failures,
loading and selection costs remain in primary request time; setup, cleanup,
admission overhead and inter-run gaps are separately scoped. Sustained
1.7B residency is not established. Variable CPU/GPU placement and session
state limit causal attribution of the measured time differences.

Two fresh blinded assistant contexts reviewed 159 exact question/outcome
groups, agreeing on 147; a third fresh blinded context adjudicated all 12
disagreements before mapping was opened. Human validation is pending.
Repeated requests are dependent: the analysis averages three repetitions
within each question, then resamples eight whole fictional scenario clusters
10,000 times. These descriptive intervals do not establish population
superiority or deployment reliability.

The [independent numeric audit](evaluation/independent_retrieval_20260913/numeric_audit_v1/numeric_audit.json)
passed **99,319 checks with zero discrepancies**; the final report passed
181 independent checks. An [offline audit correction](evaluation/independent_retrieval_20260913/analysis_audit_correction_v1.md)
recognizes 24 existing evidence-dependent question rewrites while preserving
the failed audit. Those rewrites are reported without assuming semantic
neutrality; no runtime, dataset, rubric or statistical rule changed.
The [experiment README and commands](evaluation/independent_retrieval_20260913/README.md),
[complete answer review](evaluation/independent_retrieval_20260913/report_reviewed_v3/answers.md),
and [review provenance](evaluation/independent_retrieval_20260913/reviews_verified_v1/review_agreement.json)
preserve the result and its limitations. All earlier results remain unchanged.

## 2026-09-14: routing reliability repair, first release rejected

The live speech transcript exposed two separate faults: general help could be
blocked by a false required-memory decision, and the small generator could
repeat unhelpful robot-identity prose. The replacement runtime separates
general answering, optional personalization, required personal recall and
clarification. Evidence authorization and reply-quality checks run separately
from the route. The implementation and subsequent validation are recorded in
[the repair directory](evaluation/routing_reliability_20260914/README.md).

The first frozen candidate did **not** pass its independently authored
32-case text release. Its raw local classifier matched 29/32 labels, but
empirical margin rejection reduced final agreement to 19/32. Of 12 general
requests, only one received an answer; ten unnecessarily clarified and one
incorrectly refused for missing personal memory. Five of six optional
requests received general content; the sixth exhausted the prompt budget
before model dispatch. Both mixed requests lost their independent general
part. Zero unsupported personal facts were delivered, but independent review
found one unsupported physical-action promise and one explicit count failure.

The historical Boolean router matched 20/28 scorable retrieval projections
on these cases; the four clarification labels have no Boolean equivalent.
It incorrectly requested memory for 6/12 general cases. This comparison
contains routing calls only, so it does not measure historical answer quality.
The failed replacement made 45 model calls, with 32/32 completed case records
and no transport errors. Its 359.6 seconds total and 47.22-second median among
generated answers are descriptive local timings, not a latency improvement.

The [frozen source](evaluation/routing_reliability_20260914/candidate_freeze_v1/freeze.json),
[raw replacement run](evaluation/routing_reliability_20260914/release_learned_v1/summary.json),
[legacy routing run](evaluation/routing_reliability_20260914/release_legacy_v1/summary.json),
and [independent review](evaluation/routing_reliability_20260914/release_review_v1/review.md)
preserve this failed result. These cases became development material after
inspection. Later corrections require separate validation; neither fitted
calibration scores nor passing unit tests establish unseen response quality.

## 2026-09-15: second routing candidate, release failures preserved

The second frozen candidate completed all 32 newly authored text cases, with
**29/32 raw dependency matches and 28/32 final matches**. Independent review
accepted the delivered behavior in 21/32 cases; **20/32 satisfied both routing
and delivery criteria**. This candidate still failed the full release check.

| Behavior | Observed result |
| --- | --- |
| Required missing personal information | 8/8 asked for the missing detail |
| Optional personalization without evidence | 4/6 delivered useful general content; two were nonanswers |
| Standalone general components completed | 10/18 |
| Unnecessary clarification or solicitation | 2/18 standalone answerable turns |
| Incorrect memory refusals on answerable turns | 0/18 |
| Mixed requests | 2/2 retained general prose and a missing-fact question; both explanations were partial |
| Unsupported personal or deployment/action claims | Zero observed in 32 delivered replies |

The remaining optional failures repeated an escape-room request or offered to
recommend an audio drama without giving a recommendation. A comparison
followup lost its general history and received unrelated examples. One
incomplete utterance was incorrectly framed as missing personal memory.
General factual quality also remained weak: the hexagon count was wrong,
and several explanations were incomplete or misleading. Nine outputs passed
the model answer reviewer but failed independent usefulness assessment.

All **82 actual model calls** were retained: 32 size decisions, seven
dependency reviews, 22 answer generations and 21 answer reviews. Every turn
stayed within its review and retry limits. Two contradictory review objects
were rejected and preserved; no transport or cleanup error occurred. The
19 replies with an accepted generation took **45.43 seconds median**, with
a 40.40–86.99 second range. Total run time was 1,175.78 seconds, including
loading and without concurrent unit tests. These are local text timings,
not speech-to-response timing or a demonstrated speed improvement.

The old Boolean router, replayed for routing only on the same inputs, requested
memory incorrectly on 6/12 general questions and missed 1/8 required recalls.
It matched 16/28 Boolean projections; four clarification cases have no Boolean
equivalent. Its 64 calls took 36.16 seconds and generated no answers, so that
time is not comparable to the full replacement conversation.

The [independent review](evaluation/routing_reliability_20260914/release_review_v2/review.md),
[raw run](evaluation/routing_reliability_20260914/release_learned_v2/summary.json),
[numeric audit](evaluation/routing_reliability_20260914/release_numeric_audit_v2.json),
and [legacy comparison](evaluation/routing_reliability_20260914/release_legacy_v2/interpretation.json)
preserve the failures and denominators. All 46 frozen source files matched at
run completion before development resumed. This corpus is now development
material. Its empty store and general/draft histories do not themselves test
deletion, correction or expiry; those require the separate lifecycle and
deliberately wrong-route regressions.

The next focused repairs added statement/promise detection, retained ordinary
comparison context and clarified unresolved speech without a personal-facts
review. The complete offline suite then passed **1,328 tests, with 26 skipped**.
Four known live regressions matched all four modes; three complete replies
passed review. The fourth replaced an empty offer with an audio-drama title
whose existence and described qualities could not be verified, so it was not
counted as a factual-quality success.

An independently authored, frozen **eight-case focused quality check** then
matched all eight dependency labels and produced substantive content for every
case, with no memory refusal, unnecessary clarification or promise-only
nonanswer. Nevertheless, **only 3/8 satisfied every predeclared criterion**.
Three replies missed a count/format requirement, an analogy omitted its needed
mapping, and an inbox plan appended unsupported advice to use the speech-input
tools for sorting email. No unsupported personal fact or performed physical
action was observed. Five answers passed the model reviewer but failed the
independent assessment. These are quality failures, not a successful release.

That check made 28 actual calls, stayed within all budgets, and shut down
cleanly. Median observed reply time was **53.21 seconds** (41.21–82.92 seconds),
including loading without concurrent heavy tests. Its
[review](evaluation/routing_reliability_20260914/quality_review_v3/review.md),
[frozen candidate](evaluation/routing_reliability_20260914/candidate_freeze_v3/freeze.json),
and [numeric audit](evaluation/routing_reliability_20260914/quality_numeric_audit_v3.json)
preserve the unchanged cases, exact outputs and all 46 matching source hashes.
This is a focused check, not a new full four-mode release or representative
factual-accuracy benchmark. It exercised text replies, not microphone capture.

## 2026-09-15: final scoped repair and remaining limits

Detailed deployment facts now reach generation only for relevant
assistant/specification/tool questions. Every independent answer review still
receives the complete facts. A separate bounded guard rejects unsolicited
instructions involving configured internal tools. Whisper's transcription role
and Silero VAD's speech-detection role are explicit, and ordinary creative uses
of “whisper” remain separate from software context.

The final four known regression/control cases matched **4/4 dependency modes**
and all delivered general answers. The inbox request received its three-step
general fallback without speech-tool advice. The explicit tools question
correctly distinguished transcription from speech detection. The specification
reply stayed within configured software facts but was thin and formatted the
model names awkwardly. The creative control stayed nontechnical but used
“whispered” instead of the requested literal “whisper”. Its first generic
sentence was conservatively rejected as an unsupported personal claim even
though no actual private value was asserted; one larger retry followed.
Those limitations are preserved, not counted as complete answer-quality fixes.

All **15 actual calls** stayed within their limits: four size decisions, two
dependency reviews, five generations and four answer reviews. The run completed
and unloaded cleanly; model digests were unchanged. Median text reply time was
**67.05 seconds**, with a 43.17–94.48 second range and no concurrent heavy tests.
The [targeted review](tmp/deployment_context_v4/independent_review.json) and
[numeric audit](tmp/deployment_context_v4/numeric_audit.json) retain the exact
outputs, all source/case checks and the bounded false-positive retry.
These are known regression/control cases, not a new unseen release. The earlier
20/32 full-release and 3/8 focused-quality failures remain failures. General
truthfulness, precise instruction following and latency remain limitations;
there is no new live microphone result for this final candidate.

The final complete offline suite ran **1,334 tests with 26 skipped** and passed
in **109.450 seconds** using `PYTHONPATH=src:scripts`. An isolated wheel build
verified exact bytes for five selected runtime modules and the classifier
artifact. The [final source and validation snapshot](evaluation/routing_reliability_20260914/candidate_snapshot_v4/snapshot.json)
archives 46 source/configuration files, 95 test files, model identities and
the completed test/replay evidence. It records the implemented four-part repair
and bounded reply checks, without claiming unrestricted conversation reliability.

## 2026-09-15: context-first conversation openings

Missing-context replies now ask one short question without opening with
“I don't have that memory/detail”. Safe general requests and their
clarifications can provide context for the next turn through the existing
history checks. Required recall and detected private content remain withheld
from general task history.

First-person wording alone does not establish recall. The shared guard now
distinguishes obligation questions (“What have I got to do…”), supplied work,
and procedural location questions from requests for an unstated personal value.
An accepted `required` prediction without recognizable recall intent gets one
bounded review; disagreement asks for context. Explicit stored inputs and
direct personal-value questions remain protected without requiring “remember”.
The classifier artifact and routing-review prompt are unchanged.

In six known fresh-session text cases, **5/6 raw predictions and 6/6 final modes**
fell inside their predeclared accepted sets. All six omitted memory-availability
preambles, but only **4/6 delivered acceptable behavior**. The day-planning
question repeated an already stated task, and a twenty-minute desk request
received only an offer to help. General guitar-learning steps and both genuine
missing-recall questions passed. No unsupported personal or deployment claim
was delivered. All twelve calls stayed within their limits.

The two affected cases were then replayed after replacing the generic opening
with “Could you say a little more?” and rejecting modal offers that only repeat
the requested task and constraints. **One of two behaviors passed**: the new
day question invites context, though generically. The desk nonanswer was now
rejected, but the larger retry offered to gather items itself and was also
withheld. That run therefore still did not deliver useful desk instructions.
Its five calls stayed bounded. A subsequent prompt refinement explicitly asks
practical-task retries to give steps the human can perform.

That final one-case prompt check **still failed the desk task**. The larger
model again offered to gather and sort the items itself. Both generated
candidates were withheld, leaving a clarification rather than useful steps.
The route remained `none`; this question came from exhausted answer-quality
checks, not a request for personal memory. The three calls stayed bounded,
with no answer-review call and clean shutdown. This remaining model-quality
problem has not been solved by the routing/clarification repair.

The complete suite before these final refinements passed **1,351 tests with
26 skipped** in 111.173 seconds. The final routing, reply, opening, evidence and
CLI-focused suite passed **174 tests** in 1.877 seconds. The
[validation record](tmp/conversation_opening_20260915/validation.json) preserves
the separate runs and their source hashes. These are development/regression
checks, not an unseen release, a pooled accuracy estimate or a microphone test.

## 2026-09-15: practical-answer quality repair

Explicit practical-help requests with recognized exact minute budgets now use
a typed human-instruction format on the configured general-large model from
their first generation attempt (`practical_guidance_large`). The original
compute decision is preserved separately from the actual generation; an
unattempted small answer is not reported as a fallback. Untimed
practical requests use it on the existing quality retry. Both remain within
the two-generation limit, and apply only to general requests or optional
personalization without linked evidence. Drafts, explanations, ambiguous help
and required recall retain their existing response paths. Retry feedback comes from application-owned issue
codes; rejected prose never becomes task context or personal evidence.

For a recognized exact minute budget, the application frames the model's
short instructions with “Set a N-minute timer” and “Stop when it rings”, using
the current request's parsed budget. The model supplies task steps without
computing time allocations. Untimed requests use numbered instruction strings
without the timer framing. Both formats reject malformed fields,
robot/first-person actor wording and model-added list markers. The existing
evidence and quality guards check both rendered text and the unnumbered
instruction content; the independent model reviewer still checks the delivered
answer. The actual raw generation is preserved, with the explicit
`human_guidance_steps` response transform.

The first development replay with an untimed step schema still failed human
assessment: it copied an irrelevant “Open the folder” prompt example and
ignored the twenty-minute budget, despite a model-review pass. Its
[manual assessment](tmp/practical_answers_20260915/known_desk/manual_review.json)
is preserved. An intermediate format removed concrete prompt examples and
required model-generated minute allocations to sum to the budget; its
failures are retained below. The final timer framing does not establish the
feasibility of arbitrary instructions or start a real timer on the robot.

The first six-case run used the typed format only after a failed first answer.
It repaired the desk case, but independent review accepted only **4/6 complete
outcomes**: a paper-sorting answer did not clearly enforce its ten-minute
limit, and a laundry answer offered help and asked for folding instructions
without providing them. Both passed the model reviewer. All six final modes
matched, and all 19 calls stayed within their bounds. Its
[independent review](tmp/practical_answers_20260915/live/independent_review.json)
and [end-of-run source verification](tmp/practical_answers_20260915/live/end_of_run_verification.json)
are preserved separately from later changes. This exposed the need to enforce
the typed timed format on the first attempt, without depending on a review
failure to trigger it.

That first-attempt allocation experiment also passed only **4/6**. Both
models assigned `1, 2, 3, 4, 5` minutes to the paper and laundry steps, giving
15 minutes for ten- and twelve-minute tasks. The parser correctly withheld
those outputs, so neither task received usable help. The desk and three
non-practical controls passed. The
[allocation experiment](tmp/practical_answers_20260915/live_proactive/independent_review.json)
is preserved separately. The final format uses the application-owned timer
instruction and stop rule to avoid this unnecessary model-arithmetic
dependency. All three affected practical requests were replayed with their
original criteria; earlier controls remain separate observations.

The first timer-framing replay still passed **0/3 complete practical outcomes**.
All three time limits were now explicit, but the small model generated
incoherent action sequences and the larger reviewer approved them. Examples
included emptying all desk drawers without a destination, checking whether a
folder was empty after filling it, and dismantling a laundry pile after placing
it in the basket. These were partial answers, not pure offers or explicit
instructions to discard the papers. The
[timer-only review](tmp/practical_answers_20260915/live_timer/independent_review.json)
retains those distinctions. This led to the explicit general-large generation
policy above, while preserving the same timer framing, evidence checks and
review. Its answer generation does not escalate onward to a separately configured
personal-memory model or fabricate a small-model answer attempt.

The final direct-1.7B replay passed **2/3 complete practical outcomes**:

| Case | Independent result | Turn time |
| --- | --- | --- |
| Twenty-minute desk tidy | Complete: clearing, sorting, cleaning and storage steps with a timer/stop rule. The original clarification failure is repaired in this replay. | 50.13 s |
| Ten-minute paper organization | Complete: group the papers, store them in the supplied folder and account for all papers. | 56.95 s |
| Twelve-minute laundry task | Partial: folding and basket placement are supplied, but “from the floor” and a “provided fastener” assume details that were not supplied. | 50.66 s |

All three original dependency/compute decisions remain recorded, while each
actual answer generation used `qwen3:1.7b` and `practical_guidance_large`.
There was no small-model answer attempt or invented fallback. All ten calls
met their bounds: three compute decisions, one dependency review, three
generations and three answer reviews. The
[independent review](tmp/practical_answers_20260915/live_large/independent_review.json)
and [numeric audit](tmp/practical_answers_20260915/live_large/numeric_audit.json)
separate delivered usefulness from the model review's three passes. The laundry
resource presuppositions remain a quality/evidence limitation; they are not
personal-history recall or disclosure. No blanket absence of unsupported facts
is claimed. Median turn time was **50.66 seconds**, not evidence of interactive
voice responsiveness.

The final full suite passed: **1,384 tests run, 26 skipped**, in **113.202 seconds**.
The focused suite passed **205 tests** in **2.119 seconds**. All 43 run-source
hashes matched after validation, and their exact files plus the new tests are
preserved with the [validation record](tmp/practical_answers_20260915/validation.json).
These are known development/regression cases, with the earlier failures retained.
No new microphone/transcription sample or broad answer-quality guarantee is
established by this repair.

## 2026-09-16: fresh evaluation of the latest router and answer repairs

The requested fresh text evaluation is complete. The frozen latest candidate
ran 48 independently authored challenge cases with an empty isolated memory
store. **Final routing matched 36/48; full answer quality and combined
routing-and-answer success each passed 4/48.** Five original attempts were
rejected before inference because the evaluator inserted newlines into current
requests that the CLI requires to be single-line. These setup errors remain in
the original denominator and are not model answer failures. On the 43 valid
original inputs, routing was **36/43 (83.7%)** and full quality **4/43 (9.3%)**.

A separately declared, whitespace-only correction of those five inputs ran
once per case with unchanged source and criteria: **3/5 correct routes, 1/5
complete answers and 0/5 successes on both**. All 53 attempts are preserved.
An explicitly exploratory joined view of 43 original valid inputs plus five
corrected inputs gives 39/48 routing, 5/48 quality and 4/48 combined success;
it is not the original frozen result or a pooled latency experiment.

The 24 original deliveries containing generated text took **43.57 s median /
84.93 s p95**. Application-only replies took 9.93 s median / 70.24 s p95.
No original full-quality answer arrived within 30 seconds; one arrived within
60 seconds. Thirty-two original cases had the right final route but failed
answer quality; all six explicit minute-allocation tasks failed. Twenty of 24
generated deliveries passed the runtime reviewer despite failing independent
task review. The earlier 20/32 release used different cases and source, so these
observations do not establish an improvement or regression against that score.

Two independent assistant reviewers agreed on quality for 47/48 original and
5/5 follow-up attempts; the sole original quality disagreement was explicitly
adjudicated. The independent measurement/integrity audit passed **270/270
checks**, all 137 model calls stayed within their bounds, device guards and
cleanup passed, and all frozen source hashes matched. No runtime repairs were
made during evaluation. Full methodology, setup-error accounting, exact outputs,
review judgments, latency distributions, raw traces and reproduction commands
are in the [fresh evaluation report](evaluation/fresh_routing_20260916/README.md).

## 2026-09-17: router and answer improvements; fresh validation pending

Implemented bounded self-contained-task routing, an exact four-mode fallback
review, direct generator-size policy, structured answer parts, conservative
format checks, application-owned eligible minute allocations, admitted-draft
handling, and LF-safe input/retrieval. Personal-evidence checks, bounded retries,
raw provenance, model settings and device limits remain in place. The full
offline suite passed **1,440 tests run, 26 skipped**, with no failures or errors.

The final candidate ran once on all 48 known original cases: **37/48 final
routes, 22/48 full-quality answers, and 21/48 combined successes**. Useful
general content appeared in 23/34 applicable cases. Two blinded assistant
reviewers agreed on strict quality for 47/48 cases; the disagreement and three
component/usefulness differences were explicitly adjudicated. These are known
regressions, not fresh generalization evidence.

On the **43 unchanged originally valid inputs**, full quality increased from
**4/43 to 20/43**, combined success from **4/43 to 19/43**, and routing decreased
from **36/43 to 35/43**. The new error stays in the denominator. Matched overall
median/p95 turn time changed from **38.207/81.883 seconds** to
**5.377/12.693 seconds**. These are descriptive historical-session measurements,
not a controlled causal speedup. The repaired full replay's 30 generated
deliveries took 5.207 seconds median and 8.281 seconds p95. Exact quality,
routing, latency groups and all original outcomes are retained separately.

All 48 attempts were recorded, but the last was interrupted by the existing
available-memory runtime floor. Cleanup unloaded the models. The independent
audit passed **348/349 checks**, with the operational guard/finalization failure
explicitly retained; `evaluation_complete` and `operational_success` remain
false. The original evaluation and every unsuccessful repair iteration remain
preserved. The original manifest's mutable `results.md` bytes are archived in
the repair directory before this appended entry.

The independently authored **16-case fresh holdout is frozen but has not run**.
The candidate was frozen before its first opening, and no production/test
changes followed. Offline validation passed; live admission is blocked by
swap usage above the unchanged 768 MiB start ceiling. No fresh score is claimed.
Unresolved referents, optional fallbacks, exact formatting and semantic plan
correctness still fail known cases. Full changes, review evidence, raw traces,
remaining work and the prepared fresh-run command are in the
[repair report](evaluation/answer_repair_20260916/README.md).

## 2026-09-17: fresh16 attempted and independently audited; clean run still pending

The frozen fresh16 cohort was attempted once after the device passed all
unchanged admission gates. No source, test, model, app or device-setting changes
preceded this attempt. During review of the first generated candidate, swap
crossed the existing 1 GiB runtime ceiling. The latched guard blocked later model
work. All 16 records remain: **8/16 final routing matches, 0/16 full-quality
answers, 0/16 combined successes**, eight execution errors and eight generic
application clarifications. No model-generated answer reached delivery.

Both independent blinded assistant reviewers agreed on every quality,
usefulness and component boolean. The independent audit passed **258/260
checks**; the two failures explicitly retain the guard/finalization failure
and sampled swap-limit breach. Source, cases, models, artifacts and scoring
verify. There were 25 recorded client/API attempts, only one successfully
completed raw generation, and 24 guard-error records. A recorded attempt does
not establish that backend inference ran.

Maximum sampled swap was **1,026 MiB** and temperature **52.406°C**. Cleanup
succeeded and no model remained resident. The first case took 29.733 seconds;
the overall 0.074-second median reflects later guard rejection, not useful
answer performance. Generated-answer and successful-answer latency are
unmeasured because neither population has any deliveries.

The fresh attempt and its reviews/audit are complete as records of a failed
run. **Clean operational validation remains unfinished.** One separate recovery
replay is frozen with identical source, tests, case bytes, order, rubrics and
limits. It has not run and awaits authorization for idle software-app/swap
cleanup followed by ordinary admission. Its results cannot replace this first
fresh failure or be presented as new unseen cases. Exact outputs, reviewer
judgments and resource evidence are in the
[fresh16 report](evaluation/answer_repair_20260916/fresh_holdout/README.md).
