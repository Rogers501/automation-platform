"""接口调用示例(带 trace 上下文,演示 framework 集成)."""

from __future__ import annotations

import pytest
from api.users import UsersApi

from framework.clients.http.client import AsyncHttpClient
from framework.core.context import TestContext


@pytest.mark.regression
async def test_list_users_authenticated(
    api_client: AsyncHttpClient, test_context: TestContext
) -> None:
    """鉴权客户端自动登录并调用业务接口;trace_id 关联日志与请求头."""
    users = await UsersApi(api_client).list_users()
    assert len(users) == 2
    assert users[0]["name"] == "alice"


@pytest.mark.regression
async def test_create_user(api_client: AsyncHttpClient) -> None:
    """创建用户接口返回回显数据."""
    user = await UsersApi(api_client).create_user("carol", "carol@example.com")
    assert user["id"] == 99
    assert user["name"] == "carol"
