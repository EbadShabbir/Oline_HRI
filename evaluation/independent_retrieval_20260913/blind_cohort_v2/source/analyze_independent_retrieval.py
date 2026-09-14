"""Offline integrity audit, blinded packets and dependent paired analysis.

This program never invokes a model and never assigns semantic judgments. It
scores only frozen external assistant judgments supplied through --reviews.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import csv
import json
from pathlib import Path
import random
import re
import secrets
import shlex
import statistics

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODELS = ("qwen3:0.6b", "qwen3:1.7b")
POLICIES = ("OFF", "ALWAYS", "SELECTIVE")
COMPARISONS = (("SELECTIVE", "ALWAYS"), ("SELECTIVE", "OFF"), ("ALWAYS", "OFF"))
LABELS = {"complete", "partial", "incorrect", "appropriate_abstention",
          "inappropriate_abstention", "technical_failure"}
FLAGS = ("unsupported_claim", "unsupported_personal_claim", "abstained",
         "explicit_conflict", "forbidden_disclosure")
REVIEW_FIELDS = {"review_id", "label", "rationale", *FLAGS}
PACKET_FIELDS = {"review_id", "prompt", "answer", "delivery_status", "answerability",
                 "rubric", "reference_facts_without_ids"}
BOOTSTRAP_SEED, BOOTSTRAP_REPLICATES = 2026091399, 10000


def read(path):
    return json.loads(Path(path).read_text())


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def write(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=False)
        stream.write("\n")


def write_jsonl(path, rows):
    with Path(path).open("x") as stream:
        for row in rows:
            stream.write(canonical(row) + "\n")


def verify_seal(directory):
    directory = Path(directory)
    hashes = read(directory / "seal.json")["sha256"]
    actual = {str(path.relative_to(directory)) for path in directory.rglob("*")
              if path.is_file() and path != directory / "seal.json"}
    if set(hashes) != actual:
        raise ValueError(f"seal file set differs: {directory}")
    for name, expected in hashes.items():
        if Path(name).is_absolute() or ".." in Path(name).parts or digest(directory / name) != expected:
            raise ValueError(f"sealed contents differ: {directory / name}")


def seal(directory):
    write(directory / "seal.json", {"created_at": datetime.now(timezone.utc).isoformat(),
        "sha256": {str(p.relative_to(directory)): digest(p) for p in sorted(directory.rglob("*")) if p.is_file()},
        "immutability": "exclusive creation, hashes and read-only permissions; not privileged WORM"})
    for p in directory.rglob("*"):
        p.chmod(0o500 if p.is_dir() else 0o400)
    directory.chmod(0o500)


def dist(values):
    values = sorted(value for value in values if value is not None)
    if not values:
        return {"n": 0, "mean": None, "median": None, "p95": None, "total": 0, "min": None, "max": None}
    return {"n": len(values), "mean": statistics.mean(values), "median": statistics.median(values),
            "p95": float(np.quantile(values, .95)), "total": sum(values), "min": values[0], "max": values[-1]}


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def check(condition, message, errors):
    if not condition:
        errors.append(message)


def names(snapshot):
    return [item.get("name", item.get("model")) for item in snapshot]


def observe_key(row):
    return f"slot_{row['slot']:02d}:{row['case']['id']}"


def admission_events(run, expected_freeze_hash, visited=None):
    """Include preserved earlier admissions when a continuation retains slots."""
    visited=set() if visited is None else visited
    run=Path(run).resolve()
    if run in visited:
        raise ValueError("cyclic collection continuation provenance")
    visited.add(run)
    verify_seal(run)
    plan=read(run/"plan.json")
    if plan["freeze_sha256"] != expected_freeze_hash:
        raise ValueError("admission continuation freeze differs")
    events=[];sources=[]
    if plan.get("continuation_from"):
        events,sources=admission_events(Path(plan["continuation_from"]),expected_freeze_hash,visited)
    path=run/"startup_waits.jsonl"
    if path.exists():
        events.extend(jsonl(path));sources.append({"path":str(path),"sha256":digest(path)})
    return events,sources


def fragment_layout(manifest, slot, summary, rows, errors):
    """Separate a physical worker's local indices from frozen schedule indices."""
    fragment = manifest.get("fragment", {})
    offset = fragment.get("offset", 0)
    if type(offset) is not int or not 0 <= offset < len(slot["request_ids"]):
        errors.append(f"slot {slot['slot']}: invalid physical fragment offset")
        offset = 0
    remaining = slot["request_ids"][offset:]
    if fragment:
        check(fragment.get("request_ids") == remaining and fragment.get("planned") == len(remaining),
              "fragment planned suffix differs", errors)
        check(summary.get("fragment_offset") == offset and summary.get("original_planned") == len(slot["request_ids"]),
              "fragment summary offset or original size differs", errors)
    check(summary.get("planned") == len(remaining), "fragment planned count differs", errors)
    check(summary.get("attempted") == len(rows), "fragment attempted count differs", errors)
    check([r["case"]["id"] for r in rows] == remaining[:len(rows)], "fragment request order differs", errors)
    check([r.get("index") for r in rows] == list(range(1, len(rows)+1)), "fragment local indices differ", errors)
    if summary.get("status", "").startswith("complete"):
        check(len(rows) == len(remaining), "complete fragment has unattempted suffix", errors)
    return offset, len(remaining)


def audit_prefix(rows, schedule, errors):
    expected = [f"slot_{slot['slot']:02d}:{ident}" for slot in schedule for ident in slot["request_ids"]]
    actual = [observe_key(row) for row in rows]
    check(actual == expected[:len(actual)] and len(set(actual)) == len(actual),
          "observations are not the unique strict frozen global prefix", errors)
    return expected


def fragment_overhead(directory, slot, manifest, waits, errors):
    """Never reuse the old slot-keyed timing for a later suffix worker."""
    keyed = [event for event in waits if event.get("event") == "fragment_terminal_overhead"
             and Path(event["directory"]).resolve() == Path(directory).resolve()]
    if not keyed and "fragment" not in manifest:
        keyed = [event for event in waits if event.get("event") == "admission_complete"
                 and event["slot"] == slot["slot"]]
    check(len(keyed) <= 1, "duplicate physical fragment supervisor overhead", errors)
    if not keyed:
        return None
    event = keyed[0]
    check(event["slot"] == slot["slot"] and event["wall_ns"] >= 0, "fragment overhead identity or duration differs", errors)
    return event["wall_ns"]/1e9


def audit_continuation_fragment(freeze, directory, manifest, cache):
    """Use the stdlib orchestration proof; do not import any inference module."""
    fragment = manifest.get("fragment")
    if not fragment:
        return
    from independent_retrieval_continuation import verify_continuation, verify_ledger
    continuation = Path(fragment["continuation_directory"]).resolve()
    ledger = Path(fragment["ledger_directory"]).resolve()
    if str(continuation) not in cache["plans"]:
        plan = verify_continuation(freeze, continuation)
        cache["plans"][str(continuation)] = {
            "continuation_sha256": digest(continuation/"continuation.json"),
            "seal_sha256": digest(continuation/"seal.json"),
            "source_sha256": plan["source_sha256"], "retained_attempts": plan["attempted"],
            "prior_run": plan["prior_run"], "prior_run_seal_sha256": plan["prior_run_seal_sha256"]}
    proof = verify_ledger(freeze, continuation, ledger, manifest["slot"]["slot"], fragment["offset"])
    if Path(proof["authorized_worker_directory"]).resolve() != Path(directory).resolve():
        raise ValueError("fragment worker is not authorized by its ledger")
    for field, path in (("ledger_sha256", ledger/"ledger.json"), ("ledger_seal_sha256", ledger/"seal.json"),
                        ("continuation_sha256", continuation/"continuation.json"),
                        ("continuation_seal_sha256", continuation/"seal.json")):
        if fragment[field] != digest(path):
            raise ValueError("fragment supplemental provenance differs: "+field)
    cache["ledgers"][str(ledger)] = {"ledger_sha256": digest(ledger/"ledger.json"),
        "seal_sha256": digest(ledger/"seal.json"), "worker_directory": str(Path(directory).resolve())}


def collection_timing_provenance(run):
    """Separate supervisor intervals and artifact-boundary gaps from request time."""
    plan, finish = read(run/"plan.json"), read(run/"batch_finish.json")
    result = collection_timing_provenance(Path(plan["continuation_from"])) if plan.get("continuation_from") else []
    item = {"directory":str(run.resolve()), "supervisor_started_monotonic_ns":plan.get("supervisor_started_monotonic_ns"),
        "supervisor_started_at":plan.get("supervisor_started_at"), "supervisor_wall_s":ratio(finish.get("supervisor_wall_ns"), 1e9) if finish.get("supervisor_wall_ns") is not None else None,
        "previous_run_seal_created_at":plan.get("previous_run_seal_created_at"), "seal_header_to_supervisor_start_s":None,
        "scope":"supervisor wall includes verification/ledger/launch/guard/wait and child exit/sealing, but excludes parent final batch manifest, sealing and exit; seal-header gap includes earlier sealing/exit and off-run pause, not pure pause; do not add to fragment or request timing"}
    if item["supervisor_started_at"] and item["previous_run_seal_created_at"]:
        item["seal_header_to_supervisor_start_s"] = (datetime.fromisoformat(item["supervisor_started_at"])
            - datetime.fromisoformat(item["previous_run_seal_created_at"])).total_seconds()
    result.append(item)
    return result


def audit_rejected_session(directory, slot, frozen, freeze_hash, errors):
    """A retried launch is admissible only when its preserved artifacts prove no attempt/call."""
    directory=Path(directory);verify_seal(directory)
    prefix=f"rejected {directory.name}: "
    err=lambda condition,message:check(condition,prefix+message,errors)
    manifest,summary,start,finish=(read(directory/name) for name in
        ("manifest.json","summary.json","start.json","finish.json"))
    err(manifest["slot"]==slot and manifest["freeze_sha256"]==freeze_hash,"freeze or slot differs")
    err(manifest.get("device_policy")==frozen["device_policy"],"device guard policy differs")
    err(all(manifest["config"]["ollama"].get(k)==slot["model"] for k in
            ("small_model","general_large_model","large_model")),"sole-model configuration differs")
    failure=summary.get("failure") or {}
    offset, planned = fragment_layout(manifest, slot, summary, [], errors)
    err(summary.get("attempted")==0,"rejected launch attempted a scheduled request")
    err(summary.get("status")=="interrupted" and not summary.get("cleanup_errors"),"rejected launch status/cleanup differs")
    err(failure.get("type")=="SafetyGateError" and any(phrase in failure.get("message","") for phrase in
        ("available memory is below","swap use exceeds","startup temperature")),"not a guarded resource-admission rejection")
    policy=frozen["device_policy"];memory=start.get("memory",{});temperatures=start.get("temperatures_c",{})
    failed_gate={
        "available memory is below":isinstance(memory.get("mem_available_kib"),int)
            and memory["mem_available_kib"]<policy["min_start_available_kib"],
        "swap use exceeds":isinstance(memory.get("swap_used_kib"),int)
            and memory["swap_used_kib"]>policy["max_start_swap_used_kib"],
        "startup temperature":bool(temperatures)
            and max(temperatures.values())>=policy["max_start_temperature_c_exclusive"],
    }
    err(any(phrase in failure.get("message","") and rejected for phrase,rejected in failed_gate.items()),
        "recorded startup snapshot does not substantiate rejection reason")
    contents={name:jsonl(directory/name) if (directory/name).exists() else [] for name in
              ("observations.jsonl","http_calls.jsonl","events.jsonl")}
    for name,events in contents.items():
        err(not events,"rejected launch contains observations or calls: "+name)
    err(start.get("resident_models")==[] and finish.get("resident_models")==[],"rejected launch had resident model")
    err(all(start.get(k)==finish.get(k) for k in ("boot_id","thermal_trip_events","power_mode")),"guarded boot/trips/power changed")
    err(start.get("memory",{}).get("swap_total_kib")==finish.get("memory",{}).get("swap_total_kib"),"swap capacity changed")
    return {**{k:v for k,v in slot.items() if k!="request_ids"},"directory":str(directory),
        "seal_sha256":digest(directory/"seal.json"),"attempted":summary["attempted"],"status":summary["status"],
        "fragment_offset":offset,"planned":planned,
        "failure":failure,"worker_session_wall_s":summary.get("session_wall_ns",0)/1e9,
        "observations":len(contents["observations.jsonl"]),"http_events":len(contents["http_calls.jsonl"]),
        "request_events":len(contents["events.jsonl"]),"start":start,"finish":finish,
        "accounting":"preserved zero-request admission launch; excludes quality/timing attempt denominators; its time is inside measured fragment supervisor overhead when available and must not be added twice"}


def audit_row(row, slot, case, reference, frozen, catalog, errors):
    key = observe_key(row)
    err = lambda condition, message: check(condition, f"{key}: {message}", errors)
    err(row["case"] == case, "runtime case differs")
    err(all(row.get(k) == slot[k] for k in ("slot", "model", "policy", "repetition")), "condition identity differs")
    err(row["wall_ns"] == row["finished_monotonic_ns"] - row["started_monotonic_ns"] >= 0, "request timing differs")
    ad = row["adapter"]
    err(ad["policy"].upper() == slot["policy"] and ad["model"] == slot["model"], "adapter identity differs")
    err(ad["authorization"].get("authorized") == reference["authorization_expected"], "authorization differs from reference")
    err(ad["authorization"].get("consent_authorized") == case["consent_authorized"], "request consent differs")
    err(ad["authorization"].get("requested_profile") == case["profile_id"], "requested profile differs")
    retrievals = ad["retrieval_calls"]
    err(ad["retrieval_attempts"] == len(retrievals) <= 1, "retrieval accounting differs")
    err(ad["selection"].get("retrieval_selected") == bool(retrievals), "selection/attempt differs")
    if not reference["authorization_expected"]:
        err(not retrievals and not ad["supplied_ids"] and not ad["inspected_ids"], "unauthorized memory access")
    if slot["policy"] == "OFF":
        err(not retrievals and not ad["supplied_ids"] and not ad["inspected_ids"], "OFF memory access")
        err(not ad["search_calls"], "OFF performed a memory search")
    if slot["policy"] == "ALWAYS" and row["status"] == "ok":
        err(bool(retrievals) == reference["authorization_expected"], "ALWAYS did not attempt every authorized request")
    supplied = set(ad["supplied_ids"])
    err(supplied <= set(ad["retrieved_ids"]), "supplied record was not retrieved")
    err(set(item["memory"]["id"] for item in ad["supplied_evidence"]) == supplied, "supplied evidence mismatch")
    err(not supplied.intersection(reference["disallowed_evidence_ids"]), "disallowed evidence supplied")
    for item in ad["supplied_evidence"]:
        record = item["memory"]
        err(record["id"] in catalog and record["canonical_text"] == catalog[record["id"]]["canonical_text"], "supplied fact differs from frozen catalog")
        err(record["profile_id"] == case["profile_id"] and record["consent_status"] == "confirmed" and record["status"] == "active", "invalid supplied authorization")
    inspected = {ident for event in ad["inspection_events"] for ident in event["ids"]}
    err(set(ad["inspected_ids"]) == inspected and ad["inspected_count"] == len(inspected), "inspection accounting differs")
    globally_eligible = {identifier for identifier, record in catalog.items()
                         if record["profile_id"] == case["profile_id"] and record["final_state"] == "active"}
    err(inspected <= globally_eligible, "noncurrent or other-profile record inspected")
    err(set(ad["retrieved_ids"]) <= inspected, "retrieved record lacks observed eligible search provenance")
    err(not inspected.intersection(reference["disallowed_evidence_ids"]), "disallowed record inspected after lifecycle filtering")
    if supplied and row["status"] == "ok":
        err(len(ad["freshness_calls"]) == 2 and all(call.get("current") is True for call in ad["freshness_calls"]), "delivered evidence lacks both freshness validations")
    model_calls = row["calls"]
    err(len(model_calls) == len(ad["calls"]), "backend/adapter call counts differ")
    selectors = [call for call in model_calls if call["purpose"] == "memory_selector"]
    err(len(selectors) == ad["selection"].get("classifier_calls", 0) <= 1, "selector count differs")
    if slot["policy"] != "SELECTIVE" or not reference["authorization_expected"]:
        err(not selectors, "forbidden classifier call")
    for call in model_calls:
        err(call["requested_model"] == slot["model"], "non-condition requested model")
        err(call.get("actual_model") in (None, slot["model"]), "non-condition actual model")
        err(call["purpose"] in ("generation", "memory_selector"), "unexpected compute/fallback call")
        if call["purpose"] == "generation":
            messages = call["messages"]
            roles = [message.get("role") for message in messages]
            err(len(messages) >= 2 and roles[-1:] == ["user"]
                and all(role == "system" for role in roles[:-1])
                and case["prompt"] in messages[-1].get("content", ""),
                "generation contains prior history or unexpected message roles")
        if slot["policy"] == "OFF":
            text = canonical(call["messages"])
            err(not re.search(r"mem_[0-9a-f]{32}|memory_ref_[0-9]+", text), "OFF has personal evidence identifiers")
            err(not any(record["canonical_text"] in text for record in catalog.values()), "OFF contains frozen personal fact")
    chat_http = [call for call in row["http_calls"] if call["endpoint"] == "/api/chat"]
    err(len(chat_http) == len(model_calls), "HTTP/model call count differs")
    for call in chat_http:
        body = call["body"]
        err(body["model"] == slot["model"] and body.get("think") is False, "HTTP model or thinking differs")
        options = body.get("options", {})
        err(all(options.get(k) == v for k, v in {"num_ctx": 2048, "num_predict": 192, "temperature": 0, "seed": 42}.items()), "HTTP decoding differs")
        if call.get("response"):
            err(call["response"].get("model") == slot["model"], "HTTP response model differs")
    if row["status"] == "ok":
        err(row.get("generation", {}).get("model") == slot["model"] and row.get("fallback_from_model") is None, "delivered generation/fallback differs")
        err(set(row["memory"]["supplied_ids"]) == supplied, "reply evidence differs")
    for field in ("api_ps_before", "api_ps_after"):
        snapshot = row.get(field)
        if snapshot is None:
            err(row["status"] == "interrupted", "missing residency snapshot")
            continue
        err(len(snapshot) <= 1 and all(name == slot["model"] for name in names(snapshot)), "simultaneous or foreign resident model")
        if row["status"] == "ok" and field == "api_ps_after":
            err(names(snapshot) == [slot["model"]], "successful request did not retain its sole model")
        for model in snapshot:
            err(model.get("digest") == frozen["models"][slot["model"]]["digest"], "resident model digest differs")


def collect(freeze, run):
    verify_seal(freeze); verify_seal(run)
    frozen, runtime, refs = (read(freeze / name) for name in ("freeze.json", "runtime.json", "references.json"))
    errors, warnings = [], []
    for rel, expected in frozen["source_sha256"].items():
        check(digest(freeze / "source" / rel) == expected, f"archived source changed: {rel}", errors)
        check((ROOT / rel).exists() and digest(ROOT / rel) == expected, f"working runtime source differs: {rel}", errors)
    check(digest(freeze / "runtime.json") == frozen["runtime_sha256"], "runtime digest differs", errors)
    check(digest(freeze / "references.json") == frozen["references_sha256"], "reference digest differs", errors)
    plan, finish = read(run / "plan.json"), read(run / "batch_finish.json")
    check(plan["freeze_sha256"] == digest(freeze / "freeze.json"), "collection freeze differs", errors)
    check(plan["schedule"] == frozen["schedule"], "collection schedule differs", errors)
    check(finish.get("source_unchanged") is True and finish.get("supplemental_source_unchanged", True) is True,
          "collection execution source verification failed", errors)
    from independent_retrieval_continuation import collection_chain
    chronology = collection_chain(run, freeze)
    continuation_provenance = {"plans": {}, "ledgers": {}}
    if plan.get("continuation_directory"):
        from independent_retrieval_continuation import verify_continuation
        continuation_dir = Path(plan["continuation_directory"])
        continuation = verify_continuation(freeze, continuation_dir)
        check(plan.get("continuation_sha256") == digest(continuation_dir/"continuation.json")
              and Path(continuation["authorized_run_directory"]).resolve() == run.resolve(),
              "collection supplemental plan authorization differs", errors)
        prior_rejected = continuation["prior_rejected_sessions"]
        check(finish.get("rejected_sessions", [])[:len(prior_rejected)] == prior_rejected,
              "continuation replaced or dropped inherited rejected admissions", errors)
    case_map, catalog = ({case["id"]: case for case in runtime["execution_cases"]},
                         {record["id"]: record for record in refs["memory_catalog"]})
    prepared = read(freeze / "prepared_snapshot/setup.json")["details"]
    main_profile = runtime["memory_seed"]["profile_id"]
    instant = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
    at = instant(runtime["memory_seed"]["evaluation_at"])
    retained = runtime["memory_seed"].get("retention_days")
    current_records = [record for profile in prepared["profiles"] if profile["profile_id"] == main_profile
                       for record in profile["records"] if record["status"] == "active"
                       and record["consent_status"] == "confirmed" and instant(record["valid_from"]) <= at
                       and (record["valid_until"] is None or instant(record["valid_until"]) > at)
                       and (record["retention_until"] is None or instant(record["retention_until"]) > at)
                       and (retained is None or instant(record["created_at"]) > at-timedelta(days=retained))]
    catalog_current = [r for r in catalog.values() if r["profile_id"] == main_profile and r["final_state"] == "active"]
    check({r["id"] for r in current_records} == {r["id"] for r in catalog_current},
          "blinded current-truth catalog differs from authoritative eligible snapshot", errors)
    check(len(current_records) == 23, "frozen current authorized truth catalog must contain 23 records", errors)
    check(len(case_map) == len(refs["cases"]) == 48 and set(case_map) == set(refs["cases"]), "48-case reference/runtime correspondence differs", errors)
    slots = {slot["slot"]: slot for slot in frozen["schedule"]}
    check(len(slots) == 18 and frozen["planned_attempts"] == 864, "experiment size differs", errors)
    waits,admission_sources=admission_events(run,digest(freeze/"freeze.json"))
    rejected=[];directories_seen=set()
    for entry in finish.get("rejected_sessions",[]):
        directory=Path(entry["directory"]).resolve()
        check(directory not in directories_seen,"duplicate rejected session directory",errors)
        directories_seen.add(directory)
        check(entry.get("seal_sha256", digest(directory/"seal.json")) == digest(directory/"seal.json"),
              "rejected entry seal differs", errors)
        audit_continuation_fragment(freeze, directory, read(directory/"manifest.json"), continuation_provenance)
        rejection = audit_rejected_session(directory,slots[entry["slot"]],frozen,digest(freeze/"freeze.json"),errors)
        rejection["inherited_from_prior_collection"] = directory.parent != run.resolve()
        rejected.append(rejection)
    rows, sessions, seen = [], [], set()
    boundary_gaps = []
    for fragment_number, entry in enumerate(finish["sessions"], 1):
        directory = Path(entry["directory"]).resolve()
        check(directory.resolve() not in directories_seen,"session directory duplicated or also classified rejected",errors)
        directories_seen.add(directory.resolve())
        verify_seal(directory)
        slot = slots[entry["slot"]]
        manifest, summary = read(directory / "manifest.json"), read(directory / "summary.json")
        audit_continuation_fragment(freeze, directory, manifest, continuation_provenance)
        check(manifest["slot"] == slot and manifest["freeze_sha256"] == digest(freeze / "freeze.json"), f"session {slot['slot']} manifest differs", errors)
        check(not summary["cleanup_errors"] and summary["status"] != "verification_failed", f"session {slot['slot']} integrity/cleanup failure", errors)
        start_state,finish_state=read(directory/"start.json"),read(directory/"finish.json")
        check(not start_state.get("resident_models") and not finish_state.get("resident_models"), f"session {slot['slot']} boundary residency differs", errors)
        check(all(start_state.get(k)==finish_state.get(k) for k in ("boot_id","thermal_trip_events","power_mode")), f"session {slot['slot']} boot/trips/power changed", errors)
        check(start_state.get("memory",{}).get("swap_total_kib")==finish_state.get("memory",{}).get("swap_total_kib"), f"session {slot['slot']} swap capacity changed", errors)
        config=manifest["config"]
        check(all(config["ollama"].get(k)==slot["model"] for k in ("small_model","general_large_model","large_model")), f"session {slot['slot']} sole-model client configuration differs", errors)
        values = jsonl(directory / "observations.jsonl") if (directory / "observations.jsonl").exists() else []
        offset, fragment_planned = fragment_layout(manifest, slot, summary, values, errors)
        physical_id = f"fragment_{fragment_number:02d}"
        if rows and values and Path(rows[-1]["artifact_directory"]).parent != directory.parent:
            boundary_gaps.append({"before_directory":rows[-1]["artifact_directory"], "after_directory":str(directory),
                "request_boundary_gap_s":(values[0]["started_monotonic_ns"]-rows[-1]["finished_monotonic_ns"])/1e9,
                "scope":"last request finish to next collection's first request start; includes prior cleanup, off-run pause, later admission and setup; not pure pause and not added to supervisor overhead"})
        if values:
            setup, snapshot = read(directory / "setup.json"), read(directory / "snapshot_verification.json")
            expected = digest(freeze / "prepared_snapshot/memory.sqlite3")
            check(snapshot["unchanged"] and snapshot["before"] == snapshot["after"] == expected == setup["snapshot_sha256"] == digest(directory / "memory.sqlite3"), "snapshot changed or conditions differ", errors)
        else:
            setup = {}
        previous_after = []
        for row in values:
            key = observe_key(row)
            check(key not in seen, f"duplicate observed attempt {key}", errors); seen.add(key)
            audit_row(row, slot, case_map[row["case"]["id"]], refs["cases"][row["case"]["id"]], frozen, catalog, errors)
            if previous_after is not None:
                check(names(row["api_ps_before"]) == names(previous_after),
                      f"{key}: session did not retain preceding actual residency", errors)
            previous_after = row.get("api_ps_after")
            row["artifact_directory"] = str(directory)
            row["physical_fragment_id"] = physical_id
            row["fragment_offset"] = offset
            row["scheduled_index"] = offset + row["index"]
            rows.append(row)
        session = session_metrics(directory, slot, summary, values, setup)
        session.update(physical_fragment_id=physical_id, logical_slot=slot["slot"], fragment_offset=offset,
            planned=fragment_planned, original_planned=len(slot["request_ids"]),
            first_scheduled_index=offset+1, last_scheduled_index=offset+len(values),
            inherited_from_prior_collection=directory.parent != run.resolve())
        session["admission_supervisor_overhead_s"] = fragment_overhead(directory, slot, manifest, waits, errors)
        session["admission_overhead_scope"] = (
            "physical fragment supervisor elapsed minus request-bearing worker session_wall_ns: includes rejected worker launches/guards, "
            "waiting, ledger verification, worker imports/startup, and process-exit/sealing residual; not pure waiting; original fatal fragment without terminal event is unavailable")
        if session["session_wall_s"] is not None and session["admission_supervisor_overhead_s"] is not None:
            session["supervisor_fragment_amortized_s"] = ratio(
                session["session_wall_s"]+session["admission_supervisor_overhead_s"], len(values))
        else:
            session["supervisor_fragment_amortized_s"] = None
        session["supervisor_slot_amortized_s"] = session["supervisor_fragment_amortized_s"]
        sessions.append(session)
    expected_keys = set(audit_prefix(rows, frozen["schedule"], errors))
    check(chronology["attempted"] == len(rows), "continuation helper attempted count differs", errors)
    missing = sorted(expected_keys - seen)
    if missing:
        warnings.append(f"{len(missing)} planned attempts are unobserved; no outcome imputed")
    check(not seen - expected_keys, "observed attempts outside schedule", errors)
    if finish["status"] == "complete":
        check(not missing and len(rows) == 864, "complete batch has incomplete observation coverage", errors)
    # Equal evidence must imply identical prompts/schema across models/policies
    # and repetitions. Actual model names are deliberately excluded from keys.
    by_evidence = {}
    for row in rows:
        for call in row["calls"]:
            if call["purpose"] != "generation":
                continue
            key = (row["case"]["id"], tuple(row["adapter"]["supplied_ids"]))
            value = (call["messages"], call["response_format"])
            if key in by_evidence:
                check(by_evidence[key] == value, f"equal-evidence generation input differs: {key}", errors)
            else:
                by_evidence[key] = value
    return frozen, runtime, refs, rows, sessions, {"valid": not errors, "errors": errors,
        "warnings": warnings, "planned_attempts": 864, "observed_attempts": len(rows),
        "unobserved_attempts": missing,
        "complete_sessions": sum(s["status"].startswith("complete") and s["attempted"] == s["planned"] for s in sessions),
        "physical_fragments":len(sessions), "planned_logical_slots":len(slots),
        "observed_logical_slots":len({s["slot"] for s in sessions}),
        "complete_logical_slots":sum(sum(s["attempted"] for s in sessions if s["slot"] == slot["slot"]) == len(slot["request_ids"]) for slot in frozen["schedule"]),
        "strict_frozen_global_prefix":not any("global prefix" in message for message in errors),
        "batch_status": finish["status"], "equal_evidence_input_groups_checked": len(by_evidence),
        "authorized_current_truth_catalog_records": len(current_records),
        "rejected_admission_count":len(rejected),"rejected_admissions":rejected,
        "inherited_rejected_admission_count":sum(r["inherited_from_prior_collection"] for r in rejected),
        "new_rejected_admission_count":sum(not r["inherited_from_prior_collection"] for r in rejected),
        "admission_event_sources":admission_sources,
        "continuation_provenance":continuation_provenance, "between_collection_request_boundary_gaps":boundary_gaps,
        "collection_supervisor_intervals":collection_timing_provenance(run),
        "unavailable_fragment_supervisor_overheads":sum(s["admission_supervisor_overhead_s"] is None for s in sessions),
        "admission_supervisor_overhead_s":dist(s["admission_supervisor_overhead_s"] for s in sessions),
        "assistant_review": "pending unless external judgments supplied", "human_validation": "pending"}


def session_metrics(directory, slot, summary, rows, setup):
    telemetry = jsonl(directory / "telemetry.jsonl") if (directory / "telemetry.jsonl").exists() else []
    stamps = [sample["monotonic_ns"] for sample in telemetry]
    gaps = [(b-a)/1e9 for a,b in zip(stamps, stamps[1:])]
    energy = 0.0
    energy_intervals = 0
    for a, b in zip(telemetry, telemetry[1:]):
        pa, pb = a.get("vdd_in", {}).get("instant_mw"), b.get("vdd_in", {}).get("instant_mw")
        if pa is not None and pb is not None:
            energy += (pa + pb) / 2000 * (b["monotonic_ns"] - a["monotonic_ns"]) / 1e9
            energy_intervals += 1
    allocations = [m for row in rows for m in row.get("api_ps_after", [])]
    events = jsonl(directory / "http_calls.jsonl") if (directory / "http_calls.jsonl").exists() else []
    cleanup_ns = sum(event.get("wall_ns", 0) for event in events if event.get("endpoint") == "/api/generate" and event.get("body", {}).get("keep_alive") == 0)
    values = [r["wall_ns"]/1e9 for r in rows]
    cleanup = read(directory/"cleanup_timing.json")["wall_ns"]/1e9 if (directory/"cleanup_timing.json").exists() else None
    session_wall = summary.get("session_wall_ns")
    return {**{k: v for k,v in slot.items() if k != "request_ids"}, "directory": str(directory),
        "status": summary["status"], "attempted": len(rows), "failures": sum(r["status"] != "ok" for r in rows),
        "request_s": dist(values), "cold_first_request_s": values[0] if values else None,
        "warm_request_s": dist(values[1:]), "setup_s": setup.get("wall_ns", 0)/1e9,
        "cleanup_http_s": cleanup_ns/1e9,
        "cleanup_complete_s": cleanup,
        "session_wall_s": session_wall/1e9 if session_wall is not None else None,
        "session_wall_amortized_s": ratio(session_wall/1e9,len(rows)) if session_wall is not None else None,
        "session_amortized_request_setup_cleanup_s": ratio(sum(values)+setup.get("wall_ns",0)/1e9+cleanup_ns/1e9,len(rows)),
        "telemetry_samples": len(telemetry), "telemetry_gap_s": dist(gaps),
        "ram_peak_mib": max((s.get("ram", {}).get("used_mb", 0) for s in telemetry), default=None),
        "swap_peak_mib": max((s.get("swap", {}).get("used_mb", 0) for s in telemetry), default=None),
        "temperature_peak_c": max((max(s.get("temperatures_c", {}).values(), default=0) for s in telemetry), default=None),
        "gpu_utilization_percent": dist(s.get("gr3d_percent") for s in telemetry),
        "gpu_allocation_fraction": dist(ratio(m.get("size_vram", 0), m.get("size",0)) for m in allocations),
        "board_energy_j": energy if energy_intervals else None,
        "energy_scope": "within this physical fragment's available telemetry pairs only, trapezoidal VDD_IN; background included, no idle subtraction; scheduler waits and all between-fragment gaps excluded",
        "guard_status": summary, "start": read(directory/"start.json"), "finish": read(directory/"finish.json")}


def blind_packets(rows, refs, seed):
    grouped = defaultdict(list)
    for row in rows:
        # Exact status is part of grouping, but exception classes/text stay hidden.
        key = canonical([row["case"]["id"], row["status"],
                         row.get("response", {}).get("speech") if row["status"] == "ok" else None])
        grouped[key].append(row)
    rng = random.Random(seed)
    keys = sorted(grouped); rng.shuffle(keys)
    packet, mapping = [], []
    catalog = {r["id"]: r for r in refs["memory_catalog"]}
    for key in keys:
        group = grouped[key]; row = group[0]; reference = refs["cases"][row["case"]["id"]]
        review_id = "review_" + f"{rng.getrandbits(128):032x}"
        item = {"review_id": review_id, "prompt": row["case"]["prompt"],
            "answer": row.get("response", {}).get("speech") if row["status"] == "ok" else None,
            "delivery_status": "delivered" if row["status"] == "ok" else "not_delivered",
            "answerability": reference["answerability"], "rubric": reference["rubric"],
            "reference_facts_without_ids": [record["canonical_text"] for record in refs["memory_catalog"]
                if reference["authorization_expected"] and record["profile_id"] == row["case"]["profile_id"]
                and record["final_state"] == "active"]}
        if set(item) != PACKET_FIELDS or re.search(r"mem_[0-9a-f]{32}|ir_[0-9]{2}_[0-9]{2}", canonical(item)):
            raise ValueError("blind packet contains forbidden identity")
        packet.append(item)
        mapping.append({"review_id": review_id, "case_id": row["case"]["id"], "observation_keys": [observe_key(r) for r in group]})
    packet_b = list(packet); random.Random(seed ^ 0xD21A09).shuffle(packet_b)
    return packet, packet_b, mapping


def load_judgments(path, packet):
    values = jsonl(path)
    if any(set(value) != REVIEW_FIELDS for value in values):
        raise ValueError(f"review fields must be exactly {sorted(REVIEW_FIELDS)}")
    lookup = {item["review_id"]: item for item in packet}
    judgments = {value["review_id"]: value for value in values}
    if len(judgments) != len(values) or set(judgments) != set(lookup):
        raise ValueError("reviews must uniquely cover every blinded output group")
    for key, judgment in judgments.items():
        if judgment["label"] not in LABELS or any(type(judgment[flag]) is not bool for flag in FLAGS) or not judgment["rationale"].strip():
            raise ValueError("invalid review label, flags or rationale")
        item = lookup[key]
        if item["delivery_status"] == "not_delivered" and judgment["label"] != "technical_failure":
            raise ValueError("undelivered result must retain technical_failure label")
        if item["delivery_status"] == "not_delivered" and any(judgment[flag] for flag in FLAGS):
            raise ValueError("undelivered result cannot have delivered claim/caution flags")
        if item["delivery_status"] == "delivered" and judgment["label"] == "technical_failure":
            raise ValueError("delivered result cannot be technical_failure")
        if item["answerability"] in ("known_authorized", "self_contained_general") and judgment["label"] == "appropriate_abstention":
            raise ValueError("known authorized or self-contained general abstention is a missed task")
        if judgment["label"] in ("appropriate_abstention", "inappropriate_abstention") and not judgment["abstained"]:
            raise ValueError("abstention labels require the abstained flag")
        if judgment["label"] in ("complete", "appropriate_abstention") and (judgment["unsupported_claim"] or judgment["forbidden_disclosure"]):
            raise ValueError("successful rubric label conflicts with unsupported/forbidden claims")
        if judgment["unsupported_personal_claim"] and not judgment["unsupported_claim"]:
            raise ValueError("personal unsupported claim must also be an unsupported claim")
    return judgments


def flatten_rows(rows, refs, mapping, judgments):
    review_by_observation = {key: m["review_id"] for m in mapping for key in m["observation_keys"]}
    result = []
    for row in rows:
        reference = refs["cases"][row["case"]["id"]]; ad = row["adapter"]
        relevant, supplied, retrieved = map(set, (reference["relevant_evidence_ids"], ad["supplied_ids"], ad["retrieved_ids"]))
        inspected = set(ad["inspected_ids"])
        source_candidates = {result["memory"]["id"] for call in ad["search_calls"] for result in call.get("results", [])}
        spans = lambda name: sum(span.get("wall_ns") or 0 for span in row["trace"] if span["name"] == name)/1e9
        calls = row["calls"]
        gens = [c.get("generation", c.get("raw_generation", {})) for c in calls]
        call_ns = lambda field: sum(g.get(field) or 0 for g in gens)/1e9
        selector_calls = [c for c in ad["calls"] if c["purpose"] == "memory_selector"]
        selection_resolved = reference["authorization_expected"] and ad["selection"].get("source") in (
            "policy_off", "policy_always", "policy_personal", "policy_general", "fixed_model")
        item = {"observation_key": observe_key(row), "review_id": review_by_observation[observe_key(row)],
            "case_id": row["case"]["id"], "model": row["model"], "policy": row["policy"],
            "repetition": row["repetition"], "slot": row["slot"], "index": row["index"],
            "physical_fragment_id": row.get("physical_fragment_id"),
            "artifact_directory": row.get("artifact_directory"),
            "fragment_offset": row.get("fragment_offset", 0), "local_index": row["index"],
            "scheduled_index": row.get("scheduled_index", row["index"]),
            "category": reference["category"], "scenario_id": reference["scenario_id"],
            "answerability": reference["answerability"], "authorized": reference["authorization_expected"],
            "memory_need": reference["memory_need"], "status": row["status"],
            "failure": row["status"] != "ok", "error": row.get("error"),
            "request_s": row["wall_ns"]/1e9, "cold_first_request": row["index"] == 1,
            "authorization_s": ad["authorization"].get("wall_ns", 0)/1e9,
            "selection_s": ad["selection"].get("wall_ns", 0)/1e9,
            "selector_calls": len(selector_calls), "selector_call_s": sum(c["wall_ns"] for c in selector_calls)/1e9,
            "selection_source": ad["selection"].get("source"),
            "retrieval_selected": ad["selection"].get("retrieval_selected"),
            "selection_decision": ad["selection"].get("retrieval_selected") if selection_resolved else None,
            "selection_resolved": selection_resolved,
            "selection_unresolved": reference["authorization_expected"] and not selection_resolved,
            "retrieval_attempts": ad["retrieval_attempts"],
            "unnecessary_retrievals": ad["retrieval_attempts"] if reference["authorization_expected"] and not reference["memory_need"] else 0,
            "authorization_violations": ad["retrieval_attempts"] if not reference["authorization_expected"] else 0,
            "retrieval_s": sum(c["wall_ns"] for c in ad["retrieval_calls"])/1e9,
            "shared_intent_s": ad["framing"].get("intent_wall_ns", 0)/1e9,
            "response_evidence_linking_s": ad["framing"].get("evidence_linking_wall_ns", 0)/1e9,
            "generation_s": spans("answer_generation"), "validation_s": spans("validation"),
            "loading_s": call_ns("load_duration_ns"), "prefill_s": call_ns("prompt_eval_duration_ns"),
            "decode_s": call_ns("eval_duration_ns"), "backend_total_s": call_ns("total_duration_ns"),
            "prompt_tokens": sum(g.get("prompt_eval_count") or 0 for g in gens),
            "output_tokens": sum(g.get("eval_count") or 0 for g in gens),
            "relevant_count": len(relevant), "relevant_retrieved": len(relevant & retrieved),
            "relevant_supplied": len(relevant & supplied),
            "retrieved_coverage": ratio(len(relevant & retrieved),len(relevant)),
            "supplied_coverage": ratio(len(relevant & supplied),len(relevant)),
            "complete_relevant_retrieved": bool(relevant <= retrieved) if relevant else None,
            "complete_relevant_supplied": bool(relevant <= supplied) if relevant else None,
            "inspected_count": len(inspected), "irrelevant_inspected": len(inspected-relevant),
            "source_candidate_count": len(source_candidates), "irrelevant_source_candidates": len(source_candidates-relevant),
            "retrieved_count": len(retrieved), "irrelevant_retrieved": len(retrieved-relevant),
            "supplied_count": len(supplied), "irrelevant_supplied": len(supplied-relevant),
            "inspected_ids": sorted(inspected), "supplied_ids": sorted(supplied),
            "helper_constraint": ad["helper_behavior"]["answer_constraint"],
            "helper_speech_enum": ad["helper_behavior"]["speech_enum"] is not None,
            "response_transform": ad["helper_behavior"]["response_transform"],
            "answer": row.get("response", {}).get("speech"),
        }
        item["residual_request_s"] = item["request_s"]-sum(item[k] for k in (
            "authorization_s","selection_s","retrieval_s","shared_intent_s",
            "response_evidence_linking_s","generation_s","validation_s"))
        judgment = judgments.get(item["review_id"])
        if judgment:
            item.update({key: judgment[key] for key in ("label", *FLAGS)})
            item["task_success"] = judgment["label"] in ("complete", "appropriate_abstention")
            item["known_fact_cautious_miss"] = item["answerability"] == "known_authorized" and judgment["abstained"] and not item["task_success"]
            item["posthoc_known_answer_without_supplied_evidence"] = item["answerability"] == "known_authorized" and item["task_success"] and not supplied
        result.append(item)
    return result


TIMINGS = ("request_s", "authorization_s", "selection_s", "selector_call_s", "retrieval_s",
    "shared_intent_s", "response_evidence_linking_s", "generation_s", "validation_s", "loading_s",
    "prefill_s", "decode_s", "backend_total_s", "residual_request_s")


def summarize(rows):
    authorized = [r for r in rows if r["authorized"]]
    needed = [r for r in authorized if r["memory_need"]]
    unneeded = [r for r in authorized if not r["memory_need"]]
    needed_resolved = [r for r in needed if r["selection_resolved"]]
    unneeded_resolved = [r for r in unneeded if r["selection_resolved"]]
    has_evidence = [r for r in rows if r["relevant_count"]]
    judged = [r for r in rows if "task_success" in r]
    total = lambda key: sum(r[key] for r in rows)
    result = {"attempts": len(rows), "distinct_requests": len({r["case_id"] for r in rows}),
        "scenario_clusters": len({r["scenario_id"] for r in rows}), "delivered": sum(not r["failure"] for r in rows),
        "failures": total("failure"), "authorized_requests": len(authorized), "no_memory_needed_authorized": len(unneeded),
        "retrieval_attempts": total("retrieval_attempts"), "unnecessary_retrievals": total("unnecessary_retrievals"),
        "unnecessary_retrieval_rate": ratio(total("unnecessary_retrievals"),len(unneeded)),
        "unnecessary_fraction_of_retrievals": ratio(total("unnecessary_retrievals"),total("retrieval_attempts")),
        "retrievals_per_task": ratio(total("retrieval_attempts"),len(rows)),
        "authorization_violations": total("authorization_violations"),
        "selection_sensitivity": ratio(sum(r["selection_decision"] is True for r in needed_resolved),len(needed_resolved)),
        "selection_specificity": ratio(sum(r["selection_decision"] is False for r in unneeded_resolved),len(unneeded_resolved)),
        "selection_resolved_authorized_requests": len(needed_resolved)+len(unneeded_resolved),
        "selection_unresolved_authorized_requests": total("selection_unresolved"),
        "selection_unresolved_needed": len(needed)-len(needed_resolved),
        "selection_unresolved_unneeded": len(unneeded)-len(unneeded_resolved),
        "selection_resolution_rate": ratio(len(needed_resolved)+len(unneeded_resolved),len(authorized)),
        "realized_retrieval_sensitivity_all_authorized": ratio(sum(r["retrieval_attempts"] for r in needed),len(needed)),
        "classifier_calls": total("selector_calls"), "selection_sources": dict(Counter(r["selection_source"] for r in rows)),
        "relevant_evidence_occurrences": total("relevant_count"),
        "retrieved_evidence_coverage": ratio(total("relevant_retrieved"),total("relevant_count")),
        "supplied_evidence_coverage": ratio(total("relevant_supplied"),total("relevant_count")),
        "requests_with_relevant_evidence": len(has_evidence),
        "complete_relevant_retrieved": sum(r["complete_relevant_retrieved"] for r in has_evidence),
        "complete_relevant_supplied": sum(r["complete_relevant_supplied"] for r in has_evidence),
        "empty_relevant_lookup_requests": sum(r["retrieval_attempts"] for r in rows if not r["relevant_count"]),
        "timing": {key: dist(r[key] for r in rows) for key in TIMINGS},
        "cold_first_request_s": dist(r["request_s"] for r in rows if r["cold_first_request"]),
        "warm_request_s": dist(r["request_s"] for r in rows if not r["cold_first_request"]),
        "success_conditional_request_s": dist(r["request_s"] for r in judged if r["task_success"]),
        "helpers": dict(Counter(r["helper_constraint"] or "none" for r in rows)),
        "helper_speech_enum": total("helper_speech_enum"),
        "transformations": dict(Counter(r["response_transform"] or "none" for r in rows)),
        "quality_reviewed_attempts": len(judged), "task_success": sum(r["task_success"] for r in judged) if judged else None,
        "success_rate": ratio(sum(r["task_success"] for r in judged),len(judged)),
        "labels": dict(Counter(r["label"] for r in judged)),
    }
    for key in ("inspected_count", "irrelevant_inspected", "source_candidate_count", "irrelevant_source_candidates",
                "retrieved_count", "irrelevant_retrieved", "supplied_count", "irrelevant_supplied", "prompt_tokens", "output_tokens"):
        result[key] = total(key)
    for key in (*FLAGS, "known_fact_cautious_miss", "posthoc_known_answer_without_supplied_evidence"):
        result[key] = sum(r[key] for r in judged) if judged else None
    return result


def grouped_summary(rows, keys):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    return [{**dict(zip(keys, values)), **summarize(group)} for values, group in sorted(groups.items())]


def paired_analysis(rows):
    lookup = {(r["model"], r["policy"], r["case_id"], r["repetition"]): r for r in rows}
    ids = sorted({r["case_id"] for r in rows})
    pairs, means = [], []
    metric_keys = ("request_s", "selection_s", "retrieval_s", "generation_s", "validation_s", "loading_s",
        "retrieval_attempts", "unnecessary_retrievals", "irrelevant_inspected", "irrelevant_supplied", "supplied_coverage", "failure")
    quality_keys = ("task_success", "unsupported_claim", "unsupported_personal_claim", "abstained", "known_fact_cautious_miss")
    for model in MODELS:
        for left, right in COMPARISONS:
            for case_id in ids:
                this_case = []
                for rep in (1,2,3):
                    a,b = lookup.get((model,left,case_id,rep)),lookup.get((model,right,case_id,rep))
                    if a is None or b is None:
                        continue
                    pair = {"model": model, "comparison": left+"-"+right, "case_id": case_id,
                        "repetition": rep, "scenario_id": a["scenario_id"], "category": a["category"]}
                    for key in (*metric_keys,*quality_keys):
                        if a.get(key) is not None and b.get(key) is not None:
                            pair[key+"_difference"] = float(a[key])-float(b[key])
                    if "task_success" in a and "task_success" in b:
                        pair["quality_pair"] = "both_success" if a["task_success"] and b["task_success"] else "left_only" if a["task_success"] else "right_only" if b["task_success"] else "neither_success"
                    pairs.append(pair);this_case.append(pair)
                if this_case:
                    means.append({"model":model,"comparison":left+"-"+right,"case_id":case_id,
                        "scenario_id":this_case[0]["scenario_id"],"category":this_case[0]["category"],
                        "paired_repetitions":len(this_case),
                        **{key:statistics.mean(p[key] for p in this_case if key in p)
                           for key in sorted({k for p in this_case for k in p if k.endswith("_difference")})}})
    summaries=[]
    scenario_ids=sorted({r["scenario_id"] for r in rows})
    rng=random.Random(BOOTSTRAP_SEED)
    draws=np.asarray([[rng.randrange(len(scenario_ids)) for _ in scenario_ids]
                      for _ in range(BOOTSTRAP_REPLICATES)],dtype=int) if scenario_ids else np.empty((0,0),dtype=int)
    for model in MODELS:
        for left,right in COMPARISONS:
            comparison=left+"-"+right
            categories=["overall",*sorted({r["category"] for r in rows})]
            for category in categories:
                group=[p for p in means if p["model"]==model and p["comparison"]==comparison and (category=="overall" or p["category"]==category)]
                raw=[p for p in pairs if p["model"]==model and p["comparison"]==comparison and (category=="overall" or p["category"]==category)]
                item={"model":model,"comparison":comparison,"category":category,
                    "paired_requests":len(group),"paired_attempts":len(raw),
                    "planned_paired_requests":48 if category=="overall" else 8,
                    "planned_paired_attempts":144 if category=="overall" else 24,
                    "request_mean_success_direction":dict(Counter(
                        "left_higher" if p["task_success_difference"]>0 else "right_higher"
                        if p["task_success_difference"]<0 else "equal"
                        for p in group if "task_success_difference" in p)),
                    "quality_pairs":dict(Counter(p["quality_pair"] for p in raw if "quality_pair" in p)),"differences":{}}
                if group:
                    for metric in sorted({key for p in group for key in p if key.endswith("_difference")}):
                        values=[p[metric] for p in group if metric in p]
                        totals=np.array([sum(p[metric] for p in group if p["scenario_id"]==s and metric in p) for s in scenario_ids])
                        counts=np.array([sum(p["scenario_id"]==s and metric in p for p in group) for s in scenario_ids])
                        den=counts[draws].sum(axis=1);num=totals[draws].sum(axis=1)
                        samples=num[den>0]/den[den>0]
                        item["differences"][metric]={"mean":statistics.mean(values),"distinct_requests":len(values),
                            "bootstrap_95_low":float(np.quantile(samples,.025)),"bootstrap_95_high":float(np.quantile(samples,.975)),
                            "bootstrap_nonempty_resamples":len(samples)}
                summaries.append(item)
    return pairs,means,summaries


def write_csv(path, rows):
    if not rows:
        with path.open("x") as stream: stream.write("")
        return
    keys=list(dict.fromkeys(key for row in rows for key in row))
    with path.open("x",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=keys);writer.writeheader()
        writer.writerows({k:canonical(v) if isinstance(v,(list,dict)) else v for k,v in row.items()} for row in rows)


REVIEW_INSTRUCTIONS = """# Independent blinded assistant review

Review each packet independently. Do not inspect any other experiment files,
private mapping, timing, model, policy, actual supplied evidence, or another
reviewer's judgments. Human validation is pending. Judge the delivered answer
against the same semantic rubric regardless of inferred retrieval behavior.

Return one JSON object per line with exactly these fields:
`review_id`, `label`, `unsupported_claim`, `unsupported_personal_claim`,
`abstained`, `explicit_conflict`, `forbidden_disclosure`, `rationale`.

Labels: `complete`, `partial`, `incorrect`, `appropriate_abstention`,
`inappropriate_abstention`, `technical_failure`. All five flags are booleans.
Rationale is a short nonempty explanation. Appropriate uncertainty on an
unknown/conflicting/restricted request uses `appropriate_abstention`; record
explicit conflict wording separately. A delivered known-authorized answer
must supply every required fact to be `complete`. Abstaining on such a request
is `inappropriate_abstention` and a task failure, even if cautious without
evidence. Self-contained general questions also require the requested answer;
abstaining is a task failure. Both abstention labels require `abstained=true`.
Mark `abstained` whenever the response declines a requested fact;
partial answers can also abstain. Undelivered responses are technical_failure,
with claim/caution flags false because no answer reached the user.

Authorized packets contain the entire currently eligible main-profile truth
catalog without IDs; denied requests contain no authorized background. A true
extra fact is not unsupported merely because it was unrequested. The unchanged
task rubric can nevertheless forbid unrequested disclosure, especially on
general questions, so apply every rubric restriction separately.

Unsupported claims are material claims unsupported by the question, this full
authorized truth context, or established general knowledge. The personal
subset requires both unsupported flags true. These are semantic factuality
and rubric judgments, not judgments about what runtime evidence was available
(that information is blinded). Known answers that happen to be correct without
supplied runtime evidence are separately flagged during posthoc analysis.
Set forbidden_disclosure for disclosures prohibited by the rubric, including
true personal facts on a general task that forbids personal disclosure, as
well as forbidden outdated, wrong-profile, unconsented or prohibited facts.
The successful labels are complete and appropriate_abstention; success cannot
coexist with material unsupported claims or forbidden disclosure. Do not infer
that correct syntax, citations, or cautious wording makes recall successful.

Freeze each original review before comparison. A third blinded independent
assistant adjudicates disagreements with the same packet. Keep originals and
adjudication; only then supply a fully resolved JSONL file to the analyzer.
"""


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze",type=Path,required=True)
    parser.add_argument("--run",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--reviews",type=Path)
    parser.add_argument("--blind-seed-from",type=Path)
    args=parser.parse_args(argv)
    freeze=args.freeze.parent if args.freeze.is_file() else args.freeze
    frozen,runtime,refs,raw,sessions,audit=collect(freeze,args.run)
    if args.output.exists(): raise ValueError("refusing to overwrite analysis directory")
    args.output.mkdir(parents=True,mode=0o700)
    seed=read(args.blind_seed_from)["seed"] if args.blind_seed_from else secrets.randbits(256)
    packet_a,packet_b,mapping=blind_packets(raw,refs,seed)
    private=args.output/"private";private.mkdir(mode=0o700)
    write(private/"seed.json",{"seed":seed,"scope":"private random blinding seed; never provide to reviewers"})
    write(private/"mapping.json",mapping)
    blind=args.output/"blinded";blind.mkdir(mode=0o700)
    write_jsonl(blind/"packet_a.jsonl",packet_a);write_jsonl(blind/"packet_b.jsonl",packet_b)
    (blind/"REVIEW_INSTRUCTIONS.md").write_text(REVIEW_INSTRUCTIONS)
    judgments=load_judgments(args.reviews,packet_a) if args.reviews else {}
    if judgments: write_jsonl(args.output/"resolved_reviews.jsonl",judgments.values())
    rows=flatten_rows(raw,refs,mapping,judgments)
    pairs,request_pairs,paired=paired_analysis(rows)
    request_instability=[]
    groups=defaultdict(list)
    for row in rows: groups[(row["model"],row["policy"],row["case_id"])].append(row)
    for (model,policy,case_id),group in sorted(groups.items()):
        request_instability.append({"model":model,"policy":policy,"case_id":case_id,"repetitions":len(group),
            "distinct_delivered_outcomes":len({(r["status"],r["answer"]) for r in group}),
            "mean_request_s":statistics.mean(r["request_s"] for r in group),
            "mean_success":statistics.mean(r["task_success"] for r in group) if judgments else None})
    summary={"audit":audit,"review":{"status":"assistant_reviewed" if judgments else "pending",
        "human_validation":"pending","unique_blinded_groups":len(mapping),"judged_groups":len(judgments)},
        "overall":grouped_summary(rows,("model","policy")),
        "by_category":grouped_summary(rows,("model","policy","category")),
        "by_repetition":grouped_summary(rows,("model","policy","repetition")),
        "paired":paired,"sessions":sessions,"dependence":{"distinct_requests":48,"scenario_clusters":8,
        "repetitions":3,"bootstrap_replicates":BOOTSTRAP_REPLICATES,"bootstrap_seed":BOOTSTRAP_SEED,
        "method":"average paired repetitions within request; percentile resampling of eight whole scenario clusters retaining categories and conditions; same scenario draws across all contrasts",
        "scope":"descriptive assistant-authored coverage pilot; no equivalence or population guarantee"},
        "timing_notes":{"primary":"all attempted complete request walls, including failures and each physical fragment's cold first load; interrupted attempts are retained once",
            "nested":"loading, prefill and decoding are nested backend metadata; never add them to wall spans",
            "amortized":"request+setup+cleanup HTTP divided by attempted requests; excludes admission waits and unmeasured cleanup bookkeeping",
            "supervisor_overhead":"separate physical-fragment supervisor elapsed minus worker session wall, including prior rejected launches/guards/waits and import/exit/sealing residual; original fatal fragment with no terminal event remains unavailable; not pure waiting and not added twice with rejected worker time",
            "continuation":"18 original logical slots; cumulative physical fragments preserve the unique frozen prefix. First local request is cold even when its scheduled_index exceeds 1. Between-collection request-boundary gaps are separate, include cleanup/admission/setup, and are not pure off-run pause or added to supervisor overhead",
            "inspection":"full eligible records materialized by exact cosine scans; unique per attempt, not low-level SQLite index access"},
        "instability_groups":sum(r["distinct_delivered_outcomes"]>1 for r in request_instability)}
    write(args.output/"analysis.json",summary);write(args.output/"audit.json",audit)
    for name,values in (("attempts",rows),("paired_attempts",pairs),("paired_request_means",request_pairs),
                        ("paired_summary",paired),("request_repetition_summary",request_instability),
                        ("sessions",sessions),("by_category",summary["by_category"]),("overall",summary["overall"])):
        write_csv(args.output/(name+".csv"),values)
    write_csv(args.output/"rejected_admissions.csv",audit["rejected_admissions"])
    write_csv(args.output/"between_collection_boundaries.csv",audit["between_collection_request_boundary_gaps"])
    write(args.output/"provenance.json",{"created_at":datetime.now(timezone.utc).isoformat(),
        "analyzer_sha256":digest(Path(__file__)),"freeze":str(freeze.resolve()),"freeze_sha256":digest(freeze/"seal.json"),
        "run":str(args.run.resolve()),"run_seal_sha256":digest(args.run/"seal.json"),
        "reviews_sha256":digest(args.reviews) if args.reviews else None,
        "rejected_admission_seals":{r["directory"]:r["seal_sha256"] for r in audit["rejected_admissions"]},
        "admission_event_sources":audit["admission_event_sources"],
        "continuation_provenance":audit["continuation_provenance"],
        "analysis_origin":"offline; no generated or inferred semantic scoring", "numpy_version":np.__version__})
    source=args.output/"analysis_source";source.mkdir(mode=0o700)
    (source/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    test=ROOT/"tests/test_retrieval_experiment_analysis.py"
    if test.exists(): (source/test.name).write_bytes(test.read_bytes())
    for name in ("independent_retrieval_continuation.py", "independent_retrieval_supervisor.py"):
        dependency = ROOT/"scripts"/name
        (source/name).write_bytes(dependency.read_bytes())
    command=[str(ROOT/".venv/bin/python"),str(Path(__file__).resolve()),"--freeze",str(freeze.resolve()),
        "--run",str(args.run.resolve()),"--output","/absolute/path/to/a/new/analysis-directory",
        "--blind-seed-from",str((private/"seed.json").resolve())]
    if args.reviews:command.extend(("--reviews",str(args.reviews.resolve())))
    (args.output/"commands.sh").write_text("# Offline only; choose a new output path.\n"+shlex.join(command)+"\n")
    seal(args.output)
    print(canonical({"output":str(args.output),"attempts":len(rows),"unique_blind_groups":len(mapping),
                     "audit_errors":len(audit["errors"]),"reviews":len(judgments)}))
    return 0 if audit["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
