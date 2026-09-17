# Reproduction commands

Run from the repository root. These tools never alter earlier cohorts. Choose
a new development directory for each attempt. Do not open `holdout_authoring`
until the final source is frozen. The commands below assume development v1;
substitute the actual new cohort directory consistently for later iterations.

## Offline harness checks

```bash
.venv/bin/python -m unittest discover \
  -s evaluation/quality_repair_20260917 -p 'test_*.py' -v
```

## Known sixteen-case development

Freeze and preregister after production edits and suitable offline checks:

```bash
.venv/bin/python evaluation/quality_repair_20260917/freeze_candidate.py \
  --output-dir evaluation/quality_repair_20260917/development_v1 \
  --cases evaluation/quality_repair_20260917/known_cases.json
.venv/bin/python evaluation/quality_repair_20260917/seal_evaluation.py \
  --cohort-dir evaluation/quality_repair_20260917/development_v1 \
  --scope 'Known sixteen-case quality-repair development replay; all cases previously observed.' \
  --artifact ../protocol.md --artifact ../review_plan.md \
  --artifact ../analyze.py --artifact ../audit_results.py \
  --artifact ../review_packet.py --artifact ../harness_origin.json
```

Optional offline startup verification uses its own directory and never reaches
Ollama, device probes or inference:

```bash
.venv/bin/python evaluation/quality_repair_20260917/run_guarded.py \
  --cases evaluation/quality_repair_20260917/development_v1/cases.json \
  --candidate-manifest evaluation/quality_repair_20260917/development_v1/candidate_freeze.json \
  --max-cases 16 --validate-only \
  --output-dir evaluation/quality_repair_20260917/development_v1/offline_validation
```

The following is live inference and requires the normal tool execution approval
for local service/device access. Admission gates and exclusive leases must pass:

```bash
.venv/bin/python evaluation/quality_repair_20260917/run_guarded.py \
  --cases evaluation/quality_repair_20260917/development_v1/cases.json \
  --candidate-manifest evaluation/quality_repair_20260917/development_v1/candidate_freeze.json \
  --max-cases 16 \
  --output-dir evaluation/quality_repair_20260917/development_v1/collection
```

## Freeze the final candidate before opening new cases

After all planned development edits and offline checks, freeze source without
`--cases`. Do not make further production/test edits for this candidate:

```bash
.venv/bin/python evaluation/quality_repair_20260917/freeze_candidate.py \
  --output-dir evaluation/quality_repair_20260917/final_candidate
```

Only now use the two exact hashes supplied by the independent author. Replace
`AUTHOR_CASES_SHA256` and `AUTHOR_NOTES_SHA256` below with those values; do not
read or recompute hashes from author content before freezing the final source.
This command validates source/test equality first, records opening even if
authored schema validation subsequently fails, and binds the new corpus without
changing the final freeze:

```bash
.venv/bin/python evaluation/quality_repair_20260917/prepare_holdout.py \
  --final-candidate evaluation/quality_repair_20260917/final_candidate \
  --authoring-dir evaluation/quality_repair_20260917/holdout_authoring \
  --cases-sha256 AUTHOR_CASES_SHA256 --notes-sha256 AUTHOR_NOTES_SHA256 \
  --output-dir evaluation/quality_repair_20260917/fresh_holdout
.venv/bin/python evaluation/quality_repair_20260917/seal_evaluation.py \
  --cohort-dir evaluation/quality_repair_20260917/fresh_holdout \
  --scope 'Independent twenty-case holdout; source frozen before first semantic case read.' \
  --artifact ../protocol.md --artifact ../review_plan.md \
  --artifact ../analyze.py --artifact ../audit_results.py \
  --artifact ../review_packet.py --artifact ../prepare_holdout.py \
  --artifact ../holdout_opening.json --artifact holdout_preparation.json \
  --artifact authoring_notes.md --artifact preopening_candidate_freeze.json
.venv/bin/python evaluation/quality_repair_20260917/run_guarded.py \
  --cases evaluation/quality_repair_20260917/fresh_holdout/cases.json \
  --candidate-manifest evaluation/quality_repair_20260917/fresh_holdout/candidate_freeze.json \
  --max-cases 20 \
  --output-dir evaluation/quality_repair_20260917/fresh_holdout/collection
```

## Independent reviews and arithmetic audit

Create a packet after collection, then give that packet and `review_plan.md` to
two independent reviewers. Each saves a separate immutable judgment file; do
not fabricate or infer scores from the runtime reviewer. Preserve disagreements
and root's explicit adjudication separately. This example uses development v1;
for the fresh cohort substitute `fresh_holdout` and use `--expected-count 20`
and `--cohort-kind fresh_holdout` in the later commands:

```bash
.venv/bin/python evaluation/quality_repair_20260917/review_packet.py \
  --cases evaluation/quality_repair_20260917/development_v1/cases.json \
  --observations evaluation/quality_repair_20260917/development_v1/collection/run/observations.jsonl \
  --output evaluation/quality_repair_20260917/development_v1/review_packet.json
.venv/bin/python evaluation/quality_repair_20260917/analyze.py \
  --cases evaluation/quality_repair_20260917/development_v1/cases.json \
  --collection evaluation/quality_repair_20260917/development_v1/collection \
  --judgments evaluation/quality_repair_20260917/development_v1/adjudicated_judgments.json \
  --candidate-manifest evaluation/quality_repair_20260917/development_v1/candidate_freeze.json \
  --freeze-manifest evaluation/quality_repair_20260917/development_v1/evaluation_freeze.json \
  --source-root evaluation/quality_repair_20260917/development_v1/candidate_source \
  --expected-count 16 --output-dir evaluation/quality_repair_20260917/development_v1
.venv/bin/python evaluation/quality_repair_20260917/audit_results.py \
  --cohort-dir evaluation/quality_repair_20260917/development_v1 \
  --cohort-kind development \
  --source-root evaluation/quality_repair_20260917/development_v1/candidate_source
```

The analysis explicitly uses the archived source for reproducible historical
verification. The independent audit refuses to overwrite an existing result;
use a new `--output` when preserving a corrected subsequent audit. Report failed
operational checks unchanged. Neither command makes inference calls. A clean
audit verifies measurement integrity and arithmetic, not substantive answer
quality beyond the independent saved judgments.
