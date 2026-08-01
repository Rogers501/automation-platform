"""Unit tests for database result assertions (using real Result/Row dataclasses)."""

from __future__ import annotations

from typing import Any

import pytest

from framework.clients.db.results import Result, Row
from framework.testing.assertions.base import FrameworkAssertionError
from framework.testing.assertions.database import (
    assert_column_value,
    assert_column_values,
    assert_row_contains,
    assert_row_count,
    assert_row_count_gt,
    assert_row_exists,
    assert_row_not_exists,
)


def _row(data: dict[str, Any]) -> Row:
    """Build a Row from a dict."""
    return Row(data)


def _result(rows: list[Row] | None = None, rowcount: int = -1) -> Result:
    """Build a Result from Rows."""
    return Result(rows=rows or [], rowcount=rowcount)


_ROWS = [
    _row({"id": 1, "name": "alice", "active": True}),
    _row({"id": 2, "name": "bob", "active": False}),
    _row({"id": 3, "name": "carol", "active": True}),
]


# --- assert_row_count ---


def test_row_count_equal() -> None:
    """assert_row_count passes on exact match."""
    assert_row_count(_result(_ROWS), 3)


def test_row_count_zero() -> None:
    """assert_row_count passes for empty result."""
    assert_row_count(_result(), 0)


def test_row_count_mismatch_fails() -> None:
    """assert_row_count fails on mismatch."""
    with pytest.raises(FrameworkAssertionError) as info:
        assert_row_count(_result(_ROWS), 5)
    assert "Expected 5 rows" in str(info.value)
    assert info.value.context["actual"] == 3


# --- assert_row_count_gt ---


def test_row_count_gt_passes() -> None:
    """assert_row_count_gt passes when count > minimum."""
    assert_row_count_gt(_result(_ROWS), 2)


def test_row_count_gt_fails() -> None:
    """assert_row_count_gt fails when count <= minimum."""
    with pytest.raises(FrameworkAssertionError):
        assert_row_count_gt(_result(_ROWS), 3)


def test_row_count_gt_empty_fails() -> None:
    """assert_row_count_gt fails on empty result."""
    with pytest.raises(FrameworkAssertionError):
        assert_row_count_gt(_result(), 0)


# --- assert_row_exists / not_exists ---


def test_row_exists_passes() -> None:
    """assert_row_exists passes when rows are present."""
    assert_row_exists(_result(_ROWS))


def test_row_exists_fails() -> None:
    """assert_row_exists fails on empty result."""
    with pytest.raises(FrameworkAssertionError):
        assert_row_exists(_result())


def test_row_not_exists_passes() -> None:
    """assert_row_not_exists passes on empty result."""
    assert_row_not_exists(_result())


def test_row_not_exists_fails() -> None:
    """assert_row_not_exists fails when rows are present."""
    with pytest.raises(FrameworkAssertionError):
        assert_row_not_exists(_result(_ROWS))


# --- assert_column_value ---


def test_column_value_first_row() -> None:
    """assert_column_value checks the first row by default."""
    assert_column_value(_result(_ROWS), "name", "alice")


def test_column_value_specific_row() -> None:
    """assert_column_value checks a specific row."""
    assert_column_value(_result(_ROWS), "name", "bob", row=1)
    assert_column_value(_result(_ROWS), "id", 3, row=2)


def test_column_value_mismatch_fails() -> None:
    """assert_column_value fails on value mismatch."""
    with pytest.raises(FrameworkAssertionError) as info:
        assert_column_value(_result(_ROWS), "name", "zzz")
    assert "expected 'zzz'" in str(info.value)


def test_column_value_row_out_of_range_fails() -> None:
    """assert_column_value fails when row index is out of range."""
    with pytest.raises(FrameworkAssertionError) as info:
        assert_column_value(_result(_ROWS), "name", "x", row=99)
    assert "out of range" in str(info.value)


def test_column_value_column_not_found_fails() -> None:
    """assert_column_value fails when the column doesn't exist."""
    with pytest.raises(FrameworkAssertionError) as info:
        assert_column_value(_result(_ROWS), "missing_col", 1)
    assert "not found" in str(info.value).lower()


def test_column_value_negative_index() -> None:
    """assert_column_value supports negative row indices."""
    assert_column_value(_result(_ROWS), "name", "carol", row=-1)


# --- assert_column_values ---


def test_column_values_match() -> None:
    """assert_column_values passes when all values match."""
    assert_column_values(_result(_ROWS), "id", [1, 2, 3])


def test_column_values_mismatch_fails() -> None:
    """assert_column_values fails on any mismatch."""
    with pytest.raises(FrameworkAssertionError):
        assert_column_values(_result(_ROWS), "id", [1, 2, 99])


def test_column_values_empty() -> None:
    """assert_column_values passes for empty result and empty expected."""
    assert_column_values(_result(), "id", [])


# --- assert_row_contains ---


def test_row_contains_subset() -> None:
    """assert_row_contains passes when the row is a superset."""
    assert_row_contains(_result(_ROWS), {"name": "alice", "active": True})


def test_row_contains_specific_row() -> None:
    """assert_row_contains checks a specific row."""
    assert_row_contains(_result(_ROWS), {"name": "bob"}, row=1)


def test_row_contains_mismatch_fails() -> None:
    """assert_row_contains fails on value mismatch."""
    with pytest.raises(FrameworkAssertionError):
        assert_row_contains(_result(_ROWS), {"name": "wrong"})


def test_row_contains_missing_key_fails() -> None:
    """assert_row_contains fails when a key is absent."""
    with pytest.raises(FrameworkAssertionError):
        assert_row_contains(_result(_ROWS), {"missing_key": 1})


def test_row_contains_row_out_of_range_fails() -> None:
    """assert_row_contains fails when row index is out of range."""
    with pytest.raises(FrameworkAssertionError):
        assert_row_contains(_result(_ROWS), {"name": "x"}, row=99)
