# Development iteration 1 — unsuccessful

Twelve previously seen cases were run in their frozen order on the archived candidate. All twelve completed and all device guards/cleanup checks passed. One independent assistant reviewer graded sanitized deliveries; root checked and accepted the judgments.

- Final dependency agreement: 4/12 (raw classifier 10/12).
- Full-task quality: 1/12; both route and quality: 1/12.
- Useful general content: 2/10 applicable tasks.
- All-case wall latency: median 4.031 seconds, p95 16.084 seconds. Only four deliveries contained generated answers; eight were application responses. This is not evidence of a useful speed improvement.
- Independent audit: 205/205 checks passed. Evaluation integrity is separate from candidate quality.

The recorded prompts exposed a wiring error: ReliableConversation's un-routed generation path omitted general_response_rule, including the newly added output instructions. The mode reviewer also changed complete general tasks to required recall. The iteration is retained as unsuccessful development evidence; no holdout cases were opened. Subsequent repairs address these defects and must be measured separately.

Exact source/tests, raw model calls, all rejected attempts, telemetry, review packets, original judgments, metrics and audit are adjacent. See metrics.json for unrounded values and group denominators.
