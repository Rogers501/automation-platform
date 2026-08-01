"""token 处理:TokenManager 自动登录/缓存/刷新 + BearerAuth 注入."""

from __future__ import annotations

import httpx
import pytest
from api.login import LoginApi

from framework.clients.http.auth import BearerAuth, Token, TokenManager
from framework.clients.http.client import AsyncHttpClient
from framework.core.config import HttpSettings

API_BASE_URL = "http://api.example.com"


@pytest.fixture
def token_manager(mock_transport: httpx.MockTransport) -> TokenManager:
    """TokenManager:无 token 或过期时调用 refresh_fn 自动登录.

    refresh_fn 用未鉴权客户端调用登录接口换取新 token;TokenManager 内部加锁,
    并发请求只刷新一次.
    """

    async def refresh() -> Token:
        async with AsyncHttpClient(
            settings=HttpSettings(base_url=API_BASE_URL), transport=mock_transport
        ) as client:
            return await LoginApi(client).login("demo", "demo123")

    return TokenManager(refresh_fn=refresh)


@pytest.fixture
def auth(token_manager: TokenManager) -> BearerAuth:
    """BearerAuth:每次请求自动注入 ``Authorization: Bearer <token>``."""
    return BearerAuth(token_manager=token_manager)
