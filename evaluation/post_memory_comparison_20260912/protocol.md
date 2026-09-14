# Post-memory comparison: prospective pilot protocol

Prepared 2026-09-12 before collecting answers. This is step 3 after the
lightweight routing and shared-memory implementation work. It is a fresh
assistant-authored pilot, with independent human review pending. It is not the
changing-memory ablation called “Stage 3” in the broader draft protocol.

## Question and systems

Does the updated lightweight cascade offer a useful measured quality/time
tradeoff against matched single-model systems on this Jetson? Preserve a null
or unfavorable outcome. These configurations incorporate the implemented
optimizations; they are not established global optima.

| Arm | Memory decision | Actual generator | Residency |
| --- | --- | --- | --- |
| Small-only | Shared intent rules first; if unresolved, one call to its own Qwen3 0.6B | Always that same model, including literal compositions | Retained within the session |
| Large-only | Same rules; if unresolved, one call to its own Qwen3 1.7B | Always that same model, including literal compositions | Retained within the session |
| Lightweight cascade | Same rules; if unresolved, one call on the cached resident model or intended generator | Existing lightweight selection, shared composition behavior, and logged timeout fallback | Active model retained; existing two-easy-request switching rule persists across requests |

No arm makes a compute-classifier call. Fixed arms enforce the sole allowed
model before every call; they cannot silently fall back to the other model.
All arms use the same updated retrieval/ranking, top-three budget, evidence
filtering, reference notes, bounded compositions, schema, context limits,
citations, freshness checks, and output validators. Helpers remain enabled and
are recorded separately from ordinary generation. Application-computed answers
are not evidence of model reasoning ability. Differences in the model used for
ambiguous memory classification mean this is a complete-system comparison,
not a generator-only comparison with identical supplied evidence.

The model tags are `qwen3:0.6b` and `qwen3:1.7b`. Freeze the installed digests,
reported parameter metadata and quantization; tag sizes are identifiers.
All arms use context 2,048, output cap 192, temperature zero, seed 42, thinking
disabled, and the configured CPU BGE-small-en-v1.5 embeddings. Only one LLM
may be resident and inference is serialized. No retired model is installed or
loaded for this comparison.

## Fresh workload and schedule

Use 48 new requests: 12 routine general, 12 general with multiple constraints,
12 personal recall, and 12 personal temporal/synthesis. The author prepares
prompts, fictional memories, required evidence, forbidden stale values and
complete-answer rubrics before seeing outputs. Include answerable, unknown,
conflicting, wrong-owner, corrected, forgotten and expired information, and
requests outside the bounded literal composers. The workload combines short
blocks and alternating task types; its exact order is frozen for every arm.

These application-specific requests complement the earlier public ARC
capability experiment. They are not a public benchmark. Their authors have
participated in development; new wording and cases do not establish an
independently designed or human-reviewed confirmatory test. Do not tune code,
prompts, labels, or sampling against collected answers. Any later repair makes
affected cases development data and requires a separately labeled new freeze.

Materialize the same fictional memory seed in a new private SQLite database
per session through real lifecycle APIs and real embeddings. Apply recorded
changes before questions, then use the fixed evaluation clock. This prepared
snapshot tests current evidence use; it does not measure change propagation
during conversation. Each question gets fresh history, while router state and
the model client persist across all 48 questions. Automatic memory capture,
speech recognition, synthesis, playback, and robot movement are excluded.

Run three rounds in separate processes, sequentially:

1. Small-only, large-only, cascade.
2. Large-only, cascade, small-only.
3. Cascade, small-only, large-only.

Planned coverage is 432 attempts, 144 per arm, on 48 distinct requests. Start
each session with no model resident. Preserve the first cold request rather
than discarding it; show it separately as well as in session totals. Related
questions share scenarios/profile context. Repetitions describe timing/output
variation, not additional independent quality samples.

## Device policy and interruption

Retain the existing common Stage 2 policy: startup available RAM at least
2 GiB, swap at most 768 MiB, temperature below 55°C; runtime available RAM at
least 768 MiB, swap at most 1 GiB, temperature below 68°C. Require a running
fan, the existing 15 W mode, unchanged boot and zero thermal trip counters,
working 500 ms telemetry, and no unexpected model. Apply guards from before
embedding setup through model cleanup. Do not change swap, power, cooling,
services, or running user applications to obtain a favorable result.

Allow up to 600 seconds of ordinary cooldown/resource release before each
session, checking every 20 seconds. Do not wait on an unexpected resident model
or changed boot/trip counters. Stop the batch on a failed session or failed
admission. Preserve interrupted attempts and unlaunched sessions explicitly;
never stitch a tail into a completed session or select a favorable retry.
Cleanup releases the arm's configured models using the client residency state;
if client cleanup fails, the fallback unload targets only attempted models.
Source/model/version
verification and final device checks must remain visible even after failure.

The fresh preliminary preflight is a zero-inference readiness check. Passing
it does not demonstrate that embeddings plus a model fit through a session.
Actual CPU/GPU placement and memory pressure may vary and must accompany
performance comparisons.

## Measurements and judgments

Primary text latency is entry to `Conversation.send` through complete response
validation or explicit failure. Report attempted/delivered counts, all-attempt
and delivered-answer timing, mean/median/p95, first/later requests, per-session
total, routing, retrieval, actual model calls, loads, helper use, fallbacks,
and recorded resource peaks. HTTP eviction/cleanup diagnostics help explain
switching cost; overlapping timings must not be added as independent costs.
Setup and cleanup are outside request latency and reported separately.

Do not count fast failures as responsive answers. Report paired outcomes on
common observed requests, all failures, missing coverage, and stratum results.
Primary quality units are distinct requests/scenarios; repeated deterministic
answers are dependent. With partial sessions or modest scenario counts, keep
comparisons descriptive and state coverage. No significance, equivalence, or
general safety claim follows from a small pilot. The user has not selected a
quality or response deadline, so do not invent a pass/fail requirement. Timing
distributions and observed quality/time tradeoffs remain primary.

Prepare a randomized worksheet hiding system, timing, and repetition. Give
reviewers each request, its rubric, and the permitted evidence. Score complete,
partial, incorrect, appropriate uncertainty, inappropriate abstention, and
technical failure; a withheld known answer is a failure. Preserve unsupported
personal and forbidden/stale claims separately. Regex checks are lexical
signals only. Record reviewer identity/type and disagreements; assistant
judgments are not independent human validation. Do not inspect or grade an
unattempted answer, and keep withheld raw text separate from delivered speech.

Whole-device VDD_IN samples provide an onboard energy estimate including
background activity; specify interval coverage and retain setup/cleanup
scope. A 15 W mode is not measured energy per answer. Text results do not
establish microphone-to-speaker latency. Shared application changes and a new
workload prevent attributing a difference from the old pilot to routing alone.

## Freeze and preservation

Archive the validated step 2 source before edits. After meaningful offline
checks pass, save a new immutable freeze containing runtime source, workload,
protocol, model/runtime/configuration metadata, embedding hashes and the
validation record before the first model request. Each session must verify
that freeze and write to a new directory. Keep the previous ARC, complete-system,
lightweight, and memory-replay evidence unchanged. New results belong to this
pilot alone. A cascade advantage must emerge from observed all-arm results;
it is not a prerequisite for reporting the experiment.
