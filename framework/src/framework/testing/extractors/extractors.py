"""Response value extractors for interface-dependency chains.

Extractors pull a value out of a response (JSON body or headers) so it can be
fed into a downstream request. JSON-path extraction is dependency-free (reuses
:func:`framework.testing.assertions.base.resolve_json_path`); jmespath is
lazy (optional dependency). XPath is reserved as a future extension.

A spec string selects the extractor via a prefix: ``header:<name>`` for a
response header, ``jmes:<expr>`` for jmespath, and anything else is treated as
a JSON path (``$.a.b[0].c``). :func:`compile_extractor` builds the extractor;
:func:`extract` is a one-shot convenience.

Layering: depends only on ``core`` (:class:`FrameworkError`) and
``testing.assertions.base`` (rule 11).
"""

from __future__ import annotations

import abc
import importlib
from typing import Any

from framework.core.exceptions import FrameworkError
from framework.testing.assertions.base import resolve_json_path

__all__ = [
    "Extractor",
    "HeaderExtractor",
    "JmesPathExtractor",
    "JsonPathExtractor",
    "compile_extractor",
    "extract",
]

#: Prefix selecting a header extractor.
_HEADER_PREFIX = "header:"
#: Prefix selecting a jmespath extractor.
_JMES_PREFIX = "jmes:"


class Extractor(abc.ABC):
    """Pulls a single value out of response data."""

    @abc.abstractmethod
    def extract(self, data: Any) -> Any:
        """Return the extracted value; raise :class:`FrameworkError` if absent."""


class JsonPathExtractor(Extractor):
    """JSON-path extractor (``$.a.b[0].c``), dependency-free."""

    def __init__(self, path: str) -> None:
        if not path:
            raise FrameworkError("jsonpath must be non-empty")
        self._path = path

    def extract(self, data: Any) -> Any:
        found, value = resolve_json_path(data, self._path)
        if not found:
            raise FrameworkError("jsonpath not found", context={"path": self._path})
        return value


class HeaderExtractor(Extractor):
    """Case-insensitive response-header extractor."""

    def __init__(self, name: str) -> None:
        if not name:
            raise FrameworkError("header name must be non-empty")
        self._name = name

    def extract(self, data: Any) -> Any:
        if not isinstance(data, dict):
            raise FrameworkError("header extraction requires a headers mapping")
        target = self._name.lower()
        for key, value in data.items():
            if isinstance(key, str) and key.lower() == target:
                return value
        raise FrameworkError("header not found", context={"header": self._name})


class JmesPathExtractor(Extractor):
    """jmespath extractor (lazy; raises if jmespath is not installed)."""

    def __init__(self, expression: str) -> None:
        if not expression:
            raise FrameworkError("jmespath expression must be non-empty")
        self._expression = expression

    def extract(self, data: Any) -> Any:
        try:
            jmespath = importlib.import_module("jmespath")
        except ImportError as exc:
            raise FrameworkError(
                "jmespath package is not installed; run 'uv sync' to install it"
            ) from exc
        return jmespath.search(self._expression, data)


def compile_extractor(spec: str) -> Extractor:
    """Build an :class:`Extractor` from a spec string.

    Prefixes: ``header:<name>`` -> :class:`HeaderExtractor`,
    ``jmes:<expr>`` -> :class:`JmesPathExtractor`, otherwise JSON path.
    """
    if not spec:
        raise FrameworkError("extractor spec must be non-empty")
    if spec.startswith(_HEADER_PREFIX):
        return HeaderExtractor(spec[len(_HEADER_PREFIX) :].strip())
    if spec.startswith(_JMES_PREFIX):
        return JmesPathExtractor(spec[len(_JMES_PREFIX) :].strip())
    return JsonPathExtractor(spec)


def extract(data: Any, spec: str) -> Any:
    """Compile ``spec`` and extract a value from ``data`` (one-shot)."""
    return compile_extractor(spec).extract(data)
