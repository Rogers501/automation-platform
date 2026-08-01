"""Unit tests for DatabaseClient using injected fakes (no real DB, rule 14)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from sqlalchemy.exc import SQLAlchemyError

from framework.clients.db.client import DatabaseClient, QuerySpec
from framework.clients.db.results import Result
from framework.core.config import DatabaseSettings
from framework.core.exceptions import DatabaseError


class _FakeRow:
    """Mimics a SQLAlchemy Row for scalar access (row[0])."""

    def __init__(self, mapping: Mapping[str, Any]) -> None:
        self._mapping = mapping

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return list(self._mapping.values())[key]
        return self._mapping[key]


class _FakeSAResult:
    """Stand-in for sqlalchemy.engine.Result returned by session.execute."""

    def __init__(
        self,
        mappings: list[Mapping[str, Any]] | None = None,
        *,
        rowcount: int = -1,
        scalars: list[Any] | None = None,
        first_row: _FakeRow | None = ...,
        inserted_primary_key: tuple[Any, ...] | None = None,
    ) -> None:
        self._mappings = list(mappings or [])
        self.rowcount = rowcount
        self._scalars = scalars
        self._first_row = first_row
        self.inserted_primary_key = inserted_primary_key

    def mappings(self) -> _FakeSAResult:
        return self

    def fetchall(self) -> list[Mapping[str, Any]]:
        return self._mappings

    def first(self) -> _FakeRow | None:
        if self._first_row is ...:
            return _FakeRow(self._mappings[0]) if self._mappings else None
        return self._first_row

    def scalars(self) -> list[Any]:
        if self._scalars is not None:
            return self._scalars
        return [next(iter(m.values())) for m in self._mappings]


class _FakeBegin:
    """Async context manager for session.begin()."""

    async def __aenter__(self) -> _FakeBegin:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False  # do not suppress exceptions


class _FakeSession:
    """Async-session double usable as ``async with factory() as session``."""

    def __init__(self, results: list[_FakeSAResult] | None = None) -> None:
        self._results = list(results or [])
        self.executed: list[tuple[Any, Any]] = []
        self._raises: SQLAlchemyError | None = None

    def will_raise(self, exc: SQLAlchemyError) -> None:
        self._raises = exc

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def begin(self) -> _FakeBegin:
        return _FakeBegin()

    async def execute(self, statement: Any, params: Any = None, **kw: Any) -> _FakeSAResult:
        self.executed.append((statement, params))
        if self._raises is not None:
            raise self._raises
        if self._results:
            return self._results.pop(0)
        return _FakeSAResult([])


class _FakeEngine:
    """Engine double with a coroutine dispose()."""

    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


def _factory(sessions: list[_FakeSession]) -> Any:
    """Return a callable yielding the next fake session (mimics sessionmaker)."""
    iterator = iter(sessions)

    def make() -> _FakeSession:
        return next(iterator)

    return make


def _client(session: _FakeSession) -> DatabaseClient:
    """Build a DatabaseClient wired to one fake session + fake engine."""
    return DatabaseClient(
        settings=DatabaseSettings(),
        engine=_FakeEngine(),
        session_factory=_factory([session]),
    )


async def test_execute_returns_result() -> None:
    """execute runs the statement and converts rows into a Result."""
    session = _FakeSession(results=[_FakeSAResult([{"id": 1, "name": "alice"}], rowcount=1)])
    client = _client(session)

    result = await client.execute(QuerySpec("SELECT * FROM users"))

    assert isinstance(result, Result)
    assert len(result) == 1
    assert result.first.get("name") == "alice"
    assert result.rowcount == 1


async def test_execute_accepts_raw_sql() -> None:
    """A raw SQL string is accepted in place of a QuerySpec."""
    session = _FakeSession(results=[_FakeSAResult([])])
    client = _client(session)

    result = await client.execute("DELETE FROM users WHERE active = :v", params={"v": False})

    assert result.rows == []
    assert session.executed[0][1] == {"v": False}


async def test_query_spec_params_used_when_none_passed() -> None:
    """QuerySpec.params flow through when no per-call params override."""
    session = _FakeSession(results=[_FakeSAResult([{"id": 1}])])
    client = _client(session)

    await client.execute(QuerySpec("SELECT :n AS n", params={"n": 7}))

    assert session.executed[0][1] == {"n": 7}


async def test_per_call_params_override_spec() -> None:
    """Explicit params override the spec's params."""
    session = _FakeSession(results=[_FakeSAResult([{"id": 1}])])
    client = _client(session)

    await client.execute(QuerySpec("SELECT :n AS n", params={"n": 1}), params={"n": 2})

    assert session.executed[0][1] == {"n": 2}


async def test_fetch_one_returns_row_or_none() -> None:
    """fetch_one returns the first row, or None when empty."""
    session = _FakeSession(results=[_FakeSAResult([{"id": 1, "name": "x"}])])
    client = _client(session)
    row = await client.fetch_one("SELECT * FROM users")
    assert row is not None
    assert row.get("name") == "x"


async def test_fetch_all_returns_all_rows() -> None:
    """fetch_all materializes every row."""
    session = _FakeSession(results=[_FakeSAResult([{"id": 1}, {"id": 2}, {"id": 3}])])
    client = _client(session)
    rows = await client.fetch_all("SELECT id FROM t")
    assert [r.get("id") for r in rows] == [1, 2, 3]


async def test_fetch_scalar_returns_first_column() -> None:
    """fetch_scalar returns the first column of the first row."""
    session = _FakeSession(results=[_FakeSAResult([], first_row=_FakeRow({"c": 42}))])
    client = _client(session)
    value = await client.fetch_scalar("SELECT count(*) AS c FROM t")
    assert value == 42


async def test_fetch_scalar_none_when_empty() -> None:
    """fetch_scalar returns None when there are no rows."""
    session = _FakeSession(results=[_FakeSAResult([], first_row=None)])
    client = _client(session)
    assert await client.fetch_scalar("SELECT 1") is None


async def test_fetch_scalars_returns_list() -> None:
    """fetch_scalars returns the first column of every row as a list."""
    session = _FakeSession(results=[_FakeSAResult([], scalars=[1, 2, 3])])
    client = _client(session)
    assert await client.fetch_scalars("SELECT id FROM t") == [1, 2, 3]


async def test_transaction_yields_session() -> None:
    """transaction() yields a session whose statements share one tx."""
    session = _FakeSession(results=[_FakeSAResult([{"ok": 1}])])
    client = _client(session)

    from sqlalchemy import text

    async with client.transaction() as tx:
        await tx.execute(text("INSERT INTO t (a) VALUES (1)"))

    assert session.executed[0][0].text == "INSERT INTO t (a) VALUES (1)"


async def test_sqlalchemy_error_wrapped_as_database_error() -> None:
    """A SQLAlchemy error during execute surfaces as DatabaseError."""
    session = _FakeSession()
    session.will_raise(SQLAlchemyError("syntax error"))
    client = _client(session)

    with pytest.raises(DatabaseError) as info:
        await client.execute("SELECT broken")

    assert "syntax error" in str(info.value)
    assert info.value.context["error_type"] == "SQLAlchemyError"


async def test_transaction_error_wrapped() -> None:
    """An error inside a transaction is wrapped and the tx rolls back."""
    session = _FakeSession()
    session.will_raise(SQLAlchemyError("boom"))
    client = _client(session)

    with pytest.raises(DatabaseError):
        async with client.transaction() as tx:
            await tx.execute("SELECT 1")


async def test_health_true_on_success() -> None:
    """health returns True when SELECT 1 yields 1."""
    session = _FakeSession(results=[_FakeSAResult([], first_row=_FakeRow({"c": 1}))])
    client = _client(session)
    assert await client.health() is True


async def test_health_false_on_error() -> None:
    """health returns False when the query raises a wrapped DatabaseError."""
    session = _FakeSession()
    session.will_raise(SQLAlchemyError("connection lost"))
    client = _client(session)
    assert await client.health() is False


async def test_close_disposes_engine_and_blocks_use() -> None:
    """aclose disposes the engine and marks the client unusable."""
    engine = _FakeEngine()
    client = DatabaseClient(
        settings=DatabaseSettings(),
        engine=engine,
        session_factory=_factory([_FakeSession()]),
    )
    await client.aclose()
    assert client.is_closed
    assert engine.disposed
    with pytest.raises(DatabaseError):
        await client.execute("SELECT 1")


async def test_async_context_manager_closes() -> None:
    """``async with`` disposes the engine on exit."""
    engine = _FakeEngine()
    async with DatabaseClient(
        settings=DatabaseSettings(),
        engine=engine,
        session_factory=_factory([_FakeSession(results=[_FakeSAResult([{"id": 1}])])]),
    ) as client:
        await client.execute("SELECT 1")
    assert client.is_closed
    assert engine.disposed
