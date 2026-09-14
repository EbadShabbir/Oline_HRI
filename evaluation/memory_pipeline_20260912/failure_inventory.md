# Shared-memory pipeline development inventory

The previous Stage 2 fixture and its observed outputs are **development data**
for this work. They are useful for finding defects, not for establishing the
quality of the revised system. Original observations, frozen rubrics, rejected
responses and device failures remain unchanged. A subsequent quality claim
needs separately specified evaluation data and the stated review status.

This inventory covers 184 observed attempts across four sessions, including
the incomplete 40-request cascade. It does not count unattempted requests as
executed failures. There were 92 personal attempts and 80 personal attempts
requiring particular stored facts. Only 51/80 received all required facts.
Repeated attempts and shared facts are not independent samples.

The companion [JSON inventory](failure_inventory.json) records exact source
hashes, per-attempt evidence sets and the mechanical breakdown below. Its
source is the historical [pipeline diagnostics](../complete_system_20260911/results_reviewed/pipeline_diagnostics.json)
and their hash-verified original observations.

| Stage | Historical evidence | Consequence and regression target |
| --- | --- | --- |
| Memory routing: false negative | 24/46 temporal/synthesis attempts selected no personal memory despite required facts. Cases include meeting availability, workshop supplies, available budget, mixed known/unknown facts and requested presentation preferences. | Selection/composition cannot recover facts that were never retrieved. Exercise personal requests embedded after an initial calculation or instruction, and distinguish supplied hypothetical values from missing stored values. |
| Memory routing: false positive | Six routine-general attempts retrieved personal facts: four timer attempts (`s2_r08`) and two additional self-contained requests (`s2_r11`). | A time word or arithmetic expression must not imply personal-memory need. Verify a self-contained timer and arithmetic problem need no personal citation even when unrelated memories share numbers/words. |
| Retrieval candidate omission | Two `s2_t07` attempts retrieved card supply but omitted the badge-name preference from the returned candidates. | The prompt needs both card count and badge format. Test facet coverage across candidates, rather than only similarities to the longest part of the query. A selector cannot select a fact absent from its input. |
| Evidence selection omission | Three `s2_p08` attempts retrieved both Cedar Hall and Juniper Hall for the same demonstration, then supplied only Cedar Hall. | Preserve conflicting current assertions for the same requested event/attribute. Do not select the first or most recent assertion as a correction when no correction chain exists. |
| Evidence selection/schema overreach | `s2_p01` asks only for the project name. The name, partner and meeting duration were all supplied; three attempts then failed relationship-detail coverage validation. | Select the facts needed for the requested attribute. Do not require optional neighbouring facts or their citations merely because retrieval returned them. Test project name versus partner versus duration as separate questions. |
| Composition/calculation | `s2_t03` supplied both event dates/times, yet one delivered answer said the events were “1 hour apart”; the actual interval is 30 hours 30 minutes. Both facts were available, and no verified timeline constraint was recorded. | Correct retrieval is insufficient. Test calculations from typed event times, crossing midnight, and event time versus creation/correction time. Preserve the distinction between a verified application calculation and model-written reasoning. |
| Mixed support | `s2_t11` supplied the corrected bulgur preference but some responses failed to explicitly acknowledge the unknown current banner location. | Give the supported part and abstain only on the unknown part. A blanket refusal or fabricated replacement location is not complete. |
| Output validation | Nine temporal-detail, three relationship-detail and three cited-fact-coverage failures; two reserved-memory-reference errors; one separate device interruption. | Keep validation and the withheld-response status. Diagnose which supplied/schema-required evidence caused rejection. Do not credit rejected text or remove safeguards to improve delivery counts. |

The 29 attempts missing some required supplied evidence decompose into 24
routing failures, two retrieval-candidate omissions and three selection
omissions in these recorded data. These labels do not account for every
generation or overinclusive-selection error.

The timer illustrates a failure spanning stages. It erroneously retrieved a
paper-frame trial and short-journey walking preference, then required both IDs
in the response schema. The temporal validator withheld all four candidates.
The small/cascade candidates contained 10:55, while the two large candidates
contained 11:15. Because the citations were irrelevant, the two numerically
correct candidates are not established validator-only false positives and
receive no new score credit.

No forbidden memory IDs were supplied or cited in the historical diagnostics.
This is narrower than “no fabricated personal fact”: unsupported claims can be
generated without citing an old or forbidden ID. The original assistant
reviews remain the evidence for semantic disclosure/error classifications.

Of 166 delivered replies, 162 recorded no answer constraint and four recorded
`verified_user_relationship`. The 18 nondelivered attempts did not record
those reply-only fields; their absence cannot establish that composition did
not run before rejection. Empty `reference_ids` likewise does not mean that
the model received no personal facts: use supplied evidence and citations.

# Lifecycle coverage and new regressions

Existing `tests/test_memory.py` already covers atomic correction chains,
rollback on correction/forget failures, fixed retention deadlines, exact
expiry boundaries, profile isolation, synchronized keyword/vector indexes,
index integrity, and authoritative snapshot checks. Its query-inference race
uses another `MemoryStore` instance in the same process. Existing Conversation
tests cover pre/post snapshot rejection using a fake snapshot provider. The
Stage 2 fixture itself changes memories before requests and therefore does
not exercise live correction or forgetting during a request.

The new [process lifecycle tests](../../tests/test_memory_lifecycle_process.py)
run actual separate Python processes against a temporary synthetic SQLite DB.
All six tests pass without an LLM, embedding model or personal database:

1. A writer process corrects a fact; an already-open parent store and a fresh
   reader process retrieve only its replacement. Another profile remains
   unchanged, and correction preserves the retention deadline.
2. A writer process forgets a correction chain; parent keyword/semantic
   searches and a fresh reader see no versions. Another profile remains.
3. Separate readers check one microsecond before and exactly at validity and
   retention expiry, with the other profile still retrievable.
4. A writer using another profile cannot correct or forget the first
   profile's record.
5. A writer forgets a record after real HybridRetriever retrieval but before
   generation. The real Conversation snapshot check prevents a model call
   and history commit.
6. A writer corrects a record during a fake model call. The real post-generation
   snapshot check withholds the stale answer and history; fresh recall returns
   the correction.

These tests use deterministic synthetic vectors solely to exercise the real
index contract and process visibility. They do not measure embedding recall.
Production `memory.py` was not edited for this work.

Additional useful regression targets for the shared pipeline are overlapping
conflict candidates with a later unrelated creation timestamp, requested
facets with an irrelevant high-ranked neighbour, changes/expiry while a query
embedding is computed, and forgetting after a previously successful turn has
entered conversation history. Do not claim the last scenario is covered by
the new tests: they verify that a stale in-flight answer never commits.
