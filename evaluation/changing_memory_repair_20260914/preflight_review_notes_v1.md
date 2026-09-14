# Independent repair preflight notes

Reviewer: assistant `/root/lifecycle_fix_validation_plan`. This assistant did
not implement production changes or run inference. It prepared the targeted
schedule/tooling copies and therefore discloses that authoring role. The original
expected states and rubrics were authored and independently reviewed before the
baseline inference by other assistants; this review verified exact JSON-value
equality for all 96 selected checkpoints and all 12 branch operation schedules.
The assistant inspected baseline diagnostics to select this regression subset.
This is not held-out validation. Independent human validation is pending.

The final machine-readable approval is `preflight_review_v1.json`. These notes
alone do not approve a runtime freeze: exact source hashes and final offline-test
evidence must be bound in that approval before inference.

## Code and experiment review

Compared with the sealed baseline, the repair changes `conversation.py`,
`grounded_composition.py`, `memory_evidence.py`, `relationships.py`,
`routing.py` and `evaluation_scoring.py`. Configuration, model/embedding settings, resource controls and the
collection harness are unchanged. The original baseline artifacts remain sealed.

- Routing no longer treats a visible prior personal answer as authorization.
  Explicit personal recall requires memory even when history is present; raw
  classifier outputs and independent compute decisions remain recorded. An
  offline policy-only check covered all 96 authored questions with their assigned
  history modes and found no memory-policy bypass. This is not a live accuracy
  result.
- Conversation history remains in the retained session and is available to
  routing to identify context. Personal generation receives the current query
  and freshly authorized evidence without old history values. Snapshot validation
  still runs before and after generation. An unavailable requested fact receives
  the existing fixed uncertainty response at delivery.
- Preference-containing generator examples were removed. This avoids supplying
  that particular unsupported example value; it does not establish that every
  possible model-generated personal hallucination is prevented.
- Evidence parsing adds plural locations and bounded explicit prior-memory
  preambles. Subject, owner, attribute and date checks remain. Multi-clause,
  conditional and unrelated-subject counterexamples are tested; no fixture IDs or
  named expected values are introduced into the parsing policy.
- Location composition copies one positively stated requested location only
  after subject/date linkage, and rejects conflicting, ambiguous, conditional or
  unsupported cases. Event-time suffixes may be omitted only after the request
  identifies the date. Answer constraints and validation remain visible in the
  trace; this is application-constrained delivered behavior, not unconstrained
  model reasoning.
- The generic evaluation trace validator recognizes `verified_location` only
  with one supplied/cited record, retaining its existing retrieval, privacy,
  response-shape and citation checks. A positive trace and missing/extra-evidence
  counterexamples cover this small integration addition.
- Current relationship phrasing may omit the word current when present-tense
  identity and full meaningful role remain. Former, previous and past status,
  wrong people, missing role qualifiers and negation remain rejected.
- Correction timestamps are supplied and validated only for an explicit question
  about the correction time. Ordinary corrected appointment questions use the
  supported event content. Regressions cover explicit change chronology and
  incidental mentions of changes while asking a different event's time.

The unchanged harness uses 12 separate new DB paths, the real confirmed memory
CLI/API handlers, installed embedding and conversation paths, and an explicit
shared injected clock. Strict expiry at equality is preserved. Expiry branches
contain neither correction nor forgetting operations. Twelve restart markers
produce distinct worker subprocesses reopening the same DB inode and restoring
actual serialized evaluation history/snapshots. Retained and fresh queries remain
paired exactly as authored. The OS clock and database rows are not manually
changed to simulate expiry.

Runtime inputs remain separate from the expected ledger. Original rubric and
authorized-state records appear only in subsequent review/analysis. Inference
leases, admission/temperature guards, model residency checks, operation-by-operation
durable state and untouched-suffix continuation are unchanged. Attempted failures
and missing checkpoints cannot be silently retried or dropped.

## Analysis and interpretation

The separate analyzer/auditor/renderer derive 96 rather than assume 288, validate
complete scenario coverage, and preserve the original diagnostic, vote-validation
and aggregation functions. Five offline pipeline/negative tests and ten original
auditor tests passed. Synthetic fixtures are not observations. The new review
packets preserve question/state/rubric/delivered-answer blinding; new independent
assistant votes must freeze before diagnostics. Original votes cannot score new
answers.

Final reporting must compare the same 96 original checkpoint IDs, preserve the
original 288-checkpoint result separately, distinguish useful answers from safe
withholding and report every failure. History exclusion may make some ambiguous
pronoun requests safely abstain: this targeted suite does not establish universal
conversational reference resolution or all possible lifecycle queries. Results
concern text, worker process restart and controlled logical expiry, not power-loss
recovery, seven elapsed wall-clock days or spoken performance.
