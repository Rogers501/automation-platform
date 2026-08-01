"""Unit tests for framework.reporting.history (temp dirs, rule 13)."""

from __future__ import annotations

import json
from pathlib import Path

from framework.reporting.history import (
    copy_history_to_results,
    preserve_history,
)


def _make_result(dir_path: Path, name: str, data: str = "{}") -> Path:
    """Create a fake Allure result file."""
    p = dir_path / name
    p.write_text(data, encoding="utf-8")
    return p


def test_preserve_history_copies_files(tmp_path: Path) -> None:
    results = tmp_path / "allure-results"
    results.mkdir()
    _make_result(results, "result-1.json")
    _make_result(results, "result-2.json")
    _make_result(results, "attachment-1.png", data="fake-png")

    history = tmp_path / "history"
    count = preserve_history(results, history)

    assert count == 3
    assert (history / "result-1.json").exists()
    assert (history / "result-2.json").exists()
    assert (history / "attachment-1.png").exists()


def test_preserve_history_missing_dir(tmp_path: Path) -> None:
    count = preserve_history(tmp_path / "nonexistent", tmp_path / "history")
    assert count == 0


def test_preserve_history_ignores_non_result_files(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    _make_result(results, "result.json")
    (results / "readme.md").write_text("not a result", encoding="utf-8")
    (results / "executor.xml").write_text("<x/>", encoding="utf-8")

    history = tmp_path / "history"
    count = preserve_history(results, history)

    assert count == 2  # .json and .xml are result files
    assert not (history / "readme.md").exists()


def test_copy_history_to_results(tmp_path: Path) -> None:
    history = tmp_path / "history"
    history.mkdir()
    _make_result(history, "old-1.json", data=json.dumps({"old": True}))
    _make_result(history, "old-2.json")

    results = tmp_path / "allure-results"
    results.mkdir()
    _make_result(results, "current.json")

    count = copy_history_to_results(history, results)

    assert count == 2
    assert (results / "old-1.json").exists()
    assert (results / "current.json").exists()


def test_copy_history_does_not_overwrite(tmp_path: Path) -> None:
    history = tmp_path / "history"
    history.mkdir()
    _make_result(history, "shared.json", data="old")

    results = tmp_path / "results"
    results.mkdir()
    _make_result(results, "shared.json", data="new")

    count = copy_history_to_results(history, results)

    assert count == 0
    assert (results / "shared.json").read_text(encoding="utf-8") == "new"


def test_copy_history_missing_dir(tmp_path: Path) -> None:
    results = tmp_path / "results"
    count = copy_history_to_results(tmp_path / "nope", results)
    assert count == 0


def test_preserve_history_creates_history_dir(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    _make_result(results, "r.json")

    history = tmp_path / "deep" / "history"
    assert not history.exists()

    preserve_history(results, history)
    assert history.exists()


def test_preserve_history_prunes_old_files(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    for i in range(10):
        _make_result(results, f"r-{i}.json")

    history = tmp_path / "history"
    preserve_history(results, history, max_runs=5)

    files = list(history.glob("*.json"))
    assert len(files) == 5
