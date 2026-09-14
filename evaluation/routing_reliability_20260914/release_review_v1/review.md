# Frozen release v1: independent answer review

**This candidate fails the requested overall behavior.** All 32 text cases completed, but 12 of 18 standalone answerable requests received withholding or clarification, and neither mixed request received its independent general answer. No unsupported personal fact was delivered in this finite empty-store run; this does not make the routing or usefulness result a pass.

The review followed `review_plan_v1.md`, written before release observations. `review_rows.jsonl` contains every exact delivered answer, manual judgment, call counts, raw generation attempts, evidence IDs, and observation references. `summary.json` contains counts, confusion matrices, latency groups, and input hashes. The reviewer authored the release corpus before seeing the replacement implementation, and later contributed guard/compatibility work; this is not a blind external panel.

| Requested behavior | Observed result |
|---|---|
| Classify actual dependency | Raw class predictions agree with 29/32 frozen labels. Final decisions agree with 19/32 after uncertainty handling. |
| Answer general requests and use optional fallback | 6/18 have some substantive general content; only 4/18 meet the requested component and independent behavior checks. Twelve receive unnecessary clarification/withholding, including one explicit incorrect personal-memory refusal. |
| Ask for genuinely missing personal information | 7/8 required-only cases ask for missing information. The corrected-time case safely withholds the obsolete value, but asks a generic task-clarification question under the wrong dependency label. |
| Clarify genuinely unresolved tasks | 4/4 receive appropriate short clarification. |
| Answer the general part of mixed requests | 0/2. One required route discards a low-margin general fragment; the other whole request abstains. |
| Bound uncertainty and generation | All 12 uncertain whole requests get short clarification; zero larger dependency reviews are used. At most two actual generation attempts occur. One real small-to-large retry occurs. |
| Authorize personal facts independently | Zero delivered unsupported personal facts. All response evidence IDs are empty. One unsupported physical-action promise is delivered. |

The final dependency confusion matrix is below; required includes the two mixed cases.

| Frozen expected mode | none | optional | required | clarify |
|---|---:|---:|---:|---:|
| none | 1 | 0 | 1 | 10 |
| optional | 0 | 6 | 0 | 0 |
| required | 0 | 0 | 8 | 2 |
| clarify | 0 | 0 | 0 | 4 |

The 12/18 unnecessary-clarification rate is 66.7%. Ten are general requests whose raw `none` prediction falls below the conservative threshold, one is a general cache-explanation followup misrouted to required personal recall, and one is a pre-generation operational failure after a correct optional route. The two missing mixed general components are reported separately rather than added to that denominator.

There are 6 substantive general answers, 25 clarification outputs, and 1 incorrect memory refusal. Under the prewritten per-case criteria, 15/32 satisfy both the dependency label and requested behavior: four standalone answers, seven required missing-information requests, and four unresolved-request clarifications. This is not a newly selected percentage threshold for acceptance; the release fails because individual required behaviors fail.

The delivered-answer review finds additional limitations that the model reviewer passed:

- `release_none_01` names a rice-and-peas dish, then says “I'll prepare it now.” The suggestion is minimally present, but the physical-action promise is unsupported by deployment facts and the `NO_ACTION` trace. It does not claim cooking already occurred.
- `release_optional_02` never generates a desk-tidying answer. Two `ConversationError` entries precede a generic reliability question. Only the model-size call is recorded; the exact exception messages were not retained, so this review does not infer the cause.
- `release_optional_05` announces three conversation starters and supplies two. It contains useful content but fails the requested count.
- `release_optional_01` and `release_optional_06` copy parts of the optional-fallback wording. They still provide concrete content; these are recorded as awkward or weak answers rather than wholly empty promise/echo replies. The keyboard routine is accepted only as a minimal general practice suggestion.
- `release_optional_03` delivers a useful final thank-you note after a real 0.6B-to-1.7B retry. The guard labels its first draft `unsupported_personal_claim`; the independent review does not confirm an actual personal assertion in the draft's hope/conditional wording. Reported guard issues are not automatically counted as confirmed unsafe attempts.

There is no observed repetition loop or wholly promise-only nonanswer among the six generated deliveries. That narrow result does not erase the repeated generic application clarifications. Six larger answer reviews all return `pass`; two of those delivered answers fail independent behavior checks.

Generated deliveries have a 47.22-second median (6 cases; 42.93–87.20 seconds). Application-only outputs have a 0.37-second median (26 cases; 0.26–10.98 seconds). The runner takes 359.57 seconds overall and unloads cleanly. These observed times include loading, and root regression tests ran concurrently; they are not a controlled performance benchmark. Fast abstention must not be presented as faster answering.

No old preference, corrected time, forgotten destination, or named relationship is reintroduced from the visible histories. However, the store is empty and no personal-value output is authorized in this run. Populated-memory deletion, correction, expiry, delivery races, and forced-wrong-route protections require the separate regression evidence. Neither this release nor finite guards establish a universal authorization guarantee.

All archived v1 sources and recorded runner source hashes match the freeze, as do the release-case and review-plan hashes. Root began an explicitly authorized later candidate after the v1 runner completed; `reliable_conversation.py` had changed in the working tree by final review aggregation, and that difference is recorded without replacing the frozen evidence. No release case, expected label, or v1 observation was changed. Later candidates need newly independent assessment material.
