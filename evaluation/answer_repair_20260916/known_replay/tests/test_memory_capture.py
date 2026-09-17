from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from oline_hri.memory import MemoryStore
from oline_hri.memory_capture import (
    CAPTURE_SEED,
    CAPTURE_TEMPERATURE,
    MEMORY_CAPTURE_SCHEMA,
    AutomaticMemoryCapture,
    AutomaticMemoryClassifier,
    MemoryCaptureDecision,
    MemoryCaptureError,
    automatic_memory_candidate,
    parse_memory_capture_decision,
)
from oline_hri.ollama import ChatResult


def result(content: str, *, model: str = "qwen3:0.6b") -> ChatResult:
    return ChatResult(
        model=model,
        content=content,
        done_reason="stop",
        total_duration_ns=1,
        load_duration_ns=0,
        prompt_eval_count=1,
        eval_count=1,
        eval_duration_ns=1,
    )


class FakeBackend:
    def __init__(self, response: ChatResult) -> None:
        self.response = response
        self.calls = []

    def chat(
        self,
        model,
        messages,
        *,
        response_format=None,
        temperature=None,
        seed=None,
    ):
        self.calls.append(
            (model, tuple(messages), response_format, temperature, seed)
        )
        return self.response


class StubClassifier:
    def __init__(self, decision: MemoryCaptureDecision) -> None:
        self.decision = decision
        self.calls = []

    def classify(self, text: str) -> MemoryCaptureDecision:
        self.calls.append(text)
        return self.decision


class AutomaticMemoryCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.database = Path(self.temporary_directory.name) / "memory.sqlite3"
        self.now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)

    def store(self) -> MemoryStore:
        return MemoryStore(
            self.database,
            profile_id="automatic_test",
            retention_days=7,
            clock=lambda: self.now,
        )

    def test_classifier_uses_deterministic_local_singleton_contract(self) -> None:
        backend = FakeBackend(
            result('{"store_memory":true,"kind":"preference"}')
        )
        classifier = AutomaticMemoryClassifier(backend, model="qwen3:0.6b")

        decision = classifier.classify("I prefer jasmine tea.")

        self.assertEqual(decision, MemoryCaptureDecision(True, "preference"))
        self.assertEqual(len(backend.calls), 1)
        model, messages, schema, temperature, seed = backend.calls[0]
        self.assertEqual(model, "qwen3:0.6b")
        self.assertEqual(schema, MEMORY_CAPTURE_SCHEMA)
        self.assertEqual(temperature, CAPTURE_TEMPERATURE)
        self.assertEqual(seed, CAPTURE_SEED)
        self.assertIn("untrusted JSON", messages[-1].content)
        self.assertIn("I prefer jasmine tea.", messages[-1].content)

    def test_parser_rejects_malformed_or_inconsistent_decisions(self) -> None:
        invalid = (
            "not json",
            "[]",
            '{"store_memory":1,"kind":"fact"}',
            '{"store_memory":true,"kind":"none"}',
            '{"store_memory":false,"kind":"fact"}',
            '{"store_memory":false,"kind":"none","extra":1}',
            '{"store_memory":false,"store_memory":true,"kind":"fact"}',
            '{"store_memory":NaN,"kind":"none"}',
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(MemoryCaptureError):
                    parse_memory_capture_decision(value)

        self.assertEqual(
            parse_memory_capture_decision(
                '{"store_memory":false,"kind":"none"}'
            ),
            MemoryCaptureDecision(False, None),
        )

    def test_prefilter_skips_questions_nonpersonal_text_and_secrets(self) -> None:
        for text in (
            "What tea do I prefer?",
            "what is my preferred tea",
            "Explain how a memory database works.",
            "My password is swordfish.",
            "My credit card number is 4111111111111111.",
            "My medication is fictional-tablet.",
        ):
            with self.subTest(text=text):
                self.assertFalse(automatic_memory_candidate(text))
        self.assertTrue(
            automatic_memory_candidate("I prefer jasmine tea without sugar.")
        )

    def test_capture_stores_exact_text_with_seven_day_retention(self) -> None:
        classifier = StubClassifier(MemoryCaptureDecision(True, "preference"))
        capture = AutomaticMemoryCapture(classifier, self.store())

        item = capture.consider(" I prefer jasmine tea without sugar. ")

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.canonical_text, "I prefer jasmine tea without sugar.")
        self.assertEqual(item.kind, "preference")
        self.assertEqual(item.retention_until, "2026-09-16T12:00:00.000000Z")
        self.assertEqual(classifier.calls, ["I prefer jasmine tea without sugar."])

    def test_capture_deduplicates_and_skips_non_candidates_without_model_use(
        self,
    ) -> None:
        classifier = StubClassifier(MemoryCaptureDecision(True, "fact"))
        store = self.store()
        capture = AutomaticMemoryCapture(classifier, store)

        first = capture.consider("I own a blue bicycle.")
        duplicate = capture.consider("I own a blue bicycle")
        question = capture.consider("Do I own a bicycle?")
        secret = capture.consider("My PIN is 1234.")

        self.assertIsNotNone(first)
        self.assertIsNone(duplicate)
        self.assertIsNone(question)
        self.assertIsNone(secret)
        self.assertEqual(classifier.calls, ["I own a blue bicycle."])
        self.assertEqual(len(store.list_memories()), 1)

    def test_negative_classifier_decision_stores_nothing(self) -> None:
        classifier = StubClassifier(MemoryCaptureDecision(False, None))
        store = self.store()
        capture = AutomaticMemoryCapture(classifier, store)

        self.assertIsNone(capture.consider("I am stressed right now."))
        self.assertEqual(store.list_memories(), ())

    def test_capture_outcome_identifies_existing_record_without_refreshing_it(
        self,
    ) -> None:
        classifier = StubClassifier(MemoryCaptureDecision(True, "preference"))
        store = self.store()
        capture = AutomaticMemoryCapture(classifier, store)

        original = capture.consider_with_outcome("I prefer jasmine tea.")
        duplicate = capture.consider_with_outcome("i prefer jasmine tea")
        skipped = capture.consider_with_outcome("What tea do I prefer?")

        self.assertEqual(original.status, "stored")
        self.assertEqual(duplicate.status, "duplicate")
        self.assertEqual(duplicate.item, original.item)
        self.assertEqual(skipped.status, "skipped")
        self.assertIsNone(skipped.item)
        self.assertEqual(classifier.calls, ["I prefer jasmine tea."])
        self.assertEqual(store.list_memories(), (original.item,))
