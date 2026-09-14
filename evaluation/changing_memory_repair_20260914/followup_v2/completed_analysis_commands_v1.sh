#!/usr/bin/env bash
# Completed followup analysis command history; not a runnable analysis pipeline.
# HISTORICAL OUTPUT PATHS ALREADY EXIST: never rerun these commands into them.
# This document exits before any command. For new outputs, use reproduce_analysis.sh.
# Exact argument arrays below are copied from the cited command/provenance records.
# Records using sys.argv omit the interpreter; a compatible interpreter is included.
# Added PYTHONPATH prefixes are reproduction settings, not claims about the
# original shell environment. Root's analysis calls used .venv/bin/python directly;
# the original figure call set MPLCONFIGDIR. Recorded argument arrays are preserved.
# Stage grouping is not a claim about wall-clock execution order;
# original timestamps remain in the receipts. No command here generates new answers.
# Both fresh assistant reviewers independently authored their packet-bound review
# files; no shell command substitutes for those judgments.
exit 0

set -euo pipefail

# Prepare all 24 checkpoints for fresh blinded review.
# Argument source: prepared_v1/private/provenance.json
env PYTHONPATH=src:scripts .venv/bin/python evaluation/changing_memory_repair_20260914/analyze_repair.py prepare --freeze evaluation/changing_memory_repair_20260914/followup_v2/frozen_v1 --run evaluation/changing_memory_repair_20260914/followup_v2/run_v1 --output evaluation/changing_memory_repair_20260914/followup_v2/prepared_v1

# Freeze both reviews; no disagreement required adjudication.
# Argument source: sealed_reviews_v1/review_freeze.json
env PYTHONPATH=src:scripts .venv/bin/python evaluation/changing_memory_repair_20260914/analyze_repair.py seal-reviews --prepared evaluation/changing_memory_repair_20260914/followup_v2/prepared_v1 --review-a evaluation/changing_memory_repair_20260914/followup_v2/review_a_v1.json --review-b evaluation/changing_memory_repair_20260914/followup_v2/review_b_v1.json --output evaluation/changing_memory_repair_20260914/followup_v2/sealed_reviews_v1

# Resolve frozen votes and unblind diagnostics.
# Argument source: analysis_v1/provenance.json
env PYTHONPATH=src:scripts .venv/bin/python evaluation/changing_memory_repair_20260914/analyze_repair.py resolve --prepared evaluation/changing_memory_repair_20260914/followup_v2/prepared_v1 --reviews evaluation/changing_memory_repair_20260914/followup_v2/sealed_reviews_v1 --output evaluation/changing_memory_repair_20260914/followup_v2/analysis_v1

# Run independent collection integrity audit.
# Argument source: collection_audit_v1_command.json
env PYTHONPATH=src:scripts .venv/bin/python evaluation/changing_memory_repair_20260914/audit_repair_collection.py --freeze evaluation/changing_memory_repair_20260914/followup_v2/frozen_v1 --run evaluation/changing_memory_repair_20260914/followup_v2/run_v1 --output evaluation/changing_memory_repair_20260914/followup_v2/collection_audit_v1.json

# Render tables from existing frozen judgments.
# Argument source: tables_v1/provenance.json
env PYTHONPATH=src:scripts /home/b2jetson/convo_hri_cascading/submodules/Oline_HRI/.venv/bin/python evaluation/changing_memory_repair_20260914/render_repair_tables.py --analysis evaluation/changing_memory_repair_20260914/followup_v2/analysis_v1 --audit evaluation/changing_memory_repair_20260914/followup_v2/collection_audit_v1.json --output evaluation/changing_memory_repair_20260914/followup_v2/tables_v1

# Compare the exact cm04 subset of the first repair.
# Argument source: compared_first_repair_v1/provenance.json
env PYTHONPATH=src:scripts /home/b2jetson/convo_hri_cascading/submodules/Oline_HRI/.venv/bin/python evaluation/changing_memory_repair_20260914/compare_matched.py --baseline evaluation/changing_memory_repair_20260914/analysis_v1 --repair evaluation/changing_memory_repair_20260914/followup_v2/analysis_v1 --expected-checkpoints 24 --output evaluation/changing_memory_repair_20260914/followup_v2/compared_first_repair_v1

# Compare the exact cm04 subset of the original baseline.
# Argument source: compared_original_baseline_v1/provenance.json
env PYTHONPATH=src:scripts /home/b2jetson/convo_hri_cascading/submodules/Oline_HRI/.venv/bin/python evaluation/changing_memory_repair_20260914/compare_matched.py --baseline evaluation/changing_memory_20260914/analysis_v2 --repair evaluation/changing_memory_repair_20260914/followup_v2/analysis_v1 --expected-checkpoints 24 --output evaluation/changing_memory_repair_20260914/followup_v2/compared_original_baseline_v1

# Render checkpoint figure from existing frozen judgments.
# Argument source: figures_v1/provenance.json
env PYTHONPATH=src:scripts MPLCONFIGDIR=/tmp/clara-memory-matplotlib python3 evaluation/changing_memory_repair_20260914/render_repair_figure.py --analysis evaluation/changing_memory_repair_20260914/followup_v2/analysis_v1 --output evaluation/changing_memory_repair_20260914/followup_v2/figures_v1

# Completed independent output reproduction, exit 0; no inference or rescoring.
# Exact shell command from analysis_reproduction_v1.json; 41 data checks passed.
bash evaluation/changing_memory_repair_20260914/followup_v2/reproduce_analysis.sh /tmp/clara-memory-followup-analysis-reproduction-v1 > evaluation/changing_memory_repair_20260914/followup_v2/analysis_reproduction_v1.log 2>&1

# The completed original collector invocations and source-freeze preparation
# remain in ../commands.sh. This document adds no collection, retry or new score.
