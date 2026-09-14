# Post-memory complete text-system comparison

Collection: incomplete; 192/432 planned attempts. Artifact integrity: valid for observed sessions.

pending_unique_output_reviews; reviewer types: assistant. Regex signals and delivery validity are not answer-quality scores.

| System | Attempts | Validated deliveries | Median all (s) | p95 all (s) | Median delivered (s) | Median failed (s) |
|---|---:|---:|---:|---:|---:|---:|
| small | 48/144 | 45 | 2.117 | 3.298 | 2.055 | 2.731 |
| large | 48/144 | 47 | 15.486 | 29.620 | 15.371 | 23.307 |
| cascade | 96/144 | 93 | 8.138 | 15.812 | 8.288 | 6.706 |

| Session | Status | Deliveries | First request (s) | Setup (s) | Peak RAM / swap (MiB) |
|---|---|---:|---:|---:|---:|
| 01_large_r1 | complete_with_errors | 47/48 | 50.311 | 2.470 | 6367 / 1621 |
| 02_cascade_r1 | complete_with_errors | 46/48 | 29.928 | 2.896 | 6307 / 1666 |
| 03_small_r1 | complete_with_errors | 45/48 | 11.058 | 2.777 | 5572 / 1648 |
| 04_cascade_r2 | complete_with_errors | 47/48 | 28.029 | 2.467 | 6487 / 1645 |
| 05_small_r2 | missing | 0/48 | — | — | — / — |
| 06_large_r2 | missing | 0/48 | — | — | — / — |
| 07_small_r3 | missing | 0/48 | — | — | — / — |
| 08_large_r3 | missing | 0/48 | — | — | — / — |
| 09_cascade_r3 | missing | 0/48 | — | — | — / — |

| System | Calls by actual generator | Helper constraints | Retrieval requests | Missing lexical signals | Forbidden presence signals |
|---|---|---:|---:|---:|---:|
| small | {"qwen3:0.6b": 48} | 0 | 19 | 0 | 0 |
| large | {"qwen3:1.7b": 48} | 0 | 11 | 0 | 0 |
| cascade | {"qwen3:0.6b": 2, "qwen3:1.7b": 94} | 0 | 22 | 0 | 0 |

Semantic review: 116/131 unique outputs resolved; reviewer types: assistant. Assistant review is not independent human validation.

| System | Correct / observed | Reviewed / planned | Round 1 | Round 2 | Round 3 |
|---|---:|---:|---:|---:|---:|
| small | 14/48 | 48/144 | 14/48 observed; 48/48 attempted | 0/0 reviewed; 0/48 attempted | 0/0 reviewed; 0/48 attempted |
| large | 13/48 | 48/144 | 13/48 observed; 48/48 attempted | 0/0 reviewed; 0/48 attempted | 0/0 reviewed; 0/48 attempted |
| cascade | pending | 81/144 | 15/48 observed; 48/48 attempted | 33/48 reviewed; 48/48 attempted | 0/0 reviewed; 0/48 attempted |

Observed correctness uses only attempted requests after all their outputs are graded, including technical failures. It is not full-workload accuracy when requests are missing. Correct deliveries divided by all planned requests is a conservative demonstrated-coverage fraction; unattempted requests are not demonstrated successes. Unreviewed outputs remain pending.

The correct-by-deadline curve is withheld until collection and semantic review are complete.

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
