"""用户业务接口封装示例."""

from __future__ import annotations

from typing import Any

from framework.clients.http.client import AsyncHttpClient


class UsersApi:
    """用户业务接口."""

    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def list_users(self) -> list[dict[str, Any]]:
        """``GET /users`` 返回用户列表."""
        resp = await self._client.get("/users")
        resp.raise_for_status()
        return resp.json

    async def create_user(self, name: str, email: str) -> dict[str, Any]:
        """``POST /users`` 创建用户并返回回显数据."""
        resp = await self._client.post("/users", json={"name": name, "email": email})
        resp.raise_for_status()
        return resp.json
