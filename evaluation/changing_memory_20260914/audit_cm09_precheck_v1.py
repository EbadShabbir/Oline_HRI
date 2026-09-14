#!/usr/bin/env python3
"""Partial cm09 schema/HTTP audit only; no semantic scoring or inference."""

from collections import Counter
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import traceback


BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("changing_memory_collection_audit", BASE / "audit_collection.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def main():
    output = BASE / "audit_cm09_precheck_v1.json"
    if output.exists():
        raise FileExistsError(output)
    freeze, run = BASE / "frozen_v1", BASE / "run_v2"
    audit = module.Audit()
    frozen = module.read_json(freeze / "freeze.json")
    expected = {e["checkpoint_id"]: e for e in module.read_json(freeze / "expected_ledger.json")["checkpoints"]
                if e["scenario_id"] == "cm09"}
    source_hash = module.digest(BASE / "audit_collection.py")
    input_hashes = {str(freeze / "seal.json"): module.digest(freeze / "seal.json")}
    fragments, found, large_requests = [], [], []
    failure = None
    try:
        audit.seal(freeze)
        for branch in ("correction", "deletion", "expiry"):
            branch_dir = run / ("cm09_" + branch)
            audit.seal(branch_dir)
            input_hashes[str(branch_dir / "seal.json")] = module.digest(branch_dir / "seal.json")
            for launch_path in sorted(branch_dir.glob("*_launch.json")):
                fragment = branch_dir / launch_path.name.removesuffix("_launch.json")
                audit.seal(fragment)
                finish = module.read_json(fragment / "finish.json")
                admission_only = not (fragment / "process.json").exists()
                audit.resource(fragment, frozen, admission_only=admission_only)
                fragments.append({"path": str(fragment), "admission_only": admission_only, "status": finish.get("status")})
                if admission_only:
                    audit.check(not any((fragment / name).exists() for name in ("http.jsonl", "answers.jsonl", "events.jsonl")),
                                "precheck_zero_inference_admission", fragment)
                    continue
                requests = audit.http(fragment / "http.jsonl", set(frozen["models"]), frozen["config"]["generation"])
                consumed = set()
                for row in audit.jsonl(fragment / "answers.jsonl"):
                    checkpoint = row.get("checkpoint_id")
                    if checkpoint is not None:
                        found.append(checkpoint)
                        audit.check(checkpoint in expected, "precheck_cm09_checkpoint_only", fragment, observed=checkpoint)
                    audit.answer(row, expected.get(checkpoint), requests, consumed, fragment)
                for index, request in enumerate(requests):
                    if request["endpoint"] != "/api/chat":
                        continue
                    audit.check(index in consumed, "precheck_every_chat_links_to_call", request["where"])
                    if request["body"].get("model") == "qwen3:1.7b":
                        large_requests.append({"request": request["where"], "purpose": request["purpose"],
                                               "linked_to_recorded_call": index in consumed,
                                               "bytes_sha256": request["bytes_sha256"],
                                               "received_bytes": request["received_bytes"], "status": request["status"]})
        audit.check(Counter(found) == Counter(expected), "precheck_all_24_unique_cm09_checkpoints", run / "cm09_subset",
                    expected=sorted(expected), observed=sorted(found))
        audit.check(bool(large_requests), "precheck_actual_large_model_http_exercised", run / "cm09_subset")
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
    result = {"created_at": datetime.now(timezone.utc).isoformat(), "partial": True,
              "scope": "Subset precheck of sealed cm09 correction/deletion/expiry only; final all-288 collection audit remains required.",
              "semantic_scoring_performed": False, "inference_performed": False,
              "blinded_review_status": "Original cm09 blinded review pending; no diagnostic information sent to reviewers.",
              "human_validation": "pending", "command": [sys.executable, str(Path(__file__).resolve())],
              "precheck_source_sha256": module.digest(__file__), "auditor_source_sha256": source_hash,
              "input_sha256": input_hashes, "subset_integrity_pass": failure is None and not audit.violations,
              "exception": failure, "integrity_checks": dict(audit.checks), "integrity_violations": audit.violations,
              "counts": {**dict(audit.counts), "subset_planned_checkpoints": len(expected),
                         "subset_unique_observed_checkpoints": len(set(found)), "subset_fragments": len(fragments)},
              "observed_system_events": audit.observations, "fragments": fragments,
              "actual_model_requests": [{"purpose": key[0], "model": key[1], "count": count}
                                        for key, count in sorted(audit.models.items())],
              "large_model_http_links": large_requests, "received_bytes_call_links": audit.http_links}
    with output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    output.chmod(0o400)
    print(json.dumps({"output": str(output), "partial": True, "subset_integrity_pass": result["subset_integrity_pass"],
                      "integrity_violations": len(audit.violations), "exception_type": failure["type"] if failure else None,
                      "subset_checkpoints": len(set(found)), "large_model_http_requests": len(large_requests),
                      "actual_model_requests": result["actual_model_requests"]}))
    return 0 if result["subset_integrity_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
