"""No-inference tests for the declared grid and reusable embedding cache."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_dependency_classifier import Embedder, corpus


class DependencyGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "scripts/grid_dependency_classifier.py"
        spec = importlib.util.spec_from_file_location("dependency_grid_script", path)
        cls.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.script)

    def test_six_variants_reuse_one_embedding_pass_and_preserve_every_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "corpus.json", Path(tmp) / "grid"
            source.write_text(json.dumps(corpus()), encoding="utf-8")
            provider = Embedder()
            with patch.object(self.script, "BgeOnnxEmbedder", return_value=provider):
                self.assertEqual(self.script.main(["--corpus", str(source), "--output-dir", str(output)]), 0)
            self.assertEqual(sum(map(len, provider.calls)), 28)
            self.assertTrue(all(len(call) <= 8 for call in provider.calls))
            summary = json.loads((output / "summary.json").read_text())
            self.assertEqual(len(summary["variants"]), 6)
            self.assertFalse(summary["installed"])
            self.assertIsNone(summary["selected"])
            self.assertEqual({(row["settings"]["regularization"], row["settings"]["embedding_weight"])
                              for row in summary["variants"]}, {(r, w) for r in (0.1, 1.0, 10.0) for w in (0.25, 1.0)})
            for row in summary["variants"]:
                self.assertEqual(row["calibration"]["count"], 12)
                self.assertTrue((output / row["name"] / "classifier.json").exists())
                self.assertTrue((output / row["name"] / "diagnostics.json").exists())
            self.assertEqual(len(json.loads((output / "embedding_cache.json").read_text())["records"]), 28)
            with patch.object(self.script, "BgeOnnxEmbedder") as factory, self.assertRaises(FileExistsError):
                self.script.main(["--corpus", str(source), "--output-dir", str(output)])
            factory.assert_not_called()

    def test_cache_never_falls_back_to_inference_on_unknown_input(self):
        cached, records = self.script.cache_embeddings(corpus()["cases"], Embedder())
        self.assertEqual(len(records), 28)
        with self.assertRaises(KeyError):
            cached.embed_passages(["unseen input"])

    def test_corpus_error_is_recorded_before_any_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "bad.json", Path(tmp) / "grid"
            source.write_text('{"cases":[]}', encoding="utf-8")
            with patch.object(self.script, "BgeOnnxEmbedder") as factory:
                self.assertEqual(self.script.main(["--corpus", str(source), "--output-dir", str(output)]), 1)
            factory.assert_not_called()
            summary = json.loads((output / "summary.json").read_text())
            self.assertEqual(summary["status"], "error")
            self.assertEqual(summary["variants"], [])


if __name__ == "__main__":
    unittest.main()
