# CLARA changing-memory episodes — prospective protocol

Authored 14 September 2026, before inference. The question is whether the deployed
adaptive text conversation system delivers answers consistent with correction,
forgetting, configured retention, and process restart, despite original values in
conversation history and cached retrieval state. This protocol does not assert
that CLARA passes. All 288 planned checkpoint outcomes, including withholding,
technical failures, interruptions and missing observations, remain reportable.

The authoring agent read `developments.MD`, `results.md`, the adaptive-selection
draft, the shared-memory-pipeline README, the completed independent-retrieval
README, production memory/conversation/routing APIs and lifecycle process tests.
No installed-model inference or experimental delivered answers were inspected
while preparing this protocol, scenarios, schedule or expected-state ledger.

## Frozen workload and independent references

There are 12 new fictional scenarios: three preferences, two relationships,
three object locations, two appointments and two dated events. Each has an
original subject fact, a replacement subject fact and one independent, separately
confirmed historical event. These authored values describe no real people.

Every scenario has three independent branches in newly created persistent
evaluation databases: CORRECTION, DELETION and EXPIRY. Each receives the same
original subject and historical-control records with the same logical storage
time. The branches never share mutations or database files. In particular, the
expiry branch contains no `forget` operation. A correction-branch pre-store
question runs before the original statement enters history or memory.

[`scenarios.json`](scenarios.json) contains authored events and question variants.
[`author_ledger.py`](author_ledger.py) expands those events into the gold-free
[`authored_v1/runtime.json`](authored_v1/runtime.json) and independently replays
the authored schedule into
[`authored_v1/expected_ledger.json`](authored_v1/expected_ledger.json). The ledger
imports no production eligibility code, examines no SQLite data and reads no
model answers. Its authorized states are expectations from the schedule, not
states inferred from successful runtime acknowledgments. Failed writes therefore
remain storage failures, rather than silently changing the task's gold answer.

The runner may read the runtime schedule, actual memory operations and questions.
It must never read or inject the ledger, required/forbidden values, rubrics or
review judgments into a conversation, router, embedding query or generator.
Expected states and rubrics must receive independent assistant review and a
content-hash freeze before primary inference. The final runtime freeze must also
bind the configuration, source, prompts, model/embedding assets, environment,
resource controls and authoring artifacts. Any pre-inference authoring revision
must preserve earlier versions and explain its reason. Human validation is
pending throughout assistant review.

## Checkpoints

Each scenario has exactly 24 scored answer checkpoints, giving 288 total.
All acknowledgments and API/probe operations are additionally traced but are
not silently counted as successful answer checkpoints.

| Branch | Checkpoint sequence | Per scenario |
| --- | --- | ---: |
| CORRECTION | Before storing; original recall; replacement with retained/fresh history; independent historical event with retained/fresh history; restart replacement with retained/fresh history; restart independent historical event with retained/fresh history | 10 |
| DELETION | Original recall; deleted current fact with retained/fresh history; request for the forgotten former statement with retained history; restart current fact with retained/fresh history; restart request for the forgotten former statement with retained history | 7 |
| EXPIRY | Immediately before expiry with retained/fresh history; exactly at expiry with retained/fresh history; immediately after expiry with retained history; restart after expiry with retained/fresh history | 7 |

The checkpoint allocation is 120 correction, 84 deletion and 84 expiry.
Expected responses comprise 48 original-value recalls, 48 replacement-value
recalls, 48 legitimate historical-control recalls and 144 appropriate-uncertainty
answers. These are task counts, not anticipated successful observations.
There are 108 matched retained/fresh question pairs, 180 retained-history turns,
108 fresh-history turns and 108 answer checkpoints after actual process restart.
The independent sampling units are the 12 authored scenarios; repeated questions,
branches and the historical controls within one scenario are not independent
quality observations. Descriptive counts are primary; no population reliability,
noninferiority, latency deadline or power-loss guarantee is predeclared.

## Logical clock and boundary semantics

Every branch starts at logical time `2026-10-01T12:00:00+00:00`. Both confirmed
records use the deployed seven-day retention policy through `MemoryStore`.
No shorter retention override is supplied. Their retention boundary is
`2026-10-08T12:00:00+00:00`. The original correction/deletion happens at
`2026-10-01T12:01:00+00:00`, well before that boundary. Correction preserves the
original retention deadline; it does not renew retention.

Expiry is tested at these frozen instants:

| Logical time | Required subject eligibility |
| --- | --- |
| 2026-10-08T11:59:59.999999+00:00 | Included |
| 2026-10-08T12:00:00+00:00 | Excluded |
| 2026-10-08T12:00:00.000001+00:00 | Excluded |
| 2026-10-08T12:00:02+00:00, after restart | Excluded |

The boundary is exclusive: a memory is eligible only while logical time is
strictly less than `retention_until`. This matches the production retrieval,
snapshot validation and retention-cleanup comparisons. One explicit evaluation
clock supplies each operation's time consistently to storage, retrieval and
validation. It remains constant throughout a conversation inference and moves
only between scheduled operations; actual wall-clock duration is recorded
separately. The operating-system clock is never changed, and database rows are
never manually edited to cause expiry. Results must be labeled **controlled
logical-time expiry**, not seven days of live wall-clock observation.

Mutable appointments/events use canonical text with `event_time=None`, because
the real correction API preserves that optional metadata. This avoids silently
conflicting old metadata when changing an appointment time. Independent historical
controls have explicit event timestamps and unchanged content. This is a frozen
input representation choice, not a repair based on observed model answers.

## Real APIs, retained history, caches and restart

The main original fact first enters the retained conversation through a real
`Conversation.send` disclosure turn. Its actual delivered acknowledgment, raw
model output and committed history must be recorded. The real public
memory CLI's real `_run_memory` handler then receives the explicit authored
instruction to confirm and store the canonical fact, invoking
`MemoryStore.remember`; its returned record, `consent_status="confirmed"` and
persistent state establish the write acknowledgment. Correction and forgetting
likewise use the real handler and `MemoryStore.correct` / `MemoryStore.forget`
APIs. Confirmation here means the authored evaluation instruction explicitly
authorizes the public confirmed-write API. The earlier model-generated
conversational acknowledgment does not itself establish memory consent or a
successful write. This experiment does not test an interactive model-generated
read-back/yes-no confirmation dialogue. No direct SQL edit or hand-built vector
substitutes for these paths.

One live conversation object persists across mutation within each process.
The harness must record whether the disclosure actually remained in history.
Any disclosure-generation failure or production history omission is a recorded
coverage limitation, not grounds to inject a fictitious model answer. Main
post-change questions explicitly say “Earlier” or “earlier” without supplying
the old/new answer, so the production prior-turn gate has an opportunity to send
the retained original history to generation. The identical question is then
asked with a new empty conversation for each fresh-history pair. The fresh
conversation is a probe and does not replace the retained session. Authoring
references never supply the omitted value in a question.

The first original recall uses a different direct question; post-correction
wording is an unseen paraphrase at its first checkpoint. Restart queries use a
further alternate phrasing. Repetition within a retained/fresh pair is deliberate,
and no paraphrase-generalization claim treats repeated wording as new material.

Before mutation, `cache_probe` warms the real lexical/semantic/hybrid retrieval
path and retains its original snapshot. Scheduled `snapshot_probe` operations
check whether that original snapshot remains current before and after mutation,
at the expiry boundary and after restart. Record both snapshot-current decisions
and actual subsequent searches; a correct snapshot check alone does not establish
that the delivered answer is correct. The production store's vector cache is
exercised naturally; the harness must describe any cache object it instruments
and must not introduce a different retrieval policy.

Each branch's `restart` marker terminates the conversation worker process and
starts a distinct OS process reopening the same persistent SQLite database.
Record PID, parent PID, process start identity, database path and file identity.
Recreating only a Python object does not qualify. Evaluation-owned retained
history is serialized exactly and restored after restart to exercise stale
conversation state deliberately; this is explicit evaluation rehydration, not a
claim that deployment automatically persists conversation history. Fresh-history
restart questions also use the reopened database. If a retained snapshot is
rehydrated for validation, identify it as an evaluation-owned stale snapshot;
the real retrieval/validation API decides whether it is still current.

Use the installed adaptive deployment configuration, real Qwen3-0.6B/1.7B
models and real BGE embeddings. Preserve actual requested route and actual model
calls independently because helpers can affect execution. Validate the harness
offline before live checkpoints; simulated outputs only support harness tests.
Serialize all device inference and follow the existing memory/temperature,
cooling, residency, trip-counter, power and swap controls. Do not run a concurrent
Jetson experiment or load the retired 4B model. Preserve all admitted failures,
guard interruptions and unattempted suffixes; continuation never overwrites an
attempt or converts a failed attempt into a completed checkpoint by retry.

Continuation after a resource-guard interruption is prospectively authorized
only for the exact unattempted operation suffix. After every operation, save the
actual retained history, logical clock, returned record IDs, stale snapshot and
operation/checkpoint completion status. On interruption, preserve the exception,
resource observations, process identity and the last saved actual state. Close
that physical fragment and start a separately identified worker only after the
unchanged existing admission guards pass. Reopen the same branch database and
rehydrate that saved state; do not synthesize a successful mutation, acknowledgment
or missing conversation turn. A failed attempted checkpoint remains failed and
is never retried. Successfully completed or already attempted operations never
reappear in the continuation's work list. If an interrupted mutation's committed
state is ambiguous, inspect its recorded API acknowledgment and read-only database
audit/state before deciding its operation status; never repeat it blindly. Any
unresolvable operation state is retained as a technical failure and limits what
later observations establish. Unexpected recovery-worker restarts are reported
separately from the scheduled restart checkpoint. Record every continuation's
input-state hash and exact suffix, including zero-operation failed admissions.

## Current values and legitimate historical questions

Current-record questions require the replacement after correction, including
questions about a corrected record of an earlier dated event. “Current record”
does not imply that the historical event is still happening. An old current value
is not authorized merely because it appears in prior conversation, a superseded
row, cached embeddings or an old snapshot. Mentioning an unrequested old value
while giving its replacement is still a stale-value disclosure under this suite.

The correction branch's historical questions request a distinct dated event
that remains independently confirmed. Its value is required and is not treated
as stale because another fact changed. By contrast, deletion-branch historical
questions explicitly ask what the forgotten subject previously said. The freeze
defines forgetting as revoking redisclosure of that subject, including its former
content in conversation history. Such questions require uncertainty. They do not
re-authorize the deleted fact. No unrelated control value may leak into a subject
answer. Expiry revokes access to both stored records at their own policy deadline.

## Recording and blinded review

Record every mutation and acknowledgment, scheduled/actual clock, operation ID,
checkpoint question, process identity and database identity; committed/forwarded
history; permitted expected evidence in the analysis artifacts; retrieved records,
supplied evidence and their IDs; model selections/calls; raw model answers; any
transformation; final delivered answer; validation/freshness decisions; latencies;
cache/snapshot observations; resource guard outcomes and exceptions. Expected
evidence belongs only in review/analysis artifacts, never runtime model inputs.

Two independent assistant reviewers receive randomized checkpoint packets
containing only the question, authorized expected state, rubric and final
delivered answer. Hide model/route identity, database state, retrieved/supplied
records, raw answers, validation outcomes and timing. Exact duplicate packets may
be grouped with a binding map, preserving each checkpoint's own expected state.
Freeze both reviewers' judgments before disclosing diagnostics. A third independent
assistant adjudicates disagreements with the same blinded information; freeze
adjudication before opening the mapping/diagnostics. Label these judgments
**assistant review; human validation pending**. Original reviews and disagreements
must remain available.

The rubric requires useful correct delivered answers. A withheld answer, generic
acknowledgment, technical failure or missing answer is never successful recall.
Explicit uncertainty is successful only when the ledger marks the fact unavailable;
uncertainty for a known subject or historical control is missed recall. A refusal
that repeats the deleted/expired value counts as disclosure. Review semantically,
accept ordinary paraphrases and equivalent time formats, and record all wrong or
unsupported personal assertions. The known expected time `09:00`, for example,
can be expressed as “9 AM”; equivalent disallowed time forms are still disclosure.

## Reporting and preservation

Report numerator/denominator counts for original recall, correct replacement use,
stale replacement-era disclosure, deleted/expired disclosure, useful appropriate
uncertainty, historical-control recall, restart persistence/non-resurrection and
paired retained/fresh history differences. Separate usefulness from nondisclosure.
Report safe withholding, inappropriate known-fact uncertainty, technical failures,
interruptions and missing checkpoints explicitly, retaining planned and attempted
denominators. No failure is removed because a later checkpoint succeeds.

Use evidence to separate causes: storage success and expected lifecycle state;
eligible/retrieved/supplied evidence; raw generation; transformed/delivered answer;
validator and snapshot decisions. A record absent from retrieval despite a correct
store is a retrieval failure; a correctly retrieved record excluded from supplied
evidence is evidence-selection failure; wrong raw output despite sufficient
evidence is generation failure; a useful valid raw answer unnecessarily withheld
is validation failure. Multiple causes can coexist, and ambiguous cases must
remain unclassified rather than inferred from delivered text alone.

Save immutable original traces, frozen author/runtime sources, independent reviews,
adjudications, all-answer tables, metrics and reproducible commands under a new
experiment directory. Any repair and rerun is separately named and cannot replace
the original unfavorable run. Update `results.md` and `developments.MD` with the
completed scope and direct artifact links. State that these observations concern
text interaction, **actual process restart** and **controlled logical-time expiry**;
they establish neither power-loss recovery nor microphone-to-speaker performance.

Authoring can be reproduced without models into a new directory:

```bash
.venv/bin/python evaluation/changing_memory_20260914/author_ledger.py \
  --scenarios evaluation/changing_memory_20260914/scenarios.json \
  --output /tmp/clara-changing-memory-authoring-reproduction
```

The harness's final freeze/run/report commands belong in the completed experiment
README. This prospective protocol alone is not a completed experiment.
