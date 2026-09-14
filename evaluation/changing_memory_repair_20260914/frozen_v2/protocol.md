# Changing-memory repair validation — prospective diagnostic protocol

This is a separately labeled development regression experiment following the
sealed `changing_memory_20260914` baseline. It evaluates the repaired adaptive
text runtime with the installed models and embeddings. The baseline remains
immutable. Scenarios were selected with knowledge of the baseline failures;
these results will not be described as held-out accuracy or as a replacement for
the original 288 checkpoints. No repaired-runtime inference was performed while
authoring this protocol. Independent human validation remains pending.

## Fixed scope and hypotheses

Use four unchanged baseline scenarios: cm01 (tea preference), cm04 (walking
partner), cm07 (binoculars location), and cm09 (pottery appointment). Their four
independently stored historical-control events remain part of every branch.
Selection covers old history and prompt-example matches, unnecessary partner
withholding, plural-object evidence omission, and correction-time validation.
The sketchbook omission and mutable dated-event subject scenarios are outside
this targeted live subset; they should have offline regression coverage where
the repair applies. A result on four selected scenarios is not broad reliability
evidence.

Each scenario has separate correction, deletion and expiry branches from
equivalent initial state: **12 new persistent databases, 12 scheduled real
process restarts, 96 scored checkpoints and 12 extra disclosure turns**. There
are 40 correction, 28 deletion and 28 expiry checkpoints; 60 retained-history,
36 fresh-history, 36 matched history pairs and 36 post-restart checkpoints.
Expected tasks are 16 original recalls, 16 replacement recalls, 16 legitimate
historical-control recalls and 48 unavailable-fact uncertainty responses.

The repair hypotheses are: current personal-memory questions cannot bypass
live memory through prior conversation; retained old facts do not reappear
after correction, deletion or expiry; known current evidence remains usable;
location-only questions omit unrequested event times; and appointment validation
does not mistake write/correction audit time for the appointment time.

## Frozen schedule and independent references

`scenarios.json` copies the four scenario objects without changing any authored
question, value or event. `author_ledger.py` copies the sealed independent author
and changes only the experiment label and count generalization. It imports no
CLARA code and reads no runtime database or generated answer. It expands the
authored event schedule and independently replays it into authorized states,
permitted evidence and answer rubrics. The expected ledger never enters any
router, embedding, generator, conversation or validation input.

Run the author into `authored_v1`, then copy this protocol to
`authored_v1/protocol.md`. An independent assistant must inspect the authored
schedule, ledger, protocol, exact repaired source/configuration and offline
test results before approving a source-and-artifact hash freeze. Revisions before
inference preserve earlier versions. No source/configuration changes are
permitted after the new runtime freeze. Repairs after observation require a new
labeled freeze and run, preserving every earlier outcome.

All 96 checkpoint objects, questions and rubrics must be byte-equivalent as
JSON values to the corresponding subset of the original expected ledger. All
12 branch operation schedules must similarly match the original schedules.
Only top-level experiment labels and provenance change. Equivalent wording is
accepted; useful success requires a nonempty delivered answer meeting the
entire existing rubric. Withheld, failed and missing answers are never useful
recall. Unrequested personal facts remain rubric violations.

## Lifecycle, stale state and real execution

Use the unchanged `scripts/run_changing_memory.py` freeze/collect interface with
the newly reviewed repaired source. Runtime collection loops over the authored
branches and does not require a 12-scenario workload. The original helper
`reproduce_collection.sh` rejects source changes by design and must not be used
to execute this repair experiment.

Store original subject and historical-control facts through the real memory CLI
handler and confirmed-write API at logical `2026-10-01T12:00:00+00:00`. Correct or
forget through their real APIs at +60 seconds. Retention is the configured seven
days; the expiry deadline is `2026-10-08T12:00:00+00:00`. A record is eligible only
while logical time is strictly less than its deadline. Test one microsecond
before, equality, one microsecond after, and after process restart at +2 seconds.
The same explicit evaluation clock feeds storage, retrieval and validation.
Do not modify the operating-system clock or manually edit database rows.

Preserve the actual live conversation across mutations and restore its exact
serialized content into a distinct worker process reopening the same database
inode. This deliberate evaluation history restoration exercises stale state; it
does not claim that deployment persists conversation history. Real lexical,
semantic and hybrid probes warm retrieval; original snapshots are retained and
checked through the real freshness API, including after restart. No production
persistent vector cache exists, and no offline snapshot-injection hook is
enabled. Fresh-history probes use the same database in separate empty sessions.

Every branch uses the full inherited schedule: correction has pre-store
uncertainty, original recall, replacement and historical-control queries with
retained/fresh history, then both repeated after restart; deletion has original
recall, retained/fresh post-delete queries and forgotten-former-statement queries
before/after restart; expiry has retained/fresh pre-boundary and equality
queries, retained after-boundary query and retained/fresh post-restart queries.
Deletion cannot substitute for expiry because their DBs and operations differ.

Do not expose forgotten former content in response to a historical request.
The separate historical-control event remains authorized before its own expiry;
asking its venue does not request its time. Questions and expectations are
frozen before repaired inference, and no favorable outcomes are assumed.

Use installed Qwen3-0.6B/1.7B and the installed BGE CPU ONNX model through the
actual adaptive conversation path. Freeze configuration, model tags/digests,
embedding assets, prompts, source and package versions; record actual model
selections independently of nominal routes. Serialize inference using all
existing leases and device resource guards. No concurrent Jetson experiment,
retired 4B model, model download or simulated live observation is permitted.

All storage/acknowledgment, embedding, retrieval, evidence supply, model request,
raw answer, final answer, validation, process identity, DB identity, clock and
resource traces remain durable. Preserve technical failures, failed admissions,
interruptions and missing checkpoints. The existing continuation logic may
execute only an untouched suffix; attempted failures are not retried or replaced.

## Review, comparison and reporting

After collection, prepare randomized blinded packets containing only question,
authorized state, original rubric and delivered answer. Deduplicate only exact
semantic packets with a complete checkpoint binding. Two independent assistant
reviewers must freeze their judgments before being given diagnostics. A third
blinded assistant adjudicates any disagreement before unblinding. Reviewers are
not provided baseline scores, repair details, route/model identity, raw output,
retrieval evidence or validation diagnostics while scoring. Human validation
remains explicitly pending. Original baseline votes cannot score new answers.

Report all 96 planned checkpoints, withholding, technical failures and missing
observations. Compare repaired and original answers on these exact 96 matched
checkpoint IDs; show the original 288-checkpoint aggregate only as separately
labeled background. Show full-rubric usefulness, recall and replacement, stale
correction disclosure, deleted/expired disclosure, uncertainty, historical-control
recall, restart and paired retained/fresh differences. Do not convert no
disclosure or safe withholding into successful recall. Report the explicit
field-extraction/answer-constraint path separately if used; its output is a
delivered-system observation, not unconstrained model reasoning.

Diagnose storage, retrieval, selection, generation and validation from actual
traces after votes freeze. Match observed claims to support; do not infer source
causality merely from a text match. Preserve all data, reviews and hashes in this
new directory, and update the main project notes with a clearly labeled repair
validation result. Scope is text, actual worker process restart and controlled
logical-time expiry; it establishes neither power-loss recovery nor spoken
performance.
