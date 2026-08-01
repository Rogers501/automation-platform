"""Allure reporting integration (optional dependency).

Allure attachments and steps are emitted when ``allure`` (installed via
``allure-pytest``) is available; otherwise every helper is a no-op. This lets
the framework run in environments without Allure while enriching the report
where it is available.

The testing hooks layer auto-attaches recorded HTTP exchanges at test teardown
(see :mod:`framework.testing.hooks.fixtures`); tests may also attach database
results or wrap business steps explicitly via :func:`attach_db_result` and
:func:`step`.

Layering: this module depends only on ``core`` (:class:`HttpExchange`), never
on ``clients`` or ``testing`` (rule 11).
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

from framework.core.recorder import HttpExchange

__all__ = [
    "attach_db_result",
    "attach_exchanges",
    "attach_http_exchange",
    "attach_json",
    "attach_text",
    "is_allure_available",
    "step",
]


def is_allure_available() -> bool:
    """Return ``True`` when the ``allure`` package is importable."""
    return _try_import_allure() is not None


def _try_import_allure() -> Any:
    """Import and return the ``allure`` module, or ``None`` if unavailable."""
    try:
        import allure
    except ImportError:
        return None
    return allure


def attach_text(name: str, body: str, *, mime_type: str = "text/plain") -> None:
    """Attach ``body`` as a text attachment (no-op without allure)."""
    allure = _try_import_allure()
    if allure is None:
        return
    allure.attach(body, name=name, attachment_type=mime_type)


def attach_json(name: str, data: Any) -> None:
    """Attach ``data`` as a JSON attachment (no-op without allure)."""
    allure = _try_import_allure()
    if allure is None:
        return
    body = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    allure.attach(body, name=name, attachment_type=allure.attachment_type.JSON)


def attach_http_exchange(exchange: HttpExchange, *, name: str | None = None) -> None:
    """Attach a recorded HTTP exchange (request + response) as JSON.

    Bodies and headers are pre-redacted/truncated by the recorder, so the
    attachment is safe to persist.
    """
    allure = _try_import_allure()
    if allure is None:
        return
    request_block: dict[str, Any] = {
        "method": exchange.method,
        "url": exchange.url,
        "headers": exchange.request_headers,
        "body": exchange.request_body,
    }
    response_block: dict[str, Any] = {
        "status_code": exchange.status_code,
        "headers": exchange.response_headers,
        "body": exchange.response_body,
        "elapsed_seconds": exchange.elapsed_seconds,
    }
    if exchange.error:
        response_block["error"] = exchange.error
    if exchange.trace_id:
        response_block["trace_id"] = exchange.trace_id
    payload = {"request": request_block, "response": response_block}
    label = name or f"{exchange.method} {exchange.url}"
    allure.attach(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        name=label,
        attachment_type=allure.attachment_type.JSON,
    )


def attach_exchanges(exchanges: Sequence[HttpExchange]) -> None:
    """Attach every recorded exchange (no-op without allure)."""
    for exchange in exchanges:
        attach_http_exchange(exchange)


def attach_db_result(
    rows: Sequence[Mapping[str, Any]],
    *,
    name: str = "database-result",
    query: str | None = None,
) -> None:
    """Attach database query ``rows`` as a JSON attachment (no-op without allure)."""
    allure = _try_import_allure()
    if allure is None:
        return
    payload: dict[str, Any] = {
        "query": query,
        "row_count": len(rows),
        "rows": [dict(row) for row in rows],
    }
    allure.attach(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        name=name,
        attachment_type=allure.attachment_type.JSON,
    )


@contextmanager
def step(title: str) -> Iterator[None]:
    """Wrap a block in an Allure step (no-op without allure)."""
    allure = _try_import_allure()
    if allure is None:
        yield
        return
    with allure.step(title):
        yield
