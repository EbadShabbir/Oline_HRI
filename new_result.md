# CLARA: reviewed 56-case development results

**Step 1 is complete: review and verification of the already-collected 56 text cases.** CLARA passed **43/56 complete requests (76.8%)** and failed **13/56**. Useful general help was delivered in **31/42 applicable cases (73.8%)**. No unsupported personal claims were identified by the two assistant reviewers. All 56 attempts were retained, with no missing observations or execution errors.

Collection date: **18 September 2026**, approximately **13:37–13:41 UTC**. Cohort: `structural_repair_20260918/development_v1`. This report completes analysis of the existing collection; it does not represent a new inference run.

## Scope and assessment

- These are **previously exposed development/regression cases**, comprising the earlier 36 exposed cases and a now-exposed 20-case holdout. Historical `holdout` strings in case IDs do not make this collection unseen evidence.
- The independently authored **40-case holdout remains unopened**. No speech capture, text-to-speech, new holdout collection, or small-only/large-only comparison was performed in this step.
- Personal memory was empty and isolated for the evaluation. Correct missing-memory acknowledgments and appropriate clarification can pass; this is not a positive stored-fact recall benchmark.
- Two saved independent assistant reviews assessed delivered text, full requests, prior context and frozen rubrics. Their packets withheld routes, calls, model assignments and timings. Reviews are **assistant assessments, not human validation**.
- Primary reviewers agreed on all 56 whole-answer decisions, all 125 required-component decisions, all useful-help decisions and the absence of identified unsupported personal claims. Four descriptive-flag disagreements were adjudicated without changing a quality score. Both original reviews remain preserved.
- Two separate saved diagnostic assessments judged extraction fidelity and actual answer-review candidates. They agreed on 55/56 extraction decisions and 27/27 candidate-validity decisions. One extraction disagreement was resolved separately by an unblinded adjudicator; primary answer scores were unchanged.

## Answer quality

| Measure | Result |
| --- | ---: |
| Planned / observed / reviewed cases | 56 / 56 / 56 |
| Strict whole-request success | 43/56 (76.8%) |
| Strict-success descriptive Wilson 95% interval | 64.2–85.9% |
| Useful general help when required | 31/42 (73.8%) |
| Useful-help descriptive Wilson 95% interval | 58.9–84.7% |
| Final dependency-label agreement | 53/56 (94.6%) |
| Joint routing and whole-answer success | 43/56 (76.8%) |
| Identified unsupported personal claims | 0/56 |
| Missing observations / execution errors | 0 / 0 |
| Model-generated / application-only deliveries | 20 / 36 |
| Verified task executions | 13/56 |
| Application answer-failure responses | 10/56 |
| Strict success within five seconds | 38/56 (67.9%) |

For reference, this development cohort falls below the protocol’s 80% strict-success and 85% useful-help thresholds. The prospective release decision applies to the still-unopened 40-case evaluation. Zero identified unsupported claims on these 56 prompts does not establish universal protection against unsupported personal statements. Correct routing does not imply correct answers.

| Expected dependency category | Full successes | Meaning |
| --- | ---: | --- |
| `none` | 22/28 (78.6%) | No personal memory needed |
| `optional` | 3/8 (37.5%) | Optional personalization |
| `required` | 8/9 (88.9%) | Required personal recall / missing-evidence handling |
| `clarify` | 10/11 (90.9%) | Clarification required |

## Text-turn latency and runtime

Timings cover the evaluation runner’s complete text-turn boundary, including its guard overhead, to final delivered text or failure. They are not first-token or speech-to-audible-response timings. All-attempt summaries include the quality failures. Percentiles use linear interpolation at `(n−1) × q`.

| Group | Attempts | Median (s) | p95 (s) |
| --- | ---: | ---: | ---: |
| All attempts | 56 | 2.490 | 12.112 |
| Delivered model-generated answers | 20 | 4.311 | 12.583 |
| Application-only deliveries | 36 | 0.099 | 12.112 |

Total measured case time was **229.783 s**; the slowest case took **29.035 s**. Application-only delivery can follow unsuccessful inference: the 36 application deliveries include ten answer-failure responses. It does not mean that all 36 involved no model work.

The frozen configuration provided Qwen3 0.6B and 1.7B, a 2,048-token context, a 192-token output budget, temperature zero, and thinking disabled. All **84 recorded calls** used **`qwen3:1.7b`**: 44 answer-generation, 27 answer-review, and 13 dependency-review calls. Every recorded call completed successfully, with no per-case call-bound violation. Therefore this collection does not establish a small-model selection benefit or a causal cascade speedup.

The target device was the Jetson Orin Nano with 8 GB memory in the recorded 15 W mode. Across 456 telemetry samples, peak reported RAM use was **6,147 MB**, swap use **528 MB**, and temperature **63.343°C**. RAM/swap values retain the telemetry field’s reported MB units and describe the whole device. Collection finalized without a resource-guard violation or cleanup error, and no model remained resident in the final snapshot.

## Component diagnostics

Semantic request extraction was judged faithful for **44/56 (78.6%)**, with descriptive Wilson 95% interval **66.2–87.3%**. All 56 proposals were assessable. The adjudicated disagreement concerned a scheduling request whose central operation was labeled only as a constraint: copied text preserved span coverage but did not preserve that operation’s source role. The final extraction score follows reviewer B on this one case.

The 27 attempted answer-review calls covered 23 cases; 33 cases had no attempted answer-review call. All 27 candidates and decisions were assessable, with no unusable decisions or parse failures. Candidate validity is assessed against the actual reviewed component and relevant original constraints, separately from whole-answer quality.

| Candidate-level outcome | Raw model verdict | Effective application decision |
| --- | ---: | ---: |
| Valid candidate accepted | 21 | 17 |
| Invalid candidate accepted | 5 | 3 |
| Valid candidate rejected | 0 | 4 |
| Invalid candidate rejected | 1 | 3 |

| Error measure | Raw model verdict | Effective application decision |
| --- | --- | --- |
| False acceptance among invalid candidates | 5/6 (83.3%); 95% CI 43.6–97.0% | 3/6 (50.0%); 95% CI 18.8–81.2% |
| False rejection among valid candidates | 0/21 (0.0%); 95% CI 0.0–15.5% | 4/21 (19.0%); 95% CI 7.7–40.0% |

The application reduced invalid acceptances from five to three, but rejected four valid candidates that the raw model had accepted. These are call-level descriptive findings on a small fixed cohort; repeated attempts within one case are dependent. They do not establish population reviewer reliability. A component approval does not establish that the final composed answer satisfied the whole request.

## All 13 failed requests

Ten failures delivered an application failure response or omitted independent requested work; three delivered model-generated answers also failed strict assessment. A successful model call does not establish answer correctness.

| Case | Delivered-answer failure |
| --- | --- |
| `repair_holdout_004` | The supplied paper-fan request is answerable, but the response provides no instructions and fails the required three-line format. |
| `repair_holdout_008` | The response contains no story and fails both required structural features. |
| `quality_holdout_008` | The response replaces the requested rewrite with an inability statement and preserves none of the required message content. |
| `quality_holdout_012` | The inability statement does not complete the self-contained fallback request. |
| `quality_holdout_013` | It avoids adopting the earlier guess but fails to deliver the neutral reply, time commitment, and reply-only output. |
| `quality_holdout_016` | The user expressly required a neutral-greeting draft despite the absent name. That independent task is omitted. |
| `quality_holdout_019` | Both slots were already described as available. Repeating a singular availability confirmation does not identify the chosen slot or request the required clarification. |
| `generalization_holdout_003` | The response supplies only an inability statement and omits every required announcement component. |
| `generalization_holdout_005` | The self-contained science question receives no explanatory content. |
| `generalization_holdout_009` | The response gives an incorrect causal account. A push farther from the hinges has a larger moment arm; the required turning effect is not reduced by being nearer the door’s center of mass. |
| `generalization_holdout_011` | The supplied fallback made personal style information unnecessary, but no explanatory answer is delivered. |
| `generalization_holdout_012` | The explicit genre fallback receives no story content. |
| `generalization_holdout_013` | The durations and sensible sequence are useful, but the frozen rubric explicitly requires start and end times for each chore; the overall endpoints do not satisfy that component. |

## Verification and evidence

The primary measurement audit was rerun against the archived frozen candidate and passed **623/623 checks**. The completed diagnostic audit passed **17/17 checks**, including the prior diagnostic tooling commitment. These audits verify artifact provenance, coverage and numerical consistency; they do not independently certify semantic correctness. Original reviews, original audits, collection records and failed quality outcomes were retained unchanged.

The measured candidate was frozen at **2026-09-18 12:54:21 UTC**, based on repository commit `107db33c733bffc2bb3cad20a2dcd85f01ce5d4a` **plus the local changes captured by its manifest**. The current GitHub source alone must not be assumed identical to that measured snapshot.

This publication contains the Markdown report only. Supporting raw artifacts and the frozen runtime remain in the local evaluation archive. The following paths are relative to `evaluation/structural_repair_20260918/development_v1/`; they are provenance identifiers, not links to files published with this report.

| Local evidence artifact | SHA-256 |
| --- | --- |
| `candidate_freeze.json` | `aa4634b9f3202bd4a4b3ff9d86323f689afa6073f196f20ddcb67009f42616de` |
| `cases.json` | `e9077d8c91888b0a432436ffed2a16837b4fafb0e04c459abc561f9ca8f4834d` |
| `review_packet.json` | `4bd3a284af0577a6e21e920cc2e3d68c002f61d0f3a59285cd2f7c15ffba7dba` |
| `review_a.json` | `6f6853507b5870868b7ee56bf592bba4dbf5ca8248dc2f3785cbcd37e8fe73de` |
| `review_b.json` | `8090bc1d2bb3a90f8ad494283cdc70a426aeeff5767161d78d0c06010f93cdd3` |
| `adjudicated_judgments.json` | `3a789ac2c0386a740f731937219e9224f1159364773eb147fede877817257e13` |
| `adjudication_record.json` | `47d37c272f5a0a2f51ad216f801316562879d266d602c8475f079c36f7b05026` |
| `metrics.json` | `3b36caec9aa525c8e120fd77a97d4bb96d59a3a542efbda0bd54c555e52fb5e2` |
| `per_case.jsonl` | `507afcc4144fddff72254240f7f675aba66d4365eecd66308886a7cd832bc9c9` |
| `step1_verification_v1.json` | `d615eb7e22670876f509f427ce0c3a889f44d1d48fe5f274c650dce708f9304e` |
| `diagnostics_v1/review_a.json` | `1812b33d07140aeaffd44fef8131dee5fe3691aa82b26aeff145fedf0a1c7a6e` |
| `diagnostics_v1/review_b.json` | `4678f9489b913bd4aa269f7d5e184cc416096d06035f0a4cc670c18a4a01fc02` |
| `diagnostics_v1/adjudicated_judgments.json` | `fc4c210152d1caca952dc7a4b0a8159cdaf23d076d62ab150da93fb5ff03ba30` |
| `diagnostics_v1/adjudication_record.json` | `469645d8831841b11b5cae53fd71a36cae7f1f56d0474911c7305fd440e57457` |
| `diagnostics_v1/metrics.json` | `cddb432017279e98308a7a898cbb4cad4cf2cbc34a21182f0c9343ce8caefc3e` |
| `diagnostics_v1/independent_audit.json` | `ba596ed47b543b3872e004dbb994d9b9c64851c212e10db7061e875ccaf11547` |

## Per-case outcomes

`Pass` means the entire visible request passed the frozen rubric, including an appropriate clarification or missing-memory acknowledgment when that was the expected behavior. Case IDs retain their historical names; every row below is exposed development evidence.

| Case | Expected / final dependency | Whole-answer result | Text-turn latency (s) |
| --- | --- | --- | ---: |
| `repair_holdout_001` | `none` / `none` | Pass | 29.035 |
| `repair_holdout_002` | `none` / `none` | Pass | 11.646 |
| `repair_holdout_003` | `none` / `none` | Pass | 3.021 |
| `repair_holdout_004` | `none` / `none` | Fail | 9.731 |
| `repair_holdout_005` | `none` / `none` | Pass | 2.578 |
| `repair_holdout_006` | `none` / `none` | Pass | 4.255 |
| `repair_holdout_007` | `none` / `none` | Pass | 3.870 |
| `repair_holdout_008` | `none` / `none` | Fail | 12.329 |
| `repair_holdout_009` | `optional` / `optional` | Pass | 2.303 |
| `repair_holdout_010` | `optional` / `optional` | Pass | 4.617 |
| `repair_holdout_011` | `required` / `required` | Pass | 0.087 |
| `repair_holdout_012` | `required` / `required` | Pass | 2.849 |
| `repair_holdout_013` | `required` / `required` | Pass | 4.368 |
| `repair_holdout_014` | `clarify` / `clarify` | Pass | 0.063 |
| `repair_holdout_015` | `clarify` / `clarify` | Pass | 0.054 |
| `repair_holdout_016` | `clarify` / `clarify` | Pass | 0.030 |
| `quality_holdout_001` | `none` / `none` | Pass | 0.077 |
| `quality_holdout_002` | `none` / `none` | Pass | 0.062 |
| `quality_holdout_003` | `none` / `none` | Pass | 4.531 |
| `quality_holdout_004` | `none` / `none` | Pass | 0.194 |
| `quality_holdout_005` | `none` / `none` | Pass | 7.615 |
| `quality_holdout_006` | `none` / `none` | Pass | 0.100 |
| `quality_holdout_007` | `none` / `none` | Pass | 0.079 |
| `quality_holdout_008` | `none` / `none` | Fail | 5.530 |
| `quality_holdout_009` | `none` / `none` | Pass | 6.587 |
| `quality_holdout_010` | `none` / `none` | Pass | 0.125 |
| `quality_holdout_011` | `optional` / `optional` | Pass | 3.824 |
| `quality_holdout_012` | `optional` / `optional` | Fail | 10.837 |
| `quality_holdout_013` | `optional` / `optional` | Fail | 9.993 |
| `quality_holdout_014` | `required` / `required` | Pass | 0.118 |
| `quality_holdout_015` | `required` / `required` | Pass | 0.257 |
| `quality_holdout_016` | `required` / `required` | Fail | 6.815 |
| `quality_holdout_017` | `clarify` / `clarify` | Pass | 0.064 |
| `quality_holdout_018` | `clarify` / `clarify` | Pass | 0.042 |
| `quality_holdout_019` | `clarify` / `none` | Fail | 2.403 |
| `quality_holdout_020` | `clarify` / `clarify` | Pass | 0.057 |
| `generalization_holdout_001` | `none` / `none` | Pass | 0.076 |
| `generalization_holdout_002` | `none` / `none` | Pass | 0.080 |
| `generalization_holdout_003` | `none` / `none` | Fail | 7.058 |
| `generalization_holdout_004` | `none` / `none` | Pass | 0.149 |
| `generalization_holdout_005` | `none` / `none` | Fail | 10.158 |
| `generalization_holdout_006` | `none` / `none` | Pass | 0.092 |
| `generalization_holdout_007` | `none` / `none` | Pass | 4.061 |
| `generalization_holdout_008` | `none` / `none` | Pass | 7.026 |
| `generalization_holdout_009` | `none` / `none` | Fail | 5.062 |
| `generalization_holdout_010` | `none` / `none` | Pass | 0.112 |
| `generalization_holdout_011` | `optional` / `none` | Fail | 12.040 |
| `generalization_holdout_012` | `optional` / `none` | Fail | 17.773 |
| `generalization_holdout_013` | `optional` / `optional` | Fail | 11.718 |
| `generalization_holdout_014` | `required` / `required` | Pass | 0.170 |
| `generalization_holdout_015` | `required` / `required` | Pass | 0.098 |
| `generalization_holdout_016` | `required` / `required` | Pass | 3.771 |
| `generalization_holdout_017` | `clarify` / `clarify` | Pass | 0.035 |
| `generalization_holdout_018` | `clarify` / `clarify` | Pass | 0.036 |
| `generalization_holdout_019` | `clarify` / `clarify` | Pass | 0.068 |
| `generalization_holdout_020` | `clarify` / `clarify` | Pass | 0.057 |

## Remaining evaluation work

Only checklist item 1 is completed here. The eight-question offline voice smoke test, final candidate freeze, 40-case unseen evaluation, matched CLARA/small-only/large-only comparison with fictional profiles, controlled spoken evaluation, and matched text-versus-speech comparison remain separate work. Human validation also remains pending. Any runtime repair informed by future unseen results requires a new candidate and independent data before another unseen-performance claim.

**Conclusion:** this completed development review identifies functioning execution and memory-evidence handling alongside substantial answer omissions, incorrect answers, extraction errors and reviewer mistakes. It supports reporting the measured 43/56 development result; it does not establish reliable unseen performance or complete spoken-pipeline performance.
