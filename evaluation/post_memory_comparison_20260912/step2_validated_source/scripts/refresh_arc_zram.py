"""Refresh only enough existing zram swap to pass the frozen ARC start gate.

This optional administrative preparation runs only after 03_cascade completes.
It never runs inference, stops applications, changes persistent configuration,
or disables more than one swap device at once. Each disabled device is restored
immediately, before any further recovery step. Privileged commands are limited
to sudo -n swapoff on one allowlisted device and sudo -n swapon -p 5 on it.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

from oline_hri.evaluation_model_pairs import (
    SafetyGateError, _DurableJsonlWriter, _fsync_directory,
    _require_start_safe, _write_new_json, capture_safety_snapshot,
)


DEVICES = tuple(f"/dev/zram{index}" for index in range(6))
DEVICE_SIZE_KIB = 650_268
PRIORITY = 5
TARGET_SWAP_KIB = 131_072
MAX_INITIAL_SWAP_KIB = 524_288
MIN_AVAILABLE_KIB = 2_621_440
RESERVE_KIB = 131_072
COMMAND_TIMEOUT_SECONDS = 30


def parse_swaps(raw):
    """Parse /proc/swaps without accepting unexpected devices or duplicates."""
    lines = raw.splitlines()
    if not lines or lines[0].split() != [
        "Filename", "Type", "Size", "Used", "Priority"
    ]:
        raise SafetyGateError("unexpected /proc/swaps header")
    swaps = {}
    for line in lines[1:]:
        fields = line.split()
        if len(fields) != 5:
            raise SafetyGateError("malformed /proc/swaps row")
        device, kind, size, used, priority = fields
        if device not in DEVICES or device in swaps or kind != "partition":
            raise SafetyGateError("unexpected or duplicate swap device")
        try:
            size, used, priority = int(size), int(used), int(priority)
        except ValueError:
            raise SafetyGateError("invalid swap counters") from None
        if size != DEVICE_SIZE_KIB or priority != PRIORITY or not 0 <= used <= size:
            raise SafetyGateError("swap configuration changed")
        swaps[device] = {"size_kib": size, "used_kib": used, "priority": priority}
    return swaps


def read_swaps():
    return parse_swaps(Path("/proc/swaps").read_text(encoding="ascii"))


def require_devices(swaps, *, possibly_missing=None):
    expected = set(DEVICES)
    actual = set(swaps)
    allowed = [expected]
    if possibly_missing is not None:
        if possibly_missing not in expected:
            raise SafetyGateError("invalid restoration device")
        allowed.append(expected - {possibly_missing})
    if actual not in allowed:
        raise SafetyGateError("the six original swap devices are not intact")


def require_environment(snapshot, boot_id):
    """Preserve all start checks except the explicitly targeted swap usage."""
    if snapshot.get("boot_id") != boot_id:
        raise SafetyGateError("boot changed since the completed cascade")
    if snapshot.get("resident_models") != []:
        raise SafetyGateError("an Ollama model is resident")
    memory = snapshot.get("memory", {})
    available = memory.get("mem_available_kib")
    used = memory.get("swap_used_kib")
    if type(available) is not int or available < MIN_AVAILABLE_KIB + RESERVE_KIB:
        raise SafetyGateError("insufficient RAM for guarded swap recovery")
    if type(used) is not int or not 0 <= used <= MAX_INITIAL_SWAP_KIB:
        raise SafetyGateError("swap use exceeds the recovery ceiling")
    temperatures = snapshot.get("temperatures_c")
    if not isinstance(temperatures, dict) or not temperatures:
        raise SafetyGateError("missing temperature sensors")
    if any(type(value) not in (int, float) or not math.isfinite(value)
           or value >= 55.0 for value in temperatures.values()):
        raise SafetyGateError("temperature must be below 55 C")
    fan = snapshot.get("fan_pwm")
    if type(fan) is not int or fan <= 0:
        raise SafetyGateError("fan is not running")
    trips = snapshot.get("thermal_trip_events")
    if not isinstance(trips, dict) or not trips or any(
        type(value) is not int or value != 0 for value in trips.values()
    ):
        raise SafetyGateError("thermal trip check failed")
    power = snapshot.get("power_mode")
    if not isinstance(power, str) or not re.search(
        r"NV Power Mode:\s*15W\s*\n0\s*\Z", power
    ):
        raise SafetyGateError("expected 15W power mode 0")


def require_device_headroom(snapshot, swaps, device):
    require_devices(swaps)
    if device not in DEVICES:
        raise SafetyGateError("invalid recovery device")
    projected = snapshot["memory"]["mem_available_kib"] - swaps[device]["used_kib"]
    if projected < MIN_AVAILABLE_KIB + RESERVE_KIB:
        raise SafetyGateError("target swap pages would consume the RAM reserve")


def require_private_directory(path):
    if path.resolve(strict=True) != path:
        raise SafetyGateError("run directory must not contain symlinks")
    metadata = path.lstat()
    if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700):
        raise SafetyGateError("run directory must be owned and mode 0700")


def read_cascade_finish(root):
    directory = root / "03_cascade"
    require_private_directory(directory)
    path = directory / "finish.json"
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
                or metadata.st_size > 1024 * 1024):
            raise SafetyGateError("cascade finish artifact is not trustworthy")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(1024 * 1024 + 1)
        value = json.loads(raw)
    finally:
        os.close(descriptor)
    if not isinstance(value, dict) or value.get("status") != "complete":
        raise SafetyGateError("03_cascade has not completed successfully")
    planned = value.get("planned_cases")
    if (type(planned) is not int or planned <= 0
            or value.get("completed_cases") != planned
            or value.get("resident_models") != []
            or value.get("cleanup_errors") != []
            or value.get("guard_violation") is not None
            or value.get("telemetry_reader_error") is not None):
        raise SafetyGateError("cascade completion checks failed")
    boot = value.get("boot_id")
    if not isinstance(boot, str) or not re.fullmatch(r"[0-9a-f-]{36}", boot):
        raise SafetyGateError("cascade boot ID is invalid")
    return value, sha256(raw).hexdigest()


def command_argv(action, device):
    """No arbitrary commands, device names, shell, or optional sudo flags."""
    if device not in DEVICES:
        raise SafetyGateError("command device is not allowlisted")
    if action == "swapoff":
        return ("/usr/bin/sudo", "-n", "/usr/sbin/swapoff", device)
    if action == "swapon":
        return ("/usr/bin/sudo", "-n", "/usr/sbin/swapon", "-p", "5", device)
    raise SafetyGateError("command action is not allowlisted")


def error_record(error):
    return {"type": type(error).__name__, "message": str(error)}


def refresh(root, journal):
    errors, refreshed = [], []
    result = {"status": "failed", "refreshed_devices": refreshed, "errors": errors}

    def event(kind, **fields):
        journal.write({"event": kind, "at": datetime.now(timezone.utc).isoformat(), **fields})

    def best_effort_event(kind, **fields):
        try:
            event(kind, **fields)
        except BaseException as error:
            errors.append({"phase": "journal", **error_record(error)})

    def command(action, device, *, restoring=False):
        argv = command_argv(action, device)
        # Recovery must restore swap even if the journal becomes unwritable.
        emit = best_effort_event if restoring else event
        emit("command_start", argv=list(argv))
        try:
            completed = subprocess.run(
                argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=COMMAND_TIMEOUT_SECONDS,
                check=False, text=True,
            )
        except BaseException as error:
            best_effort_event("command_exception", argv=list(argv), **error_record(error))
            raise
        emit("command_finish", argv=list(argv), returncode=completed.returncode,
             stdout=completed.stdout[:4096], stderr=completed.stderr[:4096])
        if completed.returncode:
            raise SafetyGateError(f"{action} failed with exit {completed.returncode}")

    try:
        source = Path(__file__).resolve()
        event("begin", source_sha256=sha256(source.read_bytes()).hexdigest(),
              target_swap_kib=TARGET_SWAP_KIB,
              minimum_available_kib=MIN_AVAILABLE_KIB, reserve_kib=RESERVE_KIB)
        finish, finish_hash = read_cascade_finish(root)
        boot_id = finish["boot_id"]
        event("cascade_verified", cascade_finish_sha256=finish_hash, boot_id=boot_id)
        initial = capture_safety_snapshot()
        swaps = read_swaps()
        event("initial_snapshot", snapshot=initial, swaps=swaps)
        require_environment(initial, boot_id)
        require_devices(swaps)
        for device in DEVICES:
            snapshot = capture_safety_snapshot()
            swaps = read_swaps()
            require_environment(snapshot, boot_id)
            require_devices(swaps)
            if (snapshot["memory"]["swap_used_kib"] <= TARGET_SWAP_KIB
                    and sum(item["used_kib"] for item in swaps.values()) <= TARGET_SWAP_KIB):
                break
            if swaps[device]["used_kib"] == 0:
                continue
            require_device_headroom(snapshot, swaps, device)
            event("device_before", device=device, snapshot=snapshot, swaps=swaps)
            original_error = None
            try:
                command("swapoff", device)
            except BaseException as error:
                original_error = error
            finally:
                # Always determine whether restoration is needed, even after
                # timeout/interruption. If procfs is unreadable, attempt the
                # known-device restoration rather than assuming it is active.
                needs_restore = True
                try:
                    active = read_swaps()
                    needs_restore = device not in active
                    require_devices(active, possibly_missing=device)
                except BaseException as error:
                    errors.append({"phase": "before_restore", "device": device,
                                   **error_record(error)})
                if needs_restore:
                    try:
                        command("swapon", device, restoring=True)
                    except BaseException as error:
                        errors.append({"phase": "restore", "device": device,
                                       **error_record(error)})
                try:
                    active = read_swaps()
                    require_devices(active)
                    best_effort_event("device_restored", device=device, swaps=active)
                except BaseException as error:
                    errors.append({"phase": "verify_restore", "device": device,
                                   **error_record(error)})
            if original_error is not None:
                raise original_error
            if errors:
                raise SafetyGateError("restoration or recovery journal failed")
            refreshed.append(device)
        final = capture_safety_snapshot()
        swaps = read_swaps()
        result["final_snapshot"] = final
        result["final_swaps"] = swaps
        require_devices(swaps)
        require_environment(final, boot_id)
        _require_start_safe(final)  # The original evaluation gate is unchanged.
        if sum(item["used_kib"] for item in swaps.values()) > TARGET_SWAP_KIB:
            raise SafetyGateError("swap recovery did not reach the target")
        result["status"] = "complete"
    except BaseException as error:
        errors.append({"phase": "recovery", **error_record(error)})
    finally:
        best_effort_event("result", result=result)
        if errors:
            result["status"] = "failed"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--check-only", action="store_true",
                        help="check eligibility without writes or privileged commands")
    args = parser.parse_args(argv)
    root = args.run_root.absolute()
    os.umask(0o077)
    result = None
    try:
        require_private_directory(root)
        if args.check_only:
            finish, _ = read_cascade_finish(root)
            snapshot, swaps = capture_safety_snapshot(), read_swaps()
            require_environment(snapshot, finish["boot_id"])
            require_devices(swaps)
            used = max(snapshot["memory"]["swap_used_kib"],
                       sum(item["used_kib"] for item in swaps.values()))
            if used <= TARGET_SWAP_KIB:
                _require_start_safe(snapshot)
                status = "already_ready"
            else:
                device = next(device for device in DEVICES if swaps[device]["used_kib"])
                require_device_headroom(snapshot, swaps, device)
                status = "recovery_possible"
            print(json.dumps({"status": status, "check_only": True,
                              "snapshot": snapshot, "swaps": swaps}))
            return 0
        if (root / "recovery_result.json").exists():
            raise SafetyGateError("recovery_result.json already exists")
        with _DurableJsonlWriter(root / "recovery.jsonl") as journal:
            result = refresh(root, journal)
        _write_new_json(root / "recovery_result.json", result)
        _fsync_directory(root)
    except BaseException as error:
        if result is not None:
            result["status"] = "failed"
            result["errors"].append({"phase": "artifact_finish", **error_record(error)})
            try:
                _write_new_json(root / "recovery_result.json", result)
                _fsync_directory(root)
            except BaseException:
                pass
        print(json.dumps({"status": "failed", "error": error_record(error)}), file=sys.stderr)
        return 1
    print(json.dumps({"status": result["status"], "refreshed_devices": result["refreshed_devices"]}))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
