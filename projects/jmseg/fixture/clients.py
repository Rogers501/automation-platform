"""jmseg 测试客户端 fixtures.

提供带状态的 MockTransport(覆盖 8 个端点,维护内存报价存储,支持依赖链路测试)、
异步 ``StationQuoteClient`` 与同步 ``SyncClient``。对接真实环境时:删除
``transport=mock_transport``,改用 config 中的 ``base_url``。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from api.base import SyncClient
from api.station_quote import StationQuoteClient

from framework.clients.http.client import AsyncHttpClient
from framework.core.config import HttpSettings

BASE_URL = "http://jmseg.test"


def _envelope(data: object | None) -> dict[str, object]:
    """统一响应信封(与后端 Result 结构一致)."""
    return {"code": 200, "msg": "ok", "data": data, "traceId": "t-1", "timestamp": 1700000000}


@pytest.fixture
def mock_transport() -> httpx.MockTransport:
    """带状态的 MockTransport:内存存储报价,覆盖全部端点。

    通过 ``mock_transport.store`` 可访问内存状态与已记录的请求列表(用于断言)。
    """
    store: dict[str, object] = {"quotes": {}, "seq": 1, "requests": []}

    def handler(request: httpx.Request) -> httpx.Response:
        requests = store["requests"]
        assert isinstance(requests, list)
        requests.append(request)
        path = request.url.path
        method = request.method
        body: dict[str, object] = json.loads(request.content) if request.content else {}
        quotes = store["quotes"]
        assert isinstance(quotes, dict)

        if method == "POST" and path == "/station-quote/save":
            seq = store["seq"]
            assert isinstance(seq, int)
            quote_id = seq
            store["seq"] = seq + 1
            quotes[quote_id] = {"id": quote_id, **body, "auditStatus": 0}
            return httpx.Response(200, json=_envelope(None))
        if method == "POST" and path == "/station-quote/page":
            records = list(quotes.values())
            page_data = {
                "records": records,
                "current": body.get("current", 1),
                "size": body.get("size", 20),
                "total": len(records),
            }
            return httpx.Response(200, json=_envelope(page_data))
        if method == "POST" and path == "/station-quote/ark-export/page":
            return httpx.Response(200, json=_envelope(list(quotes.values())))
        if method == "GET" and path == "/station-quote/detail":
            quote_id = int(request.url.params.get("id", "0"))
            return httpx.Response(200, json=_envelope(quotes.get(quote_id)))
        if method == "POST" and path == "/station-quote/update":
            quote_id = body.get("id")
            if quote_id in quotes:
                target = quotes[quote_id]
                assert isinstance(target, dict)
                target.update(body)
            return httpx.Response(200, json=_envelope(None))
        if method == "POST" and path == "/station-quote/delete":
            quotes.pop(body.get("id"), None)
            return httpx.Response(200, json=_envelope(None))
        if method == "POST" and path == "/station-quote/audit":
            for quote_id in body.get("ids", []):
                target = quotes.get(quote_id)
                if isinstance(target, dict):
                    target["auditStatus"] = 1
            return httpx.Response(200, json=_envelope(None))
        if method == "POST" and path == "/station-quote/unaudit":
            for quote_id in body.get("ids", []):
                target = quotes.get(quote_id)
                if isinstance(target, dict):
                    target["auditStatus"] = 0
            return httpx.Response(200, json=_envelope(None))
        return httpx.Response(404, json=_envelope(None))

    transport = httpx.MockTransport(handler)
    transport.store = store  # type: ignore[attr-defined]
    return transport


@pytest.fixture
async def api_client(
    mock_transport: httpx.MockTransport, token: str
) -> AsyncIterator[StationQuoteClient]:
    """异步业务客户端(自动注入 authtoken)."""
    async with AsyncHttpClient(
        settings=HttpSettings(base_url=BASE_URL), transport=mock_transport
    ) as client:
        yield StationQuoteClient(client, token=token, user="auto-tester")


@pytest.fixture
def sync_client(mock_transport: httpx.MockTransport, token: str) -> Iterator[SyncClient]:
    """同步业务客户端(基于 httpx.Client,复用同一端点注册表)."""
    http = httpx.Client(base_url=BASE_URL, transport=mock_transport)
    sc = SyncClient(StationQuoteClient, http, token=token, user="auto-tester")
    yield sc
    sc.close()
