# Qwen3-4B benchmark on the current Jetson

Task 11 was completed on 2026-09-06 (Asia/Dubai) against the local Ollama
service. This is a focused pull-and-run baseline for `qwen3:4b`, not the broad
four-strategy evaluation recorded in Step 16.

Step 16 now has a completed four-baseline collection and objective merge in a
private local engineering report that is deliberately excluded from version
control because it contains raw prompts, answers, provenance, and telemetry.
Its first large-model run was interrupted by an unclean reboot; after explicit
approval, the retry and remaining collections completed. The original reboot
cause remains unknown. These measurements and the earlier Task 11 success do
not establish sustained deployment stability or answer quality; independent
label and answer review remains pending.

## Environment

| Item | Observed value |
| --- | --- |
| Device | Jetson Orin Nano 8GB, 15W power mode |
| Storage | `/dev/mmcblk0` on this development unit, not the planned NVMe deployment baseline |
| Ollama | `0.33.3` |
| Model | `qwen3:4b`, Q4_K_M |
| Tag digest | `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7` |
| Model-blob digest | `sha256-3e4cb14174460404e7a233e531675303b2fbf7749c02f91864fe311ab6344e4f` |
| Downloaded tag size | 2.5 GB reported by `ollama list` |
| Resident allocation | 3.2 GB, 34% CPU / 66% GPU, reported by `ollama ps` |
| Context and mode | 2,048 tokens, non-thinking, one request at a time |

The model was already present when this run began, and `ollama list` verified
the expected tag and digest. The system was under real development-unit memory
pressure rather than being an isolated laboratory setup.

## Request

All timed answer requests used the same direct `/api/chat` body:

```json
{
  "model": "qwen3:4b",
  "messages": [
    {
      "role": "system",
      "content": "You are running a deterministic local inference benchmark. Do not think aloud. Follow the user formatting request exactly."
    },
    {
      "role": "user",
      "content": "Write a compact numbered list of practical checks for an offline household robot deployment. Continue until the response limit; do not add an introduction."
    }
  ],
  "stream": false,
  "think": false,
  "keep_alive": "10m",
  "options": {
    "num_ctx": 2048,
    "num_predict": 64,
    "temperature": 0,
    "seed": 42
  }
}
```

The unloaded cold request used `keep_alive: "5m"`; that setting does not
change the measured inference work. Each request used `curl --max-time 120` and
recorded both curl wall time and Ollama's nanosecond timing fields. Before the
warm series, an empty-prompt `/api/generate` preload took 50.376574 seconds and
returned `done_reason: "load"`; the preload is not included in the warm table.

## Results

### Unloaded cold request

| Metric | Result |
| --- | ---: |
| HTTP status | 200 |
| Curl wall time | 113.989986 s |
| Ollama total duration | 112.326615 s |
| Load duration | 72.879663 s |
| Prompt evaluation | 63 tokens in 2.955072 s (21.32 tokens/s) |
| Generation | 64 tokens in 26.127071 s (2.45 tokens/s) |
| Stop reason | `length` |

The cold request completed only about 6 seconds inside the 120-second client
limit used for this benchmark. That narrow margin motivated the application's
former provisional 300-second large-model failure budget. A later quality gate
showed that 300 seconds could expire shortly before Ollama completed under host
pressure, so the current shipped functional baseline uses 600 seconds.

### Resident warm requests

| Run | Curl wall | Ollama total | Load | Prompt eval | Cached prompt tokens | Eval | Generation rate |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 46.516262 s | 46.500094 s | 0.026876 s | 0.745158 s | 0 | 45.586577 s | 1.40 tokens/s |
| 2 | 43.885176 s | 43.874724 s | 0.003335 s | 0.864833 s | 62 | 42.994326 s | 1.49 tokens/s |
| 3 | 42.377536 s | 42.376040 s | 0.001749 s | 0.588709 s | 62 | 41.780214 s | 1.53 tokens/s |
| **Median** | **43.885176 s** | **43.874724 s** | **0.003335 s** | **0.745158 s** | **62** | **42.994326 s** | **1.49 tokens/s** |

All three warm requests returned HTTP 200 and generated 64 tokens. The warm
generation rate was unexpectedly lower than the cold request's generation
phase. Device contention, thermal state, or changing CPU/GPU offload behavior
could contribute, but this focused run did not isolate the cause; the measured
median is reported rather than replacing it with the faster single result.

## Memory, thermal, and power observations

Immediately before the cold request, `free -b` reported:

| Resource | Total | Used | Available/free |
| --- | ---: | ---: | ---: |
| RAM | 7,990,546,432 B | 4,754,841,600 B | 2,858,885,120 B available |
| Swap | 3,995,246,592 B | 3,147,673,600 B | 847,572,992 B free |

Samples captured during the cold load and generation reached approximately
7,008/7,620 MB RAM and 3,810/3,810 MB swap. The sampled GPU load reached 78%,
temperature reached about 53.7 degrees Celsius, and sampled `VDD_IN` reached
8,944 mW. These are observed samples, not guaranteed absolute peaks.

With the model resident after the warm series, `ollama ps` reported the 3.2 GB
34% CPU / 66% GPU allocation. A short subsequent snapshot reported
6,728-6,737/7,620 MB RAM, 3,139/3,810 MB swap, 67-72% GPU load, temperatures up
to 54.7 degrees Celsius, and `VDD_IN` of 7,285-7,598 mW. `free -b` reported only
720,891,904 bytes of available RAM at that point.

## Output-quality limitation

`think: false` prevented a separate thinking field, but every 64-token answer
spent its visible content restating the instructions and planning the list.
None reached the requested numbered checks before stopping at the output cap.
The run therefore proves local execution and measures its cost; it does **not**
establish acceptable instruction following or answer quality for this prompt.
Step 15 supplies a fully synthetic, author-gold seven-day fixture and
deterministic prompt harness. Step 16 has now executed the four baselines and
merged their objective measurements. The fixture contains no human-participant
data, cannot establish generalizable quality, and remains pending independent
annotation review. Free-text answer quality also awaits blinded human review.

## Decision

`qwen3:4b` is installed and runnable, but it is not a low-latency interactive
default on the current memory-constrained, SD-backed unit. The measurements
support keeping it as the slower on-demand route while `qwen3:0.6b` remains the
resident default. Tasks 13 and 14 now serialize model residency and permit one
small-model fallback only when the selected large-model request times out.

The benchmark ended with `ollama stop qwen3:4b`; a final `ollama ps` showed no
resident model.
