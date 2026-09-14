# CLARA independent personal-memory retrieval experiment

Completed **864/864 attempts**: 856 delivered answers and eight retained resource-guard interruptions. SELECTIVE reduces unnecessary memory access, but its quality/time tradeoff depends on the generator. Answer quality was reviewed by independent blinded assistants; **human validation remains pending**.

The [full report](report_reviewed_v3/report.md), [paired category/component/device tables](report_reviewed_v3/tables.md), and [all delivered answers and failures](report_reviewed_v3/answers.md) contain the complete comparison. The [independent numerical audit](numeric_audit_v1/numeric_audit.json) passed **99,319 checks with zero discrepancies**. The [final report review](reviews/final_report_review_v1.json) passed another 181 checks.

## Findings

Each condition has 144 attempts: 48 requests repeated three times. Known recall covers 26 authorized questions, or 78 attempts. Unnecessary retrieval uses the 24 authorized general-question attempts as its denominator. Mean request time includes selection, failed attempts and every physical fragment's cold first load.

| Generator | Policy | All task successes | Known recall | Unnecessary retrieval | Mean request, s | Failures |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | OFF | 51/144 | 0/78 | 0/24 | 1.577 | 0 |
| qwen3:0.6b | ALWAYS PERMITTED | 93/144 | 53/78 | 24/24 | 1.941 | 0 |
| qwen3:0.6b | SELECTIVE | 91/144 | 53/78 | 6/24 | 2.030 | 0 |
| qwen3:1.7b | OFF | 63/144 | 0/78 | 0/24 | 7.380 | 1 |
| qwen3:1.7b | ALWAYS PERMITTED | 86/144 | 53/78 | 24/24 | 10.460 | 3 |
| qwen3:1.7b | SELECTIVE | 89/144 | 52/78 | 3/24 | 9.117 | 4 |

For **0.6B**, SELECTIVE preserves the same per-request mean known-recall success as ALWAYS on all 26 known questions and reduces unnecessary retrieval by **75%**. It loses two overall successes and is **0.089 s slower** per request (about 4.6%; descriptive 95% scenario interval +0.023 to +0.147 s). Selection averages 0.107 s, versus 0.010 s for ALWAYS. No complete-request time saving was observed.

For **1.7B**, SELECTIVE reduces unnecessary retrieval by **87.5%** and saves **1.342 s per request** on average (about 12.8%; interval −2.071 to −0.614 s), after paying 0.696 s mean selection cost. It has 52/78 known successes versus 53/78: one known question improves and two worsen after averaging repetitions. Overall success improves by three attempts, but p95 latency worsens from **20.657 to 30.457 s**. Quality preservation and uniformly faster responses are not established.

Both evidence policies achieve only **6/24 paraphrased-recall successes** for either generator. SELECTIVE succeeds on unknown/conflicting questions in 9/24 small-model and 6/24 large-model attempts, versus OFF's 21/24 and 23/24. No evidence condition demonstrates explicit conflict handling in the reviewed outputs. Direct recall and multi-fact questions are stronger: 21/24 and 23/24 respectively for both evidence policies and generators. These unfavorable findings remain part of the result.

Total retrieval attempts fall from 138 to 114 for 0.6B and from 138 to 111 for 1.7B. SELECTIVE makes 21 classifier calls per generator. Its memory-need sensitivity is 94.7%; specificity is 75.0% and 87.5%, respectively. Supplied relevant-evidence coverage is 76.3% in all four evidence conditions. Irrelevant records inspected fall from 3,060 to 2,514/2,445; irrelevant records supplied fall from 48 to 36 for each generator. Inspection sums unique eligible IDs within each attempt and is distinct from bounded candidates and generation evidence. Coverage is fact-occurrence-weighted; empty relevant-ID sets are undefined, and unknown personal lookups still count as needing memory.

Known-fact abstention is a missed personalization task. OFF achieves zero known recalls despite many cautious abstentions. Detailed tables separately report caution, unsupported claims, partial answers and rubric-prohibited content. The frozen `forbidden_disclosure` flag includes unrequested personal facts and forbidden assertions; it does not alone prove unauthorized store access. Audited authorization violations were zero.

## Frozen controls and collection

The [protocol](frozen_v1/protocol.md), [runtime fixtures](frozen_v1/runtime.json), [separate references/rubrics](frozen_v1/references.json), and [freeze manifest](frozen_v1/freeze.json) were independently reviewed and sealed before primary inference. The 48 fresh fictional requests have eight in each of the six requested categories and share eight fictional topic scenarios.

The prepared snapshot applies lifecycle changes before evaluation and is copied identically to each physical session. Consent, profile isolation, prohibited-data restrictions, correction/deletion, expiry and freshness remain active. Authorization is separate from relevance selection: OFF supplies no personal evidence, ALWAYS retrieves for every authorized request, and SELECTIVE uses the current memory-need policy. Fresh conversations and OFF input checks prevent facts entering through history or helpers. Scoring references never enter runtime inputs. Live before/after propagation remains separate.

The [adapter](../../scripts/independent_retrieval_adapter.py), [runner](../../scripts/run_independent_retrieval.py), [supervisor](../../scripts/independent_retrieval_supervisor.py), and [continuation utility](../../scripts/independent_retrieval_continuation.py) retain the condition's sole generator for classification, generation, helper rendering and fallback paths. Settings are context 2048, output cap 192, temperature 0, seed 42 and thinking disabled. Source, model defaults, embedding assets and configuration are frozen. Model digests:

| Model tag | SHA256 digest |
| --- | --- |
| qwen3:0.6b | 7df6b6e09427a769808717c0a93cadc4ae99ed4eb8bf5ca557c90846becea435 |
| qwen3:1.7b | 8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7 |

All **18 logical blocks** were covered across **26 physical fragments**. The [final manifest](run_v9/batch_finish.json) includes every prior fragment in order. Eight unchanged available-memory-floor interruptions were retained once and never retried. Request rows record `KeyboardInterrupt`; session summaries identify the underlying `SafetyGateError`. Each continuation was independently approved, sealed and limited to its exact unattempted suffix. All **35 rejected zero-request admissions** remain archived.

Existing guards required at least 2 GiB available memory and temperature below 55 °C at startup, at least 768 MiB and temperature below 68 °C during inference, active cooling and unchanged 15 W power mode, boot/trip counters and swap capacity. Inference was serialized with one resident model per physical fragment. No concurrent Jetson experiment or OS/service/power/swap change was introduced. The [independent final control audit](reviews/final_collection_preflight_review.json) verified 864 unique attempts, all 906 chat calls, frozen controls and clean eviction. Sustained 1.7B residency across uninterrupted 48-request blocks is not established.

The existing evidence helper rewrites two relationship questions in 24 calls; OFF retains original wording. This evidence-dependent behavior is reported without claiming semantic neutrality. An offline audit incorrectly required original wording verbatim. Its failed artifact is retained with the independently approved [audit-only correction](analysis_audit_correction_v1.md). No runtime input, observation, rubric or statistical rule changed. A separate renderer variable error is preserved in [report_reviewed_v1/failure.json](report_reviewed_v1/failure.json); the final report contains corrected source/provenance.

## Review and interpretation limits

Two fresh blinded assistant contexts reviewed all **159 exact question/outcome groups**. They agreed on 147; a third fresh blinded context adjudicated all 12 disagreements. Originals and adjudication were sealed before mapping was opened. [Mapping and semantic binding](reviews_verified_v1/review_agreement.json) cover all 864 attempts. Human validation is pending.

Paired analysis averages the three repetitions within each request and uses 10,000 bootstrap draws of all eight whole scenario clusters, seed 2026091399. Intervals are descriptive and conditional on this authored workload and these sessions. There is no declared noninferiority margin, population equivalence claim or deployment deadline. Policies occupy each within-model order position once; model order has a 2:1 asymmetry. Variable CPU/GPU placement, cold starts, background load, helper behavior and output lengths limit causal timing claims. GPU allocation fractions are not fractions of computation. Board energy includes background power and only available within-fragment telemetry intervals. Setup, cleanup, admission overhead, warm timing and between-collection gaps are reported separately without double counting.

## Reproduction and validation

Run from this repository root and choose a **new output directory** each time. The analysis, report, review and continuation directories also preserve exact commands and source provenance.

```bash
PYTHONPATH=scripts .venv/bin/python scripts/analyze_independent_retrieval.py \
  --freeze evaluation/independent_retrieval_20260913/frozen_v1 \
  --run evaluation/independent_retrieval_20260913/run_v9 \
  --reviews evaluation/independent_retrieval_20260913/review_resolution_v1/resolved_reviews.jsonl \
  --blind-seed-from evaluation/independent_retrieval_20260913/analysis_reviewed_v1/private/seed.json \
  --output /tmp/clara-independent-analysis-reproduction

PYTHONPATH=scripts .venv/bin/python scripts/report_independent_retrieval.py \
  --analysis evaluation/independent_retrieval_20260913/analysis_reviewed_v1 \
  --review-provenance evaluation/independent_retrieval_20260913/reviews_verified_v1/review_agreement.json \
  --output /tmp/clara-independent-report-reproduction

PYTHONPATH=scripts .venv/bin/python evaluation/independent_retrieval_20260913/independent_numeric_audit.py \
  --freeze evaluation/independent_retrieval_20260913/frozen_v1 \
  --run evaluation/independent_retrieval_20260913/run_v9 \
  --analysis evaluation/independent_retrieval_20260913/analysis_reviewed_v1 \
  --output /tmp/clara-independent-numeric-reproduction
```

The original live entry point is below. It refuses changed sources, model digests, device baseline or failed resource guards. A new study with a changed baseline requires a new prospective freeze. Archived one-use continuation approvals cannot be repurposed.

```bash
PYTHONPATH=src:scripts .venv/bin/python scripts/run_independent_retrieval.py collect \
  --freeze evaluation/independent_retrieval_20260913/frozen_v1 \
  --output /absolute/path/to/a/new-live-collection
```

Before primary inference, 37 focused harness/guard checks and a separate 12/12 live development smoke passed. The continuation harness passed 17 checks before use. Final analysis validation passed 24 tests, including prompt-audit regressions; review-batch and reconciliation checks are preserved in their independent preflight records. No primary question was replaced or rerun after an unfavorable answer or interruption.

Scientific artifacts use exclusive creation, SHA256 seals and read-only permissions. These resist accidental changes and are not privileged write-once storage. Earlier project results are preserved, including [documentation before the final update](documentation_before_final_v1/). The [completion archive](completion_v1/) preserves the final documentation and artifact inventory.
