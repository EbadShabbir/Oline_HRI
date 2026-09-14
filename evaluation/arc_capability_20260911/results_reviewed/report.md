ARC capability pilot: incomplete

Generated 2026-09-11T12:38:25.716279+00:00. 3/4 arms completed and independently validated against the same 100 frozen questions.

This is a zero-shot, closed-book, JSON-constrained generated-label comparison on 50 ARC-Easy and 50 ARC-Challenge test questions. Native labels and option order are preserved. The dataset comes from [AllenAI ARC](https://huggingface.co/datasets/allenai/ai2_arc), [Clark et al. (2018)](https://arxiv.org/abs/1803.05457), under CC-BY-SA-4.0.

| Arm | Status | Overall accuracy (Wilson 95%) | ARC-Easy | ARC-Challenge | Failed requests |
| --- | --- | --- | --- | --- | --- |
| Qwen3 0.6B | complete | 64/100 (64.0%; 95% CI 54.2–72.7%) | 40/50 (80.0%; 95% CI 67.0–88.8%) | 24/50 (48.0%; 95% CI 34.8–61.5%) | 0 |
| Qwen3 1.7B | complete | 79/100 (79.0%; 95% CI 70.0–85.8%) | 43/50 (86.0%; 95% CI 73.8–93.0%) | 36/50 (72.0%; 95% CI 58.3–82.5%) | 0 |
| CLARA generator selection | complete | 79/100 (79.0%; 95% CI 70.0–85.8%) | 43/50 (86.0%; 95% CI 73.8–93.0%) | 36/50 (72.0%; 95% CI 58.3–82.5%) | 0 |
| Qwen2.5 3B Q3_K_S | preflight_blocked; 0/100 observed | withheld | withheld | withheld | — |

Errors and truncated/invalid responses count as incorrect in completed arms. An incomplete or invalid arm has no completed accuracy estimate. Wilson intervals describe sampling uncertainty; the pooled equal-stratum interval is approximate.

| Paired comparison (first → second) | Both correct | First only | Second only | Neither | Second minus first | Exact McNemar p |
| --- | --- | --- | --- | --- | --- | --- |
| small → large | 61 | 3 | 18 | 18 | +15.0 pp | 0.00149 |
| small → cascade | 61 | 3 | 18 | 18 | +15.0 pp | 0.00149 |
| large → cascade | 78 | 1 | 1 | 20 | +0.0 pp | 1 |

Paired exact p-values are descriptive, unadjusted for multiple comparisons. A nonsignificant result does not establish equivalent quality. Per-subset paired counts and discordant question IDs are retained in analysis.json.

The standalone 1.7B model rescued 18 requests that 0.6B answered incorrectly. The cascade answered 17 of these correctly and missed 1; 17 were routed to 1.7B. It lost 3 of the 3 requests where standalone 0.6B alone was correct.

Cascade selections: {"qwen3:0.6b": 5, "qwen3:1.7b": 95}. Memory intent was true on 28 requests; retrieval was disabled.

Cascade accuracy changed by +15.0 percentage points versus 0.6B and +0.0 versus 1.7B. Mean elapsed latency changed by +29.42 s and +29.20 s, respectively.

A hypothetical oracle choosing a correct standalone 0.6B/1.7B output could answer 82/100 correctly. This uses answer-key knowledge and is not a deployable result. Replaying the cascade's choices against standalone outputs gives 78/100; the live cascade achieved 79/100. There were 1 answer-label disagreements between cascade generation and the corresponding selected standalone generator.

| Arm | First request s | All mean / p50 / p95 s | Later mean / p50 / p95 s | Peak RAM / swap MiB | Peak temperature C |
| --- | --- | --- | --- | --- | --- |
| Qwen3 0.6B | 12.85 | 0.40 / 0.27 / 0.31 | 0.27 / 0.27 / 0.31 | 5761 / 160 | 56.56 |
| Qwen3 1.7B | 20.10 | 0.62 / 0.42 / 0.49 | 0.43 / 0.42 / 0.49 | 6470 / 280 | 59.25 |
| CLARA generator selection | 31.97 | 29.82 / 30.23 / 37.36 | 29.80 / 30.23 / 37.45 | 6544 / 277 | 55.59 |

Wall time includes serial routing/loading and in-turn safety/metadata checks. Each arm starts without a resident model; its first request is separated, but operating-system cache state is not reset. These are nonstreaming short-answer times, not first-token or speech-to-answer measurements. Resource peaks are sampled whole-device values, including desktop processes and cleanup, at 500 ms intervals.

| Arm / purpose | Calls | Mean wall s | Mean load s | Mean prefill s | Mean decode s |
| --- | --- | --- | --- | --- | --- |
| Qwen3 0.6B / generation | 100 | 0.37 | 0.12 | 0.06 | 0.17 |
| Qwen3 1.7B / generation | 100 | 0.59 | 0.20 | 0.09 | 0.28 |
| CLARA generator selection / classifier | 200 | 5.03 | 4.23 | 0.38 | 0.37 |
| CLARA generator selection / generation | 100 | 19.51 | 18.59 | 0.34 | 0.57 |

Load/prefill/decode values are reported by the inference backend; wall time also contains work outside those fields. Distribution summaries, totals, and token counts are included in analysis.json.

All generators use 2,048-token context, a 192-token output ceiling, temperature 0, seed 42, and thinking disabled. Fixed single-model arms keep their sole generator resident. The cascade uses the deployed two-call 0.6B router and its serial eviction policy under a common MCQ adapter; no personal memory, retrieval, answer composition, authored reference notes, conversation history, STT, or TTS are used. This is CLARA generator selection, not the full application.

The fourth arm is **Qwen2.5 3B Q3_K_S**, selected under the user's 3B-or-4B allowance. The frozen protocol excludes the installed 4B artifact because of its recorded loading watchdog reset and the existing artifact-size guard. **No 4B accuracy was measured.** The [official 3B model card](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct) describes the source model; [the Ollama artifact](https://ollama.com/library/qwen2.5:3b-instruct-q3_K_S) identifies the quantized variant. Family and quantization differ from the Qwen3 pair, so these results compare deployed artifacts and cannot isolate parameter count.

| Actual artifact | GGUF reported parameters | Quantization | Artifact bytes | Full digest |
| --- | --- | --- | --- | --- |
| qwen3:0.6b | 751632384 | Q4_K_M | 522653767 | `7df6b6e09427a769808717c0a93cadc4ae99ed4eb8bf5ca557c90846becea435` |
| qwen3:1.7b | 2031739904 | Q4_K_M | 1359293444 | `8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7` |

Nominal tags and GGUF-reported parameter counts are both retained; their numbers can differ. Runtime and host metadata, source hashes, and per-arm manifest hashes are retained in analysis.json.

The planned collection order was 0.6B, 1.7B, cascade, then 3B; completed arms are identified above. Startup/cache/thermal states and other device work may differ; timing is descriptive and not a counterbalanced repeated-run estimate. Public ARC questions may occur in training data. This science-MCQ pilot establishes neither unseen-task generalization nor personal-memory correctness, HRI quality, or spoken responsiveness. Scores are not directly comparable to full ARC or the likelihood-normalized leaderboard score in [lm-eval's ARC configuration](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/lm_eval/tasks/arc/arc_easy.yaml).

Frozen dataset SHA-256: `c0e858c862381a6ddf04de56f53d3d12113ac01920aa6a5f7fe30c297f80c4a5`. Dataset revision: `210d026faf9955653af8916fad021475a3f00453`.

Raw artifacts: `/home/b2jetson/.local/share/oline-hri/evaluation-runs/arc-capability-20260911`. This report was independently recomputed from raw answer JSON and checks exact dataset/order, source hashes, common prompts, decoding settings, native label schemas, model attribution, recorded completion state, and telemetry.

The extra condition was blocked before inference. Available RAM was 2317.4 MiB (required: at least 2560 MiB); swap use was 277.5 MiB (required: at most 128 MiB). No fourth-model score is available. The complete preflight snapshot and its hash are retained in analysis.json.
