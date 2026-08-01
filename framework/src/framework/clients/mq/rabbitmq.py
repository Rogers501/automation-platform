"""RabbitMQ message-queue client built on aio-pika.

Implements the :class:`MessageClient` interface for RabbitMQ using
``aio_pika`` (natively async, no thread bridging needed).

The ``aio_pika`` package is imported lazily so the framework does not
hard-depend on it at import time; a missing package surfaces as a clear
:class:`MQError` on first use. Pass explicit ``connection`` / ``channel``
for isolation in tests (rule 14).

Usage::

    async with RabbitMQClient() as client:
        await client.publish("orders", b'{"id":1}', key="order-1")
        await client.consume("orders", process_order, group="workers")

Defaults come from :attr:`FrameworkSettings.mq.rabbitmq`; pass an explicit
:class:`MQSettings` for isolation in tests.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from loguru import logger

from framework.clients.mq.base import Message, MessageClient, MessageHandler, PublishResult
from framework.core.config import MQSettings, get_settings
from framework.core.exceptions import MQError

__all__ = ["RabbitMQClient"]


class RabbitMQClient(MessageClient):
    """Async RabbitMQ client implementing the unified :class:`MessageClient`.

    A single connection and channel are created lazily on first use.
    Use ``async with`` to guarantee cleanup.

    Args:
        settings: MQ settings; defaults to :func:`get_settings().mq`.
        connection: Pre-built aio-pika connection for testing.
        channel: Pre-built aio-pika channel for testing.
        name: Logical client name for log correlation.
    """

    def __init__(
        self,
        settings: MQSettings | None = None,
        *,
        connection: Any = None,
        channel: Any = None,
        name: str = "rabbitmq",
    ) -> None:
        self._settings = settings if settings is not None else get_settings().mq
        self._rmq = self._settings.rabbitmq
        self._injected_connection = connection
        self._injected_channel = channel
        self._connection: Any = connection
        self._channel: Any = channel
        self._consumers: list[Any] = []
        self._active_consumer: Any = None
        self._name = name
        self._logger = logger.bind(component="rabbitmq_client", client=name)
        self._closed = False

    # --- lifecycle -----------------------------------------------------

    async def _ensure_channel(self) -> Any:
        """Lazily build the connection and channel on first use."""
        if self._closed:
            raise MQError("RabbitMQClient is closed")
        if self._channel is not None:
            return self._channel

        try:
            import aio_pika
        except ImportError as exc:
            raise MQError(
                "aio-pika package is not installed; run 'uv sync' to install it",
                context={"error_type": type(exc).__name__},
            ) from exc

        if self._rmq.url:
            self._connection = await aio_pika.connect_robust(self._rmq.url)
        else:
            self._connection = await aio_pika.connect_robust(
                host=self._rmq.host,
                port=self._rmq.port,
                login=self._rmq.username,
                password=self._rmq.password,
                virtualhost=self._rmq.virtual_host,
                timeout=self._rmq.connection_timeout,
                heartbeat=self._rmq.heartbeat,
            )

        self._channel = await self._connection.channel()
        if self._rmq.prefetch_count:
            await self._channel.set_qos(prefetch_count=self._rmq.prefetch_count)
        self._logger.info("rabbitmq channel established: {}", self._rmq.host)
        return self._channel

    async def close(self) -> None:
        """Close the channel and connection."""
        self._closed = True
        if self._channel is not None:
            try:
                await self._channel.close()
            except Exception as exc:
                self._logger.warning("channel close error: {}", exc)
            self._channel = None
        if self._connection is not None:
            try:
                await self._connection.close()
            except Exception as exc:
                self._logger.warning("connection close error: {}", exc)
            self._connection = None
        self._active_consumer = None

    async def __aenter__(self) -> RabbitMQClient:
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
        """Publish a message to a RabbitMQ exchange/queue.

        ``topic`` is the exchange name; ``key`` is the routing key.
        If no exchange is configured, the default exchange is used and
        ``topic`` is treated as the queue name.
        """
        channel = await self._ensure_channel()
        body_bytes = body.encode("utf-8") if isinstance(body, str) else body
        routing_key = key or topic

        exchange_name = self._rmq.exchange or ""
        try:
            message = self._build_message(body_bytes, headers)

            if exchange_name:
                exchange = await channel.get_exchange(exchange_name, ensure=False)
                if exchange is None:
                    exchange = await channel.declare_exchange(
                        exchange_name,
                        self._get_exchange_type(),
                        durable=self._rmq.exchange_durable,
                    )
                await exchange.publish(message, routing_key=routing_key)
            else:
                await channel.default_exchange.publish(
                    message,
                    routing_key=routing_key,
                )
        except Exception as exc:
            raise self._wrap(
                exc,
                context={"op": "publish", "exchange": exchange_name, "routing_key": routing_key},
            ) from exc

        return PublishResult(topic=topic)

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
        """Consume messages from a RabbitMQ queue.

        ``topic`` is the queue name. ``group`` is unused (RabbitMQ uses
        queue-level consumer tags, not consumer groups).
        """
        if self._closed:
            raise MQError("RabbitMQClient is closed")
        channel = await self._ensure_channel()

        try:
            queue = await channel.declare_queue(
                topic,
                durable=self._rmq.queue_durable,
                auto_delete=self._rmq.queue_auto_delete,
            )
        except Exception as exc:
            raise self._wrap(
                exc,
                context={"op": "declare_queue", "queue": topic},
            ) from exc

        received: list[Message] = []
        consume_done = asyncio.Event()

        async def _process(message: Any) -> None:
            """Process a single message from the queue."""
            msg = self._amqp_to_message(message, topic)
            try:
                await handler(msg)
                if not auto_commit:
                    await message.ack()
            except Exception as exc:
                if not auto_commit:
                    await message.nack(requeue=False)
                if isinstance(exc, MQError):
                    raise
                raise self._wrap(
                    exc,
                    context={"op": "handler", "queue": topic},
                ) from exc
            finally:
                received.append(msg)
                if max_messages is not None and len(received) >= max_messages:
                    consume_done.set()

        consumer_tag = await queue.consume(_process, no_ack=auto_commit)
        self._consumers.append(queue)
        self._active_consumer = queue
        self._logger.info("consuming queue={} auto_ack={}", topic, auto_commit)

        try:
            if max_messages is not None:
                await asyncio.wait_for(consume_done.wait(), timeout=30.0)
        except TimeoutError:
            pass
        finally:
            import contextlib

            with contextlib.suppress(Exception):
                await queue.cancel(consumer_tag)
            self._active_consumer = None
            if queue in self._consumers:
                self._consumers.remove(queue)

    # --- commit ---------------------------------------------------------

    async def commit(self, message: Message | None = None) -> None:
        """Commit/acknowledge a message (manual ack mode).

        For RabbitMQ, this is handled per-message in the consume callback
        via ``message.ack()``. This method is a no-op for compatibility.
        """
        # RabbitMQ acks per-message in the consume callback; no-op here.
        self._logger.debug("commit requested (per-message ack for rabbitmq)")

    # --- internals ------------------------------------------------------

    @staticmethod
    def _amqp_to_message(message: Any, topic: str) -> Message:
        """Convert an aio-pika IncomingMessage into a :class:`Message`."""
        body = message.body if isinstance(message.body, bytes) else str(message.body).encode()
        headers: dict[str, str] = {}
        msg_headers = getattr(message, "headers", None)
        if msg_headers:
            for h_key, h_val in msg_headers.items():
                headers[str(h_key)] = str(h_val)
        return Message(
            topic=topic,
            body=body,
            headers=headers,
        )

    def _get_exchange_type(self) -> Any:
        """Get the aio-pika ExchangeType for the configured exchange type.

        Override in tests to avoid importing aio_pika.
        """
        import aio_pika

        return aio_pika.ExchangeType(self._rmq.exchange_type)

    def _build_message(self, body: bytes, headers: Mapping[str, str] | None) -> Any:
        """Construct an aio-pika Message (lazy import).

        Override in tests to inject a fake message builder.
        """
        import aio_pika

        return aio_pika.Message(
            body=body,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            if self._rmq.message_delivery_mode == 2
            else aio_pika.DeliveryMode.NOT_PERSISTENT,
            headers=dict(headers) if headers else None,
        )

    def _wrap(self, exc: Exception, *, context: Mapping[str, Any] | None = None) -> MQError:
        """Convert a broker-library error into an :class:`MQError`."""
        ctx: dict[str, Any] = dict(context or {})
        ctx.setdefault("error_type", type(exc).__name__)
        self._logger.warning("mq error: {}", exc)
        return MQError(str(exc), context=ctx)
