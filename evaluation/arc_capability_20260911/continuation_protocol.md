# Qwen2.5 remaining-question continuation — 2026-09-11

Recorded before continuation inference, following the user's explicit request
to run only the questions left over from the interrupted 3B attempt.

## Items and evidence

Preserve `04_qwen25_3b` unchanged. Its first 83 requests succeeded, with 59
correct accepted answers. Request 84 was interrupted after backend generation;
its raw answer must not be substituted for a successfully accepted answer.
Run exactly the 17 remaining frozen items, original indices 84–100, once and
in their original order. Retain all original successful answers, including
incorrect ones. No question, answer option, prompt, model, seed, decoding
setting, output schema, or scoring rule is tuned for this continuation.

Save this segment in a separate directory. Archive parent artifacts and their
hashes, both full and derived dataset hashes, the exact remaining-item mapping,
the additional launcher source, and the effective execution policy. Preserve
the parent interrupted request and original 512 MiB runtime failure.

## Explicit diagnostic operating policy

The previous swap use remains above its old cutoff and local administrator
authentication is unavailable. This one bounded diagnostic segment leaves
system swap enabled and changes only the following experimental limits:

| Limit | Parent attempt | Diagnostic continuation |
| --- | ---: | ---: |
| Minimum available RAM before loading | 2.5 GiB | 2.25 GiB |
| Maximum used swap before loading | 384 MiB | 768 MiB |
| Maximum used swap during execution | 512 MiB | 1024 MiB |

Keep the physical runtime RAM floor at 768 MiB, temperature below 68 C, startup
temperature below 55 C, active fan and telemetry, zero/unchanged thermal trips,
stable boot, 15 W mode 0, and exactly one permitted model. Retain the original
artifact/parameter screening and all transport/time limits. Stop on the first
resource or transport failure; do not repeatedly raise limits or restart this
segment. Unload the model on exit and restore temporary Python bindings.
No applications, services, swap devices, or persistent settings are changed.

A read-only device review found about 2479 MiB available RAM and 546 MiB logical
swap occupying about 141 MiB physical zram RAM. The previous 3B attempt peaked
at 6426 MiB whole-device RAM and 60.53 C without a reset or thermal trip. These
observations support a monitored diagnostic attempt with limited headroom;
they do not guarantee successful loading or completion. The runtime swap
criterion is deliberately revised and must not be described as unchanged.

## Reporting

If all 17 items finish, report composite item accuracy across the two segments:
the 83 original accepted answers plus the designated continuation's 17 answers.
Never describe the original 100-question run as completed or feasible under
its 512 MiB runtime criterion. If the continuation fails, leave item coverage
incomplete; do not silently select a later retry's better answer.

Report each segment's timing and cold load separately. Any combined execution
cost must include the parent's interrupted request 84 and the second cold
load: 101 attempts if this segment completes. Downtime between segments is
separate from request timing. Different resource limits and initial desktop,
memory, and cache states preclude treating the composite as an uninterrupted
latency measurement. The first three model arms and their results are unchanged.
