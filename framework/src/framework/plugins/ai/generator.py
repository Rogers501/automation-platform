"""AI-powered test case generation from OpenAPI specifications.

Extends the ``plugins.ai`` module with :class:`TestCaseGenerator`, an abstract
interface for generating pytest test cases from API specs. The framework
ships :class:`LLMGenerator`, which calls an OpenAI-compatible chat completions
endpoint to produce test code.

The generator is intentionally separate from :class:`FailureAnalyzer`
(failure analysis) - it addresses a different use case (test creation vs.
failure diagnosis) but shares the same ``AISettings`` configuration.

Usage::

    from framework.plugins.ai.generator import LLMGenerator

    gen = LLMGenerator()
    cases = await gen.generate(openapi_spec, endpoint="/api/users")
    for case in cases:
        print(case.code)

All LLM calls use ``httpx`` async (rule 16). The ``http_client`` parameter
allows injecting a fake for unit tests (rule 14).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

from framework.core.config import AISettings, get_settings

__all__ = [
    "GeneratedTestCase",
    "LLMGenerator",
    "TestCaseGenerator",
]


@dataclass(frozen=True)
class GeneratedTestCase:
    """A single AI-generated test case.

    Attributes:
        code: The generated pytest test function code.
        description: A short description of what the test verifies.
        confidence: LLM confidence score (0.0-1.0).
        tags: Optional tags (e.g. ``["smoke", "happy_path"]``).
    """

    code: str
    description: str
    confidence: float = 0.5
    tags: list[str] = field(default_factory=list)


class TestCaseGenerator(ABC):
    """Abstract interface for AI test case generation.

    Implementations call an LLM or other AI service to produce pytest test
    cases from an API specification (OpenAPI / Swagger).
    """

    @abstractmethod
    async def generate(
        self,
        spec: dict[str, Any],
        *,
        endpoint: str | None = None,
        method: str | None = None,
    ) -> list[GeneratedTestCase]:
        """Generate test cases from an OpenAPI specification.

        Args:
            spec: Parsed OpenAPI spec as a dict.
            endpoint: Optional path filter (e.g. ``"/api/users"``).
            method: Optional HTTP method filter (e.g. ``"GET"``).

        Returns:
            A list of :class:`GeneratedTestCase` objects.
        """


class LLMGenerator(TestCaseGenerator):
    """LLM-powered test case generator (OpenAI-compatible API).

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
        name: str = "llm_generator",
    ) -> None:
        self._settings = settings if settings is not None else get_settings().ai
        self._injected_client = http_client
        self._name = name
        self._logger = logger.bind(component=name)

    async def generate(
        self,
        spec: dict[str, Any],
        *,
        endpoint: str | None = None,
        method: str | None = None,
    ) -> list[GeneratedTestCase]:
        """Generate test cases from an OpenAPI spec via LLM."""
        if not self._settings.api_key:
            self._logger.warning("LLM generator disabled: no API key configured")
            return []

        prompt = self._build_prompt(spec, endpoint=endpoint, method=method)
        response_text = await self._call_llm(prompt)
        return self._parse_response(response_text)

    def _build_prompt(
        self,
        spec: dict[str, Any],
        *,
        endpoint: str | None,
        method: str | None,
    ) -> str:
        """Build the user prompt from the OpenAPI spec."""
        spec_str = json.dumps(spec, ensure_ascii=False, indent=2)
        parts = [
            "You are a test engineer. Generate pytest test cases for the "
            "following OpenAPI specification.",
        ]
        if endpoint:
            parts.append(f"Focus on endpoint: {endpoint}")
        if method:
            parts.append(f"Focus on HTTP method: {method}")
        parts.append(
            "For each test case, output a JSON array where each element has: "
            '"code" (the pytest test function as a string), "description" '
            '(short description), "confidence" (0.0-1.0), "tags" (list of '
            'strings like "smoke", "happy_path", "error_case").'
        )
        parts.append(f"\nOpenAPI Spec:\n{spec_str}")
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
                {"role": "system", "content": "You are a helpful test engineering assistant."},
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

    def _parse_response(self, response_text: str) -> list[GeneratedTestCase]:
        """Parse the LLM response into a list of GeneratedTestCase.

        Handles JSON wrapped in markdown code blocks or plain JSON.
        Falls back to a single test case with the raw text if parsing fails.
        """
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
            if isinstance(data, dict):
                data = [data]
            cases: list[GeneratedTestCase] = []
            for item in data:
                cases.append(
                    GeneratedTestCase(
                        code=str(item.get("code", "")),
                        description=str(item.get("description", "")),
                        confidence=float(item.get("confidence", 0.5)),
                        tags=list(item.get("tags", [])),
                    )
                )
            return cases
        except (json.JSONDecodeError, ValueError, TypeError):
            self._logger.warning("LLM response not valid JSON, using raw text")
            return [
                GeneratedTestCase(
                    code=response_text[:2000],
                    description="Raw LLM response (not valid JSON)",
                    confidence=0.2,
                    tags=["unparsed"],
                )
            ]
