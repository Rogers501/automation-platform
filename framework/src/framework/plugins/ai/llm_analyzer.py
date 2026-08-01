"""LLM-powered failure analyzer using httpx (OpenAI-compatible API).

Implements :class:`framework.plugins.ai.base.FailureAnalyzer` by sending
the failure context to an LLM endpoint and parsing the structured response.

Supports any OpenAI-compatible chat completions API (OpenAI, Azure, Ollama,
vLLM, etc.). The API key is read from :class:`AISettings` (env-configured,
rule 10). The ``httpx`` package is a framework dependency (no lazy import
needed).

Usage::

    from framework.plugins.ai.llm_analyzer import LLMAnalyzer
    from framework.plugins.ai import set_analyzer

    set_analyzer(LLMAnalyzer())  # reads AISettings from env/config

Register in a system conftest to enable AI failure analysis.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from loguru import logger

from framework.core.config import AISettings, get_settings
from framework.plugins.ai.base import FailureAnalyzer
from framework.plugins.ai.models import AnalysisResult, FailureContext

__all__ = ["LLMAnalyzer"]


class LLMAnalyzer(FailureAnalyzer):
    """LLM-powered test failure analyzer.

    Sends the failure context to an OpenAI-compatible chat completions
    endpoint and parses the structured JSON response into an
    :class:`AnalysisResult`.

    Args:
        settings: AI settings; defaults to :func:`get_settings().ai`.
        http_client: Pre-built httpx.AsyncClient for testing (rule 14).
        name: Logical name for log correlation.
    """

    def __init__(
        self,
        settings: AISettings | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
        name: str = "llm_analyzer",
    ) -> None:
        self._settings = settings if settings is not None else get_settings().ai
        self._injected_client = http_client
        self._name = name
        self._logger = logger.bind(component=name)

    async def analyze(self, context: FailureContext) -> AnalysisResult:
        """Analyze a test failure via LLM and return structured result."""
        if not self._settings.api_key:
            return AnalysisResult(
                root_cause="LLM analyzer disabled: no API key configured",
                suggestion="Set APP_AI__API_KEY env var to enable.",
                confidence=0.0,
                category="config_error",
                metadata={"analyzer": "llm"},
            )

        prompt = self._build_prompt(context)
        response_text = await self._call_llm(prompt)
        return self._parse_response(response_text)

    def _build_prompt(self, context: FailureContext) -> str:
        """Build the user prompt from the failure context."""
        exchanges_str = ""
        if context.exchanges:
            truncated = context.exchanges[: self._settings.max_exchanges_in_prompt]
            exchanges_str = json.dumps(truncated, ensure_ascii=False, indent=2)

        parts = [
            f"Test: {context.test_name}",
            f"Node ID: {context.node_id}",
            f"Error Type: {context.error_type}",
            f"Error Message: {context.error_message}",
        ]
        if context.traceback_text:
            tb = context.traceback_text[:2000]
            parts.append(f"Traceback:\n{tb}")
        if exchanges_str:
            parts.append(f"HTTP Exchanges:\n{exchanges_str}")
        parts.append(
            "\nAnalyze this test failure. Identify the root cause and suggest a fix. "
            'Respond as JSON: {"root_cause": "...", "suggestion": "...", '
            '"confidence": 0.0-1.0, "category": "..."}'
        )
        return "\n\n".join(parts)

    async def _call_llm(self, prompt: str) -> str:
        """Send the prompt to the LLM endpoint and return the response text."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._settings.api_key}",
        }
        body: dict[str, Any] = {
            "model": self._settings.model,
            "messages": [
                {"role": "system", "content": self._settings.system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": self._settings.temperature,
            "max_tokens": self._settings.max_tokens,
        }

        client = self._injected_client
        client_owned = False
        if client is None:
            client = httpx.AsyncClient(timeout=self._settings.timeout_s)
            client_owned = True

        try:
            response = await client.post(
                self._settings.api_url,
                json=body,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            return str(data["choices"][0]["message"]["content"])
        finally:
            if client_owned:
                await client.aclose()

    def _parse_response(self, response_text: str) -> AnalysisResult:
        """Parse the LLM response text into an AnalysisResult.

        Handles JSON wrapped in markdown code blocks or plain JSON.
        Falls back to using the raw text as root_cause if parsing fails.
        """
        text = response_text.strip()
        # Strip markdown code fences if present.
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
            return AnalysisResult(
                root_cause=str(data.get("root_cause", "")),
                suggestion=str(data.get("suggestion", "")),
                confidence=float(data.get("confidence", 0.0)),
                category=str(data.get("category", "unknown")),
                metadata={"model": self._settings.model, "analyzer": "llm"},
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            # If JSON parsing fails, use the raw text as root cause.
            self._logger.warning("LLM response not valid JSON, using raw text")
            return AnalysisResult(
                root_cause=response_text[:500],
                suggestion="LLM response was not valid JSON.",
                confidence=0.3,
                category="parse_error",
                metadata={"model": self._settings.model, "analyzer": "llm"},
            )
