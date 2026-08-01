"""Unified message-queue client interface.

Defines the broker-agnostic :class:`MessageClient` abstract base class plus
the :class:`Message` and :class:`PublishResult` value objects shared by all
implementations (Kafka, RabbitMQ, RocketMQ).

The interface is intentionally minimal:

- :meth:`publish` -- fire-and-forget or confirmed send to a topic.
- :meth:`consume` -- callback-driven consumption with optional manual commit.
- :meth:`commit` -- acknowledge/commit a message (for ``auto_commit=False``).
- :meth:`close` -- release all producer/consumer resources.

New broker backends implement this interface; callers stay broker-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field

__all__ = ["Message", "MessageClient", "MessageHandler", "PublishResult"]


@dataclass(frozen=True)
class Message:
    """A message envelope exchanged via a message queue.

    Attributes:
        topic: The topic/queue the message belongs to.
        body: Raw message payload (always bytes internally).
        key: Optional partition/routing key (string form).
        headers: Optional message headers (string key/value pairs).
        partition: Broker partition number, when available.
        offset: Broker offset/sequence, when available.
        timestamp: Epoch-millis timestamp set by the broker, when available.
    """

    topic: str
    body: bytes
    key: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    partition: int | None = None
    offset: int | None = None
    timestamp: float | None = None


@dataclass(frozen=True)
class PublishResult:
    """Result metadata returned by :meth:`MessageClient.publish`.

    Attributes:
        topic: The topic the message was published to.
        partition: The broker-assigned partition, when available.
        offset: The broker-assigned offset/sequence, when available.
    """

    topic: str
    partition: int | None = None
    offset: int | None = None


#: Handler invoked by :meth:`MessageClient.consume` for each message.
MessageHandler = Callable[[Message], Awaitable[None]]


class MessageClient(ABC):
    """Unified async message-queue client interface.

    Implementations:

    - :class:`framework.clients.mq.KafkaClient` -- aiokafka (Phase 1).
    - RabbitMQClient -- aio-pika (future, same interface).
    - RocketMQClient -- future, same interface.

    Use ``async with`` to guarantee producer/consumer cleanup.
    """

    @abstractmethod
    async def publish(
        self,
        topic: str,
        body: bytes | str,
        *,
        key: str | None = None,
        headers: Mapping[str, str] | None = None,
        partition: int | None = None,
    ) -> PublishResult:
        """Publish a message to a topic.

        Args:
            topic: Target topic name.
            body: Message payload (str is UTF-8 encoded).
            key: Optional partition/routing key.
            headers: Optional message headers.
            partition: Target partition (broker-specific; ``None`` = auto).

        Returns:
            :class:`PublishResult` with broker-assigned metadata.
        """

    @abstractmethod
    async def consume(
        self,
        topic: str,
        handler: MessageHandler,
        *,
        group: str = "",
        auto_commit: bool = True,
        max_messages: int | None = None,
    ) -> None:
        """Consume messages from a topic, invoking ``handler`` for each.

        Blocks until ``max_messages`` is reached, the client is closed, or the
        consumer is exhausted. When ``auto_commit`` is ``False``, the handler
        should call :meth:`commit` to acknowledge processed messages.

        Args:
            topic: Source topic name.
            handler: Async callable invoked with each :class:`Message`.
            group: Consumer group name (broker-specific default if empty).
            auto_commit: Whether the broker auto-commits offsets/acks.
            max_messages: Stop after this many messages (``None`` = unlimited).
        """

    @abstractmethod
    async def commit(self, message: Message | None = None) -> None:
        """Acknowledge/commit a message or the current consumption position.

        Only meaningful when ``auto_commit=False``. When ``message`` is
        ``None``, commits all pending offsets/acks for the active consumer.

        Args:
            message: Specific message to commit (broker-dependent semantics).
        """

    @abstractmethod
    async def close(self) -> None:
        """Close all producer and consumer connections."""

    async def __aenter__(self) -> MessageClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
