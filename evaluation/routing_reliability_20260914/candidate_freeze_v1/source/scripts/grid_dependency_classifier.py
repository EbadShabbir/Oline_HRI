"""Six declared CPU-only classifier variants sharing one embedding pass.

Variant comparison uses authored held-group calibration rows. These rows fit
rejection thresholds and compare settings, so they are not release estimates.
This experiment does not install or automatically select any artifact.
"""

from __future__ import annotations

import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "2"

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np

from oline_hri.config import DEFAULT_CONFIG_PATH, load_config
from oline_hri.dependency_classifier import (
    INPUT_VERSION, MODES, _check_embedder, _embedding_identity, _vectors,
    encode_dependency_input, load_corpus, train_dependency_classifier,
)
from oline_hri.embedding import BgeOnnxEmbedder, EMBEDDING_DIMENSION, MODEL_ID, MODEL_REVISION
from oline_hri.ollama import ChatMessage


ROOT = Path(__file__).resolve().parents[1]
GRID = tuple({"regularization": regularization, "embedding_weight": weight, "lexical_weight": 1.0}
             for regularization in (0.1, 1.0, 10.0) for weight in (0.25, 1.0))


def write_new(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


class CachedEmbedder:
    """Exact-input cache with no fallback that could initiate extra inference."""

    model_id, model_revision, dimension = MODEL_ID, MODEL_REVISION, EMBEDDING_DIMENSION

    def __init__(self, vectors):
        self._vectors = vectors

    def embed_passages(self, passages):
        return np.vstack([self._vectors[text] for text in passages])


def cache_embeddings(cases, provider, *, batch_size=8, progress=None):
    _check_embedder(provider)
    documents = list(dict.fromkeys(encode_dependency_input(
        row["text"], tuple(ChatMessage(**turn) for turn in row["prior_turns"])) for row in cases))
    cached = {}
    for offset in range(0, len(documents), batch_size):
        batch = documents[offset:offset + batch_size]
        vectors = _vectors(provider.embed_passages(batch), len(batch))
        cached.update(zip(batch, vectors))
        if progress:
            progress(len(cached), len(documents))
    records = [{"input_sha256": sha256(text.encode("utf-8")).hexdigest(), "vector": vector.tolist()}
               for text, vector in cached.items()]
    return CachedEmbedder(cached), records


def calibration_summary(diagnostics):
    rows = [row for row in diagnostics["rows"] if row["split"] == "calibration"]
    confusion = {mode: dict(Counter(row["predicted_mode"] for row in rows if row["expected_mode"] == mode))
                 for mode in MODES}
    return {"calibration": diagnostics["calibration"], "raw_confusion": confusion,
            "effective_mode_correct": sum(row["mode"] == row["expected_mode"] for row in rows),
            "raw_errors": [{key: row[key] for key in ("id", "expected_mode", "predicted_mode", "mode", "margin", "uncertain")}
                           for row in rows if row["predicted_mode"] != row["expected_mode"]],
            "abstentions": [row["id"] for row in rows if row["uncertain"]]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, choices=range(1, 17), default=8)
    args = parser.parse_args(argv)
    directory = args.output_dir.absolute()
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    started, error, variants = perf_counter(), None, []
    try:
        with args.corpus.open("rb") as stream:
            corpus_bytes = stream.read(16 * 1024 * 1024 + 1)
        corpus_hash = sha256(corpus_bytes).hexdigest()
        with (directory / "corpus.json").open("xb") as stream:
            stream.write(corpus_bytes)
        cases = load_corpus(directory / "corpus.json")
        config = load_config()
        paths = [ROOT / "src/oline_hri" / (name + ".py") for name in ("dependency_classifier", "embedding")]
        paths += [Path(__file__).resolve(), DEFAULT_CONFIG_PATH]
        hashes = {}
        for path in paths:
            content = path.read_bytes()
            relative = path.relative_to(ROOT)
            target = directory / "source" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(content)
            hashes[str(relative)] = sha256(content).hexdigest()
        write_new(directory / "protocol.json", {
            "schema_version": "dependency_grid_run_v1", "created_at": datetime.now(timezone.utc).isoformat(),
            "grid": GRID, "corpus_sha256": corpus_hash, "source_sha256": hashes, "config": config.to_dict(),
            "intra_op_threads": 2, "openblas_threads": 1, "batch_size": args.batch_size,
            "target_error_rate": 0.0, "minimum_accepted": 3, "max_features": 4096,
            "scope": "Calibration is used for both margin fitting and model comparison; no release claim or automatic promotion.",
        })
        provider = BgeOnnxEmbedder(config.embedding.model_directory, intra_op_threads=2)
        cached, records = cache_embeddings(cases, provider, batch_size=args.batch_size,
                                          progress=lambda done, total: print(f"embedded {done}/{total}", flush=True))
        write_new(directory / "embedding_cache.json", {
            "schema_version": "dependency_embedding_cache_v1", "embedding": _embedding_identity(),
            "input_encoding": INPUT_VERSION, "corpus_sha256": corpus_hash, "records": records,
        })
        with (directory / "variants.jsonl").open("x", encoding="utf-8") as stream:
            for number, settings in enumerate(GRID, 1):
                variant_start = perf_counter()
                name, diagnostics = f"variant_{number:02d}", {}
                target = directory / name
                target.mkdir()
                artifact = train_dependency_classifier(cases, cached, corpus_sha256=corpus_hash,
                                                       diagnostics=diagnostics, batch_size=args.batch_size, **settings)
                write_new(target / "classifier.json", artifact)
                write_new(target / "diagnostics.json", diagnostics)
                record = {"name": name, "settings": settings, "fingerprint": artifact["fingerprint"],
                          "train_accuracy": artifact["training"]["train_accuracy"],
                          "wall_seconds": perf_counter() - variant_start, **calibration_summary(diagnostics)}
                stream.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                variants.append(record)
                print(json.dumps({"variant": name, "settings": settings,
                                  "raw_accuracy": record["calibration"]["raw_accuracy"],
                                  "accepted": record["calibration"]["accepted"],
                                  "count": record["calibration"]["count"]}), flush=True)
    except BaseException as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        write_new(directory / "summary.json", {
            "schema_version": "dependency_grid_run_v1", "status": "error" if error else "complete", "error": error,
            "wall_seconds": perf_counter() - started, "variants": variants, "installed": False, "selected": None,
        })
    if error:
        print(f"grid failed: {error['type']}: {error['message']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
