"""Unit tests for database dialect mapping and async URL building."""

from __future__ import annotations

import pytest

from framework.clients.db.dialects import (
    ASYNC_DRIVERS,
    DEFAULT_PORTS,
    DriverInfo,
    build_async_url,
)
from framework.core.config import DatabaseType
from framework.core.exceptions import ConfigError


def test_database_type_values() -> None:
    """DatabaseType exposes the four supported backends."""
    assert DatabaseType.MYSQL.value == "mysql"
    assert DatabaseType.POSTGRESQL.value == "postgresql"
    assert DatabaseType.ORACLE.value == "oracle"
    assert DatabaseType.CLICKHOUSE.value == "clickhouse"


def test_async_drivers_cover_all_types() -> None:
    """Every database type has an async driver mapping."""
    for db_type in DatabaseType:
        assert db_type in ASYNC_DRIVERS
        info = ASYNC_DRIVERS[db_type]
        assert isinstance(info, DriverInfo)
        assert "+" in info.scheme


@pytest.mark.parametrize(
    ("db_type", "scheme", "port"),
    [
        (DatabaseType.MYSQL, "mysql+aiomysql", 3306),
        (DatabaseType.POSTGRESQL, "postgresql+asyncpg", 5432),
        (DatabaseType.ORACLE, "oracle+oracledb_async", 1521),
        (DatabaseType.CLICKHOUSE, "clickhouse+asynch", 9000),
    ],
)
def test_default_ports_and_schemes(db_type: DatabaseType, scheme: str, port: int) -> None:
    """Each type maps to its expected async scheme and default port."""
    assert ASYNC_DRIVERS[db_type].scheme == scheme
    assert DEFAULT_PORTS[db_type] == port


def test_build_url_minimal() -> None:
    """A bare type uses defaults: localhost + dialect default port, no creds."""
    url = build_async_url(DatabaseType.POSTGRESQL)
    assert url == "postgresql+asyncpg://localhost:5432"


def test_build_url_with_credentials_and_db() -> None:
    """User/password/database are embedded into the authority and path."""
    url = build_async_url(
        DatabaseType.MYSQL,
        host="db.example.com",
        username="alice",
        password="s3cret",
        database="app",
    )
    assert url == "mysql+aiomysql://alice:s3cret@db.example.com:3306/app"


def test_build_url_custom_port_overrides_default() -> None:
    """An explicit port overrides the dialect default."""
    url = build_async_url(DatabaseType.POSTGRESQL, port=6543)
    assert url.endswith(":6543")


def test_build_url_user_without_password() -> None:
    """A username without password emits user@ (trusted auth)."""
    url = build_async_url(DatabaseType.ORACLE, username="svc", database="ORCLPDB1")
    assert url == "oracle+oracledb_async://svc@localhost:1521/ORCLPDB1"


def test_build_url_query_params_appended() -> None:
    """Extra query params are url-encoded and appended."""
    url = build_async_url(
        DatabaseType.MYSQL,
        username="u",
        password="p",
        database="d",
        query={"charset": "utf8mb4"},
    )
    assert "charset=utf8mb4" in url
    assert url.startswith("mysql+aiomysql://u:p@localhost:3306/d?")


def test_build_url_invalid_type_raises() -> None:
    """A non-DatabaseType value raises ConfigError."""
    with pytest.raises(ConfigError):
        build_async_url("sqlite")  # type: ignore[arg-type]
