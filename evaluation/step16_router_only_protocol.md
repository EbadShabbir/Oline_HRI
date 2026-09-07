# Step 16 supplementary router-only measurement

This supplement was specified after the interrupted 4B run and before
collecting router-only outputs. It allows the independent router measurement
to proceed while further 4B execution awaits approval.

Run all 30 fictional-suite prompts once, in manifest order, through the
production `ConversationRouter` with empty history. Use only `qwen3:0.6b`,
temperature 0, seed 42, and the configured context/output limits. A predicted
`large` route is recorded as a classification decision; it does not execute
the selected generator. No answer generation or memory retrieval is part of
this supplement. Expected routes and answer/retrieval gold remain evaluator-side.

Persist every route observation, including failures, and report memory-gate,
model-size, and joint accuracy over all 30 expected cases. Include confusion
matrices, incorrect escalation/non-escalation counts, predicted model shares,
router-call latency p50/p95, and Ollama token counts where available. Use
nearest-rank percentiles and include observed failed-call latency. Record the
exact suite/configuration hashes, model identity, and measurement timestamps.

These measurements do not fill adaptive answer slots or complete any missing
baseline. They cannot establish compute saved, answer correctness, or the
actual large-generator invocation rate. Labels remain
`author_gold_pending_independent_review`, and one pass provides a provisional
device snapshot. Preserve the original four-baseline protocol and its pending
slots unchanged.
