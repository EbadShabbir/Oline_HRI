> Historical collection-status document, preserved before the completed report replaced README.md. Planned output names in this record are superseded by the final report and commands.sh.

# CLARA routing-overhead experiment

Live collection is continuing in `run_v2` under the
[prospective v2 amendment](frozen_v2/protocol.md). Its offline validation reported
**946 tests: 920 passed, 26 skipped, zero failures/errors**. The continuation
preserves the original **22 whole four-turn sequences and 88 attempts** and
starts at the next unattempted slot. Final collection, timing comparisons and
answer-quality conclusions remain pending.

The plan contains 12 four-turn sequences and three timing repetitions of
small-only, large-only, lightweight adaptive and an adaptive diagnostic
routing-bypass replay: 432 main-system turns and 144 replay turns in total.
Main systems retain normal conversation history and model residency within a
sequence. Every independent sequence begins in a new process with no Ollama
model resident; OS page caches are retained. The final report will distinguish
observed time savings from reviewed answer correctness.

## Original stop and preserved continuation

The [original v1 batch](run_v1/batch_finish.json) stopped on the fourth turn of
`ro_dddd_3_r1_large`. An ordinary answer rejection,
`ResponseValidationError` for omitted temporal memory detail, was incorrectly
treated as fatal by the harness because that exception inherits `ValueError`.
All four requests had been attempted, device/transport checks passed, and
cleanup verified no model resident. The rejected answer and its timing remain
unchanged; its original turn and sequence statuses remain `interrupted`.

Before further inference, the v2 amendment removed ordinary `ValueError` from
the harness's fatal tuple. Explicit replay-invariant violations remain fatal
control errors. The application, routing, memory, questions, answer helpers,
validators, models, generation settings, resource guards, schedule and timing
boundaries did not change. Added regression coverage checks intermediate and
final answer-validation failures. This is a disclosed failure-accounting
correction during collection, not a new confirmatory experiment.

The continuation references each original artifact through file symlinks in
real sequence directories. It adds the remaining 122 sequences/488 attempts
without retrying an answered or failed request and without stitching in later
turns. The mixed-freeze analyzer checks each session against its own freeze.
Its single completion-eligibility exception requires the exact hash-pinned
four-turn original failure, clean guards/cleanup and unchanged raw artifacts;
the rejected answer still receives no useful-answer credit.

- [Original freeze](frozen_v1/freeze.json), [original protocol](frozen_v1/protocol.md),
  [v1 validation](offline_validation.json), and [v1 test log](unittest_final.log):
  945 tests, 919 passed, 26 skipped, zero failures/errors.
- [Continuation freeze](frozen_v2/freeze.json), [v2 amendment](protocol_v2.md),
  [v2 validation](offline_validation_v2.json), and [v2 test log](unittest_v2.log).
- [Exact source delta](run_v2/runner_source_delta.diff),
  [independent freeze review](freeze_v2_review.json),
  [original reuse audit](v1_reuse_audit.json),
  [adapter regression](adapter_validation_v2_final.json), and
  [continuation reuse manifest](run_v2/reuse_manifest.json).
- [Continuation plan](run_v2/batch_plan.json),
  [durable scheduler](run_v2/scheduler.jsonl), and [live log](collection_v2.log).
- The preliminary test log remains preserved; it overlapped edits to the new
  harness tests. The completed validation records and matching freezes govern
  their respective collection sessions.

## Methods and artifacts

The [workload](frozen_v2/workload.json), [workload notes](workload_notes.md) and
[methods record](report_methods.md) explain difficulty labels, social-turn
hysteresis coverage, prepared fictional memory, history and replay controls.
[Workload validation](workload_validation_final.json) uses simulated outputs;
those outputs are excluded from timing and quality evidence. The
[historical reuse record](historical_reuse.json) distinguishes previous evidence
from these new controlled observations.

Every attempt directory records its manifest, start/finish state, startup time,
actual model HTTP requests, monotonic span events, observations, telemetry and
cleanup. Scheduler logs retain admission checks and cooldown waits. Backend
load/prefill/decode durations are nested inside classifier/generation wall
spans and are not added again. Complete sequence latency includes startup,
request spans and intervening measured work; cleanup is separate. Exact-request
replay runs shared retrieval/helpers/validation while bypassing selection. It
always follows its main-system block and is a diagnostic, not a deployable
routing policy.

Repeated sequences, shared templates and the fictional profile create dependent
observations. The [pending reporting acceptance checks](report_acceptance.json)
require actual route/residency evidence, complete timing accounting, matched
replay inputs, preserved failures and semantic-review coverage. They introduce
no new quality threshold or deadline. Independent human review remains pending.

## Recorded collection commands

Commands are shown from the repository root. The `frozen_v1`, `run_v1`,
`frozen_v2` and `run_v2` paths below are **existing recorded artifacts**: do not
rerun these collection commands into them. A separate reproduction requires
new output directories, matching archived source and a fresh documented freeze.
The inference environment is `.venv`; plotting uses the pre-existing isolated
`/tmp/clara-step4-plots` environment without changing inference packages.

Offline workload coverage can be checked with a new output filename:

```bash
PYTHONPATH=src:scripts .venv/bin/python \
  evaluation/routing_overhead_20260912/validate_workload.py \
  --output /tmp/new-routing-workload-validation.json

OLINE_HRI_RUN_LIVE_QUALITY=0 OLINE_HRI_RUN_LIVE_LIFECYCLE=0 \
OLINE_HRI_RUN_LIVE_ROUTING=0 OLINE_HRI_RUN_LIVE_EMBEDDING=0 \
OLINE_HRI_RUN_LIVE_CAPTURE=0 PYTHONPATH=src:scripts \
  .venv/bin/python -m unittest discover -s tests
```

The original collection used these commands with its then-current v1 source:

```bash
PYTHONPATH=src:scripts .venv/bin/python scripts/run_routing_overhead.py freeze \
  --workload evaluation/routing_overhead_20260912/workload.json \
  --protocol evaluation/routing_overhead_20260912/protocol.md \
  --validation evaluation/routing_overhead_20260912/offline_validation.json \
  --output-dir evaluation/routing_overhead_20260912/frozen_v1

PYTHONPATH=src:scripts .venv/bin/python scripts/run_routing_overhead.py run \
  --workload evaluation/routing_overhead_20260912/frozen_v1/workload.json \
  --freeze evaluation/routing_overhead_20260912/frozen_v1/freeze.json \
  --output-dir evaluation/routing_overhead_20260912/run_v1
```

The v2 freeze and running continuation use:

```bash
PYTHONPATH=src:scripts .venv/bin/python scripts/run_routing_overhead.py freeze \
  --workload evaluation/routing_overhead_20260912/workload.json \
  --protocol evaluation/routing_overhead_20260912/protocol_v2.md \
  --validation evaluation/routing_overhead_20260912/offline_validation_v2.json \
  --output-dir evaluation/routing_overhead_20260912/frozen_v2

PYTHONPATH=src:scripts .venv/bin/python \
  evaluation/routing_overhead_20260912/continue_collection.py \
  --workload evaluation/routing_overhead_20260912/frozen_v2/workload.json \
  --freeze evaluation/routing_overhead_20260912/frozen_v2/freeze.json \
  --previous-root evaluation/routing_overhead_20260912/run_v1 \
  --previous-freeze evaluation/routing_overhead_20260912/frozen_v1/freeze.json \
  --output-dir evaluation/routing_overhead_20260912/run_v2
```

This read-only status command is safe while collection runs. It reports observed
progress and does not establish final artifact integrity or answer correctness:

```bash
.venv/bin/python evaluation/routing_overhead_20260912/collection_status.py \
  evaluation/routing_overhead_20260912/run_v2
```

## Planned final analysis and review commands

The final output paths below are **planned examples, not completed results**.
These commands perform offline reporting only, after collection. Use new output
directories; preserve any interim reports and review cohorts. The original
unreviewed v1 analyzer example is retained for provenance, but v1 alone is an
interrupted subset and is not the final comparison:

```bash
MPLCONFIGDIR=/tmp/clara-routing-mpl /tmp/clara-step4-plots/bin/python \
  scripts/analyze_routing_overhead.py analyze \
  --run-root evaluation/routing_overhead_20260912/run_v1 \
  --workload evaluation/routing_overhead_20260912/frozen_v1/workload.json \
  --freeze evaluation/routing_overhead_20260912/frozen_v1/freeze.json \
  --output-dir evaluation/routing_overhead_20260912/report_unreviewed_v1
```

The final combined analysis must use the mixed-freeze adapter:

```bash
MPLCONFIGDIR=/tmp/clara-routing-mpl /tmp/clara-step4-plots/bin/python \
  evaluation/routing_overhead_20260912/analyze_continued.py analyze \
  --run-root evaluation/routing_overhead_20260912/run_v2 \
  --workload evaluation/routing_overhead_20260912/frozen_v2/workload.json \
  --freeze evaluation/routing_overhead_20260912/frozen_v2/freeze.json \
  --previous-root evaluation/routing_overhead_20260912/run_v1 \
  --previous-freeze evaluation/routing_overhead_20260912/frozen_v1/freeze.json \
  --output-dir evaluation/routing_overhead_20260912/report_unreviewed_v2
```

Blinded semantic review is being organized in immutable `review_cohorts` using
[review instructions](review_instructions.md). For this continuation, use the
cohort adapter below instead of the historical v1 packet command in those
instructions. The adapter groups only identical question, history, rubric,
prepared/supplied evidence, citations, answer, delivery status and helper
constraint. It excludes model identity and timing. Every `--previous` argument
must name an existing packet, so already reviewed identical groups are retained
without regrading. Choose a new cohort directory; `cohort_final` is a planned
name and the shell glob below enumerates existing packets only:

```bash
.venv/bin/python evaluation/routing_overhead_20260912/prepare_review_cohort.py \
  --run-root evaluation/routing_overhead_20260912/run_v2 \
  --workload evaluation/routing_overhead_20260912/frozen_v2/workload.json \
  --previous evaluation/routing_overhead_20260912/review_cohorts/cohort*/packet.jsonl \
  --output-dir evaluation/routing_overhead_20260912/review_cohorts/cohort_final
```

Two separate blinded assistant contexts assess every new packet; preserve both
judgments as `reviewer_a.jsonl` and `reviewer_b.jsonl`. Reviewers must not read
private mappings, raw system records, timing reports or each other's judgments.
Use a third blinded context for disagreements, retaining its decisions in a
new adjudication file. The assembler checks exact final raw-answer/evidence
coverage and does not regrade answers. Omit `--adjudications` if none are needed;
the filename below is a planned artifact and must exist before use:

```bash
.venv/bin/python evaluation/routing_overhead_20260912/assemble_reviews.py \
  --cohort-root evaluation/routing_overhead_20260912/review_cohorts \
  --run-root evaluation/routing_overhead_20260912/run_v2 \
  --workload evaluation/routing_overhead_20260912/frozen_v2/workload.json \
  --adjudications evaluation/routing_overhead_20260912/review_cohorts/adjudications_final.jsonl \
  --output-dir evaluation/routing_overhead_20260912/reviews_final_v2
```

Only after every review ID is resolved, join judgments into the combined
analysis. This verifies both freezes and replay fidelity and produces core
CSV/JSON tables and figures:

```bash
MPLCONFIGDIR=/tmp/clara-routing-mpl /tmp/clara-step4-plots/bin/python \
  evaluation/routing_overhead_20260912/analyze_continued.py analyze \
  --run-root evaluation/routing_overhead_20260912/run_v2 \
  --workload evaluation/routing_overhead_20260912/frozen_v2/workload.json \
  --freeze evaluation/routing_overhead_20260912/frozen_v2/freeze.json \
  --previous-root evaluation/routing_overhead_20260912/run_v1 \
  --previous-freeze evaluation/routing_overhead_20260912/frozen_v1/freeze.json \
  --blind-dir evaluation/routing_overhead_20260912/reviews_final_v2/blind \
  --reviews evaluation/routing_overhead_20260912/reviews_final_v2/resolved.jsonl \
  --output-dir evaluation/routing_overhead_20260912/report_reviewed_v2

/tmp/clara-step4-plots/bin/python \
  evaluation/routing_overhead_20260912/report_details.py \
  --run-root evaluation/routing_overhead_20260912/run_v2 \
  --workload evaluation/routing_overhead_20260912/frozen_v2/workload.json \
  --freeze evaluation/routing_overhead_20260912/frozen_v2/freeze.json \
  --previous-root evaluation/routing_overhead_20260912/run_v1 \
  --previous-freeze evaluation/routing_overhead_20260912/frozen_v1/freeze.json \
  --blind-dir evaluation/routing_overhead_20260912/reviews_final_v2/blind \
  --reviews evaluation/routing_overhead_20260912/reviews_final_v2/resolved.jsonl \
  --output-dir evaluation/routing_overhead_20260912/report_details_final_v2
```

The supplementary details retain backend token counts for rejected answers,
per-pattern/per-repetition totals, cold/transition/following-turn rows, selected
versus actual DDEE traces and placement diagnostics. They supplement the core
disjoint timing audit and dependent-sequence analysis. Final reporting still
requires the terminal batch record, source/model/host and cleanup verification,
resolved review coverage and the checks in `report_acceptance.json`. Faster
execution or valid delivery alone does not establish a useful-answer gain.
