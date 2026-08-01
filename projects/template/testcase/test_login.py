"""登录示例 + token 处理."""

from __future__ import annotations

import pytest
from api.login import LoginApi

from framework.clients.http.auth import TokenManager
from framework.clients.http.client import AsyncHttpClient


@pytest.mark.smoke
async def test_login_returns_token(http_client: AsyncHttpClient) -> None:
    """登录接口返回包含 access_token 与过期时间的 Token."""
    token = await LoginApi(http_client).login("demo", "demo123")
    assert token.access_token == "mock-token-xyz"
    assert token.expires_at is not None


@pytest.mark.smoke
async def test_token_manager_refreshes_on_first_use(
    token_manager: TokenManager,
) -> None:
    """TokenManager 首次取 token 时自动触发登录刷新."""
    access = await token_manager.get_access_token()
    assert access == "mock-token-xyz"
