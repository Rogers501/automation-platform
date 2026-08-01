"""Framework exception hierarchy.

All errors raised inside the framework derive from :class:`FrameworkError`,
which carries a human-readable ``message`` plus a structured ``context``
mapping for diagnostics and downstream (AI) failure analysis.

The hierarchy is intentionally flat: one base class plus a focused subclass
per core concern, so callers can catch at the granularity they need.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "CacheError",
    "ClientConnectionError",
    "ClientError",
    "ClientStatusError",
    "ClientTimeoutError",
    "ConfigError",
    "ContextError",
    "DatabaseError",
    "DependencyError",
    "FrameworkError",
    "MQError",
    "RegistryError",
]


class FrameworkError(Exception):
    """Base class for every error raised by the framework.

    Args:
        message: Human-readable description of the failure.
        context: Optional structured key/value pairs aiding debugging and
            downstream analysis (e.g. request id, config key, env name).
    """

    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message: str = message
        self.context: dict[str, Any] = dict(context or {})

    def __str__(self) -> str:
        if self.context:
            pairs = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
            return f"{self.message} ({pairs})"
        return self.message


class ConfigError(FrameworkError):
    """Raised when configuration cannot be loaded or is invalid."""


class ContextError(FrameworkError):
    """Raised on test-context / scope errors (missing key, wrong scope)."""


class RegistryError(FrameworkError):
    """Raised on registry misuse (duplicate registration, unknown name)."""


class ClientError(FrameworkError):
    """Raised by capability clients (HTTP/DB/Redis/MQ) on failure."""


class ClientTimeoutError(ClientError):
    """Raised when an HTTP request exceeds its configured timeout."""


class ClientConnectionError(ClientError):
    """Raised on HTTP transport/connection failures (DNS, refused, reset)."""


class ClientStatusError(ClientError):
    """Raised when an HTTP response indicates failure (non-2xx).

    Attributes:
        status_code: The HTTP status code, when available.
        body_snippet: A truncated excerpt of the response body.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body_snippet: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        merged: dict[str, Any] = dict(context or {})
        if status_code is not None:
            merged.setdefault("status_code", status_code)
        if body_snippet is not None:
            merged.setdefault("body_snippet", body_snippet)
        super().__init__(message, context=merged)
        self.status_code: int | None = status_code
        self.body_snippet: str | None = body_snippet


class DatabaseError(ClientError):
    """Raised when a database operation fails (execution, transaction, connection).

    Wraps SQLAlchemy errors into the framework's unified hierarchy while
    preserving the original exception as ``__cause__`` for debugging.
    """


class CacheError(ClientError):
    """Raised when a Redis/cache operation fails (connection, command, pipeline).

    Wraps ``redis`` library errors into the framework's unified hierarchy
    while preserving the original exception as ``__cause__`` for debugging.
    """


class MQError(ClientError):
    """Raised when a message-queue operation fails (publish, consume, commit).

    Wraps broker-library errors (aiokafka, aio-pika, etc.) into the framework's
    unified hierarchy while preserving the original exception as
    ``__cause__`` for debugging.
    """


class DependencyError(FrameworkError):
    """Raised when a declared interface dependency cannot be resolved."""
