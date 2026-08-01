"""Database dialect mapping: type -> async SQLAlchemy driver + URL building.

Supports MySQL, PostgreSQL, Oracle, and ClickHouse. Driver packages are
imported lazily by SQLAlchemy when the engine connects, so the framework
does not hard-depend on any single driver; a missing driver surfaces as a
clear :class:`DatabaseError` at connect time.
"""

from __future__ import annotations

from dataclasses import dataclass

from framework.core.config import DatabaseType
from framework.core.exceptions import ConfigError

__all__ = [
    "ASYNC_DRIVERS",
    "DEFAULT_PORTS",
    "DriverInfo",
    "build_async_url",
]


@dataclass(frozen=True)
class DriverInfo:
    """Maps a database type to its SQLAlchemy async dialect + driver.

    Attributes:
        dialect: SQLAlchemy dialect name (the URL scheme prefix).
        driver: Async DBAPI driver name appended after ``+``.
    """

    dialect: str
    driver: str

    @property
    def scheme(self) -> str:
        """The full URL scheme, e.g. ``mysql+aiomysql``."""
        return f"{self.dialect}+{self.driver}"


#: Async driver for each supported database type. The actual driver package is
#: imported lazily by SQLAlchemy only when a connection is established.
ASYNC_DRIVERS: dict[DatabaseType, DriverInfo] = {
    DatabaseType.MYSQL: DriverInfo("mysql", "aiomysql"),
    DatabaseType.POSTGRESQL: DriverInfo("postgresql", "asyncpg"),
    DatabaseType.ORACLE: DriverInfo("oracle", "oracledb_async"),
    DatabaseType.CLICKHOUSE: DriverInfo("clickhouse", "asynch"),
}

#: Default ports per database type when none is configured.
DEFAULT_PORTS: dict[DatabaseType, int] = {
    DatabaseType.MYSQL: 3306,
    DatabaseType.POSTGRESQL: 5432,
    DatabaseType.ORACLE: 1521,
    DatabaseType.CLICKHOUSE: 9000,
}


def build_async_url(
    db_type: DatabaseType,
    *,
    host: str = "localhost",
    port: int | None = None,
    username: str = "",
    password: str = "",
    database: str = "",
    query: dict[str, str] | None = None,
) -> str:
    """Build an async SQLAlchemy connection URL from components.

    Args:
        db_type: The target database type.
        host: Database host name.
        port: Port; defaults to the dialect default when ``None``.
        username: Username (optional).
        password: Password (optional; never logged).
        database: Database/service name.
        query: Extra query-string parameters (e.g. ``{"charset": "utf8mb4"}``).

    Returns:
        A SQLAlchemy async URL string, e.g.
        ``postgresql+asyncpg://user:pwd@host:5432/db``.

    Raises:
        ConfigError: If ``db_type`` is not a supported :class:`DatabaseType`.
    """
    if not isinstance(db_type, DatabaseType):
        raise ConfigError(
            f"Unsupported database type: {db_type!r}",
            context={"value": db_type, "valid": [t.value for t in DatabaseType]},
        )
    driver = ASYNC_DRIVERS[db_type]
    effective_port = port if port is not None else DEFAULT_PORTS[db_type]

    authority = host
    if username:
        # Password may be empty (trusted auth); still emit user@.
        credentials = username
        if password:
            credentials = f"{username}:{password}"
        authority = f"{credentials}@{host}"
    authority = f"{authority}:{effective_port}"

    url = f"{driver.scheme}://{authority}"
    if database:
        url += f"/{database}"
    if query:
        from urllib.parse import urlencode

        url += "?" + urlencode(query)
    return url
