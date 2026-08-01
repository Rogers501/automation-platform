"""Unit tests for the framework exception hierarchy."""

from __future__ import annotations

import pytest

from framework.core.exceptions import (
    CacheError,
    ClientConnectionError,
    ClientError,
    ClientStatusError,
    ClientTimeoutError,
    ConfigError,
    ContextError,
    DatabaseError,
    DependencyError,
    FrameworkError,
    MQError,
    RegistryError,
)


def test_framework_error_message_and_context() -> None:
    """FrameworkError stores message and a copy of context."""
    err = FrameworkError("boom", context={"key": "value"})
    assert err.message == "boom"
    assert err.context == {"key": "value"}


def test_framework_error_default_context_empty() -> None:
    """Omitting context yields an empty dict (not None)."""
    err = FrameworkError("boom")
    assert err.context == {}


def test_framework_error_context_is_copied() -> None:
    """Mutating the caller's dict after construction does not affect the error."""
    ctx = {"a": 1}
    err = FrameworkError("boom", context=ctx)
    ctx["a"] = 2
    assert err.context == {"a": 1}


def test_framework_error_str_with_context() -> None:
    """str includes context pairs when present."""
    err = FrameworkError("boom", context={"k": 1})
    assert str(err) == "boom (k=1)"


def test_framework_error_str_without_context() -> None:
    """str is just the message when context is empty."""
    assert str(FrameworkError("boom")) == "boom"


@pytest.mark.parametrize(
    "exc_cls",
    [
        ConfigError,
        ContextError,
        RegistryError,
        ClientError,
        DependencyError,
    ],
)
def test_subclasses_are_framework_errors(exc_cls: type[FrameworkError]) -> None:
    """Each domain subclass is a FrameworkError carrying message/context."""
    err = exc_cls("x", context={"z": 9})
    assert isinstance(err, FrameworkError)
    assert isinstance(err, Exception)
    assert err.message == "x"
    assert err.context == {"z": 9}


def test_subclass_caught_as_base() -> None:
    """A subclass exception is catchable as FrameworkError."""
    with pytest.raises(FrameworkError):
        raise ConfigError("bad config")


def test_client_status_error_carries_status_and_body() -> None:
    """ClientStatusError exposes status_code and body_snippet."""
    err = ClientStatusError("bad", status_code=503, body_snippet="Service Unavailable")
    assert err.status_code == 503
    assert err.body_snippet == "Service Unavailable"
    assert err.context["status_code"] == 503
    assert err.context["body_snippet"] == "Service Unavailable"


def test_client_status_error_defaults_none() -> None:
    """Optional status/body default to None and are omitted from context."""
    err = ClientStatusError("bad")
    assert err.status_code is None
    assert err.body_snippet is None
    assert "status_code" not in err.context


def test_client_status_error_is_client_error() -> None:
    """ClientStatusError is a ClientError and a FrameworkError."""
    err = ClientStatusError("bad", status_code=500)
    assert isinstance(err, ClientError)
    assert isinstance(err, FrameworkError)


@pytest.mark.parametrize(
    "exc_cls",
    [ClientTimeoutError, ClientConnectionError, DatabaseError, CacheError, MQError],
)
def test_client_subclasses_are_client_errors(
    exc_cls: type[ClientError],
) -> None:
    """Timeout/connection/database/cache/mq errors are all ClientErrors."""
    err = exc_cls("fail", context={"url": "http://x"})
    assert isinstance(err, ClientError)
    assert isinstance(err, FrameworkError)
    assert err.message == "fail"


def test_database_error_carries_context() -> None:
    """DatabaseError preserves structured context for diagnostics."""
    err = DatabaseError("query failed", context={"error_type": "OperationalError"})
    assert isinstance(err, ClientError)
    assert err.context["error_type"] == "OperationalError"
    assert "query failed" in str(err)


def test_cache_error_carries_context() -> None:
    """CacheError preserves structured context for diagnostics."""
    err = CacheError("get failed", context={"op": "get", "key": "user:1"})
    assert isinstance(err, ClientError)
    assert err.context["op"] == "get"
    assert err.context["key"] == "user:1"
    assert "get failed" in str(err)


def test_mq_error_carries_context() -> None:
    """MQError preserves structured context for diagnostics."""
    err = MQError("publish failed", context={"op": "publish", "topic": "orders"})
    assert isinstance(err, ClientError)
    assert err.context["op"] == "publish"
    assert err.context["topic"] == "orders"
    assert "publish failed" in str(err)
