# Response-speed model comparison v2 protocol — 2026-09-09

## Status and objective

This protocol supersedes the candidate procedure in
`response_speed_model_ab_v1_protocol.md` without modifying it. The v1
`qwen3:1.7b` trial was fast but rejected: at both temperatures and all three
comparison seeds it reversed the 3 August/8 August recency ordering, omitted
the collaborator evidence selector, and failed application validation. Its
general recovery answers also omitted the explicitly required untouched copy.

V2 evaluates one compact, task-neutral instruction revision made in response:
answer every requested memory part; treat the later full date as newer; name
and cite a requested collaborator; and make the recovery completeness contract
explicit. Context/output remain `2176/320`. The production baseline remains
`qwen3:4b` at temperature `0.2`; no model change occurs before this protocol's
gate, comparison, and verification all pass.

## Frozen inputs and separation

- Ollama `0.33.3`.
- Baseline: `qwen3:4b`, list ID `359d7dd4bcda`.
- Candidate: `qwen3:1.7b`, list ID `8f68893c685c`.
- Router/small model: `qwen3:0.6b`, list ID `7df6b6e09427`.
- Dataset byte SHA-256:
  `fd046641e1b2839bfbcd98d8701f107cd030a18d5149963fe0fd405032d91c1d`.
- Unseen gate: `memory_large_recency`, seed `48`.
- Unseen comparison seeds: `49`, `50`, `51` over
  `route_large_no_memory_05`, `memory_large_temporal`, and
  `memory_large_recency`.
- One repetition, fixed expected route, fixed required evidence, temperature
  `0.2`, context `2176`, output cap `320`, thinking off, and cold
  `keep_alive=0` lifecycle.

The unchanged temperature experiment harness requires two arms. Each v2 shard
therefore collects an excluded temperature-0 companion; only temperature
`0.2` is the production candidate. Candidate output is not compared to its
companion for promotion.

The 4B latency reference is the retained, immutable Target 1 temperature-0.2
comparison: cold attempt-wall p50 `75.516` seconds and model-load p50 `44.721`
seconds over nine calls. It is historical and uses different seeds; this
non-contemporaneous comparison can support an engineering decision but not a
statistical model-performance claim.

## Execution

1. Before inference, run the complete offline test suite, validate all four v2
   plans, hash this protocol/plans/source/config/suite, and confirm no resident
   Ollama model or competing model client.
2. Run only seed 48. Continue only if the temperature-0.2 candidate is valid,
   correctly identifies navigation as newer than Luma, names Theo as the
   collaborator, cites exactly all three required records, and has no fallback,
   truncation, ID/alias/provenance leak, or missing normalization telemetry.
3. Run seeds 49–51 sequentially with a no-resident-model check before each.
   Score only after all three planned shards are final; never pool a retry.
4. If selected, change the production large-model pin/default, update historical
   evaluator assumptions without rewriting old evidence, run all offline tests,
   and run focused live routed checks using the production configuration.

## Promotion rule

Promote the temperature-0.2 `qwen3:1.7b` candidate only if:

- the gate passes every condition above;
- 9/9 comparison attempts are application-valid with `done_reason=stop`;
- all six memory answers are semantically correct with exact required
  supplied/used selectors;
- all three recovery answers explicitly cover stop/preserve, detection or
  assessment, conditional verified-backup restore or repair, a local no-backup
  salvage/rebuild contingency, validation before resumption, and prevention or
  monitoring, without impossible or unsafe claims;
- there are zero fallbacks, truncations, persistent-ID/alias/provenance leaks,
  or missing normalization fields;
- cold attempt-wall p50 is at most `45.310` seconds (60% of baseline); and
- cold load p50 is at most `26.833` seconds (60% of baseline).

Any failed condition retains `qwen3:4b`. A selected 1.7B default may still fall
back only to the resident 0.6B model on timeout under the existing policy.

## Limits and reporting

The three synthetic cases and three candidate seeds are a scoped regression,
not proof across arbitrary dialogue or a human preference study. Host load,
thermal state, and SD-card cache are not tightly controlled. The final report
must disclose the rejected v1 pilot, exact per-stage timing, quality review,
model/config/source hashes, production verification, and private artifact
locations. Raw prompts and responses stay in mode-0700 local directories with
mode-0600 artifacts.
