# Second repair: current relationship validation

This amendment lets a supported present relationship satisfy a question asking
for the **current** partner without requiring the literal word `current` in the
stored canonical text. It was selected after the first 96-checkpoint repair
exposed a remaining qualifier mismatch. This document describes implementation
and offline validation; it makes no claim about followup live answers.

Only `src/oline_hri/relationships.py` and `src/oline_hri/conversation.py` change
relative to the first repair's `frozen_v2`. The [exact second-only patch](offline_validation_v1/second_repair.patch)
includes the new regression test. Before/after source copies and unsuccessful
pre-patch tests are preserved in [offline_validation_v1](offline_validation_v1/).

The relationship witness helper now accepts optional current-status, role,
domain-qualifier and addressee requirements. All requirements must match the
same positive relationship for the same complete person name. Current matching
rejects past tense and `former`, `previous`, `past` or `old` status. Existing
calls that omit these optional requirements retain their previous behavior.

The conversation validator recognizes `current` in the existing bounded partner
query grammar and removes only that word from the required domain qualifiers.
It then checks the relationship witness in both supplied source and delivered
speech. For example, the **offline fixture** `Your walking partner is Niko
Fern.` supports a current walking-partner request. A chess partner, a different
person, someone else's partner, a negated relationship or a former partner does
not. Delivered speech must address the user; matching words in unrelated
sentences cannot supply a missing role or domain. Every cited current person
must remain represented. Snapshot freshness and evidence checks still apply.

The existing parser remains bounded. A collaborator query can match its parsed
partner role, but this patch does not add general canonical collaborator grammar
or universal relationship interpretation. The first repair's two cm01 partially
contradictory delivered answers are outside this amendment's scope and remain
an explicit limitation.

## Offline evidence and prospective approval

The [sealed receipt](offline_validation_v1/receipt.json) records commands, source
and test hashes, and return codes. The new tests first failed against the
unchanged first-repair source, then all **11 new tests** passed after the patch.
The final focused suite passed **190 tests** in **5.221 seconds**. It covers
relationship witnesses, conversation validation, evidence and history guards,
routing, and real subprocess lifecycle checks. Positive and negative cases
include composed and uncomposed conversations, wrong owner/person/role,
negation, tense, borrowed qualifiers, multiple cited people, missing evidence
and changed snapshots. Simulated transport responses in these offline tests
are not live experiment observations.

| Reviewed artifact | SHA256 |
| --- | --- |
| `conversation.py` | `878361152fcfed2dac6867badb3b935f0dea727f5ef2300cb704008a1444e2a7` |
| `relationships.py` | `29f04fc94ab15a357ef90bdf0bd645958ecf2ecdadc3ad857363756528cae505` |
| `test_current_relationship_repair.py` | `647918dae1a257350dc0538e405faa9878b13bc6888dbed01332f6c7170c0bb3` |
| `second_repair.patch` | `f3b8c52608b1c8a97338bd88350a5efdf07a72e7f5974369b8aa709b180e62d7` |
| `offline_validation_v1/receipt.json` | `f1bd0da34721d20fd7e13cc481250156d3f7fdf17df5376096d1a82a0ff3007f` |
| `preflight_review_v1.json` | `2bc5f375d72c7de2bd7458b85ca3abeecb29ee530b4eafa27c92434884f74b03` |

The [independent preflight](preflight_review_v1.json) binds all 41 runtime-source
hashes, the sealed offline inventory, and the three authored artifacts. It
reports no blocking findings. Its reviewer authored the copied subset protocol
and analysis tooling but made no production changes; this role is disclosed.
All three branch schedules and all 24 expected-state/rubric objects were
reverified as exact copies of both earlier frozen experiments.

## Followup scope

The [prospective protocol](protocol_v1.md) specifies only cm04: **24 checkpoints,
three independent databases and three actual worker process restarts**. Its
correction, deletion and expiry branches retain the original questions,
historical controls, stale-state probes and retained/fresh-history comparisons.
The unchanged collector uses the same real memory APIs and configured models,
embeddings and generation settings, with serialized inference and resource
guards. The common logical clock controls storage, retrieval and validation;
expiry excludes a record at equality with its retention boundary.

The first 96-checkpoint run was sealed and audited before this amendment.
Followup observations require fresh independent blinded assistant judgments,
frozen before diagnostics. They must be reported separately and compared only
with the matching 24 earlier checkpoints. They cannot replace first-run failures
or be pooled into its numerator. Human validation remains pending. This selected
development regression concerns text, process restart and controlled logical
expiry; it establishes neither held-out generalization, power-loss recovery nor
spoken performance.
