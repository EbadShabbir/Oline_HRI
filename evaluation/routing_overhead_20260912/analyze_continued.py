"""Offline mixed-freeze adapter; preserves all raw attempts and original statuses.

The only completion-eligibility exception is an exact, hash-pinned four-turn
v1 session whose final answer was rejected. Its failed answer remains failed.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import analyze_routing_overhead as core

ORIGINAL_LOAD = core.load_inputs
EXCEPTION_SLOT = "ro_dddd_3_r1_large"
EXCEPTION_HASHES = {
    "finish.json": "9b527a43ab884738613661974e03e1bf62536a09e2167f2fcc54a925bd25f935",
    "observations.jsonl": "d8f3980cc21ba97534a3213ce1587a73250a6cf77066d121a293cac430234050",
    "manifest.json": "29a17855abf96e364f2c1c651240b8b2d159850b8d60774ae859fdce46710f4e",
    "events.jsonl": "6811809d2665868b82357cb8a2dbde5df8b86ff61b229fa15d6f4409b5a4a027",
    "startup.json": "dc3fdab5958c39cd7d9e195d5f57a6e409bb922029d9b93d3d91f7cce123751e",
}
UNCHANGED_FIELDS = (
    "profile_id", "workload_sha256", "models", "ollama_version", "config",
    "generation", "generation_seed", "embedding_asset_sha256", "packages",
    "python", "device_policy", "arm_orders", "diagnostic_replay_order",
    "sequences", "turns_per_sequence", "repetitions", "main_attempts", "diagnostic_attempts",
)
NEW_ADAPTER_FILES = {
    "evaluation/routing_overhead_20260912/analyze_continued.py",
    "evaluation/routing_overhead_20260912/continue_collection.py",
}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def freeze_compatibility(previous_path, current_path):
    previous, current = core.read(previous_path), core.read(current_path)
    for field in UNCHANGED_FIELDS:
        if previous.get(field) != current.get(field):
            raise ValueError(f"continuation changes frozen execution setting: {field}")
    old, new = previous["source_sha256"], current["source_sha256"]
    if not set(old) <= set(new) or not (set(new) - set(old)) <= NEW_ADAPTER_FILES:
        raise ValueError("continuation source file set has an unapproved change")
    changed = {name for name in old if old[name] != new[name]}
    permitted = {"scripts/run_routing_overhead.py", "tests/test_routing_overhead_runner.py"}
    if not changed <= permitted:
        raise ValueError(f"continuation changed inference/analysis dependencies: {changed - permitted}")
    runner = "scripts/run_routing_overhead.py"
    old_text = (previous_path.parent / "source" / runner).read_text()
    new_text = (current_path.parent / "source" / runner).read_text()
    expected = old_text.replace(
        'raise ValueError("diagnostic replay did not consume every adaptive generation request")',
        'raise SafetyGateError("diagnostic replay did not consume every adaptive generation request")',
    ).replace(
        "(KeyboardInterrupt, SystemExit, SafetyGateError, ValueError)",
        "(KeyboardInterrupt, SystemExit, SafetyGateError)",
    )
    expected = expected.replace(
        '    paths.append(ROOT / "config/default.json")\n',
        '    paths += [ROOT / "evaluation/routing_overhead_20260912" / name for name in\n'
        '              ("continue_collection.py", "analyze_continued.py")]\n'
        '    paths.append(ROOT / "config/default.json")\n',
    )
    # Equal freezes are useful for auditing v1 alone; differing runner source
    # must be exactly the two error-classification edits and the added
    # provenance hashes for the continuation and offline-analysis adapters.
    if new_text not in (old_text, expected):
        raise ValueError("runner change exceeds nonfatal-answer/error classification")
    if digest(Path(core.__file__)) != old["scripts/analyze_routing_overhead.py"]:
        raise ValueError("loaded core analyzer differs from archived original")
    return dict(unchanged_fields=list(UNCHANGED_FIELDS), changed_source_files=sorted(changed),
                added_source_files=sorted(set(new) - set(old)),
                previous_freeze_sha256=digest(previous_path), current_freeze_sha256=digest(current_path))


def normalize_exact_observation(run, records, directory):
    for filename, expected in EXCEPTION_HASHES.items():
        if digest(directory / filename) != expected:
            raise ValueError(f"exceptional original artifact changed: {filename}")
    finish = core.read(directory / "finish.json")
    rows = [row for row in records if row["attempt_directory"] == EXCEPTION_SLOT]
    if (run["status"] != "interrupted" or run["complete"] or not run["accounting_ok"]
            or len(rows) != 4 or [row["index"] for row in rows] != [1, 2, 3, 4]
            or [row["status"] for row in rows] != ["ok", "ok", "ok", "interrupted"]
            or rows[-1].get("error") != "ResponseValidationError"
            or finish.get("guard_violation") is not None or finish.get("cleanup_errors")
            or finish.get("resident_models") != []
            or any(call["status"] != "ok" for call in rows[-1]["calls"])
            or any(call["status"] != "ok" for call in rows[-1]["http_calls"])):
        raise ValueError("exceptional session does not meet exact four-turn/error audit")
    run["complete"] = True
    run["completion_eligibility_note"] = "All four turns observed; final validation failure retained; original interrupted status unchanged."
    return dict(slot=EXCEPTION_SLOT, original_status="interrupted", eligibility="four_turns_observed_with_error",
                raw_turn_statuses=[row["status"] for row in rows],
                failed_turn_remains_in_quality_denominator=True,
                exact_artifact_sha256=EXCEPTION_HASHES)


class MixedFreezeLoader:
    def __init__(self, args):
        self.args = args
        self.proof = {"compatibility": freeze_compatibility(args.previous_freeze, args.freeze)}

    def __call__(self, run_root, workload_path, freeze_path):
        previous_hash, current_hash = digest(self.args.previous_freeze), digest(freeze_path)
        old_slots = {path.parent.name: path.parent for path in self.args.previous_root.glob("*/manifest.json")}
        groups = {"previous": [], "current": []}
        provenance = []
        for manifest_path in sorted(run_root.glob("*/manifest.json")):
            directory = manifest_path.parent
            manifest = core.read(manifest_path)
            origin = manifest.get("freeze_sha256")
            if origin == previous_hash and directory.name in old_slots:
                group, original = "previous", old_slots[directory.name]
                # The continuation view must reference or exactly preserve
                # every original source artifact, including HTTP/telemetry.
                for path in original.iterdir():
                    if not path.is_file():
                        continue
                    candidate = directory / path.name
                    if not candidate.is_file() or (candidate.resolve() != path.resolve() and digest(candidate) != digest(path)):
                        raise ValueError(f"reused original artifact differs or is absent: {candidate}")
            elif origin == current_hash and directory.name not in old_slots:
                group, original = "current", directory
            else:
                raise ValueError(f"unknown source freeze or repeated original slot: {directory.name}")
            groups[group].append(directory)
            provenance.append(dict(slot=directory.name, origin_freeze_sha256=origin,
                                   original_directory=str(original.resolve()), continuation_directory=str(directory.resolve()),
                                   observations_sha256=digest(directory / "observations.jsonl") if (directory / "observations.jsonl").exists() else None))
        if {path.name for path in groups["previous"]} != set(old_slots):
            raise ValueError("continuation omits an original attempt directory")
        merged = [[], [], [], [], [], []]  # runs, records, components, backends, spans, errors
        with tempfile.TemporaryDirectory(prefix="clara-mixed-freeze-analysis-") as temporary:
            for group, directories in groups.items():
                view = Path(temporary) / group
                view.mkdir()
                for directory in directories:
                    session = view / directory.name
                    session.mkdir()
                    for path in directory.iterdir():
                        if path.is_file():
                            (session / path.name).symlink_to(path.resolve())
                matching_freeze = self.args.previous_freeze if group == "previous" else freeze_path
                result = ORIGINAL_LOAD(view, workload_path, matching_freeze)
                for destination, values in zip(merged, result[2:]):
                    destination.extend(values)
        runs, records, components, backends, spans, errors = merged
        for run in runs:
            run["source_freeze"] = "v1" if run["attempt_directory"] in old_slots else "v2"
        exception = next((run for run in runs if run["attempt_directory"] == EXCEPTION_SLOT), None)
        if exception is None:
            raise ValueError("expected original four-turn validation-failure session absent")
        normalization = normalize_exact_observation(exception, records, old_slots[EXCEPTION_SLOT])
        # A future whole-session resume could separate adaptive and replay into
        # source groups. Verify the same strict replay contract after merging.
        lookup = {(row["sequence_id"], row["repetition"], row["id"]): row for row in records if row["arm"] == "adaptive"}
        verified_cross_group = set()
        replay_checks = []
        for row in records:
            if row["arm"] != "replay":
                continue
            original = lookup.get((row["sequence_id"], row["repetition"], row["id"]))
            if original is None or not row.get("calls") or not row.get("route"):
                replay_checks.append(dict(slot=row["attempt_directory"], id=row["id"],
                    status="unavailable", reason="adaptive source or recorded replay calls/route absent"))
                continue
            requests = lambda item: [{key: call.get(key) for key in ("requested_model", "messages", "response_format")}
                for call in item["calls"] if call["purpose"] == "generation"]
            bodies = lambda item: [call["body"] for call in item["http_calls"] if call["endpoint"] == "/api/chat"
                and "speech" in call["body"].get("format", {}).get("properties", {})]
            if (requests(row) != requests(original) or bodies(row) != bodies(original)
                    or row["history_before"] != original["history_before"] or row["route"] != original["route"]):
                raise ValueError("merged diagnostic replay differs from adaptive source")
            verified_cross_group.add(row["attempt_directory"])
            replay_checks.append(dict(slot=row["attempt_directory"], id=row["id"],
                status="exact_requests_verified", raw_delivery_status=row["status"]))
        errors = [error for error in errors if not (error.get("error") == "diagnostic replay lacks adaptive source"
                  and error.get("attempt_directory") in verified_cross_group)]
        self.proof.update(session_origins=provenance, original_sessions=len(groups["previous"]),
                          new_sessions=len(groups["current"]), eligibility_normalization=normalization,
                          original_raw_statuses_modified=False, original_raw_artifacts_modified=False,
                          previous_run_root=str(self.args.previous_root.resolve()),
                          previous_freeze=str(self.args.previous_freeze.resolve()), current_freeze=str(freeze_path.resolve()),
                          diagnostic_replay_input_checks=replay_checks,
                          adapter_sha256=digest(Path(__file__)))
        return (core.read(workload_path), core.read(freeze_path), runs, records, components, backends, spans, errors)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("blind", "analyze"))
    for name in ("run-root", "workload", "freeze", "output-dir", "previous-root", "previous-freeze"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--blind-dir", type=Path)
    parser.add_argument("--reviews", type=Path, action="append", default=[])
    parser.add_argument("--no-figures", action="store_true")
    args = parser.parse_args(argv)
    loader = MixedFreezeLoader(args)
    core.load_inputs = loader
    try:
        if args.command == "analyze":
            result = core.analyze(args)
        else:
            workload, _, _, records, _, _, _, errors = loader(args.run_root, args.workload, args.freeze)
            if errors:
                raise ValueError(f"mixed-freeze input audit failed: {errors}")
            core.make_blind(workload, records, args.output_dir)
            result = 0
        core.write(args.output_dir / "continuation_provenance.json", loader.proof)
        return result
    finally:
        core.load_inputs = ORIGINAL_LOAD


if __name__ == "__main__":
    raise SystemExit(main())
