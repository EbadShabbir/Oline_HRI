"""Offline schedule boundaries: no retry stitching or accidental live calls."""

from contextlib import ExitStack, nullcontext
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import freeze_post_memory_comparison as freezer
import run_post_memory_batch as batch
from oline_hri.evaluation_model_pairs import ModelPairEvaluationError


class PostMemoryBatchTests(unittest.TestCase):
    def setup_files(self, root):
        workload = root / "workload.json"
        workload.write_text('{}\n')
        frozen = root / "freeze.json"
        frozen.write_text(json.dumps({
            "profile_id": "post_memory_comparison_v1", "source_sha256": {},
            "workload_sha256": sha256(workload.read_bytes()).hexdigest(),
            "planned_attempts": 432,
            "counterbalanced_arm_orders": [list(arms) for arms in batch.ARM_ORDERS],
        }))
        return ["--workload", str(workload), "--freeze", str(frozen),
                "--output-root", str(root / "run")]

    def mocks(self, stack):
        state = {"boot_id": "fixed", "thermal_trip_events": {"x": 0},
                 "resident_models": [], "power_mode": "15W mode 0"}
        stack.enter_context(patch.object(batch, "source_hashes", return_value={}))
        snapshot = stack.enter_context(patch.object(batch, "capture_safety_snapshot", return_value=state))
        ready = stack.enter_context(patch.object(batch, "require_ready"))
        stack.enter_context(patch.object(batch, "stage2_limits", side_effect=nullcontext))
        run = stack.enter_context(patch.object(batch.subprocess, "run", return_value=SimpleNamespace(returncode=0)))
        sleep = stack.enter_context(patch.object(batch, "sleep"))
        return snapshot, ready, run, sleep

    def test_complete_serial_schedule_launches_each_arm_once_per_round(self):
        with TemporaryDirectory() as temp, ExitStack() as stack:
            root = Path(temp)
            args = self.setup_files(root)
            _, _, run, _ = self.mocks(stack)
            self.assertEqual(batch.main(args), 0)
            observed = []
            for call in run.call_args_list:
                argv = call.args[0]
                self.assertTrue(argv[1].endswith('run_post_memory_comparison.py'))
                observed.append((argv[argv.index('--arm')+1], int(argv[argv.index('--repetition')+1])))
            self.assertEqual(observed, [(arm, rep) for _, arm, rep in batch.session_slots()])
            self.assertEqual(len(set(observed)), 9)
            self.assertEqual(observed[:3], [("large", 1), ("cascade", 1), ("small", 1)])
            self.assertEqual(json.loads((root/'run/batch_finish.json').read_text())['status'], 'complete')

    def test_failed_session_stops_without_peer_or_tail_retry(self):
        with TemporaryDirectory() as temp, ExitStack() as stack:
            root=Path(temp)
            args=self.setup_files(root)
            _, _, run, _=self.mocks(stack)
            run.return_value=SimpleNamespace(returncode=1)
            self.assertEqual(batch.main(args), 1)
            self.assertEqual(run.call_count, 1)
            finish=json.loads((root/'run/batch_finish.json').read_text())
            self.assertEqual(len(finish['sessions']), 1)
            self.assertEqual(len(finish['sessions_not_launched']), 8)
            self.assertEqual(finish['sessions'][0]['exit_code'], 1)

    def test_blocked_admission_records_zero_launched_sessions(self):
        with TemporaryDirectory() as temp, ExitStack() as stack:
            root=Path(temp)
            args=self.setup_files(root)
            _, ready, run, sleep=self.mocks(stack)
            ready.side_effect=batch.SafetyGateError('swap startup gate')
            stack.enter_context(patch.object(batch, 'monotonic', side_effect=[0, 601]))
            self.assertEqual(batch.main(args), 1)
            run.assert_not_called()
            sleep.assert_not_called()
            finish=json.loads((root/'run/batch_finish.json').read_text())
            self.assertEqual(finish['sessions'], [])
            self.assertEqual(len(finish['sessions_not_launched']), 9)
            self.assertEqual(len(json.loads((root/'run/startup_waits.json').read_text())), 1)

    def test_source_change_between_sessions_prevents_next_launch(self):
        with TemporaryDirectory() as temp, ExitStack() as stack:
            root=Path(temp)
            args=self.setup_files(root)
            _, _, run, _=self.mocks(stack)
            stack.enter_context(patch.object(batch, 'source_hashes', side_effect=[{}, {}, {'changed': 'digest'}]))
            self.assertEqual(batch.main(args), 1)
            self.assertEqual(run.call_count, 1)
            self.assertIn('source changed', json.loads((root/'run/batch_finish.json').read_text())['failure']['message'])

    def test_old_profile_or_existing_output_cannot_be_reused(self):
        with TemporaryDirectory() as temp, ExitStack() as stack:
            root=Path(temp)
            args=self.setup_files(root)
            _, _, run, _=self.mocks(stack)
            (root/'run').mkdir()
            with self.assertRaisesRegex(ModelPairEvaluationError, 'output directory already exists'):
                batch.main(args)
            frozen=json.loads((root/'freeze.json').read_text())
            frozen['profile_id']='legacy'
            (root/'freeze.json').write_text(json.dumps(frozen))
            with self.assertRaisesRegex(ValueError, 'profile'):
                batch.main(args)
            run.assert_not_called()

    def test_freeze_refuses_changed_validated_source_before_device_reads(self):
        with TemporaryDirectory() as temp, ExitStack() as stack:
            root=Path(temp)
            (root/'changed.py').write_text('changed')
            validation=root/'validation.json'
            validation.write_text(json.dumps({'exit_code':0, 'failures':0, 'errors':0,
                'source_config_script_and_test_sha256':{'changed.py':'0'*64}}))
            stack.enter_context(patch.object(freezer,'ROOT',root))
            stack.enter_context(patch.object(freezer,'load_workload',return_value={}))
            stack.enter_context(patch('analyze_complete_system.validate_workload'))
            stack.enter_context(patch('run_post_memory_comparison.source_hashes',return_value={}))
            device=stack.enter_context(patch.object(freezer,'_installed_models'))
            with self.assertRaisesRegex(ValueError,'validated file changed'):
                freezer.main(['--workload',str(root/'w.json'),'--protocol',str(root/'p.md'),
                              '--validation',str(validation),'--output-dir',str(root/'frozen')])
            device.assert_not_called()
            self.assertFalse((root/'frozen').exists())


if __name__ == '__main__':
    unittest.main()
