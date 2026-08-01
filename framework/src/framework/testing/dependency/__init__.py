"""Interface-dependency DAG orchestrator with scoped variables and auto-injection.

See :mod:`framework.testing.dependency.dag` for the graph/runner and
:mod:`framework.testing.dependency.variables` for the scoped variable store.
"""

from framework.testing.dependency.dag import (
    Context,
    DependencyGraph,
    DependencyNode,
    DependencyRunner,
    Executor,
    InjectingExecutor,
    Injection,
    NodeExecutor,
)
from framework.testing.dependency.variables import Scope, VariableStore

__all__ = [
    "Context",
    "DependencyGraph",
    "DependencyNode",
    "DependencyRunner",
    "Executor",
    "InjectingExecutor",
    "Injection",
    "NodeExecutor",
    "Scope",
    "VariableStore",
]
