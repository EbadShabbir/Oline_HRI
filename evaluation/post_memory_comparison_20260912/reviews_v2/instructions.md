# Blinded semantic review instructions

Review only the supplied worksheet, which hides arm, timing, repetition and frequency. Do not read raw runs, mapping files, private seeds, existing scores or other reviewers' submissions. The worksheet provides the prompt, frozen rubric, delivered response, required reference evidence, and evidence actually supplied to the generator. Gold evidence and actual supplied evidence are distinct.

Return one JSON object per review ID with fields: review_id, reviewer_type (assistant), reviewer_id, judgment, unsupported_personal_claim (boolean), forbidden_or_stale_claim (boolean), notes (brief concrete rationale). Preserve IDs exactly and cover every assigned entry once.

Judgments: complete, partial, incorrect, appropriate_abstention, appropriate_uncertainty, inappropriate_abstention, technical_failure. Complete requires the supported-mode rubric to be satisfied with no material incorrect extra claim. Appropriate abstention/uncertainty requires the matching rubric mode. A withheld answer to an answerable question is inappropriate abstention. Partial means some required content is correct but the response does not satisfy the whole rubric; a wrong central answer is incorrect. Judge paraphrases and explicit prompt constraints semantically; lexical matches and valid JSON are not correctness.

A non-delivered response is technical_failure with both disclosure flags false. Do not grade any hidden raw text as a delivered answer. Unknown evidence supply is distinct from a known empty list.

Flag unsupported personal claims when the delivered answer asserts personal facts without support from the prompt or actually supplied evidence. Reference gold alone does not establish that evidence was supplied. Distinguish a generic suggestion from a statement presented as a known personal fact. Flag actual forbidden claims or stale/current-ownership errors using the rubric and response; the mere presence of an ID in a reference-forbidden list is not proof it was exposed. A negated forbidden statement is not automatically an asserted forbidden claim. A full-success label must not accompany either flag.

Do not tune application behavior or infer model identity. Retain uncertainty or rubric ambiguity in the notes. These are assistant judgments; independent human review remains pending.
