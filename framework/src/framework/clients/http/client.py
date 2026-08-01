"""Enterprise async HTTP client built on httpx.

Features: connection pooling, multi-stage timeout, idempotent retry with
backoff (honors ``Retry-After``), pluggable auth, persistent cookie jar,
structured request/response logging with sensitive-field redaction, and a
unified exception hierarchy (:class:`ClientTimeoutError`,
:class:`ClientConnectionError`, :class:`ClientStatusError`).

Usage::

    async with AsyncHttpClient() as client:
        resp = await client.get("/users", params={"active": "true"})
        resp.raise_for_status()

Defaults come from :attr:`FrameworkSettings.http`; pass an explicit
:class:`HttpSettings` for isolation in tests.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable, Mapping
from typing import Any

import httpx
from loguru import logger

from framework.clients.http.auth import AuthProvider
from framework.clients.http.models import ApiResponse, RequestSpec
from framework.clients.http.redaction import (
    DEFAULT_SENSITIVE_HEADERS,
    redact_headers,
    truncate_body,
)
from framework.clients.http.retry import RetryPolicy
from framework.core.config import HttpSettings, get_settings
from framework.core.context import get_context
from framework.core.exceptions import (
    ClientConnectionError,
    ClientError,
    ClientStatusError,
    ClientTimeoutError,
)
from framework.core.recorder import HttpExchange, get_recorder

__all__ = ["AsyncHttpClient"]


def _parse_retry_after(response: httpx.Response) -> float | None:
    """Parse a ``Retry-After`` header (seconds form only) from a response."""
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        # HTTP-date form is not supported in this version.
        return None


def _header_present(headers: Mapping[str, str], name: str) -> bool:
    """Return whether ``name`` (case-insensitive) is present in ``headers``."""
    target = name.lower()
    return any(key.lower() == target for key in headers)


class AsyncHttpClient:
    """Async HTTP client with retry, auth, cookies, and structured logging.

    The underlying :class:`httpx.AsyncClient` is created lazily (on first use)
    so the constructor is safe to call outside an event loop. Use ``async
    with`` to guarantee the connection pool is closed.
    """

    def __init__(
        self,
        settings: HttpSettings | None = None,
        *,
        auth: AuthProvider | None = None,
        headers: Mapping[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        sensitive_headers: Iterable[str] | None = None,
        name: str = "http",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings if settings is not None else get_settings().http
        self._auth = auth
        self._base_headers: dict[str, str] = dict(headers or {})
        self._cookies = httpx.Cookies(cookies)
        configured = (
            sensitive_headers if sensitive_headers is not None else self._settings.sensitive_headers
        )
        configured_set = frozenset(h.lower() for h in configured)
        self._sensitive = configured_set or DEFAULT_SENSITIVE_HEADERS
        self._name = name
        self._transport = transport
        self._retry = RetryPolicy(
            max_attempts=self._settings.retry_max_attempts,
            backoff_factor=self._settings.retry_backoff_factor,
            max_backoff=self._settings.retry_max_backoff,
            retry_statuses=frozenset(self._settings.retry_statuses),
            retry_methods=frozenset(m.upper() for m in self._settings.retry_methods),
        )
        self._logger = logger.bind(component="http_client", client=name)
        self._client: httpx.AsyncClient | None = None
        self._closed = False

    # --- lifecycle -----------------------------------------------------

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._closed:
            raise ClientError("AsyncHttpClient is closed")
        if self._client is None or self._client.is_closed:
            timeout = httpx.Timeout(
                connect=self._settings.connect_timeout,
                read=self._settings.read_timeout,
                write=self._settings.write_timeout,
                pool=self._settings.pool_timeout,
            )
            limits = httpx.Limits(
                max_connections=self._settings.max_connections,
                max_keepalive_connections=self._settings.max_keepalive_connections,
                keepalive_expiry=self._settings.keepalive_expiry,
            )
            client_kwargs: dict[str, Any] = {
                "timeout": timeout,
                "limits": limits,
                "cookies": self._cookies,
                "transport": self._transport,
            }
            if self._settings.base_url:
                client_kwargs["base_url"] = self._settings.base_url
            self._client = httpx.AsyncClient(**client_kwargs)
        return self._client

    async def aclose(self) -> None:
        """Close the underlying connection pool and mark the client closed."""
        self._closed = True
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> AsyncHttpClient:
        await self._ensure_client()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    @property
    def is_closed(self) -> bool:
        """Whether the client has been closed and can no longer send."""
        return self._closed

    @property
    def cookies(self) -> httpx.Cookies:
        """The persistent cookie jar shared across requests."""
        return self._cookies

    def clear_cookies(self) -> None:
        """Empty the cookie jar."""
        self._cookies.clear()

    # --- convenience verbs ---------------------------------------------

    async def get(self, url: str, **kwargs: Any) -> ApiResponse:
        """Issue a GET request."""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> ApiResponse:
        """Issue a POST request."""
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> ApiResponse:
        """Issue a PUT request."""
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> ApiResponse:
        """Issue a DELETE request."""
        return await self.request("DELETE", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> ApiResponse:
        """Issue a PATCH request."""
        return await self.request("PATCH", url, **kwargs)

    # --- spec-based (data-driven) --------------------------------------

    async def send(self, spec: RequestSpec) -> ApiResponse:
        """Execute a :class:`RequestSpec`."""
        return await self.request(
            spec.normalized_method(),
            spec.url,
            params=spec.params,
            headers=spec.headers,
            cookies=spec.cookies,
            json=spec.json_body,
            data=spec.data,
            content=spec.content,
            timeout=spec.timeout,
        )

    # --- core -----------------------------------------------------------

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        json: Any | None = None,
        data: Mapping[str, Any] | None = None,
        content: bytes | str | None = None,
        timeout: float | None = None,
        raise_for_status: bool | None = None,
        auth: AuthProvider | None = None,
    ) -> ApiResponse:
        """Execute an HTTP request with auth, logging, and retry.

        Args:
            method: HTTP verb (e.g. ``"GET"``).
            url: Absolute URL or path relative to ``base_url``.
            params: Query parameters.
            headers: Per-request headers (merged over client base headers).
            cookies: Per-request cookies (merged over the jar).
            json: JSON body (serializable object).
            data: Form-encoded body (mapping).
            content: Raw body (bytes/str).
            timeout: Per-request timeout override (seconds).
            raise_for_status: Override the client's ``raise_for_status``.
            auth: Per-request auth provider (overrides the client default).
        """
        client = await self._ensure_client()
        method_upper = method.upper()
        effective_auth = auth if auth is not None else self._auth
        merged_headers = {**self._base_headers, **dict(headers or {})}
        if effective_auth is not None:
            await effective_auth.apply(merged_headers, dict(cookies or {}))

        ctx = get_context()
        if (
            self._settings.propagate_trace_id
            and ctx.trace_id
            and not _header_present(merged_headers, self._settings.trace_header)
        ):
            merged_headers[self._settings.trace_header] = ctx.trace_id

        build_kwargs: dict[str, Any] = {
            "params": params,
            "headers": merged_headers,
            "cookies": cookies,
            "json": json,
            "data": data,
            "content": content,
        }
        if timeout is not None:
            build_kwargs["timeout"] = timeout
        request = client.build_request(method_upper, url, **build_kwargs)

        should_raise = (
            self._settings.raise_for_status if raise_for_status is None else raise_for_status
        )
        try:
            response, elapsed = await self._execute(client, request, method_upper, should_raise)
        except ClientError as exc:
            self._record(request, None, 0.0, error=exc)
            raise
        self._record(request, response, elapsed)
        return ApiResponse.from_httpx(response, elapsed_seconds=elapsed)

    async def _execute(
        self,
        client: httpx.AsyncClient,
        request: httpx.Request,
        method: str,
        raise_for_status: bool,
    ) -> tuple[httpx.Response, float]:
        """Send ``request`` with retry; return ``(response, elapsed_seconds)``."""
        attempt = 0
        while True:
            try:
                attempt += 1
                self._log_request(request, attempt)
                start = time.perf_counter()
                response = await client.send(request)
                elapsed = time.perf_counter() - start
                self._log_response(response, attempt, elapsed)

                if (
                    not self._retry.attempts_exhausted(attempt)
                    and self._retry.should_retry_method(method)
                    and self._retry.should_retry_status(response.status_code)
                ):
                    delay = self._retry.compute_delay(attempt, _parse_retry_after(response))
                    self._logger.warning(
                        "retryable status {} for {} {} (attempt {}/{}) sleeping {:.3f}s",
                        response.status_code,
                        method,
                        request.url,
                        attempt,
                        self._retry.max_attempts,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                if raise_for_status and not response.is_success:
                    raise ClientStatusError(
                        f"HTTP {response.status_code} from {method} {request.url}",
                        status_code=response.status_code,
                        body_snippet=truncate_body(response.text, 500),
                        context={
                            "method": method,
                            "url": str(request.url),
                            "attempt": attempt,
                        },
                    )
                return response, elapsed
            except httpx.TimeoutException as exc:
                if not self._retry.attempts_exhausted(attempt) and self._retry.should_retry_method(
                    method
                ):
                    delay = self._retry.compute_delay(attempt)
                    self._logger.warning(
                        "timeout on {} {} (attempt {}/{}) retrying in {:.3f}s",
                        method,
                        request.url,
                        attempt,
                        self._retry.max_attempts,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise ClientTimeoutError(
                    f"timeout calling {method} {request.url}",
                    context={
                        "method": method,
                        "url": str(request.url),
                        "attempt": attempt,
                    },
                ) from exc
            except httpx.TransportError as exc:
                if not self._retry.attempts_exhausted(attempt) and self._retry.should_retry_method(
                    method
                ):
                    delay = self._retry.compute_delay(attempt)
                    self._logger.warning(
                        "transport error on {} {} (attempt {}/{}): {}",
                        method,
                        request.url,
                        attempt,
                        self._retry.max_attempts,
                        str(exc),
                    )
                    await asyncio.sleep(delay)
                    continue
                raise ClientConnectionError(
                    f"connection error calling {method} {request.url}: {exc}",
                    context={
                        "method": method,
                        "url": str(request.url),
                        "attempt": attempt,
                        "error": str(exc),
                    },
                ) from exc

    # --- logging -------------------------------------------------------

    def _log_request(self, request: httpx.Request, attempt: int) -> None:
        """Log an outbound request (sensitive headers redacted)."""
        safe_headers = redact_headers(dict(request.headers), self._sensitive)
        self._logger.info(
            "-> {} {} attempt={}",
            request.method,
            request.url,
            attempt,
        )
        self._logger.debug("request headers: {}", safe_headers)
        if self._settings.log_bodies and request.content:
            body = truncate_body(
                request.content.decode("utf-8", errors="replace"),
                self._settings.log_body_max_length,
            )
            self._logger.debug("request body: {}", body)

    def _log_response(self, response: httpx.Response, attempt: int, elapsed_seconds: float) -> None:
        """Log an inbound response (sensitive headers redacted)."""
        safe_headers = redact_headers(dict(response.headers), self._sensitive)
        self._logger.info(
            "<- {} {} ({:.3f}s) attempt={}",
            response.status_code,
            response.request.method,
            elapsed_seconds,
            attempt,
        )
        self._logger.debug("response headers: {}", safe_headers)
        if self._settings.log_bodies and response.content:
            body = truncate_body(response.text, self._settings.log_body_max_length)
            self._logger.debug("response body: {}", body)

    def _record(
        self,
        request: httpx.Request,
        response: httpx.Response | None,
        elapsed: float,
        *,
        error: ClientError | None = None,
    ) -> None:
        """Record the exchange to the active recorder (no-op when none is bound)."""
        recorder = get_recorder()
        if recorder is None:
            return
        req_headers = redact_headers(dict(request.headers), self._sensitive)
        req_body: str | None = None
        if request.content:
            req_body = truncate_body(
                request.content.decode("utf-8", errors="replace"),
                self._settings.log_body_max_length,
            )
        status_code: int | None
        resp_headers: dict[str, str]
        resp_body: str | None
        if response is not None:
            status_code = response.status_code
            resp_headers = redact_headers(dict(response.headers), self._sensitive)
            resp_body = (
                truncate_body(response.text, self._settings.log_body_max_length)
                if response.content
                else None
            )
        else:
            status_code = error.status_code if isinstance(error, ClientStatusError) else None
            resp_headers = {}
            resp_body = error.body_snippet if isinstance(error, ClientStatusError) else None
        recorder.record(
            HttpExchange(
                method=request.method,
                url=str(request.url),
                request_headers=req_headers,
                request_body=req_body,
                status_code=status_code,
                response_headers=resp_headers,
                response_body=resp_body,
                elapsed_seconds=elapsed,
                error=str(error) if error is not None else None,
                trace_id=get_context().trace_id,
            )
        )
