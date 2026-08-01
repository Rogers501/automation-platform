"""Result conversion: SQLAlchemy rows into framework data structures.

``Row`` exposes column access by name and index; ``Result`` bundles the rows
with a row count. Conversion reads synchronously from a SQLAlchemy
:class:`Result` (after the async ``execute`` returns), so the client can
materialize rows before the session closes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import SQLAlchemyError

if TYPE_CHECKING:
    import sqlalchemy as sa

__all__ = ["Result", "Row", "convert_result"]


@dataclass(frozen=True)
class Row:
    """A single result row keyed by column name.

    Provides dict-like and attribute-free access to keep the surface small and
    predictable for assertions in tests.
    """

    data: Mapping[str, Any]

    def get(self, key: str, default: Any = None) -> Any:
        """Return the column value for ``key`` or ``default`` if absent."""
        return self.data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __contains__(self, key: object) -> bool:
        return key in self.data

    def as_dict(self) -> dict[str, Any]:
        """Return a plain dict copy of the row."""
        return dict(self.data)


@dataclass(frozen=True)
class Result:
    """A query result: rows plus metadata.

    Attributes:
        rows: Materialized rows (empty for non-row-returning statements).
        rowcount: Rows affected, or ``-1`` when the driver does not report it.
        last_inserted_id: Last autoincrement id, when available.
    """

    rows: list[Row] = field(default_factory=list)
    rowcount: int = -1
    last_inserted_id: Any | None = None

    @property
    def first(self) -> Row | None:
        """The first row, or ``None`` when there are no rows."""
        return self.rows[0] if self.rows else None

    def as_dicts(self) -> list[dict[str, Any]]:
        """Return all rows as plain dicts."""
        return [row.as_dict() for row in self.rows]

    def __len__(self) -> int:
        return len(self.rows)


def convert_result(result: sa.engine.Result[Any]) -> Result:
    """Convert a SQLAlchemy :class:`Result` into a framework :class:`Result`.

    Reads mappings eagerly so the result is safe to use after the session
    closes. ``rowcount`` and ``inserted_primary_key`` are best-effort.
    """
    if getattr(result, "returns_rows", True):
        rows = [Row(dict(mapping)) for mapping in result.mappings().fetchall()]
    else:
        rows = []
    rowcount = getattr(result, "rowcount", -1)
    inserted = None
    try:
        insert_pk = result.inserted_primary_key  # type: ignore[attr-defined]
    except (AttributeError, SQLAlchemyError):
        # inserted_primary_key raises InvalidRequestError for non-INSERT
        # statements (DDL/UPDATE/SELECT); treat as "no inserted id".
        insert_pk = None
    if insert_pk:
        # inserted_primary_key is a Row/sequence; take the first column value.
        try:
            inserted = insert_pk[0] if len(insert_pk) > 0 else None
        except TypeError:
            inserted = None
    return Result(rows=rows, rowcount=rowcount, last_inserted_id=inserted)


def convert_rows(rows: Sequence[Mapping[str, Any]]) -> list[Row]:
    """Convert a sequence of mappings into :class:`Row` objects."""
    return [Row(mapping) for mapping in rows]
