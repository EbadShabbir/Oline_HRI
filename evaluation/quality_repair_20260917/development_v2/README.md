# Known sixteen-case quality repair — development v2

This attempt **did not complete cleanly**. The existing available-memory floor interrupted case 012; cases 013–016 were not attempted. Across all **16 planned cases**, final routing is **11/16**, strict answer quality **9/16**, and combined success **9/16**. There are twelve recorded outcomes, including one execution error, and four missing outcomes. Neither execution nor evaluation completion is claimed.

Two independent reviewers agree on all twelve recorded quality/usefulness fields and all 22 required-component booleans: **9/12 recorded outcomes** pass strict quality and **9/11 recorded general-component cases** supply useful content. Those observed-only fractions are not replacements for the planned-case results. With the missing general case retained, useful content is **9/12 planned general-component cases**. Four unattempted cases have no fabricated reviewer judgments. [Aggregation](adjudication.json) retains the original [A](review_a.json)/[B](review_b.json) reviews and records one descriptive content-error flag resolution for case 007; no scored boolean changed.

| Expected mode | Planned | Correct final route | Full quality / both |
| --- | ---: | ---: | ---: |
| none | 8 | 8 | 6 |
| optional | 2 | 2 | 2 |
| required | 3 | 1 | 1 |
| clarify | 3 | 0 | 0 |

The paper-fan instructions (004) and integer arithmetic (005) now pass their frozen requirements. The retained raw expression for 005 is `(7 * 4) + 3`; the independent auditor recomputes the delivered integer **31** from current-request operands. Numbering, literal formatting and public-reference provenance also verify.

Two delivered answers still fail: case 001 returns a generic rephrase question instead of the fully specified display plan; case 007 names axial rotation but omits the required sunlight-facing versus away-from-sunlight mechanism. Case 012 delivers no answer because of the guard failure. Cases 013–016 are missing, rather than successful, failed model answers, or assumed retained passes. [Every outcome](answers.md) and the [metrics](metrics.json) preserve those distinctions.

| Text-turn latency group | Measured n | Median seconds | p95 seconds |
| --- | ---: | ---: | ---: |
| Recorded attempts, including error | 12 | 5.403 | 20.754 |
| Generated delivery | 9 | 5.455 | 8.562 |
| Application-only delivery | 2 | 17.771 | 33.709 |
| Full-quality outcomes | 9 | 5.455 | 8.562 |

All four unattempted cases have missing latency; no zero or synthetic duration is substituted. Wall time includes guard overhead; percentiles use linear interpolation at `(n-1)*q`. The first case took 35.479 seconds before an application fallback. Observed-only timing from this aborted run is not clean full-cohort performance evidence or a causal speed comparison.

There were **25 actual model calls**: twelve answer-generation attempts, nine answer reviews and four dependency reviews, all `qwen3:1.7b`; 24 completed and one errored. Nine deliveries contain generated text and two are application-only. There are no fabricated compute calls or call-bound violations.

The runtime stopped at the unchanged **768 MiB available-memory floor**. The exact triggering `MemAvailable` value was not persisted and is not reconstructed from the different tegrastats free-RAM measure. Telemetry retained **183 samples**, with sampled peak swap **735 MiB** and temperature **56.125 C**. Sampled free RAM bottomed at 1,002 MiB, which does not negate the separately recorded available-memory guard event. Cleanup succeeded with no remaining resident model or cleanup error.

The [independent audit](independent_audit.json), using the frozen archived source, passes **260/263 checks**. The three retained failures are complete planned observation coverage, the runtime guard outcome, and complete planned adjudication coverage. Other source/model/case hashes, empty personal-memory evidence, public-reference definitions/prompts, expression reconstruction, actual-call provenance and measurement arithmetic pass. No failed check is waived or erased.

The later [saved cleanup audit](../device_cleanup_v1/independent_cleanup_audit.json) passes **38/38 restoration checks**. Six existing zram devices were cycled sequentially and restored with their original 650,264 KiB sizes and priority 5; total capacity remains 3,901,584 KiB, with zero swap in use at completion. The helper matches its prior sealed bytes and retains both per-device and outer `finally` restoration, with earlier sealed failure/interruption tests intact. This read-only audit performed no administrator operation. The recorded final available RAM, **2,036,260 KiB**, is below the unchanged 2 GiB startup gate; successful restoration alone does not authorize or establish readiness for another run.

This is a known-case development attempt, preserved separately from v1 and any later candidate/run. Its guarded failure is not replaced by a subsequent recovery. The independent new holdout remains outside this cohort; voice/audio and live populated-memory validation are outside this text evaluation.
