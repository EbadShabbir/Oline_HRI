# Final report-table renderer validation

The standalone [renderer](../render_report_tables.py) consumes a final sealed
analysis made by the approved v2 analyzer plus the final collection-audit JSON.
It performs no inference or semantic answer scoring. All useful-correct and
disclosure judgments are copied from the existing reviewed rows. Its output is
a newly created, hashed, read-only directory containing 16 CSV/Markdown table
pairs, definitions, source copy and command/input provenance.

The renderer checks the final analysis seal and approved analyzer hash, rejects
partial preparation or missing reviewed checkpoints, verifies 288 unique rows
from twelve complete scenarios, checks 24 stage/history groups of twelve rows,
and compares pair bindings and overall counts with the sealed analyzer output.
It binds the collection audit to the same run and configuration freeze hashes.
An audit reporting integrity violations remains a failed audit in the output;
the renderer does not suppress unfavorable integrity results.

Outputs include:

- All 24 authored branch/stage/history aggregates with expected kind and restart
  phase, planned/attempted/delivered/useful-correct/forbidden-disclosure counts,
  withholding, interruption and missing counts.
- Additional restart/history, expected-kind/history, expected-kind/restart/history,
  and branch/restart/history splits.
- Twelve scenario summaries with whole-rubric success, disclosure, and individual
  correction/deletion/expiry success counts.
- Separate original all-forbidden judgments, broad correction stale-subject
  disclosure, current-replacement stale-subject disclosure, deleted-subject,
  expired-subject, any-expired-fact, and never-stored replacement disclosure.
  These use the canonical values already present in the frozen judgments, not
  substring matching against delivered text.
- All 108 retained/fresh pair bindings and overall/per-branch/per-restart counts
  for both succeeding, retained only, fresh only, and neither. All-forbidden and
  revoked-subject disclosure transitions are counted separately.
- Per-checkpoint nominal routing and actual requested/returned generation
  selections, per-call details including failures/fallback calls, and aggregate
  generation calls. Setup disclosure turns and classifier calls are not silently
  included in scored generation counts.
- Final integrity-audit counts and actual history-exposure counts. Literal
  history exposure remains a lower-bound witness, not semantic absence or an
  answer-quality judgment.

## Offline validation

From the repository root:

```sh
.venv/bin/python -m unittest tests.test_memory_report_tables -v
```

All **seven tests passed in 1.530 seconds**. The exact command, hashes and return
code are in [attempt_01.json](attempt_01.json), with output in
[attempt_01.log](attempt_01.log). The tests use fabricated review labels and the
authored schedule; they do not read live collection answers or invoke installed
models. They cover stage/scenario/restart/kind denominators, pair transitions
including withholding, subject-versus-control-versus-unstored disclosure scopes,
independence from answer strings, route versus actual generation calls, final
seal/provenance creation, audit hash mismatch, tampering, partial rejection and
preservation of failed-audit status.

The original and amended analyzers remain unchanged, at SHA256
`60709a1002f7537f8cfd8ea57e8c89052f7ba2e608ca4b36e275a0fc79c95215`
and `65181ee60ac1064ac00fd27d956236d92bac343829cb0f56263bd2dd55297e00`.
No frozen runtime or harness source was changed. Assistant implementation/review;
human validation pending.

## Final invocation

After final analysis and collection audit exist, pass their exact paths to:

```sh
.venv/bin/python evaluation/changing_memory_20260914/render_report_tables.py \
  --analysis FINAL_SEALED_ANALYSIS_V2_DIRECTORY \
  --audit FINAL_COLLECTION_AUDIT_JSON \
  --output NEW_TABLE_DIRECTORY
```

The uppercase paths are placeholders. The actual invocation and hashes are
recorded inside the generated table directory. The renderer does not load
models, rerun the experiment, modify its inputs, or change any answer judgment.
