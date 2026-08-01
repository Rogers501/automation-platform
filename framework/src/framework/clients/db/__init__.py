"""Database capability client (async, SQLAlchemy 2.0).

Public API: ``DatabaseClient`` plus the query, result, and dialect helpers
needed to construct and assert on database operations.
"""

from framework.clients.db.client import DatabaseClient, QuerySpec
from framework.clients.db.dialects import (
    ASYNC_DRIVERS,
    DEFAULT_PORTS,
    DriverInfo,
    build_async_url,
)
from framework.clients.db.results import Result, Row, convert_result, convert_rows

__all__ = [
    "ASYNC_DRIVERS",
    "DEFAULT_PORTS",
    "DatabaseClient",
    "DriverInfo",
    "QuerySpec",
    "Result",
    "Row",
    "build_async_url",
    "convert_result",
    "convert_rows",
]
