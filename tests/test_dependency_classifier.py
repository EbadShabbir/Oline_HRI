"""Offline classifier contracts; synthetic embeddings are not accuracy evidence."""

from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import oline_hri.dependency_classifier as dc
from oline_hri.embedding import _validated_texts
from oline_hri.ollama import ChatMessage


MARKERS = ("cobalt", "juniper", "marigold", "slate")


class Embedder:
    model_id = dc.MODEL_ID
    model_revision = dc.MODEL_REVISION
    dimension = dc.EMBEDDING_DIMENSION

    def __init__(self):
        self.calls = []

    def embed_passages(self, passages):
        _validated_texts(passages, field="passages")
        self.calls.append(tuple(passages))
        vectors = np.zeros((len(passages), self.dimension))
        for row, text in enumerate(passages):
            index = next((i for i, marker in enumerate(MARKERS) if marker in text), 0)
            vectors[row, index] = 1.0
        return vectors


def corpus():
    rows = []
    for split, count in (("train", 4), ("calibration", 3)):
        for index, mode in enumerate(dc.MODES):
            for number in range(count):
                rows.append({"id": f"{split}-{mode}-{number}", "group": f"{split}-{number}",
                             "domain": "author metadata should not enter features", "split": split,
                             "text": f"Please process {MARKERS[index]} example {number} {'training' if split == 'train' else 'calibrationonly'}.",
                             "prior_turns": [{"role": "assistant", "content": "The task context is available."}],
                             "mode": mode, "general_request": ""})
    return {"schema_version": dc.CORPUS_VERSION, "cases": rows}


def seal(document):
    document["fingerprint"] = dc._digest({key: value for key, value in document.items() if key != "fingerprint"})
    return document


class DependencyClassifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.embedder = Embedder()
        cls.rows = dc.validate_corpus(corpus())
        cls.diagnostics = {}
        cls.artifact = dc.train_dependency_classifier(
            cls.rows, cls.embedder, corpus_sha256="a" * 64, max_features=256,
            batch_size=8, diagnostics=cls.diagnostics)

    def test_roundtrip_real_shape_and_finite_serializable_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.json"
            path.write_text(json.dumps(self.artifact), encoding="utf-8")
            model = dc.DependencyClassifier(Embedder(), artifact_path=path)
            for index, mode in enumerate(dc.MODES):
                result = model.classify(f"Please process {MARKERS[index]} example 99.")
                self.assertEqual(result.predicted_mode, mode)
                self.assertEqual(result.mode, mode)
                self.assertFalse(result.uncertain)
                self.assertEqual(set(result.scores), set(dc.MODES))
                self.assertGreater(result.margin, 0)
                self.assertEqual(result.general_request, "")
                json.dumps(asdict(result), allow_nan=False)
            manifest = model.manifest
            manifest["calibration"]["per_mode"]["none"]["enabled"] = False
            self.assertTrue(model.manifest["calibration"]["per_mode"]["none"]["enabled"])

    def test_input_uses_only_text_and_bounded_history_with_current_first(self):
        expected = dc.encode_dependency_input(
            self.rows[0]["text"], (ChatMessage("assistant", "The task context is available."),))
        self.assertEqual(self.embedder.calls[0][0], expected)
        for batch in self.embedder.calls:
            self.assertLessEqual(len(batch), 8)
            for text in batch:
                self.assertNotIn("author metadata", text)
                self.assertNotIn('"mode"', text)
                self.assertNotIn("train-none-0", text)
        provider = Embedder()
        model = dc.DependencyClassifier.from_document(provider, self.artifact)
        model.classify(self.rows[0]["text"], history=(ChatMessage("assistant", "The task context is available."),))
        self.assertEqual(provider.calls, [(expected,)])
        with self.assertRaises(ValueError):
            model.classify("hello", history=(ChatMessage("system", "untrusted"),))
        self.assertEqual(dc.encode_dependency_input("Line one\nLine two\tend"), "Current request: Line one Line two end")
        with self.assertRaises(dc.DependencyClassifierError):
            dc.encode_dependency_input("embedded\x00control")

    def test_calibration_labels_do_not_fit_features_or_regression_weights(self):
        changed = deepcopy(list(self.rows))
        for row in changed:
            if row["split"] == "calibration":
                row["mode"] = dc.MODES[(dc.MODES.index(row["mode"]) + 1) % 4]
        alternative = dc.train_dependency_classifier(changed, Embedder(), corpus_sha256="b" * 64, max_features=256)
        for field in ("vocabulary", "idf", "weights", "bias"):
            self.assertEqual(alternative[field], self.artifact[field])
        self.assertNotIn("w1:calibrationonly", self.artifact["vocabulary"])
        self.assertEqual(alternative["calibration"]["raw_accuracy"], 0)
        self.assertEqual(alternative["calibration"]["coverage"], 0)

    def test_diagnostics_preserve_raw_prediction_and_calibration_membership(self):
        self.assertEqual(len(self.diagnostics["rows"]), len(self.rows))
        self.assertEqual(self.diagnostics["calibration"]["count"], 12)
        self.assertEqual(self.diagnostics["calibration"]["coverage"], 1)
        for diagnostic, row in zip(self.diagnostics["rows"], self.rows):
            self.assertEqual(diagnostic["id"], row["id"])
            self.assertEqual(diagnostic["split"], row["split"])
            self.assertEqual(diagnostic["predicted_mode"], row["mode"])

    def test_support_floor_preserves_weights_and_exact_calibration_acceptance(self):
        adjusted = dc.apply_calibration_support_floor(self.artifact, self.diagnostics,
                                                    diagnostics_sha256="b" * 64)
        for key in self.artifact.keys() - {"calibration", "fingerprint"}:
            self.assertEqual(adjusted[key], self.artifact[key])
        self.assertNotEqual(adjusted["fingerprint"], self.artifact["fingerprint"])
        self.assertEqual(adjusted["calibration"]["method"], dc.SUPPORT_FLOOR_METHOD)
        self.assertEqual(adjusted["calibration"]["support_floor"]["base_artifact_fingerprint"],
                         self.artifact["fingerprint"])
        for mode in dc.MODES:
            old = self.artifact["calibration"]["per_mode"][mode]
            new = adjusted["calibration"]["per_mode"][mode]
            accepted = [r for r in self.diagnostics["rows"] if r["split"] == "calibration"
                        and r["predicted_mode"] == mode and not r["uncertain"]]
            self.assertEqual(new["threshold"], min(r["margin"] for r in accepted))
            for row in self.diagnostics["rows"]:
                if row["split"] == "calibration" and row["predicted_mode"] == mode:
                    self.assertEqual(row["margin"] >= old["threshold"], row["margin"] >= new["threshold"])
        # Old artifacts still load, and a supported artifact retains its base fingerprint proof.
        dc.DependencyClassifier.from_document(Embedder(), self.artifact)
        dc.DependencyClassifier.from_document(Embedder(), adjusted)
        changed_training = deepcopy(self.diagnostics)
        for row in changed_training["rows"]:
            if row["split"] == "train":
                row["margin"] = 0
        self.assertEqual(adjusted, dc.apply_calibration_support_floor(
            self.artifact, changed_training, diagnostics_sha256="b" * 64))

    def test_support_floor_rejects_mismatched_diagnostics_and_resealed_provenance(self):
        for mutation in (
            lambda d: d["training"].update(corpus_sha256="f" * 64),
            lambda d: d["rows"].pop(),
            lambda d: d["rows"][-1].update(margin=0.0),
            lambda d: d["rows"][-1].update(expected_mode="none"),
            lambda d: d["rows"][-1].update(uncertain=1),
            lambda d: d["rows"][-1]["scores"].update(none=float("nan")),
        ):
            diagnostics = deepcopy(self.diagnostics)
            mutation(diagnostics)
            with self.subTest(mutation=mutation), self.assertRaises(dc.DependencyClassifierError):
                dc.apply_calibration_support_floor(self.artifact, diagnostics, diagnostics_sha256="b" * 64)
        adjusted = dc.apply_calibration_support_floor(self.artifact, self.diagnostics,
                                                    diagnostics_sha256="b" * 64)
        for mutation in (
            lambda d: d["calibration"]["support_floor"].update(extra=True),
            lambda d: d["calibration"]["support_floor"].update(diagnostics_sha256="bad"),
            lambda d: d["calibration"]["support_floor"].update(base_artifact_fingerprint="f" * 64),
            lambda d: d["calibration"]["support_floor"]["minimum_accepted_margins"].update(none=0),
            lambda d: d["calibration"]["per_mode"]["none"].update(threshold=0),
            lambda d: d["weights"][0].__setitem__(0, d["weights"][0][0] + 0.1),
        ):
            changed = deepcopy(adjusted)
            mutation(changed)
            with self.subTest(mutation=mutation), self.assertRaises(dc.DependencyClassifierError):
                dc.validate_artifact(seal(changed))

    def test_rejection_preserves_raw_mode_scores_and_fingerprint(self):
        document = deepcopy(self.artifact)
        calibration = document["calibration"]
        entry = calibration["per_mode"]["none"]
        entry.update(enabled=False, accepted=0)
        calibration.update(accepted=9, coverage=0.75)
        model = dc.DependencyClassifier.from_document(Embedder(), seal(document))
        result = model.classify("Please process cobalt.")
        self.assertEqual(result.mode, "clarify")
        self.assertEqual(result.predicted_mode, "none")
        self.assertTrue(result.uncertain)
        self.assertEqual(result.model_manifest["fingerprint"], document["fingerprint"])

    def test_group_overlap_duplicate_input_and_invalid_history_rejected(self):
        for mutation in (
            lambda rows: rows[-1].update(group=rows[0]["group"]),
            lambda rows: rows[-1].update(id=rows[0]["id"]),
            lambda rows: rows[-1].update(text=rows[0]["text"]),
            lambda rows: rows[-1].update(prior_turns=[{"role": "system", "content": "bad"}]),
            lambda rows: rows[-1].update(prior_turns=[{"role": "user", "content": "ok", "extra": 1}]),
            lambda rows: rows[-1].update(text=""),
            lambda rows: rows[-1].update(mode=True),
        ):
            document = corpus()
            mutation(document["cases"])
            with self.subTest(document=document["cases"][-1]), self.assertRaises(dc.DependencyClassifierError):
                dc.validate_corpus(document)
        document = corpus()
        document["cases"] = [row for row in document["cases"] if not (row["split"] == "calibration" and row["mode"] == "optional")]
        with self.assertRaises(dc.DependencyClassifierError):
            dc.validate_corpus(document)

    def test_artifact_rejects_tampering_and_structurally_invalid_resealed_data(self):
        mutations = (
            lambda doc: doc.update(extra=True),
            lambda doc: doc.update(schema_version="unknown"),
            lambda doc: doc["embedding"].update(model_revision="unknown"),
            lambda doc: doc["bias"].__setitem__(0, "0.2"),
            lambda doc: doc["weights"][0].__setitem__(0, True),
            lambda doc: doc["weights"].pop(),
            lambda doc: doc["idf"].__setitem__(0, 0.0),
            lambda doc: doc["vocabulary"].__setitem__(0, doc["vocabulary"][1]),
            lambda doc: doc["training"]["calibration_groups"].append(doc["training"]["train_groups"][0]),
            lambda doc: doc["training"]["class_counts"]["train"].update(none=100),
            lambda doc: doc["calibration"].update(accepted=True),
            lambda doc: doc["calibration"].update(coverage=0.2),
            lambda doc: doc["calibration"]["per_mode"]["none"].update(enabled="true"),
            lambda doc: doc["calibration"]["per_mode"]["none"].update(errors=1),
        )
        for mutation in mutations:
            document = deepcopy(self.artifact)
            mutation(document)
            with self.subTest(mutation=mutation), self.assertRaises(dc.DependencyClassifierError):
                dc.validate_artifact(seal(document))
        tampered = deepcopy(self.artifact)
        tampered["bias"][0] += 0.1
        with self.assertRaises(dc.DependencyClassifierError):
            dc.validate_artifact(tampered)

    def test_loader_rejects_duplicate_nonfinite_oversized_or_nonobject_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.json"
            for value in ('{"a":1,"a":2}', '{"value":NaN}', '[]', '{', '\ud800'):
                path.write_bytes(value.encode("utf-8", errors="surrogatepass"))
                with self.subTest(value=repr(value)), self.assertRaises(dc.DependencyClassifierError):
                    dc.DependencyClassifier(Embedder(), artifact_path=path)
            path.write_bytes(b" " * 21)
            with patch.object(dc, "MAX_ARTIFACT_BYTES", 20), self.assertRaises(dc.DependencyClassifierError):
                dc.DependencyClassifier(Embedder(), artifact_path=path)

    def test_invalid_provider_vectors_or_settings_fail_before_fit(self):
        provider = Embedder()
        provider.model_revision = "unpinned"
        with self.assertRaises(dc.DependencyClassifierError):
            dc.DependencyClassifier.from_document(provider, self.artifact)
        self.assertFalse(provider.calls)
        for vectors in (np.zeros((1, 384)), np.ones((1, 3)), np.full((1, 384), np.nan),
                        np.full((1, 384), "1"), np.full((1, 384), True)):
            with self.subTest(dtype=vectors.dtype), self.assertRaises(dc.DependencyClassifierError):
                dc._vectors(vectors, 1)
        for settings in ({"target_error_rate": -1}, {"batch_size": 17}, {"minimum_accepted": True},
                         {"regularization": float("nan")}, {"embedding_weight": 10 ** 1000}):
            provider = Embedder()
            with self.subTest(settings=settings), self.assertRaises(dc.DependencyClassifierError):
                dc.train_dependency_classifier(self.rows, provider, corpus_sha256="a" * 64, **settings)
            self.assertFalse(provider.calls)

    def test_calibration_excludes_margin_ties_together_and_disables_unsupported_modes(self):
        scores = [[0.1, 0, 0, 0], [0.1, 0, 0, 0], [0.4, 0, 0, 0], [0.5, 0, 0, 0], [0.6, 0, 0, 0]]
        result = dc.calibrate_margins(scores, [0, 1, 0, 0, 0])
        self.assertEqual(result["per_mode"]["none"]["accepted"], 3)
        self.assertGreater(result["per_mode"]["none"]["threshold"], 0.1)
        self.assertEqual(result["errors"], 0)
        self.assertFalse(result["per_mode"]["optional"]["enabled"])
        for labels in ([0.5] * 5, [True] * 5, [-1] * 5, [[0]] * 5):
            with self.subTest(labels=labels), self.assertRaises(dc.DependencyClassifierError):
                dc.calibrate_margins(scores, labels)


class DependencyTrainingRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "scripts/train_dependency_classifier.py"
        spec = importlib.util.spec_from_file_location("dependency_training_script", path)
        cls.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.script)

    def test_fresh_run_freezes_inputs_reports_diagnostics_and_never_installs(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "corpus.json", Path(tmp) / "run"
            source.write_text(json.dumps(corpus()), encoding="utf-8")
            with patch.object(self.script, "BgeOnnxEmbedder", return_value=Embedder()) as factory:
                status = self.script.main(["--corpus", str(source), "--output-dir", str(output), "--max-features", "128"])
            self.assertEqual(status, 0)
            self.assertEqual(factory.call_args.kwargs, {"intra_op_threads": 2})
            summary = json.loads((output / "summary.json").read_text())
            self.assertEqual(summary["status"], "complete")
            self.assertFalse(summary["installed"])
            self.assertEqual(summary["calibration"]["count"], 12)
            protocol = json.loads((output / "protocol.json").read_text())
            self.assertEqual(protocol["corpus_sha256"], sha256(source.read_bytes()).hexdigest())
            self.assertEqual((output / "corpus.json").read_bytes(), source.read_bytes())
            self.assertEqual(len(json.loads((output / "diagnostics.json").read_text())["rows"]), 28)
            before = (output / "classifier.json").read_bytes()
            with patch.object(self.script, "BgeOnnxEmbedder") as factory, self.assertRaises(FileExistsError):
                self.script.main(["--corpus", str(source), "--output-dir", str(output)])
            factory.assert_not_called()
            self.assertEqual(before, (output / "classifier.json").read_bytes())

    def test_embedder_failure_is_persisted_with_latency(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "corpus.json", Path(tmp) / "run"
            source.write_text(json.dumps(corpus()), encoding="utf-8")
            with patch.object(self.script, "BgeOnnxEmbedder", side_effect=RuntimeError("offline asset unavailable")):
                status = self.script.main(["--corpus", str(source), "--output-dir", str(output)])
            self.assertEqual(status, 1)
            summary = json.loads((output / "summary.json").read_text())
            self.assertEqual(summary["error"]["message"], "offline asset unavailable")
            self.assertGreaterEqual(summary["wall_seconds"], 0)
            self.assertFalse((output / "classifier.json").exists())

    def test_training_reloads_the_frozen_corpus_after_source_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "corpus.json", Path(tmp) / "run"
            original = corpus()
            changed = deepcopy(original)
            changed["cases"][0]["text"] += " changed before snapshot"
            source.write_text(json.dumps(original), encoding="utf-8")
            calls = []

            def load_and_mutate(path):
                rows = dc.load_corpus(path)
                calls.append(Path(path))
                if Path(path) == source:
                    source.write_text(json.dumps(changed), encoding="utf-8")
                return rows

            provider = Embedder()
            with patch.object(self.script, "load_corpus", side_effect=load_and_mutate), patch.object(self.script, "BgeOnnxEmbedder", return_value=provider):
                self.assertEqual(self.script.main(["--corpus", str(source), "--output-dir", str(output)]), 0)
            self.assertEqual(calls, [source, output / "corpus.json"])
            self.assertIn("changed before snapshot", provider.calls[0][0])
            artifact = json.loads((output / "classifier.json").read_text())
            self.assertEqual(artifact["training"]["corpus_sha256"], sha256(source.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
