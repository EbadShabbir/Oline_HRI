#!/usr/bin/env python3
"""Render final sealed changing-memory judgments as tables; never score answers."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys


ANALYZER_V2_SHA256 = "7013efb9a06860d676b0d0922494ad65795841923dcebc5ae4e73519356b4cb8"
BRANCHES = ("correction", "deletion", "expiry")
CORE_COLUMNS = ("planned", "attempted", "delivered", "useful_correct", "forbidden_disclosure",
                "withheld", "interrupted", "missing")


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def read_lines(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_json(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def verify_seal(directory):
    manifest = read_json(directory / "seal.json")["sha256"]
    actual = {str(p.relative_to(directory)) for p in directory.rglob("*")
              if p.is_file() and p != directory / "seal.json"}
    if actual != set(manifest) or any(digest(directory / name) != h for name, h in manifest.items()):
        raise ValueError(f"Seal mismatch: {directory}")


def stage(row):
    e = row["expected"]
    prefix = e["scenario_id"] + "_" + e["branch"] + "_"
    if not row["checkpoint_id"].startswith(prefix):
        raise ValueError("Checkpoint identifier does not bind its scenario/branch")
    label = row["checkpoint_id"][len(prefix):]
    suffix = "_" + e["history_mode"]
    return label[:-len(suffix)] if label.endswith(suffix) else label


def basic(rows):
    return {"planned": len(rows), "attempted": sum(r["observed"] for r in rows),
            "delivered": sum(r["diagnostics"]["status"] == "delivered" for r in rows),
            "useful_correct": sum(r["judgment"]["useful_correct"] for r in rows),
            "forbidden_disclosure": sum(r["judgment"]["forbidden_disclosure"] for r in rows),
            "withheld": sum(r["diagnostics"]["status"] == "withheld" for r in rows),
            "interrupted": sum(r["diagnostics"]["status"] == "interrupted" for r in rows),
            "missing": sum(not r["observed"] for r in rows)}


def dimensions(row):
    e = row["expected"]
    return {"scenario_id": e["scenario_id"], "category": e["category"], "branch": e["branch"],
            "stage": stage(row), "history_mode": e["history_mode"],
            "restart_phase": "after" if e["after_restart"] else "before", "expected_kind": e["expected_kind"]}


def grouped(rows, fields):
    groups = defaultdict(list)
    for row in rows:
        d = dimensions(row)
        groups[tuple(d[field] for field in fields)].append(row)
    return [{**dict(zip(fields, key)), **basic(value)} for key, value in sorted(groups.items())]


def disclosure_scope(row, scope):
    """Use existing canonical judgment labels; never inspect answer strings."""
    e, j = row["expected"], row["judgment"]
    disclosed = set(j["disclosed_forbidden_values"])
    state = e["mutation_state"]
    if scope == "all_forbidden":
        return True, j["forbidden_disclosure"]
    if scope == "stale_subject_broad_correction":
        eligible = state == "correction"
    elif scope == "stale_subject_current_replacement":
        eligible = e["expected_kind"] == "replacement"
    elif scope == "deleted_subject":
        eligible = state == "deletion"
    elif scope in {"expired_subject", "any_expired_fact"}:
        eligible = state == "expiry"
    elif scope == "unstored_replacement_deletion_or_expiry":
        eligible = state in {"deletion", "expiry"}
        return eligible, eligible and e["replacement_subject_value"] in disclosed
    else:
        raise ValueError(f"Unknown disclosure scope: {scope}")
    if scope == "any_expired_fact":
        # Same frozen definition as analyzer v2: the never-stored replacement is
        # forbidden, but is not an expired stored subject or historical control.
        return eligible, eligible and bool(disclosed - {e["replacement_subject_value"]})
    return eligible, eligible and e["original_subject_value"] in disclosed


DISCLOSURE_SCOPES = ("all_forbidden", "stale_subject_broad_correction", "stale_subject_current_replacement",
                     "deleted_subject", "expired_subject", "any_expired_fact",
                     "unstored_replacement_deletion_or_expiry")


def disclosure_tables(rows):
    output = []
    for scope in DISCLOSURE_SCOPES:
        for history in ("all", "retained", "fresh"):
            for restart in ("all", "before", "after"):
                selected = [r for r in rows if disclosure_scope(r, scope)[0]
                            and (history == "all" or r["expected"]["history_mode"] == history)
                            and (restart == "all" or dimensions(r)["restart_phase"] == restart)]
                if selected:
                    output.append({"scope": scope, "history_mode": history, "restart_phase": restart,
                                   "eligible_planned": len(selected),
                                   "eligible_delivered": sum(r["diagnostics"]["status"] == "delivered" for r in selected),
                                   "disclosures": sum(disclosure_scope(r, scope)[1] for r in selected)})
    return output


def expected_pairs(rows):
    groups = defaultdict(dict)
    for row in rows:
        e = row["expected"]
        key = (e["scenario_id"], e["branch"], e["logical_time"], e["question"])
        if e["history_mode"] in groups[key]:
            raise ValueError("Duplicate history mode in an authored matched-pair key")
        groups[key][e["history_mode"]] = row
    pairs = []
    for key, group in sorted(groups.items()):
        if set(group) == {"retained", "fresh"}:
            r, f = group["retained"], group["fresh"]
            if r["expected"]["after_restart"] != f["expected"]["after_restart"]:
                raise ValueError("History pair crosses scheduled restart status")
            pairs.append({"retained_checkpoint": r["checkpoint_id"], "fresh_checkpoint": f["checkpoint_id"],
                          "retained_success": r["judgment"]["useful_correct"],
                          "fresh_success": f["judgment"]["useful_correct"],
                          "retained_disclosure": r["judgment"]["forbidden_disclosure"],
                          "fresh_disclosure": f["judgment"]["forbidden_disclosure"],
                          "both_observed": r["observed"] and f["observed"]})
    return pairs


def pair_tables(rows, pairs):
    by_id = {r["checkpoint_id"]: r for r in rows}
    detailed = []
    for pair in pairs:
        retained = by_id[pair["retained_checkpoint"]]
        fresh = by_id[pair["fresh_checkpoint"]]
        original = lambda r: r["expected"]["original_subject_value"] in r["judgment"]["disclosed_forbidden_values"]
        detailed.append({**dimensions(retained), **pair,
                         "retained_revoked_subject_disclosure": original(retained),
                         "fresh_revoked_subject_disclosure": original(fresh)})
    aggregate = []
    for branch in ("all", *BRANCHES):
        for restart in ("all", "before", "after"):
            selected = [p for p in detailed if (branch == "all" or p["branch"] == branch)
                        and (restart == "all" or p["restart_phase"] == restart)]
            count = {"branch": branch, "restart_phase": restart, "pairs": len(selected),
                     "both_observed": sum(p["both_observed"] for p in selected)}
            for prefix, first, second in (("success", "retained_success", "fresh_success"),
                                          ("disclosure", "retained_disclosure", "fresh_disclosure"),
                                          ("revoked_subject_disclosure", "retained_revoked_subject_disclosure", "fresh_revoked_subject_disclosure")):
                count.update({prefix + "_both": sum(p[first] and p[second] for p in selected),
                              prefix + "_retained_only": sum(p[first] and not p[second] for p in selected),
                              prefix + "_fresh_only": sum(not p[first] and p[second] for p in selected),
                              prefix + "_neither": sum(not p[first] and not p[second] for p in selected)})
            aggregate.append(count)
    return aggregate, detailed


def selection_tables(rows):
    details, calls, route_groups, call_groups = [], [], Counter(), Counter()
    for row in rows:
        observed = row["observed_record"] or {}
        route = observed.get("route") or {}
        decision = route.get("decision") or {}
        generation = [c for c in observed.get("calls", []) if c.get("purpose") == "generation"]
        requested = [c.get("requested_model", c.get("model")) for c in generation]
        actual = [c.get("actual_model") for c in generation]
        route_key = (route.get("policy"), decision.get("memory_required"), decision.get("model_size"))
        route_groups[route_key] += 1
        details.append({"checkpoint_id": row["checkpoint_id"], **dimensions(row),
                        "status": row["diagnostics"]["status"], "recorded_route_policy": route_key[0],
                        "memory_required": route_key[1], "nominal_model_size": route_key[2],
                        "generation_policy": observed.get("generation_policy"),
                        "fallback_from_model": observed.get("fallback_from_model"),
                        "generation_call_count": len(generation), "requested_generation_models": requested,
                        "actual_generation_models": actual})
        for index, call in enumerate(generation):
            request, returned = requested[index], actual[index]
            status = call.get("status", "unrecorded")
            calls.append({"checkpoint_id": row["checkpoint_id"], "generation_call_index": index,
                          "branch": row["expected"]["branch"], "history_mode": row["expected"]["history_mode"],
                          "restart_phase": dimensions(row)["restart_phase"],
                          "requested_model": request, "actual_model": returned, "call_status": status})
            for scope in ("all", row["expected"]["branch"]):
                call_groups[(scope, request, returned, status)] += 1
    routes = [{"recorded_route_policy": k[0], "memory_required": k[1], "nominal_model_size": k[2], "checkpoints": v}
              for k, v in sorted(route_groups.items(), key=lambda item: repr(item[0]))]
    aggregated = [{"branch": k[0], "requested_model": k[1], "actual_model": k[2], "call_status": k[3], "calls": v}
                  for k, v in sorted(call_groups.items(), key=lambda item: repr(item[0]))]
    return details, calls, routes, aggregated


def workload_counts(runtime, ledger):
    """Derive lifecycle coverage while rejecting truncated or misbound schedules."""
    branches = runtime.get("branches", [])
    checkpoints = ledger.get("checkpoints", [])
    if not branches or not checkpoints:
        raise ValueError("Authored workload must not be empty")
    expected = {c["checkpoint_id"]: c for c in checkpoints}
    if len(expected) != len(checkpoints) or ledger.get("checkpoint_count") != len(checkpoints):
        raise ValueError("Ledger checkpoint identities/count disagree")
    branch_ids = [b["branch_id"] for b in branches]
    if len(set(branch_ids)) != len(branch_ids):
        raise ValueError("Duplicate authored branch")
    scenarios = sorted({b["scenario_id"] for b in branches})
    planned, disclosures, stage_counts, pairs = {}, 0, Counter(), {}
    expected_branch_counts = {"correction": 10, "deletion": 7, "expiry": 7}
    for scenario in scenarios:
        names = [b["branch"] for b in branches if b["scenario_id"] == scenario]
        if Counter(names) != Counter({name: 1 for name in expected_branch_counts}):
            raise ValueError("Each scenario requires independent correction/deletion/expiry branches")
    for branch in branches:
        operations = branch["operations"]
        if sum(op["op"] == "restart" for op in operations) != 1:
            raise ValueError("Every branch requires exactly one scheduled process restart")
        if len({op["id"] for op in operations}) != len(operations):
            raise ValueError("Duplicate scheduled operation identity")
        if branch["branch"] == "expiry" and any(op["op"] in {"correct", "forget"} for op in operations):
            raise ValueError("Expiry branch cannot substitute correction/deletion")
        after_restart, asks = False, 0
        for op in operations:
            if op["op"] == "restart":
                after_restart = True
            elif op["op"] == "disclose":
                disclosures += 1
            elif op["op"] == "ask":
                asks += 1
                cid = op["checkpoint_id"]
                if cid in planned or cid not in expected:
                    raise ValueError("Duplicate or unledgered scheduled checkpoint")
                e = expected[cid]
                if any(e[k] != branch[k] for k in ("scenario_id", "branch", "category")):
                    raise ValueError("Ledger branch/scenario identity mismatch")
                if (e["question"] != op["question"] or e["logical_time"] != op["time"]
                        or e["history_mode"] != op["history"] or e["after_restart"] != after_restart):
                    raise ValueError("Ledger question/time/history/restart mismatch")
                if e["history_mode"] not in {"retained", "fresh"}:
                    raise ValueError("Unsupported history mode")
                prefix = branch["scenario_id"] + "_" + branch["branch"] + "_"
                if not cid.startswith(prefix):
                    raise ValueError("Checkpoint ID does not bind its scenario/branch")
                stage_counts[(branch["branch"], cid[len(prefix):])] += 1
                key = (e["scenario_id"], e["branch"], e["logical_time"], e["question"])
                pair = pairs.setdefault(key, set())
                if e["history_mode"] in pair:
                    raise ValueError("Duplicate checkpoint history within a question/time pair")
                pair.add(e["history_mode"])
                planned[cid] = op
        if asks != expected_branch_counts[branch["branch"]]:
            raise ValueError("Incomplete lifecycle branch checkpoint schedule")
    if set(planned) != set(expected):
        raise ValueError("Ledger contains unscheduled checkpoints")
    if len(stage_counts) != 24 or any(count != len(scenarios) for count in stage_counts.values()):
        raise ValueError("Every scenario must cover the same 24 lifecycle checkpoint stages")
    return {"planned_checkpoints": len(checkpoints), "scenario_ids": scenarios,
            "scenario_count": len(scenarios), "independent_databases": len(branches),
            "scheduled_restarts": len(branches), "scheduled_segments": 2 * len(branches),
            "disclosures": disclosures, "history_pairs": sum(v == {"retained", "fresh"} for v in pairs.values()),
            "stage_history_groups": len(stage_counts),
            "post_restart_checkpoints": sum(c["after_restart"] for c in checkpoints)}


def load_inputs(analysis, audit_path):
    verify_seal(analysis)
    provenance, metrics = read_json(analysis / "provenance.json"), read_json(analysis / "metrics.json")
    if provenance.get("script_sha256") != ANALYZER_V2_SHA256:
        raise ValueError("Expected the separately approved final analysis_v2 source")
    if provenance.get("partial") is not False or metrics.get("partial") is not False:
        raise ValueError("Final tables reject partial analysis snapshots")
    if provenance["input_provenance"].get("partial") is not False:
        raise ValueError("Final tables reject preparation from partial inputs")
    audit = read_json(audit_path)
    inputs = {str(Path(name).resolve()): value for name, value in provenance["input_provenance"]["input_sha256"].items()}
    for kind in ("freeze", "run"):
        name = str((Path(audit[kind + "_directory"]) / "seal.json").resolve())
        if inputs.get(name) != audit[kind + "_seal_sha256"]:
            raise ValueError("Collection audit does not bind the analysis freeze/run inputs")
    freeze = Path(audit["freeze_directory"])
    verify_seal(freeze)
    runtime, ledger = read_json(freeze / "runtime.json"), read_json(freeze / "expected_ledger.json")
    workload = workload_counts(runtime, ledger)
    expected = {e["checkpoint_id"]: e for e in ledger["checkpoints"]}
    required_counts = {k: workload[k] for k in ("planned_checkpoints", "scheduled_segments", "independent_databases")}
    required_counts["unique_observed_checkpoints"] = workload["planned_checkpoints"]
    if any(audit.get("counts", {}).get(k) != v for k, v in required_counts.items()):
        raise ValueError("Collection audit does not cover the final planned workload")
    if not isinstance(audit.get("integrity_pass"), bool) or not isinstance(audit.get("integrity_violations"), list):
        raise ValueError("Collection audit lacks an explicit integrity result")
    if audit["integrity_pass"] != (not audit["integrity_violations"]):
        raise ValueError("Collection audit integrity result contradicts its violations")
    rows = read_lines(analysis / "reviewed_answers.jsonl")
    if len(rows) != workload["planned_checkpoints"] or {r["checkpoint_id"] for r in rows} != set(expected):
        raise ValueError("Final tables require every unique authored checkpoint")
    if Counter(r["expected"]["scenario_id"] for r in rows) != Counter({s: 24 for s in workload["scenario_ids"]}):
        raise ValueError("Expected complete independent authored scenarios")
    for row in rows:
        e, j, d = row["expected"], row["judgment"], row["diagnostics"]
        if e != expected[row["checkpoint_id"]]:
            raise ValueError("Reviewed expected state/rubric differs from the frozen ledger")
        if e["checkpoint_id"] != row["checkpoint_id"] or not row["observed"] or not row["observed_record"]:
            raise ValueError("Missing or inconsistently bound final observation")
        if e["branch"] not in BRANCHES or e["history_mode"] not in {"retained", "fresh"} or type(e["after_restart"]) is not bool:
            raise ValueError("Invalid authored branch/history/restart dimension")
        if any(type(j[k]) is not bool for k in ("useful_correct", "forbidden_disclosure")):
            raise ValueError("Judgment flags must remain frozen booleans")
        disclosed = j["disclosed_forbidden_values"]
        if not isinstance(disclosed, list) or not set(disclosed) <= set(e["forbidden_values"]) or bool(disclosed) != j["forbidden_disclosure"]:
            raise ValueError("Judgment disclosures do not bind authored canonical forbidden values")
        if d["status"] not in {"delivered", "withheld", "interrupted"}:
            raise ValueError("Unknown final status")
        if (row["delivered_answer"] is not None) != (d["status"] == "delivered"):
            raise ValueError("Delivered-answer availability contradicts status")
        if d["status"] != "delivered" and (j["useful_correct"] or j["forbidden_disclosure"]):
            raise ValueError("An undelivered answer cannot acquire a successful/disclosure judgment")
    stages = grouped(rows, ("branch", "stage", "history_mode", "restart_phase", "expected_kind"))
    if len(stages) != workload["stage_history_groups"] or any(r["planned"] != workload["scenario_count"] for r in stages):
        raise ValueError("Expected all authored stage/history groups with every scenario")
    summary = basic(rows)
    metric_names = {"attempted": "attempted", "delivered": "delivered", "useful_correct": "useful_correct",
                    "forbidden_disclosure": "all_forbidden_disclosure", "missing": "missing", "planned": "planned"}
    if any(summary[k] != metrics["all"][v] for k, v in metric_names.items()):
        raise ValueError("Rendered counts would disagree with final analysis metrics")
    pairs = expected_pairs(rows)
    recorded = read_lines(analysis / "history_pairs.jsonl")
    normalize = lambda values: sorted(values, key=lambda p: p["retained_checkpoint"])
    if len(pairs) != workload["history_pairs"] or normalize(pairs) != normalize(recorded):
        raise ValueError("Final history-pair bindings or judgments disagree")
    return rows, pairs, provenance, audit


def build_tables(rows, pairs, audit):
    tables = {}
    add = lambda name, values, columns=None: tables.update({name: {"rows": values, "columns": columns or list(values[0])}})
    add("overall", [basic(rows)])
    add("stage_history", grouped(rows, ("branch", "stage", "history_mode", "restart_phase", "expected_kind")))
    add("restart_history", grouped(rows, ("restart_phase", "history_mode")))
    add("expected_kind_history", grouped(rows, ("expected_kind", "history_mode")))
    add("expected_kind_restart_history", grouped(rows, ("expected_kind", "restart_phase", "history_mode")))
    add("branch_restart_history", grouped(rows, ("branch", "restart_phase", "history_mode")))
    scenarios = grouped(rows, ("scenario_id", "category"))
    for item in scenarios:
        selected = [r for r in rows if r["expected"]["scenario_id"] == item["scenario_id"]]
        for branch in BRANCHES:
            item[branch + "_useful_correct"] = sum(r["judgment"]["useful_correct"] for r in selected if r["expected"]["branch"] == branch)
        for scope in DISCLOSURE_SCOPES[1:]:
            item[scope] = sum(disclosure_scope(r, scope)[1] for r in selected)
    add("scenarios", scenarios)
    add("disclosure_scopes", disclosure_tables(rows))
    aggregate, detailed = pair_tables(rows, pairs)
    add("history_pair_aggregates", aggregate)
    add("history_pair_details", detailed)
    selections, calls, routes, generation = selection_tables(rows)
    add("checkpoint_model_selections", selections)
    add("generation_call_details", calls, ["checkpoint_id", "generation_call_index", "branch", "history_mode", "restart_phase", "requested_model", "actual_model", "call_status"])
    add("requested_routes", routes)
    add("generation_call_aggregates", generation, ["branch", "requested_model", "actual_model", "call_status", "calls"])
    add("collection_audit", [{"integrity_pass": audit["integrity_pass"], "integrity_violations": len(audit["integrity_violations"]), **audit["counts"]}])
    exposure = [{"group": group, **counts} for group, counts in sorted(audit.get("history_exposure", {}).get("counts", {}).items())]
    exposure_columns = ["group", *sorted({k for row in exposure for k in row if k != "group"})]
    for row in exposure:
        for field in exposure_columns:
            row.setdefault(field, 0)
    add("history_exposure_audit", exposure, exposure_columns)
    return tables


def scalar(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")) if isinstance(value, (list, dict)) else "" if value is None else value


def render(args):
    analysis, audit_path, output = args.analysis.resolve(), args.audit.resolve(), args.output.resolve()
    if output.is_relative_to(analysis) or output == audit_path:
        raise ValueError("Table output must be outside sealed inputs")
    before = {str(analysis / "seal.json"): digest(analysis / "seal.json"), str(audit_path): digest(audit_path)}
    rows, pairs, analysis_provenance, audit = load_inputs(analysis, audit_path)
    tables = build_tables(rows, pairs, audit)
    if any(digest(Path(name)) != value for name, value in before.items()):
        raise ValueError("Inputs changed during table preparation")
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name, table in tables.items():
        with (output / (name + ".csv")).open("x", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=table["columns"])
            writer.writeheader()
            writer.writerows({k: scalar(v) for k, v in row.items()} for row in table["rows"])
        cells = lambda values: "| " + " | ".join(str(scalar(v)).replace("|", "\\|").replace("\n", "<br>") for v in values) + " |"
        lines = ["# " + name.replace("_", " "), "", cells(table["columns"]), cells(["---"] * len(table["columns"]))]
        lines.extend(cells(row.get(k) for k in table["columns"]) for row in table["rows"])
        with (output / (name + ".md")).open("x") as stream:
            stream.write("\n".join(lines) + "\n")
    notes = ["# Targeted changing-memory repair regression tables", "",
             "These tables aggregate existing frozen assistant judgments and trace metadata. No semantic scoring or inference occurs here. Human validation is pending.", "",
             "Planned denominators include withheld and interrupted attempts. Useful correct means the frozen full-rubric useful_correct judgment; it is not inferred from replacement-value overlap. Withholding is separate from useful recall and appropriate delivered uncertainty.", "",
             f"stage_history contains all authored branch/stage/history groups, each with {len({r['expected']['scenario_id'] for r in rows})} scenarios. Restart and expected-kind splits use the frozen ledger fields. Scenarios are the authored units; this is targeted matched regression selected from observed baseline failures, not held-out evaluation.", "",
             "forbidden_disclosure preserves the original reviewer flag. Subject-specific disclosure scopes use only canonical values already listed in disclosed_forbidden_values. Broad correction includes historical-control questions; current replacement restricts to expected_kind=replacement. Deleted/expired subject counts concern the old subject value. Any-expired-fact includes the old subject and expired historical control, excluding the never-stored replacement. Its unsupported disclosure is reported separately.", "",
             f"History pairs are the {len(pairs)} authored equal-question/equal-time retained/fresh matches, verified against the sealed analyzer pairing file. Success and disclosure each have both, retained-only, fresh-only and neither counts. Disclosure transitions describe paired history modes, not temporal or causal changes. Revoked-subject transitions use the original subject value in the existing forbidden-value judgments.", "",
             "Generation call tables count actual recorded generation calls, including failed calls and additional fallback calls. Empty actual_model means no returned model was recorded. Checkpoint selections preserve requested models, returned models, fallback and generation policy separately from nominal routes. The recorder's legacy policy label is preserved; frozen deployment uses the CLI-default LLM router. Setup disclosures and classifier calls are outside these generation tables.", "",
             "The collection audit is bound to the same frozen run/configuration seals as the analysis. Its integrity result and violations remain reportable; tables do not turn a failed audit into a pass. History-exposure counts are copied from that audit: literal matches are lower-bound exposure witnesses, not semantic absence or answer correctness.", "",
             "Results concern text, process restart with evaluation history rehydration, and controlled logical-time expiry. They do not establish power-loss recovery or spoken performance.", "",
             "| Table | Rows | CSV | Markdown |", "| --- | ---: | --- | --- |"]
    notes.extend(f"| {name} | {len(table['rows'])} | [{name}.csv]({name}.csv) | [{name}.md]({name}.md) |" for name, table in tables.items())
    with (output / "README.md").open("x") as stream:
        stream.write("\n".join(notes) + "\n")
    with (output / "renderer_source.py").open("xb") as stream:
        stream.write(Path(__file__).read_bytes())
    write_json(output / "provenance.json", {"created_at": datetime.now(timezone.utc).isoformat(),
               "command": [sys.executable, *sys.argv], "renderer_sha256": digest(__file__),
               "analysis_directory": str(analysis), "collection_audit": str(audit_path), "input_sha256": before,
               "analysis_source_sha256": analysis_provenance["script_sha256"],
               "auditor_source_sha256": audit.get("auditor_script_sha256"),
               "freeze_seal_sha256": audit["freeze_seal_sha256"], "run_seal_sha256": audit["run_seal_sha256"],
               "integrity_pass": audit["integrity_pass"], "integrity_violations": audit["integrity_violations"],
               "table_rows": {name: len(table["rows"]) for name, table in tables.items()},
               "semantic_scoring_performed": False, "inference_performed": False, "human_validation": "pending"})
    manifest = {p.name: digest(p) for p in sorted(output.iterdir())}
    write_json(output / "seal.json", {"created_at": datetime.now(timezone.utc).isoformat(), "sha256": manifest,
               "immutability": "exclusive creation, SHA256 manifest, read-only permissions; not privileged WORM"})
    for path in output.iterdir():
        path.chmod(0o400)
    output.chmod(0o500)
    print(json.dumps({"output": str(output), "tables": len(tables), "checkpoints": len(rows), "pairs": len(pairs)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True, help="Final sealed analysis_v2 directory")
    parser.add_argument("--audit", type=Path, required=True, help="Final collection audit JSON")
    parser.add_argument("--output", type=Path, required=True, help="New sealed output directory")
    render(parser.parse_args())


if __name__ == "__main__":
    main()
