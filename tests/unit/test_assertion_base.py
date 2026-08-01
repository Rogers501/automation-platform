"""Unit tests for assertion base: error type, fail, resolve_json_path, is_subset."""

from __future__ import annotations

from typing import Any

import pytest

from framework.testing.assertions.base import (
    FrameworkAssertionError,
    fail,
    is_subset,
    resolve_json_path,
)

# --- FrameworkAssertionError ---


def test_error_message_and_context() -> None:
    """FrameworkAssertionError stores message and context."""
    err = FrameworkAssertionError("boom", context={"key": "value"})
    assert err.message == "boom"
    assert err.context == {"key": "value"}


def test_error_default_context_empty() -> None:
    """Omitting context yields an empty dict."""
    err = FrameworkAssertionError("boom")
    assert err.context == {}


def test_error_is_assertion_error() -> None:
    """FrameworkAssertionError is an AssertionError (pytest compatibility)."""
    err = FrameworkAssertionError("x")
    assert isinstance(err, AssertionError)


def test_error_str_with_context() -> None:
    """str includes context pairs."""
    err = FrameworkAssertionError("fail", context={"a": 1})
    assert "a=1" in str(err)


def test_error_str_without_context() -> None:
    """str is just the message when context is empty."""
    assert str(FrameworkAssertionError("fail")) == "fail"


def test_error_caught_as_assertion_error() -> None:
    """FrameworkAssertionError is catchable as AssertionError."""
    with pytest.raises(AssertionError):
        raise FrameworkAssertionError("x")


# --- fail() ---


def test_fail_raises() -> None:
    """fail() raises FrameworkAssertionError."""
    with pytest.raises(FrameworkAssertionError) as info:
        fail("custom message", context={"a": 1})
    assert info.value.message == "custom message"
    assert info.value.context == {"a": 1}


# --- resolve_json_path ---


def test_resolve_root() -> None:
    """$ or empty path returns the root data."""
    data: Any = {"a": 1}
    assert resolve_json_path(data, "$") == (True, data)
    assert resolve_json_path(data, "") == (True, data)


def test_resolve_simple_field() -> None:
    """$.field resolves a top-level dict field."""
    assert resolve_json_path({"name": "alice"}, "$.name") == (True, "alice")


def test_resolve_nested_field() -> None:
    """$.a.b.c resolves nested dict fields."""
    data = {"a": {"b": {"c": 42}}}
    assert resolve_json_path(data, "$.a.b.c") == (True, 42)


def test_resolve_array_index() -> None:
    """$.items[0] resolves an array index."""
    data = {"items": [10, 20, 30]}
    assert resolve_json_path(data, "$.items[0]") == (True, 10)
    assert resolve_json_path(data, "$.items[2]") == (True, 30)


def test_resolve_mixed_path() -> None:
    """$.users[0].name resolves a mixed dict/array path."""
    data = {"users": [{"name": "alice"}, {"name": "bob"}]}
    assert resolve_json_path(data, "$.users[0].name") == (True, "alice")
    assert resolve_json_path(data, "$.users[1].name") == (True, "bob")


def test_resolve_missing_field() -> None:
    """Missing field returns (False, None)."""
    found, value = resolve_json_path({"a": 1}, "$.b")
    assert found is False
    assert value is None


def test_resolve_missing_nested() -> None:
    """Missing nested field returns (False, None)."""
    found, value = resolve_json_path({"a": {"b": 1}}, "$.a.c")
    assert found is False
    assert value is None


def test_resolve_index_out_of_range() -> None:
    """Array index out of range returns (False, None)."""
    found, value = resolve_json_path({"items": [1]}, "$.items[5]")
    assert found is False
    assert value is None


def test_resolve_index_on_non_list() -> None:
    """Indexing a non-list returns (False, None)."""
    found, value = resolve_json_path({"a": 1}, "$.a[0]")
    assert found is False
    assert value is None


def test_resolve_field_on_non_dict() -> None:
    """Accessing a field on a non-dict returns (False, None)."""
    found, value = resolve_json_path({"a": 1}, "$.a.b")
    assert found is False
    assert value is None


def test_resolve_without_dollar() -> None:
    """Path without $ prefix also works."""
    assert resolve_json_path({"a": {"b": 2}}, "a.b") == (True, 2)


def test_resolve_deep_array() -> None:
    """$.matrix[0][1] resolves nested arrays."""
    data = {"matrix": [[1, 2], [3, 4]]}
    assert resolve_json_path(data, "$.matrix[0][1]") == (True, 2)
    assert resolve_json_path(data, "$.matrix[1][0]") == (True, 3)


# --- is_subset ---


def test_is_subset_flat_dict() -> None:
    """Flat dict subset matching."""
    assert is_subset({"a": 1}, {"a": 1, "b": 2}) is True
    assert is_subset({"a": 1}, {"a": 2}) is False


def test_is_subset_nested() -> None:
    """Nested dict subset matching."""
    expected = {"user": {"name": "alice"}}
    actual = {"user": {"name": "alice", "age": 30}, "id": 1}
    assert is_subset(expected, actual) is True


def test_is_subset_missing_key() -> None:
    """Missing key in actual returns False."""
    assert is_subset({"c": 3}, {"a": 1}) is False


def test_is_subset_scalar() -> None:
    """Non-dict values use direct equality."""
    assert is_subset(42, 42) is True
    assert is_subset(42, 43) is False
    assert is_subset("hello", "hello") is True


def test_is_subset_empty_expected() -> None:
    """Empty expected dict is a subset of anything."""
    assert is_subset({}, {"a": 1}) is True


def test_is_subset_nested_mismatch() -> None:
    """Nested value mismatch returns False."""
    assert is_subset({"a": {"b": 1}}, {"a": {"b": 2}}) is False
