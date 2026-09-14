"""Offline protection tests; never invoke freeze, collection, or model calls."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('first_repair_staging', HERE / 'stage_first_repair_reproduction.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class StagingProtectionTests(unittest.TestCase):
    def test_independent_evaluation_directory_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='clara-stage-reject-', dir='/tmp') as temporary:
            stage = Path(temporary)
            (stage / 'evaluation').mkdir()
            (stage / '.venv').symlink_to(helper.REPO / '.venv', target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'share the real repository evaluation'):
                helper.shared_lock_identities(stage)

    def test_symlink_to_copied_lease_directory_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='clara-stage-reject-', dir='/tmp') as temporary:
            parent = Path(temporary)
            stage, independent = parent / 'stage', parent / 'private-evaluation'
            stage.mkdir(); independent.mkdir()
            for lock in helper.LOCKS:
                (independent / lock).touch()
            (stage / 'evaluation').symlink_to(independent, target_is_directory=True)
            (stage / '.venv').symlink_to(helper.REPO / '.venv', target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'share the real repository evaluation'):
                helper.shared_lock_identities(stage)

    def test_source_drift_rejected_before_import_smoke(self):
        with tempfile.TemporaryDirectory(prefix='clara-stage-reject-', dir='/tmp') as temporary:
            stage = Path(temporary)
            (stage / 'evaluation').symlink_to(helper.REPO / 'evaluation', target_is_directory=True)
            (stage / '.venv').symlink_to(helper.REPO / '.venv', target_is_directory=True)
            (stage / 'config').mkdir()
            (stage / 'config/default.json').write_text('{}')
            with mock.patch.object(helper, 'smoke', side_effect=AssertionError('must not import after drift')) as smoke:
                with self.assertRaisesRegex(ValueError, 'staged source differs: config/default.json'):
                    helper.verify_stage(stage, stage.parent / 'unused-collection-output')
                smoke.assert_not_called()

    def test_existing_output_and_output_in_source_stage_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix='clara-stage-reject-', dir='/tmp') as temporary:
            parent = Path(temporary)
            with self.assertRaisesRegex(ValueError, 'must not already exist'):
                helper.checked_paths(parent / 'future-stage', parent)
            with self.assertRaisesRegex(ValueError, 'outside the source stage'):
                helper.checked_paths(parent / 'future-stage', parent / 'future-stage/output')

    def test_real_repository_lock_identities_match_staged_paths(self):
        with tempfile.TemporaryDirectory(prefix='clara-stage-identity-', dir='/tmp') as temporary:
            stage = Path(temporary)
            (stage / 'evaluation').symlink_to(helper.REPO / 'evaluation', target_is_directory=True)
            (stage / '.venv').symlink_to(helper.REPO / '.venv', target_is_directory=True)
            witnesses = helper.shared_lock_identities(stage)
            self.assertEqual(len(witnesses), 4)
            self.assertTrue(all(w['real'] == w['staged'] for w in witnesses))


if __name__ == '__main__':
    unittest.main(verbosity=2)
