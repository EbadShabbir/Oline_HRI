# Post-memory complete text-system comparison

Collection: complete; 432/432 planned attempts. Artifact integrity: valid for observed sessions.

complete_for_observed_unique_outputs; reviewer types: assistant. Regex signals and delivery validity are not answer-quality scores.

| System | Attempts | Validated deliveries | Median all (s) | p95 all (s) | Median delivered (s) | Median failed (s) |
|---|---:|---:|---:|---:|---:|---:|
| small | 144/144 | 135 | 2.090 | 3.270 | 2.021 | 2.771 |
| large | 144/144 | 139 | 8.955 | 25.430 | 8.984 | 8.501 |
| cascade | 144/144 | 140 | 7.749 | 18.772 | 7.827 | 6.700 |

| Session | Status | Deliveries | First request (s) | Setup (s) | Peak RAM / swap (MiB) |
|---|---|---:|---:|---:|---:|
| 01_large_r1 | complete_with_errors | 47/48 | 50.311 | 2.470 | 6367 / 1621 |
| 02_cascade_r1 | complete_with_errors | 46/48 | 29.928 | 2.896 | 6307 / 1666 |
| 03_small_r1 | complete_with_errors | 45/48 | 11.058 | 2.777 | 5572 / 1648 |
| 04_cascade_r2 | complete_with_errors | 47/48 | 28.029 | 2.467 | 6487 / 1645 |
| 05_small_r2 | complete_with_errors | 45/48 | 11.055 | 3.578 | 5670 / 1643 |
| 06_large_r2 | complete_with_errors | 45/48 | 29.228 | 2.502 | 6483 / 1642 |
| 07_small_r3 | complete_with_errors | 45/48 | 11.672 | 2.922 | 5707 / 1617 |
| 08_large_r3 | complete_with_errors | 47/48 | 30.244 | 2.602 | 6530 / 1618 |
| 09_cascade_r3 | complete_with_errors | 47/48 | 32.202 | 4.088 | 6521 / 1616 |

| System | Calls by actual generator | Helper constraints | Retrieval requests | Missing lexical signals | Forbidden presence signals |
|---|---|---:|---:|---:|---:|
| small | {"qwen3:0.6b": 144} | 0 | 57 | 0 | 0 |
| large | {"qwen3:1.7b": 144} | 0 | 33 | 0 | 0 |
| cascade | {"qwen3:0.6b": 3, "qwen3:1.7b": 141} | 0 | 33 | 0 | 0 |

Semantic review: 145/145 unique outputs resolved; reviewer types: assistant. Assistant review is not independent human validation.

| System | Correct / observed | Reviewed / planned | Round 1 | Round 2 | Round 3 |
|---|---:|---:|---:|---:|---:|
| small | 42/144 | 144/144 | 14/48 observed; 48/48 attempted | 14/48 observed; 48/48 attempted | 14/48 observed; 48/48 attempted |
| large | 44/144 | 144/144 | 13/48 observed; 48/48 attempted | 15/48 observed; 48/48 attempted | 16/48 observed; 48/48 attempted |
| cascade | 46/144 | 144/144 | 14/48 observed; 48/48 attempted | 16/48 observed; 48/48 attempted | 16/48 observed; 48/48 attempted |

Observed correctness uses only attempted requests after all their outputs are graded, including technical failures. It is not full-workload accuracy when requests are missing. Correct deliveries divided by all planned requests is a conservative demonstrated-coverage fraction; unattempted requests are not demonstrated successes. Unreviewed outputs remain pending.

The empirical correct-by-deadline curve is available in deadline_quality_curve.json and deadline_quality_curve.csv. It uses the complete request wall time, has a denominator of 144 planned attempts per arm, and retains failed requests in that denominator. The right-continuous steps describe every deadline from zero through the largest observed latency; no acceptance deadline was selected.

Lexical presence can match a negated statement; valid paraphrases can miss a pattern. Empty check lists do not establish correctness. Failed requests cannot count as correct abstentions.

The design plans three deterministic repetitions; achieved coverage is reported separately. Repetitions are not additional independent quality samples, and scenario/shared-profile dependencies remain.

Ollama load/prefill/decode are contained in call wall time; do not add them again. Cold first requests and setup are reported separately.

Energy and resource peaks include background activity. Whole-interval telemetry includes setup and cleanup; request-window energy uses only intervals covered by samples.

The blinded worksheet hides explicit system identity, timing, repetition, and variant frequency. Response wording can still suggest system identity. Human review is pending.

The manifest config records loaded application defaults with model-role overrides. The frozen runner explicitly constructs a separate MemoryStore in each session using the synthetic workload profile, retention period, and fixed evaluation clock. The application's configured personal-memory database/profile is not used. Saved snapshots verify the observed profiles and equality across sessions; the analyzer does not open the databases.
Actual synthetic profile: fictional_tideglass_post_memory_v1; retention: 7 days; evaluation clock: 2026-10-03T20:00:00.000000Z; database: <session-directory>/memory.sqlite3.

A complete session is retained unchanged after a later zero-request startup rejection. Only unattempted sessions were subsequently run; no request tail was joined and no completed answer was retried. The scheduler waits below 54 C; each arm still enforces its original below-55 C startup gate.
Retained complete sessions: 2; excluded startup-only rejections: 1.

Offline compatibility corrections retain the exact frozen v2 swap policy and accept the revised startup-temperature wording only after measured zero-request rejection proof. Other provenance findings and scoring are unchanged. Both adapter sources and the original findings accompany this report. Resumed adapter SHA-256: `ab9d0d5a666187d1295467189bb46bbd2e9d797fe4a1bb27c1fe1661aa4e1367`.
