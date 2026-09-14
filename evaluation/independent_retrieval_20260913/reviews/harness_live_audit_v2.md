# Final independent integration audit before primary collection

This addendum supersedes the provisional execution approval in
`independent_preflight_review.json`. The final source-bound approval is
`independent_preflight_review_v2.json`. Reviewer: independent assistant
`/root/audit_design`; human validation is pending. No primary model output was
seen and this reviewer ran no LLM inference.

The final excluded integration smoke completed all 12 development attempts:
two requests for each of six conditions, with all 12 answers delivered. The
reviewer verified its seal and independently reran the concrete input/model/
evidence/residency audit over preserved raw observations; all checks passed.
The fixtures are a previously used fictional fruit fact and elementary general
arithmetic, separate from all 48 final questions. No semantic quality score
from the smoke enters the primary experiment.

Two earlier excluded smoke artifacts remain sealed. `smoke_v1` contains six
successful small-model attempts and an interrupted pre-large admission wait;
its original audit also wrongly rejected a legitimate extra system message.
`smoke_v2` contains zero attempts following a worker resource-admission
rejection. Neither is merged into the completed smoke or final 864 attempts.
Their sources, outcomes and errors are preserved.

The resolved orchestration uses a standard-library-only waiting supervisor
and fresh guarded model workers. A native-importing parent was found to start
six OS threads; no unsafe post-import fork was adopted. The successful smoke
parent instead had one OS thread, loaded no NumPy/ONNX modules and peaked at
14,872 KiB RSS. This releases duplicate idle runtime memory while retaining
all resource thresholds and separate sole-model worker sessions. The primary
collector executes the same low-overhead supervision pattern.

Every actual session owns the inference lock; the supervisor owns a distinct
batch lock. Workers enforce a shared boot/thermal-trip/power/swap-capacity
baseline. Only proven zero-request resource-admission failures can be retried,
within the bounded ten-minute window, with each rejected artifact retained.
An answered partial session cannot be replaced or spliced into a complete one.
The protocol now states these orchestration details explicitly.

The current protocol also clarifies identical authorized truth background in
blinded packets, preserving common rubrics and separating semantic factuality
from actual-evidence grounding. Runtime questions, records, lifecycle events,
relevance labels and answer rubrics remain as independently reviewed.

The reviewer reran the final 37 focused offline tests after all execution
changes: all passed in 2.806 seconds. The source hash map contains 44 files and
matches the successful smoke's frozen source map. Model default template and
parameter equality are checked during the final execution freeze. No unresolved
collection-blocking source defect remains in this audited snapshot.
