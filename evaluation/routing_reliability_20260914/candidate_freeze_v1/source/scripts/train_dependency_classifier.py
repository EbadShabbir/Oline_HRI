"""Fit the bounded local dependency classifier on an authored grouped corpus.

Uses only existing CPU BGE assets and numpy. This creates a fresh diagnostic
directory; it does not install/promote the artifact or access the personal DB.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from time import perf_counter

# Bound this process before importing numpy/ONNX. No shell or global setting is
# modified. ONNX receives its separate explicit two-thread CPU setting below.
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ.setdefault("OMP_NUM_THREADS", "2")

import numpy as np

from oline_hri.config import load_config
from oline_hri.dependency_classifier import load_corpus, train_dependency_classifier, validate_artifact
from oline_hri.embedding import BgeOnnxEmbedder


ROOT = Path(__file__).resolve().parents[1]


def write_new(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--regularization", type=float, default=1.0)
    parser.add_argument("--max-features", type=int, default=4096)
    parser.add_argument("--embedding-weight", type=float, default=1.0)
    parser.add_argument("--lexical-weight", type=float, default=1.0)
    parser.add_argument("--target-error-rate", type=float, default=0.0)
    parser.add_argument("--minimum-accepted", type=int, default=3)
    args = parser.parse_args(argv)
    cases = load_corpus(args.corpus)
    config = load_config()
    directory = args.output_dir.absolute()
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    corpus_bytes = args.corpus.read_bytes()
    corpus_hash = sha256(corpus_bytes).hexdigest()
    with (directory / "corpus.json").open("xb") as stream:
        stream.write(corpus_bytes)
    # Fit the exact bytes we fingerprinted and froze, even if the author's
    # source file changed between its initial validation and this snapshot.
    cases = load_corpus(directory / "corpus.json")
    source_paths = [ROOT / "src/oline_hri/dependency_classifier.py", ROOT / "src/oline_hri/embedding.py", Path(__file__).resolve()]
    (directory / "source").mkdir()
    source_hashes = {}
    for source in source_paths:
        data = source.read_bytes()
        (directory / "source" / source.name).write_bytes(data)
        source_hashes[str(source.relative_to(ROOT))] = sha256(data).hexdigest()
    settings = {key: getattr(args, key) for key in ("batch_size", "regularization", "max_features", "embedding_weight",
                                                  "lexical_weight", "target_error_rate", "minimum_accepted")}
    write_new(directory / "protocol.json", {
        "schema_version": "dependency_training_run_v1", "created_at": datetime.now(timezone.utc).isoformat(),
        "corpus_sha256": corpus_hash, "source_sha256": source_hashes, "settings": settings,
        "embedding": asdict(config.embedding), "intra_op_threads": 2,
        "python": sys.version, "numpy": np.__version__, "openblas_threads": 1,
        "scope": "Authored train/held-group calibration only; no independent release or speech accuracy claim.",
    })
    started, failure, artifact, diagnostics = perf_counter(), None, None, {}
    try:
        embedder = BgeOnnxEmbedder(config.embedding.model_directory, intra_op_threads=2)
        artifact = train_dependency_classifier(
            cases, embedder, corpus_sha256=corpus_hash,
            progress=lambda done, total: print(f"embedded {done}/{total}", flush=True),
            diagnostics=diagnostics, **settings,
        )
        validate_artifact(artifact)
        write_new(directory / "classifier.json", artifact)
        write_new(directory / "diagnostics.json", diagnostics)
    except BaseException as exc:
        failure = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        write_new(directory / "summary.json", {
            "schema_version": "dependency_training_run_v1", "status": "error" if failure else "complete",
            "error": failure, "wall_seconds": perf_counter() - started,
            "fingerprint": artifact["fingerprint"] if artifact is not None else None,
            "calibration": artifact["calibration"] if artifact is not None else None,
            "installed": False,
        })
    if failure:
        print(f"training failed: {failure['type']}: {failure['message']}", file=sys.stderr)
        return 1
    print(json.dumps({"artifact": str(directory / "classifier.json"), "calibration": artifact["calibration"]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
