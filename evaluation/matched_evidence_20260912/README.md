# CLARA matched-evidence model-capability experiment

**Completed: 120 fresh requests × two generators = 240 primary attempts.** Assistant-reviewed full-rubric success was **43/120 (35.8%)** for `qwen3:0.6b` and **76/120 (63.3%)** for `qwen3:1.7b`. The larger model rescued **37** requests, including **26 answerable** requests, and lost **4** small-model successes. Its mean warm request cost was **+3.165 s (5.13×)**.

**These are two independent blinded assistant reviews with adjudication; independent human validation remains pending.** The experiment measures direct generator capability under matched evidence. It establishes no routing, retrieval, cascade, spoken-interaction, or deployment-requirement result.

## Paired correctness

| Category | Both correct | Only small correct | Only large correct | Neither correct |
| --- | --- | --- | --- | --- |
| Overall | 39 | 4 | 37 | 40 |
| Routine general | 11 | 1 | 11 | 7 |
| Several explicit constraints | 1 | 2 | 15 | 12 |
| Direct personal recall | 19 | 0 | 5 | 6 |
| Personal temporal / synthesis | 8 | 1 | 6 | 15 |

The observed large-minus-small quality difference is **+27.5 percentage points** (+33 requests); the predeclared category-stratified paired bootstrap 95% interval is **+18.3 to +36.7 points**. This is descriptive uncertainty over authored scenarios, not a population guarantee. All 120 scenarios occur once; there are no repeated quality trials.

| Category | 0.6B correct / 30 | 1.7B correct / 30 |
| --- | --- | --- |
| Routine general | 12 | 22 |
| Several explicit constraints | 3 | 16 |
| Direct personal recall | 19 | 24 |
| Personal temporal / synthesis | 9 | 14 |

| Evidence status | Requests / model | 0.6B correct | 1.7B correct | Only-large rescues |
| --- | --- | --- | --- | --- |
| answerable | 84 | 37 | 59 | 26 |
| unknown | 18 | 5 | 14 | 9 |
| conflicting | 18 | 1 | 3 | 2 |

Correct abstention/uncertainty earns success only where the rubric calls for it and all requested known facts are also supplied. A partial answer receives no full-rubric credit. No quality floor, acceptable extra-cost threshold or response deadline was chosen.

## Partial answers, abstentions, unsupported claims and failures

| Model | complete | appropriate abstention | appropriate uncertainty | partial | incorrect | inappropriate abstention | technical failure | Unsupported claim | Unsupported personal claim |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | 37 | 5 | 1 | 26 | 50 | 1 | 0 | 46 | 25 |
| qwen3:1.7b | 59 | 14 | 3 | 19 | 25 | 0 | 0 | 28 | 20 |

Flags overlap semantic labels; unsupported personal claims are a subset of unsupported claims. A schema-valid response can be semantically wrong. All **240/240** primary attempts completed with valid JSON, zero errors, timeouts, interruptions, truncations, retries or fallbacks. Four separately archived harness attempts are excluded from these counts; their harness pass concerned transport/identity/residency, not semantic accuracy.

| Category / model | complete | appropriate abstention | appropriate uncertainty | partial | incorrect | inappropriate abstention | technical failure | Unsupported | Unsupported personal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Routine general / qwen3:0.6b | 12 | 0 | 0 | 7 | 11 | 0 | 0 | 10 | 0 |
| Routine general / qwen3:1.7b | 19 | 3 | 0 | 5 | 3 | 0 | 0 | 4 | 0 |
| Several explicit constraints / qwen3:0.6b | 3 | 0 | 0 | 13 | 14 | 0 | 0 | 10 | 0 |
| Several explicit constraints / qwen3:1.7b | 12 | 2 | 2 | 8 | 6 | 0 | 0 | 4 | 0 |
| Direct personal recall / qwen3:0.6b | 15 | 4 | 0 | 1 | 9 | 1 | 0 | 9 | 8 |
| Direct personal recall / qwen3:1.7b | 18 | 6 | 0 | 0 | 6 | 0 | 0 | 6 | 6 |
| Personal temporal / synthesis / qwen3:0.6b | 7 | 1 | 1 | 5 | 16 | 0 | 0 | 17 | 17 |
| Personal temporal / synthesis / qwen3:1.7b | 10 | 3 | 1 | 6 | 10 | 0 | 0 | 14 | 14 |

## Measured latency and loading

Seconds below retain every primary outcome. Warm HTTP latency runs from submission to complete streamed response, including durable raw-byte logging. Total attempt time additionally includes the recorded attempt bookkeeping and post-request guards; pre-request admission checks are outside it. Explicit model preloading precedes every twenty-request model block and is reported separately. No values are speech-start or first-token latency.

| Model | Warm mean | Warm median | Warm p95 | Total-attempt mean | Six preloads, total | Startup-amortized mean |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | 0.767 | 0.725 | 1.586 | 0.786 | 54.128 | 1.218 |
| qwen3:1.7b | 3.932 | 2.909 | 9.144 | 3.954 | 132.060 | 5.032 |

| Model | Warm prefill mean | Warm decode mean | Warm load residual, total | Mean generated tokens | Explicit unload total |
| --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | 0.095 | 0.644 | 0.229 | 23.81 | 0.089 |
| qwen3:1.7b | 0.191 | 3.703 | 0.262 | 32.48 | 0.105 |

Across the 37 only-large successes, paired extra warm latency averaged **3.498 s** (median **3.154 s**). Across all requests it averaged **3.165 s**, and the larger model was slower on every matched request. Startup-amortized means allocate each block preload across its twenty requests. Backend loading/prefill/decode are overlapping components of measured wall time and must not be added to it again. The larger model also produced more tokens; this is measured request cost, not a controlled equal-token decode comparison.

| Run order | Paired block | Model | Warm mean s | Preload s | GPU allocation / loaded allocation | Peak °C |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | qwen3:0.6b | 0.852 | 9.185 | 100.0% | 57.312 |
| 2 | 1 | qwen3:1.7b | 6.772 | 22.150 | 73.6% | 58.531 |
| 3 | 2 | qwen3:1.7b | 3.403 | 21.768 | 78.6% | 58.531 |
| 4 | 2 | qwen3:0.6b | 0.686 | 8.834 | 100.0% | 57.656 |
| 5 | 3 | qwen3:0.6b | 0.790 | 8.746 | 100.0% | 57.906 |
| 6 | 3 | qwen3:1.7b | 3.078 | 22.164 | 78.6% | 59.468 |
| 7 | 4 | qwen3:1.7b | 3.600 | 22.353 | 76.2% | 58.500 |
| 8 | 4 | qwen3:0.6b | 0.904 | 9.177 | 100.0% | 57.812 |
| 9 | 5 | qwen3:0.6b | 0.662 | 8.832 | 100.0% | 57.906 |
| 10 | 5 | qwen3:1.7b | 3.318 | 21.629 | 78.6% | 58.750 |
| 11 | 6 | qwen3:1.7b | 3.420 | 21.996 | 78.6% | 58.968 |
| 12 | 6 | qwen3:0.6b | 0.706 | 9.352 | 100.0% | 57.718 |

The large model used **73.6–78.6%** GPU allocation versus **100%** for small, with automatic CPU offload. These are memory-allocation ratios, not GPU utilization or fractions of computation. Placement varied by block and was not forced equal. Counterbalancing controls order only partially; timing reflects these installed artifacts, their output lengths, this desktop load and this runtime.

The complete primary collection spanned **1129.574 s** of host wall time. There were **18** rejected startup checks followed by admission under unchanged guards, covering **360.728 s** between first and successful snapshots. These are recorded scheduler/admission intervals, excluded from warm and preload-only amortized timing. They are not model generation failures or a prediction of an alternative workload’s switching cost.

## Device telemetry and energy

| Model | Peak RAM MiB | Peak logical swap MiB | Peak °C | Sampled block energy kJ | Sampled request energy kJ | Request-time coverage |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | 5656 | 1741 | 57.906 | 1.672 | 1.232 | 99.500% |
| qwen3:1.7b | 6406 | 1742 | 59.468 | 6.364 | 5.380 | 99.738% |

Energy integrates onboard VDD_IN over sampled model-block windows, with background activity and no idle subtraction. Cooldown/admission waits are outside these telemetry windows. Unsampled prefixes/tails are not extrapolated; millisecond cleanup calls have little or no sample overlap, so their apparent near-zero sampled energy is not a zero-energy claim. These are whole-device estimates, not model-only energy. Logical zram occupancy and physical RAM cannot be added together.

The Jetson Orin Nano 8 GB remained in **15W mode 0**, on SD-backed `/dev/mmcblk0p1`, with active cooling. Boot ID, zero thermal-trip counters, Ollama service configuration and swap devices/capacity/priorities were unchanged. No model was resident at collection start or finish. Startup available-RAM floor was 2 GiB and temperature ceiling strictly below 55°C; runtime floor was 768 MiB and ceiling 68°C. Both logical-swap ceilings reserved 256 MiB from the existing 3810.164 MiB capacity. No OS configuration was changed.

## Representative paired answers

Examples include every observed paired outcome. All 120 pairs, raw wording, evidence and review rationales remain in [the complete paired-answer table](analysis_v1/tables_and_answers.md). Selection below takes the first request ID within each observed outcome/category, one example per available category.

### Both correct

**rg01 — Why does a wet cloth usually dry faster when spread out than when left in a ball?**

**qwen3:0.6b:** Because spreading the cloth increases surface area, allowing more water to evaporate more efficiently.

Review: complete — Correctly connects greater exposed surface with faster evaporation.

**qwen3:1.7b:** A wet cloth dries faster when spread out because it increases the surface area exposed to air, allowing water to evaporate more quickly. When the cloth is in a ball, the surface area is reduced, leading to slower evaporation.

Review: complete — Correctly explains exposed wet surface and faster evaporation.

**cg07 — Choose a rug from these options. It must cost no more than 40 tokens, be washable, and be blue. Give the name and one sentence explaining the choice.**

Evidence: Luma: blue, washable, 38 tokens. Nori: blue, not washable, 30 tokens. Selo: red, washable, 25 tokens.

**qwen3:0.6b:** Luma: blue, washable, 38 tokens. It costs no more than 40 tokens and is washable, so this is the best choice.

Review: complete — Selects only Luma and supplies its blue color, washability, and 38-token price with a one-sentence explanation.

**qwen3:1.7b:** Luma: Name - Luma, Explanation - Luma is blue, washable, and costs 38 tokens, which is within the budget of 40 tokens.

Review: complete — Names only Luma and explains all three constraints in one sentence.

**pr02 — Where did I say I keep the spare shoelaces?**

Evidence: You keep spare shoelaces in the blue tin inside the coat cupboard.; Extra buttons are in a jar on the desk.

**qwen3:0.6b:** The spare shoelaces are kept in the blue tin inside the coat cupboard.

Review: complete — Correctly locates the shoelaces in the blue tin inside the coat cupboard.

**qwen3:1.7b:** You kept the spare shoelaces in the blue tin inside the coat cupboard.

Review: complete — Correctly supplies the blue tin inside the coat cupboard.

**pt01 — How did my preferred place for breakfast change, and what is the current preference?**

Evidence: On 2 July you preferred breakfast on the balcony.; On 12 July you changed your breakfast preference to the kitchen nook, replacing the balcony preference.

**qwen3:0.6b:** Your preferred place for breakfast changed from the balcony on 12 July to the kitchen nook. The current preference is the kitchen nook.

Review: complete — Correctly describes the change from balcony to kitchen nook and identifies the current preference.

**qwen3:1.7b:** Your preferred place for breakfast changed from the balcony to the kitchen nook. The current preference is the kitchen nook.

Review: complete — Correctly states the balcony-to-kitchen-nook change and current kitchen nook preference.

### Only small correct

**rg11 — What is one simple way to stop loose socks getting separated during washing?**

**qwen3:0.6b:** Use a tight, straight washing bag or a tight, straight cloth to prevent loose socks from separating.

Review: complete — A washing bag is a plausible simple way to keep socks together despite awkward wording.

**qwen3:1.7b:** One simple way to stop loose socks getting separated during washing is to use a sock separator or a laundry basket with small holes to keep the socks from slipping apart.

Review: partial — A sock separator is plausibly a device for keeping socks organized during washing, so the proposed method has partial merit without requiring the reference mesh bag. The alternative claim that a small-holed laundry basket keeps socks together during washing lacks a credible securing mechanism and is unsupported.

**cg17 — Write a label for a box of spare buttons. It must contain "buttons", have at most four words, and contain no punctuation.**

**qwen3:0.6b:** buttons

Review: complete — The single-word label contains buttons and has no punctuation.

**qwen3:1.7b:** A box of spare buttons

Review: partial — Includes buttons and has no punctuation, but the five-word label exceeds four words.

**pt17 — By 16:00, which of my planned jobs were completed and which had not started?**

Evidence: Your shelf sorting ran 14:00-14:25.; Your card writing ran 15:10-15:40.; Your button sorting was scheduled to start at 16:20 and did start then. All are on 21 May.

**qwen3:0.6b:** Your shelf sorting was completed at 14:00-14:25, and your card writing was completed at 15:10-15:40. Your button sorting started at 16:20 and is on 21 May.

Review: complete — Identifies the first two jobs as completed and gives the button task start of 16:20, establishing that it had not begun by 16:00.

**qwen3:1.7b:** By 16:00, your shelf sorting and card writing were completed, as they were scheduled to run before 16:25 and 15:40 respectively. Your button sorting had already started at 16:20 and was in progress by 16:00.

Review: partial — Correctly marks shelf sorting and card writing complete but falsely says the 16:20 button task was already in progress at 16:00.

### Only large correct

**rg03 — What is the practical difference between sorting laundry and folding laundry?**

**qwen3:0.6b:** The practical difference is that sorting laundry involves organizing items in a specific order to maximize efficiency, while folding laundry involves folding individual items to make them compact and easier to carry or store.

Review: partial — Correctly explains compact folding but describes sorting as ordering rather than separating laundry into groups.

**qwen3:1.7b:** Sorting laundry involves organizing clothes by type, color, or category, while folding laundry involves laying out and folding clothes to prepare them for storage or washing. The practical difference lies in the preparation steps: sorting categorizes the laundry, and folding prepares it for future use.

Review: complete — Distinguishes grouping clothes from folding individual clothes for storage.

**cg04 — Use only bread, cucumber and hummus to suggest a no-cook snack. Give two preparation steps, mention all three ingredients, and do not add an ingredient.**

**qwen3:0.6b:** 1. Combine bread, cucumber, and hummus in a bowl. 2. Add a few drops of olive oil to enhance flavor.

Review: partial — Gives two no-cook steps mentioning all three ingredients but adds forbidden olive oil.

**qwen3:1.7b:** 1. Spread cucumber slices on a plate and top with hummus. 2. Add a slice of bread to the top of the hummus. All three ingredients are used: cucumber, hummus, and bread.

Review: complete — Provides two no-cook steps using only bread, cucumber, and hummus.

**pr01 — What pattern is on my preferred reading cushion?**

Evidence: You chose a cushion with tiny sailboats for reading.; Your outdoor seat pad has yellow checks.

**qwen3:0.6b:** factual

Review: incorrect — The word factual does not answer the cushion-pattern question.

**qwen3:1.7b:** The pattern on your preferred reading cushion is tiny sailboats.

Review: complete — Correctly identifies tiny sailboats on the reading cushion.

**pt03 — Put my three craft projects in completion order, earliest first, and say which was last.**

Evidence: You completed the paper mobile on 18 May 2026.; You completed the felt coaster on 6 May 2026.; You completed the bead tray on 12 May 2026.

**qwen3:0.6b:** 1. Completed the paper mobile on 18 May 2026. 2. Completed the felt coaster on 6 May 2026. 3. Completed the bead tray on 12 May 2026.

Review: incorrect — Lists the paper mobile before earlier completions and does not identify it as last.

**qwen3:1.7b:** The three craft projects in completion order, from earliest to latest, are: 1. The felt coaster (6 May 2026), 2. The bead tray (12 May 2026), and 3. The paper mobile (18 May 2026).

Review: complete — Correctly orders felt coaster, bead tray, and paper mobile from earliest to latest, establishing the mobile as last.

### Neither correct

**rg04 — There are seven bowls on a shelf. I put away four more and take two out. How many remain?**

**qwen3:0.6b:** 3

Review: incorrect — Gives three bowls instead of nine.

**qwen3:1.7b:** There are 7 - 4 + 2 = 5 bowls remaining.

Review: incorrect — Reverses both bowl operations and gives five instead of nine.

**cg01 — Suggest a quiet ten-minute indoor break. Give exactly three numbered steps, no screens, and include stretching and a drink of water.**

**qwen3:0.6b:** 1. Sit in a comfortable chair and stretch your arms and legs. 2. Take a deep breath and close your eyes. 3. Drink a glass of water to stay hydrated.

Review: partial — Gives three numbered quiet indoor steps with stretching and water, but no timing establishes a ten-minute total.

**qwen3:1.7b:** 1. Sit comfortably on a chair or floor and slowly stretch your shoulders and back by raising them slowly into a triangle position. 2. Take a few deep breaths and focus on your breath to relax your body. 3. Drink a glass of water while sitting in a quiet place to stay hydrated.

Review: partial — Gives three numbered quiet steps with stretching and water but no durations establish the required ten-minute total.

**pr25 — Where do I currently keep the embroidery hoop?**

Evidence: Current confirmed memory: your embroidery hoop is in the wicker trunk.; Another current confirmed memory: the same hoop is in the low cabinet. The trunk and cabinet are separate places, neither inside the other. Neither memory supersedes the other.

**qwen3:0.6b:** The embroidery hoop is currently in the wicker trunk, as confirmed by evidence. The low cabinet is separate and unrelated.

Review: incorrect — Resolves the hoop location to the trunk and dismisses an equally current conflicting cabinet memory.

**qwen3:1.7b:** You currently keep the embroidery hoop in the wicker trunk.

Review: incorrect — Chooses the wicker trunk despite the equally current conflicting low cabinet memory.

**pt02 — How many days passed between my buying the mosaic kit and finishing it?**

Evidence: You bought a mosaic kit on 3 June 2026.; You finished that kit on 11 June 2026.

**qwen3:0.6b:** 5 days

Review: incorrect — Gives five elapsed days instead of eight.

**qwen3:1.7b:** 5 days

Review: incorrect — Gives five elapsed days instead of eight between 3 and 11 June.

## Review, validation and reproducibility

The two independent assistant reviews initially agreed on the label and both flags for **232/240 (96.7%)** answers. A third blinded assistant adjudicated all **8** disagreements before mapping disclosure. Initial files, SHA256 freezes, disagreement packets and adjudication records are retained. Reviewer contexts were separate and received independently randomized row orders. Blinding was procedural in a shared filesystem; assistant judgments may share systematic errors. Independent human question/rubric/answer validation is pending.

**Validation:** 24 focused runner/tokenizer/analysis tests and 31 reused guard/telemetry tests passed before primary collection. Four separately archived smoke attempts verified the live path. The main analyzer and separately authored numerical audit reconstructed raw HTTP chunks, checked all 240 unique model/request assignments, identical paired input bodies, actual response models, resident digests/context, sealed input/source hashes and final host state. Actual prompt counts were **93–174 tokens**, identical within every pair; no evidence was pruned. The conservative full budget maximum was 1,020/2,048.

The request settings were context 2048, output cap 192, temperature 0, seed 42, thinking disabled, with a shared free-string JSON schema. Exact sources, settings and model digests were sealed before inference. Ollama was **0.33.3**, and both artifacts were **Q4_K_M**. The installed metadata reports 751,632,384 and 2,031,739,904 parameters, respectively; nominal tag names are not exact measured parameter counts.

| Installed generator | Frozen manifest digest |
| --- | --- |
| qwen3:0.6b | `7df6b6e09427a769808717c0a93cadc4ae99ed4eb8bf5ca557c90846becea435` |
| qwen3:1.7b | `8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7` |

- [Frozen protocol](frozen_v1/protocol.md), [approved dataset](frozen_v1/dataset.json), [independent preflight review](frozen_v1/preflight_review.json).
- [Freeze manifest and source hashes](frozen_v1/freeze.json), [tokenizer proof](frozen_v1/tokenizer_proof.json), [rendered model inputs](frozen_v1/prompts.json).
- [Primary raw collection](run_v1/), [collector completion](run_v1/finish.json), [separate smoke collection](smoke_v1/).
- [Blinded review packets](blinded_v1/), [frozen reviews and adjudication](reviews/), [initial agreement](disagreements_v1/agreement.json).
- [Machine-readable reviewed analysis](analysis_v1/analysis.json), [every scored attempt](analysis_v1/scored_answers.jsonl), [independent resource audit](resource_audit_v1/resource_audit.json).
- [Methods and limitations](methods.md), [reproducible shell commands](commands.sh), [PNG figure](figures_v1/paired_capability.png), [PDF figure](figures_v1/paired_capability.pdf), [plot data](figures_v1/attempt_latency.csv).

## Interpretation

On this frozen workload, **1.7B rescues 37 requests**, of which **26** require a supported answer rather than uncertainty alone. It also loses **4** requests that 0.6B gets right. The net gain is **+33/120**, with **+3.165 seconds** average warm request time and higher sampled device energy. These observations establish the pair’s measured complementarity and cost on this component test. No acceptable extra-cost threshold was specified, and no selector was evaluated. The results therefore do not establish that a cascade is preferable, that a router can identify the rescues, or that either model meets an HRI deployment requirement.

The larger model still fails 44/120 full rubrics, and both models fail 40 requests. Unresolved conflicting evidence is a particular weakness: only 1/18 small and 3/18 large answers satisfy those rubrics. The capability gain does not imply reliable general conflict resolution or uniformly strong temporal reasoning.

The balanced assistant-authored workload, short evidence packets, single temperature/seed run, automatic CPU/GPU placement and assistant-only scoring limit generalization. Both model answers were ordinary generation with identical evidence; results cannot be pooled with prior application experiments that used different evidence or answer helpers. All previous experiments are preserved. No deployment or routing policy was changed.
