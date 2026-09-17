"""Focused offline checks for guard transparency and frozen-source rejection."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("fresh_guard", Path(__file__).with_name("run_guarded.py"))
guarded = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guarded)


class GuardedLauncherTests(unittest.TestCase):
    def test_chat_preserves_exact_generation_options_and_residency(self):
        client, guard = Mock(), Mock()
        client.resident_model = "qwen3:1.7b"
        wrapper = guarded.TransparentGuardedClient(client, guard)
        messages = [object()]
        options = {"response_format": {"properties": {"speech": {"type": "string"}}},
                   "temperature": 0.23, "seed": 7}
        self.assertIs(wrapper.chat("qwen3:1.7b", messages, **options), client.chat.return_value)
        client.chat.assert_called_once_with("qwen3:1.7b", messages, **options)
        self.assertEqual(guard.check.call_count, 2)
        self.assertEqual(wrapper.resident_model, "qwen3:1.7b")
        wrapper.unload_all()
        client.unload_all.assert_called_once_with()

    def test_guard_prevents_inference_but_preserves_cleanup(self):
        client, guard = Mock(), Mock()
        guard.check.side_effect = guarded.pair.SafetyGateError("test abort")
        wrapper = guarded.TransparentGuardedClient(client, guard)
        with self.assertRaises(guarded.pair.SafetyGateError):
            wrapper.chat("qwen3:0.6b", [])
        client.chat.assert_not_called()
        wrapper.unload_all()
        client.unload_all.assert_called_once_with()

    def test_candidate_drift_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            path.write_text(json.dumps({"source_sha256": {"source.py": "frozen"}}))
            guarded.verify_candidate(path, {"source.py": "frozen"})
            with self.assertRaisesRegex(ValueError, "candidate differs"):
                guarded.verify_candidate(path, {"source.py": "changed"})

    def test_validate_only_checks_actual_assets_without_inference_or_device_access(self):
        with tempfile.TemporaryDirectory(prefix="fresh-routing-offline-") as temporary:
            base = Path(temporary)
            cases = base / "cases.json"
            cases.write_text(json.dumps([{"id": "offline_only", "text": "Explain condensation.",
                                          "expected_modes": ["none"]}]))
            with patch.object(guarded.pair, "_http_json", side_effect=AssertionError("network accessed")), \
                    patch.object(guarded.pair, "capture_safety_snapshot", side_effect=AssertionError("device accessed")), \
                    patch.object(guarded.runner, "main", side_effect=AssertionError("inference started")):
                code = guarded.main(["--cases", str(cases), "--output-dir", str(base / "validation"),
                                     "--validate-only"])
            self.assertEqual(code, 0)
            report = json.loads((base / "validation/validation.json").read_text())
            self.assertFalse(report["inference_started"])
            self.assertFalse(report["device_or_network_access"])


if __name__ == "__main__":
    unittest.main()
