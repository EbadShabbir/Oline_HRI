import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from oline_hri.config import (
    DEFAULT_CONFIG_PATH,
    GENERAL_LARGE_MODEL_ID,
    LARGE_MODEL_ID,
    ROUTER_MODEL_ID,
    ConfigError,
    load_config,
    parse_config,
)


class ConfigTests(unittest.TestCase):
    def test_default_config_loads(self) -> None:
        config = load_config()

        self.assertEqual(config.schema_version, 7)
        self.assertEqual(config.ollama.small_model, ROUTER_MODEL_ID)
        self.assertEqual(
            config.ollama.general_large_model, GENERAL_LARGE_MODEL_ID
        )
        self.assertEqual(config.ollama.large_model, LARGE_MODEL_ID)
        self.assertEqual(config.ollama.request_timeout_seconds, 60)
        self.assertEqual(config.ollama.large_request_timeout_seconds, 120)
        self.assertEqual(config.ollama.unload_timeout_seconds, 30)
        self.assertEqual(config.generation.context_length, 2048)
        self.assertEqual(config.generation.max_output_tokens, 192)
        self.assertEqual(config.generation.temperature, 0.0)
        self.assertFalse(config.generation.thinking)
        self.assertEqual(config.memory.profile_id, "default_user")
        self.assertEqual(config.memory.retention_days, 7)
        self.assertTrue(config.memory.database_path.startswith("~/"))
        self.assertEqual(
            config.embedding.model_directory,
            "~/.local/share/oline-hri/models/bge-small-en-v1.5/"
            "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
        )
        self.assertEqual(config.embedding.intra_op_threads, 2)
        self.assertEqual(config.speech.capture_executable_path, "/usr/bin/arecord")
        self.assertEqual(
            config.speech.capture_device, "plughw:CARD=Microphone,DEV=0"
        )
        self.assertEqual(config.speech.sample_rate_hz, 16000)
        self.assertEqual(config.speech.chunk_samples, 512)
        self.assertTrue(config.speech.silero.model_path.startswith("~/"))
        self.assertEqual(config.speech.silero.threshold, 0.5)
        self.assertEqual(config.speech.silero.silence_threshold, 0.35)
        self.assertEqual(config.speech.silero.pre_roll_seconds, 0.3)
        self.assertEqual(config.speech.silero.start_timeout_seconds, 30.0)
        self.assertEqual(config.speech.silero.start_trigger_seconds, 0.096)
        self.assertEqual(config.speech.silero.end_silence_seconds, 1.0)
        self.assertEqual(config.speech.silero.min_utterance_seconds, 0.3)
        self.assertEqual(config.speech.silero.max_utterance_seconds, 30.0)
        self.assertTrue(config.speech.whisper.executable_path.startswith("~/"))
        self.assertTrue(config.speech.whisper.primary_model_path.startswith("~/"))
        self.assertTrue(config.speech.whisper.fallback_model_path.startswith("~/"))
        self.assertEqual(config.speech.whisper.language, "en")
        self.assertEqual(config.speech.whisper.threads, 4)
        self.assertEqual(config.speech.whisper.timeout_seconds, 120)
        self.assertEqual(config.speech.quality.min_mean_token_probability, 0.2)
        self.assertEqual(config.speech.quality.min_text_characters, 1)
        self.assertEqual(config.speech.quality.max_text_characters, 1000)

    def test_custom_config_path_loads(self) -> None:
        data = load_config().to_dict()
        data["profile"]["active"] = "test_profile"

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            config = load_config(path)

        self.assertEqual(config.profile.active, "test_profile")

    def test_packaged_default_is_available_without_source_tree(self) -> None:
        with patch(
            "oline_hri.config.DEFAULT_CONFIG_PATH", Path("/missing/default.json")
        ):
            config = load_config()

        self.assertEqual(config.ollama.small_model, "qwen3:0.6b")

    def test_source_and_packaged_defaults_match(self) -> None:
        source_default = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
        with patch(
            "oline_hri.config.DEFAULT_CONFIG_PATH", Path("/missing/default.json")
        ):
            packaged_default = load_config().to_dict()

        self.assertEqual(source_default, packaged_default)

    def test_unknown_field_is_rejected(self) -> None:
        data = load_config().to_dict()
        data["ollama"]["typo_model"] = "bad"

        with self.assertRaisesRegex(ConfigError, "unknown fields: typo_model"):
            parse_config(data)

    def test_loopback_ollama_urls_are_accepted(self) -> None:
        cases = {
            "http://localhost:11434": "http://localhost:11434",
            "https://LOCALHOST:11434/": "https://LOCALHOST:11434",
            "http://127.0.0.1:11434": "http://127.0.0.1:11434",
            "http://127.42.99.7:11434": "http://127.42.99.7:11434",
            "http://127.255.255.254:11434": "http://127.255.255.254:11434",
            "http://[::1]:11434": "http://[::1]:11434",
        }
        for base_url, expected in cases.items():
            with self.subTest(base_url=base_url):
                data = load_config().to_dict()
                data["ollama"]["base_url"] = base_url

                config = parse_config(data)

                self.assertEqual(config.ollama.base_url, expected)

    def test_non_loopback_ollama_urls_are_rejected(self) -> None:
        for base_url in (
            "http://192.168.1.20:11434",
            "https://example.com:11434",
            "http://localhost.example:11434",
            "http://128.0.0.1:11434",
        ):
            with self.subTest(base_url=base_url):
                data = load_config().to_dict()
                data["ollama"]["base_url"] = base_url

                with self.assertRaisesRegex(ConfigError, "local loopback"):
                    parse_config(data)

    def test_router_model_is_fixed_to_qwen3_point_6b(self) -> None:
        for model in ("qwen3:4b", "qwen3:0.6b-instruct", "QWEN3:0.6B"):
            with self.subTest(model=model):
                data = load_config().to_dict()
                data["ollama"]["small_model"] = model

                with self.assertRaisesRegex(ConfigError, "structured routing"):
                    parse_config(data)

    def test_large_model_is_fixed_to_qwen3_1_7b(self) -> None:
        for model in ("qwen3:0.6b", "qwen3:4b", "QWEN3:1.7B"):
            with self.subTest(model=model):
                data = load_config().to_dict()
                data["ollama"]["large_model"] = model

                with self.assertRaisesRegex(ConfigError, "four-route generation"):
                    parse_config(data)

    def test_general_large_model_is_fixed_to_qwen3_1_7b(self) -> None:
        for model in ("qwen3:0.6b", "qwen3:4b", "QWEN3:1.7B"):
            with self.subTest(model=model):
                data = load_config().to_dict()
                data["ollama"]["general_large_model"] = model

                with self.assertRaisesRegex(
                    ConfigError, "large requests without memory"
                ):
                    parse_config(data)

    def test_ollama_url_credentials_are_rejected(self) -> None:
        for base_url in (
            "http://user@localhost:11434",
            "http://user:password@127.0.0.1:11434",
            "http://@[::1]:11434",
        ):
            with self.subTest(base_url=base_url):
                data = load_config().to_dict()
                data["ollama"]["base_url"] = base_url

                with self.assertRaisesRegex(ConfigError, "local loopback"):
                    parse_config(data)

    def test_ollama_url_query_fragment_and_paths_are_rejected(self) -> None:
        for base_url in (
            "http://localhost:11434?token=secret",
            "http://localhost:11434#fragment",
            "http://localhost:11434?",
            "http://localhost:11434#",
            "http://localhost:11434/api",
            "http://localhost:11434/api/chat",
            "http://localhost:11434//",
            "http://localhost:11434/;parameter",
        ):
            with self.subTest(base_url=base_url):
                data = load_config().to_dict()
                data["ollama"]["base_url"] = base_url

                with self.assertRaisesRegex(ConfigError, "local loopback"):
                    parse_config(data)

    def test_malformed_ollama_authority_is_a_config_error(self) -> None:
        for base_url in (
            "http://localhost:not-a-port",
            "http://localhost:65536",
            "http://[::1",
        ):
            with self.subTest(base_url=base_url):
                data = load_config().to_dict()
                data["ollama"]["base_url"] = base_url

                with self.assertRaisesRegex(ConfigError, "HTTP or HTTPS URL"):
                    parse_config(data)

    def test_invalid_generation_range_is_rejected(self) -> None:
        data = load_config().to_dict()
        data["generation"]["max_output_tokens"] = 4096

        with self.assertRaisesRegex(ConfigError, "no larger than context_length"):
            parse_config(data)

    def test_ollama_timeouts_are_strictly_validated(self) -> None:
        for field in (
            "request_timeout_seconds",
            "large_request_timeout_seconds",
            "unload_timeout_seconds",
        ):
            for value in (True, False, 0, 3601, 1.5, "60"):
                with self.subTest(field=field, value=value):
                    data = load_config().to_dict()
                    data["ollama"][field] = value

                    with self.assertRaisesRegex(
                        ConfigError, rf"ollama\.{field}"
                    ):
                        parse_config(data)

    def test_large_timeout_cannot_be_shorter_than_small_timeout(self) -> None:
        data = load_config().to_dict()
        data["ollama"]["request_timeout_seconds"] = 61
        data["ollama"]["large_request_timeout_seconds"] = 60

        with self.assertRaisesRegex(ConfigError, "must be no smaller"):
            parse_config(data)

    def test_unsupported_schema_is_rejected(self) -> None:
        data = load_config().to_dict()
        data["schema_version"] = 99

        with self.assertRaisesRegex(ConfigError, "unsupported schema_version"):
            parse_config(data)

    def test_pre_memory_configuration_schema_is_rejected_explicitly(self) -> None:
        data = load_config().to_dict()
        data["schema_version"] = 1
        del data["memory"]

        with self.assertRaisesRegex(ConfigError, "unsupported schema_version: 1"):
            parse_config(data)

    def test_pre_embedding_configuration_schema_is_rejected_explicitly(self) -> None:
        data = load_config().to_dict()
        data["schema_version"] = 2
        del data["embedding"]

        with self.assertRaisesRegex(ConfigError, "unsupported schema_version: 2"):
            parse_config(data)

    def test_pre_timeout_configuration_schema_is_rejected_explicitly(self) -> None:
        data = load_config().to_dict()
        data["schema_version"] = 3
        del data["ollama"]["large_request_timeout_seconds"]
        del data["ollama"]["unload_timeout_seconds"]

        with self.assertRaisesRegex(ConfigError, "unsupported schema_version: 3"):
            parse_config(data)

    def test_pre_speech_configuration_schema_is_rejected_explicitly(self) -> None:
        data = load_config().to_dict()
        data["schema_version"] = 4
        del data["speech"]

        with self.assertRaisesRegex(ConfigError, "unsupported schema_version: 4"):
            parse_config(data)

    def test_pre_general_large_model_schema_is_rejected_explicitly(self) -> None:
        data = load_config().to_dict()
        data["schema_version"] = 5
        del data["ollama"]["general_large_model"]

        with self.assertRaisesRegex(ConfigError, "unsupported schema_version: 5"):
            parse_config(data)

    def test_pre_retention_policy_schema_is_rejected_explicitly(self) -> None:
        data = load_config().to_dict()
        data["schema_version"] = 6
        del data["memory"]["retention_days"]

        with self.assertRaisesRegex(ConfigError, "unsupported schema_version: 6"):
            parse_config(data)

    def test_memory_retention_days_is_strictly_validated(self) -> None:
        for value in (True, False, 0, 3651, 1.5, "7"):
            with self.subTest(value=value):
                data = load_config().to_dict()
                data["memory"]["retention_days"] = value

                with self.assertRaisesRegex(ConfigError, "memory.retention_days"):
                    parse_config(data)

    def test_missing_speech_section_is_rejected(self) -> None:
        data = load_config().to_dict()
        del data["speech"]

        with self.assertRaisesRegex(ConfigError, "missing: speech"):
            parse_config(data)

    def test_missing_and_unknown_speech_fields_are_rejected(self) -> None:
        for field in (
            "capture_executable_path",
            "capture_device",
            "sample_rate_hz",
            "chunk_samples",
            "silero",
            "whisper",
            "quality",
        ):
            with self.subTest(missing=field):
                data = load_config().to_dict()
                del data["speech"][field]

                with self.assertRaisesRegex(ConfigError, f"missing: {field}"):
                    parse_config(data)

        data = load_config().to_dict()
        data["speech"]["unknown"] = "value"
        with self.assertRaisesRegex(ConfigError, "unknown fields: unknown"):
            parse_config(data)

    def test_invalid_speech_capture_settings_are_rejected(self) -> None:
        for executable_path in (
            "",
            "   ",
            "bin/arecord",
            "bad\x00path",
            "/tmp/bidi\u202efile",
            "/tmp/zero\u200bwidth",
        ):
            with self.subTest(executable_path=executable_path):
                data = load_config().to_dict()
                data["speech"]["capture_executable_path"] = executable_path

                with self.assertRaisesRegex(
                    ConfigError, "speech.capture_executable_path"
                ):
                    parse_config(data)

        for capture_device in (
            "",
            "   ",
            "device\nname",
            "device\u202ename",
            "device\u200bname",
            "x" * 256,
        ):
            with self.subTest(capture_device=capture_device):
                data = load_config().to_dict()
                data["speech"]["capture_device"] = capture_device

                with self.assertRaisesRegex(ConfigError, "speech.capture_device"):
                    parse_config(data)

        for sample_rate in (True, 8000, 48000, 16000.0, "16000"):
            with self.subTest(sample_rate=sample_rate):
                data = load_config().to_dict()
                data["speech"]["sample_rate_hz"] = sample_rate

                with self.assertRaisesRegex(ConfigError, "speech.sample_rate_hz"):
                    parse_config(data)

        for chunk_samples in (True, 80, 511, 513, 4096, 512.0, "512"):
            with self.subTest(chunk_samples=chunk_samples):
                data = load_config().to_dict()
                data["speech"]["chunk_samples"] = chunk_samples

                with self.assertRaisesRegex(ConfigError, "speech.chunk_samples"):
                    parse_config(data)

    def test_missing_and_unknown_silero_fields_are_rejected(self) -> None:
        fields = (
            "model_path",
            "threshold",
            "silence_threshold",
            "pre_roll_seconds",
            "start_timeout_seconds",
            "start_trigger_seconds",
            "end_silence_seconds",
            "min_utterance_seconds",
            "max_utterance_seconds",
        )
        for field in fields:
            with self.subTest(missing=field):
                data = load_config().to_dict()
                del data["speech"]["silero"][field]

                with self.assertRaisesRegex(ConfigError, f"missing: {field}"):
                    parse_config(data)

        data = load_config().to_dict()
        data["speech"]["silero"]["unknown"] = "value"
        with self.assertRaisesRegex(ConfigError, "unknown fields: unknown"):
            parse_config(data)

    def test_invalid_silero_model_path_is_rejected(self) -> None:
        for model_path in ("", "   ", "models/silero.onnx", "bad\x00path"):
            with self.subTest(model_path=model_path):
                data = load_config().to_dict()
                data["speech"]["silero"]["model_path"] = model_path

                with self.assertRaisesRegex(
                    ConfigError, r"speech\.silero\.model_path"
                ):
                    parse_config(data)

    def test_invalid_silero_numeric_settings_are_rejected(self) -> None:
        invalid_values = {
            "threshold": (True, 0, 1, -0.1, 1.1, 10**400, "0.5"),
            "silence_threshold": (True, -0.1, 1, 1.1, "0.35"),
            "pre_roll_seconds": (True, -0.1, 5.1, "0.3"),
            "start_timeout_seconds": (True, 0.9, 600.1, "30"),
            "start_trigger_seconds": (True, 0, 2.1, "0.1"),
            "end_silence_seconds": (True, 0, 5.1, "1.0"),
            "min_utterance_seconds": (True, 0, 10.1, "0.3"),
            "max_utterance_seconds": (True, 0.9, 300.1, "30"),
        }
        for field, values in invalid_values.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    data = load_config().to_dict()
                    data["speech"]["silero"][field] = value

                    with self.assertRaisesRegex(
                        ConfigError, rf"speech\.silero\.{field}"
                    ):
                        parse_config(data)

    def test_invalid_silero_timing_relationships_are_rejected(self) -> None:
        cases = (
            ("start_trigger_seconds", 0.5, "min_utterance_seconds"),
            ("min_utterance_seconds", 2.0, "max_utterance_seconds"),
            ("end_silence_seconds", 2.0, "max_utterance_seconds"),
        )
        for field, value, smaller_field in cases:
            with self.subTest(field=field):
                data = load_config().to_dict()
                data["speech"]["silero"][field] = value
                if smaller_field == "max_utterance_seconds":
                    data["speech"]["silero"][smaller_field] = 1.0

                with self.assertRaisesRegex(ConfigError, "must be no larger"):
                    parse_config(data)

        data = load_config().to_dict()
        data["speech"]["silero"]["start_timeout_seconds"] = 1.0
        data["speech"]["silero"]["start_trigger_seconds"] = 2.0
        data["speech"]["silero"]["min_utterance_seconds"] = 2.0
        with self.assertRaisesRegex(ConfigError, "start_timeout_seconds"):
            parse_config(data)

        data = load_config().to_dict()
        data["speech"]["silero"]["start_timeout_seconds"] = 1.0
        data["speech"]["silero"]["start_trigger_seconds"] = 1.0
        data["speech"]["silero"]["min_utterance_seconds"] = 1.0
        with self.assertRaisesRegex(ConfigError, "frame boundary"):
            parse_config(data)

        data = load_config().to_dict()
        data["speech"]["silero"]["start_timeout_seconds"] = 1.984
        data["speech"]["silero"]["start_trigger_seconds"] = 1.984
        data["speech"]["silero"]["min_utterance_seconds"] = 2.0
        with self.assertRaisesRegex(ConfigError, "frame boundary"):
            parse_config(data)

        data = load_config().to_dict()
        data["speech"]["silero"]["min_utterance_seconds"] = 1.0
        data["speech"]["silero"]["max_utterance_seconds"] = 1.0
        with self.assertRaisesRegex(ConfigError, "frame boundary"):
            parse_config(data)

        data = load_config().to_dict()
        data["speech"]["silero"]["pre_roll_seconds"] = 0.7
        data["speech"]["silero"]["min_utterance_seconds"] = 0.5
        data["speech"]["silero"]["max_utterance_seconds"] = 1.0
        with self.assertRaisesRegex(ConfigError, "pre-roll"):
            parse_config(data)

    def test_silero_hysteresis_requires_a_lower_silence_threshold(self) -> None:
        for threshold, silence_threshold in ((0.3, 0.35), (0.5, 0.5)):
            with self.subTest(
                threshold=threshold, silence_threshold=silence_threshold
            ):
                data = load_config().to_dict()
                data["speech"]["silero"]["threshold"] = threshold
                data["speech"]["silero"][
                    "silence_threshold"
                ] = silence_threshold

                with self.assertRaisesRegex(
                    ConfigError, r"speech\.silero\.silence_threshold"
                ):
                    parse_config(data)

    def test_missing_and_unknown_whisper_fields_are_rejected(self) -> None:
        fields = (
            "executable_path",
            "primary_model_path",
            "fallback_model_path",
            "language",
            "threads",
            "timeout_seconds",
        )
        for field in fields:
            with self.subTest(missing=field):
                data = load_config().to_dict()
                del data["speech"]["whisper"][field]

                with self.assertRaisesRegex(ConfigError, f"missing: {field}"):
                    parse_config(data)

        data = load_config().to_dict()
        data["speech"]["whisper"]["unknown"] = "value"
        with self.assertRaisesRegex(ConfigError, "unknown fields: unknown"):
            parse_config(data)

    def test_invalid_whisper_paths_are_rejected(self) -> None:
        for field in (
            "executable_path",
            "primary_model_path",
            "fallback_model_path",
        ):
            for value in (
                "",
                "relative/path",
                "bad\x00path",
                "/tmp/bidi\u202efile",
                "/tmp/zero\u200bwidth",
            ):
                with self.subTest(field=field, value=value):
                    data = load_config().to_dict()
                    data["speech"]["whisper"][field] = value

                    with self.assertRaisesRegex(
                        ConfigError, rf"speech\.whisper\.{field}"
                    ):
                        parse_config(data)

        data = load_config().to_dict()
        data["speech"]["whisper"]["fallback_model_path"] = data["speech"][
            "whisper"
        ]["primary_model_path"]
        with self.assertRaisesRegex(ConfigError, "must be different"):
            parse_config(data)

    def test_invalid_whisper_runtime_settings_are_rejected(self) -> None:
        for language in ("", " ", "en US", "en!", "fr", "auto", "nonsense"):
            with self.subTest(language=language):
                data = load_config().to_dict()
                data["speech"]["whisper"]["language"] = language

                with self.assertRaisesRegex(ConfigError, "speech.whisper.language"):
                    parse_config(data)

        data = load_config().to_dict()
        data["speech"]["whisper"]["language"] = "EN"
        self.assertEqual(parse_config(data).speech.whisper.language, "en")

        for field, values in {
            "threads": (True, 0, 65, 4.0, "4"),
            "timeout_seconds": (True, 0, 3601, 120.0, "120"),
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    data = load_config().to_dict()
                    data["speech"]["whisper"][field] = value

                    with self.assertRaisesRegex(
                        ConfigError, rf"speech\.whisper\.{field}"
                    ):
                        parse_config(data)

    def test_missing_unknown_and_invalid_quality_fields_are_rejected(self) -> None:
        fields = (
            "min_mean_token_probability",
            "min_text_characters",
            "max_text_characters",
        )
        for field in fields:
            with self.subTest(missing=field):
                data = load_config().to_dict()
                del data["speech"]["quality"][field]

                with self.assertRaisesRegex(ConfigError, f"missing: {field}"):
                    parse_config(data)

        data = load_config().to_dict()
        data["speech"]["quality"]["unknown"] = "value"
        with self.assertRaisesRegex(ConfigError, "unknown fields: unknown"):
            parse_config(data)

        invalid_values = {
            "min_mean_token_probability": (True, -0.1, 1.1, "0.2"),
            "min_text_characters": (True, 0, 101, 1.0, "1"),
            "max_text_characters": (True, 0, 1001, 1000.0, "1000"),
        }
        for field, values in invalid_values.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    data = load_config().to_dict()
                    data["speech"]["quality"][field] = value

                    with self.assertRaisesRegex(
                        ConfigError, rf"speech\.quality\.{field}"
                    ):
                        parse_config(data)

        data = load_config().to_dict()
        data["speech"]["quality"]["min_text_characters"] = 2
        data["speech"]["quality"]["max_text_characters"] = 1
        with self.assertRaisesRegex(ConfigError, "must be no larger"):
            parse_config(data)

    def test_missing_embedding_section_is_rejected(self) -> None:
        data = load_config().to_dict()
        del data["embedding"]

        with self.assertRaisesRegex(ConfigError, "missing: embedding"):
            parse_config(data)

    def test_missing_embedding_field_is_rejected(self) -> None:
        for field in ("model_directory", "intra_op_threads"):
            with self.subTest(field=field):
                data = load_config().to_dict()
                del data["embedding"][field]

                with self.assertRaisesRegex(ConfigError, f"missing: {field}"):
                    parse_config(data)

    def test_unknown_embedding_field_is_rejected(self) -> None:
        data = load_config().to_dict()
        data["embedding"]["unknown"] = "value"

        with self.assertRaisesRegex(ConfigError, "unknown fields: unknown"):
            parse_config(data)

    def test_invalid_embedding_model_directory_is_rejected(self) -> None:
        for model_directory in (
            "",
            "   ",
            "models/bge-small-en-v1.5",
            "bad\x00path",
        ):
            with self.subTest(model_directory=model_directory):
                data = load_config().to_dict()
                data["embedding"]["model_directory"] = model_directory

                with self.assertRaisesRegex(
                    ConfigError, "embedding.model_directory"
                ):
                    parse_config(data)

    def test_invalid_embedding_thread_count_is_rejected(self) -> None:
        for thread_count in (True, 0, 65, 1.5, "2"):
            with self.subTest(thread_count=thread_count):
                data = load_config().to_dict()
                data["embedding"]["intra_op_threads"] = thread_count

                with self.assertRaisesRegex(
                    ConfigError, "embedding.intra_op_threads"
                ):
                    parse_config(data)

    def test_invalid_memory_profile_is_rejected(self) -> None:
        data = load_config().to_dict()
        data["memory"]["profile_id"] = "bad profile"

        with self.assertRaisesRegex(ConfigError, "memory.profile_id"):
            parse_config(data)

    def test_relative_memory_database_path_is_rejected(self) -> None:
        data = load_config().to_dict()
        data["memory"]["database_path"] = "data/memory.sqlite3"

        with self.assertRaisesRegex(ConfigError, "absolute filesystem path"):
            parse_config(data)


if __name__ == "__main__":
    unittest.main()
