# Prepared operational recovery replay — not started

One 16-case replay is prepared under the [recovery protocol](../recovery_protocol.md).
Source 48/48 and tests 104/104 exactly match the final freeze. Case bytes, order,
declared histories and rubrics exactly match the original fresh16 cohort. The
new seal explicitly records that these are now-observed inputs, not a new
holdout. Offline validation passed. No inference has started.

The first fresh attempt crossed the runtime swap ceiling. All original outcomes
and its two failed operational audit checks remain preserved. Recovery awaits
authorization for the proposed idle-app/swap cleanup and ordinary admission
under unchanged limits. The prepared command is:

```bash
.venv/bin/python evaluation/answer_repair_20260916/run_guarded.py \
  --cases evaluation/answer_repair_20260916/fresh_recovery_v1/cases.json \
  --output-dir evaluation/answer_repair_20260916/fresh_recovery_v1/collection \
  --candidate-manifest evaluation/answer_repair_20260916/fresh_recovery_v1/candidate_freeze.json \
  --max-cases 16
```

After collection, independently review and audit this attempt separately using
`--cohort-kind known_replay`. A clean 16-case run would verify this bounded
execution only, not erase previous guard failures or establish longer-term
stability. Do not change source, cases, model settings or device limits.
