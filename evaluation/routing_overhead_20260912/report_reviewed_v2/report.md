# CLARA routing overhead: measured four-turn sequences

576 recorded turns; 144 complete sequence attempts; 0 accounting/identity audit errors.

Backend loading, prefill and decoding durations are already inside the measured client-call wall spans. They are diagnostics and are never added again. The exclusive component partition plus unaccounted wall time equals each measured request interval. Startup begins at embedding initialization and includes prepared-memory and router/Conversation setup; it is added once to the four request intervals. Client/monitor/admission setup precedes this interval and belongs to the separately recorded process envelope. Complete sequence totals additionally include the measured between-turn guard, audit and logging gaps. Final cleanup remains separate.

| System | Attempts | Delivered | Complete sequences | Mean request s | Mean startup s | Mean sequence s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| small | 144 | 135 | 36 | 4.279 | 2.820 | 20.115 |
| large | 144 | 139 | 36 | 18.916 | 2.607 | 78.454 |
| adaptive | 144 | 136 | 36 | 15.656 | 2.891 | 65.694 |
| replay | 144 | 136 | 36 | 13.636 | 2.714 | 57.434 |

Positive paired differences mean adaptive took longer; negative differences mean measured adaptive savings. Each sequence is first averaged over available timing repetitions. A repeated sequence is one cluster, not three independent quality cases. Intervals resample whole sequence variants within workload patterns and are descriptive for this small authored suite. Shared templates and the fictional memory profile limit even sequence-level independence; these are not population confidence guarantees.

| Comparator | Pattern | Sequence clusters | Adaptive minus comparator s | Descriptive cluster interval s |
| --- | --- | ---: | ---: | --- |
| small | overall | 12 | 45.579 | [42.247, 48.687] |
| small | DDDD | 3 | 65.954 | [62.373, 68.947] |
| small | DDEE | 3 | 64.436 | [56.644, 73.644] |
| small | EDED | 3 | 51.095 | [38.736, 59.406] |
| small | EEEE | 3 | 0.831 | [0.163, 1.354] |
| large | overall | 12 | -12.760 | [-16.646, -9.222] |
| large | DDDD | 3 | -3.682 | [-6.935, 0.803] |
| large | DDEE | 3 | 5.558 | [-3.738, 14.445] |
| large | EDED | 3 | -2.003 | [-16.888, 6.465] |
| large | EEEE | 3 | -50.912 | [-52.031, -49.259] |
| replay | overall | 12 | 8.261 | [3.279, 13.101] |
| replay | DDDD | 3 | 4.347 | [-9.610, 18.794] |
| replay | DDEE | 3 | 20.104 | [4.908, 29.392] |
| replay | EDED | 3 | 5.965 | [0.336, 16.421] |
| replay | EEEE | 3 | 2.626 | [2.039, 3.044] |

The routing-bypass replay is a diagnostic replay of the adaptive generator requests and selected model sequence. It is not a deployable policy. It runs after the main-system triple, so placement, allocator/cache state and device-order differences may affect its paired delta even with identical model requests.

Residency-audit HTTP checks are separately measured instrumentation overhead. The turn-pair table also shows subtraction of that direct audit span difference as a diagnostic; it does not remove thermal/cache or order effects. Verified-eviction blocking is retained in all measured systems. Model-transition bookkeeping outside explicit unload/verification spans remains in its enclosing classifier/generation component.

Model residency, transitions, return-to-small and following-turn costs are in `turns.csv` and `transition_following_turn_summary.csv`; actual model and GPU allocation fractions are included. GPU allocation is the ratio of allocated bytes, not utilization or the fraction of computation. Output tokens, prompt tokens and actual backends are retained to expose attribution limits.

Answer review status: **assistant_reviewed**. Validated delivery does not establish semantic correctness. No quality–latency improvement is claimed while review is pending. Independent human validation remains pending.

| System | Fully correct delivered / attempted |
| --- | ---: |
| small | 66/144 |
| large | 97/144 |
| adaptive | 77/144 |
| replay | 77/144 |

All raw attempts, errors and incomplete sequences remain in the input directory and the attempt tables. Incomplete sequences are excluded only from complete paired totals, with their missing coverage explicit; their observed turns remain in request distributions. Earlier experiments are contextual evidence and are not pooled into these measurements.
