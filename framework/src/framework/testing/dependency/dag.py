"""Interface-dependency DAG: declaration, validation, and async orchestration.

Capabilities:
- **Auto dependency**: a :class:`DependencyGraph` declares nodes + dependencies
  (a DAG) with topological ordering, cycle detection, and validation.
- **Auto extraction**: a node's ``extract`` mapping pulls values from its own
  response into a scoped :class:`VariableStore` (response -> variables).
- **Auto injection**: a node's ``inject`` mapping resolves request fields from
  the store and passes them to the executor (variables -> request).
- **Variable scopes**: case/module/session with read precedence
  (case > module > session); a shared store keeps session/module variables
  alive across runs.

Backward compatibility: step executors may take either ``(context)`` (legacy)
or ``(context, injected)`` (auto-injection). The runner inspects the signature
so existing one-arg executors keep working unchanged.

Layering: depends only on ``core`` (:class:`DependencyError`) and
``testing.extractors`` / ``testing.dependency.variables`` (rule 11); never on
``clients`` or business code.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from framework.core.exceptions import DependencyError
from framework.testing.dependency.variables import Scope, VariableStore
from framework.testing.extractors import extract

__all__ = [
    "Context",
    "DependencyGraph",
    "DependencyNode",
    "DependencyRunner",
    "Executor",
    "InjectingExecutor",
    "Injection",
    "NodeExecutor",
]

#: Flattened variable view passed to step executors (read-only snapshot).
Context = dict[str, Any]

#: Resolved request fields handed to an injecting executor.
Injection = dict[str, Any]

#: Legacy one-arg executor: ``(context) -> response_data``.
NodeExecutor = Callable[[Context], Awaitable[Any]]

#: Injecting executor: ``(context, injected) -> response_data``.
InjectingExecutor = Callable[[Context, Injection], Awaitable[Any]]

#: Broad executor type accepted by :meth:`DependencyRunner.run` (either arity).
Executor = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class DependencyNode:
    """A node in the dependency graph.

    Attributes:
        name: Endpoint name (matches the executor key).
        depends_on: Names that must run before this node.
        extract: Mapping ``{variable: extractor_spec}`` applied to this node's
            own response to populate the variable store.
        extract_scope: Scope at which extracted variables are stored
            (default :attr:`Scope.CASE`).
        inject: Mapping ``{request_field: variable}`` resolved from the store
            and passed to an injecting executor as the ``injected`` dict.
    """

    name: str
    depends_on: tuple[str, ...] = ()
    extract: Mapping[str, str] | None = None
    extract_scope: Scope = Scope.CASE
    inject: Mapping[str, str] | None = None


def _accepts_injection(executor: Executor) -> bool:
    """Return whether ``executor`` declares a second positional param."""
    try:
        params = inspect.signature(executor).parameters.values()
    except (TypeError, ValueError):
        return False
    positional_kinds = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    positional = [p for p in params if p.kind in positional_kinds]
    return len(positional) >= 2


class DependencyGraph:
    """Validated DAG of :class:`DependencyNode` instances."""

    def __init__(self, nodes: Iterable[DependencyNode]) -> None:
        self._nodes: dict[str, DependencyNode] = {}
        for node in nodes:
            if node.name in self._nodes:
                raise DependencyError("duplicate node", context={"name": node.name})
            self._nodes[node.name] = node

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._nodes

    def names(self) -> list[str]:
        """Return all node names (insertion order)."""
        return list(self._nodes)

    def node(self, name: str) -> DependencyNode:
        """Return a node by name; raise :class:`DependencyError` if absent."""
        try:
            return self._nodes[name]
        except KeyError as exc:
            raise DependencyError("unknown node", context={"node": name}) from exc

    def validate(self) -> None:
        """Validate the graph (all deps exist, no cycles); raise on invalid."""
        self.topological_sort()

    def topological_sort(self) -> list[str]:
        """Return node names in dependency order; raise on cycle or unknown dep."""
        visited: dict[str, int] = {}
        order: list[str] = []

        def visit(name: str) -> None:
            state = visited.get(name, 0)
            if state == 2:
                return
            if state == 1:
                raise DependencyError("cycle detected", context={"node": name})
            visited[name] = 1
            current = self.node(name)
            for dep in current.depends_on:
                if dep not in self:
                    raise DependencyError(
                        "unknown dependency",
                        context={"node": name, "dependency": dep},
                    )
                visit(dep)
            visited[name] = 2
            order.append(name)

        for name in self._nodes:
            visit(name)
        return order


class DependencyRunner:
    """Executes a :class:`DependencyGraph` in topological order.

    For each node the runner resolves ``inject`` from the variable store and
    passes the resolved fields to injecting executors; after the step it
    applies ``extract`` to the response, storing values at ``extract_scope``.
    """

    def __init__(self, graph: DependencyGraph) -> None:
        self._graph = graph

    async def run(
        self,
        executors: Mapping[str, Executor],
        *,
        store: VariableStore | None = None,
    ) -> dict[str, Any]:
        """Execute every node in order; return ``{node_name: response_data}``.

        Args:
            executors: One executor per node name. An executor may take
                ``(context)`` (legacy) or ``(context, injected)`` (auto-inject).
            store: Optional shared variable store. A fresh case-scoped store is
                used when omitted, so legacy callers are unaffected.

        Raises:
            DependencyError: If a node lacks an executor, an injected variable
                is missing, or extraction fails.
        """
        order = self._graph.topological_sort()
        variables = store if store is not None else VariableStore()
        results: dict[str, Any] = {}
        for name in order:
            executor = executors.get(name)
            if executor is None:
                raise DependencyError("no executor for node", context={"node": name})
            node = self._graph.node(name)
            injected = self._resolve_injection(node, variables)
            context = variables.to_context()
            if _accepts_injection(executor):
                response = await executor(context, injected)
            else:
                response = await executor(context)
            results[name] = response
            self._apply_extract(node, variables, response)
        return results

    @staticmethod
    def _resolve_injection(node: DependencyNode, variables: VariableStore) -> Injection:
        """Resolve a node's ``inject`` mapping into ``{field: value}``."""
        if node.inject is None:
            return {}
        injected: Injection = {}
        for field, variable in node.inject.items():
            injected[field] = variables.require(variable)
        return injected

    @staticmethod
    def _apply_extract(node: DependencyNode, variables: VariableStore, response: Any) -> None:
        """Apply a node's ``extract`` mapping, storing values at ``extract_scope``."""
        if node.extract is None:
            return
        for variable, spec in node.extract.items():
            variables.set(node.extract_scope, variable, extract(response, spec))
