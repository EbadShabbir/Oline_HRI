# Response-quality temperature A/B v3 protocol

This preregistered follow-up tests temperature `0.0` against `0.2` after
structurally separating persistent memory IDs from the Ollama model boundary
and adding one narrowly scoped, audited delivery-time normalization. All other
declared generation settings are paired. It is a synthetic local engineering
evaluation, not a user study or a production retrieval evaluation.

## Version history and held-out gate

The v2 policy rejected every memory alias appearing in raw model speech. Its
seed-42 gate outputs showed that the model can append exact source annotations
of the form `(per memory_ref_N)` to otherwise natural speech. Those raw aliases
failed the v2 rule. They are not reclassified as v2 successes and no v2 answer
is reused in this evaluation.

Because the inspected seed-42 outputs informed the v3 normalization rule, the
v3 gate uses held-out seed `46`. This anti-overfitting choice was made before
collecting any v3 gate output. The comparison shards remain seeds `43`, `44`,
and `45`; seed `42` is excluded from every v3 score and decision.

The v2 retry2 gate is also excluded as infrastructure-invalid. A concurrent
`scripts/setup_stt.sh` build, started at 20:14:45 local time, ran `nvcc`/`cicc`
throughout the 20:46:40--20:52:54 gate. The run therefore did not satisfy an
isolated inference environment; neither arm from that run may be reused.

## Structural prerequisite and permitted normalization

Before inference, the Ollama boundary must replace each exact, allowlisted
`mem_...` ID with a deterministic positional alias in copied messages and the
copied response schema. The serialized outbound request must contain no
persistent-memory ID. Only the model-declared `memory_used` aliases are mapped
back to their corresponding IDs; normal application grounding and freshness
checks remain authoritative.

For speech only, v3 permits removal of a literal ASCII annotation whose entire
form is exactly `(per memory_ref_N)`, where `memory_ref_N` is a known alias for
that request and is also present in top-level `memory_used`. The implementation
may remove only that annotation span and the minimum adjacent whitespace needed
to leave normal spacing. Every removal must produce per-attempt telemetry
sufficient to audit that normalization occurred and how many exact annotations
were removed.

No other rewriting is allowed. In particular, an unknown alias, a persistent
ID, a bare alias, different casing, compatibility-form or recognized
cross-script lookalikes, altered punctuation, missing parentheses, nested
prose, or any other alias-bearing commentary must still fail closed at the
boundary. Common explicit record/source/evidence/citation provenance phrases
must fail grounded application validation; any phrasing outside that bounded
validator remains unmodified and fails the blinded quality gate. The normalizer
must not change factual text, punctuation outside the exact annotation,
`memory_used`, gestures, or model generation metadata. A normalization event
without its required telemetry invalidates the attempt.

Leak and response-quality classification applies to the final speech delivered
by the application after this exact normalization. The delivered speech must
contain no memory alias, persistent ID, or citation commentary and must pass all
existing response, grounding, temporal, provenance, and freshness checks. Raw
annotations are discarded at the boundary; only their count is retained as
private audit evidence. Neither raw annotations nor normalization telemetry is
presented to the blinded reviewer as delivered speech.

Candidate orientation must use a per-run secret blinding nonce stored only in
`pair_key.json`, never a value reconstructable from the public plan. Reviewers
receive only immutable `paired_review.jsonl` bytes, and judgments are stored in
separate files with the review SHA-256 before any key is opened.

## Regression gate

Run `response_quality_temperature_ab_v3_memory_gate.json` first. It fixes the
`memory_large_temporal` case, held-out seed `46`, context/output `2176/320`,
expected routing, and required evidence. Both arms must satisfy all of these
conditions:

- application status `ok` and backend `done_reason=stop`;
- no fallback, truncation, persistent ID, or unpermitted alias/citation
  commentary, and no alias, ID, or citation commentary in delivered speech;
- telemetry for every permitted exact annotation removal;
- exact two-record supplied/used provenance;
- both timeline entries, Friday's ginger-tea correction, Saturday's navigation
  milestone, and the conclusion that the milestone came later.

Any failure stops the protocol. Diagnose it only after freezing the blinded gate
judgment, fix it without broadening the exact normalizer or weakening any other
validation, and rerun the whole gate in a new private directory.

## Three-seed comparison

Only after the gate passes, run the three durable seed shards in order:

1. `response_quality_temperature_ab_v3_seed43.json`
2. `response_quality_temperature_ab_v3_seed44.json`
3. `response_quality_temperature_ab_v3_seed45.json`

Each shard has one repetition over:

- `route_large_no_memory_05` — general offline recovery;
- `memory_large_temporal` — corrected preference chronology;
- `memory_large_recency` — three-record milestone/collaborator synthesis.

All use fixed expected routing/evaluator-required evidence, context/output
`2176/320`, thinking disabled, and both temperatures. Seed 44 reverses the
declared arm order; the other shards declare `0.0` first. The result is nine
pairs and eighteen cold `qwen3:4b` calls. Run sequentially with no competing
Ollama request, model generation, CUDA compilation, installer, or other
CPU/GPU/memory-heavy workload. Sharding limits a host interruption to six calls
because the runner cannot resume a partial artifact set.

Do not inspect labeled observations, summaries, mapping keys, or earlier raw
answers between shards. Infrastructure interruption invalidates that shard;
ordinary model timeout or invalid output is an arm outcome and is not retried or
cherry-picked.

## Frozen review and decision rule

For each candidate, judge the final delivered speech: first require an
answered/valid response, every required claim, no forbidden claim, and exact
citation status. A correct valid candidate always outranks a failed or incorrect
one. Then judge factuality, completeness, directness, and concision. Latency and
whether an audited exact annotation was removed must not decide response quality.

Select a temperature for the `2176/320` quality candidate only if it has all
nine application-valid outputs, all six memory answers with exact citations, no
truncation/delivered-speech leak/fallback, complete telemetry for any permitted
normalization, no worse rubric correctness, and a majority in every case (at
least six of nine overall; seven of nine is preferred). Otherwise the result is
inconclusive and its temperature remains `0.2`. Target 2 will evaluate latency
from this functional baseline. Three seeds are an engineering repeatability
check, not a claim of statistical significance.

Before any v3 inference, a dry-run found that the initial full envelope at
`2176/320` left the three-record recency prompt 28 conservative tokens over
budget, which pruned its collaborator record. It also confirmed that the former
shipped `2048/256` defaults could not fit either declared memory case after the
stricter grounded prompt. Removing only duplicated envelope wording while
retaining the canonical-text, instruction, action-authority, relevance, and
weak/conflicting-evidence boundaries reduced each conservative estimate by 80
tokens. Recency now has 52 tokens of estimated headroom at `2176/320`; all four
v3 plans and both shipped defaults use that setting, so temperature remains the
only arm difference. The explicit collaborator/partner relevance link is
covered by regression tests. No v3 model output had been observed when these
preregistration corrections were made. The personal-plan case fits this budget
but remains excluded to keep the predeclared comparison focused on the three
cases above. Adaptive routing and BGE retrieval remain separate experiments
because they are known confounds for this question.
