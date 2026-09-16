# Dependency classifier development record

These are development observations, not independent release accuracy.
The original 24-case diagnostic became development data when its failures
were inspected. Historical artifacts remain unchanged.

The initial Boolean router incorrectly required personal memory on 5 of 12
general questions and missed 1 of 8 required-recall questions. Three subsequent
Qwen semantic-prompt experiments did not make dependency classification
reliable. Their complete model calls and failures are preserved under
`tmp/semantic_dev_routing_v1`, `v2`, and `v3`, with additional bounded model
probes under `tmp/dependency_mode_probe_*` and `tmp/dependency_reason_probe_v1`.
The Qwen semantic adapter remains available for reproduction; it is not the
selected dependency classifier.

The first local classifier used 200 authored examples: 160 training and 40
calibration, with disjoint groups. Despite 37/40 raw calibration matches, it
failed the known development questions: only 5/12 general cases received
`none`, five clarified and two incorrectly required recall. Its raw scores,
rejection thresholds and outcomes are in `tmp/dependency_development_v1`.
The calibration result therefore did not establish readiness.

The second corpus has 475 examples: 387 training and 88 calibration. It adds
240 examples with more short questions, draft followups and varied dependency
wording, plus 35 explicitly observed regression examples assigned to training.
The original cases and their extracted mixed fragments are therefore
**training regressions**, not held-out evidence. The frozen combined corpus is
[dependency_training_v2.json](dependency_training_v2.json), SHA-256
`ca0cab074d42a1d7bfc7036eec7c77e91d86e4da43516a63beef27a16b77e0a4`.

Six declared variants compare ridge regularization 0.1, 1 and 10 with BGE
feature weights 0.25 and 1; lexical weight remains 1. They share one CPU
embedding pass. Vocabulary, IDF and fitted weights use training rows only.
Calibration fits rejection thresholds and compares settings, so it is also
development data. Full artifacts are in `tmp/dependency_grid_v2`.

Variant 04 had the highest calibrated coverage but rejected the reported
headache followup and an ordinary draft edit. It was not promoted. A subsequent
explicit gate required all 20 labeled old cases and all eight original cases
to receive their accepted modes, and both mixed requests to retain their exact
general fragments. Variants 01 and 02 passed. Variant 02 had better calibration
coverage among those passing and was selected. The changed selection criterion
and all six outcomes are recorded in `tmp/dependency_candidates_v3`; no release
case was used for either selection.

The installed classifier uses regularization 0.1 and equal BGE/lexical weights.
Its calibration raw agreement is 82/88; 73/88 predictions are accepted with
zero observed accepted errors after threshold fitting. These fitted results
are not an error guarantee. In particular, the conservative `none` threshold
can cause unnecessary clarification on new wording.

First installed artifact SHA-256:
`7327983915ef766c1fb319a30fc0cce0c601ead01d2336be392c1a6ab1351983`.
Its canonical fingerprint is
`d10de3a977b4fd136050861a49a4b58fa8964cbca0cf683bb9947a3b10b22ad1`.
The artifact records the corpus, embedding identity, feature configuration,
class counts, source fingerprint and calibration settings. The offline-built
wheel was checked to contain the exact same JSON bytes.

The independently authored 32-case release set was frozen before these
candidate experiments, with SHA-256
`9d44076a5c1d7d3d248fdf53b99c740cd9367013f4b885f173c2acbd3a3da56b`.
The candidate was frozen before that set was opened. The release failed:
19/32 final dependency labels matched, although 29/32 raw labels matched.
Only 1/12 general requests received a general answer; ten unnecessarily
clarified and one incorrectly refused for missing personal memory. Neither
mixed request retained its general answer. Optional classification was 6/6,
but one optional plan failed before any model dispatch because its system
prompt exhausted the context budget. These are observed defects, not transport
failures. The independent review found zero unsupported personal facts, one
unsupported physical-action promise, and one explicit count failure.

The complete source snapshot is in `candidate_freeze_v1`, raw calls and
answers in `release_learned_v1`, the historical Boolean comparison in
`release_legacy_v1`, and separate routing/utility/evidence review in
`release_review_v1`. These 32 cases became development data after inspection.
The first release is not evidence that the repair was ready to deploy.

Subsequent development removes duplicated general-answer scaffolding to fit
ordinary optional plans within the existing 2048-token context budget, fixes
a generic offer-only detection gap, and checks bounded unsupported physical
action claims. It also investigates a single larger-model review of rejected
local predictions and proposed required dependencies. Review prompts and
schemas must be assessed on actual admitted production history; raw probe
outputs are retained, including unsuccessful variants and input mistakes.
The classifier weights and original fitted thresholds remain unchanged during
these review experiments. No new release success is claimed by these changes.

A second independently authored 32-case release set was frozen before the
next candidate, SHA-256
`abca3ad3fb364995b6673c6835b3bde28218c92e239266bc4b0825a02abe0eea`.
It remains separate from development until the next source freeze and replay.

The Boolean C review removed the general-routing failures in the next known
development pass, but reviewing every accepted required decision introduced
four recall misses (update-format preference, planning from a saved schedule,
elapsed time from saved events, and corrected start time). The pass was
deliberately stopped: `tmp/dependency_C_development_v3` retains 25 completed
decisions, one interrupted attempted row, nine unattempted cases and clean
model unloading. All 12 general and six optional decisions matched; the four
recall misses remain explicit failures. This was routing-only development.

The next revision keeps accepted recall decisions and reviews only uncertainty.
For each enabled class, a deterministic calibration migration sets the floor
to `max(old threshold, minimum margin of previously accepted calibration
rows)`. The floors are none 0.7132880884449522, optional 0.19664648493007064,
required 0.06083647462458264 and clarify 0.47618045533332204. All 73 accepted
calibration IDs remain unchanged with zero fitted errors. Vocabulary, IDF,
weights, bias, embedding configuration and training metadata are byte-for-byte
equivalent as JSON values. These are empirical support limits, not probabilities.

The migration preserves its base artifact fingerprint, original calibration,
source hash and diagnostics SHA-256
`fd41933ab1fffa2022cb4e4cf8529fbfd40e30fbeaaf1e8babd459c753d8adaf`.
Its script, source, inputs, output and promotion record are under
`tmp/dependency_support_floor_v3`. The installed artifact SHA-256 is now
`2ac2fa20d05c2bd172c6e54fdb8ab50224a848effd45a768fcfbbf26ce74ac33`,
with fingerprint
`54c3ba4cb15438b1fe0044a4daae4048bec09e540a5cf35323088b05108270ec`.
An independent numeric audit reproduced the thresholds and exact accepted sets.

A fixed-small routing diagnostic then matched all 35 known mode labels, with
13 actual C reviews and no errors (`tmp/dependency_support_development_v3`).
Its 30.89 seconds include a retained larger reviewer and cannot be compared
with default model-switching latency. It still extracted an incorrect literal
mixed fragment (`a tuner?`), so mode agreement did not establish readiness.
The corrected-time review also changed verdict despite identical request,
history, model tag, prompt and sampler options; runtime state differed, and
the cause was not isolated. The independent record safeguard remains required.

The final structural split repair prioritizes complete sentence boundaries
and explicit request clauses over internal conjunctions. Separately, optional
recall with an expressly accepted general fallback no longer gets overridden
to required by the proactive recall safeguard. Output evidence checks remain
active even under a deliberately wrong optional route. These changes require
their own targeted checks and the still-unopened second release set.

The final known-transcript conversation replay (`tmp/reliable_final_original_v1`)
matched all six dependency modes and preserved the mixed battery explanation.
Its independent review found a remaining optional-weekend nonanswer: the
small model repeated the request and deferred to unspecified interests, and
the answer reviewer incorrectly passed it. The guard was extended to recognize
generic request-prefix echoes followed only by personalization scaffolding.
Concrete suggestions, drafting and requested clarifications remain covered by
positive regressions.

The affected case alone was replayed after that change
(`tmp/reliable_optional_regression_v2`). The small echo was rejected as
`promise_only`; one larger retry delivered three general activity choices.
The original blocker was resolved, but the answer still implied a basis in
unsupplied interests. No specific preference was invented. The independent
review also preserves the earlier headache reply's unjustified blanket
reassurance and the specifications reply's imprecise model-tag wording.
These are remaining answer-quality limitations, not evidence of polished or
clinically validated responses. Both replay timings overlapped CPU unit tests
and are descriptive; the single optional retry took 110.34 seconds.

The final complete offline suite passed 1,318 tests, with 26 skipped, in
140.688 seconds (`tmp/reliable_full_suite_final_v6.log`). An isolated offline
wheel build verified the exact bytes of five selected runtime modules
and the classifier artifact (`tmp/reliable_package_check_v2.json`). The build
files were removed afterward. No new live microphone sample was collected.

The second candidate was frozen before the implementer/reviewer saw the new
release texts. `candidate_freeze_v2/freeze.json` has SHA-256
`7b4fd78f09f1221fb2ac246f88e55c93ff19255b7aa97105cbd155cdc7d3a515`.
It captures 46 runtime/configuration files, source/test hashes, exact model
digests, package versions, configuration and completed validation records.
The new 32-case release uses default dynamic sizing and no concurrent heavy
tests. Its independent review may annotate completed rows as they arrive under
the frozen streaming addendum; no findings enter source or model prompts during
the fixed run. Release outcomes are reported separately after completion.

A separate read-only audit during the frozen run distinguished mechanical
checks from language recognition. For example, the synthetic request
`Explain how Noor organizes his evenings.` and unsupported answer
`Noor enjoys ceramic restoration.` passed the deterministic reply and history
admission checks. No model was called for this probe, so it does not establish
that the full runtime would disclose that answer: the independent answer
review remains in its path. It establishes that finite lexical checks alone
do not cover arbitrary private third-party claims. The documentation now
qualifies history and claim handling as applying to detected forms; no frozen
runtime or release label was changed. The audit also confirmed the source
freeze and cited-record freshness checks at the final guarded write.

The second frozen release also failed full behavioral acceptance. All 32
cases completed with clean shutdown; raw/final dependency agreement was
29/32 and 28/32. Independent review accepted 21 delivered behaviors, with
20 cases satisfying both behavior and final mode. Required missing information
was handled correctly in all eight cases, and no unsupported personal or
deployment claim was observed. Two optional requests still produced an echo
or a future-help offer without a recommendation. A comparison followup lost
general context, and a Boolean dependency review misframed an incomplete
utterance as required personal recall. Other general/mixed explanations were
factually wrong or partial. The complete [V2 review](release_review_v2/review.md)
preserves these findings; they were not corrected or relabeled in that run.

The separate numeric audit passed all hash, trace and call-budget checks.
There were 82 actual calls and a 45.43-second median among the 19 accepted
generated replies. No concurrent CPU suite ran. A separate legacy routing-only
replay made 64 small-model calls, incorrectly requiring memory for six of
twelve general questions and missing one of eight required recalls. Its
16/28 Boolean projections and 36.16 seconds do not measure answer quality or
full conversation speed. Both runs retain the exact V2 source and case hashes.

After both runs and independent end-of-run source verification, development
resumed. The next change treats all raw `clarify` predictions as a request for
a short question, without a dependency review. A Boolean about missing personal
facts cannot establish task/referent completeness in either direction. Reviews
for uncertain `none`, `optional` and `required` remain bounded to one call;
accepted required decisions remain protected. Classifier weights, calibration,
artifact and model prompts are unchanged.

The reply guard now recognizes normalized statement echoes, abstract future
plans, irrelevant assistant-preference disclaimers, and solicitations that
repeat already supplied constraints. Request vocabulary is reused only within
the echo/solicitation grammar, not as a general allowance to discard concrete
choices. Contrastive tests preserve real recommendations, steps, capability
answers, acknowledgments, requested questions and drafts. A small shared
comparison/exposition verb family (`distinguish`, `differentiate`, `contrast`,
`define`) extends guarded general-history admission; the existing personal
ownership and private-context checks remain in that path.

The initial focused checks passed 24 router tests and 87 guard/wrapper/CLI
tests. Four known failures are being replayed separately from a newly authored
eight-case focused quality check. The latter was frozen before implementation
and remains unopened by the implementer/reviewer at this point; its SHA-256
is `b92b58264dc313a3086e046e55f453597234e24464098885949735876a0bc1c9`.
It is a focused deliverable/positive-control check, not a new full four-mode
release benchmark or a general factual-accuracy evaluation.

The four affected live cases completed with all four final modes matching.
The comparison followup retained context, the escape-room echo received one
larger retry with an actual theme, and incomplete speech received the intended
short clarification. The audio-drama echo was also rejected and replaced by
a named recommendation, but the title and its described qualities could not
be verified. Independent review therefore accepted three of four complete
outcomes; it did not treat specific but unverified content as a quality pass.
No personal or deployment claim was invented in those delivered replies.
The record is `tmp/reliable_affected_v3/independent_review.json`.

The next complete test invocation ran 1,328 tests with 26 skipped but had one
subprocess import error: `PYTHONPATH=src` omitted `scripts`, which contains
`independent_retrieval_supervisor`. The failed log remains in
`tmp/reliable_full_suite_final_v7.log`. The documented full-suite command was
corrected to `PYTHONPATH=src:scripts`; no runtime or test assertion was changed
to hide that failure. A complete rerun with the corrected environment is
recorded separately.

The corrected invocation passed all 1,328 tests with 26 skipped in 106.141
seconds (`tmp/reliable_full_suite_final_v8.log`). The isolated wheel contained
the exact selected runtime/artifact bytes. Candidate V3 was frozen as
`candidate_freeze_v3/freeze.json`, SHA-256
`b8d50f4f2c3d49dde80126a6e61b63123552f8af92dfc7b77e044a34f5449cff`,
before the independent reviewer opened the eight focused cases.

The focused check completed all eight cases with all raw/final modes matching,
28 actual calls and clean shutdown. Every case contained substantive content,
but only three satisfied all predeclared criteria. The inbox plan included
unsupported speech-tool guidance; three replies missed count/format constraints;
and an analogy omitted its required mapping. Five model-review passes failed
independent quality assessment. No unsupported personal fact was observed.
The 53.21-second median includes loading, without a concurrent CPU suite.
The [frozen focused review](quality_review_v3/review.md) and numeric audit
preserve these results. The cases are now known material, not future unseen
validation.

The internal-tool guidance exposed unnecessary implementation context in
ordinary prompts. After end-of-run source verification, a focused repair was
authorized to supply detailed deployment facts to generators only for relevant
assistant/specification/tool questions, retain those facts in every independent
review, and reject bounded unsolicited instructions to use configured internal
tools. This change does not purport to repair arbitrary factual knowledge,
semantic duplication, sentence counts, or incomplete analogies.

The final scoped implementation gates only the generator's detailed deployment
context. Every independent answer review still receives the complete configured
facts, separate from authorized personal evidence. Whisper's transcription role
and Silero VAD's speech-detection role are now explicit. The additional bounded
reply check derives internal identifiers from those facts instead of a separate
tool-name catalog; it does not increase generation or review budgets.

Independent source review caught ordinary lowercase uses of “whisper” with
generic “speech” or “audio” wording being mistaken for software, plus a missed
lowercase technical question. The final refinement requires more specific
software/transcription/recognition context or an explicit named-tool query.
Ordinary creative wording, drafts, specifications and explicit tool questions
remain contrastive controls. All 93 focused guard/wrapper/CLI tests passed,
and independent review found no remaining blocker for this narrow repair.
Intent detection and unsolicited-advice detection remain finite heuristics.

The final targeted replay completed four known regression/control cases with
four raw and final mode matches and four narrow deployment-control passes.
The inbox plan no longer recommends speech tools, and explicit tool roles are
correct. Specifications remain a thin software overview with awkward model
notation. The creative sentence uses “whispered” instead of literal “whisper”,
so the independent review accepts only three under the strict word-form reading.
That case also retains a possible false-positive personal-claim rejection of
its first generic sentence and one bounded larger retry. No unsupported
personal or deployment claim was observed in the delivered four replies.

All 15 actual calls are preserved: four compute decisions, two dependency
reviews, five generations and four answer reviews. Every budget passed, all
42 run-recorded source hashes matched, cleanup succeeded and the local service
reported no resident model afterward. Exact deployed model digests and Ollama
version were unchanged. Median text latency was 67.05 seconds, with no heavy
test suite overlapping inference. The independent review and root numeric
audit are under `tmp/deployment_context_v4/`.

After the live replay, the complete suite passed 1,334 tests with 26 skipped
in 109.450 seconds (`tmp/reliable_full_suite_final_v9.log`). An isolated wheel
again verified the five selected runtime modules and classifier artifact
byte-for-byte. The post-validation `candidate_snapshot_v4/snapshot.json`
archives 46 source/configuration files, 95 test files and final evidence;
its SHA-256 is
`049ec0150d6adcad927c47fa0109356e0aef482686a0b1ab536b57dd146ddf21`.
It is not a newly frozen unseen release. Implementation and scoped validation
are complete; the broader V2/V3 quality failures remain failures. No further
general-knowledge, exact-count or analogy-quality repair is claimed, and no
new live microphone sample was taken.

## 2026-09-15 conversation-opening follow-up

The user asked for context-first conversation without a missing-memory
preamble, and for first-person wording to be distinguished from an actual
request for stored information. The active classifier still accepted
“Can you help me plan my day?” as `required` during a local CPU development
probe. In the same probe, “I have twenty minutes. Help me tidy my desk.” was
accepted as `none`, and actual keys-location/previous-appointment recall was
accepted as `required`. These observations are development examples, not an
accuracy benchmark.

The application now asks a single question for missing information, mixed
unverified facts, unresolved requests and exhausted answer attempts. It no
longer precedes those questions with an unavailable-memory statement. The
answer prompt gives the same guidance. Final CLI rejection of stale evidence
also asks for current details while preserving the diagnostic and disclosure
lock. A general request plus its application clarification may enter bounded
task history only through the existing independent `safe_history_pair` check;
required recall and detected private content remain withheld. This supports
tested safe follow-ups, not unrestricted reuse of personal dialogue.

The shared proactive recall signal now distinguishes obligation forms such as
“What have I got to do…” from past events, supplied arithmetic/quoted work from
an unspecified previous error, and procedural “Where can I find…” questions
from assertions about an actual personal location. Bare first-person words
are insufficient. Explicit stored-input requests and direct personal-value
questions remain recognized without requiring “remember”. Imperative `use`
and `retrieve` requests are not current factual assertions.

An accepted `required` prediction without recognizable recall intent receives
the existing single bounded dependency review, with reason
`unverified_required`. Agreement retains `required`; disagreement or invalid
review asks for clarification. Recognized recall remains protected, and raw
`clarify` still bypasses review. Raw classifier metadata, review output and
the recall signal are retained separately. The classifier artifact, embedding,
and dependency-review prompt were not retrained or changed. Both classifiers
can still agree wrongly; direct public/personal location syntax can still
produce unnecessary recall handling. No universal intent guarantee is claimed.

Independent review found no material blocker. Focused tests cover the grammar
contrasts, one-review bounds, raw provenance, all missing-fact question types,
safe clarification continuation, private-history exclusion and session reset.
Six known live opening cases were prepared before execution under
`tmp/conversation_opening_20260915/`; their expectations allow either general
help or a relevant clarification for collaborative day planning. They are
fresh-session text replays with empty stores; multi-turn retention and lifecycle
behavior require the separate regression tests.

The first complete follow-up suite passed 1,351 tests with 26 skipped in
111.173 seconds. Its six-case live replay then placed all final modes inside
their accepted sets (five raw predictions did so), but independent review
accepted only four complete behaviors. The day-planning clarification asked
what help was needed even though the task was already stated. The desk reply
said it could help within twenty minutes and asked what was needed, without
giving any action; the model reviewer passed that nonanswer. Guitar-learning
steps, both required-detail questions and unfinished-speech clarification
passed. All six omitted unavailable-memory preambles; no unsupported personal
or deployment claim was observed.

All twelve calls stayed bounded: six compute decisions, two dependency reviews,
two generations and two answer reviews. The two generated replies took 66.72
seconds median; the four application questions took 5.18 seconds median, with
a 0.30–44.46 second range that includes any compute/dependency review. These
different reply types are not a speed comparison. All 42 runtime hashes and
the predeclared case hash matched before development resumed, as recorded in
`tmp/conversation_opening_20260915/end_of_run_verification.json`.

The narrow follow-up changes only the generic clarification to “Could you say
a little more?” and the bounded modal-assistance promise check. An “I can
help you…” payload containing only the supplied task/constraints and abstract
scaffolding is now a nonanswer. Request vocabulary is allowed only inside
that promise wrapper; concrete added steps, recommendations, capabilities,
requested questions and drafts remain controls. All 89 focused tests passed.
Independent reconstruction of those two changes reproduced the original
six-case source hashes exactly; routing, evidence checks and call bounds were
unchanged. The two affected cases are replayed separately, retaining the first
run's quality failures.

The affected replay accepted only one of two complete behaviors: inviting the
day-planning user to elaborate meets the minimal clarification criterion,
though it is generic. The desk request still failed: its small offer was
correctly rejected as `promise_only`, then the large candidate offered robot
physical work and was rejected with the recorded `unsupported_personal_claim`
issue. Both delivered replies were application questions. All five calls
stayed bounded, with no answer-review call. All 42 source hashes matched before
the subsequent prompt edit.

The final prompt refinement adds “For practical tasks, give steps the user can
perform” to the existing retry guidance. The final focused routing, reply,
opening, wrong-route, semantic and CLI suite passed 174 tests in 1.877 seconds.
A single known desk replay nevertheless failed again: the larger candidate
offered to gather and sort items itself, so both attempts were withheld and
the application asked for detail. The dependency was correctly `none`; this
is an answer-quality failure, not a memory-routing failure. Three calls stayed
bounded and shutdown succeeded. No additional attempts or weakened evidence
checks were introduced to obtain an apparent pass.

The final record is `tmp/conversation_opening_20260915/validation.json`. It
preserves the initial full-suite log (1,351 tests, 26 skipped), final focused
log (174 tests), all three distinct known text runs and their reviews, source
hashes and unchanged local model identities. The requested clarification and
recall-intent changes are implemented; useful model answers on every general
request remain unresolved. No new microphone sample or unrestricted quality
claim accompanies this follow-up.

## 2026-09-15 practical-answer follow-up

The user requested a further repair of the remaining desk-answer failure.
Correct `none` routing and a generic retry instruction had not produced a
useful answer: the small model offered help without actions, and the larger
model promised to perform physical work itself. This follow-up changes the
format of an eligible quality retry rather than adding another generic
instruction to the same free-prose response.

The new [human-guidance module](../../src/oline_hri/human_guidance.py) applies
on the existing small-to-large quality retry, or a remaining attempt after
optional evidence was discarded, for recognized practical help, planning or
how-to requests on the general/optional path with no linked personal evidence.
An initial large-model failure does not receive another attempt under the
existing loop.
Drafts, recognized personal recall, capability questions, general explanations
and ambiguous requests for help retain their existing contracts. Eligibility
uses a bounded action grammar, so many valid phrasings remain outside this
narrow path. The compact prompt asks for actions addressing the current task
and supplied constraints; it contains no concrete example instructions to copy.

Untimed replies contain one to five instruction strings. A single supported
minute budget instead requires one to five objects containing exactly
`minutes` and `instruction`. Every duration must be a positive integer, and
the parser requires their sum to equal the supplied budget. The bounded
extractor supports explicit digit budgets from one to 120 minutes and basic
written numbers from one to sixty. Ambiguous, multiple, non-minute and
unsupported duration expressions stay untimed. The application renders the
numbering and minute labels, with a maximum of 80 total speech words.

The parser rejects malformed or extra fields, wrong types, model-authored
leading list markers, detected first-person/robot actor wording, unsafe
characters and internal memory identifiers. `NO_ACTION` and an empty
`memory_used` are fixed by the application. Both the delivered rendering and
the canonical instruction text pass through the independent reply guards;
the latter prevents application numbering from hiding an empty offer. The
ordinary answer review still checks the rendered candidate with current
assertions and deployment facts. This format supplies no new personal-fact
authority and does not relax history or lifecycle checks.

The exact generated JSON remains the recorded `ChatResult`; the rendered
answer is identified by `response_transform="human_guidance_steps"`. Trusted
issue-specific retry feedback describes the detected failure without putting
failed candidate prose into history or authorized facts. The typed dispatch
uses the existing context budget and generation trace and counts as the
second of at most two answer attempts. It adds no planner or writer call.

The preliminary untimed known-desk replay **failed**. Its delivered list
copied the irrelevant prompt example “Open the folder” and omitted the
supplied twenty-minute constraint, although the model answer reviewer passed
it. The preserved [manual assessment](../../tmp/practical_answers_20260915/known_desk/manual_review.json)
and [raw calls](../../tmp/practical_answers_20260915/known_desk/model_calls.jsonl)
retain that failure. A model pass and an automatic general-answer outcome do
not establish useful task completion. Runtime development also overlapped
that preliminary run, so it is not final-source verification.

After removing the examples and introducing exact time allocation, the
preliminary timed known-desk replay passed the separately recorded minimum
behavioral criteria: four human-performed steps each received five minutes,
with actual clearing, sorting and cleaning actions. Its final instruction
remained vague; this was an actionable-plan pass, not an optimal-plan judgment.
The [independent review](../../tmp/practical_answers_20260915/known_desk_timed/independent_review.json)
records **98.783 seconds** for the turn and four actual calls: compute
selection, two answer attempts and one answer review. The
[raw calls](../../tmp/practical_answers_20260915/known_desk_timed/model_calls.jsonl)
preserve the rejected small offer and the accepted typed generation.

That timed result is also **preliminary**. The helper's eligibility predicate
changed during the run: 42 of 43 recorded source hashes still matched, while
`human_guidance.py` differed from its run-start hash. The observed answer and
latency remain valid records, but they do not verify all final source bytes.
The subsequent [six-case run metadata](../../tmp/practical_answers_20260915/live/metadata.json)
belongs to the frozen final runtime check and is still in progress at this
entry. No six-case pass or final-suite result is claimed here.

These changes enforce a response shape, explicit supported time arithmetic
and detected actor/list-marker restrictions. They do not prove arbitrary
instruction relevance, usefulness, feasibility, factual accuracy or personal
entailment. The approximately 99-second preliminary turn is not evidence of
interactive responsiveness. No new microphone recording was collected; all
reported live calls above are known text replays.


### Final practical generator policy and remaining limits

The completed retry-only six-case run passed 4/6 complete outcomes: desk and
three non-practical controls passed, while paper and laundry replies remained
weak despite model-review passes. Enforcing typed minute allocations from the
first attempt also passed only 4/6. Both generators assigned 1,2,3,4,5 minutes
to the ten- and twelve-minute tasks, and those answers were correctly withheld.
The subsequent timer-framing run passed 0/3 complete practical outcomes: all
time limits were explicit, but the small model's action sequences were incoherent.
The [validation record](../../tmp/practical_answers_20260915/validation.json)
preserves these separate failures, source proofs, raw calls and independent reviews.

The final policy uses the configured general-large model directly for explicit
timed practical requests without linked evidence (`practical_guidance_large`).
It retains the original compute decision and actual generator independently,
without a fictitious small-model fallback or further answer escalation to a
separately configured personal-memory model. Untimed practical requests retain
the existing quality-retry path. The final schema contains instruction strings;
the application adds an instruction to set a timer for the current request's
recognized budget and stop when it rings. It does not start a real timer or
ask the model to perform duration arithmetic. Raw JSON, canonical and rendered
reply checks, independent review, history admission and evidence boundaries remain.

The [final three-case review](../../tmp/practical_answers_20260915/live_large/independent_review.json)
passes 2/3: the desk failure is repaired and paper organization is useful;
laundry is partial because it assumes an unsupplied floor location and provided
fastener. These resource presuppositions are distinct from personal-history
recall/disclosure; they remain an observed limitation. All ten calls and all
43 final source hashes were verified. Median turn time was 50.66 seconds.
The final suite passed with 1,384 tests run and 26 skipped in 113.202 seconds;
205 focused tests passed in 2.119 seconds. The final source and new tests are
archived with the validation record. This is known targeted regression evidence,
not a pooled six-case pass, broad reliability proof or new microphone test.
