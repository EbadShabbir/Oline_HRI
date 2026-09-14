"""Offline CLI wiring, cleanup, and optional-mode compatibility checks."""

from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from oline_hri.cli import main
from oline_hri.config import load_config
from oline_hri.embedding import EmbeddingError
from oline_hri.memory import MemoryStore
from oline_hri.ollama import ChatResult, OllamaError
from tests.test_cli import DeterministicEmbedder, memory_config, transcription


SMALL, LARGE = "qwen3:0.6b", "qwen3:1.7b"


class LightweightCliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.config_path = memory_config(directory.name)
        self.events = []
        self.output, self.errors = StringIO(), StringIO()
        client_patch = patch("oline_hri.cli.OllamaClient")
        self.client_class = client_patch.start()
        self.addCleanup(client_patch.stop)
        embed_patch = patch("oline_hri.cli.BgeOnnxEmbedder", DeterministicEmbedder)
        embed_patch.start()
        self.addCleanup(embed_patch.stop)
        self.client = self.client_class.return_value
        self.client.resident_model = None
        self.client.chat.side_effect = self.respond
        self.client.unload_all.side_effect = self.unload

    def unload(self):
        self.events.append(("unload",))
        self.client.resident_model = None

    def respond(self, model, messages, **kwargs):
        fields = set(kwargs["response_format"]["properties"])
        self.events.append(("chat", model, fields))
        self.client.resident_model = model
        if fields == {"form", "memory_required"}:
            payload = {"form": "statement" if "I prefer" in messages[-1].content else "question",
                       "memory_required": False}
        elif fields == {"model_size"}:
            payload = {"model_size": "small"}
        elif fields == {"store_memory", "kind"}:
            payload = {"store_memory": True, "kind": "preference"}
        else:
            speech = kwargs["response_format"]["properties"]["speech"].get(
                "enum", ["Thanks for your message."]
            )[0]
            payload = {"speech": speech, "gesture_id": "NO_ACTION", "memory_used": []}
        return ChatResult(model, json.dumps(payload), "stop", 1, 0, 1, 1, 1)

    def invoke(self, *args, input_text=""):
        return main(["--config", str(self.config_path), "chat", *args],
                    stdout=self.output, stderr=self.errors, stdin=StringIO(input_text))

    def test_explicit_mode_skips_classifiers_and_reports_provenance_then_unloads(self):
        result = self.invoke("--routing-policy", "lightweight", "--show-route",
                             "--prompt", "What is granite?")
        self.assertEqual(result, 0, self.errors.getvalue())
        self.assertEqual(self.client_class.call_args.kwargs, {"retain_large_model": True})
        self.assertEqual(self.events, [("chat", SMALL, {"speech", "gesture_id", "memory_used"}),
                                       ("unload",)])
        self.assertIn("policy=lightweight_v1", self.errors.getvalue())
        self.assertIn("compute_source=lightweight_small", self.errors.getvalue())
        self.assertIn("memory_source=policy_general", self.errors.getvalue())
        self.assertNotIn("granite", self.errors.getvalue())
        self.assertIsNone(self.client.resident_model)

    def test_default_and_explicit_llm_keep_original_two_calls_and_cleanup_policy(self):
        for option in ((), ("--routing-policy", "llm")):
            with self.subTest(option=option):
                self.events.clear()
                self.assertEqual(self.invoke(*option, "--show-route", "--prompt", "What is granite?"), 0)
                self.assertEqual(self.client_class.call_args.kwargs, {})
                self.assertEqual([event[2] for event in self.events], [
                    {"form", "memory_required"}, {"model_size"}, {"speech", "gesture_id", "memory_used"}])
                self.assertNotIn("policy=lightweight", self.errors.getvalue())

    def test_interactive_clear_and_exit_release_retained_generator(self):
        result = self.invoke("--routing-policy", "lightweight", input_text=(
            "Compare electric and diesel vehicles in general.\n/clear\nWhat is granite?\n/exit\n"))
        self.assertEqual(result, 0, self.errors.getvalue())
        self.assertEqual([event[1] for event in self.events if event[0] == "chat"], [LARGE, LARGE])
        self.assertIn("conversation cleared", self.output.getvalue())
        self.assertEqual(self.events[-1], ("unload",))

    def test_generation_error_and_interrupt_release_model_and_hide_private_errors(self):
        for error, expected in ((OllamaError("private failure detail"), 3), (KeyboardInterrupt(), 130)):
            with self.subTest(error=type(error).__name__):
                self.events.clear()
                self.client.chat.side_effect = error
                self.client.resident_model = LARGE
                result = self.invoke("--routing-policy", "lightweight", "--prompt",
                                     "Compare electric and diesel vehicles in general.")
                self.assertEqual(result, expected)
                self.assertEqual(self.events[-1], ("unload",))
                self.assertIsNone(self.client.resident_model)
                self.assertNotIn("private failure detail", self.errors.getvalue())

    def test_embedding_initialization_failure_returns_error_and_runs_cleanup(self):
        with patch("oline_hri.cli.BgeOnnxEmbedder", side_effect=EmbeddingError("private path")):
            self.assertEqual(self.invoke("--routing-policy", "lightweight", "--prompt", "Hello"), 3)
        self.client.chat.assert_not_called()
        self.assertEqual(self.events, [("unload",)])
        self.assertNotIn("private path", self.errors.getvalue())

    def test_cleanup_error_keeps_answer_but_reports_failure_and_nonzero_exit(self):
        self.client.unload_all.side_effect = OllamaError("private server detail")
        self.assertEqual(self.invoke("--routing-policy", "lightweight", "--prompt", "What is granite?"), 3)
        self.assertEqual(self.output.getvalue(), "Thanks for your message.\n")
        self.assertIn("chat cleanup error: model unloading could not be confirmed", self.errors.getvalue())
        self.assertNotIn("private server detail", self.errors.getvalue())
        self.client.unload_all.assert_called_once()

    def test_voice_still_releases_model_before_each_listen(self):
        transcripts = iter((transcription("Compare electric and diesel vehicles in general."),))
        def listen():
            self.assertIsNone(self.client.resident_model)
            self.events.append(("listen",))
            try:
                return next(transcripts)
            except StopIteration:
                raise KeyboardInterrupt()
        with patch("oline_hri.cli.OfflineSpeechRecognizer") as recognizer:
            recognizer.return_value.listen.side_effect = listen
            self.assertEqual(self.invoke("--routing-policy", "lightweight", "--voice"), 0)
        self.assertEqual([event[0] for event in self.events[:5]],
                         ["unload", "listen", "chat", "unload", "listen"])
        self.assertEqual(self.events[-1], ("unload",))
        self.assertIsNone(self.client.resident_model)

    def test_automatic_capture_keeps_its_small_model_and_stores_the_disclosure(self):
        result = self.invoke("--routing-policy", "lightweight", "--auto-memory", "--prompt",
                             "I prefer jasmine tea without sugar.")
        self.assertEqual(result, 0, self.errors.getvalue())
        self.assertEqual([(event[1], event[2]) for event in self.events if event[0] == "chat"], [
            (LARGE, {"form", "memory_required"}),
            (LARGE, {"speech", "gesture_id", "memory_used"}),
            (SMALL, {"store_memory", "kind"}),
        ])
        config = load_config(self.config_path)
        memories = MemoryStore(Path(config.memory.database_path),
                               profile_id=config.memory.profile_id).list_memories()
        self.assertEqual([item.canonical_text for item in memories], ["I prefer jasmine tea without sugar."])
        self.assertEqual(self.events[-1], ("unload",))


if __name__ == "__main__":
    unittest.main()
