# CLARA changing-memory repair — targeted matched regression

Final input coverage was prepared from verified sealed artifacts and passed process/database identity checks.

96/96 planned checkpoints have explicit attempt records; 94 delivered answers, 0 missing checkpoints. Useful correct delivered responses: 92/96.

Assistant review is complete for the supplied packets; human validation is pending. Null answers are not successful recall or appropriate uncertainty.

| Behavior | Useful correct | Planned | Delivered |
| --- | ---: | ---: | ---: |
| original | 16 | 16 | 16 |
| replacement | 12 | 16 | 14 |
| historical_control | 16 | 16 | 16 |
| uncertainty | 48 | 48 | 48 |

| Integrity outcome | Disclosures | Planned eligible checkpoints | Delivered |
| --- | ---: | ---: | ---: |
| stale_subject_disclosure_after_correction | 0 | 32 | 30 |
| stale_subject_disclosure_current_replacement_questions | 0 | 16 | 14 |
| deleted_subject_disclosure | 0 | 24 | 24 |
| expired_subject_disclosure | 0 | 20 | 20 |
| any_expired_fact_disclosure | 0 | 20 | 20 |

| Group | Useful correct | Planned | Delivered | Missing |
| --- | ---: | ---: | ---: | ---: |
| branch=correction | 36 | 40 | 38 | 0 |
| branch=deletion | 28 | 28 | 28 | 0 |
| branch=expiry | 28 | 28 | 28 | 0 |
| category=appointment | 24 | 24 | 24 | 0 |
| category=object_location | 24 | 24 | 24 | 0 |
| category=preference | 22 | 24 | 24 | 0 |
| category=relationship | 22 | 24 | 22 | 0 |
| history_mode=fresh | 34 | 36 | 35 | 0 |
| history_mode=retained | 58 | 60 | 59 | 0 |
| expected_kind=historical_control | 16 | 16 | 16 | 0 |
| expected_kind=original | 16 | 16 | 16 | 0 |
| expected_kind=replacement | 12 | 16 | 14 | 0 |
| expected_kind=uncertainty | 48 | 48 | 48 | 0 |
| after_restart | 34 | 36 | 34 | 0 |
| expiry_before | 8 | 8 | 8 | 0 |
| expiry_at | 8 | 8 | 8 | 0 |
| expiry_after | 4 | 4 | 4 | 0 |
| expiry_restart | 8 | 8 | 8 | 0 |

The broad correction exposure row includes legitimate historical-control questions; the current replacement row isolates the 16 current-value questions. Any-expired-fact disclosure includes the subject and independently stored historical control; a never-stored replacement is an unsupported claim, not an expired fact.

Matched retained/fresh history pairs: 36 planned, 36 fully observed. Both succeed: 34; retained only: 0; fresh only: 0; neither: 2.

Validation rejections with no delivered disclosure: 2. Client output-validation rejections without disclosure: 0; freshness rejections without disclosure: 0. This is safe withholding at the delivery boundary, counted separately from useful answers; it does not prove each rejected raw answer was semantically invalid.

Review groups: 47; original agreement: 47; adjudicated disagreements: 0. Exact duplicate packets were grouped without exposing the checkpoint mapping or diagnostics.

Setup disclosure acknowledgments: 12/12. Separate diagnostic answer attempts: 0.

Original statements present in stored histories: {'retained': 56}; actually forwarded in generation messages: {}. Presence in stored history does not establish exposure to a generator.

Started checkpoints lacking final records: 0; never-started missing checkpoints: 0.

Stage findings use recorded database eligibility, real retrieved records, supplied envelopes even on rejected answers, and failing trace spans. A delivered semantic failure with sufficient evidence implicates generation or transformation; the blinded review alone does not distinguish raw-generation semantics from later transformations. Validation rejection is not automatically a validator defect. Consult reviewed_answers.jsonl for raw answers and failure spans.

Results concern the deployed adaptive text path, actual process restart with explicit evaluation history rehydration, and controlled logical-time expiry. They do not establish power-loss recovery or spoken performance. The 4 scenarios, repeated branches and checkpoint pairs are not 96 independent quality samples. This targeted matched regression selected scenarios after baseline failure inspection; it is not held-out evaluation. Original unfavorable outcomes and failed checkpoints remain in planned denominators.

Detailed counts, model selections and component findings are in metrics.json. All checkpoint answers and judgments are in answers.md and reviewed_answers.jsonl; setup acknowledgments are separate.
