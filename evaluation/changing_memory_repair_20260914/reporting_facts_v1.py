"""Independent report factcheck from sealed first-repair artifacts; no inference."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import csv
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "changing_memory_20260914"


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


checks = []


def check(condition, name):
    if not condition:
        raise ValueError(name)
    checks.append(name)


def verify(directory):
    manifest = read(directory / "seal.json")["sha256"]
    actual = {str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file() and p != directory / "seal.json"}
    check(actual == set(manifest), "Sealed file inventory: " + str(directory))
    check(all(digest(directory / name) == h for name, h in manifest.items()), "Sealed content hashes: " + str(directory))


def summary(selected):
    return {"planned": len(selected), "delivered": sum(r["diagnostics"]["status"] == "delivered" for r in selected),
            "useful_correct": sum(r["judgment"]["useful_correct"] for r in selected),
            "forbidden_disclosure": sum(r["judgment"]["forbidden_disclosure"] for r in selected),
            "withheld": sum(r["diagnostics"]["status"] == "withheld" for r in selected),
            "interrupted": sum(r["diagnostics"]["status"] == "interrupted" for r in selected),
            "missing": sum(not r["observed"] for r in selected),
            "classification": dict(Counter(r["judgment"]["classification"] for r in selected))}


for path in (ROOT / "analysis_v1", ROOT / "tables_v1", ROOT / "matched_comparison_v1", BASE / "analysis_v2"):
    verify(path)
bundle = read(ROOT / "collection_audit_bundle_v1_seal.json")
check(all(digest(ROOT / name) == h for name, h in bundle["sha256"].items()), "Independent collection audit bundle hashes")
new = rows(ROOT / "analysis_v1/reviewed_answers.jsonl")
metrics = read(ROOT / "analysis_v1/metrics.json")
agreement = read(ROOT / "analysis_v1/review_agreement.json")
frozen_votes = read(ROOT / "analysis_v1/frozen_votes/resolved.json")
check(all(frozen_votes[r["blind_id"]] == r["judgment"] for r in new), "All first-repair rows bind original frozen judgments")
check(len(new) == len({r["checkpoint_id"] for r in new}) == 96, "All 96 unique first-repair checkpoints present")
check(agreement["agreements"] == agreement["groups"] == 47 and not agreement["disagreements"], "Both assistant reviewers agree on all 47 groups")
check(agreement["resolved_before_diagnostics"] is True, "Judgments resolved before diagnostic unblinding")
comparison = read(ROOT / "matched_comparison_v1/comparison.json")
audit = read(ROOT / "collection_audit_v1.json")
findings = read(ROOT / "collection_audit_findings_v1.json")
old_index = {r["checkpoint_id"]: r for r in rows(BASE / "analysis_v2/reviewed_answers.jsonl")}
old = [old_index[r["checkpoint_id"]] for r in new]
check(all(a["expected"] == b["expected"] for a, b in zip(old, new)), "All matched expected-state/rubric objects identical")
for label, selected in (("baseline", old), ("repair", new)):
    computed = summary(selected)
    reference = comparison[label + "_matched"]
    check(all(reference[k] == computed[k] for k in reference if k in computed), "Matched comparison aggregates recomputed: " + label)
for key, other in (("planned", "planned"), ("delivered", "delivered"), ("useful_correct", "useful_correct"),
                   ("forbidden_disclosure", "all_forbidden_disclosure"), ("missing", "missing")):
    check(summary(new)[key] == metrics["all"][other], "Analysis total recomputed: " + key)

stage_groups = defaultdict(list)
for row in new:
    e = row["expected"]
    label = row["checkpoint_id"].removeprefix(e["scenario_id"] + "_" + e["branch"] + "_")
    label = label.removesuffix("_" + e["history_mode"])
    stage_groups[(e["branch"], label, e["history_mode"], "after" if e["after_restart"] else "before", e["expected_kind"])].append(row)
with (ROOT / "tables_v1/stage_history.csv").open() as stream:
    stage_table = list(csv.DictReader(stream))
check(len(stage_groups) == len(stage_table) == 24, "All 24 stage/history groups present")
for row in stage_table:
    key = tuple(row[k] for k in ("branch", "stage", "history_mode", "restart_phase", "expected_kind"))
    computed = summary(stage_groups[key])
    check(all(int(row[k]) == computed[k] for k in computed if k != "classification"), "Stage table recomputed: " + repr(key))

dimensions = {}
for field in ("branch", "scenario_id", "expected_kind", "history_mode", "after_restart"):
    dimensions[field] = {str(value): summary([r for r in new if r["expected"][field] == value])
                         for value in sorted({r["expected"][field] for r in new}, key=str)}
specific = {
    "prestore_uncertainty": [r for r in new if r["checkpoint_id"].endswith("_prestore")],
    "deleted_current_value": [r for r in new if r["expected"]["mutation_state"] == "deletion" and r["expected"]["historical_scope"] == "current_record"],
    "deleted_former_statement": [r for r in new if r["expected"]["historical_scope"] == "forgotten_prior_statement"],
    "at_expiry": [r for r in new if "_expiry_at_" in r["checkpoint_id"]],
    "after_expiry": [r for r in new if "_expiry_after_" in r["checkpoint_id"]],
    "before_expiry": [r for r in new if "_expiry_before_" in r["checkpoint_id"]],
    "post_restart_replacement": [r for r in new if r["expected"]["after_restart"] and r["expected"]["expected_kind"] == "replacement"],
    "post_restart_unavailable": [r for r in new if r["expected"]["after_restart"] and r["expected"]["expected_kind"] == "uncertainty"],
}
pairs = defaultdict(dict)
for row in new:
    e = row["expected"]
    pairs[(e["scenario_id"], e["branch"], e["logical_time"], e["question"])][e["history_mode"]] = row
paired = [p for p in pairs.values() if set(p) == {"retained", "fresh"}]
history_counts = Counter((p["retained"]["judgment"]["useful_correct"], p["fresh"]["judgment"]["useful_correct"]) for p in paired)
check(len(paired) == 36 and history_counts[(True, True)] == 34 and history_counts[(False, False)] == 2,
      "Retained/fresh paired usefulness recomputed")

latency = []
for scope in ("all_attempts", "delivered_only"):
    fact = {"scope": scope}
    for label, selected in (("baseline", old), ("repair", new)):
        eligible = [r for r in selected if scope == "all_attempts" or r["diagnostics"]["status"] == "delivered"]
        samples = []
        for r in eligible:
            ns = r["observed_record"].get("wall_ns")
            if ns is not None:
                check(r["diagnostics"]["wall_seconds"] == ns / 1e9, "Measured wall clock matches trace: " + label + "/" + r["checkpoint_id"])
                samples.append(ns / 1e9)
        samples.sort()
        fact[label] = {"eligible_attempts": len(eligible), "timed_attempts": len(samples),
                       "missing_timing": len(eligible) - len(samples), "median_seconds": statistics.median(samples),
                       "p95_seconds": samples[(95 * len(samples) + 99) // 100 - 1]}
    reference = next(r for r in comparison["wall_latency"] if r["dimensions"] == "all" and r["scope"] == scope)
    check(all(reference[label + "_" + k] == value for label in ("baseline", "repair") for k, value in fact[label].items()),
          "Measured latency quantiles recomputed: " + scope)
    latency.append(fact)

actual_generators = {label: dict(Counter(model for r in selected for model in r["diagnostics"]["actual_generator_models"]))
                     for label, selected in (("baseline_matched", old), ("repair_matched", new))}
check(actual_generators["repair_matched"] == metrics["all"]["actual_generator_models"], "Actual generator counts recomputed")
constraints = dict(Counter(str(r["observed_record"].get("answer_constraint")) for r in new))
check(constraints == findings["recorded_answer_constraint_counts"], "Recorded answer constraint counts recomputed")
check(audit["integrity_pass"] and not audit["integrity_violations"] and sum(audit["integrity_checks"].values()) == 10541,
      "Full collection audit passed 10,541 checks")
check(audit["counts"] == findings["counts"], "Collection findings preserve audit counts")
known = [r for r in new if r["expected"]["required_record_keys"]]
evidence = {key: sum(r["diagnostics"][key] for r in known) for key in
            ("required_evidence_in_store", "required_evidence_retrieved", "required_evidence_supplied")}
check(len(known) == 48 and all(value == 48 for value in evidence.values()), "All 48 known-fact checkpoints had stored, retrieved and supplied evidence")
failures = []
for row in new:
    if row["judgment"]["useful_correct"]:
        continue
    d = row["diagnostics"]
    failures.append({"checkpoint_id": row["checkpoint_id"], "expected_value": row["expected"]["expected_value"],
        "frozen_judgment": row["judgment"], "delivered_answer": row["delivered_answer"],
        "status": d["status"], "raw_model_answers": d["raw_model_answers"],
        "validation_decision": d["validation_decision"], "recorded_error": d["error_message"],
        "findings": d["failure_findings"], "required_evidence_supplied": d["required_evidence_supplied"]})
input_paths = [ROOT / "analysis_v1/seal.json", ROOT / "tables_v1/seal.json", ROOT / "matched_comparison_v1/seal.json",
               BASE / "analysis_v2/seal.json", ROOT / "collection_audit_bundle_v1_seal.json",
               ROOT / "collection_audit_v1.json", ROOT / "collection_audit_findings_v1.json"]
result = {"created_at": datetime.now(timezone.utc).isoformat(), "reviewer": "assistant /root/lifecycle_fix_validation_plan",
    "review_kind": "Independent first-repair report factcheck; no new semantic scoring or inference",
    "scope": "Only the sealed first 96-checkpoint repair; followup_v2 is separate and not pooled.",
    "study_limitation": "Targeted matched development scenarios selected after baseline failures; not held-out.",
    "source_sha256": digest(Path(__file__)), "input_sha256": {str(p): digest(p) for p in input_paths},
    "checks_passed": len(checks), "checks": checks, "overall": summary(new), "matched_baseline": summary(old),
    "improvement": {"additional_useful": summary(new)["useful_correct"] - summary(old)["useful_correct"],
        "useful_percentage_baseline": 100 * summary(old)["useful_correct"] / 96,
        "useful_percentage_repair": 100 * summary(new)["useful_correct"] / 96,
        "frozen_comparison_usefulness_transitions": comparison["usefulness_transitions"],
        "frozen_comparison_disclosure_transitions": comparison["disclosure_transitions"]},
    "by_dimension": dimensions, "specific_scopes": {name: summary(selected) for name, selected in specific.items()},
    "stage_history": [{"branch": key[0], "stage": key[1], "history": key[2], "restart_phase": key[3], "expected_kind": key[4],
                       **summary(selected)} for key, selected in sorted(stage_groups.items())],
    "history_pairs": {"planned": len(paired), "both_useful": history_counts[(True, True)],
        "retained_only_useful": history_counts[(True, False)], "fresh_only_useful": history_counts[(False, True)],
        "neither_useful": history_counts[(False, False)], "both_modes_success_denominator": 36},
    "blinded_review": {"groups": agreement["groups"], "agreements": agreement["agreements"],
        "disagreements": len(agreement["disagreements"]), "adjudication_required": False,
        "votes_frozen_before_diagnostics": agreement["resolved_before_diagnostics"], "human_validation": "pending"},
    "wall_latency": latency, "wall_latency_semantics": "Seconds per complete conversation checkpoint. Median and nearest-rank p95. All-attempt includes withholding; delivered-only membership differs between systems. Admission/cooling/setup excluded; descriptive, not causal or spoken latency.",
    "actual_generators": actual_generators, "all_scored_model_requests": metrics["all"]["actual_models"],
    "all_scored_and_setup_model_requests_by_purpose": audit["actual_model_requests"],
    "nominal_routes": findings["scored_route_counts"], "recorded_constraints": constraints,
    "generation_policy": dict(Counter(str(r["diagnostics"].get("generation_policy")) for r in new)),
    "constraint_limit": "24 verified_location and 6 verified_user_relationship answers are application-constrained generation, not unconstrained model reasoning. Null policy is recorded, not inferred.",
    "known_fact_evidence": {"planned_known_fact_checkpoints": len(known), **evidence},
    "failures": failures,
    "failure_interpretation": "Two cm01 immediate-correction answers contain jasmine plus contradictory ignorance; frozen reviewers mark partial. Two cm04 restart answers are withheld after the collaborator-evidence validator despite supported raw partner content; raw assessment is unblinded diagnosis, not changed no-answer votes. These four first-run failures remain unchanged.",
    "collection": {"integrity_checks": 10541, "integrity_kinds": len(audit["integrity_checks"]), "violations": 0,
        "counts": findings["counts"], "workload": findings["workload"], "authored_probes": findings["authored_probe_results"],
        "answer_snapshot_checks": findings["answer_snapshot_checks"], "history_exposure": findings["history_exposure_counts"],
        "history_exposure_limit": findings["history_exposure_interpretation"], "resources": findings["resources"],
        "system_observations": findings["system_observations"]},
    "claims_not_supported": ["Universal lifecycle reliability", "Held-out generalization", "Power-loss recovery",
                             "OS/Ollama restart recovery", "Spoken performance", "Absence of all semantic stale-state channels"],
    "human_validation": "pending"}
target = ROOT / "reporting_facts_v1.json"
with target.open("x") as stream:
    json.dump(result, stream, indent=2, ensure_ascii=False)
    stream.write("\n")
target.chmod(0o400)
print(json.dumps({"status": "passed", "checks": len(checks), "output": str(target), "sha256": digest(target),
                  "useful": result["overall"]["useful_correct"], "planned": 96, "failures": len(failures)}))
