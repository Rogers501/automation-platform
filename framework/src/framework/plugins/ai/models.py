"""Data structures for AI failure analysis results.

Defines :class:`FailureContext` (the input to analysis) and
:class:`AnalysisResult` (the structured output). Both are frozen dataclasses
so they can be safely shared across threads/processes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["AnalysisResult", "FailureContext"]


@dataclass(frozen=True)
class FailureContext:
    """Context about a test failure, passed to :class:`FailureAnalyzer`.

    Attributes:
        node_id: pytest node id of the failed test (e.g. ``tests/test_x.py::test_foo``).
        test_name: Short test function name.
        error_type: Exception class name (e.g. ``AssertionError``).
        error_message: The exception message string.
        traceback_text: Full traceback as a string.
        exchanges: Recorded HTTP exchanges (list of dicts) if available.
        extra: Arbitrary additional context (logs, screenshots path, etc.).
    """

    node_id: str
    test_name: str
    error_type: str
    error_message: str
    traceback_text: str = ""
    exchanges: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalysisResult:
    """Structured result of AI failure analysis.

    Attributes:
        root_cause: The AI's best guess at the root cause.
        suggestion: A recommended fix or next step.
        confidence: Confidence score 0.0-1.0.
        category: A short category tag (e.g. ``assertion``, ``timeout``,
            ``env``, ``data``, ``unknown``).
        metadata: Extra analyzer-specific metadata.
    """

    root_cause: str = ""
    suggestion: str = ""
    confidence: float = 0.0
    category: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)
