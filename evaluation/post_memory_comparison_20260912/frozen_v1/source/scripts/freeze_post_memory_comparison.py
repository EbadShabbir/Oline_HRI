"""Freeze the fresh three-system pilot before inference; metadata reads only."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys

from oline_hri.config import load_config
from oline_hri.embedding import REQUIRED_ASSET_SHA256
from oline_hri.evaluation_model_pairs import (
    _http_json, _installed_models, _model_metadata, _new_private_directory,
    _write_new_json, capture_safety_snapshot,
)
from complete_system_device_guard import policy_dict
from run_complete_system import ARM_ORDERS, LARGE, SMALL, load_workload


PROFILE_ID = "post_memory_comparison_v1"
ROOT = Path(__file__).resolve().parents[1]


def package_versions():
    return {name: version(name) for name in ("numpy", "onnxruntime", "tokenizers")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--validation", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    from analyze_complete_system import validate_workload
    from run_post_memory_comparison import execution_policy, source_hashes

    workload = load_workload(args.workload)
    validate_workload(workload)
    validation = json.loads(args.validation.read_text())
    if validation.get("exit_code") != 0 or validation.get("failures") != 0 or validation.get("errors") != 0:
        raise ValueError("freeze requires a successful offline validation record")
    source = source_hashes()
    for rel, expected in validation["source_config_script_and_test_sha256"].items():
        if sha256((ROOT / rel).read_bytes()).hexdigest() != expected:
            raise ValueError(f"validated file changed: {rel}")
    config = load_config()
    config = replace(config, generation=replace(config.generation, context_length=2048,
                     max_output_tokens=192, temperature=0.0, thinking=False))
    if (config.ollama.small_model, config.ollama.general_large_model, config.ollama.large_model) != (SMALL, LARGE, LARGE):
        raise ValueError("this experiment permits only the configured 0.6B/1.7B pair")
    for rel, expected in REQUIRED_ASSET_SHA256.items():
        path = Path(config.embedding.model_directory).expanduser() / rel
        if sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"embedding asset differs: {rel}")
    installed = _installed_models()
    models = {model: _model_metadata(model, installed) for model in (SMALL, LARGE)}
    snapshot = capture_safety_snapshot()
    frozen = {
        "schema_version": 1, "profile_id": PROFILE_ID,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "fresh assistant-authored post-fix text-system pilot; independent human review pending",
        "source_sha256": source,
        "workload_sha256": sha256(args.workload.read_bytes()).hexdigest(),
        "protocol_sha256": sha256(args.protocol.read_bytes()).hexdigest(),
        "offline_validation_sha256": sha256(args.validation.read_bytes()).hexdigest(),
        "models": models, "ollama_version": _http_json("/api/version"),
        "embedding_asset_sha256": dict(REQUIRED_ASSET_SHA256),
        "embedding_config": asdict(config.embedding),
        "generation": asdict(config.generation), "generation_seed": 42,
        "base_config": config.to_dict(), "packages": package_versions(),
        "python": sys.version, "hardware": platform.uname()._asdict(),
        "device_policy": policy_dict(), "pre_freeze_snapshot": snapshot,
        "execution_policies": {arm: execution_policy(arm) for arm in ("small", "large", "cascade")},
        "distinct_requests": len(workload["execution_cases"]), "repetitions": 3,
        "planned_attempts": len(workload["execution_cases"]) * 9,
        "counterbalanced_arm_orders": ARM_ORDERS,
        "workload_metadata": workload.get("metadata", {}),
        "quality_threshold": None, "responsiveness_threshold": None,
        "no_inference_during_freeze": True,
    }
    if source_hashes() != source:
        raise ValueError("source changed while preparing freeze")
    directory = _new_private_directory(args.output_dir.absolute())
    for rel, expected in source.items():
        data = (ROOT / rel).read_bytes()
        if sha256(data).hexdigest() != expected:
            raise ValueError(f"source changed while copying: {rel}")
        target = directory / "source" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(data)
    for name, original in (("workload.json", args.workload), ("protocol.md", args.protocol),
                           ("offline_validation.json", args.validation)):
        with (directory / name).open("xb") as handle:
            handle.write(original.read_bytes())
    if source_hashes() != source:
        raise ValueError("source changed while archiving freeze")
    _write_new_json(directory / "freeze.json", frozen)
    print(f"FROZEN {directory / 'freeze.json'}; no inference", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
