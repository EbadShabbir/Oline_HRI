# Response-quality temperature A/B v3.1 protocol

This prospective engineering protocol compares generator temperatures `0.0`
and `0.2` for response quality on the local `qwen3:4b` model. It was frozen on
2026-09-08 before any v3.1 model inference. Routing and evidence are fixed to
the evaluator-authored expectations; temperature is the only generation arm
parameter. This is a synthetic repeatability check, not a user study or a
claim of statistical significance.

## Prior gate and revision boundary

The v3 seed-46 gate is an immutable failed run. Its run ID is
`10d27412f6dd4ded9faa44541973020e`; its blinded-review SHA-256 is
`f0187bc93b43012b323d03284cd8b1e027f214231fa05438001cfb167da94457`.
Temperature `0.0` timed out at the 300-second client deadline. Temperature
`0.2` was application-valid and exactly cited but omitted the mandatory fact
that the tea preference changed to ginger. Both blinded candidates were judged
incorrect before unblinding. That run remains failed, its late Ollama response
is not recovered, and neither arm is reused or scored. See
`response_quality_temperature_ab_v3_memory_gate_report_20260908.md`.

Inspection showed a benchmark contract mismatch: the v1 temporal prompt asked
when the preference changed while its rubric also required what it changed to.
The new `oline_hri_fictional_seven_day_v1_1` suite preserves v1 and changes
only suite-identifying text plus this prompt:

> Create a two-entry chronological timeline comparing my tea-preference
> change, including what it changed to and when, with when I completed the
> navigation milestone, and explain how you know which came later.

The prompt does not disclose `ginger`. The existing reference answer, required
ginger claim, forbidden current-mint claim, evidence IDs, sanitizer, grounding,
freshness checks, and application validators are unchanged.

The 300-second large-model failure budget was provisional. Ollama completed the
failed request about 16 seconds after the client deadline, while active decoding
was short; the 320-token cap can also consume roughly 215 seconds at the prior
1.49-token/s device rate before cold loading and prompt work. V3.1 therefore
fixes `large_request_timeout_seconds=600` identically for both arms, the gate,
and all three shards. This changes censoring, not sampling. A 600-second timeout
is final and is an ordinary failed arm outcome; it cannot trigger another
timeout increase or an in-arm retry.

Per-attempt console progress now reports only an opaque completed-attempt count.
It does not reveal case, arm, temperature, status, error, or response. This
corrects the operator-side blinding defect observed in v3.

## Frozen implementation and inputs

All hashes below were computed after 567 automated tests passed with 22
intentional skips and after all four plans validated against the v1.1 suite.

| Input | File SHA-256 | Canonical/runtime SHA-256 |
| --- | --- | --- |
| v1.1 evaluation suite | `fd046641e1b2839bfbcd98d8701f107cd030a18d5149963fe0fd405032d91c1d` | `dcb81b3d9f91ee82d86583f5ef99e224b40839ac718e380e4d37f422fdc38e7c` |
| default configuration | `eb785352f34606f1b8a39aea94b776532f4a701f3c6061318667aea2dc4ab4e3` | `05ffceeceaa21d0fa40558afad8ba2b6b6df2603f84e1b740797c43bb6e2f04a` |
| seed-47 gate plan | `f5e24550c89d035b4b7b6a441e0f1abdc608dc9d87addfb8c15d963e658e8d82` | `d0971cb59f57813a2b3e3d247794305f68227821f19b853eccbe0d93c64fc1dd` |
| seed-43 shard plan | `2d9db3bbefb7b9fbc83a34ef5b9dc930153209298e2d769c490aa16dc07987e4` | `b9fa64ad07dda8a4dcf8a13e372df7e0992fe4155a92ab5c8f0c640a9d2b25c5` |
| seed-44 shard plan | `087bfa61b18d89e3adcfc9f61e83465e6528377459d43314f1aeba5268bee809` | `02575fe49a70d3f92387225dd00f1efb361d4be11bf9cb682672cff97eb19987` |
| seed-45 shard plan | `644c2ca6246098536438e508feba5299e9db9bc62fc480a3d1f04e18eed97715` | `cebe4997f69238dc1a79a1037c3db68cba79b62f4584041e00f97871c306a587` |

The packaged and evaluation v1.1 suite copies are byte-identical. The experiment
source aggregate is
`b09189f5fac93671c9783ace4a4d73018b31d3a537378974fee7e32cd22ff4d5`
using the runner's
`sha256-u32be-path-length-path-u64be-content-length-content-v1` algorithm.
The runtime is Ollama `0.33.3`; `qwen3:4b` has model-list ID
`359d7dd4bcda` and base blob
`sha256-3e4cb14174460404e7a233e531675303b2fbf7749c02f91864fe311ab6344e4f`.
The installed router/small generator `qwen3:0.6b` has ID `7df6b6e09427` and
base blob
`sha256-7f4030143c1c477224c5434f8272c662a8b042079a0a584f0a27a1684fe2e1fa`.

Every arm uses context/output `2176/320`, thinking disabled, fixed expected
routing, fixed required evidence, one repetition, and the same model/config.
The conservative prompt budget is 1,728 tokens. Preflight costs/headroom are:

| Case | Cost | Headroom | Required records |
| --- | ---: | ---: | ---: |
| General offline recovery | 1,389 | 339 | 0 |
| Temporal correction chronology | 1,636 | 92 | 2 |
| Milestone recency plus collaborator | 1,676 | 52 | 3 |

No required record is pruned. A material change to any hashed source, suite,
configuration, plan, model, prompt setting, sanitizer, validator, or decision
rule invalidates this version before inference and requires a new protocol and
the next unused qualification seed.

## Host isolation and infrastructure classification

Immediately before each live run:

1. Finish all unit tests, installers, CUDA compilation, speech capture/Whisper,
   and other evaluation processes, then wait a fixed 30-second cooldown.
2. Confirm no `setup_stt`, `nvcc`, `cicc`, `ptxas`, unit-test/pytest,
   `evaluation_experiment`, `speech listen`, or Whisper process is active.
3. Confirm `ollama ps` is empty and no other Ollama frontend is generating.
4. Record a process snapshot, three `vmstat` samples with zero swap-in/swap-out
   after the first cumulative row, and a short `tegrastats` sample.

A whole run is infrastructure-invalid only when contemporaneous evidence shows
an overlapping process named above, an Ollama service restart, a kernel OOM
kill, operator interruption, or host power loss. Ordinary timeout, high but
stable swap allocation, desktop/compositor activity, a slow call, malformed
output, application rejection, or a generic watchdog warning is an arm outcome
and is not relabeled after answers are seen. For an objective infrastructure
invalidation, inspect no candidate answers, discard the entire run, document
the evidence, and preregister the next unused seed before rerunning.

## Seed-47 qualification gate

Seed 47 is the deterministic smallest unused integer above inspected gate seed
46. It is qualification-only and never enters the nine-pair comparison. The
gate reverses the prior declared arm order: temperature `0.2` then `0.0`.

Run in a new mode-0700 directory:

```bash
PYTHONPATH=src .venv/bin/python -m oline_hri.evaluation_experiment run \
  --plan evaluation/response_quality_temperature_ab_v3_1_memory_gate_seed47.json \
  --dataset evaluation/fictional_seven_day_v1_1.json \
  --output-dir /home/b2jetson/oline-hri-response-quality-ab-v3_1-memory-gate-seed47-20260908
```

Both arms must have application status `ok`, `done_reason=stop`, exactly the two
required supplied/used memory IDs, no fallback, no truncation, no persistent ID
or unpermitted alias/citation commentary in delivered speech, and complete
normalization telemetry. Each delivered answer must give a two-entry timeline,
state that the preference changed to ginger on Friday, state that the navigation
milestone was completed on Saturday, and conclude from the date order that the
milestone came later. Any ordinary arm failure permanently fails v3.1; do not
run or score the three shards.

## Blinded review procedure

The person/process supervising inference is not a reviewer. After a completed
gate, that operator may read only the exact `paired_review.jsonl` bytes and
SHA-256. Two independent reviewers must start with no inherited run history and
receive only that file—not its directory, console, plan, key, summary,
observations, raw answer, telemetry, or timing. Each independently records:

- `review_id`, `reviewer_id`, and review-file SHA-256;
- correctness of each candidate;
- preference (`candidate_1`, `candidate_2`, or `tie`);
- a concise reason tied to the frozen rubric.

Any disagreement invokes a third equally isolated reviewer, with majority vote
on each field. Store every individual review plus the resolved judgment in a
separate repository JSON file whose state is
`frozen_before_unblinding_and_raw-output_diagnosis`. Only after that file is
written and its review hash rechecked may anyone open `pair_key.json`, summary,
observations, raw generation, telemetry, or timing. The same procedure applies
to the combined shard review.

## Three-seed comparison

Only after the seed-47 gate passes, run these private shards sequentially and in
order, using the exact v1.1 dataset and output directories shown:

1. `response_quality_temperature_ab_v3_1_seed43.json` ->
   `/home/b2jetson/oline-hri-response-quality-ab-v3_1-seed43-20260908`
2. `response_quality_temperature_ab_v3_1_seed44.json` ->
   `/home/b2jetson/oline-hri-response-quality-ab-v3_1-seed44-20260908`
3. `response_quality_temperature_ab_v3_1_seed45.json` ->
   `/home/b2jetson/oline-hri-response-quality-ab-v3_1-seed45-20260908`

Each shard contains one paired repetition of general offline recovery,
temporal correction chronology, and milestone-recency/collaborator synthesis:
six cold 4B calls per shard and nine pairs overall. Seed 44 reverses the
declared arm order. Do not inspect paired reviews, labeled artifacts, mapping
keys, summaries, raw answers, or telemetry between shards. Ordinary failures
remain outcomes; absent objective infrastructure invalidation, finish all three
shards without retry or cherry-picking. Then review only the three anonymized
paired-review files, freeze all reviewer judgments/hashes, and unblind once.

## Selection rule

Select a temperature only if it has all nine application-valid outputs, exact
required citations on all six memory answers, no fallback/truncation/delivered
speech leak, complete telemetry for every permitted exact annotation removal,
and no worse rubric correctness than the other arm. It must also win at least
two of three pairs in every case and at least six of nine overall; seven of nine
is preferred. Correct valid answers always outrank failed or incorrect ones;
otherwise compare factuality, completeness, directness, and concision.

Latency and normalization occurrence are descriptive only and cannot select
response quality. If neither arm satisfies every requirement, the result is
inconclusive and the production temperature remains `0.2`. Target 2 will
optimize latency only after this functional quality decision is complete.
