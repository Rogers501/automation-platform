"""接口依赖 DAG 测试(基于 framework.testing.dependency):拓扑、环检测、编排链路."""

from __future__ import annotations

from typing import Any

import pytest
from api.station_quote import StationQuoteClient
from dependency import STATION_QUOTE_DAG
from factories import (
    make_audit_request,
    make_create_request,
    make_delete_request,
    make_detail_query,
    make_page_request,
    make_unaudit_request,
    make_update_request,
)
from models.dto import ResultDetail, ResultPage, ResultVoid

from framework.core.exceptions import DependencyError
from framework.testing.dependency import (
    Context,
    DependencyGraph,
    DependencyNode,
    DependencyRunner,
)
from framework.testing.extractors import extract


class TestDagTopology:
    def test_sort_returns_all_nodes(self) -> None:
        order = STATION_QUOTE_DAG.topological_sort()
        assert set(order) == set(STATION_QUOTE_DAG.names())

    def test_save_before_page(self) -> None:
        order = STATION_QUOTE_DAG.topological_sort()
        assert order.index("save") < order.index("page")

    def test_page_before_dependents(self) -> None:
        order = STATION_QUOTE_DAG.topological_sort()
        for dep in ("detail", "update", "audit", "delete"):
            assert order.index("page") < order.index(dep)

    def test_unaudit_after_audit(self) -> None:
        order = STATION_QUOTE_DAG.topological_sort()
        assert order.index("audit") < order.index("unaudit")

    def test_cycle_detected(self) -> None:
        cyclic = DependencyGraph(
            [DependencyNode("a", depends_on=("b",)), DependencyNode("b", depends_on=("a",))]
        )
        with pytest.raises(DependencyError):
            cyclic.topological_sort()

    def test_unknown_dependency_raises(self) -> None:
        bad = DependencyGraph([DependencyNode("a", depends_on=("missing",))])
        with pytest.raises(DependencyError):
            bad.topological_sort()


def test_extract_from_page_response() -> None:
    page_json = {"data": {"records": [{"id": 5}], "total": 1}}
    assert extract(page_json, "$.data.records[0].id") == 5


class TestChainExecution:
    """按 DAG 用 framework DependencyRunner 编排完整链路."""

    async def test_full_chain(self, api_client: StationQuoteClient) -> None:
        async def save_exec(_ctx: Context) -> Any:
            return (await api_client.save(make_create_request())).json

        async def page_exec(_ctx: Context) -> Any:
            return (await api_client.page(make_page_request())).json

        async def detail_exec(ctx: Context) -> Any:
            return (await api_client.detail(make_detail_query(ctx["id"]))).json

        async def update_exec(ctx: Context) -> Any:
            return (
                await api_client.update(make_update_request(ctx["id"], quote_name="链路改名"))
            ).json

        async def audit_exec(ctx: Context) -> Any:
            return (await api_client.audit(make_audit_request([ctx["id"]]))).json

        async def unaudit_exec(ctx: Context) -> Any:
            return (await api_client.unaudit(make_unaudit_request([ctx["id"]]))).json

        async def delete_exec(ctx: Context) -> Any:
            return (await api_client.delete(make_delete_request(ctx["id"]))).json

        executors = {
            "save": save_exec,
            "page": page_exec,
            "detail": detail_exec,
            "update": update_exec,
            "audit": audit_exec,
            "unaudit": unaudit_exec,
            "delete": delete_exec,
        }
        results = await DependencyRunner(STATION_QUOTE_DAG).run(executors)

        assert set(results) == set(STATION_QUOTE_DAG.names())
        page = ResultPage.model_validate(results["page"])
        assert page.data is not None
        assert page.data.total == 1
        quote_id = page.data.records[0].id

        detail = ResultDetail.model_validate(results["detail"])
        assert detail.data is not None
        assert detail.data.id == quote_id

        for name in ("save", "update", "audit", "unaudit", "delete"):
            assert ResultVoid.model_validate(results[name]).code == 200

        after = StationQuoteClient.parse_page(await api_client.page(make_page_request()))
        assert after.data is not None
        assert after.data.total == 0
