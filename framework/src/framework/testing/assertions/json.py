"""JSON assertions: path resolution, existence, type, subset, length.

All functions operate on parsed JSON (dict / list / scalar), not raw strings.
Path syntax uses :func:`resolve_json_path` (``$.a.b[0].c``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from framework.testing.assertions.base import fail, is_subset, resolve_json_path

__all__ = [
    "assert_json_contains",
    "assert_json_length",
    "assert_json_path",
    "assert_json_path_exists",
    "assert_json_path_not_exists",
    "assert_json_path_type",
]


def assert_json_path(data: Any, path: str, expected: Any, *, message: str = "") -> None:
    """Assert the value at JSON ``path`` equals ``expected``."""
    found, value = resolve_json_path(data, path)
    if not found:
        fail(message or f"JSON path not found: {path!r}", context={"path": path})
    if value != expected:
        fail(
            message or f"JSON path {path!r}: expected {expected!r}, got {value!r}",
            context={"path": path, "expected": expected, "actual": value},
        )


def assert_json_path_exists(data: Any, path: str, *, message: str = "") -> None:
    """Assert that JSON ``path`` exists (resolves to a value)."""
    found, _ = resolve_json_path(data, path)
    if not found:
        fail(message or f"JSON path not found: {path!r}", context={"path": path})


def assert_json_path_not_exists(data: Any, path: str, *, message: str = "") -> None:
    """Assert that JSON ``path`` does **not** exist."""
    found, _ = resolve_json_path(data, path)
    if found:
        fail(
            message or f"JSON path should not exist but does: {path!r}",
            context={"path": path},
        )


def assert_json_path_type(data: Any, path: str, expected_type: type, *, message: str = "") -> None:
    """Assert the value at JSON ``path`` is an instance of ``expected_type``."""
    found, value = resolve_json_path(data, path)
    if not found:
        fail(message or f"JSON path not found: {path!r}", context={"path": path})
    if not isinstance(value, expected_type):
        actual_type = type(value).__name__
        fail(
            message
            or (f"JSON path {path!r}: expected type {expected_type.__name__}, got {actual_type}"),
            context={
                "path": path,
                "expected_type": expected_type.__name__,
                "actual_type": actual_type,
            },
        )


def assert_json_contains(data: Any, expected: Mapping[str, Any], *, message: str = "") -> None:
    """Assert ``data`` is a superset of ``expected`` (recursive subset match).

    Every key in ``expected`` must exist in ``data`` with a matching value.
    Nested dicts are checked recursively; non-dict values use direct equality.
    """
    if not is_subset(expected, data):
        fail(
            message or "Data does not contain all expected key-value pairs",
            context={"expected": dict(expected)},
        )


def assert_json_length(data: Any, path: str, expected_length: int, *, message: str = "") -> None:
    """Assert the length of the value at JSON ``path`` equals ``expected_length``."""
    found, value = resolve_json_path(data, path)
    if not found:
        fail(message or f"JSON path not found: {path!r}", context={"path": path})
    if not isinstance(value, str | list | dict):
        fail(
            message or (f"JSON path {path!r} value has no length (got {type(value).__name__})"),
            context={"path": path, "type": type(value).__name__},
        )
    actual_length = len(value)
    if actual_length != expected_length:
        fail(
            message
            or (f"JSON path {path!r}: expected length {expected_length}, got {actual_length}"),
            context={
                "path": path,
                "expected": expected_length,
                "actual": actual_length,
            },
        )
