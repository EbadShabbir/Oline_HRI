# Fourth-arm startup amendment — recorded before 3B inference

Date: 2026-09-11. This amendment applies only to the pending
`qwen2.5:3b-instruct-q3_K_S` condition. It supersedes the original protocol's
128 MiB **startup swap** ceiling for this one attempt. The original protocol
and failed preflight records are retained as historical evidence.

After discussion of the conservative startup guard and proposed swap cleanup,
the user instructed: "just run and pu t the thinsg back to norma;". Cleanup
remains unavailable because local administrator authentication is required and
the cleanup helper's additional RAM reserve is not satisfied. The evaluation
will therefore leave the operating system's swap configuration in place and
use the same 384 MiB startup swap allowance used by the earlier model arms.
This is an implementation decision within the requested retry, disclosed before
inference; it is not evidence that the original startup criterion passed.

## Revised admission rule and unchanged execution

- Startup swap use: at most **384 MiB**, replacing 128 MiB for this arm only.
- Available RAM: at least **2.5 GiB**, retaining the stricter fourth-arm rule.
- Startup temperatures below 55 C, fan running, zero thermal trips, exactly
  15W mode 0, and no resident Ollama model.
- The original 1.5 GiB artifact screen and parameter count below 4B remain.
- All runtime checks remain: at least 768 MiB available RAM, at most 512 MiB
  swap use, temperatures below 68 C, stable boot/trip counters, active
  telemetry, and only the intended model resident.
- The frozen 100 questions, order, messages, output schema, seed, context,
  generation settings, scoring, timeouts, and single-model residency policy
  are unchanged. No 3B benchmark answer has been observed before this decision.
- Any runtime violation stops the attempt. The original runner unloads the
  attempted model in cleanup. No applications are terminated; no swap,
  service, power, or persistent model settings are changed.

The separate experimental launcher records its SHA-256 and explicit admission
policy in the run manifest. It delegates generation, monitoring, scoring, and
cleanup to the unchanged frozen runner. Any replaced Python module bindings
are restored on exit. Original application/runner source hashes and the
additional launcher provenance must be distinguished in the analysis.

## Basis and limits

A read-only review found approximately 2647 MiB available RAM and 276.5 MiB
used swap, with no resident model and normal temperature/fan/boot state. The
installed 3B artifact is about 90.7 MiB larger than the already-run 1.7B artifact
and passes the original size screen. The completed 1.7B and cascade runs
already operated with approximately 280 MiB peak swap use. These observations
support a monitored feasibility attempt, not a guarantee about unmeasured 3B
allocation buffers or loading behavior.

Report this condition as collected later under the amended startup criterion.
Do not claim identical initial memory/cache/background-process state across
arms, or represent the fourth arm as satisfying the original 128 MiB rule.
The fixed order and single pass continue to limit causal timing comparisons.
