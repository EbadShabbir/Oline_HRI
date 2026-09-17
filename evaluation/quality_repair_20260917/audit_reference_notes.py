"""Verify static public-reference provenance separately from personal memory.

This supplementary audit preserves earlier sealed auditors/results. It parses
only literal ReferenceNote constructors from hash-bound archived source, without
importing or executing production or analysis code and without network access.
"""
import argparse
import ast
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def literal_reference_notes(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "REFERENCE_NOTES" for target in node.targets)]
    if len(assignments) != 1 or not isinstance(assignments[0].value, (ast.Tuple, ast.List)):
        raise ValueError("one literal REFERENCE_NOTES assignment required")
    notes = {}
    for constructor in assignments[0].value.elts:
        if (not isinstance(constructor, ast.Call) or not isinstance(constructor.func, ast.Name)
                or constructor.func.id != "ReferenceNote" or len(constructor.args) != 4):
            raise ValueError("static ReferenceNote constructor required")
        identifier, pattern, text, sources = [ast.literal_eval(arg) for arg in constructor.args]
        if (not all(isinstance(value, str) and value for value in (identifier, pattern, text))
                or not isinstance(sources, tuple) or not sources
                or not all(isinstance(source, str) and source.startswith("https://") for source in sources)):
            raise ValueError("literal reference must contain ID, topic pattern, text and public HTTPS sources")
        if identifier in notes:
            raise ValueError("duplicate static reference ID")
        reviewed = next((ast.literal_eval(keyword.value) for keyword in constructor.keywords
                         if keyword.arg == "reviewed"), None)
        notes[identifier] = {"pattern": pattern, "text": text, "sources": list(sources),
                             "reviewed_explicit": reviewed}
    return notes


def verify(cohort, source_root):
    checks = []
    def check(condition, name, detail=None):
        checks.append({"check": name, "passed": bool(condition), "detail": detail})
    candidate = read(cohort / "candidate_freeze.json")
    source_name = "src/oline_hri/answer_guidance.py"
    source = source_root / source_name
    expected = candidate["source_sha256"][source_name]
    before = read(cohort / "collection/integrity_before.json")
    after = read(cohort / "collection/integrity_after.json")
    check(digest(source) == expected == before["source_sha256"][source_name]
          == after["source_sha256"][source_name], "reference archive matches frozen and collected source")
    notes = literal_reference_notes(source)
    check(bool(notes), "public notes are literal archived constructors, parsed without execution")
    rows = [json.loads(line) for line in (cohort / "collection/run/observations.jsonl").read_text().splitlines() if line.strip()]
    references, personal_evidence, findings = [], [], []
    for row in rows:
        reply = row.get("reply") or {}
        diagnostics = reply.get("memory_diagnostics") or {}
        for field in ("retrieved_ids", "supplied_ids", "model_used_ids"):
            if diagnostics.get(field):
                personal_evidence.append({"id": row["id"], "field": field})
        for field in ("application_memory_ids", "retrieval"):
            if reply.get(field):
                personal_evidence.append({"id": row["id"], "field": field})
        if (reply.get("response") or {}).get("memory_used"):
            personal_evidence.append({"id": row["id"], "field": "response.memory_used"})
        ids = reply.get("reference_ids") or []
        if not ids:
            continue
        if not isinstance(ids, list) or len(ids) > 2 or len(set(ids)) != len(ids):
            findings.append({"id": row["id"], "issue": "invalid public reference ID list"})
            continue
        generation = reply.get("generation")
        calls = [call for call in row.get("calls", []) if generation and call.get("result") == generation]
        if not calls:
            findings.append({"id": row["id"], "issue": "public references have no selected actual model call"})
            continue
        users = [message["content"] for message in calls[-1]["messages"] if message.get("role") == "user"]
        request = users[-1] if users else ""
        fragment = ((row.get("route") or {}).get("dependency") or {}).get("general_request") or ""
        case_text = row["case"]["text"]
        if request != case_text and not (request == fragment and fragment in case_text):
            findings.append({"id": row["id"], "issue": "reference topic selected from nonliteral request"})
        systems = [message["content"] for message in calls[-1]["messages"] if message.get("role") == "system"]
        for identifier in ids:
            note = notes.get(identifier)
            if note is None:
                findings.append({"id": row["id"], "issue": "ID absent from frozen public reference table", "reference_id": identifier})
                continue
            if not re.search(note["pattern"], request, re.I):
                findings.append({"id": row["id"], "issue": "public reference topic does not match actual request", "reference_id": identifier})
            if not any(note["text"] in system for system in systems):
                findings.append({"id": row["id"], "issue": "literal public note absent from selected generation prompt", "reference_id": identifier})
            references.append({"id": row["id"], "reference_id": identifier,
                               "sources": note["sources"], "reviewed_explicit": note["reviewed_explicit"],
                               "static_text_sha256": sha256(note["text"].encode()).hexdigest()})
    check(not personal_evidence, "all actual personal-memory evidence fields remain empty", personal_evidence)
    check(not findings, "reference IDs name topic-matched static public notes actually provided to the generator", findings)
    initial_audit_path = cohort / "independent_audit.json"
    if initial_audit_path.exists():
        initial = read(initial_audit_path)
        failures = [item for item in initial["checks"] if not item["passed"]]
        expected_findings = [{"id": row["id"], "field": "reference_ids"} for row in rows
                             if (row.get("reply") or {}).get("reference_ids")]
        check(len(failures) == 1 and failures[0]["check"] == "cohort: no fabricated memory evidence IDs"
              and failures[0]["detail"] == expected_findings,
              "only sealed-auditor failure is its conflation of static references with personal-memory evidence", failures)
    return {"checks": checks, "public_reference_uses": references,
            "checks_passed": sum(item["passed"] for item in checks),
            "checks_failed": sum(not item["passed"] for item in checks),
            "passed": all(item["passed"] for item in checks),
            "source_sha256": {str(source): digest(source)},
            "input_sha256": {str(path): digest(path) for path in (
                cohort / "candidate_freeze.json", cohort / "collection/run/observations.jsonl",
                cohort / "collection/integrity_before.json", cohort / "collection/integrity_after.json")},
            "interpretation": "Static public reference IDs are separate from personal-memory evidence. Original audit output is preserved; this supplement corrects that distinction only. It does not validate the reference website, model answer correctness or strict quality, and does not change judgments."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-dir", required=True, type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    source_root = args.source_root or args.cohort_dir / "candidate_source"
    output = args.output or args.cohort_dir / "independent_reference_audit.json"
    if output.exists():
        parser.error("supplement output already exists")
    result = {"created_at": datetime.now(timezone.utc).isoformat(),
              "method": "Standard-library literal AST, hash and raw prompt/evidence verification; no production execution, analysis imports or network access.",
              "auditor_sha256": digest(Path(__file__))}
    result.update(verify(args.cohort_dir, source_root))
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps({key: result[key] for key in ("passed", "checks_passed", "checks_failed")}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
