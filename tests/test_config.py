import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from oline_hri.config import (
    DEFAULT_CONFIG_PATH,
    LARGE_MODEL_ID,
    ROUTER_MODEL_ID,
    ConfigError,
    load_config,
    parse_config,
)


class ConfigTests(unittest.TestCase):
    def test_default_config_loads(self) -> None:
        config = load_config()

        self.assertEqual(config.schema_version, 4)
        self.assertEqual(config.ollama.small_model, ROUTER_MODEL_ID)
        self.assertEqual(config.ollama.large_model, LARGE_MODEL_ID)
        self.assertEqual(config.ollama.request_timeout_seconds, 60)
        self.assertEqual(config.ollama.large_request_timeout_seconds, 300)
        self.assertEqual(config.ollama.unload_timeout_seconds, 30)
        self.assertEqual(config.generation.context_length, 2048)
        self.assertFalse(config.generation.thinking)
        self.assertEqual(config.memory.profile_id, "default_user")
        self.assertTrue(config.memory.database_path.startswith("~/"))
        self.assertEqual(
            config.embedding.model_directory,
            "~/.local/share/oline-hri/models/bge-small-en-v1.5/"
            "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
        )
        self.assertEqual(config.embedding.intra_op_threads, 2)

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

    def test_large_model_is_fixed_to_qwen3_4b(self) -> None:
        for model in ("qwen3:0.6b", "qwen3:4b-instruct", "QWEN3:4B"):
            with self.subTest(model=model):
                data = load_config().to_dict()
                data["ollama"]["large_model"] = model

                with self.assertRaisesRegex(ConfigError, "four-route generation"):
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
