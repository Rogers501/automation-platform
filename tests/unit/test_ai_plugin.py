"""Unit tests for the AI failure analysis plugin (rule 14 - no real AI calls)."""

from __future__ import annotations

import pytest

from framework.plugins.ai import (
    AnalysisResult,
    FailureAnalyzer,
    FailureContext,
    NullFailureAnalyzer,
    analyze_failure,
    build_failure_context,
    get_analyzer,
    set_analyzer,
)
from framework.plugins.ai.base import FailureAnalyzer as BaseAnalyzer

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


def test_failure_context_defaults() -> None:
    """FailureContext requires only node_id, test_name, error_type, error_message."""
    ctx = FailureContext(
        node_id="tests/test_x.py::test_foo",
        test_name="test_foo",
        error_type="AssertionError",
        error_message="assert 1 == 2",
    )
    assert ctx.node_id == "tests/test_x.py::test_foo"
    assert ctx.test_name == "test_foo"
    assert ctx.error_type == "AssertionError"
    assert ctx.error_message == "assert 1 == 2"
    assert ctx.traceback_text == ""
    assert ctx.exchanges == []
    assert ctx.extra == {}


def test_failure_context_full() -> None:
    """FailureContext accepts all fields."""
    ctx = FailureContext(
        node_id="t::test_bar",
        test_name="test_bar",
        error_type="ValueError",
        error_message="bad value",
        traceback_text="traceback here",
        exchanges=[{"method": "GET", "url": "http://test"}],
        extra={"env": "test"},
    )
    assert ctx.traceback_text == "traceback here"
    assert ctx.exchanges == [{"method": "GET", "url": "http://test"}]
    assert ctx.extra == {"env": "test"}


def test_failure_context_is_frozen() -> None:
    """FailureContext is immutable."""
    ctx = FailureContext(
        node_id="t::test_f",
        test_name="test_f",
        error_type="Error",
        error_message="msg",
    )
    with pytest.raises(AttributeError):
        ctx.test_name = "other"  # type: ignore[misc]


def test_analysis_result_defaults() -> None:
    """AnalysisResult defaults to empty/unknown."""
    result = AnalysisResult()
    assert result.root_cause == ""
    assert result.suggestion == ""
    assert result.confidence == 0.0
    assert result.category == "unknown"
    assert result.metadata == {}


def test_analysis_result_full() -> None:
    """AnalysisResult accepts all fields."""
    result = AnalysisResult(
        root_cause="timeout",
        suggestion="increase timeout",
        confidence=0.85,
        category="timeout",
        metadata={"model": "gpt-4"},
    )
    assert result.root_cause == "timeout"
    assert result.suggestion == "increase timeout"
    assert result.confidence == 0.85
    assert result.category == "timeout"
    assert result.metadata == {"model": "gpt-4"}


def test_analysis_result_is_frozen() -> None:
    """AnalysisResult is immutable."""
    result = AnalysisResult()
    with pytest.raises(AttributeError):
        result.root_cause = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# FailureAnalyzer ABC
# ---------------------------------------------------------------------------


def test_failure_analyzer_is_abstract() -> None:
    """FailureAnalyzer cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseAnalyzer()  # type: ignore[abstract]


def test_failure_analyzer_subclass_works() -> None:
    """A fully-implemented subclass can be instantiated."""

    class _Stub(FailureAnalyzer):
        async def analyze(self, context: FailureContext) -> AnalysisResult:
            return AnalysisResult(root_cause="stub", confidence=0.5)

    analyzer = _Stub()
    assert isinstance(analyzer, FailureAnalyzer)


# ---------------------------------------------------------------------------
# NullFailureAnalyzer
# ---------------------------------------------------------------------------


async def test_null_analyzer_returns_empty() -> None:
    """NullFailureAnalyzer returns an empty, no-op result."""
    analyzer = NullFailureAnalyzer()
    ctx = FailureContext(
        node_id="t::test",
        test_name="test",
        error_type="Error",
        error_message="msg",
    )
    result = await analyzer.analyze(ctx)
    assert result.root_cause == ""
    assert result.confidence == 0.0
    assert result.category == "no_analyzer"
    assert result.metadata["analyzer"] == "null"


# ---------------------------------------------------------------------------
# set_analyzer / get_analyzer
# ---------------------------------------------------------------------------


def test_get_analyzer_returns_null_by_default() -> None:
    """get_analyzer returns NullFailureAnalyzer when nothing is registered."""
    analyzer = get_analyzer()
    assert isinstance(analyzer, NullFailureAnalyzer)


def test_set_analyzer_registers_custom() -> None:
    """set_analyzer replaces the global analyzer."""
    original = get_analyzer()

    class _Custom(FailureAnalyzer):
        async def analyze(self, context: FailureContext) -> AnalysisResult:
            return AnalysisResult(root_cause="custom", confidence=0.9)

    custom = _Custom()
    try:
        set_analyzer(custom)
        assert get_analyzer() is custom
    finally:
        set_analyzer(original)


# ---------------------------------------------------------------------------
# analyze_failure
# ---------------------------------------------------------------------------


async def test_analyze_failure_calls_analyzer() -> None:
    """analyze_failure delegates to the registered analyzer."""
    original = get_analyzer()

    class _Stub(FailureAnalyzer):
        def __init__(self) -> None:
            self.called = False

        async def analyze(self, context: FailureContext) -> AnalysisResult:
            self.called = True
            return AnalysisResult(root_cause="stub", confidence=0.7)

    stub = _Stub()
    set_analyzer(stub)
    try:
        ctx = FailureContext(
            node_id="t::test",
            test_name="test",
            error_type="Error",
            error_message="msg",
        )
        result = await analyze_failure(ctx)
        assert stub.called
        assert result.root_cause == "stub"
        assert result.confidence == 0.7
    finally:
        set_analyzer(original)


async def test_analyze_failure_catches_errors() -> None:
    """A broken analyzer does not propagate; returns low-confidence result."""
    original = get_analyzer()

    class _Broken(FailureAnalyzer):
        async def analyze(self, context: FailureContext) -> AnalysisResult:
            raise RuntimeError("AI API is down")

    set_analyzer(_Broken())
    try:
        ctx = FailureContext(
            node_id="t::test",
            test_name="test",
            error_type="Error",
            error_message="msg",
        )
        result = await analyze_failure(ctx)
        assert result.category == "analyzer_error"
        assert "AI API is down" in result.root_cause
        assert result.confidence == 0.0
    finally:
        set_analyzer(original)


# ---------------------------------------------------------------------------
# build_failure_context
# ---------------------------------------------------------------------------


def test_build_failure_context_from_excinfo() -> None:
    """build_failure_context extracts error info from an ExceptionInfo-like object."""

    class _FakeExcInfo:
        def __init__(self) -> None:
            try:
                raise ValueError("test error")
            except ValueError as exc:
                self.value = exc

        def __str__(self) -> str:
            return "Traceback (most recent call last):\n  ValueError: test error"

    excinfo = _FakeExcInfo()
    ctx = build_failure_context(
        node_id="tests/test_x.py::test_foo",
        test_name="test_foo",
        excinfo=excinfo,
    )
    assert ctx.node_id == "tests/test_x.py::test_foo"
    assert ctx.test_name == "test_foo"
    assert ctx.error_type == "ValueError"
    assert ctx.error_message == "test error"
    assert "Traceback" in ctx.traceback_text


def test_build_failure_context_with_none() -> None:
    """build_failure_context handles None excinfo gracefully."""
    ctx = build_failure_context(
        node_id="t::test",
        test_name="test",
        excinfo=None,
    )
    assert ctx.error_type == ""
    assert ctx.error_message == ""


def test_build_failure_context_with_exchanges() -> None:
    """build_failure_context includes HTTP exchanges and extra data."""
    ctx = build_failure_context(
        node_id="t::test",
        test_name="test",
        excinfo=None,
        exchanges=[{"method": "GET"}],
        extra={"env": "uat"},
    )
    assert ctx.exchanges == [{"method": "GET"}]
    assert ctx.extra == {"env": "uat"}


def test_build_failure_context_exchanges_independent() -> None:
    """The exchanges list is copied, not shared."""
    exchanges = [{"method": "GET"}]
    ctx = build_failure_context(
        node_id="t::test",
        test_name="test",
        excinfo=None,
        exchanges=exchanges,
    )
    exchanges.append({"method": "POST"})
    assert ctx.exchanges == [{"method": "GET"}]
