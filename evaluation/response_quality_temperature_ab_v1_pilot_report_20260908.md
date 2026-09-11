# Response-quality temperature pilot — 2026-09-08

## Verdict

This pilot does not establish a generally better temperature. Temperature
`0.2` was preferred for the one reviewable general-recovery pair, while the
completed raw memory answers slightly favored temperature `0.0`; neither memory
arm produced an application-valid response. Keep the production default
unchanged until structured success is reliable and a multi-repetition run is
completed.

## Controlled setup

- Model: `qwen3:4b`, thinking disabled, paired seed `42`.
- Arms: temperature `0.0` versus `0.2`.
- Routing: fixed to each case's expected route.
- Evidence: exactly the evaluator-required memory IDs in manifest order.
- Scope: one synthetic repetition; this is a smoke pilot, not a variability
  estimate or a production router/retriever test.
- Review: candidate order was blinded and judgments were stored separately
  before opening each mapping key.

## Results

| Case/run | Temperature 0.0 | Temperature 0.2 | Blinded result |
| --- | --- | --- | --- |
| Offline database recovery, context/output `2048/256` | Valid response, 117.850 s | Valid response, 135.970 s | Candidate from `0.2` preferred, but both missed explicit detection and prevention rubric items |
| Temporal memory, initial `2048/256` | Truncated at 256 tokens, 194.016 s | Truncated at 256 tokens, 179.001 s | Tie: neither was reviewable |
| Temporal memory repair, `2176/320` | Backend completed 226 tokens, application rejected, 84.323 s | Backend completed 227 tokens, application rejected, 201.570 s | Tie: neither was application-valid |

The repaired memory prompts made the missing Friday correction timestamp visible
and both raw completions correctly ordered Friday before Saturday. Both models
nevertheless copied internal `mem_...` identifiers into `speech`, so the strict
privacy validator rejected them. No fallback to `qwen3:0.6b` was counted as a
4B result.

Latency is descriptive only. The 4B load took roughly 43–50 seconds per attempt,
and equal-length repair outputs had substantially different generation times;
the run did not control thermal state or warm residency.

## Changes prompted by the pilot

- Large-model timeouts can no longer fall back to 0.6B while being labeled as
  a 4B temperature-arm result.
- Blinded candidate position alternates instead of placing one arm first in
  every pair.
- Corrected memories expose a correction-only semantic effective timestamp,
  including its derived weekday, while ordinary validity/audit timestamps stay
  hidden.
- The reusable plan now reserves context/output `2176/320` for this pair.
- Model instructions explicitly keep IDs and citation commentary out of speech;
  strict output validation remains fail-closed.
- Review templates remain immutable; judgments are separate files keyed to the
  review-template SHA-256.

## Next decision gate

Do not increase repetitions yet. First make one memory pair reach 100%
application-valid structured output without weakening ID-leak protection. Then
run at least three paired seeds over several general and memory cases before
selecting a global or route-specific temperature.

## Artifacts

- Initial run: `/home/b2jetson/oline-hri-response-quality-ab-20260908`
  (`4b4602cce5f949429f7b4e20ef5bcc92`).
- Corrected memory retry:
  `/home/b2jetson/oline-hri-response-quality-ab-memory-retry-20260908`
  (`7535c2e5d9194c6194bcbcb21230d237`).
- Frozen judgments:
  `response_quality_temperature_ab_v1_pilot_20260908_blind_judgments.json` and
  `response_quality_temperature_ab_v1_memory_retry_20260908_blind_judgments.json`.
