"""Guarded continuation of an immutable, proven-unattempted request suffix.

Only orchestration differs from the original frozen runner. Its run_cases,
adapter, client, decoding, guards, snapshot and cleanup execute unchanged.
Each physical fragment begins cold and retains its sole model until cleanup;
its local index starts at one and is not the original logical slot position.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
from time import perf_counter_ns

import run_independent_retrieval as runner
from independent_retrieval_adapter import open_snapshot
from independent_retrieval_continuation import verify_continuation, verify_ledger


def verified_inputs(args):
    """Validate new orchestration authority and old execution freeze separately."""
    continuation=verify_continuation(args.freeze,args.continuation)
    ledger=verify_ledger(args.freeze,args.continuation,args.ledger,args.slot,args.offset)
    frozen,runtime=runner.verify_frozen(args.freeze)
    slot=frozen["schedule"][args.slot-1]
    if slot["slot"]!=args.slot or not 0<=args.offset<len(slot["request_ids"]):
        raise ValueError("fragment requires a valid original slot and nonempty suffix")
    suffix=slot["request_ids"][args.offset:]
    if ledger["slot"]!=args.slot or ledger["offset"]!=args.offset or ledger["request_ids"]!=suffix:
        raise ValueError("sealed ledger does not authorize the exact original suffix")
    if args.baseline.resolve()!=Path(ledger["baseline"]).resolve():
        raise ValueError("fragment baseline must be the sealed ledger's original baseline")
    if args.output.absolute()!=Path(ledger["authorized_worker_directory"]).resolve():
        raise ValueError("fragment output must be the sealed ledger's one-use worker directory")
    return continuation,ledger,frozen,runtime,slot,suffix


def fragment_metadata(args,suffix):
    return {"offset":args.offset,"request_ids":suffix,"planned":len(suffix),
        "ledger_directory":str(args.ledger.resolve()),
        "ledger_sha256":runner.file_hash(args.ledger/"ledger.json"),
        "ledger_seal_sha256":runner.file_hash(args.ledger/"seal.json"),
        "continuation_directory":str(args.continuation.resolve()),
        "continuation_sha256":runner.file_hash(args.continuation/"continuation.json"),
        "continuation_seal_sha256":runner.file_hash(args.continuation/"seal.json"),
        "local_index_scope":"one-based index within this physical cold-start fragment"}


def _session(args):
    began=perf_counter_ns()
    _,_,frozen,runtime,slot,suffix=verified_inputs(args)
    config=runner.single_model_config(runner.configuration(),slot["model"])
    directory=runner.pair._new_private_directory(args.output.absolute())
    fragment=fragment_metadata(args,suffix)
    runner.write(directory/"manifest.json",{
        "slot":slot,"freeze_sha256":runner.file_hash(args.freeze/"freeze.json"),
        "config":config.to_dict(),"device_policy":runner.policy_dict(),"fragment":fragment})
    status="incomplete";failure=None;errors=[]
    sampler=backend=client=None;start=None;path=None;before_hash=None
    with runner.stage2_limits():
        try:
            runner.require_exclusive()
            start=runner.pair.capture_safety_snapshot();runner.write(directory/"start.json",start)
            baseline=runner.json.loads(args.baseline.read_text())
            if any(start[key]!=baseline[key] for key in ("boot_id","thermal_trip_events","power_mode")) \
                    or start["memory"]["swap_total_kib"]!=baseline["memory"]["swap_total_kib"]:
                raise runner.pair.SafetyGateError("device baseline changed across collection fragments")
            runner.require_ready(start)
            with runner.pair._DurableJsonlWriter(directory/"http_calls.jsonl") as http, \
                 runner.pair._DurableJsonlWriter(directory/"telemetry.jsonl") as telemetry:
                client=runner.DurableClient(config.ollama,config.generation,http_writer=http,retain_large_model=True)
                monitor=runner.pair._StreamingSafetyMonitor(telemetry)
                sampler=runner.GuardedSampler(monitor)
                backend=runner.ComparisonBackend(client,start,sampler,(slot["model"],))
                with sampler:
                    try:
                        runner.initial_sample(backend,sampler);setup_began=perf_counter_ns()
                        embedder=runner.BgeOnnxEmbedder(config.embedding.model_directory,config.embedding.intra_op_threads)
                        path=directory/"memory.sqlite3"
                        shutil.copyfile(args.freeze/"prepared_snapshot/memory.sqlite3",path);path.chmod(0o600)
                        before_hash=runner.file_hash(path)
                        store=open_snapshot(path,runtime["memory_seed"],embedder)
                        runner.write(directory/"setup.json",{
                            "wall_ns":perf_counter_ns()-setup_began,"snapshot_sha256":before_hash})
                        backend.check()
                        cases={case["id"]:case for case in runtime["execution_cases"]}
                        rows=runner.run_cases([cases[identifier] for identifier in suffix],
                                              slot,config,backend,store,directory)
                        status="complete" if all(row["status"]=="ok" for row in rows) else "complete_with_errors"
                        if before_hash!=runner.file_hash(path):raise ValueError("prepared snapshot mutated")
                    finally:
                        cleanup_began=perf_counter_ns()
                        errors.extend(runner.cleanup_owned(client,backend))
                        runner.write(directory/"cleanup_timing.json",{"wall_ns":perf_counter_ns()-cleanup_began})
        except BaseException as error:
            status="interrupted";failure={"type":type(error).__name__,"message":str(error)}
        finally:
            if path is not None and path.exists():
                after_hash=runner.file_hash(path)
                runner.write(directory/"snapshot_verification.json",{
                    "before":before_hash,"after":after_hash,"unchanged":before_hash==after_hash})
                if before_hash!=after_hash:errors.append("prepared snapshot mutated")
            try:
                finish=runner.pair.capture_safety_snapshot()
                if finish["resident_models"]:errors.append("resident models after fragment")
                if start and any(finish[key]!=start[key] for key in ("boot_id","thermal_trip_events","power_mode")):
                    errors.append("boot/trips/power changed")
                if start and finish["memory"]["swap_total_kib"]!=start["memory"]["swap_total_kib"]:
                    errors.append("swap capacity changed")
            except BaseException as error:
                finish={"error":type(error).__name__,"message":str(error)};errors.append("missing final snapshot")
            runner.write(directory/"finish.json",finish)
            if sampler:runner.write(directory/"telemetry_summary.json",sampler.summary())
            try:
                verified_inputs(args)
            except BaseException as error:
                errors.append("final original/continuation/ledger integrity: "+str(error))
            if errors:status="verification_failed"
            observations=directory/"observations.jsonl"
            attempted=0
            if observations.exists():
                with observations.open() as stream:attempted=sum(1 for _ in stream)
            runner.write(directory/"summary.json",{
                "status":status,"failure":failure,"cleanup_errors":errors,"attempted":attempted,
                "planned":len(suffix),"original_planned":48,"fragment_offset":args.offset,
                "session_wall_ns":perf_counter_ns()-began})
            runner.seal(directory)
    return 0 if status.startswith("complete") else 1


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ("freeze","continuation","ledger","output","baseline"):
        parser.add_argument("--"+flag,type=Path,required=True)
    parser.add_argument("--slot",type=int,choices=range(1,19),required=True)
    parser.add_argument("--offset",type=int,choices=range(48),required=True)
    args=parser.parse_args(argv)
    with runner.inference_lock():return _session(args)


if __name__=="__main__":raise SystemExit(main())
