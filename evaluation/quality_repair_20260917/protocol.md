# Answer-quality repair validation, 17 September 2026

The baseline is Git commit `e3985480cc361b42b469c395f2d9139fcc9ca86a`.
Its latest clean recovery scored 12/16 final dependency routes, 4/16 complete
answers and 4/16 combined successes. These sixteen prompts and their outcomes
have already been observed. They are development and regression evidence for
this repair cycle, never fresh validation. Earlier attempts, including resource
failures, their original grading and their manifests remain immutable.

## Development and source freezing

`known_cases.json` is an exact byte copy of the prior recovery's sixteen cases,
including declared histories, expected modes, rubrics and order. Archive each
candidate and all tests before a known-case iteration; use a new directory for
every run. Preserve every attempt, including withheld generations, parser or
review failures, operational aborts and unsuccessful repairs. Report every
iteration separately. Passing known cases may motivate further repair but does
not establish generalization.

After development and appropriate offline checks, archive the final candidate
without opening the independent holdout. The separately tasked author prepares
twenty new cases without reading implementation, earlier cases or their outputs.
The specified dependency counts are ten `none`, three `optional`, three
`required` (including two mixed requests), and four `clarify`. General tasks
include exact formatting, arithmetic, faithful draft changes, supplied-resource
or timing plans, and basic world/physical explanations. The author supplies only
artifact paths, hashes and counts before the final candidate is frozen.

Record the final source freeze and the author's exact case and note hashes
before the first semantic read of those files. `prepare_holdout.py` verifies the
live and archived candidate and authored hashes before parsing the cases, then
records the opening and creates a separate cohort using that same candidate.
Any objective setup defect is recorded before inference; do not alter tasks or
rubrics to accommodate candidate behavior. Any production change after opening
ends the unseen status of this holdout for that changed candidate and requires
an explicitly separate repair cycle for new generalization claims.

## Execution and device limits

Seal exact case order, candidate source, protocol, reviewer plan, analyzer and
independent auditor before each cohort. Use the normal learned conversation
policy, configured Qwen model pair, pinned BGE CPU embeddings, existing model
options, context/output budgets and isolated empty personal store. Do not inject
expected modes, rubrics or case identifiers into runtime prompts. No model,
generation, power, fan or guard-limit change is part of this evaluation.

Use the existing three exclusive inference leases and no concurrent inference.
Stage 2 startup requires at least 2 GiB available RAM, at most 768 MiB swap in
use, temperatures below 55 C, running fan, 15 W mode 0 and no resident model.
Runtime requires at least 768 MiB available RAM, at most 1 GiB swap in use,
temperatures below 68 C, at most one resident model and unstalled 500 ms
telemetry. Retain the same boot, thermal-trip and configured swap capacity
invariants. The existing guard and cleanup implementation remains unchanged.
Declare exactly sixteen or twenty as the cohort cap, below the absolute cap
of 64. The guarded launcher must use a new output directory.

Previously authorized cleanup may be used only within its existing scope:
close idle software-management applications and temporarily cycle the same
existing swap devices after verifying adequate headroom and no package
transaction. Preserve sizes/priorities and restore disabled devices in a finally
block. Record any such action separately. Do not weaken admission or runtime
limits to obtain a result. A clean bounded run does not establish duration
stability, and a later recovery never replaces an earlier failed attempt.

## Review, measurement and reporting

Two independent assistant reviewers grade the final known replay and fresh
holdout using the preregistered `review_plan.md`. Earlier development iterations
may use one independent review plus root assessment; label this distinction.
Review packets contain request, declared history, frozen rubric, complete
delivered text and execution status. They hide source, model identity, route,
runtime review verdict, rejected generations, timing and the other reviewer.
The root implementer may adjudicate disagreements with explicit recorded reasons;
root is not blinded. Assistant agreement is not human validation.

Score strict answer quality against the entire original request, final route
agreement separately, and combined success only when both pass. Invented prior
personal facts fail even if plausible or approved by the runtime reviewer.
Missing clarification, requested factual details, correctness or exact formatting
also fail strict quality. Useful partial general content is a separate measure.
Errors and missing outputs remain in all planned-case denominators. Do not
replace strict scores with partial-usefulness scores or average across cohorts.

Record complete text-turn wall time, including guard overhead, with n, median
and p95 using linear interpolation at `(n-1)*q`. Split generated delivery,
application-only delivery, full-quality outcomes and combined successes. Retain
raw backend load/call durations and actual model-call role/count provenance;
do not infer calls that did not occur. Historical before/after latencies are
descriptive, not a randomized causal speed comparison.

Independently audit exact case/source/model hashes, all attempts, isolated empty
memory, evidence boundaries, arithmetic, denominators, model-call bounds,
resource telemetry and successful model cleanup. The auditor does not import
the analyzer. Operational success, complete measurement and answer quality are
distinct reported properties. No predetermined release-quality pass threshold
is invented after seeing outputs; report counts and every remaining failure.

Microphone/transcription, full audio latency, automatic memory capture, live
populated-memory behavior and broad robot validation remain outside this text
evaluation. Preserve the exact baseline repository index bytes using
`baseline_snapshot/manifest.json` when updating the mutable README/results index.
