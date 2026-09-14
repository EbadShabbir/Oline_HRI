"""Local supervised dependency classification using frozen embeddings.

The four scores are regularized regression scores, not probabilities. Margin
thresholds describe a finite, group-held calibration split; they cannot prove
correctness on new conversation. A prediction never authorizes personal facts.
Only current text and supplied safe task history enter learned features.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
import unicodedata

import numpy as np

from .embedding import EMBEDDING_DIMENSION, MODEL_ID, MODEL_REVISION, REQUIRED_ASSET_SHA256
from .ollama import ChatMessage
from .routing import RoutingError, _bounded_history, _user_text


MODES = ("none", "optional", "required", "clarify")
ARTIFACT_VERSION = "dependency_classifier_v1"
CORPUS_VERSION = "dependency_corpus_v1"
ALGORITHM = "balanced_dual_ridge_v1"
FEATURE_VERSION = "word123_char345_tfidf_v1"
INPUT_VERSION = "current_first_flat_history_v1"
DEFAULT_CLASSIFIER_PATH = Path(__file__).with_name("dependency_classifier_v1.json")
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
MAX_CORPUS_CASES = 2048
MAX_VOCABULARY = 4096
MAX_FEATURE_LENGTH = 100
_WORD = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*", re.UNICODE)
_SHA = re.compile(r"[0-9a-f]{64}")
_ARTIFACT_FIELDS = {"schema_version", "algorithm", "classes", "embedding", "feature_config",
                    "vocabulary", "idf", "weights", "bias", "calibration", "training", "fingerprint"}


class DependencyClassifierError(ValueError):
    """A corpus, local model artifact, or embedding result was invalid."""


@dataclass(frozen=True)
class DependencyPrediction:
    mode: str
    predicted_mode: str
    scores: dict[str, float]
    margin: float
    threshold: float
    uncertain: bool
    general_request: str
    model_manifest: dict[str, Any]


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return sha256(_canonical(value)).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DependencyClassifierError("duplicate JSON field")
        result[key] = value
    return result


def _load_json(path: Path, *, limit: int) -> dict:
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise DependencyClassifierError("JSON artifact exceeds size limit")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               DependencyClassifierError("non-finite JSON value")))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise DependencyClassifierError("invalid JSON artifact") from exc
    if not isinstance(value, dict):
        raise DependencyClassifierError("JSON artifact must be an object")
    return value


def _number(value, *, minimum=0.0, maximum=1_000_000.0) -> float:
    if type(value) not in {int, float} or not minimum <= value <= maximum or not math.isfinite(value):
        raise DependencyClassifierError("numeric model metadata is outside its bounds")
    return float(value)


def _integer(value, *, minimum=0, maximum=MAX_CORPUS_CASES) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise DependencyClassifierError("integer model metadata is outside its bounds")
    return value


def _label(value) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        raise DependencyClassifierError("invalid corpus identifier")
    return value


def encode_dependency_input(text: str, history: Sequence[ChatMessage] = ()) -> str:
    """One versioned input format shared by training and classification."""
    try:
        current = _user_text(text)
        prior = _bounded_history(history)
    except RoutingError as exc:
        raise DependencyClassifierError(str(exc)) from exc
    def flat(value):
        normalized = " ".join(value.split())
        if any(unicodedata.category(character) == "Cc" for character in normalized):
            raise DependencyClassifierError("dependency input contains control characters")
        return normalized
    return "Current request: " + flat(current) + "".join(
        " | Previous " + message.role + ": " + flat(message.content) for message in prior)


def validate_corpus(document: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    if not isinstance(document, Mapping) or document.get("schema_version") != CORPUS_VERSION:
        raise DependencyClassifierError("unsupported dependency corpus version")
    cases = document.get("cases")
    if not isinstance(cases, list) or not 8 <= len(cases) <= MAX_CORPUS_CASES:
        raise DependencyClassifierError("corpus size is outside its bounds")
    ids, groups, inputs = set(), {}, {}
    distributions = {split: Counter() for split in ("train", "calibration")}
    for case in cases:
        if not isinstance(case, dict) or not {"id", "group", "split", "text", "prior_turns", "mode"} <= set(case):
            raise DependencyClassifierError("corpus case is missing required fields")
        identifier, group = _label(case["id"]), _label(case["group"])
        split, mode = case["split"], case["mode"]
        if type(split) is not str or split not in distributions or type(mode) is not str or mode not in MODES:
            raise DependencyClassifierError("corpus contains an unsupported split or mode")
        if identifier in ids or group in groups and groups[group] != split:
            raise DependencyClassifierError("duplicate case or group crosses training/calibration")
        ids.add(identifier)
        groups[group] = split
        history = case["prior_turns"]
        if not isinstance(history, list):
            raise DependencyClassifierError("prior_turns must be a list")
        try:
            if any(not isinstance(item, dict) or set(item) != {"role", "content"} for item in history):
                raise DependencyClassifierError("malformed prior turn")
            encoded = encode_dependency_input(case["text"], tuple(ChatMessage(**item) for item in history))
        except (ValueError, TypeError, RuntimeError) as exc:
            raise DependencyClassifierError("invalid corpus text or history") from exc
        key = unicodedata.normalize("NFKC", encoded).casefold()
        if key in inputs and inputs[key] != (split, mode):
            raise DependencyClassifierError("duplicate input leaks across splits or contradicts labels")
        inputs[key] = (split, mode)
        distributions[split][mode] += 1
    if any(set(counts) != set(MODES) for counts in distributions.values()):
        raise DependencyClassifierError("training and calibration must both cover all four modes")
    # All other author metadata remains audit material, never a feature input.
    return tuple(deepcopy(cases))


def load_corpus(path: str | Path) -> tuple[dict[str, Any], ...]:
    return validate_corpus(_load_json(Path(path), limit=16 * 1024 * 1024))


def _documents(cases) -> list[str]:
    return [encode_dependency_input(case["text"], tuple(ChatMessage(**item) for item in case["prior_turns"]))
            for case in cases]


def _counts(text: str) -> Counter:
    normalized = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    words = _WORD.findall(normalized)
    features = Counter()
    for width in (1, 2, 3):
        for index in range(len(words) - width + 1):
            feature = f"w{width}:" + " ".join(words[index:index + width])
            if len(feature) <= MAX_FEATURE_LENGTH:
                features[feature] += 1
    for width in (3, 4, 5):
        for index in range(len(normalized) - width + 1):
            features[f"c{width}:" + normalized[index:index + width]] += 1
    return features


def _vocabulary(counts, max_features):
    frequency = Counter(feature for row in counts for feature in row)
    vocabulary = sorted((feature for feature, count in frequency.items() if count >= 2),
                        key=lambda feature: (-frequency[feature], feature))[:max_features]
    if not vocabulary:
        raise DependencyClassifierError("training inputs have no shared learned features")
    idf = np.asarray([math.log((1 + len(counts)) / (1 + frequency[feature])) + 1 for feature in vocabulary])
    return vocabulary, idf


def _lexical_matrix(counts, vocabulary, idf):
    indices = {feature: index for index, feature in enumerate(vocabulary)}
    result = np.zeros((len(counts), len(vocabulary)), dtype=np.float64)
    for row, features in enumerate(counts):
        for feature, count in features.items():
            column = indices.get(feature)
            if column is not None:
                result[row, column] = (1 + math.log(count)) * (0.35 if feature.startswith("c") else 1.0)
    result *= idf
    norms = np.linalg.norm(result, axis=1, keepdims=True)
    return result / np.maximum(norms, 1e-12)


def _embedding_identity():
    return {"model_id": MODEL_ID, "model_revision": MODEL_REVISION, "dimension": EMBEDDING_DIMENSION,
            "asset_sha256": dict(REQUIRED_ASSET_SHA256)}


def _check_embedder(embedder):
    if any(getattr(embedder, name, None) != value for name, value in
           (("model_id", MODEL_ID), ("model_revision", MODEL_REVISION), ("dimension", EMBEDDING_DIMENSION))):
        raise DependencyClassifierError("embedding provider does not match the pinned model")


def _vectors(value, count):
    try:
        raw = np.asarray(value)
        if raw.dtype.kind not in "ifu":
            raise DependencyClassifierError("embedding vectors must contain real numbers")
        result = np.asarray(value, dtype=np.float64)
    except (ValueError, TypeError, OverflowError) as exc:
        raise DependencyClassifierError("malformed embedding vectors") from exc
    if result.shape != (count, EMBEDDING_DIMENSION) or not np.isfinite(result).all():
        raise DependencyClassifierError("invalid embedding vector shape or values")
    norms = np.linalg.norm(result, axis=1, keepdims=True)
    if not np.allclose(norms, 1.0, atol=1e-4, rtol=1e-4):
        raise DependencyClassifierError("embedding vectors must be unit normalized")
    return result / norms


def _ridge(features, labels, regularization):
    targets = np.eye(len(MODES), dtype=np.float64)[labels]
    counts = np.bincount(labels, minlength=len(MODES))
    sample_weights = len(labels) / (len(MODES) * counts[labels])
    mean_x = np.average(features, axis=0, weights=sample_weights)
    mean_y = np.average(targets, axis=0, weights=sample_weights)
    root_weights = np.sqrt(sample_weights)[:, None]
    centered_x, centered_y = (features - mean_x) * root_weights, (targets - mean_y) * root_weights
    gram = centered_x @ centered_x.T
    gram.flat[::len(gram) + 1] += regularization
    weights = centered_x.T @ np.linalg.solve(gram, centered_y)
    return weights, mean_y - mean_x @ weights


def calibrate_margins(scores, labels, *, target_error_rate=0.0, minimum_accepted=3):
    """Fit empirical rejection thresholds on held groups, not probabilities."""
    target_error_rate = _number(target_error_rate, maximum=0.25)
    minimum_accepted = _integer(minimum_accepted, minimum=1)
    try:
        raw_scores, raw_labels = np.asarray(scores), np.asarray(labels)
        if raw_scores.dtype.kind not in "ifu" or raw_labels.dtype.kind not in "iu" or raw_labels.ndim != 1:
            raise DependencyClassifierError("calibration requires real scores and integer labels")
        scores = np.asarray(scores, dtype=np.float64)
        labels = np.asarray(labels, dtype=np.int64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise DependencyClassifierError("malformed calibration arrays") from exc
    if scores.shape != (len(labels), len(MODES)) or not len(labels) or not np.isfinite(scores).all():
        raise DependencyClassifierError("invalid calibration scores")
    if np.any(labels < 0) or np.any(labels >= len(MODES)):
        raise DependencyClassifierError("invalid calibration labels")
    predicted = np.argmax(scores, axis=1)
    ordered = np.sort(scores, axis=1)
    margins = ordered[:, -1] - ordered[:, -2]
    per_mode, accepted_total, errors_total = {}, 0, 0
    for index, mode in enumerate(MODES):
        mask = predicted == index
        values, correct = margins[mask], labels[mask] == index
        found = {"enabled": False, "threshold": 0.0, "accepted": 0, "errors": 0, "available": int(mask.sum())}
        # Include tied scores together; moving just above a margin excludes
        # every case at that margin rather than selecting a favorable ordering.
        for threshold in [0.0, *[float(np.nextafter(value, np.inf)) for value in np.unique(values)]]:
            accepted = values >= threshold
            count, errors = int(accepted.sum()), int((~correct[accepted]).sum())
            if count >= minimum_accepted and errors / count <= target_error_rate:
                found.update(enabled=True, threshold=threshold, accepted=count, errors=errors)
                break
        per_mode[mode] = found
        accepted_total += found["accepted"]
        errors_total += found["errors"]
    return {"method": "held_group_top_two_margin_v1", "target_error_rate": target_error_rate,
            "minimum_accepted": minimum_accepted, "count": len(labels), "accepted": accepted_total,
            "errors": errors_total, "raw_accuracy": float(np.mean(predicted == labels)),
            "coverage": accepted_total / len(labels), "per_mode": per_mode,
            "scope": "Finite held-group empirical calibration; not probabilities or a universal error guarantee."}


def train_dependency_classifier(cases, embedder, *, corpus_sha256: str,
                               regularization=1.0, max_features=MAX_VOCABULARY,
                               embedding_weight=1.0, lexical_weight=1.0,
                               target_error_rate=0.0, minimum_accepted=3, batch_size=4,
                               progress=None, diagnostics: dict | None = None) -> dict[str, Any]:
    """Fit on train rows only, then calibrate on separate author groups."""
    cases = validate_corpus({"schema_version": CORPUS_VERSION, "cases": list(cases)})
    if not isinstance(corpus_sha256, str) or not _SHA.fullmatch(corpus_sha256):
        raise DependencyClassifierError("corpus fingerprint must be SHA-256")
    _check_embedder(embedder)
    regularization = _number(regularization, minimum=1e-6, maximum=1000)
    max_features = _integer(max_features, minimum=1, maximum=MAX_VOCABULARY)
    embedding_weight = _number(embedding_weight, minimum=0.01, maximum=10)
    lexical_weight = _number(lexical_weight, minimum=0.01, maximum=10)
    batch_size = _integer(batch_size, minimum=1, maximum=16)
    target_error_rate = _number(target_error_rate, maximum=0.25)
    minimum_accepted = _integer(minimum_accepted, minimum=1)
    documents = _documents(cases)
    vectors = []
    for offset in range(0, len(documents), batch_size):
        batch = documents[offset:offset + batch_size]
        vectors.append(_vectors(embedder.embed_passages(batch), len(batch)))
        if progress is not None:
            progress(min(offset + batch_size, len(documents)), len(documents))
    embeddings = np.vstack(vectors)
    counts = [_counts(document) for document in documents]
    train = np.asarray([case["split"] == "train" for case in cases])
    labels = np.asarray([MODES.index(case["mode"]) for case in cases])
    vocabulary, idf = _vocabulary([count for count, chosen in zip(counts, train) if chosen], max_features)
    lexical = _lexical_matrix(counts, vocabulary, idf)
    features = np.hstack((embeddings * embedding_weight, lexical * lexical_weight))
    weights, bias = _ridge(features[train], labels[train], regularization)
    scores = features @ weights + bias
    training_rows = [case for case in cases if case["split"] == "train"]
    calibration_rows = [case for case in cases if case["split"] == "calibration"]
    training = {
        "corpus_sha256": corpus_sha256, "train_count": len(training_rows), "calibration_count": len(calibration_rows),
        "training_case_ids_sha256": _digest([case["id"] for case in training_rows]),
        "calibration_case_ids_sha256": _digest([case["id"] for case in calibration_rows]),
        "train_groups": sorted({case["group"] for case in training_rows}),
        "calibration_groups": sorted({case["group"] for case in calibration_rows}),
        "class_counts": {split: dict(Counter(case["mode"] for case in cases if case["split"] == split))
                         for split in ("train", "calibration")},
        "regularization": regularization, "train_accuracy": float(np.mean(np.argmax(scores[train], axis=1) == labels[train])),
        "source_sha256": {Path(__file__).name: sha256(Path(__file__).read_bytes()).hexdigest()},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    artifact = {
        "schema_version": ARTIFACT_VERSION, "algorithm": ALGORITHM, "classes": list(MODES),
        "embedding": _embedding_identity(),
        "feature_config": {"version": FEATURE_VERSION, "input_encoding": INPUT_VERSION,
                           "max_features": max_features, "embedding_weight": embedding_weight, "lexical_weight": lexical_weight},
        "vocabulary": vocabulary, "idf": idf.tolist(), "weights": weights.tolist(), "bias": bias.tolist(),
        "calibration": calibrate_margins(scores[~train], labels[~train], target_error_rate=target_error_rate,
                                         minimum_accepted=minimum_accepted),
        "training": training,
    }
    artifact["fingerprint"] = _digest(artifact)
    validate_artifact(artifact)
    if diagnostics is not None:
        rows = []
        for case, values in zip(cases, scores):
            predicted = MODES[int(np.argmax(values))]
            ordered = np.sort(values)
            margin = float(ordered[-1] - ordered[-2])
            entry = artifact["calibration"]["per_mode"][predicted]
            uncertain = not entry["enabled"] or margin < entry["threshold"]
            rows.append({"id": case["id"], "group": case["group"], "split": case["split"],
                         "expected_mode": case["mode"], "predicted_mode": predicted,
                         "mode": "clarify" if uncertain else predicted, "uncertain": uncertain,
                         "margin": margin, "threshold": entry["threshold"],
                         "scores": dict(zip(MODES, map(float, values)))})
        diagnostics.update(training=deepcopy(training), calibration=deepcopy(artifact["calibration"]), rows=rows)
    return artifact


def validate_artifact(artifact: Mapping[str, Any]) -> None:
    """Reject executable formats, incompatible embeddings and malformed arrays."""
    if not isinstance(artifact, dict) or set(artifact) != _ARTIFACT_FIELDS:
        raise DependencyClassifierError("classifier artifact has invalid fields")
    if artifact["schema_version"] != ARTIFACT_VERSION or artifact["algorithm"] != ALGORITHM or artifact["classes"] != list(MODES):
        raise DependencyClassifierError("unsupported classifier artifact version")
    if artifact["embedding"] != _embedding_identity():
        raise DependencyClassifierError("classifier embedding fingerprint mismatch")
    fingerprint = artifact["fingerprint"]
    if not isinstance(fingerprint, str) or not _SHA.fullmatch(fingerprint):
        raise DependencyClassifierError("invalid classifier fingerprint")
    try:
        if fingerprint != _digest({key: value for key, value in artifact.items() if key != "fingerprint"}):
            raise DependencyClassifierError("classifier integrity check failed")
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise DependencyClassifierError("classifier is not finite JSON data") from exc
    config = artifact["feature_config"]
    if not isinstance(config, dict) or set(config) != {"version", "input_encoding", "max_features", "embedding_weight", "lexical_weight"}:
        raise DependencyClassifierError("invalid feature configuration")
    if config["version"] != FEATURE_VERSION or config["input_encoding"] != INPUT_VERSION:
        raise DependencyClassifierError("incompatible feature encoding")
    maximum = _integer(config["max_features"], minimum=1, maximum=MAX_VOCABULARY)
    for key in ("embedding_weight", "lexical_weight"):
        _number(config[key], minimum=0.01, maximum=10)
    vocabulary = artifact["vocabulary"]
    if (not isinstance(vocabulary, list) or not 1 <= len(vocabulary) <= maximum
            or any(not isinstance(feature, str) or not 3 < len(feature) <= MAX_FEATURE_LENGTH for feature in vocabulary)
            or len(set(vocabulary)) != len(vocabulary)):
        raise DependencyClassifierError("invalid learned feature vocabulary")
    for key, shape in (("idf", (len(vocabulary),)), ("weights", (EMBEDDING_DIMENSION + len(vocabulary), len(MODES))), ("bias", (len(MODES),))):
        raw = artifact[key]
        if (not isinstance(raw, list) or len(raw) != shape[0]
                or key == "weights" and any(not isinstance(row, list) or len(row) != shape[1] for row in raw)):
            raise DependencyClassifierError("malformed classifier parameter dimensions")
        scalars = (value for row in raw for value in row) if key == "weights" else iter(raw)
        if any(type(value) not in {int, float} for value in scalars):
            raise DependencyClassifierError("classifier parameters must be numeric")
        try:
            values = np.asarray(artifact[key], dtype=np.float64)
        except (ValueError, TypeError, OverflowError) as exc:
            raise DependencyClassifierError("malformed classifier parameters") from exc
        if values.shape != shape or not np.isfinite(values).all() or np.any(np.abs(values) > 100_000):
            raise DependencyClassifierError("invalid classifier parameter shape or values")
        if key == "idf" and (np.any(values < 1) or np.any(values > 20)):
            raise DependencyClassifierError("invalid learned IDF values")
    training = artifact["training"]
    required_training = {"corpus_sha256", "train_count", "calibration_count", "training_case_ids_sha256", "calibration_case_ids_sha256",
                         "train_groups", "calibration_groups", "class_counts", "regularization", "train_accuracy", "source_sha256", "created_at"}
    if not isinstance(training, dict) or set(training) != required_training:
        raise DependencyClassifierError("invalid training manifest")
    for key in ("corpus_sha256", "training_case_ids_sha256", "calibration_case_ids_sha256"):
        if not isinstance(training[key], str) or not _SHA.fullmatch(training[key]):
            raise DependencyClassifierError("invalid training data fingerprint")
    for key in ("train_count", "calibration_count"):
        _integer(training[key], minimum=4)
    if training["train_count"] + training["calibration_count"] > MAX_CORPUS_CASES:
        raise DependencyClassifierError("training manifest exceeds corpus bound")
    for key in ("train_groups", "calibration_groups"):
        if not isinstance(training[key], list) or not training[key] or len(training[key]) > MAX_CORPUS_CASES:
            raise DependencyClassifierError("invalid training group manifest")
        if len({_label(group) for group in training[key]}) != len(training[key]):
            raise DependencyClassifierError("duplicate training group")
    if set(training["train_groups"]) & set(training["calibration_groups"]):
        raise DependencyClassifierError("calibration groups overlap training")
    distributions = training["class_counts"]
    if not isinstance(distributions, dict) or set(distributions) != {"train", "calibration"}:
        raise DependencyClassifierError("invalid training class counts")
    for split, count_key in (("train", "train_count"), ("calibration", "calibration_count")):
        if not isinstance(distributions[split], dict) or set(distributions[split]) != set(MODES):
            raise DependencyClassifierError("missing class counts")
        if sum(_integer(value, minimum=1) for value in distributions[split].values()) != training[count_key]:
            raise DependencyClassifierError("class counts contradict split size")
    _number(training["regularization"], minimum=1e-6, maximum=1000)
    _number(training["train_accuracy"], maximum=1)
    _label(training["created_at"])
    if (not isinstance(training["source_sha256"], dict) or not training["source_sha256"]
            or any(not isinstance(key, str) or not isinstance(value, str) or not _SHA.fullmatch(value)
                   for key, value in training["source_sha256"].items())):
        raise DependencyClassifierError("invalid classifier source fingerprints")
    calibration = artifact["calibration"]
    if not isinstance(calibration, dict) or set(calibration) != {"method", "target_error_rate", "minimum_accepted", "count", "accepted", "errors", "raw_accuracy", "coverage", "per_mode", "scope"}:
        raise DependencyClassifierError("invalid calibration manifest")
    if calibration["method"] != "held_group_top_two_margin_v1" or calibration["count"] != training["calibration_count"]:
        raise DependencyClassifierError("calibration protocol mismatch")
    _integer(calibration["count"], minimum=4)
    _integer(calibration["accepted"])
    _integer(calibration["errors"])
    _label(calibration["scope"])
    target = _number(calibration["target_error_rate"], maximum=0.25)
    minimum = _integer(calibration["minimum_accepted"], minimum=1)
    for key in ("raw_accuracy", "coverage"):
        _number(calibration[key], maximum=1)
    if not isinstance(calibration["per_mode"], dict) or set(calibration["per_mode"]) != set(MODES):
        raise DependencyClassifierError("calibration must cover all predicted modes")
    accepted_total = errors_total = available_total = 0
    for entry in calibration["per_mode"].values():
        if not isinstance(entry, dict) or set(entry) != {"enabled", "threshold", "accepted", "errors", "available"}:
            raise DependencyClassifierError("invalid calibration mode entry")
        if type(entry["enabled"]) is not bool:
            raise DependencyClassifierError("calibration enable flag must be boolean")
        _number(entry["threshold"])
        accepted, errors, available = (_integer(entry[key]) for key in ("accepted", "errors", "available"))
        if not errors <= accepted <= available or (entry["enabled"] and (accepted < minimum or errors / accepted > target)) or (not entry["enabled"] and accepted):
            raise DependencyClassifierError("inconsistent calibration acceptance counts")
        accepted_total += accepted
        errors_total += errors
        available_total += available
    if (available_total != calibration["count"] or accepted_total != calibration["accepted"] or errors_total != calibration["errors"]
            or not math.isclose(calibration["coverage"], accepted_total / calibration["count"], abs_tol=1e-12)):
        raise DependencyClassifierError("inconsistent calibration totals")


class DependencyClassifier:
    def __init__(self, embedder, *, artifact_path: str | Path = DEFAULT_CLASSIFIER_PATH):
        self._initialize(embedder, _load_json(Path(artifact_path), limit=MAX_ARTIFACT_BYTES))

    @classmethod
    def from_document(cls, embedder, artifact: Mapping[str, Any]):
        instance = cls.__new__(cls)
        instance._initialize(embedder, artifact)
        return instance

    def _initialize(self, embedder, artifact):
        validate_artifact(artifact)
        _check_embedder(embedder)
        self._embedder = embedder
        self._artifact = deepcopy(artifact)
        self._weights = np.asarray(artifact["weights"], dtype=np.float64)
        self._bias = np.asarray(artifact["bias"], dtype=np.float64)
        self._idf = np.asarray(artifact["idf"], dtype=np.float64)

    @property
    def manifest(self) -> dict[str, Any]:
        return deepcopy({key: self._artifact[key] for key in
                         ("schema_version", "algorithm", "fingerprint", "embedding", "feature_config", "training", "calibration")})

    def classify(self, text: str, *, history: Sequence[ChatMessage] = ()) -> DependencyPrediction:
        encoded = encode_dependency_input(text, history)
        vector = _vectors(self._embedder.embed_passages([encoded]), 1)
        lexical = _lexical_matrix([_counts(encoded)], self._artifact["vocabulary"], self._idf)
        config = self._artifact["feature_config"]
        features = np.hstack((vector * config["embedding_weight"], lexical * config["lexical_weight"]))
        scores = (features @ self._weights + self._bias)[0]
        if not np.isfinite(scores).all():
            raise DependencyClassifierError("classifier produced non-finite scores")
        predicted = MODES[int(np.argmax(scores))]
        ordered = np.sort(scores)
        margin = float(ordered[-1] - ordered[-2])
        calibration = self._artifact["calibration"]["per_mode"][predicted]
        uncertain = not calibration["enabled"] or margin < calibration["threshold"]
        return DependencyPrediction(
            mode="clarify" if uncertain else predicted, predicted_mode=predicted,
            scores=dict(zip(MODES, map(float, scores))), margin=margin,
            threshold=float(calibration["threshold"]), uncertain=uncertain,
            general_request="", model_manifest=self.manifest,
        )
