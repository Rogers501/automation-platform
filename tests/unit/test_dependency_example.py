"""完整示例:登录 -> 创建订单 -> 查询订单.

演示 framework.testing.dependency 的自动提取 / 自动注入 / 变量作用域,
全程使用通用 executor(不写死任何业务系统)。能力点:

- 自动接口依赖:DependencyGraph 声明 DAG,runner 按拓扑序执行。
- 响应参数自动提取:login 提取 token(SESSION),create 提取 order_id(CASE)。
- 请求参数自动注入:create/query 通过 inject 自动获得上游变量。
- 变量作用域:SESSION token 跨 run 复用(免重登),CASE 变量按用例清理。
"""

from __future__ import annotations

from typing import Any

import pytest

from framework.core.exceptions import DependencyError
from framework.testing.dependency import (
    Context,
    DependencyGraph,
    DependencyNode,
    DependencyRunner,
    Injection,
    Scope,
    VariableStore,
)

#: 业务依赖图(通用):login 提取 token(SESSION);create 注入 token、提取 order_id;
#: query 注入 order_id + token。
ORDER_FLOW = DependencyGraph(
    [
        DependencyNode("login", extract={"token": "$.data.token"}, extract_scope=Scope.SESSION),
        DependencyNode(
            "create_order",
            depends_on=("login",),
            extract={"order_id": "$.data.orderId"},
            inject={"token": "token"},
        ),
        DependencyNode(
            "query_order",
            depends_on=("create_order",),
            inject={"order_id": "order_id", "token": "token"},
        ),
    ]
)


def _executors(token: str, order_id: str) -> dict[str, Any]:
    """构造一组 executor:login 单参(无注入);create/query 双参(自动注入)."""

    async def login_exec(_ctx: Context) -> Any:
        return {"data": {"token": token}}

    async def create_order_exec(_ctx: Context, injected: Injection) -> Any:
        assert injected == {"token": token}
        return {"data": {"orderId": order_id}}

    async def query_order_exec(_ctx: Context, injected: Injection) -> Any:
        assert injected == {"order_id": order_id, "token": token}
        return {"data": {"id": order_id, "status": "created"}}

    return {
        "login": login_exec,
        "create_order": create_order_exec,
        "query_order": query_order_exec,
    }


class TestOrderFlowExample:
    async def test_login_create_query_with_auto_extract_and_inject(self) -> None:
        store = VariableStore()
        results = await DependencyRunner(ORDER_FLOW).run(
            _executors("tok-123", "ORD-1"), store=store
        )
        assert results["query_order"]["data"]["status"] == "created"
        # 作用域落地:token -> SESSION,order_id -> CASE
        assert store.resolve("token") == (True, "tok-123")
        assert store.resolve("order_id") == (True, "ORD-1")

    async def test_legacy_one_arg_executors_still_work(self) -> None:
        """向后兼容:仅 (context) 的 executor 仍可运行,无需改造。"""
        graph = DependencyGraph(
            [
                DependencyNode("login", extract={"token": "$.data.token"}),
                DependencyNode("query", depends_on=("login",)),
            ]
        )

        async def login_exec(_ctx: Context) -> Any:
            return {"data": {"token": "abc"}}

        async def query_exec(ctx: Context) -> Any:
            assert ctx["token"] == "abc"
            return {"ok": True}

        results = await DependencyRunner(graph).run({"login": login_exec, "query": query_exec})
        assert results["query"] == {"ok": True}

    async def test_session_token_reused_without_relogin(self) -> None:
        """SESSION token 跨 run 复用:第二次只 create+query,免登录。"""
        store = VariableStore()
        await DependencyRunner(ORDER_FLOW).run(_executors("tok-xyz", "ORD-1"), store=store)
        store.clear(Scope.CASE)  # 用例级变量清理,SESSION token 保留

        # 复用流程:不再 login,create/query 直接注入 SESSION 中的 token
        reorder = DependencyGraph(
            [
                DependencyNode(
                    "create_order",
                    extract={"order_id": "$.data.orderId"},
                    inject={"token": "token"},
                ),
                DependencyNode(
                    "query_order",
                    depends_on=("create_order",),
                    inject={"order_id": "order_id", "token": "token"},
                ),
            ]
        )

        async def create_exec(_ctx: Context, injected: Injection) -> Any:
            assert injected == {"token": "tok-xyz"}
            return {"data": {"orderId": "ORD-2"}}

        async def query_exec(_ctx: Context, injected: Injection) -> Any:
            assert injected == {"order_id": "ORD-2", "token": "tok-xyz"}
            return {"data": {"id": "ORD-2"}}

        results = await DependencyRunner(reorder).run(
            {"create_order": create_exec, "query_order": query_exec}, store=store
        )
        assert results["query_order"]["data"]["id"] == "ORD-2"

    async def test_injection_missing_variable_raises(self) -> None:
        graph = DependencyGraph([DependencyNode("a", inject={"field": "missing"})])

        async def exec_a(_ctx: Context, _injected: Injection) -> Any:
            return {}

        with pytest.raises(DependencyError):
            await DependencyRunner(graph).run({"a": exec_a})
