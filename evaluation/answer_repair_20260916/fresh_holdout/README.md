# Fresh16 first attempt — resource failure retained

The frozen 16-case cohort ran once on 17 September 2026. All original prompt,
history and rubric records were retained, with no source or test changes after
the final candidate freeze or holdout opening. Startup passed the unchanged
device limits at approximately 3.01 GiB available RAM, 728.75 MiB swap use and
48.781°C maximum measured temperature. No apps, swap or device settings were
changed before this first attempt.

**Delivered-task results: final routing 8/16, full quality 0/16, combined 0/16.**
Eight cases recorded execution errors and eight delivered only a generic
application clarification. There were no delivered model-generated answers.
Both independent blinded assistant reviewers agreed on all quality, usefulness
and required-component booleans; useful general content was 0/12 applicable
tasks. Original reviews are [A](review_a.json) and [B](review_b.json); the
[review method](review_method.md) and [adjudication record](adjudication.json)
retain their independence and show that no score disagreement required resolution.
These are assistant judgments, not human validation.

## What failed

The first case produced one raw candidate answer successfully. During its
answer review, the guard observed swap above the unchanged 1 GiB runtime ceiling.
That guard failure remained latched. Later model work was rejected by the guard;
some conversation paths returned an application clarification and others
recorded an execution error. All planned attempts remain in the denominator.
The result does not measure clean-run model quality on these tasks.

There were 25 recorded client/API attempts: 16 generation attempts, one answer
review and eight dependency reviews. **One completed successfully; 24 recorded
guard errors.** An attempt record is not proof that the backend executed model
inference. Exactly one completed raw backend generation is evidenced, and no
generated answer was delivered. The backend total for that completed generation
was 26.955 seconds, including 22.886 seconds loading the model.

The [finish record](collection/finish.json) reports
`SafetyGateError: telemetry swap ceiling crossed`, `complete:false`, successful
cleanup and no remaining resident model. Sixty-three telemetry samples recorded
maximum swap 1,026 MiB and maximum temperature 52.406°C. The first above-ceiling
sample was number 59, 29.389 seconds after the first telemetry sample; five
samples exceeded the ceiling. The independent [audit](independent_audit.json)
passed **258/260 checks**. Its two failures are the guard/finalization outcome
and sampled runtime swap bound; artifact, source, model, corpus and arithmetic
checks passed. The failed checks remain explicit. Exact operational details
are in [guard_audit_details.json](guard_audit_details.json).

## Timing of the failed attempt

| Group | n | Median seconds | p95 seconds |
| --- | ---: | ---: | ---: |
| All recorded attempts, including errors | 16 | 0.074 | 7.551 |
| Application-only deliveries | 8 | 0.119 | 19.381 |
| Delivered generated answers | 0 | unmeasured | unmeasured |
| Full-quality outcomes | 0 | unmeasured | unmeasured |

These describe rapid guard rejection after the first 29.733-second case. They
must not be used as a useful-response speed claim. Quantiles use linear
interpolation at `(n-1)*q`. Exact [metrics](metrics.json), [per-case records](per_case.jsonl),
[delivered answers](answers.md), [raw observations](collection/run/observations.jsonl)
and withheld attempts remain available.

## Follow-up

The user then approved idle-app cleanup and temporary swap reset. The separately
preregistered [recovery replay](../fresh_recovery_v1/README.md) completed all 16
cases with unchanged source, case bytes/order, rubrics, models and device limits.
It passed the independent audit 260/260, with no execution errors or guard
violations: final routing 12/16, full quality and combined success 4/16. Both
reviewers agreed. All 16 recovery deliveries contained generated text, with
4.684-second median and 13.566-second p95 turn latency. Peak swap was 276 MiB
and temperature 59.875°C; cleanup unloaded all models.

The original fresh failure above remains unchanged and separate. Recovery used
now-observed inputs, not a new holdout. The clean bounded execution completes
the requested operational check, but neither erases the failures nor establishes
long-duration stability or broad answer quality. One recovery answer invented
an unsupported personal recollection; the independent judgment records it.

The earlier pending-state README is preserved under
[`../pre_completion_snapshot/`](../pre_completion_snapshot/). Historical
`pending_status.json` and `readiness_checks.jsonl` remain unchanged; resumed
readiness is in `resumed_readiness_checks.jsonl`. The candidate was frozen before
root first opened the independently authored cases, as recorded in
[`../holdout_opening.json`](../holdout_opening.json).
