"""Read-only progress snapshot; never touches inference or collection files."""
import argparse
from collections import Counter
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("run_root", type=Path)
args = parser.parse_args()
sessions = sorted(args.run_root.glob("*/manifest.json"))
finished, statuses, turns, active = 0, Counter(), Counter(), []
for manifest in sessions:
    directory = manifest.parent
    observations = directory / "observations.jsonl"
    rows = []
    if observations.exists():
        for line in observations.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # A live append may not have reached its final newline.
    turns.update(row["status"] for row in rows)
    finish = directory / "finish.json"
    if finish.exists():
        finished += 1
        statuses[json.loads(finish.read_text())["status"]] += 1
    else:
        active.append({"slot": directory.name, "recorded_turns": len(rows)})
print(json.dumps({"finished_sequences": finished, "planned_sequences": 144,
                  "sequence_statuses": dict(statuses), "recorded_turns": sum(turns.values()),
                  "turn_statuses": dict(turns), "active": active}, indent=2))
