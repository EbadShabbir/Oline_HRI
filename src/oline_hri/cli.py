"""Command-line entry point for Oline HRI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import sys
from typing import Optional, Sequence, TextIO

from . import __version__
from .config import ConfigError, load_config
from .conversation import Conversation, ConversationError, ConversationReply
from .embedding import BgeOnnxEmbedder, EmbeddingError
from .memory import (
    MEMORY_KINDS,
    MEMORY_SENSITIVITIES,
    MemoryItem,
    MemoryStore,
    MemoryStoreError,
    MemoryValidationError,
)
from .ollama import OllamaClient, OllamaError
from .retrieval import HybridRetriever
from .routing import ConversationRouter, RoutingError, RoutingResult


class _RouteReportingRouter:
    """Report validated route decisions without exposing conversation text."""

    def __init__(
        self,
        router: ConversationRouter,
        *,
        small_model: str,
        large_model: str,
        output: TextIO,
    ) -> None:
        self._router = router
        self._small_model = small_model
        self._large_model = large_model
        self._output = output

    def route(self, user_text, *, history=()) -> RoutingResult:
        result = self._router.route(user_text, history=history)
        decision = result.decision
        selected_model = (
            self._large_model
            if decision.model_size == "large"
            else self._small_model
        )
        memory_required = "true" if decision.memory_required else "false"
        print(
            "route> "
            f"model_size={decision.model_size} "
            f"selected_generator={selected_model} "
            f"memory_required={memory_required}",
            file=self._output,
            flush=True,
        )
        return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oline-hri",
        description="Offline personalized conversational robot",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="configuration JSON path (defaults to config/default.json)",
    )

    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("info", help="show local application information")

    config_parser = commands.add_parser("config", help="inspect configuration")
    config_commands = config_parser.add_subparsers(dest="config_command", required=True)
    config_commands.add_parser("check", help="validate configuration")
    config_commands.add_parser("show", help="print validated configuration")

    chat_parser = commands.add_parser(
        "chat", help="chat through the local memory and model router"
    )
    chat_parser.add_argument(
        "--prompt",
        help="send one prompt and exit; omit for an interactive session",
    )
    chat_parser.add_argument(
        "--show-route",
        action="store_true",
        help="show each validated routing decision before generation",
    )
    chat_parser.add_argument(
        "--show-memory-ids",
        action="store_true",
        help=(
            "show retrieved, supplied, and model-used memory IDs after each "
            "validated reply"
        ),
    )

    memory_parser = commands.add_parser(
        "memory", help="manage explicit local personal memories"
    )
    memory_commands = memory_parser.add_subparsers(
        dest="memory_command", required=True
    )

    remember_parser = memory_commands.add_parser(
        "remember", help="store one explicitly provided memory"
    )
    remember_parser.add_argument("--kind", choices=MEMORY_KINDS, required=True)
    remember_parser.add_argument(
        "--text", help="canonical memory text; omit to enter it privately"
    )
    remember_parser.add_argument(
        "--sensitivity", choices=MEMORY_SENSITIVITIES, default="normal"
    )
    remember_parser.add_argument(
        "--importance", type=int, choices=range(1, 6), default=3
    )
    remember_parser.add_argument("--event-time", help="timezone-aware ISO-8601")
    remember_parser.add_argument("--valid-until", help="timezone-aware ISO-8601")
    remember_parser.add_argument(
        "--retention-until", help="timezone-aware ISO-8601"
    )

    list_parser = memory_commands.add_parser("list", help="list saved memories")
    list_parser.add_argument(
        "--all",
        action="store_true",
        dest="include_inactive",
        help="include inactive records",
    )

    search_parser = memory_commands.add_parser(
        "search", help="search active memories using literal keywords"
    )
    search_parser.add_argument(
        "--query", help="keyword query; omit to enter it privately"
    )
    search_parser.add_argument("--limit", type=int, default=5)

    semantic_search_parser = memory_commands.add_parser(
        "semantic-search", help="search active memories by semantic similarity"
    )
    semantic_search_parser.add_argument(
        "--query", help="semantic query; omit to enter it privately"
    )
    semantic_search_parser.add_argument("--limit", type=int, default=5)

    hybrid_search_parser = memory_commands.add_parser(
        "hybrid-search",
        help="search active memories using fused keyword and semantic ranks",
    )
    hybrid_search_parser.add_argument(
        "--query", help="hybrid query; omit to enter it privately"
    )
    hybrid_search_parser.add_argument("--limit", type=int, default=3)

    memory_commands.add_parser(
        "rebuild-index", help="rebuild the derived keyword index"
    )
    memory_commands.add_parser(
        "rebuild-embeddings", help="rebuild the derived semantic index"
    )
    memory_commands.add_parser(
        "embedding-status", help="show semantic-index coverage"
    )

    correct_parser = memory_commands.add_parser(
        "correct", help="replace one active memory by exact ID"
    )
    correct_parser.add_argument("memory_id")
    correct_parser.add_argument(
        "--text", help="corrected canonical text; omit to enter it privately"
    )

    forget_parser = memory_commands.add_parser(
        "forget", help="forget an active memory by exact ID"
    )
    forget_parser.add_argument("memory_id")
    forget_parser.add_argument(
        "--yes", action="store_true", help="skip the confirmation prompt"
    )
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    stdin: Optional[TextIO] = None,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    """Run the CLI and return a process exit code."""

    output = stdout if stdout is not None else sys.stdout
    errors = stderr if stderr is not None else sys.stderr
    input_stream = stdin if stdin is not None else sys.stdin
    args = build_parser().parse_args(argv)

    if args.command == "info":
        print(f"Oline HRI {__version__}", file=output)
        print(f"Python {platform.python_version()}", file=output)
        print(f"Architecture {platform.machine()}", file=output)
        return 0

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=errors)
        return 2

    if args.command == "config":
        if args.config_command == "check":
            print(f"configuration valid (schema {config.schema_version})", file=output)
            return 0
        if args.config_command == "show":
            print(json.dumps(config.to_dict(), indent=2, sort_keys=True), file=output)
            return 0

    if args.command == "chat":
        try:
            client = OllamaClient(config.ollama, config.generation)
            embedder = BgeOnnxEmbedder(
                config.embedding.model_directory,
                config.embedding.intra_op_threads,
            )
            store = MemoryStore(
                config.memory.database_path,
                profile_id=config.memory.profile_id,
                embedder=embedder,
            )
            router = ConversationRouter(
                client, model=config.ollama.small_model
            )
            if args.show_route:
                router = _RouteReportingRouter(
                    router,
                    small_model=config.ollama.small_model,
                    large_model=config.ollama.large_model,
                    output=errors,
                )
            conversation = Conversation(
                client,
                router=router,
                retriever=HybridRetriever(store),
                small_model=config.ollama.small_model,
                large_model=config.ollama.large_model,
                system_prompt=config.conversation.system_prompt,
                context_length=config.generation.context_length,
                max_output_tokens=config.generation.max_output_tokens,
            )
            return _run_chat(
                conversation,
                prompt=args.prompt,
                input_stream=input_stream,
                output=output,
                errors=errors,
                show_memory_ids=args.show_memory_ids,
            )
        except (
            ConversationError,
            EmbeddingError,
            MemoryStoreError,
            OllamaError,
            RoutingError,
            ValueError,
        ):
            print("chat error: request could not be completed safely", file=errors)
            return 3

    if args.command == "memory":
        try:
            embedder = None
            if args.memory_command in {
                "remember",
                "correct",
                "hybrid-search",
                "semantic-search",
                "rebuild-embeddings",
                "embedding-status",
            }:
                embedder = BgeOnnxEmbedder(
                    config.embedding.model_directory,
                    config.embedding.intra_op_threads,
                )
            store = MemoryStore(
                config.memory.database_path,
                profile_id=config.memory.profile_id,
                embedder=embedder,
            )
            return _run_memory(
                args,
                store,
                input_stream=input_stream,
                output=output,
            )
        except (MemoryStoreError, EmbeddingError) as exc:
            print(f"memory error: {exc}", file=errors)
            return 4

    print("unsupported command", file=errors)
    return 2


def _run_chat(
    conversation: Conversation,
    *,
    prompt: Optional[str],
    input_stream: TextIO,
    output: TextIO,
    errors: TextIO,
    show_memory_ids: bool,
) -> int:
    if prompt is not None:
        reply = conversation.send(prompt)
        if show_memory_ids:
            _report_memory_ids(reply, errors)
        print(reply.response.speech, file=output)
        return 0

    print("Offline text chat", file=output)
    print("Commands: /clear, /exit", file=output)
    while True:
        print("you> ", end="", file=output, flush=True)
        line = input_stream.readline()
        if line == "":
            print(file=output)
            return 0

        user_text = line.strip()
        if not user_text:
            continue
        command = user_text.lower()
        if command in {"/exit", "/quit"}:
            return 0
        if command == "/clear":
            conversation.clear()
            print("conversation cleared", file=output)
            continue

        try:
            reply = conversation.send(user_text)
        except (
            ConversationError,
            EmbeddingError,
            MemoryStoreError,
            OllamaError,
            RoutingError,
            ValueError,
        ):
            print(
                "chat error: request could not be completed safely",
                file=errors,
            )
            continue
        if show_memory_ids:
            _report_memory_ids(reply, errors)
        print(f"robot> {reply.response.speech}", file=output)


def _report_memory_ids(reply: ConversationReply, output: TextIO) -> None:
    """Print only opaque IDs from a fully validated successful turn."""

    payload = json.dumps(
        reply.memory_diagnostics.to_dict(),
        ensure_ascii=True,
        separators=(",", ":"),
    )
    print(f"memory> {payload}", file=output, flush=True)


def _run_memory(
    args: argparse.Namespace,
    store: MemoryStore,
    *,
    input_stream: TextIO,
    output: TextIO,
) -> int:
    if args.memory_command == "remember":
        text = _memory_text(
            args.text,
            prompt="memory text> ",
            input_stream=input_stream,
            output=output,
        )
        item = store.remember(
            text,
            kind=args.kind,
            sensitivity=args.sensitivity,
            importance=args.importance,
            event_time=args.event_time,
            valid_until=args.valid_until,
            retention_until=args.retention_until,
        )
        print(f"remembered {item.id}", file=output)
        print(f"text: {item.canonical_text}", file=output)
        return 0

    if args.memory_command == "list":
        memories = store.list_memories(include_inactive=args.include_inactive)
        if not memories:
            label = "memories" if args.include_inactive else "active memories"
            print(f"no {label}", file=output)
            return 0
        print("ID\tSTATUS\tKIND\tSENSITIVITY\tCREATED\tTEXT", file=output)
        for item in memories:
            _print_memory(item, output)
        return 0

    if args.memory_command == "search":
        query = _memory_text(
            args.query,
            prompt="search query> ",
            missing_message="no search query was provided",
            input_stream=input_stream,
            output=output,
        )
        matches = store.search_keywords(query, limit=args.limit)
        if not matches:
            print("no matching active memories", file=output)
            return 0
        print(
            "BM25_RANK\tID\tSTATUS\tKIND\tSENSITIVITY\tCREATED\tTEXT",
            file=output,
        )
        for match in matches:
            print(f"{match.rank:.8g}\t", end="", file=output)
            _print_memory(match.memory, output)
        return 0

    if args.memory_command == "semantic-search":
        query = _memory_text(
            args.query,
            prompt="semantic query> ",
            missing_message="no semantic search query was provided",
            input_stream=input_stream,
            output=output,
        )
        matches = store.search_semantic(query, limit=args.limit)
        if not matches:
            print("no semantically matching active memories", file=output)
            return 0
        print(
            "COSINE_SCORE\tID\tSTATUS\tKIND\tSENSITIVITY\tCREATED\tTEXT",
            file=output,
        )
        for match in matches:
            print(f"{match.score:.8g}\t", end="", file=output)
            _print_memory(match.memory, output)
        return 0

    if args.memory_command == "hybrid-search":
        query = _memory_text(
            args.query,
            prompt="hybrid query> ",
            missing_message="no hybrid search query was provided",
            input_stream=input_stream,
            output=output,
        )
        matches = HybridRetriever(store).retrieve(query, limit=args.limit)
        if not matches:
            print("no hybrid matching active memories", file=output)
            return 0
        print(
            "FUSED_SCORE\tKEYWORD_POS\tSEMANTIC_POS\tID\tSTATUS\tKIND\t"
            "SENSITIVITY\tCREATED\tTEXT",
            file=output,
        )
        for match in matches:
            keyword_position = (
                "-" if match.keyword_position is None else match.keyword_position
            )
            semantic_position = (
                "-" if match.semantic_position is None else match.semantic_position
            )
            print(
                f"{match.fused_score:.8g}\t{keyword_position}\t"
                f"{semantic_position}\t",
                end="",
                file=output,
            )
            _print_memory(match.memory, output)
        return 0

    if args.memory_command == "rebuild-index":
        store.rebuild_keyword_index()
        print("keyword index rebuilt", file=output)
        return 0

    if args.memory_command == "rebuild-embeddings":
        status = store.rebuild_embeddings()
        print(
            f"embedding index rebuilt; indexed {status.indexed} "
            f"of {status.eligible} eligible memories",
            file=output,
        )
        return 0

    if args.memory_command == "embedding-status":
        status = store.embedding_index_status()
        print("ELIGIBLE\tINDEXED\tMISSING\tINVALID", file=output)
        print(
            f"{status.eligible}\t{status.indexed}\t{status.missing}\t{status.invalid}",
            file=output,
        )
        return 0

    if args.memory_command == "correct":
        text = _memory_text(
            args.text,
            prompt="corrected memory text> ",
            missing_message="no corrected memory text was provided",
            input_stream=input_stream,
            output=output,
        )
        replacement = store.correct(args.memory_id, text)
        print(f"corrected {args.memory_id} -> {replacement.id}", file=output)
        print(f"text: {replacement.canonical_text}", file=output)
        return 0

    if args.memory_command == "forget":
        if not args.yes:
            print(
                f"Forget {args.memory_id} and its earlier corrections? [y/N] ",
                end="",
                file=output,
                flush=True,
            )
            answer = input_stream.readline().strip().lower()
            if answer not in {"y", "yes"}:
                print("forget canceled", file=output)
                return 0
        forgotten = store.forget(args.memory_id)
        print(
            f"forgotten {args.memory_id}; removed {len(forgotten)} revision(s)",
            file=output,
        )
        return 0

    raise MemoryValidationError("unsupported memory command")


def _memory_text(
    value: Optional[str],
    *,
    prompt: str,
    missing_message: str = "no memory text was provided",
    input_stream: TextIO,
    output: TextIO,
) -> str:
    if value is not None:
        return value
    print(prompt, end="", file=output, flush=True)
    line = input_stream.readline()
    if line == "":
        raise MemoryValidationError(missing_message)
    return line.rstrip("\r\n")


def _print_memory(item: MemoryItem, output: TextIO) -> None:
    print(
        "\t".join(
            (
                item.id,
                item.status,
                item.kind,
                item.sensitivity,
                item.created_at,
                item.canonical_text,
            )
        ),
        file=output,
    )
