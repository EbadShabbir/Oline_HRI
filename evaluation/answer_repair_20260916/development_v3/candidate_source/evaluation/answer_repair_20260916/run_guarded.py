"""Bounded development evaluation using the unchanged routing-reliability runner.

No model prompt, seed, context length, output budget, routing choice or generation
option is changed. The runner retains its normal isolated empty memory store.
Safety checks and telemetry add overhead to measured case/model wall times.
This development runner defaults to 12 cases and never permits more than 64.
Each iteration requires its own current candidate freeze and a new output folder.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter, sleep
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from oline_hri import evaluation_model_pairs as pair
from oline_hri.config import load_config
from oline_hri.embedding import REQUIRED_ASSET_SHA256
from complete_system_device_guard import policy_dict, require_ready, stage2_limits
from run_pair_remediation_validation import GuardedBackend, GuardedSampler
import run_routing_reliability as runner


def digest(path):
    value = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def error_record(error):
    return {"type": type(error).__name__, "message": str(error)}


def source_manifest():
    paths = [*sorted((ROOT / "src/oline_hri").glob("*.py")),
             *sorted((ROOT / "src/oline_hri").glob("*.json")),
             ROOT / "scripts/run_routing_reliability.py",
             ROOT / "scripts/run_pair_remediation_validation.py",
             ROOT / "scripts/complete_system_device_guard.py", Path(__file__).resolve()]
    return {str(path.relative_to(ROOT)): digest(path) for path in paths}


def verify_candidate(path, current):
    frozen = json.loads(path.read_text(encoding="utf-8"))["source_sha256"]
    mismatch = [name for name, expected in frozen.items() if current.get(name) != expected]
    if mismatch:
        raise ValueError("candidate differs from preregistered source: " + repr(mismatch))


def local_integrity(cases):
    config = load_config()
    assets = {name: digest(Path(config.embedding.model_directory).expanduser() / name)
              for name in REQUIRED_ASSET_SHA256}
    if assets != REQUIRED_ASSET_SHA256:
        raise ValueError("embedding assets differ from production-pinned hashes")
    return {"source_sha256": source_manifest(), "cases_sha256": digest(cases),
            "config": config.to_dict(), "embedding_sha256": assets}


def model_inventory(config):
    if config.ollama.base_url.rstrip("/") != pair.OLLAMA_BASE_URL.rstrip("/"):
        raise ValueError("production client and safety guard must use the same Ollama endpoint")
    names = tuple(dict.fromkeys((config.ollama.small_model, config.ollama.general_large_model,
                                config.ollama.large_model)))
    installed = pair._installed_models()
    return {"ollama_version": pair._http_json("/api/version"),
            "models": {name: pair._model_metadata(name, installed) for name in names}}


@contextmanager
def inference_lock():
    """Use the same three exclusive leases as the changing-memory evaluation."""
    with ExitStack() as stack:
        for path in (Path("/tmp/clara-jetson-inference.lock"),
                     ROOT / "evaluation/independent_retrieval_inference.lock",
                     ROOT / "evaluation/matched_evidence_inference.lock"):
            stream = stack.enter_context(path.open("a"))
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        processes = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True,
                                   text=True, check=True).stdout
        conflicts = [line.strip() for line in processes.splitlines()
                     if "python" in line and any(fragment in line for fragment in
                        ("scripts/run_", "scripts/continue_", "scripts/resume_"))
                     and "ps -eo" not in line]
        if conflicts:
            raise pair.SafetyGateError("competing experiment: " + repr(conflicts))
        yield


class TransparentGuardedClient:
    """Reuse safety checks without GuardedBackend.chat's seed-42 override."""

    def __init__(self, client, guard):
        self.client, self.guard = client, guard

    @property
    def resident_model(self):
        return self.client.resident_model

    def chat(self, model, messages, **kwargs):
        self.guard.check()
        try:
            return self.client.chat(model, messages, **kwargs)
        finally:
            self.guard.check()

    def unload_all(self):
        # Cleanup remains available even after an abort boundary was crossed.
        return self.client.unload_all()


def initial_sample(guard, sampler):
    deadline = perf_counter() + 5
    while not sampler.samples and perf_counter() < deadline:
        guard.check()
        sleep(0.05)
    if not sampler.samples:
        raise pair.SafetyGateError("no initial telemetry sample")
    guard.check()


def collect(args):
    cases = runner.load_cases(args.cases)
    if not 1 <= args.max_cases <= 64:
        raise ValueError("max-cases must be between 1 and 64")
    if len(cases) > args.max_cases:
        raise ValueError(f"development case count {len(cases)} exceeds declared cap {args.max_cases}")
    directory = args.output_dir.absolute()
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    before = local_integrity(args.cases)
    verify_candidate(args.candidate_manifest, before["source_sha256"])
    write(directory / "integrity_before.json", before)
    versions = {}
    for package in ("numpy", "onnxruntime", "tokenizers"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    write(directory / "launch.json", {
        "created_at": datetime.now(timezone.utc).isoformat(), "case_count": len(cases),
        "candidate_manifest_sha256": digest(args.candidate_manifest),
        "declared_max_cases": args.max_cases,
        "policy": policy_dict(), "python": sys.version, "package_versions": versions,
        "invocation": sys.argv, "pid": os.getpid(), "validation_only": args.validate_only,
        "runner_arguments": ["--stage", "conversation", "--policy", "learned"],
        "generation_parameters_modified": False,
        "latency_scope": "Case/model wall includes guard checks; backend durations exclude those checks.",
    })
    if args.validate_only:
        write(directory / "validation.json", {"valid": True, "case_count": len(cases),
              "inference_started": False, "device_or_network_access": False})
        return 0

    failure, cleanup_errors, sampler, start, inventory = None, [], None, None, None
    clients, code = [], 1
    config = load_config()
    with inference_lock(), stage2_limits():
        try:
            start = pair.capture_safety_snapshot()
            write(directory / "start.json", start)
            # Never evict another workload: admission requires no resident model.
            require_ready(start)
            inventory = model_inventory(config)
            write(directory / "models_before.json", inventory)
            with pair._DurableJsonlWriter(directory / "telemetry.jsonl") as telemetry:
                sampler = GuardedSampler(pair._StreamingSafetyMonitor(telemetry))
                guard = GuardedBackend(None, start, sampler)
                original_client = runner.OllamaClient

                def guarded_client(*positional, **keywords):
                    client = original_client(*positional, **keywords)
                    clients.append(client)
                    return TransparentGuardedClient(client, guard)

                with sampler:
                    try:
                        initial_sample(guard, sampler)
                        # Only construction is wrapped. All production prompts/options pass through.
                        with patch.object(runner, "OllamaClient", guarded_client):
                            code = runner.main(["--cases", str(args.cases.absolute()),
                                "--output-dir", str(directory / "run"),
                                "--stage", "conversation", "--policy", "learned"])
                        guard.check()
                    finally:
                        for client in clients:
                            try:
                                client.unload_all()
                            except BaseException as error:
                                cleanup_errors.append(error_record(error))
                        # Independent recovery only after this process constructed an owned client.
                        if clients:
                            cleanup_errors.extend(pair._force_unload(tuple(inventory["models"])))
        except BaseException as error:
            failure = error_record(error)
        finally:
            finish = None
            try:
                finish = pair.capture_safety_snapshot()
                if start:
                    for key in ("boot_id", "power_mode", "thermal_trip_events"):
                        if finish[key] != start[key]:
                            cleanup_errors.append("start/finish mismatch: " + key)
                    if finish["memory"]["swap_total_kib"] != start["memory"]["swap_total_kib"]:
                        cleanup_errors.append("configured swap capacity changed")
                if clients and finish["resident_models"]:
                    cleanup_errors.append("owned model cleanup incomplete")
            except BaseException as error:
                cleanup_errors.append(error_record(error))
            try:
                after = local_integrity(args.cases)
                write(directory / "integrity_after.json", after)
                if before != after:
                    cleanup_errors.append("source, cases, config or embedding assets changed")
                if inventory:
                    final_inventory = model_inventory(config)
                    write(directory / "models_after.json", final_inventory)
                    if inventory != final_inventory:
                        cleanup_errors.append("Ollama version or configured model identity changed")
            except BaseException as error:
                cleanup_errors.append(error_record(error))
            if sampler and sampler.cleanup_error:
                cleanup_errors.append(error_record(sampler.cleanup_error))
            write(directory / "finish.json", {
                "runner_exit_code": code, "failure": failure, "cleanup_errors": cleanup_errors,
                "snapshot": finish, "telemetry": sampler.summary() if sampler else None,
                "guard_violation": sampler.monitor.violation if sampler else None,
                "complete": code == 0 and failure is None and not cleanup_errors,
            })
    write(directory / "artifact_sha256.json", {
        str(path.relative_to(directory)): digest(path)
        for path in sorted(directory.rglob("*")) if path.is_file()
    })
    return 0 if code == 0 and failure is None and not cleanup_errors else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-cases", type=int, default=12,
                        help="Declared development case cap (default 12; maximum 64)")
    parser.add_argument("--candidate-manifest", type=Path,
                        default=Path(__file__).with_name("candidate_freeze.json"))
    parser.add_argument("--validate-only", action="store_true",
                        help="Validate cases/source/config/pinned assets offline; no inference or device access")
    return collect(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
