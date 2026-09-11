# Response-quality temperature A/B v3.1 report — 2026-09-08

## Verdict

The v3.1 comparison did not identify a globally better generator temperature.
Both temperatures produced nine of nine application-valid outputs, but neither
satisfied the preregistered response-quality selection rule. The production
default therefore remains temperature `0.2` at context/output `2176/320`.

The seed-47 qualification gate passed: both answers were application-valid,
semantically correct, exactly cited, and tied. It is not part of the scored
nine-pair comparison.

## Blinded quality result

Two independent fresh-context reviewers received only the three anonymized
`paired_review.jsonl` files. They agreed on every correctness and preference
field. Their individual judgments and the unanimous resolutions were frozen,
with all three review-file SHA-256 hashes, before any mapping key, observation,
summary, raw output, telemetry, or timing was opened.

| Case | Temperature 0.0 | Temperature 0.2 | Resolved paired result |
| --- | ---: | ---: | --- |
| General offline recovery | 0/3 rubric-correct | 0/3 rubric-correct | 0.0 preferred in 3/3, but both candidates incorrect |
| Temporal correction memory | 3/3 correct, exact citations | 3/3 correct, exact citations | 3 ties |
| Recency/collaborator memory | 3/3 correct, exact citations | 3/3 correct, exact citations | 3 ties |
| Overall rubric correctness | 6/9 | 6/9 | 0.0: 3 wins; 0.2: 0 wins; 6 ties |
| Application validity | 9/9 | 9/9 | 18/18 combined |

Every recovery answer included isolation, restoration/repair, and validation
steps. Both reviewers nevertheless found all six incomplete against the frozen
five-part rubric: they did not distinctly explain corruption detection and did
not include an explicit prevention step. Temperature `0.0` gave the preferable
of the two incomplete plans at each seed, but that does not make either answer
correct.

The twelve memory outputs were semantically correct and used the exact required
citations. Within each memory pair, the two delivered responses were identical:

- the temporal answer states the Friday change to ginger tea, the Saturday
  navigation completion, and the correct later-event conclusion;
- the recency answer states both dated milestones, identifies navigation as
  newer, and names Theo as the collaborator.

## Selection-rule application

Both arms cleared the structural gate: all nine outputs were application-valid,
all six memory answers had exact supplied/used provenance, and no attempt had a
fallback, truncation, delivered-speech leak, or missing normalization telemetry.
However, a winner also needed at least two of three wins in every case and at
least six of nine wins overall. Neither temperature won a memory pair, and
temperature `0.0` won only three of nine overall. Both also had the same 6/9
rubric correctness.

The result is therefore **inconclusive**. Temperature `0.2` remains the default;
there is no route-specific or global temperature promotion from this test.

## Descriptive runtime data

Latency was excluded from the quality decision. The values below are
nearest-rank aggregates over nine cold calls per arm on the development Jetson.

| Metric | Temperature 0.0 | Temperature 0.2 |
| --- | ---: | ---: |
| Attempt wall p50 | 93.446 s | 75.516 s |
| Attempt wall p95 | 137.688 s | 119.522 s |
| Mean attempt wall | 93.409 s | 81.907 s |
| Total attempt wall | 840.682 s | 737.161 s |
| Output tokens p50 / p95 | 88 / 135 | 88 / 141 |
| Output tokens total | 910 | 925 |

The unscored gate took 63.022 seconds for temperature `0.0` and 60.542 seconds
for temperature `0.2`, with 83 output tokens each. Host, cold-load, and GPU
variation were not controlled tightly enough to infer a speed advantage from
these figures. Target 2 should run a latency-specific experiment from the
retained functional baseline.

## Integrity and safety audit

Across the gate and comparison there were 20 model attempts. Independent audit
confirmed:

- 20/20 application status `ok` and backend `done_reason=stop`;
- one successful `qwen3:4b` call per attempt with the planned seed/temperature;
- 14/14 memory attempts with exact required supplied and used IDs (the two gate
  attempts plus twelve comparison attempts);
- zero fallbacks, truncations, persistent-ID/alias/provenance leaks, and
  citation annotations removed;
- complete zero-valued normalization telemetry on every attempt;
- all outputs below the 320-token cap;
- 16/16 pre-manifest artifact hashes matching the four manifests;
- all frozen suite, configuration, source, and plan hashes matching the
  preregistration; and
- mode 0700 on all four private run directories and mode 0600 on all 20 run
  artifact files.

The seed-46 v3 failure remains preserved and excluded. V3.1 used a versioned
suite whose prompt explicitly requests the new preference value without naming
it, the same 600-second large-model failure budget for both arms, and arm-opaque
progress. The original v1 suite and failed-run artifacts were not overwritten.

Reviewer isolation and per-shard host isolation are supported by the
contemporaneous operator/tool transcript, frozen file hashes, timestamps, and
the recorded preflights; local artifacts cannot cryptographically prove access
history or the absence of every unobserved transient process. Normal desktop
activity and high but stable allocated swap were disclosed. No defined
infrastructure-invalidating event was observed.

## Reproducibility artifacts

- Frozen protocol: `response_quality_temperature_ab_v3_1_protocol.md`
- Versioned suite: `fictional_seven_day_v1_1.json`
- Gate judgments:
  `response_quality_temperature_ab_v3_1_memory_gate_seed47_20260908_blind_judgments.json`
- Comparison judgments:
  `response_quality_temperature_ab_v3_1_20260908_blind_judgments.json`
- Gate preflight: `response_quality_temperature_ab_v3_1_preflight_20260908.md`
- Shard preflights:
  `response_quality_temperature_ab_v3_1_shard_preflights_20260908.md`

Private immutable run directories and IDs:

| Run | Run ID | Paired-review SHA-256 |
| --- | --- | --- |
| Seed-47 gate | `f7d3054985b94ad48dc649fdc2a05918` | `e510ca8222377844d9fe3f34f03b8b0584ffe7ab4fc47f0501e51144d6aac360` |
| Seed 43 | `06ea983595b7406c9b2f81233b5faeb3` | `440fd0db32b71bee12ed625424b0ff11afc5479846704fc1b7dd6dde0d7eddb2` |
| Seed 44 | `48cdcccfa23b42d6a9da108c2fab0fc1` | `1e0a633b5ea774a0b528a010a16aeae7dc37172d9437835943b9c4b4e8d4acfc` |
| Seed 45 | `a84e17d547ec49deabb6e52038bf4aab` | `c5db828f3956edcf2326211e2e3dcc4dda9c91488564f1b76adf5d43ad17d60c` |

The directories are, respectively:

- `/home/b2jetson/oline-hri-response-quality-ab-v3_1-memory-gate-seed47-20260908`
- `/home/b2jetson/oline-hri-response-quality-ab-v3_1-seed43-20260908`
- `/home/b2jetson/oline-hri-response-quality-ab-v3_1-seed44-20260908`
- `/home/b2jetson/oline-hri-response-quality-ab-v3_1-seed45-20260908`

## Scope

This fixed-route, fixed-evidence experiment uses three synthetic cases, three
comparison seeds, and one repetition per seed. It isolates the generator
temperature; it does not measure adaptive routing, live retrieval, arbitrary
conversation quality, human preference, or statistical significance. It does
not resolve the broader 30-case suite's pending independent label/review status.

Target 1 is complete. Target 2 can now test response latency from the retained
temperature `0.2`, context/output `2176/320`, and 600-second functional failure
budget; no latency-driven setting was selected here.
