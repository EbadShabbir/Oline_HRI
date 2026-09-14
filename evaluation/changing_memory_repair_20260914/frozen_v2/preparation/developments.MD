# Development Decisions

Latest completed evaluation: [changing memory, 14 September 2026](evaluation/changing_memory_20260914/README.md). All 288 live checkpoints are complete. Correct persistent memory state did not prevent old-value disclosure with retained conversation history. Human validation is pending.

This file records confirmed implementation decisions for the offline personalized conversational robot.

## Changing-memory lifecycle evaluation — 2026-09-14

Completed the frozen deployed-system experiment across 12 fictional scenarios,
36 independent databases and 288 live checkpoints. Added the lifecycle runner,
independent authored ledger, offline harness validation, real process restart
orchestration, controlled logical clock, immutable tracing, blinded answer
review, analysis and report tooling. The primary run is preserved without a
production repair or rerun.

Persistent memory operations and snapshot freshness passed the audit, but
delivered answers did not reliably honor them. Retained-history current-value
queries disclosed the superseded value in 21/24 cases; deletion and expiry
queries disclosed the revoked subject in 39/48 and 27/36 retained-history cases.
Restart with evaluation-restored history did not remove this behavior. Fresh-history
queries showed no original-fact resurrection in these deletion/expiry checks,
but two answers instead matched an unsupported personal preference present in a
generator prompt example. Storage exclusion is therefore insufficient evidence of delivered
forgetting or correction.

The traces identify routing that bypasses retrieval while forwarding old history,
four genuine evidence-selection omissions, unsupported or unrequested generated
details, and five unnecessary validation withholdings. The validation defects
concern a “current” relationship qualifier and correction-operation timestamps
incorrectly required as appointment details. Those five outcomes remain failed
delivered recall despite supported raw replacements. Further implementation
changes need a separately labeled evaluation; this result does not establish
that any proposed repair works.

The observed schema-7 runtime uses the CLI-default LLM router, Qwen3 0.6B/1.7B,
2048 context, **192 output tokens**, temperature 0, seed 42, thinking disabled,
and real BGE ONNX CPU embeddings. The resolved 192-token setting is recorded in
the freeze; the older 128-token decision below is historical. Actual scored
generator selections were 254 small and 34 large. Existing inference leases,
residency rules and device guards remained active. All 13 worker admission
failures preceded inference; no attempted checkpoint was repeated.

All 288 answers received frozen independent assistant review (214 grouped
packets, complete agreement). Useful full-rubric delivery was 118/288, including
13/48 replacement recalls; human validation remains pending. A separately
preserved analysis-parser correction changes only five stage diagnoses, not
runtime behavior, answer judgments or scores. The [report](evaluation/changing_memory_20260914/README.md)
links all evidence, tables, figure and reproducible commands. Results concern
**process restart and controlled logical-time expiry**, not power-loss recovery
or spoken performance.

## Superseding deployment decision — 2026-09-09

Deploy `qwen3:0.6b` as the resident router/small generator and
`qwen3:1.7b` as the shared generator for both large roles. Only those two tags
are reachable by the application. Use a 2,048-token context, 128-token output
cap, temperature `0`, thinking disabled, and a 120-second large-request timeout.
Inference remains serialized: evict the small model before a large request and
give the large model zero keep-alive.

This decision supersedes the earlier split 1.7B/4B deployment and the earlier
temperature `0.2`, `2176/320`, 600-second baseline. A later `qwen3:4b` load
caused a recorded `BCCPLEXWDT` reset, so the 4B measurements below are retained
only as unsafe historical evidence and must not be rerun on this Jetson. The
selection evidence and known answer limitations are recorded in the
[2026-09-09 model-pair report](evaluation/model_pair_runs/20260909_report.md).

## Jetson Orin Nano deployment baseline

1. Keep Qwen3-0.6B as the resident small model and router.
2. Run Qwen3-1.7B for both large roles in non-thinking mode.
3. Initially use a dedicated TensorRT vision detector rather than a generative vision-language model.
4. Run only one heavy model at a time.
5. Use headless Linux, NVMe storage, active cooling, batch size 1, and an approximately 2K-token context.
6. Invoke vision periodically or in response to an event, rather than continuously processing the camera at full frame rate.

### Retired Qwen3-4B device baseline (historical, superseded)

Task 11 verified `qwen3:4b` Q4_K_M through local Ollama in non-thinking mode
with a 2,048-token context. The controlled cold request took 113.99 seconds
wall time, including 72.88 seconds to load, and its generation phase ran at
2.45 tokens/s. Three resident repeats had a median wall time of 43.89 seconds
and a median generation rate of 1.49 tokens/s. RAM reached approximately
7.0/7.62 GB and swap reached 3.81/3.81 GB.

At the time, these measurements supported considering 4B only as the slower,
on-demand grounded-large route. The later watchdog reset and model-pair result
supersede that conclusion. The archived setup, measurements, and limitations
are recorded in the
[Qwen3-4B Jetson benchmark](benchmarks/qwen3_4b_jetson.md).

### Target 2 route-specific speed decision (historical, superseded)

On 2026-09-09, Qwen3-1.7B passed the frozen large/no-memory recovery gate and
three comparison seeds at the retained temperature 0.2. The comparison median
was 32.697 seconds cold wall time and 21.791 seconds model load, versus reused
exact-case Qwen3-4B medians of 75.516 and 44.380 seconds. This is a 56.7% wall
reduction on that case. Global replacement was rejected at that stage: 1.7B
failed every grounded recency case and a second prompt gate. The then-current
decision changed only the large no-memory route and retained 4B for grounded
responses; the superseding decision above replaces that deployment mapping.
See the
[Target 2 frozen protocol](evaluation/response_speed_general_model_v3_protocol.md)
and [result report](evaluation/response_speed_general_model_v3_report_20260909.md).

## Confirmed conversational pipeline

```text
Speech -> STT -> compute-and-memory router
                    |-- no memory + small model -> Qwen3-0.6B
                    |-- memory + small model    -> retrieval + Qwen3-0.6B
                    |-- no memory + large model -> Qwen3-1.7B
                    `-- memory + large model    -> retrieval + Qwen3-1.7B
                                                     |
                                                     v
                                        validated speech + action
                                                     |
                                                     v
                                              TTS + gesture
```

The router makes two independent decisions: whether personal-memory retrieval
is needed and whether the request requires a small or large compute route. RAG
does not automatically require the larger model. A simple personalized
question may use retrieval with Qwen3-0.6B, a complex non-personal question uses
Qwen3-1.7B, and a complex grounded question uses that same 1.7B tag with
retrieved evidence. Generated speech
and action output must be validated before TTS or gesture execution.

## Offline personal-memory embedding and storage

### Core design decision

Embeddings are a searchable index over verified personal memories; they are not the memories themselves and do not train or modify either Qwen model.

For Version 1:

- Use [`BAAI/bge-small-en-v1.5`](https://huggingface.co/BAAI/bge-small-en-v1.5) as the embedding model.
- Run the official [ONNX model](https://huggingface.co/BAAI/bge-small-en-v1.5/tree/main/onnx) through ONNX Runtime on the Jetson CPU so that the GPU remains available for Qwen and vision workloads.
- Keep SQLite as the authoritative memory database.
- Use [SQLite FTS5](https://sqlite.org/fts5.html) for exact words, personal names, dates, locations, medicines, and abbreviations.
- Store normalized 384-dimensional `float32` embeddings as SQLite BLOBs and load only the active user's vectors into a contiguous in-memory matrix.
- Perform exact cosine-similarity search in the application for Version 1.
- Keep memory on the NVMe drive and protect it with device encryption. SQLite is not encrypted by itself.

BGE-small-en-v1.5 has approximately 33 million parameters, produces 384-dimensional embeddings, and is substantially lighter than keeping another Qwen-size model resident. `Qwen3-Embedding-0.6B` is a separate checkpoint from the conversational Qwen3-0.6B; its weights cannot be reused from the resident router/generator. It is therefore deferred unless later multilingual evaluation demonstrates a need for it.

The BGE query instruction `Represent this sentence for searching relevant passages:` is applied to retrieval queries only. Stored memory sentences are embedded without that query prefix. All embeddings must be normalized consistently. Do not mix vectors created by different embedding models or revisions in the same search matrix; a model change requires re-embedding the active records.

### Memory-writing example

```text
User: "Remember that I prefer mint tea without sugar."
                           |
                           v
Robot reads back the normalized fact and requests confirmation
                           |
                           v
Canonical memory: "Preference: user prefers mint tea without sugar."
                           |
              +------------+------------+
              |                         |
              v                         v
     SQLite text + metadata      384-number embedding
              |                         |
              `------------+------------'
                           v
                 persistent local memory
```

Later, a question such as "How do I normally take my tea?" is embedded. Similarity search locates the verified record, and the original readable memory—not an attempted reconstruction of the vector—is supplied to the selected Qwen model.

### Storage schema

The exact schema may evolve during implementation, but it must preserve the following separation:

```text
memory_item
  id
  profile_id
  kind
  canonical_text
  source_turn_id
  event_time
  sensitivity
  consent_status
  confidence
  importance
  status
  supersedes_id
  valid_from
  valid_until
  retention_until
  created_at
  updated_at

memory_embedding
  memory_id
  model_id
  model_revision
  dimension
  normalized
  content_sha256
  vector_f32
```

The content hash detects an embedding that no longer matches its memory text. Memory status includes at least `active`, `superseded`, and `retracted`. The FTS5 index and in-memory vector matrix are derived indexes and can always be rebuilt from the authoritative records.

Exact reminders, scheduled actions, medication schedules, and actuator commands must use separate structured transactional tables and deterministic validation. A retrieved semantic memory is context for conversation; it is never sufficient authorization to perform an action.

### Version 1 write policy

Version 1 does not automatically learn from every conversation. Long-term storage is limited to:

- An explicit instruction such as "remember this."
- A controlled record required by the seven-day case study.
- A fact, preference, routine, relationship, or event that the robot explicitly asks about and the user confirms.

Before writing a memory, convert it into a short canonical statement and read it back when an error would matter, especially for names, relationships, addresses, dates, times, health information, and scheduled activities. Do not embed complete transcripts when a short verified fact is sufficient. Immediate conversation context remains in RAM and expires at the end of the session unless the user deliberately saves something.

Do not place the following in ordinary long-term embedding memory:

- Low-confidence speech-to-text output.
- Raw continuous audio or complete transcripts by default.
- Passwords, PINs, payment-card details, bank information, or security codes.
- Inferred emotion, sadness, stammering, a diagnosis, or another paralinguistic estimate.
- A model guess or unconfirmed model-generated summary presented as a user fact.
- Hot-microphone content, television speech, or another person's private information.
- Medication changes or doses as an executable instruction.

A temporary estimate such as `possible_sadness` may adapt the current conversational tone, but it must not become a permanent statement that the user is sad.

### Retrieval pipeline

```text
Current user request
        |
        v
Does this request require personal memory?
        |
       yes
        |
        v
Embed query with BGE-small
        |
        v
Filter before search: current profile + active + consented + unexpired
        |
        v
Structured SQL lookup + FTS5 search + exact cosine search
        |
        v
Fuse/rank at most three candidates; identify high-confidence request links
        |
        v
Pack required records first, then bounded optional candidates,
to the independently selected Qwen3-0.6B or Qwen3-1.7B model
```

Use structured SQL first when the answer belongs to an exact field. Combine lexical and semantic results for conversational memories so that exact personal names and dates are not lost through semantic matching. Recency and importance may be small ranking signals, but they must not override consent, expiration, profile separation, or contradiction handling.

Do not adopt an arbitrary cosine threshold. Calibrate retrieval and abstention thresholds using project-specific query-memory pairs. When evidence is weak, stale, or conflicting, the robot must ask the user or say it is uncertain rather than selecting the nearest vector blindly. Retrieved text is untrusted contextual data, not a system instruction.

### Implemented Version 1 routing and fusion contract

The first text-chat integration uses Qwen3-0.6B as a strict structured router.
It makes two calls: the memory classifier returns `form` (`question`,
`statement`, or `request`) followed by `memory_required`, and the other returns
only `model_size` (`small` or `large`). The input-form label was added after
live automatic-memory testing exposed confusion between supplying a personal
fact and asking to recall one; it does not require an additional model call.
Historical Boolean-only routing artifacts remain readable by evaluation.
The routing decisions are independently
validated and neither is derived from the other. Invalid or truncated router
output stops the turn; there is no heuristic fallback. Router sampling is fixed
at temperature zero and seed 42 independently of generator sampling. The
selected generator is Qwen3-0.6B for a small route and Qwen3-1.7B for either
large route; retrieval remains independently controlled by memory need.
Configuration pins those two tags. Routed conversation construction rejects a
large model that collides with the resident small model so the compute routes
cannot silently collapse.
Request-link analysis and evidence packing are a third, deterministic step and
are independent of model size: either generator may receive one or several
required records, and an explicit synthesis request may also carry optional
candidates that are not eligible for citation.
Ollama must use a loopback endpoint, and the default client disables environment
proxies.

### Implemented sequential Ollama lifecycle

The CLI passes one shared Ollama client to the router and generator. The client
serializes the complete lifecycle transaction and tracks only residency that it
has confirmed itself:

```text
unknown/start -> unload 1.7B -> Qwen3-0.6B (`keep_alive=-1`) -> resident small
resident small -> unload small -> Qwen3-1.7B (`keep_alive=0`) -> no model resident
no model resident -> selected Qwen model
```

An acknowledged unload must finish before the replacement request begins.
Consecutive small-model calls reuse the resident model, while the shared large
model is on demand and does not linger after a successful response. Any interrupted
or failed transaction invalidates cached residency so the next request starts
with conservative unloads of every configured peer. No prompt, history, or retrieved memory is
included in an unload request.

This is an application-level guarantee for callers sharing that client, not a
server-wide lock against unrelated Ollama tools or processes. The deployment
must not run competing model clients unless Ollama is also configured and
verified with a server-wide one-model limit.

### Implemented Step 14 resilience contract

Configuration schema 6 uses separate local Ollama socket-operation budgets:
30 seconds for unload, 60 seconds for the router and selected small model, and
120 seconds for the large model. The former 300- and 600-second values were
failure budgets for the retired 4B route, not response-time objectives. The
historical Step 16 run measured a pre-redesign distribution; a current
performance claim requires a new controlled run.

The only automatic generation fallback is one `qwen3:1.7b` timeout followed by
one `qwen3:0.6b` attempt. It reuses the identical prompt, bounded history,
structured-output schema, and per-turn memory-ID authority. There is no fallback
for a router or small-model timeout, retrieval or snapshot failure, non-timeout
transport error, malformed metadata, truncation, invalid JSON, invented memory
ID, or other response-contract failure. The fallback output passes the normal
validation gate, and any failure leaves conversation history unchanged.

A memory-backed fallback validates the authoritative record snapshot before the
large request, before the fallback, and after the fallback response. Grounded
assistant speech and `memory_used` IDs are deliberately not retained as ordinary
conversation history, because correction or forgetting would otherwise leave a
stale personal fact available to future router and generator prompts. A
memory-requested answer with no retrieved record is also excluded so an
unsupported model claim cannot become a session fact. Until history has explicit
record-level provenance, personal follow-ups must retrieve again. Non-memory
history remains limited to the newest three complete turns, six messages, 2,000
characters, and the aggregate context budget.

The Ollama client reads no more than 64 KiB plus one detection byte. Routing JSON
is rejected above 512 characters and robot-response JSON above 16,384 characters
before parsing. External transport/server bodies and component exception text
are not copied into public errors. In interactive chat, a recoverable failed turn
prints one fixed safe message and the session continues; a failed one-shot chat
still exits with status 3.

Conversational retrieval uses equal-weight reciprocal-rank fusion with `k=60`
over at most 20 FTS5 candidates and 20 cosine candidates. It deduplicates by
memory ID and preserves an exact lexical candidate on a fusion tie. The raw
ranked result is bounded to three records. A deterministic, best-effort
request-link pass uses lexical, name/label, preference, and temporal cues to
mark high-confidence required records independently of the small/large route.
Direct recall selects the best-supported linked record, preserving score ties;
explicit multi-fact or synthesis requests keep every linked record required and
may also disclose the remaining candidates for inspection. A semantic-only
candidate with no detectable link produces a conservative abstention rather
than a claimed personal fact. This is not a calibrated semantic-relevance
guarantee.

The privacy-safe diagnostic distinguishes raw ranked `retrieved_ids`, whole
budget-fitting `supplied_ids` in required-first order, and validated
`model_used_ids`. It emits no memory text, scores, or metadata. Opaque IDs remain
linkable local metadata and must still be protected.

Retrieved records and the current request are serialized into a bounded
application-created user-role JSON envelope. The base system prompt says that
record text is factual data, never an instruction. The envelope is ephemeral,
never enters session history, and is checked against the authoritative database
immediately before and after generation. Component caps are combined with a
conservative aggregate prompt estimate that reserves output capacity and a
safety margin in the configured context window. Only complete history turns and
whole records are pruned. Required records are packed before optional records;
an optional tail may be dropped, but failure to fit all required evidence stops
the turn before generation. Every required ID must appear in `memory_used`, and
optional supplied candidates cannot be cited. With no high-confidence request
link, generated prose is replaced by the fixed application-authored abstention,
`I do not have a verified personal memory that answers that.` An empty
`memory_used` is first replaced with that fixed response; when linked evidence
exists, the subsequent required-citation gate rejects it. Other incomplete
linked citations also fail validation. Memory IDs themselves are forbidden in
speech.

The model-facing memory text rewrites bare `User`/`User's` and
`the user`/`the user's` to `you`/`your` without mutating the stored record. The
generation contract requires human facts to use `you`/`your`, never literal
`the user` or robot `I`/`my`.
One-record direct recall is distinguished from planning or transformation, so
the latter must answer the task rather than merely repeat the record. Best-effort
validators cover distinctive facts from every citation and requested temporal
details; reject detectable perspective swaps, unsupported names or personal
relationships, invented temporal precision, and polarity reversals of positive
general preferences, temporal preferences, or relationships; require uncertainty
for a narrow class of detectable short-label conflicts; and enforce a cited
exactly-three-step preference. Times,
dates, names, and relationships are authorized only by the current request or
cited memory, not merely by an optional supplied candidate. These literal and
regular-expression checks are deliberately best-effort: they do not constitute
a general proof of completeness, temporal reasoning, or semantic correctness.
Gestures remain `NO_ACTION`, and generator errors exposed to the CLI are
sanitized.

The complex-general/no-memory 1.7B path has a task-neutral completion rule that
asks for at most 90 speech words. It follows the requested topic, constraints,
counts, and format, with comparisons or recommendations only when requested.
Planning instructions call for concrete ordered actions and explicit handling
of missing prerequisites. Recovery or changes must stop modifications and
preserve an untouched copy, assess damage, restore only from an available
verified local backup, salvage or rebuild when no backup exists, validate
before normal use, and prevent or monitor recurrence. The instructions prohibit
assumed resources and claims that the model performed actions. This replaces a rule that imposed an
architecture comparison and deployment format on unrelated requests while
preserving normal answers to offline informational tasks. These are generation
instructions, not runtime word-count or plan-completeness guarantees.

The opt-in live-quality suite now includes an offline database-corruption
recovery plan. Its heuristic checks require protection of the original,
conditional use of a usable backup, a no-backup contingency, and validation
before resumption. Architecture checks require three distinct designs,
tradeoffs, and deployment actions. These assertions detect known omissions but
do not prove arbitrary semantic completeness; actual answers still need review.

Historical post-redesign validation on 2026-09-08 completed a 420-test unit
discovery with `OK` (`skipped=19`), 7 live routing tests with `OK` in 21.163
seconds, and 9 live answer-quality tests with `OK` in 677.452 seconds. The
quality suite retains the three fictional Theo, Tuesday-morning, and
exactly-three-step memories and the four exact failed-prompt regressions
documented in the project README. Those
recorded results predate the task-neutral general-planning rule and expanded
assertions above and do not validate those later changes.

The general-planning follow-up on 2026-09-08 passed a fresh 424-test discovery
in 18.919 seconds (`skipped=20`, 404 passed). Focused live database-recovery and
greeting-to-architecture checks passed with the final instruction rule, using
the large model without memory retrieval. The new recovery regression failed
on the original rule before implementation. This follow-up verifies general
planning; it does not claim a rerun of the entire expanded live-quality suite
or resolution of the separate relationship-completeness issue.

### Implemented Step 15 fictional evaluation fixture

Step 15 supplies a versioned, fully synthetic Monday-to-Sunday case study in
[`evaluation/fictional_seven_day_v1.json`](evaluation/fictional_seven_day_v1.json)
and a strict local harness in `oline_hri.evaluation`. Mira, Theo, Luma, and all
events are fictional. The fixture contains no human-participant data, is not a
user study, and cannot establish generalizable behavior or suitability for an
intended population.

The manifest contains 15 ordered lifecycle events (13 remembers, one
correction, and one forget), 14 deterministic record versions, three
policy-withheld topics with no private values, and 30 author-gold cases. The
cases cover every combination of memory/no-memory and small/large routing, as
well as correction, deletion, expiration, recency, contradiction, absence,
confirmed sensitive information, prohibited secrets, unconfirmed third-party
data, and unconfirmed affect inference.

The loader rejects malformed or internally inconsistent manifests. The replay
helper materializes the events into a new isolated SQLite database through the
public memory lifecycle, while prompt emission produces deterministic JSON
Lines for `all`, `router`, or `rag` tracks. Run:

```bash
PYTHONPATH=src .venv/bin/python -m oline_hri.evaluation validate
PYTHONPATH=src .venv/bin/python -m oline_hri.evaluation prompts --track all
```

The labels remain `author_gold_pending_independent_review`; a second reviewer
must inspect them without model outputs before they support reported results.
Step 15 does not run either Qwen model, score responses, or report router,
retrieval, answer-quality, latency, token, RAM, swap, thermal, or power metrics.
Those executions and objective measurements were completed by the historical
pre-redesign Step 16 run; independent label/answer review and final deployment
measurements remain open.

### Scale and deferred vector-index options

One 384-dimensional `float32` vector occupies 1,536 bytes before database overhead. Approximately 10,000 vectors require 14.6 MiB of raw vector memory, and 50,000 require about 73 MiB. The one-week study should be much smaller, so an exact scan is simpler, deterministic, and sufficient for the first implementation.

Do not deploy Chroma, Qdrant, or a separate resident vector-database service in Version 1. Do not add FAISS merely because the system uses embeddings. If measured search latency becomes unacceptable at roughly 50,000-100,000 active memories, evaluate CPU [FAISS](https://github.com/facebookresearch/faiss) or another pinned local index. Any future vector index remains a rebuildable cache; SQLite remains the source of truth.

### Privacy, profile isolation, correction, and deletion

Embeddings are sensitive data, not anonymized data. Research has shown that text and personal information can sometimes be reconstructed from embeddings; see [Text Embeddings Reveal (Almost) As Much As Text](https://aclanthology.org/2023.emnlp-main.765/). Protect memory text, embeddings, full-text indexes, backups, and exported data to the same standard.

- Use Jetson-supported LUKS storage protection as described in the [NVIDIA disk-encryption documentation](https://docs.nvidia.com/jetson/archives/r38.4/DeveloperGuide/SD/Security/DiskEncryption.html).
- Optionally add application-level database encryption with [SQLCipher](https://www.zetetic.net/sqlcipher/) if the deployment threat model requires protection beyond full-disk encryption.
- In Version 1, use one encrypted database for the single active user profile.
- For future multi-user operation, separate user databases/indexes and keys. Select the authenticated profile before retrieval; never search all users and filter afterward.
- Provide a user-visible command such as "What do you remember about me?" together with review, correction, export, and deletion controls.
- Audit memory operations using record IDs, operation type, and time without copying private memory content into ordinary logs.

A correction creates a new record, marks the old record `superseded`, and embeds the corrected canonical text. A "forget that" request retracts or deletes the authoritative record and removes its embedding and FTS entry; the in-memory matrix is then rebuilt. The retention and backup policy must define when deleted records disappear from recoverable backups as well.

### Evaluation before freezing the design

The matched-evidence generator capability experiment (2026-09-12) is complete:
120 fresh requests, 30 per category, were independently assistant-reviewed
before inference and run once on each installed generator. The experiment
bypasses routing, retrieval, composers, literal-answer constraints, rewriting
and fallbacks. Both models receive identical complete evidence, empty history,
raw rendered prompts, free-string JSON schema and 2048/192/temperature-0/seed-42
settings with thinking disabled. Dataset, protocol, source and model digests
were frozen; all 240 primary attempts completed under the existing resource
guards with sole-model residency and no OS configuration changes.

Full-rubric assistant-reviewed success is 43/120 for 0.6B and 76/120 for 1.7B:
39 both-correct, four only-small, 37 only-large and 40 neither-correct pairs.
Twenty-six large-only rescues were answerable requests. Mean warm time is
0.767 versus 3.932 seconds (+3.165 s, 5.13×); preload-amortized block means
are 1.218 versus 5.032 seconds. The larger model still fails 44 full rubrics
and succeeds on only 3/18 unresolved-conflict cases. Automatic CPU/GPU placement,
short authored cases and assistant scoring limit generalization. This supports
observed complementary capability at measured cost; it establishes no cascade,
retrieval, spoken-system or deployment-requirement benefit and changes no policy.

Two fresh blinded assistant reviews agreed on label and flags for 232/240
answers; a third blinded assistant adjudicated eight disagreements before
unblinding. Independent human validation remains pending. Validation passed
24 focused and 31 reused guard/telemetry tests plus four excluded live harness
attempts. The [full report and immutable artifacts](evaluation/matched_evidence_20260912/README.md)
include raw answers, complete paired examples, loading/timing/energy, frozen
reviews, source/model audits and reproducible commands. Earlier experiments
are preserved; current summary tables are in [results.md](results.md).

Step 4 (2026-09-12) completes the final tradeoff analysis and paper figures
using Step 3's recorded 432 attempts. No new inference or scoring was performed.
The [analysis and reproducible figures](evaluation/final_tradeoff_analysis_20260912/README.md)
separate correct delivery from validated delivery, report all three timing
rounds, and summarize loading and sampled whole-device energy. At five seconds,
small/large/cascade deliver 42/11/20 fully correct answers out of 144; at fifteen
seconds they deliver 42/39/46. These are descriptive readouts, not requirements.
The pooled cascade timing advantage reverses in two rounds and remains
confounded by GPU allocation; only 3/144 generations use small. The evidence
does not yet justify the adaptive selector. Human review, retrieval ablations,
live-memory episodes and integrated speech evaluation remain separate work.

Step 3 (2026-09-12) completed the comparison of small-only, large-only and
lightweight cascade systems under a separately frozen, user-authorized swap
allowance. All 432 attempts ran: 48 requests repeated three times per system,
starting large-only, cascade, then small-only and rotating later rounds.
Both fixed controls share the policy-first memory gate and classify unresolved
requests only on their own model. The systems share retrieval and evidence
checks while retaining router state and model residency between requests.

Assistant-assessed full-rubric success was 42/144 (29.2%) for small-only,
44/144 (30.6%) for large-only and 46/144 (31.9%) for cascade; mean text-request
times including cold loads and failures were 2.314, 11.255 and 8.916 seconds.
The cascade used small for only 3/144 generations. Its pooled speed difference
from large-only is confounded by CPU/GPU placement and reversed in rounds 2
and 3. All systems scored zero full successes on temporal/synthesis requests.
These results do not yet justify the cascade or establish a quality/deadline
requirement. Independent human review remains pending; repeated observations
of the same 48 requests are not independent quality samples.

The [full results](results.md) and
[collection, review and validation record](evaluation/post_memory_comparison_20260912/README.md)
preserve all nine sessions, 145 resolved blinded output groups and complete
artifact checks. The revised logical-swap ceiling used existing capacity minus
a 256 MiB reserve; no swap device or OS setting changed. One zero-request
temperature rejection was retained separately, then the remaining sessions
continued without retrying any answered request. Cleanup left no resident model
and preserved power, boot, thermal-trip counters, source and model metadata.
The earlier restricted-swap attempt remains historical: only its first
48-request small-only session ran. Its answers are not pooled into the revised
comparison. This exploratory reuse of the partly observed application workload
is distinct from the broader draft's live-memory Stage 3 and the earlier ARC
benchmark; earlier workloads, scores and source archives remain unchanged.

Step 2 (2026-09-12) improves the shared memory path: embedded personal-request
recognition, bounded subject/attribute/event linking, candidate field coverage,
zero disclosure of unlinked neighbors, preserved same-event conflicts, and
explicit unknown fields in supported partial recall. Consistent stored event
timestamps support bounded ordering/elapsed-time composition; unsupported or
contradictory temporal tasks decline it. Real separate-process tests exercise
correction, forgetting, expiry, profile isolation, and stale-answer rejection.
The [implementation and offline replay](evaluation/memory_pipeline_20260912/README.md)
record development checks, limitations, and source preservation. On identical
recorded candidate sets, all required facts were selected in 47/56 attempts
before and 54/56 after. This is deterministic function replay, not new answer
accuracy or a held-out quality result. Original benchmark scores are unchanged.

On 2026-09-12, the first overhead improvement was implemented as opt-in
`chat --routing-policy lightweight`: deterministic compute selection, zero or
one memory classifier call, active-generator retention, and a two-easy-turn
switch rule. Verified compositions reuse selected resident large; model peer
eviction and exit cleanup remain explicit. This is an untrained heuristic
awaiting quality and device-speed evaluation, not evidence of a cascade win.
Automatic capture still uses 0.6B and voice still unloads before recognition.
The [implementation record](evaluation/lightweight_routing_20260912/README.md)
contains validation and the blocked preflights (812.5 MiB swap versus the
unchanged 768 MiB startup limit; zero inference). The exact 34 Stage 2 execution
files were [archived](evaluation/complete_system_20260911/frozen_source_v2/archive_manifest.json)
before changes, preserving the source of the earlier results.

Proposed next paper evaluation: [adaptive selection protocol draft](evaluation/adaptive_selection_protocol_draft.md)
(2026-09-11). This separates paired generator capability, optimized single-model
comparisons, and memory-lifecycle ablations. Its acceptance thresholds are
provisional; it records proposed work, not a confirmed deployment change.

The [2026-09-11 ARC capability pilot](evaluation/arc_capability_20260911/README.md)
completed 100 questions each with 0.6B alone, resident 1.7B alone, and CLARA
generator selection: 64%, 79%, and 79% correct, with mean question times of
0.40 s, 0.62 s, and 29.82 s. The cascade selected 1.7B on 95/100 questions;
this workload shows a larger-generator capability gain but no cascade efficiency
gain. This is a public science-MCQ subset under a common adapter, not the full
personalized/spoken system. The permitted Qwen2.5 3B fourth condition later ran
under a documented 384 MiB startup swap allowance, then stopped during request
84 when swap crossed the unchanged 512 MiB runtime ceiling. It produced 59
correct accepted answers among 83 successful requests; later successful
requests averaged 0.80 s. A user-requested continuation completed only the
17 remaining questions, with 12 correct, giving 71/100 composite item accuracy
(38/50 Easy, 33/50 Challenge). The continuation used a documented 1 GiB runtime
swap ceiling and automatically placed 30/37 layers on GPU, versus 37/37 in the
first segment; later successful requests averaged 1.86 s. This is segmented
item coverage, not a successful uninterrupted run under the original 512 MiB
criterion. Cleanup unloaded the model and preserved swap/power configuration;
swap occupancy remained about 546 MiB. The 4B model was not loaded and was
removed at the user's request. Full evidence and limitations are linked.

The [complete text-system pilot](evaluation/complete_system_20260911/README.md)
then recorded 184 of 432 planned attempts using the real routing, retrieval,
generation, and validation path. On the same 40 first-round requests, assistant
rubric review scored small-only 16/40, large-only 21/40, and CLARA 19/40.
Small-only was fastest; cascade loading consumed 58% of its request time and
its first session stopped at the 768 MiB available-RAM floor. A later large-only
session completed, but residual swap blocked subsequent startup under the
unchanged common policy. Five sessions remain unattempted. Variable CPU/GPU
placement, unequal achieved repetitions, authored workload, and pending human
review limit inference. The [full results](results.md) preserve all failures,
coverage, timings, and diagnostics. This measures a prepared memory snapshot
and complete text path; spoken-system and independently varied retrieval/live
memory tests remain outstanding. No cascade advantage has been established.

The pre-redesign Step 16 run executed the embedding, retrieval, routing, and
answer paths against the Step 15 controlled seven-day fixture. A current rerun
should also use other project-specific query-memory pairs. LoCoMo remains a
separate planned benchmark and is not included in the fictional fixture. Report:

- Recall@5 and mean reciprocal rank.
- Precision of the memories actually supplied to Qwen.
- False-retrieval rate and no-memory/abstention accuracy.
- Retrieval of stale, expired, superseded, or contradictory memories.
- `memory_used` record IDs for reproducible analysis.
- Embedding latency, search latency, end-to-end retrieval latency, and p50/p95 values.
- CPU and shared-memory use, NVMe activity, power, temperature, and throttling on the final Jetson.
- Deletion/correction success and zero cross-profile retrieval in any later multi-user test.

### Historical Step 16 collection and objective scoring (pre-redesign)

The 2026-09-07 local benchmark runner executed the Step 15 fixture with real BGE,
hybrid retrieval, and Ollama. It compared always-small/no-RAG,
always-large/no-RAG, always-large/bounded-RAG, and the production adaptive
cascade over 30 stateless cases each. The
[frozen protocol](evaluation/step16_protocol.md) defines the four-bundle order,
independent top-five retrieval pass, production top-three memory bound,
decoding settings, and failed-attempt denominators before answer inspection.

The runner preserves raw observations, objective scores, model/source/asset
provenance, Jetson telemetry, and blinded answer-review rows. An offline merge
command checks source compatibility and produces one combined report using
the predeclared first bundle's component-retrieval measurements. See the
[run and merge instructions](evaluation/README.md#historical-step-16-run-and-merge-pre-redesign).
Keep private artifacts in an owner-controlled persistent directory selected by
`OLINE_HRI_RUN_ROOT`: a reboot lost an earlier collection under `/tmp`, so it
cannot serve as final evidence. Raw dated bundles and generated reports contain
prompts, answers, provenance, and device telemetry; they are intentionally not
versioned.

All four 30-case baselines completed with 120/120 valid structured turns,
zero errors, and zero fallbacks. Their provenance matched and the objective
merge completed. In the full adaptive run, memory decisions matched author
labels on 25/30 cases, model decisions on 19/30, and both on 15/30. It generated
18 answers with 4B and twelve with 0.6B; median/p95 turn latency was
82.996/126.007 s. These are observed routing and timing results, not established
answer quality or compute savings. These aggregate historical figures remain in
this document; the underlying raw bundle and generated report remain local-only.

These artifacts predate the routing and grounded-generation redesign documented
above. They must be rerun before their metrics are attributed to the current
implementation.

The separate router-only supplement remains unpooled: it matched 24/30 memory
and 20/30 model labels while executing no selected generators. An earlier
unclean reboot interrupted a 4B attempt; automatic approval review initially
blocked a retry, which the user subsequently approved. The retained retry
completed, but the original reboot cause remains unknown.

Collection and objective scoring are complete. Full Step 16 interpretation
remains provisional while the labels await independent review,
and speech accuracy, abstention, temporal correctness,
uncertainty, and hallucination adjudication remain pending blinded human review.
The current Jetson is in 15W mode on `/dev/mmcblk0`, with development processes
active; its storage results describe SD activity. Final NVMe measurements and
microphone, speaker, actuation, and physical offline-disconnection tests remain
deferred. The one-repetition, fixed-order comparison does not establish
run-to-run variability or generalizable answer quality.

## Target-user development scope

1. Build the general personalized robot first.
2. Implement an `older_adult_companion` profile as a configurable use case.
3. Keep `dementia_support` as future work requiring participatory co-design and appropriate ethical evaluation.

## Jetson installation and development reference

### Development arrangement

- Use the complete Jetson Orin Nano Super Developer Kit 8GB rather than the older Jetson Nano or a bare module.
- The Jetson is a separate ARM64 computer running Ubuntu-based Jetson Linux. Windows, macOS, or Linux may be used as the setup and development computer.
- Edit remotely from the development computer with VS Code Remote SSH or transfer code with Git or `scp`. CUDA, TensorRT, camera, GPIO, and robot workloads execute on the Jetson.
- Once SSH access works, operate the Jetson headlessly.

### Additional hardware

- 512GB to 1TB M.2 2280 PCIe NVMe SSD; 1TB is preferred for models, containers, memory, datasets, and logs. Do not use an M.2 SATA drive.
- USB flash drive of at least 16GB for the JetPack installer.
- DisplayPort monitor or DisplayPort-to-HDMI adapter, plus a USB keyboard and mouse for the initial setup.
- Ethernet connection is preferred for installation and development; Wi-Fi may be used afterward.
- Optional data-capable USB-C cable for recovery or USB device mode.
- Add the microphone, speaker, camera, and microcontroller when integrating the robot peripherals.

The developer kit includes the 19V power supply, active cooling, and a Wi-Fi/Bluetooth module. Its USB-C connector is not a display output; use DisplayPort for a monitor.

### Initial operating-system installation

As of September 2026, NVIDIA's current beginner installation path for the Orin Nano Developer Kit is JetPack 7.2.1:

1. On a Windows, macOS, or Linux computer with at least 25GB free, download the Jetson ISO.
2. Use Balena Etcher to create a bootable 16GB-or-larger USB drive; do not merely copy the ISO file onto the drive.
3. Install the NVMe SSD in the Jetson.
4. Connect the monitor, keyboard, mouse, network, installer USB, and included power supply.
5. Boot from the installer USB and install Jetson Linux onto the NVMe SSD.
6. Complete the Ubuntu first-boot configuration and create the Jetson username and password.
7. Check the UEFI/QSPI firmware when required. Firmware older than version 36 needs NVIDIA's JetPack 6.x firmware-update path before installing JetPack 7.2.1.

JetPack 7.2.1 is the current reference, not yet the frozen project version. Verify compatibility with Qwen inference, STT, TTS, camera support, and TensorRT before freezing the software stack. JetPack 6.2.3 remains a fallback if required dependencies do not yet support JetPack 7.

### Post-installation setup

Run on the Jetson:

```bash
sudo apt update
sudo apt install -y nvidia-jetpack git openssh-server python3-venv
sudo systemctl enable --now ssh
hostname -I
```

Connect from Windows PowerShell, macOS Terminal, or a Linux terminal:

```bash
ssh <jetson-username>@<jetson-ip-address>
```

Keep the project source on the Jetson and open it through VS Code Remote SSH. Use only Linux ARM64/Jetson-compatible packages and containers; Windows, macOS, and ordinary x86/AMD64 binaries or containers will not run on the Jetson. Build the TensorRT vision engine against the final frozen JetPack, CUDA, and TensorRT versions.

### Official setup references

- [Jetson Orin Nano Quick Start](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/quick_start.html)
- [Jetson Orin Nano hardware layout](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/hardware_layout.html)
- [JetPack downloads and release information](https://developer.nvidia.com/embedded/jetpack/downloads)
- [Jetson firmware-update path](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/update_firmware.html)
- [JetPack component installation](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/setup_jetpack.html)
- [Jetson Docker setup](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/setup_docker.html)
- [VS Code Remote SSH](https://code.visualstudio.com/docs/remote/ssh)

## Offline speech-to-text design

### Confirmed STT pipeline

```text
Microphone
   |
   v
16 kHz mono audio cleanup
   |
   v
Silero VAD and end-of-turn detection
   |
   v
whisper.cpp with CUDA and small.en Q5_0
   |
   v
transcription-quality and safety gate
   |
   v
personal-memory and model router
```

### Model and runtime baseline

- Run speech recognition completely offline on the Jetson.
- Use CUDA-enabled `whisper.cpp`, compiled natively for the Jetson's ARM64 platform.
- Use quantized `small.en Q5_0` as the primary English STT candidate.
- Retain `base.en Q5_0` as a lower-latency fallback.
- Use batch size 1 and transcribe one completed user utterance at a time.
- If multilingual recognition is introduced later, replace the English-only `.en` model with the appropriate multilingual Whisper model and evaluate it separately.
- Do not use NVIDIA Riva for the initial 8GB build because its resource requirements would compete with the language models, TTS, vision, and operating system.

This choice supersedes the preliminary Faster-Whisper preference. Faster-Whisper remains a fallback if the project freezes JetPack 6.2.3, but its current documented GPU path targets CUDA 12 and is not yet a confirmed drop-in option for JetPack 7.2.1 with CUDA 13.2.1.

### Conversation and endpoint behavior

1. Activate a conversation session before recognizing speech.
2. Keep a lightweight VAD active and preserve a short audio pre-roll so the first word is not clipped.
3. Treat approximately 0.8 to 1.2 seconds of silence as the initial end-of-turn range and tune it on real recordings.
4. Permit a longer silence threshold in the `older_adult_companion` profile to accommodate natural pauses.
5. Transcribe the completed utterance before invoking Qwen3-1.7B, preserving the one-heavy-model-at-a-time rule.
6. Begin with half-duplex audio: pause VAD and STT while TTS is playing so the robot does not transcribe itself.
7. Keep full-duplex interruption, barge-in, and acoustic echo cancellation as later work after the basic pipeline is stable and measured.

### Transcription safety and personal vocabulary

- Never send raw STT output directly to a gesture controller or other hardware.
- Ask the user to repeat an ordinary utterance when transcription quality is low.
- Confirm uncertain names or personal facts before writing them to long-term memory.
- Require confirmation of critical slots before any physical or state-changing action.
- Discard silence, noise-only, and rejected transcriptions rather than routing or storing them.
- Use only a short, consented contextual prompt containing relevant names, local places, and the robot's name. Do not inject the complete personal-memory database into Whisper.
- Delete the temporary raw-audio buffer after transcription by default. Retain audio only when recording is explicitly enabled under the applicable evaluation and consent process.

The STT handoff should preserve the raw transcript, normalized text, timing, and available quality signals so the confidence gate can decide whether to accept the utterance or request clarification.

### Device-level STT evaluation before freezing

Compare `base.en Q5_0` and `small.en Q5_0` on the final Jetson, microphone, speaker, and robot enclosure. Select the final model using the combined accuracy, latency, memory, and power trade-off rather than word error rate alone.

Measure:

- Word error rate and sentence exact-match rate.
- Personal-name and critical-term errors.
- Intent and critical action-slot accuracy, including negation, stop, directions, people, and times.
- Quiet, room/fan/TV noise, near-field, and far-field speech.
- Voice-activity false starts, missed speech, and speech truncation.
- End-of-speech-to-final-transcript median and p95 latency, real-time factor, and cold-start latency.
- Peak shared memory, power, temperature, and throttling on the Jetson.
- Silence hallucinations, self-echo transcription, and false or unsafe action activation in dry-run mode.

Low-confidence transcripts must not create personal memories, and the finite test set must observe zero unconfirmed hazardous action activations. This test result is an engineering requirement, not a general safety guarantee.

### STT references

- [OpenAI Whisper models and model sizes](https://github.com/openai/whisper#available-models-and-languages)
- [whisper.cpp CUDA, quantization, and VAD](https://github.com/ggml-org/whisper.cpp)
- [Silero VAD](https://github.com/snakers4/silero-vad)
- [Faster-Whisper requirements and fallback implementation](https://github.com/SYSTRAN/faster-whisper)
- [CTranslate2 installation and CUDA requirements](https://opennmt.net/CTranslate2/installation.html)

## Offline paralinguistic speech analysis

### Confirmed design

Add a speech-only `speech_paralinguistic_analyzer` that estimates how an utterance was delivered. It must distinguish observable vocal features, uncertain perceived affect, and possible speech-disfluency events. It must not claim to identify a person's true emotion or diagnose stuttering, depression, anxiety, dementia, or another clinical condition.

```text
Microphone -> VAD -> completed utterance buffer
                         |-- whisper.cpp -> transcript + timing
                         `-- paralinguistic analyzer
                               |-- pitch, energy, pace, and pauses
                               |-- coarse vocal-affect estimate
                               `-- possible disfluency events
                                          |
                                          v
                              confidence and safety gate
                                          |
                                          v
                         memory/model router -> Qwen -> TTS/gesture
```

Use the same completed utterance buffer for STT and paralinguistic analysis. Preserve interior silence and a short pre-roll because aggressive VAD trimming can remove evidence needed to measure pauses or possible speech blocks.

### Initial vocal-delivery and affect module

- Use openSMILE with the `eGeMAPSv02` feature set as the initial lightweight CPU-side feature extractor.
- Measure observable features such as pitch, pitch variation, energy/loudness, speaking rate, pause ratio, long pauses, and available voice-quality measures.
- Add only a small, calibrated classifier or regressor rather than another speech foundation model for the initial deployment.
- Represent perceived affect coarsely as activation/arousal (`low`, `normal`, or `high`) and valence tendency (`positive`, `neutral`, `negative`, or `unknown`), accompanied by confidence and an abstention result.
- Prefer statements such as `low_energy`, `fast_speech`, or `long_pauses`; never treat `happy`, `sad`, or `angry` as established facts about the user.
- Analyze one completed utterance at a time with batch size 1. The feature extractor is lightweight and does not violate the one-heavy-model-at-a-time rule.
- Keep emotion2vec and comparable learned speech-emotion models as optional research baselines, not the first Jetson deployment, until memory use, latency, target-user accuracy, licensing, and ONNX/TensorRT compatibility have been verified.

openSMILE is suitable for the research prototype because it is implemented in C++, supports incremental processing, and extracts the required acoustic features. Its open-source version permits private, research, and educational use but not use in a commercial product; commercial development requires an appropriate licence.

### Speech-fluency observation

Treat possible stammering or stuttering as a separate speech-disfluency task rather than an emotion class.

- Use the STT transcript and timestamps to observe whole-word or phrase repetitions and fillers such as `um` and `uh`.
- Use raw acoustic features for possible sound/syllable repetitions and prolonged sounds because Whisper may normalize or omit these events.
- Treat silent blocks as low-confidence or unsupported initially because they can resemble thinking pauses, endpoint silence, noise, or microphone loss.
- In a later phase, evaluate a compact MFCC/log-Mel TDNN, ConvLSTM, or comparable classifier for sound repetitions and prolongations. Export the selected small model to ONNX/TensorRT where supported.
- Produce descriptions such as `observed_word_repetition` or `possible_prolongation` with confidence. Never output `user_has_stuttering` or make a clinical diagnosis.
- Do not draw attention to a disfluency unless the user asks. Instead, allow more response time, avoid interrupting or completing the user's words, and collapse unintended repetition before intent parsing when confidence is sufficient.

SEP-28k may be used for noncommercial research and initial model development. It contains annotated three-second clips for blocks, prolongations, sound repetitions, word repetitions, and interjections. It is not a clinical diagnostic dataset, its annotators were not clinicians, its audio remains subject to the original owners' copyright, and the released dataset is licensed CC BY-NC 4.0. Target-user evaluation remains mandatory.

### Allowed conversational adaptation

Paralinguistic results may influence only reversible, low-risk conversational presentation:

- Long pauses or possible repetitions: extend turn-taking time and avoid interruption.
- Fast or high-energy speech: respond more slowly and briefly where appropriate.
- Low-energy speech: use a neutral check-in such as, "Would you like to continue talking?"
- Low confidence or unusable audio: abstain and continue with normal conversation behavior.

An affect or disfluency estimate must never by itself trigger a physical action, emergency escalation, caregiver notification, medical conclusion, or long-term personal-memory update. Critical actions continue to require the existing validation and confirmation gates.

### Privacy and older-adult safeguards

- Make speech-affect analysis an understandable opt-in feature and provide an immediate way to disable it.
- Process audio locally and delete the temporary audio buffer after STT and analysis unless research recording has been explicitly consented to.
- Keep inferred affect transient and do not build a permanent mood history by default.
- Prefer a consented within-person acoustic baseline over universal pitch, speed, or energy thresholds, while recognizing that deviation from a baseline still does not prove an emotion.
- Validate on the intended older-adult population because age, health, medication, fatigue, language, accent, microphone distance, and room noise can change pitch, breathiness, pace, pauses, and model performance.

Before freezing the module, test speaker-disjoint target recordings from the actual robot microphone and environment. Report per-class or per-event precision, recall, and F1; macro-F1 or unweighted average recall for affect; calibration and abstention coverage; false-positive rates on slow but fluent speech; inappropriate adaptation rate; latency; peak memory; power; and subgroup results where the evaluation sample supports them.

### Paper terminology

Describe this capability as:

> **Probabilistic paralinguistic state estimation and observable speech-fluency detection for adaptive conversation.**

Do not describe it as definitive emotion detection or stuttering diagnosis.

### Paralinguistic-analysis references

- [openSMILE capabilities and licensing](https://audeering.github.io/opensmile/about.html)
- [openSMILE Python feature-set documentation](https://audeering.github.io/opensmile-python/index.html)
- [ASHA guidance on fluency disorders and clinical assessment](https://www.asha.org/practice-portal/clinical-topics/fluency-disorders/)
- [Apple SEP-28k stuttering-event dataset](https://github.com/apple/ml-stuttering-events-dataset)
- [SER_AMPEL older-adult speech-emotion dataset](https://arxiv.org/abs/2311.14483)
- [Healthy-ageing voice systematic review](https://pubmed.ncbi.nlm.nih.gov/32083980/)
- [emotion2vec research implementation](https://github.com/ddlBoJack/emotion2vec)

## Offline text-to-speech design

### Confirmed model and runtime baseline

- Run TTS completely offline on the Jetson.
- Use `sherpa-onnx` on the CPU with one audited Piper/VITS medium ONNX voice as the initial TTS implementation.
- Keep the GPU available for Whisper, Qwen, and vision. CPU-side Piper/VITS synthesis is lightweight and does not count as a heavy foundation model, subject to device-level measurement.
- Use `en_US-ljspeech-medium` as the initial research voice candidate. It is approximately 63.5MB, produces 22.05kHz speech, and its model card identifies the source dataset as public domain. Compare it with other properly licensed voices before freezing the robot's voice.
- Record and audit the runtime, model, voice, training-data, and distribution licences separately. `sherpa-onnx` uses Apache-2.0, while voice-model licences vary.
- Keep Kokoro-82M ONNX as a Version 2 naturalness benchmark. Promote it only if the final Jetson tests show acceptable first-audio latency, real-time factor, memory, power, temperature, intelligibility, and user preference.
- Do not use NVIDIA Riva for this 8GB Orin Nano baseline. The current JetPack 7 Riva embedded path targets Jetson Thor, and Magpie TTS lists approximately 8.5GB of unified memory.
- Do not implement voice cloning in the first version.

### Confirmed TTS pipeline

```text
Validated Qwen response and action
                |
                v
Text normalization and pronunciation dictionary
                |
                v
Sentence chunking
                |
                v
sherpa-onnx + resident Piper/VITS voice
                |
                v
Cancellable PCM playback queue
                |
                v
USB speaker or USB DAC + amplifier
```

The complete structured response and any accompanying action must pass the existing validation gate before TTS playback begins. After validation, synthesize and queue speech sentence by sentence to reduce perceived delay without allowing unvalidated content to reach the speaker.

### Runtime decisions

- Load the selected voice once when the robot starts; do not reload it for every sentence.
- Generate speech only after the response and any accompanying action have passed validation.
- Split long responses into sentences and begin playback as soon as the first validated sentence is synthesized.
- During playback, set `tts_active=true` and pause STT under our initial half-duplex design.
- Provide immediate playback cancellation, preferably including a physical stop control.
- Maintain a pronunciation dictionary for personal names, medicines, locations, dates, and abbreviations.
- Expose user-controlled voice, volume, speaking rate, and pause duration. The `older_adult_companion` profile should sound clear and calm, not automatically extremely slow or patronizing.
- Do not implement voice cloning in the first version.

### Playback, personalization, and safety

- Use a persistent TTS service or worker and a bounded, cancellable PCM audio queue.
- Resume VAD and STT only after playback stops and a short device-tested cooldown prevents the robot from transcribing its own trailing audio.
- While the initial half-duplex design is active, provide a physical or software playback-stop control because spoken interruption will not be recognized while STT is paused.
- Normalize numbers, dates, times, abbreviations, units, and punctuation before synthesis. Use an allow-listed pronunciation dictionary rather than accepting arbitrary raw phoneme or markup instructions from generated or user-supplied text.
- Adapt pace, volume, and pauses only within tested limits. Do not make exaggerated emotional performances based on uncertain speech-affect estimates.
- Use a neutral adult stock voice. Voice choice and playback settings are preferences, not facts to infer from age or another user characteristic.
- For critical reminders or safety-related messages, present a visual cue where possible and request acknowledgement rather than relying only on synthesized audio.
- A powered USB speaker is the simplest prototype output. A bare loudspeaker requires an appropriate USB audio interface or I2S codec and amplifier; it must not be driven directly from the Jetson.

### Device-level TTS evaluation before freezing

Evaluate candidate voices on the final Jetson, speaker, amplifier, enclosure, room conditions, and target-user population. Measure:

- Time from validated text to first audible audio, median and p95.
- Real-time factor, total synthesis time, underruns, truncation, and playback-cancellation latency.
- Peak shared memory, CPU and GPU use, power, temperature, and throttling.
- Intelligibility and comprehension of names, medicines, numbers, dates, times, units, directions, and action confirmations.
- Pronunciation-error and critical-word error rates.
- Listening effort, comfort, naturalness, warmth, and voice preference, including evaluation with intended older-adult users.
- Quiet and realistic fan, television, household-noise, near-field, and far-field listening conditions.
- User-adjustable rate, volume, and pause settings, including compatibility with hearing aids where applicable.

Freeze the engine version, voice-model hash, configuration, pronunciation dictionary, and licence record together. Maintain a backend interface so the project can compare or replace Piper/VITS with Kokoro without changing the validated response pipeline.

### TTS references

- [sherpa-onnx offline speech runtime and Jetson support](https://github.com/k2-fsa/sherpa-onnx)
- [sherpa-onnx TTS models and documentation](https://k2-fsa.github.io/sherpa/onnx/tts/index.html)
- [Piper/VITS CPU benchmark examples](https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html)
- [Piper `en_US-ljspeech-medium` model](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/ljspeech/medium)
- [Piper `en_US-ljspeech-medium` model card](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/ljspeech/medium/MODEL_CARD)
- [Kokoro-82M model card](https://huggingface.co/hexgrad/Kokoro-82M)
- [sherpa-onnx Kokoro documentation and CPU benchmarks](https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/kokoro.html)
- [NVIDIA Riva support and memory matrix](https://docs.nvidia.com/deeplearning/riva/user-guide/docs/support-matrix/support-matrix.html)
- [NIDCD guidance for communicating with older adults with hearing loss](https://www.nidcd.nih.gov/sites/default/files/hearinglossolderadults-508.pdf)

## Completed routing-overhead experiment — 2026-09-12

The [controlled four-turn experiment](evaluation/routing_overhead_20260912/README.md)
is complete: 12 authored sequences, three timing repetitions, three matched
main systems and a diagnostic adaptive routing-bypass replay produced 144
sequence attempts/576 turns. All 546 delivered responses and 30 technical
failures remain recorded. The earlier post-memory comparison remains a separate
result; its 48-request sessions used different history and cold-start boundaries.

| System | Mean four-turn sequence, s | Fully correct / 144 attempts |
| --- | ---: | ---: |
| Small-only | 20.115 | 66 |
| Large-only | 78.454 | 97 |
| Lightweight adaptive | 65.694 | 77 |
| Diagnostic replay | 57.434 | 77 |

The sequence span includes BGE/prepared-memory/router/Conversation startup,
request latency and intervening measured work. Admission/client initialization,
cleanup and scheduler waits are separate. Adaptive averaged 12.760 seconds
less than large-only, 45.579 seconds more than small-only and 8.261 seconds
more than exact-request replay. Selection recovered its measured costs against
large-only chiefly for EEEE (50.912 seconds saved), while DDEE averaged 5.558
seconds slower than large-only. All nine adaptive DDEE traces exercised the
actual large/large/large/small rule; the final return has no observed following
turn. DDDD used large throughout, so its small timing difference cannot be
attributed to small-model selection. EDED showed variable results.

These measurements do not establish quality–latency dominance or justify an
unconditional policy change. Adaptive gained 11 fully correct answers over
small-only at much greater latency and lost 20 against large-only. Two blinded
assistant contexts agreed on 145/146 output groups; one disagreement was
adjudicated. Human review remains pending. Repetitions and shared workload
forms/profile are dependent. Large-model CPU/GPU allocation, output lengths,
cache/thermal conditions and replay's fixed last position limit attribution.
Replay preserves exact generation requests and shared retrieval/validation but
requires an observed trace, so it remains a diagnostic rather than a policy.

The implementation now records monotonic actual-path selection/classifier,
eviction-request/verified-absence, retrieval, generation, validation and total
request spans with before/after residency. Backend load/prefill/decode durations
are nested diagnostics and never added again. Fixed systems enforce their sole
model for classifiers and answer helpers. All main systems made 93 memory
classifier calls and zero compute classifier calls; replay made zero selection
calls. Settings remained Qwen3 0.6B/1.7B, context 2048, cap 192, temperature 0,
seed 42, thinking disabled and serialized guarded inference.

The initial harness incorrectly treated an ordinary final-turn validation
rejection as fatal. A documented prospective v2 amendment repaired only failure
handling/provenance before continuation. All 88 earlier attempts were reused
unchanged, the original rejected answer remains failed, and none was retried
or completed by splicing. The application, workload, settings, model digests,
guards and measurement boundaries stayed fixed. Offline validation passed
920 tests with 26 skipped (946 total). The
[corrected collection-integrity audit](evaluation/routing_overhead_20260912/final_collection_audit_v2_corrected/summary.json)
passed; the [audit correction record](evaluation/routing_overhead_20260912/final_collection_audit_correction.json)
preserves its predecessor and does not alter collection evidence.

The [reviewed results](evaluation/routing_overhead_20260912/report_reviewed_v2/report.md),
[sequence figure](evaluation/routing_overhead_20260912/report_reviewed_v2/sequence_latency.pdf),
[component figure](evaluation/routing_overhead_20260912/report_reviewed_v2/components.pdf)
and [detailed paired tables](evaluation/routing_overhead_20260912/report_details_final_v2/paired_sequence_components.csv)
are archived with raw traces and reproducible commands. Broader useful-answer
gains, an optimal two-easy threshold, the unobserved fifth turn after a small
return and spoken-interaction performance remain open questions.


## Independent retrieval experiment completed — 2026-09-13

The six-condition comparison is complete: 48 independently reviewed fresh
fictional requests, two fixed generators, three retrieval policies and three
counterbalanced timing repetitions, totaling **864 attempts**. The
[report](evaluation/independent_retrieval_20260913/report_reviewed_v3/report.md)
and [reproducible experiment directory](evaluation/independent_retrieval_20260913/README.md)
preserve all 856 delivered answers and eight failed attempts.

The experiment separates authorization from memory relevance. OFF supplies
no personal evidence; ALWAYS PERMITTED attempts retrieval on every authorized
request; SELECTIVE uses the current memory-need policy. Every condition
retains consent, profile isolation, prohibited-data and lifecycle/freshness
checks. Equivalent prepared snapshots include lifecycle changes before
collection. Fresh request histories and OFF input audits exclude personal
fact leakage. The actual condition model remains fixed for classifiers,
generation, helper rendering and fallbacks. Experimental decoding uses
2048 context, 192 output tokens, temperature 0, seed 42 and no thinking.
These experimental settings do not silently replace prior deployment settings.

Observed implications:

- **0.6B:** SELECTIVE matches ALWAYS's 53/78 known-recall successes, including
  the same mean success on each known question, while reducing unnecessary
  retrieval from 24 to 6. It is slower overall: 2.030 versus 1.941 s per
  request, with 91 versus 93 total task successes. The memory-access reduction
  is supported; a time-saving claim is not.
- **1.7B:** SELECTIVE reduces unnecessary retrieval from 24 to 3 and mean time
  from 10.460 to 9.117 s after selection costs. Known-recall success falls
  from 53/78 to 52/78; overall success rises from 86/144 to 89/144. p95 time
  worsens from 20.657 to 30.457 s. This is an observed mean-time benefit with
  quality and tail-latency costs, not established quality preservation.
- Both retrieval policies remain weak on paraphrases (6/24 successes) and
  uncertainty/conflict handling. OFF has zero known-fact recall successes;
  appropriate caution without evidence is separately reported as missed
  personalization, rather than successful recall.

No blanket deployment change follows from this coverage experiment. Further
work should address paraphrase retrieval/evidence linking, uncertainty and
conflict handling, and sustained residency in a new prospectively frozen
study. No fix or prompt change was introduced into the collected workload to
improve its unfavorable outcomes. Live before/after propagation remains a
separate experiment.

Collection kept original source, model digests, configuration and device
guards unchanged. Eight available-memory-floor stops were preserved once;
each independently approved continuation resumed only an unattempted suffix.
The 18 logical blocks required 26 physical fragments and 35 rejected
zero-request admissions. Each fragment retained its sole model, but sustained
1.7B residency across every uninterrupted block was not achieved. Extra cold
loads, failures and selection costs remain in primary timing. Device placement,
background load and repeated observations limit broader causal claims.

Independent blinded assistants reviewed 159 distinct question/outcome groups;
147 agreed and 12 were adjudicated by a third fresh blinded context. All
judgments were sealed before mapping, and every attempt has verified review
coverage. Human validation remains pending. Paired statistics average three
repetitions per request and resample eight shared fictional scenario clusters;
there is no noninferiority margin or population-equivalence claim.

Validation includes 37 focused pre-collection harness/guard checks, a separate
12/12 live development smoke, 17 continuation checks, and 24 final analysis
tests. Independent final audits passed 99,319 numerical checks and 181 report
checks. The original failed offline audit and renderer attempt are retained.
The [audit-only correction](evaluation/independent_retrieval_20260913/analysis_audit_correction_v1.md)
recognizes an existing helper's 24 evidence-dependent question rewrites;
semantic neutrality is not assumed. Runtime behavior, raw answers, references,
rubrics and statistical rules remained fixed. Earlier development decisions
and evaluation records are preserved.
