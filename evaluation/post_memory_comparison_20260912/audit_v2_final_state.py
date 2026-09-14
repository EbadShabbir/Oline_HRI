"""Read-only final host/configuration audit after all nine v2 sessions finish."""

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from run_post_memory_comparison import source_hashes
from oline_hri.evaluation_model_pairs import (
    capture_safety_snapshot, _installed_models, _model_metadata, _http_json,
)
import complete_system_device_guard as original_guard
import post_memory_device_guard as revised_guard


def read(path):
    return json.loads(path.read_text())


def swap_topology(raw):
    rows = []
    for line in raw.splitlines()[1:]:
        name, kind, size, used, priority = line.split()
        rows.append({"device": name, "type": kind, "size_kib": int(size),
                     "priority": int(priority)})
    return rows


def main():
    frozen = read(HERE / "frozen_v2/freeze.json")
    before = frozen["pre_freeze_snapshot"]
    preparation = read(HERE / "preparation_v2.json")
    run = HERE / "run_v2_resumed"
    terminal = read(run / "batch_finish.json")
    order = [(arm, repetition) for repetition, arms in enumerate(
        frozen["counterbalanced_arm_orders"], 1) for arm in arms]
    summaries = []
    for index, (arm, repetition) in enumerate(order, 1):
        directory = run / f"{index:02d}_{arm}_r{repetition}"
        summary, finish = read(directory / "summary.json"), read(directory / "finish.json")
        assert summary["attempted"] == 48
        assert summary["status"] in ("complete", "complete_with_errors")
        assert finish["cleanup_errors"] == [] and finish["resident_models"] == []
        summaries.append({"session": directory.name, "summary": summary,
                          "summary_sha256": sha256((directory / "summary.json").read_bytes()).hexdigest(),
                          "finish_sha256": sha256((directory / "finish.json").read_bytes()).hexdigest()})
    snapshot = capture_safety_snapshot()
    installed = _installed_models()
    metadata = {name: _model_metadata(name, installed) for name in frozen["models"]}
    version = _http_json("/api/version")
    source = source_hashes()
    swaps = Path("/proc/swaps").read_text()
    checks = {
        "batch_completed_without_terminal_failure": terminal["status"] == "complete" and terminal["failure"] is None,
        "nine_complete_sessions": len(summaries) == 9,
        "432_attempts": sum(item["summary"]["attempted"] for item in summaries) == 432,
        "frozen_source_unchanged": source == frozen["source_sha256"],
        "model_metadata_unchanged": metadata == frozen["models"],
        "ollama_version_unchanged": version == frozen["ollama_version"],
        "boot_unchanged": snapshot["boot_id"] == before["boot_id"],
        "power_mode_unchanged": snapshot["power_mode"] == before["power_mode"],
        "thermal_trip_counters_unchanged": snapshot["thermal_trip_events"] == before["thermal_trip_events"],
        "thermal_trip_counters_zero": bool(snapshot["thermal_trip_events"]) and
            all(value == 0 for value in snapshot["thermal_trip_events"].values()),
        "fan_running": isinstance(snapshot["fan_pwm"], int) and snapshot["fan_pwm"] > 0,
        "no_resident_models": snapshot["resident_models"] == [],
        "swap_capacity_unchanged": snapshot["memory"]["swap_total_kib"] ==
            frozen["device_policy"]["expected_swap_total_kib"],
        "swap_device_configuration_unchanged": swap_topology(swaps) ==
            swap_topology(preparation["proc_swaps"]),
        "original_experiment_swap_limits_preserved":
            original_guard.MAX_START_SWAP_USED_KIB == 768 * 1024 and
            original_guard.MAX_RUNTIME_SWAP_USED_KIB == 1024 * 1024,
        "revised_guard_has_no_persistent_changes": revised_guard.policy_dict()["persistent_system_changes"] is False,
    }
    record = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "audit_script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "freeze_sha256": sha256((HERE / "frozen_v2/freeze.json").read_bytes()).hexdigest(),
        "batch_finish_sha256": sha256((run / "batch_finish.json").read_bytes()).hexdigest(),
        "batch_finish": terminal, "checks": checks, "valid": all(checks.values()),
        "snapshot": snapshot, "source_sha256": source, "models": metadata,
        "ollama_version": version, "proc_swaps": swaps,
        "swap_topology": swap_topology(swaps), "sessions": summaries,
        "configuration_scope": "No OS swap, power, cooling, service or application settings were changed for v2. The revised ceilings were confined to separate experiment processes, which have exited.",
        "usage_scope": "Swap used and available RAM are live usage measurements and need not return to their starting values. Logical zram swap occupancy is not additional physical RAM and does not establish active swapping.",
    }
    os.umask(0o077)
    path = HERE / "final_state_v2.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({"valid": record["valid"], "checks": checks, "snapshot": snapshot,
                      "output": str(path)}))
    return 0 if record["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
