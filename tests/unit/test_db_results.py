"""Unit tests for database result/row conversion (no real DB)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from framework.clients.db.results import Result, Row, convert_result, convert_rows


class _FakeSAResult:
    """Minimal stand-in for sqlalchemy.engine.Result used by convert_result."""

    def __init__(
        self,
        mappings: list[Mapping[str, Any]],
        *,
        rowcount: int = -1,
        inserted_primary_key: tuple[Any, ...] | None = None,
    ) -> None:
        self._mappings = list(mappings)
        self.rowcount = rowcount
        self.inserted_primary_key = inserted_primary_key

    def mappings(self) -> _FakeSAResult:
        """Result.mappings() returns a MappingResult; here self suffices."""
        return self

    def fetchall(self) -> list[Mapping[str, Any]]:
        """Synchronous fetch of all rows (matches SA non-streaming behavior)."""
        return self._mappings


def test_row_get_and_index() -> None:
    """Row supports get() and bracket access by column name."""
    row = Row({"id": 1, "name": "alice"})
    assert row.get("id") == 1
    assert row["name"] == "alice"
    assert row.get("missing", "fallback") == "fallback"


def test_row_contains_and_as_dict() -> None:
    """Row supports ``in`` and returns a plain dict copy."""
    row = Row({"id": 1})
    assert "id" in row
    assert "x" not in row
    assert row.as_dict() == {"id": 1}


def test_row_as_dict_is_copy() -> None:
    """as_dict returns an independent dict."""
    row = Row({"id": 1})
    out = row.as_dict()
    out["id"] = 99
    assert row.get("id") == 1


def test_result_first_and_len() -> None:
    """Result.first returns the first row; len tracks row count."""
    rows = [Row({"id": 1}), Row({"id": 2})]
    result = Result(rows=rows, rowcount=2)
    assert result.first is rows[0]
    assert len(result) == 2


def test_result_first_none_when_empty() -> None:
    """An empty result has no first row."""
    assert Result().first is None
    assert len(Result()) == 0


def test_result_as_dicts() -> None:
    """as_dicts flattens rows to a list of plain dicts."""
    result = Result(rows=[Row({"id": 1}), Row({"id": 2})])
    assert result.as_dicts() == [{"id": 1}, {"id": 2}]


def test_convert_result_maps_rows() -> None:
    """convert_result materializes rows and preserves rowcount."""
    sa_result = _FakeSAResult(
        [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}],
        rowcount=2,
    )
    result = convert_result(sa_result)
    assert len(result) == 2
    assert result.rows[0].get("name") == "alice"
    assert result.rowcount == 2
    assert result.last_inserted_id is None


def test_convert_result_empty() -> None:
    """An empty SA result yields an empty framework result."""
    result = convert_result(_FakeSAResult([], rowcount=0))
    assert result.rows == []
    assert result.first is None


def test_convert_result_inserted_primary_key() -> None:
    """inserted_primary_key is surfaced as last_inserted_id (first column)."""
    sa_result = _FakeSAResult([], rowcount=1, inserted_primary_key=(42,))
    result = convert_result(sa_result)
    assert result.last_inserted_id == 42


def test_convert_result_missing_rowcount_defaults() -> None:
    """A result without rowcount reports -1 (unknown)."""
    sa_result = _FakeSAResult([{"id": 1}])  # rowcount not provided on instance
    del sa_result.rowcount  # type: ignore[attr-defined]
    result = convert_result(sa_result)
    assert result.rowcount == -1


def test_convert_result_no_rows_returns_empty() -> None:
    """A non-row-returning result (e.g. DDL) yields an empty rows list."""

    class _NoRowsResult(_FakeSAResult):
        def __init__(self, rowcount: int = -1) -> None:
            super().__init__([], rowcount=rowcount)
            self.returns_rows = False

    result = convert_result(_NoRowsResult(rowcount=0))
    assert result.rows == []
    assert result.rowcount == 0


def test_convert_rows_from_sequence() -> None:
    """convert_rows maps a sequence of mappings into Row objects."""
    rows = convert_rows([{"a": 1}, {"a": 2}])
    assert [r.get("a") for r in rows] == [1, 2]
