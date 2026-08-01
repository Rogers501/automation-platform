"""Unit tests for framework.reporting.environment (rule 14: no external deps)."""

from __future__ import annotations

import json
from pathlib import Path

from framework.reporting.environment import (
    default_categories,
    write_categories,
    write_environment,
)


def test_write_environment_creates_file(tmp_path: Path) -> None:
    """write_environment writes environment.properties."""
    env = {"base_url": "https://api.example.com", "env": "test"}
    result = write_environment(tmp_path / "allure-results", env)

    assert result.name == "environment.properties"
    assert result.exists()
    content = result.read_text(encoding="utf-8")
    assert "base_url=https://api.example.com" in content
    assert "env=test" in content


def test_write_environment_creates_dir(tmp_path: Path) -> None:
    """write_environment creates the results directory if missing."""
    target = tmp_path / "nested" / "allure-results"
    assert not target.exists()

    write_environment(target, {"key": "value"})

    assert target.exists()
    assert (target / "environment.properties").exists()


def test_write_environment_empty(tmp_path: Path) -> None:
    """write_environment handles empty env dict."""
    result = write_environment(tmp_path, {})
    assert result.exists()
    content = result.read_text(encoding="utf-8")
    assert content.strip() == ""


def test_default_categories_structure() -> None:
    """default_categories returns a valid category list."""
    cats = default_categories()
    assert len(cats) == 3
    names = [c["name"] for c in cats]
    assert "Product defects" in names
    assert "Test defects" in names
    assert "Flaky tests" in names
    for cat in cats:
        assert "matchedStatuses" in cat
        assert isinstance(cat["matchedStatuses"], list)


def test_write_categories_default(tmp_path: Path) -> None:
    """write_categories writes categories.json with defaults."""
    target = tmp_path / "allure-results"
    result = write_categories(target)

    assert result.name == "categories.json"
    assert result.exists()
    data = json.loads(result.read_text(encoding="utf-8"))
    assert len(data) == 3
    assert data[0]["name"] == "Product defects"


def test_write_categories_custom(tmp_path: Path) -> None:
    """write_categories accepts custom categories."""
    custom = [{"name": "My category", "matchedStatuses": ["failed"]}]
    result = write_categories(tmp_path, custom)

    data = json.loads(result.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["name"] == "My category"


def test_write_categories_creates_dir(tmp_path: Path) -> None:
    """write_categories creates the results directory if missing."""
    target = tmp_path / "deep" / "nested" / "results"
    assert not target.exists()

    write_categories(target)
    assert (target / "categories.json").exists()


def test_write_environment_and_categories_together(tmp_path: Path) -> None:
    """environment + categories can be written to the same dir."""
    results = tmp_path / "allure-results"
    write_environment(results, {"env": "test"})
    write_categories(results)

    assert (results / "environment.properties").exists()
    assert (results / "categories.json").exists()
