# Step 3 observed results — incomplete comparison

Only the first small-only session ran. The batch stopped at the unchanged
startup swap gate before the large-model session, after 600.946 seconds of
recovery checks. Large-only and cascade are unattempted, not measured failures.
There are no common observed requests across all three arms.

Quality is full-rubric success assessed by two agreeing assistant reviewers.
It includes appropriate abstention only where the prewritten rubric requires
it; three technical failures receive no success credit. Human review remains
pending.

| System | Attempts / planned | Validated delivery | Correct / attempted | Mean, s | Median, s | p95, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3 0.6B alone | 48/144 | 45/48 | 14/48 (29.2%) | 2.416 | 2.159 | 3.322 |
| Qwen3 1.7B alone | 0/144 | Not attempted | Not measured | — | — | — |
| Lightweight cascade | 0/144 | Not attempted | Not measured | — | — | — |

Timing includes the cold first request and failed attempts. It is time to
validated text delivery or explicit failure, not first-token or spoken latency.

| Request category | Small-only correct / attempted | Large-only | Cascade |
| --- | ---: | ---: | ---: |
| Routine general | 4/12 | Not attempted | Not attempted |
| General with multiple constraints | 1/12 | Not attempted | Not attempted |
| Personal recall | 9/12 | Not attempted | Not attempted |
| Personal temporal / synthesis | 0/12 | Not attempted | Not attempted |

## Small-only timing and resources

| Measurement | Observed value |
| --- | ---: |
| Cold first request | 13.468 s |
| Later 47 requests, mean / median / p95 | 2.180 / 2.096 / 3.277 s |
| All 48 request intervals, total | 115.949 s |
| Delivered-answer mean / median / p95 (n=45) | 2.381 / 2.062 / 3.289 s |
| Failed-attempt mean / median / p95 (n=3) | 2.935 / 2.784 / 3.272 s |
| Embedding and synthetic database setup | 2.401 s |
| Memory / compute / generator calls | 33 / 0 / 48 |
| Routing total, including applicable loading | 29.490 s |
| Retrieval total | 1.300 s |
| Reported Ollama loading total | 11.625 s |
| Peak whole-device RAM / logical swap | 5837 / 997 MiB |
| Peak temperature | 61.656 °C |
| Sampled whole-device interval | 119.241 s |
| Whole-interval onboard energy estimate | 1610.063 J |
| Covered request-interval onboard energy estimate | 1571.352 J |

Request energy covers 115.480 of 115.949 request seconds; uncovered intervals
are not extrapolated. Whole-interval figures include setup/cleanup and desktop
activity, exclude the subsequent scheduler wait, and are not calibrated
model-only energy. Loading is already inside request/call time.

Every generator was `qwen3:0.6b`. All 48 post-request residency snapshots
report model size and VRAM size as 693,423,308 bytes each; this is reported
placement evidence. No delivered response recorded a literal composition;
the three failed responses lack final helper metadata.

## Review and pipeline findings

Judgments: 11 complete, 3 appropriate abstentions, 6 partial, 22 incorrect,
3 inappropriate abstentions and 3 technical failures. Both assistant reviewers
agreed on all 48 judgments and disclosure flags, using fresh contexts and a
neutral worksheet without system labels. Agreement is not human validation.

Nine of 24 personal requests were routed without memory; four of 24 general
requests were routed to memory. All required IDs were supplied for 11 of the
20 personal requests requiring specific facts (15 of 31 required-ID occurrences).
These are mechanical diagnostics, not semantic success.

Eleven delivered outputs had unsupported personal claims. Two outputs violated
explicit forbidden-claim rubrics: an invented tram departure and a ticket
assignment copied from another person. These are not two forgotten/expired-memory
disclosures. Per-output notes preserve that distinction. None of these observed
failures was used to change the frozen implementation or workload.

## Collection limit

One of nine scheduled sessions finished; eight sessions and 384 requests
remained unattempted. Final swap was 988.5 MiB against the 768 MiB startup
limit, available RAM 2390.996 MiB, and maximum temperature 52.437 °C. No models
remained resident; boot, power mode and zero thermal-trip counters were
preserved. No OS, swap, service, model-installation or power configuration was
changed.

This does not show that 1.7B is intrinsically infeasible: its new session never
started. It cannot show a cascade advantage, equivalence, or improvement over
earlier workloads. The full comparison needs a fresh device state within the
declared limits and separately preserved collection. No stopped session was
stitched or relabeled.

Sources: [reviewed analysis](analysis.json), [semantic reviews](semantic_review.json),
[review agreement](../reviews/review_agreement.json),
[pipeline diagnostics](../small_r1_pipeline_diagnostics.json),
[batch finish](../run_v1/batch_finish.json), [startup checks](../run_v1/startup_waits.json),
and [freeze](../frozen_v1/freeze.json).
