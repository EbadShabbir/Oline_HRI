# Response-quality temperature A/B v3 gate report — 2026-09-08

## Verdict

The held-out seed-46 gate failed and is permanently excluded from temperature
selection. Run `10d27412f6dd4ded9faa44541973020e` completed both declared arm
slots, but neither candidate satisfied the preregistered semantic gate. No
seed-43/44/45 comparison output was collected under v3.

## Frozen blinded review

The immutable `paired_review.jsonl` SHA-256 is
`f0187bc93b43012b323d03284cd8b1e027f214231fa05438001cfb167da94457`.
The runtime console exposed an arm name beside its status, so the operator was
excluded as a reviewer. Two fresh-context reviewers independently received
only the anonymized review file and its rubric. Both judged candidate 1
incorrect but preferable, and candidate 2 incorrect:

- Candidate 1 supplied two chronological dated entries, exact citation status,
  and the correct later-event conclusion, but did not say that the tea
  preference changed to ginger.
- Candidate 2 failed and supplied no speech or exact citation.

Their consensus was frozen in
`response_quality_temperature_ab_v3_memory_gate_20260908_blind_judgments.json`
before `pair_key.json`, observations, or raw output were opened.

## Unblinded diagnostics

The key maps candidate 1 to temperature `0.2` and candidate 2 to temperature
`0.0`.

- Temperature `0.0` reached the configured client deadline: the recorded
  backend wall time was 301.010 seconds and the attempt remained an
  `OllamaTimeoutError`. Contemporaneous Ollama logs show that the server later
  completed the same request with HTTP 200 after about 317 seconds, roughly 16
  seconds too late. That late response is not recovered or scored. Its active
  decode was only 80 tokens and about 20 seconds; a GPU-discovery watchdog
  timeout, near-exhausted swap, and a desktop GPU-process crash indicate a long
  host/runtime stall rather than temperature-specific slow decoding.
- Temperature `0.2` completed in 115.959 seconds with `done_reason=stop`, 93
  output tokens, both required records supplied and cited exactly, no fallback,
  no truncation, no ID/alias leak, and no normalization event. Its delivered
  speech nevertheless omitted the mandatory new preference value.

The timeout remains a failed arm outcome because infrastructure-invalidating
criteria were not preregistered for that condition. The successful arm also
remains a semantic failure. Neither arm is retried or reused.

## Prospective correction

The omission exposed a benchmark contract mismatch: the v1 prompt asked when
the preference changed while its hidden rubric additionally required what it
changed to. The v3.1 suite corrects the request without disclosing the answer
and leaves the rubric, forbidden claim, required evidence, sanitizer, and
application validators unchanged.

The 300-second large-model budget was provisional and can be exhausted by a
320-token cold request on this Jetson even when decoding itself is healthy. The
v3.1 baseline fixes the same 600-second transport budget for both arms. It also
makes per-attempt console progress arm-opaque. These changes are tested and
preregistered before any v3.1 inference.

V3.1 uses the deterministic next unused qualification seed, 47. Seed 46 has
been inspected and cannot be held out again; seed 47 is a gate only and will
not enter the nine-pair score. The original comparison seeds 43, 44, and 45
remain unobserved and reserved.

## Private artifacts

The immutable run artifacts remain at
`/home/b2jetson/oline-hri-response-quality-ab-v3-memory-gate-20260908`.
Their hashes are recorded in that directory's `manifest.json`.
