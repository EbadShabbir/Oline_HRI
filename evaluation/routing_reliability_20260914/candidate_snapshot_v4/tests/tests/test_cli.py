from io import StringIO
from hashlib import sha256
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from oline_hri.cli import main as cli_main
from oline_hri.config import load_config
from oline_hri.embedding import (
    EMBEDDING_DIMENSION,
    MODEL_ID,
    MODEL_REVISION,
    EmbeddingError,
)
from oline_hri.memory import MemoryStore, MemoryStoreError
from oline_hri.ollama import ChatResult, OllamaError
from oline_hri.response import RobotResponse
from oline_hri.routing import RouteDecision, RoutingResult
from oline_hri.speech import (
    NoSpeechDetected,
    SpeechRuntimeError,
    SpeechRuntimeStatus,
    Transcription,
)



def legacy_main(argv, **kwargs):
    """Keep historical runtime assertions on the explicit legacy policy.

    The default reliable runtime is exercised in test_reliable_cli.py.
    """
    argv = list(argv)
    if "chat" in argv and "--routing-policy" not in argv:
        index = argv.index("chat") + 1
        argv[index:index] = ["--routing-policy", "llm"]
    return cli_main(argv, **kwargs)


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


def memory_capture_result() -> ChatResult:
    return ChatResult(
        model="qwen3:0.6b",
        content='{"store_memory":true,"kind":"preference"}',
        done_reason="stop",
        total_duration_ns=1,
        load_duration_ns=0,
        prompt_eval_count=1,
        eval_count=1,
        eval_duration_ns=1,
    )


def routing_result(
    *, memory_required: bool = False, model_size: str = "small",
    form: str = "question",
) -> RoutingResult:
    memory_required_generation = ChatResult(
        model="qwen3:0.6b",
        content=json.dumps(
            {"form": form, "memory_required": memory_required},
            separators=(",", ":"),
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
    *, memory_required: bool = False, model_size: str = "small",
    form: str = "question",
) -> tuple[ChatResult, ChatResult]:
    result = routing_result(
        memory_required=memory_required, model_size=model_size, form=form
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


def transcription(text: str = "Hello from the microphone.") -> Transcription:
    return Transcription(
        raw_text=f" {text}",
        text=text,
        language="en",
        audio_duration_seconds=1.25,
        capture_seconds=2.0,
        inference_seconds=0.75,
        mean_token_probability=0.91,
        peak_vad_probability=0.97,
        model_name="ggml-small.en-q5_0.bin",
        used_fallback=False,
    )


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

        result = legacy_main(["info"], stdout=output)

        self.assertEqual(result, 0)
        self.assertIn("Oline HRI 0.1.0", output.getvalue())

    def test_config_check(self) -> None:
        output = StringIO()

        result = legacy_main(["config", "check"], stdout=output)

        self.assertEqual(result, 0)
        self.assertIn("configuration valid", output.getvalue())

    def test_config_show_is_json(self) -> None:
        output = StringIO()

        result = legacy_main(["config", "show"], stdout=output)
        data = json.loads(output.getvalue())

        self.assertEqual(result, 0)
        self.assertEqual(data["ollama"]["small_model"], "qwen3:0.6b")
        self.assertEqual(
            data["ollama"]["general_large_model"], "qwen3:1.7b"
        )
        self.assertEqual(data["ollama"]["large_model"], "qwen3:1.7b")

    @patch("oline_hri.cli.speech_runtime_status")
    def test_speech_check_reports_each_runtime_component(self, status) -> None:
        status.return_value = SpeechRuntimeStatus(True, True, True, True, True)
        output = StringIO()

        result = legacy_main(["speech", "check"], stdout=output)

        self.assertEqual(result, 0)
        self.assertEqual(
            output.getvalue(),
            "capture_executable: present\n"
            "silero_model: verified\n"
            "whisper_executable: runnable\n"
            "primary_model: verified\n"
            "fallback_model: verified\n",
        )

    @patch("oline_hri.cli.speech_runtime_status")
    def test_speech_check_fails_when_no_whisper_model_exists(self, status) -> None:
        status.return_value = SpeechRuntimeStatus(True, True, True, False, False)

        result = legacy_main(["speech", "check"], stdout=StringIO())

        self.assertEqual(result, 5)

    @patch("oline_hri.cli.speech_runtime_status")
    def test_speech_check_handles_interrupt_without_traceback(self, status) -> None:
        status.side_effect = KeyboardInterrupt()
        errors = StringIO()

        result = legacy_main(["speech", "check"], stdout=StringIO(), stderr=errors)

        self.assertEqual(result, 130)
        self.assertEqual(errors.getvalue(), "speech check interrupted\n")

    @patch("oline_hri.cli.OfflineSpeechRecognizer")
    def test_speech_listen_prints_transcript_and_optional_metrics(
        self, recognizer_class
    ) -> None:
        recognizer_class.return_value.listen.return_value = transcription()
        output = StringIO()
        errors = StringIO()

        result = legacy_main(
            ["speech", "listen", "--show-metrics"],
            stdout=output,
            stderr=errors,
        )

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), "Hello from the microphone.\n")
        self.assertTrue(errors.getvalue().startswith("listening...\n"))
        metrics = json.loads(errors.getvalue().split("speech> ", 1)[1])
        self.assertEqual(metrics["mean_token_probability"], 0.91)
        self.assertEqual(metrics["model"], "ggml-small.en-q5_0.bin")
        self.assertNotIn("Hello", errors.getvalue())

    @patch("oline_hri.cli.OfflineSpeechRecognizer")
    def test_speech_listen_sanitizes_runtime_failures(
        self, recognizer_class
    ) -> None:
        recognizer_class.side_effect = SpeechRuntimeError("private model path")
        errors = StringIO()

        result = legacy_main(["speech", "listen"], stderr=errors, stdout=StringIO())

        self.assertEqual(result, 5)
        self.assertEqual(
            errors.getvalue(),
            "speech error: request could not be completed safely\n",
        )
        self.assertNotIn("private", errors.getvalue())

    @patch("oline_hri.cli.OfflineSpeechRecognizer")
    def test_speech_listen_reports_no_usable_speech(
        self, recognizer_class
    ) -> None:
        recognizer_class.return_value.listen.side_effect = NoSpeechDetected(
            "private capture detail"
        )
        errors = StringIO()

        result = legacy_main(["speech", "listen"], stderr=errors, stdout=StringIO())

        self.assertEqual(result, 5)
        self.assertEqual(
            errors.getvalue(),
            "listening...\nspeech> no usable speech detected; please try again\n",
        )
        self.assertNotIn("private", errors.getvalue())

    @patch("oline_hri.cli.OfflineSpeechRecognizer")
    def test_speech_listen_handles_interrupt_without_traceback(
        self, recognizer_class
    ) -> None:
        recognizer_class.return_value.listen.side_effect = KeyboardInterrupt()
        errors = StringIO()

        result = legacy_main(["speech", "listen"], stderr=errors, stdout=StringIO())

        self.assertEqual(result, 130)
        self.assertEqual(errors.getvalue(), "listening...\nspeech interrupted\n")

    def test_prompt_and_voice_are_mutually_exclusive(self) -> None:
        with patch("sys.stderr", StringIO()), self.assertRaises(SystemExit):
            legacy_main(["chat", "--prompt", "Hello", "--voice"])

    @patch("oline_hri.cli.OfflineSpeechRecognizer")
    @patch("oline_hri.cli.OllamaClient")
    def test_voice_auto_memory_stores_an_eligible_transcript(
        self, client_class, recognizer_class
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            recognizer_class.return_value.listen.side_effect = (
                transcription("I prefer jasmine tea without sugar."),
                KeyboardInterrupt(),
            )

            def respond(model, messages, **kwargs):
                fields = set(kwargs["response_format"]["properties"])
                if fields == {"form", "memory_required"}:
                    return routing_generations(
                        memory_required=False, form="statement"
                    )[0]
                if fields == {"model_size"}:
                    return routing_generations(model_size="small")[1]
                if fields == {"store_memory", "kind"}:
                    return ChatResult(
                        model="qwen3:0.6b",
                        content=(
                            '{"store_memory":true,"kind":"preference"}'
                        ),
                        done_reason="stop",
                        total_duration_ns=1,
                        load_duration_ns=0,
                        prompt_eval_count=1,
                        eval_count=1,
                        eval_duration_ns=1,
                    )
                return chat_result("Thanks for telling me.")

            client_class.return_value.chat.side_effect = respond
            output = StringIO()
            errors = StringIO()

            result = legacy_main(
                [
                    "--config",
                    str(config_path),
                    "chat",
                    "--voice",
                    "--auto-memory",
                ],
                stdout=output,
                stderr=errors,
            )

            config = load_config(config_path)
            stored = MemoryStore(
                config.memory.database_path,
                profile_id=config.memory.profile_id,
            ).list_memories()

        self.assertEqual(result, 0)
        self.assertEqual(len(stored), 1)
        self.assertEqual(
            stored[0].canonical_text,
            "I prefer jasmine tea without sugar.",
        )
        self.assertEqual(stored[0].kind, "preference")
        self.assertIn("Automatic seven-day memory is ON", output.getvalue())
        self.assertIn("automatically remembered", errors.getvalue())

    @patch("oline_hri.cli.OfflineSpeechRecognizer")
    @patch("oline_hri.cli.ConversationRouter")
    @patch("oline_hri.cli.OllamaClient")
    def test_auto_memory_survives_reply_failure_in_all_chat_modes(
        self, client_class, router_class, recognizer_class
    ) -> None:
        statement = "I prefer jasmine tea without sugar."
        router_class.return_value.route.return_value = routing_result()
        for mode in ("text", "voice", "prompt"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                config_path = memory_config(directory)
                generation_calls = 0
                capture_calls = 0

                def respond(model, messages, **kwargs):
                    nonlocal generation_calls, capture_calls
                    fields = set(kwargs["response_format"]["properties"])
                    if fields == {"store_memory", "kind"}:
                        capture_calls += 1
                        return memory_capture_result()
                    generation_calls += 1
                    if generation_calls == 1:
                        raise OllamaError("private generation failure detail")
                    return chat_result("Hello again.")

                client_class.return_value.chat.side_effect = respond
                recognizer_class.return_value.listen.side_effect = (
                    transcription(statement),
                    transcription("Hello"),
                    KeyboardInterrupt(),
                )
                args = ["--config", str(config_path), "chat", "--auto-memory"]
                if mode == "voice":
                    args.append("--voice")
                elif mode == "prompt":
                    args.extend(("--prompt", statement))
                output = StringIO()
                errors = StringIO()

                result = legacy_main(
                    args,
                    stdin=StringIO(f"{statement}\nHello\n/exit\n"),
                    stdout=output,
                    stderr=errors,
                )

                config = load_config(config_path)
                stored = MemoryStore(
                    config.memory.database_path,
                    profile_id=config.memory.profile_id,
                ).list_memories()

                self.assertEqual(result, 3 if mode == "prompt" else 0)
                self.assertEqual(capture_calls, 1)
                self.assertEqual(len(stored), 1)
                self.assertEqual(stored[0].canonical_text, statement)
                self.assertIn("chat error:", errors.getvalue())
                self.assertIn("automatically remembered", errors.getvalue())
                self.assertNotIn("private", errors.getvalue())
                self.assertNotIn(statement, errors.getvalue())
                if mode != "prompt":
                    self.assertIn("robot> Hello again.", output.getvalue())

    @patch("oline_hri.cli.ConversationRouter")
    @patch("oline_hri.cli.OllamaClient")
    def test_auto_memory_reports_duplicate_and_classifies_after_answer(
        self, client_class, router_class
    ) -> None:
        router_class.return_value.route.return_value = routing_result()
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            output = StringIO()
            errors = StringIO()
            capture_calls = 0

            def respond(model, messages, **kwargs):
                nonlocal capture_calls
                fields = set(kwargs["response_format"]["properties"])
                if fields == {"store_memory", "kind"}:
                    self.assertIn("robot> Thanks for telling me.", output.getvalue())
                    capture_calls += 1
                    return memory_capture_result()
                return chat_result("Thanks for telling me.")

            client_class.return_value.chat.side_effect = respond
            result = legacy_main(
                ["--config", str(config_path), "chat", "--auto-memory"],
                stdin=StringIO(
                    "I prefer jasmine tea.\ni prefer jasmine tea\n/exit\n"
                ),
                stdout=output,
                stderr=errors,
            )
            config = load_config(config_path)
            stored = MemoryStore(
                config.memory.database_path,
                profile_id=config.memory.profile_id,
            ).list_memories()

        self.assertEqual(result, 0)
        self.assertEqual(capture_calls, 1)
        self.assertEqual(len(stored), 1)
        self.assertIn(f"automatically remembered {stored[0].id}", errors.getvalue())
        self.assertIn(f"already remembered {stored[0].id}", errors.getvalue())
        self.assertNotIn("jasmine", errors.getvalue())

    @patch("oline_hri.cli.ConversationRouter")
    @patch("oline_hri.cli.OllamaClient")
    def test_auto_memory_storage_failures_allow_the_next_chat_turn(
        self, client_class, router_class
    ) -> None:
        router_class.return_value.route.return_value = routing_result()

        def respond(model, messages, **kwargs):
            fields = set(kwargs["response_format"]["properties"])
            if fields == {"store_memory", "kind"}:
                return memory_capture_result()
            return chat_result("Hello again.")

        client_class.return_value.chat.side_effect = respond
        failures = (
            ("oline_hri.cli.MemoryStore.remember", MemoryStoreError),
            ("oline_hri.cli.BgeOnnxEmbedder.embed_passages", EmbeddingError),
        )
        for target, error_class in failures:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                config_path = memory_config(directory)
                output = StringIO()
                errors = StringIO()
                with patch(target, side_effect=error_class("private failure detail")):
                    result = legacy_main(
                        ["--config", str(config_path), "chat", "--auto-memory"],
                        stdin=StringIO("I prefer jasmine tea.\nHello\n/exit\n"),
                        stdout=output,
                        stderr=errors,
                    )
                config = load_config(config_path)
                stored = MemoryStore(
                    config.memory.database_path,
                    profile_id=config.memory.profile_id,
                ).list_memories()

                self.assertEqual(result, 0)
                self.assertEqual(stored, ())
                self.assertEqual(output.getvalue().count("robot> Hello again."), 2)
                self.assertEqual(
                    errors.getvalue(), "memory> automatic capture skipped safely\n"
                )

    @patch("oline_hri.cli.OfflineSpeechRecognizer")
    @patch("oline_hri.cli.OllamaClient")
    def test_voice_chat_retries_no_speech_and_sends_only_normalized_text(
        self, client_class, recognizer_class
    ) -> None:
        client_class.return_value.chat.return_value = chat_result("Hi by voice!")
        recognizer_class.return_value.listen.side_effect = (
            NoSpeechDetected("private audio detail"),
            transcription("Normalized microphone text."),
            KeyboardInterrupt(),
        )
        output = StringIO()
        errors = StringIO()

        with patch("oline_hri.cli.ConversationRouter") as router_class:
            router_class.return_value.route.return_value = routing_result()
            result = legacy_main(
                ["chat", "--voice"],
                stdout=output,
                stderr=errors,
            )

        self.assertEqual(result, 0)
        self.assertIn("Offline voice chat", output.getvalue())
        self.assertIn("you> Normalized microphone text.", output.getvalue())
        self.assertIn("robot> Hi by voice!", output.getvalue())
        self.assertEqual(
            errors.getvalue(),
            "speech> no usable speech detected; please try again\n",
        )
        self.assertNotIn("private", errors.getvalue())
        self.assertEqual(client_class.return_value.unload_all.call_count, 4)
        messages = client_class.return_value.chat.call_args.args[1]
        self.assertEqual(messages[-1].content, "Normalized microphone text.")

    @patch("oline_hri.cli.OfflineSpeechRecognizer")
    @patch("oline_hri.cli.OllamaClient")
    def test_voice_interrupt_during_generation_unloads_without_a_traceback(
        self, client_class, recognizer_class
    ) -> None:
        recognizer_class.return_value.listen.return_value = transcription()
        client_class.return_value.chat.side_effect = KeyboardInterrupt()

        with patch("oline_hri.cli.ConversationRouter") as router_class:
            router_class.return_value.route.return_value = routing_result()
            result = legacy_main(
                ["chat", "--voice"],
                stdout=StringIO(),
                stderr=StringIO(),
            )

        self.assertEqual(result, 0)
        self.assertEqual(client_class.return_value.unload_all.call_count, 2)

    @patch("oline_hri.cli.OfflineSpeechRecognizer")
    @patch("oline_hri.cli.OllamaClient")
    def test_voice_interrupt_during_setup_is_clean_and_unloads(
        self, client_class, recognizer_class
    ) -> None:
        recognizer_class.side_effect = KeyboardInterrupt()
        errors = StringIO()

        result = legacy_main(
            ["chat", "--voice"],
            stdout=StringIO(),
            stderr=errors,
        )

        self.assertEqual(result, 130)
        self.assertEqual(errors.getvalue(), "voice interrupted\n")
        client_class.return_value.unload_all.assert_called_once_with()

    def test_invalid_config_returns_nonzero(self) -> None:
        errors = StringIO()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("{}", encoding="utf-8")

            result = legacy_main(
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
            result = legacy_main(
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
            result = legacy_main(
                ["chat"],
                stdin=StringIO("Hello\n/exit\n"),
                stdout=output,
            )

        self.assertEqual(result, 0)
        self.assertIn("robot> Hi!", output.getvalue())

    @patch("oline_hri.cli.OllamaClient")
    def test_interactive_chat_can_remember_ten_lines_then_recall_a_statement(
        self, client_class
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            route_outputs = iter(routing_generations(memory_required=True))
            calls = 0

            def respond(model, messages, **kwargs):
                nonlocal calls
                calls += 1
                if calls <= 2:
                    return next(route_outputs)
                allowed_ids = tuple(
                    kwargs["response_format"]["properties"]["memory_used"]
                    ["items"]["enum"]
                )
                return authorized_chat_result(
                    "You prefer jasmine tea without sugar.",
                    allowed_ids,
                )

            client_class.return_value.chat.side_effect = respond
            output = StringIO()
            errors = StringIO()

            result = legacy_main(
                ["--config", str(config_path), "chat", "--show-memory-ids"],
                stdin=StringIO(
                    "/remember preference I prefer jasmine tea without sugar.\n"
                    "/remember routine I usually drink tea in the morning.\n"
                    "/remember relationship Theo is my robotics project partner.\n"
                    "/remember fact I own a blue bicycle.\n"
                    "/remember preference I prefer concise answers.\n"
                    "/remember routine My robotics meetings are Tuesday mornings.\n"
                    "/remember event I completed a sensor prototype today.\n"
                    "/remember fact My desk plant is named Fern.\n"
                    "/remember preference I prefer a quiet workspace.\n"
                    "/remember event I plan to travel on Friday.\n"
                    "/memories\n"
                    "What kind of tea do I prefer?\n"
                    "/exit\n"
                ),
                stdout=output,
                stderr=errors,
            )

            config = load_config(config_path)
            stored = MemoryStore(
                config.memory.database_path,
                profile_id=config.memory.profile_id,
            ).list_memories()

        self.assertEqual(result, 0)
        self.assertEqual(len(stored), 10)
        tea = next(
            item
            for item in stored
            if item.canonical_text == "I prefer jasmine tea without sugar."
        )
        self.assertIsNotNone(tea.retention_until)
        self.assertEqual(output.getvalue().count("robot> Remembered "), 10)
        self.assertIn("[preference]", output.getvalue())
        self.assertIn(
            "robot> You prefer jasmine tea without sugar.",
            output.getvalue(),
        )
        self.assertIn(tea.id, errors.getvalue())
        generation_messages = client_class.return_value.chat.call_args_list[2].args[1]
        memory_messages = [
            message
            for message in generation_messages
            if "PERSONAL_MEMORY_DATA=" in message.content
        ]
        self.assertEqual(len(memory_messages), 1)
        self.assertIn(
            "You prefer jasmine tea without sugar.",
            memory_messages[0].content,
        )

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
                    "Routed answer.", (), model="qwen3:1.7b"
                ),
            )
        )

        def respond(*args, **kwargs):
            result = next(calls)
            if result.model == "qwen3:1.7b":
                self.assertEqual(
                    errors.getvalue(),
                    "route> model_size=large selected_generator=qwen3:1.7b "
                    "memory_required=false\n",
                )
            return result

        client_class.return_value.chat.side_effect = respond

        result = legacy_main(
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
            "route> model_size=large selected_generator=qwen3:1.7b "
            "memory_required=false\n",
        )

    @patch("oline_hri.cli.OllamaClient")
    def test_route_and_memory_id_diagnostics_have_stable_order(
        self, client_class
    ) -> None:
        client_class.return_value.chat.side_effect = (
            *routing_generations(model_size="large"),
            authorized_chat_result(
                "Routed answer.", (), model="qwen3:1.7b"
            ),
        )
        output = StringIO()
        errors = StringIO()

        result = legacy_main(
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
            "route> model_size=large selected_generator=qwen3:1.7b "
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
            result = legacy_main(
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
            result = legacy_main(
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
            ("large", "qwen3:1.7b"),
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

                result = legacy_main(
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
                    list(memory_route_format["properties"]),
                    ["form", "memory_required"],
                )
                self.assertEqual(
                    memory_route_format["required"],
                    ["form", "memory_required"],
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
            result = legacy_main(
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

            result = legacy_main(
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

            result = legacy_main(
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

        result = legacy_main(
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
            result = legacy_main(
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
            self.assertIn("retained until:", remembered_output.getvalue())

            listed_output = StringIO()
            result = legacy_main(
                ["--config", str(config_path), "memory", "list"],
                stdout=listed_output,
            )
            self.assertEqual(result, 0)
            self.assertIn(first_id, listed_output.getvalue())
            self.assertIn("User prefers mint tea.", listed_output.getvalue())

            search_output = StringIO()
            result = legacy_main(
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
            result = legacy_main(
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
            result = legacy_main(
                ["--config", str(config_path), "memory", "list", "--all"],
                stdout=all_output,
            )
            self.assertEqual(result, 0)
            self.assertIn(first_id, all_output.getvalue())
            self.assertIn("superseded", all_output.getvalue())
            self.assertIn(replacement_id, all_output.getvalue())

            old_search = StringIO()
            result = legacy_main(
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
            result = legacy_main(
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
            result = legacy_main(
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
            result = legacy_main(
                ["--config", str(config_path), "memory", "list", "--all"],
                stdout=empty_output,
            )
            self.assertEqual(result, 0)
            self.assertEqual(empty_output.getvalue().strip(), "no memories")

    def test_memory_prune_removes_legacy_records_older_than_seven_days(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            config = load_config(config_path)
            old_clock = lambda: datetime.now(timezone.utc) - timedelta(days=8)
            old_item = MemoryStore(
                config.memory.database_path,
                profile_id=config.memory.profile_id,
                clock=old_clock,
            ).remember("Old temporary memory.", kind="fact")
            output = StringIO()

            result = legacy_main(
                ["--config", str(config_path), "memory", "prune"],
                stdout=output,
            )

            remaining = MemoryStore(
                config.memory.database_path,
                profile_id=config.memory.profile_id,
            ).list_memories(include_inactive=True)
        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), "pruned 1 expired memory record(s)\n")
        self.assertNotIn(old_item.id, {item.id for item in remaining})

    @patch("oline_hri.cli.OllamaClient")
    def test_memory_input_is_interactive_and_does_not_call_ollama(
        self, client_class
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            output = StringIO()
            result = legacy_main(
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
            legacy_main(
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

            result = legacy_main(
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
            legacy_main(
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

            result = legacy_main(
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
            legacy_main(
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

            result = legacy_main(
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
            legacy_main(
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
            legacy_main(
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

            result = legacy_main(
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
            "COSINE_SCORE\tID\tSTATUS\tKIND\tSENSITIVITY\tCREATED\t"
            "RETAINED_UNTIL\tTEXT",
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

            result = legacy_main(
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
            legacy_main(
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

            result = legacy_main(
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
            "SENSITIVITY\tCREATED\tRETAINED_UNTIL\tTEXT",
        )
        self.assertIn(f"\t1\t1\t{memory_id}\t", lines[1])
        self.assertEqual(len(lines), 2)
        client_class.assert_not_called()

    def test_semantic_search_eof_reports_a_clear_memory_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = memory_config(directory)
            output = StringIO()
            errors = StringIO()

            result = legacy_main(
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
            legacy_main(
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
            result = legacy_main(
                [
                    "--config",
                    str(config_path),
                    "memory",
                    "rebuild-embeddings",
                ],
                stdout=rebuild_output,
            )
            status_output = StringIO()
            status_result = legacy_main(
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
                legacy_main(
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
                result = legacy_main(
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
                    result = legacy_main(
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
            legacy_main(
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
                result = legacy_main(
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
                result = legacy_main(
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
