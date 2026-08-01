"""HTTP response assertions for :class:`ApiResponse`.

All functions raise :class:`FrameworkAssertionError` on failure, carrying a
clear message and structured context (expected vs actual, url, etc.).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from framework.clients.http.models import ApiResponse
from framework.testing.assertions.base import fail
from framework.testing.assertions.json import assert_json_path, assert_json_path_exists

__all__ = [
    "assert_body_contains",
    "assert_header",
    "assert_header_contains",
    "assert_ok",
    "assert_response_json_path",
    "assert_response_json_path_exists",
    "assert_status",
    "assert_status_in",
]


def assert_status(response: ApiResponse, expected: int, *, message: str = "") -> None:
    """Assert the response status code equals ``expected``."""
    if response.status_code != expected:
        fail(
            message or f"Expected status {expected}, got {response.status_code}",
            context={
                "expected": expected,
                "actual": response.status_code,
                "url": response.url,
            },
        )


def assert_status_in(
    response: ApiResponse, expected_codes: Sequence[int], *, message: str = ""
) -> None:
    """Assert the response status code is in ``expected_codes``."""
    if response.status_code not in expected_codes:
        fail(
            message or f"Expected status in {list(expected_codes)}, got {response.status_code}",
            context={
                "expected": list(expected_codes),
                "actual": response.status_code,
                "url": response.url,
            },
        )


def assert_ok(response: ApiResponse, *, message: str = "") -> None:
    """Assert the response status code is 2xx."""
    if not response.ok:
        fail(
            message or f"Expected 2xx status, got {response.status_code}",
            context={"actual": response.status_code, "url": response.url},
        )


def assert_header(response: ApiResponse, name: str, value: str, *, message: str = "") -> None:
    """Assert a response header equals ``value`` (case-insensitive name)."""
    actual = _find_header(response, name)
    if actual is None:
        fail(
            message or f"Header not found: {name!r}",
            context={"header": name, "available": list(response.headers.keys())},
        )
    if actual != value:
        fail(
            message or f"Header {name!r}: expected {value!r}, got {actual!r}",
            context={"header": name, "expected": value, "actual": actual},
        )


def assert_header_contains(
    response: ApiResponse, name: str, substring: str, *, message: str = ""
) -> None:
    """Assert a response header contains ``substring`` (case-insensitive name)."""
    actual = _find_header(response, name)
    if actual is None:
        fail(
            message or f"Header not found: {name!r}",
            context={"header": name, "available": list(response.headers.keys())},
        )
    if substring not in actual:
        fail(
            message or f"Header {name!r} does not contain {substring!r}",
            context={"header": name, "substring": substring, "actual": actual},
        )


def assert_body_contains(response: ApiResponse, substring: str, *, message: str = "") -> None:
    """Assert the response body (decoded as text) contains ``substring``."""
    text = response.text
    if substring not in text:
        snippet = text[:200] if len(text) > 200 else text
        fail(
            message or f"Response body does not contain {substring!r}",
            context={"substring": substring, "body_snippet": snippet},
        )


def assert_response_json_path(
    response: ApiResponse, path: str, expected: Any, *, message: str = ""
) -> None:
    """Assert a JSON path in the response body equals ``expected``."""
    assert_json_path(response.json, path, expected, message=message)


def assert_response_json_path_exists(
    response: ApiResponse, path: str, *, message: str = ""
) -> None:
    """Assert a JSON path exists in the response body."""
    assert_json_path_exists(response.json, path, message=message)


def _find_header(response: ApiResponse, name: str) -> str | None:
    """Case-insensitive header lookup; returns ``None`` if not found."""
    lower = name.lower()
    for key, value in response.headers.items():
        if key.lower() == lower:
            return value
    return None
