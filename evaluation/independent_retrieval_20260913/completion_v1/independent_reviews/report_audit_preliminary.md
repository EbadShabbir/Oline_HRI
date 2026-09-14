# Independent report-renderer audit

Reviewer: independent assistant `/root/audit_design`. This audit inspects source and synthetic examples only; no primary collection outputs or semantic judgments were read. Human validation remains pending.

The renderer's six overall groups, 36 category groups, 42 paired contrasts, and answerability names match the analyzer and frozen reference schemas. Contrasts are left minus right: positive success differences favor the left condition and negative time differences indicate faster left-condition requests. Success differences scale to percentage points; time intervals stay in seconds. The analyzer already averages paired repetitions within request and resamples the eight full scenario clusters. The renderer does not recalculate intervals or treat repetitions as independent inferential units.

Known authorized abstention remains failure. The additional cautious-miss count does not enter success, and its clean-caution subset excludes unsupported and forbidden claims. Known-request wins compare each request's mean across repetitions. The prose retains zero-success, unfavorable quality, and increased-time results, and declines equivalence/noninferiority claims from equal totals. The complete-analysis gate requires 864 unique reviewed attempts and an integrity-valid completed batch.

Initial source SHA256: `6d83509c709f695865c8ac986e69d22fe52f1472e93a125eade179ccc0e3ffc4`.

Requested corrections/clarifications before final approval:

- All stage means are per attempted request, including zeros for unused stages. Selection sensitivity/specificity excludes unresolved decisions and unauthorized cases.
- Evidence coverage is occurrence-weighted; inspection/supply totals sum per-attempt unique IDs rather than globally distinct records.
- Semantic unsupported-claim judgments against a common truth catalog differ from grounding in supplied runtime evidence. Include the analyzer's known-success-without-supplied-evidence diagnostic.
- Supervisor slot cost includes rejected launches, guards, waiting, and successful startup/exit/sealing residual; its label must not imply only waiting.
- Energy totals use available adjacent samples with power at both endpoints. Missing individual energy intervals do not necessarily make a session value unavailable; avoid claiming that every missing interval forces n/a.

Five independent standard-library synthetic tests initially passed in 0.064 seconds. They cover signed/scaled intervals, undefined denominators, known-fact caution without success, distinct-request versus repetition counts, null/unfavorable interpretation, and CSV boolean/zero/missing-value distinctions. A final hash-bound approval will identify the corrected source and rerun results.

This source review does not validate final collection arithmetic, independent review agreement, the factual correctness of generated answers, or later renderer amendments. Those require the sealed final inputs and separate checks after collection.
