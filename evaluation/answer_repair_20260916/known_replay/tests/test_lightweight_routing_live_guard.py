"""Offline admission and cleanup tests for the bounded live diagnostic."""

from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_lightweight_routing_live as live
from oline_hri import evaluation_model_pairs as pair


def snapshot(*, swap=768 * 1024):
    return {"boot_id": "offline-boot", "fan_pwm": 80,
            "memory": {"mem_available_kib": 3 * 1024 * 1024, "swap_used_kib": swap},
            "temperatures_c": {"cpu": 52.0}, "thermal_trip_events": {"cpu": 0},
            "power_mode": "NV Power Mode: 15W\n0", "resident_models": []}


class FakeSampler:
    def __init__(self, monitor):
        self.monitor = monitor
        self.samples = [object()]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def summary(self):
        return {"scope": "offline test sampler", "sample_count": 1}


class LightweightLiveGuardTests(unittest.TestCase):
    def test_blocked_start_writes_evidence_without_constructing_client_or_unloading(self):
        old_limit = pair.MAX_START_SWAP_USED_KIB
        for policy in ("llm", "lightweight"):
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
                directory = Path(temporary) / policy
                stack.enter_context(patch.object(live, "capture_safety_snapshot",
                                                 return_value=snapshot(swap=769 * 1024)))
                client = stack.enter_context(patch.object(live, "HttpRecordingClient"))
                sampler = stack.enter_context(patch.object(live, "GuardedSampler"))
                installed = stack.enter_context(patch.object(live, "_installed_models"))
                unload = stack.enter_context(patch.object(live, "_force_unload"))
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(live.main(["--policy", policy, "--output-dir", str(directory)]), 1)
                for forbidden in (client, sampler, installed, unload):
                    forbidden.assert_not_called()
                finish = json.loads((directory / "finish.json").read_text())
                self.assertEqual(finish["status"], "blocked_preflight")
                self.assertEqual(finish["attempted"], 0)
                self.assertFalse(finish["admitted"])
                self.assertIn("768 MiB", finish["failure"]["message"])
                self.assertFalse((directory / "http_calls.jsonl").exists())
                self.assertFalse((directory / "observations.jsonl").exists())
                self.assertTrue(json.loads((directory / "plan.json").read_text())["source_sha256"])
            self.assertEqual(pair.MAX_START_SWAP_USED_KIB, old_limit)

    def test_preflight_only_never_calls_models_even_when_device_is_ready(self):
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(live, "capture_safety_snapshot", return_value=snapshot()), \
             patch.object(live, "HttpRecordingClient") as client, \
             patch.object(live, "_installed_models") as installed:
            directory = Path(temporary) / "ready"
            with redirect_stdout(io.StringIO()):
                result = live.main(["--policy", "lightweight", "--preflight-only",
                                    "--output-dir", str(directory)])
            self.assertEqual(result, 0)
            client.assert_not_called()
            installed.assert_not_called()
            finish = json.loads((directory / "finish.json").read_text())
            self.assertEqual(finish["status"], "preflight_passed_no_inference")
            self.assertEqual(finish["attempted"], 0)

    def test_existing_output_directory_is_never_reused(self):
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(live, "capture_safety_snapshot") as capture:
            path = Path(temporary) / "existing"
            path.mkdir()
            sentinel = path / "sentinel"
            sentinel.write_text("preserve original")
            with self.assertRaises(Exception):
                live.main(["--policy", "lightweight", "--output-dir", str(path)])
            self.assertEqual(sentinel.read_text(), "preserve original")
            capture.assert_not_called()

    def run_mock_http(self, directory, *, fail_chat=False):
        actual_client = live.HttpRecordingClient
        requests = []

        def opener(request, timeout):
            body = json.loads(request.data)
            endpoint = request.full_url.rsplit("/", 1)[-1]
            requests.append((endpoint, body))
            if endpoint == "generate":
                payload = {"model": body["model"], "done": True,
                           "done_reason": "unload", "response": ""}
            elif fail_chat:
                raise URLError("offline simulated transport failure")
            else:
                self.assertIn("speech", body["format"]["properties"])
                payload = {"model": body["model"], "done": True, "done_reason": "stop",
                           "message": {"role": "assistant", "content": json.dumps({
                               "speech": "Integration response.", "gesture_id": "NO_ACTION", "memory_used": []})},
                           "load_duration": 11, "prompt_eval_count": 12, "eval_count": 4}
            return io.BytesIO(json.dumps(payload).encode())

        def client_factory(*args, **kwargs):
            return actual_client(*args, opener=opener, **kwargs)

        with patch.object(live, "capture_safety_snapshot", side_effect=lambda: deepcopy(snapshot())), \
             patch.object(live, "_installed_models", return_value={}), \
             patch.object(live, "_model_metadata", return_value={"scope": "offline fake model"}), \
             patch.object(live, "_http_json", return_value={"version": "offline"}), \
             patch.object(live, "_resident_models", return_value=()), \
             patch.object(live, "GuardedSampler", FakeSampler), \
             patch.object(live.DiagnosticBackend, "check", return_value={}), \
             patch.object(live, "HttpRecordingClient", side_effect=client_factory), \
             redirect_stdout(io.StringIO()):
            result = live.main(["--policy", "lightweight", "--output-dir", str(directory)])
        return result, requests

    def test_real_conversation_router_and_client_use_retained_large_then_small_without_classifiers(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "offline"
            result, requests = self.run_mock_http(directory)
            self.assertEqual(result, 0)
            small, large = "qwen3:0.6b", "qwen3:1.7b"
            self.assertEqual([(endpoint, body["model"], body["keep_alive"]) for endpoint, body in requests], [
                ("generate", small, 0), ("chat", large, -1), ("chat", large, -1),
                ("chat", large, -1), ("generate", large, 0), ("chat", small, -1),
                ("chat", small, -1), ("generate", small, 0)])
            rows = [json.loads(line) for line in (directory / "observations.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows), 5)
            self.assertTrue(all(row["status"] == "ok" for row in rows))
            self.assertEqual([row["resident_hint_after"] for row in rows], [large] * 3 + [small] * 2)
            for row in rows:
                self.assertIsNone(row["route"]["model_size_generation"])
                self.assertIsNone(row["route"]["memory_required_generation"])
                self.assertEqual(row["retrieval_calls"], [])
                self.assertEqual(len(row["calls"]), 1)
                self.assertEqual(row["generation"]["load_duration_ns"], 11)
            saved_http = [json.loads(line) for line in (directory / "http_calls.jsonl").read_text().splitlines()]
            self.assertEqual(len(saved_http), len(requests))
            self.assertEqual(json.loads((directory / "finish.json").read_text())["cleanup_errors"], [])

    def test_actual_http_failure_stops_next_request_and_cleans_unknown_residency(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "failed"
            result, requests = self.run_mock_http(directory, fail_chat=True)
            self.assertEqual(result, 1)
            self.assertEqual(sum(endpoint == "chat" for endpoint, _ in requests), 1)
            self.assertEqual([(endpoint, body["model"]) for endpoint, body in requests[-2:]],
                             [("generate", "qwen3:0.6b"), ("generate", "qwen3:1.7b")])
            finish = json.loads((directory / "finish.json").read_text())
            self.assertEqual(finish["status"], "failed")
            self.assertEqual(finish["attempted"], 1)
            self.assertEqual(finish["cleanup_errors"], [])
            rows = [json.loads(line) for line in (directory / "observations.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "error")
            self.assertEqual(rows[0]["calls"][0]["status"], "error")


if __name__ == "__main__":
    unittest.main()
