#!/usr/bin/env python3
"""Read-only operator progress; partial JSONL lines are not checkpoint records."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

root = Path(__file__).resolve().parent
statuses, scenarios = Counter(), Counter()
for path in (root / "run_v2").rglob("answers.jsonl"):
    for line in path.read_text().splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("checkpoint_id"):
            statuses[row["status"]] += 1
            scenarios[row["scenario_id"]] += 1
print(json.dumps({"time": datetime.now(timezone.utc).isoformat(),
    "checkpoints": sum(statuses.values()), "status": statuses,
    "scenarios": dict(sorted(scenarios.items())),
    "finished": (root / "run_v2/finish.json").exists(),
    "sealed": (root / "run_v2/seal.json").exists()}))
print((root / "collection_v2.log").read_text()[-240:])
