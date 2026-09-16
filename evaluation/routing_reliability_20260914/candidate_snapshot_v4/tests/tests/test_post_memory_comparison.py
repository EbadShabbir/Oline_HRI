"""Offline call-policy, HTTP-residency, provenance and admission regressions."""

from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
from dataclasses import asdict, replace
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
import run_post_memory_comparison as runner
import post_memory_device_guard as device_guard
from oline_hri import evaluation_model_pairs as pair
from oline_hri.config import load_config
from oline_hri.conversation import ConversationError, _validated_route
from oline_hri.evaluation_systems import MemoryOnlyRouter, OptimizedMemoryOnlyRouter
from oline_hri.ollama import ChatMessage, ChatResult
from oline_hri.routing import RouteDecision, RoutingError, _memory_classifier_inputs
from tests.test_complete_system_runner import FakeEmbedder, seed
from tests.test_lightweight_integration import RecordingTransport, HARD, EASY, AMBIGUOUS
from tests.test_lightweight_routing_live_guard import snapshot as old_snapshot


SMALL, LARGE = runner.SMALL, runner.LARGE


def snapshot(*, swap=988 * 1024):
    value = old_snapshot(swap=swap)
    value["memory"]["swap_total_kib"] = device_guard.EXPECTED_SWAP_TOTAL_KIB
    return value


class Backend:
    def __init__(self, model=LARGE, value=None):
        self.resident_model = model
        self.value = value or ChatResult(model, '{"form":"request","memory_required":false}',
                                         "stop", 1, 0, 1, 1, 1)
        self.calls = []

    def chat(self, model, messages, **kwargs):
        self.calls.append((model, messages, kwargs))
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value


class FakeSampler:
    def __init__(self, monitor):
        self.monitor, self.samples, self._reader_error = monitor, [object()], None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def summary(self):
        return {"sample_count": 1, "scope": "offline fake sampler"}


class PostMemoryComparisonTests(unittest.TestCase):
    def test_optimized_fixed_memory_is_zero_or_one_real_own_model_call(self):
        for size, model in (("small", SMALL), ("large", LARGE)):
            for prompt, count, source in (
                (EASY, 0, "policy_general"),
                ("What is my preferred drink?", 0, "policy_personal"),
                (AMBIGUOUS, 1, "fixed_model"),
            ):
                with self.subTest(size=size, prompt=prompt):
                    backend = Backend(model)
                    route = OptimizedMemoryOnlyRouter(backend, model=model, fixed_model_size=size).route(prompt)
                    self.assertEqual(len(backend.calls), count)
                    self.assertEqual(route.policy, "fixed_memory_v1")
                    self.assertEqual(route.fixed_generator_model, model)
                    self.assertEqual(route.memory_decision_source, source)
                    self.assertEqual(route.model_size_decision_source, "fixed_generator")
                    self.assertIsNone(route.model_size_generation)
                    self.assertEqual(_validated_route(route, fixed_generator_model=model, fixed_model_size=size),
                                     (route.decision.memory_required, size))
                    if count:
                        self.assertEqual(backend.calls[0][0], model)
                        self.assertEqual(backend.calls[0][1], _memory_classifier_inputs(prompt, ())[3])
                        self.assertIs(route.memory_required_generation, backend.value)
                    else:
                        self.assertIsNone(route.memory_required_generation)

    def test_historical_fixed_adapter_still_makes_its_original_one_call(self):
        backend = Backend()
        route = MemoryOnlyRouter(backend, model=LARGE, fixed_model_size="large").route(EASY)
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(route.policy, "legacy")
        self.assertIs(route.memory_required_generation, backend.value)

    def test_fixed_classifier_rejects_metadata_schema_errors_and_preserves_guards(self):
        base = Backend().value
        for value in (replace(base, model=SMALL), replace(base, done_reason="length"),
                      replace(base, done_reason="unknown"), replace(base, content='{"memory_required":true}')):
            with self.subTest(value=value):
                with self.assertRaises(RoutingError):
                    OptimizedMemoryOnlyRouter(Backend(value=value), model=LARGE, fixed_model_size="large").route(AMBIGUOUS)
        for value in (runner.SafetyGateError("offline guard"), KeyboardInterrupt("offline interrupt")):
            with self.subTest(error=type(value).__name__):
                with self.assertRaises(type(value)):
                    OptimizedMemoryOnlyRouter(Backend(value=value), model=LARGE, fixed_model_size="large").route(AMBIGUOUS)

    def test_fixed_route_rejects_missing_provenance_peer_metadata_and_role_mismatch(self):
        base = OptimizedMemoryOnlyRouter(Backend(), model=LARGE, fixed_model_size="large").route(EASY)
        raw = Backend().value
        invalid = (
            replace(base, fixed_generator_model=SMALL),
            replace(base, fixed_generator_model=None),
            replace(base, decision=RouteDecision(False, "small")),
            replace(base, model_size_decision_source="lightweight_large"),
            replace(base, memory_decision_source="fixed_model"),
            replace(base, model_size_generation=raw),
            replace(base, resident_model=SMALL),
            replace(base, memory_decision_source="fixed_model", memory_required_generation=replace(raw, model=SMALL)),
            replace(base, memory_decision_source="fixed_model", memory_required_generation=replace(raw, done_reason="length")),
        )
        for route in invalid:
            with self.subTest(route=route):
                with self.assertRaises(ConversationError):
                    _validated_route(route, fixed_generator_model=LARGE, fixed_model_size="large")
        with self.assertRaises(ConversationError):
            _validated_route(base)

    def fixture(self, path, prompts):
        config = load_config()
        config = replace(config, generation=replace(config.generation, context_length=2048,
                         max_output_tokens=192, temperature=0.0, thinking=False))
        cases = [{"id": f"CASE_METADATA_SENTINEL_{i}", "scenario_id": "SCENARIO_SENTINEL",
                  "stratum": "STRATUM_SENTINEL", "prompt": prompt} for i, prompt in enumerate(prompts)]
        workload = {"execution_cases": cases,
                    "rubrics": {case["id"]: {"gold": "GOLD_MUST_NEVER_ENTER_MODEL_MESSAGES"} for case in cases},
                    "memory_seed": seed()}
        workload_path = path / "workload.json"
        workload_path.write_text(json.dumps(workload))
        frozen = {
            "profile_id": runner.PROFILE_ID, "workload_sha256": sha256(workload_path.read_bytes()).hexdigest(),
            "source_sha256": {"offline_source": "frozen"},
            "models": {SMALL: {"model": SMALL}, LARGE: {"model": LARGE}},
            "ollama_version": {"version": "offline"},
            "embedding_config": asdict(config.embedding),
            "embedding_asset_sha256": dict(runner.REQUIRED_ASSET_SHA256),
            "generation": asdict(config.generation), "generation_seed": 42,
            "base_config": config.to_dict(), "packages": runner.package_versions(),
            "python": sys.version, "device_policy": runner.policy_dict(),
            "execution_policies": {arm: runner.execution_policy(arm) for arm in ("small", "large", "cascade")},
        }
        frozen_path = path / "freeze.json"
        frozen_path.write_text(json.dumps(frozen))
        return workload_path, frozen_path

    def run_offline(self, path, arm, prompts, *, transport=None, start=None, preflight=False,
                    sources=None):
        workload, frozen = self.fixture(path, prompts)
        directory = path / "output"
        transport = transport or RecordingTransport()
        original_client = runner.ComparisonClient
        def factory(*args, **kwargs):
            return original_client(*args, opener=transport, **kwargs)
        def state():
            value = deepcopy(start or snapshot())
            value["resident_models"] = [{"name": model} for model in transport.resident]
            return value
        with ExitStack() as stack:
            stack.enter_context(patch.object(runner, "source_hashes", side_effect=sources,
                                             return_value={"offline_source": "frozen"}))
            stack.enter_context(patch.object(runner, "capture_safety_snapshot", side_effect=state))
            stack.enter_context(patch.object(runner, "_installed_models", return_value={}))
            stack.enter_context(patch.object(runner, "_model_metadata", side_effect=lambda model, installed: {"model": model}))
            stack.enter_context(patch.object(runner, "_http_json", return_value={"version": "offline"}))
            stack.enter_context(patch.object(runner, "_resident_models", side_effect=lambda: tuple({"name": m} for m in transport.resident)))
            stack.enter_context(patch.object(runner, "GuardedSampler", FakeSampler))
            stack.enter_context(patch.object(runner.ComparisonBackend, "check", return_value={}))
            client = stack.enter_context(patch.object(runner, "ComparisonClient", side_effect=factory))
            embedder = stack.enter_context(patch.object(runner, "BgeOnnxEmbedder", return_value=FakeEmbedder()))
            unload = stack.enter_context(patch.object(runner, "_force_unload", return_value=[]))
            with redirect_stdout(io.StringIO()):
                result = runner.main(["--workload", str(workload), "--freeze", str(frozen),
                                      "--output-dir", str(directory), "--arm", arm, "--repetition", "1"]
                                     + (["--preflight-only"] if preflight else []))
            called = {"client": client.call_count, "embedder": embedder.call_count, "force_unload": unload.call_count}
        observations = directory / "observations.jsonl"
        rows = [json.loads(line) for line in observations.read_text().splitlines()] if observations.exists() else []
        return result, rows, json.loads((directory / "finish.json").read_text()), called, transport

    def test_real_http_fixed_arms_never_call_or_unload_peer_and_keep_own_model_resident(self):
        for arm, model in (("small", SMALL), ("large", LARGE)):
            with self.subTest(arm=arm), tempfile.TemporaryDirectory() as tmp:
                result, rows, finish, _, transport = self.run_offline(Path(tmp), arm, (HARD, EASY, AMBIGUOUS))
                self.assertEqual(result, 0)
                self.assertEqual(len(rows), 3)
                self.assertTrue(all(row["status"] == "ok" for row in rows))
                self.assertEqual([len(row["calls"]) for row in rows], [1, 1, 2])
                self.assertEqual({r["body"]["model"] for r in transport.requests}, {model})
                self.assertEqual(len(transport.classifiers), 1)
                self.assertTrue(all(r["body"]["keep_alive"] == -1 for r in transport.chats))
                self.assertTrue(all(r["body"]["options"]["seed"] == 42 for r in transport.chats))
                self.assertEqual([row["resident_hint_after"] for row in rows], [model] * 3)
                self.assertEqual(transport.resident, set())
                self.assertTrue(finish["source_unchanged"])
                self.assertTrue(finish["model_metadata_unchanged"])
                sent = json.dumps(transport.requests)
                for private_metadata in ("GOLD_MUST_NEVER", "CASE_METADATA_SENTINEL", "SCENARIO_SENTINEL", "STRATUM_SENTINEL"):
                    self.assertNotIn(private_metadata, sent)

    def test_router_hysteresis_persists_across_fresh_conversations(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, rows, finish, _, transport = self.run_offline(Path(tmp), "cascade", (HARD, HARD, EASY, EASY))
            self.assertEqual(result, 0)
            self.assertEqual([row["generation"]["model"] for row in rows], [LARGE, LARGE, LARGE, SMALL])
            self.assertEqual(transport.classifiers, [])
            self.assertEqual([r["body"]["model"] for r in transport.requests if r["endpoint"] == "generate"],
                             [SMALL, LARGE, SMALL])  # Initial peer cleanup, switch, terminal cleanup.
            for row in rows:
                self.assertEqual(row["profile_id"], runner.PROFILE_ID)
                self.assertIsNone(row["route"]["memory_required_generation"])
                self.assertIsNone(row["route"]["model_size_generation"])
                self.assertEqual(len(row["calls"][0]["messages"]), 2)
                self.assertEqual(row["route"]["policy"], "lightweight_v1")
            self.assertEqual(finish["cleanup_errors"], [])

    def test_actual_shared_memory_path_uses_seed_and_fixed_large_for_generation(self):
        transport = RecordingTransport()
        transport.speeches.append("Your chosen instrument is the piano.")
        with tempfile.TemporaryDirectory() as tmp:
            result, rows, _, _, _ = self.run_offline(Path(tmp), "large", ("What is my chosen instrument?",), transport=transport)
            self.assertEqual(result, 0)
            self.assertEqual(rows[0]["status"], "ok")
            self.assertEqual(len(rows[0]["retrieval_calls"]), 1)
            self.assertEqual(rows[0]["response"]["memory_used"], ["mem_" + f"{2:032x}"])
            self.assertEqual(rows[0]["generation"]["model"], LARGE)
            self.assertEqual(transport.classifiers, [])
            self.assertEqual(len(json.loads((Path(tmp) / "output/memory_setup.json").read_text())["events"]), len(seed()["events"]))

    def test_output_validation_failure_remains_denominator_and_next_case_runs(self):
        transport = RecordingTransport()
        transport.speeches.extend(("memory_ref_1", "Your chosen instrument is the piano."))
        with tempfile.TemporaryDirectory() as tmp:
            prompt = "What is my chosen instrument?"
            result, rows, finish, _, _ = self.run_offline(Path(tmp), "small", (prompt, prompt), transport=transport)
            self.assertEqual(result, 0)
            self.assertEqual([r["status"] for r in rows], ["error", "ok"])
            self.assertIn("raw_generation", rows[0]["calls"][0])
            self.assertEqual(finish["status"], "complete_with_errors")

    def test_transport_failure_stops_after_durable_failed_attempt_and_cleans_only_own_model(self):
        transport = RecordingTransport()
        transport.fail_next_generation = True
        with tempfile.TemporaryDirectory() as tmp:
            result, rows, finish, _, _ = self.run_offline(Path(tmp), "large", (EASY, EASY), transport=transport)
            self.assertEqual(result, 1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "interrupted")
            self.assertEqual({r["body"]["model"] for r in transport.requests}, {LARGE})
            self.assertEqual(transport.resident, set())
            self.assertEqual(finish["cleanup_errors"], [])

    def test_blocked_admission_never_constructs_client_embedder_or_unloads(self):
        before = pair.MAX_START_SWAP_USED_KIB
        with tempfile.TemporaryDirectory() as tmp:
            result, rows, finish, called, transport = self.run_offline(
                Path(tmp), "large", (EASY,),
                start=snapshot(swap=device_guard.MAX_START_SWAP_USED_KIB + 1))
            self.assertEqual(result, 1)
            self.assertEqual(rows, [])
            self.assertEqual(called, {"client": 0, "embedder": 0, "force_unload": 0})
            self.assertEqual(transport.requests, [])
            self.assertEqual(finish["status"], "blocked_preflight")
            self.assertFalse(finish["admitted"])
            self.assertIn("swap", finish["failure"]["message"].lower())
        self.assertEqual(pair.MAX_START_SWAP_USED_KIB, before)

    def test_ready_preflight_only_performs_no_inference_or_memory_setup(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, rows, finish, called, transport = self.run_offline(Path(tmp), "cascade", (EASY,), preflight=True)
            self.assertEqual(result, 0)
            self.assertEqual(rows, [])
            self.assertEqual(called, {"client": 0, "embedder": 0, "force_unload": 0})
            self.assertEqual(transport.requests, [])
            self.assertEqual(finish["status"], "preflight_passed_no_inference")
            self.assertFalse((Path(tmp) / "output/memory.sqlite3").exists())

    def test_end_source_change_invalidates_session_without_erasing_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, rows, finish, _, transport = self.run_offline(
                Path(tmp), "small", (EASY,), sources=[{"offline_source": "frozen"}, {"offline_source": "changed"}])
            self.assertEqual(result, 1)
            self.assertEqual(len(rows), 1)
            self.assertFalse(finish["source_unchanged"])
            self.assertEqual(finish["status"], "end_verification_failed")
            self.assertEqual(transport.resident, set())
            summary = json.loads((Path(tmp) / "output/summary.json").read_text())
            self.assertEqual(summary["status"], finish["status"])

    def test_post_snapshot_failure_is_durable_missing_evidence_and_stops_next_case(self):
        transport = RecordingTransport()
        written, records, http = [], [], []
        config = runner.single_model_config(load_config(), SMALL)
        client = runner.ComparisonClient(config.ollama, config.generation, opener=transport,
                                         retain_large_model=True, http_writer=SimpleNamespace(write=http.append))
        backend = runner.ComparisonBackend(client, {}, SimpleNamespace(monitor=SimpleNamespace(violation=None)), (SMALL,))
        with tempfile.TemporaryDirectory() as tmp:
            store, _ = runner.materialize_seed(seed(), Path(tmp) / "memory.sqlite3", FakeEmbedder())
            cases = [{"id": str(i), "scenario_id": "x", "stratum": "x", "prompt": EASY} for i in range(2)]
            with patch.object(backend, "check", return_value={}), \
                 patch.object(runner, "_resident_models", side_effect=[(), RuntimeError("offline snapshot unavailable")]), \
                 redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "snapshot unavailable"):
                    runner.run_cases(cases, "small", 1, config, backend, store,
                                     SimpleNamespace(write=written.append), records)
        self.assertEqual(len(written), 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(len(transport.generations), 1)
        self.assertEqual(records[0]["status"], "interrupted")
        self.assertTrue(records[0]["post_snapshot_attempted"])
        self.assertIsNone(records[0]["api_ps_after"])
        self.assertEqual(records[0]["post_snapshot_error"]["error"], "RuntimeError")
        client.unload_all()

    def test_sole_model_enforcement_rejects_peer_before_any_http_call(self):
        transport = RecordingTransport()
        config = runner.single_model_config(load_config(), LARGE)
        client = runner.ComparisonClient(config.ollama, config.generation, opener=transport,
                                         http_writer=SimpleNamespace(write=lambda record: None), retain_large_model=True)
        monitor = SimpleNamespace(violation=None)
        backend = runner.ComparisonBackend(client, {}, SimpleNamespace(monitor=monitor), (LARGE,))
        with self.assertRaises(runner.SafetyGateError):
            backend.chat(SMALL, (ChatMessage("user", "Hello"),))
        self.assertEqual(transport.requests, [])
        self.assertEqual(monitor.violation, "attempt to call a model outside this arm")


if __name__ == "__main__":
    unittest.main()
