# Preserved offline audit correction

The first complete offline analysis, [analysis_blind_v1](analysis_blind_v1/),
is sealed and retained with its nonzero exit status and 24 prompt-check errors.
Its audit incorrectly combined fresh-history validation with a requirement
that the original question appear verbatim inside the generation prompt.

All 24 flagged calls actually contain exactly one system message followed by
one current user message. The already-frozen production helper
`conversation._memory_grounded_request` changes two questions whenever
personal evidence is supplied:

| Original frozen request | Submitted current request |
| --- | --- |
| Who is my mural-painting partner? | Who is My Mural-Painting Partner to me? |
| Who is my biscuit-cutter supplier? | Who is My Biscuit-Cutter Supplier to me? |

The helper's relationship pattern interprets these possessive role phrases as
person strings, title-cases them and appends “to me”. This occurred in both
evidence policies for each generator and repetition: 24 calls in total.
OFF retained the original questions. The wording change is an
evidence-dependent helper effect; semantic neutrality is not established.
The original questions remain the scoring targets in every condition.

The corrected offline audit separately validates the fresh message roles and
parses the actual current-request JSON. For evidence-bearing requests it
accepts only the exact result of the original source-hash-verified helper;
without evidence it requires the original request. Only the six named
functions/constants needed for the pure helper are extracted from the frozen
source. Additional prior user/assistant turns, unrelated rewrites, invalid
JSON, duplicate markers and changed source hashes remain errors. The report
now records all original/submitted wording pairs in
`audit.json:generation_request_rewrites`.

The regression suite passed 24 tests, including six added prompt-control
checks. Independent review is retained in
[analysis_prompt_audit_preflight_v1.json](reviews/analysis_prompt_audit_preflight_v1.json).
All 864 actual generation prompts pass the revised check, with exactly 24
recorded rewrites. No execution source, model, snapshot, request, raw output,
answer rubric, semantic scoring rule, grouping rule or statistical rule was
changed. All eight interrupted attempts remain failures.

The final analysis reuses the first analysis's private blinding seed and
identical public packets. Both independent original review sheets and the
third assistant's adjudication are sealed before the final reviewed analysis
opens the mapping; a separate mapping verification checks complete coverage
and exact semantic binding afterward. Human validation remains pending.
