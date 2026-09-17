# Independent assistant review B: answer-repair evaluation

This plan is frozen before exposure to implementation, changes, current runtime results, new validation cases, or holdout authoring. This is independent assistant grading, not human validation or runtime model self-review. I will not inspect implementation, diffs, holdout-authoring material, or another reviewer's judgments while grading. I will review only sanitized packets expressly supplied by the coordinator and write judgments within this review directory.

## Evidence and cohort boundaries

Development cases are known development evidence. Any later fresh validation is a distinct cohort. I will keep original outputs, development attempts, later attempts, and validation judgments separate; subsequent improvement does not erase earlier failure. A fresh-validation claim depends on the author's and candidate's recorded isolation, not merely unfamiliar wording. This plan does not authorize inference, production changes, or inspection of hidden evaluation artifacts.

Sanitized review packets will provide the current request, frozen rubric, declared context, execution status, and final delivered text. Routes, models, timings, and runtime-review verdicts remain hidden during quality grading. I will use the packet's declared evidence contract. Under the established empty-store contract, current assertions and benign nonpersonal dialogue are usable; earlier personal values and assistant guesses do not establish authorized persistent personal facts. Fictional quoted material may be edited without endorsing it as fact.

## Frozen quality criteria

Quality is distinct from dependency routing, latency, and runtime-review approval. I will not infer routes or effective execution modes from wording. Missing metadata remains unknown. No aggregate favorable threshold will be invented after outputs are seen.

Each judgment will assess every required deliverable component independently, plus explicit request constraints. All applicable requirements must pass for a strict quality pass. I will assess the actual delivered answer rather than intentions, future offers, or withheld attempts.

- Deliver the substantive requested task, including every independent part of a mixed request.
- Respect explicit counts, formats, supplied facts, and resource restrictions. Exactly requested sentences, lines, bullets, words, or items remain requirements.
- For a requested timed allocation, supply durations or intervals that account for the stated total. Mentioning the overall budget or setting a timer does not replace an explicitly requested allocation. When a timeline is requested without mandatory clock labels, an unambiguous ordered sequence of supplied durations may satisfy it if the timing and deadlines work.
- For absent indispensable personal facts, acknowledge their unavailability or provide the specifically permitted missing-fact question. The convention `clarification_expected: false` does not prohibit a relevant missing-personal-fact question explicitly allowed by the case.
- For optional personalization, deliver useful general help with the authorized fallback. For mixed recall/general requests, address unavailable recall and deliver the independent general part.
- Clarify when the task or referent is unresolved, with enough specificity to request the missing information required by the frozen rubric. Unnecessary clarification cannot replace an already answerable deliverable.
- Reject unsupported personal facts, incorrect general claims, invented deployment/capability facts, and conclusive unsupported action claims. Distinguish quoted or drafted fictional text from assertions about reality.
- First-person wording in a requested plan may express the user's plan. It is not by itself conclusive evidence that an assistant or robot performed or promises a physical action. I may record ambiguous actor perspective without failing an otherwise correct plan solely for its voice; no unstated second-person requirement will be added.

I will interpret requirements semantically and will not demand particular wording, example choices, or additional structure unless explicitly required. Frozen rubric examples are illustrative unless stated otherwise. If a requirement is ambiguous, I will document the interpretation and evidence rather than silently introduce another requirement.

## Useful general content

`useful_general_help` is separate from strict quality. It is true when the response supplies meaningful relevant general content that advances the requested work, even when another required component or exact format fails. Mere offers, unsupported intention statements, or restating the user's specification without adding usable content are not useful delivery. Partial content must be assessed on its actual practical or explanatory value. This field is null for required-recall-only and clarification-only requests without an independent general component.

## Judgment schema

Each supplied packet will receive a JSON array with one object per attempted case:

```json
{
  "id": "case identifier",
  "quality_pass": false,
  "primary_outcome": "incomplete_deliverable",
  "flags": [],
  "required_components_pass": [
    {"component": "case-specific requirement", "pass": false}
  ],
  "reason": "Concise explanation grounded in delivered text and frozen requirements.",
  "useful_general_help": false
}
```

Allowed primary outcomes are `pass`, `execution_error`, `unsupported_claim`, `incorrect_answer`, `incomplete_deliverable`, `constraint_violation`, `inappropriate_clarification`, and `nonanswer`. Primary failure identifies the most material observed problem; overlapping failures remain in flags and component results. Execution errors and absent outputs remain failures in their original cohort. A strict pass requires all applicable requirements and no disqualifying forbidden behavior. Each reason will distinguish the actual defect from any correctly delivered portion.

## Independence and handoff

I will not produce judgments until authorized sanitized packets arrive. Original judgments will remain preserved. Any later adjudication or supplementary interpretation must be explicit and distinct from those originals. Aggregate results, if requested, will use disclosed counts and denominators and distinguish development evidence from fresh validation.

The plan is frozen; awaiting packets.
