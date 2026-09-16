# HRI paper improvement plan

Assessment saved: **2026-09-10**. Target: **ACM/IEEE HRI 2027, Systems track**.
This is a planning reference based on the reports linked below. Unchecked tasks
are proposed work; they do not represent completed experiments or results.

## Fit and proposed contribution

The project fits HRI, and Systems is the strongest track for its intended
contribution. The concept fits well; the current evidence needs strengthening
for a competitive full paper. Acceptance cannot be inferred from track fit.

The Systems track welcomes integrated hardware/software contributions evaluated
through system performance, scenarios, or case studies. A user study is not
mandatory when the evaluation supports the claims. Authors should explain what
other HRI system builders can learn from the work.
See the [official full-paper and track guidance](https://humanrobotinteraction.org/2027/full-papers/).

**Finalized title:** CLARA: A Cascaded Language Architecture for Offline Personalized Robotic Assistance

**Acronym:** CLARA — **C**ascaded **L**anguage **A**rchitecture for **R**obotic **A**ssistance.

**Research question:** How can a robot support offline personalized conversation
under an 8 GB memory constraint, while balancing response quality, latency, and
control over personal-memory use?

The proposed contribution combines model routing, selective retrieval,
persistent personal memory, answer validation, and serialized model loading.
The paper should establish when this combination helps and what tradeoffs it
introduces. The model-pair comparison supports that argument, but does not by
itself establish a system-level contribution.

Existing strengths include measurements on the actual Jetson, controlled
model-pair comparisons, resource telemetry, persistent-memory checks, and
preserved experimental artifacts with provenance and integrity checks.

## Evidence to use when writing

- [Original model-pair comparison](evaluation/model_pair_runs/20260909_report.md):
  seven candidate pairs; historical 128-token configuration; 30 routing cases
  and eight answer-screen cases per pair. The answer screen forces expected
  routes and is a component assessment, not end-to-end answer accuracy.
- [Original full-memory validation](evaluation/model_pair_runs/20260909_full_memory_validation.md):
  historical adaptive baseline and process-restart checks.
- [Latest remediation and memory retest](evaluation/model_pair_runs/20260909_remediation_report.md):
  current evidence for hybrid routing and the 192-token output cap.
- [Retest results JSON](evaluation/model_pair_runs/20260909_remediation_results.json):
  objective metrics, diagnostic judgments, and artifact references.
- [Evaluation documentation](evaluation/README.md): benchmark protocol,
  annotation status, and historical-baseline limitations.
- [Project README](README.md): implemented capabilities and deployment scope.

The assessed configuration uses `qwen3:0.6b` for routing/small answers and
`qwen3:1.7b` for both large roles, with a 2,048-token context and 192 output
tokens. Runs serialize inference on a Jetson Orin Nano 8 GB in 15 W mode.
Do not combine historical and current numbers as if they used one configuration.

## Likely reviewer concerns

| Concern | Evidence and implication | Work needed |
| --- | --- | --- |
| Generalization | The hybrid router achieves 30/30 on the development fixture that informed its rules. The raw classifier remains 19/30 jointly. | Freeze the implementation and evaluate unseen queries and memories; report raw and final routing separately. |
| Personalization quality | Fresh-process known-fact recall succeeds on 3/7 questions. All four complex personal synthesis cases still fail. Persistence works, but useful recall remains unreliable. | Improve request-linked retrieval, evidence selection, citations, supported fact rendering, and temporal synthesis; evaluate the complete path. |
| Answer correctness | The retest delivers 22/30 structured responses and withholds eight. The assistant audit labels 15 complete, three partial, and four incorrect/incomplete. | Independently judge semantic correctness and appropriate abstention; keep schema validity separate. |
| Conversational responsiveness | Text-path latency is 2.666 s p50 and 54.162 s p95. Serialized model reloads contribute to the long tail. | Measure delay by stage, route, and model residency; establish the practical effect on spoken interaction. |
| Integrated robot evidence | These runs did not exercise microphone input, STT, TTS, or physical gestures. | Demonstrate and evaluate the complete interaction on the robot. |
| Evaluation independence | The latest semantic assessment is an assistant audit; blinded human review remains pending. The fixture is small and fictional, with one adaptive repetition. | Obtain independent labels and answer judgments, expand evaluation coverage, and report uncertainty and limitations. |
| Comparative benefit | Choosing the best tested model pair does not establish that adaptive routing improves the complete system. Older baseline results predate changes. | Rerun controlled complete-system baselines using the current implementation. |
| Novelty | Offline robot dialogue already has close precedent. | Explain and measure what the routing, memory controls, and resource-management combination adds. |

Relevant precedent: [Conversational AI without the Cloud: A Lightweight, Local
Dialogue Pipeline for Non-commercial Social Robots](https://lnwatson.co.uk/papers/watson2026conversational.pdf),
HRI Companion 2026. Use this as a starting point for a focused related-work
comparison; novelty still requires further assessment.

## Priorities and completion evidence

### P0 — Preserve the submission option

- [ ] Confirm the target year and submission category with the coauthors.
- [ ] Prepare the complete title, abstract, author list, and Systems track choice
  for the mandatory abstract deadline.
- [ ] Limit the abstract's claims to results that the submitted paper can support.

As checked on 2026-09-10, the HRI 2027 abstract deadline is **September 11, 2026**,
and the full-paper deadline is **September 18, 2026**, both **23:59 AoE**.
The abstract submission must contain complete information, not placeholders.
Full papers allow eight content pages, excluding references.
See the [full-paper call](https://humanrobotinteraction.org/2027/full-papers/).

### P1 — Establish a credible evaluation

- [ ] Define the main claims, metrics, answer rubric, and comparison conditions
  before collecting final results.
- [ ] Create a separate held-out set with new memories and query paraphrases,
  covering direct recall, corrections, temporal reasoning, synthesis, unknown
  information, and inappropriate memory use.
- [ ] Freeze the implementation before evaluating the held-out set. Keep cases
  used for subsequent fixes in development data and obtain a new final test set.
- [ ] Obtain independent routing labels and blinded answer judgments; document
  the rubric, disagreements, and how they were resolved.
- [ ] Report sample counts, repetitions, variation or uncertainty, and failures.

**Completion evidence:** a frozen protocol, separate development/test data,
versioned configuration and source, and independently reviewed result tables.

### P1 — Demonstrate the benefit of the cascade

Completed post-fix comparison (2026-09-12): [Step 3 record](evaluation/post_memory_comparison_20260912/README.md).
All nine sessions and 432 attempts ran under a separately frozen, user-authorized
allowance using existing swap capacity. Small-only, large-only and cascade
achieved 42/144 (29.2%), 44/144 (30.6%) and 46/144 (31.9%) full-rubric successes;
their mean text-request times were 2.314, 11.255 and 8.916 seconds. This reuses
48 partly observed assistant-authored requests across three rounds; human
validation remains pending. Earlier restricted-swap attempts, including the
first 48-request small-only session, remain separate historical evidence.

The [Step 4 final analysis and figures](evaluation/final_tradeoff_analysis_20260912/README.md)
show correct delivery versus deadline, repeated-session timing, loading costs
and sampled whole-device energy. Small-only delivers all its correct answers
within five seconds; cascade reaches its slightly higher total by fifteen
seconds. These are descriptive observations, not selected requirements.
Cascade uses small for only 3/144 generations. Its pooled timing advantage
over large-only reverses in rounds 2 and 3 and is confounded by GPU allocation.
The results do not yet justify a causal adaptive-selection benefit.

Broader proposed evaluation: [adaptive selection protocol draft](evaluation/adaptive_selection_protocol_draft.md)
(2026-09-11), including fair residency, actual-model enforcement, helper
attribution, and separate changing-memory tests. Requirements remain provisional.

First public-benchmark evidence: [2026-09-11 ARC capability pilot](evaluation/arc_capability_20260911/README.md).
The first three arms score 64%, 79%, and 79%; that cascade is much slower
than resident 1.7B on these short MCQs. The fourth 3B arm ran under an explicit
startup amendment but stopped during request 84 at the retained 512 MiB runtime
swap limit: 59 correct accepted answers among 83 successful requests. A
user-requested continuation added 12 correct among the remaining 17, yielding
71/100 composite item accuracy. That segment used an explicit 1 GiB runtime
swap limit and partial CPU execution; report segment timings and the original
failure separately. This does not establish uninterrupted full-run feasibility.
Model cleanup and unchanged system configuration were verified.
This component pilot does not complete the full-system or memory comparisons below.

Earlier text-system pilot evidence is preserved in [results.md](results.md) and the
[Stage 2 evaluation](evaluation/complete_system_20260911/README.md): 184/432
planned attempts, with 166 validated deliveries and all observed outputs
assistant-reviewed. On the common 40 first-round requests, small/large/cascade
score 16/21/19. The cascade stopped at its RAM floor, and a later startup swap
gate left five sessions unattempted. CPU/GPU placement varied materially.
The later Step 3 comparison completes all repetitions under its new freeze;
the earlier partial pilot is not pooled into it. Independent human review,
retrieval ablations, live-memory tests, spoken timing, and an optimized-system
benefit remain unproven.

Overhead reduction implementation (2026-09-12): opt-in
`chat --routing-policy lightweight` removes the compute classifier, evaluates
existing memory-intent rules before optional classification on the resident
model, and retains the active generator with a two-easy-request switch rule.
Offline contract and pipeline tests cover this change. Its initial preflights
were blocked by 812.5 MiB swap against the then-unchanged 768 MiB startup gate.
Later Step 3 measures this routing policy against matched fixed-model systems
under the revised frozen allowance. See the
[implementation record](evaluation/lightweight_routing_20260912/README.md).
Further heuristic changes require new development work and a separate test;
the completed comparison does not establish globally optimized systems.

- [x] Compare true small-only, large-only and adaptive systems on the same
  frozen query sequence with a shared retrieval implementation. System-specific
  memory classifiers can change supplied evidence; this is a complete-system
  comparison, not a matched-evidence generator test.
- [ ] Compare retrieval policies separately where needed to identify the effect
  of selective memory access. Keep other settings fixed within each comparison.
- [x] Measure semantic correctness, answer coverage, appropriate abstention,
  unsupported personal claims, latency, peak RAM, swap, and temperature.
- [x] Record cold/later requests, loading overhead and sampled whole-device
  energy, with background activity and coverage explicitly stated.
- [x] Use the installed `qwen3:1.7b` artifact for the large-only baseline under
  the documented revised experiment guards, with no retired 4B model loaded.

**Completion evidence:** a fair complete-system comparison showing when the
cascade helps and when its overhead or quality limitations outweigh benefits.

### P1 — Address memory reliability

Step 2 implementation is available (2026-09-12): improved intent and evidence
linking, no unrelated fallback disclosure, same-event conflict preservation,
bounded partial/temporal composition, and separate-process lifecycle regression
tests. The [offline development replay](evaluation/memory_pipeline_20260912/README.md)
improves complete required selection from 47/56 to 54/56 on the same recorded
candidate lists; two missing-candidate cases remain unassessed for new retrieval.
This replay and the added tests do not complete the independent unseen-case
quality assessment below. Do not reuse the development fixture as confirmatory
evidence or attribute application-computed answers to model capability.

- [ ] Improve request-linked retrieval/reranking and evidence selection.
- [ ] Address unrelated citations, omitted required evidence, relationship
  perspective, conflicting facts, and temporal reasoning failures.
- [ ] Retest cross-process recall, corrected and forgotten memories, expiry,
  and complex synthesis.
- [ ] Preserve grounding validators; count withheld answers explicitly rather
  than weakening checks to increase structured-response success.

**Completion evidence:** independently assessed improvement on unseen cases,
with correct answers and appropriate abstentions distinguished from failures.

### P1 — Evaluate the complete robot interaction

- [ ] Exercise microphone capture, STT, routing, memory retrieval, generation,
  TTS, and playback together on the robot.
- [ ] Measure from the end of the user's speech to the start of the robot's
  response, alongside stage timings and p50/p95 by route.
- [ ] Include representative general and personalized exchanges, corrections,
  unknown-information requests, and a process restart.
- [ ] Document the physical platform, autonomy, test conditions, and failures;
  capture a demonstration video as supporting evidence.
- [ ] Evaluate physical gestures if they remain part of the claimed contribution.

**Completion evidence:** recorded integrated scenarios and timing/reliability
results that support the paper's stated interaction capabilities.

### P2 — Turn the findings into a clear paper

- [ ] Compare the contribution with offline robot-dialogue systems, model
  cascades, and conversational-memory approaches.
- [ ] Explain what other robot builders can reuse: workload-dependent routing
  choices, model-residency tradeoffs, and memory-validation failure modes.
- [ ] Present the architecture, controlled baselines, integrated demonstration,
  and failure analysis as one argument.
- [ ] Package reproducible configuration, protocols, and artifacts with the
  anonymization required by the submission instructions.

## Claims to keep within the evidence

- Attribute 30/30 routing to the hybrid application router on its development
  fixture. It does not establish unseen accuracy or a fine-tuned model result.
- Distinguish structured responses, semantic correctness, abstentions, and
  withheld failures. Correct citations alone do not establish a correct answer.
- Describe the seven-day fixture as fictional benchmark data, not a seven-day
  human-participant deployment.
- Report observed stability and privacy outcomes within the tested scope.
  The absence of observed breaches on this fixture does not establish a general
  safety or privacy guarantee. Distinguish harness safeguards from production
  monitoring.
- Keep text-path timings separate from complete spoken-interaction timings.
- Claim speed, compute, or energy improvements only when matched measurements
  support them. The remediation retest itself establishes no speed gain.
- A user study is optional for Systems. Claims about improved trust, engagement,
  empathy, or perceived naturalness require suitable evidence from people.

## Submission decision

Pursue a Systems full paper if the final evidence supports an integrated,
distinct contribution with credible comparisons and clearly bounded claims.
If the integrated evaluation cannot be completed, consider a narrower Short
Contribution focused on the demonstrated result and limitations.

The HRI 2027 Short Contributions deadline is **October 1, 2026, 23:59 AoE**,
as checked on 2026-09-10. Recheck the official calls when resuming this plan.
See [Short Contributions](https://humanrobotinteraction.org/2027/short-contributions/).
