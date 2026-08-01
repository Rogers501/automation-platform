"""Kafka message-queue client built on aiokafka.

Implements the :class:`MessageClient` interface for Apache Kafka using
``aiokafka.AIOKafkaProducer`` and ``aiokafka.AIOKafkaConsumer``.

The ``aiokafka`` package is imported lazily inside :meth:`_build_producer`
and :meth:`_build_consumer` so the framework does not hard-depend on it at
import time; a missing package surfaces as a clear :class:`MQError` on first
use. Pass explicit ``producer`` / ``consumer_factory`` for isolation in
tests (rule 14).

Usage::

    async with KafkaClient() as client:
        await client.publish("orders", b'{"id":1}', key="order-1")
        await client.consume("orders", process_order, group="workers")

Defaults come from :attr:`FrameworkSettings.mq.kafka`; pass an explicit
:class:`MQSettings` for isolation in tests.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from loguru import logger

from framework.clients.mq.base import Message, MessageClient, MessageHandler, PublishResult
from framework.core.config import MQSettings, get_settings
from framework.core.exceptions import MQError

__all__ = ["KafkaClient"]


class KafkaClient(MessageClient):
    """Async Kafka client implementing the unified :class:`MessageClient`.

    The producer is created lazily on first :meth:`publish`; consumers are
    created per :meth:`consume` call. Use ``async with`` to guarantee all
    connections are closed.

    Args:
        settings: MQ settings; defaults to :func:`get_settings().mq`.
        producer: Pre-built producer for testing (bypasses lazy import).
        consumer_factory: Callable returning a consumer for testing.
        name: Logical client name for log correlation.
    """

    def __init__(
        self,
        settings: MQSettings | None = None,
        *,
        producer: Any = None,
        consumer_factory: Callable[..., Any] | None = None,
        name: str = "kafka",
    ) -> None:
        self._settings = settings if settings is not None else get_settings().mq
        self._kafka = self._settings.kafka
        self._injected_producer = producer
        self._injected_consumer_factory = consumer_factory
        self._producer: Any = producer
        self._consumers: list[Any] = []
        self._active_consumer: Any = None
        self._name = name
        self._logger = logger.bind(component="kafka_client", client=name)
        self._closed = False

    # --- lifecycle -----------------------------------------------------

    async def _ensure_producer(self) -> Any:
        """Lazily build and start the producer on first use."""
        if self._closed:
            raise MQError("KafkaClient is closed")
        if self._producer is None:
            self._producer = await self._build_producer()
        return self._producer

    async def _build_producer(self) -> Any:
        """Construct and start an ``AIOKafkaProducer`` from settings."""
        try:
            from aiokafka import AIOKafkaProducer
        except ImportError as exc:
            raise MQError(
                "aiokafka package is not installed; run 'uv sync' to install it",
                context={"error_type": type(exc).__name__},
            ) from exc

        kwargs: dict[str, Any] = {
            "bootstrap_servers": self._kafka.bootstrap_servers,
            "client_id": self._kafka.client_id,
            "acks": self._kafka.producer_acks,
            "linger_ms": self._kafka.producer_linger_ms,
            "request_timeout_ms": self._kafka.request_timeout_ms,
            "api_version": self._kafka.api_version,
            "security_protocol": self._kafka.security_protocol,
        }
        if self._kafka.sasl_mechanism:
            kwargs["sasl_mechanism"] = self._kafka.sasl_mechanism
        if self._kafka.sasl_username:
            kwargs["sasl_plain_username"] = self._kafka.sasl_username
            kwargs["sasl_plain_password"] = self._kafka.sasl_password
        if self._kafka.ssl_ca_location:
            kwargs["ssl_cafile"] = self._kafka.ssl_ca_location
        producer = AIOKafkaProducer(**kwargs)
        await producer.start()
        self._logger.info("kafka producer started: {}", self._kafka.bootstrap_servers)
        return producer

    async def _build_consumer(self, topic: str, *, group: str, auto_commit: bool) -> Any:
        """Construct a consumer for ``topic`` (injected factory or aiokafka)."""
        if self._injected_consumer_factory is not None:
            return self._injected_consumer_factory(topic, group=group, auto_commit=auto_commit)
        try:
            from aiokafka import AIOKafkaConsumer
        except ImportError as exc:
            raise MQError(
                "aiokafka package is not installed; run 'uv sync' to install it",
                context={"error_type": type(exc).__name__},
            ) from exc

        kwargs: dict[str, Any] = {
            "bootstrap_servers": self._kafka.bootstrap_servers,
            "client_id": self._kafka.client_id,
            "group_id": group or self._kafka.group_id,
            "auto_offset_reset": self._kafka.auto_offset_reset,
            "enable_auto_commit": auto_commit,
            "auto_commit_interval_ms": self._kafka.auto_commit_interval_ms,
            "request_timeout_ms": self._kafka.request_timeout_ms,
            "api_version": self._kafka.api_version,
            "security_protocol": self._kafka.security_protocol,
            "fetch_min_bytes": self._kafka.consumer_fetch_min_bytes,
            "fetch_max_wait_ms": self._kafka.consumer_fetch_max_wait_ms,
        }
        if self._kafka.sasl_mechanism:
            kwargs["sasl_mechanism"] = self._kafka.sasl_mechanism
        if self._kafka.sasl_username:
            kwargs["sasl_plain_username"] = self._kafka.sasl_username
            kwargs["sasl_plain_password"] = self._kafka.sasl_password
        if self._kafka.ssl_ca_location:
            kwargs["ssl_cafile"] = self._kafka.ssl_ca_location
        return AIOKafkaConsumer(topic, **kwargs)

    async def close(self) -> None:
        """Stop the producer and all active consumers."""
        self._closed = True
        if self._producer is not None:
            try:
                await self._producer.stop()
            except Exception as exc:
                self._logger.warning("producer stop error: {}", exc)
            self._producer = None
        for consumer in self._consumers:
            try:
                await consumer.stop()
            except Exception as exc:
                self._logger.warning("consumer stop error: {}", exc)
        self._consumers.clear()
        self._active_consumer = None

    async def __aenter__(self) -> KafkaClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    @property
    def is_closed(self) -> bool:
        """Whether the client has been closed."""
        return self._closed

    # --- publish --------------------------------------------------------

    async def publish(
        self,
        topic: str,
        body: bytes | str,
        *,
        key: str | None = None,
        headers: Mapping[str, str] | None = None,
        partition: int | None = None,
    ) -> PublishResult:
        """Publish a message to a Kafka topic."""
        producer = await self._ensure_producer()
        body_bytes = body.encode("utf-8") if isinstance(body, str) else body
        key_bytes = key.encode("utf-8") if isinstance(key, str) and key else None
        kafka_headers: list[tuple[str, bytes]] | None = None
        if headers:
            kafka_headers = [(k, v.encode("utf-8")) for k, v in headers.items()]
        try:
            self._logger.debug("publishing to topic={} key={}", topic, key)
            metadata = await producer.send_and_wait(
                topic,
                body_bytes,
                key=key_bytes,
                headers=kafka_headers,
                partition=partition,
            )
        except Exception as exc:
            raise self._wrap(exc, context={"op": "publish", "topic": topic}) from exc
        return PublishResult(
            topic=topic,
            partition=getattr(metadata, "partition", None),
            offset=getattr(metadata, "offset", None),
        )

    # --- consume --------------------------------------------------------

    async def consume(
        self,
        topic: str,
        handler: MessageHandler,
        *,
        group: str = "",
        auto_commit: bool = True,
        max_messages: int | None = None,
    ) -> None:
        """Consume messages from a Kafka topic with a callback handler."""
        if self._closed:
            raise MQError("KafkaClient is closed")
        consumer = await self._build_consumer(topic, group=group, auto_commit=auto_commit)
        try:
            await consumer.start()
        except Exception as exc:
            raise self._wrap(exc, context={"op": "consume_start", "topic": topic}) from exc

        self._consumers.append(consumer)
        self._active_consumer = consumer
        self._logger.info("consuming topic={} group={}", topic, group or self._kafka.group_id)
        try:
            count = 0
            async for record in consumer:
                msg = self._record_to_message(record)
                try:
                    await handler(msg)
                except Exception as exc:
                    if isinstance(exc, MQError):
                        raise
                    raise self._wrap(
                        exc, context={"op": "handler", "topic": topic, "offset": msg.offset}
                    ) from exc
                count += 1
                if max_messages is not None and count >= max_messages:
                    break
        except Exception as exc:
            if isinstance(exc, MQError):
                raise
            raise self._wrap(exc, context={"op": "consume", "topic": topic}) from exc
        finally:
            self._active_consumer = None
            if consumer in self._consumers:
                self._consumers.remove(consumer)
            try:
                await consumer.stop()
            except Exception as exc:
                self._logger.warning("consumer stop error: {}", exc)

    # --- commit ---------------------------------------------------------

    async def commit(self, message: Message | None = None) -> None:
        """Commit offsets for the active consumer (manual commit mode)."""
        consumer = self._active_consumer
        if consumer is None:
            raise MQError(
                "No active consumer; commit must be called during consume()",
                context={"op": "commit"},
            )
        try:
            await consumer.commit()
        except Exception as exc:
            raise self._wrap(
                exc,
                context={"op": "commit", "topic": message.topic if message else None},
            ) from exc

    # --- internals ------------------------------------------------------

    @staticmethod
    def _record_to_message(record: Any) -> Message:
        """Convert an aiokafka ConsumerRecord into a :class:`Message`."""
        headers: dict[str, str] = {}
        record_headers = getattr(record, "headers", None)
        if record_headers:
            for h_key, h_val in record_headers:
                headers[h_key] = h_val.decode("utf-8") if isinstance(h_val, bytes) else str(h_val)
        key: str | None = None
        record_key = getattr(record, "key", None)
        if record_key is not None:
            key = record_key.decode("utf-8") if isinstance(record_key, bytes) else str(record_key)
        body: bytes = (
            record.value if isinstance(record.value, bytes) else str(record.value).encode("utf-8")
        )
        return Message(
            topic=record.topic,
            body=body,
            key=key,
            headers=headers,
            partition=getattr(record, "partition", None),
            offset=getattr(record, "offset", None),
            timestamp=getattr(record, "timestamp", None),
        )

    def _wrap(self, exc: Exception, *, context: Mapping[str, Any] | None = None) -> MQError:
        """Convert a broker-library error into an :class:`MQError`."""
        ctx: dict[str, Any] = dict(context or {})
        ctx.setdefault("error_type", type(exc).__name__)
        self._logger.warning("mq error: {}", exc)
        return MQError(str(exc), context=ctx)
