"""Opt-in legacy-policy smoke test for capture with the real local model."""

from __future__ import annotations

import os
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from oline_hri.config import load_config
from oline_hri.cli import main
from oline_hri.embedding import BgeOnnxEmbedder
from oline_hri.memory import MemoryStore
from oline_hri.memory_capture import (
    AutomaticMemoryCapture,
    AutomaticMemoryClassifier,
)
from oline_hri.ollama import OllamaClient
from oline_hri.routing import ConversationRouter, RouteDecision


RUN_LIVE = os.environ.get("OLINE_HRI_RUN_LIVE_CAPTURE") == "1"


@unittest.skipUnless(
    RUN_LIVE,
    "set OLINE_HRI_RUN_LIVE_CAPTURE=1 to use the local Ollama model",
)
class LiveAutomaticMemoryCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()
        self.client = OllamaClient(
            self.config.ollama,
            self.config.generation,
        )
        self.classifier = AutomaticMemoryClassifier(
            self.client,
            model=self.config.ollama.small_model,
        )

    def tearDown(self) -> None:
        self.client.unload_all()

    def test_real_router_distinguishes_disclosures_from_recall(self):
        router = ConversationRouter(self.client, model=self.config.ollama.small_model)
        cases = (
            ("I prefer jasmine tea without sugar.", False),
            ("My robotics meetings are Tuesday mornings.", False),
            ("Theo is my robotics project partner.", False),
            ("What kind of tea do I prefer?", True),
            ("what kind of tea do i prefer", True),
            ("When are my robotics meetings?", True),
            ("Who is Theo to me?", True),
            ("What is my favorite snack?", True),
            ("What is jasmine tea?", False),
            ("I like peppermint tea in the evenings.", False),
            ("Alex is my lab partner.", False),
            ("my robotics meetings are tuesday mornings", False),
        )
        for statement, memory_required in cases:
            with self.subTest(statement=statement):
                routed = router.route(statement)
                self.assertEqual(
                    routed.decision, RouteDecision(memory_required, "small"),
                    f"prompt tokens={routed.memory_required_generation.prompt_eval_count}",
                )

    def test_real_classifier_stores_only_eligible_exact_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            embedder = BgeOnnxEmbedder(
                self.config.embedding.model_directory,
                self.config.embedding.intra_op_threads,
            )
            store = MemoryStore(
                Path(directory) / "memory.sqlite3",
                profile_id="automatic_capture_live_test",
                embedder=embedder,
                retention_days=self.config.memory.retention_days,
            )
            capture = AutomaticMemoryCapture(self.classifier, store)

            self.assertIsNone(capture.consider("What tea do I prefer?"))
            self.assertIsNone(capture.consider("I am stressed right now."))
            item = capture.consider("I prefer jasmine tea without sugar.")

            self.assertIsNotNone(item)
            assert item is not None
            self.assertEqual(
                item.canonical_text,
                "I prefer jasmine tea without sugar.",
            )
            self.assertEqual(item.kind, "preference")
            self.assertEqual(len(store.list_memories()), 1)

    def test_real_chat_captures_disclosures_and_recalls_in_new_session(self):
        statements = (
            "I prefer jasmine tea without sugar.",
            "My robotics meetings are Tuesday mornings.",
            "Theo is my robotics project partner.",
        )
        with tempfile.TemporaryDirectory() as directory:
            config_data = self.config.to_dict()
            database_path = Path(directory) / "memory.sqlite3"
            config_data["memory"]["database_path"] = str(database_path)
            config_data["memory"]["profile_id"] = "fictional_chat_capture"
            config_path = Path(directory) / "config.json"
            config_path.write_text(json.dumps(config_data), encoding="utf-8")
            arguments = [
                "--config", str(config_path), "chat", "--routing-policy", "llm", "--auto-memory",
                "--show-route", "--show-memory-ids",
            ]
            output, errors = StringIO(), StringIO()
            status = main(
                arguments,
                stdin=StringIO("\n".join((
                    *statements, "What kind of tea do I prefer?", "/exit", ""
                ))),
                stdout=output, stderr=errors,
            )
            self.assertEqual(status, 0)
            self.assertNotIn("chat error:", errors.getvalue())
            self.assertEqual(
                errors.getvalue().count("memory_required=false"), 3,
                errors.getvalue() + output.getvalue(),
            )
            self.assertNotRegex(
                output.getvalue(),
                r"(?i)robot>.*\b(?:I prefer|my robotics|my partner)\b",
            )
            last_reply = output.getvalue().rsplit("robot> ", 1)[-1].lower()
            self.assertIn("jasmine", last_reply)
            self.assertIn("without sugar", last_reply)
            self.assertEqual(errors.getvalue().count("memory_required=true"), 1)
            store = MemoryStore(database_path, profile_id="fictional_chat_capture")
            self.assertEqual(
                {item.canonical_text for item in store.list_memories()},
                set(statements),
            )

            # A new Conversation excludes session history as a source of answers.
            output, errors = StringIO(), StringIO()
            status = main(
                arguments,
                stdin=StringIO(
                    "What kind of tea do I prefer?\n"
                    "When are my robotics meetings?\n"
                    "Who is Theo to me?\n/exit\n"
                ),
                stdout=output, stderr=errors,
            )
            self.assertEqual(status, 0)
            self.assertNotIn("chat error:", errors.getvalue())
            self.assertEqual(
                errors.getvalue().count("memory_required=true"), 3,
                errors.getvalue() + output.getvalue(),
            )
            speech = output.getvalue().lower()
            self.assertIn("jasmine", speech)
            self.assertIn("without sugar", speech)
            self.assertIn("tuesday mornings", speech)
            self.assertIn("theo", speech)
            self.assertIn("your robotics project partner", speech)
            self.assertNotIn("i prefer", speech)
            self.assertEqual(len(store.list_memories()), 3)


if __name__ == "__main__":
    unittest.main()
