# Frozen fresh holdout — pending resource admission

Sixteen independently authored cases are sealed in `cases.json`. The author did
not see production implementation, previous prompts or outputs. Root first
opened them after the final candidate freeze, as recorded in
[`../holdout_opening.json`](../holdout_opening.json). No runtime or test edits
have followed that opening. Offline validation passed.

**Inference attempts: zero. Quality and latency: unmeasured.** The earlier
48-case known replay hit the existing runtime memory floor on its last case.
Cleanup unloaded all models. The subsequent read-only admission check found
788 MiB swap usage, above the unchanged 768 MiB start ceiling. RAM, temperature
and the other measured start conditions had recovered; swap had not.
[`readiness_checks.jsonl`](readiness_checks.jsonl) preserves admission readings.

No model/service/device setting has been changed to force admission. Closing an
unrelated desktop app requires user authorization and is pending. Once the
existing gate passes, the prepared command is:

```bash
.venv/bin/python evaluation/answer_repair_20260916/run_guarded.py \
  --cases evaluation/answer_repair_20260916/fresh_holdout/cases.json \
  --output-dir evaluation/answer_repair_20260916/fresh_holdout/collection \
  --candidate-manifest evaluation/answer_repair_20260916/fresh_holdout/candidate_freeze.json \
  --max-cases 16
```

Keep the candidate, case order, prompts and rubrics unchanged. Preserve any
unsuccessful attempt. After collection, produce sanitized review packets for
reviewers A/B, retain both reviews, explicitly adjudicate differences, analyze
all 16 planned cases, independently audit the measurements, and append the
fresh outcome to the repair report. A missing fresh run is not a 0/16 score and
must not be represented as completed validation.
