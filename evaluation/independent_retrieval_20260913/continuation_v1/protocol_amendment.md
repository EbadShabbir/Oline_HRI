# Prospective orchestration amendment after the first runtime interruption

The original frozen questions, memory snapshot, references, protocol, all 44
execution source files, models, decoding, policies, evidence limits, prompts,
helpers, validators and resource limits remain unchanged. This amendment adds
only immutable suffix-continuation orchestration and its validation. No answer
has been scored or used to alter the workload.

## Preserved interruption and exact coverage

The sealed `run_v1` contains 157 attempts: all 48 requests in each of the first
three logical condition blocks, followed by 13 requests in block 4
(`qwen3:1.7b`, SELECTIVE, repetition 1). Its 13th request was interrupted by the
unchanged available-memory runtime floor. All 156 delivered observations and
the interrupted observation remain intact. The interrupted request counts
once as an attempted failure and retains its exact timing, traces, supplied
evidence and available raw transport bytes.

An independent metadata audit must verify that these 157 identities form the
strict unique prefix of the original 864-request schedule, that every durable
request-start has an observation, and that the source, prepared database,
configuration and device baseline are unchanged. A continuation covers only
block 4 positions 14–48 (35 requests) and blocks 5–18 (672): exactly 707 new
attempts. It never replaces, retries or discards an attempted request.

## Explicit authority and bounded execution

Freeze the supplemental supervisor, fragment worker and both test files in a
new directory, with independent approval, this amendment, the original freeze
hash, original collection seal, every retained fragment seal, exact prior
identities/statuses and remaining suffix. Bind the plan to exactly one new
collection output directory. Exclusive creation happens under the original
batch lock; the same plan cannot execute again under another output path.

Before each worker admission, seal a separate ledger containing all preceding
attempts, their immutable artifact references, the exact next suffix, original
baseline and one authorized worker directory. The worker checks that output
identity under the unchanged inference lock. It cannot execute a stale ledger
at a new path. A guarded zero-request admission rejection can authorize the
next admission directory only with its retained zero-attempt/no-call proof;
the original 600-second recovery window and 20-second waits remain in force.

Every nonzero-attempt fatal interruption stops and seals its physical fragment
and the collection. There is no automatic request retry or planned chunking.
Any further continuation needs a new explicit independently reviewed immutable
plan for its then-unattempted suffix. Device/transport/verification failures
are retained; integrity or baseline failure is not grounds to relax a guard.
No operating-system, swap, power, service or user-application changes are made.

The fragment worker imports and calls the original `run_cases` unchanged,
including its adapter, actual sole model, helpers, client, timings, durability,
fresh conversation, retrieval, snapshot, cleanup and failure behavior. The
new worker copies only orchestration around choosing the proven remaining
cases. It retains the original complete logical-slot manifest and adds the
fragment offset/list and ledger/continuation provenance. Each physical
fragment starts with no model, retains only its sole model, then unloads it.

## Analysis and reporting consequences

There remain 18 planned logical condition blocks and 864 planned attempts.
There will be at least 19 request-bearing physical fragments, rather than 18
uninterrupted sessions. Observation identity remains `(slot, case_id)`;
physical-fragment identity, local one-based index and original scheduled
position are distinct. The first request of the continued suffix is cold even
though its scheduled position is 14. Additional starts and interrupted spans
remain in primary request time and failure denominators.

Aggregate setup, loading, cleanup, resource summaries and energy across actual
physical fragments. Never integrate power across an idle inter-fragment gap.
Report extra cold starts and interrupted blocks explicitly. New supervision
records terminal-fragment overhead including failed fragments; this scope
includes launching, checks, imports, waiting, exit and sealing. The original
fatal block has no terminal admission-overhead observation, so that value
remains unavailable rather than being invented as zero.

Report between-run boundary gaps separately from request time and measured
supervisor overhead. A last-request-to-next-request monotonic gap includes
cleanup, offline work, admission and setup, and is not pure idle pause. New
supervisor start timestamps and the preceding seal timestamp provide an
additional labeled wall-clock artifact boundary. No gap is counted twice.

All frozen task-success, cautious-abstention, paired comparison, dependent
repetition and eight-scenario bootstrap rules remain unchanged. Fragmentation
limits steady-residency deployment claims; it cannot be hidden by merging raw
fragments into a fictional uninterrupted session. Assistant review remains
blinded and independent human validation remains pending.
