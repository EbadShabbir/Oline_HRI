# Final numerical findings: CLARA routing overhead

Adaptive completed the authored four-turn sequences in 65.694 s on average, versus 78.454 s for large-only: a measured saving of 12.760 s (16.26%) after the observed routing, classification, switching, startup, and interturn costs. It took 45.579 s longer than small-only and 8.261 s longer than its diagnostic bypass replay. Thus selection recovered its observed wall-time costs against large-only for the balanced suite, but did not beat small-only. The strongest timing benefit was EEEE. DDEE was slower than large-only over the four-turn horizon, including its final small-model return.

The completed assistant review found 77/144 fully correct adaptive answers, versus 97/144 large-only and 66/144 small-only. Consequently the experiment does not establish a quality-preserving latency improvement; it shows a timing/answer-quality tradeoff. The clear EEEE speedup also reduced fully correct answers, 21/36 versus 33/36. Two independent blinded assistant contexts reviewed 146 distinct output groups, agreeing initially on 145 and adjudicating one; human validation remains pending.

All 576 turns from 144 eligible four-turn attempts are included, including 30 rejected answers. The exact v1 four-turn validation-failure session is eligible through the audited continuation adapter; its failed answer and original interrupted raw status remain preserved. Repetitions are dependent: there are 12 authored sequence clusters, with only three variants per pattern and shared templates/memory. Counts and means below are descriptive, not 576 independent trials.

## Complete-sequence accounting

Seconds below are means per four-turn sequence. Startup starts at BGE initialization and includes prepared memory and router/Conversation setup. The primary total is startup + four complete request walls + measured gaps. Initial admission/client/monitor setup belongs to the separate envelope; final cleanup is also separate. First backend loading is inside the first request, not startup.

| System | Startup | Four requests | Gaps | Complete | Cleanup | Fully correct / attempted |
| --- | --- | --- | --- | --- | --- | --- |
| small | 2.820 | 17.116 | 0.179 | 20.115 | 0.149 | 66/144 |
| large | 2.607 | 75.663 | 0.185 | 78.454 | 0.230 | 97/144 |
| adaptive | 2.891 | 62.623 | 0.181 | 65.694 | 0.187 | 77/144 |
| replay | 2.714 | 54.545 | 0.175 | 57.434 | 0.185 | 77/144 |

| Pattern | System | Startup | Four requests | Gaps | Complete | Correct / 36 | Actual route |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EEEE | small | 2.433 | 15.960 | 0.170 | 18.563 | 21 | SSSS |
| EEEE | large | 2.560 | 67.568 | 0.178 | 70.306 | 33 | LLLL |
| EEEE | adaptive | 2.902 | 16.321 | 0.172 | 19.394 | 21 | SSSS |
| EEEE | replay | 2.680 | 13.927 | 0.160 | 16.768 | 21 | SSSS |
| DDDD | small | 2.847 | 18.289 | 0.182 | 21.317 | 12 | SSSS |
| DDDD | large | 2.664 | 88.118 | 0.172 | 90.954 | 15 | LLLL |
| DDDD | adaptive | 2.742 | 84.341 | 0.188 | 87.272 | 16 | LLLL |
| DDDD | replay | 2.625 | 80.113 | 0.187 | 82.925 | 16 | LLLL |
| EDED | small | 3.025 | 17.078 | 0.176 | 20.279 | 9 | SSSS |
| EDED | large | 2.441 | 70.760 | 0.176 | 73.377 | 24 | LLLL |
| EDED | adaptive | 2.672 | 68.520 | 0.182 | 71.374 | 19 | SLLL |
| EDED | replay | 2.768 | 62.463 | 0.177 | 65.409 | 19 | SLLL |
| DDEE | small | 2.976 | 17.139 | 0.186 | 20.302 | 24 | SSSS |
| DDEE | large | 2.764 | 76.204 | 0.213 | 79.180 | 25 | LLLL |
| DDEE | adaptive | 3.247 | 81.310 | 0.181 | 84.738 | 21 | LLLS |
| DDEE | replay | 2.782 | 61.675 | 0.177 | 64.634 | 21 | LLLS |

Pattern letters are workload labels. Every repetition actually selected SSSS for EEEE, LLLL for DDDD, SLLL for EDED, and LLLS for DDEE in adaptive and replay. The first DDEE easy turn kept large; the second easy turn returned small. Fixed arms generated exclusively with their named models.

## Paired timings and repeat variation

Positive differences mean adaptive was slower. Overall and pattern means first average each sequence's three repetitions; balanced coverage makes these numerically equal to the corresponding session means.

| Pattern | Adaptive − small | Adaptive − large | Adaptive − replay |
| --- | --- | --- | --- |
| overall | 45.579 | -12.760 | 8.261 |
| EEEE | 0.831 | -50.912 | 2.626 |
| DDDD | 65.954 | -3.682 | 4.347 |
| EDED | 51.095 | -2.003 | 5.965 |
| DDEE | 64.436 | 5.558 | 20.104 |

| Pattern | Repeat | Adaptive − small | Adaptive − large | Adaptive − replay |
| --- | --- | --- | --- | --- |
| EEEE | 1 | 1.900 | -79.041 | 4.563 |
| EEEE | 2 | 0.847 | -26.682 | 2.436 |
| EEEE | 3 | -0.254 | -47.012 | 0.880 |
| DDDD | 1 | 93.994 | -3.599 | 7.151 |
| DDDD | 2 | 28.013 | -3.604 | 4.028 |
| DDDD | 3 | 75.856 | -3.844 | 1.862 |
| EDED | 1 | 46.019 | -15.797 | 1.774 |
| EDED | 2 | 67.576 | 14.307 | 19.526 |
| EDED | 3 | 39.690 | -4.518 | -3.405 |
| DDEE | 1 | 60.987 | 6.039 | 27.302 |
| DDEE | 2 | 74.251 | -1.796 | 17.903 |
| DDEE | 3 | 58.071 | 12.431 | 15.108 |

EDED reverses against large-only in repetition 2 and against replay in repetition 3. DDEE reverses against large-only in repetition 2. EEEE is faster than large-only in all repetitions, but slower than small-only in repetitions 1–2. DDDD generates entirely with large in both arms; its small timing difference is not evidence of a benefit from choosing a smaller generator. Stratified sequence-cluster intervals in `report_reviewed_v2/paired_cluster_summary.csv` are exploratory; EDED, DDDD and DDEE intervals against large-only include zero.

## Useful-answer outcomes

| Pattern | Repeat | Small correct / 12 | Large correct / 12 | Adaptive correct / 12 | Replay correct / 12 |
| --- | --- | --- | --- | --- | --- |
| EEEE | 1 | 7 | 11 | 7 | 7 |
| EEEE | 2 | 7 | 11 | 7 | 7 |
| EEEE | 3 | 7 | 11 | 7 | 7 |
| DDDD | 1 | 4 | 6 | 5 | 5 |
| DDDD | 2 | 4 | 6 | 5 | 6 |
| DDDD | 3 | 4 | 3 | 6 | 5 |
| EDED | 1 | 3 | 7 | 6 | 6 |
| EDED | 2 | 3 | 9 | 7 | 7 |
| EDED | 3 | 3 | 8 | 6 | 6 |
| DDEE | 1 | 8 | 7 | 7 | 7 |
| DDEE | 2 | 8 | 8 | 7 | 7 |
| DDEE | 3 | 8 | 10 | 7 | 7 |

| Comparator | Both correct | Adaptive only | Comparator only | Neither correct |
| --- | --- | --- | --- | --- |
| small | 52 | 25 | 14 | 53 |
| large | 74 | 3 | 23 | 44 |
| replay | 73 | 4 | 4 | 63 |

Replay and adaptive have equal overall correctness counts but disagree on eight paired outcomes (four in each direction). Identical generation inputs therefore did not imply identical delivered outputs. Partial, incorrect, inappropriate abstention, and technical-failure labels all count as not fully correct. Every review mapping, supplied-evidence list, cited ID list, rubric, and content hash was independently reconstructed against all 576 raw observations for this summary; no join defect was found.

## Disjoint wall components and nested backend durations

The following seconds are per request. For each system, the components including residual time partition the complete request wall. Routing/bookkeeping includes enclosing Python/trace work. Explicit deterministic child spans identify the decision regions, still including trace overhead; they are not an estimate of uninstrumented algorithm cost. Backend load/prefill/decode below overlap these walls and must never be added to them.

| Exclusive component | small | large | adaptive | replay |
| --- | --- | --- | --- | --- |
| answer_generation | 2.960 | 14.025 | 12.327 | 13.524 |
| deterministic_routing_and_bookkeeping | 0.021 | 0.025 | 0.035 | 0.017 |
| eviction | 0.000 | 0.000 | 0.028 | 0.027 |
| memory_classifier | 1.221 | 4.786 | 3.187 | 0.000 |
| other_instrumented | 0.029 | 0.032 | 0.030 | 0.029 |
| residency_audit | 0.014 | 0.016 | 0.015 | 0.008 |
| retrieval | 0.020 | 0.020 | 0.021 | 0.018 |
| unaccounted | 0.005 | 0.005 | 0.005 | 0.005 |
| validation | 0.008 | 0.008 | 0.008 | 0.008 |

| System | Memory calls | Compute calls | Nested load / seq | Nested prefill / seq | Nested decode / seq |
| --- | --- | --- | --- | --- | --- |
| small | 93 | 0 | 9.171 | 1.014 | 5.487 |
| large | 93 | 0 | 23.824 | 4.603 | 45.736 |
| adaptive | 93 | 0 | 25.242 | 3.287 | 32.459 |
| replay | 0 | 0 | 24.629 | 1.812 | 27.170 |

There were 93 memory-classifier calls in each normal system, none in replay, and zero compute-classifier calls. Fixed systems retain normal memory selection/retrieval and use only their named model. Adaptive memory-classifier exclusive wall totaled 458.932 s (12.748 s/sequence); it is not an incremental selection estimate because some calls also perform the cold load that replay performs in generation.

| System | Deterministic decision spans | Decision span total s | Decision span s/request |
| --- | --- | --- | --- |
| small | 144 | 1.047 | 0.007 |
| large | 144 | 1.213 | 0.008 |
| adaptive | 288 | 2.007 | 0.014 |
| replay | 0 | 0.000 | 0.000 |

## Cold residency, transitions, and the following turn

| System | Request condition | n | Request mean s | Nested load mean s |
| --- | --- | --- | --- | --- |
| small | cold_start | 36 | 11.420 | 9.158 |
| small | resident_same_model | 108 | 1.899 | 0.004 |
| large | cold_start | 36 | 39.187 | 23.811 |
| large | resident_same_model | 108 | 12.158 | 0.004 |
| adaptive | cold_start | 36 | 25.099 | 16.678 |
| adaptive | resident_same_model | 90 | 9.768 | 0.005 |
| adaptive | model_switch | 18 | 26.206 | 17.104 |
| replay | cold_start | 36 | 24.897 | 16.494 |
| replay | resident_same_model | 90 | 7.283 | 0.002 |
| replay | model_switch | 18 | 22.881 | 16.257 |

| System | Actual transition | n | Request s | Unload acknowledgment s | Verified eviction s | Nested load s |
| --- | --- | --- | --- | --- | --- | --- |
| adaptive | small_to_large | 9 | 37.406 | 0.015 | 0.115 | 24.177 |
| adaptive | large_to_small | 9 | 15.005 | 0.020 | 0.206 | 10.031 |
| replay | small_to_large | 9 | 35.207 | 0.014 | 0.120 | 23.403 |
| replay | large_to_small | 9 | 10.555 | 0.013 | 0.185 | 9.112 |

| System | Following previous request condition | n | Following request mean s | Nested load mean s |
| --- | --- | --- | --- | --- |
| small | cold_start | 36 | 2.126 | 0.004 |
| small | resident_same_model | 72 | 1.786 | 0.004 |
| large | cold_start | 36 | 12.966 | 0.004 |
| large | resident_same_model | 72 | 11.755 | 0.005 |
| adaptive | cold_start | 36 | 17.585 | 6.048 |
| adaptive | resident_same_model | 63 | 10.047 | 1.437 |
| adaptive | model_switch | 9 | 9.426 | 0.005 |
| replay | cold_start | 36 | 15.154 | 5.852 |
| replay | resident_same_model | 63 | 6.977 | 1.304 |
| replay | model_switch | 9 | 9.133 | 0.003 |

| DDEE turn | Small s | Large s | Adaptive s | Replay s |
| --- | --- | --- | --- | --- |
| 1 | 11.629 | 42.986 | 41.000 | 37.160 |
| 2 | 2.423 | 15.803 | 13.645 | 9.639 |
| 3 | 1.657 | 8.979 | 11.660 | 4.322 |
| 4 | 1.430 | 8.436 | 15.005 | 10.555 |

| System | Return request range s | Nested load range s | Return minus resident large request s |
| --- | --- | --- | --- |
| adaptive | 12.144–17.657 | 8.889–11.615 | 6.569 |
| replay | 10.048–10.882 | 8.776–9.527 | 2.119 |

Adaptive's nine real small→large transitions occur at EDED turn 2; nine following turns are observed at EDED turn 3. Its nine large→small returns occur at DDEE turn 4. No turn 5 follows those returns, so the experiment cannot establish a subsequent resident-small saving or the longer-horizon break-even point. Unload acknowledgment, verified absence, and next backend call have separately ordered spans. Most other peer-unload calls are no-ops at cold entry; they are not model switches. Residency groups pool different questions, so their mean difference is descriptive rather than a matched cold-load intervention.

## Diagnostic selection cost and attribution limits

| Adaptive − replay, per sequence | Difference |
| --- | --- |
| Complete wall s | 8.261 |
| Startup s | 0.177 |
| Four request walls s | 8.078 |
| Measured gaps s | 0.005 |
| Direct residency-audit wall s | 0.026 |
| Complete wall after direct audit subtraction s | 8.234 |
| Nested all-backend load s | 0.613 |
| Nested all-backend prefill s | 1.474 |
| Nested all-backend decode s | 5.288 |
| Nested generation load s | -5.000 |
| Nested classifier load s | 5.613 |
| Generation output tokens | -7.944 |
| Classifier output tokens | 34.917 |

| System | Generation tokens, all 144 calls | Tokens from rejected deliveries | Classifier tokens |
| --- | --- | --- | --- |
| small | 6351 | 513 | 1257 |
| large | 6539 | 421 | 1257 |
| adaptive | 6346 | 562 | 1257 |
| replay | 6632 | 594 | 0 |

| System | Generator | Calls | GPU allocated byte fraction min | Mean | Max |
| --- | --- | --- | --- | --- | --- |
| small | qwen3:0.6b | 144 | 1.000 | 1.000 | 1.000 |
| large | qwen3:1.7b | 144 | 0.491 | 0.593 | 0.662 |
| adaptive | qwen3:0.6b | 54 | 1.000 | 1.000 | 1.000 |
| adaptive | qwen3:1.7b | 90 | 0.541 | 0.608 | 0.688 |
| replay | qwen3:0.6b | 54 | 1.000 | 1.000 | 1.000 |
| replay | qwen3:1.7b | 90 | 0.515 | 0.599 | 0.662 |

The 8.261 s/sequence adaptive-minus-replay difference estimates the net observed cost of retaining selection on this execution path; it is not a pure classifier causal effect. Exact generation HTTP bodies, selected/actual generators, and adaptive starting histories were replayed, but replay always ran last. Model placement, cache/numerical execution, and output length varied. Adaptive generated 286 fewer tokens than replay overall, while its all-backend prefill/decode took longer. All 2,090 tokens from the 30 rejected deliveries are included above; delivered-only token fields in the frozen core table omit these and should not be used for all-attempt attribution.

Replay issued two extra no-op small-peer unloads following validation failures in `ro_dddd_3_r1_replay` and `ro_dddd_3_r2_replay`, when the client residency hint was invalidated. Large remained resident and generation identity remained exact. These extra unload/verification spans totaled 0.039859896 s; their negligible magnitude does not remove the state-path distinction. A cold classifier may carry loading in adaptive that shifts to answer generation in replay, so generation-only load savings overstate net savings. Small was fully GPU allocated; large was partly offloaded. GPU byte allocation is neither utilization nor a fraction of computation.

Final telemetry/resource integrity was independently audited: 15,856 samples, peak temperature 57.343 °C, RAM 6,633 MiB, swap 2,485 MiB; maximum telemetry sample gap 1.9473 s. All sessions ended with empty LLM residency and no cleanup errors. Cold entry retained OS file caches. These controls bound the recorded run; they do not establish identical placement or thermal/cache conditions across systems.

The final figures were visually checked against these values. Reproduce the supplementary findings with `python evaluation/routing_overhead_20260912/build_final_findings.py`; exact source-table hashes, unrounded values, per-pattern quality contingencies, and transition comparisons are in `final_findings.json`. Frozen sources and raw traces were read without modification.
