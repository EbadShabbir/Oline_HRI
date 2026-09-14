# Step 4: final quality, latency and cost analysis

Completed 2026-09-12 using the existing 432 attempts from the revised Step 3
comparison. No models were run and no answers were re-scored. Because no
explicit Step 4 definition was saved in the project notes, this analysis-and-
figures scope was stated as the working interpretation while clarification
was requested. Memory ablations and integrated spoken testing remain separate.

The [report](artifacts_v2/report.md) combines descriptive deadline curves,
quality/time points, all three timing rounds, loading cost, and sampled
whole-device energy. The [numeric summary](artifacts_v2/summary.json) contains
paired outcomes and energy-coverage details.

| Correct deliveries by deadline | Small-only | Large-only | Cascade |
| --- | ---: | ---: | ---: |
| 5 seconds | 42/144 | 11/144 | 20/144 |
| 10 seconds | 42/144 | 32/144 | 43/144 |
| 15 seconds | 42/144 | 39/144 | 46/144 |
| 30 seconds | 42/144 | 44/144 | 46/144 |

The deadline values are descriptive coordinates selected after collection,
not application acceptance requirements. All attempts, including failures,
remain in the denominator. These are 48 distinct items across 41 scenarios,
repeated three times per system; assistant grading and repeated observations
do not constitute independent human validation or independent quality samples.

Small-only provides more correct answers quickly. Cascade eventually gains
four successes over small-only across 144 attempts, but takes 3.85 times its
mean request time. Cascade's pooled mean is lower than large-only, while the
per-round ordering reverses twice and CPU/GPU allocation varies. Only 3/144
cascade generations use small. The results do not establish a causal adaptive-
selection advantage or a requirement-level feasible winner.

## Figures and data

- Deadline curves: [PDF](artifacts_v2/deadline_curves.pdf),
  [SVG](artifacts_v2/deadline_curves.svg), [PNG](artifacts_v2/deadline_curves.png),
  [CSV](artifacts_v2/deadline_curves.csv).
- Quality/time and repeated rounds: [PDF](artifacts_v2/quality_latency_rounds.pdf),
  [SVG](artifacts_v2/quality_latency_rounds.svg),
  [PNG](artifacts_v2/quality_latency_rounds.png),
  [round data](artifacts_v2/repetitions.csv).
- [Deadline readouts](artifacts_v2/deadline_readouts.csv),
  [analysis provenance](artifacts_v2/provenance.json),
  [independent check](independent_metrics.json), and
  [independent check script](independent_metrics.py).

Quality comes from resolved `semantic_review.review_opinions`, joined through
`blinded_mapping.jsonl`. The old `row_metrics.semantic_quality` field still has
a pending placeholder and is deliberately ignored. Both analyses verify the
mapping/worksheet hashes, all 432 assignments, all curve points and reported
totals. The original Step 3 artifacts are unchanged.

The plots use Matplotlib in a separate temporary virtual environment. The
recorded plotting Python/packages differ from CLARA's inference environment;
they affect only offline analysis. The first render in `artifacts_v1` failed
on an output-metadata name collision after input validation; its partial files
and source are preserved. `artifacts_v2` is the complete, checked output.

## Reproduction

Use a separate Python environment with the plotting versions saved in
`artifacts_v2/provenance.json`. Choose a new output directory:

```bash
python evaluation/final_tradeoff_analysis_20260912/analyze_tradeoffs.py \
  --output-dir /absolute/path/to/a/new/report

python evaluation/final_tradeoff_analysis_20260912/independent_metrics.py \
  --output /absolute/path/to/a/new/audit.json
```

The analysis script checks the completed Step 3 analysis hash and review
provenance, generates figures through Matplotlib, and archives its source,
input/output hashes, plot data and package versions. It does not load a model,
open the personal memory database, or alter device configuration.
Invoke the main script from the repository root as shown above. Its archived
copy preserves the exact source; it expects the original relative data layout.
