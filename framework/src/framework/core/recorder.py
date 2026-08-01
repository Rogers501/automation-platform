"""HTTP exchange recording for failure diagnostics.

A contextvar-based recorder captures request/response exchanges so that, on
test failure, the hooks layer can persist them as artifacts. Capability
clients (e.g. the HTTP client) write here via the recorder; the testing layer
owns the recorder lifecycle via :func:`bind_recorder`.

The recorder lives in ``core`` (not ``testing``) so capability clients can
depend on it without violating the downward dependency rule (rule 11).
Recording is a no-op when no recorder is active, so non-test use incurs no
overhead.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

__all__ = [
    "HttpExchange",
    "RequestRecorder",
    "bind_recorder",
    "clear_recorder",
    "get_recorder",
    "record_exchange",
]


@dataclass(frozen=True)
class HttpExchange:
    """A captured HTTP request/response pair (or a failed request).

    Bodies are pre-truncated and headers pre-redacted by the recording client,
    so instances are safe to persist as artifacts.
    """

    method: str
    url: str
    request_headers: dict[str, str]
    request_body: str | None
    status_code: int | None
    response_headers: dict[str, str]
    response_body: str | None
    elapsed_seconds: float
    error: str | None = None
    trace_id: str | None = None


@dataclass
class RequestRecorder:
    """Collects :class:`HttpExchange` instances for the current scope."""

    exchanges: list[HttpExchange] = field(default_factory=list)

    def record(self, exchange: HttpExchange) -> None:
        """Append a captured exchange."""
        self.exchanges.append(exchange)


_current: ContextVar[RequestRecorder | None] = ContextVar("framework_recorder", default=None)


def get_recorder() -> RequestRecorder | None:
    """Return the active recorder, or ``None`` when none is bound."""
    return _current.get()


@contextmanager
def bind_recorder() -> Iterator[RequestRecorder]:
    """Bind a fresh recorder for a scope, restoring the prior state on exit."""
    recorder = RequestRecorder()
    token = _current.set(recorder)
    try:
        yield recorder
    finally:
        _current.reset(token)


def clear_recorder() -> None:
    """Clear any active recorder."""
    _current.set(None)


def record_exchange(exchange: HttpExchange) -> None:
    """Record an exchange if a recorder is active (no-op otherwise)."""
    recorder = _current.get()
    if recorder is not None:
        recorder.record(exchange)
