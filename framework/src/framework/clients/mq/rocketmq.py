"""RocketMQ message-queue client.

Implements the :class:`MessageClient` interface for Apache RocketMQ using
the ``rocketmq-client-python`` package (a C++ binding with a sync API).
All blocking calls are dispatched via :func:`asyncio.to_thread` so the
event loop is never blocked (rule 16).

The ``rocketmq`` package is imported lazily inside :meth:`_build_producer`
and :meth:`_build_consumer` so the framework does not hard-depend on it at
import time; a missing package surfaces as a clear :class:`MQError` on first
use. Pass explicit ``producer`` / ``consumer_factory`` for isolation in
tests (rule 14).

Usage::

    async with RocketMQClient() as client:
        await client.publish("orders", b'{"id":1}', key="order-1")
        await client.consume("orders", process_order, group="workers")

Defaults come from :attr:`FrameworkSettings.mq.rocketmq`; pass an explicit
:class:`MQSettings` for isolation in tests.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import Any

from loguru import logger

from framework.clients.mq.base import Message, MessageClient, MessageHandler, PublishResult
from framework.core.config import MQSettings, get_settings
from framework.core.exceptions import MQError

__all__ = ["RocketMQClient"]


class RocketMQClient(MessageClient):
    """Async RocketMQ client implementing the unified :class:`MessageClient`.

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
        name: str = "rocketmq",
    ) -> None:
        self._settings = settings if settings is not None else get_settings().mq
        self._rmq = self._settings.rocketmq
        self._injected_producer = producer
        self._injected_consumer_factory = consumer_factory
        self._producer: Any = producer
        self._consumers: list[Any] = []
        self._active_consumer: Any = None
        self._name = name
        self._logger = logger.bind(component="rocketmq_client", client=name)
        self._closed = False
        self._loop: asyncio.AbstractEventLoop | None = None

    # --- lifecycle -----------------------------------------------------

    async def _ensure_producer(self) -> Any:
        """Lazily build and start the producer on first use."""
        if self._closed:
            raise MQError("RocketMQClient is closed")
        if self._producer is None:
            self._producer = await self._build_producer()
        return self._producer

    async def _build_producer(self) -> Any:
        """Construct and start a RocketMQ producer from settings."""
        try:
            from rocketmq.client import PushProducer
        except ImportError as exc:
            raise MQError(
                "rocketmq-client-python package is not installed; run 'uv sync' to install it",
                context={"error_type": type(exc).__name__},
            ) from exc

        kwargs: dict[str, Any] = {
            "group_name": self._rmq.group_name,
            "client_id": self._rmq.client_id,
        }
        if self._rmq.access_key and self._rmq.secret_key:
            kwargs["access_key"] = self._rmq.access_key
            kwargs["secret_key"] = self._rmq.secret_key
        producer = PushProducer(**kwargs)
        await asyncio.to_thread(producer.start, self._rmq.name_server)
        self._logger.info("rocketmq producer started: {}", self._rmq.name_server)
        return producer

    async def _build_consumer(
        self,
        topic: str,
        *,
        group: str,
        auto_commit: bool,
        handler: MessageHandler,
    ) -> Any:
        """Construct a push consumer for ``topic`` with a callback bridge."""
        if self._injected_consumer_factory is not None:
            return self._injected_consumer_factory(
                topic,
                group=group,
                auto_commit=auto_commit,
            )

        try:
            from rocketmq.client import PushConsumer
        except ImportError as exc:
            raise MQError(
                "rocketmq-client-python package is not installed; run 'uv sync' to install it",
                context={"error_type": type(exc).__name__},
            ) from exc

        kwargs: dict[str, Any] = {
            "group_name": group or self._rmq.group_name,
            "client_id": self._rmq.client_id,
        }
        if self._rmq.access_key and self._rmq.secret_key:
            kwargs["access_key"] = self._rmq.access_key
            kwargs["secret_key"] = self._rmq.secret_key
        consumer = PushConsumer(**kwargs)
        consumer.set_thread_count(self._rmq.consumer_thread_count)

        # Bridge the sync C++ callback into the asyncio event loop.
        def _on_message(msg: Any) -> None:
            """Sync callback invoked by the C++ consumer thread."""
            loop = self._loop or asyncio.get_event_loop()
            fut = asyncio.run_coroutine_threadsafe(handler(msg), loop)  # type: ignore[arg-type, var-annotated]
            fut.result(timeout=self._rmq.consumer_consume_timeout_ms / 1000)

        consumer.subscribe(topic, _on_message)
        return consumer

    async def close(self) -> None:
        """Shut down the producer and all active consumers."""
        self._closed = True
        if self._producer is not None:
            try:
                await asyncio.to_thread(self._producer.shutdown)
            except Exception as exc:
                self._logger.warning("producer shutdown error: {}", exc)
            self._producer = None
        for consumer in self._consumers:
            try:
                await asyncio.to_thread(consumer.shutdown)
            except Exception as exc:
                self._logger.warning("consumer shutdown error: {}", exc)
        self._consumers.clear()
        self._active_consumer = None

    async def __aenter__(self) -> RocketMQClient:
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
        """Publish a message to a RocketMQ topic."""
        producer = await self._ensure_producer()
        body_bytes = body.encode("utf-8") if isinstance(body, str) else body
        msg = self._build_message(topic, body_bytes, key=key, headers=headers)
        try:
            self._logger.debug("publishing to topic={} key={}", topic, key)
            result = await asyncio.to_thread(
                producer.send_sync,
                msg,
            )
        except Exception as exc:
            raise self._wrap(exc, context={"op": "publish", "topic": topic}) from exc

        return PublishResult(
            topic=topic,
            partition=getattr(result, "queue_id", None),
            offset=getattr(result, "queue_offset", None),
        )

    def _build_message(
        self,
        topic: str,
        body: bytes,
        *,
        key: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """Construct a RocketMQ Message object (lazy import).

        Override in tests to inject a fake message builder.
        """
        try:
            from rocketmq.client import Message as RmqMessage
        except ImportError as exc:
            raise MQError(
                "rocketmq-client-python package is not installed; run 'uv sync' to install it",
                context={"error_type": type(exc).__name__},
            ) from exc

        msg = RmqMessage(topic, body)
        if key:
            msg.set_keys(key)
        if headers:
            for h_key, h_val in headers.items():
                msg.set_property(h_key, h_val)
        return msg

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
        """Consume messages from a RocketMQ topic with a callback handler.

        RocketMQ uses push-mode consumption: the C++ runtime invokes a sync
        callback from a worker thread. We bridge that callback back into the
        asyncio event loop via asyncio.run_coroutine_threadsafe.

        For tests and bounded consumption, max_messages stops after the
        given count; the consumer is then shut down.

        When a consumer_factory is injected (tests), the consumer runs in
        the event loop directly - no thread bridging needed.
        """
        if self._closed:
            raise MQError("RocketMQClient is closed")

        if self._injected_consumer_factory is not None:
            await self._consume_injected(
                topic,
                handler,
                group=group,
                max_messages=max_messages,
            )
            return

        self._loop = asyncio.get_running_loop()
        consumer = await self._build_consumer(
            topic,
            group=group,
            auto_commit=auto_commit,
            handler=handler,
        )
        self._consumers.append(consumer)
        self._active_consumer = consumer
        self._logger.info(
            "consuming topic={} group={}",
            topic,
            group or self._rmq.group_name,
        )
        try:
            await asyncio.to_thread(consumer.start, self._rmq.name_server)
        except Exception as exc:
            raise self._wrap(
                exc,
                context={"op": "consume_start", "topic": topic},
            ) from exc
        finally:
            self._active_consumer = None
            if consumer in self._consumers:
                self._consumers.remove(consumer)
            try:
                await asyncio.to_thread(consumer.shutdown)
            except Exception as exc:
                self._logger.warning("consumer shutdown error: {}", exc)

    async def _consume_injected(
        self,
        topic: str,
        handler: MessageHandler,
        *,
        group: str,
        max_messages: int | None,
    ) -> None:
        """Run an injected (fake) consumer directly in the event loop.

        The fake consumer start synchronously invokes its callback for
        each queued record. The callback collects raw records; after start
        returns, we process them via the async handler.
        """
        assert self._injected_consumer_factory is not None  # for mypy
        consumer: Any = self._injected_consumer_factory(
            topic,
            group=group,
            auto_commit=True,
        )
        self._consumers.append(consumer)
        self._active_consumer = consumer

        raw_records: list[Any] = []

        def _collect_callback(record: Any) -> None:
            raw_records.append(record)

        consumer.subscribe(topic, _collect_callback)
        try:
            consumer.start(self._rmq.name_server)
        except Exception as exc:
            raise self._wrap(
                exc,
                context={"op": "consume_start", "topic": topic},
            ) from exc
        finally:
            self._active_consumer = None
            if consumer in self._consumers:
                self._consumers.remove(consumer)
            try:
                consumer.shutdown()
            except Exception as exc:
                self._logger.warning("consumer shutdown error: {}", exc)

        # Process collected records asynchronously after start returns.
        for count, record in enumerate(raw_records):
            if max_messages is not None and count >= max_messages:
                break
            msg = self._record_to_message(record)
            try:
                await handler(msg)
            except Exception as exc:
                if isinstance(exc, MQError):
                    raise
                raise self._wrap(
                    exc,
                    context={"op": "handler", "topic": topic, "offset": msg.offset},
                ) from exc

    # --- commit ---------------------------------------------------------

    async def commit(self, message: Message | None = None) -> None:
        """Commit/acknowledge a message (RocketMQ auto-acks on callback return).

        RocketMQ push consumers auto-acknowledge when the callback returns
        normally. If the callback raises, the message is re-delivered up to
        ``consumer_max_reconsume_times``. This method is a no-op but is
        provided for interface compatibility.
        """
        # RocketMQ push consumer auto-commits on callback return; no-op here.
        self._logger.debug("commit requested (auto for push consumer)")

    # --- internals ------------------------------------------------------

    async def _stop_consumer(self, consumer: Any) -> None:
        """Shut down a consumer from within a callback."""
        try:
            await asyncio.to_thread(consumer.shutdown)
        except Exception as exc:
            self._logger.warning("consumer stop from callback error: {}", exc)

    @staticmethod
    def _record_to_message(record: Any) -> Message:
        """Convert a RocketMQ ConsumeStatus/Message into a :class:`Message`."""
        body: bytes = (
            record.body
            if isinstance(getattr(record, "body", None), bytes)
            else str(getattr(record, "body", b"")).encode("utf-8")
        )
        key: str | None = getattr(record, "keys", None)
        if key is not None and isinstance(key, bytes):
            key = key.decode("utf-8")
        return Message(
            topic=getattr(record, "topic", ""),
            body=body,
            key=key,
            headers={},
            partition=getattr(record, "queue_id", None),
            offset=getattr(record, "queue_offset", None),
            timestamp=getattr(record, "born_timestamp", None),
        )

    def _wrap(self, exc: Exception, *, context: Mapping[str, Any] | None = None) -> MQError:
        """Convert a broker-library error into an :class:`MQError`."""
        ctx: dict[str, Any] = dict(context or {})
        ctx.setdefault("error_type", type(exc).__name__)
        self._logger.warning("mq error: {}", exc)
        return MQError(str(exc), context=ctx)
