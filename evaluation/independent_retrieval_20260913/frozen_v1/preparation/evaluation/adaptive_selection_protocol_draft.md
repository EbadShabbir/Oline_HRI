# CLARA adaptive selection evaluation — draft

Prepared 2026-09-11. Status: proposed protocol, not a frozen experiment or a
result. Thresholds, workload weights, sample counts, and implementation hashes
must be finalized before collecting the final test. No inference was run to
prepare this document.

Deadline feasibility is one evaluation lens, not the sole evaluation. The
proposed 5/15-second values below have not been selected. Report the
complementary measurements below regardless of whether any system meets those
illustrative targets.

| Evaluation | What it establishes |
| --- | --- |
| Paired generator capability | Which requests each model actually answers correctly |
| Quality versus latency/resources | Whether selection creates a useful tradeoff across workloads |
| Requirement feasibility | Whether a system satisfies a particular declared application target |
| Retrieval-policy ablation | The benefit and cost of independently selecting personal-memory access |
| Changing-memory episodes | Whether corrections, forgetting, expiry, and restarts affect answers correctly |
| Integrated robot subset | Whether text-path findings carry through to spoken interaction |

## Question and decision rule

On the specified Jetson Orin Nano 8 GB, does adaptive generator selection meet
quality and responsiveness requirements more efficiently than feasible,
optimized single-model systems with equivalent personal-memory capabilities?
Independently, does selective retrieval preserve useful personalization while
reducing unnecessary memory access, and do corrections/deletions take effect
in subsequent delivered answers?

The strongest result is: small-only fails the quality requirement, large-only
fails the responsiveness requirement, and adaptive meets both. This is a
hypothesis to test. If all pass, compare measured time, resources, and added
engineering complexity. If a single-model system meets both more efficiently,
recommend it. If none passes, report the unmet requirements. An inconclusive
quality difference does not establish equivalence.

Also report continuous quality, latency distributions, resource use, and
quality-versus-cost curves. A system that misses a chosen deadline can still
show useful measured gains on another metric or workload. Distinguish that
tradeoff result from meeting the application requirement. Any router threshold
sweep must use policies fixed on development data; do not select a new policy
from final-test results and claim it was prospectively validated. A claim of
similar quality at lower cost needs a predefined meaningful noninferiority
margin and an appropriate paired analysis.

## Current evidence and confounds

- Current defaults are `qwen3:0.6b` and `qwen3:1.7b`, context 2048, output cap
  192, temperature 0, thinking disabled. Pin model digests and quantization,
  runtime version, source hashes, prompts, validators, embedding revision,
  power mode, actual storage, cooling, background processes, and peripheral
  workloads. The older 128-token setup is historical.
- The [latest reasoning report](model_pair_runs/20260910_reasoning_report.md)
  records an unblinded 26/30 complete-answer diagnostic across an interrupted
  run and separate tail checks. It is not a completed final benchmark.
- Bounded plans, memory compositions, and technical notes now contribute to
  answers. Some nominally large routes decode on small. Their success cannot
  demonstrate that the large generator has superior reasoning.
- Existing runner strategies change retrieval as well as generation. The
  large-with-memory strategy can be overridden to small by composition.
  Large requests currently unload after generation, penalizing a resident
  large-only alternative that has not yet been implemented and measured.
- The original 30 cases and the later repair/paraphrase fixtures are development
  data. Reusing their scores does not establish unseen performance.

Retain the documented device restrictions: only the deployed 0.6B/1.7B pair,
serialized inference, and existing telemetry/resource guards. Do not load the
retired 4B model on this Jetson. A resident 1.7B baseline is a configuration to
validate within those guards, not an assumption that it is feasible.

## Stage 1 — establish whether the pair has useful complementary abilities

Start with 24 new development requests: six each of routine general questions,
general requests with several explicit constraints, direct personal recall,
and personal temporal/synthesis requests. Use household/robot assistance tasks
within the claimed scope, including requests outside the existing software
runbooks. Human task labels describe requirements, not which model must win.

Run every request through both generators with the same prompt, evidence,
context/output budgets, decoding settings, and answer rubric. For this
component comparison, supply identical independently checked evidence to both;
explicitly label it an evidence-controlled diagnostic. It is not retrieval or
end-to-end accuracy. Measure warm inference and model loading separately.

Separate ordinary model-generated answers from answers determined by a literal
constraint or application template. For the ordinary-generation diagnostic,
disable literal-answer constraints and composition consistently in both arms;
audit all relevant switches, since `grounded_composition=False` alone does not
disable every constraint. Disclose any common reference notes supplied.

Blindly judge the four paired outcomes: both correct, only small correct, only
large correct, neither correct. Report counts and task types. A useful large
model must rescue meaningful requests at acceptable incremental cost. Include
the small-only wins and all failures; do not retain only large-model wins.

If this pilot reveals little useful large-model advantage, stop developing a
positive cascade claim for this pair. The result may support a simpler system.
If it supports proceeding, repeat the paired comparison on the frozen final
set; pilot results alone cannot justify the paper's benefit claim.

## Stage 2 — compare complete optimized systems

| System | LLMs allowed | Generator selection | Personal memory |
| --- | --- | --- | --- |
| Small-only | 0.6B only | 0.6B for requests needing generation | Full retrieval and lifecycle support |
| Large-only | 1.7B only | 1.7B for requests needing generation | Full retrieval and lifecycle support |
| Adaptive | 0.6B and 1.7B, serialized | Frozen CLARA policy | Full retrieval and lifecycle support |

Give all systems the same memory database, retrieval implementation, evidence
budget, validators, available reference notes, and deterministic helpers. Tune
prompts, memory gating, and residency on development data with the same declared
search budget and constraints; freeze before the final test. Allow each sole
model to remain resident between turns when feasible. Remove unnecessary
compute-selection calls from fixed-model systems.

Freeze equivalent background and peripheral workload demands for all arms.
If a model must be evicted to run STT or another required component, include
that cost in the spoken-system comparison. A resident text-only baseline
remains a separately labeled condition.

A large generator that still calls 0.6B for memory classification is a
two-model system: label that condition a **fixed-large-generator control**,
not large-only. A true large-only competitor must use its own resident model
or a deterministic memory selector. If selector implementations differ, this
stage compares complete systems. Use the matched-evidence component results
to isolate generator effects; do not attribute every system difference to
generator selection.

All arms may use the same deterministic response optimization. In particular,
consider directly validating/rendering already complete authored compositions
without an LLM call, consistently across arms. This is proposed implementation,
not current behavior. Record such answers as application-produced. Fixed-model
arms must never silently invoke the other model, including on timeout or when
a composer overrides routing. Log requested route, actual model, helper use,
fallback, and final delivered response separately.

Also run matched fixed-small/fixed-large/adaptive generator controls with the
same memory selector/evidence policy if system-specific selectors differ.
These controls isolate selection; they do not replace true single-model
competitors. Keep these result tables separately labeled.

### Proposed workload and repetitions

Use 120 held-out requests, 30 in each of the four task strata above, with new
facts, names, dates, constraints, and wording families. Include answerable,
unknown, conflicting, and unnecessary-memory cases. Group related questions
into scenarios and split entire scenarios between development and test. Obtain
independent rubric/evidence review before model answers are inspected.

This is a proposed starting sample size, not a power calculation. Use the
pilot's paired disagreement rates and the smallest useful quality difference
to determine whether more independent scenarios are needed. Repetition does
not replace more tasks. Size each subgroup for any planned confidence-bound
claim as well: a one-sided 95% exact bound for a 95% success requirement needs
at least 59 independent error-free observations, even before accounting for
clustering. A small unknown-fact subset cannot certify that threshold. For the
three main systems, 120 cases repeated three
times means 1,080 measured turns, excluding diagnostics and ablations.

Use three counterbalanced device runs to measure timing variability; fixed
temperature/seed repetitions are not three independent quality samples. Freeze
the primary workload mix before the test. The balanced set is a coverage
benchmark, not evidence of real household request frequencies. Separately
show sensitivity to routine-heavy, balanced, and demanding-heavy mixtures;
state all weights and do not select the favorable mix afterward.

Start each session from a recorded no-model-resident state, then permit normal
residency for that system. Report startup separately and amortized over the
declared session length. Run identical chronological workloads under all arms,
with both grouped and alternating request types. Include the cost of returning
to 0.6B after a large request on the following turn. Randomize/counterbalance
system order between runs, not the order of dependent memory events. Do not
reset both models before every turn and call that normal session performance.

## Stage 3 — isolate memory selection and changing-memory correctness

Cross generator policy (fixed small, fixed large, adaptive) with retrieval
policy (never, always when permitted, selectively when needed): a 3 x 3
comparison on a predeclared memory-focused subset. Keep consent, profile,
expiry, freshness, and prohibited-data guards active in every arm. “Always”
does not authorize access to forbidden records. Enforce the same actual
generator/override policy across each controlled retrieval comparison. Disable
or match composer and fallback model switches; merely logging them does not
remove their influence. Separately report production combinations in which
memory availability legitimately changes execution as coupled system effects.

If resources only permit this ablation at one fixed generator, report that
narrow scope; it cannot establish independence across generator policies.
Any artificial shared classifier or evidence replay is a controlled ablation,
not another optimized single-model deployment.

Use at least 12 independent synthetic lifecycle scenarios with checkpoints:

1. Confirm/store a fact, then ask a recall question.
2. Correct it, then ask an unseen paraphrase; the replacement should be used.
3. Add a distractor or genuine unresolved conflict; test relevant selection or
   appropriate uncertainty, respectively.
4. Forget the fact, then ask again; the old value must not be disclosed.
5. Restart the process and repeat the relevant checkpoint.

Distribute expiry, unknown facts, and retained-history cases across the
scenarios. Test profile isolation at component level unless the claimed
deployment actually supports multiple users. Keep missing-value categories
synthetic and avoid storing prohibited secret values merely to test abstention.
Define whether a historical
query legitimately requests an earlier event; stale current-state answers and
supported historical answers are different outcomes.

The existing fixture replays changes before all questions. Add a sequence
harness that queries before and after each change, and tests retained
conversation history separately from fresh conversations. A deleted fact
remaining in history must not be redisclosed under the declared forget policy.
Use deterministic synchronization hooks for changes between retrieval and
validation; test the before/after validation boundaries without timing races.

Score database/index state, retrieved candidates, supplied evidence, citations,
and delivered content separately. Report correction/deletion propagation time,
stale-answer rate, unnecessary retrieval, required-evidence recall, unsupported
personal claims, and correct abstention. Correct filtering alone is insufficient
if the answer is wrong. An abstention on a known answer counts as failure.

## Acceptance criteria and measurement

The following are **illustrative proposed requirements**, pending task-owner
input and a task-based justification. They are not established HRI standards.
Freeze the final values before test outputs; never relax them to make an arm
pass. The demanding-task subset must also be defined before results.

| Requirement | Proposed threshold / definition |
| --- | --- |
| Answerable-task quality | At least 90% fully correct and complete delivered answers |
| Important demanding subset | At least 85% fully correct and complete |
| Appropriate uncertainty | At least 95% correct abstention/clarification on pre-labeled unanswerable cases |
| Memory integrity | Zero observed forbidden/stale-current-value disclosures on the declared suite |
| Routine responsiveness | At least 95% meet a 5 s deadline |
| Demanding responsiveness | At least 95% meet a 15 s deadline |

Primary text latency is request submission to the complete validated answer.
For the robot validation, latency is acoustic end of the user's speech to the
start of substantive answer audio, including endpointing, STT, validation,
TTS, and playback. Track both separately. A canned acknowledgement and an
unvalidated first token do not satisfy the answer deadline. The speech
thresholds remain provisional until selected; text tests cannot certify them.

Two independent raters should score randomized answers with system identity
and timings hidden, using expected facts, constraints, and uncertainty rules.
Record disagreements and adjudication. Separate complete, partial, incorrect,
appropriate abstention, inappropriate abstention, and technical failure.
Schema/citation validity is not semantic correctness.

Retain timeouts, rejected answers, fallbacks, and truncations in all relevant
denominators. Report p50/p95, deadline misses, and **correct answers delivered
within deadline / all requested tasks**. Fast failures are not efficiency wins.
Report latency conditional on success only as an additional diagnostic.

Report paired quality differences and 95% intervals accounting for repeated
requests within scenarios; bootstrap whole scenarios/session traces rather
than treating repeated turns as independent. Use suitable small-sample methods
if there are too few independent scenarios for a stable bootstrap. For a
strong feasibility claim, require the one-sided confidence bound to clear
each rate threshold; if it overlaps, call the result inconclusive. Zero
observed integrity failures is only a suite result, with its event count and
uncertainty, not proof of general safety. With modest samples, fine p95 and
rare-failure claims will be uncertain.

Record router/classifier time, retrieval/packing, eviction, model load, prefill,
decode, validation, and unaccounted wall-time overhead without double counting.
Ollama load duration does not include the complete switching cost. Existing
non-streaming calls provide no measured time to first token. Plot the full
latency distribution and the quality-versus-latency points with requirement
boundaries; include startup and model-transition breakdowns.

Collect peak RAM, swap, temperature, and time-integrated measured power for
each isolated system session. Existing telemetry estimates whole-run board
energy, not per-turn energy. Align measurement windows before making energy
claims; report instrumentation and idle treatment. A 15 W operating mode is
not energy per answer. List additional models/assets, inference calls,
switches, and failure paths to make complexity costs concrete.

No warm-inference arithmetic substitutes for measured workload runs: switching
depends on request order. A quality-aware oracle built from paired results can
describe diagnostic headroom, but it is not a deployable router or a measured
end-to-end latency bound. Do not sum per-stage medians or infer aggregate p95
by averaging stratum p95 values.

## Implementation and collection order

1. Add enforced generator-policy controls, a validated single-model residency
   option, and true single-model memory selectors. Preserve ordinary deployment
   defaults; version experimental configuration explicitly.
2. Add per-stage eviction/validation timings and assertions that actual model
   calls comply with each arm. Prevent hidden composer/fallback crossovers.
3. Add session scheduling, event checkpoints, counterbalancing, and held-out
   suite loading. Reuse existing provenance, immutable artifacts, blinded
   scoring export, telemetry, and stale-evidence test hooks.
4. Run the small paired pilot, fix harness defects on development data, and
   estimate final runtime/sample needs before scheduling long collections.
5. Finalize requirements, rubrics, independent test scenarios, configurations,
   source/model hashes, and analysis rules; freeze them together.
6. Run the main comparison and memory ablations in fresh persistent artifact
   directories. Preserve interrupted runs as incomplete; do not splice tail
   checks into a completed benchmark. Diagnose failures on development data.
7. Obtain blinded judgments and produce all-arm tables, paired rescue/failure
   counts, latency distributions, lifecycle results, and the null-outcome
   interpretation. Run a separate representative microphone-to-speaker subset
   before making full spoken-interaction claims.

No new CLI commands are prescribed yet: the required controls do not currently
exist. A documentation-only protocol does not mean collection is ready.

## Relation to prior work

Adaptive weak/strong model selection and quality/cost evaluation already have
precedent in [RouteLLM](https://arxiv.org/abs/2406.18665). Memory evaluation
covering updates, temporal reasoning, and abstention has precedent in
[LongMemEval](https://arxiv.org/abs/2410.10813). These motivate comparison axes;
their results do not transfer automatically to CLARA. The proposed contribution
is measured interaction between generator selection, independent memory
control, and serial model residency on this 8 GB robot computer. Any broader
novelty claim needs a fuller literature comparison.
