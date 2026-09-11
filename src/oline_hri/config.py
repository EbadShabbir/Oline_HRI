"""Load and validate application configuration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import resources
from ipaddress import ip_address
import json
from math import ceil
from pathlib import Path
import re
from typing import Any, Mapping, Optional, Union
import unicodedata
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default.json"
ROUTER_MODEL_ID = "qwen3:0.6b"
GENERAL_LARGE_MODEL_ID = "qwen3:1.7b"
LARGE_MODEL_ID = "qwen3:1.7b"
_UNSAFE_CONFIG_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Zl", "Zp"})
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
    general_large_model: str
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
    retention_days: int


@dataclass(frozen=True)
class EmbeddingConfig:
    model_directory: str
    intra_op_threads: int


@dataclass(frozen=True)
class SileroConfig:
    model_path: str
    threshold: float
    silence_threshold: float
    pre_roll_seconds: float
    start_timeout_seconds: float
    start_trigger_seconds: float
    end_silence_seconds: float
    min_utterance_seconds: float
    max_utterance_seconds: float


@dataclass(frozen=True)
class WhisperConfig:
    executable_path: str
    primary_model_path: str
    fallback_model_path: str
    language: str
    threads: int
    timeout_seconds: int


@dataclass(frozen=True)
class TranscriptionQualityConfig:
    min_mean_token_probability: float
    min_text_characters: int
    max_text_characters: int


@dataclass(frozen=True)
class SpeechConfig:
    capture_executable_path: str
    capture_device: str
    sample_rate_hz: int
    chunk_samples: int
    silero: SileroConfig
    whisper: WhisperConfig
    quality: TranscriptionQualityConfig


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
    speech: SpeechConfig
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
    try:
        return float(value)
    except (OverflowError, ValueError):
        raise ConfigError(f"{section}.{key} must be a finite number") from None


def _boolean(data: Mapping[str, Any], key: str, section: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise ConfigError(f"{section}.{key} must be true or false")
    return value


def _absolute_path(data: Mapping[str, Any], key: str, section: str) -> str:
    value = _string(data, key, section)
    try:
        expanded = Path(value).expanduser()
    except RuntimeError as exc:
        raise ConfigError(f"{section}.{key} cannot be expanded") from exc
    if (
        any(
            unicodedata.category(character) in _UNSAFE_CONFIG_CATEGORIES
            for character in value
        )
        or not expanded.is_absolute()
    ):
        raise ConfigError(
            f"{section}.{key} must resolve to an absolute filesystem path"
        )
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
        "speech",
        "logging",
    }
    schema_version = _integer(data, "schema_version", "configuration")
    if schema_version != 7:
        raise ConfigError(f"unsupported schema_version: {schema_version}")
    _check_keys(data, section="configuration", required=root_fields)

    profile_data = _section(data, "profile")
    _check_keys(profile_data, section="profile", required={"active"})
    profile = ProfileConfig(active=_string(profile_data, "active", "profile"))

    ollama_data = _section(data, "ollama")
    ollama_fields = {
        "base_url",
        "small_model",
        "general_large_model",
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
    general_large_model = _string(
        ollama_data, "general_large_model", "ollama"
    )
    if general_large_model != GENERAL_LARGE_MODEL_ID:
        raise ConfigError(
            f'ollama.general_large_model must be exactly '
            f'"{GENERAL_LARGE_MODEL_ID}" for large requests without memory'
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
        general_large_model=general_large_model,
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
        required={"database_path", "profile_id", "retention_days"},
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
    retention_days = _integer(memory_data, "retention_days", "memory")
    if not 1 <= retention_days <= 3650:
        raise ConfigError("memory.retention_days must be between 1 and 3650")
    memory = MemoryConfig(
        database_path=database_path,
        profile_id=memory_profile_id,
        retention_days=retention_days,
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

    speech_data = _section(data, "speech")
    _check_keys(
        speech_data,
        section="speech",
        required={
            "capture_executable_path",
            "capture_device",
            "sample_rate_hz",
            "chunk_samples",
            "silero",
            "whisper",
            "quality",
        },
    )
    capture_executable_path = _absolute_path(
        speech_data, "capture_executable_path", "speech"
    )
    capture_device = _string(speech_data, "capture_device", "speech")
    if len(capture_device) > 255 or any(
        unicodedata.category(character) in _UNSAFE_CONFIG_CATEGORIES
        for character in capture_device
    ):
        raise ConfigError(
            "speech.capture_device must be at most 255 characters with no "
            "control characters"
        )
    sample_rate_hz = _integer(speech_data, "sample_rate_hz", "speech")
    if sample_rate_hz != 16000:
        raise ConfigError("speech.sample_rate_hz must be exactly 16000")
    chunk_samples = _integer(speech_data, "chunk_samples", "speech")
    if chunk_samples != 512:
        raise ConfigError("speech.chunk_samples must be exactly 512")

    silero_data = _section(speech_data, "silero")
    _check_keys(
        silero_data,
        section="speech.silero",
        required={
            "model_path",
            "threshold",
            "silence_threshold",
            "pre_roll_seconds",
            "start_timeout_seconds",
            "start_trigger_seconds",
            "end_silence_seconds",
            "min_utterance_seconds",
            "max_utterance_seconds",
        },
    )
    silero_model_path = _absolute_path(
        silero_data, "model_path", "speech.silero"
    )
    vad_threshold = _number(silero_data, "threshold", "speech.silero")
    if not 0.0 < vad_threshold < 1.0:
        raise ConfigError("speech.silero.threshold must be between 0 and 1")
    silence_threshold = _number(
        silero_data, "silence_threshold", "speech.silero"
    )
    if not 0.0 <= silence_threshold < vad_threshold:
        raise ConfigError(
            "speech.silero.silence_threshold must be at least 0 and smaller "
            "than threshold"
        )
    pre_roll_seconds = _number(
        silero_data, "pre_roll_seconds", "speech.silero"
    )
    if not 0.0 <= pre_roll_seconds <= 5.0:
        raise ConfigError(
            "speech.silero.pre_roll_seconds must be between 0 and 5"
        )
    start_timeout_seconds = _number(
        silero_data, "start_timeout_seconds", "speech.silero"
    )
    if not 1.0 <= start_timeout_seconds <= 600.0:
        raise ConfigError(
            "speech.silero.start_timeout_seconds must be between 1 and 600"
        )
    start_trigger_seconds = _number(
        silero_data, "start_trigger_seconds", "speech.silero"
    )
    if not 0.01 <= start_trigger_seconds <= 2.0:
        raise ConfigError(
            "speech.silero.start_trigger_seconds must be between 0.01 and 2"
        )
    end_silence_seconds = _number(
        silero_data, "end_silence_seconds", "speech.silero"
    )
    if not 0.1 <= end_silence_seconds <= 5.0:
        raise ConfigError(
            "speech.silero.end_silence_seconds must be between 0.1 and 5"
        )
    min_utterance_seconds = _number(
        silero_data, "min_utterance_seconds", "speech.silero"
    )
    if not 0.1 <= min_utterance_seconds <= 10.0:
        raise ConfigError(
            "speech.silero.min_utterance_seconds must be between 0.1 and 10"
        )
    max_utterance_seconds = _number(
        silero_data, "max_utterance_seconds", "speech.silero"
    )
    if not 1.0 <= max_utterance_seconds <= 300.0:
        raise ConfigError(
            "speech.silero.max_utterance_seconds must be between 1 and 300"
        )
    if start_trigger_seconds > min_utterance_seconds:
        raise ConfigError(
            "speech.silero.start_trigger_seconds must be no larger than "
            "min_utterance_seconds"
        )
    if start_trigger_seconds > start_timeout_seconds:
        raise ConfigError(
            "speech.silero.start_trigger_seconds must be no larger than "
            "start_timeout_seconds"
        )
    if min_utterance_seconds > max_utterance_seconds:
        raise ConfigError(
            "speech.silero.min_utterance_seconds must be no larger than "
            "max_utterance_seconds"
        )
    if end_silence_seconds > max_utterance_seconds:
        raise ConfigError(
            "speech.silero.end_silence_seconds must be no larger than "
            "max_utterance_seconds"
        )
    chunk_seconds = chunk_samples / sample_rate_hz
    start_trigger_chunks = ceil(start_trigger_seconds / chunk_seconds)
    # The endpoint uses a strict wall-clock deadline: a frame completing exactly
    # at the timeout is too late to establish speech onset.
    start_timeout_chunks = ceil(start_timeout_seconds / chunk_seconds) - 1
    min_utterance_chunks = ceil(min_utterance_seconds / chunk_seconds)
    max_utterance_chunks = int(max_utterance_seconds / chunk_seconds)
    if start_trigger_chunks > start_timeout_chunks:
        raise ConfigError(
            "speech.silero.start trigger cannot complete within the configured "
            "start timeout at the 512-sample frame boundary"
        )
    if min_utterance_chunks > max_utterance_chunks:
        raise ConfigError(
            "speech.silero.minimum utterance cannot complete within the configured "
            "maximum at the 512-sample frame boundary"
        )
    pre_roll_chunks = ceil(pre_roll_seconds / chunk_seconds)
    if pre_roll_chunks + min_utterance_chunks > max_utterance_chunks:
        raise ConfigError(
            "speech.silero.pre-roll plus minimum utterance cannot fit within "
            "the configured maximum at the 512-sample frame boundary"
        )
    silero = SileroConfig(
        model_path=silero_model_path,
        threshold=vad_threshold,
        silence_threshold=silence_threshold,
        pre_roll_seconds=pre_roll_seconds,
        start_timeout_seconds=start_timeout_seconds,
        start_trigger_seconds=start_trigger_seconds,
        end_silence_seconds=end_silence_seconds,
        min_utterance_seconds=min_utterance_seconds,
        max_utterance_seconds=max_utterance_seconds,
    )

    whisper_data = _section(speech_data, "whisper")
    _check_keys(
        whisper_data,
        section="speech.whisper",
        required={
            "executable_path",
            "primary_model_path",
            "fallback_model_path",
            "language",
            "threads",
            "timeout_seconds",
        },
    )
    whisper_executable_path = _absolute_path(
        whisper_data, "executable_path", "speech.whisper"
    )
    whisper_primary_model_path = _absolute_path(
        whisper_data, "primary_model_path", "speech.whisper"
    )
    whisper_fallback_model_path = _absolute_path(
        whisper_data, "fallback_model_path", "speech.whisper"
    )
    if whisper_primary_model_path == whisper_fallback_model_path:
        raise ConfigError(
            "speech.whisper.primary_model_path and fallback_model_path "
            "must be different"
        )
    whisper_language = _string(whisper_data, "language", "speech.whisper")
    if whisper_language.casefold() != "en":
        raise ConfigError(
            "speech.whisper.language must be en for the configured English models"
        )
    whisper_threads = _integer(whisper_data, "threads", "speech.whisper")
    if not 1 <= whisper_threads <= 64:
        raise ConfigError("speech.whisper.threads must be between 1 and 64")
    whisper_timeout_seconds = _integer(
        whisper_data, "timeout_seconds", "speech.whisper"
    )
    if not 1 <= whisper_timeout_seconds <= 3600:
        raise ConfigError(
            "speech.whisper.timeout_seconds must be between 1 and 3600"
        )
    whisper = WhisperConfig(
        executable_path=whisper_executable_path,
        primary_model_path=whisper_primary_model_path,
        fallback_model_path=whisper_fallback_model_path,
        language=whisper_language.casefold(),
        threads=whisper_threads,
        timeout_seconds=whisper_timeout_seconds,
    )

    quality_data = _section(speech_data, "quality")
    _check_keys(
        quality_data,
        section="speech.quality",
        required={
            "min_mean_token_probability",
            "min_text_characters",
            "max_text_characters",
        },
    )
    min_mean_token_probability = _number(
        quality_data, "min_mean_token_probability", "speech.quality"
    )
    if not 0.0 <= min_mean_token_probability <= 1.0:
        raise ConfigError(
            "speech.quality.min_mean_token_probability must be between 0 and 1"
        )
    min_text_characters = _integer(
        quality_data, "min_text_characters", "speech.quality"
    )
    if not 1 <= min_text_characters <= 100:
        raise ConfigError(
            "speech.quality.min_text_characters must be between 1 and 100"
        )
    max_text_characters = _integer(
        quality_data, "max_text_characters", "speech.quality"
    )
    if not 1 <= max_text_characters <= 1000:
        raise ConfigError(
            "speech.quality.max_text_characters must be between 1 and 1000"
        )
    if min_text_characters > max_text_characters:
        raise ConfigError(
            "speech.quality.min_text_characters must be no larger than "
            "max_text_characters"
        )
    quality = TranscriptionQualityConfig(
        min_mean_token_probability=min_mean_token_probability,
        min_text_characters=min_text_characters,
        max_text_characters=max_text_characters,
    )
    speech = SpeechConfig(
        capture_executable_path=capture_executable_path,
        capture_device=capture_device,
        sample_rate_hz=sample_rate_hz,
        chunk_samples=chunk_samples,
        silero=silero,
        whisper=whisper,
        quality=quality,
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
        speech=speech,
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
