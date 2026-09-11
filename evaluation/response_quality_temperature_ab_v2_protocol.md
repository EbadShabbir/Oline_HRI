# Response-quality temperature A/B v2 protocol

This preregistered follow-up tests temperature `0.0` against `0.2` after
structurally separating persistent memory IDs from the Ollama model boundary.
All other declared generation settings are paired. It is a synthetic local
engineering evaluation, not a user study or a production retrieval evaluation.

## Structural prerequisite

Before inference, the Ollama boundary must replace each exact, allowlisted
`mem_...` ID with a deterministic positional alias in copied messages and the
copied response schema. The serialized outbound request must contain no
persistent-memory ID. Only the model-declared `memory_used` aliases are mapped
back to their corresponding IDs; normal application grounding and freshness
checks remain authoritative. Alias or persistent-ID text in speech fails closed.

Candidate orientation must use a per-run secret blinding nonce stored only in
`pair_key.json`, never a value reconstructable from the public plan. Reviewers
receive only immutable `paired_review.jsonl` bytes, and judgments are stored in
separate files with the review SHA-256 before any key is opened.

## Regression gate

Run `response_quality_temperature_ab_v2_memory_gate.json` first. It fixes the
`memory_large_temporal` case, seed `42`, context/output `2176/320`, expected
routing, and required evidence. Both arms must satisfy all of these conditions:

- application status `ok` and backend `done_reason=stop`;
- no fallback, truncation, persistent ID, model alias, or citation commentary
  in speech;
- exact two-record supplied/used provenance;
- both timeline entries, Friday's ginger-tea correction, Saturday's navigation
  milestone, and the conclusion that the milestone came later.

Any failure stops the protocol. Diagnose it only after freezing the blinded gate
judgment, fix it without weakening validation, and rerun the whole gate in a new
private directory.

## Three-seed comparison

Only after the gate passes, run the three durable seed shards in order:

1. `response_quality_temperature_ab_v2_seed43.json`
2. `response_quality_temperature_ab_v2_seed44.json`
3. `response_quality_temperature_ab_v2_seed45.json`

Each shard has one repetition over:

- `route_large_no_memory_05` — general offline recovery;
- `memory_large_temporal` — corrected preference chronology;
- `memory_large_recency` — three-record milestone/collaborator synthesis.

All use fixed expected routing/evaluator-required evidence, context/output
`2176/320`, thinking disabled, and both temperatures. Seed 44 reverses the
declared arm order; the other shards declare `0.0` first. The result is nine
pairs and eighteen cold `qwen3:4b` calls. Run sequentially with no competing
Ollama workload. Sharding limits a host interruption to six calls because the
runner cannot resume a partial artifact set.

Do not inspect labeled observations, summaries, mapping keys, or earlier raw
answers between shards. Infrastructure interruption invalidates that shard;
ordinary model timeout or invalid output is an arm outcome and is not retried or
cherry-picked.

## Frozen review and decision rule

For each candidate, judge the hard gate first: answered/valid, every required
claim, no forbidden claim, and exact citation status. A correct valid candidate
always outranks a failed or incorrect one. Then judge factuality, completeness,
directness, and concision. Latency must not decide response quality.

Promote a temperature only if it has all nine application-valid outputs, all six
memory answers with exact citations, no truncation/leak/fallback, no worse rubric
correctness, and a majority in every case (at least six of nine overall; seven
of nine is preferred). Otherwise the result is inconclusive and production
remains at temperature `0.2`. Three seeds are an engineering repeatability check,
not a claim of statistical significance.

The three-memory personal-plan case remains excluded because its conservative
prompt estimate exceeds the `2176/320` budget. Adaptive routing and BGE retrieval
remain separate experiments because they are known confounds for this question.
