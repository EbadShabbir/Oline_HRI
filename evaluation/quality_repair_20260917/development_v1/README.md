# Known sixteen-case quality repair — development v1

This development replay completed cleanly: **16/16 final routes, 12/16 full-quality answers and 12/16 combined successes**, with no execution errors or resource-guard violations. These are previously observed cases; this result is not new-case validation.

The unchanged prior recovery scored 12/16 routes and 4/16 quality/combined successes. All four prior quality passes remain passes and eight previous failures now pass. Both new reviewers agree on all 16 quality judgments, all 27 required-component booleans and all 16 usefulness fields. Useful general help was delivered in **9/12** applicable cases. Original independent reviews and their reasons remain unchanged in [review A](review_a.json) and [review B](review_b.json); [aggregation](adjudication.json) required no scoring adjudication.

| Expected mode | Cases | Correct final route | Full quality / both |
| --- | ---: | ---: | ---: |
| none | 8 | 8 | 4 |
| optional | 2 | 2 | 2 |
| required | 3 | 3 | 3 |
| clarify | 3 | 3 | 3 |

The invented cushion-pattern recall is replaced by an explicit missing-evidence acknowledgment; all three unresolved label, pronoun and conversion requests now receive targeted clarification. CSV, admitted draft facts, generic naming and activity selection also pass their frozen criteria.

Four requests still fail strict quality:

- **001 — supplied display plan:** after two withheld attempts, a generic rephrase question replaces the fully specified four-step plan.
- **004 — paper fan:** numbering and labels are correct, but the steps form a cone, omit alternating folds and introduce ribbon/string.
- **005 — arithmetic:** the required integer-only format is correct, but the answer is 23 instead of 31.
- **007 — day/night:** the answer conflates rotation with motion around the Sun and misses the required toward/away sunlight mechanism. The static reference note did not prevent this incorrect explanation.

Complete [delivered answers](answers.md), [per-case measurements](per_case.jsonl) and [metrics](metrics.json) retain these failures.

| Text-turn latency group | n | Median seconds | p95 seconds |
| --- | ---: | ---: | ---: |
| All attempts | 16 | 3.804 | 14.394 |
| Generated delivery | 11 | 4.255 | 6.880 |
| Application-only delivery | 5 | 0.069 | 26.141 |
| Full-quality outcomes | 12 | 3.280 | 6.657 |

Turn wall time includes guard overhead; percentiles use linear interpolation at `(n-1)*q`. The first case took 32.658 seconds and ultimately delivered an application fallback after two model attempts. A short application reply is not necessarily cheap. Compared with the historical recovery, delivery populations and model warm/cold state differ; these measurements do not isolate a causal speed change.

All **28 actual model calls** completed: 13 answer generations, 11 answer reviews and four dependency reviews, all `qwen3:1.7b`; no compute-classifier call or call-bound violation occurred. Eleven deliveries contain generated text and five are application-only.

The run retained **162 telemetry samples**, with peak swap **685 MiB** and temperature **57.406 C**, and at least 1,076 MiB sampled free RAM. Startup/runtime gates and cleanup passed; no model remained resident. This verifies this bounded run only, not long-duration, voice/audio or populated-memory behavior.

The sealed [independent audit](independent_audit.json) passed **260/261 checks**. Its sole failure incorrectly groups `reference_ids` with personal-memory evidence, flagging the public `earth_day_night_v1` note in case 007. That original failed audit and its preregistered source remain unchanged. The separate [reference provenance supplement](independent_reference_audit.json) passes **5/5 checks**: it verifies the literal public note against hash-bound archived source and the actual selected generation prompt, while all personal-memory IDs remain empty. It corrects this audit distinction only; case 007 remains a strict-quality failure.

The analyzer verifies the frozen [candidate archive](candidate_source/) and [evaluation seal](evaluation_freeze.json); later development changes do not alter this cohort. Both measurement capture and execution are complete. No release-quality claim is made, and the independently authored twenty-case holdout remains separate and unopened during this development report.
