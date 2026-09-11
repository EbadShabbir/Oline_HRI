# Response-quality temperature A/B pilot v1

This is a synthetic, paired pilot for one question: with every other declared
generation setting held fixed, does temperature `0.0` or `0.2` produce the
better response? It is separate from the frozen Step 16 benchmark and is not a
user study.

## Isolation and scope

The default plan uses exactly two large-model cases:

- `route_large_no_memory_05`, a general database-recovery response.
- `memory_large_temporal`, a chronological comparison grounded in two personal
  memories, including a corrected preference.

It fixes the expected route for each case and supplies exactly the case's
`required_ids`, in manifest order, from one fixed-clock memory-store snapshot.
This is intentional: current production BGE top-3 retrieval misses at least one
required record for every large-memory manifest case, so adaptive retrieval
would confound the temperature comparison. The pilot therefore tests generation
only; it does not measure router or retriever quality. Run production-adaptive
verification later as a separate experiment and do not combine its results with
this pilot.

The otherwise attractive three-memory `memory_large_personal_plan` case is not
used here because its required evidence plus current production safety envelope
does not fit the 2176-context/320-output guard (1772 prompt tokens required;
1728 available). That prompt-fit gap should be investigated independently, not
turned into an A/B failure.

Both arms use context length 2176, output cap 320, thinking disabled, and paired
seed 42. The memory fixture is materialized once, one Ollama client is shared,
and every attempt starts a fresh conversation. The attempt order is balanced
AB/BA across the two cases. One repetition is only a smoke/pilot result, not an
estimate of variability.

## Commands

Validate the checked-in plan without running inference:

```bash
PYTHONPATH=src .venv/bin/python -m oline_hri.evaluation_experiment validate
```

Create a new absolute, owner-only directory for each run, then run the pilot:

```bash
mkdir -m 700 /absolute/path/to/new-temperature-ab-run
PYTHONPATH=src .venv/bin/python -m oline_hri.evaluation_experiment run --output-dir /absolute/path/to/new-temperature-ab-run
```

Do not run competing inference workloads during a timed run. The runner refuses
relative, non-private, symlinked, or pre-existing artifact destinations.

## Artifacts and review

- `observations.jsonl`: canonical header, per-attempt route/evidence/response,
  sampling parameters, timings, and end record.
- `summary.json`: objective completeness, structured success, routing/evidence
  exactness, token counts, and latency distributions. It deliberately does not
  declare a quality winner.
- `paired_review.jsonl`: immutable blinded response pairs and case rubrics. Do
  not edit this file because the manifest hashes its original bytes; record
  judgments in a separate owner-only file or review-system record.
- `pair_key.json`: private candidate-to-arm mapping.
- `manifest.json`: SHA-256 hashes for the other four artifacts.

Freeze blinded judgments separately (including the SHA-256 of
`paired_review.jsonl`) first, then decode the mapping and compare paired
preferences. Do not call either temperature “best” from latency, schema success,
or this one-repetition pilot alone.

The 2026-09-08 smoke run and its corrected memory retry are documented in
`response_quality_temperature_ab_v1_pilot_report_20260908.md`.
