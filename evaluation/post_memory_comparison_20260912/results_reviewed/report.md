# Post-memory complete text-system comparison

Collection: incomplete; 48/432 planned attempts. Artifact integrity: valid for observed sessions.

complete_for_observed_unique_outputs; reviewer types: assistant. Regex signals and delivery validity are not answer-quality scores.

| System | Attempts | Validated deliveries | Median all (s) | p95 all (s) | Median delivered (s) | Median failed (s) |
|---|---:|---:|---:|---:|---:|---:|
| small | 48/144 | 45 | 2.159 | 3.322 | 2.062 | 2.784 |
| large | 0/144 | 0 | — | — | — | — |
| cascade | 0/144 | 0 | — | — | — | — |

| Session | Status | Deliveries | First request (s) | Setup (s) | Peak RAM / swap (MiB) |
|---|---|---:|---:|---:|---:|
| 01_small_r1 | complete_with_errors | 45/48 | 13.468 | 2.401 | 5837 / 997 |
| 02_large_r1 | missing | 0/48 | — | — | — / — |
| 03_cascade_r1 | missing | 0/48 | — | — | — / — |
| 04_large_r2 | missing | 0/48 | — | — | — / — |
| 05_cascade_r2 | missing | 0/48 | — | — | — / — |
| 06_small_r2 | missing | 0/48 | — | — | — / — |
| 07_cascade_r3 | missing | 0/48 | — | — | — / — |
| 08_small_r3 | missing | 0/48 | — | — | — / — |
| 09_large_r3 | missing | 0/48 | — | — | — / — |

| System | Calls by actual generator | Helper constraints | Retrieval requests | Missing lexical signals | Forbidden presence signals |
|---|---|---:|---:|---:|---:|
| small | {"qwen3:0.6b": 48} | 0 | 19 | 0 | 0 |
| large | {} | 0 | 0 | 0 | 0 |
| cascade | {} | 0 | 0 | 0 | 0 |

Semantic review: 48/48 unique outputs resolved; reviewer types: assistant. Assistant review is not independent human validation.

| System | Correct / observed | Reviewed / planned | Round 1 | Round 2 | Round 3 |
|---|---:|---:|---:|---:|---:|
| small | 14/48 | 48/144 | 14/48 observed; 48/48 attempted | 0/0 reviewed; 0/48 attempted | 0/0 reviewed; 0/48 attempted |
| large | pending | 0/144 | 0/0 reviewed; 0/48 attempted | 0/0 reviewed; 0/48 attempted | 0/0 reviewed; 0/48 attempted |
| cascade | pending | 0/144 | 0/0 reviewed; 0/48 attempted | 0/0 reviewed; 0/48 attempted | 0/0 reviewed; 0/48 attempted |

Observed correctness uses only attempted requests after all their outputs are graded, including technical failures. It is not full-workload accuracy when requests are missing. Correct deliveries divided by all planned requests is a conservative demonstrated-coverage fraction; unattempted requests are not demonstrated successes. Unreviewed outputs remain pending.

The correct-by-deadline curve is withheld until collection and semantic review are complete.

Lexical presence can match a negated statement; valid paraphrases can miss a pattern. Empty check lists do not establish correctness. Failed requests cannot count as correct abstentions.

The design plans three deterministic repetitions; achieved coverage is reported separately. Repetitions are not additional independent quality samples, and scenario/shared-profile dependencies remain.

Ollama load/prefill/decode are contained in call wall time; do not add them again. Cold first requests and setup are reported separately.

Energy and resource peaks include background activity. Whole-interval telemetry includes setup and cleanup; request-window energy uses only intervals covered by samples.

The blinded worksheet hides explicit system identity, timing, repetition, and variant frequency. Response wording can still suggest system identity. Human review is pending.

The manifest config records loaded application defaults with model-role overrides. The frozen runner explicitly constructs a separate MemoryStore in each session using the synthetic workload profile, retention period, and fixed evaluation clock. The application's configured personal-memory database/profile is not used. Saved snapshots verify the observed profiles and equality across sessions; the analyzer does not open the databases.
Actual synthetic profile: fictional_tideglass_post_memory_v1; retention: 7 days; evaluation clock: 2026-10-03T20:00:00.000000Z; database: <session-directory>/memory.sqlite3.
