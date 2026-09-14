"""Run only the 17 unfinished questions from the interrupted Qwen2.5 ARC arm.

The original 83 completed questions and interrupted question 84 stay untouched.
The continuation is a separate segment with its own cold load and telemetry.
Default startup uses the same retry amendment and unchanged runtime guards.
--diagnostic-continuation explicitly selects the documented diagnostic limits.
Use --check-only to inspect preparation and readiness without creating a run.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import tempfile

from oline_hri import evaluation_model_pairs as safety
import run_arc_capability as arc
import run_arc_qwen25_retry as retry


PARENT_OBSERVATIONS_SHA256 = "b36374afae51d6724a83ed718de05068c5b0c4ed592e7d2a2bf5afc5d31a9314"
PARENT_FILES = ("manifest.json", "observations.jsonl", "finish.json", "dataset.json",
                "execution_amendment.json", "execution_launcher.py", "execution_amendment.md")
DIAGNOSTIC_PROTOCOL = retry.ROOT / "evaluation" / "arc_capability_20260911" / "continuation_protocol.md"
DIAGNOSTIC_START_RAM_KIB = 2359296
DIAGNOSTIC_START_SWAP_KIB = 786432
DIAGNOSTIC_RUNTIME_SWAP_KIB = 1048576


def _json(raw):
    return json.loads(raw, object_pairs_hook=arc._unique_object,
                      parse_constant=arc._reject_constant)


def require_diagnostic_start_safe(snapshot):
    """Check real counters against the explicit diagnostic startup policy."""
    memory = snapshot.get("memory")
    if not isinstance(memory, dict):
        raise arc.SafetyGateError("diagnostic memory snapshot is incomplete")
    available, swap = memory.get("mem_available_kib"), memory.get("swap_used_kib")
    if not retry._nonnegative_integer(available) or available < DIAGNOSTIC_START_RAM_KIB:
        raise arc.SafetyGateError("diagnostic start requires at least 2.25 GiB available RAM")
    if not retry._nonnegative_integer(swap) or swap > DIAGNOSTIC_START_SWAP_KIB:
        raise arc.SafetyGateError("diagnostic startup swap exceeds 768 MiB")
    temperatures = snapshot.get("temperatures_c")
    if not isinstance(temperatures, dict) or not temperatures or any(
        type(value) not in (int, float) or not math.isfinite(value) or value >= 55
        for value in temperatures.values()
    ):
        raise arc.SafetyGateError("diagnostic start requires measured temperatures below 55 C")
    if snapshot.get("resident_models") != []:
        raise arc.SafetyGateError("diagnostic start requires no resident Ollama models")
    fan = snapshot.get("fan_pwm")
    if not retry._nonnegative_integer(fan) or fan <= 0:
        raise arc.SafetyGateError("diagnostic start requires a running fan")
    trips = snapshot.get("thermal_trip_events")
    if not isinstance(trips, dict) or not trips or any(type(value) is not int or value != 0
                                                     for value in trips.values()):
        raise arc.SafetyGateError("diagnostic start requires zero measured thermal trip counters")
    power = snapshot.get("power_mode")
    if not isinstance(power, str) or not re.search(r"NV Power Mode:\s*15W\s*\n0\s*\Z", power):
        raise arc.SafetyGateError("diagnostic start requires exact 15W power mode 0")


def diagnostic_amendment(parent, launcher_bytes, protocol_bytes):
    return {
        **parent, "scope": "diagnostic_remaining_questions_continuation",
        "launcher_path": "scripts/run_arc_qwen25_continue.py",
        "launcher_sha256": sha256(launcher_bytes).hexdigest(),
        "launcher_archive": "execution_launcher.py",
        "protocol_amendment_path": str(DIAGNOSTIC_PROTOCOL.relative_to(retry.ROOT)),
        "protocol_amendment_sha256": sha256(protocol_bytes).hexdigest(),
        "protocol_amendment_archive": "execution_amendment.md",
        "original_retry_start_limits": parent["start_limits"],
        "original_runtime_swap_ceiling_kib": parent["runtime_limits"]["max_swap_used_kib"],
        "start_limits": {**parent["start_limits"],
                         "min_available_ram_kib": DIAGNOSTIC_START_RAM_KIB,
                         "max_swap_used_kib": DIAGNOSTIC_START_SWAP_KIB},
        "runtime_limits": {**parent["runtime_limits"],
                           "max_swap_used_kib": DIAGNOSTIC_RUNTIME_SWAP_KIB},
        "runtime_guards_unchanged": False,
        "unchanged_guards": ["runtime_available_RAM", "temperature", "boot_id",
                             "thermal_trip_events", "single_model_residency", "model_artifact_admission"],
        "parent_feasibility_failure_preserved": True,
        "interpretation": "diagnostic segmented accuracy only; parent 512 MiB swap failure remains primary feasibility evidence",
        "rationale": (
            "After the original runtime swap abort, the user requested only the remaining questions. "
            "This explicitly disclosed diagnostic segment permits 768 MiB startup swap and "
            "1024 MiB runtime swap, with 2.25 GiB startup RAM. The physical runtime RAM floor, "
            "temperature, boot, trip, and residency checks remain unchanged. Exactly 17 questions "
            "are attempted once; there is no retry loop or automatic further relaxation. "
            "The original interrupted run is preserved as a feasibility failure."
        ),
    }


def prepare(parent_run, *, diagnostic=False):
    """Derive the remainder from immutable evidence, without device changes."""
    parent_run = parent_run.resolve(strict=True)
    parent_files = {name: (parent_run / name).read_bytes() for name in PARENT_FILES}
    hashes = {name: sha256(raw).hexdigest() for name, raw in parent_files.items()}
    if hashes["observations.jsonl"] != PARENT_OBSERVATIONS_SHA256:
        raise ValueError("this continuation is restricted to the recorded interrupted parent run")
    manifest = _json(parent_files["manifest.json"])
    finish = _json(parent_files["finish.json"])
    amendment = _json(parent_files["execution_amendment.json"])
    dataset, full_digest = arc.load_dataset(retry.DATASET)
    if full_digest != retry.DATASET_SHA256 or manifest.get("dataset_sha256") != full_digest:
        raise ValueError("the parent must use the unchanged frozen 100-case dataset")
    if hashes["dataset.json"] != manifest.get("artifact_dataset_sha256"):
        raise ValueError("the parent archived dataset digest does not match")
    if _json(parent_files["dataset.json"]) != dataset:
        raise ValueError("the parent archived dataset differs from the frozen dataset")
    if (manifest.get("arm") != "extra" or set(manifest.get("models", {})) != {retry.EXTRA_MODEL}
            or finish.get("status") != "interrupted" or finish.get("cleanup_errors") != []):
        raise ValueError("the parent must be the interrupted extra arm with completed cleanup")
    if manifest.get("execution_amendment") != amendment:
        raise ValueError("parent startup amendment archives disagree")
    if manifest.get("source_sha256") != arc.source_hashes():
        raise ValueError("original runner or production source differs from the parent run")
    if sha256(Path(arc.__file__).read_bytes()).hexdigest() != retry.RUNNER_SHA256:
        raise ValueError("original runner differs from the frozen source")
    retry_bytes = Path(retry.__file__).read_bytes()
    if sha256(retry_bytes).hexdigest() != amendment.get("launcher_sha256"):
        raise ValueError("retry launcher differs from the parent archived startup policy")
    if (parent_run / amendment["launcher_archive"]).read_bytes() != retry_bytes:
        raise ValueError("parent retry launcher archive differs from the current retry launcher")
    protocol_bytes = (parent_run / amendment["protocol_amendment_archive"]).read_bytes()
    if sha256(protocol_bytes).hexdigest() != amendment.get("protocol_amendment_sha256"):
        raise ValueError("parent protocol amendment archive digest does not match")

    rows = [_json(line) for line in parent_files["observations.jsonl"].splitlines()]
    all_cases = dataset["cases"]
    if (len(rows) != 84 or len(all_cases) != 100
            or [row["case_id"] for row in rows] != [case["id"] for case in all_cases[:84]]
            or [row.get("index") for row in rows] != list(range(1, 85))
            or any(row.get("status") != "ok" for row in rows[:83])
            or rows[-1].get("status") != "interrupted"):
        raise ValueError("expected 83 completed questions followed by interrupted question 84")
    accepted_ids = [row["case_id"] for row in rows[:83]]
    remaining_cases = all_cases[83:]
    original_indices = list(range(84, 101))
    derived = {
        "metadata": {**dataset["metadata"], "continuation": {
            "full_dataset_sha256": full_digest,
            "parent_observations_sha256": hashes["observations.jsonl"],
            "original_indices": original_indices,
            "selection": "only unfinished original questions; interrupted question 84 is retried",
        }},
        "cases": remaining_cases,
    }
    derived_bytes = arc._canonical_bytes(derived)
    launcher_bytes = Path(__file__).read_bytes()
    execution_launcher_bytes = retry_bytes
    if diagnostic:
        protocol_bytes = DIAGNOSTIC_PROTOCOL.read_bytes()
        amendment = diagnostic_amendment(amendment, launcher_bytes, protocol_bytes)
        execution_launcher_bytes = launcher_bytes
    provenance = {
        "schema_version": 1, "scope": "remaining_questions_after_interruption",
        "parent_run": str(parent_run), "parent_artifact_sha256": hashes,
        "parent_archives": {name: "parent_" + name for name in PARENT_FILES},
        "full_dataset_sha256": full_digest,
        "accepted_parent_case_ids": accepted_ids,
        "remaining_case_ids": [case["id"] for case in remaining_cases],
        "original_indices": original_indices,
        "derived_dataset_sha256": sha256(derived_bytes).hexdigest(),
        "launcher_path": "scripts/run_arc_qwen25_continue.py",
        "launcher_sha256": sha256(launcher_bytes).hexdigest(),
        "launcher_archive": "continuation_launcher.py",
        "local_to_original_index": {str(index): original for index, original
                                    in enumerate(original_indices, 1)},
        "timing_scope": "separate_segment_with_cold_load",
        "diagnostic_continuation": diagnostic,
        "reason": (
            "The user requested only the remaining questions after interruption. "
            "The first 83 completed questions are not replayed. The interrupted "
            "question 84 is retained in the parent evidence and retried here."
        ),
    }
    return {
        "dataset": derived, "dataset_bytes": derived_bytes, "provenance": provenance,
        "parent_files": parent_files, "parent_manifest": manifest, "amendment": amendment,
        "launcher_bytes": launcher_bytes, "retry_bytes": retry_bytes,
        "execution_launcher_bytes": execution_launcher_bytes,
        "protocol_bytes": protocol_bytes,
    }


def readiness(plan):
    snapshot = arc.capture_safety_snapshot()
    try:
        gate = require_diagnostic_start_safe if plan["provenance"]["diagnostic_continuation"] else retry.require_retry_start_safe
        gate(snapshot)
        installed = arc._installed_models()
        current = arc._model_metadata(retry.EXTRA_MODEL, installed)
        parent = plan["parent_manifest"]["models"][retry.EXTRA_MODEL]
        if current != parent:
            raise ValueError("installed model artifact metadata differs from the parent run")
    except Exception as error:
        return {"ready": False, "snapshot": snapshot,
                "error": {"type": type(error).__name__, "message": str(error)}}
    return {"ready": True, "snapshot": snapshot, "error": None}


@contextmanager
def continuation_bindings(plan):
    """Add segment provenance while reusing the original retry gate and cleanup."""
    provenance = plan["provenance"]
    with retry.retry_bindings(plan["amendment"], plan["execution_launcher_bytes"], plan["protocol_bytes"]):
        previous_writer = arc._write_new_json
        previous_gate = arc._require_start_safe
        previous_runtime_swap = safety.MAX_RUNTIME_SWAP_USED_KIB
        if provenance["diagnostic_continuation"]:
            arc._require_start_safe = require_diagnostic_start_safe
            # Both the streaming monitor and GuardedBackend runtime checks read
            # this one module constant. No production source or counters change.
            safety.MAX_RUNTIME_SWAP_USED_KIB = DIAGNOSTIC_RUNTIME_SWAP_KIB

        def write_artifact(path, value):
            if path.name == "manifest.json":
                parent = plan["parent_manifest"]
                for key in ("arm", "models", "source_sha256", "config", "system_prompt",
                            "generation_seed", "residency_policy"):
                    if value.get(key) != parent.get(key):
                        raise ValueError(f"continuation differs from parent field: {key}")
                if value.get("dataset_sha256") != provenance["derived_dataset_sha256"]:
                    raise ValueError("continuation input differs from the derived remainder")
                value = {**value, "continuation": provenance}
            previous_writer(path, value)
            if path.name == "start.json":
                for name, raw in plan["parent_files"].items():
                    retry._archive_new(path.parent / provenance["parent_archives"][name], raw)
                retry._archive_new(path.parent / provenance["launcher_archive"], plan["launcher_bytes"])
                previous_writer(path.parent / "continuation.json", provenance)

        arc._write_new_json = write_artifact
        try:
            yield
        finally:
            arc._write_new_json = previous_writer
            arc._require_start_safe = previous_gate
            safety.MAX_RUNTIME_SWAP_USED_KIB = previous_runtime_swap


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-run", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--diagnostic-continuation", action="store_true",
                        help="Explicitly select the archived diagnostic startup and runtime swap policy")
    args = parser.parse_args(argv)
    if not args.check_only and args.output_dir is None:
        parser.error("--output-dir is required unless --check-only is used")
    if args.output_dir is not None and args.output_dir.exists():
        raise ValueError("continuation output must be a fresh directory")
    plan = prepare(args.parent_run, diagnostic=args.diagnostic_continuation)
    state = readiness(plan)
    print(json.dumps({"preparation": plan["provenance"], "readiness": state}, sort_keys=True), flush=True)
    if args.check_only or not state["ready"]:
        return 0 if state["ready"] else 1
    # The derived input is archived as dataset.json by arc.main. The temporary
    # input path in its manifest is ephemeral; both input and archived hashes
    # are explicit and the original 100-case dataset stays untouched.
    with tempfile.TemporaryDirectory(prefix="arc-qwen25-remainder-") as temporary:
        dataset_path = Path(temporary) / "remaining_dataset.json"
        retry._archive_new(dataset_path, plan["dataset_bytes"])
        with continuation_bindings(plan):
            return arc.main([
                "--dataset", str(dataset_path), "--output-dir", str(args.output_dir),
                "--arm", "extra", "--extra-model", retry.EXTRA_MODEL,
            ])


if __name__ == "__main__":
    raise SystemExit(main())
