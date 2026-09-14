# Offline replay interpretation — development evidence

This replay evaluates deterministic memory-intent and evidence-linking functions on historical synthetic Stage 2 data. It performs **zero new model, embedding, retrieval or database calls**. It produces no new answer-accuracy or latency result. The 184 historical attempts reuse 48 authored prompts; they are not 184 independent test cases.

| Measure | Pre-step baseline | Current | Denominator |
| --- | ---: | ---: | ---: |
| Explicit correct personal-memory intent | 16 | 24 | 24 distinct personal prompts |
| Explicit correct general intent | 1 | 2 | 24 distinct general prompts |
| Explicit wrong intent | 0 | 0 | 48 distinct prompts |
| Deferred intent | 31 | 22 | 48 distinct prompts |
| All required facts selected | 47 | 54 | 56 required-fact attempts with recorded candidates |
| Required-ID occurrences selected | 63 | 73 | 75 required-ID occurrences in those 56 attempts |
| Required-ID occurrences selected, when present in candidates | 63 | 73 | 73 occurrences present in recorded candidates |
| Selected IDs outside minimum authored gold | 22 | 0 | Occurrences across 74 recorded candidate lists |
| Selected forbidden IDs | 0 | 0 | 74 recorded candidate lists |

`None` intent means the deterministic policy defers to downstream routing; it does not measure a downstream error. The nine newly explicit decisions are eight personal prompts (`t04`, `t05`, `t07`, `t08`, `t09`, `t10`, `t11`, `t12`) and the self-contained timer prompt `r08`. Every formerly explicit decision remains correct on this workload. The remaining 22 deferred prompts are general.

The seven improvements in complete required-fact selection are corrected lunch fact `p04` in four attempts and both conflicting pottery-room facts `p08` in three attempts. There are **no lost required IDs relative to the baseline helper** on any replayed candidate list. The two remaining incomplete selections are `t07` for small/r1 and cascade/r1: the needed badge fact is absent from both historical top-three candidate lists. Removing IDs outside minimum gold is a diagnostic reduction in extra evidence, not a general proof that every removed fact was irrelevant.

Only 74 of 184 historical attempts have recorded candidate lists, including 56 of 80 required-fact attempts. The other 110 attempts cannot be used to assess selection on actual candidates. Current policy explicitly needs memory on 24 attempts that have no recorded candidates; the replay cannot show whether a new retrieval would find the necessary facts. These are the historical personal routing misses now covered by deterministic intent. Candidate selection is replayed independently of intent, using exactly the old ordered candidates.

The baseline helper and historical executed supplied-ID set agree in 53/74 candidate-bearing attempts and differ in 21/74: `p04`, `p05`, `p06`, and `p07` each four times, `p08` three times, and `r11` twice. In every discrepancy the helper returned no required IDs, while the historical system supplied the first candidate. The archived Conversation implements `linked_matches or factual_retrieved[:1]`; this fallback and later context/schema packing are outside the helper being replayed. Thus baseline helper completeness 47/56 and historical supplied completeness 51/56 are different quantities. Across all 80 required-fact historical attempts, supplied completeness remains the original 51/80. No old score is changed.

The pre-step source archive differs from the full Stage 2 execution freeze, but the ASTs of the two specific replayed function bodies are identical between those archives; file and function digests are retained in `interpretation.json`. This does not claim that every dependency or full implementation is identical. The v2 replay incorporates the final timestamp-source patch; all comparison outputs equal v1, which is preserved.

These are development checks against prompts and candidates used to diagnose the change. They support targeted intent/linking fixes and report no regressions on this finite replay. They do not establish unseen-workload quality, retrieval recall, generator capability, full-pipeline correctness, responsiveness, or deployment feasibility. Composition and lifecycle behavior require their separate regression tests and a later guarded live evaluation.
