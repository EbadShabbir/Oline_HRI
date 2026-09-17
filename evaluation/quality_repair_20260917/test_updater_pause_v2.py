"""Offline lifecycle checks: no device access or administrator operations."""
import importlib.util
from contextlib import ExitStack
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location(
    "updater_pause_v2", Path(__file__).with_name("run_with_idle_updater_paused_v2.py")
)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


class UpdaterPauseLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.events = []
        self.emit = lambda event, **data: self.events.append((event, data))
        self.child = Mock()
        self.child.wait.return_value = 0
        self.child.poll.return_value = 0
        self.child.returncode = 0
        self.states = self.stack.enter_context(patch.object(helper, "service_state"))
        self.admin = self.stack.enter_context(patch.object(helper, "admin_service_action"))
        self.admin.return_value = subprocess.CompletedProcess([], 0)
        self.properties = self.stack.enter_context(patch.object(
            helper.subprocess, "check_output", side_effect=["u 1", "u 0"]
        ))
        self.popen = self.stack.enter_context(patch.object(
            helper.subprocess, "Popen", return_value=self.child
        ))

    def run_cohort(self):
        return helper.run_paused(Path("/prepared/cohort"), 16, self.emit)

    def actions(self):
        return [call.args[0] for call in self.admin.call_args_list]

    def event_names(self):
        return [name for name, _ in self.events]

    def test_success_restores_initial_active_service(self):
        self.states.side_effect = ["active", "inactive", "inactive", "active"]
        self.assertEqual(self.run_cohort(), 0)
        self.assertEqual(self.actions(), ["stop", "start"])
        self.assertIn("restored", self.event_names())
        self.assertEqual(self.properties.call_count, 2)
        self.child.send_signal.assert_not_called()

    def test_failed_stop_without_effect_does_not_request_restart(self):
        self.states.side_effect = ["active", "active"]
        self.admin.side_effect = subprocess.TimeoutExpired(["pkexec", "stop"], 90)
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_cohort()
        self.assertEqual(self.actions(), ["stop"])
        self.popen.assert_not_called()
        self.assertIn("restoration_not_needed", self.event_names())

    def test_failed_stop_that_took_effect_still_restores(self):
        self.states.side_effect = ["active", "inactive", "active"]
        self.admin.side_effect = [subprocess.TimeoutExpired(["pkexec", "stop"], 90),
                                  subprocess.CompletedProcess([], 0)]
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_cohort()
        self.assertEqual(self.actions(), ["stop", "start"])
        self.popen.assert_not_called()
        self.assertIn("restored", self.event_names())

    def test_child_interrupt_cleans_up_and_restores(self):
        self.states.side_effect = ["active", "inactive", "inactive", "active"]
        self.child.wait.side_effect = [KeyboardInterrupt("interrupted"), -2]
        self.child.poll.return_value = None
        with self.assertRaises(KeyboardInterrupt):
            self.run_cohort()
        self.child.send_signal.assert_called_once_with(helper.signal.SIGINT)
        self.assertEqual(self.actions(), ["stop", "start"])
        self.assertIn("child_cleanup_finished", self.event_names())

    def test_child_cleanup_timeout_cannot_skip_restoration(self):
        self.states.side_effect = ["active", "inactive", "inactive", "active"]
        self.child.wait.side_effect = [RuntimeError("child failed"),
                                       subprocess.TimeoutExpired(["guarded-child"], 90)]
        self.child.poll.return_value = None
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_cohort()
        self.assertEqual(self.actions(), ["stop", "start"])
        self.assertIn("child_cleanup_error", self.event_names())
        self.assertIn("restored", self.event_names())

    def test_child_cleanup_signal_error_cannot_skip_restoration(self):
        self.states.side_effect = ["active", "inactive", "inactive", "active"]
        self.child.wait.side_effect = RuntimeError("child failed")
        self.child.poll.return_value = None
        self.child.send_signal.side_effect = ProcessLookupError("child exited")
        with self.assertRaises(ProcessLookupError):
            self.run_cohort()
        self.assertEqual(self.actions(), ["stop", "start"])
        self.assertIn("restored", self.event_names())

    def test_inactive_initial_service_is_not_activated_by_probe(self):
        self.states.return_value = "inactive"
        with self.assertRaisesRegex(RuntimeError, "initially be active"):
            self.run_cohort()
        self.properties.assert_not_called()
        self.admin.assert_not_called()
        self.popen.assert_not_called()

    def test_busy_initial_service_is_not_stopped(self):
        self.states.return_value = "active"
        self.properties.side_effect = ["u 2", "u 15"]
        with self.assertRaisesRegex(RuntimeError, "not confirmed idle"):
            self.run_cohort()
        self.admin.assert_not_called()
        self.popen.assert_not_called()

    def test_restoration_authorization_failure_is_recorded_and_propagated(self):
        self.states.side_effect = ["active", "inactive", "inactive"]
        self.admin.side_effect = [subprocess.CompletedProcess([], 0),
                                  subprocess.CalledProcessError(126, ["pkexec", "start"])]
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_cohort()
        self.assertIn("restoration_error", self.event_names())

    def test_unreadable_final_state_still_attempts_restoration(self):
        self.states.side_effect = ["active", "inactive", RuntimeError("status unavailable"), "active"]
        self.assertEqual(self.run_cohort(), 0)
        self.assertEqual(self.actions(), ["stop", "start"])
        self.assertIn("restoration_state_check_error", self.event_names())


class ServiceOperationTests(unittest.TestCase):
    def test_state_probe_uses_systemd_without_dbus_activation(self):
        with patch.object(helper.subprocess, "run", return_value=subprocess.CompletedProcess(
            [], 0, stdout="active\n"
        )) as run:
            self.assertEqual(helper.service_state(), "active")
        self.assertEqual(run.call_args.args[0], [
            "systemctl", "show", "fwupd.service", "--property=ActiveState", "--value"
        ])
        self.assertTrue(run.call_args.kwargs["check"])

    def test_admin_operation_keeps_normal_authorization_and_timeout(self):
        with patch.object(helper.subprocess, "run") as run:
            helper.admin_service_action("stop")
        self.assertEqual(run.call_args.args[0], [
            "pkexec", "--disable-internal-agent", "/usr/bin/systemctl", "stop", "fwupd.service"
        ])
        self.assertTrue(run.call_args.kwargs["check"])
        self.assertEqual(run.call_args.kwargs["timeout"], 90)


if __name__ == "__main__":
    unittest.main(verbosity=2)
