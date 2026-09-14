# Shared memory pipeline improvements, 2026-09-12

Step 2 is implemented and checked offline. These changes apply to the shared
memory path used by the default router, lightweight router, and fixed-generator
controls. They do not establish new model accuracy, device speed, or a cascade
advantage. Earlier benchmark scores and raw observations are preserved.

Subsequent step 3 adds optimized fixed-model comparison controls. Before that
change, all 105 files in this step's validation map were verified and copied to
[the step 2 source archive](../post_memory_comparison_20260912/step2_validated_source/archive_manifest.json).
The validation below remains evidence for that snapshot. Fresh collection uses
its own [protocol](../post_memory_comparison_20260912/protocol.md) and freeze.

## What changed

| Stage | Implemented behavior |
| --- | --- |
| Memory intent | Recognizes explicit personal inputs in later clauses and recall imperatives; a fully supplied start-plus-duration question skips personal retrieval. Ambiguous requests still use the classifier. |
| Candidate ranking | Matches bounded subject/attribute/owner/event fields and prioritizes coverage of different requested fields within the existing candidate pool. |
| Evidence selection | Selects answering subjects and attributes, not adjacent project facts. Numbers, dates, and units alone do not authorize a record. A requested calendar value can link an actual meeting preference when the meeting subject also matches. |
| Disclosure | If no candidate answers the request, no candidate text or ID is supplied to the generator. The existing explicit abstention remains. |
| Conflicts | Preserves differing values for the same positive subject/relation/event context, including named halls and Lab A/B. Different owners, dates, and negated assertions are not merged into that conflict. |
| Partial direct recall | For completely parsed requests, preserves supported facts and explicitly marks the missing fields. Unsupported formats/time requirements decline this literal composition. |
| Recorded event times | Supports bounded ordering of two or three consistent event timestamps and exact elapsed hours/minutes for two. Whole source facts, citations, and freshness checks remain required. |
| Lifecycle | Separate-process tests verify correction, forgetting, expiry, profile isolation, and stale in-flight answer rejection. Storage schema and production `memory.py` are unchanged. |

Ranking still uses at most 20 candidates from each search source and the
conversation still receives at most three. There are no new search, embedding,
or classifier calls from evidence ranking. Existing RRF scores and source
positions remain diagnostics. Neither similarity nor a subject match bypasses
consent, lifecycle, context budgets, citation checks, or output validation.

The event composer checks canonical dates/clocks against `event_time`, requires
known minute-resolution instants with the same offset, and declines conflicting
timestamps, seconds/fractions, explicit timezone annotations, unsupported extra
tasks, hypothetical rescheduling, or missing subjects. A declined event task
cannot fall through to an older timeline template. Derived intervals are
application calculations, not evidence that a generator learned arithmetic.

The subject parser deliberately covers bounded grammars. Unsupported phrasing
returns an unresolved signal and uses the existing conservative path. General
planning, budget arithmetic, departure-time calculations, time-zone conversion,
and arbitrary memory synthesis remain outside the new event composer. Missing
facts outside the bounded candidate pool cannot be recovered by selection.
Independent quality evaluation is still required, including appropriate
abstentions and cases outside these grammars.

## Historical development replay

The [failure inventory](failure_inventory.md) separates the earlier routing,
candidate, selection, and generation failures. Those prompts and outputs are
now development data, not unseen evaluation data.

[Final replay report](offline_replay_v2/report.md) and
[machine-readable replay](offline_replay_v2/replay.json) compare the archived
pre-step source with current source in isolated Python processes. The workers
receive prompts and recorded candidate records, without rubric labels, and
cannot invoke models, embeddings, retrieval, a database, or networking.
The [detailed interpretation](offline_replay_v2/interpretation.md) identifies
the changed cases and reconciles helper output with historical supplied IDs.

| Deterministic development check | Before | After |
| --- | ---: | ---: |
| Personal prompts with an explicit correct memory-intent decision | 16/24 | 24/24 |
| General prompts with an explicit correct no-memory decision | 1/24 | 2/24 |
| Explicit wrong intent decisions | 0 | 0 |
| Prompts still deferred to a classifier | 31/48 | 22/48 |
| All required facts selected, among required-fact attempts with recorded candidates | 47/56 | 54/56 |
| Required fact occurrences selected | 63/75 | 73/75 |

The 22 unresolved requests are general prompts; unresolved does not mean an
incorrect classifier outcome. No classifier was rerun.

Selection replay covers 74 candidate-bearing attempts out of the 184 historical
attempts; 56 required particular facts. The other 110 attempts have no recorded
candidate list and remain unassessed for selection, including 24 personal
attempts for which the new policy would request retrieval. Repeated attempts
and shared candidate sets are not independent observations.

All 73 required fact occurrences present in the recorded candidate lists are
selected by the revised function. The two absent badge-preference occurrences
cannot be recovered from those lists. Full required selection improved on four
lunch-preference and three conflicting-room attempts, with no required-ID
selection regressions on the replayed candidates. This does not measure new
retrieval recall or answer correctness.

The baseline linking helper's result differs from historical supplied evidence
on 21 of 74 candidate lists. The old Conversation supplied the first neighbor
when the helper selected nothing. Thus the historical **51/80** complete-evidence
figure and this replay's **47/56 → 54/56** describe different populations and
stages; they must not be presented as a before/after answer-accuracy comparison.
The original supplied IDs are retained beside every replay row.

`offline_replay_v1` is retained from before the final conservative timestamp
annotation check. `offline_replay_v2` has final source hashes; the intent and
selection comparisons are identical. No prior run was replaced.

## Regression validation

Final discovery ran 854 tests: **828 passed, 26 skipped, zero failures or
errors**, in 41.936 seconds. All five live-test flags were disabled. The
[validation record](offline_validation.json) contains the command and source,
test, and replay hashes; the [complete test log](unittest.log) is preserved.

New tests cover intent rules, subject and event matching, field diversity,
conflicts, withheld unlinked data, partial recall, literal-answer constraints,
time arithmetic and its rejection boundaries, and lifecycle changes in actual
separate processes. Fake model responses and synthetic vectors are used only
to exercise the real client/pipeline interfaces; their quality and timing are
not benchmark measurements.

Legacy tests that assumed an unrelated first neighbor would be disclosed were
updated to request their fixture facts explicitly, preserving the original
budget, snapshot, rollback, and sanitization assertions. Separate tests now
require zero disclosure of unrelated candidates and rejection of their IDs.
A named third-party owner cannot answer a direct “my partner” question without
identity evidence; literal named-owner rendering remains tested separately.

Reproduce the replay without inference, using a new output directory:

```bash
.venv/bin/python scripts/check_memory_pipeline_offline.py \
  --baseline-source evaluation/memory_pipeline_20260912/baseline_source \
  --output-dir /absolute/path/to/a/new/replay-directory
```

## Source preservation

Before edits, 40 source/configuration/test files were verified against step 1's
validation record and copied to
[baseline_source](baseline_source/archive_manifest.json). The earlier Stage 2
[34-file execution archive](../complete_system_20260911/frozen_source_v2/archive_manifest.json)
and all original result artifacts remain unchanged. The working tree now
intentionally differs from both earlier source snapshots. Future live quality
comparisons require a new freeze, held-out requests, equal single-model and
cascade controls, and independent review.

Implementation: [routing](../../src/oline_hri/routing.py),
[subject/ranking signals](../../src/oline_hri/memory_evidence.py),
[conversation evidence checks](../../src/oline_hri/conversation.py), and
[bounded composition](../../src/oline_hri/grounded_composition.py).
