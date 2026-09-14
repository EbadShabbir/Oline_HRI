# Memory-lifecycle repair: implementation and offline evidence

This is a new repair following the immutable
[`changing_memory_20260914`](../changing_memory_20260914/README.md) experiment.
The original answers, scores, runtime snapshot and unfavorable observations
remain unchanged. Six production files differ from that snapshot; the
collection harness, configuration, installed models and embeddings are unchanged.
The complete reviewable patch is
[`candidate_source_v2/changes_from_primary.diff`](candidate_source_v2/changes_from_primary.diff).

## Changes

- `routing.py` now revalidates explicit personal recall even when a prior
  conversation contains the requested fact. The classifier instruction no
  longer treats old conversation as a reason to skip storage. Deterministic
  intent overrides retain the actual classifier outputs and the independent
  compute decision in diagnostics. The opt-in lightweight router inherits the
  same policy without a separate implementation.
- `conversation.py` excludes prior conversation from every personal-memory
  generation, including questions about earlier statements. The session remains
  available to routing; the generator receives the current request and freshly
  authorized records. Existing pre-generation and post-generation snapshot
  checks remain active. An unavailable requested fact continues to produce the
  fixed application uncertainty response, rather than treating uncited model
  prose as proof of abstention.
- Personal-fact examples were removed from generation instructions. The original
  fresh-history jasmine claims matched a prompt example; this observation
  motivated removing that source of accidental personal content without claiming
  that a matching phrase proves causality.
- `memory_evidence.py` supports bounded subject-only prior-memory preambles,
  elliptical references with an explicit subject in the current request, plural
  object locations and simple personal follow-ups. It checks event identity
  across ISO and written dates and rejects temporal-only values as locations.
  It does not read expected answers, fixture values or conversation history to
  authorize a record.
- Correction-operation metadata is supplied and required only when the request
  actually asks when a correction happened or explicitly requests correction
  chronology. It no longer becomes an appointment time merely because the
  appointment was corrected. Incidental mentions of a prior change do not grant
  access to that metadata.
- `relationships.py` permits present-tense wording to express a stored “current”
  relationship without repeating that adjective. Person, role, domain qualifiers
  and former/past distinctions remain checked.
- `grounded_composition.py` adds a narrow location extraction path: one positive,
  linked location fact may constrain the generated answer to the requested
  location. It preserves subject/date identity, declines inconsistent metadata,
  historical/current tense mismatches, conditional or compound statements and
  temporal-only locations. A dated event's time is omitted only under the
  supported location-only grammar. The model must still generate the constrained
  response and correct citation; deviations are rejected. This is explicit
  application composition, not a claim of unconstrained model reasoning.
- `evaluation_scoring.py` recognizes the new `verified_location` constraint
  only with one supplied and cited record, preserving existing privacy,
  retrieval, citation and metadata checks.

## Offline validation and review

The [full offline suite](offline_validation_v1/full_suite_attempt_02.log) passed
1,093 tests with 26 skipped. A final
[226-test run](offline_validation_v1/final_focused_v1.log) passed with no skips,
covering the last constraint-registration addition, routing and evidence,
conversation validation, real SQLite subprocess lifecycle tests and all 14
changing-memory harness tests. Offline simulated model outputs are not live
observations.

The [validation receipt](offline_validation_v1/receipt.json) binds exact commands,
logs, source and test hashes. The initial failed development tests and the
first full-suite failure are preserved. That first full-suite command omitted
`scripts` from `PYTHONPATH`, and one lightweight-router test still expected the
old history-based bypass; the corrected command and revalidation expectation
passed. No live checkpoint was involved.

An [independent review](code_review_v1.md) found and resolved five edge cases,
including current/past location ambiguity, inconsistent event dates, conditional
locations, temporal-only places and incidental correction mentions. The
[integration addendum](code_review_addendum_v2.json) checks the constraint
registration. That reviewer authored the routing changes and explicitly excludes
them from independent-review scope; the separate
[prospective review](preflight_review_v1.json) independently inspects routing as
well as the complete source, authored schedule, expected ledger and tests.

## Bounds

The personal-intent and field parsers are bounded English rules. Unsupported
paraphrases can remain classifier-dependent, and unresolved references may
produce uncertainty. Excluding history from memory generation does not establish
universal non-disclosure across arbitrary dialogue or provide per-record
provenance for conversation history. The targeted live run uses scenarios
selected from known failures; its observations must be reported as development
regression evidence, not held-out accuracy.
