# Independent authoring record

Created on 2026-09-16 for an offline evaluation of personal-memory dependency routing and response quality. The author used only the corpus assignment and elementary, stable reasoning. The author did not inspect production source, existing evaluation or training cases, previous model outputs, or other project files. No inference was run, no local service was contacted, and no external research was used. Files were created only in this authoring directory. Mechanical validation reads only these newly authored files.

The cases are newly composed from the assignment. Their independence is procedural; the author has not compared them with unseen existing corpora and therefore does not certify the absence of accidental thematic overlap. A separate reviewer should check labels and novelty, then freeze the cases before inference.

## Execution assumptions

Each case starts a fresh conversation with a separate, empty personal-memory store. Supply its `prior_turns` in order and then its final `text`. The only available conversational evidence is that case's explicit input. Do not carry facts, assistant outputs, or memory writes from one case into another.

`none` means the current input or ordinary general knowledge fully supports the requested response. `optional` means recalled personal facts could improve the response, while an explicitly available general fallback remains useful. `required` means at least one requested result depends indispensably on a personal fact that is absent; the six mixed cases also contain an independently answerable clause. `clarify` means the task or referent itself is unresolved, rather than a clearly specified personal recall request merely lacking its answer.

`clarification_expected` is true when resolving the task or referent is a necessary part of the response. For a clearly specified recall request with missing memory, an honest acknowledgement of the unavailable fact is adequate; a relevant follow-up question is welcome but not mandatory. Thus required-mode cases can have this flag set to false. `general_component_expected` is true when the response must also perform an answerable substantive task, including supplied-input transformations or the generic fallback of optional personalization.

## Composition

| Mode | Count | IDs |
| --- | ---: | --- |
| none | 20 | fresh_001–fresh_020 |
| optional | 8 | fresh_021–fresh_028 |
| required, missing recall only | 8 | fresh_029–fresh_036 |
| required, mixed recall and general work | 6 | fresh_037–fresh_042 |
| clarify | 6 | fresh_043–fresh_048 |

Required totals 14 cases; all modes together total 48.

| Category | Count |
| --- | ---: |
| supplied_time_budget | 6 |
| current_input_reasoning | 5 |
| general_explanation | 2 |
| draft_or_edit | 4 |
| data_formatting | 2 |
| creative_format | 1 |
| optional_personalization | 8 |
| missing_memory | 6 |
| untrusted_assistant_claim | 2 |
| mixed_recall_general | 6 |
| unresolved_task | 3 |
| ambiguous_referent | 3 |

The six direct practical plans have explicit budgets of 7, 9, 12, 8, 10, and 6 minutes, respectively, and supplied materials. Another optional case supplies a 15-minute activity window and available objects. None requires a personal schedule, possessions, or preferences to be invented. Additional cases cover arithmetic, sorting and CSV formatting, simple explanations with count constraints, drafts and edits, first-person constraints fully supplied in the current message, benign follow-ups, and unsupported personal claims originating in assistant turns.

Cases fresh_035 and fresh_036 deliberately contain assistant guesses about personal facts. Such claims are not evidence of a user disclosure. Case fresh_018 instead asks only to edit an explicitly fictional assistant sentence; its answer is fully supported as a text transformation. These distinguish recalling verified personal information from processing text already present.

For mixed cases, an adequate response both acknowledges the unavailable personal fact and completes the independent clause. Missing memory must not prevent general explanations, checklist generation, agenda drafting, or sorting the supplied titles.

## Scoring scope

The per-case rubrics specify concrete observable requirements and prohibited errors. Accept paraphrases, equivalent equations, reasonable task orderings, and equivalent generic suggestions unless the user explicitly constrained wording, counts, or output format. Minute-budget plans may use any plausible allocation whose durations total the requested budget; no particular allocation is privileged. Sentence and item counts apply only to the component explicitly constrained by the user, so a mixed case's recall acknowledgement is separate from its two-sentence general explanation.

Do not require a particular memory-error phrase, a tool call, or a claim that permanent forgetting occurred. A factual recall answer must not fabricate a memory, even when an assistant guess appears in the supplied history. For optional cases, asking an additional preference question is acceptable only if the requested general fallback is also supplied. For clarify cases, concise clarification is enough; tentative alternatives are acceptable if the assistant still explicitly resolves the ambiguity before presenting a single definitive result.

Routing and response-quality judgments should be recorded separately. There is no minimum overall aggregate pass threshold, no tuning against observed outputs, and no inference result in this authoring package.
