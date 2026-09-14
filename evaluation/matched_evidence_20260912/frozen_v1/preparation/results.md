# CLARA evaluation results

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
