# Response-speed model comparison v1 protocol — 2026-09-09

## Objective

Reduce cold response latency on the development Jetson without weakening the
structured response, memory-provenance, or answer-quality behavior established
by the Target 1 temperature comparison. The production baseline is
`qwen3:4b` at temperature `0.2`, context/output `2176/320`, and a 600-second
large-request failure budget. The candidate is `qwen3:1.7b` with every other
setting held fixed.

The experiment targets the selected large-generator call. Existing router-only
data put two-call routing p50 below one second, while the retained Target 1
`qwen3:4b` temperature-0.2 calls spent 43.704–51.533 seconds loading the model
before prompt evaluation or generation. Routing changes are therefore outside
this comparison.

## Frozen inputs

- Ollama: `0.33.3`.
- Baseline tag/list ID: `qwen3:4b` / `359d7dd4bcda`.
- Candidate tag/list ID: `qwen3:1.7b` / `8f68893c685c`.
- Router/small tag/list ID: `qwen3:0.6b` / `7df6b6e09427`.
- Dataset: `fictional_seven_day_v1_1.json`, byte SHA-256
  `fd046641e1b2839bfbcd98d8701f107cd030a18d5149963fe0fd405032d91c1d`.
- Cases: `route_large_no_memory_05`, `memory_large_temporal`, and
  `memory_large_recency`.
- Seeds: qualification gate `47`; comparison shards `43`, `44`, and `45`.
- Fixed routing and evaluator-required evidence; one repetition per seed.
- Temperature `0.2`, context length `2176`, output cap `320`, and thinking off.
- Cold model lifecycle: peer unloaded first and candidate `keep_alive=0`.

The existing temperature experiment runner is reused without changing its
source. It requires two temperature arms, so each candidate-model shard also
collects a temperature-0 companion. Only the `0.2` arm is the Target 2
candidate; the companion is excluded from the promotion decision.

The retained baseline is the temperature-0.2 arm in the immutable Target 1
seed-47 gate and seed-43/44/45 run directories listed in
`response_quality_temperature_ab_v3_1_report_20260908.md`. It is reused rather
than rerun to avoid twelve additional slow 4B calls. This makes the latency
comparison historical/non-contemporaneous, a limitation that must be stated.

## Execution order

1. Record model IDs, free memory/swap, no resident Ollama model, and absence of
   competing model clients.
2. Run only the seed-47 candidate gate and inspect it after completion.
3. Continue only if the temperature-0.2 candidate is application-valid,
   `done_reason=stop`, answers the temporal case correctly, cites exactly the
   required IDs, and has no fallback, truncation, alias/ID leak, or missing
   normalization telemetry.
4. Run candidate comparison shards 43, 44, and 45 sequentially, checking host
   isolation before each shard. Do not pool failed or retried attempts.
5. Score only after all planned candidate shards finish.

## Promotion rule

Promote `qwen3:1.7b` as the production large generator only if all conditions
hold for its temperature-0.2 arm:

- gate passes every condition above;
- 9/9 comparison attempts are application-valid with `done_reason=stop`;
- all six comparison memory answers are semantically correct and use exactly
  the required citations;
- each general-recovery answer retains the baseline's three established rubric
  components: stop/preserve, a feasible repair-or-restore path, and validation
  before normal use; it must not introduce an unsafe or impossible claim;
- zero fallbacks, truncations, persistent-ID/alias/provenance leaks, and zero
  missing normalization-telemetry fields;
- cold attempt-wall p50 is at most 60% of the retained baseline p50
  (45.310 seconds versus baseline 75.516 seconds); and
- cold model-load p50 is at most 60% of the retained baseline p50
  (26.833 seconds versus baseline 44.721 seconds).

If any condition fails, retain `qwen3:4b`. Latency is descriptive beyond these
thresholds; three seeds do not establish statistical significance or every
interactive workload. Any promoted default still needs the complete offline
test suite and focused live routed-chat verification before Target 2 closes.

## Reporting

The final report must publish per-case validity, semantic/citation checks,
attempt/load/prompt/generation timing, exact model provenance, the promotion
decision, test results, and limitations. Raw candidate artifacts remain in
owner-only local directories because they contain prompts and responses.
