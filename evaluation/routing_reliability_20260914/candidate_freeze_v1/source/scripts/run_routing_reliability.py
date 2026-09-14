"""Versioned local routing/answer diagnostic; finite cases are not a guarantee.

Each run owns a fresh directory and an empty memory database. No benchmark
labels enter model prompts. Conversation history passes production admission;
routing-only history is reference context, never evidence for an answer.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from io import StringIO
import os
from pathlib import Path
from time import perf_counter_ns

from oline_hri.config import load_config
from oline_hri.embedding import BgeOnnxEmbedder
from oline_hri.dependency_classifier import DependencyClassifier
from oline_hri.dependency_routing import LearnedSemanticRouter
from oline_hri.memory import MemoryStore
from oline_hri.ollama import ChatMessage, OllamaClient
from oline_hri.reliable_conversation import ReliableConversation, deployment_facts
from oline_hri.reply_guard import is_drafting_followup, is_drafting_request, safe_history_pair
from oline_hri.retrieval import HybridRetriever
from oline_hri.routing import ConversationRouter, references_prior_turn
from oline_hri.semantic_routing import MEMORY_DEPENDENCY_MODES, SemanticRouter


ROOT = Path(__file__).resolve().parents[1]
VERSION = "routing_reliability_v2"


def _write(path, value, *, append=False):
    with path.open("a" if append else "x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _error(exc):
    return {"type": type(exc).__name__, "message": str(exc)}


def load_cases(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases") if isinstance(data, dict) else data
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a nonempty list")
    seen = set()
    for case in cases:
        if (not isinstance(case, dict) or not isinstance(case.get("id"), str)
                or not case["id"].strip() or case["id"] in seen
                or not isinstance(case.get("text"), str) or not case["text"].strip()):
            raise ValueError("cases require unique string IDs and nonempty text")
        seen.add(case["id"])
        modes = case.get("expected_modes")
        if "expected_modes" in case and (not isinstance(modes, list) or not modes or any(
                not isinstance(mode, str) or mode not in MEMORY_DEPENDENCY_MODES for mode in modes)):
            raise ValueError("expected_modes must contain allowed semantic modes")
        if "expected_modes" not in case and "expected_memory" not in case:
            raise ValueError("a case requires expected_modes or expected_memory")
        if "expected_memory" in case and case["expected_memory"] is not None and type(case["expected_memory"]) is not bool:
            raise ValueError("expected_memory must be boolean or null for an unscored case")
        history = case.get("prior_turns", [])
        if not isinstance(history, list):
            raise ValueError("prior_turns must be a list")
        for item in history:
            if (not isinstance(item, dict) or set(item) != {"role", "content"}
                    or not isinstance(item["role"], str) or item["role"] not in {"user", "assistant"}
                    or not isinstance(item["content"], str) or not item["content"].strip()):
                raise ValueError("prior_turns require nonempty user/assistant messages")
    return cases


class RecordingBackend:
    def __init__(self, client, path):
        self.client, self.path, self.case_id, self.calls = client, path, None, []

    @property
    def resident_model(self):
        return self.client.resident_model

    def chat(self, model, messages, **kwargs):
        started = perf_counter_ns()
        row = {"schema_version": VERSION, "case_id": self.case_id, "model": model,
               "messages": [message.to_dict() for message in messages], "options": kwargs}
        try:
            result = self.client.chat(model, messages, **kwargs)
            row.update(status="ok", result=asdict(result))
            return result
        except BaseException as exc:
            row.update(status="error", error=_error(exc))
            raise
        finally:
            row["wall_ns"] = perf_counter_ns() - started
            self.calls.append(row)
            _write(self.path, row, append=True)


class RecordingRouter:
    def __init__(self, delegate):
        self.delegate, self.result = delegate, None

    def route(self, text, *, history=()):
        self.result = self.delegate.route(text, history=history)
        return self.result


class RecordingRetriever:
    def __init__(self, delegate, path):
        self.delegate, self.path, self.case_id = delegate, path, None

    def _call(self, operation, value, **kwargs):
        started = perf_counter_ns()
        row = {"schema_version": VERSION, "case_id": self.case_id, "operation": operation,
               "input": value if isinstance(value, str) else [match.memory.id for match in value],
               "options": kwargs}
        try:
            result = getattr(self.delegate, operation)(value, **kwargs)
            row.update(status="ok", result=result if isinstance(result, bool) else [asdict(match) for match in result])
            return result
        except BaseException as exc:
            row.update(status="error", error=_error(exc))
            raise
        finally:
            row["wall_ns"] = perf_counter_ns() - started
            _write(self.path, row, append=True)

    def retrieve(self, query, *, limit):
        return self._call("retrieve", query, limit=limit)

    def is_current(self, matches):
        return self._call("is_current", matches)

    def disclosure_guard(self, matches):
        return self.delegate.disclosure_guard(matches)


def _admit_history(conversation, history):
    admitted, withheld = [], False
    draft_context = False
    for offset in range(0, len(history), 2):
        pair = history[offset:offset + 2]
        drafting = (len(pair) == 2 and (is_drafting_request(pair[0].content)
                    or draft_context and is_drafting_followup(pair[0].content)))
        valid = (len(pair) == 2 and pair[0].role == "user" and pair[1].role == "assistant"
                 and safe_history_pair(pair[0].content, pair[1].content,
                                       drafting=drafting))
        if not valid or (withheld and references_prior_turn(pair[0].content)):
            admitted, withheld = [], True
            draft_context = False
        else:
            admitted.extend(pair)
            withheld = False
            draft_context = drafting
    conversation._messages.extend(admitted)
    conversation._last_turn_withheld = withheld
    return len(admitted)


def _assess(case, row):
    if row["status"] != "ok":
        return {"label_match": None, "outcome": "error"}
    route = row["route"]
    mode = route.get("dependency", {}).get("mode")
    expected = case.get("expected_modes")
    basis = "semantic_modes" if expected else "retrieval_boolean"
    if expected and mode is None:
        projected = {candidate in {"optional", "required"} for candidate in expected if candidate != "clarify"}
        match = route["decision"]["memory_required"] in projected if projected else None
        basis = "legacy_boolean_projection"
    else:
        match = (mode in expected if expected else
                 route["decision"]["memory_required"] == case["expected_memory"]
                 if case.get("expected_memory") is not None else None)
    reply = row.get("reply")
    if mode == "clarify" or reply and reply["generation_policy"] == "application_clarification":
        outcome = "clarification"
    elif reply:
        outcome = "general_answer" if reply["effective_mode"] == "none" else "personal_or_mixed_answer"
    else:
        outcome = "routed_memory" if route["decision"]["memory_required"] else "routed_general"
    return {"label_match": match, "outcome": outcome, "label_basis": basis}


def run_cases(cases, config, backend, directory, *, stage, policy, retriever=None, classifier=None):
    small, large = config.ollama.small_model, config.ollama.large_model
    if policy == "learned":
        delegate = LearnedSemanticRouter(backend, classifier=classifier, small_model=small, large_model=large)
    else:
        delegate = (SemanticRouter(backend, small_model=small, large_model=large)
                    if policy == "semantic" else ConversationRouter(backend, model=small))
    router, rows = RecordingRouter(delegate), []
    for case in cases:
        backend.case_id, router.result = case["id"], None
        if isinstance(retriever, RecordingRetriever):
            retriever.case_id = case["id"]
        started, checkpoint = perf_counter_ns(), len(backend.calls)
        row = {"schema_version": VERSION, "id": case["id"], "case": case,
               "stage": stage, "policy": policy, "status": "error"}
        try:
            history = tuple(ChatMessage(**item) for item in case.get("prior_turns", []))
            if stage == "routing":
                router.route(case["text"], history=history)
            else:
                conversation = ReliableConversation(
                    backend, router=router, retriever=retriever, small_model=small,
                    large_model=large, general_large_model=config.ollama.general_large_model,
                    system_prompt=config.conversation.system_prompt,
                    context_length=config.generation.context_length,
                    max_output_tokens=config.generation.max_output_tokens,
                    runtime_facts=deployment_facts(config),
                )
                row["admitted_history_messages"] = _admit_history(conversation, history)
                reply = conversation.send(case["text"])
                row["reply"] = asdict(reply)
                # Exercise the production output authorization boundary. Keep
                # only the short text write inside it, never artifact fsync.
                output = StringIO()
                with conversation.disclosure_guard(reply):
                    output.write(reply.response.speech)
                row["delivered_text"] = output.getvalue()
            row["status"] = "ok"
        except BaseException as exc:
            row["error"] = _error(exc)
            if not isinstance(exc, Exception):
                raise
        finally:
            row.update(wall_ns=perf_counter_ns() - started,
                       route=asdict(router.result) if router.result else None,
                       calls=backend.calls[checkpoint:])
            row["diagnostic"] = _assess(case, row)
            _write(directory / "observations.jsonl", row, append=True)
            rows.append(row)
        print(f"{case['id']}: {row['diagnostic']['outcome']} ({row['wall_ns'] / 1e9:.2f}s)", flush=True)
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--stage", choices=("routing", "conversation"), default="routing")
    parser.add_argument("--policy", choices=("learned", "semantic", "legacy"), default="learned")
    args = parser.parse_args(argv)
    if args.stage == "conversation" and args.policy == "legacy":
        parser.error("legacy policy is supported only for routing diagnostics")
    cases, config = load_cases(args.cases), load_config()
    directory = args.output_dir.absolute()
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    original_config = config.to_dict()
    config = replace(config, memory=replace(config.memory, database_path=str(directory / "memory.sqlite3")))
    paths = [*sorted((ROOT / "src/oline_hri").glob("*.py")),
             *sorted((ROOT / "src/oline_hri").glob("*.json")), Path(__file__).resolve()]
    _write(directory / "metadata.json", {
        "schema_version": VERSION, "created_at": datetime.now(timezone.utc).isoformat(),
        "stage": args.stage, "policy": args.policy, "case_count": len(cases),
        "cases_sha256": sha256(args.cases.read_bytes()).hexdigest(),
        "config_sha256": sha256(json.dumps(original_config, sort_keys=True).encode()).hexdigest(),
        "config": config.to_dict(), "retain_large_model": True,
        "source_sha256": {str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest() for path in paths},
        "scope": "Single-pass text diagnostic, empty isolated personal store; no speech or accuracy guarantee. "
                 "Legacy boolean scoring treats optional/required retrieval as true and clarify-only labels as unscored. "
                 "Answers need human review.",
    })
    rows, client, failure, cleanup = [], None, None, None
    started = perf_counter_ns()
    try:
        client = OllamaClient(config.ollama, config.generation, retain_large_model=True)
        backend = RecordingBackend(client, directory / "model_calls.jsonl")
        retriever, classifier = None, None
        if args.stage == "conversation" or args.policy == "learned":
            embedder = BgeOnnxEmbedder(config.embedding.model_directory, config.embedding.intra_op_threads)
        if args.policy == "learned":
            classifier = DependencyClassifier(embedder)
        if args.stage == "conversation":
            store = MemoryStore(config.memory.database_path, profile_id=config.memory.profile_id,
                                embedder=embedder, retention_days=config.memory.retention_days)
            store.list_memories()
            retriever = RecordingRetriever(HybridRetriever(store), directory / "retrieval_calls.jsonl")
        rows = run_cases(cases, config, backend, directory, stage=args.stage,
                         policy=args.policy, retriever=retriever, classifier=classifier)
    except BaseException as exc:
        failure = _error(exc)
    finally:
        if client is not None:
            try:
                client.unload_all()
            except BaseException as exc:
                cleanup = _error(exc)
        # Include rows already durably written if execution was interrupted.
        if (directory / "observations.jsonl").exists():
            rows = [json.loads(line) for line in (directory / "observations.jsonl").read_text().splitlines()]
        _write(directory / "summary.json", {
            "schema_version": VERSION, "case_count": len(cases), "completed": len(rows),
            "outcomes": dict(Counter(row["diagnostic"]["outcome"] for row in rows)),
            "label_matches": sum(row["diagnostic"]["label_match"] is True for row in rows),
            "label_mismatches": sum(row["diagnostic"]["label_match"] is False for row in rows),
            "failure": failure, "cleanup_error": cleanup, "wall_ns": perf_counter_ns() - started,
            "interpretation": "Clarifications and errors are separate from delivered answers; label agreement is not answer correctness.",
        })
    return 1 if failure or cleanup or any(row["status"] != "ok" for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
