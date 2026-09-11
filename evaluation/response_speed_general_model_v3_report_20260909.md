# Target 2 response-speed result (2026-09-09)

## Decision

Select `qwen3:1.7b` for routed `memory_required=false, model_size=large`
generation. Retain `qwen3:4b` for `memory_required=true, model_size=large` and
retain resident `qwen3:0.6b` for routing and every small route.

The earlier global-1.7B attempt was rejected because every recency case named
the wrong event and omitted required evidence. A second prompt gate did not
repair that grounded-memory failure. The selected split therefore changes only
the large, no-memory route that passed the v3 quality and latency gates.

## Frozen inputs

- Protocol SHA-256: `6c541c12419823373d0d56369b35a6146daf68739ee45066d440e0846f88733b`.
- Gate seed-52 plan file SHA-256: `574e5f3bf1c87614733cc5724e43d880d7f1f51d6e8e5c84504438bd0616d554`.
- Seed-53 plan file SHA-256: `6df7cccd31b3d8fcbcfab629ae5458e11e384f3c5d7200e8e13d7a3552817033`.
- Seed-54 plan file SHA-256: `730acffc8d8884e119d139b9df818ec6deac2b5d08c019b2bc3283b32c58cca5`.
- Seed-55 plan file SHA-256: `3fc59c7fcd36e7e7f766ab5a9e45e9eb9316f1d3acbd5d2472fefb180949cf27`.
- Ollama: `0.33.3`; candidate list ID `8f68893c685c`, installed size
  `1.4 GB`; baseline 4B list ID `359d7dd4bcda`.
- Context/output: `2176/320`; thinking disabled; selected production
  temperature `0.2`.

Raw artifacts remain in private, owner-controlled directories outside the Git
tree because they contain complete model answers and runtime provenance.

## Gate and comparisons

Every selected-temperature answer was valid structured output and included all
six predeclared recovery elements: stop and preserve, assess damage, restore
only from an available verified local backup, salvage or rebuild when no backup
exists, validate before use, and prevent or monitor recurrence.

| Seed | Role | Cold wall (s) | Load (s) | Quality gate |
| ---: | --- | ---: | ---: | --- |
| 52 | gate | 30.903 | 22.072 | pass |
| 53 | comparison | 32.697 | 21.890 | pass |
| 54 | comparison | 40.181 | 21.791 | pass |
| 55 | comparison | 30.543 | 21.513 | pass |

The comparison-only medians were `32.697 s` wall and `21.791 s` load. The
predeclared limits were `45.310 s` and `26.628 s`. Against the reused exact-case
4B medians (`75.516 s` wall and `44.380 s` load), the candidate reduced median
cold wall time by about `56.7%` and median load time by about `50.9%`.

## Verification and limits

The post-integration offline suite passed 572 tests with 23 live-only skips. Tests cover
the three-route model selection, strict configuration pins, serialized
three-model eviction, timeout fallback, CLI diagnostics, and evaluation
provenance.

Focused live checks also passed: the real router selected the 1.7B recovery
route and produced all required contingencies, while a grounded-large direct
recall used 4B and cited only the exact authorized relationship record.

This is a small, one-case cold-start comparison on the current Jetson, and its
4B reference is non-contemporaneous. It supports the selected route change; it
does not establish latency or semantic quality for every general prompt. The
failed memory gates are direct evidence not to replace the grounded 4B route
with 1.7B.
