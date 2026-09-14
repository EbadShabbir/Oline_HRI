# All planned checkpoint answers

Assistant review; human validation pending.

| Checkpoint | Expected | History | Restart | Delivered answer | Judgment | Useful | Forbidden | Evidence findings |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cm01_correction_prestore | uncertainty | retained | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm01_correction_recalled | rooibos | retained | False | Your preferred tea is rooibos tea. | correct_recall | True | [] | [] |
| cm01_correction_corrected_retained | jasmine | retained | False | Your preferred tea is rooibos tea. | incorrect | False | ['rooibos'] | ['retrieval_skipped_by_memory_policy'] |
| cm01_correction_corrected_fresh | jasmine | fresh | False | Your preferred tea is jasmine tea without sugar. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm01_correction_historical_retained | Maple Pavilion | retained | False | Your Larkspur picnic was at Maple Pavilion on 2026-09-03 at 14:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm01_correction_historical_fresh | Maple Pavilion | fresh | False | Your Larkspur picnic was at Maple Pavilion on 2026-09-03 at 14:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm01_correction_restart_retained | jasmine | retained | True | Your preferred tea is rooibos tea. | incorrect | False | ['rooibos'] | ['retrieval_skipped_by_memory_policy'] |
| cm01_correction_restart_fresh | jasmine | fresh | True | Your current preferred tea is jasmine tea without sugar. | partial | False | [] | ['retrieval_skipped_by_memory_policy'] |
| cm01_correction_restart_historical_retained | Maple Pavilion | retained | True | Your Larkspur picnic was at Maple Pavilion on 2026-09-03 at 14:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm01_correction_restart_historical_fresh | Maple Pavilion | fresh | True | Your Larkspur picnic was at Maple Pavilion on 2026-09-03 at 14:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm01_deletion_recalled | rooibos | retained | False | Your preferred tea is rooibos tea. | correct_recall | True | [] | [] |
| cm01_deletion_deleted_retained | uncertainty | retained | False | Your preferred tea is rooibos tea. | incorrect | False | ['rooibos'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm01_deletion_deleted_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm01_deletion_deleted_historical_retained | uncertainty | retained | False | Your preferred tea is rooibos tea. | incorrect | False | ['rooibos'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm01_deletion_restart_retained | uncertainty | retained | True | Your preferred tea is rooibos tea. | incorrect | False | ['rooibos'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm01_deletion_restart_fresh | uncertainty | fresh | True | Your current preferred tea is jasmine tea without sugar. | incorrect | False | ['jasmine'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm01_deletion_restart_historical_retained | uncertainty | retained | True | Your preferred tea is rooibos tea. | incorrect | False | ['rooibos'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm01_expiry_before_retained | rooibos | retained | False | Your preferred tea is rooibos tea. | correct_recall | True | [] | ['retrieval_skipped_by_memory_policy'] |
| cm01_expiry_before_fresh | rooibos | fresh | False | Your preferred tea is rooibos tea. | correct_recall | True | [] | [] |
| cm01_expiry_at_retained | uncertainty | retained | False | Your preferred tea is rooibos tea. | incorrect | False | ['rooibos'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm01_expiry_at_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm01_expiry_after_retained | uncertainty | retained | False | Your preferred tea is rooibos tea. | incorrect | False | ['rooibos'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm01_expiry_restart_retained | uncertainty | retained | True | Your preferred tea is rooibos tea. | incorrect | False | ['rooibos'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm01_expiry_restart_fresh | uncertainty | fresh | True | Your current preferred tea is jasmine tea without sugar. | incorrect | False | ['jasmine'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm02_correction_prestore | uncertainty | retained | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm02_correction_recalled | bluegrass | retained | False | Your preferred music is bluegrass music. | correct_recall | True | [] | [] |
| cm02_correction_corrected_retained | bossa nova | retained | False | Your preferred music is bluegrass music. | incorrect | False | ['bluegrass'] | ['retrieval_skipped_by_memory_policy'] |
| cm02_correction_corrected_fresh | bossa nova | fresh | False | Your preferred music is bossa nova music. | correct_recall | True | [] | [] |
| cm02_correction_historical_retained | Willow Hall | retained | False | Your Amber craft fair was at Willow Hall on 2026-09-04 at 10:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm02_correction_historical_fresh | Willow Hall | fresh | False | Your Amber craft fair was at Willow Hall on 2026-09-04. | correct_recall | True | [] | [] |
| cm02_correction_restart_retained | bossa nova | retained | True | Your preferred music is bluegrass music. | incorrect | False | ['bluegrass'] | ['retrieval_skipped_by_memory_policy'] |
| cm02_correction_restart_fresh | bossa nova | fresh | True | Your current preferred music is bossa nova music. | correct_recall | True | [] | [] |
| cm02_correction_restart_historical_retained | Willow Hall | retained | True | Your Amber craft fair was at Willow Hall on 2026-09-04 at 10:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm02_correction_restart_historical_fresh | Willow Hall | fresh | True | Your Amber craft fair was at Willow Hall on 2026-09-04. | correct_recall | True | [] | [] |
| cm02_deletion_recalled | bluegrass | retained | False | Your preferred music is bluegrass music. | correct_recall | True | [] | [] |
| cm02_deletion_deleted_retained | uncertainty | retained | False | Your preferred music is bluegrass music. | incorrect | False | ['bluegrass'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm02_deletion_deleted_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm02_deletion_deleted_historical_retained | uncertainty | retained | False | Your preferred music is bluegrass music. | incorrect | False | ['bluegrass'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm02_deletion_restart_retained | uncertainty | retained | True | Your preferred music is bluegrass music. | incorrect | False | ['bluegrass'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm02_deletion_restart_fresh | uncertainty | fresh | True | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm02_deletion_restart_historical_retained | uncertainty | retained | True | Your preferred music is bluegrass music. | incorrect | False | ['bluegrass'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm02_expiry_before_retained | bluegrass | retained | False | Your preferred music is bluegrass music. | correct_recall | True | [] | ['retrieval_skipped_by_memory_policy'] |
| cm02_expiry_before_fresh | bluegrass | fresh | False | Your preferred music is bluegrass music. | correct_recall | True | [] | [] |
| cm02_expiry_at_retained | uncertainty | retained | False | Your preferred music is bluegrass music. | incorrect | False | ['bluegrass'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm02_expiry_at_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm02_expiry_after_retained | uncertainty | retained | False | Your preferred music is bluegrass music. | incorrect | False | ['bluegrass'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm02_expiry_restart_retained | uncertainty | retained | True | Your preferred music is bluegrass music. | incorrect | False | ['bluegrass'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm02_expiry_restart_fresh | uncertainty | fresh | True | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm03_correction_prestore | uncertainty | retained | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm03_correction_recalled | turquoise | retained | False | Your preferred notebook color is turquoise. | correct_recall | True | [] | [] |
| cm03_correction_corrected_retained | burgundy | retained | False | Your preferred notebook color is turquoise. | incorrect | False | ['turquoise'] | ['retrieval_skipped_by_memory_policy'] |
| cm03_correction_corrected_fresh | burgundy | fresh | False | Your preferred notebook color is burgundy. | correct_recall | True | [] | [] |
| cm03_correction_historical_retained | Cedar Court | retained | False | Your Juniper reading festival was at Cedar Court on 2026-09-05 at 11:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm03_correction_historical_fresh | Cedar Court | fresh | False | Your Juniper reading festival was at Cedar Court on 2026-09-05 at 11:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm03_correction_restart_retained | burgundy | retained | True | Your preferred notebook color is turquoise. | incorrect | False | ['turquoise'] | ['retrieval_skipped_by_memory_policy'] |
| cm03_correction_restart_fresh | burgundy | fresh | True | Your preferred notebook color is blue. | incorrect | False | [] | ['retrieval_skipped_by_memory_policy'] |
| cm03_correction_restart_historical_retained | Cedar Court | retained | True | Your Juniper reading festival was at Cedar Court on 2026-09-05 at 11:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm03_correction_restart_historical_fresh | Cedar Court | fresh | True | Your Juniper reading festival was at Cedar Court on 2026-09-05 at 11:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm03_deletion_recalled | turquoise | retained | False | Your preferred notebook color is turquoise. | correct_recall | True | [] | [] |
| cm03_deletion_deleted_retained | uncertainty | retained | False | Your preferred notebook color is turquoise. | incorrect | False | ['turquoise'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm03_deletion_deleted_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm03_deletion_deleted_historical_retained | uncertainty | retained | False | Your preferred notebook color is turquoise. | incorrect | False | ['turquoise'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm03_deletion_restart_retained | uncertainty | retained | True | Your preferred notebook color is turquoise. | incorrect | False | ['turquoise'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm03_deletion_restart_fresh | uncertainty | fresh | True | Your preferred notebook color is blue. | incorrect | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm03_deletion_restart_historical_retained | uncertainty | retained | True | Your preferred notebook color is turquoise. | incorrect | False | ['turquoise'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm03_expiry_before_retained | turquoise | retained | False | Your preferred notebook color is turquoise. | correct_recall | True | [] | ['retrieval_skipped_by_memory_policy'] |
| cm03_expiry_before_fresh | turquoise | fresh | False | Your preferred notebook color is turquoise. | correct_recall | True | [] | [] |
| cm03_expiry_at_retained | uncertainty | retained | False | Your preferred notebook color is turquoise. | incorrect | False | ['turquoise'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm03_expiry_at_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm03_expiry_after_retained | uncertainty | retained | False | Your preferred notebook color is turquoise. | incorrect | False | ['turquoise'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm03_expiry_restart_retained | uncertainty | retained | True | Your preferred notebook color is turquoise. | incorrect | False | ['turquoise'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm03_expiry_restart_fresh | uncertainty | fresh | True | Your preferred notebook color is blue. | incorrect | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm04_correction_prestore | uncertainty | retained | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm04_correction_recalled | Elora Vale | retained | False | Your walking partner is Elora Vale. | correct_recall | True | [] | [] |
| cm04_correction_corrected_retained | Niko Fern | retained | False | Your walking partner is Elora Vale. | incorrect | False | ['Elora Vale'] | ['retrieval_skipped_by_memory_policy'] |
| cm04_correction_corrected_fresh | Niko Fern | fresh | False | Your walking partner is Niko Fern. | correct_recall | True | [] | [] |
| cm04_correction_historical_retained | Birch Lodge | retained | False | Your Marigold garden tour was at Birch Lodge on 2026-09-06 at 09:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm04_correction_historical_fresh | Birch Lodge | fresh | False | Your Marigold garden tour was at Birch Lodge on 2026-09-06 at 09:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm04_correction_restart_retained | Niko Fern | retained | True | Your current walking partner is Elora Vale. | incorrect | False | ['Elora Vale'] | ['retrieval_skipped_by_memory_policy'] |
| cm04_correction_restart_fresh | Niko Fern | fresh | True | [no delivered answer] | no_delivered_answer | False | [] | ['evidence_selection_required_fact_missing', 'validation_rejection'] |
| cm04_correction_restart_historical_retained | Birch Lodge | retained | True | Your Marigold garden tour was at Birch Lodge on 2026-09-06 at 09:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm04_correction_restart_historical_fresh | Birch Lodge | fresh | True | Your Marigold garden tour was at Birch Lodge on 2026-09-06 at 09:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm04_deletion_recalled | Elora Vale | retained | False | Your walking partner is Elora Vale. | correct_recall | True | [] | [] |
| cm04_deletion_deleted_retained | uncertainty | retained | False | Your walking partner is Elora Vale. | incorrect | False | ['Elora Vale'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm04_deletion_deleted_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm04_deletion_deleted_historical_retained | uncertainty | retained | False | Your walking partner is Elora Vale. | incorrect | False | ['Elora Vale'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm04_deletion_restart_retained | uncertainty | retained | True | Your current walking partner is Elora Vale. | incorrect | False | ['Elora Vale'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm04_deletion_restart_fresh | uncertainty | fresh | True | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm04_deletion_restart_historical_retained | uncertainty | retained | True | Your current walking partner is Elora Vale. | incorrect | False | ['Elora Vale'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm04_expiry_before_retained | Elora Vale | retained | False | Your walking partner is Elora Vale. | correct_recall | True | [] | ['retrieval_skipped_by_memory_policy'] |
| cm04_expiry_before_fresh | Elora Vale | fresh | False | Your walking partner is Elora Vale. | correct_recall | True | [] | [] |
| cm04_expiry_at_retained | uncertainty | retained | False | Your walking partner is Elora Vale. | incorrect | False | ['Elora Vale'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm04_expiry_at_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm04_expiry_after_retained | uncertainty | retained | False | Your walking partner is Elora Vale. | incorrect | False | ['Elora Vale'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm04_expiry_restart_retained | uncertainty | retained | True | Your current walking partner is Elora Vale. | incorrect | False | ['Elora Vale'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm04_expiry_restart_fresh | uncertainty | fresh | True | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm05_correction_prestore | uncertainty | retained | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm05_correction_recalled | Tessa Brook | retained | False | Your book club contact is Tessa Brook. | correct_recall | True | [] | [] |
| cm05_correction_corrected_retained | Orin Moss | retained | False | Your book club contact is Tessa Brook. | incorrect | False | ['Tessa Brook'] | ['retrieval_skipped_by_memory_policy'] |
| cm05_correction_corrected_fresh | Orin Moss | fresh | False | Your book club contact is Orin Moss. | correct_recall | True | [] | [] |
| cm05_correction_historical_retained | Acorn Studio | retained | False | Your Saffron painting class was at Acorn Studio on 2026-09-07 at 16:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm05_correction_historical_fresh | Acorn Studio | fresh | False | Your Saffron painting class was at Acorn Studio on 2026-09-07 at 16:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm05_correction_restart_retained | Orin Moss | retained | True | Your book club contact is Tessa Brook. | incorrect | False | ['Tessa Brook'] | ['retrieval_skipped_by_memory_policy'] |
| cm05_correction_restart_fresh | Orin Moss | fresh | True | Your book club contact is Orin Moss. | correct_recall | True | [] | [] |
| cm05_correction_restart_historical_retained | Acorn Studio | retained | True | Your Saffron painting class was at Acorn Studio on 2026-09-07 at 16:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm05_correction_restart_historical_fresh | Acorn Studio | fresh | True | Your Saffron painting class was at Acorn Studio on 2026-09-07 at 16:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm05_deletion_recalled | Tessa Brook | retained | False | Your book club contact is Tessa Brook. | correct_recall | True | [] | [] |
| cm05_deletion_deleted_retained | uncertainty | retained | False | Your book club contact is Tessa Brook. | incorrect | False | ['Tessa Brook'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm05_deletion_deleted_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm05_deletion_deleted_historical_retained | uncertainty | retained | False | Your book club contact is Tessa Brook. | incorrect | False | ['Tessa Brook'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm05_deletion_restart_retained | uncertainty | retained | True | Your book club contact is Tessa Brook. | incorrect | False | ['Tessa Brook'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm05_deletion_restart_fresh | uncertainty | fresh | True | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm05_deletion_restart_historical_retained | uncertainty | retained | True | Your book club contact is Tessa Brook. | incorrect | False | ['Tessa Brook'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm05_expiry_before_retained | Tessa Brook | retained | False | Your book club contact is Tessa Brook. | correct_recall | True | [] | ['retrieval_skipped_by_memory_policy'] |
| cm05_expiry_before_fresh | Tessa Brook | fresh | False | Your book club contact is Tessa Brook. | correct_recall | True | [] | [] |
| cm05_expiry_at_retained | uncertainty | retained | False | Your book club contact is Tessa Brook. | incorrect | False | ['Tessa Brook'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm05_expiry_at_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm05_expiry_after_retained | uncertainty | retained | False | Your book club contact is Tessa Brook. | incorrect | False | ['Tessa Brook'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm05_expiry_restart_retained | uncertainty | retained | True | Your book club contact is Tessa Brook. | incorrect | False | ['Tessa Brook'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm05_expiry_restart_fresh | uncertainty | fresh | True | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm06_correction_prestore | uncertainty | retained | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm06_correction_recalled | wicker basket | retained | False | Your sketchbook is in the wicker basket. | correct_recall | True | [] | [] |
| cm06_correction_corrected_retained | walnut drawer | retained | False | Your sketchbook is still in the wicker basket. | incorrect | False | ['wicker basket'] | ['retrieval_skipped_by_memory_policy'] |
| cm06_correction_corrected_fresh | walnut drawer | fresh | False | Your sketchbook is in the walnut drawer. Please check the drawer for it. | correct_recall | True | [] | [] |
| cm06_correction_historical_retained | Clover Field | retained | False | Your Moonbeam kite festival was at Clover Field on 2026-09-08 at 13:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm06_correction_historical_fresh | Clover Field | fresh | False | Your Moonbeam kite festival was at Clover Field on 2026-09-08 at 13:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm06_correction_restart_retained | walnut drawer | retained | True | Your sketchbook is still in the wicker basket. | incorrect | False | ['wicker basket'] | ['retrieval_skipped_by_memory_policy'] |
| cm06_correction_restart_fresh | walnut drawer | fresh | True | Your sketchbook is in the walnut drawer. Please check the drawer for your sketchbook. | correct_recall | True | [] | [] |
| cm06_correction_restart_historical_retained | Clover Field | retained | True | Your Moonbeam kite festival was at Clover Field on 2026-09-08 at 13:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm06_correction_restart_historical_fresh | Clover Field | fresh | True | Your Moonbeam kite festival was at Clover Field on 2026-09-08 at 13:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm06_deletion_recalled | wicker basket | retained | False | Your sketchbook is in the wicker basket. | correct_recall | True | [] | [] |
| cm06_deletion_deleted_retained | uncertainty | retained | False | Your sketchbook is still in the wicker basket. | incorrect | False | ['wicker basket'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm06_deletion_deleted_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm06_deletion_deleted_historical_retained | uncertainty | retained | False | Your sketchbook is still in the wicker basket. | incorrect | False | ['wicker basket'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm06_deletion_restart_retained | uncertainty | retained | True | Your sketchbook is still in the wicker basket. | incorrect | False | ['wicker basket'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm06_deletion_restart_fresh | uncertainty | fresh | True | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm06_deletion_restart_historical_retained | uncertainty | retained | True | Your sketchbook is still in the wicker basket. | incorrect | False | ['wicker basket'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm06_expiry_before_retained | wicker basket | retained | False | Your sketchbook is still in the wicker basket. | correct_recall | True | [] | ['retrieval_skipped_by_memory_policy'] |
| cm06_expiry_before_fresh | wicker basket | fresh | False | I do not have a verified personal memory that answers that. | inappropriate_uncertainty | False | [] | ['evidence_selection_required_fact_missing'] |
| cm06_expiry_at_retained | uncertainty | retained | False | Your sketchbook is still in the wicker basket. | incorrect | False | ['wicker basket'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm06_expiry_at_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm06_expiry_after_retained | uncertainty | retained | False | Your sketchbook is still in the wicker basket. | incorrect | False | ['wicker basket'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm06_expiry_restart_retained | uncertainty | retained | True | Your sketchbook is still in the wicker basket. | incorrect | False | ['wicker basket'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm06_expiry_restart_fresh | uncertainty | fresh | True | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm07_correction_prestore | uncertainty | retained | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm07_correction_recalled | canvas tote | retained | False | I do not have a verified personal memory that answers that. | inappropriate_uncertainty | False | [] | ['evidence_selection_required_fact_missing'] |
| cm07_correction_corrected_retained | cedar cabinet | retained | False | Your binoculars are in the canvas tote. I don't have physical access to them. | incorrect | False | ['canvas tote'] | ['retrieval_skipped_by_memory_policy'] |
| cm07_correction_corrected_fresh | cedar cabinet | fresh | False | Your binoculars are in the cedar cabinet. Please check it. | correct_recall | True | [] | [] |
| cm07_correction_historical_retained | Fern Terrace | retained | False | Your Rosewood puzzle afternoon was at Fern Terrace on 2026-09-09 at 15:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm07_correction_historical_fresh | Fern Terrace | fresh | False | Your Rosewood puzzle afternoon was at Fern Terrace on 2026-09-09 at 15:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm07_correction_restart_retained | cedar cabinet | retained | True | Your binoculars are in the canvas tote. I don't have physical access to them. | incorrect | False | ['canvas tote'] | ['retrieval_skipped_by_memory_policy'] |
| cm07_correction_restart_fresh | cedar cabinet | fresh | True | Your binoculars are in the cedar cabinet. Please check the cedar cabinet for your binoculars. | correct_recall | True | [] | [] |
| cm07_correction_restart_historical_retained | Fern Terrace | retained | True | Your Rosewood puzzle afternoon was at Fern Terrace on 2026-09-09 at 15:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm07_correction_restart_historical_fresh | Fern Terrace | fresh | True | Your Rosewood puzzle afternoon was at Fern Terrace on 2026-09-09 at 15:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm07_deletion_recalled | canvas tote | retained | False | I do not have a verified personal memory that answers that. | inappropriate_uncertainty | False | [] | ['evidence_selection_required_fact_missing'] |
| cm07_deletion_deleted_retained | uncertainty | retained | False | Your binoculars are in the canvas tote. | incorrect | False | ['canvas tote'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm07_deletion_deleted_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm07_deletion_deleted_historical_retained | uncertainty | retained | False | Your binoculars are in the canvas tote. | incorrect | False | ['canvas tote'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm07_deletion_restart_retained | uncertainty | retained | True | Your binoculars are in the canvas tote. | incorrect | False | ['canvas tote'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm07_deletion_restart_fresh | uncertainty | fresh | True | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm07_deletion_restart_historical_retained | uncertainty | retained | True | Your binoculars are in the canvas tote. | incorrect | False | ['canvas tote'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm07_expiry_before_retained | canvas tote | retained | False | Your binoculars are in the canvas tote. | correct_recall | True | [] | ['retrieval_skipped_by_memory_policy'] |
| cm07_expiry_before_fresh | canvas tote | fresh | False | I do not have a verified personal memory that answers that. | inappropriate_uncertainty | False | [] | ['evidence_selection_required_fact_missing'] |
| cm07_expiry_at_retained | uncertainty | retained | False | Your binoculars are in the canvas tote. | incorrect | False | ['canvas tote'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm07_expiry_at_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm07_expiry_after_retained | uncertainty | retained | False | Your binoculars are in the canvas tote. | incorrect | False | ['canvas tote'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm07_expiry_restart_retained | uncertainty | retained | True | Your binoculars are in the canvas tote. | incorrect | False | ['canvas tote'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm07_expiry_restart_fresh | uncertainty | fresh | True | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm08_correction_prestore | uncertainty | retained | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm08_correction_recalled | striped tin | retained | False | Your sewing kit is in the striped tin. | correct_recall | True | [] | [] |
| cm08_correction_corrected_retained | velvet pouch | retained | False | Your sewing kit is in the striped tin. I don't have a physical action. | incorrect | False | ['striped tin'] | ['retrieval_skipped_by_memory_policy'] |
| cm08_correction_corrected_fresh | velvet pouch | fresh | False | Your sewing kit is in the velvet pouch. Please check it. | correct_recall | True | [] | [] |
| cm08_correction_historical_retained | Elm Bridge | retained | False | Your Hawthorn lantern walk was at Elm Bridge on 2026-09-10 at 18:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm08_correction_historical_fresh | Elm Bridge | fresh | False | Your Hawthorn lantern walk was at Elm Bridge on 2026-09-10 at 18:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm08_correction_restart_retained | velvet pouch | retained | True | Your sewing kit is in the striped tin. I don't have a physical action. | incorrect | False | ['striped tin'] | ['retrieval_skipped_by_memory_policy'] |
| cm08_correction_restart_fresh | velvet pouch | fresh | True | Your sewing kit is located in the top drawer of the cabinet on the right side of the room. | incorrect | False | [] | ['retrieval_skipped_by_memory_policy'] |
| cm08_correction_restart_historical_retained | Elm Bridge | retained | True | Your Hawthorn lantern walk was at Elm Bridge on 2026-09-10 at 18:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm08_correction_restart_historical_fresh | Elm Bridge | fresh | True | Your Hawthorn lantern walk was at Elm Bridge on 2026-09-10 at 18:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm08_deletion_recalled | striped tin | retained | False | Your sewing kit is in the striped tin. | correct_recall | True | [] | [] |
| cm08_deletion_deleted_retained | uncertainty | retained | False | Your sewing kit is in the striped tin. | incorrect | False | ['striped tin'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm08_deletion_deleted_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm08_deletion_deleted_historical_retained | uncertainty | retained | False | Your sewing kit is in the striped tin. | incorrect | False | ['striped tin'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm08_deletion_restart_retained | uncertainty | retained | True | Your sewing kit is in the striped tin. | incorrect | False | ['striped tin'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm08_deletion_restart_fresh | uncertainty | fresh | True | Your sewing kit is located in the top drawer of the cabinet on the right side of the room. | incorrect | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm08_deletion_restart_historical_retained | uncertainty | retained | True | Your sewing kit is in the striped tin. | incorrect | False | ['striped tin'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm08_expiry_before_retained | striped tin | retained | False | Your sewing kit is in the striped tin. | correct_recall | True | [] | ['retrieval_skipped_by_memory_policy'] |
| cm08_expiry_before_fresh | striped tin | fresh | False | Your sewing kit is in the striped tin. No action required. | correct_recall | True | [] | [] |
| cm08_expiry_at_retained | uncertainty | retained | False | Your sewing kit is in the striped tin. | incorrect | False | ['striped tin'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm08_expiry_at_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm08_expiry_after_retained | uncertainty | retained | False | Your sewing kit is in the striped tin. | incorrect | False | ['striped tin'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm08_expiry_restart_retained | uncertainty | retained | True | Your sewing kit is in the striped tin. | incorrect | False | ['striped tin'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm08_expiry_restart_fresh | uncertainty | fresh | True | Your sewing kit is located in the top drawer of the cabinet on the right side of the room. | incorrect | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm09_correction_prestore | uncertainty | retained | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm09_correction_recalled | 09:00 | retained | False | The pottery appointment is scheduled for 2026-10-03 at 09:00. | correct_recall | True | [] | [] |
| cm09_correction_corrected_retained | 11:30 | retained | False | None of the information provided is available for the start time of the pottery appointment. | inappropriate_uncertainty | False | [] | ['retrieval_skipped_by_memory_policy'] |
| cm09_correction_corrected_fresh | 11:30 | fresh | False | [no delivered answer] | no_delivered_answer | False | [] | ['evidence_selection_required_fact_missing', 'validation_rejection'] |
| cm09_correction_historical_retained | Hazel Auditorium | retained | False | Your Silverleaf choir rehearsal was at Hazel Auditorium on 2026-09-11 at 17:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm09_correction_historical_fresh | Hazel Auditorium | fresh | False | Your Silverleaf choir rehearsal was at Hazel Auditorium on 2026-09-11 at 17:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm09_correction_restart_retained | 11:30 | retained | True | The recorded start time for your pottery appointment on 2026-10-03 is not available. | inappropriate_uncertainty | False | [] | ['retrieval_skipped_by_memory_policy'] |
| cm09_correction_restart_fresh | 11:30 | fresh | True | [no delivered answer] | no_delivered_answer | False | [] | ['evidence_selection_required_fact_missing', 'validation_rejection'] |
| cm09_correction_restart_historical_retained | Hazel Auditorium | retained | True | Your Silverleaf choir rehearsal was at Hazel Auditorium on 2026-09-11 at 17:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm09_correction_restart_historical_fresh | Hazel Auditorium | fresh | True | Your Silverleaf choir rehearsal was at Hazel Auditorium on 2026-09-11 at 17:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm09_deletion_recalled | 09:00 | retained | False | The pottery appointment is scheduled for 2026-10-03 at 09:00. | correct_recall | True | [] | [] |
| cm09_deletion_deleted_retained | uncertainty | retained | False | None of the information provided is available for the start time of the pottery appointment. | appropriate_uncertainty | True | [] | [] |
| cm09_deletion_deleted_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm09_deletion_deleted_historical_retained | uncertainty | retained | False | None of the information provided is available for the start time of the pottery appointment. | appropriate_uncertainty | True | [] | [] |
| cm09_deletion_restart_retained | uncertainty | retained | True | The recorded start time for your pottery appointment on 2026-10-03 is 09:00. | incorrect | False | ['09:00'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm09_deletion_restart_fresh | uncertainty | fresh | True | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm09_deletion_restart_historical_retained | uncertainty | retained | True | None of the information provided is available for the start time of the pottery appointment. | appropriate_uncertainty | True | [] | [] |
| cm09_expiry_before_retained | 09:00 | retained | False | None of the information provided is available for the start time of the pottery appointment. | inappropriate_uncertainty | False | [] | ['retrieval_skipped_by_memory_policy'] |
| cm09_expiry_before_fresh | 09:00 | fresh | False | Your pottery appointment is on 2026-10-03 at 09:00. | correct_recall | True | [] | [] |
| cm09_expiry_at_retained | uncertainty | retained | False | The start time of your pottery appointment is not recorded currently. | appropriate_uncertainty | True | [] | [] |
| cm09_expiry_at_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm09_expiry_after_retained | uncertainty | retained | False | The start time of your pottery appointment is not recorded currently. | appropriate_uncertainty | True | [] | [] |
| cm09_expiry_restart_retained | uncertainty | retained | True | None of the information provided is available for the start time of your pottery appointment. | appropriate_uncertainty | True | [] | [] |
| cm09_expiry_restart_fresh | uncertainty | fresh | True | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm10_correction_prestore | uncertainty | retained | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm10_correction_recalled | 14:15 | retained | False | Your bicycle fitting appointment is on 2026-10-04 at 14:15. | correct_recall | True | [] | [] |
| cm10_correction_corrected_retained | 16:45 | retained | False | I don't have current information about your bicycle fitting appointment. Please check your schedule for the latest details. | inappropriate_uncertainty | False | [] | ['retrieval_skipped_by_memory_policy'] |
| cm10_correction_corrected_fresh | 16:45 | fresh | False | [no delivered answer] | no_delivered_answer | False | [] | ['evidence_selection_required_fact_missing', 'validation_rejection'] |
| cm10_correction_historical_retained | Linden Library | retained | False | Your Foxglove chess evening was at Linden Library on 2026-09-12 at 19:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm10_correction_historical_fresh | Linden Library | fresh | False | Your Foxglove chess evening was at Linden Library on 2026-09-12 at 19:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm10_correction_restart_retained | 16:45 | retained | True | The recorded start time for your bicycle fitting appointment on 2026-10-04 is 14:15. | incorrect | False | ['14:15'] | ['retrieval_skipped_by_memory_policy'] |
| cm10_correction_restart_fresh | 16:45 | fresh | True | [no delivered answer] | no_delivered_answer | False | [] | ['evidence_selection_required_fact_missing', 'validation_rejection'] |
| cm10_correction_restart_historical_retained | Linden Library | retained | True | Your Foxglove chess evening was at Linden Library on 2026-09-12 at 19:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm10_correction_restart_historical_fresh | Linden Library | fresh | True | Your Foxglove chess evening was at Linden Library on 2026-09-12 at 19:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm10_deletion_recalled | 14:15 | retained | False | Your bicycle fitting appointment is on 2026-10-04 at 14:15. | correct_recall | True | [] | [] |
| cm10_deletion_deleted_retained | uncertainty | retained | False | I don't have current information about your bicycle fitting appointment. Please check your schedule or contact the service provider for the latest details. | appropriate_uncertainty | True | [] | [] |
| cm10_deletion_deleted_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm10_deletion_deleted_historical_retained | uncertainty | retained | False | I don't have current information about your bicycle fitting appointment. Please check your schedule or contact the service provider for the latest details. | appropriate_uncertainty | True | [] | [] |
| cm10_deletion_restart_retained | uncertainty | retained | True | I don't have current information about your bicycle fitting appointment. Please check your schedule or contact the service provider for the latest details. | appropriate_uncertainty | True | [] | [] |
| cm10_deletion_restart_fresh | uncertainty | fresh | True | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm10_deletion_restart_historical_retained | uncertainty | retained | True | I don't have current information about your bicycle fitting appointment. Please check your schedule or contact the service provider for the latest details. | appropriate_uncertainty | True | [] | [] |
| cm10_expiry_before_retained | 14:15 | retained | False | I don't have current information about your bicycle fitting appointment. Please check your schedule or contact the service provider for the latest details. | inappropriate_uncertainty | False | [] | ['retrieval_skipped_by_memory_policy'] |
| cm10_expiry_before_fresh | 14:15 | fresh | False | Your bicycle fitting appointment is on 2026-10-04 at 14:15. | correct_recall | True | [] | [] |
| cm10_expiry_at_retained | uncertainty | retained | False | I don't have current information about your bicycle fitting appointment. Please check your schedule or contact the service provider for the latest details. | appropriate_uncertainty | True | [] | [] |
| cm10_expiry_at_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm10_expiry_after_retained | uncertainty | retained | False | I don't have current information about your bicycle fitting appointment. Please check your schedule or contact the service provider for the latest details. | appropriate_uncertainty | True | [] | [] |
| cm10_expiry_restart_retained | uncertainty | retained | True | I don't have current information about your bicycle fitting appointment. Please check your schedule or contact the service provider for the latest details. | appropriate_uncertainty | True | [] | [] |
| cm10_expiry_restart_fresh | uncertainty | fresh | True | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm11_correction_prestore | uncertainty | retained | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm11_correction_recalled | Copper Hall | retained | False | Your Seaglass workshop was at Copper Hall on 2026-09-20 at 10:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm11_correction_corrected_retained | Orchid Hall | retained | False | Earlier I told you about my Seaglass workshop on 2026-09-20. The venue is Copper Hall. | incorrect | False | ['Copper Hall'] | ['retrieval_skipped_by_memory_policy'] |
| cm11_correction_corrected_fresh | Orchid Hall | fresh | False | Your Seaglass workshop was at Orchid Hall on 2026-09-20 at 10:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm11_correction_historical_retained | Aspen Cafe | retained | False | Your Bluebell poetry lunch was at Aspen Cafe on 2026-09-13 at 12:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm11_correction_historical_fresh | Aspen Cafe | fresh | False | Your Bluebell poetry lunch was at Aspen Cafe on 2026-09-13 at 12:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm11_correction_restart_retained | Orchid Hall | retained | True | The venue for your Seaglass workshop on 2026-09-20 is Copper Hall. | incorrect | False | ['Copper Hall'] | ['retrieval_skipped_by_memory_policy'] |
| cm11_correction_restart_fresh | Orchid Hall | fresh | True | Your Seaglass workshop was at Orchid Hall on 2026-09-20 at 10:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm11_correction_restart_historical_retained | Aspen Cafe | retained | True | Your Bluebell poetry lunch was at Aspen Cafe on 2026-09-13 at 12:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm11_correction_restart_historical_fresh | Aspen Cafe | fresh | True | Your Bluebell poetry lunch was at Aspen Cafe on 2026-09-13 at 12:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm11_deletion_recalled | Copper Hall | retained | False | Your Seaglass workshop was at Copper Hall on 2026-09-20 at 10:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm11_deletion_deleted_retained | uncertainty | retained | False | Earlier I told you about my Seaglass workshop on 2026-09-20. The venue is Copper Hall. | incorrect | False | ['Copper Hall'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm11_deletion_deleted_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm11_deletion_deleted_historical_retained | uncertainty | retained | False | Earlier I told you about my Seaglass workshop on 2026-09-20. The venue is Copper Hall. | incorrect | False | ['Copper Hall'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm11_deletion_restart_retained | uncertainty | retained | True | Your Seaglass workshop was at Copper Hall on 2026-09-20 at 10:00. | incorrect | False | ['Copper Hall'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm11_deletion_restart_fresh | uncertainty | fresh | True | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm11_deletion_restart_historical_retained | uncertainty | retained | True | Earlier I told you about my Seaglass workshop on 2026-09-20. The venue is Copper Hall. | incorrect | False | ['Copper Hall'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm11_expiry_before_retained | Copper Hall | retained | False | Earlier I told you about my Seaglass workshop on 2026-09-20. The venue is Copper Hall. | correct_recall | True | [] | ['retrieval_skipped_by_memory_policy'] |
| cm11_expiry_before_fresh | Copper Hall | fresh | False | Your Seaglass workshop was at Copper Hall on 2026-09-20 at 10:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm11_expiry_at_retained | uncertainty | retained | False | Earlier I told you about my Seaglass workshop on 2026-09-20. The venue is Copper Hall. | incorrect | False | ['Copper Hall'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm11_expiry_at_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm11_expiry_after_retained | uncertainty | retained | False | Earlier I told you about my Seaglass workshop on 2026-09-20. The venue is Copper Hall. | incorrect | False | ['Copper Hall'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm11_expiry_restart_retained | uncertainty | retained | True | The venue recorded for the Seaglass workshop on 2026-09-20 is Copper Hall. | incorrect | False | ['Copper Hall'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm11_expiry_restart_fresh | uncertainty | fresh | True | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm12_correction_prestore | uncertainty | retained | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm12_correction_recalled | Dune Gallery | retained | False | Your Sunstone exhibition visit was at Dune Gallery on 2026-09-22 at 15:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm12_correction_corrected_retained | Iris Gallery | retained | False | Earlier I told you about my Sunstone exhibition visit on 2026-09-22. The venue is Dune Gallery. | incorrect | False | ['Dune Gallery'] | ['retrieval_skipped_by_memory_policy'] |
| cm12_correction_corrected_fresh | Iris Gallery | fresh | False | The Sunstone exhibition was at the Iris Gallery on 2026-09-22. No action taken. | correct_recall | True | [] | [] |
| cm12_correction_historical_retained | Pine Theater | retained | False | Your Meadowlark storytelling night was at Pine Theater on 2026-09-14 at 20:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm12_correction_historical_fresh | Pine Theater | fresh | False | Your Meadowlark storytelling night was at Pine Theater on 2026-09-14 at 20:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm12_correction_restart_retained | Iris Gallery | retained | True | The venue recorded for your Sunstone exhibition visit on 2026-09-22 is Dune Gallery. | incorrect | False | ['Dune Gallery'] | ['retrieval_skipped_by_memory_policy'] |
| cm12_correction_restart_fresh | Iris Gallery | fresh | True | The Sunstone exhibition visit on 2026-09-22 was at Iris Gallery. | correct_recall | True | [] | [] |
| cm12_correction_restart_historical_retained | Pine Theater | retained | True | Your Meadowlark storytelling night was at Pine Theater on 2026-09-14 at 20:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm12_correction_restart_historical_fresh | Pine Theater | fresh | True | Your Meadowlark storytelling night was at Pine Theater on 2026-09-14 at 20:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm12_deletion_recalled | Dune Gallery | retained | False | Your Sunstone exhibition visit was at Dune Gallery on 2026-09-22 at 15:00. | partial | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm12_deletion_deleted_retained | uncertainty | retained | False | Earlier I told you about my Sunstone exhibition visit on 2026-09-22. | incorrect | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm12_deletion_deleted_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm12_deletion_deleted_historical_retained | uncertainty | retained | False | Earlier I told you about my Sunstone exhibition visit on 2026-09-22. | incorrect | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm12_deletion_restart_retained | uncertainty | retained | True | Your Sunstone exhibition visit was at Dune Gallery on 2026-09-22. | incorrect | False | ['Dune Gallery'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm12_deletion_restart_fresh | uncertainty | fresh | True | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm12_deletion_restart_historical_retained | uncertainty | retained | True | I originally named the venue for my Sunstone exhibition visit as Dune Gallery on 2026-09-22. | incorrect | False | ['Dune Gallery'] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm12_expiry_before_retained | Dune Gallery | retained | False | Earlier I told you about my Sunstone exhibition visit on 2026-09-22. | incorrect | False | [] | ['retrieval_skipped_by_memory_policy'] |
| cm12_expiry_before_fresh | Dune Gallery | fresh | False | The Sunstone exhibition was at the Dune Gallery on 2026-09-22. No action taken. | correct_recall | True | [] | [] |
| cm12_expiry_at_retained | uncertainty | retained | False | Earlier I told you about my Sunstone exhibition visit on 2026-09-22. | incorrect | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm12_expiry_at_fresh | uncertainty | fresh | False | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
| cm12_expiry_after_retained | uncertainty | retained | False | Earlier I told you about my Sunstone exhibition visit on 2026-09-22. | incorrect | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm12_expiry_restart_retained | uncertainty | retained | True | Earlier I told you about my Sunstone exhibition visit on 2026-09-22. | incorrect | False | [] | ['delivered_semantic_failure_with_sufficient_evidence'] |
| cm12_expiry_restart_fresh | uncertainty | fresh | True | I do not have a verified personal memory that answers that. | appropriate_uncertainty | True | [] | [] |
