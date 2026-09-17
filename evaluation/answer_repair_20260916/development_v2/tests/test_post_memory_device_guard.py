"""Offline boundaries for revised existing-capacity swap admission."""

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import complete_system_device_guard as original_guard
import post_memory_device_guard as guard
import run_pair_remediation_validation as remediation
from oline_hri import evaluation_model_pairs as pair


def snapshot():
    return {
        "boot_id": "offline-boot",
        "memory": {"mem_available_kib": 2391 * 1024, "swap_used_kib": 988 * 1024,
                   "swap_total_kib": guard.EXPECTED_SWAP_TOTAL_KIB},
        "temperatures_c": {"cpu": 51.281, "gpu": 51.0},
        "resident_models": [], "fan_pwm": 73,
        "thermal_trip_events": {"cpu": 0, "gpu": 0},
        "power_mode": "NV Power Mode: 15W\n0",
    }


class PostMemoryDeviceGuardTests(unittest.TestCase):
    def test_historical_988_mib_rejection_is_admitted_only_under_explicit_revision(self):
        value = snapshot()
        preserved = deepcopy(value)
        with original_guard.stage2_limits(), self.assertRaisesRegex(pair.SafetyGateError, "768 MiB"):
            original_guard.require_ready(value)
        with self.assertRaisesRegex(RuntimeError, "inside stage2_limits"):
            guard.require_ready(value)
        with guard.stage2_limits() as policy:
            guard.require_ready(value)
            self.assertEqual(policy["expected_swap_total_kib"], 3901608)
            self.assertEqual(policy["logical_swap_reserve_kib"], 262144)
            self.assertEqual(policy["max_start_swap_used_kib"], 3639464)
            self.assertEqual(policy["max_runtime_swap_used_kib"], 3639464)
            policy["max_start_swap_used_kib"] = 0
            self.assertEqual(guard.policy_dict()["max_start_swap_used_kib"], 3639464)
        self.assertEqual(value, preserved)
        self.assertIs(guard.capture_safety_snapshot, pair.capture_safety_snapshot)

    def test_reserve_boundary_accepts_equality_and_rejects_one_kib_more(self):
        value = snapshot()
        value["memory"].update(mem_available_kib=2 * 1024 * 1024,
                               swap_used_kib=guard.MAX_START_SWAP_USED_KIB)
        value["temperatures_c"]["cpu"] = 54.999
        with guard.stage2_limits():
            guard.require_ready(value)
            value["memory"]["swap_used_kib"] += 1
            with self.assertRaisesRegex(pair.SafetyGateError, "256 MiB reserve"):
                guard.require_ready(value)

    def test_capacity_drift_missing_capacity_and_bad_memory_readings_fail_closed(self):
        with guard.stage2_limits():
            for capacity in (guard.EXPECTED_SWAP_TOTAL_KIB - 1, guard.EXPECTED_SWAP_TOTAL_KIB + 1,
                             None, True, float(guard.EXPECTED_SWAP_TOTAL_KIB)):
                with self.subTest(capacity=capacity):
                    value = snapshot()
                    value["memory"]["swap_total_kib"] = capacity
                    with self.assertRaises(pair.SafetyGateError):
                        guard.require_ready(value)
            for key, bad in (("mem_available_kib", 2 * 1024 * 1024 - 1),
                             ("swap_used_kib", -1), ("swap_used_kib", True)):
                value = snapshot()
                value["memory"][key] = bad
                with self.subTest(key=key, bad=bad), self.assertRaises(pair.SafetyGateError):
                    guard.require_ready(value)

    def test_temperature_fan_power_boot_trip_and_empty_residency_requirements_remain(self):
        mutations = [
            ("temperatures_c", {"cpu": 55.0}),
            ("temperatures_c", {"cpu": float("nan")}),
            ("temperatures_c", {}), ("fan_pwm", 0), ("fan_pwm", None),
            ("fan_pwm", True), ("boot_id", ""), ("thermal_trip_events", {}),
            ("thermal_trip_events", {"cpu": 1}), ("thermal_trip_events", {"cpu": False}),
            ("resident_models", [{"name": "qwen3:0.6b"}]),
            ("power_mode", "NV Power Mode: 25W\n0"),
        ]
        with guard.stage2_limits():
            for key, bad in mutations:
                value = snapshot()
                value[key] = bad
                with self.subTest(key=key, bad=bad), self.assertRaises(pair.SafetyGateError):
                    guard.require_ready(value)

    def test_nested_revision_and_interrupt_restore_all_prior_constants(self):
        initial = {name: getattr(pair, name) for name in guard._OVERRIDES}
        with self.assertRaises(KeyboardInterrupt):
            with original_guard.stage2_limits():
                original = {name: getattr(pair, name) for name in guard._OVERRIDES}
                with guard.stage2_limits():
                    with guard.stage2_limits():
                        self.assertEqual(pair.MAX_START_SWAP_USED_KIB, 3639464)
                    self.assertEqual(pair.MAX_RUNTIME_SWAP_USED_KIB, 3639464)
                self.assertEqual({name: getattr(pair, name) for name in original}, original)
                raise KeyboardInterrupt("offline cancellation")
        self.assertEqual({name: getattr(pair, name) for name in initial}, initial)

    def test_already_imported_runtime_guard_observes_revision_and_all_original_invariants(self):
        memory = {"mem_available_kib": 768 * 1024, "swap_used_kib": guard.MAX_RUNTIME_SWAP_USED_KIB,
                  "swap_total_kib": guard.EXPECTED_SWAP_TOTAL_KIB}
        temperatures, trips, residents = {"cpu": 67.999}, {"cpu": 0}, []
        with patch.object(pair, "_memory_snapshot", return_value=memory), \
             patch.object(pair, "_temperature_snapshot", return_value=temperatures), \
             patch.object(pair, "_boot_id", return_value="offline-boot") as boot, \
             patch.object(pair, "_throttle_snapshot", return_value=trips), \
             patch.object(pair, "_resident_models", return_value=residents), \
             guard.stage2_limits():
            def check():
                return remediation._require_runtime_safe(boot_id="offline-boot", initial_trip_events={"cpu": 0})
            self.assertEqual(check()["memory"], memory)
            for mapping, key, bad in ((memory, "swap_used_kib", guard.MAX_RUNTIME_SWAP_USED_KIB + 1),
                                      (memory, "mem_available_kib", 768 * 1024 - 1),
                                      (temperatures, "cpu", 68.0), (trips, "cpu", 1)):
                previous = mapping[key]
                mapping[key] = bad
                with self.subTest(key=key), self.assertRaises(pair.SafetyGateError):
                    check()
                mapping[key] = previous
            boot.return_value = "different-boot"
            with self.assertRaisesRegex(pair.SafetyGateError, "boot ID"):
                check()
            boot.return_value = "offline-boot"
            residents.extend([{"name": "small"}, {"name": "large"}])
            with self.assertRaisesRegex(pair.SafetyGateError, "more than one"):
                check()

    def test_streaming_swap_crossing_is_saved_then_interrupts_once(self):
        saved = []
        class Writer:
            def write(self, value):
                saved.append(deepcopy(value))
        monitor = pair._StreamingSafetyMonitor(Writer())
        sample = {"ram": {"total_mb": 7620, "used_mb": 6500},
                  "swap": {"used_mb": guard.MAX_RUNTIME_SWAP_USED_KIB // 1024},
                  "temperatures_c": {"cpu": 60.0}}
        def interrupted():
            self.assertEqual(saved[-1]["swap"]["used_mb"], 3555)
            self.assertEqual(monitor.violation, "telemetry swap ceiling crossed")
        with guard.stage2_limits(), patch.object(pair._thread, "interrupt_main", side_effect=interrupted) as interrupt:
            monitor(sample)
            interrupt.assert_not_called()
            sample["swap"]["used_mb"] += 1
            monitor(sample)
            interrupt.assert_called_once()
            monitor(sample)
            self.assertEqual(len(saved), 3)
            interrupt.assert_called_once()


if __name__ == "__main__":
    unittest.main()
