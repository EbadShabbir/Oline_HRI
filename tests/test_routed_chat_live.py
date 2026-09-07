"""Opt-in smoke tests for the real local router and memory-aware chat."""

import os
from pathlib import Path
import tempfile
import unittest

from oline_hri.config import load_config
from oline_hri.conversation import Conversation
from oline_hri.embedding import BgeOnnxEmbedder
from oline_hri.memory import MemoryStore
from oline_hri.ollama import ChatMessage, OllamaClient
from oline_hri.retrieval import HybridRetriever
from oline_hri.routing import ConversationRouter, RouteDecision


RUN_LIVE = os.environ.get("OLINE_HRI_RUN_LIVE_ROUTING") == "1"


@unittest.skipUnless(
    RUN_LIVE,
    "set OLINE_HRI_RUN_LIVE_ROUTING=1 to use the local Ollama models",
)
class LiveRoutedChatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()
        self.client = OllamaClient(
            self.config.ollama, self.config.generation
        )
        self.router = ConversationRouter(
            self.client, model=self.config.ollama.small_model
        )

    def test_simple_personal_recall_uses_memory_and_small_model(self) -> None:
        cases = (
            "Who is Theo to me?",
            "How do I know Theo?",
            "What is my preferred meeting time for the robotics project?",
            "When do I usually want robotics project meetings?",
        )

        for query in cases:
            with self.subTest(query=query):
                self.assertEqual(
                    self.router.route(query).decision,
                    RouteDecision(True, "small"),
                )

    def test_complex_general_planning_skips_memory_and_uses_large_model(
        self,
    ) -> None:
        cases = (
            (
                "Compare three offline robot architectures, reason through "
                "their tradeoffs, and create a detailed deployment plan."
            ),
            (
                "Create a detailed contingency plan for recovering an offline "
                "application after database corruption without assuming "
                "network access."
            ),
            (
                "Design a robust local-only backup and restoration workflow "
                "for a corrupted service database, including verification "
                "and rollback steps."
            ),
        )

        for query in cases:
            with self.subTest(query=query):
                self.assertEqual(
                    self.router.route(query).decision,
                    RouteDecision(False, "large"),
                )

        greeting_history = (
            ChatMessage(role="user", content="Hello there!"),
            ChatMessage(role="assistant", content="Hello!"),
        )
        self.assertEqual(
            self.router.route(cases[0], history=greeting_history).decision,
            RouteDecision(False, "large"),
        )

    def test_real_router_exercises_all_four_routes_and_recall_paraphrases(
        self,
    ) -> None:
        cases = (
            ("Hello there!", RouteDecision(False, "small")),
            (
                "Who is Theo to me?",
                RouteDecision(True, "small"),
            ),
            (
                "How do I know Theo?",
                RouteDecision(True, "small"),
            ),
            (
                "What is my preferred meeting time for the robotics project?",
                RouteDecision(True, "small"),
            ),
            (
                "When do I usually want robotics project meetings?",
                RouteDecision(True, "small"),
            ),
            (
                "Compare three offline robot architectures, reason through "
                "their tradeoffs, and create a detailed deployment plan.",
                RouteDecision(False, "large"),
            ),
            (
                "Create a detailed contingency plan for recovering an offline "
                "application after database corruption without assuming "
                "network access.",
                RouteDecision(False, "large"),
            ),
            (
                "Plan my next robotics project meeting with Theo, using my "
                "preferred meeting time and project-plan format.",
                RouteDecision(True, "large"),
            ),
            (
                "Using everything relevant you remember about Theo, schedule, "
                "and plan style, create my meeting plan.",
                RouteDecision(True, "large"),
            ),
        )

        for query, expected in cases:
            with self.subTest(query=query):
                self.assertEqual(self.router.route(query).decision, expected)

    def test_unrelated_greeting_history_does_not_change_architecture_route(
        self,
    ) -> None:
        prompt = (
            "Compare three offline robot architectures, reason through their "
            "tradeoffs, and create a detailed deployment plan."
        )
        greeting_history = (
            ChatMessage(role="user", content="Hello there!"),
            ChatMessage(
                role="assistant",
                content=(
                    '{"speech":"Hello!","gesture_id":"NO_ACTION",'
                    '"memory_used":[]}'
                ),
            ),
        )

        self.assertEqual(
            self.router.route("Hello there!").decision,
            RouteDecision(False, "small"),
        )
        self.assertEqual(
            self.router.route(prompt).decision,
            RouteDecision(False, "large"),
        )
        self.assertEqual(
            self.router.route(prompt, history=greeting_history).decision,
            RouteDecision(False, "large"),
        )

    def test_explicit_session_reference_retains_relevant_history(self) -> None:
        session_history = (
            ChatMessage(
                role="user",
                content="For this conversation, my preferred tea is jasmine.",
            ),
            ChatMessage(
                role="assistant",
                content=(
                    '{"speech":"Understood.","gesture_id":"NO_ACTION",'
                    '"memory_used":[]}'
                ),
            ),
        )

        self.assertEqual(
            self.router.route(
                "What tea did I say I prefer?", history=session_history
            ).decision,
            RouteDecision(False, "small"),
        )

    def test_real_small_rag_turn_uses_exact_authorized_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            embedder = BgeOnnxEmbedder(
                self.config.embedding.model_directory,
                self.config.embedding.intra_op_threads,
            )
            store = MemoryStore(
                Path(directory) / "memory.sqlite3",
                profile_id="fictional_live_test",
                embedder=embedder,
            )
            item = store.remember(
                "User prefers jasmine tea without sugar.",
                kind="preference",
            )
            conversation = Conversation(
                self.client,
                system_prompt=self.config.conversation.system_prompt,
                router=self.router,
                retriever=HybridRetriever(store),
                small_model=self.config.ollama.small_model,
                large_model=self.config.ollama.large_model,
                context_length=self.config.generation.context_length,
                max_output_tokens=self.config.generation.max_output_tokens,
            )

            reply = conversation.send("What kind of tea do I prefer?")

        self.assertEqual(reply.route.decision, RouteDecision(True, "small"))
        self.assertEqual(
            tuple(match.memory.id for match in reply.retrieval), (item.id,)
        )
        self.assertEqual(reply.response.memory_used, (item.id,))
        self.assertEqual(reply.generation.model, self.config.ollama.small_model)

    def test_real_small_non_rag_turn_requires_empty_memory_audit(self) -> None:
        class UnexpectedRetriever:
            def retrieve(self, query, *, limit=3):
                raise AssertionError("non-RAG route must not retrieve memory")

            def is_current(self, matches):
                raise AssertionError("non-RAG route must not check memory")

        conversation = Conversation(
            self.client,
            system_prompt=self.config.conversation.system_prompt,
            router=self.router,
            retriever=UnexpectedRetriever(),
            small_model=self.config.ollama.small_model,
            large_model=self.config.ollama.large_model,
            context_length=self.config.generation.context_length,
            max_output_tokens=self.config.generation.max_output_tokens,
        )

        reply = conversation.send("Say hello in one short sentence.")

        self.assertEqual(reply.route.decision, RouteDecision(False, "small"))
        self.assertEqual(reply.retrieval, ())
        self.assertEqual(reply.response.memory_used, ())
        self.assertEqual(reply.generation.model, self.config.ollama.small_model)


if __name__ == "__main__":
    unittest.main()
