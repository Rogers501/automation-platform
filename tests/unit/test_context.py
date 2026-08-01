"""Unit tests for framework.core.context (contextvars-based trace correlation)."""

from __future__ import annotations

import asyncio
import dataclasses
from typing import Any

import pytest

from framework.core.context import (
    TestContext,
    bind_context,
    clear_context,
    current_trace_id,
    get_context,
    new_trace_id,
    set_context,
    trace,
)


@pytest.fixture(autouse=True)
def _clean_context() -> Any:
    """Ensure no context leaks between tests (rules 13/14)."""
    clear_context()
    yield
    clear_context()


# --- TestContext ---------------------------------------------------------


def test_testcontext_defaults_empty() -> None:
    """A fresh TestContext has all fields unset."""
    ctx = TestContext()
    assert ctx.trace_id is None
    assert ctx.span_id is None
    assert ctx.test_id is None
    assert ctx.request_id is None
    assert ctx.extra == {}


def test_testcontext_is_frozen() -> None:
    """TestContext is immutable; attribute assignment raises."""
    ctx = TestContext(trace_id="abc")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.trace_id = "xyz"
    assert ctx.trace_id == "abc"


def test_with_fields_sets_known_field() -> None:
    """Known fields set the matching attribute."""
    ctx = TestContext().with_fields(trace_id="t1")
    assert ctx.trace_id == "t1"


def test_with_fields_clears_known_field_with_none() -> None:
    """Passing None for a known field clears it."""
    ctx = TestContext(trace_id="t1").with_fields(trace_id=None)
    assert ctx.trace_id is None


def test_with_fields_extra_merged() -> None:
    """Unknown keys merge into extra without clobbering existing keys."""
    ctx = TestContext(extra={"a": 1}).with_fields(b=2, c=3)
    assert ctx.extra == {"a": 1, "b": 2, "c": 3}


def test_with_fields_does_not_mutate_original() -> None:
    """with_fields returns a new instance; the original is untouched."""
    ctx = TestContext(extra={"a": 1})
    child = ctx.with_fields(b=2)
    assert ctx.extra == {"a": 1}
    assert child.extra == {"a": 1, "b": 2}


def test_to_bindings_omits_none() -> None:
    """None fields are omitted; extra is flattened."""
    ctx = TestContext(trace_id="t1", span_id=None, extra={"k": "v"})
    bindings = ctx.to_bindings()
    assert bindings == {"trace_id": "t1", "k": "v"}
    assert "span_id" not in bindings


def test_to_bindings_empty_context() -> None:
    """An empty context yields no bindings."""
    assert TestContext().to_bindings() == {}


# --- new_trace_id --------------------------------------------------------


def test_new_trace_id_is_hex32() -> None:
    """A generated trace id is a 32-char hex string."""
    tid = new_trace_id()
    assert len(tid) == 32
    int(tid, 16)  # raises ValueError if not hex


def test_new_trace_id_unique() -> None:
    """Repeated generation produces distinct ids."""
    ids = {new_trace_id() for _ in range(1000)}
    assert len(ids) == 1000


# --- get / set / clear ---------------------------------------------------


def test_get_context_default_empty() -> None:
    """With no context set, get_context returns an empty TestContext."""
    assert get_context() == TestContext()


def test_set_context_replaces() -> None:
    """set_context installs the given context verbatim."""
    ctx = TestContext(trace_id="x")
    set_context(ctx)
    assert get_context() is ctx


def test_clear_context_resets() -> None:
    """clear_context removes any active trace."""
    set_context(TestContext(trace_id="x"))
    clear_context()
    assert get_context() == TestContext()
    assert current_trace_id() is None


def test_current_trace_id_default_none() -> None:
    """No trace active -> None."""
    assert current_trace_id() is None


def test_current_trace_id_after_set() -> None:
    """After setting a context, current_trace_id reflects it."""
    set_context(TestContext(trace_id="abc"))
    assert current_trace_id() == "abc"


# --- bind_context --------------------------------------------------------


def test_bind_context_sets_fields() -> None:
    """bind_context applies fields for the scope."""
    with bind_context(trace_id="t1") as ctx:
        assert ctx.trace_id == "t1"
        assert current_trace_id() == "t1"


def test_bind_context_restores_on_exit() -> None:
    """The previous context is restored when the scope exits."""
    with bind_context(trace_id="outer"):
        assert current_trace_id() == "outer"
    assert current_trace_id() is None


def test_bind_context_restores_on_exception() -> None:
    """Context is restored even when the block raises."""
    with pytest.raises(RuntimeError), bind_context(trace_id="boom"):
        raise RuntimeError("fail")
    assert current_trace_id() is None


def test_bind_context_inherits_parent() -> None:
    """A nested scope inherits the parent's fields."""
    with bind_context(trace_id="parent"):
        with bind_context(test_id="T1") as ctx:
            assert ctx.trace_id == "parent"
            assert ctx.test_id == "T1"
        assert current_trace_id() == "parent"


def test_bind_context_extra_fields() -> None:
    """Unknown fields land in extra and surface via to_bindings."""
    with bind_context(tenant_id="acme") as ctx:
        assert ctx.extra == {"tenant_id": "acme"}
        assert get_context().to_bindings() == {"tenant_id": "acme"}


# --- trace ---------------------------------------------------------------


def test_trace_auto_generates_id() -> None:
    """trace() with no id generates one."""
    with trace() as ctx:
        assert ctx.trace_id is not None
        assert len(ctx.trace_id) == 32
        assert current_trace_id() == ctx.trace_id


def test_trace_explicit_id() -> None:
    """An explicit trace id is honored."""
    with trace(trace_id="req-abc") as ctx:
        assert ctx.trace_id == "req-abc"
        assert current_trace_id() == "req-abc"


def test_trace_extra_fields() -> None:
    """trace forwards extra fields to the scope."""
    with trace(test_id="T1", tenant_id="acme") as ctx:
        assert ctx.test_id == "T1"
        assert ctx.extra == {"tenant_id": "acme"}


def test_trace_restores_on_exit() -> None:
    """trace restores the prior context on exit."""
    with trace(trace_id="x"):
        pass
    assert current_trace_id() is None


def test_trace_nested_inherits() -> None:
    """A nested trace inherits the parent trace id."""
    with trace(trace_id="outer"):
        with trace(test_id="T1") as inner:
            assert inner.trace_id == "outer"
            assert inner.test_id == "T1"
        assert current_trace_id() == "outer"


# --- async isolation -----------------------------------------------------


async def test_concurrent_tasks_isolate_context() -> None:
    """Each asyncio task carries its own context copy (concurrency requirement)."""
    results: dict[str, str | None] = {}

    async def worker(name: str, tid: str) -> None:
        with trace(trace_id=tid):
            await asyncio.sleep(0)
            results[name] = current_trace_id()

    await asyncio.gather(worker("a", "ta"), worker("b", "tb"))
    assert results == {"a": "ta", "b": "tb"}


async def test_context_does_not_leak_to_parent_task() -> None:
    """A trace set inside a task is not visible to the parent."""

    async def child() -> None:
        with trace(trace_id="child-only"):
            await asyncio.sleep(0)

    assert current_trace_id() is None
    await asyncio.create_task(child())
    assert current_trace_id() is None
