"""Opt-in monotonic tracing of the actual conversation/backend path.

Wall-clock spans are nested, never additive across ancestors and children.
Ollama durations are metadata on ``backend_chat`` spans, not extra wall spans:
loading, prompt evaluation and decoding overlap that enclosing HTTP request.
Tracing is disabled unless a recorder is explicitly activated. Captured prompts
are intended only for consented synthetic experiment data.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
import time
from typing import Any, Callable, Iterator


_ACTIVE: ContextVar["TraceRecorder | None"] = ContextVar("oline_trace", default=None)
_PARENT: ContextVar[int | None] = ContextVar("oline_trace_parent", default=None)


class TraceRecorder:
    """Record spans, optionally persisting both starts and finishes immediately.

    ``sink`` receives detached dictionaries containing ``event=span_start`` or
    ``event=span_end``. A start without an end preserves abrupt interruption.
    ``eviction_verifier`` may poll actual backend residency after an unload;
    its returned snapshot is retained and its exceptions abort the operation.
    """

    def __init__(self, sink: Callable[[dict[str, Any]], None] | None = None,
                 eviction_verifier: Callable[[str], Any] | None = None) -> None:
        self.events: list[dict[str, Any]] = []
        self.sink = sink
        self.eviction_verifier = eviction_verifier

    @contextmanager
    def activate(self) -> Iterator["TraceRecorder"]:
        active_token = _ACTIVE.set(self)
        parent_token = _PARENT.set(None)
        try:
            yield self
        finally:
            _PARENT.reset(parent_token)
            _ACTIVE.reset(active_token)

    def _emit(self, event: str, span: dict[str, Any]) -> None:
        if self.sink is not None:
            self.sink(deepcopy({"event": event, **span}))


@contextmanager
def trace_span(name: str, **attributes: Any) -> Iterator[dict[str, Any]]:
    """Yield mutable attributes; close and preserve spans on BaseException."""
    recorder = _ACTIVE.get()
    if recorder is None:
        yield attributes
        return
    span: dict[str, Any] = {
        "id": len(recorder.events) + 1,
        "parent_id": _PARENT.get(),
        "name": name,
        "clock": "monotonic_ns",
        "start_ns": time.monotonic_ns(),
        "end_ns": None,
        "wall_ns": None,
        "status": "running",
        "attributes": attributes,
    }
    recorder.events.append(span)
    parent_token = _PARENT.set(span["id"])
    try:
        recorder._emit("span_start", span)
        yield attributes
    except BaseException as exc:
        span["status"] = "interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "error"
        attributes["error_type"] = type(exc).__name__
        attributes["error"] = str(exc)
        raise
    else:
        span["status"] = "ok"
    finally:
        span["end_ns"] = time.monotonic_ns()
        span["wall_ns"] = span["end_ns"] - span["start_ns"]
        _PARENT.reset(parent_token)
        recorder._emit("span_end", span)


def traced(name: str) -> Callable:
    """Apply a span around a synchronous function, including failed returns."""
    def decorate(function: Callable) -> Callable:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            with trace_span(name):
                return function(*args, **kwargs)
        return wrapped
    return decorate


def verify_eviction(model: str) -> None:
    """Run benchmark verification only when explicitly configured."""
    recorder = _ACTIVE.get()
    if recorder is not None and recorder.eviction_verifier is not None:
        with trace_span("eviction_verification", model=model) as attributes:
            attributes["residency_after"] = recorder.eviction_verifier(model)


def generation_call(backend: Any, model: str, messages: Any, **kwargs: Any) -> Any:
    """Capture the exact pre-pseudonymization generation call for replay."""
    recorder = _ACTIVE.get()
    if recorder is None:
        return backend.chat(model, messages, **kwargs)
    with trace_span(
        "answer_generation", model=model,
        request={"model": model, "messages": [message.to_dict() for message in messages],
                 **deepcopy(kwargs)},
    ) as attributes:
        result = backend.chat(model, messages, **kwargs)
        attributes["actual_model"] = getattr(result, "model", None)
        attributes["content"] = getattr(result, "content", None)
        return result
