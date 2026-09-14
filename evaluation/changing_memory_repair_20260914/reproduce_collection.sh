#!/usr/bin/env bash
# Run from submodules/Oline_HRI; invokes REAL installed inference.
# Example: bash evaluation/changing_memory_repair_20260914/reproduce_collection.sh /tmp/clara-memory-new-run
set -euo pipefail
if [[ $# -ne 1 ]]; then
  echo 'Usage: reproduce_collection.sh NEW_OUTPUT_DIRECTORY' >&2
  exit 2
fi
experiment_output=$1
if [[ -e "$experiment_output" ]]; then
  echo 'Output must not already exist; original artifacts must be preserved.' >&2
  exit 2
fi
mkdir -m 700 -- "$experiment_output"
export PYTHONPATH=src:scripts
experiment_inputs=evaluation/changing_memory_repair_20260914
.venv/bin/python scripts/run_changing_memory.py freeze \
  --draft "$experiment_inputs/authored_v1" \
  --review "$experiment_inputs/preflight_review_v1.json" \
  --output "$experiment_output/frozen"
.venv/bin/python - "$experiment_inputs/frozen_v2/freeze.json" "$experiment_output/frozen/freeze.json" <<'PY'
import json
import sys
from pathlib import Path
original, current = [json.loads(Path(p).read_text()) for p in sys.argv[1:]]
keys = ('source_sha256', 'config', 'models', 'embedding_assets', 'packages',
        'python', 'generation_seed', 'device_policy', 'routing_policy',
        'retain_large_model', 'ollama_version', 'logical_clock')
changed = [key for key in keys if original[key] != current[key]]
if changed:
    raise SystemExit('Reproduction conditions changed; obtain renewed prospective review before inference: ' + ', '.join(changed))
PY
.venv/bin/python scripts/run_changing_memory.py collect \
  --freeze "$experiment_output/frozen" \
  --output "$experiment_output/run"
echo 'Collection saved. New delivered answers require new independent blinded reviews.'
# Changed conditions require renewed prospective review; do not bypass a failed
# comparison. Host identity is captured anew. Resource leases and guards
# serialize this run against other known Jetson experiments. This script neither
# reuses original answer judgments nor changes OS settings or memory rows.
