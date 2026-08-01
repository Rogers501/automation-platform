"""Unit tests for framework.testing.datadriven."""

from __future__ import annotations

from pathlib import Path

import pytest

from framework.testing.datadriven import CaseError, case_ids, load_cases


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_load_cases_top_level_list(tmp_path: Path) -> None:
    """A top-level list of mappings is loaded as-is."""
    path = _write(tmp_path, "cases.yaml", "- name: a\n  status: 200\n- name: b\n  status: 404\n")
    cases = load_cases(path)
    assert cases == [{"name": "a", "status": 200}, {"name": "b", "status": 404}]


def test_load_cases_cases_key(tmp_path: Path) -> None:
    """A mapping with a ``cases`` key loads the inner list."""
    path = _write(tmp_path, "cases.yaml", "meta: x\ncases:\n  - name: a\n  - name: b\n")
    cases = load_cases(path)
    assert [c["name"] for c in cases] == ["a", "b"]


def test_load_cases_empty_list(tmp_path: Path) -> None:
    """An empty list yields no cases."""
    path = _write(tmp_path, "empty.yaml", "[]\n")
    assert load_cases(path) == []


def test_load_cases_missing_file(tmp_path: Path) -> None:
    """A missing file raises CaseError."""
    with pytest.raises(CaseError):
        load_cases(tmp_path / "nope.yaml")


def test_load_cases_invalid_yaml(tmp_path: Path) -> None:
    """Malformed YAML raises CaseError."""
    path = _write(tmp_path, "bad.yaml", "name: [unterminated\n")
    with pytest.raises(CaseError):
        load_cases(path)


def test_load_cases_not_a_list(tmp_path: Path) -> None:
    """A non-list root raises CaseError."""
    path = _write(tmp_path, "scalar.yaml", "just a string\n")
    with pytest.raises(CaseError):
        load_cases(path)


def test_load_cases_non_mapping_item(tmp_path: Path) -> None:
    """A list with a non-mapping item raises CaseError."""
    path = _write(tmp_path, "mixed.yaml", "- name: a\n- notamapping\n")
    with pytest.raises(CaseError):
        load_cases(path)


def test_case_ids_from_name() -> None:
    """case_ids prefers the ``name`` field."""
    cases = [{"name": "alpha"}, {"name": "beta"}]
    assert case_ids(cases) == ["alpha", "beta"]


def test_case_ids_from_id_then_index() -> None:
    """case_ids falls back to ``id`` then the index."""
    cases = [{"id": "x"}, {}, {}]
    assert case_ids(cases) == ["x", "1", "2"]


def test_case_error_is_framework_error() -> None:
    """CaseError derives from FrameworkError (carries context)."""
    assert issubclass(CaseError, Exception)
    err = CaseError("boom", context={"path": "x"})
    assert err.context == {"path": "x"}
