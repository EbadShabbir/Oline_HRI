# Independent answer review plan

Review only the assigned delivered-text packet. Do not read implementation,
runtime calls/routes, model identity, latency, withheld text, another reviewer's
work or other artifacts before saving your independent judgments. The packet
states the evidence contract: the personal store is empty; supplied current
facts and benign draft context may be used, but guesses and prior personal
values do not authorize recollection.

For every packet case, evaluate the whole visible request and each frozen rubric
component. Accept valid paraphrases and equivalent arithmetic/formatting only
where the request permits them. Do not introduce hidden demands absent from the
request or frozen rubric. `quality_pass` requires every required component,
factual correctness, requested format and no forbidden unsupported claim.
Execution failures or empty delivered text cannot pass. A generic clarification
is not task completion for a self-contained request. For a truly unresolved
request, a concise question must identify the missing information and avoid
guessing it. Required-memory misses must acknowledge missing evidence; a mixed
request must still provide its independently answerable general component.

Create one JSON object with `reviewer`, `scope`, `packet_sha256`, and `judgments`.
Use exactly one judgment per packet ID in packet order. Each judgment contains:

```json
{
  "id": "packet case ID",
  "quality_pass": false,
  "required_components_pass": [
    {"component": "Exact frozen component text", "pass": false, "reason": "Specific observed evidence"}
  ],
  "useful_general_help": null,
  "flags": [],
  "unsupported_subtypes": [],
  "primary_outcome": "Concise descriptive outcome",
  "rationale": "Explain any failure against the visible request and rubric."
}
```

`useful_general_help` is boolean when the rubric expects a general component,
otherwise null. It measures useful delivered general content, not full quality.
Suggested flags include `unsupported_personal_claim`, `missing_clarification`,
`format_error`, `content_error`, `missing_required_detail`, `execution_error`,
and `unhelpful_answer`; apply only when supported. Unsupported subtypes describe
the actual unsupported claim and may be an empty list. Give every component a
specific pass/fail reason, including passing cases. Preserve the original review
file after submission. Record later disagreement resolutions separately.

Reviews are independent assistant assessments, not human validation. Repeated
known prompts may be recognizable and are not blinded with respect to novelty.
