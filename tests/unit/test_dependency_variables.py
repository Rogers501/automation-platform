"""Unit tests for the scoped variable store (framework.testing.dependency)."""

from __future__ import annotations

import pytest

from framework.core.exceptions import DependencyError
from framework.testing.dependency import Scope, VariableStore


def test_set_and_get_per_scope() -> None:
    store = VariableStore()
    store.set(Scope.SESSION, "a", 1)
    store.set(Scope.CASE, "b", 2)
    assert store.get("a") == 1
    assert store.get("b") == 2


def test_precedence_case_shadows_session() -> None:
    store = VariableStore()
    store.set(Scope.SESSION, "x", "session")
    store.set(Scope.CASE, "x", "case")
    assert store.get("x") == "case"
    store.clear(Scope.CASE)
    assert store.get("x") == "session"


def test_module_shadows_session() -> None:
    store = VariableStore()
    store.set(Scope.SESSION, "x", "s")
    store.set(Scope.MODULE, "x", "m")
    assert store.get("x") == "m"


def test_to_context_flattens_with_precedence() -> None:
    store = VariableStore()
    store.set(Scope.SESSION, "token", "tok")
    store.set(Scope.CASE, "order_id", "ord")
    assert store.to_context() == {"token": "tok", "order_id": "ord"}
    store.set(Scope.SESSION, "order_id", "session-ord")
    assert store.to_context()["order_id"] == "ord"


def test_require_missing_raises() -> None:
    with pytest.raises(DependencyError):
        VariableStore().require("nope")


def test_get_default() -> None:
    assert VariableStore().get("nope", "def") == "def"


def test_contains() -> None:
    store = VariableStore()
    store.set(Scope.MODULE, "k", 1)
    assert "k" in store
    assert "z" not in store


def test_clear_all() -> None:
    store = VariableStore()
    store.set(Scope.SESSION, "a", 1)
    store.set(Scope.CASE, "b", 2)
    store.clear()
    assert "a" not in store
    assert "b" not in store


def test_resolve_tuple() -> None:
    store = VariableStore()
    store.set(Scope.CASE, "a", 1)
    assert store.resolve("a") == (True, 1)
    assert store.resolve("z") == (False, None)
