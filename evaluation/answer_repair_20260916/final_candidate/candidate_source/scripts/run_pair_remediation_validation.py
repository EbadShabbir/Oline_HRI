"""Sequential Qwen-pair validation with isolated memory and a Jetson watchdog.

Only installed production models are used. Raw fictional results are saved in
a new owner-only directory. Run focus, adaptive, learn, and recall separately;
learn/recall exercise different processes and a persistent isolated database.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile
from time import perf_counter, perf_counter_ns

from oline_hri.config import load_config
from oline_hri.conversation import Conversation, _required_memory_ids
from oline_hri.embedding import BgeOnnxEmbedder
from oline_hri.evaluation import load_evaluation_suite, materialize_memory_store
from oline_hri.evaluation_model_pairs import (
    SafetyGateError, _DurableJsonlWriter, _StreamingSafetyMonitor,
    _boot_id, _throttle_snapshot, _require_runtime_safe, capture_safety_snapshot,
)
from oline_hri.evaluation_runner import run_evaluation
from oline_hri.evaluation_scoring import (
    load_observation_jsonl, render_summary_markdown, score_observations,
)
from oline_hri.evaluation_telemetry import TegrastatsSampler
from oline_hri.ollama import OllamaClient
from oline_hri.memory import MemoryStore
from oline_hri.retrieval import HybridRetriever
from oline_hri.routing import ConversationRouter


class GuardedSampler(TegrastatsSampler):
    def __init__(self, monitor):
        self.monitor = monitor
        self.last_sample = perf_counter()
        self.boot_id = _boot_id()
        self.trip_events = _throttle_snapshot()
        super().__init__(interval_ms=500, on_sample=self.sample)

    def sample(self, record):
        self.last_sample = perf_counter()
        if (
            _boot_id() != self.boot_id
            or _throttle_snapshot() != self.trip_events
        ):
            self.monitor({})
            return
        self.monitor(record)

    def _set_reader_error(self, error):
        super()._set_reader_error(error)
        if not self._stopping.is_set():
            # The monitor treats an invalid record as a fatal telemetry error.
            self.monitor({})


class GuardedBackend:
    def __init__(self, client, snapshot, sampler, *, small_only=False):
        self.client, self.snapshot, self.sampler = client, snapshot, sampler
        self.small_only = small_only
        self.calls = []
        self.generation_seed = 42

    def check(self):
        if self.sampler.monitor.violation:
            raise SafetyGateError(self.sampler.monitor.violation)
        if perf_counter() - self.sampler.last_sample > 5:
            raise SafetyGateError("telemetry stream stalled")
        try:
            return _require_runtime_safe(
                boot_id=self.snapshot["boot_id"],
                initial_trip_events=self.snapshot["thermal_trip_events"],
            )
        except SafetyGateError as error:
            self.sampler.monitor.violation = str(error)
            raise KeyboardInterrupt("Jetson safety boundary crossed") from error

    def chat(self, model, messages, **kwargs):
        if self.small_only and model != "qwen3:0.6b":
            raise SafetyGateError("restart validation permits only the small model")
        self.check()
        fields = set((kwargs.get("response_format") or {}).get("properties", {}))
        purpose = "generation" if "speech" in fields else "classifier"
        if purpose == "generation":
            kwargs["seed"] = self.generation_seed
        started = perf_counter_ns()
        record = {"model": model, "purpose": purpose, "seed": kwargs.get("seed")}
        try:
            result = self.client.chat(model, messages, **kwargs)
            record["generation"] = asdict(result)
            return result
        except Exception as error:
            record["error"] = type(error).__name__
            record["message"] = str(error)
            raise
        finally:
            record["wall_ns"] = perf_counter_ns() - started
            self.calls.append(record)
            self.check()

    def unload_all(self):
        self.client.unload_all()


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def require_ready(snapshot, *, small_only=False):
    # This is a known installed pair previously validated under desktop load.
    # Model-download screening has a separate, stricter start gate.
    if snapshot["resident_models"]:
        raise SafetyGateError("another model is resident; refusing to disturb it")
    if snapshot["memory"]["mem_available_kib"] < 2 * 1024 * 1024:
        raise SafetyGateError("less than 2 GiB available before loading the pair")
    swap_ceiling_mb = 512 if small_only else 384
    if snapshot["memory"]["swap_used_kib"] > swap_ceiling_mb * 1024:
        raise SafetyGateError("swap use exceeds this workload's start gate")
    if max(snapshot["temperatures_c"].values()) >= 55:
        raise SafetyGateError("temperature must be below 55 C before loading")
    if not snapshot["fan_pwm"] or any(snapshot["thermal_trip_events"].values()):
        raise SafetyGateError("fan or thermal-trip start check failed")
    if "15W" not in (snapshot["power_mode"] or ""):
        raise SafetyGateError("expected 15W power mode")


def focus(suite, config, directory, backend, case_ids=()):
    embedder = BgeOnnxEmbedder(config.embedding.model_directory, config.embedding.intra_op_threads)
    with tempfile.TemporaryDirectory(prefix="memory-", dir=directory) as temporary:
        store = materialize_memory_store(suite, Path(temporary) / "memory.sqlite3", embedder=embedder)
        selected = [case for case in suite.cases if case.id in {
            "route_large_no_memory_01", "route_large_no_memory_02", "route_large_no_memory_03",
        }]
        attempts = [(case, seed) for seed in range(42, 47) for case in selected]
        attempts += [(case, 42) for case in suite.cases if case.id.startswith("memory_large_")]
        if case_ids:
            if not set(case_ids).issubset({case.id for case in suite.cases}):
                raise ValueError("unknown focus case ID")
            attempts = [(case, 42) for case in suite.cases if case.id in case_ids]
        with _DurableJsonlWriter(directory / "focus.jsonl") as writer:
            for index, (case, seed) in enumerate(attempts, 1):
                backend.generation_seed = seed
                checkpoint = len(backend.calls)
                router = ConversationRouter(backend, model=config.ollama.small_model)
                conversation = Conversation(
                    backend, router=router, retriever=HybridRetriever(store),
                    system_prompt=config.conversation.system_prompt,
                    small_model=config.ollama.small_model,
                    general_large_model=config.ollama.general_large_model,
                    large_model=config.ollama.large_model,
                    context_length=config.generation.context_length,
                    max_output_tokens=config.generation.max_output_tokens,
                )
                record = {"case_id": case.id, "seed": seed, "prompt": case.prompt}
                started = perf_counter_ns()
                try:
                    reply = conversation.send(case.prompt)
                    record.update(status="ok", response=reply.response.to_dict(),
                                  answer_constraint=reply.answer_constraint,
                                  generation_policy=reply.generation_policy,
                                  reference_ids=list(reply.reference_ids),
                                  generation_model=reply.generation.model,
                                  response_transform=reply.response_transform,
                                  route=asdict(reply.route), memory=reply.memory_diagnostics.to_dict())
                except Exception as error:
                    record.update(status="error", error=type(error).__name__, message=str(error))
                record.update(wall_ns=perf_counter_ns() - started, calls=backend.calls[checkpoint:])
                writer.write(record)
                print(f"focus {index}/{len(attempts)} seed={seed} {case.id}: {record['status']}", flush=True)


def inspect_evidence(suite, config, directory, backend):
    """Inspect real retrieval independently of any answer generation."""
    embedder = BgeOnnxEmbedder(
        config.embedding.model_directory, config.embedding.intra_op_threads
    )
    with tempfile.TemporaryDirectory(prefix="memory-", dir=directory) as temporary:
        store = materialize_memory_store(
            suite, Path(temporary) / "memory.sqlite3", embedder=embedder
        )
        retriever = HybridRetriever(store)
        with _DurableJsonlWriter(directory / "evidence.jsonl") as writer:
            for case in suite.cases:
                if not case.expected_route.memory_required:
                    continue
                backend.check()
                matches = retriever.retrieve(case.prompt, limit=5)
                required = _required_memory_ids(matches[:3], case.prompt)
                record = {
                    "case_id": case.id, "prompt": case.prompt,
                    "ranked": [{"id": m.memory.id,
                                "text": m.memory.canonical_text,
                                "rrf_score": m.fused_score} for m in matches],
                    "linked_ids": list(required),
                }
                writer.write(record)
                print(json.dumps(record), flush=True)
                backend.check()


def paraphrases(config, directory, backend, fixture_path=None):
    fixture_path = fixture_path or Path(__file__).resolve().parents[1] / "evaluation" / "model_pair_runs" / "20260910_recall_paraphrases.json"
    fixture = json.loads(fixture_path.read_text())
    write_json(directory / "fixture.json", fixture)
    embedder = BgeOnnxEmbedder(
        config.embedding.model_directory, config.embedding.intra_op_threads
    )
    store = MemoryStore(directory / "memory.sqlite3",
                        profile_id="fictional_evidence_paraphrases", embedder=embedder)
    items = [store.remember(item["text"], kind=item["kind"], event_time=item.get("event_time"))
             for item in fixture["memories"]]
    write_json(directory / "memories.json", [item.to_dict() for item in items])
    with _DurableJsonlWriter(directory / "paraphrases.jsonl") as writer:
        for case in fixture["cases"]:
            checkpoint = len(backend.calls)
            conversation = Conversation(
                backend,
                router=ConversationRouter(backend, model=config.ollama.small_model),
                retriever=HybridRetriever(store),
                system_prompt=config.conversation.system_prompt,
                small_model=config.ollama.small_model,
                general_large_model=config.ollama.general_large_model,
                large_model=config.ollama.large_model,
                context_length=config.generation.context_length,
                max_output_tokens=config.generation.max_output_tokens,
            )
            record = {**case, "expected_ids": [items[i].id for i in case["memory_indices"]]}
            started = perf_counter_ns()
            try:
                reply = conversation.send(case["prompt"])
                record.update(status="ok", response=reply.response.to_dict(),
                              response_transform=reply.response_transform,
                              answer_constraint=reply.answer_constraint,
                              generation_policy=reply.generation_policy,
                              reference_ids=list(reply.reference_ids),
                              generation_model=reply.generation.model,
                              route=asdict(reply.route.decision),
                              memory=reply.memory_diagnostics.to_dict())
            except Exception as error:
                record.update(status="error", error=type(error).__name__, message=str(error))
            record.update(wall_ns=perf_counter_ns() - started, calls=backend.calls[checkpoint:])
            writer.write(record)
            print(json.dumps({k: v for k, v in record.items() if k != "calls"}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("focus", "adaptive", "learn", "recall", "evidence", "paraphrases", "composition"))
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--memory-run-dir", type=Path)
    parser.add_argument("--fixture", type=Path, help="Fictional paraphrases fixture only")
    parser.add_argument("--case-id", action="append", default=[], help="Select a focus diagnostic case")
    args = parser.parse_args()
    if args.fixture is not None and args.phase not in {"paraphrases", "composition"}:
        parser.error("--fixture is only supported for paraphrases/composition")
    if args.case_id and args.phase != "focus":
        parser.error("--case-id is only supported for focus")
    os.umask(0o077)
    directory = args.output_dir.resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    config = load_config()
    if {config.ollama.small_model, config.ollama.large_model, config.ollama.general_large_model} != {"qwen3:0.6b", "qwen3:1.7b"}:
        raise SafetyGateError("this validation is restricted to the selected Qwen pair")
    start = capture_safety_snapshot()
    write_json(directory / "start.json", start)
    small_only = args.phase in {"learn", "recall", "paraphrases"}
    require_ready(start, small_only=small_only)
    write_json(directory / "workload.json", {
        "small_only": small_only,
        "start_swap_ceiling_mb": 512 if small_only else 384,
        "runtime_swap_ceiling_mb": 512,
        "note": "Restart prompts need only the small model; large requests are blocked.",
    })
    write_json(directory / "config.json", config.to_dict())
    root = Path(__file__).resolve().parents[1]
    write_json(directory / "source_hashes.json", {
        str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest()
        for path in sorted((root / "src" / "oline_hri").glob("*.py"))
    })
    client = OllamaClient(config.ollama, config.generation)
    with _DurableJsonlWriter(directory / "telemetry.jsonl") as writer:
        monitor = _StreamingSafetyMonitor(writer)
        sampler = GuardedSampler(monitor)
        backend = GuardedBackend(client, start, sampler, small_only=small_only)
        try:
            with sampler:
                if args.phase == "focus":
                    focus(load_evaluation_suite(), config, directory, backend, args.case_id)
                elif args.phase == "evidence":
                    inspect_evidence(load_evaluation_suite(), config, directory, backend)
                elif args.phase in {"paraphrases", "composition"}:
                    paraphrases(config, directory, backend, args.fixture)
                elif args.phase == "adaptive":
                    suite = load_evaluation_suite()
                    run_evaluation(suite, config, directory / "observations.jsonl",
                                   strategies=("adaptive",), backend=backend, progress=sys.stdout)
                    summary = score_observations(suite, load_observation_jsonl(directory / "observations.jsonl"))
                    write_json(directory / "summary.json", summary)
                    with (directory / "report.md").open("x") as output:
                        output.write(render_summary_markdown(summary))
                else:
                    if args.memory_run_dir is None:
                        raise ValueError("learn/recall require --memory-run-dir")
                    import run_auto_memory_dry_run as dry_run
                    dry_run.OllamaClient = lambda *_: backend
                    sys.argv = ["run_auto_memory_dry_run", "--run-directory", str(args.memory_run_dir), "--phase", args.phase]
                    dry_run.main()
        finally:
            client.unload_all()
            write_json(directory / "backend_calls.json", backend.calls)
            write_json(directory / "telemetry_summary.json", sampler.summary())
            write_json(directory / "finish.json", {
                "guard_violation": monitor.violation,
                "telemetry_reader_error": (
                    None if sampler._reader_error is None else
                    {"type": type(sampler._reader_error).__name__, "message": str(sampler._reader_error)}
                ),
                **capture_safety_snapshot(),
            })
    print(f"ARTIFACTS {directory}", flush=True)


if __name__ == "__main__":
    main()
