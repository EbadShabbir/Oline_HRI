#!/usr/bin/env bash
# Commands used for this experiment. Collection commands create NEW directories.
# For a replication change EXPERIMENT_DIR; never overwrite the sealed original.
set -euo pipefail
cd /home/b2jetson/convo_hri_cascading/submodules/Oline_HRI
export PYTHONPATH=src:scripts
EXPERIMENT_DIR=evaluation/matched_evidence_20260912

# Offline validation (no generator calls).
.venv/bin/python -m unittest discover -s tests -p 'test_matched_evidence.py' -v
.venv/bin/python -m unittest tests.test_post_memory_device_guard tests.test_evaluation_telemetry tests.test_complete_system_device_guard -v
.venv/bin/python -m unittest discover -s tests -p 'test_matched_evidence_analysis.py' -v

# Approved exact dataset bytes; metadata-only local Ollama checks and source freeze.
.venv/bin/python scripts/run_matched_evidence.py freeze \
  --dataset evaluation/matched_evidence_20260912_draft/dataset.json \
  --review evaluation/matched_evidence_20260912_draft/preflight_review.json \
  --protocol evaluation/matched_evidence_protocol_draft_20260912.md \
  --output "$EXPERIMENT_DIR/frozen_v1"

# Four excluded smoke attempts; then exactly 240 primary attempts.
.venv/bin/python scripts/run_matched_evidence.py collect \
  --freeze "$EXPERIMENT_DIR/frozen_v1" --output "$EXPERIMENT_DIR/smoke_v1" --smoke
.venv/bin/python scripts/run_matched_evidence.py collect \
  --freeze "$EXPERIMENT_DIR/frozen_v1" --output "$EXPERIMENT_DIR/run_v1"

# Export both blinded review packets; assistant reviews are separate manual steps.
.venv/bin/python scripts/analyze_matched_evidence.py blind \
  --freeze "$EXPERIMENT_DIR/frozen_v1" --run "$EXPERIMENT_DIR/run_v1" \
  --output "$EXPERIMENT_DIR/blinded_v1"
# Freeze both independent review files before comparing or revealing mapping.
.venv/bin/python scripts/analyze_matched_evidence.py disagreements \
  --blind "$EXPERIMENT_DIR/blinded_v1" \
  --review-a "$EXPERIMENT_DIR/reviews/reviewer_a.jsonl" \
  --review-b "$EXPERIMENT_DIR/reviews/reviewer_b.jsonl" \
  --output "$EXPERIMENT_DIR/disagreements_v1"
# Third blinded assistant resolves every disagreement before unblinding.
.venv/bin/python scripts/analyze_matched_evidence.py analyze \
  --freeze "$EXPERIMENT_DIR/frozen_v1" --run "$EXPERIMENT_DIR/run_v1" \
  --blind "$EXPERIMENT_DIR/blinded_v1" \
  --review-a "$EXPERIMENT_DIR/reviews/reviewer_a.jsonl" \
  --review-b "$EXPERIMENT_DIR/reviews/reviewer_b.jsonl" \
  --adjudication "$EXPERIMENT_DIR/reviews/adjudication.jsonl" \
  --output "$EXPERIMENT_DIR/analysis_v1"

# Offline independent device/resource audit and figure rendering.
.venv/bin/python scripts/audit_matched_evidence_results.py \
  --freeze "$EXPERIMENT_DIR/frozen_v1" --run "$EXPERIMENT_DIR/run_v1" \
  --output "$EXPERIMENT_DIR/resource_audit_v1"
MPLCONFIGDIR=/tmp/clara-matched-mpl /tmp/clara-step4-plots/bin/python \
  scripts/render_matched_evidence.py --analysis "$EXPERIMENT_DIR/analysis_v1" \
  --output "$EXPERIMENT_DIR/figures_v1"
.venv/bin/python scripts/report_matched_evidence_results.py --experiment "$EXPERIMENT_DIR"

# If the temporary plotting environment is absent, recreate it before rendering:
# python3 -m venv /tmp/clara-step4-plots
# /tmp/clara-step4-plots/bin/python -m pip install -r "$EXPERIMENT_DIR/plot_requirements.txt"
# Inference uses the existing Jetson environment; installed package inventory is
# saved in inference_environment_packages.txt. No packages changed for collection.

# Recheck the original frozen results independently, without any inference.
# Choose a fresh output directory; this checker refuses to overwrite results.
python3 evaluation/matched_evidence_20260912/final_numeric_audit_v1/check_frozen_results.py \
  --output /tmp/clara-matched-final-numeric-recheck
