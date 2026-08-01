"""Unit tests for HTTP request/response data models."""

from __future__ import annotations

import httpx
import pytest

from framework.clients.http.models import ApiResponse, HttpMethod, RequestSpec
from framework.core.exceptions import ClientStatusError


def test_http_method_values() -> None:
    """HttpMethod exposes the expected verbs."""
    assert HttpMethod.GET.value == "GET"
    assert HttpMethod.POST.value == "POST"
    assert HttpMethod.DELETE.value == "DELETE"


def test_request_spec_defaults() -> None:
    """A RequestSpec requires only url; method defaults to GET."""
    spec = RequestSpec(url="/users")
    assert spec.normalized_method() == "GET"
    assert spec.url == "/users"
    assert spec.json_body is None


def test_request_spec_normalized_method_uppercases() -> None:
    """normalized_method upper-cases a string method."""
    spec = RequestSpec(method="post", url="/users", json={"a": 1})
    assert spec.normalized_method() == "POST"
    assert spec.json_body == {"a": 1}


def test_request_spec_accepts_extra_keys() -> None:
    """Extra metadata keys are ignored (data-driven friendliness)."""
    spec = RequestSpec.model_validate(
        {"method": "GET", "url": "/x", "name": "list users", "tags": ["smoke"]}
    )
    assert spec.url == "/x"
    assert spec.normalized_method() == "GET"


def test_api_response_from_httpx() -> None:
    """ApiResponse is built from an httpx.Response copying status/body/headers."""
    request = httpx.Request("GET", "http://test/users")
    response = httpx.Response(
        200,
        headers={"content-type": "application/json"},
        content=b'{"ok": true}',
        request=request,
    )
    api = ApiResponse.from_httpx(response)
    assert api.status_code == 200
    assert api.ok is True
    assert api.json == {"ok": True}
    assert api.text == '{"ok": true}'
    assert api.method == "GET"
    assert api.url.endswith("/users")


def test_api_response_json_empty_body() -> None:
    """An empty body parses to None."""
    request = httpx.Request("GET", "http://test/x")
    response = httpx.Response(204, content=b"", request=request)
    api = ApiResponse.from_httpx(response)
    assert api.json is None
    assert api.text == ""


def test_api_response_raise_for_status_ok() -> None:
    """raise_for_status is a no-op for 2xx."""
    request = httpx.Request("GET", "http://test/x")
    response = httpx.Response(200, content=b"ok", request=request)
    api = ApiResponse.from_httpx(response)
    api.raise_for_status()


def test_api_response_raise_for_status_error() -> None:
    """raise_for_status raises ClientStatusError for non-2xx."""
    request = httpx.Request("GET", "http://test/x")
    response = httpx.Response(500, content=b"boom", request=request)
    api = ApiResponse.from_httpx(response)
    with pytest.raises(ClientStatusError) as info:
        api.raise_for_status()
    assert info.value.status_code == 500
    assert "boom" in (info.value.body_snippet or "")


def test_api_response_multi_value_headers_joined() -> None:
    """Duplicate headers are joined into a single comma-separated value."""
    request = httpx.Request("GET", "http://test/x")
    response = httpx.Response(
        200,
        headers=[("x-multi", "a"), ("x-multi", "b")],
        content=b"",
        request=request,
    )
    api = ApiResponse.from_httpx(response)
    assert api.headers["x-multi"] == "a, b"
