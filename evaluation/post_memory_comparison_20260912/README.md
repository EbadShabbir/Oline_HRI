# Step 3: fresh comparison after routing and memory fixes

## Completed revised comparison: v2

The user-authorized revised swap allowance allowed **all nine sessions and
432 attempts** to finish on 2026-09-12. There are 48 distinct requests repeated
three times for each system. Large-only ran first, followed by cascade and
small-only; the other rounds rotated this order. The completed comparison
supersedes the collection status of the earlier attempts documented below.
No v1 answers are pooled into v2.

| System | Delivered / attempted | Full-rubric success | Mean / median / p95, s |
| --- | ---: | ---: | --- |
| `qwen3:0.6b` alone | 135/144 | 42/144 (29.2%) | 2.314 / 2.090 / 3.270 |
| `qwen3:1.7b` alone | 139/144 | 44/144 (30.6%) | 11.255 / 8.955 / 25.430 |
| CLARA lightweight cascade | 140/144 | 46/144 (31.9%) | 8.916 / 7.749 / 18.772 |

These are full text-response timings, including failed attempts and cold loads,
not microphone-to-speaker timings. Quality is assistant-assessed against the
frozen semantic rubrics, with appropriate abstention counted only when called
for. Two blinded assistant reviewers initially agreed on 142/145 unique output
groups. A third assistant resolved three flag disagreements and one additional
shared grounding error. All 432 attempts are graded; independent human review
remains pending. The 48 requests, repetitions and shared scenarios are dependent.
This is an exploratory repeat of a partly observed assistant-authored workload,
not a public benchmark or an independent confirmatory test.

**The results do not yet justify the cascade.** It used the small generator on
only 3/144 requests and the large generator on 141/144. Its pooled mean was
20.8% below large-only, but large-only was faster in rounds 2 and 3; measured
CPU/GPU placement differed substantially. The cascade took 3.85 times the
small-only mean request time while adding four successes across the 144
attempts. All three achieved zero full-rubric successes on temporal/synthesis
requests. No quality or response deadline was selected, so requirement-level
feasibility remains unestablished. See [results.md](../../results.md) for the
category comparison, interpretation and historical context.

The v2 guard allowed 3554.164 MiB of logical swap usage, reserving 256 MiB of
the existing 3810.164 MiB capacity. **No swap device or OS setting was changed.**
RAM and temperature guards stayed active. Existing zram occupancy is logical
usage of compressed pages in physical RAM; it is neither extra physical RAM
nor a measure of active swapping. The final audit found no resident model and
unchanged swap topology/capacity, power mode, boot, thermal-trip counters,
source, model metadata and Ollama version. Original experiment ceilings remain
unchanged; the revised process-scoped allowance ended when the processes exited.

The initial v2 batch completed two sessions, then stopped on a zero-request
temperature rejection. A separately recorded continuation retained those exact
sessions and completed the other seven. Its scheduler waited below 54°C before
handoff to the frozen below-55°C gate. No answered request was retried or spliced.
Two archived offline analyzer adapters recognize the exact frozen swap policy
and prove the revised temperature-error wording represents a zero-request
rejection. They preserve original findings and change neither runtime nor
scoring. Final collection and integrity checks passed. Offline validation before
the freeze reported 871 passed, 26 skipped and no failures/errors (897 tests).

Completed evidence:

- [Full tables, timing distributions, placement and resources](report_v2/tables.md),
  [numeric summary](report_v2/summary.json), and [renderer provenance](report_v2/provenance.json).
- [Reviewed analysis](analysis_v2_reviewed/analysis.json),
  [analysis-only compatibility corrections](analysis_v2_reviewed/analysis_compatibility_correction.json),
  and [descriptive quality/deadline data](analysis_v2_reviewed/deadline_quality_curve.json).
- [Initial review agreement and adjudication provenance](reviews_v2/review_agreement_v2.json).
- [Frozen protocol](frozen_v2/protocol.md), [workload](frozen_v2/workload.json),
  [source/model/configuration freeze](frozen_v2/freeze.json), and
  [offline validation](offline_validation_v2.json).
- [Original v2 terminal record](run_v2/batch_finish.json),
  [continuation origin](run_v2_resumed/resume_origin.json),
  [completed batch](run_v2_resumed/batch_finish.json), and
  [final host/configuration audit](final_state_v2.json).

To regenerate the completed analysis, use the matching frozen source and
installed artifacts, preserve the private blinding seed, and choose **new**
output directories. The following performs offline analysis only:

```bash
.venv/bin/python evaluation/post_memory_comparison_20260912/analyze_v2_resumed.py \
  --workload evaluation/post_memory_comparison_20260912/frozen_v2/workload.json \
  --freeze evaluation/post_memory_comparison_20260912/frozen_v2/freeze.json \
  --run-root evaluation/post_memory_comparison_20260912/run_v2_resumed \
  --output-dir /absolute/path/to/a/new/analysis \
  --blind-seed-from evaluation/post_memory_comparison_20260912/reviews_v2/private_seed.json \
  --reviews evaluation/post_memory_comparison_20260912/reviews_v2/resolved_cohort1_final.jsonl \
  --reviews evaluation/post_memory_comparison_20260912/reviews_v2/resolved_cohort2.jsonl \
  --reviews evaluation/post_memory_comparison_20260912/reviews_v2/resolved_cohort3.jsonl \
  --reviews evaluation/post_memory_comparison_20260912/reviews_v2/resolved_cohort4.jsonl \
  --reviews evaluation/post_memory_comparison_20260912/reviews_v2/resolved_cohort5.jsonl \
  --reviews evaluation/post_memory_comparison_20260912/reviews_v2/resolved_cohort6.jsonl

.venv/bin/python evaluation/post_memory_comparison_20260912/render_v2_report.py \
  --analysis-dir /absolute/path/to/the/new/analysis \
  --output-dir /absolute/path/to/a/new/report
```

For a separately labeled new live experiment, the frozen v2 batch runner
accepts the same `--workload` and `--freeze` paths with a new `--output-root`.
The original raw observations and all earlier archives must remain intact.

## Historical v1 attempt: restricted swap ceiling

Live collection ran on 2026-09-12 using the immutable
[prospective freeze](frozen_v1/freeze.json), but the comparison is **incomplete**:
48 of 432 planned attempts ran. Small-only finished its first 48-request
session; residual swap blocked the next session after the predeclared ten-minute
recovery window. Large-only and cascade were never started.

A subsequent [user-requested large-only attempt](large_only_20260912T120926Z/README.md)
also stopped before inference: 988 MiB swap exceeded the same 768 MiB startup
limit, while available RAM and temperature passed. It attempted zero requests,
so the result counts below are unchanged.

The [full tables](results_reviewed/tables.md) and
[reviewed analysis](results_reviewed/report.md) preserve all outcomes.
Small-only delivered 45/48 answers and achieved 14/48 full-rubric successes
(29.2%): 11 complete answers and three appropriate abstentions. Two assistant
reviewers agreed on every judgment; independent human review is pending.
Mean/median/p95 request times were 2.416/2.159/3.322 seconds, including the cold
first request and all three failures. This does not establish a cascade benefit.

The [terminal batch record](run_v1/batch_finish.json) records final swap of
988.5 MiB against the unchanged 768 MiB startup gate, with available RAM
2390.996 MiB and maximum temperature 52.437°C. No models remained resident;
boot, power mode and thermal-trip counters were preserved. The
[31 recovery checks](run_v1/startup_waits.json) and [collection log](collection_v1.log)
retain the interruption. Eight sessions and 384 requests remain unattempted.

The comparison includes true small-only and large-only systems with the same
policy-first memory decision used by the lightweight cascade. A fixed system
classifies ambiguous memory requests only on its sole model, never makes a
compute-classifier call, and uses that same model to render composed answers.
The cascade retains its router state and active model across requests. All
systems share the updated memory retrieval, evidence checks and answer helpers.

The [protocol](frozen_v1/protocol.md) fixes the systems, budgets, chronology,
device limits, failure accounting and scoring before outputs. The
[48-request workload](frozen_v1/workload.json) and
[workload notes](workload_notes.md) describe the new fictional snapshot and
rubrics. This is an assistant-authored application pilot, with independent
human review pending. It complements the earlier public ARC component results;
it is not a public benchmark or a confirmatory superiority test. It also differs
from the live-memory ablation named Stage 3 in the broader research draft.

## Validation and preservation

The final offline suite reported **888 tests: 862 passed, 26 skipped**, with
zero failures or errors, in 45.702 seconds. All live-test flags were disabled.
The [validation record](offline_validation.json) hashes 112 source, configuration,
script and test files; the [test log](unittest.log) is preserved. Tests exercise
the actual runner, Conversation, client and analyzer through fake HTTP, including
both classifier paths, fixed-model enforcement, cascade state, interrupted
requests and immutable output boundaries. Simulated responses are not quality
or latency observations.

Before these comparison changes, all 105 files in step 2's validation map were
verified and copied into [step2_validated_source](step2_validated_source/archive_manifest.json).
The new freeze separately archives 40 runtime/orchestration/analysis files,
the protocol, workload and validation record. The earlier source archives,
benchmark runs, scores and development replay remain intact.

The fresh [zero-inference preflight](preflight_20260912T113930365986Z/finish.json)
passed the existing startup limits: approximately 2.9 GiB available RAM,
743.25 MiB swap and maximum temperature 52.343°C at its finish, with no models
resident. Its earlier sandbox-restricted attempt is preserved separately.
Actual sessions recheck admission, guard embedding/model execution and verify
cleanup. No system configuration is changed to make an arm pass.

## Historical v1 reproduction (requires matching archived source)

Use the frozen workload and matching source/model/runtime configuration. The
commands require new output directories; reruns are separate experiments and
must not replace `run_v1` or be spliced into its interrupted sessions.

```bash
PYTHONPATH=src:scripts .venv/bin/python scripts/run_post_memory_batch.py \
  --workload evaluation/post_memory_comparison_20260912/frozen_v1/workload.json \
  --freeze evaluation/post_memory_comparison_20260912/frozen_v1/freeze.json \
  --output-root /absolute/path/to/a/new/run

PYTHONPATH=src:scripts .venv/bin/python scripts/analyze_post_memory_comparison.py \
  --workload evaluation/post_memory_comparison_20260912/frozen_v1/workload.json \
  --freeze evaluation/post_memory_comparison_20260912/frozen_v1/freeze.json \
  --run-root /absolute/path/to/the/run \
  --output-dir /absolute/path/to/a/new/analysis
```

Review sheets hide explicit arm, timing and repetition. Record assistant versus
human judgments, disagreements and missing coverage. Valid JSON, citation checks
and lexical matches are not semantic correctness. Fast failures are not useful
responses; any cascade advantage must be supported by paired observed answers
and measured costs, including model transitions.
