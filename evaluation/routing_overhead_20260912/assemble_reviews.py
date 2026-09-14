"""Audit immutable blinded cohorts and assemble final coverage without regrading."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from prepare_review_cohort import build, canonical

FIELDS = ("label", "unsupported_claim", "unsupported_personal_claim")
LABELS = {"complete", "appropriate_abstention", "appropriate_uncertainty", "partial",
          "incorrect", "inappropriate_abstention", "technical_failure"}


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def indexed(path):
    items = rows(path)
    result = {r["answer_id"]: r for r in items}
    if len(result) != len(items):
        raise ValueError(f"duplicate IDs: {path}")
    return result


def validate(review, group):
    if review.get("label") not in LABELS or not review.get("rationale"):
        raise ValueError("invalid review label/rationale")
    if any(type(review.get(key)) is not bool for key in FIELDS[1:]):
        raise ValueError("review flags must be explicit booleans")
    if not group["response_complete"] and review["label"] != "technical_failure":
        raise ValueError("undelivered answer must be a technical failure")
    if review["label"] in {"complete", "appropriate_abstention", "appropriate_uncertainty"} and any(review[k] for k in FIELDS[1:]):
        raise ValueError("correct review contradicts unsupported flags")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-root", required=True, type=Path)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--workload", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--adjudications", nargs="*", default=[], type=Path)
    args = parser.parse_args()
    groups, resolved, disagreements, provenance = {}, {}, [], {}
    agreement = 0
    for packet in sorted(args.cohort_root.glob("cohort*/packet.jsonl")):
        cohort = packet.parent
        g, a, b = indexed(packet), indexed(cohort/"reviewer_a.jsonl"), indexed(cohort/"reviewer_b.jsonl")
        if set(g) != set(a) or set(g) != set(b) or set(g) & set(groups):
            raise ValueError(f"missing, duplicate or overlapping review groups: {cohort}")
        for path in (packet, cohort/"reviewer_a.jsonl", cohort/"reviewer_b.jsonl"):
            provenance[str(path)] = sha256(path.read_bytes()).hexdigest()
        groups.update(g)
        for aid in g:
            validate(a[aid], g[aid]); validate(b[aid], g[aid])
            if all(a[aid][key] == b[aid][key] for key in FIELDS):
                resolved[aid] = {**a[aid], "review_resolution": "two_independent_assistants_agreed"}
                agreement += 1
            else:
                disagreements.append({**g[aid], "judgment_a": a[aid], "judgment_b": b[aid]})
    overrides = {}
    for path in args.adjudications:
        provenance[str(path)] = sha256(path.read_bytes()).hexdigest()
        for aid, row in indexed(path).items():
            if aid not in groups or aid in overrides:
                raise ValueError("unknown or duplicate adjudication")
            validate(row, groups[aid]); overrides[aid] = row
    resolved.update({aid: {**row, "review_resolution": "blinded_adjudication_or_documented_audit"}
                     for aid, row in overrides.items()})
    workload = json.loads(args.workload.read_text())
    actual_groups, mapping = build(args.run_root, workload)
    if groups != actual_groups:
        raise ValueError("cohort content/evidence/citations/coverage differs from final raw observations")
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=False)
    (output/"blind").mkdir()
    def write(name, data):
        (output/name).write_text(json.dumps(data, indent=2, ensure_ascii=False)+"\n")
    def lines(name, data):
        (output/name).write_text("".join(canonical(row)+"\n" for row in data))
    lines("blind/packet.jsonl", groups.values())
    write("blind/private_mapping.json", mapping)
    lines("disagreement_packet.jsonl", disagreements)
    pending = sorted(set(groups)-set(resolved))
    write("review_agreement.json", {
        "unique_groups": len(groups), "observations": len(mapping),
        "initial_label_and_both_flags_agreement": agreement,
        "initial_disagreements": len(disagreements), "adjudicated_or_audited": len(overrides),
        "pending_ids": pending, "reviewer_type": "two independent blinded assistant contexts",
        "independent_human_review": "pending", "input_sha256": provenance,
        "group_content_evidence_citation_mapping_reconstruction": "passed",
        "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "resolved_labels": dict(Counter(r["label"] for r in resolved.values())),
    })
    if not pending:
        lines("resolved.jsonl", resolved.values())
    print(f"{len(groups)} groups; {agreement} agree; {len(disagreements)} disagreements; {len(pending)} pending")


if __name__ == "__main__":
    main()
