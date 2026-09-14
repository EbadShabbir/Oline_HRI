# Routing-overhead experiment: methods and interpretation boundaries

This methods record describes the frozen collection and its documented
continuation. It makes no timing or answer-quality conclusion. The authoritative
execution documents are the [original protocol](frozen_v1/protocol.md),
[continuation protocol](frozen_v2/protocol.md), [workload](frozen_v2/workload.json),
and the two source/model freezes. Final counts and acceptance checks must come
from the completed artifacts, not from this description of planned coverage.

## Workload, history, and residency

The workload has 12 four-turn sequences: three variants each of EEEE, DDDD,
EDED, and DDEE. E and D describe the author's intended workload difficulty;
they never force a route. The 48 turn slots contain 39 different prompt texts,
including repeated social utterances. Every main system receives the same
literal questions, initially empty conversation history, prepared fictional
memory, generation settings, and shared answer helpers.

One `Conversation`, router and Ollama client persist across each sequence.
Ordinary bounded history evolves from that system's own preceding answers;
it can therefore differ between main systems after turn one. Existing exclusions
of grounded personal answers from ordinary history remain active. This is a
controlled comparison of retained conversations, not an assertion that later
main-system generator prompts are identical.

The unchanged Tideglass fictional seed is reused from the completed post-memory
comparison. Its 30 setup operations create the same 26 eligible memories at a
fixed fictional clock; correction, forgetting and expiry precede all requests.
Each sequence materializes a new SQLite store and CPU embedding instance. No
memory mutation, automatic capture, speech recognition, speech synthesis or
robot action occurs during measurement. Rubrics, answers, difficulty labels
and expected memory IDs are excluded from the model input path.

All three DDEE variants end with two social utterances that remain eligible
for the small model even with retained history. Offline fake-backend checks
confirmed the existing two-easy-turn rule can produce large/large/large/small.
Only live selections and observed residency can establish whether it did so.
EDED variant 1 deliberately includes an easy fact question following ordinary
history; the existing conservative rule can keep that request on large.
These choices exercise implemented behavior and limit generalization to less
social, more representative everyday workloads.

## Matched systems and schedule

| System | Memory selection | Answer generation and residency |
| --- | --- | --- |
| Small-only | Shared intent rules, then one 0.6B classifier if unresolved | Every renderer uses 0.6B; retain it within the sequence |
| Large-only | Same rules, then one 1.7B classifier if unresolved | Every renderer uses 1.7B; retain it within the sequence |
| Lightweight adaptive | Deterministic compute selection and independent memory rules; unresolved memory calls use the cached resident/intended generator | Existing lightweight choice, composition behavior and timeout fallback; retain active model and apply two-easy-turn hysteresis |
| Diagnostic replay | Original adaptive route returned without executing selection | Same saved adaptive generation requests, ordinary shared retrieval/helpers/validation, active-model retention |

Fixed systems enforce their sole model before each call, including composed
answers, and cannot fall back to the peer. No main system makes a compute
classifier call. A skipped call has no fabricated generation metadata or new
backend duration. Application-authored composition remains enabled equally;
a correct literal rendering is not proof of model reasoning capability.

For each sequence, three timing repetitions rotate the main-system order:
small/large/adaptive, large/adaptive/small, and adaptive/small/large. A replay
follows each main-system block. The literal sequence order is fixed within
repetitions. Planned coverage is 108 main-system sequences and 432 main turns,
plus 36 replay sequences and 144 replay turns. Each main system occupies each
main-system position once. Replay always occupies the last position and has
an acknowledged scheduling/cooldown confound.

Every independent sequence begins in a new process with no model reported by
Ollama `/api/ps` and no cached model residency. Its CPU BGE-small embedder is
initialized afresh. This is model/process cold, not filesystem-cache cold:
Ollama and the OS remain running, page caches are retained, and residual memory
and swap conditions are recorded. No cache flush, reboot, service change,
swap reconfiguration or deliberate placement override is part of the method.

## Frozen models and settings

The frozen Ollama version is 0.33.3. Both installed models use Q4_K_M
quantization. Model tags are identifiers; their reported parameter counts are
also retained rather than inferred from tag spelling.

| Tag | Installed digest | Reported parameters |
| --- | --- | --- |
| `qwen3:0.6b` | `7df6b6e09427a769808717c0a93cadc4ae99ed4eb8bf5ca557c90846becea435` | 751,632,384 |
| `qwen3:1.7b` | `8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7` | 2,031,739,904 |

Actual HTTP requests must contain context 2048, output cap 192, temperature 0,
seed 42, `think=false`, and `keep_alive=-1`. The configured small/general-large
request timeouts are 60/120 seconds and unload timeout is 30 seconds. CPU
BGE-small uses two intra-operation threads and pinned ONNX/tokenizer/configuration
hashes. Source, configuration, installed model metadata, package versions,
backend version and embedding assets are recorded in [freeze v1](frozen_v1/freeze.json)
and [freeze v2](frozen_v2/freeze.json). Model identity and allocation are also
observed during requests; matching tags alone does not guarantee matching
CPU/GPU placement.

## Exact-request diagnostic replay

The replay uses the same `Conversation` pipeline, including retrieval,
answer helpers, evidence checks and response validation. Before every turn it
restores the adaptive trace's exact pre-turn history and returns its previously
observed routing result. Original classifier metadata attached to that result
is explicitly reused provenance; actual call lists and span events, not that
metadata, determine replay classifier count and measured classifier time.

Before generation, the runner compares model identity, full messages and
response schema with the saved adaptive generation calls. It also compares the
full pseudonymized Ollama HTTP bodies, including options and keep-alive
behavior. Any missing, extra or different generation request is a control
failure. The source observation file hash and request bodies are retained.
Memory retrieval runs again against the same prepared snapshot; validation
judges the newly generated answer. Subsequent replay turns restore original
adaptive history, so a different replay answer cannot alter a later generator
request. Actual renderer and fallback sequences must match the source.

This is a diagnostic requiring an already observed adaptive trace. It is not a
deployable routing policy or an oracle. Identical requests constrain attribution
but do not force identical backend placement, cache state, thermal state,
outputs or decode lengths. Adaptive-minus-replay latency estimates the cost of
selection under these recorded conditions, including its effects on loading
and caches. It is not automatically equal to the sum of inclusive classifier
spans, and the measured replay difference can include environmental variation.

## Monotonic timing and non-overlapping accounting

Application tracing uses monotonic nanosecond timestamps and parent/child span
relationships. Durable start and end records preserve incomplete spans after
interruption. The real execution path records deterministic routing, actual
memory/compute classifier calls, model transition and unload HTTP requests,
verified eviction, retrieval, answer generation, validation, complete request,
and per-call residency audits. Eviction verification polls `/api/ps` after the
unload acknowledgment until the evicted model is absent; acknowledgment and
verified absence are distinct measurements.

Complete request latency runs from immediately before `Conversation.send` to
its validated response or recorded exception. Pre-request admission and outer
post-request checks are outside that request span. Checks inside the actual
backend path remain included. Startup runs from BGE/memory initialization to
conversation readiness. Complete sequence latency is measured from startup
start through all four turn attempts and their intervening work, before
cleanup. The recorded identity is:

```text
sequence_total = startup + sum(complete_request_spans) + sequence_gaps
```

The gaps include the relevant between-turn guards, residency reads and artifact
work. Cleanup is separately timed. The broader process envelope includes
admission, telemetry initialization and cleanup; scheduler cooldown waits are
outside the per-sequence total and retained separately. The first cold request
is never discarded or treated as an unreported warm-up.

Ollama load, prefill, decode and total durations are backend-reported metadata
inside their enclosing HTTP/classifier/generation wall span. They are not
independent additions to request latency. A cold memory classifier can load
the model subsequently reused for generation. In the bypass replay, that same
cold load may move into the first generator call. Charging the classifier's
inclusive cold load and then adding a second assumed generator load would
count the same startup cost twice.

The analyzer partitions each complete request into the deepest active observed
spans plus residual unaccounted wall time. Children must fit inside parents;
unrelated overlapping spans are rejected. Exclusive component totals must
sum exactly to request wall time, while inclusive router/generator spans and
backend durations remain separate explanatory tables. This allows eviction,
residency observation and classifier time to be described without adding
nested totals. Instrumentation, durable logging and repeated residency reads
have their own cost; reported latency belongs to this instrumented system.
Non-streaming responses do not provide measured time to first token.

## Resources and cleanup

The existing post-memory process-scoped guard requires at least 2 GiB available
RAM and temperature below 55 C at startup; runtime requires at least 768 MiB
available RAM and temperature below 68 C. The scheduler waits for below 54 C
before handing off to the startup gate. Startup/runtime logical swap usage is
capped at 3,554.1640625 MiB, reserving 256 MiB from the unchanged
3,810.1640625 MiB capacity. These experimental limits are not demonstrated
hardware safety boundaries. Zram occupancy is logical compressed-page usage,
not additional physical RAM or direct evidence of active swapping.

The collection holds a shared inference lease, launches serial child processes,
checks competing experiment processes and unexpected model residency, and
retains 500 ms telemetry. Admission/cleanup require a running fan, the existing
15 W mode, unchanged boot, zero thermal-trip counters and unchanged swap
capacity. Model operations remain serialized by the shared Ollama client.
Every sequence saves admission, telemetry, model-allocation observations and
cleanup; final verification must establish no model remained resident.

Ollama `size` and `size_vram` describe loaded allocations and provide a useful
placement diagnostic. Their ratio is not a direct measurement of the fraction
of arithmetic performed on GPU, particularly on unified-memory hardware.
Any placement or output-length differences must accompany latency attribution.
No OS or user-application change is permitted to obtain admission. Final host
and configuration claims require the completed final audit; they are not
assumed from the freeze.

## Original collection and prospective continuation

The original freeze was created at 15:45:53 UTC on 12 September 2026 after
945 offline tests: 919 passed and 26 skipped, without failures/errors. The
first collection stopped after 22 whole four-turn sequences, containing 88
attempts. Turn four of `ro_dddd_3_r1_large` raised `ResponseValidationError`
for omitted temporal detail. The harness incorrectly treated this ordinary
answer rejection as fatal because it inherits `ValueError`. All four requests
had been attempted; recorded device/transport checks and cleanup passed.
The rejected answer remains a technical failure, and the original raw turn
and sequence statuses remain `interrupted`.

Before further inference, the prospective v2 amendment removed ordinary
`ValueError` from the harness's fatal tuple and made the explicit replay
completion invariant a `SafetyGateError`. Added regression coverage verifies
continued collection following intermediate/final validation rejections. The
v2 freeze was created at 16:33:52 UTC after 946 tests: 920 passed and 26 skipped.
The exact application source, routing, workload, memory, generation settings,
model digests, guards and timing boundaries did not change. The source delta
and [independent freeze review](freeze_v2_review.json) document the limited
handler/provenance change and two added continuation/analysis adapters.

The [continuation scheduler](continue_collection.py) retains the exact first
22 whole sequences using file symlinks to their immutable originals, then
starts the next unattempted slot, `ro_dddd_3_r1_adaptive`. Its plan adds 122
sequences/488 attempts. It does not retry a wrong or rejected answer or splice
later turns into an incomplete sequence. The reused exception is eligible
because its fourth request already completed with a validation rejection;
its measured time and failure remain in all relevant denominators.

The [mixed-freeze analyzer](analyze_continued.py) verifies each session against
its actual freeze and checks identical execution controls. Its one completion
eligibility exception is restricted to named, hash-pinned original artifacts,
all four recorded turns, the exact error, successful calls, clean resources
and successful cleanup. It does not change raw statuses or quality outcomes.
The continuation is a disclosed failure-accounting correction after observed
outputs, so the combined experiment is exploratory, not a fresh confirmatory
study. The collection pause and any placement/cooldown consequences must remain
visible in the final interpretation.

## Statistical and answer-review boundaries

Paired timing differences use matching sequence IDs and repetition numbers.
Positive comparator-minus-adaptive differences mean observed adaptive savings;
adaptive-minus-replay measures the diagnostic selection increment. Report the
sign convention with each table. Startup-inclusive sequence totals, request
sums, transition turns and their following turns are complementary scopes.
A last-turn switch has no subsequent observed turn in that sequence. Actual
selected and actual generation models must remain separate when composition
or fallback changes the renderer.

The three timing repetitions are dependent repeats of 12 authored sequences,
with shared prompts, templates and one fictional memory profile. They are not
576 independent tasks. Report each repetition and pattern, and summarize paired
differences per sequence before any descriptive cluster resampling. Three
variants per pattern cannot support precise tail estimates or rare-failure
claims. A resampled interval does not establish independence of the authored
sequence variants. No application quality threshold, response deadline or
equivalence margin is selected after seeing results.

All delivered answers require semantic review against the frozen rubric and
actual supplied evidence. JSON/schema validity, memory-ID citations and lexical
checks are not answer correctness. Technical failures receive no useful-answer
credit; inappropriate abstention on a known answer fails the task. Appropriate
social responses exercise routing but provide limited evidence of improved
reasoning. Record reviewer type, blinding, disagreements and adjudication.
Assistant review must be labeled, and independent human review remains pending
unless actually obtained. Measured time savings alone do not establish a
quality–latency improvement.

Historical post-memory timing/quality results retain their original meanings.
They motivate this experiment and supply the memory fixture, but their
48-request sessions with fresh per-request history lack these controlled
four-turn/replay conditions and cannot fill missing paired observations.
