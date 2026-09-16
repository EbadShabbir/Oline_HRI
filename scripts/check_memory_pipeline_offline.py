"""Replay intent/linking on historical development inputs, without inference.

Each implementation is imported in its own subprocess. Recorded retrieval
candidates stay fixed; no new retrieval, answer quality or latency is measured.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def file_hash(path):
    return sha256(path.read_bytes()).hexdigest()


def source_hashes(root):
    paths = sorted((root / "src/oline_hri").glob("*.py"))
    if not paths:
        raise ValueError("implementation source directory is empty")
    return {str(path.relative_to(root)): file_hash(path) for path in paths}


def executed_supplied_ids(record):
    """Recover the old supplied-ID set without reading/crediting answer text."""
    memory = record.get("memory") or {}
    if "supplied_ids" in memory:
        return sorted(set(memory["supplied_ids"])), "delivered_memory_diagnostics"
    identifiers, known = set(), False
    for call in record.get("calls", []):
        if call.get("purpose") != "generation":
            continue
        schema = (call.get("response_format") or {}).get("properties", {}).get("memory_used", {})
        values = schema.get("items", {}).get("enum")
        if isinstance(values, list):
            identifiers.update(values)
            known = True
        elif schema.get("maxItems") == 0:
            known = True
    return (sorted(identifiers), "generation_response_schema") if known else (None, "unknown")


def load_inputs(workload_path, diagnostics_path):
    workload = json.loads(workload_path.read_text())
    diagnostics = json.loads(diagnostics_path.read_text())
    if file_hash(workload_path) != diagnostics["workload_sha256"]:
        raise ValueError("historical workload hash differs from diagnostics")
    cases = workload["execution_cases"]
    by_id = {case["id"]: case for case in cases}
    if len(cases) != len(by_id) or set(by_id) != set(workload["rubrics"]):
        raise ValueError("workload case/rubric coverage differs")
    attempts, worker_candidates, seen = [], [], set()
    for source, expected in sorted(diagnostics["source_observations_sha256"].items()):
        path = Path(source)
        if file_hash(path) != expected:
            raise ValueError("historical observations no longer match recorded hash")
        for line in path.read_text().splitlines():
            row = json.loads(line)
            case = by_id[row["id"]]
            if any(row[key] != case[key] for key in ("id", "prompt", "stratum", "scenario_id")):
                raise ValueError("historical row differs from frozen execution case")
            key = f"{row['arm']}:r{row['repetition']}:{row['id']}"
            if key in seen:
                raise ValueError("duplicate historical attempt")
            seen.add(key)
            calls = row.get("retrieval_calls", [])
            if len(calls) > 1:
                raise ValueError("this bounded replay expects at most one recorded retrieval per attempt")
            candidates = calls[0].get("matches") if calls else None
            if candidates is not None and (not isinstance(candidates, list) or len(candidates) > 3):
                raise ValueError("candidate replay requires the original top-three-or-fewer list")
            supplied, supplied_source = executed_supplied_ids(row)
            rubric = workload["rubrics"][case["id"]]
            attempts.append({
                "key": key, "case_id": case["id"], "arm": row["arm"], "repetition": row["repetition"],
                "stratum": case["stratum"], "historical_status": row["status"],
                "historical_route_memory_required": (row.get("route") or {}).get("decision", {}).get("memory_required"),
                "required_ids": rubric["required_memory_ids"], "forbidden_ids": rubric["forbidden_memory_ids"],
                "candidate_replay_available": candidates is not None,
                "recorded_candidate_ids": [m["memory"]["id"] for m in candidates] if candidates is not None else None,
                "frozen_executed_supplied_ids": supplied, "frozen_supplied_source": supplied_source,
            })
            # No gold, stratum, historical route, or supplied-ID labels cross
            # the function boundary being replayed.
            worker_candidates.append({"key": key, "prompt": case["prompt"], "candidates": candidates})
    recorded_count = diagnostics.get("overall", {}).get("attempted")
    if recorded_count is not None and recorded_count != len(attempts):
        raise ValueError("historical observation count differs from diagnostics")
    payload = {"cases": [{"id": case["id"], "prompt": case["prompt"]} for case in cases],
               "candidate_sets": worker_candidates}
    return workload, diagnostics, attempts, payload


def worker(source_root, payload):
    source = (source_root / "src").resolve()
    sys.path.insert(0, str(source))
    from oline_hri.conversation import _required_memory_ids
    from oline_hri.routing import memory_intent_policy
    from oline_hri.memory import MemoryItem, MemoryStore
    from oline_hri.retrieval import HybridMatch
    from oline_hri.ollama import OllamaClient
    from oline_hri.embedding import BgeOnnxEmbedder
    from unittest.mock import patch

    def forbidden(*args, **kwargs):
        raise AssertionError("offline replay forbids models, embeddings, network and memory stores")

    policies, selections = [], []
    with patch.object(OllamaClient, "chat", forbidden), \
         patch.object(BgeOnnxEmbedder, "__init__", forbidden), \
         patch.object(MemoryStore, "__init__", forbidden), \
         patch("socket.socket.connect", forbidden), \
         patch("socket.create_connection", forbidden):
        for case in payload["cases"]:
            decision, reason = memory_intent_policy(case["prompt"], ())
            if decision is not None and type(decision) is not bool:
                raise ValueError("intent policy returned a nonboolean decision")
            policies.append({"case_id": case["id"], "memory_required": decision, "source": reason})
        for item in payload["candidate_sets"]:
            candidates = item["candidates"]
            if candidates is None:
                selections.append({"key": item["key"], "selected_ids": None,
                                   "status": "not_assessed_no_recorded_candidates"})
                continue
            matches = tuple(HybridMatch(memory=MemoryItem(**candidate["memory"]),
                                        fused_score=candidate["fused_score"], keyword_rank=None,
                                        keyword_position=None, semantic_score=None, semantic_position=None)
                            for candidate in candidates)
            selected = list(_required_memory_ids(matches, item["prompt"]))
            available = {candidate["memory"]["id"] for candidate in candidates}
            if len(selected) != len(set(selected)) or not set(selected) <= available:
                raise ValueError("selector returned duplicated or absent candidate IDs")
            selections.append({"key": item["key"], "selected_ids": selected, "status": "replayed"})
    imported = {}
    for name, module in sorted(sys.modules.items()):
        if name == "oline_hri" or name.startswith("oline_hri."):
            path = getattr(module, "__file__", None)
            if path is not None:
                resolved = Path(path).resolve()
                if not resolved.is_relative_to(source):
                    raise ValueError("implementation module imported from a different source tree")
                imported[name] = {"path": str(resolved), "sha256": file_hash(resolved)}
    return {"pid": os.getpid(), "source_root": str(source_root.resolve()),
            "imported_modules": imported, "policies": policies, "selections": selections}


def run_worker(source_root, payload):
    env = dict(os.environ)
    env["PYTHONPATH"] = str((source_root / "src").resolve())
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker",
                             "--source-root", str(source_root.resolve())],
                            input=json.dumps(payload), text=True, capture_output=True,
                            check=True, timeout=60, cwd=source_root, env=env)
    value = json.loads(result.stdout)
    if value["pid"] == os.getpid():
        raise ValueError("implementation was not run in a separate process")
    return value


def evaluate(workload, attempts, versions):
    expected = {case["id"]: case["stratum"].startswith("personal_")
                for case in workload["execution_cases"]}
    summary, policy_comparison, attempt_comparison = {}, {}, []
    for label, version in versions.items():
        by_case = {row["case_id"]: row for row in version["policies"]}
        if len(by_case) != len(version["policies"]) or set(by_case) != set(expected):
            raise ValueError("policy replay case coverage differs")
        counts = Counter()
        for case_id, need in expected.items():
            result = by_case[case_id]
            predicted = result["memory_required"]
            counts["authored_personal" if need else "authored_general"] += 1
            counts["unresolved" if predicted is None else "correct_explicit" if predicted == need else "wrong_explicit"] += 1
            policy_comparison.setdefault(case_id, {"authored_memory_intent": need})[label] = result
        counts["distinct_cases"] = len(expected)
        summary[label] = {"intent_distinct_cases": dict(counts), "selection": Counter()}
    indexed = {label: {row["key"]: row for row in version["selections"]} for label, version in versions.items()}
    keys = {row["key"] for row in attempts}
    if any(set(values) != keys or len(values) != len(versions[label]["selections"]) for label, values in indexed.items()):
        raise ValueError("selection replay attempt coverage differs")
    frozen_counts = Counter()
    for attempt in attempts:
        record = dict(attempt)
        required, forbidden_ids = set(attempt["required_ids"]), set(attempt["forbidden_ids"])
        candidates = set(attempt["recorded_candidate_ids"] or [])
        record["required_ids_absent_from_recorded_candidates"] = sorted(required - candidates)
        for label in versions:
            selection = indexed[label][attempt["key"]]
            record[label] = dict(selection)
            counts = summary[label]["selection"]
            if selection["selected_ids"] is None:
                counts["not_assessed_no_candidates"] += 1
                if policy_comparison[attempt["case_id"]][label]["memory_required"] is True:
                    counts["new_policy_needs_memory_but_candidates_unavailable"] += 1
                continue
            selected = set(selection["selected_ids"])
            counts["candidate_attempts_replayed"] += 1
            counts["selected_forbidden_id_attempts"] += bool(selected & forbidden_ids)
            record[label]["required_ids_missing_from_selection"] = sorted(required - selected)
            record[label]["selected_ids_outside_minimum_gold"] = sorted(selected - required)
            if required:
                counts["required_fact_attempts_with_candidates"] += 1
                counts["all_required_selected"] += required <= selected
                counts["required_id_occurrences"] += len(required)
                counts["required_id_occurrences_selected"] += len(required & selected)
                counts["retrievable_required_id_occurrences"] += len(required & candidates)
                counts["retrievable_required_id_occurrences_selected"] += len(required & candidates & selected)
        supplied = attempt["frozen_executed_supplied_ids"]
        if supplied is None:
            frozen_counts["unknown_supplied_evidence"] += 1
        elif required:
            frozen_counts["required_fact_attempts"] += 1
            frozen_counts["all_required_supplied"] += required <= set(supplied)
        attempt_comparison.append(record)
    return {"by_implementation": summary, "frozen_executed_evidence": frozen_counts,
            "policy_cases": policy_comparison, "attempts": attempt_comparison}


def render_report(result):
    lines = ["# Offline memory pipeline development replay", "",
             "Historical authored development data; no new model calls, embeddings, retrieval, answer accuracy or latency measurement.", "",
             "| Implementation | Distinct prompts | Explicit correct intent | Explicit wrong intent | Unresolved intent |",
             "| --- | ---: | ---: | ---: | ---: |"]
    for label, item in result["comparison"]["by_implementation"].items():
        counts = item["intent_distinct_cases"]
        lines.append(f"| {label} | {counts['distinct_cases']} | {counts.get('correct_explicit',0)} | {counts.get('wrong_explicit',0)} | {counts.get('unresolved',0)} |")
    lines += ["", "None means the deterministic policy defers; it does not establish the later classifier's result.", "",
              "| Implementation | Recorded candidate attempts | Required-fact attempts with candidates | All required selected | No candidate replay available |",
              "| --- | ---: | ---: | ---: | ---: |"]
    for label, item in result["comparison"]["by_implementation"].items():
        counts = item["selection"]
        lines.append(f"| {label} | {counts.get('candidate_attempts_replayed',0)} | {counts.get('required_fact_attempts_with_candidates',0)} | {counts.get('all_required_selected',0)} | {counts.get('not_assessed_no_candidates',0)} |")
    old = result["comparison"]["frozen_executed_evidence"]
    lines += ["", f"Historically, all required facts were supplied in {old.get('all_required_supplied',0)}/{old.get('required_fact_attempts',0)} required-fact attempts. This is the executed Conversation evidence set, including its packing/schema path, and is not identical to the private linking helper's output.", "",
              "Selection is replayed independently of each policy's decision on exactly the old ordered candidates. No recorded candidates means unassessed, even when the new policy would retrieve. Missing candidates cannot establish new retrieval recall. IDs outside minimum gold are diagnostic extras, not automatically incorrect evidence. Repeated candidate sets/attempts are dependent development examples.", "",
              "The pre-step baseline archive is distinct from the original Stage 2 execution freeze. The JSON preserves both source identities and the executed supplied IDs. No historical answer score or artifact was changed.", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--source-root", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--baseline-source", type=Path)
    parser.add_argument("--current-source", type=Path, default=ROOT)
    parser.add_argument("--workload", type=Path, default=ROOT / "evaluation/complete_system_20260911/workload.json")
    parser.add_argument("--diagnostics", type=Path, default=ROOT / "evaluation/complete_system_20260911/results_reviewed/pipeline_diagnostics.json")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if args.worker:
        print(json.dumps(worker(args.source_root, json.loads(sys.stdin.read()))))
        return 0
    if args.baseline_source is None or args.output_dir is None:
        parser.error("--baseline-source and --output-dir are required")
    if args.output_dir.exists():
        raise ValueError("refusing to replace an existing replay output directory")
    workload, diagnostics, attempts, payload = load_inputs(args.workload, args.diagnostics)
    roots = {"baseline": args.baseline_source.resolve(), "current": args.current_source.resolve()}
    before = {label: source_hashes(root) for label, root in roots.items()}
    versions = {label: run_worker(root, payload) for label, root in roots.items()}
    if len({value["pid"] for value in versions.values()}) != len(versions):
        raise ValueError("implementation subprocess identity was reused")
    after = {label: source_hashes(root) for label, root in roots.items()}
    if before != after:
        raise ValueError("implementation sources changed during replay; no result published")
    result = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
              "scope": "historical authored DEVELOPMENT inputs; deterministic function replay only",
              "new_model_calls": 0, "new_embedding_calls": 0, "new_retrieval_calls": 0,
              "new_answer_accuracy": None, "new_latency_measurement": None,
              "script_sha256": file_hash(Path(__file__)), "workload_sha256": file_hash(args.workload),
              "diagnostics_sha256": file_hash(args.diagnostics),
              "source_observations_sha256": diagnostics["source_observations_sha256"],
              "historical_execution_source_sha256": diagnostics.get("frozen_execution_source_sha256", {}),
              "implementation_source_sha256": before,
              "implementations": versions, "comparison": evaluate(workload, attempts, versions)}
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "replay.json").write_text(json.dumps(result, indent=2) + "\n")
    (args.output_dir / "report.md").write_text(render_report(result))
    print(json.dumps({"output": str(args.output_dir), "observed_attempts": len(attempts),
                      "distinct_cases": len(workload["execution_cases"]), "new_model_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
