"""Unit tests for JSON assertions (path, exists, type, contains, length)."""

from __future__ import annotations

from typing import Any

import pytest

from framework.testing.assertions.base import FrameworkAssertionError
from framework.testing.assertions.json import (
    assert_json_contains,
    assert_json_length,
    assert_json_path,
    assert_json_path_exists,
    assert_json_path_not_exists,
    assert_json_path_type,
)

_DATA: Any = {
    "id": 42,
    "name": "alice",
    "active": True,
    "tags": ["dev", "test"],
    "items": [{"sku": "A1"}, {"sku": "B2"}],
    "meta": {"created": "2024-01-01", "count": 3},
}


# --- assert_json_path ---


def test_json_path_equal() -> None:
    """assert_json_path passes when the value matches."""
    assert_json_path(_DATA, "$.id", 42)


def test_json_path_nested() -> None:
    """assert_json_path resolves nested paths."""
    assert_json_path(_DATA, "$.meta.created", "2024-01-01")


def test_json_path_array() -> None:
    """assert_json_path resolves array indices."""
    assert_json_path(_DATA, "$.items[0].sku", "A1")


def test_json_path_not_equal_fails() -> None:
    """assert_json_path fails when the value doesn't match."""
    with pytest.raises(FrameworkAssertionError) as info:
        assert_json_path(_DATA, "$.id", 99)
    assert "expected 99" in str(info.value)
    assert info.value.context["path"] == "$.id"


def test_json_path_not_found_fails() -> None:
    """assert_json_path fails when the path doesn't exist."""
    with pytest.raises(FrameworkAssertionError) as info:
        assert_json_path(_DATA, "$.missing", 1)
    assert "not found" in str(info.value)


def test_json_path_custom_message() -> None:
    """Custom message is used on failure."""
    with pytest.raises(FrameworkAssertionError, match="my custom"):
        assert_json_path(_DATA, "$.id", 99, message="my custom message")


# --- assert_json_path_exists / not_exists ---


def test_json_path_exists_passes() -> None:
    """assert_json_path_exists passes when the path exists."""
    assert_json_path_exists(_DATA, "$.name")


def test_json_path_exists_fails() -> None:
    """assert_json_path_exists fails when the path doesn't exist."""
    with pytest.raises(FrameworkAssertionError):
        assert_json_path_exists(_DATA, "$.nonexistent")


def test_json_path_not_exists_passes() -> None:
    """assert_json_path_not_exists passes when the path doesn't exist."""
    assert_json_path_not_exists(_DATA, "$.nonexistent")


def test_json_path_not_exists_fails() -> None:
    """assert_json_path_not_exists fails when the path exists."""
    with pytest.raises(FrameworkAssertionError):
        assert_json_path_not_exists(_DATA, "$.name")


# --- assert_json_path_type ---


def test_json_path_type_correct() -> None:
    """assert_json_path_type passes when the type matches."""
    assert_json_path_type(_DATA, "$.id", int)
    assert_json_path_type(_DATA, "$.name", str)
    assert_json_path_type(_DATA, "$.tags", list)
    assert_json_path_type(_DATA, "$.active", bool)


def test_json_path_type_incorrect_fails() -> None:
    """assert_json_path_type fails when the type doesn't match."""
    with pytest.raises(FrameworkAssertionError) as info:
        assert_json_path_type(_DATA, "$.id", str)
    assert "expected type str" in str(info.value)


def test_json_path_type_not_found_fails() -> None:
    """assert_json_path_type fails when the path doesn't exist."""
    with pytest.raises(FrameworkAssertionError):
        assert_json_path_type(_DATA, "$.missing", int)


# --- assert_json_contains ---


def test_json_contains_subset() -> None:
    """assert_json_contains passes when data is a superset."""
    assert_json_contains(_DATA, {"id": 42, "name": "alice"})


def test_json_contains_nested() -> None:
    """assert_json_contains checks nested dicts."""
    assert_json_contains(_DATA, {"meta": {"count": 3}})


def test_json_contains_mismatch_fails() -> None:
    """assert_json_contains fails on value mismatch."""
    with pytest.raises(FrameworkAssertionError):
        assert_json_contains(_DATA, {"id": 99})


def test_json_contains_missing_key_fails() -> None:
    """assert_json_contains fails on missing key."""
    with pytest.raises(FrameworkAssertionError):
        assert_json_contains(_DATA, {"missing": 1})


# --- assert_json_length ---


def test_json_length_list() -> None:
    """assert_json_length checks list length."""
    assert_json_length(_DATA, "$.tags", 2)


def test_json_length_string() -> None:
    """assert_json_length checks string length."""
    assert_json_length(_DATA, "$.name", 5)


def test_json_length_dict() -> None:
    """assert_json_length checks dict key count."""
    assert_json_length(_DATA, "$.meta", 2)


def test_json_length_mismatch_fails() -> None:
    """assert_json_length fails on wrong length."""
    with pytest.raises(FrameworkAssertionError) as info:
        assert_json_length(_DATA, "$.tags", 99)
    assert "expected length 99" in str(info.value)


def test_json_length_non_sized_fails() -> None:
    """assert_json_length fails when the value has no length."""
    with pytest.raises(FrameworkAssertionError) as info:
        assert_json_length(_DATA, "$.id", 1)
    assert "no length" in str(info.value)


def test_json_length_not_found_fails() -> None:
    """assert_json_length fails when the path doesn't exist."""
    with pytest.raises(FrameworkAssertionError):
        assert_json_length(_DATA, "$.missing", 1)
