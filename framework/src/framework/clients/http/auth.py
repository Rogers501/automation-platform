"""Authentication providers and token management.

Auth is pluggable: implement :class:`AuthProvider` to plug in any scheme
(OAuth refresh, mTLS headers, signed requests). The built-in providers cover
Bearer, Basic, and API-Key; :class:`TokenManager` handles cached tokens with
optional async refresh.
"""

from __future__ import annotations

import abc
import asyncio
import base64
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from framework.core.exceptions import ClientError

__all__ = [
    "ApiKeyAuth",
    "AuthProvider",
    "BasicAuth",
    "BearerAuth",
    "Token",
    "TokenManager",
    "TokenRefreshFn",
]


@dataclass(frozen=True)
class Token:
    """An access token with optional expiry and refresh token.

    A ``None`` expiry means the token never expires (manual rotation only).
    """

    access_token: str
    expires_at: datetime | None = None
    refresh_token: str | None = None

    def is_expired(self, *, buffer: timedelta = timedelta(seconds=30)) -> bool:
        """Whether the token has expired (or will within ``buffer``)."""
        if self.expires_at is None:
            return False
        expiry = self.expires_at
        now = datetime.now(UTC)
        if expiry.tzinfo is None:
            now = now.replace(tzinfo=None)
        return now + buffer >= expiry


TokenRefreshFn = Callable[[], Awaitable["Token"]]


class TokenManager:
    """Async-safe token store with optional refresh-on-expiry.

    Concurrent callers that find the token expired serialize on a lock so the
    refresh function runs at most once per expiry window.
    """

    def __init__(
        self,
        refresh_fn: TokenRefreshFn | None = None,
        *,
        refresh_buffer_seconds: float = 30.0,
    ) -> None:
        self._refresh_fn = refresh_fn
        self._token: Token | None = None
        self._lock = asyncio.Lock()
        self._buffer = timedelta(seconds=refresh_buffer_seconds)

    def set_token(self, token: Token) -> None:
        """Replace the cached token."""
        self._token = token

    @property
    def token(self) -> Token | None:
        """The currently cached token (without refresh)."""
        return self._token

    def is_expired(self) -> bool:
        """Whether no token is cached or the cached token is expired."""
        return self._token is None or self._token.is_expired(buffer=self._buffer)

    async def get_access_token(self) -> str:
        """Return a valid access token, refreshing via ``refresh_fn`` if needed.

        Raises:
            ClientError: If the token is missing/expired and no refresh
                function is configured.
        """
        async with self._lock:
            if self._token is None or self._token.is_expired(buffer=self._buffer):
                if self._refresh_fn is None:
                    raise ClientError(
                        "token is missing or expired and no refresh function is configured"
                    )
                self._token = await self._refresh_fn()
            return self._token.access_token


class AuthProvider(abc.ABC):
    """Pluggable authentication applied to outbound requests."""

    @abc.abstractmethod
    async def apply(self, headers: dict[str, str], cookies: dict[str, str]) -> None:
        """Mutate ``headers``/``cookies`` in place to authenticate the request."""


class BearerAuth(AuthProvider):
    """Bearer token auth backed by a :class:`TokenManager`.

    Construct with a static token, a token manager, or a refresh function.
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        token_manager: TokenManager | None = None,
        refresh_fn: TokenRefreshFn | None = None,
    ) -> None:
        if token_manager is not None:
            self._manager = token_manager
        else:
            self._manager = TokenManager(refresh_fn=refresh_fn)
            if token is not None:
                self._manager.set_token(Token(access_token=token))

    async def apply(self, headers: dict[str, str], cookies: dict[str, str]) -> None:
        access = await self._manager.get_access_token()
        headers["Authorization"] = f"Bearer {access}"


class BasicAuth(AuthProvider):
    """HTTP Basic authentication (username + password)."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password

    async def apply(self, headers: dict[str, str], cookies: dict[str, str]) -> None:
        raw = f"{self._username}:{self._password}".encode()
        encoded = base64.b64encode(raw).decode("ascii")
        headers["Authorization"] = f"Basic {encoded}"


class ApiKeyAuth(AuthProvider):
    """API key auth injected into a configurable header."""

    def __init__(self, api_key: str, *, header_name: str = "X-API-Key") -> None:
        self._api_key = api_key
        self._header_name = header_name

    async def apply(self, headers: dict[str, str], cookies: dict[str, str]) -> None:
        headers[self._header_name] = self._api_key
