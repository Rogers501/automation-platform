"""Message-queue capability client (async, unified interface).

Public API: ``MessageClient`` ABC, ``KafkaClient`` (aiokafka),
``RocketMQClient`` (rocketmq-client-python), ``Message``, ``PublishResult``,
and the ``create_mq_client`` factory.
"""

from framework.clients.mq.base import Message, MessageClient, MessageHandler, PublishResult
from framework.clients.mq.kafka import KafkaClient
from framework.clients.mq.rabbitmq import RabbitMQClient
from framework.clients.mq.rocketmq import RocketMQClient
from framework.core.config import KafkaSettings, MQSettings, MQType, RabbitMQSettings, get_settings
from framework.core.exceptions import MQError

__all__ = [
    "KafkaClient",
    "KafkaSettings",
    "MQError",
    "MQSettings",
    "MQType",
    "Message",
    "MessageClient",
    "MessageHandler",
    "PublishResult",
    "RabbitMQClient",
    "RabbitMQSettings",
    "RocketMQClient",
    "create_mq_client",
]


def create_mq_client(settings: MQSettings | None = None) -> MessageClient:
    """Create a message-queue client for the configured broker type.

    Args:
        settings: MQ settings; defaults to :func:`get_settings().mq`.

    Returns:
        A :class:`MessageClient` implementation for the configured type.

    Raises:
        MQError: If the configured ``type`` has no implementation yet.
    """
    resolved = settings if settings is not None else get_settings().mq
    if resolved.type == MQType.KAFKA:
        return KafkaClient(resolved)
    if resolved.type == MQType.ROCKETMQ:
        return RocketMQClient(resolved)
    if resolved.type == MQType.RABBITMQ:
        return RabbitMQClient(resolved)
    raise MQError(
        f"MQ type not yet implemented: {resolved.type}",
        context={
            "type": str(resolved.type),
            "valid": [MQType.KAFKA.value, MQType.ROCKETMQ.value, MQType.RABBITMQ.value],
        },
    )
