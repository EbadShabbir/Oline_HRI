# Independent final numerical audit

PASS: 10,250 checks. This standalone script imports no experiment/analyzer code. It reconstructs 240 scored answers from 240 raw primary attempts, two complete review files, eight adjudications, and the post-review model mapping.

Human validation remains pending. Findings concern direct generator component capability on the fixed fictional workload.

| Stratum | Both correct | Only 0.6B | Only 1.7B | Neither |
|---|---:|---:|---:|---:|
| overall | 39 | 4 | 37 | 40 |
| routine_general | 11 | 1 | 11 | 7 |
| constrained_general | 1 | 2 | 15 | 12 |
| personal_recall | 19 | 0 | 5 | 6 |
| personal_temporal | 8 | 1 | 6 | 15 |

| Model | Correct | Mean request s | Median s | P95 s | Startup amortized s |
|---|---:|---:|---:|---:|---:|
| qwen3:0.6b | 43/120 | 0.766718548 | 0.724517006 | 1.585661737 | 1.217782454 |
| qwen3:1.7b | 76/120 | 3.931983196 | 2.908647639 | 9.143524166 | 5.032482283 |

Observed rescues: 37; evidence strata: {'answerable': 26, 'unknown': 9, 'conflicting': 2}. All category counts, labels, flags, evidence strata, means/medians/linear P95s, paired differences, rescue differences, startup/cleanup amortization, and the 10,000-resample bootstrap interval agree with analysis_v1.

Overall extra latency (mean/median/P95): {'n': 120, 'mean': 3.1652646480083333, 'median': 2.096137735, 'p95': 8.17679811235, 'total': 379.831757761}. Rescue extra latency: {'n': 37, 'mean': 3.497888422918919, 'median': 3.153630675, 'p95': 8.098988590599998, 'total': 129.421871648}.

Verified 201 sealed artifact hashes across 7 directories and 39 current source files against frozen hashes. All sealed listed artifacts are read-only. Reporting and resource-auditor source hashes match their provenance records.

The resource audit also agrees with independent piecewise linear integration of raw VDD_IN telemetry, primary-call coverage, load/unload energy, resource peaks, backend durations, token statistics, and primary/attempt timings.

Review chronology (UTC):

- input_freeze: 2026-09-12T14:39:54.150811+00:00
- run_start: 2026-09-12T14:41:02.733237+00:00
- run_seal: 2026-09-12T14:59:52.732469+00:00
- blind_packets: 2026-09-12T15:00:00.568226+00:00
- independent_reviews_frozen: 2026-09-12T15:05:59.660293+00:00
- disagreements_exported: 2026-09-12T15:06:00.170833+00:00
- adjudication_frozen: 2026-09-12T15:07:35.305666+00:00
- review_seal: 2026-09-12T15:07:35.322522+00:00
- unblinding: 2026-09-12T15:07:35.329142+00:00
- analysis_created: 2026-09-12T15:07:36.845936+00:00

This audit checks arithmetic and joins. A separate spot-check note records any concrete grading concerns without changing the frozen judgments. Full human validation remains pending.
