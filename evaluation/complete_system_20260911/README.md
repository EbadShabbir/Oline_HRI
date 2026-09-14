# Complete text-system evaluation

This Stage 2 pilot compares Qwen3 0.6B alone, Qwen3 1.7B alone, and CLARA's
adaptive system with the same prepared personal-memory database and full text
request pipeline. It follows the [ARC capability evaluation](../arc_capability_20260911/README.md).

Source preservation (2026-09-12): all 34 files in `freeze_v2.json` were verified
and copied unchanged into [frozen_source_v2](frozen_source_v2/archive_manifest.json)
before the subsequent lightweight-routing implementation. Current working-tree
source intentionally differs from this freeze. Historical runner commands
below require that archived source restored in a separate checkout with the
same environment and workload; they will reject changed execution source.
The [new implementation](../lightweight_routing_20260912/README.md) has separate
validation artifacts and does not change these results.

- [Protocol](protocol.md): controlled components, counterbalanced sessions,
  measurements, scope, and common device limits.
- [Frozen workload](workload.json) and [workload notes](workload_notes.md):
  48 new requests, memory lifecycle seed, and prewritten scoring rubrics.
- `freeze.json`: source, workload, model, and embedding identities fixed before inference.
- [Runner revision 2](runner_revision_v2.md) and `freeze_v2.json`: narrow failure-accounting
  correction after an interrupted 12-request diagnostic; the workload is unchanged.
- [Session resume](session_resume.md): retain a completed session after a temperature
  rejection before the next session attempted any request.
- [Resource failure and remaining sessions](resource_failure_continuation.md):
  preserve a cascade RAM-guard interruption and run only untouched independent
  repetitions under the same limits.
- [Project results](../../results.md): measured results, coverage, and limitations.

The observed pilot stopped at **184/432 planned attempts**: 166 validated
responses, 17 output-check failures, and one RAM interruption. Three sessions
completed, one stopped at 40/48, and five never started because swap remained
above the unchanged admission limit after the bounded wait. All 110 unique
response/evidence entries have assistant rubric review; human review is pending.

On the same 40 first-round requests, small-only, large-only, and CLARA scored
16, 21, and 19 correct. Small-only was fastest. The current cascade's overall
benefit is not established; its interrupted coverage, loading cost, and variable
backend placement remain part of the result.

- [Final analysis](results_reviewed/analysis.json) and [detailed report](results_reviewed/report.md).
- [Full tables](results_tables/tables.md) and [common-request metrics](results_tables/matched_first_round.json).
- [Pipeline diagnostics](results_reviewed/pipeline_diagnostics.json),
  [methodology review](methodology_review.md), and [numerical audit](numerical_audit.md).
- [Final device audit](final_device_audit.json): no model remains loaded; device
  configuration is unchanged, while logical swap occupancy remains elevated.

Regenerate tables from the final reviewed population without inference:

```bash
PYTHONPATH=src:scripts .venv/bin/python scripts/render_complete_system_tables.py \
  --analysis-dir evaluation/complete_system_20260911/results_reviewed \
  --output-dir /absolute/path/to/a/new/table-directory
```

The execution runner receives only prompt records and seeded memory. Reference
answers and rubrics are excluded from model requests. Final speech, actual
model calls, retrieved evidence, transformations, errors, and telemetry are
retained for audit. Semantic review must be distinguished from automated
lexical signals and structured-output acceptance.

From the repository root, after preparing and verifying the freeze:

```bash
PYTHONPATH=src:scripts .venv/bin/python scripts/run_complete_system_batch.py \
  --workload evaluation/complete_system_20260911/workload.json \
  --freeze evaluation/complete_system_20260911/freeze_v2.json \
  --output-root /absolute/path/to/a/new/private/run-directory
```

The batch runs each arm in a separate process, preserves natural residency
within a session, and stops on an unrecovered device or transport failure.
It never changes system swap or power settings. Existing output directories
are not reused. This is a text-system pilot with a static lifecycle snapshot;
speech, automatic memory capture, and concurrent memory changes are separate
evaluations.
