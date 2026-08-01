"""AI Agent adapter extension point.

Provides the :class:`FailureAnalyzer` plugin interface for AI-powered test
failure analysis. The framework ships a :class:`NullFailureAnalyzer` default;
register a custom analyzer via :func:`set_analyzer` in a system conftest::

    from framework.plugins.ai import set_analyzer, FailureAnalyzer

    class OpenAIAnalyzer(FailureAnalyzer):
        async def analyze(self, ctx):
            # call OpenAI / Claude / Ollama here
            return AnalysisResult(root_cause="...", suggestion="...")

    set_analyzer(OpenAIAnalyzer(api_key="sk-..."))

The hooks layer calls :func:`get_analyzer` on test failure and attaches the
result to the Allure report (if Allure is installed).

The module also provides :class:`TestCaseGenerator` / :class:`LLMGenerator`
for AI-powered test case generation from OpenAPI specs.
"""

from __future__ import annotations

from typing import Any

from framework.plugins.ai.base import FailureAnalyzer
from framework.plugins.ai.generator import GeneratedTestCase, LLMGenerator, TestCaseGenerator
from framework.plugins.ai.llm_analyzer import LLMAnalyzer
from framework.plugins.ai.models import AnalysisResult, FailureContext
from framework.plugins.ai.null_analyzer import NullFailureAnalyzer

__all__ = [
    "AnalysisResult",
    "FailureAnalyzer",
    "FailureContext",
    "GeneratedTestCase",
    "LLMAnalyzer",
    "LLMGenerator",
    "NullFailureAnalyzer",
    "TestCaseGenerator",
    "analyze_failure",
    "get_analyzer",
    "set_analyzer",
]

_analyzer: FailureAnalyzer = NullFailureAnalyzer()


def set_analyzer(analyzer: FailureAnalyzer) -> None:
    """Register a global failure analyzer instance.

    Args:
        analyzer: The analyzer to use for subsequent test failures.
    """
    global _analyzer
    _analyzer = analyzer


def get_analyzer() -> FailureAnalyzer:
    """Return the currently registered failure analyzer."""
    return _analyzer


async def analyze_failure(context: FailureContext) -> AnalysisResult:
    """Run the registered analyzer on a failure context.

    Errors from the analyzer are caught and converted to a low-confidence
    result so a broken AI backend never masks the original test failure.
    """
    try:
        return await _analyzer.analyze(context)
    except Exception as exc:
        return AnalysisResult(
            root_cause=f"Analyzer error: {exc}",
            suggestion="Check analyzer configuration.",
            confidence=0.0,
            category="analyzer_error",
            metadata={"error_type": type(exc).__name__},
        )


def build_failure_context(
    node_id: str,
    test_name: str,
    excinfo: Any,
    *,
    exchanges: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> FailureContext:
    """Construct a :class:`FailureContext` from pytest failure information.

    Args:
        node_id: pytest node id (e.g. ``tests/test_x.py::test_foo``).
        test_name: Short test function name.
        excinfo: pytest ``ExceptionInfo`` (from ``request.node.excinfo`` or
            ``call.excinfo`` in ``pytest_runtest_makereport``).
        exchanges: Recorded HTTP exchanges as dicts (from ``RequestRecorder``).
        extra: Arbitrary additional context.

    Returns:
        A :class:`FailureContext` ready for analysis.
    """
    error_type = ""
    error_message = ""
    traceback_text = ""

    if excinfo is not None:
        error_type = type(excinfo.value).__name__ if hasattr(excinfo, "value") else str(excinfo)
        error_message = str(excinfo.value) if hasattr(excinfo, "value") else str(excinfo)
        traceback_text = str(excinfo) if hasattr(excinfo, "__str__") else ""

    return FailureContext(
        node_id=node_id,
        test_name=test_name,
        error_type=error_type,
        error_message=error_message,
        traceback_text=traceback_text,
        exchanges=list(exchanges or []),
        extra=dict(extra or {}),
    )
