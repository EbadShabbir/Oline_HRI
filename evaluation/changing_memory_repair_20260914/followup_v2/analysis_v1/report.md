# CLARA changing-memory repair — targeted matched regression

Final input coverage was prepared from verified sealed artifacts and passed process/database identity checks.

24/24 planned checkpoints have explicit attempt records; 24 delivered answers, 0 missing checkpoints. Useful correct delivered responses: 24/24.

Assistant review is complete for the supplied packets; human validation is pending. Null answers are not successful recall or appropriate uncertainty.

| Behavior | Useful correct | Planned | Delivered |
| --- | ---: | ---: | ---: |
| original | 4 | 4 | 4 |
| replacement | 4 | 4 | 4 |
| historical_control | 4 | 4 | 4 |
| uncertainty | 12 | 12 | 12 |

| Integrity outcome | Disclosures | Planned eligible checkpoints | Delivered |
| --- | ---: | ---: | ---: |
| stale_subject_disclosure_after_correction | 0 | 8 | 8 |
| stale_subject_disclosure_current_replacement_questions | 0 | 4 | 4 |
| deleted_subject_disclosure | 0 | 6 | 6 |
| expired_subject_disclosure | 0 | 5 | 5 |
| any_expired_fact_disclosure | 0 | 5 | 5 |

| Group | Useful correct | Planned | Delivered | Missing |
| --- | ---: | ---: | ---: | ---: |
| branch=correction | 10 | 10 | 10 | 0 |
| branch=deletion | 7 | 7 | 7 | 0 |
| branch=expiry | 7 | 7 | 7 | 0 |
| category=relationship | 24 | 24 | 24 | 0 |
| history_mode=fresh | 9 | 9 | 9 | 0 |
| history_mode=retained | 15 | 15 | 15 | 0 |
| expected_kind=historical_control | 4 | 4 | 4 | 0 |
| expected_kind=original | 4 | 4 | 4 | 0 |
| expected_kind=replacement | 4 | 4 | 4 | 0 |
| expected_kind=uncertainty | 12 | 12 | 12 | 0 |
| after_restart | 9 | 9 | 9 | 0 |
| expiry_before | 2 | 2 | 2 | 0 |
| expiry_at | 2 | 2 | 2 | 0 |
| expiry_after | 1 | 1 | 1 | 0 |
| expiry_restart | 2 | 2 | 2 | 0 |

The broad correction exposure row includes legitimate historical-control questions; the current replacement row isolates the 4 current-value questions. Any-expired-fact disclosure includes the subject and independently stored historical control; a never-stored replacement is an unsupported claim, not an expired fact.

Matched retained/fresh history pairs: 9 planned, 9 fully observed. Both succeed: 9; retained only: 0; fresh only: 0; neither: 0.

Validation rejections with no delivered disclosure: 0. Client output-validation rejections without disclosure: 0; freshness rejections without disclosure: 0. This is safe withholding at the delivery boundary, counted separately from useful answers; it does not prove each rejected raw answer was semantically invalid.

Review groups: 11; original agreement: 11; adjudicated disagreements: 0. Exact duplicate packets were grouped without exposing the checkpoint mapping or diagnostics.

Setup disclosure acknowledgments: 3/3. Separate diagnostic answer attempts: 0.

Original statements present in stored histories: {'retained': 14}; actually forwarded in generation messages: {}. Presence in stored history does not establish exposure to a generator.

Started checkpoints lacking final records: 0; never-started missing checkpoints: 0.

Stage findings use recorded database eligibility, real retrieved records, supplied envelopes even on rejected answers, and failing trace spans. A delivered semantic failure with sufficient evidence implicates generation or transformation; the blinded review alone does not distinguish raw-generation semantics from later transformations. Validation rejection is not automatically a validator defect. Consult reviewed_answers.jsonl for raw answers and failure spans.

Results concern the deployed adaptive text path, actual process restart with explicit evaluation history rehydration, and controlled logical-time expiry. They do not establish power-loss recovery or spoken performance. The 1 scenarios, repeated branches and checkpoint pairs are not 24 independent quality samples. This targeted matched regression selected scenarios after baseline failure inspection; it is not held-out evaluation. Original unfavorable outcomes and failed checkpoints remain in planned denominators.

Detailed counts, model selections and component findings are in metrics.json. All checkpoint answers and judgments are in answers.md and reviewed_answers.jsonl; setup acknowledgments are separate.
