# CLARA routing-overhead experiment — completed 12 September 2026

**Selection recovered its measured costs against large-only on the easy-only workload, but did not establish a quality-preserving speed improvement.** Across the balanced suite, adaptive averaged **65.694 s per four-turn sequence**, compared with **78.454 s large-only** and **20.115 s small-only**. It delivered **77/144 fully correct answers**, versus **97/144 large-only** and **66/144 small-only**. Correctness here is assistant-reviewed; independent human validation remains pending.

All **144 sequence slots / 576 turns** were collected: 432 main-system turns and 144 diagnostic replay turns. Every attempt is retained, including 30 failed deliveries. All 12 authored sequence variants have three timing repetitions under every system. No answered request was retried.

## Measured outcomes

Each system contributes 36 sequences and 144 attempted turns. Sequence latency includes embedding/memory/conversation startup, all four complete requests and measured intervening work. It excludes admission/cooling waits and final cleanup, which are reported separately.

| System | Delivered / 144 | Fully correct / 144 | Mean request, s | Mean startup, s | Mean sequence, s | All 36 sequences, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Small-only | 135 | 66 | 4.279 | 2.820 | 20.115 | 724.145 |
| Large-only | 139 | 97 | 18.916 | 2.607 | 78.454 | 2824.347 |
| Lightweight adaptive | 136 | 77 | 15.656 | 2.891 | 65.694 | 2364.998 |
| Diagnostic replay | 136 | 77 | 13.636 | 2.714 | 57.434 | 2067.617 |

Adaptive saved **459.349 s (16.3%)** against large-only over 36 matched sequences, and cost **1,640.853 s more** than small-only. Easy-only sequences account for **458.205 s** of that saving; the other three patterns together saved just **1.144 s over 27 sequences**. The pooled result therefore does not show a general mixed-workload routing advantage.

Positive differences below mean adaptive took longer. Each pattern has three distinct sequence variants, each repeated three times. E/D labels describe workloads and do not force routing.

| Pattern | Small-only mean, s | Large-only mean, s | Adaptive mean, s | Replay mean, s | Adaptive − small, s | Adaptive − large, s | Adaptive − replay, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EEEE | 18.563 | 70.306 | 19.394 | 16.768 | +0.831 | -50.912 | +2.626 |
| DDDD | 21.317 | 90.954 | 87.272 | 82.925 | +65.954 | -3.682 | +4.347 |
| EDED | 20.279 | 73.377 | 71.374 | 65.409 | +51.095 | -2.003 | +5.965 |
| DDEE | 20.302 | 79.180 | 84.738 | 64.634 | +64.436 | +5.558 | +20.104 |

- **EEEE:** the timing saving versus large-only is consistent across repetitions, but small-only is slightly faster than adaptive. Both small-only and adaptive score 21/36 correct, versus 33/36 for large-only. The label “easy” did not guarantee a correct small-model answer.
- **DDDD:** adaptive generates entirely on large. Its small observed advantage over large-only cannot be credited to selecting a cheaper generator; backend conditions and output variation remain.
- **EDED:** the mean advantage over large-only is small and reverses in repetition two. The actual adaptive sequence is small/large/large/large, retaining large on the intervening easy turn.
- **DDEE:** all nine adaptive sequences actually selected and generated large/large/large/small. Returning to small did **not** recover its cost against large-only over these four turns: adaptive took 5.558 s longer per sequence on average. Small-only was both faster and more correct on this pattern.

The [paired sequence tables](report_reviewed_v2/paired_sequences.csv), [per-repetition component tables](report_details_final_v2/per_pattern_repetition.csv), and [cluster summaries](report_reviewed_v2/paired_cluster_summary.csv) retain every comparison. Repeats are averaged within each of the 12 sequence variants before descriptive resampling; 576 turns are not 576 independent observations. The overall descriptive sequence-cluster interval for adaptive minus large is −16.646 to −9.222 s; shared templates, one fictional memory profile and only three variants per pattern limit population inference. Per-pattern intervals include both signs for DDDD, EDED and DDEE.

![Complete sequence and request latency](report_reviewed_v2/sequence_latency.png)

[PDF](report_reviewed_v2/sequence_latency.pdf) · [SVG](report_reviewed_v2/sequence_latency.svg)

## Actual path, startup and following turns

Opt-in monotonic tracing records deterministic routing, each actual classifier call, retrieval, answer generation, validation and complete request latency in the application path. Model unload acknowledgment and verified eviction are separate spans. Each turn records actual model names/digests and residency before/after, with per-call residency snapshots. Parent/child spans distinguish inclusive intervals from the disjoint wall-time partition. Backend load/prefill/decode durations are backend metadata inside HTTP spans; they have no invented host timestamp boundaries and are never added to already inclusive wall time.

Actual adaptive generations were **54 small / 90 large**, with nine small→large and nine large→small transitions. Fixed systems generated all 144 answers on their own model; no cross-model fallback occurred. Each main system made **93 memory classifier calls and zero compute classifier calls**; replay made neither kind. A skipped classifier has no fabricated duration.

| Request condition | Small-only n / mean s | Large-only n / mean s | Adaptive n / mean s | Replay n / mean s |
| --- | ---: | ---: | ---: | ---: |
| First request, no model resident | 36 / 11.420 | 36 / 39.187 | 36 / 25.099 | 36 / 24.897 |
| Same generator already resident | 108 / 1.899 | 108 / 12.158 | 90 / 9.768 | 90 / 7.283 |
| Actual generator changes | 0 / — | 0 / — | 18 / 26.206 | 18 / 22.881 |

These conditional means mix different questions; they are descriptive costs, not matched causal estimates of a switch. The [turn table](report_details_final_v2/turn_details.csv) and [following-turn summary](report_details_final_v2/cold_transition_following.csv) retain the exact predecessor and current state. DDEE provides the controlled following-turn comparison below (nine observations per cell):

| DDEE turn | Workload / adaptive generator | Small-only, s | Large-only, s | Adaptive, s | Replay, s |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | Demanding / large, cold | 11.629 | 42.986 | 41.000 | 37.160 |
| 2 | Demanding / large, resident | 2.423 | 15.803 | 13.645 | 9.639 |
| 3 | First easy / large retained | 1.657 | 8.979 | 11.660 | 4.322 |
| 4 | Second easy / return to small | 1.430 | 8.436 | 15.005 | 10.555 |

The adaptive return-to-small request averaged **15.005 s** (range 12.144–17.657 s). It includes any preceding classification on large, unload acknowledgment, verified absence, small-model loading and generation. There is **no fifth turn after these returns**, so later resident-small savings are unobserved and are not inferred.

Actual transition breakdowns below use observed changes, not all peer-unload calls. Loading is nested inside the request; the columns are explanatory spans rather than quantities to add to request time.

| System / actual transition | n | Request mean, s | Unload acknowledgment, s | Verified eviction, s | Nested backend load, s |
| --- | ---: | ---: | ---: | ---: | ---: |
| Adaptive small→large | 9 | 37.406 | 0.015 | 0.115 | 24.177 |
| Adaptive large→small | 9 | 15.005 | 0.020 | 0.206 | 10.031 |
| Replay small→large | 9 | 35.207 | 0.014 | 0.120 | 23.403 |
| Replay large→small | 9 | 10.555 | 0.013 | 0.185 | 9.112 |

The nine following turns after adaptive small→large transitions averaged 9.426 s, versus 9.133 s in replay; their mean backend load durations were only 0.005 and 0.003 s. They stayed on resident large. Returning to small added 6.569 s on DDEE turn four relative to the matched resident-large request. [Complete transition and following-turn comparisons](final_findings.md) preserve the ranges, pairing and repetition detail.

Every sequence starts in a fresh process with empty conversation history, a new CPU BGE embedder and identical prepared memory, and no model resident in Ollama. OS page caches remain warm; this is model/process cold, not reboot/disk-cache cold. Startup begins at embedding initialization and ends at router/Conversation readiness. Client/monitor/admission setup precedes this boundary. Exactly: **sequence = startup + four request spans + measured gaps**; final cleanup is separate.

| System | Startup total, s | Request total, s | Gap total, s | Cleanup total, s |
| --- | ---: | ---: | ---: | ---: |
| Small-only | 101.525 | 616.192 | 6.428 | 5.367 |
| Large-only | 93.853 | 2723.852 | 6.642 | 8.283 |
| Lightweight adaptive | 104.067 | 2254.427 | 6.504 | 6.719 |
| Diagnostic replay | 97.694 | 1963.611 | 6.313 | 6.654 |

## Selection-cost diagnostic and timing accounting

Replay restores each adaptive turn’s exact pre-turn history and observed route, then reruns ordinary retrieval, shared answer helpers and validation. It checks the exact generation model, messages, schema and complete HTTP body before inference, including seed/options/think/keep-alive. All **144 replay generation requests match**. It is a **diagnostic replay requiring an existing trace, not a deployable routing policy**. Each replay starts from the same cold state as its adaptive counterpart.

Adaptive minus replay is **+8.261 s per complete sequence** (+297.381 s overall), or **+2.020 s per request** (+290.816 s overall). This estimates the net cost associated with selection under the observed conditions, rather than a pure isolated classifier cost. All main arms also perform normal memory selection; replay removes that work diagnostically without changing generator choice.

| Disjoint wall component, mean s per attempted turn | Small-only | Large-only | Adaptive | Replay |
| --- | ---: | ---: | ---: | ---: |
| Deterministic routing / bookkeeping | 0.021398 | 0.024909 | 0.035256 | 0.016660 |
| Memory classification, including nested loading | 1.220777 | 4.785982 | 3.187028 | 0.000000 |
| Unload acknowledgment + verified eviction | 0.000000 | 0.000000 | 0.028142 | 0.027311 |
| Retrieval | 0.019991 | 0.020118 | 0.020895 | 0.018066 |
| Answer generation, including nested loading | 2.960378 | 14.024541 | 12.327054 | 13.524418 |
| Validation | 0.008005 | 0.007720 | 0.007753 | 0.007691 |
| Direct residency audit | 0.014114 | 0.015512 | 0.014818 | 0.008200 |
| Other instrumented work | 0.029186 | 0.031673 | 0.029568 | 0.028516 |
| Residual wall time | 0.005264 | 0.005187 | 0.005231 | 0.005326 |

The explicitly named deterministic-decision spans totaled 1.047 s small-only, 1.213 s large-only and 2.007 s adaptive (144/144/288 spans); replay had none. These are nested within routing/bookkeeping above. The adaptive decision-span mean was 0.014 s per request; memory classification, loading and generation dominate the measured time.

![Disjoint component wall times](report_reviewed_v2/components.png)

[PDF](report_reviewed_v2/components.pdf) · [SVG](report_reviewed_v2/components.svg) · [all inclusive events](report_reviewed_v2/events.csv)

| Nested backend durations, total s across 144 turns | Small-only | Large-only | Adaptive | Replay |
| --- | ---: | ---: | ---: | ---: |
| Loading | 330.159 | 857.668 | 908.725 | 886.646 |
| Prompt evaluation | 36.517 | 165.696 | 118.328 | 65.248 |
| Decoding | 197.522 | 1646.486 | 1168.513 | 978.132 |

These backend rows overlap the wall table and must **not** be added to it. In adaptive, 202.065 s of loading occurs inside memory selection and 706.660 s inside generation. Replay has 886.646 s of generation loading and no selector loading: removing a cold classifier moves necessary loading into generation. Treating all cold classifier time as avoidable would overstate selection cost.

The replay is always last in its block, and actual CPU/GPU allocation, cache state and outputs can differ. Two replay client output-reference validation errors (reserved memory references) invalidate the client’s residency hint, causing two extra **no-op** peer-unload/verification paths on the next turns (0.040 s combined). Actual large-model residency and exact generation requests still match. There are 54 adaptive and 56 replay unload spans but only 18 real transitions in each; unload-call counts are not switch counts. The [paired component tables](report_details_final_v2/paired_sequence_components.csv) expose these effects and the [request pairs](report_reviewed_v2/paired_turns.csv) also show the direct residency-audit adjustment.

## Correctness and attribution limits

Two fresh assistant contexts reviewed randomized anonymous answer groups using the frozen question/rubric, preceding history, prepared and actually supplied evidence, citations and delivered answer. Model, system, timings and frequency were hidden. They agreed on label and both unsupported-claim flags for **145/146 groups (99.3%)**; a third blinded assistant adjudicated one disagreement. Exact duplicate groups reuse judgments across dependent repeats. The final mapping covers all 576 attempts and all 30 failed deliveries; 2,090 generated tokens from failed deliveries remain in cost accounting.

| Pattern | Small-only correct / 36 | Large-only correct / 36 | Adaptive correct / 36 | Replay correct / 36 |
| --- | ---: | ---: | ---: | ---: |
| EEEE | 21 | 33 | 21 | 21 |
| DDDD | 12 | 15 | 16 | 16 |
| EDED | 9 | 24 | 19 | 19 |
| DDEE | 24 | 25 | 21 | 21 |

Against large-only, 74 paired turns are both correct, three only adaptive correct, 23 only large correct and 44 neither correct. Adaptive’s gain over small-only is **11 correct deliveries / 7.6 percentage points**, at 45.579 s extra per sequence; its speed gain over large-only accompanies **20 fewer correct deliveries / 13.9 points**. These are tradeoffs, not a demonstrated quality–latency dominance or a deployment recommendation. No acceptable latency/correctness threshold was selected. Identical aggregate adaptive/replay correctness does not mean their answers or errors are identical.

This is the shared application pipeline, including answer helpers and literal constraints where normally used; it is not a generator-capability ablation. The easy subset includes short social turns, and the DDEE endpoints were chosen to exercise the implemented rule. Main-system histories evolve normally from each system’s own preceding answers, so later main-system generation inputs can differ. Only replay fixes the exact adaptive generation inputs. Shared templates/profile, small sample of distinct workloads, automatic placement, residual RAM/swap, background host activity and fixed-last replay order limit attribution. Lightweight offline trace checks and answer reviews ran alongside serial collection; the CPU was not isolated from all background work.

All small-model allocations were 100% GPU bytes. Large-model GPU allocation ranged **49.1–66.2% for large-only, 54.1–68.8% for adaptive, and 51.5–66.2% for replay** (see [placement tables](report_details_final_v2/placement_by_backend.csv)); these fractions describe allocated bytes, not utilization or fractions of computation. Mean generated tokens, including failures, were small **44.104**, large **45.410**, adaptive **44.069**, replay **46.056**. Exact replay requests sometimes produced different outputs; loading/decode variation remains even where lengths match. The [full backend calls](report_details_final_v2/raw_backend_calls.csv) preserve token counts, allocation sizes and durations. Independent human review and behavior beyond the four-turn window remain unmeasured.

## Frozen controls, resources and preserved exceptions

Installed models: **qwen3:0.6b** and **qwen3:1.7b**, Q4_K_M, Ollama 0.33.3; **context 2048, output cap 192, temperature 0, seed 42, thinking disabled, keep_alive −1**. Model digests, complete source archives, configuration, packages and embedding assets were frozen before collection. The [methods and full digests](report_methods.md), [workload](frozen_v2/workload.json), [original protocol](frozen_v1/protocol.md) and [continuation protocol](frozen_v2/protocol.md) document exact controls. All systems use the same 30-operation Tideglass seed with 26 eligible memories.

Inference was serialized under the shared Jetson lock, with competing-process checks and at most one resident model. Existing guards were retained: startup available RAM ≥2 GiB and temperature <55°C; runtime available RAM ≥768 MiB and temperature <68°C; logical swap ≤3,554.164 MiB. The scheduler targets <54°C before admission. No swap topology, service, power-mode or placement setting was changed. CPU BGE uses two threads.

Across **15,856 telemetry samples**, recorded peaks were **6,633 MiB RAM, 2,485 MiB logical swap and 57.343°C**; the largest sample gap was 1.947 s. All 144 admitted sequences passed startup/runtime guard, boot/power/thermal-trip and cleanup checks; rejected temperature admissions before cooling waits remain logged. Every sequence ended with no model resident, as did the independent final host check. There were **308 logged cooling waits**: 3,080 s nominal sleeps, 3,085.993 s from wait records to subsequent snapshots including snapshot overhead. Those waits and the documented collection pause are excluded from sequence totals.

The first batch stopped after sequence 22 because an ordinary answer-validation exception inherited `ValueError` and the harness incorrectly treated it as fatal. That sequence had already attempted all four turns. All **22 whole sequences / 88 turns** remain byte-identical under [freeze v1](frozen_v1/freeze.json), including its failed final turn and original interrupted status. The narrowly scoped continuation changed failure handling and its regression test, added audited continuation adapters, and created [freeze v2](frozen_v2/freeze.json) before the remaining 488 turns. Application/inference settings and workload were unchanged. No answered request was retried or sequence tail spliced. The combined view uses file symlinks to original data and explicitly marks the one four-turn observed failure as eligible for latency totals, never as a successful answer.

Validation passed **946 tests: 920 passed, 26 skipped**, with source unchanged. Simulated instrumentation/workload checks are excluded from measurements. The [final integrity audit](final_collection_audit_v2_corrected/summary.json) passed **11,384 checks** covering all 144 sequence slots, settings/digests, exact memory snapshots, monotonic accounting, replay equality and cleanup. Its first pass falsely rejected memory hashes because the audit serializer omitted the runtime’s canonical newline; that [audit-only correction](final_collection_audit_correction.json) and first audit are preserved. No data or frozen source changed. A separately [recorded prose correction](report_reviewed_v2/prose_correction.json) clarifies the generated report’s startup boundary without changing numbers.

## Artifacts and reproducible commands

The [final artifact index](artifact_index_final.json) records hashes for 2,503 files, including preserved failures and interim audits.

- [Full numerical findings, per-repetition deltas and quality contingencies](final_findings.md), [unrounded findings and provenance](final_findings.json), and [report acceptance record](report_acceptance_final.json).
- [Reviewed numeric analysis](report_reviewed_v2/analysis.json), [complete report tables](report_reviewed_v2/report.md), [sequence/turn/component CSVs](report_details_final_v2/coverage.json), and [timing audit errors: none](report_reviewed_v2/audit_errors.json).
- [Review agreement and provenance](reviews_final_v2/review_agreement.json), [resolved judgments](reviews_final_v2/resolved.jsonl), [blinded packet](reviews_final_v2/blind/packet.jsonl), [original review cohorts](review_cohorts/) and [adjudication](adjudications/cohort28_resolved.jsonl).
- [Combined raw session view](run_v2/), [original raw batch](run_v1/), [reuse hashes](run_v2/reuse_manifest.json), [mixed-freeze analysis provenance](report_reviewed_v2/continuation_provenance.json), and [post-collection host state](post_collection_host.json).
- [Offline validation](offline_validation_v2.json), [full test log](unittest_v2.log), [historical timing reuse assessment](historical_reuse.json), and [preserved collection/continuation command record](collection_record.md). Prior experiment timings are contextual; incompatible prompts/history/cold boundaries prevent pooling them as matched observations.
- [Commands](commands.sh) reproduce reviewed tables/figures without inference, or run a new complete collection in fresh output directories. The inference environment is `.venv`; the pre-existing `/tmp/clara-step4-plots` environment supplies the separately recorded [plotting packages](plot_environment.json). The [executed reproducibility check](reproducibility_check.json) regenerated identical numerical analysis, reviews, turn/sequence component tables and corrected report text; its repeated integrity audit passed.

From the Oline_HRI repository root:

```bash
bash evaluation/routing_overhead_20260912/commands.sh analyze /tmp/clara-routing-reanalysis
# Optional separate experiment; this performs 576 new answer-generation turns:
bash evaluation/routing_overhead_20260912/commands.sh collect /tmp/clara-routing-new-collection
```

The collection command means 576 answer-generation requests plus normal classifier calls; it never overwrites this experiment. Reanalysis uses the exact preserved review judgments, traces and freezes. The [results summary](../../results.md) and [development record](../../developments.MD) preserve prior results and record this completed experiment.
