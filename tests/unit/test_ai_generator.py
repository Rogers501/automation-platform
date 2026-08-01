"""Unit tests for framework.plugins.ai.generator using a fake httpx client (rule 14)."""

from __future__ import annotations

import json
from typing import Any

from framework.core.config import AISettings
from framework.plugins.ai import GeneratedTestCase, LLMGenerator, TestCaseGenerator


class _FakeResponse:
    def __init__(self, content: str, *, json_data: dict[str, Any] | None = None) -> None:
        self._content = content
        self.status_code = 200
        self._json = json_data

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        if self._json is not None:
            return self._json
        return {"choices": [{"message": {"content": self._content}}]}


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.requests: list[dict[str, Any]] = []
        self.closed = False

    async def post(self, url: str, *, json: Any, headers: Any) -> _FakeResponse:
        self.requests.append({"url": url, "json": json, "headers": headers})
        return self._response

    async def aclose(self) -> None:
        self.closed = True


def _settings() -> AISettings:
    return AISettings(api_key="sk-test", model="gpt-4o-mini")


def _spec() -> dict[str, Any]:
    return {
        "openapi": "3.0.0",
        "paths": {
            "/api/users": {
                "get": {
                    "summary": "List users",
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------


async def test_generate_returns_parsed_cases() -> None:
    llm_response = json.dumps(
        [
            {
                "code": "def test_list_users():\n    pass",
                "description": "List users",
                "confidence": 0.9,
                "tags": ["smoke"],
            },
            {
                "code": "def test_list_users_empty():\n    pass",
                "description": "Empty list",
                "confidence": 0.7,
                "tags": ["edge"],
            },
        ]
    )
    fake = _FakeAsyncClient(_FakeResponse(llm_response))
    gen = LLMGenerator(_settings(), http_client=fake)

    cases = await gen.generate(_spec())

    assert len(cases) == 2
    assert cases[0].code == "def test_list_users():\n    pass"
    assert cases[0].description == "List users"
    assert cases[0].confidence == 0.9
    assert cases[0].tags == ["smoke"]


async def test_generate_strips_markdown_fences() -> None:
    llm_response = (
        "```json\n"
        + json.dumps([{"code": "def test_x(): pass", "description": "Test X", "confidence": 0.8}])
        + "\n```"
    )
    fake = _FakeAsyncClient(_FakeResponse(llm_response))
    gen = LLMGenerator(_settings(), http_client=fake)

    cases = await gen.generate(_spec())

    assert len(cases) == 1
    assert cases[0].code == "def test_x(): pass"


async def test_generate_single_dict_response() -> None:
    llm_response = json.dumps({"code": "def test_y(): pass", "description": "Y", "confidence": 0.6})
    fake = _FakeAsyncClient(_FakeResponse(llm_response))
    gen = LLMGenerator(_settings(), http_client=fake)

    cases = await gen.generate(_spec())

    assert len(cases) == 1
    assert cases[0].description == "Y"


async def test_generate_invalid_json_fallback() -> None:
    fake = _FakeAsyncClient(_FakeResponse("This is not JSON."))
    gen = LLMGenerator(_settings(), http_client=fake)

    cases = await gen.generate(_spec())

    assert len(cases) == 1
    assert "not valid JSON" in cases[0].description
    assert cases[0].confidence == 0.2
    assert "unparsed" in cases[0].tags


async def test_generate_no_api_key_returns_empty() -> None:
    gen = LLMGenerator(AISettings(api_key=""))

    cases = await gen.generate(_spec())

    assert cases == []


async def test_generate_includes_endpoint_in_prompt() -> None:
    llm_response = json.dumps([{"code": "pass", "description": "ok", "confidence": 0.5}])
    fake = _FakeAsyncClient(_FakeResponse(llm_response))
    gen = LLMGenerator(_settings(), http_client=fake)

    await gen.generate(_spec(), endpoint="/api/users", method="GET")

    prompt = fake.requests[0]["json"]["messages"][1]["content"]
    assert "/api/users" in prompt
    assert "GET" in prompt


async def test_generate_sends_auth_header() -> None:
    llm_response = json.dumps([{"code": "pass", "description": "ok", "confidence": 0.5}])
    fake = _FakeAsyncClient(_FakeResponse(llm_response))
    gen = LLMGenerator(_settings(), http_client=fake)

    await gen.generate(_spec())

    assert fake.requests[0]["headers"]["Authorization"] == "Bearer sk-test"


async def test_generate_default_tags() -> None:
    llm_response = json.dumps([{"code": "pass", "description": "ok"}])
    fake = _FakeAsyncClient(_FakeResponse(llm_response))
    gen = LLMGenerator(_settings(), http_client=fake)

    cases = await gen.generate(_spec())

    assert cases[0].tags == []
    assert cases[0].confidence == 0.5


# ---------------------------------------------------------------------------
# Type checks
# ---------------------------------------------------------------------------


def test_llm_generator_is_test_case_generator() -> None:
    gen = LLMGenerator(_settings())
    assert isinstance(gen, TestCaseGenerator)


def test_generated_test_case_defaults() -> None:
    case = GeneratedTestCase(code="pass", description="test")
    assert case.confidence == 0.5
    assert case.tags == []
