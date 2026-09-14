# Methodology review of the complete text-system pilot

Reviewed 11 September 2026. This is a source and protocol audit, not a new
preregistration, independent human quality review, or completed-run result.
No raw session answers or review identity mapping were opened for this audit.
The reviewer authored the workload and previously assessed a system-blinded
subset; the review is therefore not an independent review of the gold labels.

The implementation supports a comparison of **three current complete text
systems with explicit single-generator controls**. It does not support a claim
that the systems are globally optimized, that generator selection alone causes
any difference, or that the strongest quality-and-responsiveness hypothesis
has been established.

## What the controls establish

| Check | Finding and reporting consequence |
| --- | --- |
| Genuine sole-generator controls | `MemoryOnlyRouter` calls the permitted model for memory classification and supplies a fixed compute route. The large baseline does not use 0.6B for classification. `fixed_generator_model` overrides helper-induced generator switches and disables peer timeout fallback. The backend additionally rejects calls outside the arm. “Single-model” here means one Qwen LLM; the common BGE embedding model and deterministic application remain present. |
| Baseline residency | `single_model_config` gives the permitted model the client's resident role and preserves its original timeout. Both sole models use `keep_alive=-1` within their session. This removes unnecessary compute classification and forced large-model eviction from the baselines. It is a reasonable deployment control, not evidence of a completed equal-budget optimization search. |
| Common application capabilities | Retrieval, top-three candidate budget, evidence filtering, schema, validators, reference notes, and composition implementations are shared. Eligibility filtering and citations are still required. Common code does not imply identical evidence or identical execution branches. |
| Different system policies | Small and large classify memory need with different LLMs; cascade also classifies compute need. The common `memory_intent_policy` may override classification. Logical route also affects general-answer completeness and disclosure-acknowledgment prompt guidance in `Conversation.send`. Thus both evidence and effective answer prompts can differ. Attribute outcomes to complete policies, not solely to generator capability. |
| Authored helpers | Compositions and verified preferences can constrain speech to an authored literal through the response schema. They still pass through an LLM call. The cascade can choose small for a composed answer; fixed baselines enforce their sole model. Postprocessing can replace speech with abstention or conflict clarification. Report actual generator, constraint, transformation, and delivered answer separately; helper success is not unconstrained model reasoning. |
| Timeout behavior | Small retains its 60-second timeout, large its 120-second timeout; adaptive may recover a large timeout through the deployed small fallback. Fixed controls cannot use that peer. This is a declared system difference, not a matched per-call deadline experiment. Preserve both failed-call cost and any eventual delivery. |

The reviewed `evaluation_systems.py`, `conversation.py`, `ollama.py`, and
`run_complete_system.py` matched the source hashes in [freeze_v2.json](freeze_v2.json).
That freeze's SHA256 is
`b980fec5a0491d24f0b79c2e7b7d78e8a6b3b9ffc3c04bab01862b90ca9f3a8e`.
Actual session attribution still requires the result analyzer's manifest,
call, configuration, and source checks; this audit does not replace them.

## Scope and limits that must accompany results

The 48 authored requests have four equally weighted strata, not measured
household frequencies. Related questions share facts, scenarios, and one
fictional profile. Three counterbalanced repetitions characterize variability;
they are not 144 independent quality samples per arm. The same balanced
alternating order is used throughout, so there is no separate grouped-order
condition or arbitrary-order guarantee. Do not infer statistical equivalence
from a small difference or an inconclusive significance test.

The real memory APIs replay 25 remembers, a correction, and a forget operation
before questions; seven-day retention and the synthetic clock leave 23 current
eligible records. Corrected, expired, forgotten, unknown, and conflicting
controls test answers against that snapshot. Every question has fresh history.
This does not test memory extraction, live change propagation, forgotten facts
remaining in dialogue history, concurrent changes, multiple user profiles, or
large-corpus retrieval. It also excludes all audio and robot execution.

Latency ends at complete validated text delivery, not speech start or first
token. It includes checks inside backend calls, so it is an instrumented
pipeline measurement. Initial embedding/database setup and scheduler cooldown
are separate costs. “Later requests” must not be called uniformly warm:
adaptive switching can reload models during the session. A validated but wrong
answer is not a correct responsive answer; a fast failure is not an answer.

Placement is materially variable despite fixed model tags and configuration.
Curated service logs show 1.7B at 18/29 GPU layers in
[large round 1](large_r1_v2_ollama_placement.json), 29/29 in
[large round 2](large_r2_v2_ollama_placement.json), and 21/29, 21/29, then 20/29
in the first three large loads of [cascade round 1](cascade_r1_initial_ollama_placement.json).
These are bounded placement observations, not exhaustive whole-session
placement labels. Session and within-session timing therefore mix backend
placement with selection, loading, retrieval, and device-state effects. Do not
attribute the difference solely to the router, parameter count, or embeddings.

Whole-device telemetry includes background activity. Logical swap occupancy
is not physical compressed-zram use or swap traffic. Sampled RAM peaks do not
recover the exact instantaneous available-memory value that trips a separate
guard. Energy integrated from 500 ms VDD_IN samples is an onboard whole-device
estimate, not calibrated isolated model energy.

## Required reporting checks

1. Keep the original 12-request harness diagnostic separate from the revision-2
   primary population. [The accounting amendment](runner_revision_v2.md)
   changed failure classification and capture after preliminary invocations;
   it did not tune the workload or answers. Do not call every primary item
   literally never invoked before, or select the better of repeated answers.
2. Link the [startup resume](session_resume.md) and
   [resource-failure continuation](resource_failure_continuation.md).
   Orchestration changed; frozen request execution and device limits did not.
   Preserve zero-inference startup rejections and the original cascade
   interruption. A new independent session does not complete a missing tail.
3. Show planned, attempted, validated-delivery, reviewed, correct, and missing
   counts by arm and session. Schedule completion is distinct from complete
   collection. Correct/attempted for an incomplete arm is observed accuracy,
   not full-workload accuracy. A correct/144 figure is only conservative
   demonstrated coverage when missing items are present.
4. Retain RAM-guard failures as feasibility observations under the declared
   768 MiB floor and recorded starting conditions. They neither establish a
   hardware crash nor prove impossibility under every deployment policy.
   Missing tails are resource-dependent, not randomly missing observations.
5. Compare paired cases on an explicitly stated common observed set, alongside
   full coverage accounting. Report per-session timing and placement before
   pooling; do not use missing demanding requests to make an incomplete arm
   appear faster. Keep failed-attempt time separate and preserve all incurred
   cost. Withhold any curve whose interpretation requires complete collection.
6. Score delivered responses against all required claims, actual supplied
   evidence, and citations. Lexical checks are signals only. Label semantic
   judgments assistant-assessed, preserve separate adjudication, and retain
   independent human review as pending. Pure calculation errors from supported
   premises are correctness failures without automatically becoming invented
   personal-fact flags.
7. Report calls, helper coverage, reference use, transformations, and retrieval
   disagreements before explaining a quality difference as model capability.
   A matched-evidence generator comparison and retrieval ablation would be
   needed to isolate those mechanisms.
8. No user-approved quality floor, responsiveness deadline, noninferiority
   margin, or optimization search budget was set. Report measured tradeoffs;
   do not retrofit thresholds or claim an optimized Pareto frontier. A useful
   result can favor a single-generator system or reveal limitations in all
   three systems.

The allowable headline is a measured comparison of the current complete text
implementations on this authored workload and device, with coverage, failure,
review, placement, and lifecycle-snapshot qualifications stated alongside it.
