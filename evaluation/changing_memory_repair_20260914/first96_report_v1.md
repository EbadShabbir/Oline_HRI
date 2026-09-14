# CLARA changing-memory repairs — 14 September 2026

**The first repair improved useful delivery from 39/96 to 92/96 on the same
selected checkpoints. Forbidden disclosures fell from 30 to zero.** All 96 live
checkpoints and their blinded assistant reviews are complete. Two contradictory
tea answers and two withheld relationship answers remain failures. A separately
labeled 24-checkpoint relationship follow-up is in preparation; human validation
remains pending.

This is targeted development regression chosen after known failures, not
held-out accuracy. The original [288-checkpoint experiment](../changing_memory_20260914/README.md)
is unchanged. Results concern text, actual worker **process restart and controlled
logical-time expiry**. They establish neither power-loss recovery nor spoken
performance.

## Changes and matched outcomes

The [implementation report](repair_changes_v1.md) and
[exact patch](candidate_source_v2/changes_from_primary.diff) describe six changed
production files. Explicit personal recall now revalidates memory despite prior
conversation. Generation receives freshly authorized evidence without prior
conversation history; routing retains the session. Personal prompt examples were
removed. Bounded evidence parsing, correction-time requirements, present-tense
relationship coverage and guarded location composition were improved.

Four fictional scenarios cover preference, relationship, object location and
appointment, each with an authorized dated-event historical control. All three
independent branches per scenario completed: 12 new persistent databases, 12 real
worker restarts, 96 scored queries and 12 extra disclosure turns. The
[protocol](protocol_v1.md), [ledger](frozen_v2/expected_ledger.json), and
[equality check](authoring_validation_v1.json) bind unchanged schedules,
questions, authorized states and rubrics to the original matched subset.
References and expected answers never enter inference.

| Full-rubric outcome | Original matched baseline | First repair |
| --- | ---: | ---: |
| Useful, correct delivered response | 39/96 (40.6%) | 92/96 (95.8%) |
| Original recall before mutation/boundary | 12/16 | 16/16 |
| Replacement recall after correction | 3/16 | 12/16 |
| Authorized historical-control recall | 0/16 | 16/16 |
| Appropriate unavailable-fact uncertainty | 24/48 | 48/48 |
| Delivered answers | 93/96 | 94/96 |
| Any forbidden disclosure | 30/96 | 0/96 |
| Withheld answers | 3/96 | 2/96 |
| Interrupted or missing checkpoints | 0 | 0 |

The baseline's 30 disclosures comprise 28 revoked original values and two
replacement values never stored in their deletion or expiry branches. The 288-row baseline
denominator is never substituted for the matching 96 rows. Every transition and
both answers appear in the [matched comparison](matched_comparison_v1/README.md).

After repair, old-value disclosure was 0/16 on current replacement questions,
deleted-subject disclosure 0/24, and expired-subject or expired-control disclosure
0/20. The deletion set includes questions about the forgotten former statement.
All deletion/expiry unavailable-fact queries delivered appropriate uncertainty,
as did all four pre-store questions. Of 16 replacement queries, only 14 delivered
answers and 12 passed; withholding is never successful recall.
[Disclosure tables](tables_v1/disclosure_scopes.md) retain narrower denominators.

Retained-history usefulness improved from 19/60 to 58/60, and fresh-history
usefulness from 20/36 to 34/36. Both histories passed in 34 of 36 matched pairs;
neither passed in two, with no one-sided successes. Post-restart usefulness
improved from 9/36 to 34/36, with zero forbidden disclosures. The two withholds
occurred after restart, so non-disclosure alone does not prove useful persistence.
See [all answers](analysis_v1/answers.md), [16 tables](tables_v1/README.md), and
[checkpoint figure](figures_v1/checkpoint_heatmap.pdf).

## Preserved failures

Both tea correction answers said: “Your preferred tea is jasmine tea. I don't
know which tea you prefer.” Both reviewers judged these contradictory answers
partial and unsuccessful. [Independent diagnosis](partial_answer_diagnostics_v1.md)
found sufficient current evidence, identical history-free generation inputs and
raw speech equal to delivery. No application composition added the contradiction;
generation produced it and validation accepted it. This remains an unresolved
limitation, not evidence of stale storage or history leakage.

Both walking-partner restart answers were withheld despite supported raw
replacements. [Independent diagnosis](withheld_diagnostics_v1.md) identifies a
validator requiring the question's literal “current” qualifier in the canonical
record. Both no-delivered-answer judgments remain failures. The
[separate follow-up protocol](followup_v2/protocol_v1.md) targets this issue with
24 unchanged cm04 checkpoints after a separately reviewed amendment.

## Runtime, integrity and expiry

The [independent full audit](collection_audit_findings_v1.md) passed **10,541
checks with zero integrity violations**: 184 authored operations, 24 confirmed
writes, four corrections, four forgetting operations, eight retention purges,
12 independent databases and 12 actual restarts. Twelve repeated cache probes
returned identical eligible results. All 32 saved-snapshot probes matched
expected eligibility, and all 96 answer freshness checks passed.

The actual conversation contained the original disclosure at all 56 scored
checkpoints where that history was expected. None of this prior conversation
was forwarded to scored memory generation; all 36 fresh sessions started empty.
Real lexical, embedding and hybrid retrieval paths were exercised. The study
does not invent a persistent vector-result cache. The evaluation explicitly
restores recorded history on restart; it does not imply deployment persists chat.

Storage, retrieval and validation share one injected evaluation clock. Seven-day
retention begins at logical 2026-10-01 12:00:00 UTC; eligibility requires time
strictly before 2026-10-08 12:00:00 UTC. Queries occur one microsecond before, at
equality, one microsecond after, and after restart two seconds past expiry.
No OS-clock change or manual row edit simulates expiry. Expiry branches contain
no correction or forgetting operation.

The successful [freeze](frozen_v2/freeze.json) uses the CLI-default LLM router,
installed Qwen3 0.6B/1.7B, real BGE ONNX CPU embeddings, context 2048, output cap
192, temperature 0, seed 42 and thinking disabled. All eleven non-source
conditions [match the original freeze](freeze_comparison_v1.json). Actual scored
generators selected 0.6B 89 times and 1.7B seven times, versus 85 and 11 in the
matched baseline. All 96 repaired routes requested memory. Recorded constraints
were 24 verified-location, six verified-relationship and 66 absent. These
application constraints and deterministic uncertainty are part of the delivered
system; their success is not unconstrained model reasoning.

Inference remained serialized under existing leases and resource guards. One
startup-temperature rejection occurred before any operation or inference; its
untouched suffix completed in another worker. All failure/continuation evidence
is preserved. There were no runtime guard or cleanup failures. Recorded maximum
temperature was 57.437°C, RAM 6,593/7,620 MB and swap 750 MB. The earlier
[sandbox-denied freeze attempt](frozen_v1/failure.json) is preserved and made no
inference; the same source then froze with authorized local-service access.

All-attempt conversation latency had median/p95 2.939/36.484 seconds in repair,
versus 3.110/48.327 seconds in the matched baseline (96 observations each).
Delivered-only median/p95 was 2.939/36.484 seconds for 94 repair deliveries and
3.005/44.211 for 93 baseline deliveries. No timing is missing. Timing includes
routing through validation but excludes setup/mutations and cooling between
operations. These are descriptive measurements with differing model selections,
not a randomized causal speed estimate. [Subgroup latency](matched_comparison_v1/wall_latency.csv)
is reported without hiding unfavorable differences.

## Review, tests and reproduction

Two fresh independent assistant contexts reviewed 47 distinct exact packets
covering all 96 outcomes in two sealed batches. Inputs contained only question,
authorized state, rubric and delivered answer. Original votes were frozen before
diagnostic analysis. Reviewers agreed on every semantic judgment; no third
adjudication was needed. [Binding provenance](bound_reviews_v1/provenance.json)
preserves original votes and content-identical packet grouping. Human validation
is pending.

Before inference, the full offline suite passed 1,093 tests with 26 skipped;
the final affected suite passed 226 with no skips. Logs, source/test hashes,
independent code and preflight reviews, and initial development failures are
preserved in the [implementation report](repair_changes_v1.md). Simulated offline
transport contributes no live observations.

[Analysis reproduction](analysis_reproduction_v1.json) passed 34 data checks:
byte-identical metrics, reviewed answers, resolved votes, all 16 CSV tables,
comparison CSVs and figure source data. New manifest timestamps/paths differ.
[reproduce_analysis.sh](reproduce_analysis.sh) recomputes frozen judgments in a
new output directory without inference or rescoring.
[reproduce_collection.sh](reproduce_collection.sh) invokes real models under the
first reviewed source and requires new blinded reviews. Changed conditions stop
collection; later source amendments cannot represent the first repair. Manifests,
exclusive creation and read-only permissions provide an auditable archive, not
privileged WORM storage. Unsupported paraphrases and the tea contradiction remain
limitations; these selected scenarios do not establish universal memory safety.
