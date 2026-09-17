"""Synthetic identity-only batch vote rebinding; no live answer access."""

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("changing_memory_batch_reviews", ROOT / "evaluation/changing_memory_20260914/batch_reviews.py")
batch = importlib.util.module_from_spec(spec); spec.loader.exec_module(batch)
A = batch.A


class BatchReviewBindingTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="clara-batch-review-offline-"))
        self.addCleanup(self.cleanup)
        self.packets = [{"blind_id": "old_one", "question": "What is the fictional preference?",
            "authorized_state": [{"canonical_text": "Preference is blue."}],
            "rubric": {"required_behavior": "Give the requested value, blue.", "forbidden_values": ["red", "green"]},
            "delivered_answer": "It is green, not red."},
            {"blind_id": "old_two", "question": "What is the missing fictional preference?", "authorized_state": [],
            "rubric": {"required_behavior": "Explicitly say the requested fact is not known or no longer available; do not guess.",
                       "forbidden_values": ["gold"]}, "delivered_answer": "I do not know."}]
        self.batches, self.a, self.b = [], [], []
        for index, packet in enumerate(self.packets):
            directory = self.make_packets(f"batch{index}", [packet]); self.batches.append(directory)
            for side, collection in (("a", self.a), ("b", self.b)):
                judgment = {"blind_id": packet["blind_id"], "classification": "incorrect" if index == 0 else "appropriate_uncertainty",
                    "useful_correct": index != 0, "forbidden_disclosure": index == 0,
                    "disclosed_forbidden_values": ["green", "red"] if index == 0 else [],
                    "reason": f"Exact original {side} rationale for {index}."}
                value = {"reviewer_id": f"offline-{side}", "human_validation": "pending", "extra_metadata": "preserve this",
                         "packet_sha256": A.digest(directory / "public/packets.jsonl"), "judgments": [judgment]}
                path = self.root / f"votes_{side}_{index}.json"; A.write(path, value); collection.append(path)
        self.final = self.make_packets("final", [{**self.packets[1], "blind_id": "new_two"}, {**self.packets[0], "blind_id": "new_one"}])

    def cleanup(self):
        for p in self.root.rglob("*"):
            p.chmod(0o700 if p.is_dir() else 0o600)
        self.root.chmod(0o700); shutil.rmtree(self.root)

    def make_packets(self, name, packets):
        directory = self.root / name; directory.mkdir(); (directory / "public").mkdir()
        A.write_lines(directory / "public/packets.jsonl", packets); A.seal(directory)
        return directory

    def args(self, **kwargs):
        values = dict(prepared=self.final, batches=self.batches, reviews_a=self.a, reviews_b=self.b, output=self.root / "bound")
        values.update(kwargs)
        return argparse.Namespace(**values)

    def test_rebinding_changes_only_identity_and_packet_hash(self):
        batch.bind(self.args())
        out = self.root / "bound"
        for side, inputs in (("a", self.a), ("b", self.b)):
            result = json.loads((out / f"review_{side}.json").read_text())
            self.assertEqual(result["extra_metadata"], "preserve this")
            actual = {r["blind_id"]: r for r in result["judgments"]}
            for path, new_id in zip(inputs, ("new_one", "new_two")):
                old = json.loads(path.read_text())["judgments"][0]
                self.assertEqual(actual[new_id], {**old, "blind_id": new_id})
            self.assertEqual(actual["new_one"]["disclosed_forbidden_values"], ["green", "red"])
        A.verify_seal(out)

    def test_gaps_and_reviewer_identity_changes_rejected(self):
        with self.assertRaisesRegex(ValueError, "Incomplete batch coverage"):
            batch.bind(self.args(batches=self.batches[:1], reviews_a=self.a[:1], reviews_b=self.b[:1]))
        value = json.loads(self.a[1].read_text()); value["reviewer_id"] = "changed-reviewer"
        self.a[1].write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "stable ID"):
            batch.bind(self.args())
        self.assertFalse((self.root / "bound").exists())

    def test_conflicting_duplicate_scores_rejected(self):
        original = json.loads(self.a[0].read_text())
        original["judgments"][0].update(classification="partial", reason="Conflicting synthetic score.")
        conflict = self.root / "conflict.json"; A.write(conflict, original)
        with self.assertRaisesRegex(ValueError, "Conflicting duplicate"):
            batch.bind(self.args(batches=self.batches + [self.batches[0]],
                reviews_a=self.a + [conflict], reviews_b=self.b + [self.b[0]]))

    def test_prepare_uses_only_selected_sealed_branches(self):
        authored = ROOT / "evaluation/changing_memory_20260914/authored_v2"
        freeze = self.root / "freeze"; freeze.mkdir()
        for name in ("runtime.json", "expected_ledger.json"):
            shutil.copyfile(authored / name, freeze / name)
        runtime = json.loads((freeze / "runtime.json").read_text())
        expected = {r["checkpoint_id"]: r for r in json.loads((freeze / "expected_ledger.json").read_text())["checkpoints"]}
        A.seal(freeze)
        run = self.root / "run"; run.mkdir()
        for number, branch in enumerate(b for b in runtime["branches"] if b["scenario_id"] == "cm01"):
            directory = run / branch["branch_id"]; directory.mkdir()
            rows = []
            for op in branch["operations"]:
                if op["op"] != "ask":
                    continue
                e = expected[op["checkpoint_id"]]
                rows.append({"checkpoint_id": op["checkpoint_id"], "op": op, "logical_time": op["time"],
                    "branch_id": branch["branch_id"], "branch": branch["branch"], "scenario_id": "cm01",
                    "status": "withheld", "delivered_answer": None,
                    "process": {"pid": 12 if e["after_restart"] else 11, "boot_id": "offline", "process_start_ticks": "12" if e["after_restart"] else "11"},
                    "database_identity": {"path": branch["branch_id"] + ".db", "device": 1, "inode": number + 1}})
            A.write_lines(directory / "answers.jsonl", rows); A.seal(directory)
        # An unsealed unrelated branch deliberately contains invalid JSON; it must never be read.
        other = run / "cm02_correction"; other.mkdir(); (other / "answers.jsonl").write_text("INVALID UNREAD LIVE PLACEHOLDER")
        output = self.root / "prepared_batch"
        batch.prepare(argparse.Namespace(freeze=freeze, run=[run], scenarios=["cm01"], output=output))
        mapping = json.loads((output / "private/mapping.json").read_text())
        self.assertEqual(sum(len(r["checkpoint_ids"]) for r in mapping), 24)
        packets = A.read_lines(output / "public/packets.jsonl")
        self.assertTrue(all(set(p) == {*batch.PACKET_FIELDS, "blind_id"} for p in packets))
        A.verify_seal(output)


if __name__ == "__main__":
    unittest.main()
