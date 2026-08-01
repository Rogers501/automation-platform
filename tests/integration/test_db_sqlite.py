"""Integration tests for DatabaseClient against an embedded aiosqlite backend.

These tests exercise the real SQLAlchemy 2.0 async path (engine creation,
pooling, sessions, transactions, result conversion) using an in-memory SQLite
database. SQLite is embedded (no network/port/external service), so this stays
within the spirit of rule 14 while validating the genuine execute path. The
target production backends (MySQL/Oracle/PostgreSQL/ClickHouse) share this
same code path; only the async driver differs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from framework.clients.db.client import DatabaseClient, QuerySpec
from framework.core.config import DatabaseSettings
from framework.core.exceptions import DatabaseError


@pytest.fixture
async def sqlite_client() -> AsyncIterator[DatabaseClient]:
    """A DatabaseClient backed by an in-memory SQLite async engine.

    A full DSN is supplied via ``url`` so the component-based URL builder is
    bypassed; ``pool_pre_ping`` is disabled because the in-memory engine has
    no server to ping.
    """
    client = DatabaseClient(
        DatabaseSettings(url="sqlite+aiosqlite:///:memory:", pool_pre_ping=False)
    )
    try:
        async with client:
            yield client
    finally:
        await client.aclose()


async def test_execute_ddl_and_select(sqlite_client: DatabaseClient) -> None:
    """DDL and a SELECT round-trip through the client."""
    await sqlite_client.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    await sqlite_client.execute(
        QuerySpec("INSERT INTO users (name) VALUES (:n)"), params={"n": "alice"}
    )

    rows = await sqlite_client.fetch_all("SELECT id, name FROM users")

    assert len(rows) == 1
    assert rows[0].get("id") == 1
    assert rows[0].get("name") == "alice"


async def test_fetch_one_and_scalar(sqlite_client: DatabaseClient) -> None:
    """fetch_one returns the row; fetch_scalar returns the first column."""
    await sqlite_client.execute("CREATE TABLE t (n INTEGER)")
    await sqlite_client.execute("INSERT INTO t (n) VALUES (1), (2), (3)")

    one = await sqlite_client.fetch_one("SELECT n FROM t ORDER BY n")
    scalar = await sqlite_client.fetch_scalar("SELECT count(*) FROM t")
    scalars = await sqlite_client.fetch_scalars("SELECT n FROM t ORDER BY n")

    assert one is not None
    assert one.get("n") == 1
    assert scalar == 3
    assert scalars == [1, 2, 3]


async def test_transaction_commit(sqlite_client: DatabaseClient) -> None:
    """Statements in one transaction commit together on normal exit."""
    await sqlite_client.execute("CREATE TABLE accounts (id INTEGER, balance INTEGER)")
    await sqlite_client.execute("INSERT INTO accounts (id, balance) VALUES (1, 100)")

    async with sqlite_client.transaction() as tx:
        from sqlalchemy import text

        await tx.execute(text("UPDATE accounts SET balance = 50 WHERE id = 1"))

    rows = await sqlite_client.fetch_all("SELECT balance FROM accounts WHERE id = 1")
    assert rows[0].get("balance") == 50


async def test_transaction_rollback_on_error(sqlite_client: DatabaseClient) -> None:
    """An exception inside a transaction rolls back the whole unit of work."""
    await sqlite_client.execute("CREATE TABLE t (n INTEGER)")
    await sqlite_client.execute("INSERT INTO t (n) VALUES (1)")

    with pytest.raises(DatabaseError):
        async with sqlite_client.transaction() as tx:
            from sqlalchemy import text

            await tx.execute(text("UPDATE t SET n = 999"))
            # Force a failure: invalid column reference.
            await tx.execute(text("SELECT no_such_column FROM t"))

    # The earlier UPDATE must have been rolled back.
    rows = await sqlite_client.fetch_all("SELECT n FROM t")
    assert rows[0].get("n") == 1


async def test_health_true(sqlite_client: DatabaseClient) -> None:
    """health() returns True for a reachable in-memory database."""
    assert await sqlite_client.health() is True


async def test_invalid_sql_raises_database_error(sqlite_client: DatabaseClient) -> None:
    """A syntax error surfaces as a wrapped DatabaseError."""
    with pytest.raises(DatabaseError):
        await sqlite_client.execute("SELECT FROM nope")


async def test_connection_pool_reuse(sqlite_client: DatabaseClient) -> None:
    """Multiple statements reuse the same engine/pool (no re-creation)."""
    await sqlite_client.execute("CREATE TABLE p (id INTEGER)")
    engine_before = sqlite_client.engine
    await sqlite_client.execute("INSERT INTO p (id) VALUES (1)")
    await sqlite_client.execute("SELECT * FROM p")
    assert sqlite_client.engine is engine_before
