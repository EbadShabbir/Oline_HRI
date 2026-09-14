# Independent harness and prepared-snapshot audit

Reviewer: independent assistant `/root/audit_design`, before primary inference.
The reviewer inspected the adapter, runner and production routing, memory,
retrieval, conversation, fixed-model, transport, resource-guard and timing code.
This is assistant review; human validation is pending.

The following findings were resolved prospectively:

- General prompts originally varied by logical small/large role. Both physical
  models now occupy the same experimental logical role. Fixed-generator and
  backend assertions constrain all actual calls to the condition model. Tests
  verify identical equal-evidence inputs across both models.
- The production route flag couples retrieval and response framing. The adapter
  now independently authorizes access, selects retrieval, and supplies common
  deterministic response intent or actually linked evidence to Conversation.
  Classifier-only decisions cannot change response framing. Empty-evidence
  prompts/schemas match across policies; unrelated neighbors do not disable
  general helpers. SELECTIVE retains the current policy and sole-model call.
- Inspection logs include both full eligible corpus materializations used by
  exact cosine search, plus bounded source candidates, final results and
  exact supplied records. This avoids treating three returned neighbors as
  the complete inspection footprint.
- Standalone sessions now acquire the inference lock; the collector uses a
  separate batch lock. Concurrent actual sessions cannot pass the same lock.
- Snapshot before/after hashes are preserved in session finalization, including
  interrupted sessions. Source hashes must match independent approval at freeze.
- Transport logs preserve every received raw byte chunk before decoding, even
  if a later read fails. Non-streaming generation may produce no received
  output before an abort; the harness cannot preserve nonexistent bytes.

Each request uses a fresh Conversation and adapter. OFF supplies no personal
facts, evidence IDs or historical turns. All arms use the same immutable
prepared database contents, production retrieval/packing/composition and
freshness validators. The prepared file is copied into each session. Its
logical digest and binary before/after digests provide distinct state checks.
No scoring reference is parsed or forwarded into model input during inference;
reference bytes may be read for integrity hashing.

Independent read-only inspection of the actual BGE-prepared SQLite snapshot
found 27 stored records and 25 stored embeddings. The original catalog has 29
historical/current records; two deletions remove two rows. Remaining catalog
texts/profiles match, all relevant IDs are active, consented, correctly scoped
and temporally eligible, and the logical digest matches the preparation record.
Old superseded, expired and neighbor-profile records are not eligible answers.
No snapshot discrepancy was found.

The reviewer reran 34 focused offline tests against the final reviewed source;
all passed in 2.801 seconds. Tests cover six conditions, genuine classifier
boundaries, equal-evidence prompts, authorization, lifecycle exclusion, current
snapshot checks, sole-model residency, timeout preservation, raw-byte logging,
interrupt starts, schedule pairing, immutability and resource guards. A prior
command failed only because the tests directory was omitted from PYTHONPATH;
that log is retained and no source changed to fix the invocation.

Primary latency encloses authorization, common response intent, access
selection, real retrieval, helper/generation and validation. The outer
production `routing` span now encloses multiple experimental phases; analysis
must use the adapter's separate selection/retrieval fields and avoid summing
nested spans. Raw model loading is nested inside call and request wall time.
Common setup, admission waits and cleanup are separate, with measured session
wall time available for an amortized total.

No unresolved collection-blocking defect remains in the reviewed source.
Final approval is bound to the exact source, dataset, protocol and prepared
snapshot hashes in `independent_preflight_review.json`. Excluded development
smoke collection, if performed, must remain separate; any resulting execution
source edit requires a new independent approval and freeze.
