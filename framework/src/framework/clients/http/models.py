"""Request/response data models for the HTTP client.

``RequestSpec`` is a serializable request description suitable for data-driven
tests (build it from YAML/JSON). ``ApiResponse`` is a decoupled wrapper around
an :class:`httpx.Response` exposing the fields tests assert on.
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from framework.core.exceptions import ClientStatusError

__all__ = ["ApiResponse", "HttpMethod", "RequestSpec"]


class HttpMethod(enum.StrEnum):
    """Supported HTTP verbs."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class RequestSpec(BaseModel):
    """A serializable request description.

    Use ``AsyncHttpClient.send(spec)`` to execute it. Extra keys are ignored
    so data-driven specs may carry metadata (name, description, tags).
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    method: str = HttpMethod.GET
    url: str
    params: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    cookies: dict[str, str] | None = None
    json_body: Any | None = Field(default=None, alias="json")
    data: dict[str, Any] | None = None
    content: bytes | str | None = None
    timeout: float | None = None

    def normalized_method(self) -> str:
        """Return the method upper-cased (accepts str or :class:`HttpMethod`)."""
        if isinstance(self.method, HttpMethod):
            return self.method.value
        return self.method.upper()


@dataclass(frozen=True)
class ApiResponse:
    """A decoupled HTTP response exposed to tests.

    Constructed from an :class:`httpx.Response`; copying the data out makes the
    response independent of the underlying client lifecycle. Timing is supplied
    by the caller (the client measures it) since httpx ``elapsed`` is only set
    for real transports.
    """

    status_code: int
    headers: dict[str, str]
    body: bytes
    url: str
    method: str
    elapsed_seconds: float
    encoding: str = "utf-8"

    @classmethod
    def from_httpx(cls, response: httpx.Response, *, elapsed_seconds: float = 0.0) -> ApiResponse:
        """Build an :class:`ApiResponse` from an :class:`httpx.Response`."""
        encoding = response.encoding or "utf-8"
        grouped: dict[str, list[str]] = {}
        for key, value in response.headers.multi_items():
            grouped.setdefault(key, []).append(value)
        headers = {key: ", ".join(values) for key, values in grouped.items()}
        return cls(
            status_code=response.status_code,
            headers=headers,
            body=response.content,
            url=str(response.url),
            method=response.request.method,
            elapsed_seconds=elapsed_seconds,
            encoding=encoding,
        )

    @property
    def text(self) -> str:
        """Decode the body using the response encoding (lenient)."""
        return self.body.decode(self.encoding or "utf-8", errors="replace")

    @property
    def json(self) -> Any:
        """Parse the body as JSON; ``None`` when the body is empty."""
        if not self.body:
            return None
        return json.loads(self.body)

    @property
    def ok(self) -> bool:
        """Whether the status code is a 2xx success."""
        return 200 <= self.status_code < 300

    def raise_for_status(self) -> None:
        """Raise :class:`ClientStatusError` when the status is not 2xx."""
        if not self.ok:
            raise ClientStatusError(
                f"HTTP {self.status_code}",
                status_code=self.status_code,
                body_snippet=self.text[:500],
                context={"method": self.method, "url": self.url},
            )
