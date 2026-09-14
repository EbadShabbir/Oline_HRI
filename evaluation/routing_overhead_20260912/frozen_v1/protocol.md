# CLARA routing overhead: frozen four-turn protocol

Prepared before live collection on 12 September 2026. The question is whether
measured savings from selecting the small generator recover deterministic
routing, optional memory classification, eviction, loading, and following-turn
costs relative to matched fixed generators. A null or unfavorable answer is an
acceptable experiment result. This is an assistant-authored diagnostic pilot,
not an independently designed benchmark or a confirmatory superiority study.

## Workload and systems

`workload.json` is authoritative: 12 four-turn sequences, three variants each
of EEEE, DDDD, EDED, and DDEE. E and D are authored workload labels; never force
a routing outcome or exclude a sequence for an unexpected route. All three
DDEE variants finish with two social utterances recognized by the existing
small-eligibility rule even with retained history. Validate that rule before
live collection and report the actual large/large/large/small trace or any
failure to exercise it. EDED variant 1 intentionally includes a direct fact
question following ordinary history; the actual conservative policy may label
that easy request large. Preserve this behavior.

Start one persistent `Conversation` per sequence with empty initial history.
Retain its ordinary bounded history, router state, and model-client residency
across all four requests. The same literal questions, initial history, prepared
fictional memory, settings, and answer helpers apply to every main system.
Subsequent history can differ because prior answers differ; log it rather than
substituting another system's history. Ordinary grounded-history exclusions
remain active. The memory seed is the unchanged fictional Tideglass snapshot
from the completed post-memory v2 comparison: 30 setup operations and 26
currently eligible IDs. No memory mutation or automatic capture occurs during
a sequence. Reference answers and workload labels must never enter model input.

| Main system | Selection and generation | Residency within a sequence |
| --- | --- | --- |
| Small-only (`small`) | Shared memory rules, ambiguous memory call on 0.6B, every answer renderer on 0.6B | Retain 0.6B |
| Large-only (`large`) | Shared memory rules, ambiguous memory call on 1.7B, every answer renderer on 1.7B | Retain 1.7B |
| Lightweight adaptive (`adaptive`) | Current deterministic compute rules, independent memory rules with at most one classifier on cached resident/intended generator, existing shared helpers and fallback | Retain active model; existing two-easy-turn rule controls large-to-small return |

No current main system calls a compute classifier. Record zero actual calls,
without fabricating a zero-duration classifier response. Fixed systems enforce
their sole model on every classifier, renderer, and fallback path. All systems
use the same retrieval, evidence packing, literal composition, schema, citation,
freshness, and response-validation helpers. Log application-authored responses
so their correctness is not credited as model reasoning.

Pin `qwen3:0.6b` and `qwen3:1.7b`, context 2048, output cap 192, temperature 0,
seed 42, and thinking disabled. Preserve configured CPU BGE-small embeddings,
model quantization, exact installed digests, backend version, timeouts, and all
other generation options in the freeze. No output-length normalization,
sampling retuning, or model-placement change is allowed after outputs are seen.

## Repetitions, cold state, and diagnostic replay

Run three timing repetitions. For each sequence/repetition, run the three main
systems in the following order, each from an independent cold state, followed
by its adaptive diagnostic replay:

1. Small, large, adaptive, diagnostic replay.
2. Large, adaptive, small, diagnostic replay.
3. Adaptive, small, large, diagnostic replay.

Iterate sequence IDs in the literal workload order within each repetition.
Each main system therefore occupies each main-system position once per
sequence. The appended replay is not counterbalanced and has an acknowledged
position/cooldown confound. Planned main coverage is 108 sequences/432 turns;
replay adds 36 sequences/144 turns. Timing repetitions and turns sharing a
sequence are dependent observations.

Cold means no LLM reported resident by `/api/ps`, no cached model residency,
a newly initialized CPU embedder, and the same prepared memory snapshot before
the first request. This is **model/process cold**, not filesystem-cache cold:
do not flush OS caches, restart Ollama, reboot, alter swap, or manipulate user
applications. Snapshot pre/post state and document residual RAM/swap/cache
conditions. Initialize embeddings and prepared memory under resource guards;
record startup separately. The first request remains in all totals, including
its backend cold load. Separate model-loading time from embedding/setup time.

For each adaptive trace, run a **diagnostic routing-bypass replay**, not a
deployable policy. Run the same `Conversation` retrieval, answer helpers and
validation, restoring the adaptive trace's exact pre-turn history before each
request. Return the original observed routing result without executing the
selector. Any attached original classifier metadata is marked reused; it is
not a replay classifier invocation or newly measured duration. Actual call
lists and tracing determine replay classifier counts, which must be zero.

Require exact equality of answer-generation model identities, messages and
response schemas with saved adaptive calls. Also assert exact equality of the
pseudonymized HTTP bodies, including options and keep-alive settings, before
sending every generation request. Preserve the actual renderer/fallback
sequence and reject any missing, extra or different generation request.
Archive the matched bodies and the adaptive source trace hash. Preserve the
same starting cold state and settings. Retrieval is run again against the same
snapshot, and validation judges the newly generated response; it does not
substitute the prior answer. This controls generator inputs and choices while
bypassing only selection. Different replay outputs or backend placement remain
possible and must be reported. Preserve unavailable/failed replay steps rather
than inventing a generation request or splicing a trace.

## Timing and accounting

Use a single process monotonic clock (`perf_counter_ns` or equivalent) for
start/end spans. Archive wall-clock UTC only for provenance/alignment. Capture:

- Each deterministic routing decision and memory-policy decision; each actual
  memory/compute classifier call, including errors and model identity.
- Unload HTTP request/acknowledgment and a separate verified-eviction span
  ending only when the evicted model is absent from `/api/ps`.
- Each answer-generation request, retrieval and packing where instrumented,
  validation, and complete request from submission to validated answer or
  recorded failure. Keep first-turn and following-turn identities/residency.
- Startup, four-request elapsed time, gaps/telemetry overhead, cleanup, and
  total sequence. Include startup and all attempts in the primary full-sequence
  total; provide request-only totals and cleanup separately.
- Backend-reported load, prefill, decode, total duration and token counts as
  metadata nested inside their enclosing HTTP/generation wall spans.

Do not add backend load to enclosing generation/HTTP/request wall time. A
cold classifier can pay the selected model's load before answer generation;
attribute the one load to the actual caller and retain the encompassing turn.
Router wall time includes its classifier when present, so separate exclusive
deterministic selection time from inclusive router time. Similarly, retrieval,
validation, and instrumentation children can overlap encompassing spans. Compute
disjoint totals or interval unions from timestamps, identify overlap explicitly,
and report residual wall time rather than manufacturing an additive total.

Classify each request from observed before/after residency as cold, resident
same-model, or transition, separately for selected and actual generation model.
A first easy turn retained on large and the second easy turn that returns to
small are distinct observations. Report the next turn after each transition;
if a transition is last in a sequence, there is no later observed request.
Verified eviction adds observation overhead; show that span and acknowledge
that this instrumented lifecycle is the measured system.

## Resources, freeze, failures, and cleanup

Before live collection, validate timing accounting and lifecycle instrumentation
with fake HTTP and deterministic offline checks; simulations are not performance
samples. Freeze workload, this protocol, execution source, configuration,
validation results, package/backend versions, model digests and embedding asset
hashes. Live runs verify the freeze and write new immutable attempt directories.
Do not edit the freeze or pool earlier studies into these paired observations.

Use the existing post-memory process-scoped resource policy unchanged: startup
available RAM at least 2 GiB and temperature below 55 C; runtime available RAM
at least 768 MiB and temperature below 68 C. Startup/runtime logical swap ceiling
is 3,554.1640625 MiB, the observed 3,810.1640625 MiB capacity minus 256 MiB.
Require unchanged swap capacity, running fan, existing 15 W mode, unchanged
boot, zero thermal-trip counters, maximum one resident LLM, and functioning
500 ms telemetry. These are existing experimental guards, not demonstrated
hardware safety limits. Never change OS settings to obtain admission.

Serialize every inference. Hold an experiment lock, inspect competing experiment
processes and unexpected model residency before collection, and stop on
interference. Capture RAM, swap, temperature, CPU/GPU placement (including
`size`/`size_vram` and available backend placement evidence), telemetry and
cleanup for every sequence. The same tag does not establish the same placement.
Allow ordinary resource cooldown using the established scheduler; preserve all
admission failures and waiting records. Abort unsafe inference, preserve its
partial trace, verify cleanup, and identify unattempted turns. A later fresh
retry has a new attempt identity; do not splice incomplete sequences or replace
unfavorable answers. Keep failures in latency/delivery denominators.

## Analysis and correctness

Report per-system and per-pattern components, first cold versus resident
requests, transition/next-turn costs, complete sequence latency, token counts,
placement, resources, failures, and actual selections. Pair the identical
sequence/repetition against each fixed system and its adaptive replay. Define
positive savings as comparator time minus adaptive time. Show each repetition
and each sequence variant; do not treat 576 turn attempts as independent data.
Use descriptive paired sequence summaries, optionally cluster intervals over
the 12 authored sequences with the shared-profile/template dependence stated.
Three variants per pattern cannot establish stable tail or rare-event estimates.

Review every delivered answer against frozen required and forbidden claims,
actual supplied evidence, and citations. A valid JSON answer, a satisfied
literal helper, or an appropriate greeting is not proof of general reasoning
quality. Social cases are deliberately useful for measuring the implemented
hysteresis mechanism; they are weak evidence of an application quality benefit.
Count complete answers, partial/incorrect answers, appropriate uncertainty and
technical failures separately. Assistant review must be labeled as such;
independent human review remains pending. Never claim a quality–latency
improvement on unreviewed outputs or count fast failures as useful savings.

Explain output-length, history, retrieval, and CPU/GPU placement differences
that limit attribution. Replay can estimate selection overhead for its exact
recorded generator sequence; it is not an oracle or deployable routing policy.
No new quality threshold or response deadline is selected after collection.
State whether measured selection recovered its costs relative to each fixed
system, which patterns benefited, and what remains uncertain. Save raw traces,
CSV/JSON tables, figures, review records, source/input hashes and reproducible
commands; append results/development notes without deleting previous evidence.
