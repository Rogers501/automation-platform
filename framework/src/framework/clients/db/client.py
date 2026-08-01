"""Enterprise async database client built on SQLAlchemy 2.0.

Features: connection pooling (``AsyncAdaptedQueuePool``), per-call
transactions with commit-on-success / rollback-on-error, an explicit
``transaction()`` context manager for multi-statement units of work, query
wrapping via :class:`QuerySpec`, and result conversion into framework
:class:`Result` / :class:`Row` structures.

Multi-backend: MySQL, PostgreSQL, Oracle, ClickHouse (driver packages are
imported lazily by SQLAlchemy on connect). Pass an explicit ``url`` to bypass
component-based URL building, e.g. for unusual DSNs.

Usage::

    async with DatabaseClient() as client:
        rows = await client.fetch_all(QuerySpec("SELECT * FROM users"))
        async with client.transaction() as tx:
            await tx.execute(text("UPDATE users SET active = :v"), {"v": True}))

Defaults come from :attr:`FrameworkSettings.database`; pass an explicit
:class:`DatabaseSettings` for isolation in tests.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from framework.clients.db.dialects import build_async_url
from framework.clients.db.results import Result, Row, convert_result
from framework.core.config import DatabaseSettings, get_settings
from framework.core.exceptions import DatabaseError

__all__ = ["DatabaseClient", "QuerySpec"]


@dataclass(frozen=True)
class QuerySpec:
    """A serializable SQL query description for data-driven tests.

    Attributes:
        text: The SQL statement (use named ``:param`` placeholders).
        params: Bound parameters as a mapping (named) or sequence (positional).
    """

    text: str
    params: Mapping[str, Any] | Sequence[Any] | None = None


class DatabaseClient:
    """Async database client with pooling, transactions, and result conversion.

    The underlying :class:`AsyncEngine` and session factory are created lazily
    (on first use) so the constructor is safe to call outside an event loop.
    Use ``async with`` to guarantee the pool is disposed.

    For tests, inject either ``engine`` (a pre-built ``AsyncEngine``) or
    ``session_factory`` (an ``async_sessionmaker`` or compatible callable) to
    avoid constructing a real connection.
    """

    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        *,
        engine: AsyncEngine | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        name: str = "db",
    ) -> None:
        self._settings = settings if settings is not None else get_settings().database
        self._injected_engine = engine
        self._injected_factory = session_factory
        self._engine: AsyncEngine | None = engine
        self._session_factory: async_sessionmaker[AsyncSession] | None = session_factory
        self._name = name
        self._logger = logger.bind(component="db_client", client=name)
        self._closed = False

    # --- lifecycle -----------------------------------------------------

    async def _ensure(self) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
        """Lazily build the engine + session factory on first use."""
        if self._closed:
            raise DatabaseError("DatabaseClient is closed")
        if self._engine is None or self._session_factory is None:
            if self._injected_engine is not None and self._injected_factory is not None:
                self._engine = self._injected_engine
                self._session_factory = self._injected_factory
            else:
                self._engine = await self._build_engine()
                self._session_factory = async_sessionmaker(
                    self._engine,
                    expire_on_commit=False,
                    class_=AsyncSession,
                )
        return self._engine, self._session_factory

    async def _build_engine(self) -> AsyncEngine:
        """Construct the async engine from settings (URL or components).

        Pool-sizing arguments are only applied for server backends; SQLite uses
        ``StaticPool`` (in-memory) and rejects ``pool_size``/``max_overflow``/
        ``pool_timeout``.
        """
        if self._settings.url:
            url = self._settings.url
        else:
            url = build_async_url(
                self._settings.type,
                host=self._settings.host,
                port=self._settings.port,
                username=self._settings.username,
                password=self._settings.password,
                database=self._settings.database,
            )
        url_obj = sa.make_url(url)
        dialect_name = url_obj.get_dialect().name
        self._logger.debug("creating async engine: {}", url_obj.drivername)
        engine_kwargs: dict[str, Any] = {
            "echo": self._settings.echo,
            "connect_args": dict(self._settings.connect_args),
        }
        if dialect_name != "sqlite":
            engine_kwargs.update(
                pool_size=self._settings.pool_size,
                max_overflow=self._settings.max_overflow,
                pool_timeout=self._settings.pool_timeout,
                pool_recycle=self._settings.pool_recycle,
                pool_pre_ping=self._settings.pool_pre_ping,
            )
        return create_async_engine(url, **engine_kwargs)

    async def aclose(self) -> None:
        """Dispose the engine pool and mark the client closed."""
        self._closed = True
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
        self._session_factory = None

    async def __aenter__(self) -> DatabaseClient:
        await self._ensure()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    @property
    def is_closed(self) -> bool:
        """Whether the client has been closed and can no longer execute."""
        return self._closed

    @property
    def engine(self) -> AsyncEngine | None:
        """The underlying async engine (``None`` until first use)."""
        return self._engine

    # --- query execution ----------------------------------------------

    async def execute(
        self,
        query: QuerySpec | str,
        *,
        params: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> Result:
        """Execute a single statement in its own transaction (commit on success).

        Args:
            query: A :class:`QuerySpec` or raw SQL string.
            params: Bound parameters (overrides ``QuerySpec.params``).

        Returns:
            A :class:`Result` with materialized rows and row count.
        """
        statement, bound = self._prepare(query, params)
        _, factory = await self._ensure()

        async with factory() as session, session.begin():
            result = await self._run(session, statement, bound)
            return convert_result(result)

    async def fetch_one(
        self,
        query: QuerySpec | str,
        *,
        params: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> Row | None:
        """Execute and return the first row, or ``None`` when empty."""
        result = await self.execute(query, params=params)
        return result.first

    async def fetch_all(
        self,
        query: QuerySpec | str,
        *,
        params: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> list[Row]:
        """Execute and return all rows."""
        result = await self.execute(query, params=params)
        return result.rows

    async def fetch_scalar(
        self,
        query: QuerySpec | str,
        *,
        params: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> Any | None:
        """Execute and return the first column of the first row (or ``None``)."""
        statement, bound = self._prepare(query, params)
        _, factory = await self._ensure()
        async with factory() as session, session.begin():
            result = await self._run(session, statement, bound)
            row = result.first()
            if row is None:
                return None
            return row[0]

    async def fetch_scalars(
        self,
        query: QuerySpec | str,
        *,
        params: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> list[Any]:
        """Execute and return the first column of every row as a list."""
        statement, bound = self._prepare(query, params)
        _, factory = await self._ensure()
        async with factory() as session, session.begin():
            result = await self._run(session, statement, bound)
            return list(result.scalars())

    # --- transactions --------------------------------------------------

    @contextlib.asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        """Open an explicit transaction yielding an :class:`AsyncSession`.

        Multiple statements share one transaction; the session is committed on
        normal exit and rolled back on any exception.
        """
        _, factory = await self._ensure()
        session = factory()
        try:
            async with session, session.begin():
                yield session
        except SQLAlchemyError as exc:
            raise self._wrap(exc, context={"phase": "transaction"}) from exc

    # --- health --------------------------------------------------------

    async def health(self) -> bool:
        """Return ``True`` if a ``SELECT 1`` succeeds."""
        try:
            result = await self.fetch_scalar(QuerySpec("SELECT 1"))
        except DatabaseError:
            return False
        return result == 1

    # --- internals -----------------------------------------------------

    def _prepare(
        self,
        query: QuerySpec | str,
        params: Mapping[str, Any] | Sequence[Any] | None,
    ) -> tuple[sa.TextClause, Mapping[str, Any] | Sequence[Any] | None]:
        """Normalize a query into a SQLAlchemy ``text()`` clause + params."""
        if isinstance(query, QuerySpec):
            statement = sa.text(query.text)
            bound = params if params is not None else query.params
        else:
            statement = sa.text(query)
            bound = params
        return statement, bound

    async def _run(
        self,
        session: AsyncSession,
        statement: sa.TextClause,
        params: Mapping[str, Any] | Sequence[Any] | None,
    ) -> sa.engine.Result[Any]:
        """Execute ``statement`` on ``session``, wrapping SQLAlchemy errors."""
        try:
            if self._settings.query_timeout is not None:
                return await session.execute(
                    statement, params, execution_options={"timeout": self._settings.query_timeout}
                )
            return await session.execute(statement, params)
        except SQLAlchemyError as exc:
            raise self._wrap(exc) from exc

    def _wrap(
        self, exc: SQLAlchemyError, *, context: Mapping[str, Any] | None = None
    ) -> DatabaseError:
        """Convert a SQLAlchemy error into a :class:`DatabaseError`."""
        ctx: dict[str, Any] = dict(context or {})
        ctx.setdefault("error_type", type(exc).__name__)
        self._logger.warning("database error: {}", exc)
        return DatabaseError(str(exc), context=ctx)
