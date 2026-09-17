"""Preserve immutable delivered-text packets, blinded to implementation outputs."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--stop", type=int)
    args = parser.parse_args()
    payload = json.loads(args.cases.read_text())
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    rows = []
    for line in args.observations.read_bytes().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            break
    stop = len(rows) if args.stop is None else args.stop
    assert 0 <= args.start < stop <= len(rows) <= len(cases)
    assert [row["id"] for row in rows] == [case["id"] for case in cases[:len(rows)]]
    packet = []
    for case, row in zip(cases[args.start:stop], rows[args.start:stop]):
        assert case == row["case"]
        packet.append({"id": case["id"], "text": case["text"],
                       "declared_prior_turns": case.get("prior_turns", []),
                       "rubric": case["rubric"], "status": row["status"],
                       "delivered_text": row.get("delivered_text", ""),
                       "execution_failed": row["status"] != "ok"})
    result = {"created_at": datetime.now(timezone.utc).isoformat(),
              "cases_sha256": sha256(args.cases.read_bytes()).hexdigest(),
              "scope": "Complete delivered text; routes, model identity, timing, internal verdicts and withheld outputs hidden.",
              "evidence_contract": "Empty personal store. Current assertions and benign supplied drafts can support answers; assistant guesses and prior personal values cannot authorize recall.",
              "rubric_conventions": payload.get("rubric_conventions", {}) if isinstance(payload, dict) else {},
              "cases": packet}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"packet": str(args.output), "cases": len(packet),
                      "sha256": sha256(args.output.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
