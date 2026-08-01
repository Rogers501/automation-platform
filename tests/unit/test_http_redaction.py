"""Unit tests for HTTP header/body redaction helpers."""

from __future__ import annotations

from framework.clients.http.redaction import (
    DEFAULT_SENSITIVE_HEADERS,
    redact_headers,
    truncate_body,
)


def test_default_sensitive_headers_present() -> None:
    """The default set masks auth/cookie/api-key headers."""
    assert "authorization" in DEFAULT_SENSITIVE_HEADERS
    assert "cookie" in DEFAULT_SENSITIVE_HEADERS
    assert "set-cookie" in DEFAULT_SENSITIVE_HEADERS


def test_redact_headers_masks_sensitive() -> None:
    """Sensitive headers are replaced with a redaction marker."""
    out = redact_headers({"Authorization": "Bearer s3cret", "Accept": "application/json"})
    assert out["Authorization"] == "***REDACTED***"
    assert out["Accept"] == "application/json"


def test_redact_headers_case_insensitive() -> None:
    """Header name matching is case-insensitive."""
    out = redact_headers({"AUTHORIZATION": "x", "Cookie": "y"})
    assert out["AUTHORIZATION"] == "***REDACTED***"
    assert out["Cookie"] == "***REDACTED***"


def test_redact_headers_custom_set() -> None:
    """A custom sensitive iterable is honored."""
    out = redact_headers({"X-Trace": "1", "Accept": "*/*"}, sensitive={"x-trace"})
    assert out["X-Trace"] == "***REDACTED***"
    assert out["Accept"] == "*/*"


def test_redact_headers_returns_copy() -> None:
    """The input dict is not mutated."""
    original = {"Authorization": "Bearer x"}
    out = redact_headers(original)
    assert original["Authorization"] == "Bearer x"
    assert out["Authorization"] == "***REDACTED***"


def test_truncate_body_short_text_unchanged() -> None:
    """Text within the limit is returned unchanged."""
    assert truncate_body("short", 100) == "short"


def test_truncate_body_long_text_cut() -> None:
    """Text beyond the limit is cut and marked."""
    out = truncate_body("a" * 50, 10)
    assert out.startswith("a" * 10)
    assert out.endswith("...(truncated)")


def test_truncate_body_disabled() -> None:
    """A non-positive max_length returns the full text."""
    assert truncate_body("a" * 50, 0) == "a" * 50
    assert truncate_body("a" * 50, -1) == "a" * 50
