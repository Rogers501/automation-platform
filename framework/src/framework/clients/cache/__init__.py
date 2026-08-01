"""Redis cache capability client (async, redis.asyncio).

Public API: ``RedisClient`` plus the settings and exception types needed to
construct and assert on cache operations.
"""

from framework.clients.cache.client import RedisClient
from framework.core.config import RedisSettings
from framework.core.exceptions import CacheError

__all__ = [
    "CacheError",
    "RedisClient",
    "RedisSettings",
]
