"""Unit tests for framework.reporting.allure.

``allure`` is not installed in this environment, so we inject a fake into
``sys.modules`` to exercise the attach/step logic, and verify the no-op path
when allure is absent (rule 14: isolate external deps).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from framework.core.recorder import HttpExchange
from framework.reporting.allure import (
    attach_db_result,
    attach_exchanges,
    attach_http_exchange,
    attach_json,
    attach_text,
    is_allure_available,
    step,
)


class _AttachmentType:
    JSON = "application/json"
    TEXT = "text/plain"


class FakeAllure:
    """Records attach/step calls for assertions."""

    attachment_type = _AttachmentType

    def __init__(self) -> None:
        self.attaches: list[dict[str, Any]] = []
        self.steps: list[str] = []

    def attach(
        self,
        body: str,
        name: str | None = None,
        attachment_type: Any = None,
        **kwargs: Any,
    ) -> None:
        self.attaches.append({"body": body, "name": name, "type": attachment_type})

    @contextmanager
    def step(self, title: str) -> Iterator[None]:
        self.steps.append(title)
        yield


@pytest.fixture
def fake_allure(monkeypatch: pytest.MonkeyPatch) -> FakeAllure:
    """Inject a FakeAllure into sys.modules so the lazy import finds it."""
    fake = FakeAllure()
    monkeypatch.setitem(sys.modules, "allure", fake)
    return fake


def _exchange(
    *,
    method: str = "GET",
    url: str = "http://x",
    status_code: int | None = 200,
    error: str | None = None,
    trace_id: str | None = None,
) -> HttpExchange:
    return HttpExchange(
        method=method,
        url=url,
        request_headers={},
        request_body=None,
        status_code=status_code,
        response_headers={},
        response_body=None,
        elapsed_seconds=0.1,
        error=error,
        trace_id=trace_id,
    )


def test_is_allure_available_false_when_absent() -> None:
    assert is_allure_available() is False


def test_is_allure_available_true_when_injected(fake_allure: FakeAllure) -> None:
    assert is_allure_available() is True


def test_attach_text_noop_without_allure() -> None:
    attach_text("req", "body")
    assert is_allure_available() is False


def test_attach_text_calls_allure(fake_allure: FakeAllure) -> None:
    attach_text("req", "hello", mime_type="text/plain")
    assert len(fake_allure.attaches) == 1
    assert fake_allure.attaches[0]["body"] == "hello"
    assert fake_allure.attaches[0]["name"] == "req"
    assert fake_allure.attaches[0]["type"] == "text/plain"


def test_attach_json_calls_allure(fake_allure: FakeAllure) -> None:
    attach_json("data", {"a": 1})
    assert len(fake_allure.attaches) == 1
    assert json.loads(fake_allure.attaches[0]["body"]) == {"a": 1}
    assert fake_allure.attaches[0]["type"] == "application/json"


def test_attach_json_noop_without_allure() -> None:
    attach_json("data", {"a": 1})


def test_attach_http_exchange_noop_without_allure() -> None:
    attach_http_exchange(_exchange())


def test_attach_http_exchange_attaches_request_response(fake_allure: FakeAllure) -> None:
    ex = HttpExchange(
        method="POST",
        url="http://x/api",
        request_headers={"h": "v"},
        request_body='{"k":1}',
        status_code=201,
        response_headers={},
        response_body='{"id":9}',
        elapsed_seconds=0.2,
        trace_id="t1",
    )
    attach_http_exchange(ex)
    assert len(fake_allure.attaches) == 1
    call = fake_allure.attaches[0]
    assert "POST" in call["name"]
    assert "http://x/api" in call["name"]
    payload = json.loads(call["body"])
    assert payload["request"]["method"] == "POST"
    assert payload["request"]["body"] == '{"k":1}'
    assert payload["response"]["status_code"] == 201
    assert payload["response"]["trace_id"] == "t1"


def test_attach_http_exchange_custom_name(fake_allure: FakeAllure) -> None:
    attach_http_exchange(_exchange(), name="custom")
    assert fake_allure.attaches[0]["name"] == "custom"


def test_attach_http_exchange_includes_error(fake_allure: FakeAllure) -> None:
    attach_http_exchange(_exchange(status_code=None, error="timeout"))
    payload = json.loads(fake_allure.attaches[0]["body"])
    assert payload["response"]["error"] == "timeout"


def test_attach_http_exchange_omits_error_when_none(fake_allure: FakeAllure) -> None:
    attach_http_exchange(_exchange())
    payload = json.loads(fake_allure.attaches[0]["body"])
    assert "error" not in payload["response"]


def test_attach_exchanges_attaches_each(fake_allure: FakeAllure) -> None:
    attach_exchanges([_exchange(url="http://x/1"), _exchange(url="http://x/2")])
    assert len(fake_allure.attaches) == 2


def test_attach_exchanges_noop_without_allure() -> None:
    attach_exchanges([_exchange()])


def test_attach_db_result_calls_allure(fake_allure: FakeAllure) -> None:
    rows = [{"name": "alice"}, {"name": "bob"}]
    attach_db_result(rows, name="users", query="SELECT name FROM users")
    assert len(fake_allure.attaches) == 1
    payload = json.loads(fake_allure.attaches[0]["body"])
    assert payload["row_count"] == 2
    assert payload["query"] == "SELECT name FROM users"
    assert payload["rows"] == rows


def test_attach_db_result_default_name(fake_allure: FakeAllure) -> None:
    attach_db_result([])
    assert fake_allure.attaches[0]["name"] == "database-result"


def test_attach_db_result_noop_without_allure() -> None:
    attach_db_result([], name="x")


def test_step_noop_without_allure() -> None:
    with step("do thing"):
        assert True


def test_step_calls_allure(fake_allure: FakeAllure) -> None:
    with step("do thing"):
        assert True
    assert fake_allure.steps == ["do thing"]


def test_step_nested_without_allure() -> None:
    with step("outer"), step("inner"):
        assert True
