"""Assertion library: response, JSON, schema, and database assertions.

All assertions raise :class:`FrameworkAssertionError` (an
:class:`AssertionError` subclass) on failure, making them fully
pytest-compatible. Each failure carries a clear human-readable message plus a
structured ``context`` dict for diagnostics and downstream AI analysis.

Usage::

    from framework.testing.assertions import (
        assert_status, assert_json_path, assert_schema, assert_row_count,
    )

    assert_status(response, 200)
    assert_json_path(response.json, "$.data.id", 42)
    assert_schema(response.json, {"type": "object", "required": ["id"]})
    assert_row_count(db_result, 3)
"""

from framework.testing.assertions.base import (
    FrameworkAssertionError,
    fail,
    is_subset,
    resolve_json_path,
)
from framework.testing.assertions.database import (
    assert_column_value,
    assert_column_values,
    assert_row_contains,
    assert_row_count,
    assert_row_count_gt,
    assert_row_exists,
    assert_row_not_exists,
)
from framework.testing.assertions.json import (
    assert_json_contains,
    assert_json_length,
    assert_json_path,
    assert_json_path_exists,
    assert_json_path_not_exists,
    assert_json_path_type,
)
from framework.testing.assertions.response import (
    assert_body_contains,
    assert_header,
    assert_header_contains,
    assert_ok,
    assert_response_json_path,
    assert_response_json_path_exists,
    assert_status,
    assert_status_in,
)
from framework.testing.assertions.schema import assert_schema

__all__ = [
    "FrameworkAssertionError",
    "assert_body_contains",
    "assert_column_value",
    "assert_column_values",
    "assert_header",
    "assert_header_contains",
    "assert_json_contains",
    "assert_json_length",
    "assert_json_path",
    "assert_json_path_exists",
    "assert_json_path_not_exists",
    "assert_json_path_type",
    "assert_ok",
    "assert_response_json_path",
    "assert_response_json_path_exists",
    "assert_row_contains",
    "assert_row_count",
    "assert_row_count_gt",
    "assert_row_exists",
    "assert_row_not_exists",
    "assert_schema",
    "assert_status",
    "assert_status_in",
    "fail",
    "is_subset",
    "resolve_json_path",
]
