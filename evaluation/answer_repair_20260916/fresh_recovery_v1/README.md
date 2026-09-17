# Recovery evaluation complete — 17 September 2026

The prepared 16-case recovery replay completed cleanly after the user-approved
memory cleanup. **Final routing matched 12/16, full answer quality passed 4/16,
and combined success passed 4/16.** All 16 cases delivered generated text with
zero execution errors, no resource-guard violation and successful model cleanup.
The independent measurement/integrity audit passed **260/260 checks**. These
results complete the requested bounded clean-run check; answer quality remains
insufficient for a broad release-readiness claim.

The source, tests, case bytes, order, declared histories, rubrics, model tags,
embedding assets, generation settings and device limits were unchanged from
the original frozen candidate. The original fresh attempt remains preserved
separately with 0/16 complete answers under a swap-guard abort. This recovery
uses now-observed prompts, not a newly authored independent holdout. Its scores
and latency are neither substituted for nor pooled with that first attempt.

## Quality and routing

| Expected mode | Cases | Raw classifier matches | Final route matches | Full quality / combined |
| --- | ---: | ---: | ---: | ---: |
| General/current input | 8 | 7 | 8 | 2 |
| Optional personalization | 2 | 2 | 2 | 0 |
| Required personal/mixed recall | 3 | 3 | 2 | 2 |
| Clarification | 3 | 2 | 0 | 0 |
| Total | 16 | 14 | 12 | 4 |

Both independent assistant reviewers agreed on every full-quality, usefulness
and required-component boolean. Complete successes were cases 002 (fixed
rehearsal timeline), 008 (two-line kite story), 012 (unavailable motto recall
plus a general definition), and 013 (unavailable comic reader plus a generic
proofreading checklist). Useful general content appeared in **10/12** applicable
cases; that looser standard does not imply that all requirements were satisfied.

The main failures were:

- Missing requested numbering/card detail, CSV header, number-only or name-only
  output, and an incomplete paper-fan procedure.
- A draft edit that lost its essential announcement facts, an incorrect causal
  day/night explanation, and multiple activity suggestions where one actionable
  activity was requested.
- All three required-clarification cases: the target label, pronoun referent and
  conversion units were not resolved.
- **Unsupported personal recall in case 011.** With an empty memory store, the
  response claimed the user chose “a floral print with geometric accents.” The
  raw classifier selected required recall, but the dependency review changed
  the final route to no-memory; retrieval was skipped and no evidence IDs were
  supplied. The answer reviewer incorrectly returned `supported_answer`.
  Independent quality remains false. Clean resource execution does not validate
  this unsupported personal claim.

Review packets withheld source, model identity, timing, routing and runtime
verdicts. Reviewers had seen the prompts in the earlier aborted attempt; this
repeat-prompt limitation is explicit. Root retained reviewer A rows only where
all scored booleans agreed, preserving both originals. No scored disagreement
needed adjudication. These are assistant reviews, not human validation.
See [review method](review_method.md), [adjudication](adjudication.json), and
[all delivered answers and reasons](answers.md).

## Latency and calls

| Complete text-turn wall-time group | n | Median seconds | p95 seconds |
| --- | ---: | ---: | ---: |
| All attempts / delivered generated answers | 16 | 4.684 | 13.566 |
| Full-quality outcomes / combined successes | 4 | 4.112 | 7.591 |
| Application-only replies | 0 | not applicable | not applicable |

Three full-quality outcomes arrived within five seconds and all four within ten
seconds, out of all 16 planned cases. Mean turn time was 6.277 seconds; the first
case took 27.282 seconds and the complete runner took 100.798 seconds. The cold
start remains included. Percentiles use linear interpolation at `(n-1)*q` and
are descriptive for this small cohort. No causal speedup or voice-latency claim
is made, and the aborted first attempt's tiny failure latencies are not a
performance baseline.

All **41 recorded model calls completed**: 17 answer generations, 16 answer
reviews and eight dependency reviews, all using the configured `qwen3:1.7b`.
Only case 010 retried generation. There were no compute-classifier calls or
per-case call-bound violations. Backend durations total 96.791 seconds,
including 20.142 seconds of model load; call wall totaled 97.503 seconds and
case wall 100.437 seconds. These are nested scopes, not additive costs.
[Metrics](metrics.json) and [per-case records](per_case.jsonl) preserve exact
numbers, raw modes, delivered outputs, reviews and attempt provenance.

## Approved cleanup and clean device run

The user explicitly approved closing idle Software Center/Software Updater and
temporarily resetting existing swap. Package transactions were confirmed idle,
no models were resident, and only the two approved apps were closed. The
normal `pkexec` administrator authorization ran the bounded cleanup helper;
credentials were not supplied through chat or command arguments.

All six existing zram devices were cycled one at a time and restored with their
original **650,264 KiB sizes and priority 5** (3,901,584 KiB total). The helper
checked RAM headroom and restored disabled devices in finally blocks; four
offline injected-success/failure/interruption/headroom checks verified those
paths. No persistent swap, fan, power, model or guard configuration changed.
The independent [cleanup audit](independent_cleanup_audit.json) passed **45/45**.
See [authorization and scope](cleanup_authorization_and_scope.json),
[app cleanup](approved_app_cleanup.json), [swap action log](swap_reset.log), and
[post-cleanup admission](post_cleanup_readiness.json).

The live run started with 2,308,424 KiB available RAM, zero swap used, maximum
measured temperature 50.531°C, no resident model, running fan, 15W mode 0 and
zero thermal-trip counters. All unchanged admission checks passed. During the
run, **200 samples** recorded peak swap **276 MiB** (limit 1,024 MiB) and peak
temperature **59.875°C** (limit below 68°C). The existing available-memory guard
reported no violation. The minimum tegrastats total-minus-used proxy was
1,177 MiB; this is not an exact `MemAvailable` minimum, which was not persisted.

The [finish record](collection/finish.json) has exit code 0, `complete:true`, no
guard violation, no cleanup errors and no remaining resident models. The
[independent audit](independent_audit.json) passed 260/260 checks covering raw
artifacts, source/tests/seals, model identities, prompt boundaries, empty memory,
four successful empty retrievals, call bounds, arithmetic, timing and resources.
[Recovery audit details](recovery_audit_details.json) retain the unsupported
personal-recall trace separately from the operational pass.

This proves clean execution for this bounded 16-case session. It does not erase
the previous 48- and 16-case guard failures or establish long-duration stability.

## Preservation and reproducibility

The [recovery protocol](../recovery_protocol.md) and this cohort's
[evaluation seal](evaluation_freeze.json) were created before recovery inference.
The protocol's then-pending permission is superseded by the later explicit
approval record; the frozen protocol itself is unchanged. Original fresh cases,
attempts, reviews, audit failures and seals are intact. Pre-approval documents
are preserved in [the snapshot manifest](../pre_recovery_completion_snapshot/manifest.json).
No production or test file changed after the holdout was opened. The passing
1,440-test offline suite remains applicable to the identical frozen candidate;
this resumption added only evaluation/cleanup/report artifacts.

The recovery launcher used `--max-cases 16` with this directory's `cases.json`,
`candidate_freeze.json` and a new `collection` directory. Reanalysis requires
`analyze.py --expected-count 16` and the explicit case, collection, judgment,
candidate and evaluation-freeze paths. The independent auditor uses
`--cohort-kind known_replay`, accurately labeling these now-observed inputs.
Never overwrite an existing collection or independent audit to rerun a result.
