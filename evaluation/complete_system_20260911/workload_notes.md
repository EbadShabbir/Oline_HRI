# Complete text-system pilot: workload and scoring

Prepared on 11 September 2026 before inference on these requests. The frozen
workload is `workload.json`, SHA256
`5ac0f9f8c160862e0a14a2162e6bda0d61a3cdf6045ed31e844f63f93996542c`.
Execution and device policy are specified in `protocol.md`. The author-written
references have status `author_gold_pending_independent_review`.

## Scope and sampling

This is a new application-specific pilot for the complete text-request path.
It complements the separate public ARC capability experiment; it is not a
public benchmark, a representative sample of household requests, or the final
120-item test proposed in the draft evaluation protocol. The prompts and
fictional memories were authored without inspecting outputs on these items.
Generic task forms such as arithmetic and scheduling are familiar; new wording
and facts do not establish absence of model training contamination.

| Stratum | Cases | What the references require |
| --- | ---: | --- |
| Routine general | 12 | Self-contained arithmetic, conversion, reading, or ordering |
| General with multiple constraints | 12 | Satisfy all stated constraints, often with an explicit calculation or schedule |
| Personal recall | 12 | Recall current facts or appropriately handle correction, expiration, forgetting, conflict, and unknown information |
| Personal temporal/synthesis | 12 | Combine up to three stored facts, event times, or a stored fact with explicit new constraints |

The stratum labels describe task requirements, not an oracle choice of model.
No item requires a large-model win, and no case is selected or removed based on
model performance. Some tasks within a stratum can be easy. Arithmetic prompts
supply all necessary constants and avoid external factual lookup.

The explicit `execution_cases` order is authoritative. It was constructed with
Python `random.Random(20260911)`: shuffle each stratum, then shuffle the four
stratum positions separately for each of 12 blocks. Every four-request block
contains one request from each stratum. All systems and repetitions use that
same order. The sequence is a balanced alternating workload; a second grouped
sequence is outside this pilot.

Three repetitions use arm orders small/large/cascade, large/cascade/small, and
cascade/small/large, for 432 planned attempts. There are 48 distinct requests,
not 144 independent quality samples per system. Related personal questions
share scenarios and one fictional profile. Even differently named scenario
groups can share facts, such as lunch, schedules, and workshop supplies. These
dependencies limit population inference; case counts are descriptive and do
not establish an independent-scenario success guarantee.

## Frozen fictional memory snapshot

The new profile is `fictional_solstice_stage2_v1`. Every timestamp is UTC.
`evaluation_at` is **20 September 2026, 18:00 UTC** and retention is seven days.
This deliberately synthetic clock is separate from the device's real date.
All supported memories were created from 14–18 September and remain within
retention at the evaluation clock. Stored upcoming events can occur after the
clock; their records are still current confirmed information.

The seed contains 27 chronologically ordered operations: 25 remembers, one
correction producing a replacement memory, and one forgetting operation. The
expected current eligible set contains 23 memories. Eligibility is distinct
from relevance or appearance in a query's three retrieved candidates.

| Control | Setup | Required response behavior |
| --- | --- | --- |
| Corrected preference | Lunch grain changes from couscous to bulgur on 17 September | Use bulgur as current; do not assert the old preference as current |
| Expired fact | The west-counter banner location expires on 16 September at 18:00 | Acknowledge that the current location is unknown |
| Forgotten fact | The attic-drawer pencilcase location is forgotten on 19 September | Do not disclose that location; acknowledge missing information |
| Unresolved conflict | Separate current records name Cedar Hall and Juniper Hall for the same demonstration | Explain the conflict and avoid choosing a definite room |
| Never recorded | No favourite train station exists in the seed | Acknowledge that the preference is unknown |
| Mixed support | A request asks for current lunch grain and current banner location | Answer the supported grain part and identify the unknown location |

The two hall assertions are both active and are not a correction chain. Their
different creation times do not make the later assertion a confirmed
replacement. The event-time questions concern completed trials, a submitted
form, and upcoming appointments. In particular, collection on 21 September
at 09:30 precedes rehearsal on 22 September at 16:00 by **30 hours 30 minutes**.
Form submission on 16 September at 12:00 precedes the lampshade trial on
18 September at 14:00 by **50 hours**.

Materialize a new database for each arm/session with `MemoryStore`, the fixed
profile, a mutable replay clock, `retention_days=7`, and the event-provided
deterministic memory IDs. For `remember`, pass the canonical text, kind,
`source_turn_id=event.id`, and any event/validity timestamps. For `correct`,
call `correct(target_id, canonical_text)` and verify the new ID. For `forget`,
call `forget(target_id)`. Freeze the store's clock at `evaluation_at` after
all events. Use the same configured embedding/retrieval implementation for
every session. The ID list, operations, and expected-state metadata permit
offline lifecycle auditing without extracting gold from the generated answers.

All changes happen before requests. Every request uses a fresh Conversation
with no previous user or assistant turns. Model residency continues normally
within the 48-request session. Therefore this is a lifecycle **snapshot**
evaluation: it does not test live correction propagation, forgetting from
conversation history, concurrent changes, restart effects, automatic memory
extraction, or spoken interaction.

## Rubric and execution boundary

The JSON deliberately separates `execution_cases` from `rubrics`. Each
execution case contains only `id`, `stratum`, `scenario_id`, and `prompt`.
Only `prompt` enters the user-message path. IDs, categories, reference answers,
memory-ID gold, and checks must not enter model, router, or retrieval prompts.
The seed itself is provided through the real memory system, not inserted as
the complete database in every prompt.

Each rubric has these fields:

| Field | Meaning |
| --- | --- |
| `mode` | `supported`, `abstain`, or `uncertain` |
| `reference_answer` | One acceptable answer; equivalent concise wording is allowed |
| `required_claims` | Every listed claim must be conveyed correctly for complete-answer correctness |
| `forbidden_claims` | Assertions or disclosures that must not occur |
| `required_memory_ids` | Current evidence needed for the requested personal claims |
| `forbidden_memory_ids` | Corrected, expired, or forgotten evidence that must not support the current answer |
| `automated_checks` | Optional lexical signals for triage, never a semantic score |

There are 43 supported, three abstain, and two uncertain rubrics. The supported
mode includes one mixed known/unknown item; its rubric requires both parts.
No length or exact-wording penalty applies unless the prompt explicitly asks
for it. The stored preference for short project answers is a common system
input; stylistic length alone is not a factual correctness error in this pilot.

A complete correct answer must satisfy every required claim, avoid all
forbidden claims, and introduce no unsupported factual assertion. A correct
abstention says the requested personal fact is unavailable without guessing.
An uncertainty answer identifies the conflicting possibilities and does not
present either as established. A blanket refusal or empty response does not
satisfy an otherwise answerable case. A partially answered multi-part request
is not completely correct. Reasonable paraphrases, equivalent units, and
equivalent 12-hour/24-hour clock expressions are acceptable when unambiguous.

Assess delivered content, evidence retrieval, supplied evidence, citation
validity, and transport/validation outcomes separately. A textually correct
answer can still have an evidence or citation failure. Conversely, valid
citations and JSON do not prove the content correct. A timeout or safety
interruption is an unavailable answer, not an accurate, responsive answer.
Preserve failed attempts rather than replacing them with selective retries.

For `automated_checks`, use case-insensitive regex search. Each
`required_groups` entry is satisfied lexically if any of its `any` patterns
appears; `forbidden_presence_patterns` detects candidate mentions for review.
These signals deliberately cover only some rubric claims. They do not verify
negation, numerical role, chronology, contradiction, entailment, or whether a
name is asserted rather than rejected. An empty required-group list means
**no lexical check was defined**, not that the answer passed. A negated stale
value may trigger a presence flag without violating the current-state rubric;
the forgotten-location disclosure rule is separately explicit. Record check
coverage and flags, and preserve the text for semantic review.

Prepare system-blinded review records that include case prompt, rubric,
necessary fictional evidence, and delivered response, with a separate private
mapping to system and repetition. Blinding reduces exposure to arm labels but
cannot guarantee an assessor cannot infer the source. If an assistant reviews
the records, label the result **assistant-assessed** and retain the individual
judgments and explanations. Do not call it independently human reviewed.
Independent human adjudication remains pending before any final quality claim.

## Interpretation

Report accuracy only at the stated review status and denominator, alongside
category outcomes, paired disagreements, abstention/conflict behavior, model
calls, helpers, retrieval, loading, latency, and resource use. Repetitions
measure variability; they do not create more independent tasks. Exact check
rates must be labeled as lexical signal rates, never substituted for accuracy.
There is no accepted pass/fail quality or responsiveness threshold in this
pilot, so do not retrofit one to favor a system.

This workload compares the current complete systems under the common frozen
protocol. It neither proves each baseline is globally optimized nor isolates
generator choice from differences in memory classification and evidence.
Application-authored helpers may supply some content, so distinguish their
outputs from unconstrained model reasoning. If a single-model system performs
better, retain that result. Equal quality with additional cascade overhead
does not establish a benefit from using two generators.
