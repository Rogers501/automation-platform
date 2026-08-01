"""Unit tests for HTTP response assertions (using real ApiResponse dataclass)."""

from __future__ import annotations

import pytest

from framework.clients.http.models import ApiResponse
from framework.testing.assertions.base import FrameworkAssertionError
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


def _response(
    status_code: int = 200,
    body: bytes = b'{"id": 42, "name": "alice"}',
    headers: dict[str, str] | None = None,
) -> ApiResponse:
    """Build a minimal ApiResponse for testing."""
    return ApiResponse(
        status_code=status_code,
        headers=headers or {"Content-Type": "application/json", "X-Request-Id": "abc123"},
        body=body,
        url="http://test.example.com/api",
        method="GET",
        elapsed_seconds=0.01,
    )


# --- assert_status ---


def test_status_equal() -> None:
    """assert_status passes on exact match."""
    assert_status(_response(200), 200)


def test_status_not_equal_fails() -> None:
    """assert_status fails on mismatch."""
    with pytest.raises(FrameworkAssertionError) as info:
        assert_status(_response(404), 200)
    assert "Expected status 200" in str(info.value)
    assert info.value.context["actual"] == 404


# --- assert_status_in ---


def test_status_in_found() -> None:
    """assert_status_in passes when code is in the set."""
    assert_status_in(_response(201), [200, 201, 202])


def test_status_in_not_found_fails() -> None:
    """assert_status_in fails when code is not in the set."""
    with pytest.raises(FrameworkAssertionError):
        assert_status_in(_response(404), [200, 201])


# --- assert_ok ---


def test_ok_2xx() -> None:
    """assert_ok passes for 2xx."""
    assert_ok(_response(200))
    assert_ok(_response(204))


def test_ok_non_2xx_fails() -> None:
    """assert_ok fails for non-2xx."""
    with pytest.raises(FrameworkAssertionError):
        assert_ok(_response(500))


# --- assert_header ---


def test_header_equal() -> None:
    """assert_header passes on exact match."""
    assert_header(_response(), "Content-Type", "application/json")


def test_header_case_insensitive() -> None:
    """assert_header looks up header names case-insensitively."""
    assert_header(_response(), "content-type", "application/json")


def test_header_not_found_fails() -> None:
    """assert_header fails when the header is absent."""
    with pytest.raises(FrameworkAssertionError) as info:
        assert_header(_response(), "X-Missing", "value")
    assert "not found" in str(info.value).lower()


def test_header_value_mismatch_fails() -> None:
    """assert_header fails when the value doesn't match."""
    with pytest.raises(FrameworkAssertionError):
        assert_header(_response(), "Content-Type", "text/plain")


# --- assert_header_contains ---


def test_header_contains_passes() -> None:
    """assert_header_contains passes when substring is present."""
    assert_header_contains(_response(), "Content-Type", "json")


def test_header_contains_fails() -> None:
    """assert_header_contains fails when substring is absent."""
    with pytest.raises(FrameworkAssertionError):
        assert_header_contains(_response(), "Content-Type", "xml")


# --- assert_body_contains ---


def test_body_contains_passes() -> None:
    """assert_body_contains passes when substring is in the body."""
    assert_body_contains(_response(200, b'{"id": 42}'), "id")


def test_body_contains_fails() -> None:
    """assert_body_contains fails when substring is not in the body."""
    with pytest.raises(FrameworkAssertionError) as info:
        assert_body_contains(_response(200, b'{"id": 42}'), "missing")
    assert "does not contain" in str(info.value)


# --- assert_response_json_path ---


def test_response_json_path_passes() -> None:
    """assert_response_json_path passes when the value matches."""
    assert_response_json_path(_response(), "$.id", 42)


def test_response_json_path_nested() -> None:
    """assert_response_json_path resolves nested paths."""
    body = b'{"data": {"user": {"id": 7}}}'
    assert_response_json_path(_response(200, body), "$.data.user.id", 7)


def test_response_json_path_fails() -> None:
    """assert_response_json_path fails on mismatch."""
    with pytest.raises(FrameworkAssertionError):
        assert_response_json_path(_response(), "$.id", 99)


# --- assert_response_json_path_exists ---


def test_response_json_path_exists_passes() -> None:
    """assert_response_json_path_exists passes when path exists."""
    assert_response_json_path_exists(_response(), "$.name")


def test_response_json_path_exists_fails() -> None:
    """assert_response_json_path_exists fails when path doesn't exist."""
    with pytest.raises(FrameworkAssertionError):
        assert_response_json_path_exists(_response(), "$.missing")
