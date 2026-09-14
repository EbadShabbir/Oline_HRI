# CLARA changing-memory results — assistant-reviewed draft

Final input coverage was prepared from verified sealed artifacts and passed process/database identity checks.

288/288 planned checkpoints have explicit attempt records; 283 delivered answers, 0 missing checkpoints. Useful correct delivered responses: 118/288.

Assistant review is complete for the supplied packets; human validation is pending. Null answers are not successful recall or appropriate uncertainty.

| Behavior | Useful correct | Planned | Delivered |
| --- | ---: | ---: | ---: |
| original | 36 | 48 | 48 |
| replacement | 13 | 48 | 43 |
| historical_control | 2 | 48 | 48 |
| uncertainty | 67 | 144 | 144 |

| Integrity outcome | Disclosures | Planned eligible checkpoints | Delivered |
| --- | ---: | ---: | ---: |
| stale_subject_disclosure_after_correction | 21 | 96 | 91 |
| stale_subject_disclosure_current_replacement_questions | 21 | 48 | 43 |
| deleted_subject_disclosure | 39 | 72 | 72 |
| expired_subject_disclosure | 27 | 60 | 60 |
| any_expired_fact_disclosure | 27 | 60 | 60 |

| Group | Useful correct | Planned | Delivered | Missing |
| --- | ---: | ---: | ---: | ---: |
| branch=correction | 36 | 120 | 115 | 0 |
| branch=deletion | 37 | 84 | 84 | 0 |
| branch=expiry | 45 | 84 | 84 | 0 |
| category=appointment | 29 | 48 | 44 | 0 |
| category=dated_event | 14 | 48 | 48 | 0 |
| category=object_location | 26 | 72 | 72 | 0 |
| category=preference | 28 | 72 | 72 | 0 |
| category=relationship | 21 | 48 | 47 | 0 |
| history_mode=fresh | 66 | 108 | 103 | 0 |
| history_mode=retained | 52 | 180 | 180 | 0 |
| expected_kind=historical_control | 2 | 48 | 48 | 0 |
| expected_kind=original | 36 | 48 | 48 | 0 |
| expected_kind=replacement | 13 | 48 | 43 | 0 |
| expected_kind=uncertainty | 67 | 144 | 144 | 0 |
| after_restart | 29 | 108 | 105 | 0 |
| expiry_before | 18 | 24 | 24 | 0 |
| expiry_at | 14 | 24 | 24 | 0 |
| expiry_after | 2 | 12 | 12 | 0 |
| expiry_restart | 11 | 24 | 24 | 0 |

The broad correction exposure row includes legitimate historical-control questions; the current replacement row isolates the 48 current-value questions. Any-expired-fact disclosure includes the subject and independently stored historical control; a never-stored replacement is an unsupported claim, not an expired fact.

Matched retained/fresh history pairs: 108 planned, 108 fully observed. Both succeed: 13; retained only: 3; fresh only: 53; neither: 39.

Validation rejections with no delivered disclosure: 5. Client output-validation rejections without disclosure: 0; freshness rejections without disclosure: 0. This is safe withholding at the delivery boundary, counted separately from useful answers; it does not prove each rejected raw answer was semantically invalid.

Review groups: 214; original agreement: 214; adjudicated disagreements: 0. Exact duplicate packets were grouped without exposing the checkpoint mapping or diagnostics.

Setup disclosure acknowledgments: 36/36. Separate diagnostic answer attempts: 0.

Original statements present in stored histories: {'retained': 144}; actually forwarded in generation messages: {'retained': 94}. Presence in stored history does not establish exposure to a generator.

Started checkpoints lacking final records: 0; never-started missing checkpoints: 0.

Stage findings use recorded database eligibility, real retrieved records, supplied envelopes even on rejected answers, and failing trace spans. A delivered semantic failure with sufficient evidence implicates generation or transformation; the blinded review alone does not distinguish raw-generation semantics from later transformations. Validation rejection is not automatically a validator defect. Consult reviewed_answers.jsonl for raw answers and failure spans.

Results concern the deployed adaptive text path, actual process restart with explicit evaluation history rehydration, and controlled logical-time expiry. They do not establish power-loss recovery or spoken performance. The twelve scenarios, repeated branches and checkpoint pairs are not 288 independent quality samples. Original unfavorable outcomes and failed checkpoints remain in planned denominators.

Detailed counts, model selections and component findings are in metrics.json. All checkpoint answers and judgments are in answers.md and reviewed_answers.jsonl; setup acknowledgments are separate.
