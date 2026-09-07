"""Small, dependency-free client for the local Ollama chat API."""

from __future__ import annotations

from dataclasses import dataclass
import json
from math import isfinite
import socket
from threading import Lock
from typing import Any, Callable, Mapping, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from .config import GenerationConfig, OllamaConfig


class OllamaError(RuntimeError):
    """Raised when Ollama cannot return a usable chat response."""


class OllamaTimeoutError(OllamaError):
    """Raised when a local Ollama socket operation exceeds its time budget."""


SMALL_MODEL_KEEP_ALIVE = -1
LARGE_MODEL_KEEP_ALIVE = 0
UNLOAD_KEEP_ALIVE = 0
MAX_OLLAMA_RESPONSE_BYTES = 64 * 1024


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

    @property
    def generation_tokens_per_second(self) -> Optional[float]:
        if self.eval_count <= 0 or self.eval_duration_ns <= 0:
            return None
        return self.eval_count * 1_000_000_000 / self.eval_duration_ns


class OllamaClient:
    """Call one local Ollama server using application configuration."""

    def __init__(
        self,
        ollama: OllamaConfig,
        generation: GenerationConfig,
        *,
        opener: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._ollama = ollama
        self._generation = generation
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
        if model not in {
            self._ollama.small_model,
            self._ollama.large_model,
        }:
            raise ValueError("model must be the configured small or large model")
        if not messages:
            raise ValueError("at least one chat message is required")

        request_temperature = (
            self._generation.temperature
            if temperature is None
            else _temperature(temperature)
        )
        request_seed = None if seed is None else _seed(seed)

        body = {
            "model": model,
            "messages": [message.to_dict() for message in messages],
            "stream": False,
            "think": self._generation.thinking,
            "keep_alive": (
                SMALL_MODEL_KEEP_ALIVE
                if model == self._ollama.small_model
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

        with self._schedule_lock:
            try:
                self._prepare_model(model)
                request_timeout = (
                    self._ollama.request_timeout_seconds
                    if model == self._ollama.small_model
                    else self._ollama.large_request_timeout_seconds
                )
                payload = self._post_json(
                    "/api/chat", body, timeout_seconds=request_timeout
                )
                result = _chat_result(payload, requested_model=model)
            except BaseException:
                # A failed or interrupted request may have changed Ollama's
                # actual residency even when no trustworthy response arrived.
                self._residency_known = False
                self._resident_model = None
                raise

            self._residency_known = True
            self._resident_model = (
                model if model == self._ollama.small_model else None
            )
            return result

    def _prepare_model(self, requested_model: str) -> None:
        if self._residency_known:
            if self._resident_model in {None, requested_model}:
                return
            model_to_unload = self._resident_model
        else:
            model_to_unload = (
                self._ollama.large_model
                if requested_model == self._ollama.small_model
                else self._ollama.small_model
            )

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
    ) -> Mapping[str, Any]:
        request = Request(
            f"{self._ollama.base_url}{endpoint}",
            data=json.dumps(body).encode("utf-8"),
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
