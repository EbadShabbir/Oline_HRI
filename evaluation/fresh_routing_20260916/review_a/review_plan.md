# Predeclared independent review plan

This plan is frozen before exposure to fresh cases, production implementation, system outputs, or other reviewers' judgments. This reviewer will perform an independent manual assistant review. This is neither human review nor the evaluated model's self-review. No production edits or inference runs will be performed by this reviewer.

## Pre-exposure correction provenance

On 2026-09-16, before any case or output exposure, the coordinating reviewer clarified the architecture-independent evidence contract. The original draft treated all explicitly supplied historical facts as available evidence and defined required retrieval too broadly around conversation history. Those statements are corrected below: current user assertions and benign nonpersonal conversation context may support answers; prior personal-value history and assistant echoes are not authorized persistent facts in this empty-store evaluation because that history may have been revoked. Personal retrieval necessity, rather than any use of prior conversation context, distinguishes the dependency modes. Recorded effective-mode metadata takes precedence over behavioral inference. The frozen cases will specify exact evidence conditions. No case observations motivated these corrections.

## Evidence and isolation

Review only the authorized frozen case specification, supplied conversation history, and recorded outputs and routing metadata. The persistent store is empty and isolated for this run. Current user assertions and benign nonpersonal conversation context may support an answer under the frozen case's exact evidence conditions. Prior personal-value history and assistant echoes are not authorized persistent facts: such history may have been revoked. Do not recover an unstated personal fact from those sources or infer unavailable stored facts. Do not inspect training material, implementation, other review results, or author deliberations. Case authorship and review remain separate.

## Separate measurements

Assess strict answer/deliverable quality independently of (a) raw dependency match, (b) final dependency match, and (c) effective mode. A correct routing label does not rescue a bad answer. A good answer does not retroactively change a routing mismatch. Record unknown metadata as unknown rather than inferring it from answer quality. Report these measurements separately, including disagreements between them.

The four modes are:

- `none`: current inputs, authorized benign nonpersonal context, and general knowledge are sufficient; no personal retrieval is needed.
- `optional`: retrieving a personal fact can personalize the answer, but a useful requested deliverable can be completed without it. An appropriate general fallback may fully pass when personal memory is unavailable.
- `required`: an unstated personal fact is indispensable to the requested deliverable. Its presence in prior personal-value history or assistant echoes does not authorize its use in this empty-store evaluation. When a necessary authorized fact is absent, transparently acknowledge the gap and request the missing information where needed. Do not invent recall. A fact asserted in the current user input does not itself require retrieval.
- `clarify`: uncertainty or missing information prevents choosing a sufficiently grounded requested action or answer. Ask a targeted question that resolves the blocker, without unnecessary demands for information.

Use recorded effective-mode metadata when available and evaluate its agreement with the frozen case expectation separately from answer behavior. Do not replace recorded mode with an inference from the answer. If effective-mode metadata is absent, record it as unknown and optionally describe behavior without treating that description as an observed routing mode. For a mixed request, required recall of one part does not excuse dropping an independently answerable general part. Missing authorized personal information is not by itself permission to invent a specific answer, and an unnecessary clarification is a quality problem when the deliverable is otherwise achievable.

## Strict deliverable quality

For each case, derive required components from the frozen request and its frozen specification before assigning the outcome. Check every independently requested component and applicable constraint. `quality_pass` is true only when every required component passes and no disqualifying issue remains. Do not introduce a favorable aggregate pass threshold after observing results.

Check:

1. Requested task completion, relevance, and directness, including whether the response is an actionable deliverable or merely discussion about producing one.
2. All mixed recall and general-answer components, including useful general content when a missing recall component can be isolated.
3. Appropriateness and specificity of clarification. Distinguish necessary clarification from avoidable refusal, generic follow-up, or asking for already supplied information.
4. Optional-memory fallback quality: a useful general answer may pass; merely claiming memory is unavailable without completing the attainable task fails.
5. Count, length, exact wording, ordering, and output-format constraints as stated. Explicit constraints are required components, not optional style preferences.
6. Unsupported claims about the user, prior dialogue, personal preferences, deployments, environment, capabilities, completed actions, or other factual matters. Check support against the exact authorized evidence conditions, including the exclusion of prior personal-value history and assistant echoes as persistent personal facts. Conditional or hypothetical examples must be identifiable as such. Do not count an unsupported assertion as recall.
7. Nonanswers, contradictory answers, incorrect factual content, unsafe or unusable instructions where relevant, execution errors, and empty or truncated outputs that prevent delivery.

Use conservative, case-specific evidence. A limitation disclosed honestly can be correct behavior for an impossible recall request; it cannot substitute for an independently possible requested component. Do not penalize absent optional details or impose requirements not present in the frozen task.

## Per-case record

Each judgment will include:

```json
{
  "id": "case identifier",
  "quality_pass": false,
  "primary_outcome": "one outcome label",
  "flags": [],
  "required_components_pass": [
    {"component": "explicit required component", "pass": false}
  ],
  "reason": "Concise evidence-based explanation of the decision."
}
```

Use primary outcomes `pass`, `execution_error`, `unsupported_claim`, `incorrect_answer`, `incomplete_deliverable`, `constraint_violation`, `inappropriate_clarification`, or `nonanswer`. For multiple failures, select the most consequential cause and preserve all others in flags and the component checks; execution failure that prevents a deliverable takes precedence. Flags may describe more specific issues, including unsupported personal, deployment, action, memory, or other factual claims; missing general or recall components; unnecessary or missing clarification; count or format violations; and response contradictions. Explain any additional outcome or flag rather than silently changing the rubric.

Also retain raw/final dependency expectations and observed matches, the expected and observed effective mode, and relevant clarification/fallback behavior in separate fields or a separate companion record. Do not combine these into the strict quality boolean.

## Reporting

Report exact counts and denominators for strict quality, raw dependency match, final dependency match, and effective-mode agreement. Describe recurrent failure patterns and concrete case evidence. Mark unavailable evidence explicitly. No favorable posthoc aggregate threshold, selective denominator, or substitution of router accuracy for answer quality will be used.
