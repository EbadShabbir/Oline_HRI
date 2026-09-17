# Router and answer repairs — 16–17 September 2026

The requested fresh attempt, two independent reviews, measurement audits and
a **clean 16-case recovery run are complete**. The recovery finished with no
execution errors or guard violations: **12/16 correct final routes, 4/16
full-quality answers and 4/16 combined successes**. All 16 deliveries included
generated text, taking **4.684 seconds median / 13.566 seconds p95**. Both
reviewers agreed on every scored boolean; the independent recovery audit passed
**260/260 checks**. Exact results and remaining failures are in the
[recovery report](fresh_recovery_v1/README.md). Clean execution does not establish
release readiness: one response invented a personal recollection.

The repaired candidate produces substantially more complete answers on the
known cases. On the 43 unchanged inputs that reached inference in the original
evaluation, strict answer quality increased from **4/43 to 20/43** and combined
routing-and-answer success from **4/43 to 19/43**. Final routing decreased from
**36/43 to 35/43**, including one new execution error. These are development
and regression measurements; fresh generalization is not established yet.

All 48 planned replay attempts were recorded and independently reviewed. The
last attempt hit the existing available-memory floor. Models were unloaded,
but the run is **operationally unsuccessful**, and its analyzer correctly
records `evaluation_complete: false`. On 17 September the device passed the
unchanged start gates and the separately authored **16-case fresh attempt ran**,
but crossed the 1 GiB runtime swap ceiling during the first answer's review.
All 16 outcomes were retained: **8/16 final routes, 0/16 full-quality answers,
eight errors and eight application clarifications**. Both independent reviewers
agreed. This is an operationally failed first attempt, with no delivered
generated answer; its tiny aborted-turn latencies do not measure useful answer
performance. See the [fresh report](fresh_holdout/README.md).

## What changed

- Route bounded, self-contained tasks using supplied data and admitted draft
  context. Keep the learned classifier's original scores in the trace and use
  an exact four-mode fallback review for remaining uncertain requests.
- Select generator size with an explicit policy, removing the separate
  model-size inference call. Substantive tasks use the configured 1.7B model;
  the 0.6B model remains configured for brief social turns.
- Generate recognized line, bullet, sentence and CSV tasks as bounded structured
  parts, with application rendering and validation. Validate conservative exact
  counts and requested words. Use application-computed minute allocations for
  eligible practical plans; these enforce totals, not semantic plan quality.
- Accept LF in user requests and validated answers while retaining other
  control-character checks. Normalize LF only for retrieval backend queries;
  preserve the original request and stored evidence.
- Improve missing-detail questions, admitted-draft edits, assistant-guess
  handling, and separation of independent general help from unavailable recall.
  Preserve evidence authorization, source checks, bounded retries and raw output
  provenance. Wrong or incomplete answers can still pass the model reviewer.

No model tags, embedding assets, context/output budgets, temperature, power
mode, fan settings or resource limits were changed. For the separately recorded
recovery, the user authorized closing idle software-management apps and
temporarily cycling existing swap devices. Their original sizes and priorities
were restored; no persistent swap configuration changed. The final
source was frozen **before root opened the fresh holdout**, and no production
or test source has changed since. The [candidate archive](final_candidate/)
contains exact source, tests and the working diff.

## Known replay results

| Population | Final routing | Full answer quality | Both |
| --- | ---: | ---: | ---: |
| Original 48 attempts, including five input-validation failures | 36/48 | 4/48 | 4/48 |
| Repaired 48 attempts, including one resource-aborted attempt | 37/48 | 22/48 | 21/48 |
| Original 43 valid inputs, matched subset | 36/43 | 4/43 | 4/43 |
| Repaired same 43 inputs, retaining the new error | 35/43 | 20/43 | 19/43 |

The five originally rejected LF inputs now execute without that setup failure;
two pass all criteria. They are newly covered inputs, not five paired model
improvements. Original prompts, declared histories and rubrics are byte-for-byte
unchanged. The original whitespace-only follow-up remains separate.

The [matched comparison with collection status](known_replay/matched_with_operational_status/matched_comparison.json)
records 18 quality gains, two regressions, two retained passes and 21 retained
failures. Its separate [independent arithmetic audit](known_replay/matched_independent_audit.json)
passed 158/158 checks. Both the first comparison and its later status-explicit
version are preserved; their paired rows are identical.

| Expected mode | Cases | Correct final route | Full quality | Both |
| --- | ---: | ---: | ---: | ---: |
| General/current input (`none`) | 20 | 20 | 8 | 8 |
| Optional personalization | 8 | 5 | 3 | 2 |
| Required personal/mixed recall | 14 | 11 | 10 | 10 |
| Clarification | 6 | 1 | 1 | 1 |

Useful general content was delivered in **23/34** applicable cases, a looser
criterion than completing the whole request. Sixteen cases had a correct final
route but failed full answer quality. One complete optional-personalization
answer (`fresh_021`) had the wrong final route, explaining the difference
between 22 quality passes and 21 combined passes.

Two independent assistant reviewers agreed on strict quality for 47/48 cases.
Root adjudicated the single strict disagreement and three component/usefulness
disagreements using the frozen rubrics. Reviewers saw requests, declared
context, rubrics and delivered text/error status, with source, model identity,
routes, runtime verdicts and timing withheld. Root was not blinded. These are
assistant reviews, not human validation or a population estimate. Original
reviews and [adjudication decisions](known_replay/adjudication.json) remain
available alongside [every delivered answer](known_replay/answers.md).

## Latency and execution

All numbers below are complete text-turn wall time, including the launcher
checks. Percentiles use linear interpolation at `(n-1)*q`. Application replies
can include failed or withheld model attempts and are not necessarily cheap.

| Repaired 48-case replay group | n | Median seconds | p95 seconds |
| --- | ---: | ---: | ---: |
| All attempts, including the error | 48 | 5.207 | 12.157 |
| Delivered generated text | 30 | 5.207 | 8.281 |
| Application-only delivery | 17 | 5.854 | 15.412 |
| Full-quality outcomes | 22 | 4.106 | 7.356 |
| Combined successes | 21 | 4.043 | 7.283 |

On the matched 43 inputs, overall median/p95 changed from **38.207/81.883 s**
to **5.377/12.693 s**. The original 24 generated deliveries had median/p95
43.569/84.929 s; delivery populations differ, so that is not a paired generated
answer comparison. Historical sessions, warm/cold state, and unpinned execution
placement prevent attribution of a causal speedup. Quality and error accounting
remain necessary: a quick generic question is not task completion.

All 22 strict-quality outcomes arrived within ten seconds; 16 contained
generated text. There were **106 actual model calls**: 52 answer generations,
36 answer reviews and 18 dependency reviews, all using `qwen3:1.7b` in this
cohort. One dependency-review attempt was interrupted; 105 calls completed.
There were no compute-classifier calls, fabricated small-model generations or
call-bound violations. [Metrics](known_replay/metrics.json) retain backend load
and call durations separately from turn wall time.

The last case, `fresh_043`, was interrupted after 0.484 seconds by the existing
768 MiB available-memory runtime floor. The exact failing `MemAvailable` reading
was not persisted, so it is not reconstructed from the different tegrastats RAM
measure. Sampled maximum swap was 788 MiB and temperature 63.406 °C. Cleanup
succeeded with no resident models. This is a real resource failure, not a clean
release pass. The [finish record](known_replay/collection/finish.json) is retained.

## Development and verification

The same 12 known cases were used in three separately archived iterations:

| Iteration | Final routing | Full quality / both | Overall median / p95 seconds |
| --- | ---: | ---: | ---: |
| [v1](development_v1/README.md) | 4/12 | 1/12 | 4.031 / 16.084 |
| [v2](development_v2/README.md) | 12/12 | 5/12 | 19.426 / 48.528 |
| [v3](development_v3/README.md) | 12/12 | 8/12 | 7.515 / 31.120 |

V1 exposed an ineffective routing review and a prompt-wiring omission. V2
retained one handled retrieval error on an LF query. V3 corrected retrieval
normalization and added structured parts and bounded allocation handling, but
still failed item destinations, complete preparation, an invitation and a
treasure-hunt plan. Earlier attempts and audit corrections remain preserved.
Each development iteration used one blinded independent assistant reviewer plus
root assessment; the final replay used two reviewers. The 12-case score is not
substituted for the later 48-case result, whose generated outputs can differ.

The final full offline suite passed: **1,440 tests run, 26 skipped, no failures
or errors**, in 113.441 seconds of test execution. All live opt-ins were
disabled, and source/tests were unchanged during the run. See the
[log](full_offline_checks_v4.log), [status](full_offline_checks_v4.status.json),
and [earlier check corrections](offline_check_corrections.md). No extra broad
test run was needed for documentation changes after the source freeze.

The [independent known-replay audit](known_replay/independent_audit.json)
passed **348/349 checks**; its only failure
is the guard/finalization outcome. Source, raw artifacts, model digests, grading
arithmetic, empty memory and evidence boundaries verify. The failed operational
check is retained rather than waived. Development audits and their failed first
attempts are also preserved.

## Clean recovery and remaining limitations

The fresh 16-case attempt has both blinded reviews and an independent audit:
258/260 checks passed, with guard/finalization and sampled swap-limit failures
retained. The separate [operational recovery replay](fresh_recovery_v1/README.md)
then completed all 16 cases using the exact same source, case bytes, order,
rubrics and limits. Its audit passed 260/260 checks; the approved cleanup audit
passed 45/45. Peak sampled swap was 276 MiB and temperature 59.875°C, with no
guard violation, cleanup error or remaining resident model. This verifies that
bounded run; it neither erases previous failures nor establishes long-duration
stability. The recovery used now-observed cases and is not a new holdout.

Both recovery reviewers agreed on 4/16 complete answers and 10/12 useful general
components. Failures include exact-format omissions, an unusable draft edit,
an incorrect day/night explanation, all three unresolved-target/unit requests,
and an invented cushion-pattern recollection. Raw classifier agreement was
14/16, but final routing was 12/16 after downstream decisions. In case 011 the
route changed from required recall to no-memory, retrieval was skipped, and the
runtime answer reviewer incorrectly approved the fabricated recollection.
The independent judgment retains that failure. These are concrete priorities
for a future repair; no production or test edits followed the holdout opening.

The known replay exposes substantial remaining failures: unresolved referents
are often answered without clarification, optional fallbacks can be withheld,
exact formats remain imperfect, and plans can allocate time correctly while
omitting items or giving impossible instructions. Another repair cycle would
need a newly authored holdout; the present 16 cases have now been observed and
cannot become fresh evidence again after further tuning.

Microphone/transcription, audio latency, automatic memory capture and a new
populated-memory live validation were outside this text evaluation. Existing
offline evidence and lifecycle checks remain in the passing suite. This report
does not establish a broad quality, release-readiness or voice-responsiveness
claim.

## Artifacts and reproduction

The [protocol](protocol.md), [holdout-opening record](holdout_opening.json),
candidate archives and per-cohort evaluation seals establish the sequence.
Original evaluation artifacts remain unchanged. Because its manifest included
the mutable repository `results.md`, its exact original index bytes are archived
as [baseline_results_snapshot.md](baseline_results_snapshot.md); the
[preservation note](baseline_preservation_note.md) documents the later index
append rather than modifying the historical seal.

The historical [progress manifest](progress_manifest.json) records the original
pending state. The exact four documents subsequently updated are preserved in
[pre_completion_snapshot/manifest.json](pre_completion_snapshot/manifest.json),
so all 1,150 earlier hashes remain independently verifiable through explicit
snapshot mappings. The subsequent 1,354-artifact
[fresh-attempt manifest](fresh_attempt_manifest.json) is also unchanged, with
its five later-updated documents preserved in
[pre_recovery_completion_snapshot/manifest.json](pre_recovery_completion_snapshot/manifest.json).
The [completion manifest](completion_manifest.json) records the final results
and verifies these preservation mappings. Its completion status refers to the
requested evaluation work, not a release-quality pass. Original failed cohorts
retain their unsuccessful operational status.

Run analysis only from the repository root; it makes no inference calls:

```bash
.venv/bin/python evaluation/answer_repair_20260916/analyze.py \
  --cases evaluation/answer_repair_20260916/known_replay/cases.json \
  --collection evaluation/answer_repair_20260916/known_replay/collection \
  --judgments evaluation/answer_repair_20260916/known_replay/adjudicated_judgments.json \
  --candidate-manifest evaluation/answer_repair_20260916/known_replay/candidate_freeze.json \
  --freeze-manifest evaluation/answer_repair_20260916/known_replay/evaluation_freeze.json \
  --expected-count 48 --output-dir /tmp/oline-repair-reanalysis
```

The guarded live launcher requires a new output directory, matching source and
case hashes, exclusive inference leases, no resident model, and all established
resource checks. Re-running known cases would be a new attempt and cannot
replace the preserved resource-aborted replay.
