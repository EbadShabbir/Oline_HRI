# history pair details

| scenario_id | category | branch | stage | history_mode | restart_phase | expected_kind | retained_checkpoint | fresh_checkpoint | retained_success | fresh_success | retained_disclosure | fresh_disclosure | both_observed | retained_revoked_subject_disclosure | fresh_revoked_subject_disclosure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cm04 | relationship | correction | corrected | retained | before | replacement | cm04_correction_corrected_retained | cm04_correction_corrected_fresh | True | True | False | False | True | False | False |
| cm04 | relationship | correction | historical | retained | before | historical_control | cm04_correction_historical_retained | cm04_correction_historical_fresh | True | True | False | False | True | False | False |
| cm04 | relationship | correction | restart | retained | after | replacement | cm04_correction_restart_retained | cm04_correction_restart_fresh | True | True | False | False | True | False | False |
| cm04 | relationship | correction | restart_historical | retained | after | historical_control | cm04_correction_restart_historical_retained | cm04_correction_restart_historical_fresh | True | True | False | False | True | False | False |
| cm04 | relationship | deletion | deleted | retained | before | uncertainty | cm04_deletion_deleted_retained | cm04_deletion_deleted_fresh | True | True | False | False | True | False | False |
| cm04 | relationship | deletion | restart | retained | after | uncertainty | cm04_deletion_restart_retained | cm04_deletion_restart_fresh | True | True | False | False | True | False | False |
| cm04 | relationship | expiry | before | retained | before | original | cm04_expiry_before_retained | cm04_expiry_before_fresh | True | True | False | False | True | False | False |
| cm04 | relationship | expiry | at | retained | before | uncertainty | cm04_expiry_at_retained | cm04_expiry_at_fresh | True | True | False | False | True | False | False |
| cm04 | relationship | expiry | restart | retained | after | uncertainty | cm04_expiry_restart_retained | cm04_expiry_restart_fresh | True | True | False | False | True | False | False |
