"""Enterprise async Redis client built on redis.asyncio.

Features: connection pooling, key-prefix isolation, string/hash/list/set
operations, TTL, atomic counters, pipeline batching, health check, and a
unified exception hierarchy (:class:`CacheError`).

The ``redis`` package is imported lazily inside :meth:`_build` so the
framework does not hard-depend on it at import time; a missing package
surfaces as a clear :class:`CacheError` on first use. Pass an explicit
``client`` for isolation in tests (rule 14).

Usage::

    async with RedisClient() as client:
        await client.set("user:1", "alice", ex=3600)
        name = await client.get("user:1")
        await client.hset("hash:1", {"field": "value"})

Defaults come from :attr:`FrameworkSettings.redis`; pass an explicit
:class:`RedisSettings` for isolation in tests.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Mapping
from typing import Any

from loguru import logger

from framework.core.config import RedisSettings, get_settings
from framework.core.exceptions import CacheError

__all__ = ["RedisClient"]

# Type alias: avoids shadowing builtins.set by RedisClient.set in annotations.
_StringSet = set[str]


class RedisClient:
    """Async Redis client with connection pooling and structured error wrapping.

    The underlying ``redis.asyncio.Redis`` client is created lazily (on first
    use) so the constructor is safe to call outside an event loop. Use
    ``async with`` to guarantee the connection pool is closed.

    Args:
        settings: Redis settings; defaults to :func:`get_settings().redis`.
        client: Pre-built async Redis client for testing (bypasses lazy import).
        name: Logical client name for log correlation.
    """

    def __init__(
        self,
        settings: RedisSettings | None = None,
        *,
        client: Any = None,
        name: str = "redis",
    ) -> None:
        self._settings = settings if settings is not None else get_settings().redis
        self._injected_client = client
        self._client: Any = client
        self._name = name
        self._logger = logger.bind(component="redis_client", client=name)
        self._closed = False

    # --- lifecycle -----------------------------------------------------

    async def _ensure(self) -> Any:
        """Lazily build the Redis client on first use."""
        if self._closed:
            raise CacheError("RedisClient is closed")
        if self._client is None:
            self._client = await self._build()
        return self._client

    async def _build(self) -> Any:
        """Construct the async Redis client with a connection pool.

        When ``url`` is set it takes precedence over component fields.
        The ``redis.asyncio`` package is imported lazily here.
        """
        try:
            from redis.asyncio import ConnectionPool, Redis
        except ImportError as exc:
            raise CacheError(
                "redis package is not installed; run 'uv sync' to install it",
                context={"error_type": type(exc).__name__},
            ) from exc

        common_kwargs: dict[str, Any] = {
            "max_connections": self._settings.max_connections,
            "decode_responses": self._settings.decode_responses,
            "socket_timeout": self._settings.socket_timeout,
            "socket_connect_timeout": self._settings.socket_connect_timeout,
            "health_check_interval": self._settings.health_check_interval,
        }
        if self._settings.url:
            pool = ConnectionPool.from_url(self._settings.url, **common_kwargs)
        else:
            pool = ConnectionPool(
                host=self._settings.host,
                port=self._settings.port,
                db=self._settings.db,
                username=self._settings.username or None,
                password=self._settings.password or None,
                **common_kwargs,
            )
        self._logger.debug(
            "creating redis pool: host={} db={} max_connections={}",
            self._settings.host,
            self._settings.db,
            self._settings.max_connections,
        )
        return Redis(connection_pool=pool)

    async def aclose(self) -> None:
        """Close the connection pool and mark the client closed."""
        self._closed = True
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> RedisClient:
        await self._ensure()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    @property
    def is_closed(self) -> bool:
        """Whether the client has been closed and can no longer operate."""
        return self._closed

    # --- key helpers ---------------------------------------------------

    def _key(self, key: str) -> str:
        """Apply the configured key prefix for namespace isolation."""
        prefix = self._settings.key_prefix
        return f"{prefix}{key}" if prefix else key

    def _wrap(self, exc: Exception, *, context: Mapping[str, Any] | None = None) -> CacheError:
        """Convert a redis library error into a :class:`CacheError`."""
        ctx: dict[str, Any] = dict(context or {})
        ctx.setdefault("error_type", type(exc).__name__)
        self._logger.warning("cache error: {}", exc)
        return CacheError(str(exc), context=ctx)

    # --- string operations ---------------------------------------------

    async def get(self, key: str) -> str | None:
        """Get the value of a key (``None`` if missing)."""
        client = await self._ensure()
        try:
            return await client.get(self._key(key))
        except Exception as exc:
            raise self._wrap(exc, context={"op": "get", "key": key}) from exc

    async def set(
        self,
        key: str,
        value: str | bytes | int | float,
        *,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """Set a key-value pair with optional expiry and NX/XX semantics.

        Args:
            key: Cache key.
            value: Value to store.
            ex: Expire in *N* seconds.
            px: Expire in *N* milliseconds.
            nx: Only set if the key does not exist.
            xx: Only set if the key already exists.

        Returns:
            ``True`` if the key was set, ``False`` if NX/XX condition failed.
        """
        client = await self._ensure()
        try:
            result = await client.set(self._key(key), value, ex=ex, px=px, nx=nx, xx=xx)
            return result is not None
        except Exception as exc:
            raise self._wrap(exc, context={"op": "set", "key": key}) from exc

    async def delete(self, *keys: str) -> int:
        """Delete one or more keys. Returns the number of keys removed."""
        if not keys:
            return 0
        client = await self._ensure()
        prefixed = [self._key(k) for k in keys]
        try:
            return await client.delete(*prefixed)
        except Exception as exc:
            raise self._wrap(exc, context={"op": "delete", "keys": list(keys)}) from exc

    async def exists(self, *keys: str) -> int:
        """Return the number of existing keys among the given keys."""
        if not keys:
            return 0
        client = await self._ensure()
        prefixed = [self._key(k) for k in keys]
        try:
            return await client.exists(*prefixed)
        except Exception as exc:
            raise self._wrap(exc, context={"op": "exists", "keys": list(keys)}) from exc

    async def expire(self, key: str, seconds: int) -> bool:
        """Set a TTL on a key. Returns ``False`` if the key does not exist."""
        client = await self._ensure()
        try:
            return await client.expire(self._key(key), seconds)
        except Exception as exc:
            raise self._wrap(exc, context={"op": "expire", "key": key}) from exc

    async def ttl(self, key: str) -> int:
        """Return remaining TTL in seconds (-1 = no expire, -2 = missing)."""
        client = await self._ensure()
        try:
            return await client.ttl(self._key(key))
        except Exception as exc:
            raise self._wrap(exc, context={"op": "ttl", "key": key}) from exc

    async def incr(self, key: str, *, amount: int = 1) -> int:
        """Increment a key's integer value by ``amount``. Returns the new value."""
        client = await self._ensure()
        try:
            return await client.incrby(self._key(key), amount)
        except Exception as exc:
            raise self._wrap(exc, context={"op": "incr", "key": key}) from exc

    async def decr(self, key: str, *, amount: int = 1) -> int:
        """Decrement a key's integer value by ``amount``. Returns the new value."""
        client = await self._ensure()
        try:
            return await client.decrby(self._key(key), amount)
        except Exception as exc:
            raise self._wrap(exc, context={"op": "decr", "key": key}) from exc

    # --- hash operations -----------------------------------------------

    async def hset(self, name: str, mapping: Mapping[str, str | bytes | int | float]) -> int:
        """Set multiple hash fields. Returns the number of new fields added."""
        client = await self._ensure()
        try:
            return await client.hset(self._key(name), mapping=dict(mapping))
        except Exception as exc:
            raise self._wrap(exc, context={"op": "hset", "name": name}) from exc

    async def hget(self, name: str, key: str) -> str | None:
        """Get a single hash field value (``None`` if missing)."""
        client = await self._ensure()
        try:
            return await client.hget(self._key(name), key)
        except Exception as exc:
            raise self._wrap(exc, context={"op": "hget", "name": name, "field": key}) from exc

    async def hgetall(self, name: str) -> dict[str, str]:
        """Get all hash fields and values as a dict."""
        client = await self._ensure()
        try:
            return await client.hgetall(self._key(name))
        except Exception as exc:
            raise self._wrap(exc, context={"op": "hgetall", "name": name}) from exc

    async def hdel(self, name: str, *keys: str) -> int:
        """Delete hash fields. Returns the number of fields removed."""
        if not keys:
            return 0
        client = await self._ensure()
        try:
            return await client.hdel(self._key(name), *keys)
        except Exception as exc:
            raise self._wrap(
                exc, context={"op": "hdel", "name": name, "fields": list(keys)}
            ) from exc

    # --- list operations ------------------------------------------------

    async def lpush(self, name: str, *values: str | bytes | int | float) -> int:
        """Prepend values to a list. Returns the new list length."""
        if not values:
            return 0
        client = await self._ensure()
        try:
            return await client.lpush(self._key(name), *values)
        except Exception as exc:
            raise self._wrap(exc, context={"op": "lpush", "name": name}) from exc

    async def rpush(self, name: str, *values: str | bytes | int | float) -> int:
        """Append values to a list. Returns the new list length."""
        if not values:
            return 0
        client = await self._ensure()
        try:
            return await client.rpush(self._key(name), *values)
        except Exception as exc:
            raise self._wrap(exc, context={"op": "rpush", "name": name}) from exc

    async def lpop(self, name: str, count: int | None = None) -> str | list[str] | None:
        """Pop from the head of a list.

        With ``count`` returns a list (possibly empty); without returns a
        single value or ``None`` when the list is empty.
        """
        client = await self._ensure()
        try:
            if count is not None:
                return await client.lpop(self._key(name), count)
            return await client.lpop(self._key(name))
        except Exception as exc:
            raise self._wrap(exc, context={"op": "lpop", "name": name}) from exc

    async def rpop(self, name: str, count: int | None = None) -> str | list[str] | None:
        """Pop from the tail of a list.

        With ``count`` returns a list (possibly empty); without returns a
        single value or ``None`` when the list is empty.
        """
        client = await self._ensure()
        try:
            if count is not None:
                return await client.rpop(self._key(name), count)
            return await client.rpop(self._key(name))
        except Exception as exc:
            raise self._wrap(exc, context={"op": "rpop", "name": name}) from exc

    async def lrange(self, name: str, start: int, stop: int) -> list[str]:
        """Get a range of list elements (0-based; ``-1`` = last)."""
        client = await self._ensure()
        try:
            return await client.lrange(self._key(name), start, stop)
        except Exception as exc:
            raise self._wrap(exc, context={"op": "lrange", "name": name}) from exc

    async def llen(self, name: str) -> int:
        """Return the length of a list."""
        client = await self._ensure()
        try:
            return await client.llen(self._key(name))
        except Exception as exc:
            raise self._wrap(exc, context={"op": "llen", "name": name}) from exc

    # --- set operations -------------------------------------------------

    async def sadd(self, name: str, *values: str | bytes | int | float) -> int:
        """Add members to a set. Returns the number of new members added."""
        if not values:
            return 0
        client = await self._ensure()
        try:
            return await client.sadd(self._key(name), *values)
        except Exception as exc:
            raise self._wrap(exc, context={"op": "sadd", "name": name}) from exc

    async def smembers(self, name: str) -> _StringSet:
        """Return all members of a set."""
        client = await self._ensure()
        try:
            return await client.smembers(self._key(name))
        except Exception as exc:
            raise self._wrap(exc, context={"op": "smembers", "name": name}) from exc

    async def srem(self, name: str, *values: str | bytes | int | float) -> int:
        """Remove members from a set. Returns the number removed."""
        if not values:
            return 0
        client = await self._ensure()
        try:
            return await client.srem(self._key(name), *values)
        except Exception as exc:
            raise self._wrap(exc, context={"op": "srem", "name": name}) from exc

    # --- pipeline -------------------------------------------------------

    @contextlib.asynccontextmanager
    async def pipeline(self) -> AsyncIterator[Any]:
        """Yield a Redis pipeline for batched, atomic command execution.

        Commands are queued on the pipeline object; ``execute()`` is called
        automatically on normal exit. On exception, the pipeline is reset
        without executing.

        Usage::

            async with client.pipeline() as pipe:
                pipe.set("a", "1")
                pipe.set("b", "2")
                # pipe.execute() called automatically on exit
        """
        client = await self._ensure()
        pipe = client.pipeline()
        try:
            yield pipe
        except Exception:
            with contextlib.suppress(Exception):
                await pipe.reset()
            raise
        try:
            await pipe.execute()
        except Exception as exc:
            raise self._wrap(exc, context={"op": "pipeline"}) from exc

    # --- health ---------------------------------------------------------

    async def health(self) -> bool:
        """Return ``True`` if a ``PING`` succeeds."""
        try:
            client = await self._ensure()
            return await client.ping()
        except Exception:
            return False
