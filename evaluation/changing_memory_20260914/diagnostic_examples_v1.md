# Diagnostic examples from sealed cm01–cm04 branches

Prepared 14 September 2026 by `/root/runtime_audit`, acting as an integrity and
diagnostics auditor, not a blinded answer reviewer. Scope: the 12 completed,
sealed correction/deletion/expiry branches for cm01–cm04 only. Before inspecting
diagnostics, I verified the four original A/B review files against the hashes in
the [batch 01 receipt](review_receipts/batch_01.json) and
[batch 02 receipt](review_receipts/batch_02.json), including their read-only modes
and recorded freeze-before-diagnostics status. All 529 files in these branch
manifests and all 41 frozen source files matched their hashes. No inference or
runtime changes were performed. These selected examples are not full-run
metrics or a replacement for frozen blinded judgments. **Assistant diagnostic
review; human validation pending.**

The [frozen expected-state ledger](frozen_v1/expected_ledger.json) requires
replacement values after correction and appropriate uncertainty after deletion
or at/after expiry. Its rubric disallows unsupported extra personal details.
All generator calls discussed below used the installed `qwen3:0.6b`. Line
numbers below are one-based JSONL lines; checkpoint and operation IDs provide
stable search keys.

## Correction: a committed replacement bypassed through retained history

At logical `2026-10-01T12:01:01+00:00`, checkpoint
`cm01_correction_corrected_retained` asked:

> Earlier I told you about my tea preference. Which tea do I prefer now?

The required value was jasmine. The delivered answer was:

> Your preferred tea is rooibos tea.

The real correction acknowledgment at operation `cm01_correction_op07` says
`text: Your preferred tea is jasmine tea.` Its database snapshot marks the
rooibos record superseded and the replacement active; the following original
snapshot probe returns `snapshot_current=false`. See
[mutation events](run_v2/cm01_correction/initial/events.jsonl), lines 105 and 107.

The [answer trace](run_v2/cm01_correction/initial/answers.jsonl), line 4, records
`memory_required=false`, an empty `retrieval_calls` list and no supplied records.
The actual generation messages include both the original user statement and its
assistant acknowledgment. Raw output repeats rooibos with `memory_used=[]`;
validation accepts it and the same speech is delivered. The replacement remains
active before and after the query.

This is a routing/history bypass followed by generation and validation allowing
a stale answer. Retrieval did not run, so this checkpoint does not demonstrate
a retriever returning the superseded record. Nor did the correction fail to
commit. After actual worker restart, retained-history checkpoint
`cm01_correction_restart_retained` repeats the same stale answer with retrieval
again skipped: [restart answers](run_v2/cm01_correction/restart/answers.jsonl),
line 1. Process identity changes from PID 16975/start ticks 407234 to
17156/412783 while database device/inode remains 45825/3283550. This is answer
resurrection from retained state despite a persistent corrected database.

The matched fresh-history correction query does retrieve the active replacement,
but its answer adds an unsupported restriction; it must not be treated as a fully
correct delivered answer merely because it includes jasmine. That separate
generation failure is described below.

## Deletion: the record is absent while the answer discloses it

At operation `cm01_deletion_op06`, the real forgetting API acknowledges
`removed 1 revision(s)`. The after-mutation database contains only the unrelated
historical control. The original snapshot is rejected. See
[deletion events](run_v2/cm01_deletion/initial/events.jsonl), lines 74 and 76.

One logical second later, `cm01_deletion_deleted_retained` asks the same current
tea question and delivers `Your preferred tea is rooibos tea.` The record is
already absent in both database snapshots. Routing says memory is not required;
retrieval is skipped. Actual generation messages contain the original statement
and acknowledgment, and validation accepts the uncited raw answer. See
[deletion answers](run_v2/cm01_deletion/initial/answers.jsonl), line 3.

In the matched fresh-history query, line 4, routing requests memory. Retrieval
returns only the unrelated historical control; evidence selection supplies no
personal records. The delivered answer is `I do not have a verified personal
memory that answers that.` The raw answer had a first-person wording problem;
the production application replaces it with this fixed uncertainty response.
Thus the useful safe result belongs to the delivered system, not solely to raw
generation. The absent subject is not a retrieval failure: absence is required
by the frozen deletion state.

Deletion also fails to prevent retained-history disclosure after restart:
[restart continuation answers](run_v2/cm01_deletion/restart_continuation_02/answers.jsonl),
line 1. The source remains the retained conversation, while the database still
contains only the control. This scheduled restart segment required a separately
recorded continuation; that recovery must remain visible in full-run reporting.

## Expiry: exclusion and purge succeed while retained history still discloses

The cm01 expiry branch contains no forgetting or correction. Its original
snapshot is current one microsecond before the seven-day boundary and rejected
exactly at `2026-10-08T12:00:00+00:00`:
[expiry events](run_v2/cm01_expiry/initial/events.jsonl), lines 43 and 103.

At that exact boundary, `cm01_expiry_at_retained` delivers the expired rooibos
fact. Routing skips retrieval and the generation request includes the original
statement plus earlier assistant echoes. Validation accepts the uncited answer.
The persisted rows still have `status=active`, but their deadline equals the
logical time, so they are already ineligible under the frozen exclusive
boundary. Physical row presence alone is not eligibility. See
[expiry answers](run_v2/cm01_expiry/initial/answers.jsonl), line 4.

The following fresh-history query at the same logical instant requests memory,
retrieves no records and delivers appropriate uncertainty (line 5). Production
retention cleanup removes both records, recorded at events line 150. The next
retained-history query, one microsecond after expiry, still delivers rooibos even
though both its before/after database snapshots are empty (answers line 6).
The failure therefore persists after real purge; it cannot be explained as an
expired row being selected by retrieval. Original-snapshot validation after
purge also remains false (events line 162).

The retained answer repeats after restart at logical `12:00:02`:
[restart continuation answers](run_v2/cm01_expiry/restart_continuation_02/answers.jsonl),
line 1. These observations concern controlled logical-time expiry and worker
process restart; they do not establish power-loss or wall-clock aging behavior.

## Unnecessary withholding: the current walking partner was fully supported

Checkpoint `cm04_correction_restart_fresh` asks:

> Returning to my earlier walking partner information, who is my current walking partner?

The ledger requires Niko Fern. The database has an active confirmed record
`Your walking partner is Niko Fern.`, valid after the correction and before its
retention deadline. The former Elora Vale record is superseded. Routing requests
memory, retrieval returns the Niko record and a historical control, and evidence
selection supplies only the Niko record. Both recorded freshness checks return
true. See [restart answer trace](run_v2/cm04_correction/restart/answers.jsonl),
line 2, especially `retrieval_calls`, `snapshot_checks`, `calls[2].messages`, and
trace spans `answer_generation` and `validation`.

The actual supplied envelope contains the Niko canonical text and correction
effective time. The raw model output says:

> Your current walking partner is Niko Fern.

It cites the authorized selector `memory_ref_1`; the backend translates that
selector to the actual Niko memory ID before application validation. The
[recorded HTTP exchange](run_v2/cm04_correction/restart/http.jsonl) and
`backend_chat` trace preserve the original selector and raw bytes. This is not an
unknown-selector, stale-evidence, missing-citation or unsupported-name answer.
No delivered answer is produced: status is `withheld`, `delivered_answer=null`,
and validation reports `robot response lacks evidence for the requested
collaborator`.

The cause is visible in the frozen
[conversation validator](frozen_v1/source/src/oline_hri/conversation.py):
`_require_requested_named_collaborator` at line 2138 calls
`_collaborator_request_link` at line 2267. That helper requires all topic terms
from the requested role qualifiers to occur in the canonical text. Here,
`current walking` produces `{'current', 'walk'}`, while the record produces
`{'fern', 'niko', 'partner', 'walk'}`. The word `current` fails this literal
subset check even though the record's current eligibility was independently
verified. A read-only call to this frozen pure function returned false for the
actual strings and true when only `current` was removed from the question. No
model was called and no source was changed in that diagnostic check.

The supported raw response was therefore withheld unnecessarily by this
validator. It is safe in the narrow sense that no answer was delivered, but it
is neither successful recall nor a successful delivered uncertainty response.
The failure belongs to validation, not storage, retrieval or raw generation.

One tracing caveat matters: the convenience field
`supplied_evidence_envelopes` is empty in this row, and `supplied_records` is
absent on the rejected-response path. The actual generation message nevertheless
contains the envelope after a prose prefix. The frozen runner's extractor at
[line 258](frozen_v1/source/scripts/run_changing_memory.py) only recognizes a
message starting with `PERSONAL_MEMORY_DATA=`. For this case, use the preserved
generation/HTTP messages as the evidence source. An empty convenience field
must not be interpreted as absence of supplied evidence. A separately labeled
analysis parser amendment will preserve the frozen runner and original traces.

## Unsupported additions and prompt examples are separate from memory recall

At `cm01_correction_corrected_fresh`, the real supplied canonical text is only
`Your preferred tea is jasmine tea.` Raw and delivered speech add `without
sugar`. The frozen rubric forbids unsupported personal details, so replacement
value presence is insufficient for a fully correct answer. Retrieval selected
the current record; generation added the restriction and validation accepted
it. See [initial correction answers](run_v2/cm01_correction/initial/answers.jsonl),
line 5. The actual generation request contains a production demonstration using
`jasmine tea without sugar`; this is a plausible prompt source for the addition,
not proof of a causal model mechanism.

The fresh restart correction query also says `jasmine tea without sugar`, but
has no retained conversation, no retrieval call and no supplied records:
[restart answers](run_v2/cm01_correction/restart/answers.jsonl), line 2.
The same production example appears in its system prompt. The fresh restart
deletion query produces the identical unsupported personal claim even though
jasmine was never stored in that independent deletion branch:
[deletion restart answers](run_v2/cm01_deletion/restart_continuation_02/answers.jsonl),
line 2. The trace does not establish cross-database cache leakage. It establishes
an unsupported answer on a route that skipped memory, with matching example
content already visible in the current prompt. Report it accordingly rather
than inferring persistence or correct recall from answer-text overlap.

These examples distinguish four mechanisms: committed mutation with history
bypass; correct exclusion/purge with later conversation disclosure; unsupported
extra generation accepted by validation; and fully supported generation
unnecessarily rejected by validation. Final rates still require all planned
checkpoints, frozen blinded judgments and the complete sealed-run audit.
