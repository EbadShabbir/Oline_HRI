# Independent final integrity and diagnosis notes

This is an unblinded technical audit, performed after the final collection was sealed and both original assistant reviews were frozen. It does not replace the blinded delivered-answer judgments or pending human validation. No model inference, semantic rescoring, runtime changes, analyzer changes, or audit-code changes were made for this verification.

## Completed collection and integrity

The full audit ran once and passed all **31,342 checks across 82 kinds, with zero integrity violations**. All 288 unique planned checkpoints were observed. There were 36 independent persistent evaluation databases, 36 real scheduled process restarts, and 72 admitted worker process segments. All 552 authored operations started and finished. Actual API acknowledgments cover 72 remember operations, 12 corrections, and 12 forgetting operations; 24 record IDs were purged in the separate expiry branches. Deletion did not substitute for expiry.

There were 85 worker fragments: 72 admitted segments and 13 preserved startup-temperature rejections. Each rejected fragment performed zero operations and zero inference, so continuation did not repeat an attempted checkpoint. The 72 admitted process identities should not be described as all physical launches. Every scored checkpoint completed; 283 delivered answers and five withheld answers are recorded. Another 36 setup disclosure answers were delivered, giving 324 total answer rows and 319 total delivered rows.

The audit's 42 system observations comprise 13 startup rejections, 24 retained-history checkpoints whose original disclosure statement had been pruned, and five withheld answers. These are preserved system behavior, not integrity violations. The absence of integrity violations does not mean the delivered answers were correct.

The audit and its exact command/log receipt are [collection_audit_v1.json](collection_audit_v1.json), [collection_audit_v1.log](collection_audit_v1.log), and [collection_audit_v1_command.json](collection_audit_v1_command.json). The JSON SHA-256 is `e754a02b39adb3f3b2a8a5cd5bf41e6008dbbb9bc2cc111e82f33f7ff0f7de49`. All are read-only.

## Resources, models, and history exposure

All 972 chat calls link to preserved HTTP requests and received content. The two selectors each used `qwen3:0.6b` 324 times. Actual scored generation used `qwen3:0.6b` 254 times and `qwen3:1.7b` 34 times; all 36 setup generations used the smaller model. Requested and returned generation aliases agree. This separates actual generation from nominal routing decisions and classifier calls.

The 6,450 telemetry samples reached a maximum temperature of 58.281°C, maximum reported RAM use of 6,668 MB out of 7,620 MB, and maximum reported swap use of 448 MB. There were no recorded runtime guard violations or cleanup errors. Minimum captured boundary `MemAvailable` was 1,469,760 KiB. RAM-used telemetry is not Linux `MemAvailable`; these samples and guard outcomes do not establish unobserved instantaneous resource values. Startup temperature rejections remained effective and were preserved.

Across 180 retained-history checkpoints, the exact original user statement was present in 144 and forwarded to actual generation in 94. Literal original-value text was present in 164 and forwarded in 114. The extra 20 witnesses occur after restart, when assistant echoes can retain old values after the original statement is pruned. All 108 fresh-history checkpoints have neither witness. Literal case-insensitive matching is a lower bound on exposure; absence is not semantic absence, and exposure is not answer disclosure. Time aliases may differ. Forwarding witnesses intersect actual generation messages with preceding history and exclude system, current-request, and evidence-tail text.

## Independent analysis comparison

[final_analysis_verification_v3.json](final_analysis_verification_v3.json) verifies the two final analysis seals, compares every non-diagnostic field of all 288 reviewed rows, and compares all three frozen vote files byte-for-byte. All match. All answer metrics also match exactly after excluding diagnostic finding counts. Only five withheld-row diagnostics change: actual generation-request evidence removes the five erroneous v1 evidence-selection omissions. The four remaining omissions are real production behavior. Reproducible source, log, and command receipt are adjacent; the verification JSON SHA-256 is `61af91a605a45047423a8c8ba704feccff801a47d4b8e84bd2d9c88191e4c38b`.

Two failed read-only comparison wrappers are preserved. The first incorrectly required the diagnostic Markdown rendering to be identical. The second included the differently shaped collection-level `finish.json` when aggregating worker resources. The third changes only those auxiliary assumptions. Neither failure caused an experiment, analysis, judgment, or audit change.

## Generation versus evidence selection and transformation

All **131** rows labeled `delivered_semantic_failure_with_sufficient_evidence` have parsed raw HTTP JSON `speech` exactly equal to the delivered speech; none has a recorded response transform. Therefore their delivered defects were already present in model output and passed validation. The label includes **77 uncertainty tasks with no required fact**, where the evidence condition is vacuously satisfied. Only **54** require an available fact: 46 historical-control, five original-value, and three replacement-value tasks. Do not describe all 131 as answers generated from supplied factual evidence.

Across all delivered rows, 58 raw speeches changed to the fixed application abstention, “I do not have a verified personal memory that answers that.” Their recorded `response_transform` remains null, so that convenience field alone is insufficient to detect all transformations. The actual frozen implementation performs this normalization in `frozen_v1/source/src/oline_hri/conversation.py:1115`. Mechanical raw-to-delivered comparison captures it. These 58 are outside the 131-row group.

The four genuine evidence-selection omissions are `cm06_expiry_before_fresh`, `cm07_correction_recalled`, `cm07_deletion_recalled`, and `cm07_expiry_before_fresh`. Every required record was present, eligible, and returned by retrieval. Each actual generation request supplied zero memory records, contained no `PERSONAL_MEMORY_DATA` envelope, and explicitly told generation there were no verified records. The normalizer then delivered the fixed abstention. This is production request-linked selection behavior, consistent with the conservative selection path at `conversation.py:853` and `conversation.py:1541`, not a remaining extraction gap. The complete four request/retrieval witnesses are in the verification JSON. Their existing unsuccessful-recall scores remain unchanged.

## Two fresh-history forbidden answers after restart

Both `cm01_deletion_restart_fresh` and `cm01_expiry_restart_fresh` delivered “Your current preferred tea is jasmine tea without sugar.” The original subject in those independent branches was rooibos; jasmine was never stored there. Their actual generator system prompts contain the example `I prefer jasmine tea without sugar.` Neither classifier prompt contains jasmine. History was empty, no evidence was supplied, and the memory route was skipped.

This provides a concrete matching value in the actual generation input. It supports a prompt-example explanation, while not establishing causality or excluding other model influences. These two answers are forbidden unsupported personal disclosures under the frozen rubric, not resurrection of deleted/expired rooibos and not evidence of cross-database or cache contamination. The full matching system messages and metadata are preserved in the verification JSON.

These findings concern application process restart and controlled logical-time expiry, not power-loss recovery, elapsed real-time retention, or spoken performance.
