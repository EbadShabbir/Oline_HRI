"""Audit saved swap-cycle evidence only; perform no live or administrator action."""
import ast
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def identity(rows):
    return sorted((row["name"], row["kind"], row["size_kib"], row["priority"]) for row in rows)


checks = []
def check(name, condition, detail=None):
    checks.append({"check": name, "passed": bool(condition), "detail": detail})


status = read(HERE / "status.json")
events = [json.loads(line) for line in (HERE / "swap_reset.jsonl").read_text().splitlines()]
start, end = events[0], events[-1]
helper = ROOT / status["helper"]
prior_manifest = ROOT / "evaluation/answer_repair_20260916/completion_manifest.json"
prior = read(prior_manifest)
mock_path = ROOT / "evaluation/answer_repair_20260916/fresh_recovery_v1/swap_reset_offline_checks.json"
check("saved invocation reports successful bounded authorized helper", status["exit_code"] == 0
      and status["helper"] == "evaluation/answer_repair_20260916/reset_swap_once.py"
      and "Prior user authorization" in status["authorization"])
check("helper matches prior frozen completion-manifest bytes", digest(helper) == prior["artifact_sha256"][status["helper"]])
check("prior restoration tests remain sealed", digest(mock_path) == prior["artifact_sha256"][str(mock_path.relative_to(ROOT))])
mock = read(mock_path)
check("sealed mocked success failure interruption and headroom cases preserve restoration",
      {row["case"] for row in mock["checks"]} == {"success", "failure_after_disable", "interrupt_after_disable", "insufficient_headroom"}
      and all(row["passed"] and row["restoration_preserved"] for row in mock["checks"]))
tree = ast.parse(helper.read_text())
cycle = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "cycle")
restoring_finally = [node for node in ast.walk(cycle) if isinstance(node, ast.Try) and node.finalbody
                    and any(isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "restore"
                            for statement in node.finalbody for call in ast.walk(statement))]
check("cycle source has both per-device and outer finally restoration", len(restoring_finally) == 2)
check("stderr is empty", not (HERE / "swap_reset.stderr").read_text().strip())
check("start and completion are recorded in timestamp order", start["event"] == "start" and end["event"] == "complete"
      and all(datetime.fromisoformat(left["at"]) <= datetime.fromisoformat(right["at"])
              for left, right in zip(events, events[1:])))
check("models were absent before swap cycling", start["resident_models"] == [])
devices = start["swaps"]
total = sum(row["size_kib"] for row in devices)
initial_used = sum(row["used_kib"] for row in devices)
check("exact six existing zram devices only", [row["name"] for row in devices] == [f"/dev/zram{i}" for i in range(6)]
      and all(row["kind"] == "partition" for row in devices))
check("original sizes and priorities are unchanged", identity(devices) == identity(end["swaps"])
      and all(row["size_kib"] == 650264 and row["priority"] == 5 for row in devices))
check("total swap capacity is unchanged", total == start["memory"]["SwapTotal"] == end["memory"]["SwapTotal"] == 3901584)
check("initial drain has a 1 GiB RAM reserve", start["memory"]["MemAvailable"] >= initial_used + 1048576)
for index, device in enumerate(devices):
    own = events[1 + 4 * index:5 + 4 * index]
    check(device["name"] + " sequential cycle order", [row["event"] for row in own] == ["before_swapoff", "disabled", "restore", "cycled"]
          and all(row["device"] == device["name"] for row in own))
    check(device["name"] + " successful restoration with unchanged inventory", own[2]["returncode"] == 0
          and own[2]["stderr"] == "" and identity(own[3]["swaps"]) == identity(devices))
    check(device["name"] + " only its capacity removed temporarily", own[1]["memory"]["SwapTotal"] == total - device["size_kib"]
          and own[3]["memory"]["SwapTotal"] == total)
    check(device["name"] + " recorded drain reserve", own[0]["memory"]["MemAvailable"] >= device["used_kib"] + 1048576)
check("all six devices restored and empty at completion", len(events) == 26
      and all(row["used_kib"] == 0 for row in end["swaps"]) and end["memory"]["SwapFree"] == total)
check("no cleanup error or persistent configuration change recorded", not any(row["event"] == "error" for row in events)
      and end["persistent_settings_changed"] is False)
inputs = [HERE / "status.json", HERE / "swap_reset.jsonl", HERE / "swap_reset.stderr", helper,
          prior_manifest, mock_path, Path(__file__)]
result = {"created_at": datetime.now(timezone.utc).isoformat(),
          "scope": "Saved artifacts and literal source AST only; no live device, /proc, model, network, process or administrator operations.",
          "authorization_limit": "Prior user and normal administrator authorization are described by the saved operator status; this audit does not query authentication logs.",
          "checks": checks, "checks_passed": sum(row["passed"] for row in checks),
          "checks_failed": sum(not row["passed"] for row in checks), "passed": all(row["passed"] for row in checks),
          "device_count": len(devices), "initial_swap_used_kib": initial_used,
          "final_swap_used_kib": sum(row["used_kib"] for row in end["swaps"]), "swap_total_kib": total,
          "post_cleanup_mem_available_kib": end["memory"]["MemAvailable"],
          "post_cleanup_meets_2gib_ram_start_gate": end["memory"]["MemAvailable"] >= 2097152,
          "readiness_interpretation": "Successful restoration does not establish inference readiness. The captured post-cleanup available RAM must independently meet the unchanged 2 GiB start gate before a new run; other gates are not captured by this swap log.",
          "artifact_sha256": {str(path.relative_to(ROOT)): digest(path) for path in inputs}}
with (HERE / "independent_cleanup_audit.json").open("x") as stream:
    json.dump(result, stream, indent=2)
    stream.write("\n")
print(json.dumps({key: result[key] for key in ("passed", "checks_passed", "checks_failed", "post_cleanup_meets_2gib_ram_start_gate")}, indent=2))
raise SystemExit(0 if result["passed"] else 1)
