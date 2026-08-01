"""Pytest fixtures and hooks: env init, trace context, and failure artifacts.

Enable in a consuming system's ``conftest.py``::

    pytest_plugins = ["framework.testing.hooks.fixtures"]

Fixtures provided:

- ``framework_env`` (session): initializes logging and configuration once.
- ``test_context`` (function): opens a trace scope plus a request recorder;
  on test failure, persists recorded HTTP exchanges and triggers a screenshot.
- ``screenshot_provider`` (function): the active :class:`ScreenshotProvider`
  (default no-op; override in a system conftest to enable Web/App capture).
- ``artifact_dir`` (session): base directory for failure artifacts.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from framework.core.config import FrameworkSettings, get_settings
from framework.core.context import TestContext, trace
from framework.core.logger import get_logger, setup_logging
from framework.core.recorder import bind_recorder
from framework.plugins.ai import analyze_failure, build_failure_context
from framework.reporting.allure import attach_exchanges
from framework.testing.hooks.artifacts import save_failure_artifacts
from framework.testing.hooks.screenshot import NullScreenshotProvider, ScreenshotProvider

__all__ = [
    "artifact_dir",
    "framework_env",
    "screenshot_provider",
    "test_context",
]

#: Stash key for the call-phase test report, so fixtures can detect failure.
_CALL_REPORT: pytest.StashKey[pytest.TestReport] = pytest.StashKey()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Any:
    """Stash the call-phase report so fixtures can detect failures at teardown."""
    outcome = yield
    report = outcome.get_result()
    if report.when == "call":
        item.stash[_CALL_REPORT] = report


@pytest.fixture(scope="session")
def framework_env() -> Iterator[FrameworkSettings]:
    """Initialize logging and configuration once per session."""
    settings = get_settings()
    setup_logging(settings)
    yield settings


@pytest.fixture(scope="session")
def artifact_dir(framework_env: FrameworkSettings) -> Path:
    """Base directory for failure artifacts (persistent; override for tests)."""
    path = Path(framework_env.log_dir) / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def screenshot_provider() -> ScreenshotProvider:
    """Active screenshot provider; override in a system conftest for Web/App."""
    return NullScreenshotProvider()


@pytest.fixture
def test_context(
    request: pytest.FixtureRequest,
    framework_env: FrameworkSettings,
    screenshot_provider: ScreenshotProvider,
    artifact_dir: Path,
) -> Iterator[TestContext]:
    """Open a trace scope + request recorder; on failure, persist artifacts.

    Yields the active :class:`TestContext` (with an auto-generated trace id).
    Capability clients (e.g. the HTTP client) record exchanges to the bound
    recorder; if the test fails, those exchanges are written to ``artifact_dir``
    and a screenshot is captured via ``screenshot_provider``.
    """
    with trace() as ctx, bind_recorder() as recorder:
        yield ctx
    # Auto-attach recorded HTTP exchanges to the Allure report (no-op w/o allure).
    attach_exchanges(recorder.exchanges)
    report = request.node.stash.get(_CALL_REPORT, None)
    if report is not None and report.failed:
        save_failure_artifacts(
            node_id=request.node.nodeid,
            recorder=recorder,
            screenshot_provider=screenshot_provider,
            artifact_dir=artifact_dir,
        )
        _run_ai_analysis(
            node_id=request.node.nodeid,
            test_name=request.node.name,
            report=report,
            recorder=recorder,
        )


def _run_ai_analysis(
    *,
    node_id: str,
    test_name: str,
    report: pytest.TestReport,
    recorder: Any,
) -> None:
    """Run the registered AI analyzer on a test failure (best-effort).

    The result is logged and, if Allure is installed, attached to the report.
    Any exception from the analyzer is caught so it never masks the original
    test failure.
    """
    from framework.plugins.ai import get_analyzer
    from framework.plugins.ai.null_analyzer import NullFailureAnalyzer

    analyzer = get_analyzer()
    if isinstance(analyzer, NullFailureAnalyzer):
        return

    from dataclasses import asdict

    exchanges_data: list[dict[str, Any]] = []
    if recorder is not None:
        exchanges_data = [
            asdict(e) if hasattr(e, "__dataclass_fields__") else e for e in recorder.exchanges
        ]

    context = build_failure_context(
        node_id=node_id,
        test_name=test_name,
        excinfo=report.longrepr,
        exchanges=exchanges_data,
    )
    try:
        result = asyncio.run(analyze_failure(context))
    except RuntimeError:
        return
    except Exception:
        return

    log = get_logger("ai_analyzer")
    if result.root_cause:
        log.info(
            "AI analysis for {}: root_cause={} confidence={}",
            test_name,
            result.root_cause,
            result.confidence,
        )
    _attach_analysis_to_allure(test_name, result)


def _attach_analysis_to_allure(test_name: str, result: Any) -> None:
    """Attach the AI analysis result to the Allure report (if installed)."""
    try:
        import allure
    except ImportError:
        return
    from dataclasses import asdict

    allure.attach(
        json.dumps(asdict(result), ensure_ascii=False, indent=2),
        name=f"AI Analysis: {test_name}",
        attachment_type=allure.attachment_type.JSON,
    )
