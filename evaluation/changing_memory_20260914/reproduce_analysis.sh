#!/usr/bin/env bash
# Recompute the original sealed judgments; no model inference or rescoring.
# Run from submodules/Oline_HRI, with a NEW output directory argument.
set -euo pipefail
if [[ $# -ne 1 || -e "$1" ]]; then
  echo 'Usage: reproduce_analysis.sh NEW_OUTPUT_DIRECTORY' >&2
  exit 2
fi
analysis_output=$1
mkdir -m 700 -- "$analysis_output"
experiment_inputs=evaluation/changing_memory_20260914
export PYTHONPATH=src:scripts
.venv/bin/python scripts/analyze_changing_memory.py resolve \
  --prepared "$experiment_inputs/prepared_final_v1" \
  --reviews "$experiment_inputs/sealed_reviews_v1" \
  --output "$analysis_output/analysis_v1"
.venv/bin/python scripts/analyze_changing_memory_v2.py resolve \
  --prepared "$experiment_inputs/prepared_final_v1" \
  --reviews "$experiment_inputs/sealed_reviews_v1" \
  --output "$analysis_output/analysis_v2"
.venv/bin/python "$experiment_inputs/render_report_tables.py" \
  --analysis "$analysis_output/analysis_v2" \
  --audit "$experiment_inputs/collection_audit_v1.json" \
  --output "$analysis_output/tables"
MPLCONFIGDIR=/tmp/clara-memory-matplotlib python3 "$experiment_inputs/render_checkpoint_figure.py" \
  --analysis "$analysis_output/analysis_v2" \
  --output "$analysis_output/figures"
