"""Load and validate application configuration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import resources
from ipaddress import ip_address
import json
from pathlib import Path
import re
from typing import Any, Mapping, Optional, Union
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default.json"
ROUTER_MODEL_ID = "qwen3:0.6b"
LARGE_MODEL_ID = "qwen3:4b"
PathLike = Union[str, Path]


class ConfigError(ValueError):
    """Raised when a configuration file is missing or invalid."""


@dataclass(frozen=True)
class ProfileConfig:
    active: str


@dataclass(frozen=True)
class OllamaConfig:
    base_url: str
    small_model: str
    large_model: str
    request_timeout_seconds: int
    large_request_timeout_seconds: int
    unload_timeout_seconds: int


@dataclass(frozen=True)
class GenerationConfig:
    context_length: int
    max_output_tokens: int
    temperature: float
    thinking: bool


@dataclass(frozen=True)
class ConversationConfig:
    system_prompt: str


@dataclass(frozen=True)
class MemoryConfig:
    database_path: str
    profile_id: str


@dataclass(frozen=True)
class EmbeddingConfig:
    model_directory: str
    intra_op_threads: int


@dataclass(frozen=True)
class LoggingConfig:
    level: str


@dataclass(frozen=True)
class AppConfig:
    schema_version: int
    profile: ProfileConfig
    ollama: OllamaConfig
    generation: GenerationConfig
    conversation: ConversationConfig
    memory: MemoryConfig
    embedding: EmbeddingConfig
    logging: LoggingConfig

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return asdict(self)


def _section(data: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = data.get(name)
    if not isinstance(value, Mapping):
        raise ConfigError(f"{name} must be an object")
    return value


def _check_keys(
    data: Mapping[str, Any], *, section: str, required: set[str]
) -> None:
    keys = set(data)
    missing = sorted(required - keys)
    unknown = sorted(keys - required)
    if missing:
        raise ConfigError(f"{section} is missing: {', '.join(missing)}")
    if unknown:
        raise ConfigError(f"{section} contains unknown fields: {', '.join(unknown)}")


def _string(data: Mapping[str, Any], key: str, section: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{section}.{key} must be a non-empty string")
    return value.strip()


def _integer(data: Mapping[str, Any], key: str, section: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{section}.{key} must be an integer")
    return value


def _number(data: Mapping[str, Any], key: str, section: str) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{section}.{key} must be a number")
    return float(value)


def _boolean(data: Mapping[str, Any], key: str, section: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise ConfigError(f"{section}.{key} must be true or false")
    return value


def parse_config(data: Mapping[str, Any]) -> AppConfig:
    """Validate a decoded configuration mapping."""

    if not isinstance(data, Mapping):
        raise ConfigError("configuration root must be an object")

    root_fields = {
        "schema_version",
        "profile",
        "ollama",
        "generation",
        "conversation",
        "memory",
        "embedding",
        "logging",
    }
    schema_version = _integer(data, "schema_version", "configuration")
    if schema_version != 4:
        raise ConfigError(f"unsupported schema_version: {schema_version}")
    _check_keys(data, section="configuration", required=root_fields)

    profile_data = _section(data, "profile")
    _check_keys(profile_data, section="profile", required={"active"})
    profile = ProfileConfig(active=_string(profile_data, "active", "profile"))

    ollama_data = _section(data, "ollama")
    ollama_fields = {
        "base_url",
        "small_model",
        "large_model",
        "request_timeout_seconds",
        "large_request_timeout_seconds",
        "unload_timeout_seconds",
    }
    _check_keys(ollama_data, section="ollama", required=ollama_fields)
    configured_base_url = _string(ollama_data, "base_url", "ollama")
    try:
        parsed_url = urlparse(configured_base_url)
        hostname = parsed_url.hostname
        # Accessing ``port`` makes urllib reject malformed and out-of-range
        # authorities now instead of much later when a request is attempted.
        parsed_url.port
    except ValueError as exc:
        raise ConfigError(
            "ollama.base_url must be an HTTP or HTTPS URL"
        ) from exc
    if parsed_url.scheme not in {"http", "https"} or not hostname:
        raise ConfigError("ollama.base_url must be an HTTP or HTTPS URL")
    if (
        not _is_loopback_host(hostname)
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.params
        or parsed_url.query
        or parsed_url.fragment
        or "?" in configured_base_url
        or "#" in configured_base_url
        or parsed_url.path not in {"", "/"}
    ):
        raise ConfigError(
            "ollama.base_url must identify a local loopback Ollama server"
        )
    base_url = configured_base_url.rstrip("/")
    timeout = _integer(ollama_data, "request_timeout_seconds", "ollama")
    if not 1 <= timeout <= 3600:
        raise ConfigError("ollama.request_timeout_seconds must be between 1 and 3600")
    large_timeout = _integer(
        ollama_data, "large_request_timeout_seconds", "ollama"
    )
    if not 1 <= large_timeout <= 3600:
        raise ConfigError(
            "ollama.large_request_timeout_seconds must be between 1 and 3600"
        )
    if large_timeout < timeout:
        raise ConfigError(
            "ollama.large_request_timeout_seconds must be no smaller than "
            "ollama.request_timeout_seconds"
        )
    unload_timeout = _integer(
        ollama_data, "unload_timeout_seconds", "ollama"
    )
    if not 1 <= unload_timeout <= 3600:
        raise ConfigError(
            "ollama.unload_timeout_seconds must be between 1 and 3600"
        )
    small_model = _string(ollama_data, "small_model", "ollama")
    if small_model != ROUTER_MODEL_ID:
        raise ConfigError(
            f'ollama.small_model must be exactly "{ROUTER_MODEL_ID}" '
            "for structured routing"
        )
    large_model = _string(ollama_data, "large_model", "ollama")
    if large_model != LARGE_MODEL_ID:
        raise ConfigError(
            f'ollama.large_model must be exactly "{LARGE_MODEL_ID}" '
            "for four-route generation"
        )
    ollama = OllamaConfig(
        base_url=base_url,
        small_model=small_model,
        large_model=large_model,
        request_timeout_seconds=timeout,
        large_request_timeout_seconds=large_timeout,
        unload_timeout_seconds=unload_timeout,
    )

    generation_data = _section(data, "generation")
    generation_fields = {
        "context_length",
        "max_output_tokens",
        "temperature",
        "thinking",
    }
    _check_keys(generation_data, section="generation", required=generation_fields)
    context_length = _integer(generation_data, "context_length", "generation")
    max_output_tokens = _integer(
        generation_data, "max_output_tokens", "generation"
    )
    temperature = _number(generation_data, "temperature", "generation")
    if not 128 <= context_length <= 131072:
        raise ConfigError("generation.context_length must be between 128 and 131072")
    if not 1 <= max_output_tokens <= context_length:
        raise ConfigError(
            "generation.max_output_tokens must be positive and no larger than "
            "context_length"
        )
    if not 0.0 <= temperature <= 2.0:
        raise ConfigError("generation.temperature must be between 0 and 2")
    generation = GenerationConfig(
        context_length=context_length,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        thinking=_boolean(generation_data, "thinking", "generation"),
    )

    conversation_data = _section(data, "conversation")
    _check_keys(
        conversation_data, section="conversation", required={"system_prompt"}
    )
    conversation = ConversationConfig(
        system_prompt=_string(conversation_data, "system_prompt", "conversation")
    )

    memory_data = _section(data, "memory")
    _check_keys(
        memory_data,
        section="memory",
        required={"database_path", "profile_id"},
    )
    database_path = _string(memory_data, "database_path", "memory")
    try:
        expanded_path = Path(database_path).expanduser()
    except RuntimeError as exc:
        raise ConfigError("memory.database_path cannot be expanded") from exc
    if "\x00" in database_path or not expanded_path.is_absolute():
        raise ConfigError(
            "memory.database_path must resolve to an absolute filesystem path"
        )
    memory_profile_id = _string(memory_data, "profile_id", "memory")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", memory_profile_id) is None:
        raise ConfigError(
            "memory.profile_id must be 1-64 letters, numbers, dots, "
            "underscores, or hyphens"
        )
    memory = MemoryConfig(
        database_path=database_path,
        profile_id=memory_profile_id,
    )

    embedding_data = _section(data, "embedding")
    _check_keys(
        embedding_data,
        section="embedding",
        required={"model_directory", "intra_op_threads"},
    )
    model_directory = _string(
        embedding_data, "model_directory", "embedding"
    )
    try:
        expanded_model_directory = Path(model_directory).expanduser()
    except RuntimeError as exc:
        raise ConfigError("embedding.model_directory cannot be expanded") from exc
    if "\x00" in model_directory or not expanded_model_directory.is_absolute():
        raise ConfigError(
            "embedding.model_directory must resolve to an absolute filesystem path"
        )
    intra_op_threads = _integer(
        embedding_data, "intra_op_threads", "embedding"
    )
    if not 1 <= intra_op_threads <= 64:
        raise ConfigError("embedding.intra_op_threads must be between 1 and 64")
    embedding = EmbeddingConfig(
        model_directory=model_directory,
        intra_op_threads=intra_op_threads,
    )

    logging_data = _section(data, "logging")
    _check_keys(logging_data, section="logging", required={"level"})
    log_level = _string(logging_data, "level", "logging").upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError("logging.level is not a supported Python logging level")

    return AppConfig(
        schema_version=schema_version,
        profile=profile,
        ollama=ollama,
        generation=generation,
        conversation=conversation,
        memory=memory,
        embedding=embedding,
        logging=LoggingConfig(level=log_level),
    )


def load_config(path: Optional[PathLike] = None) -> AppConfig:
    """Load configuration from *path* or the packaged project default."""

    if path is not None:
        config_source = str(Path(path))
        try:
            raw = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(
                f"cannot read configuration {config_source}: {exc}"
            ) from exc
    elif DEFAULT_CONFIG_PATH.is_file():
        config_source = str(DEFAULT_CONFIG_PATH)
        try:
            raw = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(
                f"cannot read configuration {config_source}: {exc}"
            ) from exc
    else:
        config_source = "packaged default_config.json"
        try:
            raw = (
                resources.files("oline_hri")
                .joinpath("default_config.json")
                .read_text(encoding="utf-8")
            )
        except (FileNotFoundError, OSError) as exc:
            raise ConfigError(f"cannot read {config_source}: {exc}") from exc

    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"invalid JSON in {config_source} at line {exc.lineno}, column {exc.colno}"
        ) from exc

    if not isinstance(decoded, Mapping):
        raise ConfigError("configuration root must be an object")
    return parse_config(decoded)


def _is_loopback_host(hostname: str) -> bool:
    if hostname.casefold() == "localhost":
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False
