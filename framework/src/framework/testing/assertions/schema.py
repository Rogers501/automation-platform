"""JSON Schema validation assertion.

Uses the ``jsonschema`` library (lazy import) to validate data against a
JSON Schema draft. Validation errors are wrapped into
:class:`FrameworkAssertionError` with the error message, path, and validator.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from framework.testing.assertions.base import FrameworkAssertionError, fail

__all__ = ["assert_schema"]


def assert_schema(data: Any, schema: Mapping[str, Any], *, message: str = "") -> None:
    """Validate ``data`` against a JSON ``schema``.

    The ``jsonschema`` package is imported lazily; if it is not installed a
    clear :class:`FrameworkAssertionError` is raised directing the user to
    run ``uv sync``.

    Args:
        data: The JSON value to validate.
        schema: A JSON Schema mapping (draft 4/6/7/2019/2020).
        message: Optional custom failure message (overrides the default).
    """
    try:
        import jsonschema
    except ImportError as exc:
        raise FrameworkAssertionError(
            "jsonschema package is not installed; run 'uv sync' to install it",
            context={"error_type": type(exc).__name__},
        ) from exc

    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as exc:
        fail(
            message or f"Schema validation failed: {exc.message}",
            context={
                "path": list(exc.path) if exc.path else [],
                "validator": getattr(exc, "validator", None),
                "schema_path": list(exc.schema_path) if exc.schema_path else [],
            },
        )
