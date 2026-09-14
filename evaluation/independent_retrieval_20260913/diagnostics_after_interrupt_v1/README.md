# Resource diagnosis after the first collection interruption

At 2026-09-13T16:53:12.875178+00:00, available RAM was 2285.6 MiB, 237.6 MiB above the unchanged 2 GiB startup gate. Maximum measured temperature was 51.937 C. All observed frozen admission checks passed; no model or competing experiment remained resident/running.

This supports a fresh guarded admission attempt. It does not show that a resident 1.7B session fits sustainably. No model, embedding, service, power, swap, application or OS change was made. Existing user apps were left open.

| Slot | Attempted | Available start / finish, MiB | Telemetry RAM first / peak, MiB | Peak C | Outcome |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 48 | 2255.5 / 1822.0 | 5161 / 5767 | 60.031 | complete |
| 2 | 48 | 2308.4 / 1639.9 | 5095 / 5990 | 60.906 | complete |
| 3 | 48 | 2112.4 / 1349.3 | 5278 / 6284 | 61.062 | complete |
| 4 | 13 | 2277.2 / 955.1 | 5116 / 6636 | 56.875 | interrupted |

The large session admitted with 2277.2 MiB available. Its first model load raised sampled RAM from 5116 to about 6359 MiB. Later values fluctuated and reached 6636 MiB; request13 triggered the frozen available-RAM floor. The exact offending MemAvailable value is not stored by the throwing guard; the guard message establishes that it fell below786432 KiB (768 MiB). Temperature and swap stayed below their runtime ceilings.

Ollama reported one fixed allocation throughout the successful large requests: 1,658,826,259 bytes total and936,703,426 bytes in VRAM, with context2048. This is allocation metadata, not a complete process-memory measurement. No increasing model allocation or second resident model was observed.

The large worker finish snapshot had955.1 MiB available even after model cleanup; the current host recovered to2285.6 MiB after worker exit/cooldown. That recovery is consistent with process-lifetime/backend allocation pressure and does not identify its owner. No per-process RSS/PSS trace exists during inference, so a specific leak or background contributor cannot be proved from these artifacts. The code-lifetime reviewer separately found only a few MiB of bounded Python diagnostic/telemetry graphs, one lazy embedding session, and no growing conversation history.

Preserve all157 attempts:156 delivered and one interrupted. A continuation can attempt only the707 never-started tasks under explicit provenance and unchanged guards. New worker fragments introduce additional cold-start boundaries; record them and do not claim an uninterrupted original48-request session.

Evidence: [host probe](host_probe.json), [nonsemantic resource tables and source hashes](resource_review.json). The initial sandbox process listing exposed only its own PID namespace, so the retained host scan used an authorized read-only host execution.
