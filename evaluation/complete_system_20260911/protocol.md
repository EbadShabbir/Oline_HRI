# Complete text-system comparison — frozen pilot protocol

Prepared 11 September 2026, before inference on the new workload. This is
Stage 2 of the adaptive-selection evaluation, following the separate ARC
generator-capability pilot. It evaluates the current application with fair
single-model controls; it does not establish that every system has reached
its best attainable configuration.

## Systems and controlled components

| Arm | Permitted models | Memory selector | Generator and residency |
| --- | --- | --- | --- |
| Small-only | Qwen3 0.6B | One classification by 0.6B, followed by the existing memory-intent policy | All generation uses 0.6B, retained within the session |
| Large-only | Qwen3 1.7B | One classification by 1.7B, followed by the same memory-intent policy | All generation uses 1.7B, retained within the session |
| CLARA cascade | Qwen3 0.6B and 1.7B, serially | Existing 0.6B classifier and memory-intent policy | Existing compute classifier, helper overrides, and serial loading/unloading policy |

All arms share the same fictional memory-event seed, evaluation clock, real
SQLite lifecycle operations, BGE-small-en-v1.5 CPU embeddings, hybrid retrieval,
top-three candidate budget, evidence filtering, reference notes, grounded
compositions, response schema, validators, and repair/abstention logic. Fixed
baselines skip unnecessary compute classification. Their explicit generator
override also covers authored compositions and prevents fallback to another
model. The adaptive arm retains its deployed behavior. A baseline timeout is
not silently replaced by an answer from the peer model.

The selector model differs between the single-model baselines. Consequently,
this is a system-policy comparison; it does not isolate generator choice under
identical supplied evidence. Record actual retrieval, supplied/cited IDs, every
model call, helper constraint, response transformation, and final delivery.

Context is 2,048 tokens, output ceiling 192, temperature zero, seed 42, and
thinking disabled for all arms. Model digests, effective configuration, source
hashes, workload hash, and Ollama version are frozen before the first session.
No tuning against these outputs or selective answer retries are allowed.

## Workload and execution

There are 48 new author-designed requests: 12 routine general requests, 12
general requests with multiple constraints, 12 direct personal-recall requests,
and 12 personal temporal/synthesis requests. See `workload.json` and
`workload_notes.md` for the exact prompts, prewritten references, rubrics,
scenario grouping, and deterministic checks. These application-specific items
complement ARC; they are not an established public benchmark or a final
independently reviewed test set. They have not been used to tune this system.

Each session starts with no model resident and a newly materialized equivalent
memory database. Corrections, forgetting, and validity intervals are replayed
before requests. Each request uses fresh conversation history, while the same
client retains natural model residency across the full 48-item order. This
controls prior-answer contamination and measures switching costs; it does not
measure conversational follow-ups or automatic memory capture.

Run three rounds in the following orders, without concurrent inference:

1. Small-only, large-only, cascade.
2. Large-only, cascade, small-only.
3. Cascade, small-only, large-only.

Every arm uses the identical frozen request order. This gives 432 planned
attempts (48 × 3 arms × 3 rounds), with 48 distinct request items per arm.
Personal requests share a profile and some scenarios, so even the distinct
items are clustered. Repeated outputs are not additional independent quality samples.
The repetitions characterize latency and output variability. A guard or
unrecovered transport failure stops the session and remains visible; the
adaptive system's existing timeout fallback is retained and logged. Unavailable attempts
are reported separately. Do not silently stitch a new run into a completed
session. Cooldown and startup waits stay outside per-request timers.

## Measurements and scoring

Primary text latency is from entry to `Conversation.send` until a complete
validated response or an explicit failure. It includes routing, retrieval,
generation, model-loading transitions, validation, and checks inside backend
calls. Preserve failed-attempt timing separately from successful-answer timing;
fast errors are not responsive answers. Report mean, median, p95, first request,
later requests, total request time, routing time, generation time, loading time,
retrieval time, and the actual generator distribution. Initial embedding and
database setup are measured separately, not charged to each request.

Report delivered responses, rubric correctness/completeness, appropriate
abstention or uncertainty, unsupported personal claims, forbidden/stale facts,
and category-level outcomes. Exact checks are constraint signals, not a
substitute for semantic review. Any assistant review must be identified as
such, with human review still pending. Preserve all outputs and a system-blinded
review worksheet. Compare paired cases; do not treat the 144 repeated attempts
as 144 independent quality cases. No quality or responsiveness cutoff has
been accepted by the user, so continuous measures and tradeoffs are primary.

Sample whole-device RAM, logical swap occupancy, temperature, GPU activity,
and VDD_IN power at 500 ms. Energy is the integral of the onboard VDD_IN samples
over the reported interval, includes background load, and is not calibrated
external energy measurement. Peaks include setup and cleanup unless explicitly
scoped to request intervals. Preserve model-placement logs where available;
Ollama may choose different CPU/GPU placement as available memory changes.

## Common device policy for this experiment

All three arms use the same new Stage 2 limits: startup at least 2 GiB available
RAM, at most 768 MiB logical swap, and temperature below 55°C; runtime at least
768 MiB available RAM (and sampled RAM headroom), at most 1 GiB logical swap,
and temperature below 68°C. Require the expected 15 W mode, active fan, unchanged
boot and thermal-trip counters, a live telemetry stream, and at most one model
resident. Reject models outside the current arm.

These are explicitly declared Stage 2 limits, not an extension of the separate
3B continuation. The preflight found approximately 2,328 MiB available RAM,
483 MiB logical swap (approximately 132 MiB physical zram), and 52.7°C with no
model resident. Historical full-retrieval runs began with comparable available
RAM. The residual swap occupancy exceeds the earlier ARC pair's startup gate;
therefore the new common policy and starting state must accompany comparisons.
Measured fit remains an experimental outcome. No swap device, power setting,
service configuration, or user application is changed. Process-scoped guard
constants are restored after every session and only attempted models are
unloaded during cleanup.

## Limits on interpretation

This round measures the complete text-request path against a prepared memory
snapshot. It excludes microphone capture, speech recognition, speech synthesis,
audio playback, robot motion, automatic memory extraction, and changes arriving
during an answer. A later integrated spoken/lifecycle evaluation is still
needed. The preliminary 48-item authored workload and absence of independent
human quality review limit publication claims. If a single-model baseline
performs better, retain that finding; equal quality with extra cascade overhead
is not evidence for using two models.
