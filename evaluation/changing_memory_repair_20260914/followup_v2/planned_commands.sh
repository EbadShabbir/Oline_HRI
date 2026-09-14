#!/usr/bin/env bash
# Prospective staged command history. Run from Oline_HRI root, one stage at a time.
# Authoring already ran; all producers refuse existing output paths.
set -euo pipefail
repair_dir=evaluation/changing_memory_repair_20260914
followup_dir="$repair_dir/followup_v2"

.venv/bin/python "$followup_dir/author_ledger.py" \
  --scenarios "$followup_dir/scenarios.json" --output "$followup_dir/authored_v1"
cp "$followup_dir/protocol_v1.md" "$followup_dir/authored_v1/protocol.md"

# Before the following: finish/seal/audit first96; implement the separate amendment;
# complete offline_validation_v1; independently review exact source/test hashes;
# write preflight_review_v1.json with the three authored hashes and sources().
.venv/bin/python scripts/run_changing_memory.py freeze \
  --draft "$followup_dir/authored_v1" --review "$followup_dir/preflight_review_v1.json" \
  --output "$followup_dir/frozen_v1"
.venv/bin/python scripts/run_changing_memory.py collect \
  --freeze "$followup_dir/frozen_v1" --output "$followup_dir/run_v1" \
  > "$followup_dir/collection_v1.log" 2>&1
.venv/bin/python "$repair_dir/audit_repair_collection.py" \
  --freeze "$followup_dir/frozen_v1" --run "$followup_dir/run_v1" \
  --output "$followup_dir/collection_audit_v1.json"
.venv/bin/python "$repair_dir/analyze_repair.py" prepare \
  --freeze "$followup_dir/frozen_v1" --run "$followup_dir/run_v1" \
  --output "$followup_dir/prepared_v1"

# Give only prepared_v1/public to fresh independent reviewers; freeze both votes.
.venv/bin/python "$repair_dir/analyze_repair.py" seal-reviews \
  --prepared "$followup_dir/prepared_v1" \
  --review-a "$followup_dir/reviewer_a_v1.json" --review-b "$followup_dir/reviewer_b_v1.json" \
  --output "$followup_dir/sealed_reviews_v1"
# Add --adjudication PATH only after any disagreements have third blinded review.
.venv/bin/python "$repair_dir/analyze_repair.py" resolve \
  --prepared "$followup_dir/prepared_v1" --reviews "$followup_dir/sealed_reviews_v1" \
  --output "$followup_dir/analysis_v1"
.venv/bin/python "$repair_dir/render_repair_tables.py" \
  --analysis "$followup_dir/analysis_v1" --audit "$followup_dir/collection_audit_v1.json" \
  --output "$followup_dir/tables_v1"
.venv/bin/python "$repair_dir/compare_matched.py" \
  --baseline "$repair_dir/analysis_v1" --repair "$followup_dir/analysis_v1" \
  --expected-checkpoints 24 --output "$followup_dir/compared_first_repair_v1"
.venv/bin/python "$repair_dir/compare_matched.py" \
  --baseline evaluation/changing_memory_20260914/analysis_v2 \
  --repair "$followup_dir/analysis_v1" --expected-checkpoints 24 \
  --output "$followup_dir/compared_original_baseline_v1"
