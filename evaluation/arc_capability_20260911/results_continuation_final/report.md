Qwen2.5 3B diagnostic ARC continuation

Generated 2026-09-11T14:16:39.302225+00:00. Status: **diagnostic_composite_complete**.

The original Qwen2.5 run remains **interrupted by the 512 MiB runtime swap limit**. This report keeps that feasibility failure and separately evaluates the user-requested recovery of original questions 84–100. Questions 1–83 are not replayed; their accepted outputs are retained regardless of correctness.

The recovery segment completed 17/17 designated requests. The resulting **diagnostic composite** is 71/100 (71.0%; 95% CI 61.5–79.0%). This combines 83 accepted parent answers with 17 designated recovery outcomes under changed resource limits. It is not a successful uninterrupted 100-question run.

| System / result type | Overall | ARC-Easy | ARC-Challenge |
| --- | --- | --- | --- |
| Qwen3 0.6B / original completed run | 64/100 (64.0%; 95% CI 54.2–72.7%) | 40/50 (80.0%; 95% CI 67.0–88.8%) | 24/50 (48.0%; 95% CI 34.8–61.5%) |
| Qwen3 1.7B / original completed run | 79/100 (79.0%; 95% CI 70.0–85.8%) | 43/50 (86.0%; 95% CI 73.8–93.0%) | 36/50 (72.0%; 95% CI 58.3–82.5%) |
| CLARA generator selection / original completed run | 79/100 (79.0%; 95% CI 70.0–85.8%) | 43/50 (86.0%; 95% CI 73.8–93.0%) | 36/50 (72.0%; 95% CI 58.3–82.5%) |
| Qwen2.5 3B / diagnostic composite | 71/100 (71.0%; 95% CI 61.5–79.0%) | 38/50 (76.0%; 95% CI 62.6–85.7%) | 33/50 (66.0%; 95% CI 52.2–77.6%) |

Original question 84 is represented twice in the execution record: its parent attempt was interrupted and its designated recovery attempt contributes to composite item scoring. The interrupted parent's raw answer is retained as evidence and is not substituted for the recovery output. Per-item source directory, source observation hash, local/original index, question, choices, label, and correctness are recorded in [composite_answers.jsonl](composite_answers.jsonl) and analysis.json.

Parent progress: 84 attempted requests, 83 successful requests, 59 correct accepted answers, and one interrupted request. Recovery progress: 17 attempted, 17 successful, 12 correct accepted answers.

| Segment | Attempted requests | First request s | All mean / median / p95 s | Later mean / median / p95 s | Peak RAM / swap MiB | Peak temperature C |
| --- | --- | --- | --- | --- | --- | --- |
| Original interrupted parent | 84 | 25.42 | 1.09 / 0.79 / 0.92 | 0.80 / 0.79 / 0.90 | 6426 / 546 | 60.53 |
| Diagnostic recovery | 17 | 30.07 | 3.52 / 1.38 / 10.99 | 1.86 / 1.36 / 3.78 | 6297 / 546 | 56.34 |

Total observed execution cost is 101 attempts and 151.65 seconds of request wall time, including the interrupted parent request and both segment cold loads. This sum excludes the recovery gap, device checks, and idle time between segments; it must not be reported as uninterrupted end-to-end completion latency. Full call load/prefill/decode distributions and all-attempt timing are retained in analysis.json.

The recovery uses an explicitly documented diagnostic policy: startup available RAM at least 2.25 GiB and swap at most 768 MiB; runtime available RAM at least 768 MiB, swap at most **1 GiB**, and temperature below 68 C. Startup temperature below 55 C, active fan, thermal-trip/reset checks, one resident model, model-artifact checks, and cleanup remain required. The earlier parent's amended startup limits were 2.5 GiB RAM and 384 MiB swap, with the original **512 MiB runtime swap limit**. The runtime swap policy changed for this recovery; no claim is made that the stricter feasibility requirement was met.

The parent manifest, observations, finish record, dataset, startup amendment, launcher, and protocol text are archived in the recovery directory and hash-checked against the untouched originals. The diagnostic launcher and new policy are archived separately. Original inference source hashes, model artifact/digest, prompt, schema, decoding settings, and question/choice order are compared with the parent. Additional launcher behavior and its effective resource policy are disclosed independently of those unchanged sources.

Diagnostic launcher SHA-256: `376ce5716a946cd35149786ef2a7f225f9b2596b40b77d763f27c29b1bf1202d`. Diagnostic protocol SHA-256: `8946eb8e90e5e4e996c879c41fe449d41599f456acf0bd9bc36af47844719b31`. Startup snapshot: `{"available_ram_kib": 2533604, "maximum_temperature_c": 52.687, "swap_used_kib": 558848}`.

| Reference → diagnostic composite | Both correct | Reference only | Composite only | Neither | Composite minus reference | Exact paired p |
| --- | --- | --- | --- | --- | --- | --- |
| small → 3B composite | 55 | 9 | 16 | 20 | +7.0 pp | 0.2295 |
| large → 3B composite | 65 | 14 | 6 | 15 | -8.0 pp | 0.1153 |
| cascade → 3B composite | 64 | 15 | 7 | 14 | -8.0 pp | 0.1338 |

Intervals and paired tests are descriptive and unadjusted for multiple comparisons. The pooled Wilson interval is approximate for this equal-stratum sample. The composite has a recovery attempt and changed device/resource conditions. A nonsignificant difference does not establish quality equivalence.

The benchmark is the same 50 ARC-Easy and 50 ARC-Challenge questions from [AllenAI ARC](https://huggingface.co/datasets/allenai/ai2_arc), [Clark et al. (2018)](https://arxiv.org/abs/1803.05457), CC-BY-SA-4.0. It measures zero-shot schema-constrained answer-label generation with 2,048-token context, 192-token output limit, temperature 0, seed 42, and thinking disabled. Public data may occur in model training. This is neither a full ARC leaderboard evaluation nor personal-memory, conversational, or spoken robot evaluation. Qwen2.5 3B Q3_K_S differs in model family and quantization from the Qwen3 Q4_K_M pair; the comparison does not isolate parameter count.

Full frozen dataset SHA-256: `c0e858c862381a6ddf04de56f53d3d12113ac01920aa6a5f7fe30c297f80c4a5`. Parent: `/home/b2jetson/.local/share/oline-hri/evaluation-runs/arc-capability-20260911/04_qwen25_3b`. Recovery: `/home/b2jetson/.local/share/oline-hri/evaluation-runs/arc-capability-20260911/04_qwen25_3b_remaining`.
