# Numerical audit of the observed complete-system results

Audited 11 September 2026 against
[analysis_second_batch_reviewed/analysis.json](analysis_second_batch_reviewed/analysis.json),
SHA256 `bcee5d01e8ae0d9a78b960a7dd4335400ffa1a22f860b2fcad5aa6b4b26325b3`,
and its [row metrics](analysis_second_batch_reviewed/row_metrics.jsonl),
SHA256 `b30ee6fe887f7a11c3e1c10313f8de32698f15b86be943b3a835fabe16ffb9be`.
The audit independently recomputed table counts and interpolated latency
quantiles from the reviewed metrics. It did not change judgments or raw evidence.

The observed population contains **184 of 432 planned attempts**, **166
validated deliveries**, and **248 unattempted requests**. All observed attempts
have resolved assistant assessments; independent human review remains pending.

The common first-round set is exactly frozen requests 1–40, with ten requests
from each stratum in every arm. It is a deterministic prefix ending at the
cascade interruption, not a random sample or a complete 48-request comparison.

| Common 40 requests | Small-only | Large-only | Cascade |
| --- | ---: | ---: | ---: |
| Correct | 16/40 | 21/40 | 19/40 |
| Validated delivery | 35/40 | 39/40 | 34/40 |
| Mean attempt latency, seconds | 2.554 | 21.740 | 19.959 |
| p95 attempt latency, seconds | 3.519 | 40.315 | 53.773 |

All session and pooled latency values in the audited draft agree with the
reviewed rows. Failed attempts and the initial request are included in the
above latency figures; delivery alone does not establish answer correctness.

Across all observed attempts, memory/compute/generation call counts are
48/0/48 for small-only, 96/0/96 for large-only, and 40/40/40 for cascade:
**408 calls**, all with reported duration metadata. Cascade generation used
0.6B on 26 calls and 1.7B on 14 calls. Its reported backend loading time is
463.243960 seconds out of 798.376920 request seconds, or **58.0232%** (58.0%
rounded). Loading is already included in request time and must not be added
again.

Energy figures agree with the analysis. Cascade request integration covers
798.225203 of 798.376920 seconds (99.9810%), leaving 0.151717 seconds
unextrapolated. The other executed sessions have full sampled request-interval
coverage. These are whole-device onboard estimates, including background
activity; scheduler waits and inter-session gaps are outside their intervals.

At this snapshot, sessions 05–09 have not started. Startup admission blockage
must not be labeled a runtime failure of cascade round 2. A terminal schedule
does not imply all nine sessions or all 432 requests executed. Final analysis
may refresh completion/admission provenance while retaining this same observed
population; these hashes identify the exact audited snapshot. Any change to
observed requests or judgments requires a new numerical audit.
