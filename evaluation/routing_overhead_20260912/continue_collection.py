"""Continue whole sequence slots after the documented v1 validation-handler stop.

No answered request is retried. Prior files remain immutable and are referenced
through file symlinks in real session directories. The only v1 eligibility
exception is the recorded four-turn temporal-validation failure at slot 22.
"""
import argparse
import difflib
from hashlib import sha256
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
from time import monotonic, sleep

from oline_hri.evaluation_model_pairs import SafetyGateError, _DurableJsonlWriter, _new_private_directory, _write_new_json
from post_memory_device_guard import capture_safety_snapshot, require_ready, stage2_limits
import run_routing_overhead as runner

SPECIAL = "ro_dddd_3_r1_large"


def read(path):
    return json.loads(path.read_text())


def validate_reuse(directory, frozen, freeze_path):
    manifest, finish = read(directory/"manifest.json"), read(directory/"finish.json")
    observations = [json.loads(line) for line in (directory/"observations.jsonl").read_text().splitlines()]
    expected = [f"{manifest['sequence_id']}_t{i}" for i in range(1, 5)]
    if ([r["id"] for r in observations] != expected or [r["index"] for r in observations] != [1,2,3,4]
            or manifest["freeze_sha256"] != sha256(freeze_path.read_bytes()).hexdigest()
            or finish["attempted"] != 4 or finish["guard_violation"] is not None
            or finish["cleanup_errors"] or finish["resident_models"] or not finish["source_unchanged"]):
        raise ValueError("previous sequence is not a verified whole attempt")
    special = directory.name == SPECIAL and finish["status"] == "interrupted"
    if special:
        failure = finish["failure"]
        if (failure != {"type": "ResponseValidationError", "message": "robot response omits requested temporal memory detail"}
                or [r["status"] for r in observations] != ["ok", "ok", "ok", "interrupted"]
                or observations[-1]["error"] != "ResponseValidationError"
                or any(c["status"] != "ok" for r in observations for c in r["calls"])
                or any(r.get("post_guard_error") or r.get("post_snapshot_error") for r in observations)):
            raise ValueError("v1 final-turn validation exception differs from the audited case")
    elif finish["status"] not in {"complete", "complete_with_errors"}:
        raise ValueError("cannot splice or silently retry an interrupted sequence")
    from analyze_routing_overhead import account_spans, audit_calls
    for row in observations:
        account_spans(row); audit_calls(row)
    if finish["request_total_ns"] != sum(r["wall_ns"] for r in observations):
        raise ValueError("old request accounting differs")
    if finish["sequence_total_ns"] != finish["startup_ns"]+finish["request_total_ns"]+finish["sequence_gaps_ns"]:
        raise ValueError("old sequence accounting differs")
    return {"directory": directory.name, "original_status": finish["status"],
            "analysis_eligibility": "four_turns_observed_with_error" if special else "complete",
            "attempts_retained": 4, "source": str(directory.resolve()),
            "file_sha256": {p.name: sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file()},
            "raw_files_or_statuses_modified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", required=True, type=Path)
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--previous-root", required=True, type=Path)
    parser.add_argument("--previous-freeze", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    workload, frozen = runner.check_freeze(args)
    previous = read(args.previous_freeze)
    for field in ("profile_id", "workload_sha256", "models", "ollama_version", "config", "generation",
                  "generation_seed", "embedding_asset_sha256", "packages", "python", "device_policy", "arm_orders"):
        if previous[field] != frozen[field]:
            raise ValueError(f"execution control changed across continuation: {field}")
    for relative, expected in previous["source_sha256"].items():
        if sha256((args.previous_freeze.parent/"source"/relative).read_bytes()).hexdigest() != expected:
            raise ValueError("old source archive differs")
    changed = [p for p in previous["source_sha256"] if previous["source_sha256"][p] != frozen["source_sha256"].get(p)]
    if set(changed) != {"scripts/run_routing_overhead.py", "tests/test_routing_overhead_runner.py"}:
        raise ValueError(f"unexpected previously existing source changes: {changed}")
    directory = _new_private_directory(args.output_dir.absolute())
    prior_slots, reuse = {}, []
    for seq, rep, arm in runner.slots(workload):
        name = f"{seq}_r{rep}_{arm}"
        old = args.previous_root/name
        if not old.exists():
            continue
        proof = validate_reuse(old, previous, args.previous_freeze)
        destination = directory/name
        destination.mkdir(mode=0o700)
        for source in old.iterdir():
            if source.is_file():
                (destination/source.name).symlink_to(source.resolve())
        prior_slots[name] = proof
        reuse.append(proof)
    if len(reuse) != 22 or sum(p["attempts_retained"] for p in reuse) != 88:
        raise ValueError("this continuation requires exactly the preserved first 22 whole sequences")
    first_slots = {f"{seq}_r{rep}_{arm}" for seq, rep, arm in list(runner.slots(workload))[:22]}
    if set(prior_slots) != first_slots or {p.parent.name for p in args.previous_root.glob("*/manifest.json")} != first_slots:
        raise ValueError("reused attempts must be exactly the first 22 scheduled slots")
    old_source = (args.previous_freeze.parent/"source/scripts/run_routing_overhead.py").read_text()
    new_source = (runner.ROOT/"scripts/run_routing_overhead.py").read_text()
    (directory/"runner_source_delta.diff").write_text("".join(difflib.unified_diff(
        old_source.splitlines(True), new_source.splitlines(True), fromfile="frozen_v1", tofile="frozen_v2")))
    _write_new_json(directory/"reuse_manifest.json", {"previous_root": str(args.previous_root.resolve()),
        "previous_freeze": str(args.previous_freeze.resolve()), "previous_freeze_sha256": sha256(args.previous_freeze.read_bytes()).hexdigest(),
        "new_freeze_sha256": sha256(args.freeze.read_bytes()).hexdigest(), "reused_sequences": reuse,
        "changed_existing_source": changed, "added_source": sorted(set(frozen["source_sha256"])-set(previous["source_sha256"])),
        "reason": "ordinary ResponseValidationError inherited ValueError and was incorrectly treated as fatal; current handling continues ordinary answer failures",
        "no_answered_request_retried": True, "no_tail_splicing": True})
    planned = list(runner.slots(workload))
    _write_new_json(directory/"batch_plan.json", {"created_at": runner.utc(), "slots": planned,
        "main_attempts": 432, "diagnostic_attempts": 144, "reused_attempts": 88, "new_attempts": 488,
        "cold_wait_seconds": 600, "scheduler_temperature_target_c": 54.0,
        "freeze_sha256": sha256(args.freeze.read_bytes()).hexdigest()})
    completed, status, failure = [], "incomplete", None
    try:
        with runner.exclusive_inference() as lease, _DurableJsonlWriter(directory/"scheduler.jsonl") as scheduler:
            baseline = capture_safety_snapshot()
            _write_new_json(directory/"before.json", baseline)
            previous_state = read(args.previous_root/"batch_finish.json")["snapshot"]
            if any(baseline[k] != previous_state[k] for k in ("boot_id", "thermal_trip_events", "power_mode")):
                raise SafetyGateError("host invariants changed across the collection pause")
            for seq, rep, arm in planned:
                name = f"{seq}_r{rep}_{arm}"
                if name in prior_slots:
                    completed.append({"slot": name, "reused": True, "original_status": prior_slots[name]["original_status"]})
                    continue
                deadline = monotonic()+600
                while True:
                    state, audit = capture_safety_snapshot(), runner.process_audit()
                    scheduler.write({"kind": "preflight", "slot": name, "snapshot": state, "audit": audit})
                    if audit["conflicts"]:
                        raise SafetyGateError("competing experiment detected")
                    if any(state[k] != baseline[k] for k in ("boot_id", "thermal_trip_events", "power_mode")):
                        raise SafetyGateError("host invariants changed")
                    try:
                        with stage2_limits(): require_ready(state)
                        if max(state["temperatures_c"].values()) >= 54:
                            raise SafetyGateError("scheduler cooling target below 54 C")
                        break
                    except SafetyGateError as error:
                        scheduler.write({"kind": "wait", "slot": name, "reason": str(error), "at": runner.utc()})
                        if state["resident_models"] or monotonic() >= deadline:
                            raise
                        print(f"COOLING {name}: {error}", flush=True)
                        sleep(10)
                command = [sys.executable, str(runner.ROOT/"scripts/run_routing_overhead.py"), "session",
                           "--workload", str(args.workload.resolve()), "--freeze", str(args.freeze.resolve()),
                           "--output-dir", str(directory/name), "--sequence", seq, "--repetition", str(rep),
                           "--arm", arm, "--lock-fd", str(lease)]
                if arm == "replay": command += ["--replay", str(directory/f"{seq}_r{rep}_adaptive"/"observations.jsonl")]
                scheduler.write({"kind": "launch", "slot": name, "command": command, "at": runner.utc()})
                print(f"SESSION {len(completed)+1}/{len(planned)} {name}", flush=True)
                result = subprocess.run(command, check=False, pass_fds=(lease,))
                completed.append({"slot": name, "reused": False, "exit_code": result.returncode})
                if result.returncode:
                    raise RuntimeError(f"{name} stopped; preserved without tail stitching")
            runner.check_freeze(args)
            status = "complete"
    except BaseException as error:
        status, failure = "interrupted", {"type": type(error).__name__, "message": str(error)}
    finally:
        try:
            final = capture_safety_snapshot()
        except BaseException as error:
            final = {"error": type(error).__name__, "message": str(error)}
            status = "final_snapshot_failed"
        try:
            configuration = runner.server_configuration()
        except BaseException as error:
            configuration = {"error": type(error).__name__, "message": str(error)}
            status = "final_configuration_failed"
        _write_new_json(directory/"batch_finish.json", {"status": status, "failure": failure,
            "completed": completed, "planned": len(planned), "snapshot": final,
            "source_unchanged": runner.source_hashes() == frozen["source_sha256"],
            "server_configuration": configuration, "reused_attempts": 88})
    return 0 if status == "complete" else 1


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt("SIGTERM")))
    raise SystemExit(main())
