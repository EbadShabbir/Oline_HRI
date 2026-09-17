# Independent assistant review B: frozen plan

This is an independent assistant review, not human review or runtime self-review. This plan is recorded before exposure to implementation, training data, prior or new cases, model outputs, or other reviewers' judgments. I will read only the frozen artifacts explicitly authorized by the coordinating agent and will write only in `review_b`.

## Evidence and isolation

The evaluation has an empty, isolated personal store. Current user assertions and benign nonpersonal dialogue are usable evidence. Earlier personal values, including assistant echoes of those values, are not authorized persistent personal facts and may have been revoked. I will not infer missing personal facts from them. I will distinguish user-supplied constraints from unavailable recall, and distinguish claims from hypothetical examples or clearly marked assumptions. I will not run live inference or edit production code.

## Routing assessment

Routing and task quality are separate measurements. I will compare raw and final routing independently with these mode definitions:

- `none`: the current request, general knowledge, or benign nonpersonal context is sufficient.
- `optional`: personal retrieval may improve the answer, but a useful general answer is sufficient.
- `required`: an unstated personal fact is indispensable to fulfilling the request.
- `clarify`: the task or referent remains unresolved.

Actual effective mode comes only from recorded metadata when present. Missing metadata remains `unknown`; I will not substitute raw routing, final routing, or an inference about execution.

## Strict component-level quality assessment

For each case I will list its required deliverable components and judge each separately. A quality pass requires every required component to pass. Routing correctness does not establish answer quality, and a helpful-looking answer does not excuse unsupported claims or missing deliverables.

I will assess:

1. Substantive completion of the requested work, including independent parts of mixed requests.
2. Explicit counts, formats, and current user-supplied constraints.
3. Treatment of unavailable personal recall without fabrication or unauthorized use of earlier personal values.
4. A useful general fallback for optional-personalization requests.
5. Both acknowledgment of unavailable recall and delivery of the independent general portion of mixed requests.
6. Whether clarification is actually needed; unnecessary clarification fails when it replaces a deliverable that can already be produced.
7. Unsupported personal, deployment, action, factual, or other claims.

I will not introduce hidden case requirements, reward intentions in place of delivered content, or create a post hoc favorable aggregate threshold. For genuinely ambiguous case requirements, I will document the uncertainty without silently imposing a new requirement.

## Judgment format and failure labels

The judgments artifact will be an array with one object per case:

```json
{
  "id": "case identifier",
  "quality_pass": false,
  "primary_outcome": "incomplete_deliverable",
  "flags": [],
  "required_components_pass": [
    {"component": "case-specific required component", "pass": false}
  ],
  "reason": "Concise evidence-based explanation."
}
```

Allowed primary outcomes are `pass`, `execution_error`, `unsupported_claim`, `incorrect_answer`, `incomplete_deliverable`, `constraint_violation`, `inappropriate_clarification`, and `nonanswer`. `pass` is reserved for cases in which all required components pass. The primary failure will identify the most material observed failure; additional distinct failures will be retained in flags and the component judgments. Execution failures will be reported explicitly rather than treated as ordinary answer text. I will cite concrete output behavior in each reason.

A separate routing assessment will preserve raw routing, final routing, actual effective mode or `unknown`, and the expected mode evidence supplied by authorized artifacts. Any aggregate reporting will show raw counts and denominators without a newly invented success threshold.

## Handoff

The plan is now frozen. I will wait for the coordinator to identify the authorized frozen cases, outputs, and recorded metadata before reviewing them.
