"""Offline replay isolation, evidence denominators, and provenance checks."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_memory_pipeline_offline as replay


def dump(path, value):
    path.write_text(json.dumps(value))


def implementation(root, *, improved=False, forbidden_database=False):
    package = root / "src/oline_hri"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "memory.py").write_text(
        "class MemoryItem:\n def __init__(self, **kwargs): self.__dict__.update(kwargs)\n"
        "class MemoryStore:\n def __init__(self, *args, **kwargs): raise RuntimeError('unpatched DB')\n")
    (package / "retrieval.py").write_text(
        "class HybridMatch:\n def __init__(self, **kwargs): self.__dict__.update(kwargs)\n")
    (package / "ollama.py").write_text("class OllamaClient:\n def chat(self, *args, **kwargs): pass\n")
    (package / "embedding.py").write_text("class BgeOnnxEmbedder:\n def __init__(self, *args, **kwargs): pass\n")
    if forbidden_database:
        routing = "from .memory import MemoryStore\ndef memory_intent_policy(prompt, history):\n MemoryStore('forbidden.sqlite3')\n return False, 'bad'\n"
    else:
        expression = "True if 'my' in prompt else False" if improved else "False"
        routing = f"def memory_intent_policy(prompt, history):\n return {expression}, 'fixture'\n"
    (package / "routing.py").write_text(routing)
    index = "-1" if improved else "0"
    (package / "conversation.py").write_text(
        f"def _required_memory_ids(matches, prompt):\n return (matches[{index}].memory.id,) if matches else ()\n")


class MemoryPipelineOfflineTests(unittest.TestCase):
    def fixture(self, temporary):
        root = Path(temporary)
        baseline, current = root / "baseline", root / "current"
        implementation(baseline)
        implementation(current, improved=True)
        cases = [
            {"id": "personal", "prompt": "Where is my bicycle?", "stratum": "personal_recall", "scenario_id": "bike"},
            {"id": "general", "prompt": "What is a bicycle?", "stratum": "routine_general", "scenario_id": "general"},
        ]
        gold, optional = "mem_" + "1" * 32, "mem_" + "2" * 32
        workload = {"execution_cases": cases, "rubrics": {
            "personal": {"required_memory_ids": [gold], "forbidden_memory_ids": []},
            "general": {"required_memory_ids": [], "forbidden_memory_ids": []}}}
        path = root / "workload.json"
        dump(path, workload)
        rows = [
            {**cases[0], "arm": "small", "repetition": 1, "index": 1, "status": "ok",
             "route": {"decision": {"memory_required": True}},
             "memory": {"supplied_ids": [optional, gold]},
             "retrieval_calls": [{"matches": [
                 {"memory": {"id": optional, "canonical_text": "An irrelevant stored fact."}, "fused_score": .03},
                 {"memory": {"id": gold, "canonical_text": "Your bicycle is in the shed."}, "fused_score": .02}]}]},
            {**cases[1], "arm": "small", "repetition": 1, "index": 2, "status": "ok",
             "route": {"decision": {"memory_required": False}},
             "memory": {"supplied_ids": []}, "retrieval_calls": []},
        ]
        observations = root / "observations.jsonl"
        observations.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        diagnostic = root / "diagnostics.json"
        dump(diagnostic, {"workload_sha256": replay.file_hash(path),
                          "source_observations_sha256": {str(observations): replay.file_hash(observations)}})
        return root, baseline, current, path, diagnostic, observations

    def test_rejected_output_evidence_is_recovered_without_answer_credit(self):
        self.assertEqual(replay.executed_supplied_ids({"calls": [{"purpose": "generation", "status": "error",
            "response_format": {"properties": {"memory_used": {"items": {"enum": ["fact-a"]}}}}}]}),
            (["fact-a"], "generation_response_schema"))
        self.assertEqual(replay.executed_supplied_ids({"calls": [{"purpose": "generation",
            "response_format": {"properties": {"memory_used": {"maxItems": 0}}}}]}),
            ([], "generation_response_schema"))
        self.assertEqual(replay.executed_supplied_ids({"response": {"memory_used": ["do-not-use-citations"]}}),
                         (None, "unknown"))

    def test_distinct_source_subprocesses_and_fixed_candidates_are_replayed_without_gold(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, baseline, current, workload, diagnostic, observations = self.fixture(temporary)
            before = observations.read_bytes()
            _, _, _, payload = replay.load_inputs(workload, diagnostic)
            self.assertEqual(set(payload["cases"][0]), {"id", "prompt"})
            self.assertEqual(set(payload["candidate_sets"][0]), {"key", "prompt", "candidates"})
            target = root / "output"
            with redirect_stdout(io.StringIO()):
                result = replay.main(["--baseline-source", str(baseline), "--current-source", str(current),
                                      "--workload", str(workload), "--diagnostics", str(diagnostic),
                                      "--output-dir", str(target)])
            self.assertEqual(result, 0)
            value = json.loads((target / "replay.json").read_text())
            self.assertEqual(value["new_model_calls"], 0)
            self.assertEqual(value["new_embedding_calls"], 0)
            self.assertIsNone(value["new_answer_accuracy"])
            self.assertIsNone(value["new_latency_measurement"])
            a, b = value["implementations"]["baseline"], value["implementations"]["current"]
            self.assertNotEqual(a["pid"], b["pid"])
            for label, source in (("baseline", baseline), ("current", current)):
                self.assertTrue(all(Path(v["path"]).is_relative_to(source / "src")
                                    for v in value["implementations"][label]["imported_modules"].values()))
            counts = value["comparison"]["by_implementation"]
            self.assertEqual(counts["baseline"]["intent_distinct_cases"]["wrong_explicit"], 1)
            self.assertEqual(counts["current"]["intent_distinct_cases"]["correct_explicit"], 2)
            self.assertEqual(counts["baseline"]["selection"]["all_required_selected"], 0)
            self.assertEqual(counts["current"]["selection"]["all_required_selected"], 1)
            self.assertEqual(counts["current"]["selection"]["not_assessed_no_candidates"], 1)
            self.assertIsNone(value["comparison"]["attempts"][1]["current"]["selected_ids"])
            self.assertEqual(observations.read_bytes(), before)

    def test_tampered_observations_fail_before_replaying_any_implementation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, baseline, current, workload, diagnostic, observations = self.fixture(temporary)
            observations.write_text(observations.read_text() + "\n")
            with patch.object(replay, "run_worker") as run, self.assertRaisesRegex(ValueError, "recorded hash"):
                replay.main(["--baseline-source", str(baseline), "--current-source", str(current),
                             "--workload", str(workload), "--diagnostics", str(diagnostic),
                             "--output-dir", str(root / "output")])
            run.assert_not_called()
            self.assertFalse((root / "output").exists())

    def test_worker_forbids_even_accidental_memory_store_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "bad"
            implementation(root, forbidden_database=True)
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                replay.run_worker(root, {"cases": [{"id": "x", "prompt": "Where is my bicycle?"}],
                                         "candidate_sets": []})
            self.assertIn("offline replay forbids", caught.exception.stderr)
            self.assertFalse((root / "forbidden.sqlite3").exists())

    def test_source_change_during_workers_prevents_publishing_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, baseline, current, workload, diagnostic, _ = self.fixture(temporary)
            actual = replay.run_worker

            def changing(source, payload):
                result = actual(source, payload)
                if source == current:
                    with (current / "src/oline_hri/routing.py").open("a") as stream:
                        stream.write("\n# changed while replaying\n")
                return result

            with patch.object(replay, "run_worker", side_effect=changing), self.assertRaisesRegex(ValueError, "sources changed"):
                replay.main(["--baseline-source", str(baseline), "--current-source", str(current),
                             "--workload", str(workload), "--diagnostics", str(diagnostic),
                             "--output-dir", str(root / "output")])
            self.assertFalse((root / "output").exists())


if __name__ == "__main__":
    unittest.main()
