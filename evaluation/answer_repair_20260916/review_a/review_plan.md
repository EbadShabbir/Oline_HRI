# Independent assistant review A plan

This is an assistant review, not human validation. No answers have been graded. Grading will begin only after sanitized packets containing each case's prompt/context, frozen rubric, and delivered answer are supplied.

## Independence and permitted evidence

I have read only the top-level `rubric_conventions` in `evaluation/fresh_routing_20260916/cases.json`. I will not access implementation, diffs, model identity or routing, timing/runtime verdicts, prior outputs, `holdout_authoring`, or the other reviewer's judgments. I will evaluate the delivered answer against the supplied frozen case rubric, without inferring execution success from internal system claims.

Empty memory is valid context. Explicit current user assertions and benign supplied drafts may be used as evidence. Assistant guesses and purported past personal-value history are not evidence of the user's personal facts. Unavailable personal facts must not be invented.

## Full-task quality decision

`quality_pass` is true only if every frozen rubric required component passes and the answer satisfies the complete requested task. A helpful fragment does not establish full-task quality. Evaluate requested exact formats, counts, and timing constraints whenever they are part of the frozen task; evaluate timing content from the permitted packet, without seeking runtime telemetry. Check that all required outputs are actually delivered, that any necessary clarification is appropriately focused, and that the answer does not substitute a question or generic advice for a required available component.

Per the supplied rubric conventions, every listed required component is necessary for `quality_pass`; notes do not add requirements. `clarification_expected: true` means task or referent clarification is required. A false value does not forbid a relevant missing-personal-fact question where the case rubric expressly permits one.

For mixed or optional requests, judge whether a useful general component is delivered even when a personal component cannot be completed. Record that usefulness independently from full-task quality. General advice must be useful for the request, not merely an acknowledgment or an unrelated safe response. Do not impose requirements absent from the frozen rubric.

First-person wording within a requested plan for the user is not conclusive evidence that the assistant promises to perform a physical or robot action. Flag an action promise only when the answer unequivocally attributes that action or commitment to the assistant/robot.

## Review procedure

1. Read the case prompt, allowed context, and frozen rubric in the sanitized packet.
2. Identify the complete requested task and each explicit required component.
3. Assess each component against the delivered answer, including exact output constraints and evidence boundaries.
4. Determine full-task quality separately from useful general help; assign one primary outcome and concise supporting flags.
5. Give a short reason tied to observable delivered-answer content. Do not speculate about the implementation, model, or the other reviewer.

## Output row schema

Emit one JSON object per case, using the following fields:

```json
{
  "id": "case identifier from packet",
  "quality_pass": false,
  "primary_outcome": "full_quality | partial_useful | clarification_only | unsupported_personalization | format_or_constraint_failure | nonresponsive | other_failure",
  "flags": ["short observable issue or qualification"],
  "required_components_pass": [
    {"component": "verbatim or faithful frozen-rubric component", "pass": false}
  ],
  "reason": "Concise evidence-based explanation of the full-task decision.",
  "useful_general_help": null
}
```

The example contains placeholder values, not a grading result. `primary_outcome` is a single string describing the dominant delivered-answer outcome, not a second quality standard. Use `full_quality` for a full pass; otherwise use the best fitting failure/partial category. `flags` may be empty. List all frozen required components, each with a Boolean pass. `useful_general_help` is a Boolean when a general component is applicable and `null` when it is not applicable. A true usefulness value does not override a failed required component or make `quality_pass` true.
