Qwen2.5 3B diagnostic ARC continuation

Generated 2026-09-11T14:15:32.751293+00:00. Status: **diagnostic_continuation_incomplete**.

The original Qwen2.5 run remains **interrupted by the 512 MiB runtime swap limit**. This report keeps that feasibility failure and separately evaluates the user-requested recovery of original questions 84–100. Questions 1–83 are not replayed; their accepted outputs are retained regardless of correctness.

The continuation is `invalid_artifacts` with 17/17 observations. Composite 100-question accuracy is withheld until all designated requests complete and the artifacts validate.

Parent progress: 84 attempted requests, 83 successful requests, 59 correct accepted answers, and one interrupted request. Recovery progress: 17 attempted, 17 successful, 12 correct accepted answers.

| Segment | Attempted requests | First request s | All mean / median / p95 s | Later mean / median / p95 s | Peak RAM / swap MiB | Peak temperature C |
| --- | --- | --- | --- | --- | --- | --- |
| Original interrupted parent | 84 | 25.42 | 1.09 / 0.79 / 0.92 | 0.80 / 0.79 / 0.90 | 6426 / 546 | 60.53 |
| Diagnostic recovery | 17 | 30.07 | 3.52 / 1.38 / 10.99 | 1.86 / 1.36 / 3.78 | 6297 / 546 | 56.34 |

Total observed execution cost is 101 attempts and 151.65 seconds of request wall time, including the interrupted parent request and both segment cold loads. This sum excludes the recovery gap, device checks, and idle time between segments; it must not be reported as uninterrupted end-to-end completion latency. Full call load/prefill/decode distributions and all-attempt timing are retained in analysis.json.

The recovery uses an explicitly documented diagnostic policy: startup available RAM at least 2.25 GiB and swap at most 768 MiB; runtime available RAM at least 768 MiB, swap at most **1 GiB**, and temperature below 68 C. Startup temperature below 55 C, active fan, thermal-trip/reset checks, one resident model, model-artifact checks, and cleanup remain required. The earlier parent's amended startup limits were 2.5 GiB RAM and 384 MiB swap, with the original **512 MiB runtime swap limit**. The runtime swap policy changed for this recovery; no claim is made that the stricter feasibility requirement was met.

The parent manifest, observations, finish record, dataset, startup amendment, launcher, and protocol text are archived in the recovery directory and hash-checked against the untouched originals. The diagnostic launcher and new policy are archived separately. Original inference source hashes, model artifact/digest, prompt, schema, decoding settings, and question/choice order are compared with the parent. Additional launcher behavior and its effective resource policy are disclosed independently of those unchanged sources.

Diagnostic launcher SHA-256: `376ce5716a946cd35149786ef2a7f225f9b2596b40b77d763f27c29b1bf1202d`. Diagnostic protocol SHA-256: `8946eb8e90e5e4e996c879c41fe449d41599f456acf0bd9bc36af47844719b31`. Startup snapshot: `{"available_ram_kib": 2533604, "maximum_temperature_c": 52.687, "swap_used_kib": 558848}`.

The benchmark is the same 50 ARC-Easy and 50 ARC-Challenge questions from [AllenAI ARC](https://huggingface.co/datasets/allenai/ai2_arc), [Clark et al. (2018)](https://arxiv.org/abs/1803.05457), CC-BY-SA-4.0. It measures zero-shot schema-constrained answer-label generation with 2,048-token context, 192-token output limit, temperature 0, seed 42, and thinking disabled. Public data may occur in model training. This is neither a full ARC leaderboard evaluation nor personal-memory, conversational, or spoken robot evaluation. Qwen2.5 3B Q3_K_S differs in model family and quantization from the Qwen3 Q4_K_M pair; the comparison does not isolate parameter count.

Full frozen dataset SHA-256: `c0e858c862381a6ddf04de56f53d3d12113ac01920aa6a5f7fe30c297f80c4a5`. Parent: `/home/b2jetson/.local/share/oline-hri/evaluation-runs/arc-capability-20260911/04_qwen25_3b`. Recovery: `/home/b2jetson/.local/share/oline-hri/evaluation-runs/arc-capability-20260911/04_qwen25_3b_remaining`.

Validation findings:

- effective execution amendment has unexpected original_retry_start_limits
