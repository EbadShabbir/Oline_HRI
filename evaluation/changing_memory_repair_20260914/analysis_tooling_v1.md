# Separate repair-analysis tooling

These copies preserve the sealed baseline tools. They perform no inference or
semantic scoring and never change original baseline reviews. Their reports
describe a targeted matched development regression selected after baseline
failures, not held-out evaluation. New answers require new blinded votes.

- `analyze_repair.py` copies `scripts/analyze_changing_memory_v2.py`, preserving
  its evidence parser, vote checks, diagnostic functions and aggregation. A
  schedule validator derives counts rather than enforcing 288. Preparation and
  final provenance record the derived workload; report prose uses its counts.
- `audit_repair_collection.py` copies the original collection auditor. All audit
  classes and individual checks remain unchanged. Expected checkpoint, process
  segment and database totals derive from the reviewed schedule. Every scenario
  must still have separate correction/deletion/expiry branches and all stages.
- `render_repair_tables.py` copies the original renderer with the new analyzer
  source hash pinned. It verifies the frozen schedule/ledger and requires every
  expected checkpoint, exact expected state/rubric equality, complete stage
  coverage and correct pair/audit denominators. All aggregation helpers are
  unchanged; no answer text is rescored.

The shared workload-validation function is included directly in each file so a
single recorded source hash covers all execution dependencies. An AST regression
requires the three copies to match. It also proves that diagnostics, frozen
review handling, scalar aggregation, pair aggregation and auditor classes have
not changed. Workload validation rejects duplicated/truncated schedules and
misbound questions, times, history modes, restart flags or scenario identities.

Five new offline tests verify both 288- and 96-checkpoint preparation, frozen
fabricated reviews, final resolution and table rendering, plus negative integrity
cases. The ten original synthetic auditor tests pass against the new copy. The
synthetic answers are fixtures and are not experimental observations. Test logs,
commands and source hashes are in `analysis_tooling_validation_v1.json`.

`baseline_matched_counts_v1.json` aggregates the original frozen votes on the
same 96 planned checkpoint IDs: 39 useful responses, 30 forbidden disclosures,
93 delivered and three withheld. Those descriptive original-baseline counts are
not repaired observations. Preserve this distinction in the final comparison.

Follow `planned_commands.sh` one stage at a time. Authoring has already run; do
not rerun its exclusive-create command on `authored_v1`. Collection must follow
the independent source/configuration/protocol preflight review and fresh runtime
freeze. Existing output paths always remain immutable.
