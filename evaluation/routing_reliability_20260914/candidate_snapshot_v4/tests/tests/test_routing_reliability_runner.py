"""Offline diagnostic-runner checks; no model server or embedding inference."""

from contextlib import ExitStack, redirect_stdout, redirect_stderr
from dataclasses import asdict
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_routing_reliability as runner

from oline_hri.ollama import ChatMessage, ChatResult
from oline_hri.dependency_classifier import DependencyPrediction
from oline_hri.dependency_review import DEPENDENCY_REVIEW_SCHEMA, REVIEW_VARIANT
from oline_hri.semantic_routing import ANSWERABILITY_SCHEMA, SEMANTIC_MODE_SCHEMA


def dep(mode="none", *, uncertain=False):
    return dict(form="request", mode=mode, uncertain=uncertain, general_request="",
                missing_fact={"none": "", "required": "stored personal fact", "clarify": "request context"}[mode])


class Client:
    def __init__(self, payloads=(), *, cleanup_error=None):
        self.payloads, self.calls = list(payloads), []
        self.resident_model, self.unloaded = None, False
        self.cleanup_error = cleanup_error

    def chat(self, model, messages, **kwargs):
        self.calls.append((model, messages, kwargs))
        self.resident_model = model
        schema = kwargs.get("response_format")
        value = ({"answer_source": "current_inputs"} if schema is ANSWERABILITY_SCHEMA
                 else self.payloads.pop(0))
        if isinstance(value, BaseException):
            raise value
        if isinstance(value, ChatResult):
            return value
        if schema is SEMANTIC_MODE_SCHEMA:
            value = {key: value[key] for key in ("form", "mode")}
        return ChatResult(model, json.dumps(value), "stop", 100, 3, 12, 8, 7, 90)

    def unload_all(self):
        self.unloaded = True
        if self.cleanup_error:
            raise self.cleanup_error


def case(**updates):
    return dict(id="example", text="Explain a lever.", prior_turns=[], expected_modes=["none"], **updates)


def learned_prediction(mode="none", *, uncertain=False):
    return DependencyPrediction(
        mode="clarify" if uncertain else mode, predicted_mode=mode,
        scores={key: (0.05 if uncertain else 1.0) if key == mode else 0.0
                for key in ("none", "optional", "required", "clarify")},
        margin=0.05 if uncertain else 1.0, threshold=0.2,
        uncertain=uncertain, general_request="",
        model_manifest={"schema_version": "dependency_classifier_v1",
                        "fingerprint": "offline-runner-fixture",
                        "training": {"corpus_sha256": "offline-fixture-corpus"}},
    )


def reviewed_dependency(mode, *, model):
    return ChatResult(model, json.dumps({"needs_personal_facts": mode == "required"}),
                      "stop", 123, 5, 20, 9, 11, 99)


class RoutingReliabilityRunnerTests(unittest.TestCase):
    def run_main(self, temporary, cases, client, *, stage="routing", policy="semantic", extra_patches=()):
        source = Path(temporary) / "cases.json"
        source.write_text(json.dumps(cases))
        output = Path(temporary) / "output"
        with ExitStack() as stack:
            factory = stack.enter_context(patch.object(runner, "OllamaClient", return_value=client))
            for item in extra_patches:
                stack.enter_context(item)
            stack.enter_context(redirect_stdout(io.StringIO()))
            arguments = ["--cases", str(source), "--output-dir", str(output), "--stage", stage]
            if policy is not None:
                arguments.extend(("--policy", policy))
            code = runner.main(arguments)
        return code, output, factory

    def test_case_validation_accepts_legacy_unscored_and_rejects_malformed_cases(self):
        valid = dict(id="old", text="Which one?", prior_turns=[], expected_memory=None)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "cases.json"
            path.write_text(json.dumps({"cases": [valid]}))
            self.assertEqual(runner.load_cases(path), [valid])
            invalid = [[], [valid, valid], [{**valid, "expected_memory": "false"}],
                       [{**valid, "expected_modes": None}], [{**valid, "expected_modes": ["unknown"]}],
                       [{**valid, "prior_turns": [{"role": "system", "content": "bad"}]}],
                       [{**valid, "prior_turns": [{"role": [], "content": "bad"}]}],
                       [dict(id="x", text="Hello")]]
            for value in invalid:
                path.write_text(json.dumps(value))
                with self.subTest(value=value), self.assertRaises(ValueError):
                    runner.load_cases(path)

    def test_existing_output_is_not_overwritten_or_used_for_inference(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(runner, "OllamaClient") as client:
            source = Path(temporary) / "cases.json"
            source.write_text(json.dumps([case()]))
            output = Path(temporary) / "old"
            output.mkdir()
            sentinel = output / "sentinel"
            sentinel.write_text("keep")
            with self.assertRaises(FileExistsError):
                runner.main(["--cases", str(source), "--output-dir", str(output)])
            self.assertEqual(sentinel.read_text(), "keep")
            client.assert_not_called()

    def test_legacy_conversation_combination_is_rejected_before_loading(self):
        with patch.object(runner, "load_cases") as loader, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                runner.main(["--cases", "missing", "--output-dir", "missing-out",
                             "--policy", "legacy", "--stage", "conversation"])
            loader.assert_not_called()

    def test_routing_records_hashes_raw_results_and_excludes_labels_from_prompts(self):
        client = Client([dep(), {"model_size": "small"}])
        fixture = case()
        fixture["hidden_label_note"] = "DO_NOT_SEND_RELEASE_LABELS_482"
        with tempfile.TemporaryDirectory() as temporary:
            code, output, factory = self.run_main(temporary, [fixture], client)
            self.assertEqual(code, 0)
            self.assertTrue(client.unloaded)
            self.assertTrue(factory.call_args.kwargs["retain_large_model"])
            metadata = json.loads((output / "metadata.json").read_text())
            self.assertEqual(metadata["schema_version"], runner.VERSION)
            self.assertEqual(len(metadata["cases_sha256"]), 64)
            self.assertEqual(len(metadata["config_sha256"]), 64)
            self.assertTrue(metadata["source_sha256"])
            row = json.loads((output / "observations.jsonl").read_text())
            self.assertEqual(row["diagnostic"], {"label_match": True, "outcome": "routed_general", "label_basis": "semantic_modes"})
            self.assertEqual(row["route"]["memory_required_generation"]["total_duration_ns"], 100)
            calls = [json.loads(line) for line in (output / "model_calls.jsonl").read_text().splitlines()]
            self.assertEqual(len(calls), 3)
            self.assertEqual(json.loads(row["route"]["answerability_generation"]["content"]),
                             {"answer_source": "current_inputs"})
            for call in calls:
                self.assertGreaterEqual(call["wall_ns"], 0)
                prompt = json.dumps(call["messages"])
                self.assertNotIn(fixture["hidden_label_note"], prompt)
                self.assertNotIn("expected_modes", prompt)

    def test_raw_large_review_and_final_clarification_are_distinct(self):
        client = Client([dep("required"), {"model_size": "small"}, dep("clarify")])
        with tempfile.TemporaryDirectory() as temporary:
            _, output, _ = self.run_main(temporary, [case()], client)
            row = json.loads((output / "observations.jsonl").read_text())
            self.assertEqual(row["route"]["review_reason"], "required_dependency")
            self.assertIsNotNone(row["route"]["review_generation"])
            self.assertEqual(row["diagnostic"], {"label_match": False, "outcome": "clarification", "label_basis": "semantic_modes"})
            summary = json.loads((output / "summary.json").read_text())
            self.assertEqual(summary["outcomes"], {"clarification": 1})
            self.assertEqual(summary["label_matches"], 0)

    def test_learned_route_preserves_classifier_metadata_without_fabricated_generations(self):
        fixture = case()
        fixture["hidden_label_note"] = "LABELS_MUST_NOT_ENTER_CLASSIFIER_725"
        fixture["prior_turns"] = [
            {"role": "user", "content": "Explain a pulley."},
            {"role": "assistant", "content": "A pulley redirects force through a rope and wheel."},
        ]
        raw = learned_prediction()
        classifier = Mock()
        classifier.classify.return_value = raw
        client = Client([{"model_size": "small"}])
        with tempfile.TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            output = Path(temporary)
            backend = runner.RecordingBackend(client, output / "model_calls.jsonl")
            rows = runner.run_cases(
                [fixture], runner.load_config(), backend, output,
                stage="routing", policy="learned", classifier=classifier,
            )
            row = json.loads((output / "observations.jsonl").read_text())
            self.assertEqual(rows, [row])
            self.assertEqual(row["status"], "ok")
            route = row["route"]
            self.assertEqual(route["classifier_metadata"]["whole_request"], asdict(raw))
            self.assertEqual(route["policy"], "dependency_v1")
            for name in ("memory_required_generation", "review_generation", "answerability_generation"):
                self.assertIsNone(route[name])
            self.assertEqual(json.loads(route["model_size_generation"]["content"]), {"model_size": "small"})
            classifier.classify.assert_called_once_with(
                fixture["text"], history=tuple(ChatMessage(**item) for item in fixture["prior_turns"]),
            )
            self.assertEqual(len(row["calls"]), 1)
            encoded_input = json.dumps(row["calls"][0]["messages"])
            self.assertNotIn(fixture["hidden_label_note"], encoded_input)
            self.assertNotIn("expected_modes", encoded_input)

    def test_main_defaults_to_learned_and_constructs_classifier_without_personal_store(self):
        classifier = Mock()
        classifier.classify.return_value = learned_prediction()
        client = Client([{"model_size": "small"}])
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(runner, "BgeOnnxEmbedder") as embedder, \
                patch.object(runner, "DependencyClassifier", return_value=classifier) as factory, \
                patch.object(runner, "MemoryStore") as store, \
                patch.object(runner, "SemanticRouter") as semantic:
            code, output, _ = self.run_main(temporary, [case()], client, policy=None)
            self.assertEqual(code, 0)
            embedder.assert_called_once()
            factory.assert_called_once_with(embedder.return_value)
            store.assert_not_called()
            semantic.assert_not_called()
            self.assertTrue(client.unloaded)
            metadata = json.loads((output / "metadata.json").read_text())
            self.assertEqual(metadata["policy"], "learned")
            self.assertEqual(metadata["schema_version"], "routing_reliability_v2")
            row = json.loads((output / "observations.jsonl").read_text())
            self.assertEqual(row["route"]["classifier_metadata"]["whole_request"],
                             asdict(classifier.classify.return_value))
            self.assertEqual(len(client.calls), 1)
            self.assertEqual(row["diagnostic"]["outcome"], "routed_general")

    def test_accepted_required_route_preserves_local_decision_without_dependency_review(self):
        raw = learned_prediction("required")
        classifier = Mock()
        classifier.classify.return_value = raw
        client = Client([{"model_size": "small"}])
        fixture = {**case(), "text": "Which room did I reserve?", "expected_modes": ["required"]}
        with tempfile.TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            output = Path(temporary)
            backend = runner.RecordingBackend(client, output / "model_calls.jsonl")
            runner.run_cases([fixture], runner.load_config(), backend, output,
                             stage="routing", policy="learned", classifier=classifier)
            row = json.loads((output / "observations.jsonl").read_text())
            self.assertEqual(row["status"], "ok")
            route = row["route"]
            self.assertEqual(route["dependency"]["mode"], "required")
            self.assertEqual(route["classifier_metadata"]["whole_request"], asdict(raw))
            self.assertEqual(route["memory_decision_source"], "dependency_classifier")
            self.assertIsNone(route["memory_required_generation"])
            self.assertIsNone(route["review_generation"])
            self.assertIsNone(route["review_reason"])
            self.assertEqual(len(row["calls"]), 1)
            self.assertTrue(row["diagnostic"]["label_match"])

    def test_uncertain_routes_preserve_actual_dependency_review(self):
        config = runner.load_config()
        for mode, uncertain, request in (
            ("required", True, "Which room did I reserve?"),
            ("none", True, "Explain a lever."),
        ):
            with self.subTest(mode=mode, uncertain=uncertain), \
                    tempfile.TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
                raw = learned_prediction(mode, uncertain=uncertain)
                classifier = Mock()
                classifier.classify.return_value = raw
                review = reviewed_dependency(mode, model=config.ollama.large_model)
                client = Client([{"model_size": "small"}, review])
                output = Path(temporary)
                backend = runner.RecordingBackend(client, output / "model_calls.jsonl")
                fixture = {**case(), "text": request, "expected_modes": [mode]}
                runner.run_cases([fixture], config, backend, output, stage="routing",
                                 policy="learned", classifier=classifier)
                row = json.loads((output / "observations.jsonl").read_text())
                route = row["route"]
                self.assertEqual(row["status"], "ok")
                self.assertEqual(route["dependency"]["mode"], mode)
                self.assertFalse(route["dependency"]["uncertain"])
                self.assertEqual(route["classifier_metadata"]["whole_request"], asdict(raw))
                self.assertEqual(route["review_generation"], asdict(review))
                self.assertEqual(route["review_reason"], "memory_uncertain")
                self.assertEqual(route["memory_decision_source"], "dependency_review")
                self.assertIsNone(route["memory_required_generation"])
                self.assertEqual([call["model"] for call in row["calls"]],
                                 [config.ollama.small_model, config.ollama.large_model])
                self.assertEqual(row["calls"][1]["result"], asdict(review))
                review_input = json.loads(row["calls"][1]["messages"][-1]["content"])
                self.assertEqual(review_input["current_message"], request)
                self.assertNotIn("proposed_mode", review_input)
                self.assertNotIn("expected_modes", review_input)
                self.assertNotIn("scores", review_input)
                self.assertEqual(row["calls"][1]["options"]["response_format"], DEPENDENCY_REVIEW_SCHEMA)
                self.assertEqual(route["classifier_metadata"]["review"]["variant"], REVIEW_VARIANT)
                self.assertIs(route["classifier_metadata"]["review"]["needs_personal_facts"],
                              mode == "required")

    def test_accepted_required_mixed_request_retains_raw_fragment_checks_without_model_review(self):
        recall = "Which room did I reserve?"
        fragment = "Explain how door hinges work."
        whole, general, personal = (learned_prediction("required"), learned_prediction("none"),
                                    learned_prediction("required"))
        classifier = Mock()
        classifier.classify.side_effect = (whole, general, personal)
        fixture = {**case(), "text": recall + " " + fragment, "expected_modes": ["required"]}
        client = Client([{"model_size": "small"}])
        with tempfile.TemporaryDirectory() as temporary:
            code, output, _ = self.run_main(temporary, [fixture], client, policy="learned", extra_patches=(
                patch.object(runner, "BgeOnnxEmbedder"),
                patch.object(runner, "DependencyClassifier", return_value=classifier),
            ))
            self.assertEqual(code, 0)
            route = json.loads((output / "observations.jsonl").read_text())["route"]
            self.assertEqual(route["dependency"]["mode"], "required")
            self.assertEqual(route["dependency"]["general_request"], fragment)
            self.assertIsNone(route["review_generation"])
            self.assertEqual(route["classifier_metadata"]["whole_request"], asdict(whole))
            checks = route["classifier_metadata"]["fragment_checks"]
            self.assertEqual([item["prediction"] for item in checks], [asdict(general), asdict(personal)])
            self.assertEqual([item.args[0] for item in classifier.classify.call_args_list],
                             [fixture["text"], fragment, recall])
            self.assertEqual(len(client.calls), 1)

    def test_malformed_learned_review_is_recorded_then_clarifies_without_another_review(self):
        config = runner.load_config()
        raw = learned_prediction("none", uncertain=True)
        classifier = Mock()
        classifier.classify.return_value = raw
        broken = ChatResult(config.ollama.large_model, '{"invalid":true}', "stop", 123, 5, 20, 9, 11, 99)
        client = Client([{"model_size": "small"}, broken])
        with tempfile.TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            output = Path(temporary)
            backend = runner.RecordingBackend(client, output / "model_calls.jsonl")
            runner.run_cases([case()], config, backend, output, stage="routing",
                             policy="learned", classifier=classifier)
            row = json.loads((output / "observations.jsonl").read_text())
            self.assertEqual(row["status"], "ok")
            self.assertEqual(row["route"]["review_generation"], asdict(broken))
            self.assertEqual(row["route"]["dependency"]["mode"], "clarify")
            self.assertEqual(row["route"]["classifier_metadata"]["review"]["error"]["type"], "RoutingError")
            self.assertFalse(row["diagnostic"]["label_match"])
            self.assertEqual(row["diagnostic"]["outcome"], "clarification")
            self.assertEqual(len(row["calls"]), 2)

    def test_legacy_boolean_schema_remains_supported(self):
        client = Client([{"form": "request", "memory_required": False}, {"model_size": "small"}])
        old = dict(id="legacy", text="Explain a lever.", prior_turns=[], expected_memory=False)
        with tempfile.TemporaryDirectory() as temporary:
            code, output, _ = self.run_main(temporary, [old], client, policy="legacy")
            self.assertEqual(code, 0)
            row = json.loads((output / "observations.jsonl").read_text())
            self.assertTrue(row["diagnostic"]["label_match"])
            self.assertNotIn("dependency", row["route"])

    def test_legacy_mode_projection_leaves_clarification_unscored(self):
        row = {"status": "ok", "route": {"decision": {"memory_required": False}}}
        self.assertTrue(runner._assess(case(), row)["label_match"])
        fixture = case()
        fixture["expected_modes"] = ["clarify"]
        scored = runner._assess(fixture, row)
        self.assertIsNone(scored["label_match"])
        self.assertEqual(scored["label_basis"], "legacy_boolean_projection")

    def test_conversation_serializes_actual_attempts_reviews_and_isolated_store(self):
        client = Client([dep(), {"model_size": "small"},
                         {"speech": "A lever is a rigid bar that turns around a pivot.",
                          "gesture_id": "NO_ACTION", "memory_used": []},
                         {"verdict": "pass", "reason": "supported_answer"}])
        store_factory = patch.object(runner, "MemoryStore")
        embedder_factory = patch.object(runner, "BgeOnnxEmbedder")
        empty = SimpleNamespace(retrieve=lambda *args, **kwargs: (), is_current=lambda matches: True)
        with tempfile.TemporaryDirectory() as temporary, store_factory as store, embedder_factory as embedder:
            code, output, _ = self.run_main(temporary, [case()], client, stage="conversation",
                                           extra_patches=[patch.object(runner, "HybridRetriever", return_value=empty)])
            self.assertEqual(code, 0)
            store.assert_called_once()
            self.assertEqual(Path(store.call_args.args[0]), output / "memory.sqlite3")
            self.assertIs(store.call_args.kwargs["embedder"], embedder.return_value)
            store.return_value.list_memories.assert_called_once()
            row = json.loads((output / "observations.jsonl").read_text())
            self.assertEqual(row["reply"]["effective_mode"], "none")
            self.assertEqual(row["reply"]["retrieval_status"], "skipped")
            self.assertEqual(len(row["reply"]["attempts"]), 1)
            self.assertEqual(len(row["reply"]["answer_reviews"]), 1)
            self.assertEqual(row["diagnostic"]["outcome"], "general_answer")

    def test_history_admission_excludes_old_personal_values_and_their_followups(self):
        conversation = SimpleNamespace(_messages=[ChatMessage("system", "rules")])
        old = [ChatMessage("user", "My meeting starts at 09:42."),
               ChatMessage("assistant", "Your meeting starts at 09:42."),
               ChatMessage("user", "Why?"), ChatMessage("assistant", "That is the planned time.")]
        self.assertEqual(runner._admit_history(conversation, old), 0)
        self.assertTrue(conversation._last_turn_withheld)
        safe = [ChatMessage("user", "Explain why leaves change color."),
                ChatMessage("assistant", "Leaf pigments become visible as chlorophyll decreases.")]
        self.assertEqual(runner._admit_history(conversation, old + safe), 2)
        self.assertFalse(conversation._last_turn_withheld)
        self.assertNotIn("09:42", json.dumps([message.to_dict() for message in conversation._messages]))

    def test_draft_edit_history_matches_production_admission(self):
        conversation = SimpleNamespace(_messages=[ChatMessage("system", "rules")])
        history = [
            ChatMessage("user", "Draft a fictional note declining an invitation."),
            ChatMessage("assistant", "I am unable to attend."),
            ChatMessage("user", "Make it more direct."),
            ChatMessage("assistant", "I am not attending."),
        ]
        self.assertEqual(runner._admit_history(conversation, history), 4)
        self.assertFalse(conversation._last_turn_withheld)
        self.assertEqual(conversation._messages[1:], history)
        self.assertEqual(runner.ReliableConversation._safe_history(conversation), tuple(history))

    def test_withheld_personal_pair_clears_draft_provenance(self):
        conversation = SimpleNamespace(_messages=[ChatMessage("system", "rules")])
        history = [
            ChatMessage("user", "Draft a fictional note declining an invitation."),
            ChatMessage("assistant", "I am unable to attend."),
            ChatMessage("user", "My parcel arrives Thursday."),
            ChatMessage("assistant", "Your parcel arrives Thursday."),
            ChatMessage("user", "Make it more direct."),
            ChatMessage("assistant", "I am not attending."),
        ]
        self.assertEqual(runner._admit_history(conversation, history), 0)
        self.assertTrue(conversation._last_turn_withheld)
        self.assertEqual(conversation._messages, [ChatMessage("system", "rules")])

    def test_case_error_is_flushed_and_cleanup_runs_even_after_interrupt(self):
        for error in (RuntimeError("controlled guard failure"), KeyboardInterrupt("controlled stop")):
            client = Client([error])
            with self.subTest(error=type(error)), tempfile.TemporaryDirectory() as temporary:
                code, output, _ = self.run_main(temporary, [case()], client)
                self.assertEqual(code, 1)
                self.assertTrue(client.unloaded)
                row = json.loads((output / "observations.jsonl").read_text())
                call = json.loads((output / "model_calls.jsonl").read_text())
                self.assertEqual(row["error"]["type"], type(error).__name__)
                self.assertEqual(call["error"]["message"], str(error))
                self.assertEqual(row["diagnostic"]["outcome"], "error")
                summary = json.loads((output / "summary.json").read_text())
                self.assertEqual(summary["completed"], 1)

    def test_setup_and_cleanup_failures_are_preserved(self):
        client = Client(cleanup_error=RuntimeError("cleanup failed"))
        with tempfile.TemporaryDirectory() as temporary:
            code, output, _ = self.run_main(temporary, [case()], client, stage="conversation",
                                           extra_patches=[patch.object(runner, "BgeOnnxEmbedder",
                                                                        side_effect=RuntimeError("setup failed"))])
            self.assertEqual(code, 1)
            summary = json.loads((output / "summary.json").read_text())
            self.assertEqual(summary["failure"]["message"], "setup failed")
            self.assertEqual(summary["cleanup_error"]["message"], "cleanup failed")

    def test_retrieval_errors_are_persisted_even_if_conversation_recovers(self):
        with tempfile.TemporaryDirectory() as temporary:
            def fail(*args, **kwargs):
                raise RuntimeError("embedding unavailable")
            retriever = runner.RecordingRetriever(SimpleNamespace(retrieve=fail), Path(temporary) / "retrieval.jsonl")
            retriever.case_id = "sample"
            with self.assertRaises(RuntimeError):
                retriever.retrieve("query", limit=3)
            row = json.loads((Path(temporary) / "retrieval.jsonl").read_text())
            self.assertEqual(row["case_id"], "sample")
            self.assertEqual(row["status"], "error")
            self.assertEqual(row["error"]["message"], "embedding unavailable")


if __name__ == "__main__":
    unittest.main()
