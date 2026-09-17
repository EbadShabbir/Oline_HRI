# Fresh router and answer evaluation — 16 September 2026

**Completed. The latest candidate still fails most full-task criteria on this
fresh challenge set.** The original 48 attempts produced **36/48 correct final
dependency routes, 4/48 complete answers, and 4/48 successes on both**. Five
attempts were rejected before inference because of an evaluation input-format
mistake; these remain in the original denominator. Among the 43 valid original
inputs, routing was **36/43 (83.7%)** and complete answers were **4/43 (9.3%)**.
The separately declared correction of those five inputs produced **3/5 correct
routes, 1/5 complete answers, and 0/5 successes on both**.

Generated deliveries took **43.57 seconds median / 84.93 seconds p95** in the
original cohort. These observations do not demonstrate responsive conversation
or dependable full-task completion. No overall acceptance threshold was chosen
after seeing the results. The evaluation is finished; the candidate's quality
problems remain.

The [complete delivered answers and judgments](answers.md),
[primary metrics](metrics.json), [follow-up metrics](whitespace_analysis/metrics.json),
and [independent numeric/integrity audit](independent_audit.json) preserve the
evidence. The audit passed **270/270 checks**. The earlier **20/32** release used
different cases and source, so these scores do not establish improvement or
degradation relative to that release.

The candidate and test design were frozen before inference in the
[protocol](protocol.md) and [evaluation manifest](evaluation_freeze.json).
All 43 production/configuration/runner files match the final 15 September
practical-answer repair, whose prior validation ran 1,384 tests with 26 skipped.
The source was archived before the new cases were opened. No production code,
classifier, model, prompt or generation setting changed during this evaluation.
The Git revision was `54a80e30a4036ec6047e965560c452627988b63c`; exact file hashes,
rather than the revision alone, identify the evaluated candidate.

A separate assistant context authored 48 cases without access to implementation,
training data, earlier cases or earlier outputs. The cases cover general/current
input tasks, optional personalization, absent personal facts, mixed recall and
general help, and unresolved requests. The authoring originals and all amendments
are preserved in [authoring/](authoring/) and the
[pre-inference case audit](pre_inference_case_audit.json). A wording audit against
765 unique available prior case/training/workload prompts found no exact or
character-similarity matches at or above 0.85. This establishes limited wording
novelty, not novel task concepts or independence from model pretraining; see the
[frozen novelty audit](frozen_novelty_audit.json).

The single randomized pass used seed `20260916`, separate conversations with
only each case's declared history, and an isolated empty memory database.
The normal learned router, BGE CPU embeddings and installed `qwen3:0.6b` /
`qwen3:1.7b` models ran with context 2048, output cap 192, temperature 0 and
thinking disabled. Production seed behavior and timeouts were retained. Model
residency followed the ordinary sequential workload, starting with no resident
models. [Collection metadata](collection/run/metadata.json),
[launcher metadata](collection/launch.json) and
[model identities](collection/models_before.json) record configuration, packages,
Ollama 0.33.3 and exact model digests.

**Cohort accounting and quality.** Full answer quality requires every applicable
frozen task criterion, including requested content, count/format, supplied
constraints and appropriate handling of missing information. Some useful content
does not equal complete success. Combined success additionally requires the
correct final dependency route.

| Cohort | Attempts | Raw route match | Final route match | Complete answer | Both |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original frozen set, including five setup errors | 48 | 36/48 | 36/48 | 4/48 | 4/48 |
| Original valid-input subset; conditional result | 43 | 36/43 | 36/43 | 4/43 | 4/43 |
| Separate whitespace correction follow-up | 5 | 2/5 | 3/5 | 1/5 | 0/5 |
| Exploratory corrected-input view: 43 original + 5 follow-up | 48 | 38/48 | 39/48 | 5/48 | 4/48 |

The exploratory row is a joined descriptive view, not the original frozen
48-case result or a single-session latency estimate. Its exact lineage is in
[exploratory_corrected_input.json](exploratory_corrected_input.json).

The evaluator's pre-inference context amendment inserted newlines into current
requests `fresh_035`, `036`, `044`, `046` and `047`. The production CLI rejects
these control characters. All five recorded the same `ValueError`, with no route,
no model calls and no delivered answer. These are **evaluation setup errors,
not model answer failures**. After the first such rejection, and before any
inference on the five affected requests, the
[follow-up protocol](whitespace_followup_protocol.md) declared replacing each
newline with a space and changing nothing else. All five satisfied the
[mechanical eligibility check](whitespace_eligibility.json). Each normalized
request then ran once in original relative order, in a separate session with a
new empty store. All 53 attempts and the original judgments remain preserved;
no routing or answer failure was retried to select a better result.

In the follow-up, only `fresh_046` passed answer quality: it repeated the supplied
options and asked the user to choose. Its final dependency route was `optional`
(effective fallback `none`) rather than the expected `clarify`, so combined
success was zero. The other four replies failed
the same missing-information or targeted-clarification requirements.

| Expected dependency mode, original cohort | Cases | Raw match | Final match | Complete answer | Both | Setup errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `none`: fully answerable from current input/general knowledge | 20 | 14 | 14 | 3 | 3 | 0 |
| `optional`: useful without personalization | 8 | 8 | 8 | 1 | 1 | 0 |
| `required`: absent personal recall, including six mixed requests | 14 | 11 | 11 | 0 | 0 | 2 |
| `clarify`: unresolved task or referent | 6 | 3 | 3 | 0 | 0 | 3 |

Raw classifier agreement was 36/48, confidence-thresholded agreement 25/48,
and final agreement after dependency review 36/48. Raw and final totals are
equal, but three individual labels changed. The final confusion matrix is:

| Expected / final | `none` | `optional` | `required` | `clarify` | Setup error |
| --- | ---: | ---: | ---: | ---: | ---: |
| `none` | 14 | 0 | 0 | 6 | 0 |
| `optional` | 0 | 8 | 0 | 0 | 0 |
| `required` | 1 | 0 | 11 | 0 | 2 |
| `clarify` | 0 | 0 | 0 | 3 | 3 |

The seven valid-input final routing errors were `fresh_004`, `009`, `011`,
`018`, `019`, `020` (answerable requests routed to clarification), and `037`
(required recall routed to `none`). An effective application fallback can differ
from the final dependency label; it does not replace that label for scoring.
All raw, thresholded, final and effective matrices are retained in `metrics.json`.

History admission is part of this measured path. `fresh_011` supplied a two-message
draft exchange and `fresh_018` an unpaired fictional assistant statement; the
existing history checks admitted zero messages for each. The current request in
`018` restated its editable sentence, while `011` depended on the withheld draft.
Thus `011` measures an end-to-end context-admission/clarification failure; it
does not show the model ignoring draft text it actually received. The other
cases supplied no separate history messages. This run does not demonstrate
successful retention of prior dialogue.

**What failed.** Thirty-two original cases had the right final route but failed
answer quality. Of 24 delivered responses containing generated text, 20 had a
runtime review pass yet failed independent task review. Eight of 28 answerable
`none`/`optional` requests ended in application clarification. Nineteen of 34
requests with a general component supplied some useful general content, but
only four original answers met all their criteria.

| Observed problem | Concrete evidence |
| --- | --- |
| Practical task completion | All six explicit minute-allocation tasks failed. The drawing-table plan (`001`) gave incorrect destinations and omitted allocations; the whiteboard plan (`006`) largely repeated the request. The treasure hunt (`003`) lacked clue texts and the requested sequence. |
| Deliverable omitted | The CSV request (`014`) received an introduction to conversion without CSV rows. The story task (`025`) supplied a premise without the separately requested opening sentence. |
| Count or format ignored | Arithmetic (`007`) reached 18 but gave three equations/three sentences instead of one each; the poem (`015`) was a paragraph instead of four lines; the geometry explanation (`016`) omitted the requested two bullets. |
| Missing recall handled too vaguely | Replies commonly asked for “a little more detail” without explicitly acknowledging the unavailable personal fact or asking for that specific fact. All six mixed requests failed full quality, although four supplied some useful general content. |
| Ambiguity handled too vaguely | The original valid unresolved-task cases received generic clarification rather than a question identifying the missing task or referent. |

The original successes were `fresh_010` (polite rewrite), `012` (choice from
current facts), `017` (feasible schedule) and `021` (bookmark themes). No invented
personal value was observed in the delivered replies. This finite empty-memory
test does not establish a general privacy or factual-reliability guarantee.
First-person wording in three requested plans was recorded as actor-perspective
ambiguity, not conclusive evidence of a robot action or an action already done.
The observed final generation policies were `reliable_generation` (21),
`reliable_quality_retry` (3), application clarification (19), and unavailable
(5); no final delivery selected `practical_guidance_large` in this cohort.

Two independent assistant reviewers graded sanitized packets containing the
request, rubric, declared context and delivered text. Packets omitted routes,
model identities, timings and runtime review verdicts. The reviewers had no
access to each other's judgments or the implementation. Reviewer A had audited
case labels before inference; Reviewer B had not. They agreed on binary quality
for **47/48 original attempts** and **5/5 follow-up attempts**. These are assistant
reviews, not independent human validation.

The one original quality disagreement, `fresh_017`, was resolved as a pass:
its supplied schedule was feasible and met every timing constraint; the rubric
did not require second-person wording. A usefulness disagreement on `006` was
resolved as a fail because merely repeating the supplied task added no method.
A component disagreement on `039` was resolved permissively without changing
its overall failure. [Original reviews](review_a/), [second reviews](review_b/),
[agreement](review_agreement.json) and [adjudication notes](adjudication_notes.json)
preserve the judgments and explanations, including revised perspective flags.

**Latency and work performed.** Times below are seconds of instrumented complete
text-turn wall time. They include history/conversation setup, classification,
retrieval, model loading/switching, generation, reviews, call tracing and device
checks. They exclude suite admission, embedding initialization, subsequent
observation-file serialization, cleanup and independent grading. They are not
first-token or speech latency. Quantiles interpolate at `(n-1)*q`.

| Original cohort group | n | Median | p95 | Mean | Minimum | Maximum |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| All attempts, including five immediate input errors | 48 | 36.24 | 81.34 | 36.87 | <0.001 | 89.00 |
| Delivered text containing model generation | 24 | 43.57 | 84.93 | 53.50 | 27.81 | 89.00 |
| Application-only delivered replies | 19 | 9.93 | 70.24 | 25.55 | 0.50 | 78.42 |
| Complete-quality / combined successes | 4 | 68.71 | 81.29 | 64.53 | 38.62 | 82.10 |

Application-only delivery can follow attempted generation and review; it does
not imply zero inference. The five immediate setup errors lower the all-attempt
latency distribution and should not be mistaken for fast successful replies.
Full-quality delivery was **0/48 by 5, 10 or 30 seconds, and 1/48 by 60 seconds**.
These deadlines are descriptive, not predefined usability requirements.

The follow-up's five attempts had **34.66 s median / 72.76 s p95 / 49.38 s mean**,
with a 33.52–73.03 s range. Its two generated deliveries had 72.35 s median /
72.96 s p95; its three application replies had 34.05 s median / 34.60 s p95.
Its single quality success took 71.67 s. These small samples are reported
separately; latency is not pooled across the sessions.

| Actual model-call role | Original | Follow-up |
| --- | ---: | ---: |
| Compute classifier | 43 | 5 |
| Dependency review | 17 | 5 |
| Answer generation, including withheld attempts | 35 | 2 |
| Answer review | 28 | 2 |
| Total | 123 | 14 |

All 137 calls completed at the transport level; this does not mean their outputs
were correct. Every case stayed within one compute call, one dependency review,
two generation attempts and two answer reviews. Original calls used the small
model 71 times and the large model 52 times; generation attempts were 28 small
and 7 large. Follow-up calls split 7 small / 7 large.

Original summed case wall time was 1,769.58 s; recorded call wall time was
1,762.68 s. Backend total time was 1,760.13 s, of which 1,454.39 s (82.6%) was
reported model loading. Loading is included inside backend total and must not
be added to it. The follow-up reported 245.08 s backend total, including 223.32 s
loading. This locates a substantial measured cost; it does not quantify a
causal optimization benefit or predict latency with different residency rules.

Both runs retained the existing 15 W device policy, serialized inference and
resource guards. Original/follow-up telemetry contained 3,492/488 samples, with
peak reported RAM 6,601/6,511 MB, swap 93/92 MB and temperature 56.343/55.031 C.
There were no guard violations, thermal trips, boot changes or cleanup failures.
All owned models were unloaded after each collection. No OS, fan, power or swap
settings changed. Both isolated databases remained empty; all 19 original and
2 follow-up retrievals returned no evidence. The audit also checked recorded
payloads for forbidden evaluator fields and distinctive rubric literals; absence
of literal matches is not a universal proof against semantic leakage.

The original wrapper records exit 1 and `complete: false` because the five input
errors are retained. All 48 planned rows and judgments were captured, so analysis
correctly records `evaluation_complete: true` and `operational_success: false`.
The follow-up completed all five rows with exit 0. Collection integrity and
cleanup passed in both sessions.

The existing runner/compatibility checks passed 24/24, guarded-launcher checks
4/4 and analysis checks 5/5. The initial runner-check invocation omitted the
tests directory from its import path and failed one import; both that log and
the corrected invocation are preserved. The separate audit independently
recomputed counts and quantiles, verified frozen/archived/current hashes,
checked raw calls, empty stores, resources, supplement eligibility and all
53-attempt accounting, passing 270/270 checks. An audit pass validates the
measurement record; it does not change the candidate's failing task scores.

To recompute analysis without inference, run from the repository root:

```bash
.venv/bin/python evaluation/fresh_routing_20260916/analyze.py \
  --freeze-manifest evaluation/fresh_routing_20260916/evaluation_freeze.json
.venv/bin/python evaluation/fresh_routing_20260916/analyze.py \
  --cases evaluation/fresh_routing_20260916/whitespace_followup_cases.json \
  --collection evaluation/fresh_routing_20260916/collection_whitespace \
  --judgments evaluation/fresh_routing_20260916/whitespace_adjudicated_judgments.json \
  --freeze-manifest evaluation/fresh_routing_20260916/whitespace_followup_freeze.json \
  --expected-count 5 \
  --output-dir evaluation/fresh_routing_20260916/whitespace_analysis
.venv/bin/python evaluation/fresh_routing_20260916/summarize_followup.py
.venv/bin/python evaluation/fresh_routing_20260916/audit_results.py
```

The primary [raw observations](collection/run/observations.jsonl),
[model calls](collection/run/model_calls.jsonl), [telemetry](collection/telemetry.jsonl),
and [follow-up collection](collection_whitespace/) retain failed and withheld
attempts. [Per-case metrics](per_case.jsonl) and
[follow-up per-case metrics](whitespace_analysis/per_case.jsonl) support further
inspection. The final artifact seal is recorded in
[completion_manifest.json](completion_manifest.json).

These are single-pass, assistant-authored and assistant-reviewed challenge
cases on one device session per cohort. They are not a random population sample,
repeated latency experiment, populated-memory lifecycle test, microphone/STT/TTS
test, gesture test or power-loss test. Once exposed here, the cases are known
development evidence for subsequent repairs; another fresh set would be needed
to evaluate those repairs independently.
