"""Offline final collection integrity audit; never queries hardware or inference.

Run only after collection stops. This supplementary audit is deliberately outside
both frozen inference source sets. Raw statuses and response judgments are never
changed. All heavyweight archive/telemetry checks run only in the final command.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(HERE))
import analyze_routing_overhead as core
import analyze_continued as mixed

SMALL, LARGE = "qwen3:0.6b", "qwen3:1.7b"
CONTROL_KEYS = ("boot_id", "thermal_trip_events", "power_mode")


def read(path):
    return json.loads(path.read_text())


def rows(path):
    with path.open() as stream:
        for number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except ValueError as error:
                    raise ValueError(f"malformed JSONL {path}:{number}") from error


def digest(path):
    hasher = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def expected_slots(workload, orders):
    return [(seq["id"], rep, arm) for rep, order in enumerate(orders, 1)
            for seq in workload["sequences"] for arm in (*order, "replay")]


def slot_name(slot):
    return f"{slot[0]}_r{slot[1]}_{slot[2]}"


def expected_config(frozen, arm):
    value = deepcopy(frozen["config"])
    if arm in {"small", "large"}:
        model = SMALL if arm == "small" else LARGE
        original = value["ollama"]
        timeout = original["request_timeout_seconds"] if arm == "small" else original["large_request_timeout_seconds"]
        original.update(small_model=model, general_large_model=model, large_model=model,
                        request_timeout_seconds=timeout)
    return value


def normalized_swap_topology(value):
    """Usage varies; devices/type/capacity/priority are controls."""
    result = []
    for line in value.splitlines()[1:]:
        fields = line.split()
        if len(fields) != 5:
            raise ValueError("unrecognized recorded swap topology")
        result.append([fields[0], fields[1], int(fields[2]), int(fields[4])])
    return sorted(result)


def durable_errors(observations, events, cleanup):
    errors = []
    markers = [e for e in events if e.get("kind") == "turn_attempt"]
    if [(e.get("id"), e.get("index")) for e in markers] != [(r["id"], r["index"]) for r in observations]:
        errors.append("turn attempt markers do not exactly match completed observations")
    starts, ends = {}, {}
    for event in events:
        kind = event.get("event")
        if kind not in {"span_start", "span_end"}:
            continue
        key = (event.get("index"), event.get("id"))
        target = starts if kind == "span_start" else ends
        if key in target:
            errors.append(f"duplicate durable {kind}: {key}")
        target[key] = event
    if starts.keys() != ends.keys():
        errors.append("unfinished or unstarted durable span exists")
    expected = [(r["index"], e) for r in observations for e in r.get("events", [])]
    expected += [("cleanup", e) for e in cleanup.get("events", [])]
    if {(index, e["id"]) for index, e in expected} != set(ends):
        errors.append("durable span set differs from observations and cleanup")
    for index, event in expected:
        start, end = starts.get((index, event["id"])), ends.get((index, event["id"]))
        if end is None or any(end.get(key) != value for key, value in event.items()):
            errors.append(f"terminal span differs: {(index, event['id'])}")
        if start is None or any(start.get(key) != event.get(key) for key in ("name", "parent_id", "start_ns", "clock")):
            errors.append(f"start identity differs: {(index, event['id'])}")
    return errors


class Audit:
    def __init__(self):
        self.checks = []
        self.sequence_details = []
        self.inventory = []
        self.provenance = {}
        self.output_created = False

    def check(self, category, context, condition, **detail):
        self.checks.append(dict(category=category, context=context,
                                status="pass" if condition else "fail", **detail))
        return condition

    def step(self, context, function):
        try:
            return function()
        except Exception as error:
            self.check("audit_execution", context, False, error=type(error).__name__, message=str(error))
            return None

    def residency(self, snapshot, frozen, arm, context):
        allowed = {SMALL} if arm == "small" else {LARGE} if arm == "large" else {SMALL, LARGE}
        valid = isinstance(snapshot, list) and len(snapshot) <= 1
        for state in snapshot or []:
            model = state.get("name", state.get("model"))
            valid = valid and model in allowed and state.get("digest") == frozen["models"].get(model, {}).get("digest")
            valid = valid and state.get("context_length") == 2048
            valid = valid and isinstance(state.get("size"), int) and state["size"] > 0
            valid = valid and isinstance(state.get("size_vram"), int) and 0 <= state["size_vram"] <= state["size"]
        self.check("eviction_and_residency", context, valid, models=snapshot)

    def snapshot(self, value, baseline, policy, context, cold=False):
        issues = []
        if any(value.get(k) != baseline.get(k) for k in CONTROL_KEYS):
            issues.append("boot, power or thermal-trip state changed")
        if value.get("power_mode", "").split() != ["NV", "Power", "Mode:", "15W", "0"]:
            issues.append("not the frozen 15 W mode 0")
        if not value.get("thermal_trip_events"):
            issues.append("thermal-trip counters are absent")
        if any(value.get("thermal_trip_events", {}).values()):
            issues.append("nonzero thermal-trip counter")
        if value.get("fan_pwm", 0) <= 0:
            issues.append("fan is not recorded running")
        memory = value.get("memory", {})
        if memory.get("swap_total_kib") != policy["expected_swap_total_kib"]:
            issues.append("swap capacity changed")
        if cold:
            if value.get("resident_models") != []:
                issues.append("cold admission has missing or nonempty residency")
            if memory.get("mem_available_kib", -1) < policy["min_start_available_kib"]:
                issues.append("cold RAM admission floor failed")
            if memory.get("swap_used_kib", float("inf")) > policy["max_start_swap_used_kib"]:
                issues.append("cold swap admission ceiling failed")
            if max(value.get("temperatures_c", {}).values(), default=float("inf")) >= policy["max_start_temperature_c_exclusive"]:
                issues.append("cold temperature admission failed")
        self.check("cold_admission" if cold else "resource_integrity", context, not issues, issues=issues)

    def telemetry(self, directory, policy):
        count, previous, maximum_gap = 0, None, 0
        issues = []
        peaks = {"temperature_c": 0, "swap_mib": 0, "ram_used_mib": 0}
        minimum_free = None
        for sample in rows(directory / "telemetry.jsonl"):
            now = sample["monotonic_ns"]
            if previous is not None:
                if now <= previous:
                    issues.append("nonincreasing telemetry timestamp")
                maximum_gap = max(maximum_gap, now - previous)
            previous = now
            count += 1
            free = sample["ram"]["total_mb"] - sample["ram"]["used_mb"]
            swap = sample["swap"]["used_mb"]
            temp = max(sample["temperatures_c"].values())
            minimum_free = free if minimum_free is None else min(free, minimum_free)
            peaks["temperature_c"] = max(peaks["temperature_c"], temp)
            peaks["swap_mib"] = max(peaks["swap_mib"], swap)
            peaks["ram_used_mib"] = max(peaks["ram_used_mib"], sample["ram"]["used_mb"])
            if (free < policy["min_runtime_available_kib"] // 1024 or
                    swap > policy["max_runtime_swap_used_kib"] // 1024 or
                    temp >= policy["max_runtime_temperature_c_exclusive"]):
                issues.append(f"recorded resource threshold crossed at sample {count}")
        summary = read(directory / "telemetry_summary.json")
        if summary.get("sample_count") != count or count == 0:
            issues.append("summary/raw telemetry count mismatch or no samples")
        if maximum_gap > policy["telemetry_stall_ceiling_seconds"] * 1e9:
            issues.append("recorded telemetry gap exceeded stall ceiling")
        self.check("resource_integrity", directory.name + "/telemetry", not issues,
                   issues=issues, samples=count, maximum_sample_gap_seconds=maximum_gap / 1e9,
                   minimum_recorded_free_ram_mib=minimum_free, peaks=peaks,
                   interpretation="Tegrastats free RAM guard; per-call MemAvailable guards are recorded by their absence of violation, not reconstructed.")
        return count

    def archive(self, freeze_path):
        frozen = read(freeze_path)
        for name, expected in frozen["source_sha256"].items():
            path = freeze_path.parent / "source" / name
            self.check("source_and_freeze", str(path), path.is_file() and digest(path) == expected)
        for name, key in (("workload.json", "workload_sha256"), ("protocol.md", "protocol_sha256"),
                          ("offline_validation.json", "validation_sha256")):
            path = freeze_path.parent / name
            self.check("source_and_freeze", str(path), path.is_file() and digest(path) == frozen[key])
        validation = read(freeze_path.parent / "offline_validation.json")
        self.check("source_and_freeze", str(freeze_path) + "/validation",
                   validation.get("exit_code") == 0 and validation.get("failures") == 0 and validation.get("errors") == 0
                   and validation.get("source_sha256") == frozen["source_sha256"])
        return frozen

    def sequence(self, directory, slot, sequence, frozen, freeze_path, baseline, cases, reference_memory):
        name, arm = directory.name, slot[2]
        manifest, finish = read(directory / "manifest.json"), read(directory / "finish.json")
        start, startup, cleanup = (read(directory / file) for file in ("start.json", "startup.json", "cleanup.json"))
        observed, events = list(rows(directory / "observations.jsonl")), list(rows(directory / "events.jsonl"))
        raw_http = list(rows(directory / "http_calls.jsonl"))
        core.audit_calls({"arm": arm, "http_calls": raw_http})
        logged_chats = [h for h in raw_http if h["endpoint"] == "/api/chat"]
        turn_chats = [h for row in observed for h in row["http_calls"] if h["endpoint"] == "/api/chat"]
        self.check("durable_attempts", name + "/http_complete", logged_chats == turn_chats,
                   raw_chat_attempts=len(logged_chats), observed_chat_attempts=len(turn_chats))
        allowed = {SMALL} if arm == "small" else {LARGE} if arm == "large" else {SMALL, LARGE}
        self.check("settings_and_fixed_models", name + "/all_http_models",
                   all(h["body"].get("model") in allowed for h in raw_http))

        expected_ids = sequence["case_ids"]
        self.check("coverage", name, len(observed) == 4 and [r["id"] for r in observed] == expected_ids
                   and [r["index"] for r in observed] == [1, 2, 3, 4], attempted=len(observed), statuses=[r["status"] for r in observed])
        self.check("source_and_freeze", name, manifest.get("freeze_sha256") == digest(freeze_path)
                   and manifest.get("sequence") == sequence and manifest.get("sequence_id") == slot[0]
                   and manifest.get("arm") == arm and manifest.get("repetition") == slot[1]
                   and finish.get("source_unchanged") is True)
        self.check("settings_and_fixed_models", name, manifest.get("config") == expected_config(frozen, arm)
                   and manifest.get("generation_seed") == 42)
        self.snapshot(start, baseline, frozen["device_policy"], name + "/start", cold=True)
        self.snapshot(finish, start, frozen["device_policy"], name + "/finish")
        special = name == mixed.EXCEPTION_SLOT
        self.check("resource_integrity", name + "/cleanup", finish.get("guard_violation") is None
                   and finish.get("cleanup_errors") == [] and cleanup.get("errors") == []
                   and finish.get("resident_models") == [] and finish.get("admitted") is True
                   and (finish.get("status") in {"complete", "complete_with_errors"} or special))
        actual_memory = core.canonical(startup["memory_snapshot"])
        self.check("memory_snapshot", name, sha256(actual_memory + b"\n").hexdigest() == startup["memory_snapshot_sha256"]
                   and actual_memory == reference_memory[0]
                   and startup["events"] == reference_memory[1]
                   and startup["embedding_asset_sha256"] == frozen["embedding_asset_sha256"]
                   and startup["embedding_placement"] == "CPUExecutionProvider, 2 intra-op threads",
                   snapshot_sha256=startup["memory_snapshot_sha256"], setup_operations=len(startup["events"]),
                   stored_records=len(startup["memory_snapshot"]))
        issues = durable_errors(observed, events, cleanup)
        self.check("durable_attempts", name, not issues, issues=issues)
        self.check("resource_integrity", name + "/process_audit", read(directory / "process_audit.json").get("conflicts") == [])
        model_calls, requests = [], []
        for index, row in enumerate(observed):
            context = f"{name}/{row['id']}"
            self.check("workload_and_history", context,
                       all(row.get(k) == cases[row["id"]][k] for k in ("id", "prompt", "scenario_id", "stratum"))
                       and row["sequence_id"] == slot[0] and row["repetition"] == slot[1] and row["arm"] == arm)
            if index == 0:
                self.check("cold_admission", context, row.get("api_ps_before") == [] and row.get("resident_hint_before") is None
                           and row.get("history_before") == [{"role": "system", "content": frozen["config"]["conversation"]["system_prompt"]}])
            elif arm != "replay":
                self.check("workload_and_history", context + "/history", row["history_before"] == observed[index - 1]["history_after"])
            if row["status"] != "ok":
                self.check("durable_attempts", context + "/failed_history", row["history_after"] == row["history_before"],
                           original_status=row["status"], error=row.get("error"))
            self.residency(row.get("api_ps_before"), frozen, arm, context + "/before")
            self.residency(row.get("api_ps_after"), frozen, arm, context + "/after")
            core.audit_calls(row)
            self.check("span_accounting", context, sum(core.account_spans(row).values()) == row["wall_ns"])
            calls = row.get("calls", [])
            audits = [e for e in row["events"] if e["name"] == "residency_audit"]
            self.check("eviction_and_residency", context + "/call_audits", len(audits) == len(calls))
            for ordinal, audit in enumerate(audits):
                states = audit["attributes"].get("models")
                self.residency(states, frozen, arm, context + f"/call{ordinal + 1}")
                if ordinal < len(calls) and calls[ordinal].get("status") == "ok":
                    actual = calls[ordinal].get("actual_model") or calls[ordinal]["requested_model"]
                    self.check("eviction_and_residency", context + f"/retained_call{ordinal + 1}",
                               [state.get("name", state.get("model")) for state in states or []] == [actual])
            chat_spans = [e for e in row["events"] if e["name"] == "backend_chat"]
            for event in chat_spans:
                model_calls.append((event["start_ns"], event["end_ns"], context))
            self.check("nested_loads", context,
                       all(e["name"] != "backend_load" for e in row["events"])
                       and len(chat_spans) == len([h for h in row["http_calls"] if h["endpoint"] == "/api/chat"]),
                       backend_load_ns=sum(c.get("generation", c.get("raw_generation", {})).get("load_duration_ns", 0) for c in calls),
                       note="Backend loading is overlapping metadata, excluded from additive wall component accounting.")
            if index == 0:
                self.check("cold_admission", context + "/first_backend_load", bool(calls)
                           and calls[0].get("generation", calls[0].get("raw_generation", {})).get("load_duration_ns", 0) > 0)
            requests.append(dict(index=row["index"], status=row["status"], generator=core.model_for_turn(row),
                                 route=(row.get("route") or {}).get("decision"), wall_ns=row["wall_ns"],
                                 model_size_source=(row.get("route") or {}).get("model_size_decision_source")))
        all_events = [e for row in observed for e in row["events"]] + cleanup["events"]
        unloads = [e for e in all_events if e["name"] == "unload_request"]
        verified = [e for e in all_events if e["name"] == "eviction_verification"]
        self.check("durable_attempts", name + "/unload_complete",
                   len(unloads) == len([h for h in raw_http if h["endpoint"] == "/api/generate"]))
        self.check("eviction_and_residency", name + "/evictions", len(unloads) == len(verified)
                   and all(u["status"] == v["status"] == "ok" and u["end_ns"] <= v["start_ns"]
                           and u["attributes"]["model"] == v["attributes"]["model"]
                           and v["attributes"].get("residency_after", {}).get("verified_absent") == u["attributes"]["model"]
                           and not any(m.get("name", m.get("model")) == u["attributes"]["model"]
                                       for m in v["attributes"]["residency_after"]["polls"][-1]["models"])
                           for u, v in zip(unloads, verified)), unload_requests=len(unloads), verified_evictions=len(verified))
        self.check("sequence_accounting", name,
                   finish["sequence_total_ns"] == finish["sequence_end_ns"] - finish["sequence_start_ns"]
                   == finish["startup_ns"] + sum(r["wall_ns"] for r in observed) + finish["sequence_gaps_ns"]
                   and finish["request_total_ns"] == sum(r["wall_ns"] for r in observed)
                   and finish["startup_ns"] == startup["wall_ns"] == startup["end_ns"] - startup["start_ns"]
                   and finish["cleanup_ns"] == cleanup["wall_ns"] and finish["sequence_gaps_ns"] >= 0)
        if arm == "adaptive" and sequence["pattern"] == "DDEE":
            self.check("hysteresis", name, [r["generator"] for r in requests] == [LARGE, LARGE, LARGE, SMALL]
                       and requests[2]["model_size_source"] == "lightweight_resident"
                       and requests[3]["model_size_source"] == "lightweight_small", observed_turns=requests)
        self.sequence_details.append(dict(slot=name, freeze_sha256=digest(freeze_path), original_status=finish["status"],
            attempts=len(observed), failures=sum(r["status"] != "ok" for r in observed), requests=requests,
            following_last_turn="unobserved: four-turn sequence ends", sequence_start_ns=finish["sequence_start_ns"],
            sequence_end_ns=finish["sequence_end_ns"], startup_ns=finish["startup_ns"], sequence_gaps_ns=finish["sequence_gaps_ns"],
            model_call_intervals=model_calls, telemetry_samples=self.telemetry(directory, frozen["device_policy"])))

    def inventory_paths(self, roots, extra=()):
        cached, seen = {}, set()
        for path in [p for root in roots for p in root.rglob("*") if p.is_file()] + list(extra):
            if not path.is_file() or str(path.absolute()) in seen:
                continue
            seen.add(str(path.absolute()))
            target = path.resolve()
            key = str(target)
            if key not in cached:
                before = target.stat()
                hashed = digest(target)
                after = target.stat()
                self.check("artifacts_and_conclusion", str(path),
                           (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
                           check="artifact_not_changing_during_audit")
                cached[key] = (hashed, after.st_size)
            hashed, size = cached[key]
            self.inventory.append(dict(path=str(path.absolute()), resolved_path=key, symlink=path.is_symlink(),
                                       sha256=hashed, bytes=size))


def _run(args, audit):
    # Only one small file is inspected before permitting full scans.
    if not (args.run_root / "batch_finish.json").is_file():
        raise ValueError("collection has no terminal batch_finish.json; do not audit during live collection")
    args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    audit.output_created = True
    current, previous = audit.archive(args.freeze), audit.archive(args.previous_freeze)
    workload = read(args.workload)
    slots = expected_slots(workload, current["arm_orders"])
    expected = [slot_name(s) for s in slots]
    discovered = sorted(p.parent.name for p in args.run_root.glob("*/manifest.json"))
    audit.check("coverage", "planned_slots", len(slots) == len(set(expected)) == 144 and set(discovered) == set(expected),
                expected=144, discovered=len(discovered), missing=sorted(set(expected)-set(discovered)), extra=sorted(set(discovered)-set(expected)))
    audit.check("counterbalance", "batch_plan", read(args.run_root / "batch_plan.json")["slots"] == [list(s) for s in slots])
    batch = read(args.run_root / "batch_finish.json")
    audit.check("coverage", "batch_terminal_status", batch.get("status") == "complete", original_status=batch.get("status"), failure=batch.get("failure"))
    audit.check("counterbalance", "batch_completed_order", [r["slot"] for r in batch.get("completed", [])] == expected)
    reuse = read(args.run_root / "reuse_manifest.json")
    reused = reuse["reused_sequences"]
    audit.check("whole_sequence_reuse", "prefix", [p["directory"] for p in reused] == expected[:22]
                and sum(p["attempts_retained"] for p in reused) == 88 and reuse["no_answered_request_retried"] and reuse["no_tail_splicing"])
    for proof in reused:
        original = args.previous_root / proof["directory"]
        linked = args.run_root / proof["directory"]
        for name, expected_hash in proof["file_sha256"].items():
            old, new = original / name, linked / name
            audit.check("whole_sequence_reuse", str(new), new.is_symlink() and new.resolve() == old.resolve()
                        and digest(old) == expected_hash and digest(new) == expected_hash)
    for module in (core, mixed):
        path = Path(module.__file__).resolve()
        relative = str(path.relative_to(ROOT))
        audit.check("source_and_freeze", "loaded_helper/" + relative,
                    digest(path) == current["source_sha256"][relative])
    loader = mixed.MixedFreezeLoader(args)
    merged = audit.step("mixed_freeze_and_replay", lambda: loader(args.run_root, args.workload, args.freeze))
    if merged is not None:
        audit.check("source_and_freeze", "mixed_freeze_analysis_errors", not merged[-1], errors=merged[-1])
        audit.check("coverage", "turn_denominators", len(merged[3]) == 576
                    and sum(r["arm"] == "replay" for r in merged[3]) == 144,
                    attempted=len(merged[3]), main=sum(r["arm"] != "replay" for r in merged[3]),
                    replay=sum(r["arm"] == "replay" for r in merged[3]), statuses=dict(Counter(r["status"] for r in merged[3])))
        checks = loader.proof.get("diagnostic_replay_input_checks", [])
        audit.check("replay_fidelity", "all144_replay_turns", len(checks) == 144 and all(c["status"] == "exact_requests_verified" for c in checks))
        audit.provenance["mixed_freeze"] = loader.proof
    baseline = read(args.previous_root / "before.json")
    reference = read(args.previous_root / expected[0] / "startup.json")
    memory = (core.canonical(reference["memory_snapshot"]), reference["events"])
    cases = {c["id"]: c for c in workload["execution_cases"]}
    sequences = {s["id"]: s for s in workload["sequences"]}
    for position, slot in enumerate(slots):
        name = slot_name(slot)
        if name not in discovered:
            continue
        frozen, path = (previous, args.previous_freeze) if position < 22 else (current, args.freeze)
        audit.step(name, lambda name=name, slot=slot, frozen=frozen, path=path:
                   audit.sequence(args.run_root / name, slot, sequences[slot[0]], frozen, path, baseline, cases, memory))
    intervals = sorted(i for s in audit.sequence_details for i in s["model_call_intervals"])
    overlaps = [(a[2], b[2]) for a, b in zip(intervals, intervals[1:]) if a[1] > b[0]]
    audit.check("resource_integrity", "serialized_inference", not overlaps, overlapping_call_pairs=overlaps, calls=len(intervals))
    commands, observed_launches = [], []
    for version, root, freeze_path in (("v1", args.previous_root, args.previous_freeze), ("v2", args.run_root, args.freeze)):
        final = read(root / "batch_finish.json")
        audit.snapshot(final["snapshot"], baseline, current["device_policy"], version + "/batch_finish")
        audit.check("resource_integrity", version + "/batch_no_residents", final["snapshot"].get("resident_models") == [])
        configuration = final["server_configuration"]
        audit.check("resource_integrity", version + "/server_configuration",
                    configuration["service_query_exit_code"] == 0
                    and configuration["selected_environment"] == previous["server_configuration"]["selected_environment"]
                    and normalized_swap_topology(configuration["swap_topology"]) == normalized_swap_topology(previous["server_configuration"]["swap_topology"]))
        last_preflight = {}
        for event in rows(root / "scheduler.jsonl"):
            if event.get("kind") == "preflight":
                audit.check("resource_integrity", version + "/scheduler/" + event["slot"], event["audit"]["conflicts"] == [])
                audit.snapshot(event["snapshot"], baseline, current["device_policy"], version + "/scheduler/" + event["slot"])
                last_preflight[event["slot"]] = event["snapshot"]
            elif event.get("kind") == "launch":
                command = event["command"]
                observed_launches.append(event["slot"])
                commands.append(dict(version=version, **event))
                preflight = last_preflight[event["slot"]]
                audit.snapshot(preflight, baseline, current["device_policy"], version + "/launch/" + event["slot"], cold=True)
                audit.check("counterbalance", version + "/launch/" + event["slot"],
                            max(preflight["temperatures_c"].values()) < 54
                            and "--lock-fd" in command and command[command.index("--freeze") + 1] == str(freeze_path.resolve()))
    audit.check("counterbalance", "actual_launch_order", observed_launches == expected,
                actual_count=len(observed_launches), unique_count=len(set(observed_launches)))
    audit.provenance["actual_session_commands"] = commands
    audit.provenance["batch_records"] = {"v1": read(args.previous_root / "batch_finish.json"), "v2": batch}
    audit.provenance["audit_command"] = [sys.executable, *sys.argv]
    audit.provenance["audit_source_sha256"] = digest(Path(__file__))
    audit.inventory_paths([args.run_root, args.previous_root, args.freeze.parent, args.previous_freeze.parent],
                          [args.workload, Path(__file__), HERE / "report_acceptance.json", *HERE.glob("*.log")])
    statuses = Counter(c["status"] for c in audit.checks)
    categories = {name: {status: sum(c["category"] == name and c["status"] == status for c in audit.checks)
                        for status in ("pass", "fail")} for name in sorted({c["category"] for c in audit.checks})}
    write(args.output_dir / "checks.json", audit.checks)
    write(args.output_dir / "artifact_hash_inventory.json", audit.inventory)
    write(args.output_dir / "sequence_details.json", audit.sequence_details)
    write(args.output_dir / "command_provenance.json", audit.provenance)
    summary = dict(status="pass" if not statuses["fail"] else "fail", checks=dict(statuses), categories=categories,
        generated_at=datetime.now(timezone.utc).isoformat(), sequence_records=len(audit.sequence_details),
        inventory_paths=len(audit.inventory), audit_source_sha256=digest(Path(__file__)),
        scope="Recorded collection integrity only; no new inference, device queries or artifact rewriting.",
        limitations=["Independent human correctness review and final report conclusions are separate acceptance checks.",
                     "Recorded allocation does not prove exact CPU/GPU compute placement.",
                     "Monitoring is sampled; no claim of continuous resource observability.",
                     "Initial model/process state is cold; operating-system file caches were retained.",
                     "Original v1 final-turn interrupted status and failed answer are unchanged; exact documented whole-sequence eligibility exception is explicit in provenance."])
    acceptance = read(HERE / "report_acceptance.json")
    write(args.output_dir / "acceptance_integrity_status.json", [
        {"id": item["id"], "criterion": item["criterion"],
         "status": ("fail" if categories[item["id"]]["fail"] else "pass")
                   if item["id"] in categories else "not_audited_here",
         "scope": "Integrity evidence only; report presentation and answer correctness require separate review."}
        for item in acceptance["checks"]])
    write(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "pass" else 1



def run(args):
    audit = Audit()
    try:
        return _run(args, audit)
    except Exception as error:
        audit.check("audit_execution", "terminal_exception", False,
                    error=type(error).__name__, message=str(error))
        summary = {"status": "fail", "error": type(error).__name__, "message": str(error),
                   "completed_checks": len(audit.checks),
                   "scope": "Incomplete offline audit; this is not a passing collection certificate."}
        if audit.output_created:
            # Preserve diagnostics even if a malformed/missing artifact aborts
            # the audit. Input files are never rewritten or statuses repaired.
            write(args.output_dir / "checks.json", audit.checks)
            write(args.output_dir / "partial_sequence_details.json", audit.sequence_details)
            write(args.output_dir / "partial_command_provenance.json", audit.provenance)
            write(args.output_dir / "partial_artifact_hash_inventory.json", audit.inventory)
            write(args.output_dir / "summary.json", summary)
        print(json.dumps(summary, indent=2))
        return 1


def self_test():
    event = dict(id=1, parent_id=None, name="complete_request", clock="monotonic_ns",
                 start_ns=1, end_ns=3, wall_ns=2, status="ok", attributes={})
    observed = [dict(id="case", index=1, events=[event])]
    durable = [dict(kind="turn_attempt", id="case", index=1),
               dict(event, event="span_start", index=1, status="running", end_ns=None, wall_ns=None),
               dict(event, event="span_end", index=1)]
    assert durable_errors(observed, durable, {"events": []}) == []
    assert durable_errors(observed, durable[:-1], {"events": []})
    assert durable_errors(observed, durable + [durable[-1]], {"events": []})
    assert normalized_swap_topology("Header\n/dev/zram0 partition 100 30 5\n") == [["/dev/zram0", "partition", 100, 5]]
    assert normalized_swap_topology("Header\n/dev/zram0 partition 100 40 5\n") == [["/dev/zram0", "partition", 100, 5]]
    value = {"config": {"ollama": {"small_model": SMALL, "large_model": LARGE,
             "general_large_model": LARGE, "request_timeout_seconds": 60, "large_request_timeout_seconds": 120}}}
    assert expected_config(value, "large")["ollama"]["request_timeout_seconds"] == 120
    assert value["config"]["ollama"]["small_model"] == SMALL
    print("PASS: synthetic durable-span corruption, topology normalization and fixed-config checks; no collection files scanned.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--run-root", type=Path, default=HERE / "run_v2")
    parser.add_argument("--previous-root", type=Path, default=HERE / "run_v1")
    parser.add_argument("--freeze", type=Path, default=HERE / "frozen_v2/freeze.json")
    parser.add_argument("--previous-freeze", type=Path, default=HERE / "frozen_v1/freeze.json")
    parser.add_argument("--workload", type=Path, default=HERE / "frozen_v2/workload.json")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.output_dir is None:
        parser.error("--output-dir is required for final audit")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
