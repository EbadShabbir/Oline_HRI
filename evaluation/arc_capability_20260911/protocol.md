# ARC capability pilot — frozen before inference, 2026-09-11

The requested order is small-only, large-only, CLARA cascade, then the additional
Qwen model. Each arm runs separately and unloads before the next starts.
The fourth arm uses the user's permitted **3B option**:
`qwen2.5:3b-instruct-q3_K_S`. The installed `qwen3:4b` has a recorded watchdog
reset during loading and exceeds the existing 1.5 GiB artifact screen; it is
not part of this run. No claim about that untested 4B model will be made.

## Data and score

- Official [AllenAI ARC](https://huggingface.co/datasets/allenai/ai2_arc),
  revision `210d026faf9955653af8916fad021475a3f00453`, test split.
- 50 ARC-Easy and 50 ARC-Challenge questions. Within each ID-sorted split,
  sample using one Python `Random(42)` generator, Easy first, then Challenge;
  shuffle the combined list using the same generator.
- All arms use the frozen [dataset.json](dataset.json), SHA-256
  `c0e858c862381a6ddf04de56f53d3d12113ac01920aa6a5f7fe30c297f80c4a5`.
  No exclusions or substitutions. Maximum question-plus-options length is
  643 characters, below the production router's 1,000-character limit.
- Preserve original option order and letter/numeric labels. No question ID,
  Easy/Challenge label, answer key, or other gold information enters a prompt.
- Zero-shot, closed-book, schema-constrained generation of one answer label.
  The schema lists every offered label and never identifies the correct one.
  Exact equality against the published key determines correctness.
- Invalid JSON, invalid/multiple labels, truncation, and failed requests count
  as incorrect. No retries or prompt/model tuning after seeing test outputs.
- Backend transport/protocol errors or timeouts stop an arm after preserving
  its failed observation; ordinary answer-format errors may continue. An
  incomplete arm is reported as incomplete, not a completed accuracy estimate.
- Report overall and per-split accuracy, Wilson 95% intervals, paired model
  wins/losses, and cascade selection outcomes. This is **generated-label
  accuracy on a 100-question subset**, not full ARC or the choice-likelihood
  `acc_norm` metric used by the lm-evaluation-harness leaderboard recipe.
- Source data is attributed to Clark et al., *Think you have Solved Question
  Answering? Try ARC, the AI2 Reasoning Challenge* (2018), Allen Institute for
  AI; [paper](https://arxiv.org/abs/1803.05457). Dataset license is CC-BY-SA-4.0.
  Source URLs and SHA-256 values are in [source/manifest.json](source/manifest.json).

## Conditions

| Arm | Models invoked | Residency |
| --- | --- | --- |
| 01 small | `qwen3:0.6b` only | Sole model retained until arm cleanup |
| 02 large | `qwen3:1.7b` only | Sole model retained until arm cleanup |
| 03 cascade | Production 0.6B router, selected 0.6B/1.7B generator | Existing serial eviction; 1.7B does not remain loaded |
| 04 extra | `qwen2.5:3b-instruct-q3_K_S` only | Sole model retained until arm cleanup |

All generators receive identical question/options and generation instructions,
2,048-token context, maximum 192 output tokens, temperature 0, seed 42, and
thinking disabled. Only the answer label is requested; latency therefore
describes short MCQ answers, not long explanations or conversation. The exact
system prompt, configuration, source hashes, runtime version, and model digests
are saved in each arm's manifest. The two Qwen3 artifacts are Q4_K_M; the fourth
model is Q3_K_S and from Qwen2.5. Results compare these artifacts, not parameter
count in isolation. Nominal model tags and GGUF-reported parameter counts are
both retained because their reported numbers differ.

The cascade condition calls the real `ConversationRouter` for both independent
classifications on the complete question/options text. Its final compute
decision selects the generator. Memory intent and raw/policy routing outputs
are recorded, but no personal-memory retrieval, authored plans, composition,
technical notes, conversation history, or speech pipeline is invoked. This is
**CLARA's generator-selection policy under a common benchmark adapter**, not
an evaluation of the complete personalized application. No memory data is used.

## Hardware, timing, and collection

Jetson Orin Nano 8 GB, current 15 W mode, active cooling, existing desktop
processes, `/dev/mmcblk0p1` storage. No model concurrency. Source hashes freeze
the application, benchmark runner, and reused monitoring code before inference.
No production configuration is edited. Single-model residency is an
evaluation-local mapping to the existing client's retained-model role.

Each arm starts with no resident model. Report first-request latency separately
from subsequent requests; all-request p50/p95/mean include the first load.
For cascade, include both classifier calls and all model switches/reloads in
request wall time. Also retain model load, prefill, decode, token counts, and
per-call wall time. Turn wall time includes in-turn safety/metadata checks;
this is elapsed capability-turn timing. There is no streaming/first-token
measurement. Calls use a
120-second request budget; the cascade router retains its deployed 60-second
small-call budget. Different startup/cache states and the user-requested fixed
arm order limit causal speed interpretations; one pass does not establish
run-to-run stability. No deliberate OS page-cache flush or background-process
termination is performed.

Use the existing 500 ms telemetry monitor throughout inference and cleanup.
Retain runtime limits: 768 MiB available-memory floor, 512 MiB swap ceiling,
68 C temperature ceiling, unchanged boot/trip counters, active telemetry, and
at most one resident model. The new 3B arm additionally requires the stricter
2.5 GiB available/128 MiB swap startup screen. Do not relax guards to finish.
Incomplete or interrupted arms remain visibly incomplete and are not silently
resumed or combined. Persist each observation with flush/fsync and retain
all raw responses, model calls, telemetry, start/finish state, and failures.

Private persistent artifacts:
`/home/b2jetson/.local/share/oline-hri/evaluation-runs/arc-capability-20260911/`.
The runner is [run_arc_capability.py](../../scripts/run_arc_capability.py).
Dataset preparation is [prepare_arc_capability_dataset.py](../../scripts/prepare_arc_capability_dataset.py);
it uses a temporary pinned DuckDB 1.3.2 reader, not a new project dependency.

## Interpretation

The model-capability result is the paired correctness matrix, especially
large-only-correct requests and small-only-correct requests. The cascade result
shows whether the frozen selector retains useful quality and what its routing
and loading overhead costs. Report all outcomes, including a single-model win.
A hypothetical per-question oracle is diagnostic headroom only, never a
deployable result. A non-significant quality difference is not equivalence.

These public science MCQs may have appeared in model training. This pilot
does not establish novel-task generalization, memory correctness, HRI task
quality, or spoken responsiveness. Further conversational and memory evaluations
remain separate work in the [draft evaluation plan](../adaptive_selection_protocol_draft.md).
