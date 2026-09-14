# Routing-overhead workload design and evidence reuse

`workload.json` defines 48 turn slots in 12 four-turn sequences, with three
variants of each requested EEEE/DDDD/EDED/DDEE pattern. A sequence is a retained
conversation beginning with empty history. E and D are author-assigned workload
labels, never forced model choices. The deterministic policy and all model
outputs remain unchanged by the labels.

| Pattern | Variant 1 | Variant 2 | Variant 3 |
| --- | --- | --- | --- |
| EEEE | Four social turns | Triangle definition, then three social turns | Editor recall, then three social turns |
| DDDD | Arithmetic, dependency timing, constrained choice, filtering | Budget, precedence, route comparison, exhaustive codes | Four short memory-backed calculations |
| EDED | Definition, arithmetic, definition, ordering | Greeting, timing, thanks, constrained choice | Recall, memory-based route choice, recall, memory rule |
| DDEE | Arithmetic and timing, thanks and farewell | Unit-cost comparison and precedence, thanks and farewell | Two memory-backed calculations, two greetings |

All three DDEE terminal pairs use the policy's existing social grammar. Those
remain small-eligible even when previous non-memory answers are retained. A
successful resident-large trace should therefore hold large on its first easy
turn and return to small on the second. Offline validation checks eligibility
and this transition with a simulated classifier; live actual choices, failures,
and residency remain authoritative. Repeated greetings are deliberately chosen
to exercise a concrete implemented rule, so this subset is not a representative
sample of all easy application questions.

EDED variant 1's third turn is an ordinary independent island definition.
Because non-social easy detection refuses prior history, this easy-labeled
request may select large. This is a policy characteristic to measure, not an
excuse to clear history or force a route. Social turns after ordinary history
can require real memory classifiers because memory need is independent of
compute need. Memory-backed answers are normally excluded from retained
history under the existing privacy/evidence contract; preserve that behavior.

The seed is reused byte-for-byte as a JSON value from
`../post_memory_comparison_20260912/frozen_v2/workload.json`, with its source
hash stored in metadata. It contains fictional, explicitly confirmed facts,
30 lifecycle operations, and 26 eligible records at the fixed evaluation clock.
Reuse avoids inventing a new memory fixture merely for timing. All supported
personal rubrics identify exact authorized memory IDs. The corrections,
forgetting, expiry and conflict facts remain in the prepared fixture, although
this narrow overhead workload does not independently evaluate every lifecycle
case. Setup remains a static snapshot, not live memory-changing evaluation.

Required numerical answers were computed from the explicitly supplied data or
frozen seed before collection. Equivalent concise wording and equivalent clock
formats are acceptable. Social success means an appropriate brief response
without an invented personal claim; exact wording is not prescribed. Full
success requires every listed substantive claim and no forbidden assertion;
reference prose is illustrative. For personal answers, factual correctness,
retrieval support, citations, unsupported facts and technical delivery should
remain distinguishable. All automated checks are empty lexical-signal lists,
so semantic review is required. No benchmark accuracy can be inferred from
schema validation alone.

This is assistant-authored, developer-informed workload design with independent
human review pending. It includes repeated social prompts, shared task forms,
and one shared fictional profile. There are 12 designed sequences, not 48
independent scenarios or 576 independent quality observations. Deterministic
rule checks made before outputs are coverage validation; no live answers were
used to choose the requests.

## Earlier timing evidence that can be reused

The completed post-memory v2 records provide valid historical full-request,
classifier, HTTP, generation backend-duration, placement, telemetry and cleanup
measurements for their own frozen source, 48-request session order and empty
history per request. Retain their already reviewed answers and reported counts:
small 42/144, large 44/144, cascade 46/144 full-rubric successes. Their observed
means are 2.314, 11.255 and 8.916 seconds respectively. Those historical results
motivated measuring overhead; they are not new observations in this experiment.

The v2 cascade selected small on only 3/144 requests, and its pooled mean was
20.8% below large-only while large-only was faster in rounds 2 and 3. Recorded
placement varied substantially. Existing loading is already inside recorded
HTTP/request wall spans. Backend load totals from the final analysis were
28.363 seconds small, 72.821 large, and 166.549 cascade; these must never be
added to their request totals. These data can be reused for historical
comparison, instrumentation schema design, and arithmetic checks, not to fill
missing paired four-turn sequences.

The lightweight-routing README contains successful offline validation and two
zero-inference admission rejections. Its proposed five-request smoke was not a
hardware timing result. No selection savings or hysteresis timing can be
recovered from those zero-request preflights. Earlier complete-system or ARC
runs use other workload/history/lifecycle rules and do not substitute for the
controlled four-turn experiment. Retired 4B data remain historical and must not
be rerun.

The missing controlled evidence consists of monotonic verified eviction,
explicit validation and deterministic-decision timing, true retained-history
four-turn transitions, independent sequence cold startup, three main-system
orders, and an exact-generation adaptive bypass replay. Prior records lack
these paired experimental conditions; pooling them would create a false
measurement of routing cost. Cite old evidence separately and reuse only
fields whose provenance and scope are actually valid.

## Reproduce offline coverage checks

From the repository root, with a new output filename:

```bash
PYTHONPATH=src:scripts .venv/bin/python \
  evaluation/routing_overhead_20260912/validate_workload.py \
  --output /tmp/new-routing-workload-validation.json
```

The final workload check is `workload_validation_final.json`; the preceding
`workload_validation.json` preserves the pre-freeze arm-name spelling update. This validates schema, seed
eligibility and deterministic DDEE hysteresis with a fake backend. It makes
zero live model or embedding calls and does not test answer quality.
