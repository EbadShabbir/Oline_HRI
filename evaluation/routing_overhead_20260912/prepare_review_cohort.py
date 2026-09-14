"""Read completed attempts only; add supplied evidence to anonymous review groups.

This offline review adapter never invokes inference or modifies frozen source.
Stable content IDs permit judgments on exact duplicate groups to be reused
across incremental cohorts. Timing, system names and frequency stay private.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import random


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def build(run_root, workload):
    groups, mapping = {}, []
    for finish in sorted(run_root.glob("*/finish.json")):
        observations = finish.parent / "observations.jsonl"
        if not observations.exists():
            continue
        rows = [json.loads(line) for line in observations.read_text().splitlines()]
        known = {(r.get("id"), r.get("index")) for r in rows}
        durable = finish.parent / "events.jsonl"
        for line in durable.read_text().splitlines() if durable.exists() else []:
            event = json.loads(line)
            if event.get("kind") == "turn_attempt" and (event.get("id"), event.get("index")) not in known:
                rows.append({**event, "status": "interrupted"})
                known.add((event.get("id"), event.get("index")))
        for raw in rows:
            response = raw.get("response") or {}
            supplied = set((raw.get("memory") or {}).get("supplied_ids", []))
            matches = {m["memory"]["id"]: m["memory"]
                       for call in raw.get("retrieval_calls", []) for m in call.get("matches", [])}
            content = {
                "question": raw["prompt"], "history": raw.get("history_before", []),
                "rubric": workload["rubrics"][raw["id"]],
                "prepared_memory": workload["memory_seed"],
                "answer": response.get("speech", ""), "response_complete": raw["status"] == "ok",
                "answer_constraint": raw.get("answer_constraint"),
                "supplied_evidence": [matches[i] for i in sorted(supplied) if i in matches],
                "cited_memory_ids": response.get("memory_used", []),
            }
            aid = sha256(canonical(content).encode()).hexdigest()[:24]
            groups[aid] = {"answer_id": aid, **content}
            mapping.append({"answer_id": aid, "attempt_directory": str(finish.parent.relative_to(run_root)),
                            "id": raw["id"], "index": raw["index"], "arm": raw["arm"],
                            "sequence_id": raw["sequence_id"], "repetition": raw["repetition"]})
    return groups, mapping


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--previous", nargs="*", type=Path, default=[])
    args = parser.parse_args()
    workload = json.loads(args.workload.read_text())
    groups, mapping = build(args.run_root, workload)
    prior = {json.loads(line)["answer_id"] for path in args.previous for line in path.read_text().splitlines()}
    packet = [g for aid, g in groups.items() if aid not in prior]
    random.SystemRandom().shuffle(packet)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    def write(name, data):
        (args.output_dir / name).write_text(json.dumps(data, indent=2, ensure_ascii=False)+"\n")
    (args.output_dir / "packet.jsonl").write_text("".join(canonical(g)+"\n" for g in packet))
    write("private_mapping.json", mapping)
    write("provenance.json", {
        "created_at": datetime.now(timezone.utc).isoformat(), "observed_attempts": len(mapping),
        "all_unique_groups": len(groups), "new_groups": len(packet),
        "adapter_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "workload_sha256": sha256(args.workload.read_bytes()).hexdigest(),
        "previous_packet_sha256": {str(p): sha256(p.read_bytes()).hexdigest() for p in args.previous},
        "grouping": "exact frozen question, history, rubric, prepared and supplied evidence, citations, delivered answer, delivery status and helper constraint",
        "scope": "offline blinded review only; no timing/source/settings changes",
    })
    print(f"{len(mapping)} attempts; {len(groups)} unique groups; {len(packet)} new review groups")


if __name__ == "__main__":
    main()
