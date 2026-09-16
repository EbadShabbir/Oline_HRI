"""Offline live CLI delivery checks using synthetic temporary memory only."""

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from oline_hri import cli
from oline_hri.config import load_config
from oline_hri.dependency_classifier import DependencyPrediction
from oline_hri.memory import MemoryStore
from oline_hri.reliable_conversation import ReliableConversation
from oline_hri.retrieval import HybridRetriever

from tests.test_cli import DeterministicEmbedder, memory_config, transcription
from tests.test_conversation_routed import (
    FakeBackend, FakeRetriever, GENERAL_LARGE_MODEL, LARGE_MODEL,
    SMALL_MODEL, chat_result,
)
from tests.test_reliable_conversation import StubReviewer, reliable, semantic_route


WITHHELD = (
    "That personal information is no longer available. "
    "Could you provide the current details?"
)


class ReliableCliDeliveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.now = datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)
        self.store = MemoryStore(
            Path(temporary.name) / "fictional.sqlite3", profile_id="fictional-user",
            clock=lambda: self.now, embedder=DeterministicEmbedder(),
        )
        self.output, self.errors = StringIO(), StringIO()

    def personal_reply(self, **memory_options):
        item = self.store.remember(
            "Your camera is in the ochre cabinet.", kind="fact", **memory_options,
        )
        session, _, _, _ = reliable(
            FakeBackend(), route=semantic_route("required"),
            retriever=HybridRetriever(self.store),
        )
        reply = session.send("Where is my camera?")
        self.assertEqual(reply.response.memory_used, (item.id,))
        self.assertIn("ochre", reply.response.speech)
        return session, reply, item

    def write(self, session, reply, *, prefix=""):
        cli._write_reply(session, reply, output=self.output, errors=self.errors, prefix=prefix)

    def assert_withheld(self, session, reply):
        original_generation = reply.generation
        self.write(session, reply, prefix="robot> ")
        self.assertEqual(self.output.getvalue(), "robot> " + WITHHELD + "\n")
        self.assertIn("personal evidence changed before output; reply withheld", self.errors.getvalue())
        self.assertNotIn("ochre", self.output.getvalue() + self.errors.getvalue())
        # Withholding delivery must not rewrite the recorded raw model attempt.
        self.assertIs(reply.generation, original_generation)
        self.assertIn("ochre", reply.generation.content)

    def test_current_real_snapshot_is_delivered(self):
        session, reply, _ = self.personal_reply()
        self.write(session, reply)
        self.assertEqual(self.output.getvalue(), reply.response.speech + "\n")
        self.assertEqual(self.errors.getvalue(), "")

    def test_deleted_real_snapshot_is_withheld_at_output(self):
        session, reply, item = self.personal_reply()
        self.store.forget(item.id)
        self.assert_withheld(session, reply)

    def test_corrected_real_snapshot_is_withheld_at_output(self):
        session, reply, item = self.personal_reply()
        self.now += timedelta(seconds=1)
        self.store.correct(item.id, "Your camera is in the silver drawer.")
        self.assert_withheld(session, reply)
        self.assertNotIn("silver", self.output.getvalue())

    def test_validity_and_retention_expiry_are_checked_after_generation(self):
        for field in ("valid_until", "retention_until"):
            with self.subTest(field=field):
                self.output, self.errors = StringIO(), StringIO()
                boundary = self.now + timedelta(minutes=1)
                session, reply, _ = self.personal_reply(**{field: boundary.isoformat()})
                self.now = boundary
                self.assert_withheld(session, reply)

    def test_unsupported_guard_or_incomplete_snapshot_fails_closed(self):
        session, reply, _ = self.personal_reply()
        for broken in ("unsupported", "incomplete"):
            with self.subTest(broken=broken):
                self.output, self.errors = StringIO(), StringIO()
                if broken == "unsupported":
                    session._retriever = FakeRetriever(reply.retrieval)
                    candidate = reply
                else:
                    session._retriever = HybridRetriever(self.store)
                    candidate = replace(reply, retrieval=())
                self.assert_withheld(session, candidate)

    def test_application_and_general_replies_need_no_memory_guard(self):
        for route, request in (
            (semantic_route(), "Explain recursion."),
            (semantic_route("required", missing="personal schedule"),
             "When is my next appointment?"),
        ):
            with self.subTest(mode=route.dependency.mode):
                self.output, self.errors = StringIO(), StringIO()
                session, _, retriever, _ = reliable(
                    FakeBackend((chat_result("Recursion is a function calling itself."),)),
                    route=route,
                )
                self.assertFalse(hasattr(retriever, "disclosure_guard"))
                reply = session.send(request)
                self.write(session, reply)
                cli._report_reply_checks(reply, self.errors)
                self.assertEqual(self.output.getvalue(), reply.response.speech + "\n")
                self.assertNotIn("withheld", self.errors.getvalue())
                if route.dependency.mode == "required":
                    self.assertIsNone(reply.generation)
                    self.assertIn("generator=application attempts=0 reviews=0", self.errors.getvalue())
                else:
                    self.assertIn("attempts=1 reviews=1", self.errors.getvalue())

    def test_prompt_text_and_voice_use_the_same_guarded_writer(self):
        for path in ("prompt", "text", "voice"):
            with self.subTest(path=path):
                self.output, self.errors = StringIO(), StringIO()
                session, reply, item = self.personal_reply()
                self.store.forget(item.id)
                # The candidate was complete before transport began. Exercise
                # the actual transport with that now-stale response.
                with patch.object(session, "send", return_value=reply) as send, \
                        patch("oline_hri.cli._write_reply", wraps=cli._write_reply) as writer:
                    common = dict(
                        automatic_memory=None, output=self.output, errors=self.errors,
                        show_memory_ids=True, show_route=True,
                    )
                    if path == "voice":
                        recognizer = Mock()
                        recognizer.listen.side_effect = [transcription("Where is my camera?"), KeyboardInterrupt()]
                        client = Mock()
                        status = cli._run_voice_chat(session, recognizer, client=client, **common)
                        self.assertGreaterEqual(client.unload_all.call_count, 2)
                    else:
                        status = cli._run_chat(
                            session, memory_store=self.store,
                            prompt="Where is my camera?" if path == "prompt" else None,
                            input_stream=StringIO("Where is my camera?\n/exit\n"), **common,
                        )
                self.assertEqual(status, 0)
                send.assert_called_once_with("Where is my camera?")
                writer.assert_called_once()
                self.assertIs(writer.call_args.args[0], session)
                self.assertIs(writer.call_args.args[1], reply)
                self.assertIn(WITHHELD, self.output.getvalue())
                self.assertNotIn("ochre", self.output.getvalue() + self.errors.getvalue())
                self.assertIn("answer> effective_mode=required", self.errors.getvalue())

    def test_optional_and_mixed_missing_memory_deliver_the_checked_general_part(self):
        fragment = "Explain how batteries work."
        speech = "Batteries convert chemical energy into electrical energy."
        for route, request in (
            (semantic_route("optional"), fragment),
            (semantic_route("required", missing="personal schedule", fragment=fragment),
             "When is my next appointment? " + fragment),
        ):
            with self.subTest(mode=route.dependency.mode):
                self.output, self.errors = StringIO(), StringIO()
                session, _, _, _ = reliable(FakeBackend((chat_result(speech),)), route=route)
                reply = session.send(request)
                self.assertIsNotNone(reply.generation)
                self.assertEqual(reply.response.memory_used, ())
                self.write(session, reply)
                self.assertIn(speech, self.output.getvalue())
                self.assertEqual(self.errors.getvalue(), "")
                if route.dependency.mode == "required":
                    self.assertIn("time or date", self.output.getvalue())

    def test_diagnostics_finish_before_final_authorization(self):
        session, reply, item = self.personal_reply()
        store = self.store

        class RevokingDiagnostics(StringIO):
            revoked = False

            def write(self, value):
                if value.startswith("answer> effective_mode=") and not self.revoked:
                    store.forget(item.id)
                    self.revoked = True
                return super().write(value)

        errors = RevokingDiagnostics()
        with patch.object(session, "send", return_value=reply):
            status = cli._run_chat(
                session, memory_store=store, automatic_memory=None,
                prompt="Where is my camera?", input_stream=StringIO(),
                output=self.output, errors=errors, show_memory_ids=True, show_route=True,
            )
        self.assertEqual(status, 0)
        self.assertTrue(errors.revoked)
        self.assertEqual(self.output.getvalue(), WITHHELD + "\n")
        self.assertNotIn("ochre", self.output.getvalue())

    def test_verified_mixed_prefix_reports_application_evidence_and_remains_guarded(self):
        item = self.store.remember("Your camera is in the ochre cabinet.", kind="fact")
        fragment = "Explain how batteries work."
        general = "Batteries convert chemical energy into electrical energy."
        session, _, _, reviewer = reliable(
            FakeBackend((chat_result(general),)),
            route=semantic_route("required", fragment=fragment),
            retriever=HybridRetriever(self.store),
        )
        reply = session.send("Where is my camera? " + fragment)
        self.assertIn("ochre", reply.response.speech)
        self.assertIn(general, reply.response.speech)
        self.assertEqual(reply.response.memory_used, (item.id,))
        self.assertEqual(reply.application_memory_ids, (item.id,))
        self.assertEqual(reply.memory_diagnostics.supplied_ids, ())
        self.assertEqual(reply.memory_diagnostics.model_used_ids, ())
        self.assertEqual(json.loads(reply.generation.content)["memory_used"], [])
        self.assertNotIn("ochre", reply.generation.content)
        self.assertEqual(reviewer.calls[0]["answer"], reply.response.speech)
        cli._report_memory_ids(reply, self.errors)
        diagnostics = json.loads(self.errors.getvalue().removeprefix("memory> "))
        self.assertEqual(diagnostics["application_used_ids"], [item.id])
        self.assertEqual(diagnostics["response_used_ids"], [item.id])
        self.assertEqual(diagnostics["supplied_ids"], [])
        self.assertEqual(diagnostics["model_used_ids"], [])
        self.store.forget(item.id)
        self.write(session, reply)
        self.assertEqual(self.output.getvalue(), WITHHELD + "\n")
        self.assertNotIn("ochre", self.output.getvalue() + self.errors.getvalue())


class ReliableCliConstructionTests(unittest.TestCase):
    def test_explicit_reliable_policy_preserves_roles_and_reports_actual_attempts(self):
        self.assert_reliable_construction(("--routing-policy", "reliable"))

    def test_default_policy_uses_actual_learned_reliable_construction(self):
        self.assertEqual(cli.build_parser().parse_args(["chat"]).routing_policy, "reliable")
        self.assert_reliable_construction(())

    def assert_reliable_construction(self, routing_options):
        class RoutingBackend(FakeBackend):
            def chat(self, model, messages, *, response_format=None, **options):
                return super().chat(model, messages, response_format=response_format)

        with tempfile.TemporaryDirectory() as directory:
            config = load_config(memory_config(directory))
            # Distinct synthetic roles expose accidental model-role collapse;
            # this tests wiring rather than the separate deployment validator.
            config = replace(config, ollama=replace(config.ollama, large_model=LARGE_MODEL))
            for proposed, uncertain, reviewed_mode, size, expected_model in (
                ("none", False, None, "small", SMALL_MODEL),
                ("none", False, None, "large", GENERAL_LARGE_MODEL),
                ("required", False, None, "large", LARGE_MODEL),
                ("none", True, "none", "small", SMALL_MODEL),
                ("required", True, "none", "small", SMALL_MODEL),
            ):
                mode = reviewed_mode or proposed
                with self.subTest(proposed=proposed, uncertain=uncertain, resolved=mode, size=size):
                    if mode == "required":
                        store = MemoryStore(config.memory.database_path,
                                            profile_id=config.memory.profile_id,
                                            embedder=DeterministicEmbedder())
                        store.remember("Your camera is in the ochre cabinet.", kind="fact")
                    outcomes = [chat_result(raw=json.dumps({"model_size": size}))]
                    dependency_review = None
                    if reviewed_mode is not None:
                        dependency_review = chat_result(
                            raw=json.dumps({"needs_personal_facts": reviewed_mode == "required"}),
                            model=LARGE_MODEL,
                        )
                        outcomes.append(dependency_review)
                    if mode != "required":
                        outcomes.append(
                            chat_result("Recursion is a function calling itself.", model=expected_model),
                        )
                    backend = RoutingBackend(outcomes)
                    backend.unload_all = Mock()
                    prediction = DependencyPrediction(
                        mode="clarify" if uncertain else proposed, predicted_mode=proposed,
                        scores={key: (0.05 if uncertain else 1.0) if key == proposed else 0.0
                                for key in ("none", "optional", "required", "clarify")},
                        margin=0.05 if uncertain else 1.0, threshold=0.2,
                        uncertain=uncertain, general_request="",
                        model_manifest={"fingerprint": "offline-cli-fixture"},
                    )
                    classifier = Mock()
                    classifier.classify.return_value = prediction
                    embedder = DeterministicEmbedder()
                    reviewer, instances = StubReviewer(), []

                    class RecordingConversation(ReliableConversation):
                        def __init__(self, *args, **kwargs):
                            self.construction_options = dict(kwargs)
                            super().__init__(*args, reviewer=reviewer, **kwargs)
                            instances.append(self)

                        def send(self, text):
                            self.last_reply = super().send(text)
                            return self.last_reply

                    output, errors = StringIO(), StringIO()
                    with patch("oline_hri.cli.load_config", return_value=config), \
                            patch("oline_hri.cli.OllamaClient", return_value=backend) as client_class, \
                            patch("oline_hri.cli.BgeOnnxEmbedder", return_value=embedder), \
                            patch("oline_hri.cli.DependencyClassifier", return_value=classifier) as classifier_class, \
                            patch("oline_hri.cli.LearnedSemanticRouter", wraps=cli.LearnedSemanticRouter) as router_class, \
                            patch("oline_hri.cli.ReliableConversation", RecordingConversation):
                        status = cli.main(
                            ["chat", *routing_options, "--show-route", "--show-memory-ids",
                             "--prompt", "Where is my camera?" if mode == "required" else "Explain recursion."],
                            stdout=output, stderr=errors, stdin=StringIO(),
                        )
                    self.assertEqual(status, 0, errors.getvalue())
                    self.assertEqual(client_class.call_args.kwargs, {"retain_large_model": True})
                    classifier_class.assert_called_once_with(embedder)
                    router_class.assert_called_once_with(
                        backend, small_model=SMALL_MODEL, large_model=LARGE_MODEL,
                        classifier=classifier,
                    )
                    classifier.classify.assert_called_once_with(
                        "Where is my camera?" if mode == "required" else "Explain recursion.", history=(),
                    )
                    self.assertEqual(len(instances), 1)
                    options = instances[0].construction_options
                    self.assertEqual((options["small_model"], options["general_large_model"], options["large_model"]),
                                     (SMALL_MODEL, GENERAL_LARGE_MODEL, LARGE_MODEL))
                    self.assertEqual(options["context_length"], config.generation.context_length)
                    self.assertEqual(options["max_output_tokens"], config.generation.max_output_tokens)
                    self.assertTrue(options["runtime_facts"])
                    self.assertTrue(reviewer.calls, (output.getvalue(), errors.getvalue(), backend.calls))
                    self.assertEqual(reviewer.calls[0]["deployment_facts"], options["runtime_facts"])
                    expected_calls = [SMALL_MODEL]
                    if dependency_review is not None:
                        expected_calls.append(LARGE_MODEL)
                    self.assertEqual([call[0] for call in backend.calls], [*expected_calls, expected_model])
                    reply = instances[0].last_reply
                    self.assertIs(reply.route.review_generation, dependency_review)
                    self.assertEqual(reply.route.classifier_metadata["whole_request"], asdict(prediction))
                    self.assertEqual(reply.effective_mode, mode)
                    self.assertEqual(reply.attempted_models, (expected_model,))
                    if mode == "none":
                        self.assertEqual(reply.retrieval_status, "skipped")
                        self.assertEqual(reply.response.memory_used, ())
                    self.assertIn(f"selected_generator={expected_model}", errors.getvalue())
                    self.assertIn(f"memory_mode={mode}", errors.getvalue())
                    source = "dependency_review" if dependency_review is not None else "dependency_classifier"
                    self.assertIn(f"policy=dependency_v1 dependency_source={source}", errors.getvalue())
                    self.assertIn(f"generator={expected_model} attempts=1 reviews=1", errors.getvalue())
                    self.assertIn("memory> ", errors.getvalue())
                    self.assertNotIn("ochre", errors.getvalue())
                    self.assertNotIn("Recursion", errors.getvalue())
                    backend.unload_all.assert_called_once()


if __name__ == "__main__":
    unittest.main()
