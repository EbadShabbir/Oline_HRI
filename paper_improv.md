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

- [ ] Compare always-small, always-large, and adaptive routing on the current
  configuration and the same query set, with controlled retrieval conditions.
- [ ] Compare retrieval policies separately where needed to identify the effect
  of selective memory access. Keep other settings fixed within each comparison.
- [ ] Measure semantic correctness, answer coverage, appropriate abstention,
  unsupported personal claims, latency, peak RAM, swap, and temperature.
- [ ] Record cold/warm model conditions and loading overhead. Measure power or
  energy directly if making energy-efficiency claims; 15 W mode alone is not an
  energy-per-turn measurement.
- [ ] Use the current 1.7B generator for the always-large baseline and preserve
  the documented device limits. Do not load the retired 4B path on this unit.

**Completion evidence:** a fair complete-system comparison showing when the
cascade helps and when its overhead or quality limitations outweigh benefits.

### P1 — Address memory reliability

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
