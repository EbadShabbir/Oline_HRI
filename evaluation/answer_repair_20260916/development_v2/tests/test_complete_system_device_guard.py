"""Offline admission, shared runtime policy, and exception restoration checks."""

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import complete_system_device_guard as guard
import run_pair_remediation_validation as remediation
from oline_hri import evaluation_model_pairs as pair


def snapshot():
    return {
        "boot_id": "offline-boot",
        "memory": {"mem_available_kib": 2 * 1024 * 1024,
                   "swap_used_kib": 768 * 1024},
        "temperatures_c": {"cpu": 54.999, "gpu": 51.0},
        "resident_models": [], "fan_pwm": 77,
        "thermal_trip_events": {"cpu": 0, "gpu": 0},
        "power_mode": "NV Power Mode: 15W\n0",
    }


class CompleteSystemDeviceGuardTests(unittest.TestCase):
    def test_start_boundary_has_no_snapshot_mutation_and_requires_explicit_scope(self):
        value = snapshot()
        original = deepcopy(value)
        with self.assertRaisesRegex(RuntimeError, "inside stage2_limits"):
            guard.require_ready(value)
        with guard.stage2_limits() as policy:
            guard.require_ready(value)
            self.assertEqual(policy["max_runtime_swap_used_kib"], 1024 * 1024)
            policy["max_runtime_swap_used_kib"] = 0
            self.assertEqual(guard.policy_dict()["max_runtime_swap_used_kib"], 1024 * 1024)
        self.assertEqual(value, original)

    def test_missing_and_invalid_sensors_fail_closed(self):
        mutations = [
            ("memory", "mem_available_kib", 2 * 1024 * 1024 - 1),
            ("memory", "swap_used_kib", 768 * 1024 + 1),
            ("memory", "swap_used_kib", -1),
            ("memory", "swap_used_kib", True),
            ("memory", "mem_available_kib", float("nan")),
            ("temperatures_c", "cpu", 55.0),
            ("temperatures_c", "cpu", float("nan")),
            ("temperatures_c", "cpu", float("inf")),
            ("thermal_trip_events", "cpu", 1),
            ("thermal_trip_events", "cpu", False),
        ]
        with guard.stage2_limits():
            for section, key, bad in mutations:
                with self.subTest(section=section, key=key, bad=bad):
                    value = snapshot()
                    value[section][key] = bad
                    with self.assertRaises(pair.SafetyGateError):
                        guard.require_ready(value)
            for key, bad in (("fan_pwm", None), ("fan_pwm", 0), ("fan_pwm", True),
                             ("boot_id", ""), ("thermal_trip_events", {}),
                             ("temperatures_c", {}),
                             ("resident_models", [{"name": "unrelated:model"}]),
                             ("power_mode", "NV Power Mode: 25W\n0"),
                             ("power_mode", "NV Power Mode: 15W\n1")):
                with self.subTest(key=key, bad=bad):
                    value = snapshot()
                    value[key] = bad
                    with self.assertRaises(pair.SafetyGateError):
                        guard.require_ready(value)

    def test_nested_and_interrupt_exit_restore_every_previous_limit(self):
        original = {name: getattr(pair, name) for name in guard._OVERRIDES}
        with self.assertRaises(KeyboardInterrupt):
            with guard.stage2_limits():
                with guard.stage2_limits():
                    self.assertEqual(pair.MAX_RUNTIME_SWAP_USED_KIB, 1024 * 1024)
                self.assertEqual(pair.MAX_START_SWAP_USED_KIB, 768 * 1024)
                raise KeyboardInterrupt("offline interrupt")
        self.assertEqual({name: getattr(pair, name) for name in original}, original)

    def test_already_imported_runtime_guard_uses_new_limits_and_keeps_invariants(self):
        memory = {"mem_available_kib": 768 * 1024, "swap_used_kib": 900 * 1024}
        temperatures = {"cpu": 60.0}
        trips = {"cpu": 0}
        residents = []
        with patch.object(pair, "_memory_snapshot", return_value=memory), \
             patch.object(pair, "_temperature_snapshot", return_value=temperatures), \
             patch.object(pair, "_boot_id", return_value="offline-boot") as boot, \
             patch.object(pair, "_throttle_snapshot", return_value=trips), \
             patch.object(pair, "_resident_models", return_value=residents), \
             guard.stage2_limits():
            def check():
                return remediation._require_runtime_safe(
                    boot_id="offline-boot", initial_trip_events={"cpu": 0})
            self.assertEqual(check()["memory"], memory)
            for mapping, key, bad in ((memory, "mem_available_kib", 768 * 1024 - 1),
                                      (memory, "swap_used_kib", 1024 * 1024 + 1),
                                      (temperatures, "cpu", 68.0), (trips, "cpu", 1)):
                old = mapping[key]
                mapping[key] = bad
                with self.subTest(key=key), self.assertRaises(pair.SafetyGateError):
                    check()
                mapping[key] = old
            boot.return_value = "different-boot"
            with self.assertRaisesRegex(pair.SafetyGateError, "boot ID"):
                check()
            boot.return_value = "offline-boot"
            residents.extend([{"name": "small"}, {"name": "large"}])
            with self.assertRaisesRegex(pair.SafetyGateError, "more than one"):
                check()

    def test_streaming_guard_persists_crossing_before_interrupt_and_uses_common_ceiling(self):
        persisted = []
        class Writer:
            def write(self, value):
                persisted.append(deepcopy(value))
        monitor = pair._StreamingSafetyMonitor(Writer())
        sample = {"ram": {"total_mb": 7620, "used_mb": 6500},
                  "swap": {"used_mb": 1024}, "temperatures_c": {"cpu": 60.0}}
        def interrupted():
            self.assertEqual(persisted[-1]["swap"]["used_mb"], 1025)
            self.assertEqual(monitor.violation, "telemetry swap ceiling crossed")
        with guard.stage2_limits(), patch.object(pair._thread, "interrupt_main",
                                                 side_effect=interrupted) as interrupt:
            monitor(sample)
            interrupt.assert_not_called()
            sample["swap"]["used_mb"] = 1025
            monitor(sample)
            interrupt.assert_called_once()
            monitor(sample)
            self.assertEqual(len(persisted), 3)
            interrupt.assert_called_once()


if __name__ == "__main__":
    unittest.main()
