from hashlib import sha256
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from oline_hri.embedding import (
    EMBEDDING_DIMENSION,
    MAX_LENGTH,
    MODEL_ID,
    MODEL_REVISION,
    QUERY_PREFIX,
    REQUIRED_ASSET_SHA256,
    BgeOnnxEmbedder,
    EmbeddingError,
    EmbeddingProvider,
)


class FakeEncoding:
    def __init__(self, values: list[int]) -> None:
        self.ids = values
        self.attention_mask = [1 if value else 0 for value in values]
        self.type_ids = [0] * len(values)


class FakeTokenizer:
    loaded_path = None
    instance = None

    def __init__(self) -> None:
        self.encoded_batches = []
        self.truncation = None
        self.padding = None

    @classmethod
    def from_file(cls, path):
        cls.loaded_path = path
        cls.instance = cls()
        return cls.instance

    def enable_truncation(self, **arguments):
        self.truncation = arguments

    def enable_padding(self, **arguments):
        self.padding = arguments

    def encode_batch(self, texts, *, add_special_tokens):
        self.encoded_batches.append((tuple(texts), add_special_tokens))
        return [FakeEncoding([101, index + 1, 102]) for index, _ in enumerate(texts)]


class FakeSession:
    def __init__(self, output=None, *, inputs=None, providers=None) -> None:
        self.output = output
        self.input_names = inputs or (
            "input_ids",
            "attention_mask",
            "token_type_ids",
        )
        self.providers = providers or ("CPUExecutionProvider",)
        self.output_names = ("last_hidden_state",)
        self.run_calls = []

    def get_providers(self):
        return list(self.providers)

    def get_inputs(self):
        return [SimpleNamespace(name=name) for name in self.input_names]

    def get_outputs(self):
        return [SimpleNamespace(name=name) for name in self.output_names]

    def run(self, output_names, feeds):
        self.run_calls.append((output_names, feeds))
        if self.output is not None:
            return [self.output]
        count, length = feeds["input_ids"].shape
        hidden = np.zeros((count, length, EMBEDDING_DIMENSION), dtype=np.float32)
        for index in range(count):
            hidden[index, 0, 0] = 3.0
            hidden[index, 0, 1] = 4.0 + index
            # Non-CLS token values must have no effect on sentence pooling.
            hidden[index, 1:, 2] = 1000.0
        return [hidden]


class FakeOrtFactory:
    def __init__(self, session: FakeSession, *, available=None) -> None:
        self.session = session
        self.available = available or ("CUDAExecutionProvider", "CPUExecutionProvider")
        self.calls = []
        self.logger_severities = []
        factory = self

        class SessionOptions:
            def __init__(self) -> None:
                self.intra_op_num_threads = None
                self.inter_op_num_threads = None
                self.log_severity_level = None

        self.SessionOptions = SessionOptions

    def get_available_providers(self):
        return list(self.available)

    def set_default_logger_severity(self, severity):
        self.logger_severities.append(severity)

    def InferenceSession(self, path, *, sess_options, providers):
        self.calls.append((path, sess_options, providers))
        return self.session


class EmbeddingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.model_directory = Path(self.temporary_directory.name)
        files = {
            "config.json": b"fake config",
            "tokenizer.json": b"fake tokenizer",
            "onnx/model.onnx": b"fake model",
        }
        self.hashes = {}
        for relative_path, body in files.items():
            path = self.model_directory / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            self.hashes[relative_path] = sha256(body).hexdigest()

    def runtime(self, session=None, *, available=None):
        fake_session = session or FakeSession()
        ort_factory = FakeOrtFactory(fake_session, available=available)
        ort_module = ModuleType("onnxruntime")
        ort_module.get_available_providers = ort_factory.get_available_providers
        ort_module.set_default_logger_severity = (
            ort_factory.set_default_logger_severity
        )
        ort_module.SessionOptions = ort_factory.SessionOptions
        ort_module.InferenceSession = ort_factory.InferenceSession
        tokenizers_module = ModuleType("tokenizers")
        tokenizers_module.Tokenizer = FakeTokenizer
        return fake_session, ort_factory, {
            "onnxruntime": ort_module,
            "tokenizers": tokenizers_module,
        }

    def embedder_with_runtime(self, session=None, *, available=None, threads=2):
        fake_session, ort_factory, modules = self.runtime(
            session, available=available
        )
        embedder = BgeOnnxEmbedder(self.model_directory, threads)
        patches = (
            patch.dict(REQUIRED_ASSET_SHA256, self.hashes, clear=True),
            patch.dict(sys.modules, modules),
        )
        return embedder, fake_session, ort_factory, patches

    def test_contract_constants_and_protocol(self) -> None:
        self.assertEqual(MODEL_ID, "BAAI/bge-small-en-v1.5")
        self.assertEqual(
            MODEL_REVISION, "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
        )
        self.assertEqual(EMBEDDING_DIMENSION, 384)
        self.assertEqual(MAX_LENGTH, 512)
        self.assertEqual(
            QUERY_PREFIX,
            "Represent this sentence for searching relevant passages: ",
        )
        self.assertEqual(
            REQUIRED_ASSET_SHA256,
            {
                "config.json": (
                    "094f8e891b932f2000c92cfc663bac4c62069f5d8af5b5278c4306aef3084750"
                ),
                "tokenizer.json": (
                    "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66"
                ),
                "onnx/model.onnx": (
                    "828e1496d7fabb79cfa4dcd84fa38625c0d3d21da474a00f08db0f559940cf35"
                ),
            },
        )
        self.assertIsInstance(BgeOnnxEmbedder(self.model_directory), EmbeddingProvider)

    def test_empty_passages_do_not_load_runtime(self) -> None:
        embedder = BgeOnnxEmbedder(Path(self.temporary_directory.name) / "missing")

        result = embedder.embed_passages([])

        self.assertEqual(result.shape, (0, EMBEDDING_DIMENSION))
        self.assertEqual(result.dtype, np.float32)

    def test_passages_use_cls_pooling_normalize_and_force_cpu(self) -> None:
        embedder, session, ort_factory, patches = self.embedder_with_runtime(threads=3)
        with patches[0], patches[1]:
            result = embedder.embed_passages(["first passage", "second passage"])

        self.assertEqual(result.shape, (2, EMBEDDING_DIMENSION))
        self.assertEqual(result.dtype, np.float32)
        np.testing.assert_allclose(np.linalg.norm(result, axis=1), [1.0, 1.0])
        np.testing.assert_allclose(result[0, :3], [0.6, 0.8, 0.0])
        self.assertEqual(FakeTokenizer.instance.truncation, {"max_length": MAX_LENGTH})
        self.assertEqual(FakeTokenizer.instance.padding["direction"], "right")
        self.assertEqual(FakeTokenizer.instance.encoded_batches[0][0], (
            "first passage",
            "second passage",
        ))
        self.assertEqual(ort_factory.calls[0][2], ["CPUExecutionProvider"])
        self.assertEqual(ort_factory.logger_severities, [3])
        self.assertEqual(ort_factory.calls[0][1].intra_op_num_threads, 3)
        self.assertEqual(ort_factory.calls[0][1].inter_op_num_threads, 1)
        self.assertEqual(ort_factory.calls[0][1].log_severity_level, 3)
        output_names, feeds = session.run_calls[0]
        self.assertEqual(output_names, ["last_hidden_state"])
        self.assertEqual(set(feeds), {
            "input_ids",
            "attention_mask",
            "token_type_ids",
        })
        for value in feeds.values():
            self.assertEqual(value.dtype, np.int64)
            self.assertTrue(value.flags.c_contiguous)

    def test_query_prefix_is_applied_only_to_query(self) -> None:
        embedder, _, _, patches = self.embedder_with_runtime()
        with patches[0], patches[1]:
            query_vector = embedder.embed_query("  mint tea  ")
            embedder.embed_passages(["mint tea"])

        batches = FakeTokenizer.instance.encoded_batches
        self.assertEqual(batches[0][0], (QUERY_PREFIX + "mint tea",))
        self.assertEqual(batches[1][0], ("mint tea",))
        self.assertEqual(query_vector.shape, (EMBEDDING_DIMENSION,))

    def test_runtime_is_loaded_only_once(self) -> None:
        embedder, _, ort_factory, patches = self.embedder_with_runtime()
        with patches[0], patches[1]:
            embedder.embed_query("one")
            embedder.embed_query("two")

        self.assertEqual(len(ort_factory.calls), 1)

    def test_missing_and_hash_mismatch_are_sanitized(self) -> None:
        missing = BgeOnnxEmbedder(self.model_directory / "absent")
        with self.assertRaisesRegex(EmbeddingError, "config.json") as missing_error:
            missing.embed_query("private missing text")
        self.assertNotIn("private missing text", str(missing_error.exception))

        corrupted = BgeOnnxEmbedder(self.model_directory)
        with self.assertRaisesRegex(EmbeddingError, "config.json") as hash_error:
            corrupted.embed_query("private corrupted text")
        self.assertNotIn("private corrupted text", str(hash_error.exception))

    def test_cpu_provider_is_required_and_is_the_only_active_provider(self) -> None:
        embedder, _, _, patches = self.embedder_with_runtime(
            available=("CUDAExecutionProvider",)
        )
        with patches[0], patches[1]:
            with self.assertRaisesRegex(EmbeddingError, "CPU execution provider"):
                embedder.embed_query("query")

        session = FakeSession(
            providers=("CPUExecutionProvider", "CUDAExecutionProvider")
        )
        embedder, _, _, patches = self.embedder_with_runtime(session)
        with patches[0], patches[1]:
            with self.assertRaisesRegex(EmbeddingError, "only the CPU provider"):
                embedder.embed_query("query")

    def test_unsupported_model_input_signature_is_rejected(self) -> None:
        session = FakeSession(inputs=("input_ids", "attention_mask"))
        embedder, _, _, patches = self.embedder_with_runtime(session)
        with patches[0], patches[1]:
            with self.assertRaisesRegex(EmbeddingError, "input signature"):
                embedder.embed_query("query")

    def test_malformed_nonfinite_and_zero_outputs_are_rejected(self) -> None:
        malformed_outputs = {
            "wrong shape": np.zeros((1, EMBEDDING_DIMENSION), dtype=np.float32),
            "wrong sequence": np.zeros(
                (1, 2, EMBEDDING_DIMENSION), dtype=np.float32
            ),
            "wrong dimension": np.zeros((1, 3, 8), dtype=np.float32),
            "non-finite": np.full(
                (1, 3, EMBEDDING_DIMENSION), np.nan, dtype=np.float32
            ),
            "zero": np.zeros((1, 3, EMBEDDING_DIMENSION), dtype=np.float32),
        }
        for label, output in malformed_outputs.items():
            with self.subTest(label=label):
                embedder, _, _, patches = self.embedder_with_runtime(
                    FakeSession(output=output)
                )
                with patches[0], patches[1]:
                    with self.assertRaises(EmbeddingError):
                        embedder.embed_query("private malformed text")

    def test_input_validation_does_not_echo_text(self) -> None:
        embedder = BgeOnnxEmbedder(self.model_directory)
        invalid = "private\nsecret"
        with self.assertRaises(EmbeddingError) as error:
            embedder.embed_query(invalid)
        self.assertNotIn("private", str(error.exception))
        with self.assertRaises(EmbeddingError):
            embedder.embed_passages("not a sequence of passages")
        with self.assertRaises(EmbeddingError):
            embedder.embed_passages([""])

    def test_invalid_thread_count_is_rejected(self) -> None:
        for value in (0, -1, 65, True, 1.5):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    BgeOnnxEmbedder(self.model_directory, value)


if __name__ == "__main__":
    unittest.main()
