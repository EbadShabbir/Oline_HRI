"""Independent final artifact audit. Standard library only; never imports analyze.

Run only after the requested cohort has completed. This auditor never imports
production or analysis modules, never opens holdout authoring or individual
reviews, and never merges cohorts. It checks arithmetic and artifacts, not
the reviewers' substantive judgments. Historical archives are supported via
--source-root COHORT/candidate_source.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def cases_at(path):
    value = read(path)
    return value["cases"] if isinstance(value, dict) else value


def sha(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


def independent_latency(values):
    ordered = sorted(values)
    if not ordered:
        return {"n": 0, "p50_seconds": None, "p95_seconds": None, "mean_seconds": None,
                "minimum_seconds": None, "maximum_seconds": None}
    result = {"n": len(ordered), "mean_seconds": math.fsum(ordered) / len(ordered),
              "minimum_seconds": ordered[0], "maximum_seconds": ordered[-1]}
    for percent in (50, 95):
        rank = (len(ordered) - 1) * percent / 100
        left, right = math.floor(rank), math.ceil(rank)
        result[f"p{percent}_seconds"] = (ordered[left] if left == right else
            ordered[left] * (right - rank) + ordered[right] * (rank - left))
    return result


def approximate_equal(actual, expected):
    if actual is None or expected is None:
        return actual is expected
    return math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-8)


class Audit:
    def __init__(self):
        self.checks = []

    def check(self, condition, label, detail=None):
        self.checks.append({"check": label, "passed": bool(condition), "detail": detail})

    def hashes(self, base, expected, label):
        mismatches = [name for name, value in expected.items()
                      if not (base / name).is_file() or sha(base / name) != value]
        self.check(not mismatches, label, mismatches)


def schema_names(value):
    names = set()
    if isinstance(value, dict):
        if isinstance(value.get("properties"), dict):
            names.update(value["properties"])
        for nested in value.values():
            names.update(schema_names(nested))
    elif isinstance(value, list):
        for nested in value:
            names.update(schema_names(nested))
    return names


def independent_role(call):
    names = schema_names(call["options"].get("response_format"))
    if any(name in names for name in ("speech", "steps_for_user", "instructions", "steps", "answer_parts")):
        return "answer_generation"
    if names == {"mode"}:
        return "dependency_review"
    for marker, role in (("verdict", "answer_review"), ("needs_personal_facts", "dependency_review"),
                         ("model_size", "compute_classifier")):
        if marker in names:
            return role
    return "unrecognized"


def _unique_parts_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate selected-generation JSON key")
        result[key] = value
    return result


def _unquoted_directives(request):
    return re.sub(r'"[^"\n]*"|“[^”\n]*”|(?<!\w)\'[^\'\n]*\'(?!\w)', " ", request)


def _positive_directive(request, position):
    clause_start = max(request.rfind(mark, 0, position) for mark in ".!?;\n") + 1
    return not re.search(r"\b(?:do\s+not|don't|never|avoid)\b", request[clause_start:position], re.I)


def _first_literal_directive(pattern, request):
    quoted = [(match.start(), match.end()) for match in re.finditer(
        r'"[^"\n]*"|“[^”\n]*”|(?<!\w)\'[^\'\n]*\'(?!\w)', request)]
    for match in re.finditer(pattern, request, re.I):
        if (_positive_directive(request, match.start())
                and not any(left <= match.start() < right for left, right in quoted)):
            return match
    return None


def _scalar_directive(request):
    request = _unquoted_directives(request)
    match = re.search(r"\b(?:return|output|give|answer\s+with)\s+(?:only|just)\s+"
                      r"(?:the\s+|a\s+)?(?:whole\s+number|integer)\b", request, re.I)
    return bool(match and _positive_directive(request, match.start()))


def _numbered_directive(request, count):
    """Recognize counted positive output directives, not quoted/input lists."""
    request = _unquoted_directives(request)
    words = "zero one two three four five six seven eight nine ten eleven twelve".split()
    token = r"(?:\d{1,3}|" + "|".join(words) + r")"
    modifiers = r"(?:(?:short|brief|simple|exact|practical|timed)\s+){0,2}"
    pattern = r"\b(" + token + r")[ -]+" + modifiers + r"numbered\s+(?:steps?|lines?|items?)\b"
    qualifier = r"(?:(?:exactly|only|just)\s+)?(?:(?:a|an)\s+)?(?:(?:friendly|polite|formal|informal|brief|short|simple|concise)\s+)?"
    verbs = r"(?:write|give|provide|return|use|include|produce|compose|draft|output|suggest|choose|pick)"
    eligible = set()
    for match in re.finditer(pattern, request, re.I):
        boundary = max(request.rfind(mark, 0, match.start()) for mark in ".!?;\n") + 1
        prefix = request[boundary:match.start()]
        suffix = re.split(r"[.!?;\n]", request[match.end():], maxsplit=1)[0]
        if not _positive_directive(request, match.start()):
            continue
        if re.search(r"\b(?:passage|paragraph|text|source|input|document|file|example)\s+"
                     r"(?:with|of|containing|having|has|uses)\s+$", prefix, re.I):
            continue
        if re.search(r"\b(?:each|every|per)\b", prefix, re.I) or re.match(
                r"\s*(?:each|apiece|per\b|for\s+(?:each|every)\b|at\s+(?:most|least)|minimum|maximum|or\s+(?:fewer|less|more))", suffix, re.I):
            continue
        if re.match(r"\s+(?:can|could|may|might|is|are|was|were)\b", suffix, re.I):
            continue
        direct = re.search(r"\b" + verbs + r"\s+(?:(?:me|us)\s+)?" + qualifier + "$", prefix, re.I)
        formatted = (re.search(r"\b(?:in|using|with|as|to)\s+" + qualifier + "$", prefix, re.I)
                     and re.search(r"\b(?:write|give|provide|return|respond|answer|reply|use|explain|describe|summarize|rewrite|shorten|condense|format|compose|draft|produce|render|output|keep|limit)\b", prefix, re.I))
        prescribed = re.search(r"\b(?:answer|reply|response|output)\s+(?:must|should)\s+"
                               r"(?:have|contain|use|include|be|consist\s+of)\s+" + qualifier + "$", prefix, re.I)
        standalone = re.fullmatch(r"\s*(?:exactly|only)\s+", prefix, re.I)
        if direct or formatted or prescribed or standalone:
            value = match.group(1).lower()
            eligible.add(int(value) if value.isdigit() else words.index(value))
    return eligible == {count}


def _csv_directive(request):
    text = _unquoted_directives(request)
    for sentence in re.split(r"[.!?\n]", text):
        for clause in (sentence, *sentence.split(";")[1:]):
            clause = re.sub(r"^\s*(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+)?", "", clause, flags=re.I).strip()
            if re.search(r"\b(?:do\s+not|don't|never|avoid)\b", clause, re.I):
                continue
            if (re.fullmatch(r"(?:only\s+CSV|CSV\s+only)[;,\s]*", clause, re.I)
                    or re.match(r"(?:return|output|emit|produce|provide|give|use)\s+(?:(?:only|plain|valid|raw)\s+)*CSV\b", clause, re.I)
                    or re.match(r"(?:convert|format|render|rewrite|return|output|respond|reply|give|provide)\b.*?\b(?:to|into|as|in)\s+(?:(?:plain|valid|raw)\s+)*CSV\b", clause, re.I)):
                return True
    return False


def source_authorized_part_renderings(request, parts):
    """Independent cosmetic rendering candidates; never imports task_parts.

    Separator and list-layout choices are also graded by the independent answer
    reviewers. This provenance check permits only raw content, whitespace/list
    separators and literal header/labels justified by the actual request.
    """
    if (type(parts) is not list or not 1 <= len(parts) <= 32 or
            any(type(part) is not str or not part.strip() or len(part) > 600 or "\n" in part
                for part in parts)):
        raise ValueError("invalid bounded answer_parts")
    clean = [part.strip() for part in parts]
    numbered = _numbered_directive(request, len(parts))
    labelled = _first_literal_directive(r"\b(?:prefixes|labels|(?:start|begin)\s+(?:(?:the|their)\s+)?"
                                       r"(?:lines?|text)\s+with)\s*:?\s*([^.!?\n]+)", request)
    if labelled:
        labels = [re.sub(r"^and\s+", "", value, flags=re.I).strip() + ":"
                  for value in re.findall(r"\b([A-Za-z][A-Za-z -]{0,24}):", labelled.group(1))]
        if len(labels) == len(clean):
            clean = [label + " " + (part[len(label):].lstrip() if part.startswith(label) else part)
                     for label, part in zip(labels, clean)]
    header = None
    if _csv_directive(request):
        declared = _first_literal_directive(r"\bheader\s+(?:(?:must\s+be|should\s+be|is)\s+)?[\"'`]?"
                                           r"([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)+)", request)
        if declared:
            header = ",".join(value.strip() for value in declared.group(1).split(","))
    if header:
        clean.insert(0, header)
    if numbered:
        if any(re.match(r"\s*(?:[-*•]|\d+[.)])\s", part) for part in parts):
            raise ValueError("raw numbered parts already contain application markers")
        return {"\n".join(f"{index}. {part}" for index, part in enumerate(clean, 1))}
    if header:
        return {"\n".join(clean)}
    candidates = {"\n".join(clean), " ".join(clean)}
    if re.search(r"\b(?:bullets?|items?|steps?|checklist)\b", request, re.I):
        candidates.add("\n".join("- " + part for part in clean))
    return candidates


def audit_parts_transforms(audit, raw):
    findings, checked, mixed_prefixes = [], [], []
    for row in raw:
        reply = row.get("reply") or {}
        if reply.get("response_transform") != "task_parts_v1":
            continue
        identifier = row["id"]
        checked.append(identifier)
        try:
            generation = reply["generation"]
            selected = [call for call in row.get("calls", []) if call.get("result") == generation
                        and independent_role(call) == "answer_generation"]
            if not selected:
                raise ValueError("selected parts are absent from actual generation calls")
            users = [message["content"] for message in selected[-1]["messages"] if message.get("role") == "user"]
            request = users[-1] if users else None
            case_text = row["case"]["text"]
            dependency = (row.get("route") or {}).get("dependency") or {}
            fragment = dependency.get("general_request") or ""
            if request != case_text and not (request == fragment and fragment in case_text):
                raise ValueError("formatting request is neither the frozen request nor its literal general fragment")
            content = generation["content"]
            if not isinstance(content, str) or len(content) > 8192:
                raise ValueError("selected parts JSON is unbounded")
            payload = json.loads(content, object_pairs_hook=_unique_parts_fields)
            if type(payload) is not dict or set(payload) != {"answer_parts"}:
                raise ValueError("selected parts JSON has unexpected fields")
            parts = payload["answer_parts"]
            schema = selected[-1]["options"]["response_format"]["properties"]["answer_parts"]
            if not schema.get("minItems", 0) <= len(parts) <= schema.get("maxItems", 32):
                raise ValueError("selected parts count violates the actual requested schema")
            pattern = schema.get("items", {}).get("pattern")
            if pattern and not _scalar_directive(request):
                raise ValueError("scalar schema is not authorized by a positive unquoted integer directive")
            if pattern and any(not isinstance(part, str) or re.fullmatch(pattern, part.strip()) is None for part in parts):
                raise ValueError("selected scalar content violates the actual requested schema")
            renderings = source_authorized_part_renderings(request, parts)
            delivered = row["delivered_text"]
            if delivered != reply["response"]["speech"]:
                raise ValueError("delivered text differs from recorded response speech")
            if delivered not in renderings:
                prefixes = [delivered[:-len(value)] for value in renderings if value and delivered.endswith(value)]
                valid_prefix = next((value for value in prefixes
                    if value.startswith("I don't have that earlier information available. ")
                    and value.endswith("? ") and len(value) <= 500), None)
                if not (fragment and request == fragment and dependency.get("mode") == "required"
                        and reply.get("effective_mode") == "required" and valid_prefix):
                    raise ValueError("delivered parts contain a transformation not authorized by the request")
                mixed_prefixes.append({"id": identifier, "prefix": valid_prefix})
        except (KeyError, ValueError, TypeError, IndexError) as error:
            findings.append({"id": identifier, "issue": str(error)})
    audit.check(not findings, "typed parts reconstruct from raw content and source-authorized formatting", findings)
    return {"checked_case_ids": checked, "mixed_missing_evidence_prefixes": mixed_prefixes,
            "findings": findings,
            "scope": "Independent cosmetic provenance reconstruction; exact task layout and semantic correctness remain subject to the strict answer judgments. Mixed missing-evidence prefix wording is exposed separately, not credited as generated content."}


def judgments_at(path):
    value = read(path)
    if isinstance(value, dict) and "judgments" in value:
        value = value["judgments"]
    if isinstance(value, dict):
        return value
    if len(value) != len({row["id"] for row in value}):
        raise ValueError("duplicate adjudication ID")
    return {row["id"]: row for row in value}


def independent_rows(cases, raw, judgments):
    indexed = {row["id"]: row for row in raw}
    result = []
    for case in cases:
        row = indexed.get(case["id"], {})
        route, reply = row.get("route") or {}, row.get("reply") or {}
        prediction = (route.get("classifier_metadata") or {}).get("whole_request") or {}
        good_status = row.get("status") == "ok"
        delivered = good_status and bool(row.get("delivered_text", "").strip())
        judgment = judgments.get(case["id"], {})
        quality = bool(delivered and judgment.get("quality_pass") is True and
                       all(item["pass"] for item in judgment.get("required_components_pass", [])))
        final = (route.get("dependency") or {}).get("mode")
        expected = case["expected_modes"]
        result.append({"id": case["id"], "category": case["category"], "expected": expected[0],
                       "raw_mode": prediction.get("predicted_mode"), "thresholded_mode": prediction.get("mode"),
                       "final_mode": final, "effective_mode": reply.get("effective_mode"),
                       "raw_match": good_status and prediction.get("predicted_mode") in expected,
                       "thresholded_match": good_status and prediction.get("mode") in expected,
                       "final_match": good_status and final in expected, "quality_pass": quality,
                       "combined_pass": quality and final in expected,
                       "generated": delivered and reply.get("generation") is not None,
                       "application": delivered and reply.get("generation") is None,
                       "seconds": row["wall_ns"] / 1e9 if row.get("wall_ns") is not None else None,
                       "status": row.get("status", "missing")})
    return result


def check_metrics(audit, rows, metrics, label):
    summary = metrics["summary"]
    audit.check(summary["planned"] == len(rows), label + ": planned denominator")
    counts = {}
    for key in ("raw_match", "thresholded_match", "final_match", "quality_pass", "combined_pass"):
        count = sum(row[key] for row in rows)
        counts[key] = count
        supplied = summary[key]
        audit.check(supplied["count"] == count and supplied["denominator"] == len(rows)
                    and approximate_equal(supplied["rate"], count / len(rows) if rows else None), label + ": " + key)
    for field, metric in (("category", "per_category"), ("expected", "per_mode")):
        for group in sorted({row[field] for row in rows}):
            subset = [row for row in rows if row[field] == group]
            entry = metrics[metric][group]
            audit.check(entry["planned"] == len(subset), f"{label}: {metric}/{group} denominator")
            for key in counts:
                audit.check(entry[key]["count"] == sum(row[key] for row in subset)
                            and entry[key]["denominator"] == len(subset), f"{label}: {metric}/{group}/{key}")
    groups = {"overall_observed": rows,
              "delivered_model_generated": [row for row in rows if row["generated"]],
              "application_only": [row for row in rows if row["application"]],
              "full_quality": [row for row in rows if row["quality_pass"]],
              "combined_success": [row for row in rows if row["combined_pass"]]}
    latency_result = {}
    for name, subset in groups.items():
        computed = independent_latency([row["seconds"] for row in subset if row["seconds"] is not None])
        latency_result[name] = computed
        audit.check(all(approximate_equal(metrics["latency"][name][key], value) for key, value in computed.items()),
                    f"{label}: latency/{name}", computed)
    for dimension, key in (("category", "per_category"), ("expected", "per_mode")):
        for group in sorted({row[dimension] for row in rows}):
            computed = independent_latency([row["seconds"] for row in rows if row[dimension] == group and row["seconds"] is not None])
            audit.check(all(approximate_equal(metrics["latency"][key][group][name], value)
                            for name, value in computed.items()), f"{label}: latency/{key}/{group}")
    for seconds in (5, 10, 30, 60):
        for field, metric in (("quality_pass", "quality_deadlines"), ("combined_pass", "combined_deadlines")):
            count = sum(row[field] and row["seconds"] is not None and row["seconds"] <= seconds for row in rows)
            audit.check(metrics[metric][str(seconds)]["count"] == count
                        and metrics[metric][str(seconds)]["denominator"] == len(rows), f"{label}: {metric}/{seconds}")
        count = sum(row["generated"] and row["quality_pass"] and row["seconds"] is not None and row["seconds"] <= seconds for row in rows)
        for metric, denominator in (("generated_quality_deadlines", sum(row["generated"] for row in rows)),
                                    ("generated_quality_deadlines_all_planned", len(rows))):
            audit.check(metrics[metric][str(seconds)]["count"] == count
                        and metrics[metric][str(seconds)]["denominator"] == denominator, f"{label}: {metric}/{seconds}")
    return {"planned": len(rows), "counts": counts, "statuses": dict(Counter(row["status"] for row in rows)),
            "latency": latency_result}


def audit_resources(audit, collection, label):
    start, finish = read(collection / "start.json"), read(collection / "finish.json")
    end = finish["snapshot"]
    audit.check(start["memory"]["mem_available_kib"] >= 2 * 1024 * 1024
                and start["memory"]["swap_used_kib"] <= 768 * 1024
                and max(start["temperatures_c"].values()) < 55, label + ": startup resource gates")
    audit.check(not start["resident_models"] and not end["resident_models"], label + ": initial/final model eviction")
    audit.check(start["fan_pwm"] > 0 and end["fan_pwm"] > 0, label + ": running fan snapshots")
    audit.check(all(start[key] == end[key] for key in ("boot_id", "power_mode", "thermal_trip_events"))
                and start["memory"]["swap_total_kib"] == end["memory"]["swap_total_kib"],
                label + ": device invariants")
    audit.check(bool(re.search(r"NV Power Mode:\s*15W\s*\n0\s*$", start["power_mode"]))
                and bool(start["thermal_trip_events"]) and not any(start["thermal_trip_events"].values()),
                label + ": power mode and zero trip counters")
    audit.check(finish["failure"] is None and not finish["cleanup_errors"] and finish["guard_violation"] is None,
                label + ": guard and cleanup outcome")
    telemetry = lines(collection / "telemetry.jsonl")
    free = [sample["ram"]["total_mb"] - sample["ram"]["used_mb"] for sample in telemetry]
    swap = [sample["swap"]["used_mb"] for sample in telemetry]
    temperature = [max(sample["temperatures_c"].values()) for sample in telemetry]
    timestamps = [sample["monotonic_ns"] for sample in telemetry]
    gaps = [(later - earlier) / 1e9 for earlier, later in zip(timestamps, timestamps[1:])]
    audit.check(bool(telemetry) and len(telemetry) == finish["telemetry"]["sample_count"], label + ": telemetry count")
    audit.check(all(0 < gap <= 5 for gap in gaps), label + ": telemetry monotonic and unstalled")
    audit.check(bool(telemetry) and min(free) >= 768 and max(swap) <= 1024 and max(temperature) < 68,
                label + ": sampled runtime RAM/swap/temperature bounds")
    return {"samples": len(telemetry), "minimum_free_ram_mb": min(free), "maximum_swap_used_mb": max(swap),
            "maximum_temperature_c": max(temperature), "maximum_sample_gap_seconds": max(gaps, default=0),
            "residency_scope": "Snapshots show startup/final empty. Existing backend checks enforce at most one resident model; raw tegrastats has no model-residency field."}


def audit_memory(audit, collection, raw, label):
    retrieval_path = collection / "run/retrieval_calls.jsonl"
    retrieval = lines(retrieval_path) if retrieval_path.exists() else []
    retrieval_results = [row for row in retrieval if row["operation"] == "retrieve"]
    successful = [row for row in retrieval_results if row["status"] == "ok"]
    errors = [row for row in retrieval_results if row["status"] != "ok"]
    audit.check(all(row.get("result") == [] for row in successful),
                label + ": all successful retrieval results empty")
    audit.check(all(row["status"] == "error" and isinstance(row.get("error"), dict)
                    and row.get("result") in (None, []) for row in errors),
                label + ": failed retrievals preserve explicit errors without evidence")
    evidence = []
    for row in raw:
        reply = row.get("reply") or {}
        diagnostics = reply.get("memory_diagnostics") or {}
        for name in ("retrieved_ids", "supplied_ids", "model_used_ids"):
            if diagnostics.get(name):
                evidence.append({"id": row["id"], "field": name})
        for name in ("reference_ids", "application_memory_ids", "retrieval"):
            if reply.get(name):
                evidence.append({"id": row["id"], "field": name})
        if (reply.get("response") or {}).get("memory_used"):
            evidence.append({"id": row["id"], "field": "response.memory_used"})
    audit.check(not evidence, label + ": no fabricated memory evidence IDs", evidence)
    database = collection / "run/memory.sqlite3"
    before = sha(database)
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        counts = {name: connection.execute('SELECT count(*) FROM "' + name + '"').fetchone()[0]
                  for name in ("memory_item", "memory_audit", "memory_embedding", "memory_fts")}
        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
    audit.check(not any(counts.values()) and quick_check == "ok", label + ": isolated SQLite empty and valid", counts)
    audit.check(sha(database) == before, label + ": SQLite audit was read-only")
    return {"retrieval_calls": len(retrieval_results), "successful_empty_retrievals": len(successful),
            "retrieval_error_count": len(errors),
            "retrieval_errors": [{"id": row.get("case_id"), "error": row["error"]} for row in errors],
            "candidate_retrieval_operations_successful": not errors,
            "table_counts": counts, "database_quick_check": quick_check,
            "error_interpretation": "Recorded retrieval errors are candidate outcomes, not empty-result successes or artifact-integrity failures."}


def flat(text):
    return " ".join(text.casefold().split())


def audit_prompt_boundaries(audit, cases, calls, label):
    all_rubric_strings = [text for case in cases for key in ("required_components", "forbidden")
                          for text in case.get("rubric", {}).get(key, []) if isinstance(text, str)]
    uniqueness = Counter(flat(text) for text in all_rubric_strings)
    cases_by_id = {case["id"]: case for case in cases}
    hidden_keys = re.compile(r'["\'](?:expected_modes|required_components|forbidden|rubric|general_component_expected|clarification_expected)["\']\s*:')
    findings = []
    checked = 0
    for call_index, call in enumerate(calls, 1):
        case = cases_by_id[call["case_id"]]
        authorized_input = " ".join([case["text"], *[message["content"] for message in case.get("prior_turns", [])]])
        authorized_flat = flat(authorized_input)
        candidates = [phrase for phrase in all_rubric_strings if len(phrase) >= 40 and len(phrase.split()) >= 6
                      and uniqueness[flat(phrase)] == 1 and flat(phrase) not in authorized_flat]
        for message in call["messages"]:
            content = message["content"]
            checked += 1
            for match in hidden_keys.finditer(content):
                if match.group() not in authorized_input:
                    findings.append({"call_index": call_index, "id": case["id"], "kind": "hidden_rubric_key", "value": match.group()})
            if case["id"] in content and case["id"] not in authorized_input:
                findings.append({"call_index": call_index, "id": case["id"], "kind": "hidden_case_id"})
            for phrase in candidates:
                if flat(phrase) in flat(content):
                    findings.append({"call_index": call_index, "id": case["id"], "kind": "unique_complete_rubric_literal", "value": phrase})
    audit.check(not findings, label + ": no hidden labels or unique rubric literals in model prompts", findings)
    return {"messages_checked": checked, "rubric_strings_available": len(all_rubric_strings), "findings": findings,
            "scope": "Checks hidden rubric-field keys, case IDs, and unique complete rubric sentences >=40 characters/6 words absent from authorized input. Generic mode words are intentionally excluded; this literal check is not proof against semantic leakage."}


BOUNDS = {"answer_generation": 2, "answer_review": 2, "dependency_review": 1,
          "compute_classifier": 1}
MODES = ("none", "optional", "required", "clarify")
EXPECTED_POLICY = {
    "policy_id": "complete_system_stage2_common_device_limits_v1",
    "min_start_available_kib": 2097152, "max_start_swap_used_kib": 786432,
    "max_start_temperature_c_exclusive": 55.0,
    "min_runtime_available_kib": 786432, "max_runtime_swap_used_kib": 1048576,
    "max_runtime_temperature_c_exclusive": 68.0, "maximum_resident_models": 1,
    "power_mode": "15W mode 0", "fan_required": True,
    "unchanged_boot_and_thermal_trip_counters": True, "telemetry_interval_ms": 500,
    "telemetry_stall_ceiling_seconds": 5, "persistent_system_changes": False,
}


def audit_sources(audit, cohort, source_root, candidate, initial):
    frozen = candidate["source_sha256"]
    audit.hashes(cohort / "candidate_source", frozen, "archived candidate SHA256")
    audit.hashes(source_root, frozen, "selected verification source SHA256")
    audit.check(initial["source_sha256"] == frozen, "complete runtime source set was frozen")
    working_drift = [name for name, expected in frozen.items()
                     if not (ROOT / name).is_file() or sha(ROOT / name) != expected]
    if candidate.get("tests_sha256"):
        audit.hashes(cohort / "tests", candidate["tests_sha256"], "archived offline tests SHA256")
    if candidate.get("working_diff_sha256"):
        audit.check(sha(cohort / "working_changes.diff") == candidate["working_diff_sha256"],
                    "archived working diff SHA256")
    return {"verification_source_root": str(source_root.resolve()),
            "archived_source_count": len(frozen), "working_source_drift": working_drift,
            "working_drift_interpretation": "Working drift is permitted only when another explicit source root, normally the historical archive, is verified. It never changes the cohort's archived candidate."}


def audit_calls(audit, raw, calls, models, metrics=None):
    flattened = [call for row in raw for call in row.get("calls", [])]
    audit.check(flattened == calls, "all durable raw calls match observations exactly")
    roles = Counter(independent_role(call) for call in calls)
    audit.check("unrecognized" not in roles, "all actual call schemas recognized")
    audit.check(all(call["model"] in models["models"] and
                    (not call.get("result") or call["result"].get("model") == call["model"])
                    for call in calls), "every call and result uses its frozen model")
    bounds, provenance, deterministic = {}, [], []
    generation_distribution = Counter()
    for row in raw:
        identifier = row["id"]
        own_calls = row.get("calls", [])
        counts = Counter(independent_role(call) for call in own_calls)
        generation_distribution[counts["answer_generation"]] += 1
        exceeded = {role: {"actual": counts[role], "maximum": bound}
                    for role, bound in BOUNDS.items() if counts[role] > bound}
        if exceeded:
            bounds[identifier] = exceeded
        if any(call.get("case_id") != identifier for call in own_calls):
            provenance.append({"id": identifier, "issue": "call case ID mismatch"})
        reply, route = row.get("reply") or {}, row.get("route") or {}
        if reply:
            for role, field in (("answer_generation", "attempts"), ("answer_review", "review_attempts")):
                actual = [call["result"] for call in own_calls
                          if independent_role(call) == role and call.get("result") is not None]
                if actual != reply.get(field, []):
                    provenance.append({"id": identifier, "issue": field + " do not preserve successful raw results"})
            if reply.get("attempted_models", []) != [call["model"] for call in own_calls
                                                       if independent_role(call) == "answer_generation"]:
                provenance.append({"id": identifier, "issue": "attempted model sequence mismatch"})
            if reply.get("generation") is not None and reply["generation"] not in reply.get("attempts", []):
                provenance.append({"id": identifier, "issue": "selected generation absent from attempts"})
            if any(review.get("generation") not in reply.get("review_attempts", [])
                   for review in reply.get("answer_reviews", [])):
                provenance.append({"id": identifier, "issue": "parsed review absent from raw review attempts"})
        if route.get("model_size_decision_source") == "dependency_size_policy_v2":
            deterministic.append(identifier)
            if counts["compute_classifier"] or route.get("model_size_generation") is not None:
                provenance.append({"id": identifier, "issue": "deterministic size policy has a compute call or fabricated generation"})
        for field, role in (("model_size_generation", "compute_classifier"),
                            ("review_generation", "dependency_review"),
                            ("answerability_generation", "dependency_review")):
            value = route.get(field)
            if value is not None and not any(call.get("result") == value and independent_role(call) == role
                                             for call in own_calls):
                provenance.append({"id": identifier, "issue": "route " + field + " missing from actual calls"})
    audit.check(not provenance, "attempts, selections, reviews and skipped compute retain actual provenance", provenance)
    totals = {
        "total": len(calls), "by_role": dict(roles),
        "by_model": dict(Counter(call["model"] for call in calls)),
        "by_status": dict(Counter(call["status"] for call in calls)),
        "bound_violations": bounds,
        "recorded_call_wall_seconds_total": math.fsum(call["wall_ns"] for call in calls) / 1e9,
        "backend_total_seconds_available": math.fsum((call.get("result") or {}).get("total_duration_ns") or 0 for call in calls) / 1e9,
        "backend_load_seconds_available": math.fsum((call.get("result") or {}).get("load_duration_ns") or 0 for call in calls) / 1e9,
        "calls_missing_backend_duration": sum((call.get("result") or {}).get("total_duration_ns") is None for call in calls),
    }
    if metrics is not None:
        for key, expected in totals.items():
            value = metrics["actual_calls"][key]
            audit.check(approximate_equal(value, expected) if isinstance(expected, (int, float)) else value == expected,
                        "independent actual_calls/" + key, expected)
        audit.check(metrics["actual_calls"]["declared_bounds_per_case"] == BOUNDS, "declared call bounds agree")
        # Missing planned cases also count as zero actual calls and attempts.
        missing = metrics["summary"]["planned"] - len(raw)
        call_distribution = Counter(len(row.get("calls", [])) for row in raw)
        if missing:
            call_distribution[0] += missing
            generation_distribution[0] += missing
        for key, expected in (("call_count_distribution", call_distribution),
                              ("generation_attempt_distribution", generation_distribution)):
            audit.check(metrics["actual_calls"][key] == {str(k): v for k, v in expected.items()},
                        "independent actual_calls/" + key)
    totals.update(deterministic_size_policy_cases=deterministic,
                  candidate_within_declared_call_bounds=not bounds,
                  timing_interpretation="Backend load is part of backend total; call wall is part of case wall. No causal overhead estimate is inferred.")
    return totals


def audit_derived_rows(audit, cases, raw, judgments, rows, metrics, reported_rows):
    audit.check([row["id"] for row in reported_rows] == [case["id"] for case in cases],
                "derived per-case output keeps all planned cases in order")
    observed = {row["id"]: row for row in raw}
    for independent, reported, case in zip(rows, reported_rows, cases):
        identifier = case["id"]
        original = observed.get(identifier, {})
        reply = original.get("reply") or {}
        expected = {key: independent[key] for key in (
            "id", "raw_mode", "thresholded_mode", "final_mode", "effective_mode",
            "raw_match", "thresholded_match", "final_match", "quality_pass", "combined_pass", "status")}
        expected.update(wall_seconds=independent["seconds"], attempts=reply.get("attempts", []),
                        review_attempts=reply.get("review_attempts", []),
                        attempted_models=reply.get("attempted_models", []),
                        answer_reviews=reply.get("answer_reviews", []),
                        delivered_text=original.get("delivered_text"))
        audit.check(all(reported.get(key) == value for key, value in expected.items()),
                    "derived per-case raw provenance: " + identifier)
        own_calls = original.get("calls", [])
        audit.check(len(reported.get("calls", [])) == len(own_calls) and
                    all(recorded["model"] == call["model"] and recorded["role"] == independent_role(call)
                        and recorded["wall_ns"] == call["wall_ns"] and recorded["status"] == call["status"]
                        for recorded, call in zip(reported.get("calls", []), own_calls)),
                    "derived per-call fields: " + identifier)
        judgment = judgments.get(identifier, {})
        flags = set(judgment.get("flags", []))
        if not original:
            flags.add("missing_observation")
        elif original["status"] == "error":
            flags.add("execution_error")
        if not judgment:
            flags.add("missing_judgment")
        audit.check(set(reported.get("flags", [])) == flags, "derived case flags: " + identifier)
    for field in ("raw_mode", "thresholded_mode", "final_mode", "effective_mode"):
        confusion = {mode: dict(Counter((row[field] or "unavailable") if row["status"] == "ok" else row["status"]
                                       for row in rows if row["expected"] == mode)) for mode in MODES}
        audit.check(metrics["confusion"][field] == confusion, "independent confusion/" + field)
    summary_counts = {"observed": len(raw), "errors": sum(row["status"] == "error" for row in rows),
                      "missing": sum(row["status"] == "missing" for row in rows),
                      "delivered": sum(row["generated"] or row["application"] for row in rows),
                      "generated_delivery": sum(row["generated"] for row in rows),
                      "application_delivery": sum(row["application"] for row in rows)}
    audit.check(all(metrics["summary"][key] == value for key, value in summary_counts.items()),
                "independent delivery and error denominators", summary_counts)
    audit.check(approximate_equal(metrics["actual_calls"]["case_wall_seconds_total"],
                                 math.fsum(row["seconds"] or 0 for row in rows)), "independent total case wall time")


def audit_cohort(audit, args):
    cohort = args.cohort_dir.resolve()
    collection = cohort / "collection"
    cases_path = cohort / "cases.json"
    cases, raw = cases_at(cases_path), lines(collection / "run/observations.jsonl")
    candidate = read(cohort / "candidate_freeze.json")
    freeze = read(cohort / "evaluation_freeze.json")
    metrics = read(args.metrics) if not args.artifacts_only else None
    judgments = judgments_at(args.judgments) if not args.artifacts_only else {}
    source_root = args.source_root.resolve()
    identifiers = [case["id"] for case in cases]
    audit.check(bool(cases) and len(identifiers) == len(set(identifiers)), "nonempty unique planned cohort")
    audit.check(all(len(case["expected_modes"]) == 1 and case["expected_modes"][0] in MODES for case in cases),
                "one valid preregistered dependency label per case")
    audit.check([row["id"] for row in raw] == identifiers, "every planned observation retained in exact frozen order")
    audit.check(all(row["case"] == case for row, case in zip(raw, cases)), "embedded cases unchanged")
    audit.check(all(row.get("stage") == "conversation" and row.get("policy") == "learned" for row in raw),
                "normal learned conversation policy used")
    audit.check(candidate["cases_sha256"] == freeze["cases_sha256"] == sha(cases_path), "candidate and preregistered corpus hashes")
    audit.hashes(cohort, freeze["artifact_sha256"], "preregistered artifact SHA256")
    audit.hashes(collection, read(collection / "artifact_sha256.json"), "sealed collection SHA256")
    initial, final = read(collection / "integrity_before.json"), read(collection / "integrity_after.json")
    audit.check(initial == final and initial["cases_sha256"] == sha(cases_path),
                "before/after source, configuration, corpus and embeddings unchanged")
    audit.check(freeze["source_sha256"] == candidate["source_sha256"], "evaluation and candidate source sets agree")
    sources = audit_sources(audit, cohort, source_root, candidate, initial)
    models = read(collection / "models_before.json")
    audit.check(models == read(collection / "models_after.json"), "model digests and server version unchanged")
    audit.check(all(re.fullmatch(r"[0-9a-f]{64}", model["digest"]) and
                    0 < model["parameter_count"] < 4_000_000_000 and model["size"] <= 1_610_612_736
                    for model in models["models"].values()), "model artifact bounds")
    launch = read(collection / "launch.json")
    audit.check(all(launch["policy"].get(key) == value for key, value in EXPECTED_POLICY.items()),
                "unchanged strict Stage 2 guard policy")
    audit.check(launch["case_count"] == len(cases) <= launch["declared_max_cases"] <= 64
                and not launch["validation_only"] and launch["generation_parameters_modified"] is False,
                "declared bounded cohort and unchanged generation parameters")
    audit.check(launch["candidate_manifest_sha256"] == sha(cohort / "candidate_freeze.json"),
                "launcher used this candidate manifest")
    metadata, summary = read(collection / "run/metadata.json"), read(collection / "run/summary.json")
    audit.check(metadata["cases_sha256"] == sha(cases_path) and
                metadata["config_sha256"] == hashlib.sha256(json.dumps(initial["config"], sort_keys=True).encode()).hexdigest(),
                "runner corpus and configuration hashes")
    audit.check(all(initial["source_sha256"].get(name) == value for name, value in metadata["source_sha256"].items()),
                "runner runtime source hashes")
    audit.check(metadata["case_count"] == summary["case_count"] == len(cases) and
                summary["completed"] == len(raw), "runner planned and completed denominators")
    audit.check(summary["label_matches"] == sum(row["diagnostic"]["label_match"] is True for row in raw),
                "runner raw label-match summary")
    calls_path = collection / "run/model_calls.jsonl"
    calls = lines(calls_path) if calls_path.exists() else []
    call_report = audit_calls(audit, raw, calls, models, metrics)
    transforms = audit_parts_transforms(audit, raw)
    resources = audit_resources(audit, collection, "cohort")
    memory = audit_memory(audit, collection, raw, "cohort")
    prompts = audit_prompt_boundaries(audit, cases, calls, "cohort")
    result = {"cohort_dir": str(cohort), "cohort_kind": args.cohort_kind,
              "preregistered_scope": freeze.get("scope"), "case_ids": identifiers,
              "source_verification": sources, "model_identities": models,
              "actual_calls": call_report, "resources": resources, "memory": memory,
              "parts_transform_provenance": transforms,
              "prompt_boundaries": prompts, "measurement_audited": not args.artifacts_only,
              "interpretation": "This single cohort is never merged with another attempt. Known development/replay cases do not become fresh by receiving new model outputs."}
    kind_scope = str(freeze.get("scope", "")).casefold()
    audit.check(not (args.cohort_kind == "fresh_holdout" and ("known" in kind_scope or "development" in kind_scope)),
                "known development is not relabeled as fresh")
    if metrics is not None:
        audit.check(set(judgments) == set(identifiers), "complete exact adjudication coverage")
        audit.check(all(type(j.get("quality_pass")) is bool and
                        (not j["quality_pass"] or all(c["pass"] is True for c in j.get("required_components_pass", [])))
                        for j in judgments.values()), "boolean judgments agree with required components")
        rows = independent_rows(cases, raw, judgments)
        result["arithmetic"] = check_metrics(audit, rows, metrics, "cohort")
        audit_derived_rows(audit, cases, raw, judgments, rows, metrics, lines(args.per_case))
        finish = read(collection / "finish.json")
        clean = (finish.get("failure") is None and not finish.get("cleanup_errors") and
                 finish.get("guard_violation") is None and summary.get("failure") is None and
                 summary.get("cleanup_error") is None)
        complete = len(raw) == len(cases) and set(judgments) == set(identifiers) and clean
        audit.check(metrics["evaluation_complete"] == complete and
                    metrics["operational_success"] == bool(finish.get("complete")),
                    "evaluation completion and operational outcome remain separate")
        result["evaluation_complete"] = complete
    paths = [cohort / "cases.json", cohort / "candidate_freeze.json", cohort / "evaluation_freeze.json",
             collection / "artifact_sha256.json", collection / "run/observations.jsonl", Path(__file__).resolve()]
    if metrics is not None:
        paths.extend([args.metrics, args.judgments, args.per_case])
    result["audited_artifact_sha256"] = {str(path.resolve()): sha(path) for path in paths}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-dir", type=Path, required=True)
    parser.add_argument("--cohort-kind", choices=("development", "known_replay", "fresh_holdout"), required=True)
    parser.add_argument("--source-root", type=Path, default=ROOT,
                        help="Working repository, or historical COHORT/candidate_source")
    parser.add_argument("--metrics", type=Path)
    parser.add_argument("--judgments", type=Path)
    parser.add_argument("--per-case", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--artifacts-only", action="store_true",
                        help="Audit a finalized collection before judgments exist; explicitly not a completed measurement audit")
    args = parser.parse_args(argv)
    args.metrics = args.metrics or args.cohort_dir / "metrics.json"
    args.judgments = args.judgments or args.cohort_dir / "adjudicated_judgments.json"
    args.per_case = args.per_case or args.metrics.parent / "per_case.jsonl"
    args.output = args.output or args.cohort_dir / ("independent_artifact_audit.json" if args.artifacts_only else "independent_audit.json")
    # Refuse to overwrite prior audit attempts or any collected/sealed inputs.
    if args.output.exists():
        parser.error("audit output already exists; choose a new --output path")
    audit = Audit()
    result = {"created_at": datetime.now(timezone.utc).isoformat(),
              "method": "Independent standard-library arithmetic and artifact checks; no production, analyzer or reviewer imports."}
    try:
        result.update(audit_cohort(audit, args))
    except Exception as error:
        audit.check(False, "audit execution completed", {"type": type(error).__name__, "message": str(error)})
    result["checks"] = audit.checks
    result["checks_passed"] = sum(check["passed"] for check in audit.checks)
    result["checks_failed"] = sum(not check["passed"] for check in audit.checks)
    result["passed"] = bool(audit.checks) and result["checks_failed"] == 0
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps({key: result[key] for key in ("passed", "checks_passed", "checks_failed")}, indent=2))
    for check in audit.checks:
        if not check["passed"]:
            print("FAILED: " + check["check"] + " " + json.dumps(check["detail"]))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
