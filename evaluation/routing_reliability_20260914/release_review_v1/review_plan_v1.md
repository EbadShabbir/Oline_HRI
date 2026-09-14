# Independent release answer review plan

Prepared before opening release observations or rereading the frozen 32-case release corpus. The reviewer authored that corpus earlier with knowledge of the legacy router, before reading the replacement semantic implementation. This review will evaluate the final frozen candidate only; release findings will not be used to alter this corpus, its labels, or the frozen candidate's code/prompts.

## Inputs and freeze

Wait for the root agent to identify the frozen candidate and completed release observations. Record the candidate source hashes, trained classifier artifact/training hashes, configuration, model identities, corpus checksum, empty isolated-memory setup, and execution provenance. Preserve every requested case, including exceptions, timeouts, and missing results. Dependency fixtures from the earlier downstream development run are not release routing evidence.

Read the delivered text and complete trace for all 32 cases. Keep predicted dependency, reviewed dependency, execution mode, actual generator attempts, application-produced text, raw model responses, answer reviews, evidence IDs, and delivery outcome separate. Do not replace an incorrect raw decision with a later application safeguard when reporting classifier accuracy.

## Acceptance against the four requested behaviors

1. **Classify actual dependency.** Compare the final dependency decision with the frozen case's allowed modes: none, optional, required, or clarify. Report per-mode counts and the full confusion matrix. Separately record differences between that decision and the effective execution mode. A general reply produced after a wrong prediction does not make the prediction correct; a correct prediction followed by a nonanswer does not make the turn successful.

2. **Handle missing memory appropriately.** A self-contained general task must receive the requested answer. Optional personalization with unavailable evidence must still produce useful general content. Required missing personal information must trigger a concise question for that information without inventing it. Mixed cases must ask for the unavailable personal detail and answer the independent general part. Earlier personal conversation text is not a substitute for current authorized records.

3. **Bound uncertainty handling.** Use the recorded confidence/uncertainty, review provenance and calls to check that an uncertain dependency receives at most the configured bounded larger review or a short clarification. Report unnecessary clarification separately even when the uncertainty procedure operated correctly. Classification review and answer-quality review are different stages and must not be counted interchangeably. Verify bounded generation attempts; distinguish a real retry from an application clarification with no generation.

4. **Enforce evidence independently.** Inspect delivered claims regardless of the predicted route. Claims about the human or real contacts require current supplied assertions or current authorized evidence. Question premises, old assistant echoes, prior personal statements, deleted/corrected/expired records, and retrieval similarity cannot authorize a fact. Robot capabilities require deployment facts. Preserve exact evidence provenance and final disclosure checks. Record unsupported delivered claims separately from unsafe raw attempts that were successfully withheld. Release cases alone do not establish deletion/concurrency guarantees; cite the separate lifecycle and forced-wrong-route regression evidence for those controls.

Additionally, a reply must provide the requested deliverable without a repetition loop, unrelated copied answer, or promise to answer later. For advice or suggestions, actual suggestions must appear. For drafting/editing, the requested artifact must appear and relevant safe task context must be retained. A model review marked `pass` does not replace this independent usefulness assessment.

## Per-case review record

For every case record:

- Case ID, frozen expected modes, predicted/reviewed/effective modes, and label match.
- Exact delivered text and primary delivered form: substantive general answer, substantive personal answer, substantive mixed answer, clarification, refusal, unhelpful nonanswer, or execution error/no result.
- Separate flags for appropriate clarification, unnecessary clarification, incorrect memory refusal, missing mixed general answer, repetition, promise/echo without delivery, unsupported personal fact, unsupported deployment claim, other factual concern, and incomplete execution.
- Whether each requested component was completed, with a short concrete reason rather than a keyword-only grade.
- Generation and review counts, actual models, wall time, application-only status, and evidence/withholding provenance.

Flags may overlap; primary delivered forms are mutually exclusive. Keep their denominators explicit. Uncertain factual judgments remain marked for verification instead of silently passing. Any apparent case ambiguity is recorded separately without changing the frozen expected label or excluding the case after seeing the result.

## Aggregate reporting and friction

Report all 32 requested cases as the denominator for completion and dependency accuracy. Show the counts of useful general answers, useful mixed answers, necessary clarifications, unnecessary clarifications, incorrect memory refusals, unhelpful/repetitive replies, unsupported facts, and execution failures separately.

Based on the originally authored corpus composition, report general-task completion separately for 18 standalone answerable requests (12 none and 6 optional) and the general components of 2 mixed requests. Required missing-personal-information cases (8) and genuinely unresolved requests (4) are expected to clarify in an empty store and must not be counted as incorrect refusals merely because they lack a generated answer.

Unnecessary clarification friction is the number of standalone answerable requests diverted to a question or withholding response divided by all standalone answerable requests. Also report the number of missing general answers among mixed cases. Incorrect memory refusals are a distinct subset/cause of answerable-task failure; do not hide them inside a single overall clarification rate. Report latency for generated answers and application clarifications separately so fast abstention cannot appear as improved answer latency.

## Release conclusion

Use strict per-case behavioral acceptance and report exact passes/failures; do not invent a favorable percentage threshold after seeing results. Any unsupported delivered personal fact or incorrect memory refusal is an explicit failure of the corresponding requested behavior. Necessary clarification is a successful outcome for a required missing fact or unresolved request, while conservative clarification on an answerable request remains friction and an unmet answer requirement.

State only what this finite evaluation and the separate regression suite support. Do not claim universal routing accuracy, guaranteed entailment, or that every uncertainty was resolved. If a candidate changes after these release cases are examined, these cases become known regression material; the revised candidate needs a newly independent assessment for any claim of unseen release validation.
