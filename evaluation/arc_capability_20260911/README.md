# ARC capability pilot — four conditions, with segmented 3B item coverage

The [consolidated results tables](../../results.md) cover accuracy, timing,
resource peaks, model setup, and the documented 3B continuation.

Collected on the Jetson Orin Nano 8 GB on 2026-09-11, in the requested order.
The first three conditions completed all 100 frozen questions with no failed
requests, safety interruption, or remaining resident model. Qwen2.5 3B now has
accepted answers for all 100 items across its interrupted first attempt and
the explicitly requested 17-question continuation. The original interruption
remains recorded; it is not an uninterrupted completed run.
See the [composite-item report](results_continuation_placement_reviewed/report.md),
[machine-readable analysis](results_continuation_placement_reviewed/analysis.json),
[all 100 attributed answers](results_continuation_placement_reviewed/composite_answers.jsonl),
[original four-arm audit](results_four_arm_reviewed/report.md), and
[frozen protocol](protocol.md).

| System | Correct / 100 | Easy / 50 | Challenge / 50 | Mean question time | Median / p95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qwen3 `0.6b` | 64 | 40 | 24 | 0.40 s | 0.27 / 0.31 s |
| Qwen3 `1.7b` alone, resident | 79 | 43 | 36 | 0.62 s | 0.42 / 0.49 s |
| CLARA generator selection | 79 | 43 | 36 | 29.82 s | 30.23 / 37.36 s |
| Qwen2.5 `3b-instruct-q3_K_S` | 71 (two segments) | 38 | 33 | See segment timings | — |

The fourth condition combines 59 correct answers among the first 83 accepted
responses with 12 correct answers among the remaining 17. The latter includes
a fresh attempt at interrupted question 84. All original successful answers,
including incorrect ones, are retained. This is **71/100 composite item
accuracy across two segments**, with changed operating limits and automatic
GPU/CPU placement. It does not establish uninterrupted 100-question feasibility.

Qwen3 1.7B has the highest observed standalone accuracy in this pilot. The
additional Qwen2.5 3B artifact did not improve that score. Model family,
quantization, execution placement, and starting state differ, so this is not
an isolated test of parameter count.

The larger generator shows a measured capability advantage: 18 questions were
correct only with 1.7B, versus three correct only with 0.6B. The present cascade
provides no measured efficiency benefit over resident 1.7B on this short-answer
ARC workload. It selected 1.7B on 95 questions and 0.6B on five; reported model
loading accounts for about 91% of cascade question wall time. Its mean was
approximately 47.8 times the resident 1.7B mean in this run.

Equal total scores do not establish equivalent quality. The cascade missed one
large-model success by selecting small. A separate 1.7B answer changed from
incorrect to correct despite identical generation messages/settings; that gain
must not be attributed to routing. Replaying the cascade's selections against
the standalone outputs gives 78/100, versus the live cascade's 79/100.

The test uses 50 ARC-Easy and 50 ARC-Challenge questions from the official test
splits, deterministic sampling, and exact published answer keys. It measures
zero-shot, constrained answer-label generation. It is a subset pilot, not the
full benchmark or its standard choice-likelihood leaderboard score. The CLARA
condition exercises its production router under a common benchmark adapter;
personal memory, authored answers, STT, and TTS are outside this experiment.

All times include the first request: 12.85 s for small, 20.10 s for large,
31.97 s for cascade, and 25.42 / 30.07 s for the two 3B segments. Single-model
arms retain their sole model; the cascade
uses current serial eviction/loading. Hardware is in 15 W mode with active
cooling and SD-backed `/dev/mmcblk0p1` storage. The single pass, fixed condition
order, and uncontrolled desktop activity limit causal timing comparisons.
No background applications were stopped. The final process snapshot contained
Firefox processes in addition to the development/desktop applications.

## Fourth condition, interruption, and final device state

The user's allowed 3B alternative was downloaded and its artifact verified:
`qwen2.5:3b-instruct-q3_K_S`, digest
`5ed381ff5c13d3259de8a24724e08bf779766be072e3648ac80ca759d4a37902`.
The 4B model was excluded because of its recorded loading reset and
artifact-size restriction, and subsequently removed from Ollama at the user's
request. No 4B accuracy was measured.

The first 3B preflights were blocked by conservative RAM/swap admission checks.
After the user requested continuation, an explicit
[startup amendment](extra_startup_amendment.md) allowed up to 384 MiB used
swap, matching the earlier arms' allowance, while retaining the fourth arm's
2.5 GiB RAM requirement and every runtime limit. The actual start recorded
2711.3 MiB available RAM and 276.5 MiB swap. The original 128 MiB startup
criterion did not pass. The separate launcher and amendment were archived
before inference; generation, prompts, scoring, and the original runner stayed
unchanged. No privileged swap cleanup was performed.

During request 84, used swap crossed the retained 512 MiB runtime ceiling,
and the runner stopped. Whole-device peaks were 6426 MiB RAM, 546 MiB swap,
and 60.53 C. The backend generated the correct label for request 84, but the
post-call check interrupted acceptance; it is not counted among the 59
correct accepted answers. This stopped run alone does not establish complete-workload
feasibility or the model's full 100-question accuracy. It also does not prove
the model cannot fit: the observed termination was a configured swap limit,
with no reboot or thermal trip.

At the user's request, the [continuation protocol](continuation_protocol.md)
then selected only original questions 84–100 (11 Easy and six Challenge).
All 17 completed, with eight Easy and four Challenge answers correct. The
separate diagnostic segment used a 2.25 GiB startup RAM floor, 768 MiB startup
swap ceiling, and 1024 MiB runtime swap ceiling. Physical runtime RAM and
temperature limits remained 768 MiB and 68 C, with the same boot, fan, trip,
telemetry, and single-model checks. These revised limits were documented
before inference and applied only within that process.

| 3B segment | Attempts / successful | First request | Mean of all attempts | Mean of later successful requests | Peak RAM / swap / temperature |
| --- | ---: | ---: | ---: | ---: | --- |
| Original, interrupted at question 84 | 84 / 83 | 25.42 s | 1.09 s | 0.80 s | 6426 MiB / 546 MiB / 60.53 C |
| Remaining questions 84–100 | 17 / 17 | 30.07 s | 3.52 s | 1.86 s | 6297 MiB / 546 MiB / 56.34 C |

Total measured request execution was 151.65 s across 101 attempts, including
the original interrupted request and both cold model loads; downtime between
segments is separate. These segment means must not be presented as one
uninterrupted 3B latency measurement.

[Curated Ollama logs](qwen25_3b_offload_logs.json) confirm the original segment
put 37/37 model layers on the GPU, while the continuation put 30/37 on the GPU
and the remaining layers on the CPU. Ollama's automatic fitter made this
change after available device memory fell from 2692 to 2337 MiB. Context and
batch sizes were unchanged. This establishes different execution placement;
it does not quantify how much of the latency difference that change caused.

Cleanup succeeded. No model remains resident. All six zram devices retain
their original sizes and priorities; power mode, boot ID, thermal counters,
and production code match the before-state. No applications were closed and
no persistent system settings were changed. Linux-managed swap occupancy
remained approximately 546 MiB afterward, versus 276.5 MiB before; it was
not cleared. Previously resident desktop/service pages moved into swap, but
the observations do not isolate the cause of memory pressure.

Before/after verification is saved as `04_retry_environment_before.json`,
`04_retry_environment_after.json`, `04_continuation_environment_before.json`,
and `04_continuation_environment_after.json` under the private root. Initial
preflights and the failed original request remain intact. The completed
continuation adds item coverage; the original 512 MiB full-run feasibility
criterion remains unmet.

## Reproducibility and verification

- [Frozen 100-question dataset](dataset.json), source revision and hashes in
  [source/manifest.json](source/manifest.json).
- [Dataset preparation](../../scripts/prepare_arc_capability_dataset.py),
  [guarded runner](../../scripts/run_arc_capability.py),
  [explicit extra-arm launcher](../../scripts/run_arc_qwen25_retry.py),
  [continuation launcher](../../scripts/run_arc_qwen25_continue.py),
  [original analysis](../../scripts/analyze_arc_capability.py),
  [composite analysis](../../scripts/analyze_arc_continuation.py), and
  [optional administrative helper](../../scripts/refresh_arc_zram.py).
- Twenty-one offline runner/launcher tests passed. Independent analysis checked
  all 401 observed requests, including the interrupted fourth-arm request,
  against dataset/order, prompt/schema, source hashes, model identity,
  completion records, telemetry, archived amendment provenance, exact remaining
  item selection, and per-item segment attribution.
  The optional helper was
  checked with mocked recovery/restoration tests and read-only device checks;
  it has not performed privileged operations.
- Raw immutable observations, manifests, telemetry, and preflight evidence:
  `/home/b2jetson/.local/share/oline-hri/evaluation-runs/arc-capability-20260911/`.
- Earlier `results/`, `results_reviewed/`, and `results_four_arm/` audits are
  preserved. `results_four_arm_reviewed/` includes the amended fourth-arm
  attempt and explicit partial-answer diagnostics. The three completed-arm
  scores are unchanged. `results_continuation_placement_reviewed/` is the
  latest continuation audit; it adds the explicit composite item score and
  verified execution-placement evidence, keeping both timing segments separate.

The protocol's timeout wording is clarified here without changing execution:
single-model requests use 120 seconds; cascade small-model calls retain 60
seconds, and cascade large-model calls use 120 seconds. No timeout occurred.

Dataset attribution: Allen Institute for AI, Clark et al. (2018),
[AI2 ARC](https://huggingface.co/datasets/allenai/ai2_arc), CC-BY-SA-4.0.
