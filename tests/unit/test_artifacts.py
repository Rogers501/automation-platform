"""Unit tests for framework.testing.hooks.artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from framework.core.recorder import HttpExchange, RequestRecorder
from framework.testing.hooks.artifacts import sanitize_node_id, save_failure_artifacts
from framework.testing.hooks.screenshot import ScreenshotProvider


def _exchange(**overrides: Any) -> HttpExchange:
    base: dict[str, Any] = {
        "method": "GET",
        "url": "http://x/api",
        "request_headers": {},
        "request_body": None,
        "status_code": 200,
        "response_headers": {},
        "response_body": None,
        "elapsed_seconds": 0.1,
        "trace_id": "t1",
    }
    base.update(overrides)
    return HttpExchange(**base)


def test_sanitize_node_id_basic() -> None:
    """Special chars in a node id are replaced with underscores."""
    assert sanitize_node_id("tests/test_x.py::test_fail") == "tests_test_x.py_test_fail"


def test_sanitize_node_id_empty() -> None:
    """An all-separator id falls back to a default name."""
    assert sanitize_node_id(":::") == "unknown_test"


def test_sanitize_node_id_preserves_safe_chars() -> None:
    """Dots, dashes, and underscores are preserved."""
    name = sanitize_node_id("a.b-c_d")
    assert "." in name and "-" in name and "_" in name


def test_save_artifacts_writes_exchanges(tmp_path: Path) -> None:
    """Recorded exchanges are serialized to exchanges.json."""
    recorder = RequestRecorder()
    recorder.record(_exchange())
    recorder.record(_exchange(method="POST", status_code=500))
    save_failure_artifacts(
        node_id="tests/test_x.py::test_fail",
        recorder=recorder,
        screenshot_provider=None,
        artifact_dir=tmp_path,
    )
    target = tmp_path / sanitize_node_id("tests/test_x.py::test_fail")
    assert target.exists()
    data = json.loads((target / "exchanges.json").read_text(encoding="utf-8"))
    assert len(data) == 2
    assert data[0]["method"] == "GET"
    assert data[1]["status_code"] == 500
    assert data[0]["trace_id"] == "t1"


def test_save_artifacts_no_recorder(tmp_path: Path) -> None:
    """A None recorder still creates the per-test dir but no exchanges.json."""
    save_failure_artifacts(
        node_id="t::test",
        recorder=None,
        screenshot_provider=None,
        artifact_dir=tmp_path,
    )
    assert (tmp_path / "t_test").exists()
    assert not (tmp_path / "t_test" / "exchanges.json").exists()


def test_save_artifacts_empty_recorder(tmp_path: Path) -> None:
    """An empty recorder produces no exchanges.json."""
    save_failure_artifacts(
        node_id="t::test",
        recorder=RequestRecorder(),
        screenshot_provider=None,
        artifact_dir=tmp_path,
    )
    target = tmp_path / "t_test"
    assert target.exists()
    assert not (target / "exchanges.json").exists()


class _FakeShot(ScreenshotProvider):
    def __init__(self) -> None:
        self.called: list[str] = []

    def screenshot(self, name: str) -> Path | None:
        self.called.append(name)
        return None


def test_save_artifacts_calls_screenshot(tmp_path: Path) -> None:
    """The screenshot provider is invoked with the sanitized node id."""
    shot = _FakeShot()
    save_failure_artifacts(
        node_id="t::test",
        recorder=None,
        screenshot_provider=shot,
        artifact_dir=tmp_path,
    )
    assert shot.called == ["t_test"]


class _FailingShot(ScreenshotProvider):
    def screenshot(self, name: str) -> Path | None:
        raise RuntimeError("boom")


def test_save_artifacts_swallows_screenshot_error(tmp_path: Path) -> None:
    """A failing screenshot provider must not raise (best-effort persistence)."""
    save_failure_artifacts(
        node_id="t::test",
        recorder=None,
        screenshot_provider=_FailingShot(),
        artifact_dir=tmp_path,
    )
