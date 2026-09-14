"""Run a recorded fictional conversation through the real interactive chat loop.

Run learn and recall separately to test a genuine process restart. This does
not change application behavior or use the default personal-memory database.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import platform
import time

from oline_hri.cli import _RouteReportingRouter, _run_chat
from oline_hri.config import load_config
from oline_hri.conversation import Conversation
from oline_hri.embedding import BgeOnnxEmbedder
from oline_hri.memory import MemoryStore
from oline_hri.memory_capture import AutomaticMemoryCapture, AutomaticMemoryClassifier
from oline_hri.ollama import OllamaClient
from oline_hri.retrieval import HybridRetriever
from oline_hri.routing import ConversationRouter


DISCLOSURES = (
    ("greeting", "Hello, let's have a chat.", "skipped", None),
    ("tea", "I prefer peppermint tea without sugar.", "stored", "preference"),
    ("meetings", "My robotics meetings are Thursday afternoons.", "stored", "routine"),
    ("partner", "Maya is my sensor calibration partner.", "stored", "relationship"),
    ("bicycle", "I own a green bicycle.", "stored", "fact"),
    ("plant", "My desk plant is named Sprout.", "stored", "fact"),
    ("event", "I completed a camera calibration test.", "stored", "event"),
    ("length", "I prefer short answers.", "stored", "preference"),
    ("mood", "I feel tired right now.", "skipped", None),
    ("duplicate", "I prefer peppermint tea without sugar.", "duplicate", "preference"),
)
QUESTIONS = (
    ("tea", "What kind of tea do I prefer?", "peppermint tea without sugar"),
    ("meetings", "When are my robotics meetings?", "Thursday afternoons"),
    ("partner", "Who is Maya to me?", "your sensor calibration partner"),
    ("bicycle", "What color is my bicycle?", "green"),
    ("plant", "What is my desk plant's name?", "Sprout"),
    ("event", "What test did I complete?", "camera calibration test"),
    ("length", "Do I prefer short or long answers?", "short answers"),
    ("unknown_dog", "What is my dog's name?", "unknown; no dog information provided"),
    ("unknown_birthday", "When is my birthday?", "unknown; no birthday information provided"),
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class Recorder:
    def __init__(self, run_directory, phase, store):
        self.run_directory = run_directory
        self.phase = phase
        self.store = store
        self.turns = []
        self.active = None
        self.started = None

    def begin(self, case):
        self.active = {**case, "calls": [], "started_utc": utc_now()}
        self.started = time.perf_counter()
        print(f"START {self.phase} {case['id']}: {case['text']}", flush=True)

    def finish(self):
        if self.active is None:
            return
        self.active["full_turn_seconds"] = time.perf_counter() - self.started
        self.active["memories_after"] = [
            item.to_dict() for item in self.store.list_memories()
        ]
        self.turns.append(self.active)
        with (self.run_directory / f"{self.phase}_turns.jsonl").open(
            "a", encoding="utf-8"
        ) as handle:
            handle.write(json.dumps(self.active, ensure_ascii=False) + "\n")
        print(
            "RESULT " + json.dumps({
                "id": self.active["id"],
                "reply": self.active.get("reply"),
                "error": self.active.get("error"),
                "route": self.active.get("route"),
                "capture": self.active.get("capture"),
                "reply_seconds": self.active.get("reply_seconds"),
                "full_turn_seconds": self.active["full_turn_seconds"],
                "records": len(self.active["memories_after"]),
            }, ensure_ascii=False), flush=True,
        )
        self.active = None


class ObservedBackend:
    def __init__(self, client, recorder):
        self.client = client
        self.recorder = recorder

    def chat(self, model, messages, **kwargs):
        fields = set(kwargs.get("response_format", {}).get("properties", {}))
        purpose = (
            "memory_router" if "memory_required" in fields else
            "size_router" if "model_size" in fields else
            "capture" if "store_memory" in fields else "generation"
        )
        started = time.perf_counter()
        record = {"purpose": purpose, "model": model}
        try:
            result = self.client.chat(model, messages, **kwargs)
            record["result"] = asdict(result)
            return result
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            record["seconds"] = time.perf_counter() - started
            self.recorder.active["calls"].append(record)


class ObservedRouter:
    def __init__(self, router, recorder):
        self.router, self.recorder = router, recorder

    def route(self, text, *, history=()):
        result = self.router.route(text, history=history)
        self.recorder.active["route"] = asdict(result.decision)
        self.recorder.active["router_history_messages"] = len(history)
        return result


class ObservedConversation:
    def __init__(self, conversation, recorder):
        self.conversation, self.recorder = conversation, recorder

    def send(self, text):
        try:
            result = self.conversation.send(text)
            self.recorder.active["reply"] = json.loads(result.response.to_json())
            self.recorder.active["memory_ids"] = result.memory_diagnostics.to_dict()
            self.recorder.active["generator"] = result.generation.model
            self.recorder.active["response_transform"] = result.response_transform
            self.recorder.active["answer_constraint"] = result.answer_constraint
            self.recorder.active["generation_policy"] = result.generation_policy
            self.recorder.active["reference_ids"] = list(result.reference_ids)
            return result
        except Exception as exc:
            self.recorder.active["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self.recorder.active["reply_seconds"] = (
                time.perf_counter() - self.recorder.started
            )


class ObservedCapture:
    def __init__(self, capture, recorder):
        self.capture, self.recorder = capture, recorder

    def consider_with_outcome(self, text):
        started = time.perf_counter()
        try:
            outcome = self.capture.consider_with_outcome(text)
            self.recorder.active["capture"] = {
                "status": outcome.status,
                "item": outcome.item.to_dict() if outcome.item else None,
            }
            return outcome
        except Exception as exc:
            self.recorder.active["capture_error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self.recorder.active["capture_seconds"] = time.perf_counter() - started


class ScriptedInput:
    def __init__(self, cases, recorder):
        self.cases, self.recorder = iter(cases), recorder

    def readline(self):
        self.recorder.finish()
        case = next(self.cases, None)
        if case is None:
            return "/exit\n"
        self.recorder.begin(case)
        return case["text"] + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--phase", choices=("learn", "recall"), required=True)
    args = parser.parse_args()
    directory = args.run_directory.resolve()
    config_path = directory / "config.json"
    if args.phase == "learn":
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        config_data = load_config().to_dict()
        config_data["memory"]["database_path"] = str(directory / "memory.sqlite3")
        config_data["memory"]["profile_id"] = "fictional_auto_memory_dry_run"
        config_path.write_text(json.dumps(config_data, indent=2) + "\n", encoding="utf-8")
    if (directory / f"{args.phase}_turns.jsonl").exists():
        raise RuntimeError("refusing to overwrite an existing phase")
    config = load_config(config_path)
    if Path(config.memory.database_path).resolve() != directory / "memory.sqlite3":
        raise RuntimeError("dry run must use its isolated database")
    cases = []
    if args.phase == "learn":
        cases.extend({"id": key, "stage": "disclosure", "text": text,
                      "expected_capture": capture, "expected_kind": kind}
                     for key, text, capture, kind in DISCLOSURES)
        selected_questions = QUESTIONS[:3]
    else:
        selected_questions = QUESTIONS
    cases.extend({"id": "qa_" + key, "stage": "question", "text": text,
                  "expected_answer": answer, "expected_capture": "skipped"}
                 for key, text, answer in selected_questions)
    started = utc_now()
    client = OllamaClient(config.ollama, config.generation)
    store = MemoryStore(
        config.memory.database_path, profile_id=config.memory.profile_id,
        retention_days=config.memory.retention_days,
        embedder=BgeOnnxEmbedder(config.embedding.model_directory,
                                 config.embedding.intra_op_threads),
    )
    before = [item.to_dict() for item in store.list_memories()]
    recorder = Recorder(directory, args.phase, store)
    backend = ObservedBackend(client, recorder)
    output, errors = StringIO(), StringIO()
    router = _RouteReportingRouter(
        ObservedRouter(ConversationRouter(backend, model=config.ollama.small_model), recorder),
        small_model=config.ollama.small_model,
        general_large_model=config.ollama.general_large_model,
        large_model=config.ollama.large_model, output=errors,
    )
    conversation = ObservedConversation(Conversation(
        backend, router=router, retriever=HybridRetriever(store),
        small_model=config.ollama.small_model,
        general_large_model=config.ollama.general_large_model,
        large_model=config.ollama.large_model,
        system_prompt=config.conversation.system_prompt,
        context_length=config.generation.context_length,
        max_output_tokens=config.generation.max_output_tokens,
    ), recorder)
    capture = ObservedCapture(AutomaticMemoryCapture(
        AutomaticMemoryClassifier(backend, model=config.ollama.small_model), store
    ), recorder)
    source_root = Path(__file__).resolve().parents[1] / "src" / "oline_hri"
    source_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(source_root.glob("*.py"))
    }
    try:
        status = _run_chat(
            conversation, memory_store=store, automatic_memory=capture,
            prompt=None, input_stream=ScriptedInput(cases, recorder),
            output=output, errors=errors, show_memory_ids=True,
        )
    finally:
        recorder.finish()
        (directory / f"{args.phase}_stdout.txt").write_text(output.getvalue(), encoding="utf-8")
        (directory / f"{args.phase}_stderr.txt").write_text(errors.getvalue(), encoding="utf-8")
        result = {
            "phase": args.phase, "started_utc": started, "finished_utc": utc_now(),
            "pid": os.getpid(), "architecture": platform.machine(),
            "source_sha256": source_hashes, "config": config.to_dict(),
            "cases": cases, "turns": recorder.turns,
            "memories_before": before,
            "memories_after": [item.to_dict() for item in store.list_memories()],
            "note": "Real interactive text loop; no microphone/STT/TTS. One observed run, not a benchmark.",
        }
        (directory / f"{args.phase}.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        client.unload_all()
    print(f"ARTIFACT {directory / (args.phase + '.json')}", flush=True)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
