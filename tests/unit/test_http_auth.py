"""Unit tests for HTTP auth providers and the token manager."""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime, timedelta

import pytest

from framework.clients.http.auth import (
    ApiKeyAuth,
    AuthProvider,
    BasicAuth,
    BearerAuth,
    Token,
    TokenManager,
)
from framework.core.exceptions import ClientError


async def test_bearer_auth_static_token() -> None:
    """A static Bearer token is injected into the Authorization header."""
    auth = BearerAuth(token="abc123")
    headers: dict[str, str] = {}
    await auth.apply(headers, {})
    assert headers["Authorization"] == "Bearer abc123"


async def test_bearer_auth_uses_token_manager() -> None:
    """A shared TokenManager supplies the token."""
    manager = TokenManager()
    manager.set_token(Token(access_token="mgr-token"))
    auth = BearerAuth(token_manager=manager)
    headers: dict[str, str] = {}
    await auth.apply(headers, {})
    assert headers["Authorization"] == "Bearer mgr-token"


async def test_bearer_auth_refresh_when_expired() -> None:
    """An expired token triggers the refresh function once."""
    calls = 0

    async def refresh() -> Token:
        nonlocal calls
        calls += 1
        return Token(access_token="refreshed", expires_at=None)

    manager = TokenManager(refresh_fn=refresh)
    expired = Token(
        access_token="old",
        expires_at=datetime.now(UTC) - timedelta(seconds=10),
    )
    manager.set_token(expired)
    auth = BearerAuth(token_manager=manager)

    headers: dict[str, str] = {}
    await auth.apply(headers, {})
    assert headers["Authorization"] == "Bearer refreshed"
    assert calls == 1

    # second call reuses the refreshed (non-expiring) token, no new refresh
    await auth.apply(headers, {})
    assert calls == 1


async def test_token_manager_missing_no_refresh_raises() -> None:
    """No token and no refresh function raises ClientError."""
    manager = TokenManager()
    with pytest.raises(ClientError):
        await manager.get_access_token()


async def test_token_manager_refresh_serialized() -> None:
    """Concurrent callers trigger a single refresh."""
    calls = 0

    async def refresh() -> Token:
        nonlocal calls
        calls += 1
        return Token(access_token="once")

    manager = TokenManager(refresh_fn=refresh)
    manager.set_token(
        Token(
            access_token="old",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    results = await asyncio.gather(manager.get_access_token(), manager.get_access_token())
    assert results == ["once", "once"]
    assert calls == 1


async def test_basic_auth_header() -> None:
    """BasicAuth encodes credentials as base64."""
    auth = BasicAuth("user", "pass")
    headers: dict[str, str] = {}
    await auth.apply(headers, {})
    assert headers["Authorization"].startswith("Basic ")
    decoded = base64.b64decode(headers["Authorization"].split(" ", 1)[1])
    assert decoded == b"user:pass"


async def test_api_key_auth_custom_header() -> None:
    """ApiKeyAuth injects the key into the configured header."""
    auth = ApiKeyAuth("secret", header_name="X-Token")
    headers: dict[str, str] = {}
    await auth.apply(headers, {})
    assert headers["X-Token"] == "secret"


def test_token_is_expired_with_buffer() -> None:
    """A token expiring within the buffer is considered expired."""
    soon = datetime.now(UTC) + timedelta(seconds=10)
    token = Token(access_token="x", expires_at=soon)
    assert token.is_expired(buffer=timedelta(seconds=30)) is True


def test_token_no_expiry_never_expired() -> None:
    """A token with no expiry is never considered expired."""
    token = Token(access_token="x", expires_at=None)
    assert token.is_expired() is False


def test_auth_provider_is_abstract() -> None:
    """AuthProvider cannot be instantiated directly."""
    with pytest.raises(TypeError):
        AuthProvider()  # type: ignore[abstract]
