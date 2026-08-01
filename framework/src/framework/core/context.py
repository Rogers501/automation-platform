"""Request/test context propagation via ``contextvars``.

Provides trace_id (and extensible correlation fields) that flow across the
request lifecycle: the logger auto-binds the current context, and the HTTP
client injects it as an ``X-Trace-Id`` header. Because the storage is a
:class:`contextvars.ContextVar`, concurrent tests/tasks each carry their own
trace -- no cross-talk under ``pytest-xdist`` or ``asyncio`` concurrency
(requirement: concurrent execution).

Usage::

    from framework.core.context import trace, current_trace_id
    from framework.core.logger import get_logger

    with trace() as ctx:                      # auto-generates a trace_id
        log = get_logger("orders")            # logs now carry trace_id
        assert current_trace_id() == ctx.trace_id
        await client.get("/orders")           # X-Trace-Id header injected

    with trace(trace_id="req-abc", test_id="T1") as ctx:
        ...                                   # explicit id + extra fields
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from typing import Any, ClassVar

__all__ = [
    "TestContext",
    "bind_context",
    "clear_context",
    "current_trace_id",
    "get_context",
    "new_trace_id",
    "set_context",
    "trace",
]

#: Correlation fields stored directly on :class:`TestContext`.
_KNOWN_FIELDS: frozenset[str] = frozenset({"trace_id", "span_id", "test_id", "request_id"})


@dataclass(frozen=True)
class TestContext:
    """Immutable correlation context for a single test/request flow.

    Instances are value objects: mutate by producing a new copy via
    :meth:`with_fields` (never by editing fields in place). The ``extra``
    mapping holds arbitrary additional correlation keys (e.g. ``tenant_id``).

    Attributes:
        trace_id: End-to-end trace identifier (propagated to logs + HTTP).
        span_id: Optional finer-grained span within a trace.
        test_id: Optional identifier of the owning test case.
        request_id: Optional per-request identifier.
        extra: Optional bag of additional correlation key/value pairs.
    """

    __test__: ClassVar[bool] = False
    trace_id: str | None = None
    span_id: str | None = None
    test_id: str | None = None
    request_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def with_fields(self, **fields: Any) -> TestContext:
        """Return a copy with the given fields updated.

        Known fields (``trace_id``/``span_id``/``test_id``/``request_id``) set
        the matching attribute; any other key is merged into ``extra``.

        Args:
            **fields: Fields to set (``None`` clears a known field).

        Returns:
            A new :class:`TestContext` with the updates applied.
        """
        updates: dict[str, Any] = {}
        extra_update: dict[str, Any] = {}
        for key, value in fields.items():
            if key in _KNOWN_FIELDS:
                updates[key] = value
            else:
                extra_update[key] = value
        if extra_update:
            updates["extra"] = {**self.extra, **extra_update}
        return replace(self, **updates)

    def to_bindings(self) -> dict[str, Any]:
        """Return non-None correlation fields as a flat dict for log binding.

        Omits ``None`` values so unset fields do not clutter log records.
        """
        bindings: dict[str, Any] = {}
        if self.trace_id is not None:
            bindings["trace_id"] = self.trace_id
        if self.span_id is not None:
            bindings["span_id"] = self.span_id
        if self.test_id is not None:
            bindings["test_id"] = self.test_id
        if self.request_id is not None:
            bindings["request_id"] = self.request_id
        if self.extra:
            bindings.update(self.extra)
        return bindings


_current: ContextVar[TestContext | None] = ContextVar("framework_test_context", default=None)


def new_trace_id() -> str:
    """Generate a new random trace id (32-char hex)."""
    return uuid.uuid4().hex


def get_context() -> TestContext:
    """Return the current :class:`TestContext` (an empty one if none set)."""
    ctx = _current.get()
    return ctx if ctx is not None else TestContext()


def set_context(ctx: TestContext) -> None:
    """Replace the current context with ``ctx``."""
    _current.set(ctx)


def clear_context() -> None:
    """Reset the current context to an empty state."""
    _current.set(None)


def current_trace_id() -> str | None:
    """Return the current trace id, or ``None`` if no trace is active."""
    return get_context().trace_id


@contextmanager
def bind_context(**fields: Any) -> Iterator[TestContext]:
    """Open a child context scope for a block, restoring the parent on exit.

    The new context inherits all fields from the current one and applies
    ``fields`` (see :meth:`TestContext.with_fields`). The previous context is
    restored when the block exits, even on exception.

    Args:
        **fields: Correlation fields to set for the scope.

    Yields:
        The new :class:`TestContext`.
    """
    parent = get_context()
    ctx = parent.with_fields(**fields)
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)


@contextmanager
def trace(trace_id: str | None = None, **fields: Any) -> Iterator[TestContext]:
    """Open a trace scope, auto-generating a trace id when none is supplied.

    Convenience wrapper around :func:`bind_context` that ensures a trace id
    exists (generating one via :func:`new_trace_id` when ``trace_id`` is
    ``None``).

    Args:
        trace_id: Explicit trace id; inherited from the parent scope or
            auto-generated when ``None``.
        **fields: Additional correlation fields for the scope.

    Yields:
        The new :class:`TestContext` (with ``trace_id`` guaranteed set).
    """
    parent = get_context()
    resolved = trace_id if trace_id is not None else (parent.trace_id or new_trace_id())
    with bind_context(trace_id=resolved, **fields) as ctx:
        yield ctx
