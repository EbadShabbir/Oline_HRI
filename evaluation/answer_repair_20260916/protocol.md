# Router and answer repair validation

The user requested improvement after the 16 September fresh evaluation. Its
original cases, observations, reviews and seals remain untouched. Those cases
are now development evidence, not a new holdout. Production changes must retain
personal evidence authorization, disclosure freshness, trace provenance and
bounded retries. No model, power, swap, fan or device-limit change is planned.

First run a 12-case known development selection, frozen in
`development_cases_v1.json`, after offline tests. Archive exact source per
iteration; never overwrite an unsuccessful attempt or claim it was unseen.
Use original prompt bytes, including LF: the proposed input contract accepts LF
while retaining other control-character restrictions. Development outcomes may
inform further changes, followed by appropriate offline verification.

Freeze the final repaired candidate before opening an independently authored
16-case holdout. Its author receives task-family counts but no implementation,
previous prompts or outputs. The holdout covers eight general/current-input
tasks, two optional-personalization tasks, three required personal/mixed tasks,
and three unresolved requests. Authoring artifacts are sealed before root sees
their contents. Any objective pre-inference setup correction must be recorded;
do not change tasks or rubrics to match candidate behavior.

Validate the final candidate once on all 48 known original cases and once on
the 16 fresh cases, separately. Freeze case order and hashes before each run.
Use isolated empty stores, the current configured Qwen pair and BGE CPU
embeddings, normal generation settings and serialized model residency. The
guarded launcher defaults to 12 attempts and has a declared maximum of 64;
each cohort must specify its own bounded count. It retains the prior Stage 2
admission/runtime resource limits and cleanup checks. No concurrent inference.

Preserve every attempt and withheld output. Grade delivered text against each
case's original full-task criteria, separately from final dependency agreement.
Success on both requires both. Errors and missing outputs stay in denominators.
Independent assistant reviews receive request, rubric, declared context and
delivered text, with model identity, timing, route and runtime verdict withheld.
Preserve original judgments and explicitly adjudicate disagreements. This is not
human validation or a representative population estimate.

Report complete text-turn latency with sample size, median and p95, separately
for generated/application replies and complete-quality outcomes. Use linear
interpolation at `(n-1)*q`, retaining backend load/call durations and telemetry.
Include model-call counts and actual roles; omitted compute calls must never
acquire fabricated generations. Compare the 43 unchanged formerly valid prompts
as a matched descriptive subset; the five formerly invalid prompts are newly
covered, not previously executed model answers. Historical sessions are not a
randomized causal latency experiment. Keep known development and fresh holdout
results separate, and report remaining failures candidly.
