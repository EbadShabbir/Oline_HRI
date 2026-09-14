# Lightweight routing implementation, 2026-09-12

Status: implemented as an opt-in text-chat mode. Hardware timing and answer
quality are unmeasured. This work addresses the routing/loading cost seen in
the [previous complete-system pilot](../complete_system_20260911/README.md).
It does not establish superiority over an optimized single generator.

Subsequent source change: the [shared-memory work](../memory_pipeline_20260912/README.md)
archives this step's 40 validated source/configuration/test files before editing
the memory path. The validation record below remains evidence for that earlier
snapshot; current source and subsequent checks are documented separately.

## Implemented behavior

```bash
PYTHONPATH=src .venv/bin/python -m oline_hri chat --routing-policy lightweight --show-route
```

The default remains `--routing-policy llm`. Only the explicit lightweight mode
changes selection and retention. It uses the same configured Qwen3 0.6B/1.7B
tags, generation settings, retrieval implementation, and answer checks.

| Component | Lightweight behavior |
| --- | --- |
| Compute selector | Untrained deterministic rules; no classifier model call |
| Easy cases | Bounded greetings, direct facts, and simple recall; reasoning/constraint rules take priority |
| Unknown or context-dependent requests | Select large |
| Switching from resident large to small | First consecutive easy request stays large; second selects small; complex request or lost residency resets the streak |
| Memory selector | Existing independent intent rules first; zero calls when decisive, one actual classifier call otherwise |
| Optional classifier placement | Cached resident model when known, otherwise intended generator; same memory schema and deterministic decoding |
| Retention | Active configured model retained with `keep_alive=-1`; peer eviction and generation serialized by the existing client lock |
| Composed answer | Already selected/resident large may render the same authored literal and required citations; timeout fallback records small as actual renderer |
| Cleanup | Unload on normal exit, error, or interrupt; report failed cleanup and make an otherwise successful exit nonzero |
| Provenance | `policy=lightweight_v1`; explicit decision sources; skipped classifier generations are `None`, never fabricated results |

The two-easy-request threshold is a constructor parameter defaulting to 2.
It is not a learned or measured switching-cost optimum. Easy-case eligibility
is a heuristic and does not establish that 0.6B answers the request correctly.
Memory-classification behavior on 1.7B also needs quality measurement.
The cached residency hint is local to the shared client; other Ollama clients,
server restart, or abrupt process death can defeat residency assumptions.

Automatic memory capture remains a separate opt-in path: eligible disclosures
still trigger its 0.6B classifier after the answer, potentially evicting large.
Voice chat still unloads before every speech-recognition stage. The diagnostic
below excludes both paths and cannot establish spoken-system performance.

## Offline validation

Final discovery reported **809 tests: 783 passed and 26 skipped**, with zero
failures or errors, in 35.396 seconds. All live-test flags were explicitly
disabled. [Validation record and source hashes](offline_validation.json) and
[test output](unittest.log) preserve the command and outcome. `git diff --check`
and CLI help verification also passed.

| Focused coverage included in discovery | Tests |
| --- | ---: |
| Lightweight router contract | 18 |
| Real-client conversation integration with fake HTTP | 14 |
| CLI mode selection, capture, voice, and cleanup | 8 |
| Guarded diagnostic admission and lifecycle | 5 |
| Ollama client, including seven new retention checks | 50 |

Focused tests exercise actual routing and the real Ollama client using a
recording fake HTTP server, plus CLI tests with an in-process backend. They
check peer eviction, retention, classifier counts, ambiguous-memory placement,
hysteresis, failure recovery, metadata, citations, literal constraints, real
temporary-memory-store deletion checks, privacy, history clearing, and exit
cleanup. Simulated outputs and timing are never counted as benchmark results.

The new guarded diagnostic also has offline admission tests: blocked startup
must make zero inference or unload calls; existing output directories cannot
be reused; `--preflight-only` never runs a model even if all gates pass.

## Device preflights

Each policy received a separate read-only preflight, recorded at
2026-09-11 20:04:45 UTC (2026-09-12 00:04:45 Asia/Dubai).

| Policy | Final available RAM | Final swap used | Final maximum temperature | Outcome |
| --- | ---: | ---: | ---: | --- |
| Original `llm` | 2470.91 MiB | 812.5 MiB | 53.0 °C | Startup blocked; 0 requests |
| `lightweight` | 2471.97 MiB | 812.5 MiB | 52.562 °C | Startup blocked; 0 requests |

Both exceeded the unchanged 768 MiB startup swap gate. Neither preflight
started a model or changed swap, power, services, or model installation. Both
finished with no resident models, the same boot and 15 W power mode, active
fan, and zero thermal-trip counters.

- [Original-policy plan](preflight_llm_20260911T200445Z/plan.json),
  [start](preflight_llm_20260911T200445Z/start.json),
  [finish](preflight_llm_20260911T200445Z/finish.json).
- [Lightweight-policy plan](preflight_lightweight_20260911T200445Z/plan.json),
  [start](preflight_lightweight_20260911T200445Z/start.json),
  [finish](preflight_lightweight_20260911T200445Z/finish.json).

The plans record source hashes at preflight time; later cleanup/reporting
fixes do not turn these zero-inference records into a final-source model run.

## Guarded component smoke, pending device admission

Run sequentially, each with a new output directory, after the existing device
gates pass. These commands retain the Stage 2 startup and runtime limits and
never adjust system settings:

```bash
PYTHONPATH=src:scripts .venv/bin/python scripts/check_lightweight_routing_live.py \
  --policy llm --output-dir /absolute/path/to/new/llm-diagnostic
PYTHONPATH=src:scripts .venv/bin/python scripts/check_lightweight_routing_live.py \
  --policy lightweight --output-dir /absolute/path/to/new/lightweight-diagnostic
```

Add `--preflight-only` for zero-inference admission checking. Each actual run
contains two identical general comparison requests followed by three identical
simple definitions. Conversation history is fresh for every request; router
state and model residency persist. The expected lightweight generators are
large, large, large, small, small, with zero classifier calls for these explicit
general requests. Both repetitions are retained; no sample is dropped as a
warmup. HTTP calls, loads, wall time, generation metadata, device telemetry,
residency snapshots, errors, and cleanup are recorded.

This is a five-request lifecycle diagnostic using an empty retrieval fixture,
without embeddings or any personal database. Repeated easy/hard templates do
not estimate accuracy or general routing efficiency. A subsequent full-system
study must freeze the final policy, use held-out requests and independent
quality review, include optimized small-only and large-only controls, and
report actual placement, loading, resource use, failures, and equal coverage.

## Source and historical results

Implementation: [router](../../src/oline_hri/lightweight_routing.py),
[client](../../src/oline_hri/ollama.py), [conversation](../../src/oline_hri/conversation.py),
[CLI](../../src/oline_hri/cli.py), [route record](../../src/oline_hri/routing.py).
Diagnostic: [runner](../../scripts/check_lightweight_routing_live.py).

The existing benchmark runners still use their original router selection.
Before these source changes, all 34 execution files from the old freeze were
verified and copied to
[frozen_source_v2](../complete_system_20260911/frozen_source_v2/archive_manifest.json).
The old freeze, raw runs, scores, and result tables were preserved. The old
source freeze must not be edited to admit the new policy; a new experiment
requires its own freeze and result directory.
