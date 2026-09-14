# Withheld appointment answers and retained-history exposure

Prepared 14 September 2026 by `/root/runtime_audit`. This is **unblinded assistant
diagnostic review; human validation pending**, not a revision of blinded answer
scores. The original A/B batch 05 judgments were frozen before this inspection;
their hashes match the [receipt](review_receipts/batch_05.json). The six cm09/cm10
branch seals were checked against 260 files. No active later branch was read,
no inference ran, no runtime source changed, and no diagnostics were sent to the
blinded reviewers. The final all-288 collection audit is still required.

The [evidence companion](withheld_appointment_diagnostics_v1_evidence.json)
preserves the exact questions/rubrics, raw answers, actual supplied records,
freshness checks, temporal-token comparisons, all 30 retained-history witnesses,
source paths and hashes. All 41 frozen runtime source hashes remain unchanged.

## Four supported raw answers were withheld for correction-time metadata

All four checkpoints have `status=withheld`, `delivered_answer=null`, and the
same `ResponseValidationError`: `robot response omits requested temporal memory
detail`. Each routed to memory and the large model, retrieved the active
replacement, supplied it to real `qwen3:1.7b` generation, cited its authorized
selector, and passed two freshness checks. Generation completed; the subsequent
temporal-coverage validator rejected its answer. The v2 analysis parser recovers
the actual envelope after its prose prefix, so none of these cases should be
diagnosed as missing supplied evidence.

The exact cm09 questions were:

- `cm09_correction_corrected_fresh`: “Earlier I told you about my pottery
  appointment on 2026-10-03. What start time is currently recorded?”
- `cm09_correction_restart_fresh`: “Returning to my earlier pottery appointment,
  what is its recorded start time on 2026-10-03 now?”

Both raw answers say:

> Your pottery appointment is on 2026-10-03 at 11:30.

The supplied canonical text is exactly that sentence. The
[initial trace](run_v2/cm09_correction/initial/answers.jsonl), line 5, and
[restart trace](run_v2/cm09_correction/restart/answers.jsonl), line 2, both cite
the current record `mem_9f74e737c09a4cb483c1f2224290c1b9`; the actual model-facing
selector is `memory_ref_1`. The frozen rubric requires: “Give the requested
value, 11:30, clearly and directly.” The old 09:00 value and the unrelated
historical control are forbidden.

The exact cm10 questions were:

- `cm10_correction_corrected_fresh`: “Earlier I told you about my bicycle fitting
  appointment on 2026-10-04. What start time is currently recorded?”
- `cm10_correction_restart_fresh`: “Returning to my earlier bicycle fitting
  appointment, what is its recorded start time on 2026-10-04 now?”

The first raw answer says:

> Your bicycle fitting appointment is on 2026-10-04 at 16:45.

The restart raw answer says:

> The recorded start time of your bicycle fitting appointment is 2026-10-04 at 16:45.

Both use the supplied canonical fact `Your bicycle fitting appointment is on
2026-10-04 at 16:45.` and cite `mem_7f9b12be62d447e098388b47ce5c6bd2`
through `memory_ref_1`. See the
[initial continuation trace](run_v2/cm10_correction/initial_continuation_02/answers.jsonl),
line 5, and [restart trace](run_v2/cm10_correction/restart/answers.jsonl), line 2.
The rubric requires: “Give the requested value, 16:45, clearly and directly.”
The former 14:15 value and unrelated historical control are forbidden. The
initial physical continuation remains part of provenance; this diagnosis does
not relabel it as the original initial worker.

Each actual supplied envelope also contains:

```json
{"correction_effective_time":"Thursday, 2026-10-01T12:01:00.000000Z"}
```

This is when the correction operation took effect, not the appointment's start
time. In the frozen [conversation source](frozen_v1/source/src/oline_hri/conversation.py),
`_require_cited_memory_coverage` at line 2056 adds correction-effective temporal
claims to the required coverage for temporal questions. It then requires the
speech to contain their union with the canonical appointment claims.
`_correction_effective_time` at line 2788 constructs that metadata from the
replacement's `valid_from` value.

A read-only comparison using those frozen helper functions gives:

| Cases | Canonical appointment date/time missing from raw speech | Additional validator demands missing from raw speech |
| --- | --- | --- |
| Both cm09 cases | None: date 2026-10-03 and time 11:30 are present | Thursday; date 2026-10-01; month/day 10-01; time 12:01 |
| Both cm10 cases | None: date 2026-10-04 and time 16:45 are present | Thursday; date 2026-10-01; month/day 10-01; time 12:01 |

The helper's metadata-clock exception is false for all four questions. The
recorded error thus follows from demanding unrelated correction-operation
metadata, not from omission of the requested start time, an expired record, an
old value, an unknown selector or incomplete transport.

There are two distinct judgments here. First, the validator's stated rejection
is unnecessary for the frozen task: none of the four questions asks when the
database correction happened. Second, my unblinded raw-answer assessment is that
all four answers are useful under these particular rubrics. Each gives the
required replacement time and repeats the appointment/date already identified
in the question. The date is not a newly introduced personal detail or a date
from an unrelated historical control. The wording adds no unsupported or
unrequested new personal fact. This assessment does not assume that every
supported canonical detail is always requested; answers to other questions may
still be partial for adding unrelated dates or details.

None of these four examples demonstrates justified rejection of an answer that
omitted the required start time. That conclusion is limited to these inspected
raw answers. Their actual delivered outcomes remain **four withheld answers,
zero useful delivered responses**. They disclose nothing at the delivery
boundary, but this safe withholding is not successful recall or a useful
delivered uncertainty response.

## Stored history and actual generation exposure differ

The following counts cover all 15 retained-history scored questions in each
scenario, including pre-store, original-recall and historical-control questions.
They are not a subset success rate.

| Scenario | Retained questions | Exact original statement present | Exact original statement forwarded | Literal old value present | Literal old value forwarded | Memory requested | Memory skipped |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cm09: old time 09:00 | 15 | 12 | 8 | 13 | 9 | 5 | 10 |
| cm10: old time 14:15 | 15 | 12 | 6 | 12 | 6 | 5 | 10 |

Forwarding is witnessed by intersecting `history_before` with actual generation
messages by exact role/content, excluding system messages, the current request
and evidence tail. Literal old-value matching is a lower-bound exposure measure;
alternate time formatting or paraphrases can escape it. It does not establish
semantic absence, disclosure authorization or correctness of the delivered
answer.

The five memory-requested retained questions in each scenario are the pre-store
question, the original correction/deletion recalls, and the two independent
historical-control questions in correction. They use the retrieval path; the
original statement is not forwarded to generation in those turns. All ten
other retained questions in each scenario have a recorded memory classifier
output `form=request, memory_required=false` and no retrieval call. The actual
generation models include both 0.6B and 1.7B. These are trace observations, not a
claim that model size causes a particular answer.

Three examples show why the exposure distinctions matter:

- In `cm10_correction_restart_retained`, original 14:15 is actually forwarded,
  routing skips memory, and the 1.7B generator delivers the old time even though
  the database replacement is 16:45. See
  [correction restart answers](run_v2/cm10_correction/restart/answers.jsonl),
  line 1. The trace supports a history bypass; it does not show the retriever
  returning the superseded record, because retrieval never ran.
- In `cm09_deletion_restart_historical_retained`, the exact original user
  statement is already absent. A later assistant echo containing 09:00 is still
  present and forwarded: history index 6 matches generation message index 4.
  See [deletion restart answers](run_v2/cm09_deletion/restart/answers.jsonl),
  line 3. This particular delivered answer expresses unavailability. Exposure
  therefore does not imply disclosure, and checking only the original user
  statement would undercount stale-history exposure.
- In `cm10_deletion_restart_retained`, the original statement remains in
  `history_before` but neither it nor its literal old value appears in the
  forwarded history. See
  [deletion restart answers](run_v2/cm10_deletion/restart/answers.jsonl), line 1.
  Production builds a separately bounded generation history with the remaining
  prompt budget (conversation source, lines 955–964). By the next retained
  historical question, the original statement and literal old value are absent
  even from stored history. Session retention is not identical to generator
  exposure at every checkpoint.

The routed-without-memory appointment turns do not all disclose stale values.
Several return unavailability despite old-value exposure. In both scenarios,
unavailability also occurs immediately before expiry while the original fact is
still authorized. An appropriate uncertainty answer after expiry therefore
does not alone establish that its generation consulted the expiry state. The
actual retrieval and freshness traces, plus the independent expected state,
are needed to explain the stage behavior. These descriptive observations leave
all frozen answer judgments unchanged and support no causal claim about history
length, model size or a repair that was not run.
