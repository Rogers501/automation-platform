"""HTTP capability client (async, httpx-based).

Public API: ``AsyncHttpClient`` plus the supporting auth, model, retry, and
redaction helpers needed to construct and assert on requests.
"""

from framework.clients.http.auth import (
    ApiKeyAuth,
    AuthProvider,
    BasicAuth,
    BearerAuth,
    Token,
    TokenManager,
)
from framework.clients.http.client import AsyncHttpClient
from framework.clients.http.models import ApiResponse, HttpMethod, RequestSpec
from framework.clients.http.redaction import (
    DEFAULT_SENSITIVE_HEADERS,
    redact_headers,
    truncate_body,
)
from framework.clients.http.retry import RetryPolicy

__all__ = [
    "DEFAULT_SENSITIVE_HEADERS",
    "ApiKeyAuth",
    "ApiResponse",
    "AsyncHttpClient",
    "AuthProvider",
    "BasicAuth",
    "BearerAuth",
    "HttpMethod",
    "RequestSpec",
    "RetryPolicy",
    "Token",
    "TokenManager",
    "redact_headers",
    "truncate_body",
]
