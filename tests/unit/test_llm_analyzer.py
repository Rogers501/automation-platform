"""Unit tests for LLMAnalyzer using a fake httpx client (rule 14)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from framework.core.config import AISettings
from framework.plugins.ai import (
    FailureAnalyzer,
    FailureContext,
    LLMAnalyzer,
    get_analyzer,
    set_analyzer,
)

# ---------------------------------------------------------------------------
# Fake httpx client
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Fake httpx.Response."""

    def __init__(
        self,
        content: str,
        *,
        status_code: int = 200,
        json_data: dict[str, Any] | None = None,
    ) -> None:
        self._content = content
        self.status_code = status_code
        self._json = json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("POST", "https://fake"),
                response=httpx.Response(self.status_code),
            )

    def json(self) -> dict[str, Any]:
        if self._json is not None:
            return self._json
        return {"choices": [{"message": {"content": self._content}}]}


class _FakeAsyncClient:
    """Fake httpx.AsyncClient that returns a canned response."""

    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.requests: list[dict[str, Any]] = []
        self.closed = False

    async def post(self, url: str, *, json: Any, headers: Any) -> _FakeResponse:
        self.requests.append({"url": url, "json": json, "headers": headers})
        return self._response

    async def aclose(self) -> None:
        self.closed = True


def _context(**kwargs: Any) -> FailureContext:
    """Build a FailureContext with defaults."""
    defaults: dict[str, Any] = {
        "node_id": "tests/test_x.py::test_foo",
        "test_name": "test_foo",
        "error_type": "AssertionError",
        "error_message": "assert 1 == 2",
    }
    defaults.update(kwargs)
    return FailureContext(**defaults)


def _analyzer(
    response_content: str = "",
    *,
    settings: AISettings | None = None,
    json_data: dict[str, Any] | None = None,
) -> tuple[LLMAnalyzer, _FakeAsyncClient]:
    """Build an LLMAnalyzer with a fake httpx client."""
    resp = _FakeResponse(response_content, json_data=json_data)
    fake = _FakeAsyncClient(resp)
    s = settings or AISettings(
        api_key="sk-test",
        model="gpt-4o-mini",
        api_url="https://fake.test/v1/chat/completions",
    )
    analyzer = LLMAnalyzer(settings=s, http_client=fake)
    return analyzer, fake


# ---------------------------------------------------------------------------
# Analyze
# ---------------------------------------------------------------------------


async def test_analyze_returns_parsed_result() -> None:
    """analyze parses a valid JSON LLM response."""
    llm_response = json.dumps(
        {
            "root_cause": "value mismatch",
            "suggestion": "fix the assertion",
            "confidence": 0.9,
            "category": "assertion",
        }
    )
    analyzer, fake = _analyzer(llm_response)

    result = await analyzer.analyze(_context())

    assert result.root_cause == "value mismatch"
    assert result.suggestion == "fix the assertion"
    assert result.confidence == 0.9
    assert result.category == "assertion"
    assert result.metadata["model"] == "gpt-4o-mini"
    assert result.metadata["analyzer"] == "llm"
    # Verify the request was sent.
    assert len(fake.requests) == 1
    req = fake.requests[0]
    assert req["headers"]["Authorization"] == "Bearer sk-test"
    assert req["json"]["model"] == "gpt-4o-mini"


async def test_analyze_strips_markdown_fences() -> None:
    """analyze handles JSON wrapped in markdown code fences."""
    llm_response = (
        "```json\n"
        + json.dumps(
            {
                "root_cause": "timeout",
                "suggestion": "increase timeout",
                "confidence": 0.8,
                "category": "timeout",
            }
        )
        + "\n```"
    )
    analyzer, _ = _analyzer(llm_response)

    result = await analyzer.analyze(_context())

    assert result.root_cause == "timeout"
    assert result.confidence == 0.8
    assert result.category == "timeout"


async def test_analyze_invalid_json_fallback() -> None:
    """analyze falls back to raw text when LLM returns non-JSON."""
    analyzer, _ = _analyzer("This is not JSON at all.")

    result = await analyzer.analyze(_context())

    assert result.category == "parse_error"
    assert "This is not JSON" in result.root_cause
    assert result.confidence == 0.3


async def test_analyze_no_api_key_returns_config_error() -> None:
    """analyze returns config_error when no API key is set."""
    analyzer = LLMAnalyzer(settings=AISettings(api_key=""))

    result = await analyzer.analyze(_context())

    assert result.category == "config_error"
    assert "no API key" in result.root_cause
    assert result.confidence == 0.0


async def test_analyze_includes_exchanges_in_prompt() -> None:
    """analyze includes HTTP exchanges in the prompt."""
    llm_response = json.dumps({"root_cause": "api error", "confidence": 0.7})
    analyzer, fake = _analyzer(llm_response)

    ctx = _context(exchanges=[{"method": "GET", "url": "http://test/api", "status": 500}])
    await analyzer.analyze(ctx)

    prompt = fake.requests[0]["json"]["messages"][1]["content"]
    assert "GET" in prompt
    assert "http://test/api" in prompt


async def test_analyze_truncates_exchanges() -> None:
    """analyze limits exchanges in prompt to max_exchanges_in_prompt."""
    llm_response = json.dumps({"root_cause": "ok", "confidence": 0.5})
    settings = AISettings(api_key="sk-test", max_exchanges_in_prompt=2)
    analyzer, fake = _analyzer(llm_response, settings=settings)

    exchanges = [{"method": "GET", "url": f"http://test/{i}"} for i in range(10)]
    await analyzer.analyze(_context(exchanges=exchanges))

    prompt = fake.requests[0]["json"]["messages"][1]["content"]
    assert "http://test/0" in prompt
    assert "http://test/1" in prompt
    assert "http://test/2" not in prompt


async def test_analyze_includes_traceback_in_prompt() -> None:
    """analyze includes traceback in the prompt when available."""
    llm_response = json.dumps({"root_cause": "tb error", "confidence": 0.6})
    analyzer, fake = _analyzer(llm_response)

    await analyzer.analyze(_context(traceback_text="Traceback: ValueError at line 42"))

    prompt = fake.requests[0]["json"]["messages"][1]["content"]
    assert "Traceback" in prompt
    assert "ValueError" in prompt


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_llm_analyzer_is_failure_analyzer() -> None:
    """LLMAnalyzer is a FailureAnalyzer."""
    analyzer = LLMAnalyzer(settings=AISettings(api_key="sk-test"))
    assert isinstance(analyzer, FailureAnalyzer)


def test_register_llm_analyzer() -> None:
    """LLMAnalyzer can be registered as the global analyzer."""
    original = get_analyzer()
    try:
        set_analyzer(LLMAnalyzer(settings=AISettings(api_key="sk-test")))
        assert isinstance(get_analyzer(), LLMAnalyzer)
    finally:
        set_analyzer(original)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_ai_settings_defaults() -> None:
    """AISettings has sensible defaults."""
    settings = AISettings()
    assert settings.enabled is False
    assert settings.provider == "openai"
    assert settings.model == "gpt-4o-mini"
    assert settings.temperature == 0.3
    assert settings.max_tokens == 1024
    assert settings.timeout_s == 30.0


def test_ai_settings_custom() -> None:
    """AISettings accepts custom values."""
    settings = AISettings(
        enabled=True,
        provider="ollama",
        api_url="http://localhost:11434/v1/chat/completions",
        model="llama3",
    )
    assert settings.provider == "ollama"
    assert settings.api_url == "http://localhost:11434/v1/chat/completions"
    assert settings.model == "llama3"
