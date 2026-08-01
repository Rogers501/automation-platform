"""Scoped variable store for interface-dependency chains.

Variables extracted from responses are stored under a :class:`Scope`
(case/module/session). Reads apply precedence case > module > session, so a
case-scoped value shadows a session-scoped one of the same name. A store may
be shared across :class:`DependencyRunner` runs to keep session/module
variables alive between tests while clearing case variables per test.

Layering: depends only on ``core`` (:class:`DependencyError`).
"""

from __future__ import annotations

import enum
from typing import Any

from framework.core.exceptions import DependencyError

__all__ = ["Scope", "VariableStore"]


class Scope(enum.StrEnum):
    """Variable lifetime scope (mirrors pytest fixture scopes)."""

    CASE = "case"
    """Per-test (cleared between tests)."""

    MODULE = "module"
    """Per-module (shared within a test module)."""

    SESSION = "session"
    """Per-session (shared across the whole run)."""


#: Read precedence, highest first (case shadows module shadows session).
_PRECEDENCE: tuple[Scope, ...] = (Scope.CASE, Scope.MODULE, Scope.SESSION)


class VariableStore:
    """Key-value store partitioned by :class:`Scope`.

    ``to_context`` flattens all scopes into a single dict applying the
    precedence above (case wins), suitable for passing to step executors.
    """

    def __init__(self) -> None:
        self._data: dict[Scope, dict[str, Any]] = {
            Scope.CASE: {},
            Scope.MODULE: {},
            Scope.SESSION: {},
        }

    def set(self, scope: Scope, key: str, value: Any) -> None:
        """Store ``value`` under ``key`` at ``scope``."""
        self._data[scope][key] = value

    def resolve(self, key: str) -> tuple[bool, Any]:
        """Return ``(found, value)`` applying scope precedence."""
        for scope in _PRECEDENCE:
            data = self._data[scope]
            if key in data:
                return True, data[key]
        return False, None

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for ``key`` (precedence), or ``default`` if absent."""
        found, value = self.resolve(key)
        return value if found else default

    def require(self, key: str) -> Any:
        """Return the value for ``key``; raise :class:`DependencyError` if absent."""
        found, value = self.resolve(key)
        if not found:
            raise DependencyError("variable not found", context={"variable": key})
        return value

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self.resolve(key)[0]

    def clear(self, scope: Scope | None = None) -> None:
        """Clear one scope, or every scope when ``scope`` is ``None``."""
        if scope is None:
            for data in self._data.values():
                data.clear()
        else:
            self._data[scope].clear()

    def to_context(self) -> dict[str, Any]:
        """Flatten all scopes into a dict (case overrides module overrides session)."""
        result: dict[str, Any] = {}
        for scope in reversed(_PRECEDENCE):
            result.update(self._data[scope])
        return result
