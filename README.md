# Oline HRI

Software scaffold for an offline personalized conversational robot running on a
Jetson Orin Nano.

The research concept and system decisions remain documented in
[`README(2).md`](<README(2).md>) and [`developments.MD`](developments.MD).

## Current scope

The current milestone provides the Python 3.10 package, validated JSON
configuration, offline automated tests, and routed terminal conversation
through local Ollama models. The resident `qwen3:0.6b` makes two independent
structured classifications per turn: one singleton request returns
`memory_required`, and another returns `model_size`. Neither decision is
derived from the other. Model output is constrained and validated as:

```json
{
  "speech": "You prefer jasmine tea without sugar.",
  "gesture_id": "NO_ACTION",
  "memory_used": ["mem_0123456789abcdef0123456789abcdef"]
}
```

Of the model output, only validated `speech` is printed to standard output.
Optional route and ID-only diagnostics are written to standard error.
`gesture_id` remains `NO_ACTION` until the later hardware-action milestone.
`memory_used` may contain only unique IDs from the exact verified evidence
supplied for that turn. Request-linked records are required citations; optional
candidates supplied for inspection are not answer authority and cannot be cited
as grounding. Without a high-confidence request link, the
application returns a fixed safe abstention instead of trusting generated
personal claims.

Add `--show-memory-ids` to print privacy-safe, ID-only diagnostics after a
validated reply. They distinguish the ranked records returned by retrieval,
the whole records actually disclosed to the generator, and the model's
validated citations. Memory text, scores, and metadata are never printed by
this diagnostic.

Explicit personal memories can be stored in SQLite, reviewed, corrected as
versioned records, and forgotten by exact ID. FTS5 provides literal keyword
search. The pinned
[`BAAI/bge-small-en-v1.5`](https://huggingface.co/BAAI/bge-small-en-v1.5/tree/5c38ec7c405ec4b44b94cc5a9bb96e735b38267a)
ONNX model also creates normalized 384-dimensional embeddings on the CPU for
exact cosine-similarity search. Deterministic reciprocal-rank fusion combines
the two result lists for inspection and memory-aware chat.

## Local commands

Run these commands from the repository root using the project virtual
environment explicitly:

```bash
PYTHONPATH=src .venv/bin/python -m oline_hri info
PYTHONPATH=src .venv/bin/python -m oline_hri config check
PYTHONPATH=src .venv/bin/python -m oline_hri config show
PYTHONPATH=src .venv/bin/python -m oline_hri chat --prompt "Hello"
PYTHONPATH=src .venv/bin/python -m oline_hri chat
PYTHONPATH=src .venv/bin/python -m oline_hri chat --show-route --show-memory-ids
PYTHONPATH=src .venv/bin/python -m oline_hri memory remember --kind preference
PYTHONPATH=src .venv/bin/python -m oline_hri memory list
PYTHONPATH=src .venv/bin/python -m oline_hri memory search
PYTHONPATH=src .venv/bin/python -m oline_hri memory semantic-search
PYTHONPATH=src .venv/bin/python -m oline_hri memory hybrid-search
PYTHONPATH=src .venv/bin/python -m oline_hri memory rebuild-index
PYTHONPATH=src .venv/bin/python -m oline_hri memory rebuild-embeddings
PYTHONPATH=src .venv/bin/python -m oline_hri memory embedding-status
PYTHONPATH=src .venv/bin/python -m oline_hri memory correct MEMORY_ID
PYTHONPATH=src .venv/bin/python -m oline_hri memory forget MEMORY_ID
PYTHONPATH=src .venv/bin/python -m oline_hri.evaluation validate
PYTHONPATH=src .venv/bin/python -m oline_hri.evaluation prompts --track all
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

To validate another configuration file, put `--config` before the command:

```bash
PYTHONPATH=src .venv/bin/python -m oline_hri --config path/to/config.json config check
```

Memory text is requested interactively so it does not have to appear in shell
history. `--text` is available for fictional test data and automation. The
default plaintext database is `~/.local/share/oline-hri/memory.sqlite3`, with
private directory/file permissions and SQLite secure deletion enabled. This is
not guaranteed erasure from flash media or backups, and SQLite is not encrypted;
do not store real sensitive information until the device and backup storage are
encrypted.

The current development unit was observed using `/dev/mmcblk0` storage with no
visible dm-crypt/LUKS layer, rather than the planned encrypted NVMe baseline.
Use fictional memory data on this unit until that deployment prerequisite is
met.

`memory.profile_id` is a logical data partition, not authentication. Anyone
with access to the local account or database file may read its contents. Do not
store passwords, PINs, payment details, security codes, or unconfirmed model
inferences in ordinary personal memory.

The FTS5 index contains a derived copy of searchable memory text and must be
protected like the authoritative database. Keyword queries are treated as
literal terms joined with `AND` and do not perform synonym matching. Hybrid
search uses lexical and semantic rank positions rather than adding their
incomparable raw scores. Semantic queries accept up to 1,000 characters, while
the stricter lexical leg remains capped at 200 characters and 16 unique terms;
a lexical validation failure degrades to semantic-only retrieval. The Jetson's
SQLite version cannot guarantee forensic erasure of deleted FTS segments,
reinforcing the encrypted-storage requirement.

Ollama is restricted to a loopback URL (`localhost`, `127.0.0.0/8`, or `::1`).
Configuration validation rejects remote hosts, credentials, URL paths, queries,
and fragments. The default HTTP client also disables environment proxies, and
generation failures are sanitized before reaching the CLI, so retrieved
personal records cannot be redirected or echoed through routine error output.
Interactive chat reports a failed turn with one fixed message and remains open;
a failed `chat --prompt` request exits with status `3`.

## Routed chat and hybrid retrieval

Each chat turn follows this sequence:

```text
user text
  |-> qwen3:0.6b memory classifier -> no: skip retrieval
  |                                  `-> yes: FTS5 + BGE -> RRF candidates
  |                                           `-> request-link analysis
  |                                               + required-first packing
  `-> qwen3:0.6b size classifier   -> small or large generator

selected evidence + compute result -> selected generator
```

The two decisions produce this exact matrix:

| Personal memory | Compute route | Retrieval | Generator |
| --- | --- | --- | --- |
| No | Small | Skipped | `qwen3:0.6b` |
| Yes | Small | FTS5 + BGE + RRF | `qwen3:0.6b` |
| No | Large | Skipped | `qwen3:4b` |
| Yes | Large | FTS5 + BGE + RRF | `qwen3:4b` |

Each classifier returns only its singleton field; malformed or truncated
routing output fails closed without a heuristic fallback. Routing uses greedy
decoding (`temperature=0`) with seed `42`, independently of the generator's
conversational temperature. The four small/large and memory/no-memory
combinations are tested independently. Configuration rejects model names that
would collapse or change these planned routes.

Memory need and model size are separate classifications: personal recall does
not imply a large model, and a complex general plan does not imply memory.
Evidence cardinality is also independent of model size. Direct recall uses the
best-supported request-linked record or tied records. Explicit multi-fact or
synthesis wording may disclose the bounded candidate set, with linked records
first; optional candidates remain ineligible for citation. A simple multi-fact
recall can therefore use several required records with the small generator.
Self-contained requests are classified without unrelated session history;
bounded prior turns are included only when the current request explicitly
refers back to them. This prevents a greeting from turning a later general
architecture question into a memory request.

For an interactive cascade test, add `--show-route`. After the resident 0.6B
classifier returns a validated decision and before retrieval or answer
generation begins, the CLI writes a diagnostic such as this to standard error:

```text
route> model_size=large selected_generator=qwen3:4b memory_required=false
```

The diagnostic deliberately omits the prompt and retrieved memory text. Normal
chat output is unchanged when the flag is absent.

After a successful turn, `--show-memory-ids` writes a second diagnostic to
standard error:

```text
memory> {"retrieved_ids":["mem_000000000000000000000000000000a1"],"supplied_ids":["mem_000000000000000000000000000000a1"],"model_used_ids":["mem_000000000000000000000000000000a1"]}
```

`retrieved_ids` shows the raw ranked candidates returned by retrieval,
`supplied_ids` shows the budget-fitting whole records actually disclosed to the
generator in required-first order, and `model_used_ids` shows the exact
validated request-linked citations. Thus an optional supplied ID can be absent
from `model_used_ids`; it is not authorized as answer grounding. Fields are
emitted in fixed order, and each list preserves its pipeline order. The values
are opaque but can still be correlated with local records, so diagnostic logs
should be protected like other local application metadata.

### Serialized model lifecycle

The CLI shares one `OllamaClient` between the router and both generators. That
client holds one lock across each complete peer-unload and chat transaction, so
two application conversations cannot switch or generate concurrently through
the shared client.

| Requested model | Before generation | Ollama `keep_alive` | State after success |
| --- | --- | ---: | --- |
| `qwen3:0.6b` | Unload 4B when startup state is unknown or 4B was active | `-1` | 0.6B remains resident |
| `qwen3:4b` | Unload 0.6B and wait for acknowledgement | `0` | 4B unloads immediately |

Consecutive router-to-small-generator calls reuse the resident 0.6B model
without redundant unloading. After a large route, the next router request
reloads 0.6B; it is not synchronously preloaded after the answer. Failed or
interrupted operations make the cached residency unknown, forcing a
conservative peer unload on the next call. Unload requests contain only the
model name and lifecycle fields—never prompts, history, or retrieved memory.

This guarantee covers calls using the one shared application client. A separate
Ollama frontend, direct API caller, or another `OllamaClient` can bypass its
lock, so do not run competing model clients on the deployment service.

### Timeout and fallback policy

Configuration schema 4 separates local Ollama socket timeouts by workload:
unload requests use 30 seconds, router and small-model requests use 60 seconds,
and large-model requests use 300 seconds. These are failure budgets, not latency
targets.

Only one failure has a generation fallback: if a routed `qwen3:4b` request times
out, the application makes exactly one `qwen3:0.6b` attempt with the same prompt,
history, response schema, and memory-ID allowlist. The reply records
`fallback_from_model="qwen3:4b"` while its generation metadata identifies the
small model. A router timeout, selected-small timeout, retrieval/freshness
failure, HTTP or protocol error, truncation, wrong model metadata, malformed
JSON, or response-contract violation never triggers a fallback. A failed
fallback aborts the turn without adding partial output to history.

For a memory-grounded fallback, the same authoritative memory snapshot is
checked before the large attempt, again before disclosing it to the fallback,
and once more after generation. Ollama HTTP bodies are read with a 64 KiB cap;
route JSON is capped at 512 characters and robot-response JSON at 16,384
characters before parsing. Transport, router, retrieval, and freshness errors
cross public boundaries only as fixed application-authored messages.

Hybrid retrieval takes at most 20 candidates from each index, deduplicates by
authoritative memory ID, and uses equal-weight reciprocal-rank fusion with
`k=60`. Exact lexical results win an otherwise exact fusion tie so names and
dates are not displaced. Retrieval returns at most three ranked records to the
conversation layer. A deterministic request-link heuristic uses lexical stems,
explicit names and labels, preference cues, and temporal cues to identify
high-confidence required evidence independently of the small/large route. A
direct recall keeps the best-supported linked record (preserving tied records
so detectable conflicts are not hidden). Explicit multi-fact, multi-question,
"all," or synthesis wording keeps all linked records required and may also
supply the remaining bounded retrieval candidates for inspection.

Required records are reordered before optional candidates and packed as whole
records. Context pressure can drop only optional tail records; if all required
records cannot fit, the turn fails before generation. All required IDs must be
cited. An optional candidate must not be cited, even though the model
was allowed to inspect it. When no candidate has a high-confidence request
link, the application discards generated prose and returns exactly `I do not
have a verified personal memory that answers that.` This conservative rule also
covers an unlinked answer with empty or optional-only citations. Any empty
`memory_used` is first replaced with the fixed abstention; if linked evidence
exists, the subsequent required-citation gate rejects that response. Incomplete
linked citations likewise fail validation rather than silently accepting the
answer.

This request-link analysis is deliberately best-effort, not a calibrated
semantic-relevance test. In particular, a genuinely relevant candidate found
only through semantic similarity can lack the lexical or temporal anchors
needed to become required, causing a conservative abstention. No raw
BM25/cosine addition or uncalibrated cosine threshold is used.

Retrieved records and the current request are placed in one bounded,
application-created user-role JSON envelope. Memory text is explicitly treated
as factual data rather than an instruction and can never authorize an action.
The model-facing copy rewrites bare `User` and `User's`, as well as `the user`
and `the user's`, to second person (`you`/`your`) and adjusts supported verb
agreement, without changing stored memory. Instructions require human-user
facts to use `you`/`your`, never literal `the user` or robot `I`/`my`; the
validator rejects common violations. Direct-recall and transformation or
planning requests have distinct instructions, so a one-record planning request
is not reduced to verbatim recall. Audit timestamps and record-kind metadata
are not disclosed to generation; an explicit event time is included only when
the record actually has one. Times, dates, names, and relationships may come
from either the current request or cited memory, but not from elsewhere.
Neither the envelope nor any memory-requested answer is kept in reusable model
history—even when retrieval found no record—so unsupported or stale personal
claims cannot become session facts. A later personal follow-up must retrieve
current records again. Non-memory history is capped at the newest three complete
turns and 2,000 characters, and the memory envelope is capped at 3,000
characters. An aggregate
conservative prompt estimate also reserves the configured output tokens plus a
safety margin within `num_ctx`; overflow drops only complete oldest history
turns or whole lowest-ranked records, and an input that still cannot fit is
rejected before generation. Chat turns are serialized within a conversation.

The database snapshot is checked immediately before disclosure and again after
generation. A corrected, forgotten, expired, cross-profile, or otherwise
changed record causes the turn to be rejected without committing it to history.
The response validator independently rejects invented, duplicate, malformed,
or non-supplied `memory_used` IDs, and forbids memory IDs in user-facing speech.
Every request-linked required record must be cited, and optional candidates
cannot be cited. Best-effort validators then check that each cited record's
distinctive literal anchors are covered and that a temporal recall includes its
stored weekday, daypart, clock, and date details. They reject common human/robot
perspective swaps; detectable negation of a positive personal relationship,
general preference, or temporal preference; unsupported personal names or
relationships; and unsupported temporal
precision from outside the current request or cited memory. A cited preference
for exactly three steps is enforced as three recognizable numbered or ordinal
steps. Detectable conflicting short-label records with shared fact anchors
require an uncertainty statement.

These checks use conservative token and regular-expression heuristics. They do
not understand every paraphrase, contradiction, relationship, or temporal
association, and they do not prove general factual completeness or semantic
correctness. Records without a safely detectable literal anchor are not rejected
merely for paraphrasing; blinded semantic review remains necessary.

Complex general, no-memory requests use a separate JSON request envelope with
an adjacent compact completion rule. The current rule tells the 4B generator to
answer now rather than refuse because the runtime is offline or merely announce
what it could do: speech is capped at 75 words, compares exactly three
architectures in compact clauses, gives one recommendation, and ends with
exactly three short deployment steps. This architecture-shaped rule is tuned to
the current regression case; it is not a general semantic proof for arbitrary
planning requests.

Install both configured local generators before routed chat:

```bash
ollama pull qwen3:0.6b
ollama pull qwen3:4b
ollama list
```

The development Jetson was verified with Ollama `0.33.3`, `qwen3:0.6b`
digest `7df6b6e09427a769808717c0a93cadc4ae99ed4eb8bf5ca557c90846becea435`
(Q4_K_M, 522 MB), and `qwen3:4b` digest
`359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`
(Q4_K_M, 2.5 GB). Tags can change upstream, so record and re-verify these
digests before collecting reproducible evaluation results.

### Qwen3-4B Jetson benchmark

A controlled non-thinking benchmark of the installed `qwen3:4b` Q4_K_M model
used a 2,048-token context, a 64-token output cap, temperature `0`, and seed
`42`. The unloaded cold run took 113.99 seconds wall time, including a
72.88-second load; its generation phase produced 64 tokens at 2.45 tokens/s.
Three resident warm repeats had a median wall time of 43.89 seconds and a
median generation rate of 1.49 tokens/s.

During the cold run, `tegrastats` reported approximately 7.0/7.62 GB RAM use
and full 3.81/3.81 GB swap. The model runs on this development unit, but it is
not a low-latency default under the current memory pressure. This measurement
motivated the provisional 300-second large-request failure budget; it does not
make 4B a low-latency route. The capped responses also exposed an
instruction-following limitation, so runtime success is not an answer-quality
result. See the
[full reproducible Qwen3-4B benchmark](benchmarks/qwen3_4b_jetson.md).

## Fictional seven-day evaluation suite

Step 15 adds the versioned
[`fictional_seven_day_v1.json`](evaluation/fictional_seven_day_v1.json)
fixture and a strict local validation, replay, and prompt-emission harness. The
case study is fully synthetic: Mira, Theo, Luma, and every event are invented.
It contains no human-participant data, is not a user study, and cannot support
claims about real users or generalizable system quality.

The fixture covers one controlled Monday-to-Sunday timeline with:

- 15 ordered memory events: 13 remembers, one correction, and one forget;
- 14 deterministic memory-record versions;
- three policy-withheld topics that contain explanations but no private values;
  and
- 30 author-gold cases spanning all four combinations of memory/no-memory and
  small/large model routing.

Cases exercise direct recall, correction, forgetting, expiration, temporal
reasoning, absence, sensitive-but-confirmed memory, prohibited storage, and
unresolved contradiction. They also compare older and newer milestones and
test that unconfirmed third-party data and affect inference remain absent.
Their annotation status is
`author_gold_pending_independent_review`; independent review is still required
before reported evaluation results use these labels.

Validate the manifest or emit stable JSON Lines from the repository root:

```bash
PYTHONPATH=src .venv/bin/python -m oline_hri.evaluation validate
PYTHONPATH=src .venv/bin/python -m oline_hri.evaluation prompts --track all
PYTHONPATH=src .venv/bin/python -m oline_hri.evaluation prompts --track router
PYTHONPATH=src .venv/bin/python -m oline_hri.evaluation prompts --track rag
```

These commands validate or emit prompts; they do not call Ollama, score model
answers, or produce latency, token, RAM, swap, thermal, power, or routing
accuracy measurements. See the
[`evaluation` documentation](evaluation/README.md) for the replay and gold-data
contract.

## Historical Step 16 objective evaluation (pre-redesign)

The 2026-09-07 benchmark runner executed the real local embedding, hybrid
retrieval, routing, and answer paths. It compared 30 stateless cases across four
strategies: always-small without RAG, always-large without RAG, always-large
with bounded RAG, and the adaptive cascade. The
[frozen protocol](evaluation/step16_protocol.md) defines the settings,
denominators, measurement scope, and limitations before answer inspection.

Each run preserves raw observations, objective scores, a blinded answer-review
sheet, model/source/asset provenance, and Jetson telemetry. The offline merger
checks the four bundles' provenance and keeps the first strategy's component
retrieval pass as the predeclared source. See
[run and merge instructions](evaluation/README.md#historical-step-16-run-and-merge-pre-redesign).
Choose an owner-controlled persistent directory through `OLINE_HRI_RUN_ROOT`;
`/tmp` artifacts were lost when this Jetson rebooted during evaluation. Raw
bundles and generated dated reports can contain prompts, answers, provenance,
and device telemetry, so they are intentionally ignored and not versioned.

All four 30-case baselines completed with 120/120 valid structured turns,
zero errors, and zero fallbacks. Their provenance matched and the offline
merge completed. The adaptive run used 4B for 18/30 answers; memory and model
decisions matched the author labels on 25/30 and 19/30 cases respectively.
Its median/p95 turn latency was 82.996/126.007 s. These routing and timing
measurements do not establish answer correctness or compute savings.

These 2026-09-07 Step 16 artifacts predate the routing and grounded-generation
fixes documented above. Their aggregate historical figures are retained here,
but the private raw artifacts and generated report are local-only and must be
rerun before those metrics are attributed to the current implementation. The
separate router-only supplement remains unpooled with the adaptive run. An
unclean reboot interrupted an earlier attempt; the original trigger remains
unknown.

Collection and objective scoring are complete, but full Step 16 interpretation
remains provisional while the fixture labels await independent review and
natural-language answer quality awaits blinded human review. The current unit
runs in 15W mode on
`/dev/mmcblk0`, so storage measurements describe SD-card activity. Final NVMe,
microphone, speaker, actuation, and physical offline-disconnection measurements
remain deferred.

## Offline embedding model

Embedding inference uses ONNX Runtime's `CPUExecutionProvider` with two worker
threads. It does not use Ollama, PyTorch, a cloud API, CUDA, or TensorRT. Stored
memory text is embedded as-is; only search queries receive BGE's retrieval
instruction. Vectors are normalized `float32` values and searched exhaustively
in memory—there is no FAISS or separate vector service.

The runtime dependencies are pinned in `setup.cfg`. Model assets are stored
outside Git at the configured private local directory:

```text
~/.local/share/oline-hri/models/bge-small-en-v1.5/
  5c38ec7c405ec4b44b94cc5a9bb96e735b38267a/
```

Provisioning is the only step that needs internet access. From the repository
root, install the pinned dependencies and download only the three required
files from the immutable model revision:

```bash
.venv/bin/python -m pip install --editable .
.venv/bin/hf download BAAI/bge-small-en-v1.5 \
  config.json tokenizer.json onnx/model.onnx \
  --revision 5c38ec7c405ec4b44b94cc5a9bb96e735b38267a \
  --local-dir ~/.local/share/oline-hri/models/bge-small-en-v1.5/5c38ec7c405ec4b44b94cc5a9bb96e735b38267a
chmod -R go-rwx \
  ~/.local/share/oline-hri/models/bge-small-en-v1.5/5c38ec7c405ec4b44b94cc5a9bb96e735b38267a
```

The application never downloads model files at runtime. It refuses to load the
bundle unless all three SHA-256 hashes match:

| Asset | SHA-256 |
| --- | --- |
| `config.json` | `094f8e891b932f2000c92cfc663bac4c62069f5d8af5b5278c4306aef3084750` |
| `tokenizer.json` | `d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66` |
| `onnx/model.onnx` | `828e1496d7fabb79cfa4dcd84fa38625c0d3d21da474a00f08db0f559940cf35` |

The pinned model revision is licensed MIT. Embeddings are sensitive derived
personal data, not anonymized data, and receive the same profile, consent,
validity, retention, correction, deletion, and storage protections as their
authoritative memory records. Semantic scores are used only for relative
ranking; this milestone deliberately applies no uncalibrated score threshold.

To exercise the real local assets rather than the deterministic unit-test
embedder, run the opt-in Jetson smoke test:

```bash
OLINE_HRI_RUN_LIVE_EMBEDDING=1 PYTHONPATH=src \
  .venv/bin/python -m unittest tests.test_embedding_live -v
```

To exercise all four real Qwen routing decisions, self-contained requests after
unrelated greeting history, exact and paraphrased personal recall, large
planning paraphrases, and temporary fictional small-model RAG/non-RAG turns,
run:

```bash
OLINE_HRI_RUN_LIVE_ROUTING=1 PYTHONPATH=src \
  .venv/bin/python -m unittest tests.test_routed_chat_live -v
```

That routing suite verifies the four decisions and recall paraphrases without
requiring every large-route case to generate a full 4B answer.

To run semantic answer-quality regressions, including the exact formerly
failing prompts through the real router, retriever, and generator, run:

```bash
OLINE_HRI_RUN_LIVE_QUALITY=1 PYTHONPATH=src \
  .venv/bin/python -m unittest tests.test_chat_quality_live -v
```

The quality suite creates an isolated temporary database and keeps exactly
these three fictional regression memories:

- Theo is the user's fictional robotics project partner.
- The user prefers robotics project meetings on Tuesday mornings.
- The user prefers project plans containing exactly three concise steps.

Its acceptance cases are:

- `"Hello there!"`, followed in the same conversation by `"Compare three
  offline robot architectures, reason through their tradeoffs, and create a
  detailed deployment plan."` -> `false/large`, with a substantive answer and
  no offline/physical-action refusal;
- `"Who is Theo to me?"` -> `true/small`, answering that Theo is your robotics
  project partner;
- `"What is my preferred meeting time for the robotics project?"` ->
  `true/small`, answering Tuesday mornings without invented clock or date
  precision; and
- `"Using what you remember about Theo, my robotics-project meeting schedule,
  and my preferred project-plan format, create a plan for our next meeting."`
  -> `true/large`, using/citing all three memories and producing exactly three
  concise actionable steps.

The live suites also cover the documented recall and planning paraphrases.

It also checks second-person perspective and rejects unsupported names or
relationships. It never reads or writes the configured personal-memory
database. Full 4B generations unload after each call on this setup, so the
suite can take several minutes.

### Post-fix validation

The post-fix verification completed on 2026-09-08:

| Verification | Result |
| --- | --- |
| Full automated discovery | 420 tests, `OK` (`skipped=19`) |
| Full real-routing suite | 7 tests, `OK` in 21.163 seconds |
| Full live answer-quality suite | 9 tests, `OK` in 677.452 seconds |
| Exact end-to-end failed-prompt subset | 4/4 passed (included in the quality suite) |

To exercise the real small -> large -> small lifecycle with short generations
and verify `/api/ps` after every transition, run:

```bash
OLINE_HRI_RUN_LIVE_LIFECYCLE=1 PYTHONPATH=src \
  .venv/bin/python -m unittest tests.test_ollama_lifecycle_live -v
```

This test performs a cold 4B load and can take several minutes. Its cleanup
unloads both configured models even when an assertion fails.

The lifecycle test intentionally does not generate a full 4B answer. The
separate live-quality suite does exercise complete 4B architecture and
multi-memory planning answers; device measurements are documented in the
[Qwen3-4B Jetson benchmark](benchmarks/qwen3_4b_jetson.md).
