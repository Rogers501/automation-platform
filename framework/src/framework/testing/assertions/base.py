"""Assertion foundation: error type, fail helper, JSON path resolver.

``FrameworkAssertionError`` inherits from :class:`AssertionError` so pytest
reports assertion failures as *failures* (not errors), while still carrying
a structured ``context`` dict for diagnostics and downstream AI analysis.

``resolve_json_path`` supports dot-notation paths (``$.a.b[0].c``) without
any external dependency. ``is_subset`` performs recursive dict-subset matching
for ``assert_json_contains`` / ``assert_row_contains``.
"""

from __future__ import annotations

import re
from typing import Any, NoReturn

__all__ = ["FrameworkAssertionError", "fail", "is_subset", "resolve_json_path"]


class FrameworkAssertionError(AssertionError):
    """Assertion error with structured context for diagnostics and AI analysis.

    Inherits from :class:`AssertionError` so pytest treats it as a test
    *failure* rather than an *error*.

    Args:
        message: Human-readable description of what went wrong.
        context: Optional structured key/value pairs (expected vs actual,
            path, url, etc.) for debugging and downstream analysis.
    """

    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message: str = message
        self.context: dict[str, Any] = dict(context or {})

    def __str__(self) -> str:
        if self.context:
            pairs = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
            return f"{self.message} ({pairs})"
        return self.message


def fail(message: str, *, context: dict[str, Any] | None = None) -> NoReturn:
    """Raise a :class:`FrameworkAssertionError` with a clear message and context.

    Args:
        message: Human-readable failure description.
        context: Structured key/value pairs for diagnostics.
    """
    raise FrameworkAssertionError(message, context=context)


#: Matches ``.field`` or ``[index]`` segments in a JSON path.
_SEGMENT_RE = re.compile(r"(?:^|\.)([^.\[\]]+)|\[(\d+)\]")


def resolve_json_path(data: Any, path: str) -> tuple[bool, Any]:
    """Resolve a JSON path (``$.a.b[0].c``) against ``data``.

    Supports dot-notation for dict fields and ``[N]`` for list indices.
    Wildcards (``[*]``) are not supported in this version.

    Args:
        data: The parsed JSON value (dict, list, scalar).
        path: A JSON path starting with ``$`` or ``.`` or bare field name.

    Returns:
        ``(found, value)`` — ``found`` is ``False`` if any segment is absent.
    """
    if not path or path == "$":
        return True, data

    normalized = path
    if normalized.startswith("$"):
        normalized = normalized[1:]
    if normalized.startswith("."):
        normalized = normalized[1:]

    if not normalized:
        return True, data

    current: Any = data
    for match in _SEGMENT_RE.finditer(normalized):
        field, index = match.group(1), match.group(2)
        if field is not None:
            if not isinstance(current, dict) or field not in current:
                return False, None
            current = current[field]
        elif index is not None:
            idx = int(index)
            if not isinstance(current, list) or idx < 0 or idx >= len(current):
                return False, None
            current = current[idx]

    return True, current


def is_subset(expected: Any, actual: Any) -> bool:
    """Check whether ``actual`` contains all of ``expected``'s key-value pairs.

    Recursively descends into nested dicts. For non-dict values, performs
    direct equality. Used by ``assert_json_contains`` and
    ``assert_row_contains``.

    Args:
        expected: The subset to look for.
        actual: The superset to search in.

    Returns:
        ``True`` if every key in ``expected`` exists in ``actual`` with a
        matching (recursively subset) value.
    """
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key, value in expected.items():
            if key not in actual:
                return False
            if not is_subset(value, actual[key]):
                return False
        return True
    return bool(expected == actual)
