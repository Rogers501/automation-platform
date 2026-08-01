"""End-to-end integration test: config -> HTTP client -> assertion -> recorder.

Exercises the real framework HTTP path (config, client, retry, recorder,
assertions, Allure attachment) using httpx.MockTransport - no real network
(rule 14). This validates that the modules compose correctly end-to-end.
"""

from __future__ import annotations

import httpx
import pytest

from framework.clients.http.client import AsyncHttpClient
from framework.clients.http.models import ApiResponse
from framework.core.config import HttpSettings
from framework.core.recorder import RequestRecorder, bind_recorder
from framework.reporting.allure import attach_http_exchange
from framework.testing.assertions.json import assert_json_path
from framework.testing.assertions.response import (
    assert_body_contains,
    assert_ok,
    assert_response_json_path,
    assert_status,
)


def _mock_handler(request: httpx.Request) -> httpx.Response:
    """Route mock requests to canned responses based on path."""
    if request.url.path == "/api/users":
        return httpx.Response(
            200,
            json={"users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]},
            headers={"Content-Type": "application/json"},
        )
    if request.url.path == "/api/login":
        return httpx.Response(
            200,
            json={"token": "mock-jwt-token", "expires_in": 3600},
        )
    return httpx.Response(404, json={"error": "not found"})


@pytest.fixture
def http_settings() -> HttpSettings:
    return HttpSettings(base_url="https://mock.test")


@pytest.fixture
def mock_transport() -> httpx.MockTransport:
    return httpx.MockTransport(_mock_handler)


@pytest.fixture
def recorder() -> RequestRecorder:
    """Fresh recorder for each test (rule 13: independent, repeatable)."""
    with bind_recorder() as rec:
        yield rec


async def test_get_returns_response_and_records_exchange(
    http_settings: HttpSettings,
    mock_transport: httpx.MockTransport,
    recorder: RequestRecorder,
) -> None:
    """GET request returns ApiResponse and records an HTTP exchange."""
    async with AsyncHttpClient(http_settings, transport=mock_transport) as client:
        resp = await client.get("/api/users")

    assert isinstance(resp, ApiResponse)
    assert resp.status_code == 200
    assert resp.method == "GET"
    data = resp.json
    assert len(data["users"]) == 2

    # Exchange was recorded.
    assert len(recorder.exchanges) == 1
    ex = recorder.exchanges[0]
    assert ex.method == "GET"
    assert ex.status_code == 200


async def test_full_flow_assertions_compose(
    http_settings: HttpSettings,
    mock_transport: httpx.MockTransport,
    recorder: RequestRecorder,
) -> None:
    """Response assertions + JSON assertions work together on a real response."""
    async with AsyncHttpClient(http_settings, transport=mock_transport) as client:
        resp = await client.get("/api/users")

    # Response-level assertions.
    assert_ok(resp)
    assert_status(resp, 200)
    assert_body_contains(resp, "Alice")

    # JSON-path assertions (response-level).
    assert_response_json_path(resp, "users[0].name", "Alice")

    # JSON-path assertions (parsed body).
    body = resp.json
    assert_json_path(body, "users[1].id", 2)
    assert_json_path(body, "users[0].name", "Alice")


async def test_post_and_extract_token(
    http_settings: HttpSettings,
    mock_transport: httpx.MockTransport,
    recorder: RequestRecorder,
) -> None:
    """POST login, extract token, verify it can be used in a header."""
    async with AsyncHttpClient(http_settings, transport=mock_transport) as client:
        login_resp = await client.post("/api/login", json={"user": "admin"})
        token = login_resp.json["token"]

        # Use the extracted token in a subsequent request.
        users_resp = await client.get(
            "/api/users",
            headers={"Authorization": "Bearer " + token},
        )

    assert login_resp.status_code == 200
    assert token == "mock-jwt-token"
    assert users_resp.status_code == 200

    # Both exchanges recorded.
    assert len(recorder.exchanges) == 2


async def test_404_raises_status_error(
    http_settings: HttpSettings,
    mock_transport: httpx.MockTransport,
) -> None:
    """A 404 response is returned; raise_for_status surfaces the error."""
    from framework.core.exceptions import ClientStatusError

    async with AsyncHttpClient(http_settings, transport=mock_transport) as client:
        resp = await client.get("/api/unknown")

    assert resp.status_code == 404
    with pytest.raises(ClientStatusError):
        resp.raise_for_status()


async def test_allure_attach_exchange_no_crash(
    http_settings: HttpSettings,
    mock_transport: httpx.MockTransport,
    recorder: RequestRecorder,
) -> None:
    """Attaching a recorded exchange to Allure does not crash without allure."""
    async with AsyncHttpClient(http_settings, transport=mock_transport) as client:
        await client.get("/api/users")

    exchange = recorder.exchanges[0]
    # No-op without allure installed, must not raise.
    attach_http_exchange(exchange)
