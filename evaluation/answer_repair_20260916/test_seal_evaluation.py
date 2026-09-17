"""Small synthetic pre-inference seal checks; no real cohort or model access."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("repair_seal", Path(__file__).with_name("seal_evaluation.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SealTests(unittest.TestCase):
    def fixture(self, root):
        (root / "source.py").write_text("version = 1\n")
        cohort = root / "cohort"
        archived = cohort / "candidate_source"
        archived.mkdir(parents=True)
        (archived / "source.py").write_bytes((root / "source.py").read_bytes())
        (cohort / "cases.json").write_text("[]\n")
        candidate = {"cases_sha256": module.sha(cohort / "cases.json"),
                     "source_sha256": {"source.py": module.sha(root / "source.py")}}
        (cohort / "candidate_freeze.json").write_text(json.dumps(candidate))
        (cohort / "protocol.md").write_text("Known development only.\n")
        return cohort

    def test_source_archive_and_explicit_artifacts_are_sealed_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cohort = self.fixture(root)
            with patch.object(module, "ROOT", root):
                target, value = module.seal(cohort, "Known development", ["protocol.md"])
                self.assertEqual(set(value["artifact_sha256"]), {"cases.json", "candidate_freeze.json", "protocol.md"})
                self.assertFalse(value["inference_started"])
                before = target.read_bytes()
                with self.assertRaisesRegex(ValueError, "already exists"):
                    module.seal(cohort, "Changed scope", [])
                self.assertEqual(target.read_bytes(), before)

    def test_post_inference_and_source_drift_fail_before_creating_seal(self):
        for reason in ("collection", "source"):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                cohort = self.fixture(root)
                if reason == "collection":
                    (cohort / "collection").mkdir()
                else:
                    (root / "source.py").write_text("version = 2\n")
                with patch.object(module, "ROOT", root), self.assertRaises(ValueError):
                    module.seal(cohort, "Known development", [])
                self.assertFalse((cohort / "evaluation_freeze.json").exists())


if __name__ == "__main__":
    unittest.main()
