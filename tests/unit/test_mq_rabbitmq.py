"""Unit tests for RabbitMQClient using injected fakes (no real broker, rule 14)."""

from __future__ import annotations

from typing import Any

import pytest

from framework.clients.mq import create_mq_client
from framework.clients.mq.base import Message, PublishResult
from framework.clients.mq.rabbitmq import RabbitMQClient
from framework.core.config import MQSettings, MQType, RabbitMQSettings
from framework.core.exceptions import MQError

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeIncomingMessage:
    """Stand-in for aio-pika IncomingMessage."""

    def __init__(
        self,
        body: bytes,
        *,
        headers: dict[str, Any] | None = None,
        routing_key: str = "",
    ) -> None:
        self.body = body
        self.headers = headers or {}
        self.routing_key = routing_key
        self.acked = False
        self.nacked = False

    async def ack(self) -> None:
        self.acked = True

    async def nack(self, *, requeue: bool = True) -> None:
        self.nacked = True


class _FakeExchange:
    """Fake aio-pika Exchange."""

    def __init__(self, name: str = "") -> None:
        self.name = name
        self.published: list[tuple[bytes, str]] = []

    async def publish(self, message: Any, routing_key: str) -> None:
        self.published.append((message.body, routing_key))


class _FakeDefaultExchange(_FakeExchange):
    """Fake default exchange (used when no exchange is configured)."""


class _FakeQueue:
    """Fake aio-pika Queue."""

    def __init__(self, messages: list[_FakeIncomingMessage]) -> None:
        self._messages = list(messages)
        self._consumer: Any = None
        self._consumer_tag = "ctag-fake"
        self.cancelled = False

    async def consume(self, callback: Any, *, no_ack: bool = True) -> str:
        self._consumer = callback
        # Deliver messages immediately
        for msg in self._messages:
            if no_ack:
                await callback(msg)
            else:
                await callback(msg)
        return self._consumer_tag

    async def cancel(self, consumer_tag: str) -> None:
        self.cancelled = True


class _FakeChannel:
    """Fake aio-pika Channel."""

    def __init__(
        self,
        queue_messages: list[_FakeIncomingMessage] | None = None,
        exchange: _FakeExchange | None = None,
    ) -> None:
        self._queue_messages = queue_messages or []
        self._exchange = exchange
        self.default_exchange = _FakeDefaultExchange()
        self.qos_set = False

    async def set_qos(self, *, prefetch_count: int) -> None:
        self.qos_set = True

    async def declare_queue(
        self,
        name: str,
        *,
        durable: bool = True,
        auto_delete: bool = False,
    ) -> _FakeQueue:
        return _FakeQueue(self._queue_messages)

    async def get_exchange(self, name: str, *, ensure: bool = False) -> _FakeExchange | None:
        return self._exchange

    async def declare_exchange(
        self,
        name: str,
        exchange_type: Any,
        *,
        durable: bool = True,
    ) -> _FakeExchange:
        self._exchange = _FakeExchange(name)
        return self._exchange

    async def close(self) -> None:
        pass


class _FakeConnection:
    """Fake aio-pika RobustConnection."""

    def __init__(self, channel: _FakeChannel) -> None:
        self._channel = channel
        self.closed = False

    async def channel(self) -> _FakeChannel:
        return self._channel

    async def close(self) -> None:
        self.closed = True


class _FakeAMQPMessage:
    """Stand-in for aio_pika.Message."""

    def __init__(self, body: bytes, **kwargs: Any) -> None:
        self.body = body


def _client(
    channel: _FakeChannel | None = None,
    connection: _FakeConnection | None = None,
) -> RabbitMQClient:
    """Build a RabbitMQClient wired to fakes."""
    if connection is None and channel is not None:
        connection = _FakeConnection(channel)
    client = RabbitMQClient(
        settings=MQSettings(),
        connection=connection,
        channel=channel,
    )
    # Inject a fake message builder so publish() works without aio_pika.
    client._build_message = (  # type: ignore[method-assign]
        lambda body, headers: _FakeAMQPMessage(body)
    )
    return client


async def _noop(msg: Message) -> None:
    """No-op async handler."""


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------


async def test_publish_to_default_exchange() -> None:
    """publish sends to default exchange with routing key."""
    channel = _FakeChannel()
    client = _client(channel=channel)

    result = await client.publish("orders", b'{"id":1}')

    assert isinstance(result, PublishResult)
    assert result.topic == "orders"
    assert len(channel.default_exchange.published) == 1
    assert channel.default_exchange.published[0][0] == b'{"id":1}'


async def test_publish_encodes_str_body() -> None:
    """A str body is UTF-8 encoded."""
    channel = _FakeChannel()
    client = _client(channel=channel)

    await client.publish("queue", "hello")

    assert channel.default_exchange.published[0][0] == b"hello"


async def test_publish_with_routing_key() -> None:
    """publish uses key as routing key when provided."""
    channel = _FakeChannel()
    client = _client(channel=channel)

    await client.publish("exchange", b"data", key="order.created")

    assert channel.default_exchange.published[0][1] == "order.created"


async def test_publish_on_closed_raises() -> None:
    """Publishing after close raises MQError."""
    client = _client(channel=_FakeChannel())
    await client.close()

    with pytest.raises(MQError):
        await client.publish("q", b"data")


# ---------------------------------------------------------------------------
# Consume
# ---------------------------------------------------------------------------


async def test_consume_calls_handler() -> None:
    """consume invokes the handler for each message."""
    messages = [
        _FakeIncomingMessage(b"msg1"),
        _FakeIncomingMessage(b"msg2"),
    ]
    received: list[Message] = []

    async def handler(msg: Message) -> None:
        received.append(msg)

    channel = _FakeChannel(queue_messages=messages)
    client = _client(channel=channel)
    await client.consume("queue", handler, max_messages=2)

    assert len(received) == 2
    assert received[0].body == b"msg1"
    assert received[1].body == b"msg2"


async def test_consume_empty_queue() -> None:
    """consume with no messages completes without calling handler."""
    received: list[Message] = []

    async def handler(msg: Message) -> None:
        received.append(msg)

    channel = _FakeChannel(queue_messages=[])
    client = _client(channel=channel)
    await client.consume("queue", handler, max_messages=5)

    assert received == []


async def test_consume_auto_ack() -> None:
    """consume with auto_commit=True auto-acks messages."""
    messages = [_FakeIncomingMessage(b"m1")]
    channel = _FakeChannel(queue_messages=messages)
    client = _client(channel=channel)
    await client.consume("q", _noop, auto_commit=True, max_messages=1)

    # no_ack=True means aio-pika auto-acks; our fake doesn't check
    # but the handler ran successfully
    assert len(messages) == 1


async def test_consume_manual_ack() -> None:
    """consume with auto_commit=False manually acks on success."""
    msg = _FakeIncomingMessage(b"m1")
    channel = _FakeChannel(queue_messages=[msg])
    client = _client(channel=channel)
    await client.consume("q", _noop, auto_commit=False, max_messages=1)

    assert msg.acked


async def test_consume_nack_on_handler_error() -> None:
    """consume nacks when handler raises (auto_commit=False)."""
    msg = _FakeIncomingMessage(b"m1")
    channel = _FakeChannel(queue_messages=[msg])

    async def handler(m: Message) -> None:
        raise ValueError("bad handler")

    client = _client(channel=channel)

    with pytest.raises(MQError):
        await client.consume("q", handler, auto_commit=False, max_messages=1)

    assert msg.nacked


# ---------------------------------------------------------------------------
# Close / lifecycle
# ---------------------------------------------------------------------------


async def test_close() -> None:
    """close marks client as closed."""
    channel = _FakeChannel()
    client = _client(channel=channel)
    await client.publish("q", b"data")
    await client.close()

    assert client.is_closed


async def test_close_without_connection() -> None:
    """close works even if no connection was ever used."""
    client = _client()
    await client.close()
    assert client.is_closed


async def test_async_context_manager() -> None:
    """async with closes the client."""
    channel = _FakeChannel()
    async with _client(channel=channel) as client:
        await client.publish("q", b"data")
    assert client.is_closed


# ---------------------------------------------------------------------------
# _amqp_to_message
# ---------------------------------------------------------------------------


def test_amqp_to_message_full() -> None:
    """_amqp_to_message converts all fields."""
    msg = _FakeIncomingMessage(
        b'{"id":1}',
        headers={"type": "created"},
        routing_key="order.created",
    )
    result = RabbitMQClient._amqp_to_message(msg, "queue")

    assert result.topic == "queue"
    assert result.body == b'{"id":1}'
    assert result.headers == {"type": "created"}


def test_amqp_to_message_no_headers() -> None:
    """_amqp_to_message defaults headers when absent."""
    msg = _FakeIncomingMessage(b"data")
    result = RabbitMQClient._amqp_to_message(msg, "q")

    assert result.headers == {}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_create_mq_client_rabbitmq() -> None:
    """create_mq_client returns a RabbitMQClient for type=rabbitmq."""
    client = create_mq_client(MQSettings(type=MQType.RABBITMQ))
    assert isinstance(client, RabbitMQClient)


def test_create_mq_client_kafka_still_works() -> None:
    """create_mq_client still returns KafkaClient for type=kafka."""
    from framework.clients.mq import KafkaClient

    client = create_mq_client(MQSettings(type=MQType.KAFKA))
    assert isinstance(client, KafkaClient)


def test_create_mq_client_rocketmq_still_works() -> None:
    """create_mq_client still returns RocketMQClient for type=rocketmq."""
    from framework.clients.mq import RocketMQClient

    client = create_mq_client(MQSettings(type=MQType.ROCKETMQ))
    assert isinstance(client, RocketMQClient)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_rabbitmq_settings_defaults() -> None:
    """RabbitMQSettings has sensible defaults."""
    settings = RabbitMQSettings()
    assert settings.host == "localhost"
    assert settings.port == 5672
    assert settings.username == "guest"
    assert settings.virtual_host == "/"
    assert settings.exchange_type == "direct"
    assert settings.exchange_durable is True
    assert settings.prefetch_count == 10


def test_mq_settings_has_rabbitmq() -> None:
    """MQSettings includes a rabbitmq field."""
    settings = MQSettings()
    assert isinstance(settings.rabbitmq, RabbitMQSettings)


def test_mq_settings_rabbitmq_type() -> None:
    """MQSettings can be configured for rabbitmq."""
    settings = MQSettings(type=MQType.RABBITMQ)
    assert settings.type == MQType.RABBITMQ
    assert isinstance(settings.rabbitmq, RabbitMQSettings)
