# Independent retrieval: detailed tables

ALWAYS means ALWAYS PERMITTED. All times are seconds. Repetitions are dependent observations; counts retain all attempts. Bracketed paired intervals are the analyzer's frozen 95% scenario-bootstrap intervals.

## qwen3:0.6b: answer quality and complete request time

| Category | Policy | Success | Unsupported | Personal unsupported | Abstained | Failures | Mean | Median | p95 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Direct recall | OFF | 0/24 | 0 | 0 | 24 | 0 | 1.668 | 1.311 | 1.632 |
| Direct recall | ALWAYS | 21/24 | 0 | 0 | 0 | 0 | 2.099 | 1.666 | 1.876 |
| Direct recall | SELECTIVE | 21/24 | 0 | 0 | 0 | 0 | 2.195 | 1.665 | 1.845 |
| Paraphrased recall | OFF | 0/24 | 3 | 3 | 21 | 0 | 1.783 | 1.288 | 2.012 |
| Paraphrased recall | ALWAYS | 6/24 | 3 | 3 | 15 | 0 | 2.067 | 1.513 | 2.238 |
| Paraphrased recall | SELECTIVE | 6/24 | 3 | 3 | 15 | 0 | 2.193 | 1.701 | 2.188 |
| Multi-fact personal | OFF | 0/24 | 0 | 0 | 24 | 0 | 1.506 | 1.445 | 2.046 |
| Multi-fact personal | ALWAYS | 23/24 | 1 | 1 | 0 | 0 | 2.163 | 2.106 | 2.520 |
| Multi-fact personal | SELECTIVE | 23/24 | 1 | 1 | 0 | 0 | 2.201 | 2.132 | 2.587 |
| General without memory need | OFF | 12/24 | 9 | 0 | 0 | 0 | 1.343 | 1.375 | 1.647 |
| General without memory need | ALWAYS | 13/24 | 5 | 0 | 0 | 0 | 1.677 | 1.599 | 2.351 |
| General without memory need | SELECTIVE | 11/24 | 10 | 0 | 0 | 0 | 1.787 | 1.622 | 2.883 |
| Unknown or conflicting | OFF | 21/24 | 0 | 0 | 24 | 0 | 1.282 | 1.258 | 1.520 |
| Unknown or conflicting | ALWAYS | 9/24 | 15 | 15 | 9 | 0 | 1.623 | 1.644 | 1.867 |
| Unknown or conflicting | SELECTIVE | 9/24 | 15 | 15 | 9 | 0 | 1.724 | 1.640 | 2.458 |
| Lifecycle or authorization | OFF | 18/24 | 0 | 0 | 24 | 0 | 1.876 | 1.316 | 2.094 |
| Lifecycle or authorization | ALWAYS | 21/24 | 0 | 0 | 21 | 0 | 2.019 | 1.429 | 2.185 |
| Lifecycle or authorization | SELECTIVE | 21/24 | 0 | 0 | 21 | 0 | 2.082 | 1.452 | 2.236 |

## qwen3:0.6b: paired differences

| Category | Left−right | Requests / repeated pairs | Success Δ, pp [95%] | Request Δ, s [95%] | Unnecessary retrieval Δ/task [95%] | Left-only / right-only successes |
| --- | --- | --- | --- | --- | --- | --- |
| Overall | SELECTIVE-ALWAYS | 48 / 144 | -1.4 [-6.9, +3.5] | +0.089 [+0.023, +0.147] | -0.125 [-0.167, -0.062] | 2 / 4 |
| Overall | SELECTIVE-OFF | 48 / 144 | +27.8 [+17.4, +38.2] | +0.454 [+0.346, +0.581] | +0.042 [+0.000, +0.104] | 56 / 16 |
| Overall | ALWAYS-OFF | 48 / 144 | +29.2 [+15.3, +43.8] | +0.365 [+0.269, +0.468] | +0.167 [+0.167, +0.167] | 60 / 18 |
| Direct recall | SELECTIVE-ALWAYS | 8 / 24 | +0.0 [+0.0, +0.0] | +0.096 [-0.000, +0.271] | +0.000 [+0.000, +0.000] | 0 / 0 |
| Direct recall | SELECTIVE-OFF | 8 / 24 | +87.5 [+62.5, +100.0] | +0.526 [+0.261, +0.918] | +0.000 [+0.000, +0.000] | 21 / 0 |
| Direct recall | ALWAYS-OFF | 8 / 24 | +87.5 [+62.5, +100.0] | +0.431 [+0.252, +0.651] | +0.000 [+0.000, +0.000] | 21 / 0 |
| Paraphrased recall | SELECTIVE-ALWAYS | 8 / 24 | +0.0 [+0.0, +0.0] | +0.126 [-0.043, +0.319] | +0.000 [+0.000, +0.000] | 0 / 0 |
| Paraphrased recall | SELECTIVE-OFF | 8 / 24 | +25.0 [+0.0, +62.5] | +0.410 [+0.176, +0.627] | +0.000 [+0.000, +0.000] | 6 / 0 |
| Paraphrased recall | ALWAYS-OFF | 8 / 24 | +25.0 [+0.0, +62.5] | +0.284 [+0.112, +0.482] | +0.000 [+0.000, +0.000] | 6 / 0 |
| Multi-fact personal | SELECTIVE-ALWAYS | 8 / 24 | +0.0 [+0.0, +0.0] | +0.038 [+0.023, +0.051] | +0.000 [+0.000, +0.000] | 0 / 0 |
| Multi-fact personal | SELECTIVE-OFF | 8 / 24 | +95.8 [+87.5, +100.0] | +0.694 [+0.505, +0.873] | +0.000 [+0.000, +0.000] | 23 / 0 |
| Multi-fact personal | ALWAYS-OFF | 8 / 24 | +95.8 [+87.5, +100.0] | +0.657 [+0.465, +0.832] | +0.000 [+0.000, +0.000] | 23 / 0 |
| General without memory need | SELECTIVE-ALWAYS | 8 / 24 | -8.3 [-41.7, +20.8] | +0.110 [-0.194, +0.412] | -0.750 [-1.000, -0.375] | 2 / 4 |
| General without memory need | SELECTIVE-OFF | 8 / 24 | -4.2 [-12.5, +0.0] | +0.443 [+0.164, +0.753] | +0.250 [+0.000, +0.625] | 0 / 1 |
| General without memory need | ALWAYS-OFF | 8 / 24 | +4.2 [-33.3, +37.5] | +0.334 [+0.136, +0.569] | +1.000 [+1.000, +1.000] | 4 / 3 |
| Unknown or conflicting | SELECTIVE-ALWAYS | 8 / 24 | +0.0 [+0.0, +0.0] | +0.101 [-0.006, +0.284] | +0.000 [+0.000, +0.000] | 0 / 0 |
| Unknown or conflicting | SELECTIVE-OFF | 8 / 24 | -50.0 [-87.5, +0.0] | +0.442 [+0.204, +0.722] | +0.000 [+0.000, +0.000] | 3 / 15 |
| Unknown or conflicting | ALWAYS-OFF | 8 / 24 | -50.0 [-87.5, +0.0] | +0.341 [+0.177, +0.504] | +0.000 [+0.000, +0.000] | 3 / 15 |
| Lifecycle or authorization | SELECTIVE-ALWAYS | 8 / 24 | +0.0 [+0.0, +0.0] | +0.062 [+0.009, +0.139] | +0.000 [+0.000, +0.000] | 0 / 0 |
| Lifecycle or authorization | SELECTIVE-OFF | 8 / 24 | +12.5 [+0.0, +37.5] | +0.206 [+0.043, +0.423] | +0.000 [+0.000, +0.000] | 3 / 0 |
| Lifecycle or authorization | ALWAYS-OFF | 8 / 24 | +12.5 [+0.0, +37.5] | +0.143 [-0.011, +0.377] | +0.000 [+0.000, +0.000] | 3 / 0 |

Positive differences favor the left condition for success and increase cost for time/access. Left-only/right-only counts are repeated paired attempts, not independent requests. Paired unnecessary-retrieval Δ/task averages over every paired request, with zeros on needed and denied tasks; it is not the difference between rates restricted to authorized no-memory tasks.

## qwen3:0.6b: retrieval, relevance and disclosure by category

| Category | Policy | Retrievals | Unnecessary / eligible tasks | Relevant retrieved | Relevant supplied | Irrelevant inspected | Irrelevant bounded candidates | Irrelevant supplied |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Direct recall | OFF | 0 | n/a | 0.0% | 0.0% | 0 | 0 | 0 |
| Direct recall | ALWAYS | 24 | n/a | 100.0% | 87.5% | 528 | 456 | 6 |
| Direct recall | SELECTIVE | 24 | n/a | 100.0% | 87.5% | 528 | 456 | 6 |
| Paraphrased recall | OFF | 0 | n/a | 0.0% | 0.0% | 0 | 0 | 0 |
| Paraphrased recall | ALWAYS | 24 | n/a | 87.5% | 25.0% | 528 | 456 | 3 |
| Paraphrased recall | SELECTIVE | 18 | n/a | 75.0% | 25.0% | 396 | 342 | 0 |
| Multi-fact personal | OFF | 0 | n/a | 0.0% | 0.0% | 0 | 0 | 0 |
| Multi-fact personal | ALWAYS | 24 | n/a | 100.0% | 100.0% | 504 | 432 | 6 |
| Multi-fact personal | SELECTIVE | 24 | n/a | 100.0% | 100.0% | 504 | 432 | 6 |
| General without memory need | OFF | 0 | 0/24 | n/a | n/a | 0 | 0 | 0 |
| General without memory need | ALWAYS | 24 | 24/24 | n/a | n/a | 552 | 480 | 12 |
| General without memory need | SELECTIVE | 6 | 6/24 | n/a | n/a | 138 | 120 | 3 |
| Unknown or conflicting | OFF | 0 | n/a | 0.0% | 0.0% | 0 | 0 | 0 |
| Unknown or conflicting | ALWAYS | 24 | n/a | 100.0% | 75.0% | 540 | 468 | 15 |
| Unknown or conflicting | SELECTIVE | 24 | n/a | 100.0% | 75.0% | 540 | 468 | 15 |
| Lifecycle or authorization | OFF | 0 | n/a | 0.0% | 0.0% | 0 | 0 | 0 |
| Lifecycle or authorization | ALWAYS | 18 | n/a | 100.0% | 50.0% | 408 | 354 | 6 |
| Lifecycle or authorization | SELECTIVE | 18 | n/a | 100.0% | 50.0% | 408 | 354 | 6 |

Evidence percentages divide the sum of relevant retrieved/supplied ID occurrences by the sum of all frozen relevant-ID occurrences; they are not means of per-question coverage. Questions with no relevant IDs contribute no coverage denominator. Inspection/candidate/disclosure totals sum each attempt's unique IDs, so the same memory can contribute again on another request or repetition; these are not globally unique memory counts.

## qwen3:1.7b: answer quality and complete request time

| Category | Policy | Success | Unsupported | Personal unsupported | Abstained | Failures | Mean | Median | p95 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Direct recall | OFF | 0/24 | 0 | 0 | 24 | 0 | 7.371 | 5.835 | 12.763 |
| Direct recall | ALWAYS | 21/24 | 2 | 2 | 0 | 0 | 10.750 | 7.791 | 33.321 |
| Direct recall | SELECTIVE | 21/24 | 3 | 3 | 0 | 0 | 5.877 | 4.334 | 11.420 |
| Paraphrased recall | OFF | 0/24 | 1 | 1 | 20 | 0 | 8.337 | 6.897 | 16.877 |
| Paraphrased recall | ALWAYS | 6/24 | 0 | 0 | 12 | 1 | 10.666 | 9.144 | 17.520 |
| Paraphrased recall | SELECTIVE | 6/24 | 1 | 1 | 12 | 1 | 11.833 | 7.545 | 37.647 |
| Multi-fact personal | OFF | 0/24 | 0 | 0 | 24 | 0 | 7.937 | 7.473 | 12.585 |
| Multi-fact personal | ALWAYS | 23/24 | 0 | 0 | 0 | 1 | 13.489 | 12.761 | 16.236 |
| Multi-fact personal | SELECTIVE | 23/24 | 0 | 0 | 0 | 1 | 8.737 | 7.385 | 16.507 |
| General without memory need | OFF | 22/24 | 0 | 0 | 0 | 0 | 6.175 | 5.079 | 13.366 |
| General without memory need | ALWAYS | 12/24 | 4 | 3 | 0 | 0 | 8.841 | 7.014 | 19.487 |
| General without memory need | SELECTIVE | 17/24 | 2 | 0 | 0 | 0 | 12.114 | 8.825 | 33.590 |
| Unknown or conflicting | OFF | 23/24 | 0 | 0 | 23 | 1 | 5.917 | 6.232 | 9.613 |
| Unknown or conflicting | ALWAYS | 6/24 | 12 | 12 | 6 | 0 | 8.034 | 6.985 | 13.193 |
| Unknown or conflicting | SELECTIVE | 6/24 | 12 | 12 | 6 | 0 | 7.638 | 5.594 | 14.139 |
| Lifecycle or authorization | OFF | 18/24 | 0 | 0 | 24 | 0 | 8.544 | 6.370 | 27.205 |
| Lifecycle or authorization | ALWAYS | 18/24 | 0 | 0 | 17 | 1 | 10.977 | 10.795 | 20.756 |
| Lifecycle or authorization | SELECTIVE | 16/24 | 0 | 0 | 17 | 2 | 8.504 | 7.171 | 13.029 |

## qwen3:1.7b: paired differences

| Category | Left−right | Requests / repeated pairs | Success Δ, pp [95%] | Request Δ, s [95%] | Unnecessary retrieval Δ/task [95%] | Left-only / right-only successes |
| --- | --- | --- | --- | --- | --- | --- |
| Overall | SELECTIVE-ALWAYS | 48 / 144 | +2.1 [-2.8, +7.6] | -1.342 [-2.071, -0.614] | -0.146 [-0.167, -0.104] | 6 / 3 |
| Overall | SELECTIVE-OFF | 48 / 144 | +18.1 [+7.6, +27.8] | +1.737 [+0.974, +2.323] | +0.021 [+0.000, +0.062] | 54 / 28 |
| Overall | ALWAYS-OFF | 48 / 144 | +16.0 [+2.1, +29.2] | +3.079 [+2.171, +4.072] | +0.167 [+0.167, +0.167] | 55 / 32 |
| Direct recall | SELECTIVE-ALWAYS | 8 / 24 | +0.0 [+0.0, +0.0] | -4.873 [-7.905, -2.183] | +0.000 [+0.000, +0.000] | 0 / 0 |
| Direct recall | SELECTIVE-OFF | 8 / 24 | +87.5 [+62.5, +100.0] | -1.494 [-2.381, -0.781] | +0.000 [+0.000, +0.000] | 21 / 0 |
| Direct recall | ALWAYS-OFF | 8 / 24 | +87.5 [+62.5, +100.0] | +3.379 [+0.282, +6.837] | +0.000 [+0.000, +0.000] | 21 / 0 |
| Paraphrased recall | SELECTIVE-ALWAYS | 8 / 24 | +0.0 [+0.0, +0.0] | +1.167 [-1.641, +4.338] | +0.000 [+0.000, +0.000] | 0 / 0 |
| Paraphrased recall | SELECTIVE-OFF | 8 / 24 | +25.0 [+0.0, +62.5] | +3.496 [+1.331, +5.627] | +0.000 [+0.000, +0.000] | 6 / 0 |
| Paraphrased recall | ALWAYS-OFF | 8 / 24 | +25.0 [+0.0, +62.5] | +2.330 [-0.037, +4.662] | +0.000 [+0.000, +0.000] | 6 / 0 |
| Multi-fact personal | SELECTIVE-ALWAYS | 8 / 24 | +0.0 [-12.5, +12.5] | -4.752 [-8.192, -2.517] | +0.000 [+0.000, +0.000] | 1 / 1 |
| Multi-fact personal | SELECTIVE-OFF | 8 / 24 | +95.8 [+87.5, +100.0] | +0.799 [-0.491, +2.264] | +0.000 [+0.000, +0.000] | 23 / 0 |
| Multi-fact personal | ALWAYS-OFF | 8 / 24 | +95.8 [+87.5, +100.0] | +5.551 [+3.087, +8.746] | +0.000 [+0.000, +0.000] | 23 / 0 |
| General without memory need | SELECTIVE-ALWAYS | 8 / 24 | +20.8 [+0.0, +50.0] | +3.273 [+0.762, +6.052] | -0.875 [-1.000, -0.625] | 5 / 0 |
| General without memory need | SELECTIVE-OFF | 8 / 24 | -20.8 [-58.3, +16.7] | +5.939 [+3.001, +8.911] | +0.125 [+0.000, +0.375] | 2 / 7 |
| General without memory need | ALWAYS-OFF | 8 / 24 | -41.7 [-87.5, +4.2] | +2.666 [+1.064, +4.586] | +1.000 [+1.000, +1.000] | 2 / 12 |
| Unknown or conflicting | SELECTIVE-ALWAYS | 8 / 24 | +0.0 [+0.0, +0.0] | -0.396 [-2.664, +2.996] | +0.000 [+0.000, +0.000] | 0 / 0 |
| Unknown or conflicting | SELECTIVE-OFF | 8 / 24 | -70.8 [-100.0, -37.5] | +1.721 [-1.154, +5.271] | +0.000 [+0.000, +0.000] | 0 / 17 |
| Unknown or conflicting | ALWAYS-OFF | 8 / 24 | -70.8 [-100.0, -37.5] | +2.117 [+0.645, +3.698] | +0.000 [+0.000, +0.000] | 0 / 17 |
| Lifecycle or authorization | SELECTIVE-ALWAYS | 8 / 24 | -8.3 [-20.8, +0.0] | -2.473 [-3.768, -1.252] | +0.000 [+0.000, +0.000] | 0 / 2 |
| Lifecycle or authorization | SELECTIVE-OFF | 8 / 24 | -8.3 [-37.5, +20.8] | -0.040 [-3.272, +1.852] | +0.000 [+0.000, +0.000] | 2 / 4 |
| Lifecycle or authorization | ALWAYS-OFF | 8 / 24 | +0.0 [-37.5, +37.5] | +2.433 [-0.728, +4.955] | +0.000 [+0.000, +0.000] | 3 / 3 |

Positive differences favor the left condition for success and increase cost for time/access. Left-only/right-only counts are repeated paired attempts, not independent requests. Paired unnecessary-retrieval Δ/task averages over every paired request, with zeros on needed and denied tasks; it is not the difference between rates restricted to authorized no-memory tasks.

## qwen3:1.7b: retrieval, relevance and disclosure by category

| Category | Policy | Retrievals | Unnecessary / eligible tasks | Relevant retrieved | Relevant supplied | Irrelevant inspected | Irrelevant bounded candidates | Irrelevant supplied |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Direct recall | OFF | 0 | n/a | 0.0% | 0.0% | 0 | 0 | 0 |
| Direct recall | ALWAYS | 24 | n/a | 100.0% | 87.5% | 528 | 456 | 6 |
| Direct recall | SELECTIVE | 24 | n/a | 100.0% | 87.5% | 528 | 456 | 6 |
| Paraphrased recall | OFF | 0 | n/a | 0.0% | 0.0% | 0 | 0 | 0 |
| Paraphrased recall | ALWAYS | 24 | n/a | 87.5% | 25.0% | 528 | 456 | 3 |
| Paraphrased recall | SELECTIVE | 18 | n/a | 75.0% | 25.0% | 396 | 342 | 0 |
| Multi-fact personal | OFF | 0 | n/a | 0.0% | 0.0% | 0 | 0 | 0 |
| Multi-fact personal | ALWAYS | 24 | n/a | 100.0% | 100.0% | 504 | 432 | 6 |
| Multi-fact personal | SELECTIVE | 24 | n/a | 100.0% | 100.0% | 504 | 432 | 6 |
| General without memory need | OFF | 0 | 0/24 | n/a | n/a | 0 | 0 | 0 |
| General without memory need | ALWAYS | 24 | 24/24 | n/a | n/a | 552 | 480 | 12 |
| General without memory need | SELECTIVE | 3 | 3/24 | n/a | n/a | 69 | 60 | 3 |
| Unknown or conflicting | OFF | 0 | n/a | 0.0% | 0.0% | 0 | 0 | 0 |
| Unknown or conflicting | ALWAYS | 24 | n/a | 100.0% | 75.0% | 540 | 468 | 15 |
| Unknown or conflicting | SELECTIVE | 24 | n/a | 100.0% | 75.0% | 540 | 468 | 15 |
| Lifecycle or authorization | OFF | 0 | n/a | 0.0% | 0.0% | 0 | 0 | 0 |
| Lifecycle or authorization | ALWAYS | 18 | n/a | 100.0% | 50.0% | 408 | 354 | 6 |
| Lifecycle or authorization | SELECTIVE | 18 | n/a | 100.0% | 50.0% | 408 | 354 | 6 |

Evidence percentages divide the sum of relevant retrieved/supplied ID occurrences by the sum of all frozen relevant-ID occurrences; they are not means of per-question coverage. Questions with no relevant IDs contribute no coverage denominator. Inspection/candidate/disclosure totals sum each attempt's unique IDs, so the same memory can contribute again on another request or repetition; these are not globally unique memory counts.

## Known-authorized personalization and unavailable information

| Generator | Policy | Known successes | Misses with abstention | Such misses without unsupported/forbidden claims | Known successes with no supplied evidence | Personal unsupported | Failures |
| --- | --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 0/78 | 75 | 75 | 0 | 3 | 0 |
| qwen3:0.6b | ALWAYS | 53/78 | 18 | 18 | 0 | 4 | 0 |
| qwen3:0.6b | SELECTIVE | 53/78 | 18 | 18 | 0 | 4 | 0 |
| qwen3:1.7b | OFF | 0/78 | 74 | 74 | 0 | 1 | 0 |
| qwen3:1.7b | ALWAYS | 53/78 | 14 | 14 | 0 | 2 | 3 |
| qwen3:1.7b | SELECTIVE | 52/78 | 15 | 15 | 0 | 4 | 3 |

| Generator | Unavailable/uncertain task | OFF success | ALWAYS success | SELECTIVE success |
| --- | --- | --- | --- | --- |
| qwen3:0.6b | unknown | 15/18 | 9/18 | 9/18 |
| qwen3:0.6b | conflicting | 6/6 | 0/6 | 0/6 |
| qwen3:0.6b | unavailable_lifecycle | 12/12 | 12/12 | 12/12 |
| qwen3:0.6b | unauthorized | 6/6 | 6/6 | 6/6 |
| qwen3:1.7b | unknown | 17/18 | 6/18 | 6/18 |
| qwen3:1.7b | conflicting | 6/6 | 0/6 | 0/6 |
| qwen3:1.7b | unavailable_lifecycle | 12/12 | 9/12 | 8/12 |
| qwen3:1.7b | unauthorized | 6/6 | 6/6 | 6/6 |

Abstention on a known authorized fact remains a missed task in every condition. The no-unsupported-claim subset describes caution and is not counted as successful recall. Unknown/conflicting/restricted successes follow the same uncertainty/refusal rubric in every condition.

Unsupported-claim flags judge factual truth using the question, common full authorized reference context and general knowledge, not the evidence actually supplied at runtime. A correct known answer produced without supplied personal evidence can therefore pass the task rubric; its separate count above does not establish memory-grounded recall.

## Selection, stage timings and helper behavior

| Generator | Policy | Classifier calls | Unresolved decisions | Selection sensitivity | Specificity | Selection mean | Classifier mean | Retrieval mean | Generation mean | Validation mean | Nested loading mean | Residual mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 0 | 0 | 0.0% | 100.0% | 0.012 | 0.000 | 0.000 | 1.474 | 0.006 | 0.206 | 0.051 |
| qwen3:0.6b | ALWAYS | 0 | 0 | 100.0% | 0.0% | 0.010 | 0.000 | 0.098 | 1.737 | 0.011 | 0.193 | 0.053 |
| qwen3:0.6b | SELECTIVE | 21 | 0 | 94.7% | 75.0% | 0.107 | 0.084 | 0.096 | 1.731 | 0.009 | 0.214 | 0.053 |
| qwen3:1.7b | OFF | 0 | 0 | 0.0% | 100.0% | 0.011 | 0.000 | 0.000 | 7.280 | 0.006 | 0.663 | 0.050 |
| qwen3:1.7b | ALWAYS | 0 | 0 | 100.0% | 0.0% | 0.010 | 0.000 | 0.134 | 10.218 | 0.010 | 1.015 | 0.055 |
| qwen3:1.7b | SELECTIVE | 21 | 0 | 94.7% | 87.5% | 0.696 | 0.670 | 0.146 | 8.173 | 0.009 | 1.196 | 0.054 |

Classifier time is inside selection time; model loading/prefill/decode are inside model calls. Do not add nested stage durations again. Every stage mean divides by all attempted requests in that condition, including zero time when that stage was not invoked. Selection sensitivity and specificity use resolved authorized decisions only; unresolved and unauthorized requests are excluded from those decision denominators and unresolved counts remain visible. Residual time contains unlisted bookkeeping and checks.

| Generator | Policy | Literal speech constraints | Helper counts | Transformations | Prompt tokens | Output tokens | Authorization violations | Forbidden disclosures | Explicit conflicts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 0 | {"none": 144} | {"none": 144} | 39516 | 6070 | 0 | 0 | 0 |
| qwen3:0.6b | ALWAYS | 3 | {"none": 141, "verified_user_relationship": 3} | {"none": 144} | 58377 | 6882 | 0 | 15 | 0 |
| qwen3:0.6b | SELECTIVE | 3 | {"none": 141, "verified_user_relationship": 3} | {"none": 144} | 72825 | 7007 | 0 | 15 | 0 |
| qwen3:1.7b | OFF | 0 | {"none": 144} | {"none": 144} | 39516 | 7191 | 0 | 0 | 0 |
| qwen3:1.7b | ALWAYS | 3 | {"none": 141, "verified_user_relationship": 3} | {"none": 144} | 58377 | 6003 | 0 | 20 | 0 |
| qwen3:1.7b | SELECTIVE | 3 | {"none": 141, "verified_user_relationship": 3} | {"none": 144} | 72825 | 6458 | 0 | 15 | 0 |

Helpers have identical configured availability; evidence can change their realized use, prompts, output lengths and validation paths. These are complete-policy effects, not isolated generator capability.

## Repetition-level totals

| Generator | Repetition | Policy | Success | Retrievals | Unnecessary | Request mean | Failures |
| --- | --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | 1 | OFF | 17/48 | 0 | 0 | 1.603 | 0 |
| qwen3:0.6b | 1 | ALWAYS | 31/48 | 46 | 8 | 1.956 | 0 |
| qwen3:0.6b | 1 | SELECTIVE | 31/48 | 38 | 2 | 2.050 | 0 |
| qwen3:0.6b | 2 | OFF | 17/48 | 0 | 0 | 1.547 | 0 |
| qwen3:0.6b | 2 | ALWAYS | 31/48 | 46 | 8 | 1.926 | 0 |
| qwen3:0.6b | 2 | SELECTIVE | 29/48 | 38 | 2 | 2.028 | 0 |
| qwen3:0.6b | 3 | OFF | 17/48 | 0 | 0 | 1.580 | 0 |
| qwen3:0.6b | 3 | ALWAYS | 31/48 | 46 | 8 | 1.943 | 0 |
| qwen3:0.6b | 3 | SELECTIVE | 31/48 | 38 | 2 | 2.013 | 0 |
| qwen3:1.7b | 1 | OFF | 21/48 | 0 | 0 | 6.214 | 0 |
| qwen3:1.7b | 1 | ALWAYS | 29/48 | 46 | 8 | 12.202 | 1 |
| qwen3:1.7b | 1 | SELECTIVE | 29/48 | 37 | 1 | 13.205 | 2 |
| qwen3:1.7b | 2 | OFF | 22/48 | 0 | 0 | 5.554 | 0 |
| qwen3:1.7b | 2 | ALWAYS | 28/48 | 46 | 8 | 11.702 | 1 |
| qwen3:1.7b | 2 | SELECTIVE | 31/48 | 37 | 1 | 6.834 | 0 |
| qwen3:1.7b | 3 | OFF | 20/48 | 0 | 0 | 10.372 | 1 |
| qwen3:1.7b | 3 | ALWAYS | 29/48 | 46 | 8 | 7.475 | 1 |
| qwen3:1.7b | 3 | SELECTIVE | 29/48 | 37 | 1 | 7.313 | 2 |

## Physical fragment costs and device state

| Physical fragment | Logical slot | Scheduled indices | Generator | Policy | Rep | Attempts | Cold first | Warm mean | Nested load total | Setup | Cleanup | Fragment/attempt | Admission/supervisor overhead | Supervisor fragment/attempt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fragment_01 | 1 | 1–48 | qwen3:0.6b | OFF | 1 | 48 | 11.235 | 1.398 | 9.360 | 0.002 | 0.017 | 1.652 | 0.614 | 1.665 |
| fragment_02 | 2 | 1–48 | qwen3:0.6b | ALWAYS | 1 | 48 | 12.189 | 1.738 | 9.135 | 0.003 | 0.016 | 2.009 | 62.952 | 3.321 |
| fragment_03 | 3 | 1–48 | qwen3:0.6b | SELECTIVE | 1 | 48 | 13.615 | 1.804 | 9.892 | 0.004 | 0.024 | 2.107 | 83.954 | 3.856 |
| fragment_04 | 4 | 1–13 | qwen3:1.7b | SELECTIVE | 1 | 13 | 53.956 | 16.403 | 27.453 | 0.005 | 0.021 | 19.416 | n/a | n/a |
| fragment_05 | 4 | 14–40 | qwen3:1.7b | SELECTIVE | 1 | 27 | 37.693 | 9.185 | 25.137 | 0.004 | 0.020 | 10.399 | 1.432 | 10.452 |
| fragment_06 | 4 | 41–48 | qwen3:1.7b | SELECTIVE | 1 | 8 | 38.098 | 9.777 | 27.765 | 0.002 | 0.020 | 13.885 | 2.252 | 14.167 |
| fragment_07 | 5 | 1–25 | qwen3:1.7b | ALWAYS | 1 | 25 | 42.620 | 10.816 | 24.778 | 0.003 | 0.023 | 12.302 | 25.787 | 13.334 |
| fragment_08 | 5 | 26–48 | qwen3:1.7b | ALWAYS | 1 | 23 | 43.041 | 10.929 | 24.091 | 0.003 | 0.020 | 12.617 | 2.287 | 12.716 |
| fragment_09 | 6 | 1–48 | qwen3:1.7b | OFF | 1 | 48 | 30.694 | 5.693 | 24.336 | 0.002 | 0.021 | 6.351 | 28.127 | 6.937 |
| fragment_10 | 7 | 1–40 | qwen3:1.7b | ALWAYS | 2 | 40 | 43.880 | 11.853 | 24.374 | 0.002 | 0.023 | 12.852 | 81.090 | 14.879 |
| fragment_11 | 7 | 41–48 | qwen3:1.7b | ALWAYS | 2 | 8 | 30.193 | 3.622 | 24.750 | 0.003 | 0.021 | 7.975 | 2.732 | 8.316 |
| fragment_12 | 8 | 1–48 | qwen3:1.7b | OFF | 2 | 48 | 27.587 | 5.086 | 22.304 | 0.003 | 0.022 | 5.740 | 2.316 | 5.788 |
| fragment_13 | 9 | 1–48 | qwen3:1.7b | SELECTIVE | 2 | 48 | 29.362 | 6.354 | 22.103 | 0.002 | 0.022 | 7.048 | 60.377 | 8.306 |
| fragment_14 | 10 | 1–48 | qwen3:0.6b | SELECTIVE | 2 | 48 | 14.252 | 1.768 | 10.497 | 0.002 | 0.017 | 2.220 | 31.696 | 2.880 |
| fragment_15 | 11 | 1–48 | qwen3:0.6b | OFF | 2 | 48 | 10.441 | 1.358 | 9.109 | 0.003 | 0.015 | 1.736 | 61.166 | 3.010 |
| fragment_16 | 12 | 1–48 | qwen3:0.6b | ALWAYS | 2 | 48 | 12.055 | 1.710 | 8.900 | 0.003 | 0.016 | 2.124 | 61.787 | 3.411 |
| fragment_17 | 13 | 1–48 | qwen3:0.6b | ALWAYS | 3 | 48 | 12.361 | 1.721 | 9.710 | 0.002 | 0.020 | 2.174 | 62.526 | 3.477 |
| fragment_18 | 14 | 1–48 | qwen3:0.6b | SELECTIVE | 3 | 48 | 13.384 | 1.771 | 10.468 | 0.004 | 0.022 | 2.249 | 63.334 | 3.569 |
| fragment_19 | 15 | 1–48 | qwen3:0.6b | OFF | 3 | 48 | 12.541 | 1.346 | 11.202 | 0.003 | 0.024 | 1.784 | 63.346 | 3.104 |
| fragment_20 | 16 | 1–42 | qwen3:1.7b | OFF | 3 | 42 | 29.786 | 9.660 | 23.050 | 0.003 | 0.022 | 10.407 | 95.675 | 12.685 |
| fragment_21 | 16 | 43–48 | qwen3:1.7b | OFF | 3 | 6 | 35.175 | 7.371 | 25.748 | 0.003 | 0.019 | 14.289 | 113.784 | 33.253 |
| fragment_22 | 17 | 1–20 | qwen3:1.7b | SELECTIVE | 3 | 20 | 30.650 | 4.626 | 22.508 | 0.002 | 0.017 | 6.690 | 4.411 | 6.911 |
| fragment_23 | 17 | 21–43 | qwen3:1.7b | SELECTIVE | 3 | 23 | 34.444 | 6.464 | 24.007 | 0.002 | 0.019 | 8.506 | 5.616 | 8.750 |
| fragment_24 | 17 | 44–48 | qwen3:1.7b | SELECTIVE | 3 | 5 | 35.089 | 5.188 | 23.308 | 0.003 | 0.020 | 15.771 | 6.697 | 17.110 |
| fragment_25 | 18 | 1–44 | qwen3:1.7b | ALWAYS | 3 | 44 | 32.318 | 6.407 | 23.255 | 0.002 | 0.018 | 7.563 | 6.653 | 7.714 |
| fragment_26 | 18 | 45–48 | qwen3:1.7b | ALWAYS | 3 | 4 | 33.873 | 5.712 | 24.925 | 0.003 | 0.019 | 19.887 | 7.674 | 21.806 |

Each row is one physical worker with its own setup, cleanup, model load and cold first request, including suffix workers whose first scheduled index exceeds 1. Admission/supervisor overhead is that fragment's elapsed supervisor time minus its request-bearing worker's session time. It includes rejected launches, guard checks, ledger verification and waiting, plus worker import/startup and exit/sealing residual; it is not pure waiting. Supervisor fragment/attempt includes that overhead once. Missing original fatal-fragment overhead remains n/a.

| Prior fragment | Next fragment | Between-collection request boundary gap, s |
| --- | --- | --- |
| session_04_admission_retry_04 | session_04_from_14 | 897.547 |
| session_04_from_14 | session_04_from_41 | 191.846 |
| session_05_from_01_admission_retry_01 | session_05_from_26 | 214.037 |
| session_07_from_01_admission_retry_03 | session_07_from_41 | 187.153 |
| session_16_from_01_admission_retry_03 | session_16_from_43_admission_retry_03 | 309.061 |
| session_17_from_01 | session_17_from_21 | 142.034 |
| session_17_from_21 | session_17_from_44 | 144.681 |
| session_18_from_01 | session_18_from_45 | 182.526 |

Boundary gaps run from the prior request finish to the next collection's first request start. They include prior cleanup, the off-run pause, later admission and setup. They are separate from supervisor overhead, are not pure pause, and are not added to measured request totals.

| Collection | Supervisor wall, s | Prior seal header to supervisor start, s |
| --- | --- | --- |
| run_v1 | n/a | n/a |
| run_v2 | 283.244 | 892.740 |
| run_v3 | 448.647 | 184.205 |
| run_v4 | 1223.718 | 204.239 |
| run_v5 | 2220.233 | 172.611 |
| run_v6 | 358.032 | 163.450 |
| run_v7 | 223.498 | 97.517 |
| run_v8 | 449.860 | 93.358 |
| run_v9 | 115.639 | 121.215 |

The seal-header gap includes earlier sealing/exit and the off-run pause. Supervisor wall includes verification, orchestration and child exit/sealing, but excludes the parent final batch manifest, sealing and exit. These scopes overlap other diagnostic timings and are not added to request or fragment totals.

| Generator | Policy | Peak RAM, MiB | Peak logical swap, MiB | Peak °C | GPU allocation min | GPU allocation max | Physical-fragment board J | Max telemetry gap, s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 5845 | 2720 | 60.28 | 1.000 | 1.000 | 3000.4 | 1.020 |
| qwen3:0.6b | ALWAYS | 6178 | 2717 | 60.91 | 1.000 | 1.000 | 3664.1 | 1.396 |
| qwen3:0.6b | SELECTIVE | 6284 | 2722 | 61.06 | 1.000 | 1.000 | 3793.5 | 1.004 |
| qwen3:1.7b | OFF | 6621 | 2777 | 60.75 | 0.541 | 0.736 | 11568.4 | 1.678 |
| qwen3:1.7b | ALWAYS | 6670 | 2915 | 58.06 | 0.515 | 0.762 | 14380.1 | 1.927 |
| qwen3:1.7b | SELECTIVE | 6678 | 2972 | 59.16 | 0.541 | 0.736 | 13129.9 | 1.761 |

GPU allocation fractions are model placement, not utilization or fractions of computation. Logical compressed swap is not extra physical RAM. Board energy covers each physical fragment's sampled telemetry interval, includes background power, has no idle subtraction, and excludes admission waiting and all between-fragment gaps. A condition total is n/a if any session has no valid powered sample-pair interval. Otherwise it sums the available sample-pair intervals; missing-power intervals may be omitted, so a numeric total does not establish complete energy coverage.
