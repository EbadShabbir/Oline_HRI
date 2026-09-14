"""Correct generated prose about the startup boundary; no numerical changes."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("report_dir", type=Path)
args = parser.parse_args()
path = args.report_dir / "report.md"
before = path.read_text()
old = "Startup includes prepared-memory/client setup and is added once to the four request intervals."
new = ("Startup begins at embedding initialization and includes prepared-memory and router/Conversation setup; "
       "it is added once to the four request intervals. Client/monitor/admission setup precedes this interval "
       "and belongs to the separately recorded process envelope.")
if before.count(old) != 1:
    raise ValueError("Expected exactly one original startup-scope sentence")
after = before.replace(old, new)
with (args.report_dir / "report.generated.md").open("x") as stream:
    stream.write(before)
with (args.report_dir / "prose_correction.json").open("x") as stream:
    json.dump({"reason": "Match the actual monotonic sequence/startup boundary in the frozen runner",
               "before_sha256": sha256(before.encode()).hexdigest(),
               "after_sha256": sha256(after.encode()).hexdigest(),
               "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
               "original": old, "corrected": new,
               "numerical_data_changed": False, "frozen_analyzer_changed": False}, stream, indent=2)
path.write_text(after)
