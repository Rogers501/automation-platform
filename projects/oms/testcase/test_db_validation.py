"""数据库校验示例."""

from __future__ import annotations

from pathlib import Path

import pytest

from framework.clients.db.client import DatabaseClient
from framework.testing.assertions import (
    assert_column_value,
    assert_row_contains,
    assert_row_count,
)

_SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def _read_sql(name: str) -> str:
    """读取 sql/ 下的脚本:去除 ``--`` 注释行与尾部分号.

    去除注释行可避免 SQLAlchemy ``text()`` 把注释里的 ``:param`` 误识别为绑定
    参数--sqlite 会忽略注释中的占位符,导致"语句用 1 个绑定、却传入 2 个参数"
    的数量不匹配错误.
    """
    raw = (_SQL_DIR / name).read_text(encoding="utf-8")
    lines = [
        line for line in raw.splitlines() if line.strip() and not line.lstrip().startswith("--")
    ]
    return "\n".join(lines).rstrip(";").strip()


@pytest.mark.regression
async def test_user_can_be_validated(db_client: DatabaseClient) -> None:
    """建表 -> 插入 -> 用 SQL 脚本查询 -> 框架断言校验."""
    await db_client.execute(_read_sql("init_users.sql"))
    await db_client.execute(
        "INSERT INTO users (name, email) VALUES (:name, :email)",
        params={"name": "alice", "email": "alice@example.com"},
    )

    result = await db_client.execute(_read_sql("check_users.sql"), params={"name": "alice"})
    assert_row_count(result, 1)
    assert_column_value(result, "name", "alice")
    assert_row_contains(result, {"name": "alice", "email": "alice@example.com"})
