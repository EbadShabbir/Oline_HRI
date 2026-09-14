# Post-memory system comparison

All nine sessions and 432 planned attempts are complete.

Answer quality is assistant-assessed full-rubric success. Correctness includes appropriate abstention or uncertainty only when required by the frozen rubric. Withheld, failed and interrupted attempts receive no quality credit. Independent human validation remains pending.

The statistical unit is the request: 48 distinct requests repeated three times per system, with shared scenario and synthetic-profile dependencies. The 144 planned attempts per system are not 144 independent quality samples. All comparisons here are descriptive; no quality or responsiveness pass threshold is inferred.

Timing runs from text-request entry to full validated delivery or failure. It includes classifier, retrieval, generation and validation work. This is a complete text-pipeline snapshot comparison; live memory capture, speech input and speech output are outside its scope.

Frozen session order: qwen3:1.7b alone, CLARA lightweight selection, qwen3:0.6b alone → CLARA lightweight selection, qwen3:0.6b alone, qwen3:1.7b alone → qwen3:0.6b alone, qwen3:1.7b alone, CLARA lightweight selection.

## Exact model artifacts

The tag is an artifact identifier, not an independently verified parameter count. The metadata values are copied exactly from the frozen model inspection.

| Ollama tag | Reported parameter size | Parameter count | Quantization | Artifact bytes | Digest |
| --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | 751.63M | 751632384 | Q4_K_M | 522653767 | 7df6b6e09427a769808717c0a93cadc4ae99ed4eb8bf5ca557c90846becea435 |
| qwen3:1.7b | 2.0B | 2031739904 | Q4_K_M | 1359293444 | 8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7 |

## Observed quality and delivery

Correct / planned is demonstrated correct-delivery coverage. When coverage is incomplete, it is not full-workload accuracy. Validated delivery alone does not establish correctness.

| System | Observed / planned | Distinct items | Validated | Technical failures | Correct / observed | Correct / planned |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b alone | 144/144 | 48 | 135 | 9 | 42/144 (29.2%) | 42/144 (29.2%) |
| qwen3:1.7b alone | 144/144 | 48 | 139 | 5 | 44/144 (30.6%) | 44/144 (30.6%) |
| CLARA lightweight selection | 144/144 | 48 | 140 | 4 | 46/144 (31.9%) | 46/144 (31.9%) |

## Request latency

Pooled observed attempts include each session's initial cold request. Missing populations show an em dash; a zero failure count is not zero failure latency.

| System | All mean / p50 / p95, s | Delivered mean / p50 / p95, s | Failed mean / p50 / p95, s |
| --- | --- | --- | --- |
| qwen3:0.6b alone | 2.314 / 2.090 / 3.270 | 2.276 / 2.021 / 3.281 | 2.885 / 2.771 / 3.268 |
| qwen3:1.7b alone | 11.255 / 8.955 / 25.430 | 11.242 / 8.984 / 25.836 | 11.597 / 8.501 / 21.933 |
| CLARA lightweight selection | 8.916 / 7.749 / 18.772 | 8.962 / 7.827 / 19.060 | 7.288 / 6.700 / 9.374 |

## Quality by request category

| Category | System | Correct / observed | Validated | Failures | Observed / planned |
| --- | --- | --- | --- | --- | --- |
| general multiconstraint | qwen3:0.6b alone | 3/36 (8.3%) | 36 | 0 | 36/36 |
| general multiconstraint | qwen3:1.7b alone | 8/36 (22.2%) | 36 | 0 | 36/36 |
| general multiconstraint | CLARA lightweight selection | 11/36 (30.6%) | 36 | 0 | 36/36 |
| personal recall | qwen3:0.6b alone | 27/36 (75.0%) | 33 | 3 | 36/36 |
| personal recall | qwen3:1.7b alone | 17/36 (47.2%) | 35 | 1 | 36/36 |
| personal recall | CLARA lightweight selection | 17/36 (47.2%) | 35 | 1 | 36/36 |
| personal temporal synthesis | qwen3:0.6b alone | 0/36 (0.0%) | 33 | 3 | 36/36 |
| personal temporal synthesis | qwen3:1.7b alone | 0/36 (0.0%) | 32 | 4 | 36/36 |
| personal temporal synthesis | CLARA lightweight selection | 0/36 (0.0%) | 33 | 3 | 36/36 |
| routine general | qwen3:0.6b alone | 12/36 (33.3%) | 33 | 3 | 36/36 |
| routine general | qwen3:1.7b alone | 19/36 (52.8%) | 36 | 0 | 36/36 |
| routine general | CLARA lightweight selection | 18/36 (50.0%) | 36 | 0 | 36/36 |

## Repetitions and cold versus later requests

Sessions appear in executed order. Each started without a resident generator; the first request includes cold loading. Later-request distributions exclude only that session's first attempt, including any failed first attempt.

| Session | Outcome | Observed | Validated | Correct / observed | First, s | All mean / p50 / p95, s | Later mean / p50 / p95, s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 01_large_r1 | complete_with_errors | 48/48 | 47 | 13/48 (27.1%) | 50.311 | 17.448 / 15.486 / 29.620 | 16.749 / 15.371 / 28.039 |
| 02_cascade_r1 | complete_with_errors | 48/48 | 46 | 14/48 (29.2%) | 29.928 | 7.288 / 6.362 / 11.146 | 6.806 / 6.238 / 11.047 |
| 03_small_r1 | complete_with_errors | 48/48 | 45 | 14/48 (29.2%) | 11.058 | 2.335 / 2.117 / 3.298 | 2.150 / 2.101 / 3.229 |
| 04_cascade_r2 | complete_with_errors | 48/48 | 47 | 16/48 (33.3%) | 28.029 | 10.372 / 9.455 / 16.804 | 9.996 / 9.396 / 15.184 |
| 05_small_r2 | complete_with_errors | 48/48 | 45 | 14/48 (29.2%) | 11.055 | 2.336 / 2.145 / 3.266 | 2.151 / 2.080 / 3.233 |
| 06_large_r2 | complete_with_errors | 48/48 | 45 | 15/48 (31.2%) | 29.228 | 7.957 / 7.101 / 16.312 | 7.504 / 7.015 / 15.359 |
| 07_small_r3 | complete_with_errors | 48/48 | 45 | 14/48 (29.2%) | 11.672 | 2.271 / 2.021 / 3.178 | 2.071 / 1.998 / 3.060 |
| 08_large_r3 | complete_with_errors | 48/48 | 47 | 16/48 (33.3%) | 30.244 | 8.359 / 7.478 / 14.377 | 7.893 / 7.371 / 11.897 |
| 09_cascade_r3 | complete_with_errors | 48/48 | 47 | 16/48 (33.3%) | 32.202 | 9.087 / 7.167 / 20.187 | 8.595 / 7.087 / 18.199 |

## Recorded calls and loading

Counts include failed attempts. Returned generator identities come from source-hashed raw call metadata, including responses later withheld by validation; requested tags do not fill missing returned identities. Backend loading is already contained in call/request time. Duration totals cover only calls with returned timing metadata. No compute-classifier inference is permitted by this profile.

| System | Memory / compute / generator calls | All calls | Duration metadata available | Returned 0.6b / 1.7b generator tags | Calls without returned model | Fallbacks | Retrieval requests | Routing total, s | Retrieval total, s | Backend load total, s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b alone | 99 / 0 / 144 | 243 | 243 | 144 / 0 | 0 | 0 | 57 | 80.078 | 3.961 | 28.363 |
| qwen3:1.7b alone | 99 / 0 / 144 | 243 | 243 | 0 / 144 | 0 | 0 | 33 | 332.131 | 2.436 | 72.821 |
| CLARA lightweight selection | 99 / 0 / 144 | 243 | 243 | 3 / 141 | 0 | 0 | 33 | 251.686 | 2.308 | 166.549 |

## Residency and cleanup evidence

The analyzer audits recorded request snapshots and model calls against each arm's allowed tags. 0 interrupted attempts lack a successful post-request residency snapshot. Per-request server snapshots are archived in runtime_evidence.json. They observe residency at the recorded boundaries; no switch count is inferred from cached hints.

| Session | Permitted model tags | Start residency | Finish residency | Cleanup errors |
| --- | --- | --- | --- | --- |
| 01_large_r1 | qwen3:1.7b | empty | empty | [] |
| 02_cascade_r1 | qwen3:0.6b, qwen3:1.7b | empty | empty | [] |
| 03_small_r1 | qwen3:0.6b | empty | empty | [] |
| 04_cascade_r2 | qwen3:0.6b, qwen3:1.7b | empty | empty | [] |
| 05_small_r2 | qwen3:0.6b | empty | empty | [] |
| 06_large_r2 | qwen3:1.7b | empty | empty | [] |
| 07_small_r3 | qwen3:0.6b | empty | empty | [] |
| 08_large_r3 | qwen3:1.7b | empty | empty | [] |
| 09_cascade_r3 | qwen3:0.6b, qwen3:1.7b | empty | empty | [] |

## Observed CPU/GPU allocation

Ollama /api/ps size and size_vram describe reported allocation, not a fraction of model computation. Jetson GPU allocation shares physical memory with the CPU; it is not additional physical RAM. A ratio below 100% records partial GPU allocation and is a possible latency factor. These measurements do not establish equal CPU/GPU placement across arms, and do not isolate a causal routing effect.

| Session | Resident tag | Snapshots | Numeric allocation snapshots | Reported allocation range, MiB | GPU allocation range, MiB | GPU / reported allocation range, % |
| --- | --- | --- | --- | --- | --- | --- |
| 01_large_r1 | qwen3:1.7b | 95 | 95 | 1582.0–1582.0 | 972.2–972.2 | 61.5–61.5 |
| 02_cascade_r1 | qwen3:1.7b | 93 | 93 | 1582.0–1582.0 | 1322.5–1363.5 | 83.6–86.2 |
| 02_cascade_r1 | qwen3:0.6b | 2 | 2 | 661.3–661.3 | 661.3–661.3 | 100.0–100.0 |
| 03_small_r1 | qwen3:0.6b | 95 | 95 | 661.3–661.3 | 661.3–661.3 | 100.0–100.0 |
| 04_cascade_r2 | qwen3:1.7b | 93 | 93 | 1582.0–1582.0 | 1205.7–1281.5 | 76.2–81.0 |
| 04_cascade_r2 | qwen3:0.6b | 2 | 2 | 661.3–661.3 | 661.3–661.3 | 100.0–100.0 |
| 05_small_r2 | qwen3:0.6b | 95 | 95 | 661.3–661.3 | 661.3–661.3 | 100.0–100.0 |
| 06_large_r2 | qwen3:1.7b | 95 | 95 | 1582.0–1582.0 | 1243.6–1243.6 | 78.6–78.6 |
| 07_small_r3 | qwen3:0.6b | 95 | 95 | 661.3–661.3 | 661.3–661.3 | 100.0–100.0 |
| 08_large_r3 | qwen3:1.7b | 95 | 95 | 1582.0–1582.0 | 1205.7–1205.7 | 76.2–76.2 |
| 09_cascade_r3 | qwen3:1.7b | 93 | 93 | 1582.0–1582.0 | 1126.8–1205.7 | 71.2–76.2 |
| 09_cascade_r3 | qwen3:0.6b | 2 | 2 | 661.3–661.3 | 661.3–661.3 | 100.0–100.0 |

## Whole-device resources and energy

Existing zram swap occupancy is logical usage backed by compressed pages in physical RAM. It cannot be added to physical RAM capacity or usage, and occupancy alone is not a measure of active swapping. Onboard VDD_IN energy integrates sampled whole-device power without idle subtraction. The whole interval includes setup and cleanup plus background activity. Request energy covers sampled overlap only; unsampled prefixes/suffixes are not extrapolated. Scheduler waits and gaps between sessions are excluded. This is not calibrated model-only energy.

| Session | Memory setup, s | Peak RAM, MiB | Peak logical swap, MiB | Peak temperature, °C | Sampled interval, s | Whole interval, kJ | Request intervals, kJ | Request coverage / requested, s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 01_large_r1 | 2.470 | 6367.0 | 1621.0 | 58.44 | 841.134 | 8.058 | 8.024 | 837.104 / 837.523 |
| 02_cascade_r1 | 2.896 | 6307.0 | 1666.0 | 62.00 | 353.887 | 4.215 | 4.176 | 349.552 / 349.831 |
| 03_small_r1 | 2.777 | 5572.0 | 1648.0 | 61.84 | 116.213 | 1.586 | 1.544 | 112.036 / 112.086 |
| 04_cascade_r2 | 2.467 | 6487.0 | 1645.0 | 59.59 | 501.754 | 5.401 | 5.365 | 497.800 / 497.854 |
| 05_small_r2 | 3.578 | 5670.0 | 1643.0 | 62.03 | 116.698 | 1.586 | 1.539 | 111.714 / 112.135 |
| 06_large_r2 | 2.502 | 6483.0 | 1642.0 | 61.12 | 385.846 | 4.274 | 4.238 | 381.879 / 381.915 |
| 07_small_r3 | 2.922 | 5707.0 | 1617.0 | 61.81 | 112.963 | 1.490 | 1.448 | 108.607 / 108.998 |
| 08_large_r3 | 2.602 | 6530.0 | 1618.0 | 60.03 | 404.893 | 4.404 | 4.368 | 400.767 / 401.224 |
| 09_cascade_r3 | 4.088 | 6521.0 | 1616.0 | 60.56 | 441.768 | 4.675 | 4.629 | 436.136 / 436.155 |

## Recorded admission and runtime limits

These are the limits saved in this analysis, including any frozen amendment. A terminal resource interruption remains a failure of that recorded session; missing requests are not silently replaced.

| Minimum start RAM, MiB | Maximum start swap, MiB | Minimum runtime RAM, MiB | Maximum runtime swap, MiB | Start temperature below, °C | Runtime temperature below, °C |
| --- | --- | --- | --- | --- | --- |
| 2048 | 3554 | 768 | 3554 | 55.0 | 68.0 |

## Semantic judgments

Counts map resolved blinded judgments back to attempts, retaining repetitions. The forbidden-claim flag covers the whole rubric, including general-task constraints; it is not solely a personal-data exposure count.

| System | complete | appropriate abstention | appropriate uncertainty | partial | incorrect | inappropriate abstention | technical failure | Unsupported personal claim | Forbidden / stale rubric claim |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b alone | 33 | 9 | 0 | 12 | 72 | 9 | 9 | 18 | 6 |
| qwen3:1.7b alone | 38 | 6 | 0 | 33 | 56 | 6 | 5 | 34 | 6 |
| CLARA lightweight selection | 40 | 6 | 0 | 31 | 57 | 6 | 4 | 38 | 6 |

Blinded review resolved 145 unique evidence-aware output groups covering 432 observed attempts. Identical responses are grouped only for the same request and supplied-memory ID set; non-deliveries are grouped per request. Grouping reduces duplicate grading, not the denominator.

Workload SHA-256: `5599e106f4bb502a96e92538bee70cec3ee8743a3e282bbc2051354bb5c7ec59`. Freeze SHA-256: `6497504cb7a3fd29c2b3b3740aa26f1a77dad8d626cbf0fedcabed997bfc7783`.
