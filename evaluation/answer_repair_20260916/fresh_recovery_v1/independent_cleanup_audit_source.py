"""Offline audit of saved cleanup and prior-manifest preservation evidence."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = BASE.parents[1]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(rows):
    return sorted((row["name"], row["kind"], row["size_kib"], row["priority"]) for row in rows)


checks = []


def check(name, passed, detail=None):
    checks.append({"check": name, "passed": bool(passed), "detail": detail})


pre = read(HERE / "cleanup_preflight.json")
apps = read(HERE / "approved_app_cleanup.json")
scope = read(HERE / "cleanup_authorization_and_scope.json")
ready = read(HERE / "post_cleanup_readiness.json")
events = [json.loads(line) for line in (HERE / "swap_reset.log").read_text().splitlines()]
start, finish = events[0], events[-1]
check("saved authorization records identify approved bounded cleanup", scope["user_authorization"] == "yeah do it" and "approving" in apps["authorization"])
check("cleanup script bytes match recorded invocation source", sha(BASE / "reset_swap_once.py") == scope["cleanup_script_sha256"])
check("no active package transaction in saved preflight", pre["package_transactions"]["returncode"] == 0 and pre["package_transactions"]["stdout"].strip() == apps["package_transactions"] == "ao 0")
check("only approved app actions recorded", [action["action"] for action in apps["actions"]] == ["gnome-software --quit", "SIGTERM idle update-manager"])
check("software quit succeeded and targeted processes absent", apps["actions"][0]["returncode"] == 0 and apps["remaining_target_pids"] == [])
check("updater PID matches preflight identity", any(proc["Name"] == "update-manager" and int(proc["Pid"]) == apps["actions"][1]["pid"] for proc in pre["relevant_processes"]))
check("models absent before and after app cleanup and at swap start", pre["snapshot"]["resident_models"] == apps["before"]["resident_models"] == apps["after"]["resident_models"] == start["resident_models"] == [])
check("complete monotonic cleanup event sequence", start["event"] == "start" and finish["event"] == "complete" and all(datetime.fromisoformat(a["at"]) <= datetime.fromisoformat(b["at"]) for a, b in zip(events, events[1:])))
devices = start["swaps"]
check("exact six existing zram device identities", [row["name"] for row in devices] == [f"/dev/zram{i}" for i in range(6)] and all(row["kind"] == "partition" for row in devices))
check("all six original sizes and priorities retained", identity(devices) == identity(finish["swaps"]) and all(row["size_kib"] == 650264 and row["priority"] == 5 for row in devices))
total = sum(row["size_kib"] for row in devices)
check("total swap capacity unchanged", total == start["memory"]["SwapTotal"] == finish["memory"]["SwapTotal"] == ready["snapshot"]["memory"]["swap_total_kib"] == 3901584)
initial_used = sum(row["used_kib"] for row in devices)
check("initial drain had at least 1GiB reserve", start["memory"]["MemAvailable"] >= initial_used + 1048576)
for index, device in enumerate(devices):
    own = events[1 + 4 * index:5 + 4 * index]
    check(device["name"] + " sequential disable and restoration", [row["event"] for row in own] == ["before_swapoff", "disabled", "restore", "cycled"] and all(row["device"] == device["name"] for row in own))
    check(device["name"] + " restored successfully with complete inventory", own[2]["returncode"] == 0 and own[2]["stderr"] == "" and identity(own[3]["swaps"]) == identity(devices))
    check(device["name"] + " only one device capacity removed temporarily", own[1]["memory"]["SwapTotal"] == total - device["size_kib"] and own[3]["memory"]["SwapTotal"] == total)
    check(device["name"] + " recorded drain headroom", own[0]["memory"]["MemAvailable"] >= device["used_kib"] + 1048576)
check("all devices restored and empty at completion", len(events) == 26 and all(row["used_kib"] == 0 for row in finish["swaps"]) and finish["memory"]["SwapFree"] == total)
check("no cleanup error event", not any(row["event"] == "error" for row in events))
check("no persistent-setting change recorded", finish["persistent_settings_changed"] is False)
s = ready["snapshot"]
check("post-cleanup readiness independently satisfies start gates", ready["ready"] is True and ready["cleanup_authorized_and_completed"] is True and s["memory"]["mem_available_kib"] >= 2097152 and s["memory"]["swap_used_kib"] <= 786432 and max(s["temperatures_c"].values()) < 55 and s["fan_pwm"] > 0 and s["resident_models"] == [])
check("saved boot power and thermal counters unchanged", all(snapshot["boot_id"] == s["boot_id"] and snapshot["power_mode"] == s["power_mode"] and snapshot["thermal_trip_events"] == s["thermal_trip_events"] for snapshot in [pre["snapshot"], apps["before"], apps["after"]]))
check("cleanup completed before readiness capture", datetime.fromisoformat(finish["at"]) < datetime.fromisoformat(s["captured_at"]))
snapshot = read(BASE / "pre_recovery_completion_snapshot/manifest.json")
manifest_path = BASE / "fresh_attempt_manifest.json"
manifest = read(manifest_path)
check("previous manifest bytes retained", sha(manifest_path) == snapshot["fresh_attempt_manifest_sha256"])
check("five exact prior document snapshots", len(snapshot["documents"]) == 5 and all(sha(ROOT / row["snapshot_path"]) == row["sha256"] for row in snapshot["documents"].values()))
mismatches, mapped = [], []
for name, expected in manifest["artifact_sha256"].items():
    path = ROOT / name
    if path.is_file() and sha(path) == expected:
        continue
    old = snapshot["documents"].get(name)
    if old and old["sha256"] == expected and sha(ROOT / old["snapshot_path"]) == expected:
        mapped.append(name)
    else:
        mismatches.append(name)
check("all 1354 previous manifest hashes preserved using explicit mappings", len(manifest["artifact_sha256"]) == manifest["artifact_count"] == 1354 and not mismatches, {"mapped_documents": mapped, "mismatches": mismatches})
inputs = [HERE / "cleanup_preflight.json", HERE / "approved_app_cleanup.json", HERE / "cleanup_authorization_and_scope.json", HERE / "swap_reset.log", HERE / "post_cleanup_readiness.json", BASE / "reset_swap_once.py", BASE / "pre_recovery_completion_snapshot/manifest.json", manifest_path, Path(__file__)]
result = {
    "created_at": datetime.now(timezone.utc).isoformat(),
    "scope": "Artifact-only audit of approved cleanup; no live /proc, device, model, network or configuration access by this auditor.",
    "authorization_evidence_limit": "User and normal pkexec authorization are documented in the operator's saved scope record; this audit does not independently query the OS authentication log.",
    "checks": checks,
    "checks_passed": sum(row["passed"] for row in checks),
    "checks_failed": sum(not row["passed"] for row in checks),
    "passed": all(row["passed"] for row in checks),
    "cleanup_device_count": len(devices),
    "original_swap_used_kib": initial_used,
    "final_swap_used_kib": sum(row["used_kib"] for row in finish["swaps"]),
    "swap_total_kib": total,
    "swap_device_size_kib": 650264,
    "swap_device_priority": 5,
    "post_cleanup_available_kib": s["memory"]["mem_available_kib"],
    "post_cleanup_max_temperature_c": max(s["temperatures_c"].values()),
    "artifact_sha256": {str(path.relative_to(ROOT)): sha(path) for path in inputs},
}
with (HERE / "independent_cleanup_audit.json").open("x", encoding="utf-8") as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
    stream.write("\n")
print(json.dumps({key: result[key] for key in ("passed", "checks_passed", "checks_failed")}, indent=2))
for row in checks:
    if not row["passed"]:
        print(json.dumps(row))
raise SystemExit(0 if result["passed"] else 1)
