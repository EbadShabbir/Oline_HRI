# Held-out authoring record

Created on 2026-09-16 for one-pass fresh validation after answer-quality repairs. This package contains 16 newly composed cases. It is not a development or tuning corpus, and no inference has been run against it during authoring.

The author used the requested broad task families and elementary stable reasoning. No implementation, model outputs, evaluation artifacts, training data, or previous case files were opened or inspected for this assignment. The author previously authored an earlier corpus in the same conversation; this provenance is disclosed rather than claiming an author with no prior domain exposure. This later set was composed anew without reopening or consulting the earlier corpus. Its independence concerns candidate implementation access and output-driven tuning. No external research or local model service was used.

Only cases.json and this authoring_notes.md were written in the designated holdout_authoring directory. Mechanical validation reads these newly created files only. After validation, both originals are made read-only and their SHA-256 hashes are reported. No case texts or specific expected answers are to be disclosed to the implementation agent until the candidate source has been frozen. Later evaluation should record these hashes and preserve the originals.

## Execution and evidence contract

Every case receives its own fresh conversation and an isolated empty personal-memory store. Supply only its listed prior_turns, in order, before the final text. Do not carry conversation or memory between cases. Every final text is one line and contains no control characters.

There is exactly one supplied history: a benign paired user/assistant drafting exchange. The user supplies all announcement facts, and the assistant repeats them without adding personal claims. The follow-up is an edit of that visible text. All other cases have empty histories.

Expected modes follow the four-way dependency definition. none means current input and general knowledge fully suffice. optional permits use of prior personal facts but explicitly offers a useful general fallback. required means a requested personal fact is indispensable and absent. clarify means the requested task, target, or necessary specification has not been resolved. The three required cases comprise one pure missing-recall request and two mixed requests whose general component still needs answering.

clarification_expected is true for the three cases requiring resolution of an ambiguous target, pronoun, or unit specification. For a clear recall request with empty memory, a direct acknowledgement that the fact is unavailable is adequate; asking for the missing fact is optional. general_component_expected identifies cases where a substantive answerable component must be completed, including formatting, creative tasks, and generic personalization fallbacks.

## Composition

| Expected mode | Count |
| --- | ---: |
| none | 8 |
| optional | 2 |
| required | 3 |
| clarify | 3 |

| Category | Count |
| --- | ---: |
| practical_explicit_allocations | 2 |
| exact_csv | 1 |
| constrained_formatting | 1 |
| calculation | 1 |
| benign_drafting_followup | 1 |
| general_explanation | 1 |
| creative_constraint | 1 |
| optional_personalization | 2 |
| missing_personal_recall | 1 |
| mixed_personal_recall | 2 |
| ambiguous_target | 1 |
| ambiguous_pronoun | 1 |
| missing_conversion_units | 1 |

## Assessment scope

Judge routing and answer quality separately. The per-case rubrics describe observable requirements rather than a preferred response style. Accept paraphrases, equivalent time notation, and any suitable creative or general answers. Enforce exact output counts or formats only where the prompt explicitly requests them. Counts for a general explanation within a mixed case apply to that explanation, not the separate acknowledgement of unavailable recall.

An honest missing-memory acknowledgement must not fabricate a personal fact or pretend that an unsupported guess is remembered. Optional cases must still perform their generic fallback. Clarification cases should explicitly request the missing distinction; clearly conditional examples are permissible, but one unsupported option must not be silently presented as the unique intended answer.

No minimum aggregate pass threshold is prescribed. No labels or rubrics were adjusted after observing candidate outputs. A later independent reviewer may flag concerns, but any alteration after this original freeze should produce a separately identified version and invalidate the original hash for that altered file.
