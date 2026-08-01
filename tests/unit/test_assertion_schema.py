"""Unit tests for JSON Schema assertion (with fake jsonschema module, rule 14)."""

from __future__ import annotations

import sys
from typing import Any

import pytest

from framework.testing.assertions.base import FrameworkAssertionError
from framework.testing.assertions.schema import assert_schema


class _FakeValidationError(Exception):
    """Stand-in for jsonschema.ValidationError."""

    def __init__(
        self,
        message: str,
        *,
        path: list[Any] | None = None,
        validator: str = "required",
        schema_path: list[Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.path = list(path or [])
        self.validator = validator
        self.schema_path = list(schema_path or [])


class _FakeJsonSchema:
    """Minimal fake of the jsonschema module for unit tests."""

    ValidationError = _FakeValidationError

    @staticmethod
    def validate(data: Any, schema: dict[str, Any]) -> None:
        """Validate required fields and type (simplified)."""
        if "required" in schema:
            for field in schema["required"]:
                if field not in data:
                    raise _FakeValidationError(
                        f"'{field}' is a required property",
                        path=[field],
                        validator="required",
                    )
        if "type" in schema:
            t = schema["type"]
            type_map: dict[str, type] = {
                "string": str,
                "integer": int,
                "object": dict,
                "array": list,
                "boolean": bool,
            }
            if t in type_map and not isinstance(data, type_map[t]):
                raise _FakeValidationError(
                    f"{type(data).__name__} is not of type {t}",
                    validator="type",
                )


@pytest.fixture
def fake_jsonschema(monkeypatch: pytest.MonkeyPatch) -> type[_FakeJsonSchema]:
    """Inject the fake jsonschema module into sys.modules."""
    monkeypatch.setitem(sys.modules, "jsonschema", _FakeJsonSchema)
    return _FakeJsonSchema


def test_schema_valid(fake_jsonschema: type[_FakeJsonSchema]) -> None:
    """assert_schema does not raise when data is valid."""
    assert_schema(
        {"name": "alice", "age": 30},
        {"type": "object", "required": ["name", "age"]},
    )


def test_schema_missing_required_fails(fake_jsonschema: type[_FakeJsonSchema]) -> None:
    """assert_schema fails when a required field is missing."""
    with pytest.raises(FrameworkAssertionError) as info:
        assert_schema({"name": "alice"}, {"required": ["name", "age"]})
    assert "required property" in str(info.value)
    assert info.value.context["path"] == ["age"]


def test_schema_wrong_type_fails(fake_jsonschema: type[_FakeJsonSchema]) -> None:
    """assert_schema fails when the type doesn't match."""
    with pytest.raises(FrameworkAssertionError) as info:
        assert_schema("not an object", {"type": "object"})
    assert "not of type" in str(info.value)


def test_schema_custom_message(fake_jsonschema: type[_FakeJsonSchema]) -> None:
    """Custom message overrides the default on failure."""
    with pytest.raises(FrameworkAssertionError, match="my schema msg"):
        assert_schema({}, {"required": ["x"]}, message="my schema msg")


def test_schema_context_has_validator(fake_jsonschema: type[_FakeJsonSchema]) -> None:
    """Failure context includes the validator that failed."""
    with pytest.raises(FrameworkAssertionError) as info:
        assert_schema({}, {"required": ["x"]})
    assert info.value.context["validator"] == "required"


def test_schema_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """assert_schema raises when jsonschema is not installed."""
    # Setting to None (rather than deleting) simulates a missing package even
    # when jsonschema is actually installed: Python raises ImportError for a
    # None entry in sys.modules. (rule 14 - isolate external dependency)
    monkeypatch.setitem(sys.modules, "jsonschema", None)
    with pytest.raises(FrameworkAssertionError) as info:
        assert_schema({}, {"type": "object"})
    assert "not installed" in str(info.value)
