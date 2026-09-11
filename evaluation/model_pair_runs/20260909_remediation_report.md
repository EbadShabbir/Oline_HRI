# Qwen-pair remediation and memory retest — 2026-09-09

Follow-up: [2026-09-10 memory-evidence improvements](./20260910_memory_evidence_report.md).
The results below remain the original remediation baseline.

## Outcome

The targeted fixes are implemented and tested on the Jetson Orin Nano 8 GB.
Keep `qwen3:0.6b` for routing/small answers and `qwen3:1.7b` for both large
roles, with a 2,048-token context, **192 output tokens**, temperature 0,
thinking off, and an 80-word speech limit. Inference remains serialized.

The tested routing errors, 128-token truncation failures, and Luma validator
false rejection are resolved. This is still a guarded development configuration,
not a reliable unrestricted personalized assistant: the full run delivered
22/30 structured answers, withheld eight, and retained general factual errors.
Persistence passed, but fresh-process recall still answered only 3/7 known-fact
questions correctly. No crash or recorded safety-limit breach occurred.

Machine-readable evidence: [20260909_remediation_results.json](./20260909_remediation_results.json).
Baseline: [previous full-memory validation](./20260909_full_memory_validation.md).

## Changes applied

- Hybrid routing: bounded rules override clear general/personal memory intent
  and explicit comparison/synthesis workload. Ambiguous and retained-history
  cases still use the classifier. Raw model decisions and policy provenance
  are saved separately; model output is not rewritten to make scores look better.
- Output allowance increased from 128 to 192, with consistent 80-word speech
  instructions. Redundant memory instructions were shortened to preserve room
  for mandatory evidence inside the unchanged context window.
- Named/called values are recognized as memory-coverage anchors. The correct
  Luma answer now passes without repeating its unrelated kickoff date; a wrong
  project name is still rejected.
- An independent gate blocks retrieval and substitutes fixed refusals for
  recognized credential, hot-microphone third-party, and unconfirmed-affect
  recall. Citation, conflict, temporal, and relationship checks remain active.
- Evaluation provenance/scoring and regression tests cover the new policies.
  A sequential validation harness records configuration, source hashes,
  model calls, isolated memory, and guarded Jetson telemetry.

Both classifier calls still run. No larger model, larger context, decoding
retry, or speed optimization was introduced. The privacy patterns are bounded
recognizers, not a complete natural-language privacy classifier.

## Full adaptive run

Run ID: `de98105a9ab94f1b989cf9a4d30414c2`.
Same 30-case fictional seven-day fixture, one repetition, seed 42, real BGE
embeddings and SQLite hybrid retrieval. All 16 component-retrieval records and
30 cascade records were collected. The fixture is development/regression
evidence; the new rules were informed by its failures, so this is not an unseen
accuracy estimate.

| Metric | Previous 128-token run | Retest |
| --- | ---: | ---: |
| Final memory-intent accuracy | 19/30 | 30/30 |
| Final model-size accuracy | 28/30 | 30/30 |
| Final joint route accuracy | 19/30 | 30/30 |
| Structured application responses | 23/30 | 22/30 |
| Validation failures / withheld answers | 7 | 8 |
| Truncated responses | 3 | 0 |
| Context-overflow failures | 0 | 0 |
| Timeout/fallback events | 0 | 0 |
| Component retrieval recall@3 | 81.82% | 81.82% |
| End-to-end p50 / p95 | 2.688 / 54.236 s | 2.666 / 54.162 s |
| Routing p50 / p95 | 0.856 / 10.932 s | 0.885 / 10.667 s |

The raw, unmodified classifier scored 19/30 for memory, 29/30 for size, and
19/30 jointly in this retest. The 30/30 scores belong to the **hybrid application
router**, not an improved or fine-tuned 0.6B model. All five prior general-query
false-positive routes and all six missed memory routes were corrected.

Structured success decreased because previously skipped grounded requests now
reach retrieval/generation and fail evidence checks. That is a detected failure,
not a successful answer. The Luma answer is accepted; the Sunday train question
now retrieves memory but its otherwise correct raw claim includes unrelated
citations and is withheld. All four complex personal synthesis cases still fail.
The three privacy cases invoke no retrieval and return no memory citations.

Only 13/25 supplied memory records match gold evidence (52% micro precision).
Accepted citations score 4/4 precision but only 4/18 recall; neither number
establishes overall answer correctness. There were no forbidden-ID retrieval
hits. Actual generation calls: 19 small and 11 large.

Latency is effectively unchanged at these sample sizes; no speed gain is
claimed. Serialized model reloads contribute to the long tail. The complete
adaptive telemetry interval lasted 612.90 seconds, versus 476.66 seconds for
the earlier run with fewer large grounded requests.

### Diagnostic answer review

This is an assistant rubric audit, not an independent blinded human review.
The formal quality sheet remains `pending_blinded_human_review`. Strict review
finds 15 complete answers, three partial answers, four incorrect/incomplete
answers, and eight withheld answers. Per-case judgments are saved in the JSON.

| Cases | Assessment |
| --- | --- |
| 1–6, 12, 15, 16, 18, 21–25 | Complete: general basics, recovery plan, supported direct facts, or appropriate abstention |
| 9, 10, 13 | Partial: missing concrete rollback criteria, stale-read interleaving, or meaningful context/safety tradeoffs |
| 7, 8, 11, 14 | Incorrect/incomplete: cosine magnitude claim, SQLite ACID claim, weak ranking comparison, or non-actionable release plan |
| 17 | Withheld: supported relationship fact fails the validator's user-perspective/binding requirement |
| 19, 26 | Withheld: fabricated location or unacknowledged conflicting lab evidence |
| 20, 27, 30 | Withheld: citations to unrelated supplied records; synthesis also omits or invents details |
| 28, 29 | Withheld: missing required evidence/citations and incorrect temporal reasoning |

No unsupported personal claim or unrelated personal disclosure was observed
in the delivered answers on this fixture. General factual errors remain: for
example, the SQLite comparison incorrectly says SQLite lacks ACID compliance.
Consequently, valid JSON and the absence of personal-data leakage are not
evidence of fully correct answers.

## Focused truncation and context checks

Three previously truncating general prompts were run five times each, with
generator seeds 42–46 and router seed 42. All 15 returned application-valid
responses with no truncation; the largest generated output was 123 tokens.
Some wording varied even at temperature 0. The incorrect SQLite claim persisted
in all five repeats: this test verifies completion, not semantic correctness.

Four grounded synthesis probes followed sequentially. Three reached generation
and failed validation; the timeline probe exposed a context-budget regression
before generation. Together the focused run made 18 generator calls, none
truncated. It was a pre-final prompt revision, not a second final benchmark.

The timeline regression was fixed before the full adaptive run by shortening
redundant response instructions. Its actual three-record prompt estimate fell
from 1,755 to 1,725 tokens, within the 1,728-token input budget at 2048/192.
All four final synthesis cases then reached generation without context errors.
Offline packing checks preserve all three required recency records at 192;
256 also fits that recency example but not the live timeline envelope. The cap
therefore remains 192 rather than expanding the context or dropping evidence.

## Automatic memory and process restart

The learn process (PID 48174) and fresh recall process (PID 48311) used the
same isolated owner-only database, not the user's personal database.

| Check | Result |
| --- | ---: |
| Disclosure capture status | 10/10 correct |
| Stored records | 7 |
| Memory-kind classification | 6/7 correct; plant fact labeled event |
| Same-process recall | 3/3 correct |
| Records after fresh-process recall | Same seven records, unchanged |
| Fresh-process known-fact recall | 3/7 correct |
| Unknown-information abstention | 2/2 correct |
| Overall fresh-process expectations | 5/9 correct; unchanged from baseline |

Tea, meeting time, and Maya's relationship were recalled correctly. Bicycle and
completed-test questions incorrectly abstained despite stored facts. Plant and
answer-length responses were rejected for unrelated citations. All nine final
routes requested memory, so these failures cannot be attributed simply to
memory-intent routing. Some capture acknowledgments also retained first-person
echoes of the human's disclosure.

## Device safety and offline verification

All live phases ran sequentially in 15 W mode with an active fan. No model was
downloaded, no 4B model was loaded, and no two LLMs were intentionally resident
together. Each phase finished with no resident models, no guard violation, the
same boot ID, and all thermal-trip counters zero.

| Phase | Samples | Duration | Peak RAM | Peak swap | Peak temperature |
| --- | ---: | ---: | ---: | ---: | ---: |
| Focus | 2,174 | 1,102.83 s | 6,579 MB | 369 MB | 56.50 °C |
| Adaptive | 1,209 | 612.90 s | 6,649 MB | 392 MB | 58.97 °C |
| Learn | 77 | 38.51 s | 5,774 MB | 392 MB | 57.50 °C |
| Fresh recall | 64 | 31.90 s | 5,697 MB | 392 MB | 56.72 °C |

Runtime stops remained: below 768 MiB available RAM, above 512 MiB swap,
temperature at/above 68 °C, changed boot/trip state, or failed telemetry.
Start checks required at least 2 GiB available, temperature below 55 °C, an
active fan, no resident model, and 15 W mode. Pair phases required swap at/below
384 MiB. Restart phases started with background swap above that pair gate and
were explicitly restricted to the 0.6B model, with a 512 MiB start ceiling;
large-model requests were prohibited. This is recorded in `workload.json`.
These are validation-harness safeguards, not newly installed production
monitoring. Measured stability does not guarantee safety under other workloads.

Final offline discovery: **608 passed, 26 opt-in live tests skipped**, 634 total,
29.217 seconds. Seven remediation test methods include table-driven routing,
near-miss/history, privacy, Luma/wrong-name, context packing, and provenance
regressions. Python compilation, runtime-error-only Flake8 checks, and
`git diff --check` passed; full style-lint cleanliness is not claimed.

## Stored evidence and limitations

Raw fictional prompts, responses, citations, source hashes, and telemetry are
in private directories under
`/home/b2jetson/.local/share/oline-hri/evaluation-runs/`:

- `remediation-focus-20260909`
- `remediation-adaptive-20260909`
- `remediation-learn-20260909`
- `remediation-recall-20260909`
- `remediation-memory-20260909` (persistent database and learn/recall transcripts)

The linked JSON contains artifact SHA-256 values and exact objective metrics.
Repository and packaged defaults have the same file SHA-256:
`ec44f88b0393c4dcc5465bd5bc0e4e042d49500a7f00aadc1e56422a6d08c3c9`.
An initial workspace-local attempt stopped before inference because its
group-writable directory ancestry failed the memory store's security check;
the successful runs used private directories instead.

A final small privacy-rule change exempts general definitions of unconfirmed
affect inference. The adaptive process had already imported its routing code.
Replaying all retained raw classifier/generator outputs with final source
reproduced all 30 final decisions, gate outcomes, accepted responses, and
validation errors exactly. This replay and the final offline suite verify the
change; it is not presented as another live run.

The next reliability work is request-linked retrieval/reranking, evidence
coverage and citation selection, then supported fact rendering/relationship
perspective and synthesis quality. Retest on held-out paraphrases and new
memories before trusting unrestricted personalization. Do not remove grounding
validators merely to increase the structured-success count.

Microphone capture, STT, TTS, and physical gestures were not exercised. These
results cover the text conversation, capture, retrieval, persistence, and
generation path only; no end-to-end spoken-system success is claimed.
