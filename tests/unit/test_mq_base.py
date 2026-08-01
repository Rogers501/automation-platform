"""Unit tests for the unified MQ interface and value objects (rule 14)."""

from __future__ import annotations

import pytest

from framework.clients.mq.base import Message, MessageClient, PublishResult


def test_message_defaults() -> None:
    """Message requires only topic + body; other fields default."""
    msg = Message(topic="orders", body=b'{"id":1}')
    assert msg.topic == "orders"
    assert msg.body == b'{"id":1}'
    assert msg.key is None
    assert msg.headers == {}
    assert msg.partition is None
    assert msg.offset is None
    assert msg.timestamp is None


def test_message_full() -> None:
    """Message accepts all fields."""
    msg = Message(
        topic="events",
        body=b"data",
        key="event-42",
        headers={"type": "created"},
        partition=3,
        offset=99,
        timestamp=1700000000.0,
    )
    assert msg.key == "event-42"
    assert msg.headers == {"type": "created"}
    assert msg.partition == 3
    assert msg.offset == 99
    assert msg.timestamp == 1700000000.0


def test_message_is_frozen() -> None:
    """Message is immutable."""
    msg = Message(topic="t", body=b"x")
    with pytest.raises(AttributeError):
        msg.topic = "other"  # type: ignore[misc]


def test_message_headers_independent_per_instance() -> None:
    """Each Message gets its own headers dict (no shared mutable default)."""
    m1 = Message(topic="t", body=b"1", headers={"a": "1"})
    m2 = Message(topic="t", body=b"2")
    assert m1.headers == {"a": "1"}
    assert m2.headers == {}


def test_publish_result_defaults() -> None:
    """PublishResult requires only topic; partition/offset default to None."""
    result = PublishResult(topic="orders")
    assert result.topic == "orders"
    assert result.partition is None
    assert result.offset is None


def test_publish_result_full() -> None:
    """PublishResult accepts all fields."""
    result = PublishResult(topic="orders", partition=2, offset=42)
    assert result.partition == 2
    assert result.offset == 42


def test_publish_result_is_frozen() -> None:
    """PublishResult is immutable."""
    result = PublishResult(topic="t")
    with pytest.raises(AttributeError):
        result.topic = "other"  # type: ignore[misc]


def test_message_client_is_abstract() -> None:
    """MessageClient cannot be instantiated directly."""
    with pytest.raises(TypeError):
        MessageClient()  # type: ignore[abstract]


def test_message_client_subclass_must_implement_all() -> None:
    """A subclass missing methods cannot be instantiated."""

    class _Incomplete(MessageClient):
        async def publish(self, topic, body, **kw):  # type: ignore[no-untyped-def]
            ...

    with pytest.raises(TypeError):
        _Incomplete()  # type: ignore[abstract]


def test_message_client_subclass_works() -> None:
    """A fully-implemented subclass can be instantiated."""

    class _Complete(MessageClient):
        async def publish(self, topic, body, **kw):  # type: ignore[no-untyped-def]
            return PublishResult(topic=topic)

        async def consume(self, topic, handler, **kw):  # type: ignore[no-untyped-def]
            ...

        async def commit(self, message=None):  # type: ignore[no-untyped-def, override]
            ...

        async def close(self):  # type: ignore[no-untyped-def, override]
            ...

    client = _Complete()
    assert isinstance(client, MessageClient)


async def test_message_client_context_manager_calls_close() -> None:
    """``async with`` calls close() on exit."""

    class _Tracking(MessageClient):
        closed = False

        async def publish(self, topic, body, **kw):  # type: ignore[no-untyped-def]
            return PublishResult(topic=topic)

        async def consume(self, topic, handler, **kw):  # type: ignore[no-untyped-def]
            ...

        async def commit(self, message=None):  # type: ignore[no-untyped-def, override]
            ...

        async def close(self) -> None:  # type: ignore[override]
            self.closed = True

    client = _Tracking()
    async with client:
        pass
    assert client.closed


def test_message_handler_type_alias() -> None:
    """MessageHandler is a callable type alias (smoke check)."""

    async def handler(msg: Message) -> None:
        return None

    assert callable(handler)
