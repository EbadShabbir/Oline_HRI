# Large no-memory response-speed v3 protocol — 2026-09-09

## Objective and rationale

Reduce latency without replacing the proven grounded-memory generator. V1
showed that `qwen3:1.7b` was materially faster but failed the recency case at
all three comparison seeds. V2's compact memory prompt revision then failed its
unseen recency gate. Those artifacts remain preserved and neither attempt
authorizes a global model replacement.

V3 narrows the candidate to the large, no-personal-memory route. Production
would use:

- `qwen3:0.6b` for routing and small answers;
- `qwen3:1.7b` only when `memory_required=false, model_size=large`; and
- the existing `qwen3:4b` when `memory_required=true, model_size=large`.

The general recovery instruction is task-neutral but now makes its completeness
contract explicit: stop/preserve, detect/assess, conditional local restore or
repair, no-backup salvage/rebuild or limits, validation, and prevention or
monitoring. The Target 1 memory instructions and generator remain unchanged.

## Frozen inputs

- Ollama `0.33.3`.
- Candidate `qwen3:1.7b`, list ID `8f68893c685c`.
- Retained grounded-large model `qwen3:4b`, list ID `359d7dd4bcda`.
- Router/small model `qwen3:0.6b`, list ID `7df6b6e09427`.
- Dataset byte SHA-256
  `fd046641e1b2839bfbcd98d8701f107cd030a18d5149963fe0fd405032d91c1d`.
- Case `route_large_no_memory_05` only.
- Unseen gate seed `52`; unseen comparison seeds `53`, `54`, and `55`.
- One repetition, fixed expected route, no supplied memory, temperature `0.2`,
  context/output `2176/320`, thinking off, and cold `keep_alive=0` lifecycle.

The unchanged temperature harness also collects a temperature-0 companion.
Only the temperature-0.2 output is the candidate; companion output is excluded
from selection.

The historical 4B temperature-0.2 baseline for this exact case uses Target 1
seeds 43–45: attempt-wall values `79.217`, `73.440`, and `75.516` seconds
(p50 `75.516`), and load values `44.686`, `43.704`, and `44.380` seconds
(p50 `44.380`). Reuse avoids new slow 4B calls but is non-contemporaneous and
uses different seeds.

## Execution and gate

1. Before inference, run the full offline suite, validate all four plans, hash
   protocol/plans/source/config/suite, and confirm no resident model or competing
   client.
2. Run seed 52 only. Continue only if the temperature-0.2 result is
   application-valid with `done_reason=stop`, no fallback/truncation/leak, and
   covers all six recovery components below without impossible claims.
3. Run seeds 53–55 sequentially after a no-resident-model check. Score after all
   three final shards; never pool a retry.
4. If selected, implement the three-model route, retain 4B for all large memory
   requests, update diagnostics/config/evaluation assumptions, run the full
   offline suite, then run focused production-adaptive live checks.

## Promotion rule

The temperature-0.2 candidate must have:

- a passing gate and 3/3 application-valid comparison responses;
- explicit stop/preserve, detection/assessment, conditional verified-local-
  backup repair/restore, local no-backup salvage/rebuild or stated limits,
  validation before resumption, and prevention/monitoring in every answer;
- no unsafe/impossible claim, fallback, truncation, memory/provenance leak, or
  missing normalization telemetry;
- cold attempt-wall p50 at most `45.310` seconds (60% of 4B p50); and
- cold load p50 at most `26.628` seconds (60% of 4B p50).

If any condition fails, do not add the route and retain the two-model baseline.
If selected, the default production configuration must still pass a live
no-memory recovery request on 1.7B and the existing temporal and recency memory
requests on 4B with exact citations.

## Limits and reporting

This is one synthetic recovery case across three candidate seeds, not a broad
quality or statistical claim. It does not show 1.7B is safe for personal-memory
reasoning. Host load, thermal state, and SD-card caching are not tightly
controlled. Report the rejected global-candidate trials, exact stage timing,
quality assessment, final route mapping, tests, and private artifact paths.
