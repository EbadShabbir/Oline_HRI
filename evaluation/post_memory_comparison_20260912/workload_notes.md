# Fresh complete-system pilot workload

Prepared on 12 September 2026 before any inference on these requests. The
authoritative data are in `workload.json`. The parent experiment must freeze
the execution source, model artifacts, session schedule and resource policy
before collecting outputs.

This is an **assistant-authored fresh pilot, with independent human review
pending**. It is not a public benchmark, an independent evaluation, or a
confirmatory test of superiority. Prior pilot failure modes informed the
coverage of memory tasks. The author also participated in earlier development,
so different wording and facts do not remove evaluator/developer dependence.
No outputs on these 48 items were used to select, remove or revise them. Do not
tune the implementation to individual items after freezing and then describe
the resulting scores as untouched test performance.

## Coverage

| Stratum | Requests | Coverage |
| --- | ---: | --- |
| Routine general | 12 | Four ordinary definitions/functions, four supplied-data or rule/string tasks, four arithmetic/time tasks |
| General with multiple constraints | 12 | Feasible selection, parallel dependencies, exhaustive small code lists, filtering/sorting, exact purchases, travel timing, packing, conditional exceptions, corrected statistics, and source consistency |
| Personal recall | 12 | Naming, roles, a format preference, corrected collection arrangements, forgotten/expired/unknown facts, unresolved conflicting times, object placement, inventory, an operational preference and a wrong-owner control |
| Personal temporal/synthesis | 12 | Cross-midnight ordering and elapsed time, protected resource allocation, schedule feasibility, preference-based selection, conflict consequences, mixed known/unknown recall, a waiting rule, equipment pairing, a due-date errand, missing travel duration and filename construction |

The routine-general mix was broadened during the before-output design review:
the four ordinary knowledge items are `s3_r04`, `s3_r06`, `s3_r10`, `s3_r11`;
supplied-data/rule/string items are `s3_r01`, `s3_r02`, `s3_r05`, `s3_r09`;
arithmetic/time items are `s3_r03`, `s3_r07`, `s3_r08`, `s3_r12`. This was a
coverage decision made without router testing or model outputs, not a response
to observed winners. Definitions concern common, stable, nonmedical concepts.
All numerical multi-constraint tasks supply their necessary data.

There are 41 scenario labels, including 24 separate self-contained general
scenarios. This supplies more than 12 distinct scenario groups, but **41 labels
are not 41 proven independent statistical units**. Personal tasks share one
fictional profile and some facts across scenarios: for example the sound
archive, library, map session and photo-processing timeline each recur. Even
different labels can share a setting or task form. Report this clustering and
the 48 distinct requests; repeated runs do not create additional independent
quality samples.

The task forms were varied beyond replacing names and numbers: examples
include exhaustive valid codes, a cross-midnight process with separate start
and finish records, a protected water reserve, and identifying a known
appointment while declining an unknown departure time. Familiar arithmetic
and scheduling forms remain familiar; no training-contamination claim follows
from freshly written prose.

## Fixed sequence and sessions

The literal `execution_cases` order is authoritative and identical for every
arm and repetition. It was constructed using `random.Random(20260912)`: shuffle
the twelve items within each stratum, then for each of six blocks shuffle the
four stratum names and pop one item per stratum. These first 24 requests mix
the strata. Append the six remaining routine-general items, then six personal
recall items, six general multi-constraint items, and six personal-synthesis
items. The second half therefore includes consecutive runs of related task
types alongside the alternating first half.

These are strata, not predetermined router choices or measured difficulty
labels. The mixed and clustered portions were chosen to exercise serial model
residency patterns, but the workload does not force a particular route. Their
items differ, so a within-run comparison of the two portions cannot isolate
the causal effect of request ordering.

The workload records three planned repetitions with arm orders
small/large/cascade, large/cascade/small, and cascade/small/large: 432 planned
attempts. Any collection-schedule change must be documented before its
affected outputs are collected. Each request starts a fresh Conversation;
model residency continues naturally within a session. Report actual attempts,
validated delivery, interrupted sessions and unattempted slots separately.

## Fictional memory snapshot

The profile is `fictional_tideglass_post_memory_v1`. The evaluation clock is
**3 October 2026 at 20:00 UTC**, distinct from real device time, and retention
is seven days. Records are created from 29 September through 3 October, so all
supported records remain within retention. Upcoming bookings after the
evaluation clock are confirmed future facts, not future observations.

There are **30 chronological setup operations: 28 remembers, one correction,
and one forgetting operation**. They create 29 distinct record IDs; the
expected currently retrievable set has 26 IDs. The other three created IDs
are superseded, forgotten and expired respectively. `list_memories()` alone
is not an eligibility oracle: an expired record may remain physically active
while failing the retrieval snapshot check.

| Control | Setup and expected handling |
| --- | --- |
| Correction | Library pickup changes from the lobby shelf to the side-window desk. Only the replacement supports the current answer. |
| Forgetting | The spare transit-card location is forgotten before evaluation. Never disclose the striped-notebook location, even as historical or negated information. |
| Expiry | Equipment locker 17 expires on 2 October at 18:00. Its current number is unknown. |
| Conflict | Separate current records give 14:00 and 15:00 for the same 5 October map session. Their creation order is not a correction. Both must be considered. |
| Unknown | The user’s audiobook-language preference and home-to-repair tram duration were never stored. |
| Wrong owner | The upper-deck river-ferry ticket belongs to Dalia. It does not establish the user’s ticket assignment. |
| Mixed support | Book pickup can be answered while the locker number is unknown; the repair appointment can be stated while exact departure remains unknowable. |

The atlas due date is a date-only fact; no artificial midnight deadline is
added. All hypothetical travel, allocation and handling requests describe
possible actions and do not mutate the snapshot. Answering one item does not
consume water, loan equipment or advance the fictional clock for another.

Setup uses the existing `materialize_seed` helper and real `MemoryStore`
lifecycle APIs with deterministic IDs. An offline replay in a temporary
database, with `embedder=None`, validated all 30 operations and the exact 26-ID
eligible set using `retrieval_snapshot_is_current`. It also checked the
correction chain, removal of forgotten content, exclusion of expired locker
content, current pickup keyword retrieval and retention of both conflicting
session records. No model or embedding call was made. This checks setup and
lifecycle eligibility, not semantic candidate recall or quality.

Every correction, forgetting and expiry transition precedes all requests.
Consequently this is a **static lifecycle-snapshot test**. It cannot demonstrate
live memory-update propagation, automatic capture quality, concurrent-change
safety, forgetting from conversation history, or voice/STT/TTS behavior.

## Rubric and review boundary

Execution cases contain only `id`, `stratum`, `scenario_id`, and `prompt`.
Only the prompt belongs in the user-message path. Reference answers, expected
memory IDs, scenario labels, rubric text and expected-state metadata must not
be supplied to the router or generator. Memories are seeded through the
ordinary memory store, not handed to every request as the full database.

Each rubric retains the existing schema: `mode`, `reference_answer`,
`required_claims`, `forbidden_claims`, `required_memory_ids`,
`forbidden_memory_ids`, and `automated_checks`. There are **42 supported,
4 abstain and 2 uncertain** items. Mixed supported/unknown items have mode
`supported`, with both parts explicitly required. The reference is an example,
not an exact-match answer string.

For complete-answer correctness, all substantive requested claims must be
correct, the relevant constraint must be satisfied, and forbidden assertions
must be absent. Concise equivalent wording, unambiguous equivalent clock
formats and units, and mathematically equivalent feasible solutions are
acceptable. A fact clearly conveyed by the proposed solution need not be
repeated in a separate sentence. Optional explanatory detail in a reference
is not an extra requirement; several rubric entries state this explicitly.
For the crate task, any four positive integer occupancies summing to 22, each
at most six, are accepted. For the code-list task, both valid codes and no
invalid codes are required. Filename capitalization may vary, but the
specified date, order and separator structure must remain correct.

Appropriate abstention counts as correct only for the matching unavailable
fact. A blanket refusal fails an answerable request; answering just the known
half of a mixed request is incomplete. Conflict handling must identify both
stored possibilities without arbitrarily choosing one. A timeout, invalid
response or interrupted generation is not a delivered correct answer.

Grounding is judged against evidence actually supplied to the answer, not
merely evidence known to the rubric author. Record factual correctness,
retrieval coverage, supplied evidence, citations, unsupported personal claims
and delivery failures separately. A correct-looking guess cannot establish
grounded personal recall, and valid JSON/citations do not establish correct
reasoning. The current forbidden ticket ID is a wrong-owner control, not a
stale record; the reason for its exclusion must remain distinguishable.

Automated checks are lexical signals only. One routine distinct-tag-count
item has an auxiliary numeral/word signal; the other 47 have empty lexical
check lists and require semantic review. Empty lists mean no lexical test was
defined, not successful validation. Numeric presence, negation and role
binding are not semantic proof, so no lexical rate may be reported as
accuracy. Review actual outputs with system identities concealed where
feasible, preserve judgments and rationales, and clearly label any assistant
grading as assistant-assessed. Independent human review remains pending.

Report quality and measured latency/calls/loading/resources together for the
specified frozen models, hardware and complete pipelines. There is no new
quality or responsiveness cutoff in this pilot, no assumption of globally
optimized single-model controls, and no rule requiring the cascade to win.
The earlier pilot and benchmark results remain unchanged historical evidence.
