#!/usr/bin/env bash
# Run from the Oline_HRI repository root. Every output directory must be new.
set -euo pipefail
experiment=evaluation/routing_overhead_20260912
action=${1:-help}
destination=${2:-}
if [[ "$action" == help || -z "$destination" ]]; then
  echo 'Usage: bash evaluation/routing_overhead_20260912/commands.sh analyze|collect NEW_OUTPUT_DIRECTORY'
  echo 'analyze reproduces the reviewed tables and figures without inference.'
  echo 'collect performs a new complete 576-turn Jetson experiment under the validated controls.'
  exit 0
fi
[[ ! -e "$destination" ]] || { echo 'Output directory already exists' >&2; exit 1; }
case "$action" in
  analyze)
    mkdir -p "$destination"
    .venv/bin/python "$experiment/assemble_reviews.py" \
      --cohort-root "$experiment/review_cohorts" --run-root "$experiment/run_v2" \
      --workload "$experiment/frozen_v2/workload.json" \
      --adjudications "$experiment/adjudications/cohort28_resolved.jsonl" \
      --output-dir "$destination/reviews"
    MPLCONFIGDIR=/tmp/clara-routing-mpl PYTHONPATH=src:scripts \
      /tmp/clara-step4-plots/bin/python "$experiment/analyze_continued.py" analyze \
      --run-root "$experiment/run_v2" --previous-root "$experiment/run_v1" \
      --previous-freeze "$experiment/frozen_v1/freeze.json" \
      --freeze "$experiment/frozen_v2/freeze.json" --workload "$experiment/frozen_v2/workload.json" \
      --blind-dir "$destination/reviews/blind" --reviews "$destination/reviews/resolved.jsonl" \
      --output-dir "$destination/report"
    .venv/bin/python "$experiment/correct_report_scope.py" "$destination/report"
    PYTHONPATH=src:scripts .venv/bin/python "$experiment/report_details.py" \
      --run-root "$experiment/run_v2" --previous-root "$experiment/run_v1" \
      --previous-freeze "$experiment/frozen_v1/freeze.json" \
      --freeze "$experiment/frozen_v2/freeze.json" --workload "$experiment/frozen_v2/workload.json" \
      --blind-dir "$destination/reviews/blind" --reviews "$destination/reviews/resolved.jsonl" \
      --output-dir "$destination/details"
    PYTHONPATH=src:scripts .venv/bin/python "$experiment/final_collection_audit.py" \
      --output-dir "$destination/integrity"
    ;;
  collect)
    # Refuse source, package, settings or installed-model drift from this run.
    PYTHONPATH=src:scripts .venv/bin/python -c 'from argparse import Namespace; from pathlib import Path; import run_routing_overhead as r; p=Path("evaluation/routing_overhead_20260912/frozen_v2"); r.check_freeze(Namespace(workload=p/"workload.json", freeze=p/"freeze.json"))'
    mkdir -p "$destination"
    PYTHONPATH=src:scripts .venv/bin/python -m unittest discover -s tests
    PYTHONPATH=src:scripts .venv/bin/python "$experiment/validate_workload.py" \
      --output "$destination/workload_validation.json"
    PYTHONPATH=src:scripts .venv/bin/python scripts/run_routing_overhead.py freeze \
      --workload "$experiment/workload.json" --protocol "$experiment/protocol_v2.md" \
      --validation "$experiment/offline_validation_v2.json" --output-dir "$destination/frozen"
    PYTHONPATH=src:scripts .venv/bin/python scripts/run_routing_overhead.py run \
      --workload "$destination/frozen/workload.json" --freeze "$destination/frozen/freeze.json" \
      --output-dir "$destination/run"
    ;;
  *) echo 'Unknown action' >&2; exit 2 ;;
esac
