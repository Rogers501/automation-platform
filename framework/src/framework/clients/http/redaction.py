"""Sensitive-data redaction for HTTP request/response logging.

Keeps secrets (Authorization, Cookie, API keys) out of log output while still
logging enough to debug. The redaction set is the single source of truth; the
HTTP client falls back to it when :attr:`HttpSettings.sensitive_headers` is
empty.
"""

from __future__ import annotations

from collections.abc import Iterable

__all__ = [
    "DEFAULT_SENSITIVE_HEADERS",
    "redact_headers",
    "truncate_body",
]

#: Default header names whose values must never be logged verbatim.
DEFAULT_SENSITIVE_HEADERS: frozenset[str] = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "proxy-authorization",
    }
)


def redact_headers(
    headers: dict[str, str],
    sensitive: Iterable[str] = DEFAULT_SENSITIVE_HEADERS,
) -> dict[str, str]:
    """Return a copy of ``headers`` with sensitive values masked.

    Header name matching is case-insensitive.

    Args:
        headers: Raw request/response headers.
        sensitive: Iterable of header names to redact.

    Returns:
        A new dict with sensitive values replaced by ``"***REDACTED***"``.
    """
    lowered = {h.lower() for h in sensitive}
    return {
        key: ("***REDACTED***" if key.lower() in lowered else value)
        for key, value in headers.items()
    }


def truncate_body(text: str, max_length: int) -> str:
    """Truncate ``text`` to ``max_length`` chars, appending an ellipsis marker.

    A non-positive ``max_length`` disables truncation (returns the full text).
    """
    if max_length <= 0 or len(text) <= max_length:
        return text
    return text[:max_length] + "...(truncated)"
