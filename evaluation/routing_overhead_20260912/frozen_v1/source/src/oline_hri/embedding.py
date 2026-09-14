"""Offline BGE embeddings backed by the pinned official ONNX model."""

from __future__ import annotations

from hashlib import sha256
import hmac
from pathlib import Path
from threading import Lock
from typing import Any, Protocol, Sequence, runtime_checkable
import unicodedata

import numpy as np


MODEL_ID = "BAAI/bge-small-en-v1.5"
MODEL_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
EMBEDDING_DIMENSION = 384
MAX_LENGTH = 512
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

REQUIRED_ASSET_SHA256 = {
    "config.json": "094f8e891b932f2000c92cfc663bac4c62069f5d8af5b5278c4306aef3084750",
    "tokenizer.json": (
        "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66"
    ),
    "onnx/model.onnx": (
        "828e1496d7fabb79cfa4dcd84fa38625c0d3d21da474a00f08db0f559940cf35"
    ),
}

_EXPECTED_INPUTS = frozenset({"input_ids", "attention_mask", "token_type_ids"})
_EXPECTED_OUTPUT = "last_hidden_state"


class EmbeddingError(RuntimeError):
    """Raised when local embedding inference cannot produce a safe vector."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Interface implemented by local personal-memory embedding engines."""

    model_id: str
    model_revision: str
    dimension: int

    def embed_passages(self, passages: Sequence[str]) -> np.ndarray:
        """Embed passage text as a normalized ``(n, dimension)`` matrix."""

    def embed_query(self, query: str) -> np.ndarray:
        """Embed one retrieval query as a normalized ``(dimension,)`` vector."""


class BgeOnnxEmbedder:
    """CPU-only inference for a locally provisioned, pinned BGE model."""

    model_id = MODEL_ID
    model_revision = MODEL_REVISION
    dimension = EMBEDDING_DIMENSION

    def __init__(
        self,
        model_directory: str | Path,
        intra_op_threads: int = 2,
    ) -> None:
        if isinstance(intra_op_threads, bool) or not isinstance(
            intra_op_threads, int
        ) or not 1 <= intra_op_threads <= 64:
            raise ValueError("intra_op_threads must be an integer from 1 to 64")
        try:
            directory = Path(model_directory).expanduser()
        except (TypeError, ValueError, RuntimeError) as exc:
            raise EmbeddingError("embedding model directory is invalid") from exc

        self._model_directory = directory
        self._intra_op_threads = intra_op_threads
        self._tokenizer: Any = None
        self._session: Any = None
        self._load_lock = Lock()

    def embed_passages(self, passages: Sequence[str]) -> np.ndarray:
        """Embed passages without adding the retrieval-query instruction."""

        texts = _validated_texts(passages, field="passages")
        if not texts:
            return np.empty((0, EMBEDDING_DIMENSION), dtype=np.float32)
        return self._embed(texts)

    def embed_query(self, query: str) -> np.ndarray:
        """Embed one query with the exact BGE retrieval instruction."""

        text = _validated_text(query, field="query")
        return self._embed((f"{QUERY_PREFIX}{text}",))[0]

    def _embed(self, texts: tuple[str, ...]) -> np.ndarray:
        tokenizer, session = self._runtime()

        try:
            encodings = tokenizer.encode_batch(list(texts), add_special_tokens=True)
            input_ids = np.asarray(
                [encoding.ids for encoding in encodings], dtype=np.int64
            )
            attention_mask = np.asarray(
                [encoding.attention_mask for encoding in encodings], dtype=np.int64
            )
            token_type_ids = np.asarray(
                [encoding.type_ids for encoding in encodings], dtype=np.int64
            )
        except Exception as exc:
            raise EmbeddingError("embedding tokenization failed") from exc

        expected_shape = input_ids.shape
        if (
            input_ids.ndim != 2
            or input_ids.shape[0] != len(texts)
            or input_ids.shape[1] < 1
            or input_ids.shape[1] > MAX_LENGTH
            or attention_mask.shape != expected_shape
            or token_type_ids.shape != expected_shape
        ):
            raise EmbeddingError("embedding tokenizer returned malformed tensors")

        feeds = {
            "input_ids": np.ascontiguousarray(input_ids),
            "attention_mask": np.ascontiguousarray(attention_mask),
            "token_type_ids": np.ascontiguousarray(token_type_ids),
        }
        try:
            outputs = session.run([_EXPECTED_OUTPUT], feeds)
        except Exception as exc:
            raise EmbeddingError("embedding inference failed") from exc
        if not isinstance(outputs, (list, tuple)) or len(outputs) != 1:
            raise EmbeddingError("embedding model returned malformed output")

        try:
            hidden_state = np.asarray(outputs[0])
        except Exception as exc:
            raise EmbeddingError("embedding model returned malformed output") from exc
        if (
            hidden_state.ndim != 3
            or hidden_state.shape[0] != len(texts)
            or hidden_state.shape[1] != input_ids.shape[1]
            or hidden_state.shape[2] != EMBEDDING_DIMENSION
        ):
            raise EmbeddingError("embedding model returned an unexpected shape")

        try:
            vectors = np.asarray(hidden_state[:, 0, :], dtype=np.float32)
        except (TypeError, ValueError, OverflowError) as exc:
            raise EmbeddingError("embedding model returned malformed values") from exc
        if not np.all(np.isfinite(vectors)):
            raise EmbeddingError("embedding model returned non-finite values")

        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if not np.all(np.isfinite(norms)) or np.any(norms <= 0.0):
            raise EmbeddingError("embedding model returned a zero-length vector")
        normalized = np.ascontiguousarray(vectors / norms, dtype=np.float32)
        if (
            normalized.shape != (len(texts), EMBEDDING_DIMENSION)
            or not np.all(np.isfinite(normalized))
        ):
            raise EmbeddingError("embedding normalization failed")
        normalized_norms = np.linalg.norm(normalized, axis=1)
        if not np.allclose(normalized_norms, 1.0, rtol=1e-5, atol=1e-6):
            raise EmbeddingError("embedding normalization failed")
        return normalized

    def _runtime(self) -> tuple[Any, Any]:
        if self._tokenizer is not None and self._session is not None:
            return self._tokenizer, self._session

        with self._load_lock:
            if self._tokenizer is not None and self._session is not None:
                return self._tokenizer, self._session

            # Model files are authenticated before importing or initializing a
            # tokenizer or inference runtime. Loading never consults a hub.
            self._verify_assets()
            try:
                import onnxruntime as ort
                from tokenizers import Tokenizer
            except (ImportError, OSError) as exc:
                raise EmbeddingError(
                    "local embedding runtime dependencies are unavailable"
                ) from exc

            # Suppress provider-discovery warnings from unavailable accelerators;
            # this implementation deliberately creates a CPU-only session.
            ort.set_default_logger_severity(3)

            try:
                tokenizer = Tokenizer.from_file(
                    str(self._model_directory / "tokenizer.json")
                )
                tokenizer.enable_truncation(max_length=MAX_LENGTH)
                tokenizer.enable_padding(
                    direction="right",
                    pad_id=0,
                    pad_type_id=0,
                    pad_token="[PAD]",
                )
            except Exception as exc:
                raise EmbeddingError(
                    "local embedding tokenizer could not be loaded"
                ) from exc

            try:
                available_providers = tuple(ort.get_available_providers())
                if "CPUExecutionProvider" not in available_providers:
                    raise EmbeddingError(
                        "ONNX Runtime CPU execution provider is unavailable"
                    )
                session_options = ort.SessionOptions()
                session_options.intra_op_num_threads = self._intra_op_threads
                session_options.inter_op_num_threads = 1
                session_options.log_severity_level = 3
                session = ort.InferenceSession(
                    str(self._model_directory / "onnx" / "model.onnx"),
                    sess_options=session_options,
                    providers=["CPUExecutionProvider"],
                )
            except EmbeddingError:
                raise
            except Exception as exc:
                raise EmbeddingError(
                    "local embedding ONNX model could not be loaded"
                ) from exc

            try:
                providers = tuple(session.get_providers())
                input_names = frozenset(item.name for item in session.get_inputs())
                output_names = frozenset(item.name for item in session.get_outputs())
            except Exception as exc:
                raise EmbeddingError("embedding model metadata is unavailable") from exc
            if providers != ("CPUExecutionProvider",):
                raise EmbeddingError("embedding model must use only the CPU provider")
            if input_names != _EXPECTED_INPUTS:
                raise EmbeddingError(
                    "embedding model has an unsupported input signature"
                )
            if _EXPECTED_OUTPUT not in output_names:
                raise EmbeddingError(
                    "embedding model has an unsupported output signature"
                )

            self._tokenizer = tokenizer
            self._session = session
            return tokenizer, session

    def _verify_assets(self) -> None:
        for relative_path, expected_hash in REQUIRED_ASSET_SHA256.items():
            path = self._model_directory.joinpath(*relative_path.split("/"))
            try:
                if not path.is_file():
                    raise OSError("not a regular file")
                digest = _sha256_file(path)
            except OSError as exc:
                raise EmbeddingError(
                    "required embedding asset is missing or unreadable: "
                    f"{relative_path}"
                ) from exc
            if not hmac.compare_digest(digest, expected_hash):
                raise EmbeddingError(
                    f"embedding asset failed integrity verification: {relative_path}"
                )


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validated_texts(value: Sequence[str], *, field: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise EmbeddingError(f"{field} must be a sequence of strings")
    return tuple(
        _validated_text(text, field=f"{field} item")
        for text in value
    )


def _validated_text(value: str, *, field: str) -> str:
    if not isinstance(value, str):
        raise EmbeddingError(f"{field} must be a string")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized:
        raise EmbeddingError(f"{field} cannot be empty")
    if any(unicodedata.category(character) == "Cc" for character in normalized):
        raise EmbeddingError(f"{field} cannot contain control characters")
    return normalized
