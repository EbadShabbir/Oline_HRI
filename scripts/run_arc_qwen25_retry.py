"""Explicit, one-process startup amendment for the frozen Qwen2.5 3B ARC arm.

The original runner and production files stay unchanged. This launcher changes
only the extra arm's startup swap allowance from 128 to 384 MiB, while requiring
2.5 GiB available RAM and preserving the original runtime checks and cleanup.
It never changes system settings. The exact launcher and written protocol
amendment are archived before inference, and both temporary bindings are restored.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from hashlib import sha256
import math
import os
from pathlib import Path
import re

import run_arc_capability as arc


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation" / "arc_capability_20260911" / "dataset.json"
PROTOCOL_AMENDMENT = ROOT / "evaluation" / "arc_capability_20260911" / "extra_startup_amendment.md"
EXTRA_MODEL = "qwen2.5:3b-instruct-q3_K_S"
DATASET_SHA256 = "c0e858c862381a6ddf04de56f53d3d12113ac01920aa6a5f7fe30c297f80c4a5"
RUNNER_SHA256 = "2d55342123aa853952a44b6496285b338b322ec65f32f83bbf106e5c606885a0"
MIN_START_RAM_KIB = 2621440
MAX_START_SWAP_KIB = 393216


def _nonnegative_integer(value):
    return type(value) is int and value >= 0


def require_retry_start_safe(snapshot):
    """Validate the real snapshot without modifying any measured counters."""
    memory = snapshot.get("memory")
    temperatures = snapshot.get("temperatures_c")
    trips = snapshot.get("thermal_trip_events")
    if not isinstance(memory, dict):
        raise arc.SafetyGateError("retry memory snapshot is incomplete")
    available = memory.get("mem_available_kib")
    swap = memory.get("swap_used_kib")
    if not _nonnegative_integer(available) or available < MIN_START_RAM_KIB:
        raise arc.SafetyGateError("available memory is below the unchanged 2.5 GiB start gate")
    if not _nonnegative_integer(swap) or swap > MAX_START_SWAP_KIB:
        raise arc.SafetyGateError("swap use exceeds the explicit 384 MiB retry start gate")
    if not isinstance(temperatures, dict) or not temperatures:
        raise arc.SafetyGateError("retry temperature snapshot is incomplete")
    if any(type(value) not in (int, float) or not math.isfinite(value) or value >= 55
           for value in temperatures.values()):
        raise arc.SafetyGateError("retry requires all temperatures below 55 C")
    if snapshot.get("resident_models") != []:
        raise arc.SafetyGateError("retry requires no resident Ollama models")
    fan = snapshot.get("fan_pwm")
    if not _nonnegative_integer(fan) or fan <= 0:
        raise arc.SafetyGateError("retry requires a running fan")
    if (not isinstance(trips, dict) or not trips
            or any(type(value) is not int or value != 0 for value in trips.values())):
        raise arc.SafetyGateError("retry requires measured zero thermal trip counters")
    power_mode = snapshot.get("power_mode")
    if not isinstance(power_mode, str) or not re.search(
        r"NV Power Mode:\s*15W\s*\n0\s*\Z", power_mode
    ):
        raise arc.SafetyGateError("retry requires exact 15W power mode 0")


def execution_amendment(launcher_bytes, protocol_bytes):
    return {
        "schema_version": 1, "arm": "extra", "model": EXTRA_MODEL,
        "scope": "extra_startup_only",
        "launcher_path": "scripts/run_arc_qwen25_retry.py",
        "launcher_sha256": sha256(launcher_bytes).hexdigest(),
        "launcher_archive": "execution_launcher.py",
        "original_runner_sha256": RUNNER_SHA256,
        "dataset_sha256": DATASET_SHA256,
        "protocol_amendment_path": str(PROTOCOL_AMENDMENT.relative_to(ROOT)),
        "protocol_amendment_sha256": sha256(protocol_bytes).hexdigest(),
        "protocol_amendment_archive": "execution_amendment.md",
        "original_start_swap_ceiling_kib": 131072,
        "start_limits": {
            "min_available_ram_kib": MIN_START_RAM_KIB,
            "max_swap_used_kib": MAX_START_SWAP_KIB,
            "max_temperature_c_exclusive": 55, "fan_running": True,
            "thermal_trip_events_zero": True, "power_mode": "15W mode 0",
            "resident_model_count": 0,
        },
        "runtime_limits": {
            "min_available_ram_kib": 786432, "max_swap_used_kib": 524288,
            "max_temperature_c_exclusive": 68,
        },
        "runtime_guards_unchanged": True, "system_settings_changed": False,
        "rationale": (
            "The original extra-model start was blocked by the conservative 128 MiB "
            "swap gate. The user requested continuation after that distinction was "
            "explained. This explicit single-run amendment uses the previously "
            "used pair-workload 384 MiB startup allowance, retains the stricter "
            "2.5 GiB RAM requirement, and leaves swap enabled. Runtime limits, "
            "model artifact admission, inference, scoring, and cleanup are unchanged."
        ),
    }


def _archive_new(path, content):
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def retry_bindings(amendment, launcher_bytes, protocol_bytes):
    """Patch only this imported runner's gate and artifact writer, then restore."""
    original_gate, original_writer = arc._require_start_safe, arc._write_new_json
    archived = False

    def write_artifact(path, value):
        nonlocal archived
        if path.name == "manifest.json":
            if not archived:
                raise ValueError("retry provenance must be archived before the manifest")
            if value.get("arm") != "extra" or set(value.get("models", {})) != {EXTRA_MODEL}:
                raise ValueError("retry amendment is restricted to the exact extra model")
            value = {**value, "execution_amendment": amendment}
        original_writer(path, value)
        if path.name == "start.json":
            # The start snapshot is written unchanged. Extra files carry the
            # amendment; neither telemetry nor measured counters are rewritten.
            _archive_new(path.parent / amendment["launcher_archive"], launcher_bytes)
            _archive_new(path.parent / amendment["protocol_amendment_archive"], protocol_bytes)
            original_writer(path.parent / "execution_amendment.json", amendment)
            archived = True

    arc._require_start_safe = require_retry_start_safe
    arc._write_new_json = write_artifact
    try:
        yield
    finally:
        arc._require_start_safe = original_gate
        arc._write_new_json = original_writer


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    if sha256(Path(arc.__file__).read_bytes()).hexdigest() != RUNNER_SHA256:
        raise ValueError("the original ARC runner differs from the frozen source")
    if sha256(DATASET.read_bytes()).hexdigest() != DATASET_SHA256:
        raise ValueError("the retry dataset differs from the frozen 100-case dataset")
    launcher_bytes = Path(__file__).read_bytes()
    protocol_bytes = PROTOCOL_AMENDMENT.read_bytes()
    amendment = execution_amendment(launcher_bytes, protocol_bytes)
    with retry_bindings(amendment, launcher_bytes, protocol_bytes):
        return arc.main([
            "--dataset", str(DATASET), "--output-dir", str(args.output_dir),
            "--arm", "extra", "--extra-model", EXTRA_MODEL,
        ])


if __name__ == "__main__":
    raise SystemExit(main())
