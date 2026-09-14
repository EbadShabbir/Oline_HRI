"""Independent metadata-only audit; never prints or judges collected answer text."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT = ROOT / "evaluation/independent_retrieval_20260913"
FREEZE = EXPERIMENT / "frozen_v1"
RUN = EXPERIMENT / "run_v1"


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def verify(directory):
    hashes = read(directory / "seal.json")["sha256"]
    actual = {str(path.relative_to(directory)) for path in directory.rglob("*")
              if path.is_file() and path != directory / "seal.json"}
    assert set(hashes) == actual, "seal file set differs"
    assert all(digest(directory / name) == value for name, value in hashes.items()), "sealed bytes differ"


def main():
    verify(FREEZE)
    verify(RUN)
    frozen = read(FREEZE / "freeze.json")
    runtime = read(FREEZE / "runtime.json")
    terminal = read(RUN / "batch_finish.json")
    assert terminal["source_unchanged"] is True
    assert all(digest(ROOT / name) == value for name, value in frozen["source_sha256"].items())
    assert len(frozen["source_sha256"]) == 44
    slots = {slot["slot"]: slot for slot in frozen["schedule"]}
    cases = {case["id"]: case for case in runtime["execution_cases"]}
    planned = [(slot["slot"], identifier) for slot in frozen["schedule"] for identifier in slot["request_ids"]]
    observed, status_counts, fragment_counts = [], Counter(), []
    snapshot = digest(FREEZE / "prepared_snapshot/memory.sqlite3")
    baseline = previous_end = None
    for entry in terminal["sessions"]:
        directory = Path(entry["directory"])
        verify(directory)
        slot = slots[entry["slot"]]
        manifest, summary = read(directory / "manifest.json"), read(directory / "summary.json")
        assert manifest["slot"] == slot
        assert manifest["freeze_sha256"] == digest(FREEZE / "freeze.json")
        config = deepcopy(frozen["config"])
        timeout = config["ollama"]["request_timeout_seconds"] if slot["model"] == config["ollama"]["small_model"] else config["ollama"]["large_request_timeout_seconds"]
        for key in ("small_model", "general_large_model", "large_model"):
            config["ollama"][key] = slot["model"]
        config["ollama"]["request_timeout_seconds"] = timeout
        assert manifest["config"] == config and manifest["device_policy"] == frozen["device_policy"]
        assert not summary["cleanup_errors"]
        rows = lines(directory / "observations.jsonl")
        starts = [event["request_id"] for event in lines(directory / "events.jsonl") if event.get("event") == "request_start"]
        assert starts == [row["case"]["id"] for row in rows]
        assert summary["attempted"] == len(rows) and summary["planned"] == 48
        assert [row["case"]["id"] for row in rows] == slot["request_ids"][:len(rows)]
        checked = read(directory / "snapshot_verification.json")
        assert checked["unchanged"] and checked["before"] == checked["after"] == snapshot
        assert digest(directory / "memory.sqlite3") == read(directory / "setup.json")["snapshot_sha256"] == snapshot
        for state in (read(directory / "start.json"), read(directory / "finish.json")):
            baseline = state if baseline is None else baseline
            assert state["resident_models"] == []
            assert all(state[key] == baseline[key] for key in ("boot_id", "thermal_trip_events", "power_mode"))
            assert state["memory"]["swap_total_kib"] == baseline["memory"]["swap_total_kib"]
        for index, row in enumerate(rows, 1):
            assert row["case"] == cases[row["case"]["id"]]
            assert row["index"] == index
            assert all(row[key] == slot[key] for key in ("slot", "model", "policy", "repetition"))
            assert row["wall_ns"] == row["finished_monotonic_ns"] - row["started_monotonic_ns"] >= 0
            assert previous_end is None or row["started_monotonic_ns"] >= previous_end
            previous_end = row["finished_monotonic_ns"]
            assert row["status"] in ("ok", "error", "interrupted")
            assert row["status"] != "interrupted" or index == len(rows)
            observed.append((slot["slot"], row["case"]["id"]))
            status_counts[row["status"]] += 1
        fragment_counts.append({"slot": slot["slot"], "attempted": len(rows), "status": summary["status"]})
    assert observed == planned[:len(observed)] and len(set(observed)) == len(observed)
    assert len(observed) == 157 and status_counts == {"ok": 156, "interrupted": 1}
    assert len(planned) - len(observed) == 707
    assert len(terminal["rejected_sessions"]) == 11
    result = {"created_at": datetime.now(timezone.utc).isoformat(), "passed": True,
              "reviewer": "independent assistant /root/audit_design",
              "scope": "Independent metadata arithmetic and seals; no answer text printed or semantically judged.",
              "auditor_sha256": digest(Path(__file__)), "freeze_seal_sha256": digest(FREEZE / "seal.json"),
              "prior_run_seal_sha256": digest(RUN / "seal.json"), "original_sources_unchanged": 44,
              "observed_attempts": len(observed), "remaining_attempts": len(planned) - len(observed),
              "status_counts": dict(status_counts), "fragments": fragment_counts,
              "preserved_rejected_admissions": len(terminal["rejected_sessions"]),
              "next_slot": planned[len(observed)][0], "next_scheduled_index": 14,
              "next_case_id": planned[len(observed)][1], "human_validation": "pending"}
    output = Path(__file__).with_name("continuation_prefix_metadata_v1.json")
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
