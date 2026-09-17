# Loading and model handoffs

This is a read-only investigation of the preserved fresh evaluation, preceding
the candidate repair. No live inference or production setting changes were made.

The existing client already retains large models for the reliable runtime,
skips eviction when the requested model remains resident, serializes peer
eviction before loading its replacement, and invalidates uncertain residency
after transport/response failures. Nine existing offline retention, concurrency
and eviction tests passed. No unsupported client change was introduced.

Across the original and supplementary collections, 137 actual model calls
reported 2,005.204 seconds of backend time, including 1,677.714 seconds of
loading. Of those, 32 consecutive same-model calls reported only 0.071 seconds
of loading in total. All other loading was associated with the 105 initial or
changed-model calls. This identifies orchestration as the useful intervention
point; it does not establish a causal end-to-end speedup.

| Call purpose | Calls | Backend load seconds |
| --- | ---: | ---: |
| Compute classification | 48 | 349.956 |
| Dependency review | 22 | 501.825 |
| Answer generation | 37 | 228.319 |
| Answer review | 30 | 597.614 |

Observed cross-model transitions included 22 compute-to-dependency-review,
15 dependency-review-to-generation, 26 generation-to-answer-review, and
27 answer-review-to-next-compute transitions. Dependency and answer reviews
used the large model; most initial generation used the small model.

Recommended orchestration changes are deterministic compute sizing with
explicit policy provenance, avoiding compute calls for already unresolved
requests, and generation on an already resident large model after dependency
review. Substantive constrained output can select the large generator directly.
Required personal requests without a general fragment still need a valid
generator plan when a populated store contains evidence; they cannot always be
classified as application-only merely because this evaluation used empty stores.

The development launcher in this directory reuses the prior strict device
guards unchanged, defaults to a 12-case cap, and accepts an explicit cap no
greater than 64. Each candidate iteration must have a current source freeze and
a fresh output directory. Its wall timings include guard overhead and cannot
be presented as uninstrumented speech latency.
