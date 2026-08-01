"""Unit tests for framework.testing.dependency (DAG + runner)."""

from __future__ import annotations

from typing import Any

import pytest

from framework.core.exceptions import DependencyError, FrameworkError
from framework.testing.dependency import (
    Context,
    DependencyGraph,
    DependencyNode,
    DependencyRunner,
)


class TestDependencyGraph:
    def test_topological_sort_order(self) -> None:
        graph = DependencyGraph(
            [
                DependencyNode("login", extract={"token": "$.token"}),
                DependencyNode("create", depends_on=("login",)),
                DependencyNode("verify", depends_on=("create",)),
            ]
        )
        order = graph.topological_sort()
        assert order.index("login") < order.index("create") < order.index("verify")

    def test_duplicate_node_raises(self) -> None:
        with pytest.raises(DependencyError):
            DependencyGraph([DependencyNode("a"), DependencyNode("a")])

    def test_cycle_detected(self) -> None:
        graph = DependencyGraph(
            [
                DependencyNode("a", depends_on=("b",)),
                DependencyNode("b", depends_on=("a",)),
            ]
        )
        with pytest.raises(DependencyError):
            graph.topological_sort()

    def test_unknown_dependency_raises(self) -> None:
        graph = DependencyGraph([DependencyNode("a", depends_on=("missing",))])
        with pytest.raises(DependencyError):
            graph.topological_sort()

    def test_node_missing_raises(self) -> None:
        with pytest.raises(DependencyError):
            DependencyGraph([DependencyNode("a")]).node("nope")

    def test_validate_passes_on_valid_graph(self) -> None:
        DependencyGraph([DependencyNode("a"), DependencyNode("b", depends_on=("a",))]).validate()

    def test_contains_and_names(self) -> None:
        graph = DependencyGraph([DependencyNode("a"), DependencyNode("b")])
        assert "a" in graph
        assert "z" not in graph
        assert set(graph.names()) == {"a", "b"}


class TestDependencyRunner:
    async def test_run_executes_in_order_and_extracts(self) -> None:
        graph = DependencyGraph(
            [
                DependencyNode("login", extract={"token": "$.data.token"}),
                DependencyNode("create", depends_on=("login",)),
            ]
        )
        seen: list[tuple[str, Context]] = []

        async def login_exec(ctx: Context) -> Any:
            seen.append(("login", dict(ctx)))
            return {"data": {"token": "abc"}}

        async def create_exec(ctx: Context) -> Any:
            seen.append(("create", dict(ctx)))
            assert ctx["token"] == "abc"
            return {"ok": True}

        results = await DependencyRunner(graph).run({"login": login_exec, "create": create_exec})
        assert results["login"]["data"]["token"] == "abc"
        assert results["create"] == {"ok": True}
        assert seen[0][0] == "login"
        assert seen[1][0] == "create"
        assert seen[1][1]["token"] == "abc"

    async def test_missing_executor_raises(self) -> None:
        graph = DependencyGraph([DependencyNode("a")])
        with pytest.raises(DependencyError):
            await DependencyRunner(graph).run({})

    async def test_extraction_failure_raises(self) -> None:
        graph = DependencyGraph([DependencyNode("a", extract={"id": "$.missing"})])

        async def exec_a(ctx: Context) -> Any:
            return {"data": {}}

        with pytest.raises(FrameworkError):
            await DependencyRunner(graph).run({"a": exec_a})

    async def test_run_validates_graph_first(self) -> None:
        graph = DependencyGraph(
            [DependencyNode("a", depends_on=("b",)), DependencyNode("b", depends_on=("a",))]
        )

        async def exec_a(ctx: Context) -> Any:
            return {}

        with pytest.raises(DependencyError):
            await DependencyRunner(graph).run({"a": exec_a, "b": exec_a})
