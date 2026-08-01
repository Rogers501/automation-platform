"""Unit tests for KafkaClient using injected fakes (no real Kafka, rule 14)."""

from __future__ import annotations

from typing import Any

import pytest

from framework.clients.mq import create_mq_client
from framework.clients.mq.base import Message, PublishResult
from framework.clients.mq.kafka import KafkaClient
from framework.core.config import KafkaSettings, MQSettings, MQType
from framework.core.exceptions import MQError

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeRecordMetadata:
    """Stand-in for aiokafka.structs.RecordMetadata."""

    def __init__(self, topic: str, partition: int, offset: int) -> None:
        self.topic = topic
        self.partition = partition
        self.offset = offset


class _FakeConsumerRecord:
    """Stand-in for aiokafka's ConsumerRecord."""

    def __init__(
        self,
        topic: str,
        value: bytes,
        *,
        key: bytes | None = None,
        headers: list[tuple[str, bytes]] | None = None,
        partition: int = 0,
        offset: int = 0,
        timestamp: float = 0.0,
    ) -> None:
        self.topic = topic
        self.value = value
        self.key = key
        self.headers = headers
        self.partition = partition
        self.offset = offset
        self.timestamp = timestamp


class _FakeProducer:
    """Fake aiokafka AIOKafkaProducer."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, bytes | None, list[tuple[str, bytes]] | None]] = []
        self.started = False
        self.stopped = False
        self._raises: Exception | None = None

    def will_raise(self, exc: Exception) -> None:
        self._raises = exc

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def send_and_wait(
        self,
        topic: str,
        value: bytes,
        *,
        key: bytes | None = None,
        headers: list[tuple[str, bytes]] | None = None,
        partition: int | None = None,
    ) -> _FakeRecordMetadata:
        if self._raises is not None:
            raise self._raises
        self.sent.append((topic, value, key, headers))
        return _FakeRecordMetadata(topic=topic, partition=partition or 0, offset=len(self.sent) - 1)


class _FakeConsumer:
    """Fake aiokafka AIOKafkaConsumer (async iterator)."""

    def __init__(
        self,
        records: list[_FakeConsumerRecord],
        *,
        raises_on_start: Exception | None = None,
    ) -> None:
        self._records = list(records)
        self._raises_on_start = raises_on_start
        self.started = False
        self.stopped = False
        self.commit_count = 0

    async def start(self) -> None:
        if self._raises_on_start is not None:
            raise self._raises_on_start
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def commit(self) -> None:
        self.commit_count += 1

    def __aiter__(self) -> _FakeConsumer:
        return self

    async def __anext__(self) -> _FakeConsumerRecord:
        if not self._records:
            raise StopAsyncIteration
        return self._records.pop(0)


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
) -> KafkaClient:
    """Build a KafkaClient wired to fakes."""
    return KafkaClient(
        settings=MQSettings(),
        producer=producer,
        consumer_factory=consumer_factory,
    )


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
    assert producer.sent[0][0] == "orders"
    assert producer.sent[0][1] == b'{"id":1}'


async def test_publish_encodes_str_body() -> None:
    """A str body is UTF-8 encoded before sending."""
    producer = _FakeProducer()
    client = _client(producer=producer)

    await client.publish("topic", "hello")

    assert producer.sent[0][1] == b"hello"


async def test_publish_with_key_and_headers() -> None:
    """publish encodes key and headers into Kafka wire format."""
    producer = _FakeProducer()
    client = _client(producer=producer)

    await client.publish("topic", b"data", key="order-1", headers={"type": "created"})

    _, _, key, headers = producer.sent[0]
    assert key == b"order-1"
    assert headers == [("type", b"created")]


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
        _FakeConsumerRecord(topic="t", value=b"msg1"),
        _FakeConsumerRecord(topic="t", value=b"msg2"),
    ]
    received: list[Message] = []

    async def handler(msg: Message) -> None:
        received.append(msg)

    client = _client(consumer_factory=_consumer_factory(records))
    await client.consume("t", handler, max_messages=2)

    assert len(received) == 2
    assert received[0].body == b"msg1"
    assert received[1].body == b"msg2"


async def test_consume_stops_at_max_messages() -> None:
    """consume stops after max_messages even if more are available."""
    records = [
        _FakeConsumerRecord(topic="t", value=b"m1"),
        _FakeConsumerRecord(topic="t", value=b"m2"),
        _FakeConsumerRecord(topic="t", value=b"m3"),
    ]
    received: list[Message] = []

    async def handler(msg: Message) -> None:
        received.append(msg)

    client = _client(consumer_factory=_consumer_factory(records))
    await client.consume("t", handler, max_messages=2)

    assert len(received) == 2


async def test_consume_empty_topic() -> None:
    """consume with no messages completes without calling the handler."""
    received: list[Message] = []

    async def handler(msg: Message) -> None:
        received.append(msg)

    client = _client(consumer_factory=_consumer_factory([]))
    await client.consume("t", handler, max_messages=5)

    assert received == []


async def test_consume_handler_error_wrapped() -> None:
    """An error in the handler surfaces as MQError."""
    records = [_FakeConsumerRecord(topic="t", value=b"m1")]

    async def handler(msg: Message) -> None:
        raise ValueError("bad handler")

    client = _client(consumer_factory=_consumer_factory(records))

    with pytest.raises(MQError) as info:
        await client.consume("t", handler, max_messages=1)

    assert "bad handler" in str(info.value)
    assert info.value.context["op"] == "handler"


async def test_consume_start_error_wrapped() -> None:
    """A consumer.start() error surfaces as MQError."""

    def factory(topic: str, **kw: Any) -> _FakeConsumer:
        return _FakeConsumer([], raises_on_start=ConnectionError("no broker"))

    client = _client(consumer_factory=factory)

    with pytest.raises(MQError) as info:
        await client.consume("t", _noop, max_messages=1)

    assert "no broker" in str(info.value)
    assert info.value.context["op"] == "consume_start"


async def test_consume_stops_consumer() -> None:
    """consume stops the consumer on completion."""
    records = [_FakeConsumerRecord(topic="t", value=b"m1")]
    consumer = _FakeConsumer(records)
    client = _client(consumer_factory=lambda *a, **kw: consumer)

    await client.consume("t", _noop, max_messages=1)

    assert consumer.started
    assert consumer.stopped


# ---------------------------------------------------------------------------
# Commit
# ---------------------------------------------------------------------------


async def test_commit_during_consume() -> None:
    """commit during consume delegates to the active consumer."""
    records = [_FakeConsumerRecord(topic="t", value=b"m1")]
    consumer = _FakeConsumer(records)
    client = _client(consumer_factory=lambda *a, **kw: consumer)

    async def handler(msg: Message) -> None:
        await client.commit(msg)

    await client.consume("t", handler, auto_commit=False, max_messages=1)

    assert consumer.commit_count == 1


async def test_commit_without_consumer_raises() -> None:
    """commit outside consume raises MQError."""
    client = _client()

    with pytest.raises(MQError) as info:
        await client.commit()

    assert "No active consumer" in str(info.value)


# ---------------------------------------------------------------------------
# Close / lifecycle
# ---------------------------------------------------------------------------


async def test_close_stops_producer() -> None:
    """close stops the producer."""
    producer = _FakeProducer()
    client = _client(producer=producer)
    await client.publish("t", b"data")
    await client.close()

    assert producer.stopped
    assert client.is_closed


async def test_close_stops_active_consumers() -> None:
    """close stops any active consumers."""
    records = [_FakeConsumerRecord(topic="t", value=b"m1")]
    consumer = _FakeConsumer(records)
    client = _client(consumer_factory=lambda *a, **kw: consumer)

    await client.consume("t", _noop, max_messages=1)
    await client.close()

    assert consumer.stopped


async def test_async_context_manager_closes() -> None:
    """async with closes the client on exit."""
    producer = _FakeProducer()
    async with _client(producer=producer) as client:
        await client.publish("t", b"data")
    assert client.is_closed
    assert producer.stopped


# ---------------------------------------------------------------------------
# _record_to_message
# ---------------------------------------------------------------------------


def test_record_to_message_full() -> None:
    """_record_to_message converts all fields from a ConsumerRecord."""
    record = _FakeConsumerRecord(
        topic="orders",
        value=b'{"id":1}',
        key=b"order-1",
        headers=[("type", b"created")],
        partition=2,
        offset=42,
        timestamp=1700000000.0,
    )
    msg = KafkaClient._record_to_message(record)

    assert msg.topic == "orders"
    assert msg.body == b'{"id":1}'
    assert msg.key == "order-1"
    assert msg.headers == {"type": "created"}
    assert msg.partition == 2
    assert msg.offset == 42
    assert msg.timestamp == 1700000000.0


def test_record_to_message_str_values() -> None:
    """_record_to_message handles non-bytes key/value/headers."""
    record = _FakeConsumerRecord(
        topic="t",
        value="body_str",
        key="key_str",
        headers=[("h1", "v1_str")],
    )
    msg = KafkaClient._record_to_message(record)

    assert msg.body == b"body_str"
    assert msg.key == "key_str"
    assert msg.headers == {"h1": "v1_str"}


def test_record_to_message_defaults() -> None:
    """_record_to_message defaults key/headers when absent."""
    record = _FakeConsumerRecord(topic="t", value=b"body")
    msg = KafkaClient._record_to_message(record)

    assert msg.key is None
    assert msg.headers == {}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_create_mq_client_kafka() -> None:
    """create_mq_client returns a KafkaClient for type=kafka."""
    client = create_mq_client(MQSettings(type=MQType.KAFKA))
    assert isinstance(client, KafkaClient)


def test_create_mq_client_unsupported_raises() -> None:
    """create_mq_client raises MQError for unimplemented types."""
    settings = MQSettings(type=MQType.KAFKA)
    settings.type = "pulsar"
    with pytest.raises(MQError) as info:
        create_mq_client(settings)

    assert "not yet implemented" in str(info.value)
    assert info.value.context["type"] == "pulsar"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_kafka_settings_defaults() -> None:
    """KafkaSettings has sensible defaults."""
    settings = KafkaSettings()
    assert settings.bootstrap_servers == ["localhost:9092"]
    assert settings.client_id == "automation-platform"
    assert settings.producer_acks == "1"
    assert settings.auto_offset_reset == "latest"
    assert settings.enable_auto_commit is True


def test_mq_settings_defaults() -> None:
    """MQSettings defaults to kafka type."""
    settings = MQSettings()
    assert settings.type == MQType.KAFKA
    assert isinstance(settings.kafka, KafkaSettings)


def test_mq_type_values() -> None:
    """MQType exposes kafka, rabbitmq, rocketmq."""
    assert MQType.KAFKA.value == "kafka"
    assert MQType.RABBITMQ.value == "rabbitmq"
    assert MQType.ROCKETMQ.value == "rocketmq"
