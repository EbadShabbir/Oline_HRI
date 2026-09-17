# Fresh current-candidate text evaluation — 16 September 2026

This protocol is specified before inference. The user requested completion of a
fresh evaluation of the latest router and answer repairs, measuring quality and
latency on new cases. This is a finite, independently authored assistant test set,
not a human study or representative population benchmark.

## Candidate and independence

The 43 production/configuration/runner files in `candidate_freeze.json` were
archived in `candidate_source/` before the newly authored cases were opened.
All match the final 15 September practical-repair validation. No production,
classifier, model, prompt, or generation-setting changes are permitted during
this evaluation. Fixing observed failures requires separate subsequent work.

A separate author context creates 48 cases without reading implementation,
training material, prior cases, or outputs: 20 general/current-input (`none`),
8 optional-personalization (`optional`), 8 missing-personal-fact (`required`),
6 mixed personal-recall/general-help (`required`), and 6 unresolved-task
(`clarify`) cases. They include practical tasks, supplied constraints, exact
formats, drafts/edits, and supplied benign or untrusted history. All personal
stores are empty and isolated from the user's database. No production memories
are read. Cases have explicit required components and forbidden behaviors.

Root checks label consistency, rubric clarity and exact/near duplication before
freezing the corpus; every revision must precede inference and be recorded.
Existing benchmark structures and broad task families may overlap. Novel text
does not prove novel concepts or independence from model pretraining. The
author's isolation and the available-corpus duplicate audit define the claim.

Review A declares its criteria before opening cases. Independent assistant
reviews assess final delivered text against frozen rubrics, not the runtime
model review verdict. Reviewer independence, disagreements and resolution are
documented. This does not substitute for independent human validation.
Both quality reviewers receive the request, rubric, declared context and delivered
text with model identity, timings, routing decisions and runtime review verdicts
removed. They may review immutable snapshots of completed rows while later cases
run. Original judgments are retained, disagreements resolved explicitly, and no
review result changes the frozen system or remaining cases.

## Collection

Use the existing `run_routing_reliability.py` conversation runner with learned
dependency routing, the installed Qwen3 0.6B/1.7B artifacts, real BGE CPU
embeddings, and the current production configuration: context 2048, output cap
192, temperature 0, thinking disabled, normal production seed behavior and
timeouts. No forced routes or evaluator labels enter model inputs. No extra
generation retry is added. Record model digests, server version, package
versions, effective configuration and source hashes.

Run every case once in the order obtained by `random.Random(20260916).shuffle`
of the authored list. Each case starts a fresh conversation with only its
declared history, admitted through production history checks. Model residency
is natural across sequential cases; no models are resident at initial admission.
The runner owns a new empty database. No memory writes or lifecycle mutations
are part of this evaluation. Retain every output, withheld attempt, timeout,
error and missing case; do not rerun failed cases to select favorable results.

The evaluation-only wrapper uses the existing Stage 2 device policy: startup
available RAM at least 2 GiB, swap use at most 768 MiB, temperature below 55 C;
runtime available RAM at least 768 MiB, swap use at most 1 GiB, temperature below
68 C. Use existing telemetry and streaming guards, a running fan, unchanged
15 W power mode, boot and thermal-trip counters, serialized inference leases,
and at most one resident model. Do not change OS, swap, fan or power settings.
Any admission/guard failures remain recorded. A pre-inference admission retry
may wait under the same limits; it cannot silently alter them. A partial run
must be explicitly reported and any continuation separately specified.

Freeze the evaluation harness, corpus, protocol and review plans before the
first request. Verify working and archived source hashes again after collection;
record clean model unloading and unchanged device identity/configuration.

## Scoring and latency

Report raw classifier agreement, final dependency agreement and strict answer
quality separately. The strict combined score requires both final dependency
agreement and every applicable answer criterion. Appropriate missing-fact
responses and targeted clarification are successful only where required by the
case. A mixed request must also answer its independent general component.
Optional personalization must give useful general help when memory is absent.
Errors and absent outputs count as failures in all planned-case denominators.
No favorable aggregate acceptance threshold is chosen after seeing results.

Report per-mode/category counts, confusion matrices, useful general delivery,
unnecessary clarification/withholding, unsupported personal/deployment/action
claims, requested count/format violations, incomplete answers and contradictions.
Separate useful content from full-rubric success. Runtime review passes are not
ground truth. Report actual calls by role/model, bounded retries, generation
selection, application-only outputs, evidence IDs and history admission.

Primary latency is the existing runner's per-case monotonic wall time from
before conversation/history setup through final text authorization, including
local classification, retrieval, model switching/loading, all actual calls and
durable call tracing and the wrapper's before/after-call device guard checks.
Backend-reported durations are retained separately; no subtraction is used to
invent an uninstrumented latency. It excludes subsequent observation-file serialization,
embedding initialization, suite admission, cleanup and human/assistant review.
This is instrumented complete text-turn latency, not first-token or speech
latency. Report sample size, p50, p95, mean, minimum and maximum overall and
separately for delivered model-generated text, application-only replies, fully
successful cases and categories. Quantiles use linear interpolation at
`(n-1)*q`. Report full-quality deliveries by 5/10/30/60-second deadlines as
descriptive curves; these are not declared usability requirements.

The single shuffled pass describes this device session. There is no repeated
latency estimate or causal speed/quality comparison with the earlier 20/32
release, which used different cases and source. Empty-memory text results do
not establish populated-memory lifecycle, microphone/STT/TTS, gestures,
power-loss behavior or broad factual reliability.

## Deliverables

Preserve the frozen source, new cases and rubrics, authoring/novelty checks,
protocol, environment/model metadata, telemetry, complete raw traces, independent
judgments, adjudication where needed, reproducible metrics, per-case readable
results, final report and integrity manifest. Add a dated summary to `results.md`
without changing historical outcomes. Completion means the evaluation and
review are finished; it does not mean the candidate passed every case.
