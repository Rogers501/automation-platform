"""Allure 报告示例.

展示三类 Allure 集成(安装 allure-pytest 后生成报告;未安装时全部 no-op,用例仍绿色):

1. 自动附件 - test_context 在 teardown 自动把本次录制的 HTTP 交换作为附件
   (由 framework.testing.hooks 触发,无需手写).
2. 显式步骤 - framework.reporting.allure.step 包裹业务步骤.
3. 显式附件 - attach_db_result 把数据库查询结果作为附件.

生成报告:

    uv pip install allure-pytest
    pytest --alluredir=allure-results
    allure serve allure-results
"""

from __future__ import annotations

import pytest
from api.users import UsersApi

from framework.clients.db.client import DatabaseClient
from framework.clients.http.client import AsyncHttpClient
from framework.core.context import TestContext
from framework.reporting.allure import attach_db_result, step


@pytest.mark.regression
async def test_allure_report_demo(
    api_client: AsyncHttpClient,
    db_client: DatabaseClient,
    test_context: TestContext,
) -> None:
    """登录态调用接口 + 数据库校验, 全程产出 Allure 步骤与附件."""
    with step("查询用户列表"):
        users = await UsersApi(api_client).list_users()
        assert len(users) >= 1

    with step("数据库写入并校验"):
        await db_client.execute(
            "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)"
        )
        await db_client.execute(
            "INSERT INTO users (name, email) VALUES (:name, :email)",
            params={"name": "dave", "email": "dave@example.com"},
        )
        result = await db_client.execute("SELECT name, email FROM users")
        attach_db_result(
            result.as_dicts(),
            name="users-in-db",
            query="SELECT name, email FROM users",
        )
        assert len(result) >= 1
