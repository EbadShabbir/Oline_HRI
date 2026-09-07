from io import StringIO
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from oline_hri.cli import main
from oline_hri.config import load_config
from oline_hri.embedding import (
    EMBEDDING_DIMENSION,
    MODEL_ID,
    MODEL_REVISION,
    EmbeddingError,
)
from oline_hri.memory import MemoryStore
from oline_hri.ollama import ChatResult, OllamaError
from oline_hri.response import RobotResponse
from oline_hri.routing import RouteDecision, RoutingResult


def chat_result(content: str = "Hello from the robot.") -> ChatResult:
    return ChatResult(
        model="qwen3:0.6b",
        content=RobotResponse(content, "NO_ACTION", ()).to_json(),
        done_reason="stop",
        total_duration_ns=1,
        load_duration_ns=0,
        prompt_eval_count=1,
        eval_count=1,
        eval_duration_ns=1,
    )


def routing_result(
    *, memory_required: bool = False, model_size: str = "small"
) -> RoutingResult:
    memory_required_generation = ChatResult(
        model="qwen3:0.6b",
        content=json.dumps(
            {"memory_required": memory_required}, separators=(",", ":")
        ),
        done_reason="stop",
        total_duration_ns=1,
        load_duration_ns=0,
        prompt_eval_count=1,
        eval_count=1,
        eval_duration_ns=1,
    )
    model_size_generation = ChatResult(
        model="qwen3:0.6b",
        content=json.dumps({"model_size": model_size}, separators=(",", ":")),
        done_reason="stop",
        total_duration_ns=1,
        load_duration_ns=0,
        prompt_eval_count=1,
        eval_count=1,
        eval_duration_ns=1,
    )
    return RoutingResult(
        decision=RouteDecision(memory_required, model_size),
        memory_required_generation=memory_required_generation,
        model_size_generation=model_size_generation,
    )


def routing_generations(
    *, memory_required: bool = False, model_size: str = "small"
) -> tuple[ChatResult, ChatResult]:
    result = routing_result(
        memory_required=memory_required, model_size=model_size
    )
    return (
        result.memory_required_generation,
        result.model_size_generation,
    )


def authorized_chat_result(
    content: str,
    memory_ids: tuple[str, ...],
    *,
    model: str = "qwen3:0.6b",
) -> ChatResult:
    return ChatResult(
        model=model,
        content=json.dumps(
            {
                "speech": content,
                "gesture_id": "NO_ACTION",
                "memory_used": list(memory_ids),
            },
            separators=(",", ":"),
        ),
        done_reason="stop",
        total_duration_ns=1,
        load_duration_ns=0,
        prompt_eval_count=1,
        eval_count=1,
        eval_duration_ns=1,
    )


def memory_config(directory: str, *, profile_id: str = "test_user") -> Path:
    data = load_config().to_dict()
    data["memory"]["database_path"] = str(Path(directory) / "memory.sqlite3")
    data["memory"]["profile_id"] = profile_id
    path = Path(directory) / f"{profile_id}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class DeterministicEmbedder:
    """Small in-process embedding fake; CLI tests never load an ONNX model."""

    model_id = MODEL_ID
    model_revision = MODEL_REVISION
    dimension = EMBEDDING_DIMENSION

    def __init__(self, model_directory="/unused", intra_op_threads=2) -> None:
        self.model_directory = model_directory
        self.intra_op_threads = intra_op_threads

    def embed_passages(self, passages):
        return np.stack([self._vector(text) for text in passages]).astype(
            np.float32, copy=False
        )

    def embed_query(self, query):
        return self._vector(query)

    @classmethod
    def _vector(cls, text):
        vector = np.zeros(cls.dimension, dtype=np.float32)
        for token in text.casefold().split():
            digest = sha256(token.strip(".,!?'\"").encode("utf-8")).digest()
            vector[int.from_bytes(digest[:2], "big") % cls.dimension] += 1.0
        norm = np.linalg.norm(vector)
        if norm == 0.0:
            vector[0] = 1.0
            return vector
        return vector / norm


class FailingQueryEmbedder(DeterministicEmbedder):
    def embed_query(self, query):
        raise EmbeddingError("embedding inference failed")


@patch("oline_hri.cli.BgeOnnxEmbedder", DeterministicEmbedder)
class CliTests(unittest.TestCase):
    def test_info(self) -> None:
        output = StringIO()

        result = main(["info"], stdout=output)

        self.assertEqual(result, 0)
        self.assertIn("Oline HRI 0.1.0", output.getvalue())

    def test_config_check(self) -> None:
        output = StringIO()

        result = main(["config", "check"], stdout=output)

        self.assertEqual(result, 0)
        self.assertIn("configuration valid", output.getvalue())

    def test_config_show_is_json(self) -> None:
        output = StringIO()

        result = main(["config", "show"], stdout=output)
        data = json.loads(output.getvalue())

        self.assertEqual(result, 0)
        self.assertEqual(data["ollama"]["small_model"], "qwen3:0.6b")

    def test_invalid_config_returns_nonzero(self) -> None:
        errors = StringIO()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("{}", encoding="utf-8")

            result = main(
                ["--config", str(path), "config", "check"], stderr=errors
            )

        self.assertEqual(result, 2)
        self.assertIn("configuration error", errors.getvalue())

    @patch("oline_hri.cli.OllamaClient")
    def test_one_shot_chat(self, client_class) -> None:
        client_class.return_value.chat.return_value = chat_result()
        output = StringIO()
        errors = StringIO()

        with patch("oline_hri.cli.ConversationRouter") as router_class:
            router_class.return_value.route.return_value = routing_result()
            result = main(
                ["chat", "--show-memory-ids", "--prompt", "Hello"],
                stdout=output,
                stderr=errors,
            )

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue().strip(), "Hello from the robot.")
        self.assertEqual(
            errors.getvalue(),
            'memory> {"retrieved_ids":[],"supplied_ids":[],'
            '"model_used_ids":[]}\n',
        )
        model, messages = client_class.return_value.chat.call_args.args
        self.assertEqual(model, "qwen3:0.6b")
        self.assertEqual(messages[-1].content, "Hello")
        self.assertIn(
            "response_format", client_class.return_value.chat.call_args.kwargs
        )

    @patch("oline_hri.cli.OllamaClient")
    def test_interactive_chat(self, client_class) -> None:
        client_class.return_value.chat.return_value = chat_result("Hi!")
        output = StringIO()

        with patch("oline_hri.cli.ConversationRouter") as router_class:
            router_class.return_value.route.return_value = routing_result()
            result = main(
                ["chat"],
                stdin=StringIO("Hello\n/exit\n"),
                stdout=output,
            )

        self.assertEqual(result, 0)
        self.assertIn("robot> Hi!", output.getvalue())

    @patch("oline_hri.cli.OllamaClient")
    def test_show_route_reports_decision_before_generation(
        self, client_class
    ) -> None:
        output = StringIO()
        errors = StringIO()
        calls = iter(
            (
                *routing_generations(model_size="large"),
                authorized_chat_result(
                    "Routed answer.", (), model="qwen3:4b"
                ),
            )
        )

        def respond(*args, **kwargs):
            result = next(calls)
            if result.model == "qwen3:4b":
                self.assertEqual(
                    errors.getvalue(),
                    "route> model_size=large selected_generator=qwen3:4b "
                    "memory_required=false\n",
                )
            return result

        client_class.return_value.chat.side_effect = respond

        result = main(
            [
                "chat",
                "--show-route",
                "--prompt",
                "Compare three robot architectures.",
            ],
            stdout=output,
            stderr=errors,
        )

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), "Routed answer.\n")
        self.assertEqual(
            errors.getvalue(),
            "route> model_size=large selected_generator=qwen3:4b "
            "memory_required=false\n",
        )

    @patch("oline_hri.cli.OllamaClient")
    def test_route_and_memory_id_diagnostics_have_stable_order(
        self, client_class
    ) -> None:
        client_class.return_value.chat.side_effect = (
            *routing_generations(model_size="large"),
            authorized_chat_result(
                "Routed answer.", (), model="qwen3:4b"
            ),
        )
        output = StringIO()
        errors = StringIO()

        result = main(
            [
                "chat",
                "--show-route",
                "--show-memory-ids",
                "--prompt",
                "Compare three robot architectures.",
            ],
            stdout=output,
            stderr=errors,
        )

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), "Routed answer.\n")
        self.assertEqual(
            errors.getvalue(),
            "route> model_size=large selected_generator=qwen3:4b "
            "memory_required=false\n"
            'memory> {"retrieved_ids":[],"supplied_ids":[],'
            '"model_used_ids":[]}\n',
        )

    @patch("oline_hri.cli.OllamaClient")
    def test_chat_error_returns_nonzero(self, client_class) -> None:
        client_class.return_value.chat.side_effect = OllamaError("offline")
        errors = StringIO()

        with patch("oline_hri.cli.ConversationRouter") as router_class:
            router_class.return_value.route.return_value = routing_result()
            result = main(
                ["chat", "--prompt", "Hello"],
                stdout=StringIO(),
                stderr=errors,
            )

        self.assertEqual(result, 3)
        self.assertEqual(
            errors.getvalue(),
            "chat error: request could not be completed safely\n",
        )
        self.assertNotIn("offline", errors.getvalue())

    @patch("oline_hri.cli.OllamaClient")
    def test_invalid_structured_chat_prints_no_model_output(self, client_class) -> None:
        client_class.return_value.chat.return_value = ChatResult(
            model="qwen3:0.6b",
            content='{"speech":"I waved.","gesture_id":"WAVE","memory_used":[]}',
            done_reason="stop",
            total_duration_ns=1,
            load_duration_ns=0,
            prompt_eval_count=1,
            eval_count=1,
            eval_duration_ns=1,
        )
        output = StringIO()
        errors = StringIO()

        with patch("oline_hri.cli.ConversationRouter") as router_class:
            router_class.return_value.route.return_value = routing_result()
            result = main(
                ["chat", "--show-memory-ids", "--prompt", "Wave"],
                stdout=output,
                stderr=errors,
            )

        self.assertEqual(result, 3)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(
            errors.getvalue(),
            "chat error: request could not be completed safely\n",
        )

    @patch("oline_hri.cli.OllamaClient")
    def test_chat_runs_router_then_selected_small_or_large_model(
        self, client_class
    ) -> None:
        for model_size, selected_model in (
            ("small", "qwen3:0.6b"),
            ("large", "qwen3:4b"),
        ):
            with self.subTest(model_size=model_size):
                client = client_class.return_value
                client.reset_mock()
                client.chat.side_effect = [
                    *routing_generations(model_size=model_size),
                    authorized_chat_result(
                        "Routed answer.", (), model=selected_model
                    ),
                ]
                output = StringIO()

                result = main(
                    ["chat", "--prompt", "Please answer this."],
                    stdout=output,
                )

                self.assertEqual(result, 0)
                self.assertEqual(output.getvalue(), "Routed answer.\n")
                self.assertEqual(client.chat.call_count, 3)
                self.assertEqual(
                    client.chat.call_args_list[0].args[0], "qwen3:0.6b"
                )
                self.assertEqual(
                    client.chat.call_args_list[1].args[0], "qwen3:0.6b"
                )
                self.assertEqual(
                    client.chat.call_args_list[2].args[0], selected_model
                )
                memory_route_format = client.chat.call_args_list[0].kwargs[
                    "response_format"
                ]
                model_route_format = client.chat.call_args_list[1].kwargs[
                    "response_format"
                ]
                response_format = client.chat.call_args_list[2].kwargs[
                    "response_format"
                ]
                self.assertEqual(
                    set(memory_route_format["properties"]),
                    {"memory_required"},
                )
                self.assertEqual(
                    set(model_route_format["properties"]),
                    {"model_size"},
                )
                self.assertEqual(
                    response_format["properties"]["memory_used"]["maxItems"],
                    0,
                )

    @patch("oline_hri.cli.OllamaClient")
    def test_chat_retrieves_memory_and_authorizes_only_injected_ids(
        self, client_class
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            remembered = StringIO()
            result = main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "remember",
                    "--kind",
                    "preference",
                    "--text",
                    "User prefers jasmine tea without sugar.",
                ],
                stdout=remembered,
            )
            self.assertEqual(result, 0)
            memory_id = remembered.getvalue().splitlines()[0].split()[1]
            client = client_class.return_value
            client.chat.side_effect = [
                *routing_generations(memory_required=True),
                authorized_chat_result(
                    "You prefer jasmine tea without sugar.",
                    (memory_id,),
                ),
            ]
            output = StringIO()
            errors = StringIO()

            result = main(
                [
                    "--config",
                    str(config_path),
                    "chat",
                    "--show-memory-ids",
                    "--prompt",
                    "How do I take my tea?",
                ],
                stdout=output,
                stderr=errors,
            )

        self.assertEqual(result, 0)
        self.assertEqual(
            output.getvalue(), "You prefer jasmine tea without sugar.\n"
        )
        self.assertEqual(
            errors.getvalue(),
            "memory> "
            + json.dumps(
                {
                    "retrieved_ids": [memory_id],
                    "supplied_ids": [memory_id],
                    "model_used_ids": [memory_id],
                },
                separators=(",", ":"),
            )
            + "\n",
        )
        self.assertNotIn("jasmine tea", errors.getvalue())
        self.assertNotIn("How do I take my tea?", errors.getvalue())
        self.assertEqual(client.chat.call_count, 3)
        _, generation_messages = client.chat.call_args_list[2].args
        context_messages = [
            message
            for message in generation_messages
            if "PERSONAL_MEMORY_DATA=" in message.content
        ]
        self.assertEqual(len(context_messages), 1)
        self.assertIn(memory_id, context_messages[0].content)
        self.assertIn("jasmine tea", context_messages[0].content)
        response_format = client.chat.call_args_list[2].kwargs[
            "response_format"
        ]
        self.assertEqual(
            response_format["properties"]["memory_used"]["items"]["enum"],
            [memory_id],
        )

    @patch("oline_hri.cli.OllamaClient")
    def test_chat_fails_closed_when_embedding_index_is_incomplete(
        self, client_class
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            config = load_config(config_path)
            MemoryStore(
                config.memory.database_path,
                profile_id=config.memory.profile_id,
            ).remember("User prefers mint tea.", kind="preference")
            client_class.return_value.chat.side_effect = routing_generations(
                memory_required=True
            )
            errors = StringIO()

            result = main(
                [
                    "--config",
                    str(config_path),
                    "chat",
                    "--prompt",
                    "What tea do I prefer?",
                ],
                stdout=StringIO(),
                stderr=errors,
            )

        self.assertEqual(result, 3)
        self.assertEqual(
            errors.getvalue(),
            "chat error: request could not be completed safely\n",
        )
        self.assertEqual(client_class.return_value.chat.call_count, 2)

    @patch("oline_hri.cli.OllamaClient")
    def test_router_failure_is_sanitized_at_cli_boundary(
        self, client_class
    ) -> None:
        client_class.return_value.chat.side_effect = OllamaError(
            "private prompt echoed by backend"
        )
        errors = StringIO()

        result = main(
            ["chat", "--prompt", "private prompt"],
            stdout=StringIO(),
            stderr=errors,
        )

        self.assertEqual(result, 3)
        self.assertEqual(
            errors.getvalue(),
            "chat error: request could not be completed safely\n",
        )
        self.assertNotIn("private prompt echoed", errors.getvalue())

    def test_memory_cli_remember_list_correct_and_forget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            remembered_output = StringIO()
            result = main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "remember",
                    "--kind",
                    "preference",
                    "--text",
                    "User prefers mint tea.",
                ],
                stdout=remembered_output,
            )
            first_id = remembered_output.getvalue().splitlines()[0].split()[1]

            self.assertEqual(result, 0)
            self.assertTrue(first_id.startswith("mem_"))

            listed_output = StringIO()
            result = main(
                ["--config", str(config_path), "memory", "list"],
                stdout=listed_output,
            )
            self.assertEqual(result, 0)
            self.assertIn(first_id, listed_output.getvalue())
            self.assertIn("User prefers mint tea.", listed_output.getvalue())

            search_output = StringIO()
            result = main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "search",
                    "--query",
                    "mint tea",
                ],
                stdout=search_output,
            )
            self.assertEqual(result, 0)
            self.assertIn("BM25_RANK", search_output.getvalue())
            self.assertIn(first_id, search_output.getvalue())

            corrected_output = StringIO()
            result = main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "correct",
                    first_id,
                    "--text",
                    "User prefers ginger tea.",
                ],
                stdout=corrected_output,
            )
            correction_line = corrected_output.getvalue().splitlines()[0]
            replacement_id = correction_line.split(" -> ")[1]
            self.assertEqual(result, 0)
            self.assertNotEqual(first_id, replacement_id)

            all_output = StringIO()
            result = main(
                ["--config", str(config_path), "memory", "list", "--all"],
                stdout=all_output,
            )
            self.assertEqual(result, 0)
            self.assertIn(first_id, all_output.getvalue())
            self.assertIn("superseded", all_output.getvalue())
            self.assertIn(replacement_id, all_output.getvalue())

            old_search = StringIO()
            result = main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "search",
                    "--query",
                    "mint",
                ],
                stdout=old_search,
            )
            self.assertEqual(result, 0)
            self.assertEqual(
                old_search.getvalue().strip(), "no matching active memories"
            )

            rebuilt_output = StringIO()
            result = main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "rebuild-index",
                ],
                stdout=rebuilt_output,
            )
            self.assertEqual(result, 0)
            self.assertEqual(
                rebuilt_output.getvalue().strip(), "keyword index rebuilt"
            )

            forgotten_output = StringIO()
            result = main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "forget",
                    replacement_id,
                    "--yes",
                ],
                stdout=forgotten_output,
            )
            self.assertEqual(result, 0)
            self.assertIn("removed 2 revision(s)", forgotten_output.getvalue())

            empty_output = StringIO()
            result = main(
                ["--config", str(config_path), "memory", "list", "--all"],
                stdout=empty_output,
            )
            self.assertEqual(result, 0)
            self.assertEqual(empty_output.getvalue().strip(), "no memories")

    @patch("oline_hri.cli.OllamaClient")
    def test_memory_input_is_interactive_and_does_not_call_ollama(
        self, client_class
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            output = StringIO()
            result = main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "remember",
                    "--kind",
                    "fact",
                ],
                stdin=StringIO("User has a blue bicycle.\n"),
                stdout=output,
            )

        self.assertEqual(result, 0)
        self.assertIn("memory text> ", output.getvalue())
        self.assertIn("User has a blue bicycle.", output.getvalue())
        client_class.assert_not_called()

    @patch("oline_hri.cli.OllamaClient")
    def test_keyword_search_input_can_be_interactive_without_ollama(
        self, client_class
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "remember",
                    "--kind",
                    "fact",
                    "--text",
                    "User owns a blue bicycle.",
                ],
                stdout=StringIO(),
            )
            output = StringIO()

            result = main(
                ["--config", str(config_path), "memory", "search"],
                stdin=StringIO("blue bicycle\n"),
                stdout=output,
            )

        self.assertEqual(result, 0)
        self.assertIn("search query> ", output.getvalue())
        self.assertIn("blue bicycle", output.getvalue().lower())
        client_class.assert_not_called()

    def test_forget_confirmation_defaults_to_cancel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            remembered = StringIO()
            main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "remember",
                    "--kind",
                    "fact",
                    "--text",
                    "Keep this memory.",
                ],
                stdout=remembered,
            )
            memory_id = remembered.getvalue().splitlines()[0].split()[1]
            output = StringIO()

            result = main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "forget",
                    memory_id,
                ],
                stdin=StringIO("no\n"),
                stdout=output,
            )

            listed = StringIO()
            main(
                ["--config", str(config_path), "memory", "list"],
                stdout=listed,
            )
        self.assertEqual(result, 0)
        self.assertIn("forget canceled", output.getvalue())
        self.assertIn(memory_id, listed.getvalue())

    def test_memory_errors_return_code_four_without_echoing_private_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            errors = StringIO()
            private_text = "private-value-that-must-not-be-echoed"

            result = main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "remember",
                    "--kind",
                    "fact",
                    "--text",
                    f"{private_text}\ninvalid",
                ],
                stdout=StringIO(),
                stderr=errors,
            )

        self.assertEqual(result, 4)
        self.assertIn("memory error:", errors.getvalue())
        self.assertNotIn(private_text, errors.getvalue())

    @patch("oline_hri.cli.OllamaClient")
    def test_semantic_search_is_ranked_and_never_calls_ollama(
        self, client_class
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            tea_output = StringIO()
            main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "remember",
                    "--kind",
                    "preference",
                    "--text",
                    "User prefers jasmine tea.",
                ],
                stdout=tea_output,
            )
            tea_id = tea_output.getvalue().splitlines()[0].split()[1]
            main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "remember",
                    "--kind",
                    "fact",
                    "--text",
                    "User owns a blue bicycle.",
                ],
                stdout=StringIO(),
            )
            output = StringIO()

            result = main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "semantic-search",
                    "--query",
                    "jasmine tea",
                    "--limit",
                    "1",
                ],
                stdout=output,
            )

        self.assertEqual(result, 0)
        lines = output.getvalue().splitlines()
        self.assertEqual(
            lines[0],
            "COSINE_SCORE\tID\tSTATUS\tKIND\tSENSITIVITY\tCREATED\tTEXT",
        )
        self.assertIn(tea_id, lines[1])
        self.assertEqual(len(lines), 2)
        client_class.assert_not_called()

    @patch("oline_hri.cli.OllamaClient")
    def test_semantic_search_interactive_empty_result_is_clear(
        self, client_class
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            output = StringIO()

            result = main(
                ["--config", str(config_path), "memory", "semantic-search"],
                stdin=StringIO("anything\n"),
                stdout=output,
            )

        self.assertEqual(result, 0)
        self.assertEqual(
            output.getvalue(),
            "semantic query> no semantically matching active memories\n",
        )
        client_class.assert_not_called()

    @patch("oline_hri.cli.OllamaClient")
    def test_hybrid_search_reports_fused_source_positions_without_ollama(
        self, client_class
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            remembered = StringIO()
            main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "remember",
                    "--kind",
                    "preference",
                    "--text",
                    "User prefers jasmine tea.",
                ],
                stdout=remembered,
            )
            memory_id = remembered.getvalue().splitlines()[0].split()[1]
            output = StringIO()

            result = main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "hybrid-search",
                    "--query",
                    "jasmine tea",
                    "--limit",
                    "1",
                ],
                stdout=output,
            )

        self.assertEqual(result, 0)
        lines = output.getvalue().splitlines()
        self.assertEqual(
            lines[0],
            "FUSED_SCORE\tKEYWORD_POS\tSEMANTIC_POS\tID\tSTATUS\tKIND\t"
            "SENSITIVITY\tCREATED\tTEXT",
        )
        self.assertIn(f"\t1\t1\t{memory_id}\t", lines[1])
        self.assertEqual(len(lines), 2)
        client_class.assert_not_called()

    def test_semantic_search_eof_reports_a_clear_memory_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            output = StringIO()
            errors = StringIO()

            result = main(
                ["--config", str(config_path), "memory", "semantic-search"],
                stdin=StringIO(""),
                stdout=output,
                stderr=errors,
            )

        self.assertEqual(result, 4)
        self.assertEqual(output.getvalue(), "semantic query> ")
        self.assertEqual(
            errors.getvalue(),
            "memory error: no semantic search query was provided\n",
        )

    @patch("oline_hri.cli.OllamaClient")
    def test_embedding_rebuild_and_status_report_all_counts(
        self, client_class
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "remember",
                    "--kind",
                    "fact",
                    "--text",
                    "User likes astronomy.",
                ],
                stdout=StringIO(),
            )
            rebuild_output = StringIO()
            result = main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "rebuild-embeddings",
                ],
                stdout=rebuild_output,
            )
            status_output = StringIO()
            status_result = main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "embedding-status",
                ],
                stdout=status_output,
            )

        self.assertEqual(result, 0)
        self.assertEqual(status_result, 0)
        self.assertEqual(
            rebuild_output.getvalue().strip(),
            "embedding index rebuilt; indexed 1 of 1 eligible memories",
        )
        self.assertEqual(
            status_output.getvalue(),
            "ELIGIBLE\tINDEXED\tMISSING\tINVALID\n1\t1\t0\t0\n",
        )
        client_class.assert_not_called()

    @patch("oline_hri.cli.OllamaClient")
    def test_only_semantic_aware_memory_commands_construct_embedder(
        self, client_class
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            expected_config = load_config(config_path).embedding
            fake = DeterministicEmbedder()
            with patch(
                "oline_hri.cli.BgeOnnxEmbedder", return_value=fake
            ) as embedder_class:
                remembered = StringIO()
                main(
                    [
                        "--config",
                        str(config_path),
                        "memory",
                        "remember",
                        "--kind",
                        "fact",
                        "--text",
                        "User owns a blue bicycle.",
                    ],
                    stdout=remembered,
                )
                memory_id = remembered.getvalue().splitlines()[0].split()[1]
                embedder_class.assert_called_once_with(
                    expected_config.model_directory,
                    expected_config.intra_op_threads,
                )
                embedder_class.reset_mock()

                corrected = StringIO()
                result = main(
                    [
                        "--config",
                        str(config_path),
                        "memory",
                        "correct",
                        memory_id,
                        "--text",
                        "User owns a green bicycle.",
                    ],
                    stdout=corrected,
                )
                self.assertEqual(result, 0)
                replacement_id = (
                    corrected.getvalue().splitlines()[0].split(" -> ")[1]
                )
                embedder_class.assert_called_once_with(
                    expected_config.model_directory,
                    expected_config.intra_op_threads,
                )
                embedder_class.reset_mock()

                commands = (
                    ["memory", "list"],
                    ["memory", "search", "--query", "green"],
                    ["memory", "rebuild-index"],
                    ["memory", "forget", replacement_id, "--yes"],
                )
                for command in commands:
                    result = main(
                        ["--config", str(config_path), *command],
                        stdout=StringIO(),
                    )
                    self.assertEqual(result, 0)

                embedder_class.assert_not_called()

        client_class.assert_not_called()

    @patch("oline_hri.cli.OllamaClient")
    def test_embedding_error_is_sanitized_as_memory_error(
        self, client_class
    ) -> None:
        private_query = "private-semantic-query"
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "remember",
                    "--kind",
                    "fact",
                    "--text",
                    "User likes local robotics.",
                ],
                stdout=StringIO(),
            )
            errors = StringIO()
            with patch(
                "oline_hri.cli.BgeOnnxEmbedder",
                return_value=FailingQueryEmbedder(),
            ):
                result = main(
                    [
                        "--config",
                        str(config_path),
                        "memory",
                        "semantic-search",
                        "--query",
                        private_query,
                    ],
                    stdout=StringIO(),
                    stderr=errors,
                )

        self.assertEqual(result, 4)
        self.assertEqual(
            errors.getvalue(),
            "memory error: personal-memory query embedding failed\n",
        )
        self.assertNotIn(private_query, errors.getvalue())
        client_class.assert_not_called()

    @patch("oline_hri.cli.OllamaClient")
    def test_embedder_construction_error_returns_code_four(
        self, client_class
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            errors = StringIO()
            with patch(
                "oline_hri.cli.BgeOnnxEmbedder",
                side_effect=EmbeddingError(
                    "local embedding runtime dependencies are unavailable"
                ),
            ):
                result = main(
                    [
                        "--config",
                        str(config_path),
                        "memory",
                        "embedding-status",
                    ],
                    stdout=StringIO(),
                    stderr=errors,
                )

        self.assertEqual(result, 4)
        self.assertEqual(
            errors.getvalue(),
            "memory error: local embedding runtime dependencies are unavailable\n",
        )
        client_class.assert_not_called()


if __name__ == "__main__":
    unittest.main()
