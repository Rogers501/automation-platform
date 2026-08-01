"""Unit tests for AsyncHttpClient (isolated via httpx.MockTransport)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from framework.clients.http.auth import BearerAuth
from framework.clients.http.client import AsyncHttpClient
from framework.clients.http.models import RequestSpec
from framework.core.config import HttpSettings, reset_settings
from framework.core.context import clear_context, trace
from framework.core.exceptions import ClientError, ClientStatusError, ClientTimeoutError
from framework.core.recorder import bind_recorder, clear_recorder


def _settings(**overrides: Any) -> HttpSettings:
    """Build HttpSettings with fast retry defaults overridden by kwargs."""
    base: dict[str, Any] = {
        "retry_max_attempts": 3,
        "retry_backoff_factor": 0.0,
        "retry_max_backoff": 0.0,
        "connect_timeout": 5.0,
        "read_timeout": 5.0,
        "write_timeout": 5.0,
        "pool_timeout": 5.0,
    }
    base.update(overrides)
    return HttpSettings(**base)


@pytest.fixture(autouse=True)
def _reset_settings() -> Iterator[None]:
    """Ensure no stale cached settings leak into tests."""
    reset_settings()
    yield
    reset_settings()


@pytest.fixture(autouse=True)
def _clean_context_recorder() -> Iterator[None]:
    """Clear trace context and recorder between tests (rules 13/14)."""
    clear_context()
    clear_recorder()
    yield
    clear_context()
    clear_recorder()


async def test_get_returns_response() -> None:
    """GET sends the request and returns a decoded response."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"ok": True})

    async with AsyncHttpClient(
        settings=_settings(base_url="http://test"), transport=httpx.MockTransport(handler)
    ) as client:
        resp = await client.get("/users", params={"active": "true"})

    assert seen["method"] == "GET"
    assert "active=true" in seen["url"]
    assert resp.status_code == 200
    assert resp.json == {"ok": True}
    assert resp.ok is True


async def test_post_sends_json_body() -> None:
    """POST serializes the json body and sets content-type."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"id": 1})

    async with AsyncHttpClient(
        settings=_settings(base_url="http://test"), transport=httpx.MockTransport(handler)
    ) as client:
        resp = await client.post("/users", json={"name": "alice"})

    assert resp.status_code == 201


async def test_put_and_delete() -> None:
    """PUT and DELETE verbs are wired through."""
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(200, json={})

    async with AsyncHttpClient(
        settings=_settings(base_url="http://test"), transport=httpx.MockTransport(handler)
    ) as client:
        await client.put("/users/1", json={"name": "bob"})
        await client.delete("/users/1")

    assert methods == ["PUT", "DELETE"]


async def test_auth_injected() -> None:
    """A Bearer auth provider sets the Authorization header."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={})

    async with AsyncHttpClient(
        settings=_settings(base_url="http://test"),
        transport=httpx.MockTransport(handler),
        auth=BearerAuth(token="tok"),
    ) as client:
        await client.get("/secure")

    assert seen["auth"] == "Bearer tok"


async def test_per_request_auth_override() -> None:
    """Per-request auth overrides the client default."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={})

    async with AsyncHttpClient(
        settings=_settings(base_url="http://test"),
        transport=httpx.MockTransport(handler),
        auth=BearerAuth(token="default"),
    ) as client:
        await client.get("/x", auth=BearerAuth(token="override"))

    assert seen["auth"] == "Bearer override"


async def test_base_headers_merged() -> None:
    """Client base headers are present and overridden by per-request headers."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["x-client"] = request.headers.get("x-client", "")
        seen["x-req"] = request.headers.get("x-req", "")
        return httpx.Response(200, json={})

    async with AsyncHttpClient(
        settings=_settings(base_url="http://test"),
        transport=httpx.MockTransport(handler),
        headers={"X-Client": "c", "X-Req": "base"},
    ) as client:
        await client.get("/x", headers={"X-Req": "overridden"})

    assert seen["x-client"] == "c"
    assert seen["x-req"] == "overridden"


async def test_cookie_persistence() -> None:
    """Set-Cookie from a response persists into the next request."""
    received: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request.headers.get("cookie", ""))
        return httpx.Response(200, headers={"set-cookie": "session=abc; Path=/"}, json={})

    async with AsyncHttpClient(
        settings=_settings(base_url="http://test"), transport=httpx.MockTransport(handler)
    ) as client:
        await client.get("/login")
        await client.get("/dashboard")

    # first request has no cookie; second carries the session set by the first
    assert "session=abc" in received[1]


async def test_clear_cookies() -> None:
    """clear_cookies empties the jar."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    async with AsyncHttpClient(
        settings=_settings(base_url="http://test"), transport=httpx.MockTransport(handler)
    ) as client:
        client.cookies.set("k", "v")
        assert client.cookies.get("k") == "v"
        client.clear_cookies()
        assert client.cookies.get("k") is None


async def test_retry_on_503_then_success() -> None:
    """A retryable 503 is retried and succeeds on the final attempt."""
    statuses: list[int] = [503, 503, 200]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(statuses.pop(0), json={})

    async with AsyncHttpClient(
        settings=_settings(), transport=httpx.MockTransport(handler)
    ) as client:
        resp = await client.get("http://test/flaky")

    assert resp.status_code == 200
    assert statuses == []


async def test_retry_not_for_post() -> None:
    """POST (non-idempotent) is not retried on a retryable status."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={})

    async with AsyncHttpClient(
        settings=_settings(), transport=httpx.MockTransport(handler)
    ) as client:
        resp = await client.post("http://test/x", json={})

    assert attempts == 1
    assert resp.status_code == 503


async def test_retry_respects_retry_after() -> None:
    """Retry-After (seconds) is honored as the sleep duration."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"retry-after": "0"}, json={})
        return httpx.Response(200, json={})

    async with AsyncHttpClient(
        settings=_settings(), transport=httpx.MockTransport(handler)
    ) as client:
        resp = await client.get("http://test/x")

    assert calls == 2
    assert resp.status_code == 200


async def test_retry_exhausted_returns_last_response() -> None:
    """When retries are exhausted the last retryable response is returned."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={})

    async with AsyncHttpClient(
        settings=_settings(retry_max_attempts=2), transport=httpx.MockTransport(handler)
    ) as client:
        resp = await client.get("http://test/x")

    assert attempts == 2
    assert resp.status_code == 503


async def test_timeout_raises_client_timeout_error() -> None:
    """A read timeout raises ClientTimeoutError after retries."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async with AsyncHttpClient(
        settings=_settings(retry_max_attempts=2), transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(ClientTimeoutError):
            await client.get("http://test/slow")


async def test_raise_for_status_client_default() -> None:
    """raise_for_status=True on the client raises on non-2xx."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"oops", request=request)

    async with AsyncHttpClient(
        settings=_settings(raise_for_status=True, retry_max_attempts=1),
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(ClientStatusError) as info:
            await client.get("http://test/x")
    assert info.value.status_code == 500


async def test_raise_for_status_per_call_override() -> None:
    """raise_for_status=True per call overrides the client default."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"nope", request=request)

    async with AsyncHttpClient(
        settings=_settings(retry_max_attempts=1), transport=httpx.MockTransport(handler)
    ) as client:
        # default client setting is False -> returns response
        resp = await client.get("http://test/x")
        assert resp.status_code == 404
        # per-call override -> raises
        with pytest.raises(ClientStatusError):
            await client.get("http://test/x", raise_for_status=True)


async def test_send_request_spec() -> None:
    """send(spec) executes a serialized request description."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        return httpx.Response(200, json={})

    async with AsyncHttpClient(
        settings=_settings(base_url="http://test"), transport=httpx.MockTransport(handler)
    ) as client:
        spec = RequestSpec(method="POST", url="/users", json={"name": "x"}, headers={"X-T": "1"})
        resp = await client.send(spec)

    assert seen["method"] == "POST"
    assert seen["url"].endswith("/users")
    assert resp.status_code == 200


async def test_request_after_close_raises() -> None:
    """Using a closed client raises ClientError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client = AsyncHttpClient(
        settings=_settings(base_url="http://test"), transport=httpx.MockTransport(handler)
    )
    await client.aclose()
    assert client.is_closed
    with pytest.raises(ClientError):
        await client.get("/x")


async def test_logs_request_and_response() -> None:
    """A request emits a structured log line via loguru."""
    from loguru import logger

    records: list[str] = []

    def sink(message: Any) -> None:
        records.append(str(message))

    handler_id = logger.add(sink, level="DEBUG", format="{message}")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    try:
        async with AsyncHttpClient(
            settings=_settings(base_url="http://test"), transport=httpx.MockTransport(handler)
        ) as client:
            await client.get("/users")
    finally:
        logger.remove(handler_id)

    joined = "\n".join(records)
    assert "GET" in joined
    assert "/users" in joined


async def test_sensitive_headers_not_logged() -> None:
    """Authorization values are redacted in logs."""
    from loguru import logger

    records: list[str] = []

    def sink(message: Any) -> None:
        records.append(str(message))

    handler_id = logger.add(sink, level="DEBUG", format="{message}")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    try:
        async with AsyncHttpClient(
            settings=_settings(base_url="http://test", log_bodies=True),
            transport=httpx.MockTransport(handler),
            auth=BearerAuth(token="super-secret"),
        ) as client:
            await client.get("/secure")
    finally:
        logger.remove(handler_id)

    joined = "\n".join(records)
    assert "super-secret" not in joined
    assert "***REDACTED***" in joined


async def test_trace_header_injected_from_context() -> None:
    """The current trace id is injected as X-Trace-Id."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["trace"] = request.headers.get("X-Trace-Id", "")
        return httpx.Response(200, json={})

    with trace(trace_id="trace-abc"):
        async with AsyncHttpClient(
            settings=_settings(base_url="http://test"), transport=httpx.MockTransport(handler)
        ) as client:
            await client.get("/api")
    assert seen["trace"] == "trace-abc"


async def test_trace_header_not_injected_when_disabled() -> None:
    """propagate_trace_id=False disables header injection."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["trace"] = request.headers.get("X-Trace-Id", "")
        return httpx.Response(200, json={})

    with trace(trace_id="trace-abc"):
        async with AsyncHttpClient(
            settings=_settings(base_url="http://test", propagate_trace_id=False),
            transport=httpx.MockTransport(handler),
        ) as client:
            await client.get("/api")
    assert seen["trace"] == ""


async def test_explicit_header_not_overridden_by_context() -> None:
    """An explicit X-Trace-Id header is not overridden by the context."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["trace"] = request.headers.get("X-Trace-Id", "")
        return httpx.Response(200, json={})

    with trace(trace_id="ctx-id"):
        async with AsyncHttpClient(
            settings=_settings(base_url="http://test"), transport=httpx.MockTransport(handler)
        ) as client:
            await client.get("/api", headers={"X-Trace-Id": "explicit-id"})
    assert seen["trace"] == "explicit-id"


async def test_no_trace_no_header() -> None:
    """Without an active trace, no X-Trace-Id header is sent."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["trace"] = request.headers.get("X-Trace-Id", "")
        return httpx.Response(200, json={})

    async with AsyncHttpClient(
        settings=_settings(base_url="http://test"), transport=httpx.MockTransport(handler)
    ) as client:
        await client.get("/api")
    assert seen["trace"] == ""


async def test_recorder_captures_successful_exchange() -> None:
    """A successful request is recorded with its trace id."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    with trace(trace_id="rec-1"), bind_recorder() as recorder:
        async with AsyncHttpClient(
            settings=_settings(base_url="http://test"),
            transport=httpx.MockTransport(handler),
        ) as client:
            await client.get("/api")
    assert len(recorder.exchanges) == 1
    exchange = recorder.exchanges[0]
    assert exchange.method == "GET"
    assert exchange.status_code == 200
    assert exchange.trace_id == "rec-1"
    assert exchange.request_headers.get("x-trace-id") == "rec-1"
    assert exchange.error is None


async def test_recorder_captures_failed_exchange() -> None:
    """A failed (non-2xx, raise_for_status) request is recorded with its error."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with bind_recorder() as recorder:
        async with AsyncHttpClient(
            settings=_settings(base_url="http://test", raise_for_status=True, retry_max_attempts=1),
            transport=httpx.MockTransport(handler),
        ) as client:
            with pytest.raises(ClientStatusError):
                await client.get("/api")
    assert len(recorder.exchanges) == 1
    exchange = recorder.exchanges[0]
    assert exchange.status_code == 500
    assert exchange.error is not None
    assert "500" in exchange.error


async def test_no_recorder_request_still_succeeds() -> None:
    """Without a recorder, requests succeed (recording is a no-op)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    async with AsyncHttpClient(
        settings=_settings(base_url="http://test"), transport=httpx.MockTransport(handler)
    ) as client:
        resp = await client.get("/api")
    assert resp.status_code == 200
