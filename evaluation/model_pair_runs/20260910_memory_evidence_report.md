# Personalized-memory improvements — 2026-09-10

## Outcome

The original restart test improved from **3/7 to 7/7 correct known-fact
answers**, with both unknown-information questions still safely abstaining.
All seven stored records survived and remained unchanged. The full adaptive
run improved from **22/30 to 25/30 validated responses**; five were withheld.
The three newly successful cases are expired-notebook abstention, Sunday-train
recall, and the tea-change/navigation timeline.

Keep the same Jetson configuration: `qwen3:0.6b` routing/small answers,
`qwen3:1.7b` for both large roles, context 2048, output cap 192, temperature 0,
thinking off, speech instructions capped at 80 words, serialized LLM residency.
No models were downloaded, replaced, or deleted, and 4B inference was not used.

This is a substantial improvement in guarded recall, **not unrestricted
personalization**. Twelve additional checks with new fictional facts and wording
passed 9/12; general factual errors and difficult synthesis remain.

Exact metrics and artifact hashes are saved in
[20260910_memory_evidence_results.json](./20260910_memory_evidence_results.json).
The comparison baseline is the
[2026-09-09 remediation run](./20260909_remediation_report.md).

## Changes implemented

- Rerank the existing, bounded RRF candidate pool using lexical topic coverage.
  Multi-topic requests favor uncovered topics so adjacent project records do
  not crowd out the requested answer-length preference, tea change, or travel
  plan. No new model, embedding pass, or larger candidate pool is needed.
  Original RRF scores/source positions remain diagnostics, not final-rank scores.
- When request-linked evidence exists, exclude unrelated records and their IDs
  from both the generation prompt and citation allowlist. Mandatory evidence
  remains whole and must fit the unchanged context budget.
- Correct the parser that mistook `plant`/`planetary` for `plan`. Treat a direct
  preference choice as direct recall. Share completion-word normalization
  between retrieval ranking and evidence linking.
- Add bounded subject/attribute checks: notebook recall needs notebook evidence;
  bicycle color needs a color bound to the bicycle, not a neighboring backpack
  or helmet; an object's existence alone does not establish its name.
- Select each explicitly compared `when ... with when ...` event separately.
  This excludes a kickoff milestone from a tea-change/navigation comparison
  while preserving it in an earlier/latest milestone comparison.
- Normalize only a verbatim, correctly cited copy of a single first-person
  human disclosure to you/your. Preserve raw model output and record
  `response_transform=verified_memory_perspective`. Arbitrary claims and missing
  citations are not repaired; all grounding validators still run afterward.
- Strengthen the first-person event guard, retain conflict/relationship checks,
  and add tests for missing attributes, unrelated candidates, new names/objects,
  temporal facets, raw-output preservation, and transformation provenance.

The rules are bounded English heuristics. They do not replace consent,
retention, snapshot freshness, citation, or semantic-quality checks. Unknown
queries can still retrieve and inspect an unlinked nearest neighbor internally;
that record is not answer authority and the application returns fixed abstention.

## Full adaptive comparison

Run ID: `ba81470723834592baa69164d2c7257f`. The same fictional seven-day fixture,
seed 42, one repetition, production conversation path, real BGE embeddings,
SQLite retrieval, and final application source were used. Collection completed
all 16 retrieval records and all 30 adaptive cascade records.

| Metric | Previous remediation | This run |
| --- | ---: | ---: |
| Final joint routing | 30/30 | 30/30 |
| Structured application responses | 22/30 | 25/30 |
| Withheld responses | 8 | 5 |
| Component retrieval recall@3 | 81.82% | 100% |
| Required supplied-evidence coverage | 81.82% | 100% |
| Supplied-evidence micro precision | 52% (13/25) | 90% (18/20) |
| Accepted citation micro precision | 100% (4/4) | 100% (7/7) |
| Citation recall | 22.22% (4/18) | 38.89% (7/18) |
| Truncated responses | 0 | 0 |
| Timeout/fallback events | 0 | 0 |
| End-to-end p50 / p95 | 2.666 / 54.162 s | 2.581 / 36.698 s |
| Adaptive telemetry interval | 612.90 s | 443.84 s |

Retrieval coverage is averaged over the 11 answerable cases, not all 30
prompts. The two irrelevant supplied records belong to empty-gold questions;
their generated claims were replaced by safe abstention. All three privacy
queries blocked cascade retrieval, and no forbidden IDs were retrieved or cited.

The raw classifier still scores 19/30 memory, 29/30 size, and 19/30 jointly.
The 30/30 final score belongs to the existing hybrid policy. These development
fixtures informed the changes; neither routing nor retrieval scores estimate
unseen accuracy.

Latency was lower in this run, but it is not a controlled speedup estimate.
The board rebooted between test dates, had substantially less memory/swap
pressure, and some generated answers changed despite the fixed recipe. Both
router calls and answer generation still execute. The context/model limits
were not increased to achieve the result.

### Remaining adaptive failures

All five failures were reproduced offline from the retained generations using
the final source. They are validation errors, not model transport failures.

| Case | First rejecting check and remaining issue |
| --- | --- |
| 17: relationship | Supported fact is still phrased as “Mira's … partner is Theo”; the requested user-perspective relationship binding fails |
| 26: conflicting labs | Both records are available/cited, but the model asserts Lab B without acknowledging uncertainty |
| 27: personal preparation plan | All three relevant records are supplied/cited, but meeting-window/completion details are omitted and the model adopts the human's preference |
| 29: recency + collaborator | Milestone order is now correct, but the kickoff record's required citation is missing; full relationship/date details also need work |
| 30: travel synthesis | The temporal-detail check rejects the answer; it also omits Al Ain and the full robotics-museum context |

The travel check currently requires temporal metadata beyond the dates alone
in this request. That validator contract deserves separate review; rejection
alone does not establish that every omitted detail was requested. The answer
still does not fully cover the fixture's travel facts.

A diagnostic assistant review finds 18 complete answers, four partial answers
(9, 10, 13, 14), three incorrect answers (7, 8, 11), and five withheld answers.
This is not blinded human review; formal quality remains
`pending_blinded_human_review`. General errors include cosine magnitude,
SQLite transaction/foreign-key claims, and a misleading rank-fusion comparison.
No unsupported personal claim was observed in the delivered original-fixture
answers, but raw generations still contain errors that the application blocks.

## Restart and additional wording checks

The final learn and recall phases used separate PIDs, 13671 and 14007, with
a new isolated database. Capture status matched 10/10 disclosure expectations;
seven records were stored. Kind classification remains 6/7: the plant fact
was again labeled an event. The same-process three-question recall passed 3/3.

Fresh-process recall correctly answered tea, meeting time, Maya's relationship,
bicycle color, plant name, completed test, and answer-length preference. Dog name
and birthday correctly abstained: **9/9 total**. Stored dictionaries matched
exactly before and after recall. Meeting/event replies used the logged verbatim
perspective normalization; the other seven replies did not.

The [additional fixture](./20260910_recall_paraphrases.json) was fixed before
collection and was not retuned after seeing its failures. It uses new objects,
names, values, and wording. Results: **5/8 known-fact questions correct and 4/4
unknowns safely abstaining, 9/12 overall**. The unresolved cases were:

- “Do I prefer brief or lengthy replies?” — generated “brief replies” but lost
  the stored under-two-sentences limit; coverage validation rejected it.
- “Remind me what test I finished.” — the router skipped memory and incorrectly
  denied having a test to recall.
- “What do you remember about my scooter?” — retrieval found the correct
  record, but the conservative request-link check still led to abstention.

These checks limit the generalization claim. They are additional developer
checks, not an independent or statistically representative benchmark.

## Jetson safety and verification

All final live phases ran sequentially in 15 W mode with an active fan. Start
gates and runtime limits were unchanged. One additional-check attempt was
refused before loading a model because start temperature was at/above 55°C;
the successful retry began after cooling. No runtime guard fired.

| Final phase | Samples | Peak RAM | Peak swap | Peak temperature |
| --- | ---: | ---: | ---: | ---: |
| Learn | 73 | 5,247 MB | 7 MB | 57.63°C |
| Fresh recall | 58 | 5,214 MB | 7 MB | 57.63°C |
| Additional wording | 70 | 5,266 MB | 7 MB | 57.78°C |
| Full adaptive | 877 | 6,087 MB | 10 MB | 59.47°C |

Each final phase ended with no resident LLM, unchanged within-run boot ID, and
zero thermal-trip counters. Safety measurements apply to this guarded test
workload, not arbitrary concurrent workloads or new production monitoring.

Final offline suite: **620 passed, 26 opt-in live tests skipped**, 646 total,
28.416 seconds. The new evidence suite has 12 methods. Python compilation,
runtime-error-only Flake8 checks, and whitespace checks passed. Full style-lint
cleanliness is not claimed. All four final live source-hash manifests match
the current application source exactly.

## Saved evidence and next work

Owner-only raw bundles under
`/home/b2jetson/.local/share/oline-hri/evaluation-runs/`:

- `evidence-final-learn-20260910`
- `evidence-final-recall-20260910`
- `evidence-final-memory-20260910` — persistent database and transcripts
- `evidence-paraphrases-20260910-02`
- `evidence-adaptive-20260910`

Preliminary runs and the refused warm-start attempt remain separate and are
not pooled into final scores. The JSON report contains bundle hashes, exact
metrics, raw/final response comparisons, and per-case diagnostic judgments.

Next priorities are citation-complete constrained generation, complete fact
rendering and user perspective, conflict-aware answers, date-versus-clock
validation, and recall phrasing beyond the current heuristics. Keep the
grounding gates active. The model pair remains a guarded development baseline.
Microphone, STT, TTS, physical gestures, and the production personal-memory
database were not part of these tests.
