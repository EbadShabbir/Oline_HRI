"""Process-scoped device limits for the three-arm Stage 2 comparison.

These are an explicit common Stage 2 policy, independent of the ARC 3B
continuation. No configuration file, service, swap device, or hardware setting
is modified. Keep the context active from before embedding setup until after
inference, sampler shutdown, model cleanup, and final device checks.

The established GuardedSampler, GuardedBackend, and _StreamingSafetyMonitor
read their runtime limits from evaluation_model_pairs globals. Replacing only
those constants preserves their existing abort and telemetry behavior, then
restores every original value when the context exits, including on failure.
Use separate processes for the three arms; this context is not intended for
concurrent evaluations within one Python process.
"""

from __future__ import annotations

from contextlib import contextmanager
import math
from types import MappingProxyType

from oline_hri import evaluation_model_pairs as pair


POLICY_ID = "complete_system_stage2_common_device_limits_v1"
MIN_START_AVAILABLE_KIB = 2 * 1024 * 1024
MAX_START_SWAP_USED_KIB = 768 * 1024
MAX_START_TEMPERATURE_C = 55.0
MIN_RUNTIME_AVAILABLE_KIB = 768 * 1024
MAX_RUNTIME_SWAP_USED_KIB = 1024 * 1024
MAX_RUNTIME_TEMPERATURE_C = 68.0

_OVERRIDES = MappingProxyType({
    "MIN_START_AVAILABLE_KIB": MIN_START_AVAILABLE_KIB,
    "MAX_START_SWAP_USED_KIB": MAX_START_SWAP_USED_KIB,
    "MAX_START_TEMPERATURE_C": MAX_START_TEMPERATURE_C,
    "MIN_RUNTIME_AVAILABLE_KIB": MIN_RUNTIME_AVAILABLE_KIB,
    "MAX_RUNTIME_SWAP_USED_KIB": MAX_RUNTIME_SWAP_USED_KIB,
    "MAX_RUNTIME_TEMPERATURE_C": MAX_RUNTIME_TEMPERATURE_C,
})


def policy_dict():
    """Return fresh JSON-compatible manifest fields for the common policy."""
    return {
        "policy_id": POLICY_ID,
        "scope": "all three Stage 2 arms; embeddings through final cleanup",
        "min_start_available_kib": MIN_START_AVAILABLE_KIB,
        "max_start_swap_used_kib": MAX_START_SWAP_USED_KIB,
        "max_start_temperature_c_exclusive": MAX_START_TEMPERATURE_C,
        "min_runtime_available_kib": MIN_RUNTIME_AVAILABLE_KIB,
        "max_runtime_swap_used_kib": MAX_RUNTIME_SWAP_USED_KIB,
        "max_runtime_temperature_c_exclusive": MAX_RUNTIME_TEMPERATURE_C,
        "maximum_resident_models": 1,
        "power_mode": "15W mode 0",
        "fan_required": True,
        "unchanged_boot_and_thermal_trip_counters": True,
        "telemetry_interval_ms": 500,
        "telemetry_stall_ceiling_seconds": 5,
        "persistent_system_changes": False,
        "prior_arc_limits_reused": False,
    }


@contextmanager
def stage2_limits():
    """Install six Python constants temporarily, restoring them in finally."""
    previous = {name: getattr(pair, name) for name in _OVERRIDES}
    try:
        for name, value in _OVERRIDES.items():
            setattr(pair, name, value)
        yield policy_dict()
    finally:
        for name, value in previous.items():
            setattr(pair, name, value)


def require_ready(snapshot):
    """Apply the original start checks using the explicit Stage 2 constants."""
    if any(getattr(pair, name) != value for name, value in _OVERRIDES.items()):
        raise RuntimeError("require_ready must run inside stage2_limits()")
    memory = snapshot.get("memory")
    if not isinstance(memory, dict) or any(
        type(memory.get(name)) is not int or memory[name] < 0
        for name in ("mem_available_kib", "swap_used_kib")
    ):
        raise pair.SafetyGateError("Stage 2 startup memory readings are incomplete")
    if not isinstance(snapshot.get("boot_id"), str) or not snapshot["boot_id"]:
        raise pair.SafetyGateError("Stage 2 startup boot ID is unavailable")
    if type(snapshot.get("fan_pwm")) is not int or snapshot["fan_pwm"] <= 0:
        raise pair.SafetyGateError("Stage 2 requires a measured running fan")
    trips = snapshot.get("thermal_trip_events")
    if not isinstance(trips, dict) or not trips or any(
        type(value) is not int or value != 0 for value in trips.values()
    ):
        raise pair.SafetyGateError("Stage 2 requires measured zero thermal trip counters")
    # The existing pair start guard accepts exactly 55 C; this experiment
    # preregisters a strict below-55 start, matching the known-pair launcher.
    temperatures = snapshot.get("temperatures_c")
    if not isinstance(temperatures, dict) or not temperatures or any(
        type(value) not in (int, float) or not math.isfinite(value) or value < 0
        for value in temperatures.values()
    ):
        raise pair.SafetyGateError("Stage 2 startup temperatures are incomplete")
    if max(temperatures.values()) >= MAX_START_TEMPERATURE_C:
        raise pair.SafetyGateError("Stage 2 startup temperature must be below 55 C")
    try:
        pair._require_start_safe(snapshot)
    except pair.SafetyGateError as error:
        # Two messages in the older helper contain its original literal
        # thresholds. Keep errors truthful while reusing every actual check.
        messages = {
            "available memory is below the 2.5 GiB start gate":
                "available memory is below the Stage 2 2 GiB start gate",
            "swap use exceeds the 128 MiB start gate":
                "swap use exceeds the Stage 2 768 MiB start gate",
        }
        raise pair.SafetyGateError(messages.get(str(error), str(error))) from error


# This is read-only metadata capture; no inference or device mutation occurs.
capture_safety_snapshot = pair.capture_safety_snapshot
