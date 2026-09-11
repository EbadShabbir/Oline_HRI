# General answers and bounded software plans — 2026-09-10

## Outcome and important execution caveat

The diagnostic answer review improves from **22/30 to 26/30 complete answers**.
Two answers remain partial and two remain incorrect. Supported offline testing,
release, recovery, presentation, and travel plans are more concrete. General
model reasoning is **not solved**.

The final-source evidence is **split**, not one uninterrupted 30-case benchmark:
the watchdog stopped a rerun after 27 completed answers on a malformed-telemetry
notification. After a healthy no-inference monitoring check, the remaining
three cases passed separately. Across those 30 distinct cases, every delivered
answer passed validation and all 18 required citations were correct. The
interrupted run's protocol remains incomplete; it was not relabeled complete
or merged into a synthetic uninterrupted benchmark.

Additional checks: **12/12 memory paraphrases**, **5/5 memory compositions**,
and **5/6 complete answers** on a six-question reasoning/planning development
fixture. These are targeted development checks and an unblinded assistant
review, not independent human evaluation or an estimate of general accuracy.

The pair remains `qwen3:0.6b` / `qwen3:1.7b`, context 2048, output cap 192,
temperature 0, thinking off, seed 42, and serial model residency. No weights
were trained, downloaded, or replaced. No cloud reasoning service was added.
The production personal-memory database was not touched.

Baseline: [previous composition report](./20260910_composition_report.md).
Observations, audit labels, source-match checks, telemetry, and artifact hashes:
[results JSON](./20260910_reasoning_results.json).

## Changes

- Add at most two small, reviewed technical notes for explicitly matched
  concepts. These are bundled application knowledge, not personal memories,
  and require no runtime network access. `reference_ids` records their use
  independently of personal citations. The generator still writes its answer;
  receiving a note does not establish that the answer is correct.
- Narrow the database-note selector after a live regression: an FTS5 or
  virtual-table question does not receive generic transaction/comparison
  notes unless it actually asks about transaction/concurrency behavior.
  The final FTS5 definition is back to a clean, correct answer.
- Use task-shaped instructions for comparisons, mechanisms/limitations, and
  plans. Request one-line spoken English without LaTeX or backslash escapes.
  Unsafe control characters are still rejected, not silently repaired.
  Machine-field echoes such as `Memory used: []` are rejected even without
  personal citations. Two narrow observed SQLite/RRF contradictions have
  explicit rejection checks; this is not a general fact checker.
- Prompt-only planning remained unreliable, so recognized offline software
  testing, release, and database-recovery requests can use **application-authored
  bounded plans**. These specify faults, checks, stop/rollback conditions,
  preservation of originals, or recovery limits as appropriate. They are not
  evidence that the small model learned to reason. No step is executed.
- Constrain the complete bounded plan during small-model decoding, and reject
  any changed speech or invalid citations. `answer_constraint` identifies
  `bounded_software_validation`, `bounded_software_release`, or
  `bounded_database_recovery`. `generation_policy=verified_constraint_small`
  distinguishes the deliberate decoder choice from a timeout fallback.
  Original routing intent, actual model, and raw generations remain recorded.
- Recognize three/five-stage validation and three-stage release plans. Decline
  known unsupported counts, custom formats, budgets, time limits, languages,
  and incompatible constraints. Unsupported requests keep ordinary guarded
  generation; these bounded heuristics do not understand every possible request.
- Improve memory-based preparation plans: presentation stages now include
  evidence/timing checks and a demo fallback; travel checks stay with their
  specific date, transport, and venue. Complete original memory facts and all
  citation/freshness validators remain intact.

Composed answers remain capped at 80 words and 850 characters, without cutting
source facts. Ordinary model prose has an 80-word prompt target, not a universal
word-count validator; some development answers exceeded that target. The hard
192-token generation limit is unchanged. An overlong five-stage prototype
truncated; the shortened version completed in **177 tokens** in a real budget
check and in the later adaptive tests.

Production conversations enable composition by default. The controlled
temperature-comparison runner's existing `grounded_composition=False` also
opts out of these software runbooks. New prompt/reference guidance is still
source-versioned behavior; historical experimental results remain historical.

## Technical reference basis

The cosine note uses the normalized-dot-product definition. Positive-scaling
invariance, sign reversal under negative scaling, and the mathematical
zero-vector limitation follow from that formula; library conventions can
differ at zero. [scikit-learn definition](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.pairwise.cosine_similarity.html).

The database note corrects the observed false claim that SQLite lacks
transactions and distinguishes embedded storage from a server database.
Concurrency/resource guidance is drawn from the database documentation.
[SQLite transactions](https://www.sqlite.org/transactional.html),
[SQLite usage guidance](https://www.sqlite.org/whentouse.html),
[PostgreSQL transactions](https://www.postgresql.org/docs/18/tutorial-transactions.html).

The fusion note distinguishes rank-based fusion from combining numerical
scores. The loss of score-gap information and invariance to score rescaling
are consequences of rank-only input; normalization/calibration guidance is
application reasoning, not a universal guarantee of which method wins.
[RRF definition and formula](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion).

These notes cover three concepts only. The software runbooks are authored
application procedures, not externally certified operational instructions.

## Answer quality on final-source case coverage

| Cases | Observed outcome |
| --- | --- |
| 3: FTS5 | Correct definition restored after removing irrelevant database notes |
| 7: cosine | Correct normalized-dot-product explanation |
| 9: validation | Five actual faults, checks, stop conditions, isolation, logging and rollback |
| 12: recovery | Original preservation, conditional backup path, salvage, checks and recovery limits |
| 14: release | Local preparation, staged tests, acceptance checks, rollback trigger and operator records |
| 27: presentation | Full remembered facts plus actionable checks and demo fallback |
| 30: travel | Both dates/facts preserved with separate transport/venue checks and contingencies |

Remaining **incorrect** cases are 8 and 11. The SQLite ACID misconception is
fixed, but case 8 still gives a poor migration sequence that tests after
switching, with overbroad concurrency claims. Case 11 still misdescribes RRF's
mechanism as adding a constant to scores. These are observed defective answers,
not recommendations from this report.

Cases 10 and 13 remain **partial**: vague correction/retrieval-race mitigations,
and overlapping context-bounding options with an inadequately justified default.
Structured output validation does not catch all of these semantic defects.

The 26-complete count uses the final rerun's first 27 cases plus the three
separate tail cases. All 30 final hybrid route decisions match the fixture;
the cross-run citation check is 18/18 precision and recall. These are diagnostic
coverage calculations, not a new completed benchmark protocol or latency run.

## Development and transfer checks

The [six-question fixture](./20260910_reasoning_checks.json) was frozen before
baseline collection. Baseline review: zero complete, three partial, three
incorrect answers. Prompt-only revisions corrected some facts but also produced
LaTeX/control-character failures, inverted fusion facts, missing stop conditions,
and a release answer that merely echoed the request. Those runs are retained.

With bounded plans, the latest six-question development run had five complete
answers and one incorrect fusion recommendation: it suggested averaging without
resolving incompatible score scales. All six passed structural validation.
This run preceded the final FTS5-only relevance filter; all six questions still
select the same reference IDs under the final code. Its source hash is therefore
not presented as a final-source run, and it is not an untouched holdout.

On final source, the [12-case memory fixture](./20260910_recall_paraphrases.json)
passed eight known facts and four safe unknown-fact abstentions. The
[five-case composition fixture](./20260910_composition_checks.json) preserved
all expected facts and citations, including the more detailed presentation and
travel checks. Both used fresh isolated databases and real BGE retrieval.
Process-restart persistence was not rerun in this revision; the earlier 7/7
result remains in the baseline report, not a new result here.

## Performance: completed development run only

Run `a103c8299d094b71823839d4bd148664` completed all 16 retrieval records and
30 adaptive cases before the final FTS5 filter. It retained 30/30 validation,
18/18 citation precision/recall, and 100% required evidence coverage. Raw router
accuracy was 19/30 for memory, 28/30 for size, and 19/30 jointly; hybrid routing
was 30/30. These are not claims of perfect raw-model routing.

| Metric | Previous composition run | Completed development run |
| --- | ---: | ---: |
| Actual small / large generations | 23 / 7 | 26 / 4 |
| End-to-end p50 | 2.851 s | 2.853 s |
| End-to-end p95 | 59.969 s | 38.778 s |
| Telemetry interval | 478.81 s | 303.18 s |

This measured run was shorter and had a lower p95; the median was unchanged.
Three software plans no longer require loading 1.7B. Do not interpret one
development comparison as a controlled speedup or use these timings as an
uninterrupted benchmark of the final source. The later split runs have no
combined benchmark latency metric.

## Telemetry interruption and safety

Final-source run `40d5ac6e40d846959faf856ab004ee49` completed 27/30 cases and
all 16 retrieval records before the watchdog reported `telemetry sample was
malformed`. It interrupted inference and unloaded the model. Its protocol is
still incomplete. Recorded peak RAM/swap/temperature were 6,399 MB / 228 MB /
59.0°C, with unchanged boot ID and zero thermal-trip counters. No hard resource
limit breach or reboot was observed, but monitoring continuity was lost.

The precise underlying reader/sample error was not retained in that run, so
its root cause is unresolved. A subsequent 20-second no-inference probe returned
39 valid samples and no reader error. Only the short remaining-case, paraphrase,
and composition checks resumed afterward; all passed with healthy monitoring.
The harness now records future telemetry-reader error type/message in the
finish artifact. No watchdog threshold or fail-closed behavior was relaxed.

| Phase | Peak RAM | Peak swap | Peak temperature |
| --- | ---: | ---: | ---: |
| Completed pre-filter adaptive | 6,457 MB | 220 MB | 59.41°C |
| Interrupted final-source adaptive | 6,399 MB | 228 MB | 59.00°C |
| Final three tail cases | 5,772 MB | 228 MB | 55.56°C |
| Final 12 memory paraphrases | 5,672 MB | 228 MB | 57.09°C |
| Final five compositions | 5,805 MB | 224 MB | 56.59°C |

All inference remained serial in 15 W mode with an active fan. Start gates
retained the 2 GiB available-RAM minimum, below-55°C requirement, and no resident
model. Runtime guards retained the 768 MiB available-RAM floor, 512 MiB swap
ceiling, 68°C temperature ceiling, and boot/trip/telemetry checks. All recorded
finish snapshots have no resident models. One permission review timed out
before a transfer test started; its permitted retry ran normally.

## Verification and artifacts

**691 offline tests: 665 passed, 26 opt-in live tests skipped.** Added tests cover
reference relevance/provenance, budget accounting, escaped user text, privacy
separation, narrow contradiction guards, machine-field leakage, bounded plan
counts/constraints, missing backups, strict literal decoding and scoring.
Selected fatal flake8 and scoped whitespace checks passed.

The final interrupted run, tail, paraphrases, and compositions match the final
application source hashes. Prototype and pre-filter results intentionally do
not. Telemetry error reporting was added to the harness after the interruption;
it does not change the application or relax monitoring.

Raw fictional artifacts are owner-only under
`/home/b2jetson/.local/share/oline-hri/evaluation-runs/reasoning-*20260910*`.
All earlier results were preserved. This tests the real text/model/retrieval
path, not microphones, ASR, TTS, or robot motion. No unrelated user changes were
reset, committed, or deleted.
