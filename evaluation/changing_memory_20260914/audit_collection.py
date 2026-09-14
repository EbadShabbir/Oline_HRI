"""Independent, read-only post-collection integrity audit; never performs inference.

Integrity checks establish trace coverage and provenance, not answer quality.
Observed storage/retrieval/generation/validation failures remain observations.
Run only after collection finishes; output must be outside the sealed inputs.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("logical timestamps must include a timezone")
    return result


def eligible(record, time):
    now = instant(time)
    return (record.get("status") == "active" and record.get("consent_status") == "confirmed"
            and instant(record["valid_from"]) <= now
            and all(record.get(key) is None or now < instant(record[key])
                    for key in ("valid_until", "retention_until")))


def replace_strings(value, aliases):
    if isinstance(value, str):
        for old, new in aliases.items():
            value = value.replace(old, new)
        return value
    if isinstance(value, list):
        return [replace_strings(item, aliases) for item in value]
    if isinstance(value, dict):
        return {key: replace_strings(item, aliases) for key, item in value.items()}
    return value


HISTORY_EXPOSURE_LIMITATION = (
    "Literal old-value matching is a case-insensitive substring lower bound on exposure, "
    "not evidence of semantic absence, memory authorization, or answer correctness. "
    "Equivalent times, names, paraphrases and alternate formatting may not match. "
    "Forwarding witnesses intersect actual generation messages with history_before by exact "
    "role/content; system messages, the final current-request message and personal-memory "
    "evidence envelopes are excluded. Matching duplicate history indices identify equivalent "
    "candidate occurrences, not the unique originating turn."
)


def history_exposure(row, original_statement, original_value):
    """Separate exact original-turn persistence from later literal value echoes."""
    history = [(index, message) for index, message in enumerate(row.get("history_before", []))
               if message.get("role") in {"user", "assistant"}]
    needle = original_value.casefold()

    def features(message):
        content = message.get("content", "")
        return dict(exact_original_statement=message.get("role") == "user" and content == original_statement,
                    literal_original_value=bool(needle) and needle in content.casefold())

    present = [dict(history_before_index=index, role=message["role"], content=message["content"],
                    **features(message)) for index, message in history if any(features(message).values())]
    forwarded = []
    generation_calls = []
    for call_index, call in enumerate(row.get("calls", [])):
        if call.get("purpose") != "generation":
            continue
        generation_calls.append(call_index)
        # The production request ends with the current user/evidence request.
        # Its earlier messages may contain retained history; never count the tail.
        for message_index, message in enumerate(call.get("messages", [])[:-1]):
            if message.get("role") not in {"user", "assistant"}:
                continue
            if message.get("content", "").startswith("PERSONAL_MEMORY_DATA="):
                continue
            candidates = [index for index, previous in history
                          if (previous.get("role"), previous.get("content")) ==
                             (message.get("role"), message.get("content"))]
            matched = features(message)
            if candidates and any(matched.values()):
                forwarded.append(dict(call_index=call_index, generation_message_index=message_index,
                    matching_history_before_indices=candidates, role=message["role"],
                    content=message["content"], **matched))
    exact_present = any(w["exact_original_statement"] for w in present)
    literal_present = any(w["literal_original_value"] for w in present)
    literal_forwarded = any(w["literal_original_value"] for w in forwarded)
    return dict(exact_original_statement_present=exact_present,
                exact_original_statement_forwarded=any(w["exact_original_statement"] for w in forwarded),
                literal_original_value_present=literal_present,
                literal_original_value_forwarded=literal_forwarded,
                literal_value_present_without_exact_statement=literal_present and not exact_present,
                literal_value_forwarded_without_exact_statement=literal_forwarded and not exact_present,
                generation_call_indices=generation_calls,
                history_witnesses=present, forwarded_history_witnesses=forwarded)


class Audit:
    def __init__(self):
        self.checks = Counter()
        self.violations = []
        self.observations = []
        self.counts = Counter()
        self.models = Counter()
        self.resources = []
        self.branches = []
        self.http_links = []
        self.history_witnesses = []
        self.history_counts = {}

    def history(self, row, ledger, original_statement):
        exposure = history_exposure(row, original_statement, ledger["original_subject_value"])
        self.history_witnesses.append(dict(checkpoint_id=row["checkpoint_id"], branch_id=row["branch_id"],
            history_mode=ledger["history_mode"], after_restart=ledger["after_restart"], **exposure))
        groups = ["all_scored_checkpoints", "history_mode=" + ledger["history_mode"],
                  "branch=" + ledger["branch"]]
        if ledger["after_restart"]:
            groups.append("after_restart")
        for group in groups:
            counts = self.history_counts.setdefault(group, Counter())
            counts["checkpoints"] += 1
            counts["checkpoints_with_generation_call"] += bool(exposure["generation_call_indices"])
            for key, value in exposure.items():
                if type(value) is bool:
                    counts[key] += value

    def check(self, condition, code, where, *, expected=None, observed=None):
        self.checks[code] += 1
        if not condition:
            self.violations.append(dict(code=code, where=str(where), expected=expected, observed=observed))
        return bool(condition)

    def observe(self, condition, stage, code, where, **details):
        if not condition:
            self.observations.append(dict(stage=stage, code=code, where=str(where), **details))

    def jsonl(self, path):
        rows = []
        if not self.check(Path(path).is_file(), "artifact_exists", path):
            return rows
        for number, line in enumerate(Path(path).read_text().splitlines(), 1):
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                self.check(False, "jsonl_complete_line", f"{path}:{number}", observed=str(error))
        return rows

    def seal(self, directory):
        path = directory / "seal.json"
        if not self.check(path.is_file(), "sealed_directory", directory):
            return
        manifest = read_json(path)["sha256"]
        actual = {str(p.relative_to(directory)) for p in directory.rglob("*")
                  if p.is_file() and p != path}
        self.check(actual == set(manifest), "seal_file_set", directory,
                   expected=sorted(set(manifest) - actual), observed=sorted(actual - set(manifest)))
        for name, expected in manifest.items():
            file = directory / name
            self.check(file.is_file() and digest(file) == expected, "seal_file_hash", file)
        self.check(not directory.stat().st_mode & 0o222, "sealed_directory_readonly", directory)
        for file in directory.rglob("*"):
            self.check(not file.stat().st_mode & 0o222, "sealed_artifact_readonly", file)

    def http(self, path, allowed_models, config):
        """Reassemble the exact received bytes for each serialized HTTP request."""
        requests, active = [], None
        for number, row in enumerate(self.jsonl(path), 1):
            where = f"{path}:{number}"
            if row.get("event") == "http_start":
                self.check(active is None, "serialized_http_start", where)
                active = {"start": row, "chunks": [], "where": where}
            elif row.get("event") == "http_received_bytes":
                if not self.check(active is not None, "bytes_have_request", where):
                    continue
                try:
                    data = base64.b64decode(row["bytes_base64"], validate=True)
                    self.check(row["offset"] == sum(map(len, active["chunks"])), "byte_chunk_offset", where)
                    active["chunks"].append(data)
                except (ValueError, KeyError) as error:
                    self.check(False, "valid_received_bytes", where, observed=str(error))
            elif "endpoint" in row and "status" in row:
                if not self.check(active is not None, "http_completion_has_start", where):
                    continue
                self.check((active["start"]["endpoint"], active["start"]["body"]) == (row["endpoint"], row["body"]),
                           "http_start_completion_match", where)
                data = b"".join(active["chunks"])
                entry = dict(row, bytes_sha256=sha256(data).hexdigest(), received_bytes=len(data), where=where)
                if row["status"] == "ok":
                    try:
                        decoded = json.loads(data)
                        self.check(decoded == row["response"], "received_bytes_match_parsed_response", where)
                    except (ValueError, UnicodeDecodeError) as error:
                        self.check(False, "received_bytes_decode", where, observed=str(error))
                else:
                    self.observe(False, "transport", "recorded_http_failure", where,
                                 error=row.get("error"), received_bytes=len(data))
                if row["endpoint"] == "/api/chat":
                    body = row["body"]
                    fields = body.get("format", {}).get("properties", {})
                    purpose = "generation" if "speech" in fields else "memory_selector" if "memory_required" in fields else "compute_selector"
                    entry["purpose"] = purpose
                    expected_options = dict(num_ctx=config["context_length"], num_predict=config["max_output_tokens"],
                                            temperature=config["temperature"], seed=42)
                    self.check(body.get("options") == expected_options, "actual_chat_options", where,
                               expected=expected_options, observed=body.get("options"))
                    self.check(body.get("think") is False and body.get("stream") is False,
                               "actual_chat_nonstream_no_thinking", where)
                    self.check(body.get("model") in allowed_models, "requested_installed_model", where,
                               observed=body.get("model"))
                    encoded = json.dumps(body)
                    self.check(not any(key in encoded for key in ("expected_value", "forbidden_values", "authorized_state", "required_behavior")),
                               "no_oracle_fields_in_model_input", where)
                    if row["status"] == "ok":
                        self.check(row["response"].get("model") == body.get("model"), "returned_requested_model", where)
                    self.models[(purpose, body.get("model"))] += 1
                    self.counts["chat_http_requests"] += 1
                requests.append(entry)
                active = None
        self.check(active is None, "http_request_completion_preserved", path)
        return requests

    def resource(self, directory, frozen, *, admission_only=False):
        start_path, finish_path = directory / "start.json", directory / "finish.json"
        if not self.check(start_path.is_file() and finish_path.is_file(), "resource_captures_present", directory):
            return
        start, finish_record = read_json(start_path), read_json(finish_path)
        finish, baseline = finish_record.get("snapshot", {}), frozen["host"]["snapshot"]
        self.observe(not finish_record.get("cleanup_errors"), "resource", "cleanup_errors", directory,
                     errors=finish_record.get("cleanup_errors"))
        self.observe(not finish_record.get("guard_violation"), "resource", "guard_violation", directory,
                     violation=finish_record.get("guard_violation"))
        for label, snapshot in (("start", start), ("finish", finish)):
            for key in ("boot_id", "power_mode", "thermal_trip_events"):
                self.observe(snapshot.get(key) == baseline.get(key), "resource", "frozen_invariant_changed",
                             f"{directory}/{label}", invariant=key, expected=baseline.get(key), actual=snapshot.get(key))
            self.observe(snapshot.get("memory", {}).get("swap_total_kib") == baseline["memory"]["swap_total_kib"],
                         "resource", "swap_capacity_changed", f"{directory}/{label}")
            self.observe(snapshot.get("resident_models") == [], "resource", "model_resident_at_boundary",
                         f"{directory}/{label}", actual=snapshot.get("resident_models"))
        telemetry = self.jsonl(directory / "telemetry.jsonl") if not admission_only else []
        self.observe(bool(telemetry) or admission_only, "resource", "missing_telemetry", directory)
        temperatures = [max(row["temperatures_c"].values()) for row in telemetry if row.get("temperatures_c")]
        maximum = max(temperatures, default=None)
        policy = frozen["device_policy"]
        self.observe(admission_only or maximum is not None and maximum < policy["max_runtime_temperature_c_exclusive"],
                     "resource", "observed_runtime_temperature_violation", directory, maximum=maximum)
        self.resources.append(dict(fragment=str(directory), status=finish_record.get("status"),
                                   cleanup_errors=finish_record.get("cleanup_errors"), samples=len(telemetry),
                                   maximum_temperature_c=maximum, admission_only=admission_only))

    def answer(self, row, ledger, requests, consumed, fragment):
        where = f"{fragment}/{row.get('checkpoint_id') or row.get('op', {}).get('id')}"
        self.counts["answer_rows"] += 1
        self.counts["answer_status_" + row.get("status", "missing")] += 1
        self.check(row.get("validation_decision") == ("accepted" if row.get("status") == "delivered" else "rejected_or_pipeline_failure"),
                   "validation_delivery_link", where)
        if row.get("status") == "delivered":
            self.check(row.get("delivered_answer") == row.get("response", {}).get("speech")
                       and isinstance(row.get("delivered_answer"), str) and bool(row["delivered_answer"]),
                       "final_delivered_answer_link", where)
        else:
            self.check(row.get("delivered_answer") is None, "withheld_has_no_delivered_answer", where)
            self.observe(False, "validation_or_pipeline", "withheld_or_interrupted_answer", where,
                         status=row.get("status"), error=row.get("error"), message=row.get("message"))
        raw = [c.get("raw_generation", c.get("generation", {})).get("content")
               for c in row.get("calls", []) if c.get("purpose") == "generation"]
        self.check(row.get("raw_model_answers") == raw, "raw_answer_call_link", where)
        last_generations = [c["generation"] for c in row.get("calls", []) if c.get("purpose") == "generation" and "generation" in c]
        if row.get("status") == "delivered":
            self.check(bool(last_generations) and row.get("generation") == last_generations[-1], "delivered_generation_link", where)
        for number, call in enumerate(row.get("calls", [])):
            call_where = f"{where}/call{number}"
            aliases = {actual: f"memory_ref_{index}" for index, actual in enumerate(
                call.get("response_format", {}).get("properties", {}).get("memory_used", {}).get("items", {}).get("enum", []), 1)}
            messages = replace_strings(call.get("messages", []), aliases)
            schema = replace_strings(call.get("response_format"), aliases)
            candidates = [(i, request) for i, request in enumerate(requests)
                          if i not in consumed and request["endpoint"] == "/api/chat"
                          and request["body"].get("model") == call.get("requested_model")
                          and request["body"].get("messages") == messages and request["body"].get("format") == schema]
            if not candidates and call.get("status") == "error" and not call.get("raw_generation") and not call.get("generation"):
                self.observe(False, "pre_transport", "model_call_failed_before_http", call_where,
                             error=call.get("error"), message=call.get("message"))
                continue
            if self.check(bool(candidates), "model_call_has_http_request", call_where):
                index, request = candidates[0]
                consumed.add(index)
                if call.get("raw_chat_payload") is not None:
                    self.check(call["raw_chat_payload"] == request.get("response"), "call_raw_payload_byte_link", call_where)
                if call.get("raw_generation") is not None:
                    self.check(call["raw_generation"].get("content") == request.get("response", {}).get("message", {}).get("content"),
                               "raw_generation_received_content", call_where)
                self.http_links.append(dict(checkpoint_id=row.get("checkpoint_id"), operation_id=row["op"]["id"],
                                            purpose=call.get("purpose"), request=request["where"],
                                            bytes_sha256=request["bytes_sha256"], received_bytes=request["received_bytes"]))
        if ledger is None:
            return
        self.check(row["logical_time"] == ledger["logical_time"], "checkpoint_expected_clock", where)
        self.check(row["op"].get("question") == ledger["question"], "checkpoint_authored_question", where)
        expected_state = {r["canonical_text"] for r in ledger["authorized_state"]}
        permitted = {r["canonical_text"] for r in ledger["permitted_evidence"]}
        current = [r for r in row["database_before"].get("memory_item", []) if eligible(r, row["logical_time"])]
        self.observe({r["canonical_text"] for r in current} == expected_state, "storage", "authorized_state_mismatch", where,
                     expected=sorted(expected_state), actual=sorted(r["canonical_text"] for r in current))
        for call in row.get("retrieval_calls", []):
            self.check(call["logical_time"] == row["logical_time"], "shared_retrieval_clock", where)
            self.observe(all(eligible(m["memory"], row["logical_time"]) and m["memory"]["canonical_text"] in expected_state
                             for m in call.get("matches", [])), "retrieval", "ineligible_retrieved_record", where)
        for check in row.get("snapshot_checks", []):
            self.check(check["logical_time"] == row["logical_time"], "shared_validation_clock", where)
        for envelope in row.get("supplied_evidence_envelopes", []):
            self.observe(all(r["canonical_text"] in permitted for r in envelope.get("records", [])),
                         "retrieval_filtering", "unpermitted_supplied_evidence", where)


def audit_collection(freeze_dir, run_dir, repository):
    audit = Audit()
    audit.seal(freeze_dir)
    audit.seal(run_dir)
    frozen = read_json(freeze_dir / "freeze.json")
    runtime = read_json(freeze_dir / "runtime.json")
    ledger = read_json(freeze_dir / "expected_ledger.json")
    planned = {row["checkpoint_id"]: row for row in ledger["checkpoints"]}
    audit.check(len(planned) == len(ledger["checkpoints"]) == 288, "planned_288_unique_checkpoints", freeze_dir)
    audit.check(len(runtime["branches"]) == 36 and len({b["scenario_id"] for b in runtime["branches"]}) == 12,
                "planned_12_scenarios_36_branches", freeze_dir)
    for scenario in {b["scenario_id"] for b in runtime["branches"]}:
        branches = [b for b in runtime["branches"] if b["scenario_id"] == scenario]
        subjects = [next(op for op in b["operations"] if op["op"] == "remember" and op.get("record_key") == "subject")
                    for b in branches]
        audit.check({b["branch"] for b in branches} == {"correction", "deletion", "expiry"}, "independent_branch_types", scenario)
        audit.check(len({(op["text"], op["time"], op["kind"], op.get("event_time")) for op in subjects}) == 1,
                    "equivalent_initial_subject_fact", scenario)
    for rel, expected in frozen["source_sha256"].items():
        for label, base in (("frozen", freeze_dir / "source"), ("current", repository)):
            path = base / rel
            audit.check(path.is_file() and digest(path) == expected, label + "_source_hash", path)
    for name, expected in read_json(freeze_dir / "preflight_review.json")["sha256"].items():
        audit.check((freeze_dir / name).is_file() and digest(freeze_dir / name) == expected, "reviewed_artifact_hash", name)
    generation = frozen["config"]["generation"]
    audit.check(generation == dict(context_length=2048, max_output_tokens=192, temperature=0.0, thinking=False),
                "frozen_generation_options", freeze_dir, observed=generation)
    audit.check(frozen["generation_seed"] == 42 and frozen["routing_policy"] == "llm (CLI default)", "frozen_adaptive_policy", freeze_dir)
    allowed_models = set(frozen["models"])
    audit.check(allowed_models == {"qwen3:0.6b", "qwen3:1.7b"}, "frozen_installed_model_pair", freeze_dir)
    found_checkpoints, all_database_ids, all_process_ids, all_memory_ids = [], set(), set(), set()
    fragment_count = scheduled_segments = 0
    for branch in runtime["branches"]:
        branch_dir = run_dir / branch["branch_id"]
        audit.seal(branch_dir)
        database = branch_dir / "memory.sqlite3"
        if not audit.check(database.is_file(), "persistent_branch_database", branch_dir):
            continue
        stat = database.stat()
        file_id = (stat.st_dev, stat.st_ino)
        audit.check(file_id not in all_database_ids, "independent_database_inode", database)
        all_database_ids.add(file_id)
        previous_state, branch_rows, operation_events, starts = None, [], [], []
        branch_ids, process_ids = set(), []
        scheduled_processes = {}
        restart_index = next(i for i, op in enumerate(branch["operations"]) if op["op"] == "restart")
        disclosure = next(op["text"] for op in branch["operations"] if op["op"] == "disclose")
        for segment in ("initial", "restart"):
            ops = branch["operations"][:restart_index] if segment == "initial" else branch["operations"][restart_index + 1:]
            launches = sorted(branch_dir.glob(segment + "*_launch.json"), key=lambda p: ("continuation" in p.name, p.name))
            if not audit.check(bool(launches), "scheduled_segment_exists", f"{branch_dir}/{segment}"):
                continue
            scheduled_segments += 1
            next_offset = 0
            for launch_path in launches:
                launch = read_json(launch_path)
                directory = branch_dir / launch_path.name.removesuffix("_launch.json")
                fragment_count += 1
                audit.seal(directory)
                finish = read_json(directory / "finish.json")
                admission_only = (not (directory / "process.json").exists()
                                  and finish["next_offset"] == launch.get("start_offset", 0))
                audit.resource(directory, frozen, admission_only=admission_only)
                if admission_only:
                    audit.check(finish.get("error", {}).get("type") == "SafetyGateError",
                                "pre_inference_rejection_is_recorded_guard_failure", directory,
                                observed=finish.get("error"))
                    audit.check(not any((directory / name).exists() for name in ("http.jsonl", "answers.jsonl", "events.jsonl")),
                                "pre_inference_rejection_has_no_model_or_operation_events", directory)
                    audit.check(launch.get("start_offset", 0) == next_offset, "admission_rejection_does_not_advance_schedule", directory)
                    audit.counts["zero_operation_worker_admission_rejections"] += 1
                    audit.observations.append(dict(stage="admission", code="preserved_zero_inference_worker_rejection",
                                                   where=str(directory), launch_pid=launch["pid"], error=finish.get("error")))
                    process_ids.append(launch["pid"])
                    continue
                process = read_json(directory / "process.json")
                process_id = (process["boot_id"], process["pid"], process["process_start_ticks"])
                audit.check(process_id not in all_process_ids, "fresh_worker_process_identity", directory)
                all_process_ids.add(process_id)
                process_ids.append(process["pid"])
                scheduled_processes.setdefault(segment, process_id)
                audit.check(launch["pid"] == process["pid"], "launched_actual_worker_pid", directory)
                audit.check(launch.get("start_offset", 0) == next_offset, "continuation_offset_no_replay", directory)
                events = audit.jsonl(directory / "events.jsonl")
                rows = audit.jsonl(directory / "answers.jsonl")
                initial_state = read_json(directory / "state_initial.json") if (directory / "state_initial.json").exists() else None
                if previous_state is not None:
                    restored = [event for event in events if event.get("event") == "history_restored_after_process_restart"]
                    audit.check(len(restored) == 1, "restored_history_event", directory)
                    if restored:
                        audit.check(restored[0]["exact_history"] == previous_state["history"], "exact_history_across_processes", directory)
                    if initial_state:
                        for key in ("ids", "history", "logical_time", "saved_snapshot"):
                            audit.check(initial_state[key] == previous_state[key], "restored_" + key, directory)
                requests = audit.http(directory / "http.jsonl", allowed_models, generation)
                consumed = set()
                for row in rows:
                    checkpoint = row.get("checkpoint_id")
                    if checkpoint:
                        found_checkpoints.append(checkpoint)
                        audit.check(checkpoint in planned, "checkpoint_is_planned", directory, observed=checkpoint)
                    audit.answer(row, planned.get(checkpoint), requests, consumed, directory)
                    audit.check(row["process"]["pid"] == process["pid"], "answer_process_identity", directory)
                    ident = row["database_identity"]
                    audit.check((ident["device"], ident["inode"]) == file_id, "same_database_inode_all_checkpoints", directory)
                    is_fresh = row["op"].get("history") == "fresh"
                    history_has_original = any(m["role"] == "user" and m["content"] == disclosure for m in row["history_before"])
                    audit.check(row.get("original_disclosure_present_in_history") == history_has_original,
                                "recorded_history_presence_truthful", row["op"]["id"])
                    if checkpoint in planned:
                        audit.history(row, planned[checkpoint], disclosure)
                    if is_fresh:
                        audit.check(not history_has_original and len(row["history_before"]) == 1, "fresh_history_is_empty", row["op"]["id"])
                    elif checkpoint and not checkpoint.endswith("_prestore"):
                        audit.counts["retained_history_expected"] += 1
                        audit.counts["retained_history_with_original_disclosure"] += int(history_has_original)
                        audit.observe(history_has_original, "history", "original_disclosure_missing_in_retained_history", checkpoint)
                for index, request in enumerate(requests):
                    if request["endpoint"] == "/api/chat":
                        audit.check(index in consumed, "http_chat_assigned_to_answer_attempt", request["where"])
                branch_rows.extend(rows)
                operation_events.extend(e for e in events if e.get("event") == "operation")
                fragment_starts = [e for e in events if e.get("event") in ("operation_start", "question_start")]
                starts.extend(fragment_starts)
                expected_slice = ops[next_offset:finish["next_offset"]]
                audit.check([e["op"] for e in fragment_starts] == expected_slice, "authored_operation_sequence", directory)
                for row in fragment_starts:
                    audit.check(row["logical_time"] == row["op"]["time"], "shared_operation_clock", row["op"]["id"])
                next_offset = finish["next_offset"]
                states = sorted(directory.glob("state_after_*.json"))
                final_state = directory / "state.json"
                if not final_state.exists():
                    final_state = states[-1] if states else directory / "state_initial.json"
                if final_state.exists():
                    previous_state = read_json(final_state)
                    branch_ids.update(previous_state["ids"].values())
                for event in events:
                    if event.get("event") == "automatic_retention_purge" and event.get("removed_ids"):
                        audit.counts["purged_record_ids"] += len(event["removed_ids"])
                        audit.observe(branch["branch"] == "expiry", "storage", "purge_outside_expiry_branch", directory)
            audit.check(next_offset == len(ops), "scheduled_segment_operation_coverage", f"{branch_dir}/{segment}",
                        expected=len(ops), observed=next_offset)
        audit.check(scheduled_processes.get("initial") != scheduled_processes.get("restart"), "real_scheduled_process_restart", branch_dir)
        operation_ids = [e["op"]["id"] for e in starts]
        expected_ids = [op["id"] for op in branch["operations"] if op["op"] != "restart"]
        audit.check(operation_ids == expected_ids, "complete_independent_branch_schedule", branch_dir)
        completed_ids = [e["op"]["id"] for e in operation_events] + [row["op"]["id"] for row in branch_rows]
        audit.check(Counter(completed_ids) == Counter(expected_ids), "all_operations_have_terminal_records", branch_dir,
                    expected=sorted((Counter(expected_ids) - Counter(completed_ids)).elements()),
                    observed=sorted((Counter(completed_ids) - Counter(expected_ids)).elements()))
        audit.counts["operations_started"] += len(starts)
        audit.counts["operations_finished"] += len(operation_events) + len(branch_rows)
        original = None
        for event in operation_events:
            op, where = event["op"], event["op"]["id"]
            if event.get("status") != "ok":
                audit.observe(False, "storage_or_probe", "failed_operation", where, error=event.get("error"))
                continue
            before, after = event["database_before"].get("memory_item", []), event["database_after"].get("memory_item", [])
            if op["op"] in ("remember", "correct", "forget"):
                audit.counts["mutation_" + op["op"]] += 1
                ack = event.get("acknowledgement", "")
                audit.check(bool(ack) and {"remember": "remembered", "correct": "corrected", "forget": "forgotten"}[op["op"]] in ack,
                            "actual_mutation_acknowledgement", where)
                audit.check(bool(event.get("explicit_confirmation")), "explicit_authored_mutation_authorization", where)
                if op["op"] != "forget":
                    result = event["result"]
                    branch_ids.add(result["id"])
                    audit.observe(result["canonical_text"] == op["text"] and result["id"] in ack,
                                  "storage", "mutation_result_matches_instruction", where)
                    audit.observe(len(after) == len(before) + 1, "storage", "mutation_row_delta", where)
                    audit.observe(instant(result["retention_until"]) == instant(result["created_at"]) + timedelta(days=runtime["logical_clock"]["retention_days"])
                                  if op["op"] == "remember" else True, "storage", "configured_retention_deadline", where)
                    if op.get("record_key") == "subject":
                        original = result
                    if op["op"] == "correct" and original:
                        audit.observe(result["supersedes_id"] == original["id"] and result["retention_until"] == original["retention_until"],
                                      "storage", "replacement_chain_or_retention", where)
                else:
                    audit.observe(len(after) < len(before), "storage", "forget_removed_no_rows", where)
            if op["op"] in ("cache_probe", "snapshot_probe"):
                snapshot = event.get("retained_snapshot", [])
                audit.observe(bool(snapshot), "retrieval_snapshot", "empty_snapshot_probe", where)
                if snapshot:
                    actual_ids = {r["id"] for r in after if eligible(r, event["logical_time"])}
                    expected_current = all(r["id"] in actual_ids and eligible(r, event["logical_time"]) for r in snapshot)
                    audit.observe(event.get("snapshot_current") is expected_current, "retrieval_snapshot", "stale_snapshot_currentness_error", where,
                                  expected=expected_current, actual=event.get("snapshot_current"))
        if starts:
            audit.check(starts[0]["database_before"].get("memory_item", []) == [], "new_branch_initial_database_empty", branch_dir)
            audit.check(starts[0]["database_before"].get("memory_audit", []) == [], "new_branch_initial_audit_empty", branch_dir)
        with sqlite3.connect(f"file:{database}?mode=ro&immutable=1", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            records = [dict(r) for r in conn.execute("SELECT * FROM memory_item")]
            db_audits = [dict(r) for r in conn.execute("SELECT * FROM memory_audit")]
        if branch["branch"] == "expiry":
            audit.check(not any(op["op"] == "forget" for op in branch["operations"]), "expiry_has_no_authored_forgetting", branch_dir)
            audit.check(not any(r["operation"] == "forget" for r in db_audits), "expiry_has_no_real_forgetting", branch_dir)
        mutation_counts = Counter(e["op"]["op"] for e in operation_events
                                  if e.get("status") == "ok" and e["op"]["op"] in ("remember", "correct", "forget"))
        audit.observe(Counter(r["operation"] for r in db_audits) == mutation_counts, "storage", "database_audit_mutation_counts", branch_dir,
                      expected=dict(mutation_counts), actual=dict(Counter(r["operation"] for r in db_audits)))
        audit.check(not (branch_ids & all_memory_ids), "independent_generated_memory_ids", branch_dir)
        all_memory_ids.update(branch_ids)
        audit.branches.append(dict(branch_id=branch["branch_id"], process_pids=process_ids, database_inode=list(file_id),
                                   checkpoints=sum(bool(r.get("checkpoint_id")) for r in branch_rows),
                                   operation_count=len(starts), final_record_count=len(records),
                                   final_audit_count=len(db_audits), mutation_counts=dict(mutation_counts)))
    counts = Counter(found_checkpoints)
    audit.check(set(counts) == set(planned), "all_planned_checkpoints_present", run_dir,
                expected=sorted(set(planned) - set(counts)), observed=sorted(set(counts) - set(planned)))
    audit.check(all(count == 1 for count in counts.values()), "unique_checkpoint_attempts", run_dir,
                observed={key: count for key, count in counts.items() if count != 1})
    audit.check(scheduled_segments == 72, "all_72_scheduled_segments", run_dir, observed=scheduled_segments)
    audit.check(len(all_database_ids) == 36, "all_36_independent_databases", run_dir, observed=len(all_database_ids))
    finish_path = run_dir / "finish.json"
    if audit.check(finish_path.is_file(), "collection_finish_record_exists", run_dir):
        collection_finish = read_json(finish_path)
        audit.check(collection_finish.get("status") == "complete", "collection_completed_status", run_dir)
        audit.check(len(collection_finish.get("segments", [])) == fragment_count,
                    "supervisor_fragment_count_matches_artifacts", run_dir)
    audit.counts.update(planned_checkpoints=len(planned), unique_observed_checkpoints=len(counts),
                        scheduled_segments=scheduled_segments, process_fragments=fragment_count,
                        extra_continuation_fragments=fragment_count - scheduled_segments,
                        independent_databases=len(all_database_ids), distinct_processes=len(all_process_ids))
    return dict(schema_version=1, created_at=datetime.now(timezone.utc).isoformat(),
                scope="Independent artifact integrity and coverage audit; answer correctness requires separate blinded review.",
                limitations="Process restart and controlled logical expiry only; no power-loss or spoken-performance claims.",
                auditor_script_sha256=digest(__file__), freeze_directory=str(freeze_dir), run_directory=str(run_dir),
                freeze_seal_sha256=digest(freeze_dir / "seal.json"), run_seal_sha256=digest(run_dir / "seal.json"),
                integrity_pass=not audit.violations, integrity_checks=dict(audit.checks), integrity_violations=audit.violations,
                observed_system_failures=audit.observations, counts=dict(audit.counts), branches=audit.branches,
                history_exposure=dict(interpretation=HISTORY_EXPOSURE_LIMITATION,
                    counts={group: dict(counts) for group, counts in audit.history_counts.items()},
                    checkpoint_witnesses=audit.history_witnesses),
                actual_model_requests=[dict(purpose=key[0], model=key[1], count=value) for key, value in sorted(audit.models.items())],
                resource_fragments=audit.resources, received_bytes_call_links=audit.http_links)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for sealed in (args.freeze.resolve(), args.run.resolve()):
        if args.output.resolve().is_relative_to(sealed):
            parser.error("audit output must be outside sealed inputs")
    result = audit_collection(args.freeze.resolve(), args.run.resolve(), args.repository.resolve())
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps({"integrity_pass": result["integrity_pass"], "counts": result["counts"],
                      "integrity_violations": len(result["integrity_violations"]),
                      "system_failure_observations": len(result["observed_system_failures"])}))
    return 0 if result["integrity_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
