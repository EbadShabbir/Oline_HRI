# Bounded memory composition — 2026-09-10

## Outcome

The full adaptive run improved from **26/30 to 30/30 validated responses**,
with no withheld answers. All 18 required memory citations were present and
correct. The previously missing partner, milestone, meeting-window, tea, and
travel facts now survive into the delivered answers.

The 12-case paraphrase regression passed again. Fresh-process recall answered
all seven known facts and safely declined both unknown questions; all seven
persisted records remained unchanged.

This is an application-level improvement, not 100% model accuracy. A diagnostic,
unblinded assistant review counts **22 complete, five partial, and three
incorrect answers**. The partial answers include the generic travel checklist;
general factual explanations still contain errors. Independent human quality
review and representative unseen testing remain necessary.

Keep `qwen3:0.6b` for routing/small answers and `qwen3:1.7b` for general and
memory large-model roles, with context 2048, output cap 192, temperature 0,
thinking off, and one model resident at a time. Fully specified, bounded
memory compositions now decode on 0.6B even when the router selects large.
No models were downloaded/replaced, no 4B model was used, and the production
personal-memory database was not touched.

Baseline: [previous reliability report](./20260910_reliability_report.md).
Detailed observations and artifact hashes: [results JSON](./20260910_composition_results.json).

## What changed

- A small extractive answer builder preserves complete source facts for a
  named partner, two-event chronology, milestone comparison, three-stage
  presentation preparation, and a two-date travel checklist. Names, values,
  dates, and destinations come from the retrieved records, not fixture IDs or
  hard-coded answers. Planning steps are generic application templates, not
  retrieved facts or evidence of improved model reasoning.
- Speech is constrained to the composed literal. The model must still emit
  valid structured output and all required citations. Changed speech, missing,
  duplicate, invented, unauthorized, or stale citations remain rejected.
  Both pre-generation and post-generation freshness checks remain active.
- Named-owner facts retain their owner: `Mira's ...` is not silently changed
  to `your ...`. Explicit first-person user facts can use you/your. A complete
  literal named-owner relationship is now accepted by the relationship guard;
  a negated prefix or a missing requested relationship is not.
- Explicit collaborator requests link to positive relationship evidence,
  including user-owned `Noor is my ... partner` records. Topic qualifiers must
  agree; an astronomy partner cannot satisfy a robotics-partner question.
- Compositions are limited to one to three simple facts and 80 speech words.
  Missing/ambiguous dates, same-day chronology, conflicting labels, exact-clock
  requests, quoted/conditional facts, unsupported formats/modifiers, and
  over-budget answers decline this path. Ordinary guarded generation remains
  available; these heuristics do not cover arbitrary questions.
- `answer_constraint` identifies the builder; `generation_policy` records
  `verified_constraint_small` when it overrides large-model decoding. Raw
  model output and original routing intent are retained. This is not a timeout
  fallback, and scoring reports the actual model separately.

Production conversations enable this path by default. The controlled
temperature-comparison runner explicitly disables these new compositions so
its sampled-prose arms do not all receive identical compiled answers. It is
not the production adaptive run reported below.

## Full adaptive workflow

Run `aa04e657cf8745ec8a278fa5c0246559` completed all 16 component retrieval
records and all 30 adaptive cases on the original fictional seven-day fixture,
seed 42. Application source hashes match the final tested revision. Other
evaluation strategies were not rerun. This is one development comparison,
not a blinded benchmark or a repeated performance estimate.

| Metric | Previous reliability run | This run |
| --- | ---: | ---: |
| Final hybrid routing | 30/30 | 30/30 |
| Validated responses | 26/30 | 30/30 |
| Withheld answers | 4 | 0 |
| Complete answers, unblinded diagnostic audit | 18/30 | 22/30 |
| Retrieval recall@3, 11 answerable cases | 100% | 100% |
| Required supplied-evidence coverage | 100% | 100% |
| Supplied-evidence precision | 18/20 | 18/20 |
| Accepted citation precision | 9/9 | 18/18 |
| Citation recall | 9/18 | 18/18 |
| Small / large decoding attempts | 19 / 11 | 23 / 7 |
| End-to-end p50 / p95 | 2.805 / 55.789 s | 2.851 / 59.969 s |
| Telemetry interval | 612.57 s | 478.81 s |

The full interval was shorter, but median latency was essentially unchanged
and p95 was worse. Do not claim a general latency improvement from this single
run. The four large-intent memory compositions now took **4.37–5.51 seconds**
each, using 0.6B without a large-model load. Seven general tasks still used
1.7B and dominate the slow tail.

Raw classifier accuracy was 19/30 for memory intent, 28/30 for size, and
19/30 jointly. The 30/30 score belongs to the hybrid application policy,
not to the raw router. All three privacy cases blocked cascade retrieval.
No forbidden retrieval/citation, unexpected citation, timeout fallback, or
output truncation was recorded. Two empty-gold cases still supplied an
irrelevant nearest neighbor, although the answers correctly abstained.

| Changed case | Delivered result |
| --- | --- |
| 17: partner | Complete literal `Mira's robotics project partner is Theo.` |
| 27: presentation | Completion, 09:00–11:00 window, full answer-length preference, three short preparation stages |
| 28: timeline | Ginger tea without sugar, both dates, chronological entries, explicit later entry |
| 29: milestones | Both complete milestones, newer entry, and full collaborator relationship |
| 30: travel | Both dates, train/destination and museum retained; generic checklist, still partial for requested detail |

The audit marks cases 9, 10, 13, 14, and 30 partial, and cases 7, 8, and 11
incorrect. These concern incomplete general plans/explanations, an incorrect
cosine-similarity explanation, incorrect SQLite transaction claims, and a
misleading fusion-method comparison. They are observed answer defects, not
new technical recommendations. Case 8 also leaks `Memory used: []` into speech;
that generic provenance wording still passes the existing boundary. The new
composition path does not repair general answers.

## Additional wording and development evidence

The original [12-case paraphrase regression](./20260910_recall_paraphrases.json)
passed **8/8 known facts and 4/4 unknown-fact abstentions** again with real BGE
retrieval, isolated SQLite storage, and the installed small model. Expected
citations match every delivered answer.

The [five-case composition fixture](./20260910_composition_checks.json) uses
different names, objects, dates, preferences, and destinations. Its first live
attempt exposed an unlinked user-owned partner facet: one partner answer was
withheld and one milestone answer omitted the collaborator. After the linking
and guard fix, **5/5 passed the factual-coverage and citation checks**. This is
now a development regression set, not an untouched holdout. Its detailed
presentation request still receives only three generic preparation steps;
factual coverage is not the same as satisfying every depth/style request.

Two earlier five-case focus runs passed validation while developing the
builder and the small-decoder policy. Their application hashes precede the
final collaborator fix, so they are retained as prototype evidence only.
All failed/incomplete development results remain available in separate private
artifact directories; none were overwritten or counted as final successes.

## Capture, restart, and Jetson safety

Learn and recall ran in separate processes, PIDs 29166 and 29345. Capture
status matched 10/10 disclosure expectations and stored seven records.
Same-session recall passed 3/3; fresh-process recall passed 7/7 known facts
plus 2/2 safe abstentions. Full stored-record dictionaries match after capture,
before restarted recall, and after recall. Two restarted answers used the
existing preference constraint and two used verbatim perspective normalization.

Capture kind classification remains 6/7: the plant is labeled an event.
The event and mood disclosure acknowledgements still echo the human's
first-person wording. These are remaining chat-quality defects, not successful
personalized-answer results. The mood was correctly not stored.

Every inference phase ran sequentially with an active fan in 15 W mode. Start
gates retained the 2 GiB available-RAM minimum, below-55°C requirement, and
empty model residency. Runtime guards retained the 768 MiB available-RAM floor,
512 MiB swap ceiling, 68°C temperature ceiling, telemetry health, and unchanged
boot/thermal-trip checks. No safety guard fired, no reboot or thermal trip
was observed, and all phases ended with no resident models.

| Final-source phase | Peak RAM | Peak swap | Peak temperature |
| --- | ---: | ---: | ---: |
| Five composition checks | 5,872 MB | 163 MB | 55.59°C |
| Full adaptive | 6,484 MB | 167 MB | 58.41°C |
| Twelve paraphrases | 5,640 MB | 167 MB | 55.47°C |
| Learn | 5,787 MB | 167 MB | 57.03°C |
| Fresh-process recall | 5,753 MB | 167 MB | 56.28°C |

All five final-source phases match the final application hashes. The three
prototype phases intentionally do not. One permission-review attempt timed
out before starting paraphrase inference; its permitted retry completed.

## Verification scope

Offline verification: **674 tests discovered, 648 passed, 26 opt-in live tests
skipped**. Regression tests cover complete composition, strict backend output,
citation order/cardinality/aliases, stale snapshots, missing collaborators,
named-owner versus user ownership, novel dates/values, unsupported formats,
ambiguous dates, and budgets. Selected fatal flake8 and scoped whitespace
checks passed. The live runs above exercise real text generation and retrieval;
they do not test microphone, ASR, TTS, or robot motion.

Private owner-only artifacts are under
`/home/b2jetson/.local/share/oline-hri/evaluation-runs/composition-*20260910*`.
Only fictional summaries are included here. Existing user changes were
preserved; no user files were reset, committed, or deleted.
