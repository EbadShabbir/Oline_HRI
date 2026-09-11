# Winning-pair full-memory validation — 2026-09-09

Follow-up: [remediation and memory retest](./20260909_remediation_report.md)
documents the subsequent routing, output-budget, and validator fixes. This
report preserves the original 128-token baseline results.

## Outcome

The deployed two-model cascade is now `qwen3:0.6b` for routing and small
answers, with `qwen3:1.7b` shared by both large routes. It is safe and much
faster than the retired 4B path on this Jetson, but the full-memory run does
not support calling it production-ready for answer correctness.

The memory implementation itself is sound: configuration, storage,
seven-day retention, process-restart persistence, correction/forgetting
replay, BGE embeddings, hybrid retrieval, model serialization, and safety
cleanup all completed. The limiting component is model behavior. In the
30-case adaptive run, memory-intent accuracy was 19/30, model-size accuracy was
28/30, joint route accuracy was 19/30, and 23/30 cascades produced an
application-valid structured response. Three of the seven response errors were
large answers truncated at the fixed 128-token limit. Several structured
successes were still semantically wrong because the router skipped required
memory.

Keep this pair as the best tested Jetson-safe baseline. Do not restore or load
`qwen3:4b` on this unit. Before treating the system as a reliable personalized
assistant, improve or override the 0.6B memory-intent decision and retest a
larger large-answer output budget without changing the selected pair.

## Tested configuration

```json
{
  "ollama": {
    "small_model": "qwen3:0.6b",
    "general_large_model": "qwen3:1.7b",
    "large_model": "qwen3:1.7b",
    "request_timeout_seconds": 60,
    "large_request_timeout_seconds": 120,
    "unload_timeout_seconds": 30
  },
  "generation": {
    "context_length": 2048,
    "max_output_tokens": 128,
    "temperature": 0.0,
    "thinking": false
  }
}
```

The repository and packaged defaults were byte-identical at collection time,
with SHA-256
`1f07a145ec21286e67b9659327a05fe488f02d61bc0c1f9e2e70964cf1ddaee8`.
The benchmark's canonical parsed-configuration digest was
`16460466ac1dc9fbf29f596ed5e56966720f86a3c1ffd058ca71716f7c389edd`.

## Verification results

| Check | Result |
| --- | --- |
| Configuration validation | Valid, schema 7 |
| Focused config/router/lifecycle/scorer tests | 190 passed |
| Final offline discovery in `.venv` | 601 passed, 26 live tests skipped (627 total) |
| Real BGE embedding and SQLite vectors | 2/2 passed |
| Live automatic capture | 3/3 passed |
| Live four-route and grounded-chat smoke tests | 9/9 passed |
| Live semantic-quality suite | 10/16 passed overall; 5/11 live model cases passed and 5/5 offline assertions passed |
| Real serialized residency | 1/1 passed: 0.6B -> 1.7B -> 0.6B, never overlapping |
| Two-process automatic-memory dry run | Completed, distinct PIDs, no default personal database used |
| Seven-day adaptive benchmark | Complete: 16 retrieval records and 30 cascade records |

The first embedding invocation used the system Python, which does not contain
`onnxruntime`, and therefore did not exercise the provisioned application
runtime. Repeating the exact test with the documented `.venv` interpreter
passed both live embedding tests.

## Automatic-memory restart run

The learn process completed 13 turns in 35.73 seconds. Capture status matched
all 10 disclosure expectations: seven records were stored, greeting and
current mood were skipped, and the duplicate tea preference reused its prior
record. Six of seven predicted memory kinds matched; the desk-plant fact was
classified as an event. All three same-process recall questions were answered
and cited correctly.

The recall phase used a different PID, reopened exactly seven records, and
left those seven records unchanged. It answered 5/9 expectations: tea,
meetings, and relationship recall were correct, and both unknown-information
questions safely abstained. Of the other four known-memory questions:

- bicycle generation contained the correct color but omitted its required
  citation, so the application returned the fixed abstention;
- the plant answer over-cited unrelated supplied records and was rejected;
- the completed-test question was classified as a statement and skipped
  memory; and
- the answer-length response over-cited unrelated records and was rejected.

This establishes real persistence across process restart while also exposing
small-model routing and citation limitations.

## Adaptive 30-case result

Run ID: `1304f73212f34292bb753ad0e34f312c`.

| Metric | Result |
| --- | ---: |
| Protocol completion | Complete |
| Component retrieval errors | 0/16 |
| Recall@1 / @3 / @5 | 0.6970 / 0.8182 / 0.8485 |
| Component retrieval MRR | 0.9545 |
| Forbidden-ID retrieval hits | 0/16 |
| Memory-intent accuracy | 19/30 (63.33%) |
| Model-size accuracy | 28/30 (93.33%) |
| Joint route accuracy | 19/30 (63.33%) |
| Structured cascade success | 23/30 (76.67%) |
| Citation micro precision / recall | 75.00% / 16.67% |
| End-to-end latency p50 / p95 | 2.688 s / 54.236 s |
| Route latency p50 / p95 | 0.856 s / 10.932 s |

The memory classifier produced five false-positive retrieval routes and six
false-negative no-memory routes. The size classifier missed two of the four
large grounded-synthesis cases. The seven application errors were all response
validation failures: three 1.7B large responses ended at the 128-token limit,
and four 0.6B grounded responses failed fact, relationship, expiry, or
contradiction safeguards. No transport timeout or fallback occurred.

The formal free-text sheet remains `pending_blinded_human_review`; objective
structured success must not be presented as answer accuracy. A separate
assistant rubric audit is recorded below as diagnostic evidence, not as an
independent human review.

### Assistant semantic audit

This is a diagnostic assistant review, not the pending independent human
review. Against the fixture's explicit reference answers, required claims, and
forbidden claims, 11/30 cases were correct. Of the 23 delivered structured
answers, 11 were correct and 12 were incorrect; the other seven cases had no
reviewable application response. One delivered answer made an unsupported
claim, and one unnecessarily disclosed a true but forbidden personal fact on
a general question.

The clean semantic cases were the greeting, general morning-meeting benefit,
database-recovery plan, context-bounding comparison, meeting-window recall,
corrected tea preference, confirmed appointment, absent-memory abstention, PIN
abstention, third-party-address abstention, and unconfirmed-inference
abstention. The main failure groups were:

- five false-positive memory routes that either disclosed unrelated personal
  data or abstained from ordinary general questions;
- six false-negative memory routes that skipped required evidence, including
  all four complex grounded cases;
- three truncated 1.7B large responses;
- incomplete but structurally valid large plans;
- one unsupported denial of the current Sunday travel plan; and
- validator rejections for a correct Luma answer, third-person relationship
  wording, an expired-memory fabrication, and a contradiction stated without
  uncertainty.

The Luma rejection is a validator false negative: the raw answer named Luma
and cited the exact record, but the current distinctive-anchor check expected
unrelated date anchors from that record. This should be fixed independently of
model selection.

## Jetson safety result

The 476.66-second run collected 942 Tegrastats samples under an active guard.
The guard would interrupt below 768 MiB free RAM, above 512 MiB swap use, at or
above 68 degrees C, on malformed telemetry, on a boot-ID change, or on a
thermal-trip increment. It did not fire.

| Device metric | Result |
| --- | ---: |
| Peak RAM used | 6,466 / 7,620 MB |
| Peak swap used | 317 / 3,810 MB |
| Peak temperature | 57.937 degrees C |
| Peak GPU use | 99% |
| Thermal-trip increments | 0 |
| Boot ID changed | No |
| Resident models after cleanup | None |

The run began with the fan active at PWM 80 and power mode `15W / 0`. Desktop
pressure put the board slightly outside the earlier conservative model-download
start gate (about 2.47 GiB available and 294 MiB swap used), so no downloads
were attempted and the stricter runtime guard remained active throughout.

## Stored evidence

Raw prompts, generated answers, memory IDs, and telemetry remain in private
owner-only directories outside Git:

- restart run:
  `/home/b2jetson/.local/share/oline-hri/evaluation-runs/winning-pair-memory-20260909T2127p0400`
- adaptive run:
  `/home/b2jetson/.local/share/oline-hri/evaluation-runs/adaptive-qwen06-qwen17-20260909T2138p0400`

Key SHA-256 values:

| Artifact | SHA-256 |
| --- | --- |
| `learn.json` | `9ab6ac1564ece26ca8a7f43f83ecfacba5e79acb8829b780fc7a1705a6d09e25` |
| `recall.json` | `db7b0fd44ba134f45c234d34479e759fcb22513204b312906964d803586cd49d` |
| `observations.jsonl` | `491cb4d5188bc063a68ce4dd1980bc8f6c3204f69912f9bd1a701315d77b2266` |
| `summary.json` | `e50be0b22988f2a9fbe06f83f61dc6ae37454f07af93261970214f469098bdca` |
| `telemetry.jsonl` | `30728d6286842a9bd0acd961b6a6e863f5b0c17e399f5356c2a3ffeccf8ae4ec` |
| `telemetry_summary.json` | `d8572a1759059f95e6dd4911e9e1d4d0c655519af03b4a316d89963614c3582f` |

All fictional test databases were isolated from the configured personal-memory
database. No microphone, speech-to-text, text-to-speech, or physical gesture
was part of this model-and-memory validation.
