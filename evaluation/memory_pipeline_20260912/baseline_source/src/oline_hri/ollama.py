"""Small, dependency-free client for the local Ollama chat API."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import json
from math import isfinite
import re
import socket
from threading import Lock
from typing import Any, Callable, Mapping, Optional, Sequence
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from .config import GenerationConfig, OllamaConfig
from .response import ResponseValidationError, build_robot_response_schema


class OllamaError(RuntimeError):
    """Raised when Ollama cannot return a usable chat response."""


class OllamaTimeoutError(OllamaError):
    """Raised when a local Ollama socket operation exceeds its time budget."""


SMALL_MODEL_KEEP_ALIVE = -1
LARGE_MODEL_KEEP_ALIVE = 0
UNLOAD_KEEP_ALIVE = 0
MAX_OLLAMA_RESPONSE_BYTES = 64 * 1024
_MEMORY_ID_IN_REQUEST_PATTERN = re.compile(r"mem_[0-9a-f]{32}")
_RESERVED_MEMORY_ALIAS_PATTERN = re.compile(r"memory_ref_[0-9]+")
# Targeted UTS-39-style skeleton characters for the letters that can occur in
# ``memory_ref``. NFKC handles full-width/mathematical compatibility forms;
# these mappings close the common Cyrillic/Greek cross-script lookalikes while
# leaving ordinary non-ASCII speech untouched.
_BOUNDARY_CONFUSABLE_TRANSLATION = str.maketrans(
    {
        "ε": "e",  # Greek epsilon
        "μ": "m",  # Greek mu
        "ο": "o",  # Greek omicron
        "υ": "y",  # Greek upsilon
        "е": "e",  # Cyrillic ie
        "м": "m",  # Cyrillic em
        "о": "o",  # Cyrillic o
        "у": "y",  # Cyrillic u
        "і": "i",  # Cyrillic byelorussian-ukrainian i
        "ӏ": "1",  # Cyrillic palochka (digit-one lookalike)
    }
)
_MEMORY_CITATION_ANNOTATION_PATTERN = re.compile(
    r"(?<=\S) +\(per (?P<alias>memory_ref_[1-9][0-9]*)\)"
    r"(?=[.!?,;:]|$)"
)


@dataclass(frozen=True)
class _MemoryPseudonyms:
    """One request-local, deterministic memory-ID translation."""

    actual_to_alias: Mapping[str, str]
    alias_to_actual: Mapping[str, str]


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        if self.role not in {"system", "user", "assistant"}:
            raise ValueError(f"unsupported chat role: {self.role}")
        if not self.content.strip():
            raise ValueError("chat message content cannot be empty")
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class ChatResult:
    model: str
    content: str
    done_reason: str
    total_duration_ns: int
    load_duration_ns: int
    prompt_eval_count: int
    eval_count: int
    eval_duration_ns: int
    prompt_eval_duration_ns: int = 0
    citation_annotations_removed: int = 0

    @property
    def generation_tokens_per_second(self) -> Optional[float]:
        if self.eval_count <= 0 or self.eval_duration_ns <= 0:
            return None
        return self.eval_count * 1_000_000_000 / self.eval_duration_ns


class OllamaClient:
    """Call one local Ollama server using application configuration.

    By default, small-model calls retain their model and large-model calls
    expire it. ``retain_large_model=True`` retains any configured model until
    a peer is selected or cleanup runs; peer eviction remains serialized.
    """

    def __init__(
        self,
        ollama: OllamaConfig,
        generation: GenerationConfig,
        *,
        opener: Optional[Callable[..., Any]] = None,
        retain_large_model: bool = False,
    ) -> None:
        if type(retain_large_model) is not bool:
            raise ValueError("retain_large_model must be a boolean")
        self._ollama = ollama
        self._generation = generation
        self._retain_large_model = retain_large_model
        self._configured_models = tuple(
            dict.fromkeys(
                (
                    ollama.small_model,
                    ollama.general_large_model,
                    ollama.large_model,
                )
            )
        )
        self._opener = (
            opener
            if opener is not None
            else build_opener(ProxyHandler({})).open
        )
        # The CLI shares one client between its router and selected generator.
        # Holding this lock across peer eviction and the complete chat request
        # makes those model transitions one indivisible local transaction.
        self._schedule_lock = Lock()
        self._residency_known = False
        self._resident_model: Optional[str] = None

    @property
    def resident_model(self) -> Optional[str]:
        """Return the client-tracked residency hint without querying the server.

        Waits for this client's current scheduling transaction to finish. None
        means either unknown or known empty. This hint is not an /api/ps
        guarantee: another client or the server can change actual residency.
        """
        with self._schedule_lock:
            return self._resident_model if self._residency_known else None

    def chat(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        *,
        response_format: Optional[Mapping[str, Any]] = None,
        temperature: Optional[float] = None,
        seed: Optional[int] = None,
    ) -> ChatResult:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model cannot be empty")
        if model not in self._configured_models:
            raise ValueError("model must be one of the configured models")
        if not messages:
            raise ValueError("at least one chat message is required")

        request_temperature = (
            self._generation.temperature
            if temperature is None
            else _temperature(temperature)
        )
        request_seed = None if seed is None else _seed(seed)

        body: dict[str, Any] = {
            "model": model,
            "messages": [message.to_dict() for message in messages],
            "stream": False,
            "think": self._generation.thinking,
            "keep_alive": (
                SMALL_MODEL_KEEP_ALIVE
                if self._retain_large_model or model == self._ollama.small_model
                else LARGE_MODEL_KEEP_ALIVE
            ),
            "options": {
                "num_ctx": self._generation.context_length,
                "num_predict": self._generation.max_output_tokens,
                "temperature": request_temperature,
            },
        }
        if request_seed is not None:
            body["options"]["seed"] = request_seed
        if response_format is not None:
            body["format"] = dict(response_format)

        pseudonyms = _robot_memory_pseudonyms(response_format)
        if pseudonyms is not None:
            # Check the pristine body before introducing our own reserved
            # aliases. This prevents user text or schema data from being
            # confused with request-local references during restoration.
            original_body = _serialize_json_body(body)
            if _contains_reserved_memory_alias(original_body.decode("utf-8")):
                raise OllamaError(
                    "Ollama chat request contains a reserved memory reference"
                )
            body = _replace_memory_ids(
                deepcopy(body), pseudonyms.actual_to_alias
            )

        # Serialize and inspect before entering the model-residency transaction.
        # Thus a missed, unknown, case-variant, or compatibility-form memory ID
        # cannot cause even the peer-unload request to run.
        serialized_body = _serialize_json_body(body)
        if _contains_memory_id(serialized_body.decode("utf-8")):
            raise OllamaError(
                "Ollama chat request contains an unpseudonymized memory ID"
            )

        with self._schedule_lock:
            try:
                self._prepare_model(model)
                request_timeout = (
                    self._ollama.request_timeout_seconds
                    if model == self._ollama.small_model
                    else self._ollama.large_request_timeout_seconds
                )
                payload = self._post_json(
                    "/api/chat",
                    body,
                    timeout_seconds=request_timeout,
                    serialized_body=serialized_body,
                )
                result = _chat_result(payload, requested_model=model)
                if pseudonyms is not None:
                    restored_content, annotations_removed = _restore_memory_ids(
                        result.content, pseudonyms.alias_to_actual
                    )
                    result = replace(
                        result,
                        content=restored_content,
                        citation_annotations_removed=annotations_removed,
                    )
            except BaseException:
                # A failed or interrupted request may have changed Ollama's
                # actual residency even when no trustworthy response arrived.
                self._residency_known = False
                self._resident_model = None
                raise

            self._residency_known = True
            self._resident_model = (
                model
                if self._retain_large_model or model == self._ollama.small_model
                else None
            )
            return result

    def unload_all(self) -> None:
        """Release configured Qwen models before another GPU-heavy stage."""

        with self._schedule_lock:
            if self._residency_known:
                models = (
                    ()
                    if self._resident_model is None
                    else (self._resident_model,)
                )
            else:
                # The server may retain any configured model from work done
                # before this client was created. Establish a known empty state.
                models = self._configured_models
            try:
                for model in models:
                    self._unload_model(model)
            except BaseException:
                self._residency_known = False
                self._resident_model = None
                raise
            self._residency_known = True
            self._resident_model = None

    def _prepare_model(self, requested_model: str) -> None:
        if self._residency_known:
            if self._resident_model in {None, requested_model}:
                return
            model_to_unload = self._resident_model
        else:
            peers = tuple(
                model
                for model in self._configured_models
                if model != requested_model
            )
            for peer in peers:
                self._unload_model(peer)
            self._residency_known = True
            self._resident_model = None
            return

        self._unload_model(model_to_unload)
        self._residency_known = True
        self._resident_model = None

    def _unload_model(self, model: str) -> None:
        payload = self._post_json(
            "/api/generate",
            {
                "model": model,
                "prompt": "",
                "stream": False,
                "keep_alive": UNLOAD_KEEP_ALIVE,
            },
            timeout_seconds=self._ollama.unload_timeout_seconds,
        )
        if (
            payload.get("model") != model
            or payload.get("response") != ""
            or payload.get("done") is not True
            or payload.get("done_reason") != "unload"
        ):
            raise OllamaError("Ollama returned an invalid model-unload response")

    def _post_json(
        self,
        endpoint: str,
        body: Mapping[str, Any],
        *,
        timeout_seconds: int,
        serialized_body: Optional[bytes] = None,
    ) -> Mapping[str, Any]:
        request = Request(
            f"{self._ollama.base_url}{endpoint}",
            data=(
                _serialize_json_body(body)
                if serialized_body is None
                else serialized_body
            ),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with self._opener(request, timeout=timeout_seconds) as response:
                raw_bytes = response.read(MAX_OLLAMA_RESPONSE_BYTES + 1)
                if len(raw_bytes) > MAX_OLLAMA_RESPONSE_BYTES:
                    raise OllamaError("Ollama response exceeded size limit")
                raw = raw_bytes.decode("utf-8")
        except HTTPError as exc:
            raise OllamaError(f"Ollama HTTP {exc.code}") from None
        except (TimeoutError, socket.timeout):
            raise OllamaTimeoutError("Ollama request timed out") from None
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise OllamaTimeoutError("Ollama request timed out") from None
            raise OllamaError("cannot reach Ollama") from None
        except UnicodeDecodeError as exc:
            raise OllamaError(
                "Ollama returned a response that is not UTF-8"
            ) from None
        except OSError:
            raise OllamaError("cannot reach Ollama") from None

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            raise OllamaError("Ollama returned invalid JSON") from None
        if not isinstance(payload, Mapping):
            raise OllamaError("Ollama response must be a JSON object")
        if payload.get("error"):
            raise OllamaError("Ollama returned an error response")
        return payload


def _robot_memory_pseudonyms(
    response_format: Optional[Mapping[str, Any]],
) -> Optional[_MemoryPseudonyms]:
    """Alias only recognized robot schemas, including bounded constraints."""

    if not isinstance(response_format, Mapping):
        return None
    try:
        properties = response_format["properties"]
        if not isinstance(properties, Mapping):
            return None
        memory_used = properties["memory_used"]
        if not isinstance(memory_used, Mapping):
            return None
        items = memory_used["items"]
        if not isinstance(items, Mapping):
            return None
        enum = items["enum"]
        if not isinstance(enum, list) or not enum:
            return None
        allowed_ids = tuple(enum)
        minimum = memory_used.get("minItems")
        if "minItems" in memory_used and (
            type(minimum) is not int or minimum not in (1, len(allowed_ids))
        ):
            return None
        require_citation = minimum is not None
        expected = build_robot_response_schema(
            allowed_ids,
            require_citation=require_citation,
        )
        if require_citation:
            expected["properties"]["memory_used"]["minItems"] = minimum
        speech = properties["speech"]
        if "enum" in speech:
            verified = speech["enum"]
            if (
                not 1 <= len(allowed_ids) <= 3 or minimum != len(allowed_ids)
                or not isinstance(verified, list) or len(verified) != 1
                or not isinstance(verified[0], str)
                or not 1 <= len(verified[0]) <= 1200
            ):
                return None
            expected["properties"]["speech"]["enum"] = verified
    except (KeyError, ResponseValidationError, TypeError):
        return None
    if not _same_json_value(response_format, expected):
        return None

    actual_to_alias = {
        memory_id: f"memory_ref_{ordinal}"
        for ordinal, memory_id in enumerate(allowed_ids, start=1)
    }
    return _MemoryPseudonyms(
        actual_to_alias=actual_to_alias,
        alias_to_actual={
            alias: actual for actual, alias in actual_to_alias.items()
        },
    )


def _same_json_value(actual: Any, expected: Any) -> bool:
    """Compare JSON-like values without Python's bool/number coercion."""

    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping) or len(actual) != len(expected):
            return False
        return all(
            key in actual and _same_json_value(actual[key], expected_value)
            for key, expected_value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(
                _same_json_value(actual_item, expected_item)
                for actual_item, expected_item in zip(actual, expected)
            )
        )
    return type(actual) is type(expected) and actual == expected


def _replace_memory_ids(value: Any, replacements: Mapping[str, str]) -> Any:
    """Recursively translate every known ID in a detached JSON-like value."""

    if isinstance(value, str):
        for memory_id, alias in replacements.items():
            value = value.replace(memory_id, alias)
        return value
    if isinstance(value, Mapping):
        replaced: dict[Any, Any] = {}
        for key, item in value.items():
            new_key = _replace_memory_ids(key, replacements)
            if new_key in replaced:
                raise OllamaError(
                    "memory pseudonymization produced a duplicate object key"
                )
            replaced[new_key] = _replace_memory_ids(item, replacements)
        return replaced
    if isinstance(value, list):
        return [_replace_memory_ids(item, replacements) for item in value]
    if isinstance(value, tuple):
        return tuple(_replace_memory_ids(item, replacements) for item in value)
    return value


def _serialize_json_body(body: Mapping[str, Any]) -> bytes:
    # Keeping Unicode literal is necessary for the compatibility-normalized
    # scan below; JSON's default ``\\u`` escapes would hide those characters.
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def _normalized_for_boundary_scan(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    skeleton = normalized.translate(_BOUNDARY_CONFUSABLE_TRANSLATION)
    characters = []
    for character in skeleton:
        try:
            decimal = unicodedata.decimal(character)
        except ValueError:
            characters.append(character)
        else:
            characters.append(str(decimal))
    return "".join(characters)


def _contains_memory_id(serialized_body: str) -> bool:
    return _MEMORY_ID_IN_REQUEST_PATTERN.search(
        _normalized_for_boundary_scan(serialized_body)
    ) is not None


def _contains_reserved_memory_alias(value: str) -> bool:
    return _RESERVED_MEMORY_ALIAS_PATTERN.search(
        _normalized_for_boundary_scan(value)
    ) is not None


def _restore_memory_ids(
    content: str, alias_to_actual: Mapping[str, str]
) -> tuple[str, int]:
    """Normalize exact speech citations, then restore structured IDs."""

    try:
        decoded = json.loads(
            content,
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
            parse_float=_finite_json_float,
        )
    except (ValueError, RecursionError):
        # Conversation owns response-contract errors (including truncation,
        # duplicate keys, and non-standard constants), so retain that behavior
        # and all generation metadata by returning the model text unchanged.
        return content, 0
    if not isinstance(decoded, dict):
        return content, 0

    memory_used = decoded.get("memory_used")
    cited_aliases: frozenset[str] = frozenset()
    if isinstance(memory_used, list):
        if any(
            isinstance(item, str) and _contains_memory_id(item)
            for item in memory_used
        ):
            # A model must cite only request-local aliases. Never let a lucky,
            # stale, or injected internal ID bypass the translation boundary
            # merely because it happens to be allowlisted downstream.
            raise OllamaError(
                "Ollama assistant returned an internal memory ID"
            )
        cited_aliases = frozenset(
            item
            for item in memory_used
            if isinstance(item, str) and item in alias_to_actual
        )

    annotations_removed = 0
    speech = decoded.get("speech")
    if isinstance(speech, str):
        speech, annotations_removed = _remove_memory_citation_annotations(
            speech, cited_aliases
        )
        if _contains_reserved_memory_alias(speech):
            raise OllamaError(
                "Ollama assistant speech contains a reserved memory reference"
            )
        decoded["speech"] = speech

    if isinstance(memory_used, list):
        # List order and duplicates deliberately survive. The downstream robot
        # response validator remains the sole authority for citation validity.
        decoded["memory_used"] = [
            alias_to_actual.get(item, item) if isinstance(item, str) else item
            for item in memory_used
        ]
    return (
        json.dumps(decoded, ensure_ascii=False, separators=(",", ":")),
        annotations_removed,
    )


def _remove_memory_citation_annotations(
    speech: str, cited_aliases: frozenset[str]
) -> tuple[str, int]:
    """Remove only exact, redundant suffix citations declared structurally."""

    removed = 0
    while True:
        iteration_removed = 0

        def replacement(match: re.Match[str]) -> str:
            nonlocal iteration_removed
            if match.group("alias") not in cited_aliases:
                return match.group(0)
            iteration_removed += 1
            return ""

        normalized = _MEMORY_CITATION_ANNOTATION_PATTERN.sub(
            replacement, speech
        )
        if iteration_removed == 0:
            return speech, removed
        speech = normalized
        removed += iteration_removed


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    decoded: dict[str, Any] = {}
    for key, value in pairs:
        if key in decoded:
            raise ValueError("duplicate JSON object key")
        decoded[key] = value
    return decoded


def _reject_json_constant(value: str) -> None:
    raise ValueError("non-standard JSON constant")


def _finite_json_float(value: str) -> float:
    decoded = float(value)
    if not isfinite(decoded):
        raise ValueError("non-finite JSON number")
    return decoded


def _chat_result(payload: Mapping[str, Any], *, requested_model: str) -> ChatResult:
    if payload.get("done") is not True:
        raise OllamaError("Ollama returned an incomplete non-streaming response")

    response_model = payload.get("model")
    if response_model != requested_model:
        raise OllamaError("Ollama returned unexpected model metadata")

    message = payload.get("message")
    if not isinstance(message, Mapping):
        raise OllamaError("Ollama response is missing the assistant message")
    if message.get("role") != "assistant":
        raise OllamaError("Ollama response has an invalid message role")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise OllamaError("Ollama returned an empty assistant message")

    return ChatResult(
        model=response_model,
        content=content.strip(),
        done_reason=_optional_string(payload.get("done_reason"), "unknown"),
        total_duration_ns=_nonnegative_integer(payload.get("total_duration")),
        load_duration_ns=_nonnegative_integer(payload.get("load_duration")),
        prompt_eval_count=_nonnegative_integer(payload.get("prompt_eval_count")),
        eval_count=_nonnegative_integer(payload.get("eval_count")),
        eval_duration_ns=_nonnegative_integer(payload.get("eval_duration")),
        prompt_eval_duration_ns=_nonnegative_integer(
            payload.get("prompt_eval_duration")
        ),
    )


def _optional_string(value: Any, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _nonnegative_integer(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _temperature(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("temperature must be a number from 0 to 2")
    normalized = float(value)
    if not isfinite(normalized) or not 0.0 <= normalized <= 2.0:
        raise ValueError("temperature must be a number from 0 to 2")
    return normalized


def _seed(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("seed must be a non-negative integer")
    return value
