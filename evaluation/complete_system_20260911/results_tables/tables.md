### Observed coverage and answer quality

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
