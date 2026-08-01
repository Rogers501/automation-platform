"""Test data lifecycle management (setup / teardown / seeding / cleanup).

Provides :class:`DataLifecycle`, an async context manager that executes seed
SQL on enter and cleanup SQL on exit via a :class:`DatabaseClient`. SQL can
be supplied inline or loaded from directories of ``.sql`` files (executed in
sorted filename order for deterministic results).

Cleanup is best-effort: a failure during teardown is logged but never masks
the original test failure (consistent with artifact persistence, rule 12).

Layering: depends on ``core`` (logger, exceptions) and ``clients.db``
(DatabaseClient). Never depends on ``testing.assertions`` or business code
(rule 11).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from framework.core.exceptions import FrameworkError
from framework.core.logger import get_logger

if TYPE_CHECKING:
    from framework.clients.db.client import DatabaseClient

__all__ = [
    "DataLifecycle",
    "DataLifecycleError",
    "load_sql_files",
    "split_statements",
]

_LOGGER = get_logger("data_lifecycle")

_LINE_COMMENT_RE = re.compile(r"--[^\n]*")


class DataLifecycleError(FrameworkError):
    """Raised when test data setup or teardown fails."""


def split_statements(sql_text: str) -> list[str]:
    """Split a multi-statement SQL string into individual statements.

    Respects single-quoted strings (so semicolons inside string literals are
    not treated as delimiters) and strips ``--`` line comments.

    Args:
        sql_text: Raw SQL potentially containing multiple statements.

    Returns:
        A list of trimmed, non-empty SQL statements.
    """
    cleaned = _LINE_COMMENT_RE.sub("", sql_text)
    statements: list[str] = []
    current: list[str] = []
    in_quote = False
    for char in cleaned:
        if char == "'":
            in_quote = not in_quote
            current.append(char)
        elif char == ";" and not in_quote:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(char)
    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return statements


def load_sql_files(
    directory: Path,
    *,
    pattern: str = "*.sql",
) -> list[tuple[str, str]]:
    """Load SQL files from ``directory``, sorted by filename.

    Args:
        directory: Directory containing ``.sql`` files.
        pattern: Glob pattern (default ``"*.sql"``).

    Returns:
        A list of ``(filename, sql_text)`` tuples, sorted by filename.
    """
    files = sorted(directory.glob(pattern), key=lambda p: p.name)
    return [(f.name, f.read_text(encoding="utf-8")) for f in files]


class DataLifecycle:
    """Async context manager for test data setup and teardown.

    Executes seed SQL on ``__aenter__`` and cleanup SQL on ``__aexit__``
    via the wrapped :class:`DatabaseClient`.

    Args:
        db: The database client used to execute SQL.
        setup_sql: Optional inline SQL to run on enter.
        teardown_sql: Optional inline SQL to run on exit.
        seed_dir: Optional directory of ``.sql`` files to run on enter.
        cleanup_dir: Optional directory of ``.sql`` files to run on exit.
    """

    def __init__(
        self,
        db: DatabaseClient,
        *,
        setup_sql: str | None = None,
        teardown_sql: str | None = None,
        seed_dir: Path | None = None,
        cleanup_dir: Path | None = None,
    ) -> None:
        self._db = db
        self._setup_sql = setup_sql
        self._teardown_sql = teardown_sql
        self._seed_dir = seed_dir
        self._cleanup_dir = cleanup_dir

    async def _run_sql(self, sql: str, *, phase: str) -> None:
        """Execute one or more SQL statements (split by semicolon)."""
        for stmt in split_statements(sql):
            try:
                await self._db.execute(stmt)
            except Exception as exc:
                raise DataLifecycleError(
                    f"Data lifecycle {phase} failed: {exc}",
                    context={"phase": phase, "sql": stmt[:200]},
                ) from exc

    async def _run_dir(self, directory: Path, *, phase: str) -> None:
        """Execute all SQL files in a directory in sorted order."""
        if not directory.exists():
            _LOGGER.warning("SQL directory not found for {}: {}", phase, directory)
            return
        for filename, sql_text in load_sql_files(directory):
            _LOGGER.debug("Executing {} from {}", filename, phase)
            await self._run_sql(sql_text, phase=phase)

    async def setup(self) -> None:
        """Execute seed SQL (inline + directory)."""
        if self._seed_dir is not None:
            await self._run_dir(self._seed_dir, phase="setup")
        if self._setup_sql is not None:
            await self._run_sql(self._setup_sql, phase="setup")

    async def teardown(self) -> None:
        """Execute cleanup SQL (inline + directory). Best-effort."""
        errors: list[str] = []
        if self._teardown_sql is not None:
            try:
                await self._run_sql(self._teardown_sql, phase="teardown")
            except DataLifecycleError as exc:
                errors.append(str(exc))
        if self._cleanup_dir is not None:
            try:
                await self._run_dir(self._cleanup_dir, phase="teardown")
            except DataLifecycleError as exc:
                errors.append(str(exc))
        if errors:
            _LOGGER.warning("Teardown completed with errors: {}", "; ".join(errors))

    async def execute(self, sql: str) -> None:
        """Execute ad-hoc SQL during the lifecycle scope."""
        await self._run_sql(sql, phase="runtime")

    async def __aenter__(self) -> DataLifecycle:
        await self.setup()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.teardown()
