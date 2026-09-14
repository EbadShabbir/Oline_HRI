"""Scoped revised swap admission for the post-memory comparison.

Both swap ceilings use the already configured logical capacity minus a
256 MiB reserve. This is an explicitly revised experimental rule, not an
established hardware safety threshold or a promise that a workload fits.
No swap device, service, power setting, or other OS configuration is changed.

Physical-memory, temperature, residency, boot/trip and telemetry protections
remain those used by the existing sampler/backend. Keep this context active
from before embedding setup through cleanup, sampler shutdown and final
verification. Capacity is observed at admission and final capture;
existing runtime guards continuously/sample-check RAM, logical swap and heat.
Separate arm processes are required; these module globals are not intended
for concurrent experiments within one Python process.
"""

from __future__ import annotations

from contextlib import contextmanager
import math
from types import MappingProxyType

from oline_hri import evaluation_model_pairs as pair


POLICY_ID = "post_memory_existing_swap_reserve_v2"
EXPECTED_SWAP_TOTAL_KIB = 3901608
SWAP_RESERVE_KIB = 256 * 1024
MIN_START_AVAILABLE_KIB = 2 * 1024 * 1024
MAX_START_SWAP_USED_KIB = EXPECTED_SWAP_TOTAL_KIB - SWAP_RESERVE_KIB
MAX_START_TEMPERATURE_C = 55.0
MIN_RUNTIME_AVAILABLE_KIB = 768 * 1024
MAX_RUNTIME_SWAP_USED_KIB = MAX_START_SWAP_USED_KIB
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
    return {
        "policy_id": POLICY_ID,
        "scope": "all revised post-memory arms; embeddings through final cleanup",
        "min_start_available_kib": MIN_START_AVAILABLE_KIB,
        "max_start_swap_used_kib": MAX_START_SWAP_USED_KIB,
        "max_start_temperature_c_exclusive": MAX_START_TEMPERATURE_C,
        "min_runtime_available_kib": MIN_RUNTIME_AVAILABLE_KIB,
        "max_runtime_swap_used_kib": MAX_RUNTIME_SWAP_USED_KIB,
        "max_runtime_temperature_c_exclusive": MAX_RUNTIME_TEMPERATURE_C,
        "expected_swap_total_kib": EXPECTED_SWAP_TOTAL_KIB,
        "logical_swap_reserve_kib": SWAP_RESERVE_KIB,
        "swap_capacity_policy": "existing capacity minus 256 MiB; equal start/runtime ceilings",
        "swap_policy_interpretation": "revised experiment admission; not a validated physical safety threshold",
        "swap_configuration_monitoring": "capacity in admission/final snapshots; runtime logical usage monitoring",
        "maximum_resident_models": 1,
        "power_mode": "15W mode 0",
        "fan_required": True,
        "unchanged_boot_and_thermal_trip_counters": True,
        "telemetry_interval_ms": 500,
        "telemetry_stall_ceiling_seconds": 5,
        "persistent_system_changes": False,
        "prior_arc_limits_reused": False,
    }


capture_safety_snapshot = pair.capture_safety_snapshot


@contextmanager
def stage2_limits():
    """Temporarily install six Python constants; always restore their values."""
    previous = {name: getattr(pair, name) for name in _OVERRIDES}
    try:
        for name, value in _OVERRIDES.items():
            setattr(pair, name, value)
        yield policy_dict()
    finally:
        for name, value in previous.items():
            setattr(pair, name, value)


def require_ready(snapshot):
    if any(getattr(pair, name) != value for name, value in _OVERRIDES.items()):
        raise RuntimeError("require_ready must run inside stage2_limits()")
    memory = snapshot.get("memory")
    if not isinstance(memory, dict) or any(
        type(memory.get(name)) is not int or memory[name] < 0
        for name in ("mem_available_kib", "swap_used_kib", "swap_total_kib")
    ):
        raise pair.SafetyGateError("revised startup memory readings are incomplete")
    if memory["swap_total_kib"] != EXPECTED_SWAP_TOTAL_KIB:
        raise pair.SafetyGateError("configured swap capacity differs from the revised freeze")
    if not isinstance(snapshot.get("boot_id"), str) or not snapshot["boot_id"]:
        raise pair.SafetyGateError("revised startup boot ID is unavailable")
    if type(snapshot.get("fan_pwm")) is not int or snapshot["fan_pwm"] <= 0:
        raise pair.SafetyGateError("revised comparison requires a measured running fan")
    trips = snapshot.get("thermal_trip_events")
    if not isinstance(trips, dict) or not trips or any(
        type(value) is not int or value != 0 for value in trips.values()
    ):
        raise pair.SafetyGateError("revised comparison requires measured zero thermal trip counters")
    temperatures = snapshot.get("temperatures_c")
    if not isinstance(temperatures, dict) or not temperatures or any(
        type(value) not in (int, float) or not math.isfinite(value) or value < 0
        for value in temperatures.values()
    ):
        raise pair.SafetyGateError("revised startup temperatures are incomplete")
    if max(temperatures.values()) >= MAX_START_TEMPERATURE_C:
        raise pair.SafetyGateError("revised startup temperature must be below 55 C")
    try:
        pair._require_start_safe(snapshot)
    except pair.SafetyGateError as error:
        messages = {
            "available memory is below the 2.5 GiB start gate":
                "available memory is below the revised 2 GiB start gate",
            "swap use exceeds the 128 MiB start gate":
                "swap use exceeds existing capacity minus the 256 MiB reserve",
        }
        raise pair.SafetyGateError(messages.get(str(error), str(error))) from error
