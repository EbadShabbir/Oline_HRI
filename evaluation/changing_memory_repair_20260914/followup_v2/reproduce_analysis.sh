#!/usr/bin/env bash
# Recompute sealed assistant judgments; no inference or rescoring.
# Run from submodules/Oline_HRI with a new output directory.
set -euo pipefail
if [[ $# -ne 1 || -e "$1" ]]; then
  echo 'Usage: reproduce_analysis.sh NEW_OUTPUT_DIRECTORY' >&2
  exit 2
fi
analysis_output=$1
mkdir -m 700 -- "$analysis_output"
experiment_tools=evaluation/changing_memory_repair_20260914
experiment_inputs="$experiment_tools/followup_v2"
export PYTHONPATH=src:scripts
adjudication_args=()
if [[ -f "$experiment_inputs/adjudication_v1.json" ]]; then
  adjudication_args=(--adjudication "$experiment_inputs/adjudication_v1.json")
fi
.venv/bin/python "$experiment_tools/analyze_repair.py" resolve \
  --prepared "$experiment_inputs/prepared_v1" \
  --reviews "$experiment_inputs/sealed_reviews_v1" \
  "${adjudication_args[@]}" \
  --output "$analysis_output/analysis_v1"
.venv/bin/python "$experiment_tools/render_repair_tables.py" \
  --analysis "$analysis_output/analysis_v1" \
  --audit "$experiment_inputs/collection_audit_v1.json" \
  --output "$analysis_output/tables"
.venv/bin/python "$experiment_tools/compare_matched.py" \
  --baseline "$experiment_tools/analysis_v1" \
  --repair "$analysis_output/analysis_v1" \
  --expected-checkpoints 24 --output "$analysis_output/matched_comparison"
.venv/bin/python "$experiment_tools/compare_matched.py" \
  --baseline evaluation/changing_memory_20260914/analysis_v2 \
  --repair "$analysis_output/analysis_v1" \
  --expected-checkpoints 24 --output "$analysis_output/original_baseline_comparison"
MPLCONFIGDIR=/tmp/clara-memory-matplotlib python3 "$experiment_tools/render_repair_figure.py" \
  --analysis "$analysis_output/analysis_v1" \
  --output "$analysis_output/figures"
