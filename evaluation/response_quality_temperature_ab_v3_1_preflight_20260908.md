# Response-quality v3.1 live preflight — 2026-09-08

Protocol SHA-256 before inference:
`1ea65e9c05caf9e579ec77afe69e9677f8d8b547b0473616800f265f3c4024ab`.

Automated verification before cooldown: 567 tests passed, 22 intentionally
skipped. All four v3.1 plans validated against the v1.1 dataset. Exact prompt
headroom was 339 tokens for general recovery, 92 for temporal chronology, and
52 for recency/collaborator; every required record was retained.

The first host sample at `2026-09-08T22:10:29+04:00` was rejected before
inference because one post-cooldown `vmstat` interval reported 1,032 KiB/s
swap-in. No model call was made. After another cooldown, the accepted preflight
began at `2026-09-08T22:11:28+04:00`:

- Ollama service: active since 2026-09-07 11:33:30 +04, `NRestarts=0`.
- `ollama ps`: empty.
- Process filter: no `setup_stt`, CUDA compiler, unit-test/pytest,
  `evaluation_experiment`, `oline_hri speech listen`, or `whisper-cli` process;
  only the preflight shell matched its own command text.
- Extended `vmstat` sampling observed three consecutive post-header intervals
  with `si=0` and `so=0`; those intervals reported 77--78% CPU idle and 0% I/O
  wait.
- Jetson sample: RAM about 4,087/7,620 MiB, allocated swap stable near
  3,551/3,810 MiB, GPU about 50.3 C, and GR3D 53--57% under the normal VS Code
  desktop/compositor workload.
- Ollama `0.33.3`; model IDs and blobs match the frozen protocol.
- Gate and all three shard output paths were absent. `git diff --check` passed.

Normal desktop activity is disclosed and permitted by the frozen protocol.
There was no preregistered competing heavy workload at gate launch.
