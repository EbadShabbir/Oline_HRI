# Stage 2 complete text-system pilot

Collection: incomplete; 136/432 planned attempts. Artifact integrity: valid for observed sessions.

complete_for_observed_unique_outputs; reviewer types: assistant. Regex signals and delivery validity are not answer-quality scores.

| System | Attempts | Validated deliveries | Median all (s) | p95 all (s) | Median delivered (s) |
|---|---:|---:|---:|---:|---:|
| cascade | 40/144 | 34 | 12.135 | 53.773 | 11.826 |
| large | 48/144 | 46 | 18.998 | 39.795 | 18.998 |
| small | 48/144 | 42 | 2.216 | 3.442 | 2.091 |

| Session | Status | Deliveries | First request (s) | Setup (s) | Peak RAM / swap (MiB) |
|---|---|---:|---:|---:|---:|
| 01_small_r1 | complete_with_errors | 42/48 | 11.960 | 2.697 | 5845 / 483 |
| 02_large_r1 | complete_with_errors | 46/48 | 38.628 | 2.143 | 6467 / 706 |
| 03_cascade_r1 | interrupted | 34/48 | 13.299 | 3.228 | 6571 / 719 |
| 04_large_r2 | missing | 0/48 | — | — | — / — |
| 05_cascade_r2 | missing | 0/48 | — | — | — / — |
| 06_small_r2 | missing | 0/48 | — | — | — / — |
| 07_cascade_r3 | missing | 0/48 | — | — | — / — |
| 08_small_r3 | missing | 0/48 | — | — | — / — |
| 09_large_r3 | missing | 0/48 | — | — | — / — |

| System | Calls by actual generator | Helper constraints | Retrieval requests | Missing lexical signals | Forbidden presence signals |
|---|---|---:|---:|---:|---:|
| cascade | {"qwen3:0.6b": 26, "qwen3:1.7b": 14} | 1 | 19 | 13 | 0 |
| large | {"qwen3:1.7b": 48} | 1 | 17 | 20 | 0 |
| small | {"qwen3:0.6b": 48} | 1 | 21 | 20 | 0 |

Semantic review: 93/93 unique outputs resolved; reviewer types: assistant. Assistant review is not independent human validation.

| System | Correct / observed | Reviewed / planned | Round 1 | Round 2 | Round 3 |
|---|---:|---:|---:|---:|---:|
| small | 18/48 | 48/144 | 18/48 observed; 48/48 attempted | 0/0 reviewed; 0/48 attempted | 0/0 reviewed; 0/48 attempted |
| large | 24/48 | 48/144 | 24/48 observed; 48/48 attempted | 0/0 reviewed; 0/48 attempted | 0/0 reviewed; 0/48 attempted |
| cascade | 19/40 | 40/144 | 19/40 observed; 40/48 attempted | 0/0 reviewed; 0/48 attempted | 0/0 reviewed; 0/48 attempted |

Observed correctness uses only attempted requests after all their outputs are graded, including technical failures. It is not full-workload accuracy when requests are missing. Correct deliveries divided by all planned requests is a conservative demonstrated-coverage fraction; unattempted requests are not demonstrated successes. Unreviewed outputs remain pending.

The correct-by-deadline curve is withheld until collection and semantic review are complete.

Lexical presence can match a negated statement; valid paraphrases can miss a pattern. Empty check lists do not establish correctness. Failed requests cannot count as correct abstentions.

Three deterministic repetitions are not additional independent quality samples; scenario and shared-profile dependencies remain.

Ollama load/prefill/decode are contained in call wall time; do not add them again. Cold first requests and setup are reported separately.

Energy and resource peaks include background activity. Whole-interval telemetry includes setup and cleanup; request-window energy uses only intervals covered by samples.

The blinded worksheet hides explicit system identity, timing, repetition, and variant frequency. Response wording can still suggest system identity. Human review is pending.

The manifest config records loaded application defaults with model-role overrides. The frozen runner explicitly constructs a separate MemoryStore in each session using the synthetic workload profile, retention period, and fixed evaluation clock. The application's configured personal-memory database/profile is not used. Saved snapshots verify the observed profiles and equality across sessions; the analyzer does not open the databases.
Actual synthetic profile: fictional_solstice_stage2_v1; retention: 7 days; evaluation clock: 2026-09-20T18:00:00.000000Z; database: <session-directory>/memory.sqlite3.

A complete session is retained unchanged after a later zero-request startup rejection. Only unattempted sessions were subsequently run; no request tail was joined and no completed answer was retried. The scheduler waits below 54 C; each arm still enforces its original below-55 C startup gate.
Retained complete sessions: 1; excluded startup-only rejections: 1.
