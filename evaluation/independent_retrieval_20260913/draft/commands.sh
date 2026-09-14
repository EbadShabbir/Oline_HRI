#!/usr/bin/env bash
# Run from the Oline_HRI repository. Every output path must be new.
# These are the original experiment commands, not permission to overwrite artifacts.
set -euo pipefail
export PYTHONPATH=src:scripts:tests

.venv/bin/python -m unittest \
  tests.test_independent_retrieval_adapter tests.test_independent_retrieval_runner \
  tests.test_post_memory_device_guard tests.test_evaluation_systems tests.test_routing_timing -v

.venv/bin/python scripts/run_independent_retrieval.py prepare \
  --runtime evaluation/independent_retrieval_20260913/draft/runtime.json \
  --output evaluation/independent_retrieval_20260913/prepared_snapshot_v1

.venv/bin/python scripts/smoke_independent_retrieval.py \
  --output evaluation/independent_retrieval_20260913/smoke_v3

# Independent approval is created by the separate reviewer after validation.
.venv/bin/python scripts/run_independent_retrieval.py freeze \
  --draft evaluation/independent_retrieval_20260913/draft \
  --snapshot evaluation/independent_retrieval_20260913/prepared_snapshot_v1 \
  --review evaluation/independent_retrieval_20260913/reviews/independent_preflight_review_v2.json \
  --output evaluation/independent_retrieval_20260913/frozen_v1

.venv/bin/python scripts/run_independent_retrieval.py collect \
  --freeze evaluation/independent_retrieval_20260913/frozen_v1 \
  --output evaluation/independent_retrieval_20260913/run_v1

# Offline review export and final analysis commands are also recorded in the report.
