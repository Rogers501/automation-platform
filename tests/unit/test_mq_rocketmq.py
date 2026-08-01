"""Unit tests for RocketMQClient using injected fakes (no real broker, rule 14)."""

from __future__ import annotations

from typing import Any

import pytest

from framework.clients.mq import create_mq_client
from framework.clients.mq.base import Message, PublishResult
from framework.clients.mq.rabbitmq import RabbitMQClient
from framework.clients.mq.rocketmq import RocketMQClient
from framework.core.config import MQSettings, MQType, RocketMQSettings
from framework.core.exceptions import MQError

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeSendResult:
    """Stand-in for rocketmq SendResult."""

    def __init__(self, queue_id: int = 0, queue_offset: int = 0) -> None:
        self.queue_id = queue_id
        self.queue_offset = queue_offset


class _FakeRmqMessage:
    """Stand-in for rocketmq.client.Message."""

    def __init__(self, topic: str, body: bytes) -> None:
        self.topic = topic
        self.body = body
        self._keys: str | None = None
        self._properties: dict[str, str] = {}

    def set_keys(self, keys: str) -> None:
        self._keys = keys

    def set_property(self, key: str, value: str) -> None:
        self._properties[key] = value


class _FakeProducer:
    """Fake rocketmq PushProducer."""

    def __init__(self) -> None:
        self.sent: list[_FakeRmqMessage] = []
        self.started = False
        self.shutdown_called = False
        self._raises: Exception | None = None
        self._send_count = 0

    def will_raise(self, exc: Exception) -> None:
        self._raises = exc

    def start(self, name_server: str) -> None:
        self.started = True

    def shutdown(self) -> None:
        self.shutdown_called = True

    def send_sync(self, msg: _FakeRmqMessage) -> _FakeSendResult:
        if self._raises is not None:
            raise self._raises
        self.sent.append(msg)
        result = _FakeSendResult(queue_id=0, queue_offset=self._send_count)
        self._send_count += 1
        return result


class _FakeConsumerRecord:
    """Stand-in for a RocketMQ message delivered to the callback."""

    def __init__(
        self,
        topic: str,
        body: bytes,
        *,
        keys: str | None = None,
        queue_id: int = 0,
        queue_offset: int = 0,
        born_timestamp: float = 0.0,
    ) -> None:
        self.topic = topic
        self.body = body
        self.keys = keys
        self.queue_id = queue_id
        self.queue_offset = queue_offset
        self.born_timestamp = born_timestamp


class _FakeConsumer:
    """Fake rocketmq PushConsumer."""

    def __init__(self, records: list[_FakeConsumerRecord]) -> None:
        self._records = list(records)
        self.started = False
        self.shutdown_called = False
        self._callback: Any = None
        self._topic = ""

    def set_thread_count(self, count: int) -> None:
        pass

    def subscribe(self, topic: str, callback: Any) -> None:
        self._topic = topic
        self._callback = callback

    def start(self, name_server: str) -> None:
        self.started = True
        # Immediately deliver all messages to the callback.
        for record in self._records:
            self._callback(record)

    def shutdown(self) -> None:
        self.shutdown_called = True


def _consumer_factory(records: list[_FakeConsumerRecord]) -> Any:
    """Return a callable that creates a _FakeConsumer with a copy of records."""

    def factory(topic: str, **kwargs: Any) -> _FakeConsumer:
        return _FakeConsumer(list(records))

    return factory


async def _noop(msg: Message) -> None:
    """No-op async handler for tests."""


def _client(
    producer: _FakeProducer | None = None,
    consumer_factory: Any = None,
) -> RocketMQClient:
    """Build a RocketMQClient wired to fakes."""
    client = RocketMQClient(
        settings=MQSettings(),
        producer=producer,
        consumer_factory=consumer_factory,
    )
    # Inject a fake message builder so publish() works without rocketmq installed.
    client._build_message = (  # type: ignore[method-assign]
        lambda topic, body, key=None, headers=None: _build_fake_message(topic, body, key, headers)
    )
    return client


def _build_fake_message(
    topic: str,
    body: bytes,
    key: str | None = None,
    headers: Any = None,
) -> _FakeRmqMessage:
    """Build a _FakeRmqMessage matching the real rocketmq Message API."""
    msg = _FakeRmqMessage(topic, body)
    if key:
        msg.set_keys(key)
    if headers:
        for h_key, h_val in headers.items():
            msg.set_property(h_key, h_val)
    return msg


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------


async def test_publish_returns_result() -> None:
    """publish sends the message and returns PublishResult metadata."""
    producer = _FakeProducer()
    client = _client(producer=producer)

    result = await client.publish("orders", b'{"id":1}')

    assert isinstance(result, PublishResult)
    assert result.topic == "orders"
    assert len(producer.sent) == 1
    assert producer.sent[0].topic == "orders"
    assert producer.sent[0].body == b'{"id":1}'


async def test_publish_encodes_str_body() -> None:
    """A str body is UTF-8 encoded before sending."""
    producer = _FakeProducer()
    client = _client(producer=producer)

    await client.publish("topic", "hello")

    assert producer.sent[0].body == b"hello"


async def test_publish_with_key() -> None:
    """publish sets the message key."""
    producer = _FakeProducer()
    client = _client(producer=producer)

    await client.publish("topic", b"data", key="order-1")

    assert producer.sent[0]._keys == "order-1"


async def test_publish_with_headers() -> None:
    """publish sets message properties as headers."""
    producer = _FakeProducer()
    client = _client(producer=producer)

    await client.publish("topic", b"data", headers={"type": "created"})

    assert producer.sent[0]._properties == {"type": "created"}


async def test_publish_error_wrapped() -> None:
    """A producer error surfaces as MQError."""
    producer = _FakeProducer()
    producer.will_raise(RuntimeError("broker unavailable"))
    client = _client(producer=producer)

    with pytest.raises(MQError) as info:
        await client.publish("topic", b"data")

    assert "broker unavailable" in str(info.value)
    assert info.value.context["op"] == "publish"
    assert info.value.context["error_type"] == "RuntimeError"


async def test_publish_on_closed_raises() -> None:
    """Publishing after close raises MQError."""
    producer = _FakeProducer()
    client = _client(producer=producer)
    await client.close()

    with pytest.raises(MQError):
        await client.publish("topic", b"data")


# ---------------------------------------------------------------------------
# Consume
# ---------------------------------------------------------------------------


async def test_consume_calls_handler() -> None:
    """consume invokes the handler for each message."""
    records = [
        _FakeConsumerRecord(topic="t", body=b"msg1"),
        _FakeConsumerRecord(topic="t", body=b"msg2"),
    ]
    received: list[Message] = []

    async def handler(msg: Message) -> None:
        received.append(msg)

    client = _client(consumer_factory=_consumer_factory(records))
    await client.consume("t", handler, max_messages=2)

    assert len(received) == 2
    assert received[0].body == b"msg1"
    assert received[1].body == b"msg2"


async def test_consume_empty_topic() -> None:
    """consume with no messages completes without calling the handler."""
    received: list[Message] = []

    async def handler(msg: Message) -> None:
        received.append(msg)

    client = _client(consumer_factory=_consumer_factory([]))
    await client.consume("t", handler, max_messages=5)

    assert received == []


# ---------------------------------------------------------------------------
# Commit
# ---------------------------------------------------------------------------


async def test_commit_is_noop() -> None:
    """commit is a no-op for push consumer (auto-ack)."""
    client = _client()
    # Should not raise.
    await client.commit()
    await client.commit(Message(topic="t", body=b"x"))


# ---------------------------------------------------------------------------
# Close / lifecycle
# ---------------------------------------------------------------------------


async def test_close_stops_producer() -> None:
    """close shuts down the producer."""
    producer = _FakeProducer()
    client = _client(producer=producer)
    await client.publish("t", b"data")
    await client.close()

    assert producer.shutdown_called
    assert client.is_closed


async def test_close_without_producer() -> None:
    """close works even if no producer was ever used."""
    client = _client()
    await client.close()
    assert client.is_closed


async def test_async_context_manager_closes() -> None:
    """async with closes the client on exit."""
    producer = _FakeProducer()
    async with _client(producer=producer) as client:
        await client.publish("t", b"data")
    assert client.is_closed
    assert producer.shutdown_called


# ---------------------------------------------------------------------------
# _record_to_message
# ---------------------------------------------------------------------------


def test_record_to_message_full() -> None:
    """_record_to_message converts all fields from a RocketMQ record."""
    record = _FakeConsumerRecord(
        topic="orders",
        body=b'{"id":1}',
        keys="order-1",
        queue_id=2,
        queue_offset=42,
        born_timestamp=1700000000.0,
    )
    msg = RocketMQClient._record_to_message(record)

    assert msg.topic == "orders"
    assert msg.body == b'{"id":1}'
    assert msg.key == "order-1"
    assert msg.partition == 2
    assert msg.offset == 42
    assert msg.timestamp == 1700000000.0


def test_record_to_message_str_body() -> None:
    """_record_to_message handles non-bytes body."""
    record = _FakeConsumerRecord(topic="t", body="body_str")
    msg = RocketMQClient._record_to_message(record)

    assert msg.body == b"body_str"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_create_mq_client_rocketmq() -> None:
    """create_mq_client returns a RocketMQClient for type=rocketmq."""
    client = create_mq_client(MQSettings(type=MQType.ROCKETMQ))
    assert isinstance(client, RocketMQClient)


def test_create_mq_client_kafka_still_works() -> None:
    """create_mq_client still returns KafkaClient for type=kafka."""
    from framework.clients.mq import KafkaClient

    client = create_mq_client(MQSettings(type=MQType.KAFKA))
    assert isinstance(client, KafkaClient)


def test_create_mq_client_rabbitmq_now_works() -> None:
    """create_mq_client now returns RabbitMQClient for type=rabbitmq."""
    client = create_mq_client(MQSettings(type=MQType.RABBITMQ))
    assert isinstance(client, RabbitMQClient)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_rocketmq_settings_defaults() -> None:
    """RocketMQSettings has sensible defaults."""
    settings = RocketMQSettings()
    assert settings.name_server == "localhost:9876"
    assert settings.group_name == "automation-platform"
    assert settings.send_msg_timeout_ms == 30000
    assert settings.producer_retry_times == 3


def test_mq_settings_has_rocketmq() -> None:
    """MQSettings includes a rocketmq field."""
    settings = MQSettings()
    assert isinstance(settings.rocketmq, RocketMQSettings)


def test_mq_settings_rocketmq_type() -> None:
    """MQSettings can be configured for rocketmq."""
    settings = MQSettings(type=MQType.ROCKETMQ)
    assert settings.type == MQType.ROCKETMQ
    assert isinstance(settings.rocketmq, RocketMQSettings)
