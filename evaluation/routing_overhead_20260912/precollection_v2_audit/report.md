# CLARA routing overhead: measured four-turn sequences

88 recorded turns; 22 complete sequence attempts; 0 accounting/identity audit errors.

Backend loading, prefill and decoding durations are already inside the measured client-call wall spans. They are diagnostics and are never added again. The exclusive component partition plus unaccounted wall time equals each measured request interval. Startup includes prepared-memory/client setup and is added once to the four request intervals. Complete sequence totals additionally include the measured between-turn guard, audit and logging gaps. Final cleanup remains separate.

| System | Attempts | Delivered | Complete sequences | Mean request s | Mean startup s | Mean sequence s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| small | 24 | 24 | 6 | 4.352 | 2.510 | 20.080 |
| large | 24 | 23 | 6 | 26.672 | 2.491 | 109.347 |
| adaptive | 20 | 20 | 5 | 13.855 | 3.428 | 59.017 |
| replay | 20 | 20 | 5 | 11.721 | 2.631 | 49.675 |

Positive paired differences mean adaptive took longer; negative differences mean measured adaptive savings. Each sequence is first averaged over available timing repetitions. A repeated sequence is one cluster, not three independent quality cases. Intervals resample whole sequence variants within workload patterns and are descriptive for this small authored suite. Shared templates and the fictional memory profile limit even sequence-level independence; these are not population confidence guarantees.

| Comparator | Pattern | Sequence clusters | Adaptive minus comparator s | Descriptive cluster interval s |
| --- | --- | ---: | ---: | --- |
| small | overall | 5 | 39.409 | [34.246, 44.573] |
| small | DDDD | 2 | 95.673 | [84.303, 107.042] |
| small | EEEE | 3 | 1.900 | [0.293, 3.372] |
| large | overall | 5 | -47.899 | [-58.529, -37.269] |
| large | DDDD | 2 | -1.186 | [-13.956, 11.584] |
| large | EEEE | 3 | -79.041 | [-95.959, -68.348] |
| replay | overall | 5 | 9.342 | [3.240, 15.443] |
| replay | DDDD | 2 | 16.510 | [1.925, 31.096] |
| replay | EEEE | 3 | 4.563 | [3.836, 5.171] |

The routing-bypass replay is a diagnostic replay of the adaptive generator requests and selected model sequence. It is not a deployable policy. It runs after the main-system triple, so placement, allocator/cache state and device-order differences may affect its paired delta even with identical model requests.

Residency-audit HTTP checks are separately measured instrumentation overhead. The turn-pair table also shows subtraction of that direct audit span difference as a diagnostic; it does not remove thermal/cache or order effects. Verified-eviction blocking is retained in all measured systems. Model-transition bookkeeping outside explicit unload/verification spans remains in its enclosing classifier/generation component.

Model residency, transitions, return-to-small and following-turn costs are in `turns.csv` and `transition_following_turn_summary.csv`; actual model and GPU allocation fractions are included. GPU allocation is the ratio of allocated bytes, not utilization or the fraction of computation. Output tokens, prompt tokens and actual backends are retained to expose attribution limits.

Answer review status: **pending**. Validated delivery does not establish semantic correctness. No quality–latency improvement is claimed while review is pending. Independent human validation remains pending.

All raw attempts, errors and incomplete sequences remain in the input directory and the attempt tables. Incomplete sequences are excluded only from complete paired totals, with their missing coverage explicit; their observed turns remain in request distributions. Earlier experiments are contextual evidence and are not pooled into these measurements.
