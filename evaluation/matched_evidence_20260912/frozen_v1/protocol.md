# CLARA matched-evidence generator capability protocol

Prepared before primary inference, 2026-09-12. The user specifies 120 fresh requests,
30 per category, extending Stage 1's smaller proposal. This is an evidence-controlled
component diagnostic, not retrieval, routing, application, or spoken-system accuracy.

## Workload and review

120 assistant-authored independent fictional scenarios, one request each: routine
general, general with several explicit constraints, direct personal recall, and
personal temporal reasoning/synthesis. Balanced coverage is not a household frequency
estimate. Evidence includes answerable, unknown and unresolved conflicting cases.
Empty conversation history for every request. Every supplied record is retained whole.
A separate assistant reviews questions, evidence and all rubrics before inference;
its approval is tied to the final dataset hash. Human dataset validation is pending.
References live only in rubrics. No answer, rubric, category, evidence-status label,
scenario ID or request ID is supplied to the generator.

## Controlled generation

Only installed qwen3:0.6b and qwen3:1.7b, with digests, GGUF metadata, model templates,
runtime version, Python, source files and hashes frozen. Direct local /api/generate
with raw=true uses one explicitly rendered Qwen3 chat template, /no_think and the
empty closed think prefix, plus think=false. Both tags have the same installed
chat template. One ordinary string field, {"answer": string}, without literals,
enumerated solutions, answer hints or task-specific schema constraints. Streamed
output is archived without rewriting. JSON transport/schema is assessed separately
from semantics. No routers, live retrieval, answer composers, answer rewriting,
application validators, literal-answer constraints, reference notes, or fallbacks.

Identical input bytes except the required model selector: prompt, complete evidence,
history, schema, raw/stream/think/keep_alive flags and options. Context 2048;
output cap 192; temperature 0; seed 42; thinking disabled. Explicit common options:
top_k 20, top_p .95, repeat_penalty 1, num_batch 512 and Qwen chat stop tokens.
Automatic placement remains Ollama-controlled and is measured, not tuned per arm.
Each prompt must fit a conservative byte-level BPE token upper bound, reserving
192 output tokens and 64 safety tokens. Tokenizer metadata/byte coverage proof is
frozen. Runtime prompt_eval_count is additionally checked, including the entire
prompt; no evidence packing/truncation occurs in the runner.

## Schedule, timing and resource policy

Random schedule seed 42120; six paired blocks, twenty different requests per block
(five/category, interleaved). Blocks use AB, BA, AB, BA, AB, BA, where A is 0.6B and
B is 1.7B. Identical within-block request order for both models. This yields 120
requests/model and 240 primary attempts, no repetitions or best-of selection.
At the start of each model block require no resident model, admit under existing
post-memory device policy, explicitly preload only the selected model, retain it
for twenty requests, then unload it. Twelve preload plus twelve cleanup calls
are diagnostic lifecycle events, not primary answers. No request retries. Errors
retain their primary slot; a violated guard or lost residency stops collection.
Any interruption is reported; unattempted slots are not filled from tail checks.

Reuse the existing post_memory_existing_swap_reserve_v2 limits: startup available
RAM >=2 GiB, temperature <55 C; runtime available RAM >=768 MiB, temperature <68 C;
both logical swap ceilings use existing 3901608 KiB capacity minus 256 MiB. No OS
configuration changes. Require active fan and 15W mode 0 at admission/final capture, unchanged boot/thermal-trip
counters, one selected model at most. Capture device state, swap configuration,
storage and background processes. Use 500 ms tegrastats; telemetry stalls >5 s
abort via an active periodic signal watchdog. Absolute request/load timeout 120 s;
cleanup timeout 30 s. Between blocks, allow up to 900 s under unchanged startup
guards, recording each check every 20 s. Preserve thermal/carry-over waits separately.

Verify actual response model and resident name/digest/context (2048) before/after
each primary request. Verify source/model/runtime freeze again at completion.
Use a nonblocking cooperative file lock and serialized calls; residency observations
do not prove absence of every unrelated client between samples.

Measure direct HTTP submit-to-complete/error wall time, total attempt time including
post-checks, backend load/prefill/decode times and output tokens. Explicit preload
wall time is separate from warm request time. Report any backend per-request load
residuals rather than calling them zero. Report startup-amortized totals over the
20-request blocks, eviction and waits separately. No token-first/speech latency.
Whole-device sampled power integration includes background load, no idle subtraction;
report sample windows/coverage, no model-only/per-token energy claim. RAM and logical
zram occupancy are distinct and must not be added together.

## Blinded assistant judgments

Randomized opaque answer IDs and randomized row orders hide model, timings, block,
request ID and mapping. Every attempted answer is represented; do not deduplicate.
Two fresh-context independent assistant reviewers receive only question, complete
evidence, rubric, answer and shared scoring instructions. Mapping remains unprovided
until both judgment files are frozen by hash and read-only permissions. Reviewers do
not read raw runs, source, dataset metadata, mapping or each other's judgments.
Blinding is procedural (shared filesystem, no enforced permission partition).

Each reviewer assigns one label: complete, appropriate_abstention,
appropriate_uncertainty, partial, incorrect, inappropriate_abstention, or
technical_failure; and Boolean unsupported_claim and unsupported_personal_claim,
with concise rationale. Unsupported claims are substantive invented or contradicted
claims, not ordinary harmless explanation/inference. Partial means a materially useful
correct subset but at least one unmet required element/constraint; a central wrong
result is incorrect. For unknown/conflict tasks, complete credit requires all rubric
requirements, including known requested facts. Unsupported guessing cannot earn full
credit. Reference answers are illustrative, not exact-match targets. Equivalent
wording/format is accepted unless the request explicitly constrains it. Word limits
apply to the answer string (whitespace-separated words), not JSON overhead.

Full-rubric success = complete or appropriate_abstention or appropriate_uncertainty.
Unanswerable cases can earn success for correct uncertainty, while abstention on an
answerable task fails. Invalid schema, truncation, errors/timeouts/interruption count
as technical failures in the primary full-response metric. Raw useful partial text
is preserved and described, but cannot turn an incomplete transport into success.
A third blinded assistant adjudicates all label or flag disagreements before unblinding.
Additional scoring defects found in audit are preserved with explicit amendments;
never erase initial judgments. All reviews are assistant review; independent human
validation remains pending.

## Analysis fixed before answers

Overall and by category, report both correct, only-small correct, only-large correct,
neither correct; per-model semantic labels, unsupported claims, failures and evidence
status strata. Include all requests and unsuccessful attempts. Report representative
paired examples from every observed outcome, including unfavorable results. Summarize
mean/median/p95 (linear interpolation) request latency, prefill/decode/loading, placement,
RAM/swap/temperature and sampled energy. Report measured extra cost of 1.7B overall
and on rescued requests. An answerable only-large success is an observed useful rescue;
unknown/conflict-only improvements are separately identified. No acceptance deadline,
noninferiority margin or cost-acceptability threshold is invented after results.

Use a category-stratified paired bootstrap (10000 resamples, seed 42121) over the
120 independent authored scenarios for a descriptive 95% interval on quality difference.
One request/scenario avoids within-scenario repeats, but shared authorship/templates
and assistant judgment limit statistical generalization. Report pair counts as primary.
No router/cascade gain is inferred; an oracle sum is at most diagnostic headroom and
is not a measured selector. Whether extra cost is acceptable requires an application
requirement outside this component experiment.

## Preservation and reproducibility

New exclusive experiment directories, durable attempt-start and attempt-finish records,
raw HTTP chunks (base64), parsed raw response without modification, errors and telemetry.
No overwritten prior runs. Frozen inputs/source and finished collection/reviews/reports
are sealed with SHA256 manifests and read-only permissions. This is application-level
immutability, not privileged write-once storage. SIGKILL/power loss may leave only a
start record or partial HTTP chunks; analysis must reconcile starts to finishes and
count dangling starts as interrupted attempts. Save reproducible shell commands and
update results.md/developments.MD after independent review and analysis.

Before primary collection, run the frozen runner on two fixed unrelated harness
requests per model (four separately archived smoke attempts). They check raw endpoint,
loading, schema, identity, repeated residency and complete telemetry capture. Smoke
answers are excluded from every primary score; no primary prompt/rubric is tuned.
Offline mocked failure-path tests precede these live harness checks.
