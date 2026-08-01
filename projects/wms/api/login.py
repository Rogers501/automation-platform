"""登录接口封装示例."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from framework.clients.http.auth import Token
from framework.clients.http.client import AsyncHttpClient


class LoginApi:
    """登录接口:用账号密码换取 :class:`Token`."""

    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def login(self, username: str, password: str) -> Token:
        """``POST /login`` -> :class:`Token`(含过期时间,供 TokenManager 判断刷新)."""
        resp = await self._client.post("/login", json={"username": username, "password": password})
        resp.raise_for_status()
        data: dict[str, Any] = resp.json
        expires_in = data.get("expires_in")
        expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in)) if expires_in else None
        return Token(access_token=data["access_token"], expires_at=expires_at)
