"""Offline, failure-preserving analysis of CLARA's four-turn routing experiment.

Backend durations are nested diagnostics, never additive wall-time components.
Timing repetitions are averaged within their frozen sequence before descriptive
cluster resampling. No model inference or changes to raw artifacts occur here.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import csv
import json
import math
from pathlib import Path
import random
import secrets
import statistics


NS = 1_000_000_000
ARMS = ("small", "large", "adaptive", "replay")
SMALL, LARGE = "qwen3:0.6b", "qwen3:1.7b"
LABELS = {"complete", "appropriate_abstention", "appropriate_uncertainty", "partial",
          "incorrect", "inappropriate_abstention", "technical_failure"}
CORRECT = {"complete", "appropriate_abstention", "appropriate_uncertainty"}


def read(path):
    return json.loads(Path(path).read_text())


def jsonl(path):
    if not path.is_file():
        return []
    rows = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError as error:
                raise ValueError(f"{path}:{i}: malformed durable record") from error
    return rows


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def lines(path, values):
    path.write_text("".join(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n" for value in values))


def table(path, rows):
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                             for k, v in row.items()})


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def quantile(values, proportion):
    values = sorted(values)
    if not values:
        return None
    index = (len(values) - 1) * proportion
    lo, hi = math.floor(index), math.ceil(index)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def dist(values):
    values = [v for v in values if v is not None]
    return dict(n=len(values), total=sum(values), mean=statistics.mean(values) if values else None,
                median=quantile(values, .5), p95=quantile(values, .95),
                min=min(values) if values else None, max=max(values) if values else None)


def interval(event):
    start = event.get("start_ns", event.get("started_monotonic_ns"))
    end = event.get("end_ns", event.get("finished_monotonic_ns"))
    if not number(start) or not number(end) or end < start:
        raise ValueError("missing or reversed monotonic interval")
    if "wall_ns" in event and event["wall_ns"] != end - start:
        raise ValueError("wall_ns differs from monotonic interval")
    return start, end


def union_ns(intervals):
    total, last = 0, None
    for start, end in sorted(intervals):
        if end < start:
            raise ValueError("reversed interval")
        if last is None or start >= last:
            total += end - start
        elif end > last:
            total += end - last
        last = max(last or end, end)
    return total


def component(name, ancestry=()):
    """Classify a leaf using its enclosing actual-path operation, when needed."""
    terms = " ".join([name, *ancestry]).lower()
    if name == "residency_audit":
        return "residency_audit"
    if any(token in name.lower() for token in ("eviction", "unload", "evict")):
        return "eviction"
    if "validation" in terms or "validate" in terms:
        return "validation"
    if "retriev" in terms:
        return "retrieval"
    if "memory" in terms and any(token in terms for token in ("classif", "selector")):
        return "memory_classifier"
    if "compute" in terms and any(token in terms for token in ("classif", "selector")):
        return "compute_classifier"
    if any(token in terms for token in ("generation", "generate", "answer_model")):
        return "answer_generation"
    if any(token in terms for token in ("routing", "route", "selection", "selector", "deterministic")):
        return "deterministic_routing_and_bookkeeping"
    return "other_instrumented"


def account_spans(record):
    """Partition the request into disjoint deepest observed spans and residual.

    Nested span durations remain available in the event table. Unrelated spans
    may not overlap: accepting such overlaps would disguise concurrent inference
    or broken instrumentation. Parent spans may enclose their complete children.
    """
    start, end = interval(record)
    events = record.get("events", record.get("spans", []))
    if not isinstance(events, list):
        raise ValueError("events must be a list")
    by_id, usable = {}, []
    for event in events:
        if event.get("end_ns", event.get("finished_monotonic_ns")) is None:
            continue  # Explicit unfinished events remain in raw events.jsonl.
        left, right = interval(event)
        eid = event.get("id")
        if eid in by_id:
            raise ValueError("duplicate span id")
        if left < start or right > end:
            raise ValueError("span outside complete request interval")
        by_id[eid] = event
        usable.append((left, right, event))
    ancestors = {}
    for eid, event in by_id.items():
        parent, chain = event.get("parent_id"), []
        while parent is not None and parent in by_id:
            if parent == eid or parent in chain:
                raise ValueError("cyclic span parent")
            chain.append(parent)
            child_interval, parent_interval = interval(event), interval(by_id[parent])
            if child_interval[0] < parent_interval[0] or child_interval[1] > parent_interval[1]:
                raise ValueError("child span outside parent")
            parent = by_id[parent].get("parent_id")
        ancestors[eid] = chain
    boundaries = sorted({start, end, *(v for left, right, _ in usable for v in (left, right))})
    totals = defaultdict(int)
    for left, right in zip(boundaries, boundaries[1:]):
        active = [event for a, b, event in usable if a <= left and b >= right and b > a]
        if not active:
            totals["unaccounted"] += right - left
            continue
        leaf = max(active, key=lambda e: len(ancestors[e.get("id")]))
        if any(e.get("id") != leaf.get("id") and e.get("id") not in ancestors[leaf.get("id")]
               for e in active):
            raise ValueError("overlapping spans are not parent/child")
        names = [by_id[eid].get("name", "") for eid in ancestors[leaf.get("id")]]
        totals[component(leaf.get("name", ""), names)] += right - left
    if sum(totals.values()) != end - start:
        raise ValueError("exclusive components fail request accounting")
    return dict(totals)


def residents(snapshot):
    if snapshot is None:
        return None
    if not isinstance(snapshot, list):
        raise ValueError("residency snapshot must be a list or explicit null")
    return [row.get("name", row.get("model")) for row in snapshot]


def placement(snapshot, model):
    matches = [item for item in (snapshot or []) if item.get("name", item.get("model")) == model]
    if len(matches) != 1:
        return {}
    model_state = matches[0]
    size, gpu = model_state.get("size"), model_state.get("size_vram")
    return dict(model_digest=model_state.get("digest"), loaded_bytes=size, gpu_allocated_bytes=gpu,
                gpu_allocation_fraction=gpu / size if number(size) and size > 0 and number(gpu) else None,
                context_length=model_state.get("context_length"))


def model_for_turn(record):
    generation = record.get("generation") or {}
    return generation.get("model") or next((call.get("actual_model") or call.get("requested_model")
                for call in reversed(record.get("calls", [])) if call.get("purpose") == "generation"), None)


def audit_calls(record):
    arm = record["arm"]
    allowed = {SMALL} if arm == "small" else {LARGE} if arm == "large" else {SMALL, LARGE}
    for call in record.get("calls", []):
        requested = call.get("requested_model", call.get("model"))
        actual = call.get("actual_model")
        if requested not in allowed or actual not in allowed | {None}:
            raise ValueError("actual model call violates true fixed-system model policy")
        if actual is not None and actual != requested:
            raise ValueError("requested/actual model mismatch")
        if arm == "replay" and call.get("purpose") in {"memory_selector", "compute_selector"}:
            raise ValueError("diagnostic replay made a selector model call")
    for call in record.get("http_calls", []):
        if call.get("endpoint") != "/api/chat":
            continue
        body = call.get("body", {})
        if (body.get("model") not in allowed or body.get("think") is not False
                or body.get("keep_alive") != -1 or body.get("options") !=
                {"num_ctx": 2048, "num_predict": 192, "temperature": 0.0, "seed": 42}):
            raise ValueError("actual HTTP generation settings or model differ from freeze")


def backend_rows(record, identity):
    result = []
    placement_audits = sorted([event for event in record.get("events", []) if event.get("name") == "residency_audit"],
                             key=lambda event: event.get("start_ns", 0))
    for index, call in enumerate(record.get("calls", []), 1):
        generation = call.get("generation") or call.get("raw_generation") or {}
        row = dict(identity, call_index=index, purpose=call.get("purpose"),
                   requested_model=call.get("requested_model"), actual_model=call.get("actual_model"),
                   status=call.get("status"), call_wall_seconds=call.get("wall_ns", 0) / NS,
                   prompt_tokens=generation.get("prompt_eval_count"), output_tokens=generation.get("eval_count"))
        for key in ("total_duration_ns", "load_duration_ns", "prompt_eval_duration_ns", "eval_duration_ns"):
            value = generation.get(key)
            if value is not None and not number(value):
                raise ValueError(f"invalid backend duration: {key}")
            row[key.removesuffix("_ns") + "_seconds"] = value / NS if value is not None else None
        if len(placement_audits) == len(record.get("calls", [])):
            state = placement_audits[index - 1].get("attributes", {}).get("models")
            row.update(residency_after_call=state, **placement(state, row["actual_model"] or row["requested_model"]))
        result.append(row)
    return result


def load_inputs(run_root, workload_path, freeze_path):
    workload, frozen = read(workload_path), read(freeze_path)
    expected_hash = frozen.get("workload_sha256")
    if expected_hash and expected_hash != sha256(workload_path.read_bytes()).hexdigest():
        raise ValueError("workload differs from freeze")
    for relative, digest in frozen.get("source_sha256", {}).items():
        source = freeze_path.parent / "source" / relative
        if not source.is_file() or sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError(f"archived frozen source differs: {relative}")
    runs, records, components, backends, events, audit_errors = [], [], [], [], [], []
    paths = sorted(run_root.rglob("manifest.json"))
    for directory in [path.parent for path in paths]:
        manifest = read(directory / "manifest.json")
        if manifest.get("arm") not in ARMS:
            continue
        finish = read(directory / "finish.json") if (directory / "finish.json").is_file() else {}
        startup = read(directory / "startup.json") if (directory / "startup.json").is_file() else {}
        observed = jsonl(directory / "observations.jsonl")
        durable = jsonl(directory / "events.jsonl")
        observed_keys = {(row.get("id"), row.get("index")) for row in observed}
        if len(observed_keys) != len(observed):
            raise ValueError("duplicate completed turn record")
        for marker in durable:
            if marker.get("kind") == "turn_attempt" and (marker.get("id"), marker.get("index")) not in observed_keys:
                observed.append({**marker, "status": "interrupted", "dangling_attempt_marker": True})
                observed_keys.add((marker.get("id"), marker.get("index")))
        observed.sort(key=lambda row: row.get("index", 0))
        identity = {key: manifest.get(key) for key in ("sequence_id", "pattern", "arm", "repetition")}
        identity["attempt_directory"] = str(directory.relative_to(run_root))
        if (manifest.get("freeze_sha256") is not None
                and manifest["freeze_sha256"] != sha256(freeze_path.read_bytes()).hexdigest()):
            audit_errors.append(dict(identity, error="session used a different freeze"))
        if finish.get("source_unchanged") is False:
            audit_errors.append(dict(identity, error="execution source changed during collection"))
        initial = read(directory / "start.json") if (directory / "start.json").is_file() else {}
        if initial.get("resident_models"):
            audit_errors.append(dict(identity, error="sequence did not start from no-model residency"))
        completed_rows = []
        for record in observed:
            if any(key in record and record[key] != value for key, value in identity.items()
                   if key != "attempt_directory"):
                audit_errors.append(dict(identity, index=record.get("index"), error="turn/session identity mismatch"))
            row = {**identity, **record}
            row["attempt_directory"] = identity["attempt_directory"]
            if not number(row.get("wall_ns")) or row.get("phase") == "before_request":
                # A durable start without finish counts as an interrupted turn.
                row["status"] = "interrupted"
                row["missing_request_latency"] = True
                row["wall_ns"] = None
            else:
                try:
                    parts = account_spans(row)
                    audit_calls(row)
                    record_identity = {k: row.get(k) for k in (*identity, "id", "index")}
                    components.extend(dict(record_identity, component=name, exclusive_wall_seconds=ns / NS)
                                      for name, ns in parts.items())
                    backends.extend(backend_rows(row, record_identity))
                    events.extend(dict(record_identity, request_id=row.get("id"), **event) for event in row.get("events", row.get("spans", [])))
                    row["exclusive_components_ns"] = parts
                    completed_rows.append(row)
                except (ValueError, TypeError, KeyError) as error:
                    audit_errors.append(dict(identity, index=row.get("index"), error=str(error)))
            records.append(row)
        startup_ns = finish.get("startup_ns", startup.get("wall_ns"))
        measured_total = sum(row["wall_ns"] for row in completed_rows)
        request_ns = finish.get("request_total_ns")
        total_ns = finish.get("sequence_total_ns")
        gaps_ns = finish.get("sequence_gaps_ns", 0)
        accounting_ok = (number(startup_ns) and number(request_ns) and number(total_ns)
                         and number(gaps_ns) and request_ns == measured_total
                         and total_ns == startup_ns + request_ns + gaps_ns)
        if "sequence_start_ns" in finish or "sequence_end_ns" in finish:
            accounting_ok = accounting_ok and (number(finish.get("sequence_start_ns"))
                 and number(finish.get("sequence_end_ns"))
                 and total_ns == finish["sequence_end_ns"] - finish["sequence_start_ns"])
        terminal_complete = finish.get("status") in {"complete", "complete_with_errors", "ok"}
        complete = terminal_complete and len(completed_rows) == 4 and len(observed) == 4 and accounting_ok
        if terminal_complete and not complete:
            audit_errors.append(dict(identity, error="claimed complete sequence fails four-turn/startup accounting"))
        runs.append(dict(identity, status=finish.get("status", "interrupted_without_finish"),
                         attempted_turns=len(observed), complete=complete, accounting_ok=accounting_ok,
                         startup_seconds=startup_ns / NS if number(startup_ns) else None,
                         request_seconds=request_ns / NS if number(request_ns) else None,
                         sequence_seconds=total_ns / NS if number(total_ns) else None,
                         sequence_gaps_seconds=gaps_ns / NS if number(gaps_ns) else None,
                         envelope_seconds=finish.get("envelope_ns", 0) / NS if "envelope_ns" in finish else None,
                         cleanup_seconds=finish.get("cleanup_ns", 0) / NS if "cleanup_ns" in finish else None,
                         delivered=sum(row.get("status") == "ok" for row in observed),
                         resident_models_after_cleanup=finish.get("api_ps_after", finish.get("resident_models_after_cleanup", finish.get("resident_models"))),
                         error=finish.get("error", finish.get("failure")), cleanup_errors=finish.get("cleanup_errors", [])))
    adaptive = {(row["sequence_id"], row["repetition"], row.get("id")): row for row in records if row["arm"] == "adaptive"}
    for row in records:
        if row["arm"] != "replay" or row.get("status") != "ok":
            continue
        original = adaptive.get((row["sequence_id"], row["repetition"], row.get("id")))
        if original is None:
            audit_errors.append(dict(attempt_directory=row["attempt_directory"], error="diagnostic replay lacks adaptive source"))
            continue
        calls = lambda raw: [{key: call.get(key) for key in ("requested_model", "messages", "response_format")}
                             for call in raw.get("calls", []) if call.get("purpose") == "generation"]
        bodies = lambda raw: [call["body"] for call in raw.get("http_calls", []) if call.get("endpoint") == "/api/chat"
                              and "speech" in call.get("body", {}).get("format", {}).get("properties", {})]
        if (calls(row) != calls(original) or bodies(row) != bodies(original)
                or row.get("history_before") != original.get("history_before") or row.get("route") != original.get("route")):
            audit_errors.append(dict(attempt_directory=row["attempt_directory"], index=row.get("index"),
                                     error="diagnostic replay differs from adaptive generation requests/history/route"))
    return workload, frozen, runs, records, components, backends, events, audit_errors


def resource_rows(run_root, runs):
    rows = []
    for run in runs:
        directory = run_root / run["attempt_directory"]
        samples = jsonl(directory / "telemetry.jsonl")
        identity = {key: run[key] for key in ("attempt_directory", "sequence_id", "pattern", "arm", "repetition")}
        stamps = [sample.get("monotonic_ns") for sample in samples]
        if any(not number(stamp) for stamp in stamps) or any(a >= b for a, b in zip(stamps, stamps[1:])):
            raise ValueError("telemetry monotonic samples are missing or unordered")
        measured = lambda fn: dist(value for sample in samples if (value := fn(sample)) is not None)
        peak_temp = measured(lambda sample: max(sample.get("temperatures_c", {}).values(), default=None))["max"]
        memory = measured(lambda sample: sample.get("ram", {}).get("used_mb"))
        swap = measured(lambda sample: sample.get("swap", {}).get("used_mb"))
        gpu = measured(lambda sample: sample.get("gr3d_percent"))
        cpu = measured(lambda sample: statistics.mean(cpu["utilization_percent"] for cpu in sample.get("cpu", []) if cpu.get("online"))
                       if any(cpu.get("online") for cpu in sample.get("cpu", [])) else None)
        rows.append(dict(identity, telemetry_samples=len(samples), ram_peak_mib=memory["max"],
                         logical_swap_peak_mib=swap["max"], temperature_peak_c=peak_temp,
                         gpu_utilization_mean_percent=gpu["mean"], gpu_utilization_max_percent=gpu["max"],
                         cpu_utilization_mean_percent=cpu["mean"], cpu_utilization_max_percent=cpu["max"],
                         cleanup_seconds=run["cleanup_seconds"], cleanup_errors=run["cleanup_errors"],
                         resident_models_after_cleanup=run["resident_models_after_cleanup"]))
    return rows


def turn_table(records):
    result, previous = [], {}
    for raw in records:
        key = raw["attempt_directory"]
        model = model_for_turn(raw)
        before, after = residents(raw.get("api_ps_before")), residents(raw.get("api_ps_after"))
        old = previous.get(key)
        transition = ("cold_start" if before == [] else "resident_same_model" if before == [model]
                      else "model_switch" if before is not None and model is not None else "unknown")
        route = raw.get("route") or {}
        row = {k: raw.get(k) for k in ("attempt_directory", "sequence_id", "pattern", "arm", "repetition", "id", "index", "status")}
        row.update(wall_seconds=raw["wall_ns"] / NS if number(raw.get("wall_ns")) else None,
                   workload_label=raw.get("workload_label"),
                   actual_generator=model, selected_model_size=(route.get("decision") or {}).get("model_size"),
                   model_size_decision_source=route.get("model_size_decision_source"),
                   memory_decision_source=route.get("memory_decision_source"),
                   residency_before=before, residency_after=after, residency_condition=transition,
                   previous_actual_generator=old["actual_generator"] if old else None,
                   following_turn_of_transition=old["residency_condition"] if old else None,
                   following_small_return=bool(old and old["previous_actual_generator"] == LARGE and old["actual_generator"] == SMALL),
                   return_to_small=bool(old and old["actual_generator"] == LARGE and model == SMALL),
                   output_tokens=(raw.get("generation") or {}).get("eval_count"),
                   prompt_tokens=(raw.get("generation") or {}).get("prompt_eval_count"),
                   **placement(raw.get("api_ps_after"), model))
        inclusive = defaultdict(int)
        for event in raw.get("events", []):
            if number(event.get("wall_ns")):
                inclusive[event.get("name")] += event["wall_ns"]
        for name in ("routing", "deterministic_routing", "memory_classifier", "compute_classifier", "model_transition", "unload_request", "eviction_verification"):
            row[name + "_inclusive_seconds"] = inclusive[name] / NS
        counts = Counter(call.get("purpose") for call in raw.get("calls", []))
        row.update(memory_classifier_calls=counts["memory_selector"], compute_classifier_calls=counts["compute_selector"],
                   generation_calls=counts["generation"])
        for category, value in raw.get("exclusive_components_ns", {}).items():
            row[category + "_seconds"] = value / NS
        result.append(row)
        previous[key] = row
    return result


def paired_sequences(runs):
    lookup = {}
    for row in runs:
        if not row["complete"]:
            continue
        key = row["sequence_id"], row["repetition"], row["arm"]
        if key in lookup:
            raise ValueError("multiple complete attempts for same sequence/repetition/arm; specify an unambiguous run root")
        lookup[key] = row
    pairs = []
    for (sequence, repetition, arm), adaptive in sorted(lookup.items()):
        if arm != "adaptive":
            continue
        for comparator in ("small", "large", "replay"):
            fixed = lookup.get((sequence, repetition, comparator))
            if fixed is None:
                continue
            pairs.append(dict(sequence_id=sequence, pattern=adaptive["pattern"], repetition=repetition,
                              comparator=comparator, adaptive_seconds=adaptive["sequence_seconds"],
                              comparator_seconds=fixed["sequence_seconds"],
                              adaptive_minus_comparator_seconds=adaptive["sequence_seconds"] - fixed["sequence_seconds"],
                              adaptive_startup_minus_comparator_seconds=adaptive["startup_seconds"] - fixed["startup_seconds"],
                              adaptive_requests_minus_comparator_seconds=adaptive["request_seconds"] - fixed["request_seconds"]))
    return pairs


def paired_turns(turns):
    lookup = {(row["sequence_id"], row["repetition"], row["id"], row["arm"]): row for row in turns}
    result = []
    for key, adaptive in lookup.items():
        sequence, repetition, rid, arm = key
        if arm != "adaptive":
            continue
        for comparator in ("small", "large", "replay"):
            other = lookup.get((sequence, repetition, rid, comparator))
            if other is None:
                continue
            row = dict(sequence_id=sequence, pattern=adaptive["pattern"], repetition=repetition,
                       id=rid, index=adaptive["index"], comparator=comparator,
                       adaptive_status=adaptive["status"], comparator_status=other["status"],
                       adaptive_actual_model=adaptive["actual_generator"], comparator_actual_model=other["actual_generator"],
                       identical_actual_model=adaptive["actual_generator"] == other["actual_generator"],
                       adaptive_residency_condition=adaptive["residency_condition"], comparator_residency_condition=other["residency_condition"],
                       adaptive_minus_comparator_seconds=adaptive["wall_seconds"] - other["wall_seconds"]
                       if adaptive["wall_seconds"] is not None and other["wall_seconds"] is not None else None,
                       output_tokens_difference=adaptive["output_tokens"] - other["output_tokens"]
                       if adaptive["output_tokens"] is not None and other["output_tokens"] is not None else None,
                       gpu_allocation_fraction_difference=adaptive["gpu_allocation_fraction"] - other["gpu_allocation_fraction"]
                       if adaptive.get("gpu_allocation_fraction") is not None and other.get("gpu_allocation_fraction") is not None else None)
            if "correct" in adaptive and "correct" in other:
                row.update(adaptive_correct=adaptive["correct"], comparator_correct=other["correct"],
                           quality_outcome="both_correct" if adaptive["correct"] and other["correct"] else
                           "adaptive_only_correct" if adaptive["correct"] else "comparator_only_correct" if other["correct"] else "neither_correct")
            if row["adaptive_minus_comparator_seconds"] is not None:
                row["adaptive_minus_comparator_excluding_residency_audit_seconds"] = row["adaptive_minus_comparator_seconds"] - (
                    adaptive.get("residency_audit_seconds", 0) - other.get("residency_audit_seconds", 0))
            result.append(row)
    return result


def cluster_summary(pairs, *, resamples=4000):
    groups = defaultdict(list)
    for pair in pairs:
        groups[pair["comparator"], pair["sequence_id"], pair["pattern"]].append(pair)
    clusters = [dict(comparator=comparator, sequence_id=sequence, pattern=pattern,
                     timing_repetitions=len(rows),
                     mean_adaptive_minus_comparator_seconds=statistics.mean(r["adaptive_minus_comparator_seconds"] for r in rows))
                for (comparator, sequence, pattern), rows in sorted(groups.items())]
    summaries = []
    for comparator in ("small", "large", "replay"):
        for pattern in ["overall", *sorted({row["pattern"] for row in clusters})]:
            rows = [row for row in clusters if row["comparator"] == comparator
                    and (pattern == "overall" or row["pattern"] == pattern)]
            values = [row["mean_adaptive_minus_comparator_seconds"] for row in rows]
            strata = defaultdict(list)
            for row in rows:
                strata[row["pattern"]].append(row["mean_adaptive_minus_comparator_seconds"])
            rng, samples = random.Random(20260912), []
            if values and all(len(v) >= 2 for v in strata.values()):
                for _ in range(resamples):
                    sample = [rng.choice(v) for v in strata.values() for _ in v]
                    samples.append(statistics.mean(sample))
            summaries.append(dict(comparator=comparator, pattern=pattern, sequence_clusters=len(rows),
                                  complete_three_repetition_clusters=sum(row["timing_repetitions"] == 3 for row in rows),
                                  mean_adaptive_minus_comparator_seconds=statistics.mean(values) if values else None,
                                  cluster_min_seconds=min(values) if values else None,
                                  cluster_max_seconds=max(values) if values else None,
                                  descriptive_cluster_bootstrap_95_low=quantile(samples, .025),
                                  descriptive_cluster_bootstrap_95_high=quantile(samples, .975)))
    return clusters, summaries


def packet_inputs(workload, records):
    rubrics = workload.get("rubrics", {})
    cases = {case.get("id"): case for case in workload.get("execution_cases", [])}
    for sequence in workload.get("sequences", []):
        for case in sequence.get("turns", sequence.get("cases", [])):
            cases[case.get("id")] = case
    return rubrics, cases


def make_blind(workload, records, output):
    output.mkdir(parents=True, exist_ok=False)
    rubrics, cases = packet_inputs(workload, records)
    groups, mapping = {}, []
    for raw in records:
        response = raw.get("response") or {}
        answer = response.get("speech", "")
        case = cases.get(raw.get("id"), {})
        content = dict(question=raw.get("prompt", case.get("prompt")),
                       history=raw.get("history_before", []),
                       rubric=rubrics.get(raw.get("id"), case.get("rubric", {})),
                       prepared_memory=workload.get("memory_seed", {}),
                       answer=answer, response_complete=raw.get("status") == "ok",
                       answer_constraint=raw.get("answer_constraint"))
        key = canonical(content)
        if key not in groups:
            groups[key] = dict(answer_id=secrets.token_hex(8), **content)
        mapping.append(dict(answer_id=groups[key]["answer_id"], attempt_directory=raw["attempt_directory"],
                            id=raw.get("id"), index=raw.get("index"), arm=raw["arm"],
                            sequence_id=raw["sequence_id"], repetition=raw["repetition"]))
    packet = list(groups.values())
    random.SystemRandom().shuffle(packet)
    lines(output / "packet.jsonl", packet)
    write(output / "private_mapping.json", mapping)
    write(output / "provenance.json", dict(created_at=datetime.now(timezone.utc).isoformat(),
          observations=len(records), unique_output_context_groups=len(packet),
          grouping="Identical question, retained history, rubric, answer and delivery status only.",
          independent_human_review="pending"))
    return len(packet)


def quality_join(records, blind_dir, review_paths):
    if not blind_dir or not review_paths:
        return {}, dict(status="pending", independently_human_reviewed=False)
    packet = jsonl(blind_dir / "packet.jsonl")
    packet_map = {row["answer_id"]: row for row in packet}
    if len(packet_map) != len(packet):
        raise ValueError("duplicate anonymous answer in review packet")
    mapping = read(blind_dir / "private_mapping.json")
    ids = {row["answer_id"] for row in packet}
    reviews = {}
    for path in review_paths:
        for review in jsonl(path):
            aid = review.get("answer_id")
            if aid not in ids or aid in reviews:
                raise ValueError("unknown or duplicate answer review")
            if review.get("label") not in LABELS or not review.get("rationale"):
                raise ValueError("review requires recognized label and explicit rubric rationale")
            if any(key in review for key in ("model", "arm", "latency", "wall_ns")):
                raise ValueError("review contains unblinded fields")
            if review["label"] in CORRECT and any(review.get(key) is True for key in ("unsupported_claim", "unsupported_personal_claim")):
                raise ValueError("fully correct judgment conflicts with unsupported-claim flags")
            reviews[aid] = review
    if set(reviews) != ids:
        raise ValueError("quality claims require review of every output group")
    lookup = {(row["attempt_directory"], row.get("id"), row.get("index")): row for row in records}
    joined = {}
    for entry in mapping:
        key = entry["attempt_directory"], entry.get("id"), entry.get("index")
        if key not in lookup or key in joined:
            raise ValueError("review mapping does not uniquely cover raw observations")
        raw, review = lookup[key], reviews[entry["answer_id"]]
        item = packet_map[entry["answer_id"]]
        if (item["question"] != raw.get("prompt") or item["history"] != raw.get("history_before", [])
                or item["answer"] != (raw.get("response") or {}).get("speech", "")
                or item["response_complete"] != (raw.get("status") == "ok")):
            raise ValueError("reviewed question/history/answer differs from raw observation")
        if raw.get("status") != "ok" and review["label"] in CORRECT:
            raise ValueError("undelivered answer cannot be a correct delivered answer")
        joined[key] = dict(review, correct=review["label"] in CORRECT)
    if set(joined) != set(lookup):
        raise ValueError("review mapping omits observed attempts")
    summaries = {}
    for arm in ARMS:
        rows = [joined[key] for key, raw in lookup.items() if raw["arm"] == arm]
        summaries[arm] = dict(attempts=len(rows), correct=sum(row["correct"] for row in rows),
                              labels=dict(Counter(row["label"] for row in rows)))
    return joined, dict(status="assistant_reviewed", independently_human_reviewed=False,
                        unique_output_groups=len(ids), systems=summaries,
                        caveat="Repeated answers and turns within sequences are dependent; judgments require independent human validation.")


def grouped_turns(turns):
    result = []
    for field in ("residency_condition", "following_turn_of_transition", "return_to_small", "following_small_return"):
        groups = defaultdict(list)
        for row in turns:
            groups[row["arm"], str(row.get(field))].append(row)
        for (arm, value), rows in sorted(groups.items()):
            result.append(dict(arm=arm, grouping=field, condition=value,
                               **dist(row["wall_seconds"] for row in rows),
                               output_tokens_mean=dist(row.get("output_tokens") for row in rows)["mean"]))
    return result


def plot(output, turns, runs, components, pairs):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = dict(small="#277da1", large="#f9844a", adaptive="#43aa8b", replay="#8c78b5")
    patterns = sorted({row["pattern"] for row in runs})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    width = .18
    for j, arm in enumerate(ARMS):
        means, starts = [], []
        for pattern in patterns:
            rows = [row for row in runs if row["complete"] and row["arm"] == arm and row["pattern"] == pattern]
            means.append(dist(row["sequence_seconds"] for row in rows)["mean"] or 0)
            starts.append(dist(row["startup_seconds"] for row in rows)["mean"] or 0)
        x = [i + (j - 1.5) * width for i in range(len(patterns))]
        axes[0].bar(x, means, width, label=arm, color=colors[arm])
        axes[0].bar(x, starts, width, facecolor="none", edgecolor="#222", hatch="///", linewidth=.5)
        values = sorted(row["wall_seconds"] for row in turns if row["arm"] == arm and row["wall_seconds"] is not None)
        if values:
            axes[1].step(values, [(i + 1) / len(values) for i in range(len(values))], where="post", label=arm, color=colors[arm])
    axes[0].set(xticks=range(len(patterns)), xticklabels=patterns, ylabel="Mean complete sequence seconds",
                title="Four-turn total, including startup (hatched)")
    axes[1].set(xlabel="Complete request wall time (s)", ylabel="Observed fraction", title="All measured requests, including failed delivery")
    for ax in axes:
        ax.legend(frameon=False)
        ax.grid(axis="y", alpha=.2)
    for extension in ("png", "pdf", "svg"):
        fig.savefig(output / f"sequence_latency.{extension}", dpi=180)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 4.5), constrained_layout=True)
    comps = sorted({row["component"] for row in components})
    bottoms = [0.] * 4
    for name in comps:
        values = [sum(row["exclusive_wall_seconds"] for row in components if row["arm"] == arm and row["component"] == name)
                  / max(1, sum(row["arm"] == arm for row in turns)) for arm in ARMS]
        ax.bar(ARMS, values, bottom=bottoms, label=name.replace("_", " "))
        bottoms = [a + b for a, b in zip(bottoms, values)]
    ax.set(ylabel="Seconds per attempted turn", title="Disjoint wall-time accounting; backend loading is nested")
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1), frameon=False, fontsize=8)
    for extension in ("png", "pdf", "svg"):
        fig.savefig(output / f"components.{extension}", dpi=180)
    plt.close(fig)


def report(output, summary):
    fmt = lambda value: "unavailable" if value is None else f"{value:.3f}"
    text = ["# CLARA routing overhead: measured four-turn sequences", "",
            f"{summary['attempted_turns']} recorded turns; {summary['complete_sequences']} complete sequence attempts; "
            f"{summary['audit_error_count']} accounting/identity audit errors.", "",
            "Backend loading, prefill and decoding durations are already inside the measured client-call wall spans. "
            "They are diagnostics and are never added again. The exclusive component partition plus unaccounted "
            "wall time equals each measured request interval. Startup includes prepared-memory/client setup and is "
            "added once to the four request intervals. Complete sequence totals additionally include the measured "
            "between-turn guard, audit and logging gaps. Final cleanup remains separate.", "",
            "| System | Attempts | Delivered | Complete sequences | Mean request s | Mean startup s | Mean sequence s |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for arm, row in summary["systems"].items():
        text.append(f"| {arm} | {row['attempts']} | {row['delivered']} | {row['complete_sequences']} | "
                    f"{fmt(row['request_seconds']['mean'])} | {fmt(row['startup_seconds']['mean'])} | {fmt(row['sequence_seconds']['mean'])} |")
    text += ["", "Positive paired differences mean adaptive took longer; negative differences mean measured adaptive savings. "
             "Each sequence is first averaged over available timing repetitions. A repeated sequence is one cluster, "
             "not three independent quality cases. Intervals resample whole sequence variants within workload patterns "
             "and are descriptive for this small authored suite. Shared templates and the fictional memory profile "
             "limit even sequence-level independence; these are not population confidence guarantees.", "",
             "| Comparator | Pattern | Sequence clusters | Adaptive minus comparator s | Descriptive cluster interval s |",
             "| --- | --- | ---: | ---: | --- |"]
    for row in summary["paired_cluster_summary"]:
        if row["sequence_clusters"]:
            text.append(f"| {row['comparator']} | {row['pattern']} | {row['sequence_clusters']} | "
                        f"{fmt(row['mean_adaptive_minus_comparator_seconds'])} | "
                        f"[{fmt(row['descriptive_cluster_bootstrap_95_low'])}, {fmt(row['descriptive_cluster_bootstrap_95_high'])}] |")
    quality = summary["quality"]
    text += ["", "The routing-bypass replay is a diagnostic replay of the adaptive generator requests and selected model "
             "sequence. It is not a deployable policy. It runs after the main-system triple, so placement, allocator/cache "
             "state and device-order differences may affect its paired delta even with identical model requests.", "",
             "Residency-audit HTTP checks are separately measured instrumentation overhead. The turn-pair table also "
             "shows subtraction of that direct audit span difference as a diagnostic; it does not remove thermal/cache "
             "or order effects. Verified-eviction blocking is retained in all measured systems. Model-transition "
             "bookkeeping outside explicit unload/verification spans remains in its enclosing classifier/generation component.", "",
             "Model residency, transitions, return-to-small and following-turn costs are in `turns.csv` and "
             "`transition_following_turn_summary.csv`; actual model and GPU allocation fractions are included. "
             "GPU allocation is the ratio of allocated bytes, not utilization or the fraction of computation. "
             "Output tokens, prompt tokens and actual backends are retained to expose attribution limits.", "",
             f"Answer review status: **{quality['status']}**. Validated delivery does not establish semantic correctness. "
             "No quality–latency improvement is claimed while review is pending. Independent human validation remains pending."]
    if quality.get("systems"):
        text += ["", "| System | Fully correct delivered / attempted |", "| --- | ---: |"]
        for arm, row in quality["systems"].items():
            text.append(f"| {arm} | {row['correct']}/{row['attempts']} |")
    text += ["", "All raw attempts, errors and incomplete sequences remain in the input directory and the attempt tables. "
             "Incomplete sequences are excluded only from complete paired totals, with their missing coverage explicit; "
             "their observed turns remain in request distributions. Earlier experiments are contextual evidence and "
             "are not pooled into these measurements.", ""]
    (output / "report.md").write_text("\n".join(text))


def analyze(args):
    workload, frozen, runs, records, components, backends, events, errors = load_inputs(args.run_root, args.workload, args.freeze)
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=False)
    turns = turn_table(records)
    pairs = paired_sequences(runs)
    clusters, paired_summary = cluster_summary(pairs)
    judgments, quality = quality_join(records, args.blind_dir, args.reviews)
    for row in turns:
        review = judgments.get((row["attempt_directory"], row.get("id"), row.get("index")))
        if review:
            row.update(quality_label=review["label"], correct=review["correct"])
    turn_pairs = paired_turns(turns)
    resources = resource_rows(args.run_root, runs)
    systems = {}
    for arm in ARMS:
        rows, sequences = [row for row in turns if row["arm"] == arm], [row for row in runs if row["arm"] == arm and row["complete"]]
        systems[arm] = dict(attempts=len(rows), delivered=sum(row["status"] == "ok" for row in rows),
                            complete_sequences=len(sequences), missing_request_latency=sum(row["wall_seconds"] is None for row in rows),
                            request_seconds=dist(row["wall_seconds"] for row in rows),
                            startup_seconds=dist(row["startup_seconds"] for row in sequences),
                            sequence_seconds=dist(row["sequence_seconds"] for row in sequences),
                            actual_generators=dict(Counter(row["actual_generator"] for row in rows)),
                            output_tokens=dist(row["output_tokens"] for row in rows),
                            gpu_allocation_fraction=dist(row.get("gpu_allocation_fraction") for row in rows))
        systems[arm]["call_counts"] = {name: sum(row.get(name, 0) for row in rows)
                                      for name in ("memory_classifier_calls", "compute_classifier_calls", "generation_calls")}
        systems[arm]["exclusive_components_seconds"] = {name: sum(row["exclusive_wall_seconds"] for row in components
                    if row["arm"] == arm and row["component"] == name) for name in sorted({row["component"] for row in components})}
        systems[arm]["backend_nested_seconds"] = {name: sum(row.get(name) or 0 for row in backends if row["arm"] == arm)
                    for name in ("total_duration_seconds", "load_duration_seconds", "prompt_eval_duration_seconds", "eval_duration_seconds")}
        systems[arm]["resources"] = {name: max((row[name] for row in resources if row["arm"] == arm and row[name] is not None), default=None)
                    for name in ("ram_peak_mib", "logical_swap_peak_mib", "temperature_peak_c")}
    summary = dict(profile_id=frozen.get("profile_id"), attempted_turns=len(records), sequence_attempts=len(runs),
                   complete_sequences=sum(row["complete"] for row in runs), audit_error_count=len(errors),
                   systems=systems, paired_cluster_summary=paired_summary, quality=quality,
                   dependence="12 authored sequence variants, with 4 dependent turns and 3 timing repetitions per system; descriptive stratified cluster bootstrap.")
    write(output / "analysis.json", summary)
    write(output / "audit_errors.json", errors)
    for filename, rows in (("turns", turns), ("sequence_attempts", runs), ("components", components),
                           ("backend_nested_durations", backends), ("events", events), ("paired_sequences", pairs),
                           ("paired_turns", turn_pairs), ("resources", resources),
                           ("paired_sequence_clusters", clusters), ("paired_cluster_summary", paired_summary),
                           ("transition_following_turn_summary", grouped_turns(turns))):
        table(output / f"{filename}.csv", rows)
    report(output, summary)
    if not args.no_figures:
        plot(output, turns, runs, components, pairs)
    inputs = [args.workload, args.freeze, *sorted(args.run_root.rglob("*.json")), *sorted(args.run_root.rglob("*.jsonl"))]
    if args.blind_dir:
        inputs += sorted(args.blind_dir.glob("*.json*"))
    inputs += args.reviews
    write(output / "provenance.json", dict(created_at=datetime.now(timezone.utc).isoformat(),
          source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
          input_sha256={str(path): sha256(path.read_bytes()).hexdigest() for path in inputs},
          offline_only=True, raw_artifacts_modified=False))
    print(json.dumps(summary, indent=2))
    return 1 if errors else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("blind", "analyze"))
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--blind-dir", type=Path)
    parser.add_argument("--reviews", type=Path, action="append", default=[])
    parser.add_argument("--no-figures", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "blind":
        workload, _, _, records, _, _, _, errors = load_inputs(args.run_root, args.workload, args.freeze)
        if errors:
            raise ValueError(f"repair artifact interpretation before blinding: {errors}")
        print(make_blind(workload, records, args.output_dir))
        return 0
    return analyze(args)


if __name__ == "__main__":
    raise SystemExit(main())
