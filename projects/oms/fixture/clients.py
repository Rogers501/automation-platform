"""项目级客户端 fixtures:HTTP(mock)与数据库(内存 SQLite).

对接真实环境时:删除 ``transport=mock_transport`` 改用配置中的 ``base_url``;
``db_client`` 改用 ``DatabaseSettings`` 中的真实数据库配置.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest

from framework.clients.db.client import DatabaseClient
from framework.clients.http.auth import BearerAuth
from framework.clients.http.client import AsyncHttpClient
from framework.core.config import DatabaseSettings, HttpSettings

API_BASE_URL = "http://api.example.com"


def _mock_handler(request: httpx.Request) -> httpx.Response:
    """Mock 路由:/login 返回 token,/users 返回用户数据.对接真实环境时删除."""
    path = request.url.path
    if path == "/login":
        return httpx.Response(200, json={"access_token": "mock-token-xyz", "expires_in": 3600})
    if path == "/users" and request.method == "GET":
        return httpx.Response(200, json=[{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}])
    if path == "/users" and request.method == "POST":
        body = json.loads(request.content) if request.content else {}
        return httpx.Response(201, json={"id": 99, **body})
    return httpx.Response(404, json={"error": "not found", "path": path})


@pytest.fixture
def mock_transport() -> httpx.MockTransport:
    """共享 mock 传输层(登录刷新与业务调用复用同一实例)."""
    return httpx.MockTransport(_mock_handler)


@pytest.fixture
async def http_client(
    mock_transport: httpx.MockTransport,
) -> AsyncIterator[AsyncHttpClient]:
    """未鉴权 HTTP 客户端(用于登录等内部调用)."""
    async with AsyncHttpClient(
        settings=HttpSettings(base_url=API_BASE_URL), transport=mock_transport
    ) as client:
        yield client


@pytest.fixture
async def api_client(
    auth: BearerAuth, mock_transport: httpx.MockTransport
) -> AsyncIterator[AsyncHttpClient]:
    """带鉴权的业务 HTTP 客户端(BearerAuth 自动注入 token)."""
    async with AsyncHttpClient(
        settings=HttpSettings(base_url=API_BASE_URL),
        transport=mock_transport,
        auth=auth,
    ) as client:
        yield client


@pytest.fixture
async def db_client() -> AsyncIterator[DatabaseClient]:
    """内存 SQLite 数据库客户端(对接真实环境时改用配置中的 database)."""
    client = DatabaseClient(
        DatabaseSettings(url="sqlite+aiosqlite:///:memory:", pool_pre_ping=False)
    )
    try:
        async with client:
            yield client
    finally:
        await client.aclose()
