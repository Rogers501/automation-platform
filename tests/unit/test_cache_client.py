"""Unit tests for RedisClient using an in-memory fake (no real Redis, rule 14)."""

from __future__ import annotations

from typing import Any

import pytest

from framework.clients.cache.client import RedisClient
from framework.core.config import RedisSettings
from framework.core.exceptions import CacheError

# ---------------------------------------------------------------------------
# Fake redis.asyncio.Redis + Pipeline
# ---------------------------------------------------------------------------


class _FakePipeline:
    """Fake async pipeline: queues sync commands, executes on ``execute()``."""

    def __init__(self, redis: _FakeRedis) -> None:
        self._redis = redis
        self._commands: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def set(self, key: str, value: Any, **kwargs: Any) -> None:
        self._commands.append(("set", (key, value), kwargs))

    def get(self, key: str) -> None:
        self._commands.append(("get", (key,), {}))

    def delete(self, *keys: str) -> None:
        self._commands.append(("delete", keys, {}))

    async def execute(self) -> list[Any]:
        results: list[Any] = []
        for op, args, kwargs in self._commands:
            if op == "set":
                results.append(await self._redis.set(*args, **kwargs))
            elif op == "get":
                results.append(await self._redis.get(*args))
            elif op == "delete":
                results.append(await self._redis.delete(*args))
        return results

    async def reset(self) -> None:
        self._commands.clear()


class _FakeRedis:
    """In-memory fake of redis.asyncio.Redis for unit tests (rule 14)."""

    def __init__(self) -> None:
        self._strings: dict[str, str] = {}
        self._hashes: dict[str, dict[str, str]] = {}
        self._lists: dict[str, list[str]] = {}
        self._sets: dict[str, set[str]] = {}
        self._ttls: dict[str, int] = {}
        self._raises: Exception | None = None
        self.closed = False

    def will_raise(self, exc: Exception) -> None:
        self._raises = exc

    async def _check(self) -> None:
        if self._raises is not None:
            raise self._raises

    # --- string ---

    async def get(self, key: str) -> str | None:
        await self._check()
        return self._strings.get(key)

    async def set(
        self,
        key: str,
        value: Any,
        *,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool | None:
        await self._check()
        exists = key in self._strings
        if nx and exists:
            return None
        if xx and not exists:
            return None
        self._strings[key] = str(value)
        if ex is not None:
            self._ttls[key] = ex
        return True

    async def delete(self, *keys: str) -> int:
        await self._check()
        count = 0
        for k in keys:
            removed = False
            for store in (self._strings, self._hashes, self._lists, self._sets, self._ttls):
                if k in store:
                    del store[k]
                    removed = True
            if removed:
                count += 1
        return count

    async def exists(self, *keys: str) -> int:
        await self._check()
        return sum(
            1
            for k in keys
            if k in self._strings or k in self._hashes or k in self._lists or k in self._sets
        )

    async def expire(self, key: str, seconds: int) -> bool:
        await self._check()
        if key not in self._strings:
            return False
        self._ttls[key] = seconds
        return True

    async def ttl(self, key: str) -> int:
        await self._check()
        if key not in self._strings:
            return -2
        return self._ttls.get(key, -1)

    async def incrby(self, key: str, amount: int) -> int:
        await self._check()
        current = int(self._strings.get(key, "0"))
        new_val = current + amount
        self._strings[key] = str(new_val)
        return new_val

    async def decrby(self, key: str, amount: int) -> int:
        await self._check()
        current = int(self._strings.get(key, "0"))
        new_val = current - amount
        self._strings[key] = str(new_val)
        return new_val

    # --- hash ---

    async def hset(self, name: str, *, mapping: dict[str, Any] | None = None) -> int:
        await self._check()
        if name not in self._hashes:
            self._hashes[name] = {}
        new = 0
        for k, v in (mapping or {}).items():
            if k not in self._hashes[name]:
                new += 1
            self._hashes[name][k] = str(v)
        return new

    async def hget(self, name: str, key: str) -> str | None:
        await self._check()
        return self._hashes.get(name, {}).get(key)

    async def hgetall(self, name: str) -> dict[str, str]:
        await self._check()
        return dict(self._hashes.get(name, {}))

    async def hdel(self, name: str, *keys: str) -> int:
        await self._check()
        h = self._hashes.get(name, {})
        count = sum(1 for k in keys if k in h)
        for k in keys:
            h.pop(k, None)
        return count

    # --- list ---

    async def lpush(self, name: str, *values: Any) -> int:
        await self._check()
        if name not in self._lists:
            self._lists[name] = []
        for v in values:
            self._lists[name].insert(0, str(v))
        return len(self._lists[name])

    async def rpush(self, name: str, *values: Any) -> int:
        await self._check()
        if name not in self._lists:
            self._lists[name] = []
        for v in values:
            self._lists[name].append(str(v))
        return len(self._lists[name])

    async def lpop(self, name: str, count: int | None = None) -> str | list[str] | None:
        await self._check()
        lst = self._lists.get(name, [])
        if not lst:
            return None if count is None else []
        if count is None:
            return lst.pop(0)
        result = lst[:count]
        del lst[:count]
        return result

    async def rpop(self, name: str, count: int | None = None) -> str | list[str] | None:
        await self._check()
        lst = self._lists.get(name, [])
        if not lst:
            return None if count is None else []
        if count is None:
            return lst.pop()
        result = lst[-count:]
        del lst[-count:]
        return result

    async def lrange(self, name: str, start: int, stop: int) -> list[str]:
        await self._check()
        lst = list(self._lists.get(name, []))
        if not lst:
            return []
        n = len(lst)
        if start < 0:
            start = n + start
        if start < 0:
            start = 0
        if stop < 0:
            stop = n + stop
        if stop < 0:
            return []
        return lst[start : stop + 1]

    async def llen(self, name: str) -> int:
        await self._check()
        return len(self._lists.get(name, []))

    # --- set ---

    async def sadd(self, name: str, *values: Any) -> int:
        await self._check()
        if name not in self._sets:
            self._sets[name] = set()
        new = 0
        for v in values:
            s = str(v)
            if s not in self._sets[name]:
                new += 1
            self._sets[name].add(s)
        return new

    async def smembers(self, name: str) -> set[str]:
        await self._check()
        return set(self._sets.get(name, set()))

    async def srem(self, name: str, *values: Any) -> int:
        await self._check()
        s = self._sets.get(name, set())
        count = sum(1 for v in values if str(v) in s)
        for v in values:
            s.discard(str(v))
        return count

    # --- misc ---

    async def ping(self) -> bool:
        await self._check()
        return True

    async def aclose(self) -> None:
        self.closed = True

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client(fake: _FakeRedis | None = None, **kwargs: Any) -> RedisClient:
    """Build a RedisClient wired to a fake (or a new one)."""
    fake = fake or _FakeRedis()
    return RedisClient(settings=RedisSettings(**kwargs), client=fake)


# ---------------------------------------------------------------------------
# String operations
# ---------------------------------------------------------------------------


async def test_get_returns_value() -> None:
    """get returns the stored string value."""
    fake = _FakeRedis()
    fake._strings["k"] = "v"
    client = _client(fake)
    assert await client.get("k") == "v"


async def test_get_returns_none_for_missing() -> None:
    """get returns None for a non-existent key."""
    client = _client()
    assert await client.get("missing") is None


async def test_set_stores_value() -> None:
    """set stores a value and returns True."""
    fake = _FakeRedis()
    client = _client(fake)
    assert await client.set("k", "v") is True
    assert fake._strings["k"] == "v"


async def test_set_with_expiry() -> None:
    """set with ex stores the TTL."""
    fake = _FakeRedis()
    client = _client(fake)
    await client.set("k", "v", ex=60)
    assert fake._ttls["k"] == 60


async def test_set_nx_fails_on_existing() -> None:
    """set with nx returns False when the key already exists."""
    fake = _FakeRedis()
    fake._strings["k"] = "old"
    client = _client(fake)
    assert await client.set("k", "new", nx=True) is False
    assert fake._strings["k"] == "old"


async def test_set_xx_fails_on_missing() -> None:
    """set with xx returns False when the key does not exist."""
    client = _client()
    assert await client.set("k", "v", xx=True) is False


async def test_delete_removes_keys() -> None:
    """delete removes keys and returns the count."""
    fake = _FakeRedis()
    fake._strings["a"] = "1"
    fake._strings["b"] = "2"
    client = _client(fake)
    assert await client.delete("a", "b", "c") == 2
    assert "a" not in fake._strings


async def test_delete_no_keys_returns_zero() -> None:
    """delete with no keys returns 0."""
    client = _client()
    assert await client.delete() == 0


async def test_exists_counts_keys() -> None:
    """exists returns the number of existing keys."""
    fake = _FakeRedis()
    fake._strings["a"] = "1"
    client = _client(fake)
    assert await client.exists("a", "b") == 1


async def test_expire_sets_ttl() -> None:
    """expire sets a TTL on an existing key."""
    fake = _FakeRedis()
    fake._strings["k"] = "v"
    client = _client(fake)
    assert await client.expire("k", 30) is True
    assert fake._ttls["k"] == 30


async def test_expire_false_for_missing() -> None:
    """expire returns False for a non-existent key."""
    client = _client()
    assert await client.expire("missing", 30) is False


async def test_ttl_returns_remaining() -> None:
    """ttl returns the remaining TTL."""
    fake = _FakeRedis()
    fake._strings["k"] = "v"
    fake._ttls["k"] = 45
    client = _client(fake)
    assert await client.ttl("k") == 45


async def test_ttl_no_expire_returns_minus_one() -> None:
    """ttl returns -1 for a key without expiry."""
    fake = _FakeRedis()
    fake._strings["k"] = "v"
    client = _client(fake)
    assert await client.ttl("k") == -1


async def test_ttl_missing_returns_minus_two() -> None:
    """ttl returns -2 for a non-existent key."""
    client = _client()
    assert await client.ttl("missing") == -2


async def test_incr_increments() -> None:
    """incr increments a key's integer value."""
    client = _client()
    assert await client.incr("counter") == 1
    assert await client.incr("counter", amount=5) == 6


async def test_der_decrements() -> None:
    """decr decrements a key's integer value."""
    client = _client()
    assert await client.decr("counter") == -1
    assert await client.decr("counter", amount=3) == -4


# ---------------------------------------------------------------------------
# Hash operations
# ---------------------------------------------------------------------------


async def test_hset_sets_fields() -> None:
    """hset stores multiple hash fields and returns the new-field count."""
    client = _client()
    count = await client.hset("h", {"f1": "v1", "f2": "v2"})
    assert count == 2


async def test_hget_returns_value() -> None:
    """hget returns a single hash field value."""
    fake = _FakeRedis()
    fake._hashes["h"] = {"f": "v"}
    client = _client(fake)
    assert await client.hget("h", "f") == "v"


async def test_hget_none_for_missing() -> None:
    """hget returns None for a missing field."""
    client = _client()
    assert await client.hget("h", "f") is None


async def test_hgetall_returns_all() -> None:
    """hgetall returns all hash fields as a dict."""
    fake = _FakeRedis()
    fake._hashes["h"] = {"a": "1", "b": "2"}
    client = _client(fake)
    assert await client.hgetall("h") == {"a": "1", "b": "2"}


async def test_hdel_removes_fields() -> None:
    """hdel removes hash fields and returns the count."""
    fake = _FakeRedis()
    fake._hashes["h"] = {"a": "1", "b": "2"}
    client = _client(fake)
    assert await client.hdel("h", "a", "c") == 1
    assert "a" not in fake._hashes["h"]


# ---------------------------------------------------------------------------
# List operations
# ---------------------------------------------------------------------------


async def test_lpush_prepends() -> None:
    """lpush prepends values and returns the new length."""
    client = _client()
    assert await client.lpush("l", "a", "b") == 2


async def test_rpush_appends() -> None:
    """rpush appends values and returns the new length."""
    client = _client()
    assert await client.rpush("l", "a", "b") == 2


async def test_lpop_returns_head() -> None:
    """lpop removes and returns the head element."""
    fake = _FakeRedis()
    fake._lists["l"] = ["a", "b", "c"]
    client = _client(fake)
    assert await client.lpop("l") == "a"


async def test_rpop_returns_tail() -> None:
    """rpop removes and returns the tail element."""
    fake = _FakeRedis()
    fake._lists["l"] = ["a", "b", "c"]
    client = _client(fake)
    assert await client.rpop("l") == "c"


async def test_lpop_count_returns_list() -> None:
    """lpop with count returns a list of elements."""
    fake = _FakeRedis()
    fake._lists["l"] = ["a", "b", "c"]
    client = _client(fake)
    assert await client.lpop("l", count=2) == ["a", "b"]


async def test_lrange_returns_slice() -> None:
    """lrange returns a range of elements (inclusive stop)."""
    fake = _FakeRedis()
    fake._lists["l"] = ["a", "b", "c", "d", "e"]
    client = _client(fake)
    assert await client.lrange("l", 0, -1) == ["a", "b", "c", "d", "e"]
    assert await client.lrange("l", 1, 3) == ["b", "c", "d"]
    assert await client.lrange("l", -2, -1) == ["d", "e"]


async def test_llen_returns_length() -> None:
    """llen returns the list length."""
    fake = _FakeRedis()
    fake._lists["l"] = ["a", "b"]
    client = _client(fake)
    assert await client.llen("l") == 2


async def test_lpop_empty_returns_none() -> None:
    """lpop on an empty list returns None."""
    client = _client()
    assert await client.lpop("empty") is None


# ---------------------------------------------------------------------------
# Set operations
# ---------------------------------------------------------------------------


async def test_sadd_adds_members() -> None:
    """sadd adds members and returns the new-member count."""
    client = _client()
    assert await client.sadd("s", "a", "b") == 2


async def test_smembers_returns_all() -> None:
    """smembers returns all set members."""
    fake = _FakeRedis()
    fake._sets["s"] = {"a", "b"}
    client = _client(fake)
    assert await client.smembers("s") == {"a", "b"}


async def test_srem_removes_members() -> None:
    """srem removes members and returns the count."""
    fake = _FakeRedis()
    fake._sets["s"] = {"a", "b", "c"}
    client = _client(fake)
    assert await client.srem("s", "a", "z") == 1
    assert "a" not in fake._sets["s"]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


async def test_pipeline_executes_batch() -> None:
    """pipeline queues commands and executes them on exit."""
    fake = _FakeRedis()
    client = _client(fake)
    async with client.pipeline() as pipe:
        pipe.set("a", "1")
        pipe.set("b", "2")
    assert fake._strings["a"] == "1"
    assert fake._strings["b"] == "2"


async def test_pipeline_reset_on_error() -> None:
    """pipeline resets without executing when an exception occurs."""
    fake = _FakeRedis()
    client = _client(fake)
    with pytest.raises(ZeroDivisionError):
        async with client.pipeline() as pipe:
            pipe.set("a", "1")
            raise ZeroDivisionError("boom")
    assert "a" not in fake._strings


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


async def test_health_true_on_success() -> None:
    """health returns True when PING succeeds."""
    client = _client()
    assert await client.health() is True


async def test_health_false_on_error() -> None:
    """health returns False when PING raises."""
    fake = _FakeRedis()
    fake.will_raise(RuntimeError("connection lost"))
    client = _client(fake)
    assert await client.health() is False


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


async def test_close_marks_closed_and_blocks_use() -> None:
    """aclose closes the client and prevents further operations."""
    fake = _FakeRedis()
    client = _client(fake)
    await client.aclose()
    assert client.is_closed
    assert fake.closed
    with pytest.raises(CacheError):
        await client.get("k")


async def test_async_context_manager_closes() -> None:
    """async with closes the client on exit."""
    fake = _FakeRedis()
    async with _client(fake) as client:
        await client.set("k", "v")
    assert client.is_closed
    assert fake.closed


# ---------------------------------------------------------------------------
# Error wrapping
# ---------------------------------------------------------------------------


async def test_get_error_wrapped_as_cache_error() -> None:
    """A redis error during get surfaces as CacheError."""
    fake = _FakeRedis()
    fake.will_raise(RuntimeError("timeout"))
    client = _client(fake)
    with pytest.raises(CacheError) as info:
        await client.get("k")
    assert "timeout" in str(info.value)
    assert info.value.context["op"] == "get"
    assert info.value.context["error_type"] == "RuntimeError"


async def test_set_error_wrapped() -> None:
    """A redis error during set surfaces as CacheError."""
    fake = _FakeRedis()
    fake.will_raise(RuntimeError("OOM"))
    client = _client(fake)
    with pytest.raises(CacheError):
        await client.set("k", "v")


async def test_hset_error_wrapped() -> None:
    """A redis error during hset surfaces as CacheError."""
    fake = _FakeRedis()
    fake.will_raise(RuntimeError("wrong type"))
    client = _client(fake)
    with pytest.raises(CacheError):
        await client.hset("h", {"f": "v"})


# ---------------------------------------------------------------------------
# Key prefix
# ---------------------------------------------------------------------------


async def test_key_prefix_applied() -> None:
    """The configured key prefix is prepended to all keys."""
    fake = _FakeRedis()
    client = _client(fake, key_prefix="test:")
    await client.set("k", "v")
    assert fake._strings["test:k"] == "v"
    assert "k" not in fake._strings


async def test_key_prefix_applied_to_hash() -> None:
    """The key prefix is applied to hash operations."""
    fake = _FakeRedis()
    client = _client(fake, key_prefix="test:")
    await client.hset("h", {"f": "v"})
    assert "test:h" in fake._hashes
    assert "h" not in fake._hashes


async def test_no_prefix_passes_key_through() -> None:
    """Without a prefix, keys are passed through unchanged."""
    fake = _FakeRedis()
    client = _client(fake)
    await client.set("k", "v")
    assert "k" in fake._strings
