"""Offline schema, fictional seed, and DDEE-rule checks; never live inference.

Run from repository root with PYTHONPATH=src:scripts .venv/bin/python
 evaluation/routing_overhead_20260912/validate_workload.py --output /new/file.json
"""
from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from run_complete_system import load_workload, materialize_seed
from oline_hri.lightweight_routing import LightweightRouter, _small_eligible
from oline_hri.ollama import ChatMessage, ChatResult

ROOT = Path(__file__).resolve().parents[2]
WORKLOAD = Path(__file__).with_name("workload.json")


class FakeBackend:
    def __init__(self):
        self.resident_model = None

    def chat(self, model, messages, **kwargs):
        self.resident_model = model
        return ChatResult(
            model=model, content='{"form":"question","memory_required":false}',
            done_reason="stop", total_duration_ns=1, load_duration_ns=0,
            prompt_eval_count=1, eval_count=1, eval_duration_ns=1,
            prompt_eval_duration_ns=0,
        )


def validate():
    workload = load_workload(WORKLOAD)
    by_id = {case["id"]: case for case in workload["execution_cases"]}
    sequences = workload["sequences"]
    assert len(sequences) == 12
    assert Counter(seq["pattern"] for seq in sequences) == Counter(
        {"EEEE": 3, "DDDD": 3, "EDED": 3, "DDEE": 3})
    assert len(by_id) == 48
    assert {cid for seq in sequences for cid in seq["case_ids"]} == set(by_id)
    for seq in sequences:
        assert len(seq["case_ids"]) == 4 and seq["initial_history"] == []
        assert all(by_id[cid]["scenario_id"] == seq["id"] for cid in seq["case_ids"])
    checks = []
    for seq in sequences:
        if seq["pattern"] != "DDEE":
            continue
        backend = FakeBackend()
        router = LightweightRouter(backend, small_model="qwen3:0.6b", large_model="qwen3:1.7b")
        history, actual = [], []
        for cid in seq["case_ids"]:
            case = by_id[cid]
            result = router.route(case["prompt"], history=tuple(history))
            actual.append({"id": cid, "choice": result.decision.model_size,
                           "source": result.model_size_decision_source,
                           "memory_source": result.memory_decision_source,
                           "small_eligible": _small_eligible(case["prompt"], history)})
            backend.resident_model = ("qwen3:0.6b" if result.decision.model_size == "small"
                                      else "qwen3:1.7b")
            history += [ChatMessage("user", case["prompt"]),
                        ChatMessage("assistant", "A simulated validated answer.")]
        assert [item["choice"] for item in actual] == ["large", "large", "large", "small"]
        assert [item["source"] for item in actual][-2:] == ["lightweight_resident", "lightweight_small"]
        checks.append({"sequence": seq["id"], "simulated_choices": actual,
                       "note": "Simulated classifier always returns memory false; fake timings are not measurements. Full prior history retained to check the strictest non-social history condition."})
    with TemporaryDirectory() as directory:
        store, events = materialize_seed(workload["memory_seed"],
                                        Path(directory) / "memory.sqlite", embedder=None)
        eligible = [item.id for item in store.list_memories()
                    if store.retrieval_snapshot_is_current((item,))]
        assert set(eligible) == set(workload["memory_seed"]["expected_state"]["eligible_current_memory_ids"])
    old_path = ROOT / "evaluation/post_memory_comparison_20260912/frozen_v2/workload.json"
    old = json.loads(old_path.read_text())
    old_prompts = {case["prompt"] for case in old["execution_cases"]}
    source_paths = [Path("src/oline_hri/lightweight_routing.py"),
                    Path("src/oline_hri/routing.py"), Path("scripts/run_complete_system.py")]
    return dict(
        status="passed", scope="offline_workload_schema_seed_and_DDEE_rules_only_zero_model_and_embedding_calls",
        workload_sha256=sha256(WORKLOAD.read_bytes()).hexdigest(),
        sequence_count=len(sequences), turn_slots=len(by_id),
        unique_prompt_texts=len({case["prompt"] for case in by_id.values()}),
        patterns=dict(Counter(seq["pattern"] for seq in sequences)),
        seed_operations=len(events), eligible_memory_count=len(eligible),
        seed_value_identical_to_post_memory_v2=workload["memory_seed"] == old["memory_seed"],
        exact_prompt_overlap_with_post_memory_v2=[case["id"] for case in by_id.values()
                                                if case["prompt"] in old_prompts],
        ddee_rule_checks=checks,
        source_hashes={str(path): sha256((ROOT / path).read_bytes()).hexdigest()
                       for path in source_paths},
    )


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to replace an existing validation record")
    result = validate()
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "sequences": result["sequence_count"],
                      "turn_slots": result["turn_slots"], "output": str(args.output)}))
