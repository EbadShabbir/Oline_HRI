# Final changing-memory report tables

These tables aggregate existing frozen assistant judgments and trace metadata. No semantic scoring or inference occurs here. Human validation is pending.

Planned denominators include withheld and interrupted attempts. Useful correct means the frozen full-rubric useful_correct judgment; it is not inferred from replacement-value overlap. Withholding is separate from useful recall and appropriate delivered uncertainty.

stage_history contains all 24 authored branch/stage/history groups, each with twelve scenarios. Restart and expected-kind splits use the frozen ledger fields. The twelve scenarios are the independent authored units.

forbidden_disclosure preserves the original reviewer flag. Subject-specific disclosure scopes use only canonical values already listed in disclosed_forbidden_values. Broad correction includes historical-control questions; current replacement restricts to expected_kind=replacement. Deleted/expired subject counts concern the old subject value. Any-expired-fact includes the old subject and expired historical control, excluding the never-stored replacement. Its unsupported disclosure is reported separately.

History pairs are the 108 authored equal-question/equal-time retained/fresh matches, verified against the sealed analyzer pairing file. Success and disclosure each have both, retained-only, fresh-only and neither counts. Disclosure transitions describe paired history modes, not temporal or causal changes. Revoked-subject transitions use the original subject value in the existing forbidden-value judgments.

Generation call tables count actual recorded generation calls, including failed calls and additional fallback calls. Empty actual_model means no returned model was recorded. Checkpoint selections preserve requested models, returned models, fallback and generation policy separately from nominal routes. The recorder's legacy policy label is preserved; frozen deployment uses the CLI-default LLM router. Setup disclosures and classifier calls are outside these generation tables.

The collection audit is bound to the same frozen run/configuration seals as the analysis. Its integrity result and violations remain reportable; tables do not turn a failed audit into a pass. History-exposure counts are copied from that audit: literal matches are lower-bound exposure witnesses, not semantic absence or answer correctness.

Results concern text, process restart with evaluation history rehydration, and controlled logical-time expiry. They do not establish power-loss recovery or spoken performance.

| Table | Rows | CSV | Markdown |
| --- | ---: | --- | --- |
| overall | 1 | [overall.csv](overall.csv) | [overall.md](overall.md) |
| stage_history | 24 | [stage_history.csv](stage_history.csv) | [stage_history.md](stage_history.md) |
| restart_history | 4 | [restart_history.csv](restart_history.csv) | [restart_history.md](restart_history.md) |
| expected_kind_history | 8 | [expected_kind_history.csv](expected_kind_history.csv) | [expected_kind_history.md](expected_kind_history.md) |
| expected_kind_restart_history | 14 | [expected_kind_restart_history.csv](expected_kind_restart_history.csv) | [expected_kind_restart_history.md](expected_kind_restart_history.md) |
| branch_restart_history | 12 | [branch_restart_history.csv](branch_restart_history.csv) | [branch_restart_history.md](branch_restart_history.md) |
| scenarios | 12 | [scenarios.csv](scenarios.csv) | [scenarios.md](scenarios.md) |
| disclosure_scopes | 63 | [disclosure_scopes.csv](disclosure_scopes.csv) | [disclosure_scopes.md](disclosure_scopes.md) |
| history_pair_aggregates | 12 | [history_pair_aggregates.csv](history_pair_aggregates.csv) | [history_pair_aggregates.md](history_pair_aggregates.md) |
| history_pair_details | 108 | [history_pair_details.csv](history_pair_details.csv) | [history_pair_details.md](history_pair_details.md) |
| checkpoint_model_selections | 288 | [checkpoint_model_selections.csv](checkpoint_model_selections.csv) | [checkpoint_model_selections.md](checkpoint_model_selections.md) |
| generation_call_details | 288 | [generation_call_details.csv](generation_call_details.csv) | [generation_call_details.md](generation_call_details.md) |
| requested_routes | 4 | [requested_routes.csv](requested_routes.csv) | [requested_routes.md](requested_routes.md) |
| generation_call_aggregates | 8 | [generation_call_aggregates.csv](generation_call_aggregates.csv) | [generation_call_aggregates.md](generation_call_aggregates.md) |
| collection_audit | 1 | [collection_audit.csv](collection_audit.csv) | [collection_audit.md](collection_audit.md) |
| history_exposure_audit | 7 | [history_exposure_audit.csv](history_exposure_audit.csv) | [history_exposure_audit.md](history_exposure_audit.md) |
