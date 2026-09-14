"""Export sealed partial cohorts and reuse blinded reviews by exact public content.

Standard library only. Export is run only while model inference is paused.
Other commands open public packets and sealed reviewer artifacts, never raw
experiment observations or condition mappings. No semantic labels are guessed.
"""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import random
import shlex
import sys

import reconcile_independent_retrieval_reviews as review

ROOT=Path(__file__).resolve().parents[1]
ANALYZER=ROOT/"scripts/analyze_independent_retrieval.py"
TEST=ROOT/"tests/test_retrieval_review_batches.py"


def instructions_from_source(path=ANALYZER):
    for node in ast.parse(path.read_text()).body:
        if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=="REVIEW_INSTRUCTIONS" for target in node.targets):
            result=ast.literal_eval(node.value)
            if not isinstance(result,str):break
            return result
    raise ValueError("analyzer has no literal shared review instructions")


def public_content(item):
    return review.canonical({key:value for key,value in item.items() if key!="review_id"})


def observe_key(row):
    return f"slot_{row['slot']:02d}:{row['case']['id']}"


def blind_packets(rows,refs,seed):
    """Intentionally identical to the analyzer's public packet construction."""
    grouped=defaultdict(list)
    for row in rows:
        key=review.canonical([row["case"]["id"],row["status"],
            row.get("response",{}).get("speech") if row["status"]=="ok" else None])
        grouped[key].append(row)
    rng=random.Random(seed);keys=sorted(grouped);rng.shuffle(keys)
    packets=[];mapping=[]
    for key in keys:
        group=grouped[key];row=group[0];reference=refs["cases"][row["case"]["id"]]
        identifier="review_"+f"{rng.getrandbits(128):032x}"
        packets.append({"review_id":identifier,"prompt":row["case"]["prompt"],
            "answer":row.get("response",{}).get("speech") if row["status"]=="ok" else None,
            "delivery_status":"delivered" if row["status"]=="ok" else "not_delivered",
            "answerability":reference["answerability"],"rubric":reference["rubric"],
            "reference_facts_without_ids":[record["canonical_text"] for record in refs["memory_catalog"]
                if reference["authorization_expected"] and record["profile_id"]==row["case"]["profile_id"]
                and record["final_state"]=="active"]})
        mapping.append({"review_id":identifier,"case_id":row["case"]["id"],
                        "observation_keys":[observe_key(value) for value in group]})
    review.packet_index(packets)
    second=list(packets);random.Random(seed^0xD21A09).shuffle(second)
    return packets,second,mapping


def verify_truth_catalog(freeze,runtime,refs):
    prepared=review.read(freeze/"prepared_snapshot/setup.json")["details"]
    instant=lambda value:datetime.fromisoformat(value.replace("Z","+00:00"))
    seed=runtime["memory_seed"];at=instant(seed["evaluation_at"]);retention=seed.get("retention_days")
    current=[record for profile in prepared["profiles"] if profile["profile_id"]==seed["profile_id"]
        for record in profile["records"] if record["status"]=="active" and record["consent_status"]=="confirmed"
        and instant(record["valid_from"])<=at
        and (record["valid_until"] is None or instant(record["valid_until"])>at)
        and (record["retention_until"] is None or instant(record["retention_until"])>at)
        and (retention is None or instant(record["created_at"])>at-timedelta(days=retention))]
    catalog=[record for record in refs["memory_catalog"] if record["profile_id"]==seed["profile_id"] and record["final_state"]=="active"]
    truth=lambda values:{value["id"]:value["canonical_text"] for value in values}
    if len(current)!=23 or len(catalog)!=23 or truth(current)!=truth(catalog):
        raise ValueError("public truth context must equal the 23 authoritative current authorized facts")


def collect_sealed_rows(freeze,run):
    # Lazy import keeps remapping independent from raw collection provenance.
    import independent_retrieval_continuation as continuation
    freeze,run=freeze.resolve(),run.resolve()
    review.verify_seal(freeze);review.verify_seal(run)
    frozen=review.read(freeze/"freeze.json");runtime=review.read(freeze/"runtime.json");refs=review.read(freeze/"references.json")
    for name,expected in frozen["source_sha256"].items():
        if review.digest(ROOT/name)!=expected or review.digest(freeze/"source"/name)!=expected:
            raise ValueError("original archived or current frozen source changed")
    if review.digest(freeze/"runtime.json")!=frozen["runtime_sha256"] or review.digest(freeze/"references.json")!=frozen["references_sha256"]:
        raise ValueError("frozen runtime or reference contents changed")
    cases={case["id"]:case for case in runtime["execution_cases"]}
    if len(cases)!=48 or set(cases)!=set(refs["cases"]) or len(frozen["schedule"])!=18 or frozen["planned_attempts"]!=864:
        raise ValueError("original experiment size or request/reference correspondence changed")
    verify_truth_catalog(freeze,runtime,refs)
    chronology=continuation.collection_chain(run,freeze)
    if not chronology["attempted"]:raise ValueError("no attempted requests in sealed cohort")
    run_plan=review.read(run/"plan.json")
    if run_plan.get("continuation_directory"):
        directory=Path(run_plan["continuation_directory"])
        plan=continuation.verify_continuation(freeze,directory)
        if run_plan["continuation_sha256"]!=review.digest(directory/"continuation.json") or Path(plan["authorized_run_directory"]).resolve()!=run:
            raise ValueError("run continuation authorization differs")
    rows=[]
    for entry in chronology["prior_sessions"]:
        directory=Path(entry["directory"]);manifest=review.read(directory/"manifest.json")
        fragment=manifest.get("fragment")
        if fragment:
            proof=continuation.verify_ledger(freeze,Path(fragment["continuation_directory"]),
                Path(fragment["ledger_directory"]),manifest["slot"]["slot"],fragment["offset"])
            if Path(proof["authorized_worker_directory"]).resolve()!=directory.resolve():
                raise ValueError("fragment physical directory differs from its authorization")
        rows.extend(review.lines(directory/"observations.jsonl"))
    if len(rows)!=chronology["attempted"] or len({observe_key(row) for row in rows})!=len(rows):
        raise ValueError("cohort coverage differs from unique sealed prefix")
    return rows,refs,chronology


def provenance(directory,command,inputs,metadata,extra_sources=()):
    source=directory/"source";source.mkdir(mode=0o700)
    dependencies=[Path(__file__),Path(review.__file__),*extra_sources]
    if TEST.exists():dependencies.append(TEST)
    hashes={}
    for path in dict.fromkeys(dependencies):
        review.copy_exact(path,source/path.name);hashes[str(path.resolve())]=review.digest(path)
    review.write(directory/"provenance.json",{"created_at":datetime.now(timezone.utc).isoformat(),
        "command":command,"working_directory":str(Path.cwd()),"source_sha256":hashes,
        "inputs":{str(Path(path).resolve()):review.digest(path) for path in inputs},
        "semantic_judgments_generated_by_program":False,"human_validation":"pending",**metadata})
    replay=[sys.executable,str(Path(__file__).resolve()),*command]
    if "--output" in replay:replay[replay.index("--output")+1]="/absolute/path/to/a/new/batch-artifact"
    (directory/"commands.sh").write_text("# Offline only; export requires a no-model interval.\ncd "+shlex.quote(str(Path.cwd()))+"\n"+shlex.join(replay)+"\n")


def export(args,command):
    rows,refs,chronology=collect_sealed_rows(args.freeze,args.run)
    seed=int.from_bytes(os.urandom(32),"big")
    packets,second,mapping=blind_packets(rows,refs,seed)
    directory=review.new_directory(args.output)
    public=directory/"blinded";public.mkdir(mode=0o700);private=directory/"private";private.mkdir(mode=0o700)
    review.write_lines(public/"packet_a.jsonl",packets);review.write_lines(public/"packet_b.jsonl",second)
    (public/"REVIEW_INSTRUCTIONS.md").write_text(instructions_from_source())
    review.write(private/"seed.json",{"seed":seed});review.write(private/"mapping.json",mapping)
    review.write(private/"cohort.json",{"freeze":str(args.freeze.resolve()),"run":str(args.run.resolve()),
        "freeze_seal_sha256":review.digest(args.freeze/"seal.json"),"run_seal_sha256":review.digest(args.run/"seal.json"),
        "attempted":len(rows),"remaining":chronology["remaining"],"sessions":chronology["prior_sessions"],
        "scope":"sealed cumulative strict-prefix cohort; final full analyzer audit and coverage remain required"})
    provenance(directory,command,[args.freeze/"seal.json",args.run/"seal.json"],
        {"phase":"export_partial_blinded_cohort","private_mapping_read":True,"review_mapping_exposed_in_public":False},
        [ANALYZER,ROOT/"scripts/independent_retrieval_continuation.py",ROOT/"scripts/independent_retrieval_supervisor.py"])
    (directory/"WORKFLOW.md").write_text(WORKFLOW)
    review.seal(directory)
    print(review.canonical({"output":str(directory),"attempted":len(rows),"blinded_groups":len(packets)}))


def identities(primary,aliases=()):
    value=primary.strip();others=[item.strip() for item in aliases]
    if not value or any(not item for item in others):raise ValueError("reviewer identity must be nonempty")
    return value,sorted(set([value,*others]))


def load_batch(directory):
    review.verify_seal(directory)
    metadata=review.read(directory/"review_batch.json")
    if metadata["artifact_type"]!="frozen_reviewer_batch":raise ValueError("not a frozen individual reviewer batch")
    primary,aliases=identities(metadata["reviewer"],metadata.get("identity_aliases",[]))
    if primary!=metadata["reviewer"] or aliases!=metadata["identity_aliases"]:
        raise ValueError("reviewer identity metadata is not normalized")
    packet=review.packet_index(review.lines(directory/"packet.jsonl"))
    judgments=review.review_index(review.lines(directory/"original_reviews.jsonl"),packet)
    if metadata["packet_sha256"]!=review.digest(directory/"packet.jsonl") or metadata["sheet_sha256"]!=review.digest(directory/"original_reviews.jsonl"):
        raise ValueError("review batch content binding differs")
    return metadata,packet,judgments


def batch_metadata(directory,reviewer,aliases,**extra):
    review.write(directory/"review_batch.json",{"artifact_type":"frozen_reviewer_batch", "reviewer":reviewer,
        "identity_aliases":aliases,"packet_sha256":review.digest(directory/"packet.jsonl"),
        "sheet_sha256":review.digest(directory/"original_reviews.jsonl"),
        "review_kind":"independent blinded assistant review","human_validation":"pending",
        "identity_scope":"caller-provided identity and alias attestation; not proof of independent cognition",**extra})


def freeze_review(args,command):
    packet=review.packet_index(review.lines(args.packet))
    review.review_index(review.lines(args.sheet),packet)
    primary,aliases=identities(args.reviewer,args.alias)
    directory=review.new_directory(args.output)
    for path,name in ((args.packet,"packet.jsonl"),(args.instructions,"REVIEW_INSTRUCTIONS.md"),(args.sheet,"original_reviews.jsonl")):
        review.copy_exact(path,directory/name)
    batch_metadata(directory,primary,aliases,originals_preserved_exactly=True)
    provenance(directory,command,[args.packet,args.instructions,args.sheet],{"phase":"freeze_individual_review","private_mapping_read":False})
    review.seal(directory)
    print(review.canonical({"output":str(directory),"reviewer":primary,"frozen_judgments":len(packet)}))


def compute_remapping(packet,candidates):
    """Content equality and existing score-vector consistency, never grading."""
    reused=[];missing=[];mapping=[]
    for identifier,item in packet.items():
        options=candidates.get(public_content(item),[])
        eligible=bool(options) and all(review.agrees(options[0]["judgment"],choice["judgment"]) for choice in options[1:])
        if eligible:reused.append({**options[0]["judgment"],"review_id":identifier})
        else:missing.append(item)
        mapping.append({"final_review_id":identifier,"public_content_sha256":__import__("hashlib").sha256(public_content(item).encode()).hexdigest(),
            "status":"reused_exact_public_content" if eligible else "conflicting_prior_score_vectors" if options else "unreviewed_public_content",
            "prior_candidates":[{k:v for k,v in option.items() if k!="judgment"} for option in options],
            "selected_candidate":{k:v for k,v in options[0].items() if k!="judgment"} if eligible else None})
    return reused,missing,mapping


def remap(args,command):
    packet_values=review.lines(args.packet);packet=review.packet_index(packet_values)
    primary,aliases=identities(args.reviewer,args.alias)
    candidates=defaultdict(list);batches=[]
    if len({path.resolve() for path in args.batch})!=len(args.batch):raise ValueError("duplicate prior batch directory")
    for index,path in enumerate(args.batch):
        metadata,prior,judgments=load_batch(path)
        if not set(metadata["identity_aliases"])<=set(aliases):raise ValueError("prior sheet belongs to an unapproved reviewer identity")
        if review.digest(path/"REVIEW_INSTRUCTIONS.md")!=review.digest(args.instructions):
            raise ValueError("review instruction bytes changed between batches")
        batches.append({"batch_index":index,"directory":str(path.resolve()),"seal_sha256":review.digest(path/"seal.json"),
                        "reviewer":metadata["reviewer"],"identity_aliases":metadata["identity_aliases"]})
        for identifier,item in prior.items():
            candidates[public_content(item)].append({"batch_index":index,"prior_review_id":identifier,"judgment":judgments[identifier]})
    reused,missing,mapping=compute_remapping(packet,candidates)
    random.SystemRandom().shuffle(missing)
    directory=review.new_directory(args.output)
    review.copy_exact(args.packet,directory/"packet.jsonl");review.copy_exact(args.instructions,directory/"REVIEW_INSTRUCTIONS.md")
    review.write_lines(directory/"reused_reviews.jsonl",reused);review.write_lines(directory/"missing_packet.jsonl",missing)
    review.write(directory/"remapping.json",mapping)
    archives=directory/"original_batches";archives.mkdir(mode=0o700)
    for index,path in enumerate(args.batch):review.copy_sealed_directory(path,archives/f"batch_{index:03d}")
    review.write(directory/"remap.json",{"reviewer":primary,"identity_aliases":aliases,"batches":batches,
        "groups":len(packet),"reused_groups":len(reused),"missing_groups":len(missing),
        "matching_rule":"exact canonical public packet content excluding only review_id; no observation/model/condition mapping",
        "rationale_rule":"equal label and five flags allow reuse of first exact original rationale; all originals retained",
        "conflict_rule":"conflicting prior score vectors require an explicit new missing-packet judgment",
        "private_mapping_read":False})
    provenance(directory,command,[args.packet,args.instructions,*[path/"seal.json" for path in args.batch]],
        {"phase":"remap_by_exact_public_content","private_mapping_read":False})
    review.seal(directory)
    print(review.canonical({"output":str(directory),"reviewer":primary,"reused_groups":len(reused),"missing_groups":len(missing)}))


def assemble(args,command):
    review.verify_seal(args.remap)
    metadata=review.read(args.remap/"remap.json")
    packet=review.packet_index(review.lines(args.remap/"packet.jsonl"))
    missing=review.packet_index(review.lines(args.remap/"missing_packet.jsonl"))
    reused_values=review.lines(args.remap/"reused_reviews.jsonl")
    reused_packet={identifier:item for identifier,item in packet.items() if identifier not in missing}
    reused=review.review_index(reused_values,reused_packet)
    primary,aliases=identities(metadata["reviewer"],metadata["identity_aliases"])
    if primary!=metadata["reviewer"] or aliases!=metadata["identity_aliases"]:
        raise ValueError("remap reviewer identities differ from normalized provenance")
    candidates=defaultdict(list)
    archives=args.remap/"original_batches"
    if {path.name for path in archives.iterdir()}!={f"batch_{index:03d}" for index in range(len(metadata["batches"]))}:
        raise ValueError("remap original-batch inventory differs")
    for index,recorded in enumerate(metadata["batches"]):
        path=archives/f"batch_{index:03d}";prior_meta,prior,judgments=load_batch(path)
        if recorded["batch_index"]!=index or recorded["seal_sha256"]!=review.digest(path/"seal.json") or any(recorded[key]!=prior_meta[key] for key in ("reviewer","identity_aliases")):
            raise ValueError("remap original batch provenance differs")
        if not set(prior_meta["identity_aliases"])<=set(aliases) or review.digest(path/"REVIEW_INSTRUCTIONS.md")!=review.digest(args.remap/"REVIEW_INSTRUCTIONS.md"):
            raise ValueError("remap original reviewer or instructions differ")
        for identifier,item in prior.items():
            candidates[public_content(item)].append({"batch_index":index,"prior_review_id":identifier,"judgment":judgments[identifier]})
    expected_reused,expected_missing,expected_mapping=compute_remapping(packet,candidates)
    if expected_reused!=reused_values or review.packet_index(expected_missing)!=missing or expected_mapping!=review.read(args.remap/"remapping.json"):
        raise ValueError("remap reused judgments or public-content mapping differ from frozen originals")
    if metadata["groups"]!=len(packet) or metadata["reused_groups"]!=len(reused) or metadata["missing_groups"]!=len(missing):
        raise ValueError("remap coverage accounting differs")
    extra={}
    if missing:
        if args.missing_review is None:raise ValueError("missing public groups require explicit frozen review judgments")
        new_metadata,new_packet,extra=load_batch(args.missing_review)
        if new_packet!=missing:raise ValueError("missing-review packet differs from exact remap missing groups")
        if not set(new_metadata["identity_aliases"])<=set(aliases):raise ValueError("missing sheet belongs to a different reviewer")
        if review.digest(args.missing_review/"REVIEW_INSTRUCTIONS.md")!=review.digest(args.remap/"REVIEW_INSTRUCTIONS.md"):
            raise ValueError("missing-review instructions changed")
    elif args.missing_review is not None:raise ValueError("no missing groups exist for a supplemental sheet")
    combined=[(reused if identifier in reused else extra)[identifier] for identifier in packet]
    review.review_index(combined,packet)
    directory=review.new_directory(args.output)
    review.copy_exact(args.remap/"packet.jsonl",directory/"packet.jsonl")
    review.copy_exact(args.remap/"REVIEW_INSTRUCTIONS.md",directory/"REVIEW_INSTRUCTIONS.md")
    review.write_lines(directory/"original_reviews.jsonl",combined)
    review.copy_sealed_directory(args.remap,directory/"sealed_remap")
    if args.missing_review is not None:review.copy_sealed_directory(args.missing_review,directory/"sealed_missing_review")
    batch_metadata(directory,metadata["reviewer"],aliases,assembled_from_frozen_originals=True,
        reused_groups=len(reused),newly_judged_groups=len(extra),public_content_mapping_only=True)
    provenance(directory,command,[args.remap/"seal.json",*([args.missing_review/"seal.json"] if args.missing_review else [])],
        {"phase":"assemble_complete_individual_review","private_mapping_read":False})
    review.seal(directory)
    print(review.canonical({"output":str(directory),"reviewer":metadata["reviewer"],"complete_judgments":len(combined)}))


WORKFLOW="""Blinded review batching (assistant review; human validation pending)

1. During a no-model interval, export a SEALED cumulative run. Only give a
   fresh independent reviewer A blinded/packet_a.jsonl plus instructions;
   give reviewer B packet_b.jsonl plus the same instructions. Do not give
   private/, provenance, raw artifacts, mapping, or the other reviewer's sheet.
2. freeze-review each exact original sheet independently before any comparison.
   Keep the same two reviewers across batches, recording identity aliases.
3. Once the final analyzer exports its public packet, remap separately for
   each reviewer using only that public packet and that reviewer's frozen
   earlier batches. Exact question/answer/status/rubric/full truth context must
   match. Give each reviewer only missing_packet.jsonl and instructions. If
   earlier scores conflict for identical content, a new judgment is required.
4. freeze-review each missing sheet, then assemble each complete A/B sheet.
   Originals, all aliases, and public-content remapping remain sealed.
5. Use reconcile_independent_retrieval_reviews.py compare on final public
   packet and the two assembled original_reviews.jsonl files; a fresh third
   blinded reviewer adjudicates disagreements. Resolve and seal all judgments
   before verify-mapping or examining any private observation mapping.

The program validates schema/provenance only. It does not produce or infer
semantic labels, verify cognitive independence, or replace final full analysis.
"""


def main(argv=None):
    command=list(sys.argv[1:] if argv is None else argv)
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest="command",required=True)
    export_parser=sub.add_parser("export")
    export_parser.add_argument("--freeze",type=Path,required=True);export_parser.add_argument("--run",type=Path,required=True)
    freeze_parser=sub.add_parser("freeze-review");freeze_parser.add_argument("--sheet",type=Path,required=True)
    remap_parser=sub.add_parser("remap");remap_parser.add_argument("--batch",type=Path,action="append",default=[])
    for item in (freeze_parser,remap_parser):
        item.add_argument("--packet",type=Path,required=True);item.add_argument("--instructions",type=Path,required=True)
        item.add_argument("--reviewer",required=True);item.add_argument("--alias",action="append",default=[])
    assemble_parser=sub.add_parser("assemble");assemble_parser.add_argument("--remap",type=Path,required=True)
    assemble_parser.add_argument("--missing-review",type=Path)
    for item in (export_parser,freeze_parser,remap_parser,assemble_parser):item.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(command)
    {"export":export,"freeze-review":freeze_review,"remap":remap,"assemble":assemble}[args.command](args,command)


if __name__=="__main__":main()
