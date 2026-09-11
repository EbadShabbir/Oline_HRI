# Guarded memory reliability — 2026-09-10

## Outcome

The earlier additional-wording test improved from **9/12 to 12/12 correct
application answers**, including all eight known facts and all four unknown-fact
abstentions. A second, frozen fictional fixture also passed **12/12** with new
names, objects, values, and wording. The full adaptive fixture improved from
**25/30 to 26/30 validated responses**; four responses were withheld.
Fresh-process recall remains **7/7 known facts plus 2/2 safe abstentions**, and
all seven persisted records remained unchanged.

Keep the same `qwen3:0.6b` router/small model and `qwen3:1.7b` for both large
roles, context 2048, output cap 192, temperature 0, thinking off, and serialized
model residency. No model downloads, replacements, 4B inference, or larger
context were used. The production personal-memory database was not touched.

These results support better **guarded direct recall**, not unrestricted
personalization or 100% model accuracy. Structured validation does not establish
semantic correctness. Complex synthesis and general factual answers remain weak.

The baseline is the [earlier memory-evidence report](./20260910_memory_evidence_report.md).
Detailed observations, metrics, and artifact hashes are in
[the results JSON](./20260910_reliability_results.json).

## Changes

- Recognize explicit personal `remind me what/which/...` recall, without
  treating future `remind me to ...` tasks as factual recall. History-sensitive
  routing still defers to the classifier. Raw classifier output is retained.
- Link explicit `what do you remember about my <object>` queries to that
  object. Attribute questions still need attribute evidence; a canoe record
  does not reveal its color. Normalize finished/completed evidence and rewrite
  narrowly recognized completion-recall requests into direct questions.
- Require as many citation-array entries as required evidence records during
  generation, not merely one. Existing missing, duplicate, unauthorized, and
  stale-citation checks remain. The Ollama alias boundary now recognizes only
  these bounded schema variants; actual memory IDs still do not go on the wire.
- For a direct preference question supported by one simple first-person
  canonical sentence, constrain speech to that complete fact in you/your form.
  This preserves numerical limits and restrictions. Named-owner, quoted,
  reasoning, and multi-fact requests are excluded. This is explicit extractive
  decoding, recorded as `answer_constraint=verified_preference`, not evidence
  of improved model reasoning. A backend ignoring the constraint is rejected.
- When the existing narrow conflict detector finds alternative labels such
  as Lab A/Lab B, a confident model choice becomes a fixed clarification only
  after required-citation and freshness checks pass. Raw output is preserved,
  and `response_transform=conflict_clarification` records the intervention.
  All subsequent validators still run. Missing citations are never fabricated.
- A date-only comparison of distinct-date events need not repeat metadata
  clock times. Explicit clock requests, same-day events, and clocks stated in
  canonical facts retain strict coverage requirements. This has offline
  regression coverage; the full travel answer did not succeed in this run.
- Tighten the memory-answer instruction and retain the explicit ban on spoken
  citation/provenance labels. Instructions remain imperfect, as the synthesis
  results below demonstrate.

## Full workflow

Run `ad6311081ccb4403a565666da92a57d9`: all 16 retrieval records and 30 adaptive
cases completed, using the original fictional seven-day suite and seed 42.
The final application source hashes match the collected run. One repetition
was collected; this is a development comparison, not a blinded benchmark.

| Metric | Earlier run | This run |
| --- | ---: | ---: |
| Final hybrid routing | 30/30 | 30/30 |
| Validated application responses | 25/30 | 26/30 |
| Withheld | 5 | 4 |
| Retrieval recall@3, 11 answerable cases | 100% | 100% |
| Required supplied-evidence coverage | 100% | 100% |
| Supplied-evidence micro precision | 18/20 | 18/20 |
| Accepted citation precision | 7/7 | 9/9 |
| Citation recall | 7/18 | 9/18 |
| End-to-end p50 / p95 | 2.581 / 36.698 s | 2.805 / 55.789 s |
| Telemetry interval | 443.84 s | 612.57 s |

This run was slower, not faster. Large-model load time and device memory
pressure varied; no controlled speedup is claimed. Raw router accuracy remains
19/30 memory decisions, 29/30 size decisions, and 19/30 jointly. The 30/30 score
belongs to the hybrid application policy. All three privacy cases blocked
cascade retrieval. No forbidden citation or retrieved-ID hits were recorded.
No timeout/fallback or truncation was recorded; one generation failed without
a retained generation object, so its completion reason is unavailable.

The newly delivered adaptive response is the Lab A/Lab B clarification. The
raw model still chose Lab B: the reliability gain comes from the application
guard, not from a correct raw model answer.

| Remaining case | Observed issue |
| --- | --- |
| 17: partner | Requested user/collaborator relationship binding is missing; withheld |
| 27: preparation plan | All three records are cited, but meeting/completion facts are missing; withheld |
| 29: recency | All three required citations now appear, but the earlier milestone is missing from speech; withheld |
| 30: travel | The generation adapter reported `OllamaError`; no response was delivered |

A separate one-case diagnostic reproduced the travel failure with the same
application source and seed: `Ollama assistant speech contains a reserved
memory reference`. This is the citation/speech boundary rejecting model text,
not an observed timeout, Jetson safety failure, or memory-persistence failure.
Its failed result is retained separately and does not alter the 30-case score.

The three response-validation failures reproduce offline from retained raw
generations. Timeline case 28 passes validation and gets the dates/order right,
but omits ginger tea and does not clearly format two entries. It is incomplete,
not a full semantic pass. General cases 7, 8, and 11 still contain incorrect
explanations. Formal answer quality remains pending blinded human review.
A diagnostic, unblinded assistant audit counts 18 complete, five partial
(9, 10, 13, 14, 28), three incorrect (7, 8, 11), and four withheld answers.
The complete-answer count on this full fixture therefore has not increased
from the earlier audit: conflict handling improved, but the timeline became
less complete. Do not interpret 26/30 validation as 26 correct answers.

## Recall and persistence

The original [12-case fixture](./20260910_recall_paraphrases.json) is now a
development regression set: final result 8/8 known facts plus 4/4 abstentions.
The [second fixture](./20260910_reliability_paraphrases.json) was frozen before
live collection and was not tuned after seeing its results: also 8/8 plus 4/4.
It is a small targeted check, not an independent or representative benchmark.
Each fixture used a fresh isolated SQLite database and real BGE retrieval.
Each used one constrained preference answer; the first used two verified
perspective normalizations and the second used one.

The fresh learn and recall phases ran in separate processes, PIDs 23031 and
23304. Capture status matched 10/10 disclosure expectations, with seven records
stored. Same-session recall passed 3/3; fresh-process recall passed 7/7 known
facts and 2/2 unknown-fact abstentions. Full stored-record dictionaries match
before and after restart/recall. Two answers used the preference constraint and
two used the existing verbatim perspective normalization.

Capture kind classification remains 6/7: the plant fact is labeled an event.
Some non-memory disclosure acknowledgements still echo first-person human
event/mood wording; these are not counted as successful personalized answers.
These tests use the real text chat/capture path, not microphone, ASR, TTS, or
robot motion.

## Jetson safety and verification

All inference phases ran sequentially in 15 W mode with an active fan. Start
gates require at least 2 GiB available RAM, temperature below 55°C, and no
resident model. The runtime watchdog retains the 768 MiB available-RAM floor,
512 MiB swap ceiling, 68°C temperature ceiling, and unchanged boot/trip checks.
No runtime safety guard fired, no reboot or thermal trip was observed, and
models were unloaded at each successful phase's end.

| Phase | Peak RAM | Peak swap | Peak temperature |
| --- | ---: | ---: | ---: |
| Final 12-case regression | 5,840 MB | 19 MB | 57.59°C |
| New 12-case wording | 5,896 MB | 25 MB | 58.38°C |
| Full adaptive | 6,484 MB | 141 MB | 59.28°C |
| Learn | 5,765 MB | 141 MB | 58.44°C |
| Fresh-process recall | 5,679 MB | 141 MB | 58.34°C |
| Travel diagnostic | 6,336 MB | 141 MB | 55.84°C |

The first development attempt exposed a schema/alias integration error and an
unfixed recall-answer perspective error. The second fixed those but still
withheld an unknown-fact answer for a spoken reserved citation reference. The
final regression includes the restored no-spoken-provenance instruction and
passes all 12. Failed development runs are retained, not counted as final
successes. Two start attempts were refused by the temperature gate before
inference; successful retries used new artifact directories after cooling.

Offline verification: **659 tests discovered, 633 passed, 26 opt-in live tests
skipped**. Targeted transport, citation, conflict, freshness, preference,
paraphrase, and temporal counterexamples pass. Selected fatal flake8 checks,
script compilation, and scoped whitespace checks pass. No user files were
reset, committed, or deleted by this revision.

Private owner-only raw artifacts are under
`/home/b2jetson/.local/share/oline-hri/evaluation-runs/reliability-*20260910*`.
Only fictional summaries are included in the repository report.
