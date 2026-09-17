# Third known development iteration

The same 12 development cases passed 12/12 final routes and 8/12 full task criteria (8/12 combined), with useful general help on 8/10 applicable tasks. One independent blinded assistant reviewer and root assessment were used; this is development evidence, not a fresh holdout or human validation.

All 12 attempts delivered an answer: eight generated, four application-only. Overall median/p95 was 7.515/31.120 seconds; generated median/p95 was 7.515/28.636 seconds. The independent audit passed 206/206 checks. There were 21 model calls (13 generation, eight answer review), all on the configured 1.7B model, with no dependency-review or compute calls. Three retrievals completed with empty results. Device guards and cleanup passed.

The four strict failures were fresh_001 (wrong item destinations), fresh_004 (omitted items and unsuitable preparation steps), fresh_009 (invitation withheld after sentence-count failure), and fresh_003 (no usable treasure-hunt plan). Exact minute totals do not establish useful planning.

See [metrics](metrics.json), [delivered answers](answers.md), [judgments](adjudicated_judgments.json), [review method](review_method.md), and [independent audit](independent_audit.json). The final candidate was frozen from this implementation before the new holdout was opened. Later 48-case replay outcomes remain separate observations.
