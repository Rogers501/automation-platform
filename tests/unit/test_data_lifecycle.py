"""Unit tests for framework.testing.data.lifecycle (fake DB, rule 14)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from framework.testing.data import (
    DataLifecycle,
    DataLifecycleError,
    load_sql_files,
    split_statements,
)


class _FakeDB:
    """Fake DatabaseClient that records executed statements."""

    def __init__(self, *, fail_on: str | None = None) -> None:
        self.executed: list[str] = []
        self._fail_on = fail_on

    async def execute(self, query: Any, **kwargs: Any) -> Any:
        sql = str(query)
        if self._fail_on and self._fail_on in sql:
            raise RuntimeError(f"Simulated failure on: {sql}")
        self.executed.append(sql)
        return None


# ---------------------------------------------------------------------------
# split_statements
# ---------------------------------------------------------------------------


def test_split_single_statement() -> None:
    assert split_statements("SELECT 1") == ["SELECT 1"]


def test_split_multiple_statements() -> None:
    result = split_statements("INSERT INTO t VALUES(1); DELETE FROM t;")
    assert result == ["INSERT INTO t VALUES(1)", "DELETE FROM t"]


def test_split_strips_line_comments() -> None:
    sql = "-- this is a comment\nSELECT 1; -- another\n-- trailing"
    assert split_statements(sql) == ["SELECT 1"]


def test_split_respects_single_quotes() -> None:
    sql = "INSERT INTO t VALUES('a;b;c'); SELECT 2"
    result = split_statements(sql)
    assert result == ["INSERT INTO t VALUES('a;b;c')", "SELECT 2"]


def test_split_empty_string() -> None:
    assert split_statements("") == []


def test_split_only_comments() -> None:
    assert split_statements("-- nothing\n-- here") == []


def test_split_trailing_no_semicolon() -> None:
    assert split_statements("SELECT 1; SELECT 2") == ["SELECT 1", "SELECT 2"]


# ---------------------------------------------------------------------------
# load_sql_files
# ---------------------------------------------------------------------------


def test_load_sql_files_sorted(tmp_path: Path) -> None:
    (tmp_path / "02_second.sql").write_text("SELECT 2", encoding="utf-8")
    (tmp_path / "01_first.sql").write_text("SELECT 1", encoding="utf-8")

    result = load_sql_files(tmp_path)

    assert len(result) == 2
    assert result[0] == ("01_first.sql", "SELECT 1")
    assert result[1] == ("02_second.sql", "SELECT 2")


def test_load_sql_files_empty_dir(tmp_path: Path) -> None:
    assert load_sql_files(tmp_path) == []


# ---------------------------------------------------------------------------
# DataLifecycle - inline SQL
# ---------------------------------------------------------------------------


async def test_setup_executes_inline_sql() -> None:
    db = _FakeDB()
    lc = DataLifecycle(db, setup_sql="INSERT INTO t VALUES(1)")

    await lc.setup()

    assert db.executed == ["INSERT INTO t VALUES(1)"]


async def test_teardown_executes_inline_sql() -> None:
    db = _FakeDB()
    lc = DataLifecycle(db, teardown_sql="DELETE FROM t")

    await lc.teardown()

    assert db.executed == ["DELETE FROM t"]


async def test_context_manager_setup_then_teardown() -> None:
    db = _FakeDB()
    lc = DataLifecycle(
        db,
        setup_sql="INSERT INTO t VALUES(1)",
        teardown_sql="DELETE FROM t",
    )

    async with lc:
        assert db.executed == ["INSERT INTO t VALUES(1)"]

    assert db.executed == ["INSERT INTO t VALUES(1)", "DELETE FROM t"]


async def test_context_manager_teardown_on_exception() -> None:
    db = _FakeDB()
    lc = DataLifecycle(db, teardown_sql="DELETE FROM t")

    with pytest.raises(ValueError):
        async with lc:
            raise ValueError("test error")

    assert "DELETE FROM t" in db.executed


async def test_setup_failure_raises_error() -> None:
    db = _FakeDB(fail_on="INSERT")
    lc = DataLifecycle(db, setup_sql="INSERT INTO t VALUES(1)")

    with pytest.raises(DataLifecycleError):
        await lc.setup()


async def test_teardown_failure_does_not_raise() -> None:
    db = _FakeDB(fail_on="DELETE")
    lc = DataLifecycle(db, teardown_sql="DELETE FROM t")

    # Should not raise despite the failure.
    await lc.teardown()


# ---------------------------------------------------------------------------
# DataLifecycle - directory-based
# ---------------------------------------------------------------------------


async def test_setup_from_seed_dir(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "01_init.sql").write_text("INSERT INTO t VALUES(1);", encoding="utf-8")
    (seed / "02_more.sql").write_text("INSERT INTO t VALUES(2);", encoding="utf-8")

    db = _FakeDB()
    lc = DataLifecycle(db, seed_dir=seed)

    await lc.setup()

    assert db.executed == ["INSERT INTO t VALUES(1)", "INSERT INTO t VALUES(2)"]


async def test_teardown_from_cleanup_dir(tmp_path: Path) -> None:
    cleanup = tmp_path / "cleanup"
    cleanup.mkdir()
    (cleanup / "01_drop.sql").write_text("DELETE FROM t;", encoding="utf-8")

    db = _FakeDB()
    lc = DataLifecycle(db, cleanup_dir=cleanup)

    await lc.teardown()

    assert db.executed == ["DELETE FROM t"]


async def test_missing_dir_warns_not_raises(tmp_path: Path) -> None:
    db = _FakeDB()
    lc = DataLifecycle(db, seed_dir=tmp_path / "nonexistent")

    await lc.setup()
    assert db.executed == []


async def test_execute_during_scope() -> None:
    db = _FakeDB()
    lc = DataLifecycle(db)

    async with lc:
        await lc.execute("UPDATE t SET v=1")

    assert db.executed == ["UPDATE t SET v=1"]


async def test_multi_statement_inline_sql() -> None:
    db = _FakeDB()
    lc = DataLifecycle(db, setup_sql="INSERT INTO t VALUES(1); INSERT INTO t VALUES(2)")

    await lc.setup()

    assert db.executed == ["INSERT INTO t VALUES(1)", "INSERT INTO t VALUES(2)"]
