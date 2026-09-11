# Response-quality v3.1 shard preflights — 2026-09-08

This file transcribes the contemporaneous command outputs recorded in the
operator/tool transcript before each comparison shard. It was assembled after
the shards completed so the checks are easy to audit beside the final report;
it is not a cryptographic process-attestation record. No shard answer or
artifact was opened between runs.

## Seed 43

- A fresh 30-second cooldown completed before the check at
  `2026-09-08T22:17:14+04:00`.
- Ollama was active with `NRestarts=0` and no resident model.
- The heavy-workload process filter found only its own preflight shell: no
  installer, CUDA compiler, test runner, experiment, speech listener, or
  Whisper process was active.
- Initial and extended `vmstat` sampling contained three final consecutive
  intervals with `si=0`, `so=0`; CPU idle was 76--80% for those intervals.
- `tegrastats` reported about 4,392/7,620 MiB RAM, 3,592/3,810 MiB allocated
  swap, GR3D 40--44%, and GPU temperature about 51.7--51.9 C.
- The private directory was confirmed absent, then created mode 0700. Run
  `06ea983595b7406c9b2f81233b5faeb3` completed 6/6 attempts with zero
  console-reported errors.

## Seed 44

- A fresh 30-second cooldown completed before the check at
  `2026-09-08T22:26:36+04:00`.
- Ollama was active with `NRestarts=0` and no resident model.
- The process filter again found only its own shell and no disallowed workload.
- Five consecutive post-header `vmstat` intervals ended with `si=0`, `so=0`;
  CPU idle was about 63--66%.
- `tegrastats` reported about 3,758/7,620 MiB RAM, 3,449/3,810 MiB allocated
  swap, GR3D 58--67%, and GPU temperature about 53.2 C.
- The private directory was confirmed absent, then created mode 0700. Run
  `48cdcccfa23b42d6a9da108c2fab0fc1` completed 6/6 attempts with zero
  console-reported errors.

## Seed 45

- A fresh 30-second cooldown completed before the check at
  `2026-09-08T22:38:27+04:00`.
- Ollama was active with `NRestarts=0` and no resident model.
- The process filter found only its own shell and no disallowed workload.
- The first sample was extended because its zero-I/O intervals were
  interrupted. The extension then recorded five consecutive intervals with
  `si=0`, `so=0`, satisfying the three-sample rule; CPU idle was 79--83%.
  A later 4 KiB/s swap-in sample occurred after that accepted sequence and was
  disclosed rather than silently omitted.
- `tegrastats` reported about 4,294/7,620 MiB RAM, 3,590/3,810 MiB allocated
  swap, GR3D 55--63%, and GPU temperature about 52.2 C.
- The private directory was confirmed absent, then created mode 0700. Run
  `a84e17d547ec49deabb6e52038bf4aab` completed 6/6 attempts with zero
  console-reported errors.

## End state

After all three shards, Ollama remained active with `NRestarts=0` and no
resident model. The transcript-backed procedure and artifact timestamps are
consistent with gate -> seed 43 -> seed 44 -> seed 45 execution. Filesystem
artifacts alone cannot prove that a reviewer never accessed another file or
that no unobserved process briefly ran between samples; this is a limitation of
the local evaluation, not evidence of an observed violation.
