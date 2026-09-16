# Release-v2 review protocol: streaming addendum v1

This addendum is written before the reviewer has opened any release-v2 case, expected label, or observation. It supplements, and does not modify, `review_plan_v1.md` (SHA256 `edadae26f204e29d0b62ee30db1c9f779a98f20594ecc2066e8f1ee02ff43efd`). The original rubric, provenance requirements, and acceptance criteria remain in force.

After root freezes the candidate source, model, configuration, and input artifacts and explicitly sends the stream-review start signal, the reviewer may inspect completed observation rows as they arrive. This replaces only the original instruction to wait for the completed replay before opening observations. The freeze and explicit start signal are both required; elapsed time or file existence is not authorization to begin.

Only completed rows may be graded. An incomplete trailing JSONL record is pending evidence, not a completed case or an execution failure. Preserve observation identity and trace references for each provisional judgment. A missing case is counted and reported under the original rubric when the run has ended, not silently excluded.

Streaming review permits reading and durable annotation only. No release-derived feedback may alter runtime code, models, prompts, configuration, cases, labels, or later requests in the ongoing replay. Review findings are quarantined from runtime decisions and prompt construction. A candidate change would require explicit versioning and separate assessment rather than silently continuing the same frozen release run.

All 32 requested cases remain in the final denominator. Final aggregation, source/input integrity checks, cleanup status, completeness checks, and release conclusions occur only after the run completes. Partial annotations are provisional and cannot be represented as the final release result. Retain the original separation of raw/final/effective routing, actual answer usefulness, unnecessary clarification, mixed components, count/draft constraints, operational errors, and evidence authorization.

Save this addendum and its checksum alongside the untouched original plan. The final review will identify both protocol documents and hashes so the timing change is auditable.
