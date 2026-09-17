"""Real four-turn runner and diagnostic replay through fake HTTP, never hardware."""

from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_routing_overhead as runner
import analyze_routing_overhead as analyzer
import post_memory_device_guard as device_guard
from oline_hri.ollama import ChatMessage
from oline_hri.response import ResponseValidationError
from tests.test_complete_system_runner import FakeEmbedder, seed
from tests.test_lightweight_integration import RecordingTransport, HARD, EASY, AMBIGUOUS
from tests.test_post_memory_comparison import FakeSampler, snapshot


SMALL, LARGE = runner.SMALL, runner.LARGE


def read_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class RoutingOverheadRunnerTests(unittest.TestCase):
    def fixture(self, path, prompts):
        cases, sequences = [], []
        for pattern in ("EEEE", "DDDD", "EDED", "DDEE"):
            for variant in range(1, 4):
                seq = {"id": f"{pattern}_{variant}", "pattern": pattern, "case_ids": []}
                for index, label in enumerate(pattern):
                    case = {"id": f"CASE_SENTINEL_{seq['id']}_{index}", "stratum": label,
                            "scenario_id": "SCENARIO_SENTINEL",
                            "prompt": prompts[index] if pattern == "DDEE" and variant == 1 else EASY if label == "E" else HARD}
                    seq["case_ids"].append(case["id"])
                    cases.append(case)
                sequences.append(seq)
        workload = {"execution_cases": cases, "sequences": sequences, "initial_history": [],
                    "memory_seed": seed(), "rubrics": {c["id"]: {"gold": "GOLD_SENTINEL"} for c in cases}}
        path.mkdir(parents=True, exist_ok=True)
        workload_path = path / "workload.json"
        workload_path.write_text(json.dumps(workload))
        (path / "source").mkdir(exist_ok=True)
        (path / "source/offline").write_bytes(b"frozen")
        frozen = {"profile_id": runner.PROFILE, "source_sha256": {"offline": sha256(b"frozen").hexdigest()},
                  "workload_sha256": sha256(workload_path.read_bytes()).hexdigest(),
                  "config": runner.config_for("adaptive").to_dict(), "python": sys.version,
                  "packages": runner.package_versions(), "device_policy": runner.policy_dict(),
                  "models": {SMALL: {"model": SMALL}, LARGE: {"model": LARGE}},
                  "ollama_version": {"version": "offline"}}
        frozen_path = path / "freeze.json"
        frozen_path.write_text(json.dumps(frozen))
        return workload_path, frozen_path, workload, frozen

    def run_offline(self, path, arm, prompts=(HARD, HARD, EASY, EASY), *, transport=None,
                    replay=None, start=None, check=None):
        workload_path, frozen_path, workload, frozen = self.fixture(path, prompts)
        transport = transport or RecordingTransport()
        directory = path / "output"
        actual_client = runner.OverheadClient
        def client_factory(*args, **kwargs):
            return actual_client(*args, opener=transport, **kwargs)
        def state():
            value = deepcopy(start or snapshot())
            value["resident_models"] = [{"name": m} for m in transport.resident]
            return value
        def ps():
            return tuple({"name": m, "digest": "fake-digest", "size": 100, "size_vram": 75}
                         for m in sorted(transport.resident))
        def hardware_check(backend):
            if backend.sampler.monitor.violation:
                raise runner.SafetyGateError(backend.sampler.monitor.violation)
            if check is not None:
                return check()
            return {}
        args = SimpleNamespace(workload=workload_path, freeze=frozen_path, arm=arm,
                               output_dir=directory, sequence="DDEE_1", repetition=1, replay=replay)
        with ExitStack() as stack:
            stack.enter_context(patch.object(runner, "source_hashes", return_value=frozen["source_sha256"]))
            stack.enter_context(patch.object(runner, "_installed_models", return_value={}))
            stack.enter_context(patch.object(runner, "_model_metadata", side_effect=lambda m, _: {"model": m}))
            stack.enter_context(patch.object(runner, "_http_json", return_value={"version": "offline"}))
            stack.enter_context(patch.object(runner, "capture_safety_snapshot", side_effect=state))
            stack.enter_context(patch.object(runner, "_resident_models", side_effect=ps))
            stack.enter_context(patch.object(runner, "GuardedSampler", FakeSampler))
            stack.enter_context(patch.object(runner.OverheadBackend, "check", autospec=True, side_effect=hardware_check))
            stack.enter_context(patch.object(runner, "process_audit", return_value={"conflicts": []}))
            stack.enter_context(patch.object(runner, "LOCK", path / "inference.lock"))
            client = stack.enter_context(patch.object(runner, "OverheadClient", side_effect=client_factory))
            embedder = stack.enter_context(patch.object(runner, "BgeOnnxEmbedder", return_value=FakeEmbedder()))
            with redirect_stdout(io.StringIO()):
                result = runner.session(args)
        rows = read_lines(directory / "observations.jsonl")
        finish = json.loads((directory / "finish.json").read_text())
        return SimpleNamespace(result=result, rows=rows, finish=finish, transport=transport,
                               directory=directory, workload=workload_path, freeze=frozen_path,
                               calls={"client": client.call_count, "embedder": embedder.call_count})

    def test_full_sequence_switching_accounting_and_fixed_system_isolation(self):
        for arm, selected in (("small", [SMALL] * 4), ("large", [LARGE] * 4),
                              ("adaptive", [LARGE, LARGE, LARGE, SMALL])):
            with self.subTest(arm=arm), tempfile.TemporaryDirectory() as tmp:
                run = self.run_offline(Path(tmp), arm)
                self.assertEqual(run.result, 0, run.finish)
                self.assertEqual([r["generation"]["model"] for r in run.rows], selected)
                self.assertEqual(len(run.rows), 4)
                self.assertEqual(run.rows[0]["api_ps_before"], [])
                self.assertEqual(run.rows[0]["history_before"], [run.rows[0]["history_before"][0]])
                self.assertGreater(len(run.rows[1]["history_before"]), 1)
                self.assertEqual(run.finish["sequence_total_ns"], run.finish["startup_ns"] + sum(r["wall_ns"] for r in run.rows) + run.finish["sequence_gaps_ns"])
                for row in run.rows:
                    parts = analyzer.account_spans(row)
                    self.assertEqual(sum(parts.values()), row["wall_ns"])
                    analyzer.audit_calls(row)
                self.assertEqual(run.transport.resident, set())
                self.assertEqual(run.finish["cleanup_errors"], [])
                self.assertTrue(all(c["body"]["keep_alive"] == -1 for c in run.transport.chats))
                self.assertTrue(all(c["body"]["options"] == {"num_ctx": 2048, "num_predict": 192,
                                     "temperature": 0.0, "seed": 42} for c in run.transport.chats))
                self.assertTrue(all(c["body"]["think"] is False for c in run.transport.chats))
                if arm in {"small", "large"}:
                    self.assertEqual({c["body"]["model"] for c in run.transport.requests}, {selected[0]})
                sent = json.dumps(run.transport.requests)
                for marker in ("CASE_SENTINEL", "SCENARIO_SENTINEL", "GOLD_SENTINEL"):
                    self.assertNotIn(marker, sent)
                _, _, runs, _, _, _, _, audit_errors = analyzer.load_inputs(Path(tmp), run.workload, run.freeze)
                self.assertEqual(audit_errors, [])
                self.assertTrue(runs[0]["complete"])

    def test_diagnostic_replay_preserves_exact_payloads_and_adaptive_history_without_classifiers(self):
        prompts = (AMBIGUOUS, AMBIGUOUS, EASY, EASY)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adaptive = self.run_offline(root / "adaptive", "adaptive", prompts)
            replay_transport = RecordingTransport()
            replay_transport.speeches.extend(["A different synthetic response."] * 4)
            replay = self.run_offline(root / "replay", "replay", prompts,
                                      replay=adaptive.directory / "observations.jsonl", transport=replay_transport)
            self.assertEqual(adaptive.result, 0, adaptive.finish)
            self.assertEqual(replay.result, 0, replay.finish)
            self.assertEqual(len(adaptive.transport.classifiers), 2)
            self.assertEqual(replay.transport.classifiers, [])
            self.assertEqual([c["body"] for c in adaptive.transport.generations],
                             [c["body"] for c in replay.transport.generations])
            self.assertEqual([r["generation"]["model"] for r in adaptive.rows],
                             [r["generation"]["model"] for r in replay.rows])
            self.assertEqual([r["history_before"] for r in adaptive.rows], [r["history_before"] for r in replay.rows])
            self.assertNotEqual(adaptive.rows[0]["response"], replay.rows[0]["response"])
            self.assertTrue(all(r["diagnostic_replay"] for r in replay.rows))
            self.assertFalse(any(e["name"] in {"memory_classifier", "compute_classifier", "deterministic_routing"}
                                 for r in replay.rows for e in r["events"]))
            for row in replay.rows:
                self.assertEqual(sum(analyzer.account_spans(row).values()), row["wall_ns"])

    def test_replay_payload_mismatch_stops_at_durable_attempt_before_different_generation(self):
        for boundary in ("arguments", "http_body"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                adaptive = self.run_offline(root / "adaptive", "adaptive")
                rows = deepcopy(adaptive.rows)
                if boundary == "arguments":
                    generation = next(c for c in rows[0]["calls"] if c["purpose"] == "generation")
                    generation["messages"][-1]["content"] = "Different unapproved request"
                else:
                    generation = next(c for c in rows[0]["http_calls"] if c["endpoint"] == "/api/chat")
                    generation["body"]["options"]["num_predict"] = 191
                corrupted = root / "corrupted_replay.jsonl"
                corrupted.write_text("".join(json.dumps(row) + "\n" for row in rows))
                replay = self.run_offline(root / "replay", "replay", replay=corrupted)
                self.assertEqual(replay.result, 1)
                self.assertEqual(len(replay.rows), 1)
                self.assertEqual(replay.rows[0]["status"], "interrupted")
                self.assertEqual(replay.transport.generations, [])
                self.assertEqual(replay.transport.resident, set())
                self.assertIn("differ", replay.finish["failure"]["message"])

    def test_preturn_guard_failure_is_preserved_without_inference(self):
        checks = iter(({}, runner.SafetyGateError("offline preturn refusal")))
        def check():
            value = next(checks)
            if isinstance(value, BaseException):
                raise value
            return value
        with tempfile.TemporaryDirectory() as tmp:
            run = self.run_offline(Path(tmp), "small", check=check)
            self.assertEqual(run.result, 1)
            self.assertEqual(len(run.rows), 1)
            self.assertEqual(run.rows[0]["status"], "interrupted")
            self.assertEqual(run.rows[0]["phase"], "before_request")
            self.assertIsNone(run.rows[0]["wall_ns"])
            self.assertFalse(run.rows[0]["request_started"])
            self.assertEqual(run.transport.requests, [])
            events = read_lines(run.directory / "events.jsonl")
            self.assertTrue(any(e.get("kind") == "turn_attempt" for e in events))

    def test_answer_validation_failure_keeps_sequence_residency_history_and_denominator(self):
        # ResponseValidationError is a ValueError; classifying every ValueError
        # as fatal previously stopped collection on an ordinary invalid answer.
        self.assertTrue(issubclass(ResponseValidationError, ValueError))
        for arm in ("large", "adaptive"):
            with self.subTest(arm=arm), tempfile.TemporaryDirectory() as tmp:
                transport = RecordingTransport()
                transport.speeches.extend(("First valid answer.", None, "Third valid answer.", None))
                run = self.run_offline(Path(tmp), arm, transport=transport)
                self.assertEqual(run.result, 0, run.finish)
                self.assertEqual(run.finish["status"], "complete_with_errors")
                self.assertIsNone(run.finish["failure"])
                self.assertEqual(run.finish["attempted"], 4)
                self.assertEqual([r["status"] for r in run.rows], ["ok", "error", "ok", "error"])
                self.assertEqual([r["error"] for r in run.rows if r["status"] == "error"],
                                 ["ResponseValidationError", "ResponseValidationError"])
                self.assertEqual(run.rows[1]["history_after"], run.rows[1]["history_before"])
                self.assertEqual(run.rows[2]["history_before"], run.rows[1]["history_after"])
                self.assertEqual(run.rows[3]["history_after"], run.rows[3]["history_before"])
                self.assertEqual(run.rows[1]["resident_hint_before"], LARGE)
                self.assertEqual(run.rows[1]["resident_hint_after"], LARGE)
                self.assertEqual(run.rows[2]["resident_hint_before"], LARGE)
                selected = [LARGE] * 4 if arm == "large" else [LARGE, LARGE, LARGE, SMALL]
                self.assertEqual([r["body"]["model"] for r in transport.generations], selected)
                for row in (run.rows[1], run.rows[3]):
                    self.assertEqual(row["calls"][-1]["status"], "ok")
                    self.assertIn("raw_generation", row["calls"][-1])
                    validation = next(e for e in row["events"] if e["name"] == "validation")
                    self.assertEqual(validation["status"], "error")
                    self.assertGreater(row["wall_ns"], 0)
                    self.assertEqual(sum(analyzer.account_spans(row).values()), row["wall_ns"])
                self.assertEqual(run.finish["request_total_ns"], sum(r["wall_ns"] for r in run.rows))
                self.assertEqual(run.transport.resident, set())
                self.assertEqual(run.finish["cleanup_errors"], [])

    def test_transport_failure_and_interrupt_preserve_failed_turn_and_cleanup(self):
        for error in ("transport", "interrupt"):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as tmp:
                transport = RecordingTransport()
                if error == "transport":
                    transport.fail_next_generation = True
                else:
                    transport.after_generation = lambda: (_ for _ in ()).throw(KeyboardInterrupt("offline interrupt"))
                run = self.run_offline(Path(tmp), "large", transport=transport)
                self.assertEqual(run.result, 1)
                self.assertEqual(len(run.rows), 1)
                self.assertEqual(run.rows[0]["status"], "interrupted")
                self.assertEqual(run.transport.resident, set())
                events = read_lines(run.directory / "events.jsonl")
                self.assertTrue(any(e.get("kind") == "turn_attempt" for e in events))
                self.assertTrue(any(e.get("event") == "span_start" for e in events))
                self.assertTrue(any(e.get("event") == "span_end" and e["name"] == "complete_request"
                                    and e["status"] in {"error", "interrupted"} for e in events))
                self.assertTrue(any(e["name"] == "eviction_verification" for e in json.loads((run.directory / "cleanup.json").read_text())["events"]))

    def test_blocked_cold_admission_performs_no_model_or_embedding_calls(self):
        for reason, changed in (("swap", snapshot(swap=device_guard.MAX_START_SWAP_USED_KIB + 1)),
                                ("temperature", {**snapshot(), "temperatures_c": {"cpu": 56}})):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as tmp:
                run = self.run_offline(Path(tmp), "large", start=changed)
                self.assertEqual(run.result, 1)
                self.assertEqual(run.finish["status"], "blocked_preflight")
                self.assertEqual(run.rows, [])
                self.assertEqual(run.calls, {"client": 0, "embedder": 0})
                self.assertEqual(run.transport.requests, [])

    def test_schedule_is_three_counterbalanced_repetitions_with_matched_replays(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, workload, _ = self.fixture(Path(tmp), (HARD, HARD, EASY, EASY))
            runner.validate_workload(workload)
            slots = list(runner.slots(workload))
        self.assertEqual(len(slots), 144)
        for rep, expected in enumerate(runner.ORDERS, 1):
            for sequence in workload["sequences"]:
                observed = [arm for sid, r, arm in slots if sid == sequence["id"] and r == rep]
                self.assertEqual(observed, [*expected, "replay"])
        self.assertEqual({tuple(order.index(arm) for order in runner.ORDERS) for arm in ("small", "large", "adaptive")},
                         {(0, 2, 1), (1, 0, 2), (2, 1, 0)})

    def test_exclusive_lock_refuses_second_collector(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, "LOCK", Path(tmp) / "lock"):
            with runner.exclusive_inference():
                with self.assertRaises(runner.SafetyGateError):
                    with runner.exclusive_inference():
                        self.fail("second inference collector was admitted")

    def test_fixed_peer_is_rejected_before_http(self):
        transport = RecordingTransport()
        config = runner.config_for("large")
        client = runner.OverheadClient(config.ollama, config.generation, opener=transport,
                                      retain_large_model=True, http_writer=SimpleNamespace(write=lambda _: None))
        backend = runner.OverheadBackend(client, {}, SimpleNamespace(monitor=SimpleNamespace(violation=None)), (LARGE,))
        with patch.object(runner, "_resident_models", return_value=()), self.assertRaises(runner.SafetyGateError):
            backend.chat(SMALL, (ChatMessage("user", "Hello"),))
        self.assertEqual(transport.requests, [])


if __name__ == "__main__":
    unittest.main()
