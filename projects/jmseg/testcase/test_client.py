"""客户端测试:鉴权自动识别 + 8 端点(异步) + token 注入 + 同步路径."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from api.base import AuthKind, SyncClient, detect_auth_scheme
from api.station_quote import StationQuoteClient
from factories import (
    make_audit_request,
    make_create_request,
    make_delete_request,
    make_detail_query,
    make_page_request,
    make_unaudit_request,
    make_update_request,
)

from framework.testing.assertions.response import assert_ok, assert_status

OPENAPI_PATH = Path(__file__).resolve().parent.parent / "openapi.json"


def _load_spec() -> dict[str, object]:
    return json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))


class TestAuthDetection:
    def test_detects_authtoken_custom_header_from_real_spec(self) -> None:
        scheme = detect_auth_scheme(_load_spec())
        assert scheme.kind is AuthKind.CUSTOM_HEADER
        assert scheme.header_name == "authtoken"

    def test_detects_bearer_from_authorization_header(self) -> None:
        spec = {
            "paths": {"/x": {"get": {"parameters": [{"in": "header", "name": "Authorization"}]}}}
        }
        assert detect_auth_scheme(spec).kind is AuthKind.BEARER

    def test_detects_bearer_from_security_scheme(self) -> None:
        spec = {"components": {"securitySchemes": {"jwt": {"type": "http", "scheme": "bearer"}}}}
        assert detect_auth_scheme(spec).kind is AuthKind.BEARER

    def test_detects_cookie(self) -> None:
        spec = {"paths": {"/x": {"get": {"parameters": [{"in": "cookie", "name": "sid"}]}}}}
        scheme = detect_auth_scheme(spec)
        assert scheme.kind is AuthKind.COOKIE
        assert scheme.cookie_name == "sid"

    def test_detects_none(self) -> None:
        assert detect_auth_scheme({"paths": {}}).kind is AuthKind.NONE


class TestAsyncEndpoints:
    async def test_save_returns_void_envelope(self, api_client: StationQuoteClient) -> None:
        resp = await api_client.save(make_create_request())
        assert_status(resp, 200)
        result = StationQuoteClient.parse_void(resp)
        assert result.code == 200

    async def test_page_returns_records_after_save(self, api_client: StationQuoteClient) -> None:
        await api_client.save(make_create_request())
        resp = await api_client.page(make_page_request())
        assert_ok(resp)
        result = StationQuoteClient.parse_page(resp)
        assert result.data is not None
        assert result.data.total == 1
        assert result.data.records[0].id == 1

    async def test_detail_by_id(self, api_client: StationQuoteClient) -> None:
        await api_client.save(make_create_request())
        page = StationQuoteClient.parse_page(await api_client.page(make_page_request()))
        quote_id = page.data.records[0].id
        resp = await api_client.detail(make_detail_query(quote_id))
        result = StationQuoteClient.parse_detail(resp)
        assert result.data is not None
        assert result.data.id == quote_id

    async def test_ark_export_page(self, api_client: StationQuoteClient) -> None:
        await api_client.save(make_create_request())
        resp = await api_client.ark_export_page(make_page_request())
        result = StationQuoteClient.parse_list(resp)
        assert result.data is not None
        assert len(result.data) == 1

    async def test_update(self, api_client: StationQuoteClient) -> None:
        await api_client.save(make_create_request())
        page = StationQuoteClient.parse_page(await api_client.page(make_page_request()))
        quote_id = page.data.records[0].id
        resp = await api_client.update(make_update_request(quote_id, quote_name="改名"))
        assert_ok(resp)

    async def test_audit_and_unaudit(self, api_client: StationQuoteClient) -> None:
        await api_client.save(make_create_request())
        page = StationQuoteClient.parse_page(await api_client.page(make_page_request()))
        quote_id = page.data.records[0].id
        assert_ok(await api_client.audit(make_audit_request([quote_id])))
        assert_ok(await api_client.unaudit(make_unaudit_request([quote_id])))

    async def test_delete(self, api_client: StationQuoteClient) -> None:
        await api_client.save(make_create_request())
        page = StationQuoteClient.parse_page(await api_client.page(make_page_request()))
        quote_id = page.data.records[0].id
        assert_ok(await api_client.delete(make_delete_request(quote_id)))
        after = StationQuoteClient.parse_page(await api_client.page(make_page_request()))
        assert after.data is not None
        assert after.data.total == 0


class TestTokenInjection:
    async def test_authtoken_header_injected(
        self,
        api_client: StationQuoteClient,
        mock_transport: httpx.MockTransport,
        token: str,
    ) -> None:
        await api_client.save(make_create_request())
        store = mock_transport.store  # type: ignore[attr-defined]
        requests = store["requests"]  # type: ignore[index]
        assert isinstance(requests, list)
        last = requests[-1]
        assert last.headers["authtoken"] == token
        assert last.headers["x-ups-user"] == "auto-tester"


class TestSyncClient:
    def test_sync_save_and_page(self, sync_client: SyncClient) -> None:
        resp = sync_client.save(make_create_request())
        assert_status(resp, 200)
        page_resp = sync_client.page(make_page_request())
        result = StationQuoteClient.parse_page(page_resp)
        assert result.data is not None
        assert result.data.total == 1

    def test_sync_detail(self, sync_client: SyncClient) -> None:
        sync_client.save(make_create_request())
        page = StationQuoteClient.parse_page(sync_client.page(make_page_request()))
        quote_id = page.data.records[0].id
        detail = StationQuoteClient.parse_detail(sync_client.detail(make_detail_query(quote_id)))
        assert detail.data is not None
        assert detail.data.id == quote_id

    def test_sync_context_manager_closes(self) -> None:
        def _ok_handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"code": 200, "data": None})

        http = httpx.Client(
            base_url="http://jmseg.test", transport=httpx.MockTransport(_ok_handler)
        )
        with SyncClient(StationQuoteClient, http) as sc:
            assert sc.save(make_create_request()).status_code == 200
        assert http.is_closed


def test_endpoint_lookup_unknown_raises() -> None:
    with pytest.raises(KeyError):
        StationQuoteClient.endpoint("does_not_exist")
