# Matched changing-memory repair comparison

The same 24 checkpoint IDs and complete expected-state/rubric objects match exactly.

| Metric | Original matched baseline | Repaired runtime | Change |
| --- | ---: | ---: | ---: |
| planned | 24 | 24 | +0 |
| delivered | 23 | 24 | +1 |
| useful_correct | 10 | 24 | +14 |
| forbidden_disclosure | 9 | 0 | -9 |
| revoked_original_disclosure | 9 | 0 | -9 |
| unstored_replacement_disclosure | 0 | 0 | +0 |
| withheld | 1 | 0 | -1 |
| interrupted | 0 | 0 | +0 |
| missing | 0 | 0 | +0 |

These selected development scenarios were chosen after baseline failures. This is a targeted matched regression, not held-out evaluation. The full baseline count is context only and is never used as a comparison denominator.

Existing frozen assistant judgments determine every success/disclosure/category count. No answer is rescored. Withholding, interruption and missing delivery never count as useful recall. Human validation is pending.

`aggregate.csv` includes all checkpoints and branch, history, restart, expected-kind and scenario splits. All deltas are repair minus baseline; positive disclosure or withholding deltas mean more failures. `classification_transitions.csv` reports both changed and unchanged judgment categories. `checkpoints.csv` preserves both delivered answers and original review reasons.

`revoked_original_disclosure` requires a correction/deletion/expiry state and the original subject value in the frozen disclosed-value list. `unstored_replacement_disclosure` concerns replacement claims in deletion/expiry branches that never stored that value. These are judgment-derived counts, not new text matching.

Repair diagnostic files copy recorded new-system metadata only. Constraints come from the trace preserved in observed_record; routing and generation policy come from diagnostics. Null means absent or explicitly null; field-present flags distinguish those for constraint/generation policy. No constraint, policy or actual model is inferred from a task label or the answer text. These fields diagnose delivered-system paths; an answer constraint does not establish unconstrained model reasoning.

`wall_latency.csv` reports measured end-to-end conversation-checkpoint wall time, including routing, retrieval, generation and validation. It excludes setup/mutation turns and admission/cooling gaps between operations. Timing requires an explicit wall_ns trace and matching diagnostic wall_seconds; missing timing is counted, never replaced with zero. Median uses the ordinary sample median; p95 is nearest-rank ceil(0.95*n). All-attempt rows include withheld/interrupted checkpoints. Delivered-only rows condition separately on each system's delivered status, so their membership and sample counts can differ. Deltas are descriptive, not randomized causal latency estimates.

`actual_generator_counts.csv` counts returned generator model tags recorded in diagnostics for each system on the matched checkpoints. Multiple generation/fallback calls count separately; classifier calls and setup disclosures are excluded. Missing metadata and explicit empty returned-model lists are separate fields. Nominal routing decisions never substitute for actual model calls.

Results concern text, real worker process restart and controlled logical expiry. They do not establish universal dialogue handling, power-loss recovery or spoken performance.

Reproduce with the command recorded in `provenance.json` and a new output directory. Inputs and output are sealed; all unfavorable baseline and repair judgments are preserved.
