"""Synthetic checks for freeze-before-opening and immutable holdout provenance."""
import argparse
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("quality_holdout_preparation", Path(__file__).with_name("prepare_holdout.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HoldoutPreparationTests(unittest.TestCase):
    def fixture(self, base):
        root = base / "repo"
        here = root / "evaluation/quality_repair_20260917"
        here.mkdir(parents=True)
        final = here / "final"
        final.mkdir()
        source_paths = ["src/oline_hri/example.py", "src/oline_hri/example.json",
                        "scripts/run_routing_reliability.py", "scripts/run_pair_remediation_validation.py",
                        "scripts/complete_system_device_guard.py", "evaluation/quality_repair_20260917/run_guarded.py"]
        hashes = {}
        for relative in source_paths:
            data = (relative + "\n").encode()
            for prefix in (root, final / "candidate_source"):
                path = prefix / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            hashes[relative] = sha256(data).hexdigest()
        for prefix in (root, final):
            (prefix / "tests").mkdir()
            (prefix / "tests/test_example.py").write_text("synthetic test\n")
        (final / "working_changes.diff").write_text("synthetic diff\n")
        manifest = {"created_at": "2026-09-17T00:00:00+00:00", "source_sha256": hashes,
                    "tests_sha256": {"test_example.py": module.digest(final / "tests/test_example.py")},
                    "working_diff_sha256": module.digest(final / "working_changes.diff")}
        (final / "candidate_freeze.json").write_text(json.dumps(manifest))
        author = here / "synthetic_author"
        author.mkdir()
        modes = [mode for mode, count in module.EXPECTED_COUNTS.items() for _ in range(count)]
        cases = [{"id": f"quality_holdout_{index:03d}", "text": "Synthetic request for harness testing.",
                  "expected_modes": [mode], "rubric": {"required_components": ["Synthetic criterion."],
                  "forbidden": [], "clarification_expected": mode == "clarify",
                  "general_component_expected": mode in {"none", "optional"}}}
                 for index, mode in enumerate(modes, 1)]
        (author / "cases.json").write_text(json.dumps(cases))
        (author / "authoring_notes.md").write_text("Synthetic fixtures only.\n")
        args = argparse.Namespace(final_candidate=final, authoring_dir=author,
                cases_sha256=module.digest(author / "cases.json"),
                notes_sha256=module.digest(author / "authoring_notes.md"),
                output_dir=here / "holdout", opening_record=here / "opening.json")
        return root, here, args

    def test_success_preserves_parent_and_author_bytes_with_opening_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, here, args = self.fixture(Path(temporary))
            original = (args.final_candidate / "candidate_freeze.json").read_bytes()
            with patch.object(module, "ROOT", root), patch.object(module, "HERE", here):
                result = module.prepare(args)
            self.assertEqual(result["case_count"], 20)
            self.assertEqual(result["mode_counts"], module.EXPECTED_COUNTS)
            self.assertEqual((args.final_candidate / "candidate_freeze.json").read_bytes(), original)
            self.assertEqual((args.output_dir / "preopening_candidate_freeze.json").read_bytes(), original)
            self.assertEqual((args.authoring_dir / "cases.json").read_bytes(), (args.output_dir / "cases.json").read_bytes())
            opening = json.loads(args.opening_record.read_text())
            self.assertTrue(opening["candidate_source_and_tests_verified_before_authoring_read"])
            self.assertFalse(opening["inference_started"])

    def test_source_drift_fails_before_authoring_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, here, args = self.fixture(Path(temporary))
            (root / "src/oline_hri/example.py").write_text("changed")
            args.authoring_dir = here / "does_not_exist"
            with patch.object(module, "ROOT", root), patch.object(module, "HERE", here):
                with self.assertRaisesRegex(ValueError, "candidate source drift"):
                    module.prepare(args)
            self.assertFalse(args.opening_record.exists())
            self.assertFalse(args.output_dir.exists())

    def test_added_source_or_changed_test_fails_before_authoring_access(self):
        for changed in ("source", "test"):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as temporary:
                root, here, args = self.fixture(Path(temporary))
                target = root / ("src/oline_hri/extra.py" if changed == "source" else "tests/test_example.py")
                target.write_text("changed")
                args.authoring_dir = here / "does_not_exist"
                with patch.object(module, "ROOT", root), patch.object(module, "HERE", here):
                    with self.assertRaisesRegex(ValueError, "runtime file set|candidate test drift"):
                        module.prepare(args)
                self.assertFalse(args.opening_record.exists())

    def test_either_author_hash_mismatch_fails_before_semantic_opening(self):
        for field in ("cases_sha256", "notes_sha256"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root, here, args = self.fixture(Path(temporary))
                setattr(args, field, "0" * 64)
                with patch.object(module, "ROOT", root), patch.object(module, "HERE", here):
                    with self.assertRaisesRegex(ValueError, "hash differs"):
                        module.prepare(args)
                self.assertFalse(args.opening_record.exists())
                self.assertFalse(args.output_dir.exists())

    def test_bad_authored_schema_keeps_semantic_opening_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, here, args = self.fixture(Path(temporary))
            (args.authoring_dir / "cases.json").write_text("[]")
            args.cases_sha256 = module.digest(args.authoring_dir / "cases.json")
            with patch.object(module, "ROOT", root), patch.object(module, "HERE", here):
                with self.assertRaisesRegex(ValueError, "twenty cases"):
                    module.prepare(args)
            self.assertTrue(args.opening_record.exists())
            self.assertFalse(args.output_dir.exists())

    def test_existing_opening_or_cohort_cannot_be_overwritten(self):
        for existing in ("opening", "cohort"):
            with self.subTest(existing=existing), tempfile.TemporaryDirectory() as temporary:
                root, here, args = self.fixture(Path(temporary))
                if existing == "opening":
                    args.opening_record.write_text("prior opening")
                else:
                    args.output_dir.mkdir()
                with patch.object(module, "ROOT", root), patch.object(module, "HERE", here):
                    with self.assertRaisesRegex(ValueError, "already exists"):
                        module.prepare(args)
                if existing == "opening":
                    self.assertEqual(args.opening_record.read_text(), "prior opening")


if __name__ == "__main__":
    unittest.main()
