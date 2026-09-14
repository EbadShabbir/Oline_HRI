# Third explicit continuation: preserve 217 attempts and execute 647 remaining

The sealed first continuation amendment remains the procedural authority.
The original 44 execution files and four supplemental continuation files,
models, snapshot, questions, references, policies, prompts, helpers, decoding,
validators, analysis rules, device baseline and resource limits are unchanged.

The sealed cumulative `run_v3` retains 217 unique attempts: 214 delivered
observations and three memory-floor interruptions. Logical block 4 is fully
covered across its original and continued physical fragments. Logical block 5
(`qwen3:1.7b`, ALWAYS PERMITTED, repetition 1) recorded its first 25 requests;
the 25th (`ir_02_06`) was interrupted by the unchanged available-memory runtime
floor. All three interrupted attempts count once as failures and are retained
with their original timings and available evidence, traces and transport data.

Independent metadata review must verify the exact 217-request frozen prefix,
all previous source/plan/ledger/session seals, unchanged snapshot and baseline,
clean model eviction, and complete durable-start/observation correspondence.
The next suffix is block 5 positions 26–48 (23 requests), then blocks 6–18
(624 requests): exactly 647 unattempted requests. This plan is authorized only
as `continuation_v3` for the new `run_v4` output directory.

No attempted request may be retried. The existing one-use ledgers, inference
lock, sole-model residency within each physical fragment, cold admission,
600-second bounded zero-attempt recovery and fatal-stop rules remain in force.
Any further fatal interruption ends its collection and requires another
explicit independently reviewed plan. No planned chunking or resource-limit
relaxation is introduced.

Report 18 planned logical blocks and at least 21 actual physical fragments on
completion, with all failed attempts, extra cold starts, loading, fragment
overhead and inter-run boundary gaps retained. Recurrent memory-floor stops
prevent claiming uninterrupted sustained large-model operation. The frozen
task rubric and paired eight-scenario dependent analysis remain unchanged;
independent human validation is pending.
