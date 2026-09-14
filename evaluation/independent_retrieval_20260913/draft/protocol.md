# CLARA independent personal-memory retrieval comparison

Prepared 13 September 2026. Prospective draft: independent assistant review,
validation and the immutable execution freeze must precede inference. Human
validation is pending. This assistant-authored fictional coverage experiment is
exploratory; it is not a public benchmark or a household-frequency sample.

## Question and scope

Does selective personal-memory retrieval preserve useful personalization while
reducing unnecessary retrieval and complete request time, after paying its own
selection costs? Compare retrieval policies within each fixed generator. This
is a controlled static-snapshot text experiment, separate from generator
routing and from live before/after memory propagation.

No acceptable latency deadline, quality threshold or meaningful noninferiority
margin has been supplied. Report observed differences, paired wins/losses and
uncertainty. Equal totals or overlapping intervals do not establish equivalence.
Do not invent a favorable margin after seeing answers. Do not change the frozen
questions, records, policy, helpers, settings or rubrics in response to failures.

## Six conditions

| Generator | OFF | ALWAYS PERMITTED | SELECTIVE |
| --- | --- | --- | --- |
| `qwen3:0.6b` | No evidence | Retrieve each authorized request | Current memory-need policy |
| `qwen3:1.7b` | No evidence | Retrieve each authorized request | Current memory-need policy |

Authorization runs before relevance selection for all conditions. Consent,
profile isolation, prohibited-data restrictions, correction, deletion, expiry
and evidence freshness remain active. ALWAYS PERMITTED bypasses memory-need
selection, not authorization or evidence relevance/packing checks. Its lookup
may find no answer and supply no evidence. An ordinary authorized lookup of a
currently unknown fact is still a memory-needing request.

OFF performs no personal retrieval and receives no personal facts through the
system prompt, request history, side channels or helpers. Only the current
question is available as user text. All conditions use a fresh Conversation
and empty history per request. Automatic memory capture is disabled. Runtime
request consent/profile controls are part of authorization, not scoring hints.

SELECTIVE uses the current deterministic memory-need policy first, then the
sole condition model for any unresolved classifier call. Fixed systems make no
compute-classifier call. Every classifier, answer renderer, helper generation
and permitted fallback must use that same model. A fixed-model timeout must
never call the other model. Archive requested and actual model identities and
assert compliance; logging a model crossover would not make it acceptable.

Prompts, generation schema, decoding, retrieval and evidence limits, validators,
and helper configuration are shared wherever applicable. Both fixed generators
use common logical-small prompt framing; this normalization never changes the
actual configured generator. Evidence availability
is the intervention. Evidence-dependent compositions, literal constraints,
abstentions, prompt sizes, supplied IDs, generated lengths and transformations
are logged as realized execution differences. Those paths form part of the
system-policy result and must not be attributed to raw generator capability.

## Workload and fixed lifecycle snapshot

`runtime.json` contains 48 new fictional requests and confirmed seed events.
`references.json` separately contains categories, scenario clusters, memory-need
labels, expected authorization, relevant and disallowed IDs, reference facts,
and answer rubrics. Inference must never load the reference file. Only current
request text and authorized retrieved records may reach model inputs.

| Category | Requests | Frozen scope |
| --- | ---: | --- |
| Direct personal recall | 8 | One known authorized fact each |
| Paraphrased personal recall | 8 | New wording for the eight topic facts |
| Multi-fact personal questions | 8 | Two supporting facts per request |
| General questions without personal need | 8 | Self-contained questions or general knowledge |
| Unknown or conflicting personal information | 8 | Six unknown attributes; two unresolved two-record conflicts |
| Lifecycle or authorization restrictions | 8 | Two corrections, two deletions, expiry, wrong profile, denied consent, prohibited password recall |

The eight topics each contribute one request to every category. Direct,
paraphrased and multi-fact questions intentionally share topic facts. The 48
questions are therefore nested within eight scenario clusters, not 48
independent personal histories. Repetitions share those questions and memories.

The main profile is `fictional_reedharbor_v1`; one neighbor-profile record is
stored in the same database under `fictional_reedharbor_neighbor_v1` to test
ordinary profile filtering. The fixture has 29 historical/current records and
30 primary lifecycle events plus one neighbor event. All writes/corrections are
explicitly confirmed fictional operations. No password or other secret is ever
stored. Request `ir_07_06` has consent denied; `ir_08_06` invokes the ordinary
prohibited-data gate. Both remain outside authorized selection denominators.

Replay all confirmed seed and lifecycle operations before requests, using the
normal MemoryStore APIs. Then hold the semantic clock at
`2026-11-06T12:00:00.000000Z` throughout every evaluation, independent of real
device time. The retention policy is 30 days. Corrections supersede old records;
forgetting hard-deletes the two target records; the temporary room has expired
by the evaluation clock. Build one equivalent logical snapshot for each
condition and verify canonical snapshot and embedding/index equality. A
snapshot never changes between requests. Freshness validation still compares
retrieved evidence against authoritative storage before and after generation.

This evaluates already-applied lifecycle outcomes, not propagation latency,
retained-history forgetting, races or process-restart propagation. Those remain
separate experiments and existing component regression tests.

## Independent pre-inference review and freeze

A separate assistant reviews every question, memory record, expected evidence
ID, relevance label and rubric without seeing model outputs. Record concerns,
resolutions and final approval. Review must check that known answers are
supported, unknowns are not accidentally answerable, conflicts are unresolved,
forbidden records stay unavailable, and general questions require no personal
information. Preserve the assistant origin and pending human validation.

Freeze approved runtime/reference files, protocol, all execution dependencies,
configuration, prompt/helper/validator behavior, model digests and metadata,
embedding model/revision/assets, Python/package/Ollama versions, counterbalance
schedule and analysis rules. Record hashes and immutable file copies. Tests
must validate real harness paths with fake backends before collection, covering
authorization/relevance separation, six fixed-model paths, no OFF leakage,
snapshot preparation, telemetry, evidence logging, failures and interruptions.
Any live harness smoke requests use separate development fixtures and artifacts;
they never become one of the 864 observations.

## Settings, scheduling and resources

All calls use context 2048, output cap 192, temperature 0, seed 42, and thinking
disabled. Each condition/repetition is a 48-request session with its sole model
retained between requests. Each session starts from verified no-model
residency; cold first loading belongs in primary total request time. Record
session setup, index preparation, cleanup and admission waiting separately and
also provide a clearly labeled amortized deployment/session cost.

There are 18 sessions: 48 requests × 6 conditions × 3 timing repetitions = 864
planned attempts. Within each model, each policy occupies each of the three
positions once. Model order alternates small/large, large/small, small/large.
Three rounds cannot fully balance all six global positions; disclose the
remaining 2:1 model-order asymmetry.

| Repetition | Session order |
| --- | --- |
| 1 | small OFF, small ALWAYS, small SELECTIVE, large SELECTIVE, large ALWAYS, large OFF |
| 2 | large ALWAYS, large OFF, large SELECTIVE, small SELECTIVE, small OFF, small ALWAYS |
| 3 | small ALWAYS, small SELECTIVE, small OFF, large OFF, large SELECTIVE, large ALWAYS |

Use `random.Random(seed).shuffle` on the stored `execution_cases` order, with
seeds 2026091301, 2026091302 and 2026091303 respectively. All six conditions in
a repetition receive the same resulting order. Save the exact orders in the
freeze. These are timing repetitions, not additional independent quality cases.

Serialize all inference and acquire the experiment-wide exclusive lock. Verify
no competing Jetson experiment or unexpected resident model before admission.
The waiting supervisor imports only the Python standard library; each session
runs in its own guarded worker process. This avoids charging available memory
for a second idle copy of the embedding/runtime imports. Every worker owns the
inference lock and checks the same collection boot, thermal-trip, power and
swap-capacity baseline. Proven zero-request resource-admission rejections may
be retried within the ten-minute recovery window; each rejected directory is
preserved separately from the 18 request-bearing sessions and the 864 attempts.
Reuse `post_memory_existing_swap_reserve_v2`: startup available RAM at least
2 GiB, runtime available RAM at least 768 MiB, measured temperatures below 55°C
at startup and below 68°C during execution, logical swap at most existing
3901608 KiB capacity minus a 256 MiB reserve, one resident model maximum,
running fan, unchanged boot and zero thermal-trip counters. Keep the existing
500 ms telemetry and 5 second stall ceiling. No OS/service/power/swap changes
are made to admit a condition. The revised swap ceiling is an existing scoped
experimental allowance, not a validated physical-safety guarantee.

Preserve request starts, interrupted spans, partial raw output, rejected
responses, timeouts, admission failures and terminal session records. Ordinary
answer-validation failures count as attempted failed tasks and do not justify
changing the test. Fatal device/transport interruptions stop their session.
Continuation may execute previously unattempted requests only under an explicit
immutable continuation record; no answered or interrupted request is silently
replaced, retried into success, or dropped. State missing coverage if guards
prevent all 864 attempts. Recovery waits are logged separately from request
latency and remain within the existing bounded scheduler policy.

## Measurements and denominators

Record every routing decision, decision source, classifier count/latency,
authorization result and actual retrieval attempt. Selection latency includes
deterministic policy work and classifier calls. It must not be omitted from
SELECTIVE's total request time. OFF and ALWAYS make no relevance-classifier
calls, but the common authorization cost remains.

Relevant-evidence coverage uses only frozen `relevant_evidence_ids`: report
fraction of relevant IDs retrieved and supplied, plus complete relevant-set
coverage per request. Coverage is undefined, not 100%, when no relevant record
exists; present unknown lookup outcomes separately. An unknown personal query
can need memory even though its correct relevant set is empty.

Unnecessary retrieval rate is retrieval attempts among authorized
`memory_need=false` requests divided by such requests. Also report unnecessary
attempts as a fraction of all retrieval attempts, and total retrieval attempts
per all requested tasks. Denied-consent and prohibited requests have a separate
authorization-violation count and never inflate the unnecessary-access saving.
Report selection sensitivity/specificity on authorized labeled requests.

Distinguish the full eligible semantic corpus scored/materialized, source-returned
candidate records (semantic top-20 ∪ lexical top-20), final ranked top-three
candidates, and exact whole records supplied to the generator. The primary
inspected-record count is the distinct union of all semantic records
scored/materialized and all lexical source results. The bounded top-20 source
union is a secondary candidate diagnostic. A candidate irrelevant to the
requested attribute remains irrelevant
even when it is about the same topic. Report irrelevant records inspected and
irrelevant records supplied separately; their counts are not interchangeable.
If an internal scan cannot be observed, label the measured boundary explicitly.

Archive full bounded evidence objects and IDs, exact raw model requests and
outputs, model-reported identities/digests, final delivered answers, validation
errors and all helper transformations. Capture monotonic request, retrieval,
generation, validation, loading, classifier and device-monitor spans. Backend
load/prefill/decode durations are nested diagnostics, never added a second time
to enclosing wall time. Report complete request mean, median and p95, warm and
cold first-request costs, total model-loading costs, and residual overhead.
Keep latency of failed requests in the primary distribution; success-conditional
latency is secondary. Do not add component medians to invent total latency.

Archive residency and CPU/GPU allocation snapshots, RAM, available RAM,
logical swap, temperatures, power/energy telemetry where available, guard
status and run boundaries. State board-energy scope and any sampling gaps;
nominal power mode is not energy per request.

## Blinded answer review

Two independent fresh assistant contexts review randomized answer packets.
Packets contain opaque review IDs, question, delivered answer or failure,
semantic reference facts without IDs, and the common task rubric. Hide model,
retrieval policy, repetition, timing, actual supplied evidence, raw citations,
source observation IDs and the private mapping. Behavioral wording may allow
reviewers to guess a policy; blinding means no explicit identity is provided,
not that linguistic inference is impossible.
Authorized packets include the same full currently eligible profile truth
catalog without IDs, so a true but unrequested personal fact is not mislabeled
as unsupported merely because it was omitted from the requested-fact rubric.
Denied packets have no authorized background; their forbidden-value rubrics
remain available. The rubric still governs prohibited extra disclosure.
Semantic unsupported-claim judgments concern truth and the common rubric;
actual supplied-evidence grounding is a separate post-review diagnostic.

Identical delivered outputs for the same request may be grouped for efficient
semantic review while retaining every raw attempt and mapping each frozen
judgment back afterward. Do not merge different questions or materially
different outputs. Freeze both original review sheets. A third independent
blinded assistant adjudicates differences using the same packet and rubric;
freeze adjudication before opening the mapping. Label all conclusions
assistant-reviewed with independent human validation pending.

Use labels complete, partial, incorrect, appropriate abstention/uncertainty,
inappropriate abstention and technical failure. Record task success, unsupported
claims, unsupported personal claims and caution separately. A known authorized
fact requires successful recall under every condition: OFF abstention is a
missed personalization task even when prudent without evidence. Unknowns,
conflicts and unavailable/unauthorized facts succeed only through their common
uncertainty/refusal rubric. For conflict cases an explicit conflict explanation
is a useful additional diagnostic; clear inability to know also satisfies the
uncertainty task across every condition. Mere citation/schema
validity is not semantic task success.

## Paired analysis and report

Present OFF/ALWAYS/SELECTIVE tables separately for each generator and each of
the six categories, plus generator-specific overall totals. Pair all policies
on the same request and repetition. Show correctness wins/losses and retrieval,
coverage, unsupported-claim, caution/failure and total-time differences for
SELECTIVE−ALWAYS, SELECTIVE−OFF and ALWAYS−OFF.

For each request/policy, average its three timing measurements and its three
success indicators; retain all individual results and repetition-level totals
as well. If outputs differ across repetitions, report that instability rather
than treating them as extra independent tasks. Missing attempts remain missing
and are not scored as unseen successes; show completed-pair and planned-task
coverage explicitly.

Descriptive 95% percentile bootstrap intervals resample the eight whole scenario
clusters with replacement, retaining every category, policy, generator and
repetition within the sampled scenario. Use 10,000 replicates and seed
2026091399. This paired scenario resampling preserves the shared-fact and
repetition dependence. With only eight fictional scenarios the intervals are
coarse and describe this coverage pilot, not population guarantees. Category
tables have eight distinct requests each, not 24 independent requests.

Answer the research question in three parts for each generator: observed
personalization preserved or lost compared with ALWAYS; unnecessary access
reduced or not; complete request time saved or increased after selection costs.
Show OFF's missed known-fact tasks separately from appropriate caution. Report
unfavorable and null findings directly. Attribute helper-mediated changes to
the complete policy path and avoid unsupported noninferiority, causal
generator-capability, live-memory-propagation or spoken-HRI claims.

Save the report, machine-readable analysis, paired tables, provenance checks
and exact reproducible commands in a new immutable experiment directory.
Update `results.md` and `developments.MD` by adding this experiment while
preserving every earlier result and artifact.
