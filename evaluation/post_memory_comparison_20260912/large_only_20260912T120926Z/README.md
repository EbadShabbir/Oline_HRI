# Requested large-only session, 2026-09-12

The user requested the large-only condition separately after the original
batch stopped. The unchanged frozen runner was invoked with `--arm large
--repetition 1` and the same 48-request workload. This directory is a separate
collection attempt; the original batch and small-only results are unchanged.

Startup was blocked before model inference or embedding/database setup:

| Startup measurement | Observed | Required |
| --- | ---: | ---: |
| Available RAM | 2391.012 MiB | At least 2048 MiB |
| Logical swap used | 988.000 MiB | At most 768 MiB |
| Maximum temperature | 51.281 °C | Below 55 °C |
| Resident models | 0 | 0 |

The runner attempted **0/48 requests**. There are no new answers, quality
scores or request-latency observations, and this is not evidence that 1.7B
itself failed inference. Waiting had already failed to resolve the same swap
condition over the original batch's ten-minute window; this attempt retained
the existing limit.

All 40 frozen runtime files still match. The runner verified unchanged source,
model metadata and Ollama version; final residency was empty with no cleanup
errors. Boot, power mode and thermal-trip counters were unchanged. No model,
swap, power, service or other system configuration was changed.

Evidence: [collection plan](collection_plan.json),
[startup snapshot](02_large_r1/start.json),
[runner finish](02_large_r1/finish.json),
[request counts](02_large_r1/summary.json), and
[standalone verification](standalone_finish.json).

The remaining large-only condition needs device state within the
[frozen protocol's startup limits](../frozen_v1/protocol.md). Any later
collection must use a new output directory and preserve this rejection.
