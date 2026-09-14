#!/usr/bin/env bash
# Prospective command sequence; run from the Oline_HRI repository root.
# Do not execute collection until the independent review and source freeze exist.
set -euo pipefail
repair_dir=evaluation/changing_memory_repair_20260914

.venv/bin/python "$repair_dir/author_ledger.py" \
  --scenarios "$repair_dir/scenarios.json" --output "$repair_dir/authored_v1"
cp "$repair_dir/protocol_v1.md" "$repair_dir/authored_v1/protocol.md"

# Root writes offline_validation_v1 with exact regression commands, test outputs,
# source hashes, and an independent preflight_review_v1.json after source settles.
# The existing freeze requires reviewed runtime.json/expected_ledger.json/protocol.md
# hashes, approved=true, and the exact run_changing_memory.sources() dictionary.
.venv/bin/python scripts/run_changing_memory.py freeze \
  --draft "$repair_dir/authored_v1" --review "$repair_dir/preflight_review_v1.json" \
  --output "$repair_dir/frozen_v1"
.venv/bin/python scripts/run_changing_memory.py collect \
  --freeze "$repair_dir/frozen_v1" --output "$repair_dir/run_v1" \
  > "$repair_dir/collection_v1.log" 2>&1

# Collect is serialized and automatically preserves/continues untouched suffixes.
# Use a new output/version for any independent rerun; never overwrite prior data.
# These are the separately adapted analysis tools; the baseline analyzer rejects
# a subset. New independent blinded votes are required before seal-reviews.
.venv/bin/python "$repair_dir/audit_repair_collection.py" \
  --freeze "$repair_dir/frozen_v1" --run "$repair_dir/run_v1" \
  --output "$repair_dir/collection_audit_v1.json"
.venv/bin/python "$repair_dir/analyze_repair.py" prepare \
  --freeze "$repair_dir/frozen_v1" --run "$repair_dir/run_v1" \
  --output "$repair_dir/prepared_v1"

# Give only prepared_v1/public to two fresh independent assistant reviewers.
# Freeze their original reviewer_a_v1.json and reviewer_b_v1.json before unblinding.
.venv/bin/python "$repair_dir/analyze_repair.py" seal-reviews \
  --prepared "$repair_dir/prepared_v1" \
  --review-a "$repair_dir/reviewer_a_v1.json" --review-b "$repair_dir/reviewer_b_v1.json" \
  --output "$repair_dir/sealed_reviews_v1"

# If there are disagreements, obtain/freeze third blinded adjudication and add
# --adjudication PATH to resolve; original votes and disagreements remain intact.
.venv/bin/python "$repair_dir/analyze_repair.py" resolve \
  --prepared "$repair_dir/prepared_v1" --reviews "$repair_dir/sealed_reviews_v1" \
  --output "$repair_dir/analysis_v1"
.venv/bin/python "$repair_dir/render_repair_tables.py" \
  --analysis "$repair_dir/analysis_v1" --audit "$repair_dir/collection_audit_v1.json" \
  --output "$repair_dir/tables_v1"
