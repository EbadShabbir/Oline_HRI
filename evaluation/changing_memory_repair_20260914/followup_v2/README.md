# Current-partner followup: 24-checkpoint second repair

CLARA delivered a useful, rubric-correct answer at **all 24 checkpoints** in this
separate cm04 followup. There were **no forbidden disclosures, withheld answers,
technical failures, interrupted attempts or missing checkpoints**. The two
current-partner questions withheld after restart in the first repair now
received correct replacement answers, with retained and fresh history.

This is a targeted development regression chosen after a known first-repair
failure. **The final source was evaluated live on these 24 checkpoints only.**
The earlier 96-checkpoint result remains **92/96**, including two unresolved
cm01 contradictory partial answers and the original two cm04 withholds. No
followup observation replaces or is pooled into that result. These are
independent **assistant reviews; human validation remains pending**.

## Delivered outcomes

The [reviewed answers](analysis_v1/answers.md), [machine-readable judgments](analysis_v1/reviewed_answers.jsonl)
and [tables](tables_v1/README.md) preserve every checkpoint and denominator.
Useful correctness requires the complete frozen rubric; safe withholding never
counts as recall or as delivered uncertainty.

| Required behavior | Useful and delivered / planned |
| --- | ---: |
| Original recall before mutation/expiry | 4/4 |
| Correct replacement after correction | 4/4 |
| Authorized dated historical-control recall | 4/4 |
| Appropriate uncertainty when unavailable | 12/12 |
| Correction branch, all stages | 10/10 |
| Deletion branch, all stages | 7/7 |
| Expiry branch, all stages | 7/7 |
| Retained conversation history | 15/15 |
| Fresh conversation history | 9/9 |
| After actual process restart | 9/9 |

The nine equal-question/equal-time history pairs succeeded in both modes; none
showed a usefulness or disclosure difference. After restart, both replacement
answers and both authorized historical-control answers were correct, and all
five unavailable-fact answers expressed appropriate uncertainty. Deleted and
expired facts did not reappear. A request about a forgotten former partner did
not reauthorize disclosure; the separate authorized garden-tour event remained
answerable during correction.

There were **0/4** stale-subject disclosures on current replacement questions
(**0/8** across all post-correction questions including historical controls),
**0/6** deleted-subject disclosures, and **0/5** expired-fact disclosures. No
withheld response contributed to these successful recall counts.

Both [matched comparisons](compared_first_repair_v1/README.md) bind the same
24 checkpoint IDs and complete expected-state/rubric objects. The [original-baseline comparison](compared_original_baseline_v1/README.md)
uses its cm04 subset, not its full 288-row denominator.

| Same 24 checkpoints | Useful / planned | Delivered | Forbidden disclosure | Withheld |
| --- | ---: | ---: | ---: | ---: |
| Original baseline cm04 | 10/24 | 23 | 9 | 1 |
| First repair cm04 | 22/24 | 22 | 0 | 2 |
| This second repair | 24/24 | 24 | 0 | 0 |

## What changed and what ran

The [second-only patch](offline_validation_v1/second_repair.patch) changes
`conversation.py` and `relationships.py`. A current-partner request no longer
requires the literal word `current` in the stored present-tense relationship.
The validator still requires a positive witness for the same person, role,
domain and addressee, and rejects former/past relationships, negation and
unsupported claims. [Implementation notes](implementation_v1.md) describe its
bounded grammar and preserved guards. **190 focused offline tests passed**,
including 11 new regressions; pre-patch failing tests remain preserved.

The [prospective review](preflight_review_v1.json) bound all 41 runtime files and
the authored runtime, ledger and protocol before inference. The [freeze comparison](freeze_comparison_v1.json)
confirms exactly those two source changes and equality of all 11 compared
non-source runtime conditions, including installed models, embedding assets,
configuration, seed, generation settings, routing policy and resource guards.
Host state was captured anew. The [schedule/rubric comparison](authoring_validation_v1.json)
proves that all three branch schedules and all 24 expected objects are unchanged
from both earlier experiments; references and expected answers were outside
model inputs.

All **24 scored generations actually used `qwen3:0.6b`**. All 24 scored routes
requested memory and selected the small model under the frozen CLI-default LLM
router; the trace's `legacy` route label is retained in the tables. Including
three setup generations and both selector calls for all 27 conversation turns,
the trace contains **81 actual chat calls**, all using `qwen3:0.6b`. Installed
embeddings and real storage, retrieval, generation and validation paths ran.
Recorded constraints were **eight `verified_user_relationship`, four
`verified_location`, and 12 with no constraint**. Null generation-policy fields
do not erase those observed constraints. These results concern the delivered
system, including constrained generation and validation.

## Lifecycle and stale-state checks

The [independent collection audit](collection_audit_findings_v1.md) passed
**2,811 checks with zero integrity violations**. It verified 46 completed
non-restart authored operations, six confirmed remembers, one correction, one
forgetting operation and expiry purging of two records. Three independent new
fictional databases underwent **three real worker process restarts**, with six
distinct admitted processes reopening the same database identity per branch.
Actual history and retained snapshots were explicitly restored by the
evaluation harness. This does not imply deployment persists chat history.

Expiry used the configured seven-day retention and one injected **logical
evaluation clock** consistently across storage, retrieval and validation.
Records created at `2026-10-01T12:00:00+00:00` were eligible strictly before
`2026-10-08T12:00:00+00:00`, and excluded at equality and later. Checkpoints ran
one microsecond before, at, one microsecond after, and two seconds after the
boundary following restart. No OS clock change or manual database expiry edit
was used; the expiry branch performed no correction or forgetting.

All three retrieval-warming probes returned equal repeated results with current
snapshots. Eight subsequent snapshot probes produced the expected seven stale
and one current results; all 24 answer-time freshness checks passed. The
retriever rebuilds its matrix and has no persistent vector cache. Preserved
HTTP diagnostics also report positive backend cached-token counts on all 27
generation calls, 27 compute-selector calls and 21 of 27 memory-selector calls.
These observations document existing cache activity and snapshot checks; stale
snapshots were not injected as production evidence.

The original statement remained in all **14 retained-history checkpoints after
disclosure**, including five after restart. It was forwarded into **zero**
scored generation inputs. The remaining retained query preceded storage; all
nine fresh-history queries had empty prior history. This supports exclusion in
the executed personal-memory requests, without claiming universal semantic
absence from arbitrary dialogue. The recorded evidence identifies no storage,
retrieval, generation or validation failure in this followup.

There were no rejected admissions, continuation fragments, runtime guard or
cleanup failures. The 285 telemetry samples reached **56.906°C**, RAM use
**6,116/7,620 MB**, and swap use **748 MB**. These are sampled maxima; RAM-used
telemetry is not Linux `MemAvailable`. Inference was serialized under the
existing leases and guards.

## Latency, review and reproduction

Measured conversation wall latency was slightly higher than the first repair's
matched cm04 subset. [Recorded latency](compared_first_repair_v1/wall_latency.csv)
includes routing, retrieval, generation and validation, excluding setup,
mutation, admission and cooling gaps. No timing values were missing.

| Timing scope | First repair median / p95 | Followup median / p95 |
| --- | ---: | ---: |
| All attempts, 24 versus 24 | 2.633 / 12.341 s | 2.760 / 12.647 s |
| Delivered only, 22 versus 24 | 2.572 / 11.832 s | 2.760 / 12.647 s |

The median and nearest-rank p95 increases are descriptive, not causal estimates
of repair overhead. Delivered-only populations differ because the earlier
system withheld two answers; these measurements do not establish spoken
latency.

Two fresh independent assistant contexts, C and D, received only the question,
authorized state, unchanged rubric and delivered answer. Their [frozen judgments](sealed_reviews_v1/review_freeze.json)
agreed on **all 11 distinct blinded groups covering 24 checkpoints**, so no
adjudication was needed. Votes were frozen before diagnostics were revealed.
The report's author reviewed source and authored the copied subset protocol,
and did not serve as either blinded answer reviewer.

[Analysis reproduction](analysis_reproduction_v1.json) passed **41 data checks**
without inference or rescoring, reproducing resolved votes, answers, metrics,
16 CSV tables, both matched comparisons and figure source data. Fresh manifest
paths/timestamps and the resulting vote-seal identity are explicitly excluded
from byte-equality claims. The [checkpoint figure](figures_v1/checkpoint_heatmap.png)
and [PDF](figures_v1/checkpoint_heatmap.pdf) derive only from those frozen votes.
[Completed analysis commands](completed_analysis_commands_v1.sh) preserve actual
arguments; [reproduce_analysis.sh](reproduce_analysis.sh) takes a new output
directory. [reproduce_collection.sh](reproduce_collection.sh) requires the
reviewed source/runtime identities and new blinded reviews for any new answers.

All earlier unfavorable outcomes and failed preparation attempts remain in
their original directories. This single selected scenario is not held-out
validation or evidence of universal memory reliability. The results concern
**text, application process restart and controlled logical expiry**. They do
not establish OS/Ollama restart, power-loss recovery or spoken performance.
