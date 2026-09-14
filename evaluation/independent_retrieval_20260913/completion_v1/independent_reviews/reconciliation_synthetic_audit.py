"""Independent small checks using fictional review sheets, without primary data."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("review_reconciliation_under_audit",
    ROOT / "scripts/reconcile_independent_retrieval_reviews.py")
reviews = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reviews)


def packet(number=1, delivered=True):
    return {"review_id": "review_" + f"{number:032x}",
            "prompt": "What is my fictional album called?",
            "answer": "It is called Fernpath." if delivered else None,
            "delivery_status": "delivered" if delivered else "not_delivered",
            "answerability": "known_authorized", "rubric": {},
            "reference_facts_without_ids": ["Your album is called Fernpath."]}


def judgment(number=1, label="partial"):
    return {"review_id": "review_" + f"{number:032x}", "label": label,
            "rationale": "Independent synthetic structural example.",
            **{flag: False for flag in reviews.FLAGS}}


class IndependentReconciliationChecks(unittest.TestCase):
    def test_every_label_flag_difference_requires_adjudication_but_rationale_does_not(self):
        original = judgment()
        second = dict(original, rationale="Different explanation.")
        self.assertTrue(reviews.agrees(original, second))
        self.assertFalse(reviews.agrees(original, dict(original, label="incorrect")))
        for flag in reviews.FLAGS:
            with self.subTest(flag=flag):
                self.assertFalse(reviews.agrees(original, {**original, flag: True}))

    def test_exact_review_id_coverage_rejects_duplicate_missing_and_unknown(self):
        lookup = reviews.packet_index([packet(1), packet(2)])
        for values in ([judgment(1)], [judgment(1), judgment(1)],
                       [judgment(1), judgment(3)]):
            with self.subTest(ids=[value["review_id"] for value in values]):
                with self.assertRaises(ValueError):
                    reviews.review_index(values, lookup)
        self.assertEqual(set(reviews.review_index([judgment(2), judgment(1)], lookup)), set(lookup))

    def test_failure_cannot_be_promoted_or_receive_delivered_claim_flags(self):
        lookup = reviews.packet_index([packet(delivered=False)])
        with self.assertRaises(ValueError):
            reviews.review_index([judgment(label="complete")], lookup)
        good = judgment(label="technical_failure")
        self.assertEqual(len(reviews.review_index([good], lookup)), 1)
        for flag in reviews.FLAGS:
            with self.subTest(flag=flag):
                with self.assertRaises(ValueError):
                    reviews.review_index([{**good, flag: True}], lookup)

    def test_packet_must_hide_ids_and_undelivered_raw_text(self):
        for invalid in ([packet(), packet()],
                        [{**packet(), "model": "secret model"}],
                        [{**packet(), "prompt": "Recall mem_" + "a" * 32}],
                        [{**packet(delivered=False), "answer": "Unseen raw answer"}]):
            with self.assertRaises(ValueError):
                reviews.packet_index(invalid)

    def test_seal_detects_modified_bytes_and_additional_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "sealed"
            directory.mkdir()
            original = directory / "original.json"
            original.write_bytes(b'{"synthetic":true}\n')
            reviews.seal(directory)
            reviews.verify_seal(directory)
            original.chmod(0o600)
            original.write_bytes(b'{"synthetic":false}\n')
            with self.assertRaisesRegex(ValueError, "contents differ"):
                reviews.verify_seal(directory)
            original.write_bytes(b'{"synthetic":true}\n')
            directory.chmod(0o700)
            (directory / "added.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "file set differs"):
                reviews.verify_seal(directory)


if __name__ == "__main__":
    unittest.main(verbosity=2)
