"""Database result assertions for :class:`Result` / :class:`Row`.

All functions raise :class:`FrameworkAssertionError` on failure with clear
messages and structured context (expected vs actual, row index, column name).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from framework.clients.db.results import Result
from framework.testing.assertions.base import fail, is_subset

__all__ = [
    "assert_column_value",
    "assert_column_values",
    "assert_row_contains",
    "assert_row_count",
    "assert_row_count_gt",
    "assert_row_exists",
    "assert_row_not_exists",
]


def assert_row_count(result: Result, expected: int, *, message: str = "") -> None:
    """Assert the number of rows equals ``expected``."""
    actual = len(result)
    if actual != expected:
        fail(
            message or f"Expected {expected} rows, got {actual}",
            context={"expected": expected, "actual": actual},
        )


def assert_row_count_gt(result: Result, minimum: int, *, message: str = "") -> None:
    """Assert the number of rows is strictly greater than ``minimum``."""
    actual = len(result)
    if actual <= minimum:
        fail(
            message or f"Expected more than {minimum} rows, got {actual}",
            context={"minimum": minimum, "actual": actual},
        )


def assert_row_exists(result: Result, *, message: str = "") -> None:
    """Assert at least one row exists."""
    if len(result) == 0:
        fail(message or "Expected at least one row, got 0", context={"actual": 0})


def assert_row_not_exists(result: Result, *, message: str = "") -> None:
    """Assert no rows exist."""
    actual = len(result)
    if actual > 0:
        fail(
            message or f"Expected no rows, got {actual}",
            context={"actual": actual},
        )


def assert_column_value(
    result: Result,
    column: str,
    expected: Any,
    *,
    row: int = 0,
    message: str = "",
) -> None:
    """Assert a column value in a specific row equals ``expected``.

    Args:
        result: The query result.
        column: Column name to check.
        expected: Expected value.
        row: Zero-based row index (default 0 = first row).
        message: Optional custom failure message.
    """
    if row >= len(result) or row < -len(result):
        fail(
            message or f"Row index {row} out of range (only {len(result)} rows)",
            context={"row": row, "row_count": len(result)},
        )
    actual_row = result.rows[row]
    if column not in actual_row:
        fail(
            message or f"Column not found: {column!r}",
            context={"column": column, "available": list(actual_row.as_dict().keys())},
        )
    actual = actual_row.get(column)
    if actual != expected:
        fail(
            message or (f"Column {column!r} in row {row}: expected {expected!r}, got {actual!r}"),
            context={
                "column": column,
                "row": row,
                "expected": expected,
                "actual": actual,
            },
        )


def assert_column_values(
    result: Result, column: str, expected: list[Any], *, message: str = ""
) -> None:
    """Assert all values in a column (across all rows) match ``expected``.

    The comparison is order-sensitive: row *i*'s column value must equal
    ``expected[i]``.
    """
    actual = [row.get(column) for row in result.rows]
    if actual != expected:
        fail(
            message or f"Column {column!r}: expected {expected!r}, got {actual!r}",
            context={"column": column, "expected": expected, "actual": actual},
        )


def assert_row_contains(
    result: Result,
    expected: Mapping[str, Any],
    *,
    row: int = 0,
    message: str = "",
) -> None:
    """Assert a specific row is a superset of ``expected`` key-value pairs.

    Args:
        result: The query result.
        expected: Key-value pairs that must all be present in the row.
        row: Zero-based row index (default 0 = first row).
        message: Optional custom failure message.
    """
    if row >= len(result) or row < -len(result):
        fail(
            message or f"Row index {row} out of range (only {len(result)} rows)",
            context={"row": row, "row_count": len(result)},
        )
    actual_row = result.rows[row]
    if not is_subset(expected, actual_row.as_dict()):
        fail(
            message or f"Row {row} does not contain expected key-value pairs",
            context={
                "row": row,
                "expected": dict(expected),
                "actual": actual_row.as_dict(),
            },
        )
