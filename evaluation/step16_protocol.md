# Step 16 text-pipeline evaluation protocol

This protocol freezes the measurements for the first execution of the
fictional seven-day suite. It was written before inspecting model answers.
Mira, Theo, Luma, and every memory are synthetic. The run is not a user study
and cannot establish generalizable quality or suitability for real users.

The suite annotation status is
`author_gold_pending_independent_review`. Objective results may be reported as
provisional engineering measurements, but answer-quality claims remain
`reportable: false` until a second human reviews the labels without seeing
model output.

## Fixed runtime settings

- Run all 30 cases once per strategy with an empty conversation history.
- Send only the case prompt to the system under test. Gold routes, retrieval
  labels, rubrics, and reference answers remain evaluator-side.
- Use the configured 2,048-token context, 256-token output cap, and
  non-thinking mode.
- Override evaluation generation to temperature 0 and seed 42. The router
  already uses temperature 0 and seed 42.
- Preserve every timeout, invalid response, fallback, and other failed attempt
  in its denominator.
- Use one shared production Ollama client within a run so its normal serialized
  residency and large-model unload policy remain active.
- Record the case order, model and asset digests, configuration and suite
  hashes, power mode, storage device, software versions, and dirty-tree state.

One repetition provides a device snapshot rather than a variability claim.
The p50 and p95 values summarize the observed case distribution using the
nearest-rank order statistic; they are not confidence bounds.

## Evaluation phases

The component retrieval pass queries all 16 RAG-tagged cases directly with
`HybridRetriever(...).retrieve(limit=5)`. This prevents router errors and the
production top-three context limit from hiding ranks four and five. Corpus
materialization and passage embedding are reported separately from query
latency.

The four stateless cascade strategies are:

1. `always_small_no_rag`: fixed Qwen3-0.6B generation with no retrieval.
2. `always_large_no_rag`: fixed Qwen3-4B generation with no retrieval.
3. `always_large_with_rag`: Qwen3-4B generation after top-three hybrid
   retrieval for every prompt, including general prompts.
4. `adaptive`: the production independent memory/model router, conditional
   top-three retrieval, selected generator, and normal timeout fallback.

The fixed always-large baselines do not use the adaptive cascade's small-model
timeout fallback: a Qwen3-4B timeout remains a failed Qwen3-4B attempt. The
adaptive strategy retains the production fallback policy.

For checkpointing and strategy-level whole-device telemetry, execute four
separate single-strategy bundles in this frozen order:
`always_small_no_rag`, `always_large_no_rag`, `always_large_with_rag`, then
`adaptive`. Confirm that Ollama has no resident model before each bundle. Use
the first bundle as the predeclared component-retrieval source when merging the
four immutable observation streams. The order is a known one-repetition
thermal/cache confound and must be reported as such.

"Full memory/RAG" means always invoking the current bounded hybrid retriever;
it does not mean disclosing every database row.

## Objective metrics

Router results over all 30 adaptive cases include memory-gate accuracy,
model-size accuracy, joint four-route accuracy, both confusion matrices,
incorrect escalation/non-escalation counts, predicted-small share, actual
large-generator invocation rate, and fallback rate.

For the 11 cases with non-empty relevance gold, component retrieval reports
macro Recall@1, Recall@3, Recall@5, required-ID coverage, and mean reciprocal
rank of the first relevant record. A contradiction has two equally
authoritative records; either may appear first, while completeness requires
both. Cases with `top_id: null` are excluded from expected-top-ID accuracy.

For records actually supplied to generation, report micro and macro precision,
required-ID coverage, and any forbidden stale, expired, superseded, or deleted
ID. On the five memory-required cases with empty relevance gold, false
retrieval is the fraction that supplies at least one record. Citation precision
and recall use the validated `memory_used` IDs. No-RAG strategies must emit an
empty citation list.

Natural-language required and forbidden claims are not exact strings and are
not defensibly scored by substring matching or by the same Qwen model being
evaluated. Preserve every expected attempt in a blinded review sheet; failed
or missing generations receive an explicit non-answer row and cannot silently
shrink the review denominator. Keep answer accuracy, temporal accuracy,
updated-preference accuracy, abstention, uncertainty, and hallucination
adjudication pending human review. Structural response and citation-ID validity
remain automated.

Latency summaries retain raw sample counts and report p50/p95 for routing,
query embedding, separately instrumented semantic search, separately
instrumented keyword search, complete hybrid retrieval, generator attempts,
and complete turns where observed. A missing or unattempted stage is `null`,
not a synthetic zero or an elapsed-time subtraction. Ollama-reported load,
prompt evaluation, and token-generation durations remain separate from wall
time. `semantic_search_wall_ns` measures the exact public semantic-search call
and therefore contains its query-embedding work; the separately recorded
embedding duration is a nested diagnostic, so those two values are not added.

## Device measurements and limitations

Sample Jetson RAM, swap, CPU, GPU, temperature, and `VDD_IN` with
`tegrastats`; integrate energy only across monotonic samples. Capture Linux
block-counter deltas for the device that actually backs the run. Jetson memory
is unified, so RAM is not relabeled as separately measured VRAM.

The current unit uses `/dev/mmcblk0`, not the planned NVMe device. Its storage
numbers must be labeled SD-card activity, and the final-NVMe criterion remains
unmet. GUI and development processes are not stopped automatically, so this
run is a noisy development-device measurement. Microphone, STT, speaker, TTS,
gesture, actuation, and physical offline-disconnection tests are deferred: the
peripherals are not attached, and disabling networking would sever the remote
development session. The application path itself remains loopback-only and
uses locally authenticated embedding assets.
