# Offline memory pipeline development replay

Historical authored development data; no new model calls, embeddings, retrieval, answer accuracy or latency measurement.

| Implementation | Distinct prompts | Explicit correct intent | Explicit wrong intent | Unresolved intent |
| --- | ---: | ---: | ---: | ---: |
| baseline | 48 | 17 | 0 | 31 |
| current | 48 | 26 | 0 | 22 |

None means the deterministic policy defers; it does not establish the later classifier's result.

| Implementation | Recorded candidate attempts | Required-fact attempts with candidates | All required selected | No candidate replay available |
| --- | ---: | ---: | ---: | ---: |
| baseline | 74 | 56 | 47 | 110 |
| current | 74 | 56 | 54 | 110 |

Historically, all required facts were supplied in 51/80 required-fact attempts. This is the executed Conversation evidence set, including its packing/schema path, and is not identical to the private linking helper's output.

Selection is replayed independently of each policy's decision on exactly the old ordered candidates. No recorded candidates means unassessed, even when the new policy would retrieve. Missing candidates cannot establish new retrieval recall. IDs outside minimum gold are diagnostic extras, not automatically incorrect evidence. Repeated candidate sets/attempts are dependent development examples.

The pre-step baseline archive is distinct from the original Stage 2 execution freeze. The JSON preserves both source identities and the executed supplied IDs. No historical answer score or artifact was changed.
