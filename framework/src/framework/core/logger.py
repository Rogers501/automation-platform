"""Centralized loguru logging configuration.

Reads ``log_level``, ``log_dir``, ``log_rotation``, and ``log_retention`` from
:class:`FrameworkSettings`. Provides:

- **Console sink** -- colored output to ``stderr``.
- **File sink** -- rotating files (default: daily at midnight).
- **Exception logging** -- full tracebacks with structured context.
- **Request logging** -- HTTP request/response with body truncation.
- **Context binding** -- ``get_logger(name, **bindings)`` for per-component logs.
- **JSON utility** -- ``format_record_as_json`` for custom structured sinks.

Usage::

    from framework.core.logger import setup_logging, get_logger, log_request

    setup_logging()                       # call once at startup
    log = get_logger("orders", trace_id="abc-123")
    log.info("processing order")
    log_request("POST", "/api/orders", status_code=201, elapsed=0.05)
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loguru import logger as _logger

from framework.core.config import FrameworkSettings, get_settings
from framework.core.context import get_context

__all__ = [
    "CONSOLE_FORMAT",
    "FILE_FORMAT",
    "MAX_BODY_LENGTH",
    "format_record_as_json",
    "get_logger",
    "log_exception",
    "log_request",
    "setup_logging",
]

#: Default console format with loguru color tags.
CONSOLE_FORMAT: str = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

#: Plain-text file format (no color tags).
FILE_FORMAT: str = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"
)

#: Maximum body snippet length included in request/response logs.
MAX_BODY_LENGTH: int = 1024


def format_record_as_json(record: dict[str, Any]) -> str:
    """Format a loguru record dict as a single JSON line.

    Utility for creating custom JSON-structured sinks outside of loguru's
    built-in ``serialize=True`` option.

    Args:
        record: The ``record`` dict from a loguru :class:`Message`.

    Returns:
        A JSON string with ``timestamp``, ``level``, ``message``, ``module``,
        ``function``, ``line``, and optional ``extra`` fields.
    """
    payload: dict[str, Any] = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "message": record["message"],
        "module": record["name"],
        "function": record["function"],
        "line": record["line"],
    }
    extra = record.get("extra", {})
    if extra:
        payload["extra"] = dict(extra)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _truncate_body(
    body: str | bytes | None,
    max_length: int = MAX_BODY_LENGTH,
) -> str | None:
    """Truncate a request/response body for safe logging.

    Args:
        body: Raw body (str or bytes); ``None`` passes through.
        max_length: Maximum characters to keep (appends ``...`` when truncated).

    Returns:
        The truncated string, or ``None``.
    """
    if body is None:
        return None
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    if len(body) > max_length:
        return body[:max_length] + "..."
    return body


def setup_logging(
    settings: FrameworkSettings | None = None,
    *,
    json_file: Path | None = None,
) -> None:
    """Configure loguru with console + file sinks from :class:`FrameworkSettings`.

    Idempotent: removes all existing handlers before adding new ones, so
    calling this multiple times never duplicates output.

    Args:
        settings: Framework settings; defaults to :func:`get_settings`.
        json_file: Optional path for an additional JSON-structured sink
            (uses loguru ``serialize=True``).
    """
    resolved = settings if settings is not None else get_settings()

    _logger.remove()

    # Console sink (colored)
    _logger.add(
        sys.stderr,
        level=resolved.log_level,
        format=CONSOLE_FORMAT,
        colorize=True,
    )

    # File sink (rotating + retention)
    log_dir = Path(resolved.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    _logger.add(
        log_dir / "app.log",
        level=resolved.log_level,
        format=FILE_FORMAT,
        rotation=resolved.log_rotation,
        retention=resolved.log_retention,
        encoding="utf-8",
    )

    # Optional JSON sink
    if json_file is not None:
        _logger.add(
            json_file,
            level=resolved.log_level,
            serialize=True,
            encoding="utf-8",
        )


def get_logger(name: str | None = None, **bindings: Any) -> Any:
    """Return a loguru logger bound with extra context.

    Args:
        name: Logical component name (stored as ``component`` in extra).
        **bindings: Additional context key-value pairs (e.g. ``trace_id="abc"``).

    Returns:
        A context-bound loguru logger instance.
    """
    extra: dict[str, Any] = get_context().to_bindings()
    if name:
        extra.setdefault("component", name)
    extra.update(bindings)
    return _logger.bind(**extra)


def log_exception(
    exc: BaseException,
    *,
    log: Any = None,
    context: Mapping[str, Any] | None = None,
) -> None:
    """Log an exception with full traceback and structured context.

    Uses loguru ``opt(exception=exc)`` to embed the traceback in the log
    record. The ``error_type`` is automatically added to the context.

    Args:
        exc: The exception to log.
        log: Optional pre-bound logger; defaults to ``get_logger("exception")``.
        context: Optional structured key/value pairs for diagnostics.
    """
    logger = log if log is not None else get_logger("exception")
    extra: dict[str, Any] = dict(context or {})
    extra.setdefault("error_type", type(exc).__name__)
    logger.opt(exception=exc).bind(**extra).error("Exception: {}", str(exc))


def log_request(
    method: str,
    url: str,
    *,
    status_code: int | None = None,
    elapsed: float | None = None,
    request_headers: Mapping[str, str] | None = None,
    response_headers: Mapping[str, str] | None = None,
    request_body: str | bytes | None = None,
    response_body: str | bytes | None = None,
    log: Any = None,
) -> None:
    """Log an HTTP request and/or response with structured details.

    When ``status_code`` is ``None``, logs only the outgoing request (``->``).
    When ``status_code`` is provided, logs the incoming response (``<-``).

    Bodies are truncated to :data:`MAX_BODY_LENGTH` characters. Non-2xx
    responses are logged at ``WARNING`` level; successful responses at ``INFO``.

    Args:
        method: HTTP method (``GET``, ``POST``, etc.).
        url: Request URL.
        status_code: Response status code (``None`` for request-only).
        elapsed: Elapsed time in seconds.
        request_headers: Optional request headers dict.
        response_headers: Optional response headers dict.
        request_body: Optional request body (truncated for logging).
        response_body: Optional response body (truncated for logging).
        log: Optional pre-bound logger; defaults to ``get_logger("http")``.
    """
    logger = log if log is not None else get_logger("http")
    extra: dict[str, Any] = {"method": method, "url": url}

    if elapsed is not None:
        extra["elapsed_ms"] = round(elapsed * 1000, 2)
    if request_headers is not None:
        extra["request_headers"] = dict(request_headers)
    if response_headers is not None:
        extra["response_headers"] = dict(response_headers)

    req_snippet = _truncate_body(request_body)
    if req_snippet is not None:
        extra["request_body"] = req_snippet
    resp_snippet = _truncate_body(response_body)
    if resp_snippet is not None:
        extra["response_body"] = resp_snippet

    if status_code is None:
        # Outgoing request
        logger.bind(**extra).info("-> {} {}", method, url)
    else:
        extra["status_code"] = status_code
        elapsed_str = f"{extra.get('elapsed_ms', '?')}ms"
        if 200 <= status_code < 400:
            logger.bind(**extra).info("<- {} {} ({})", status_code, method, elapsed_str)
        else:
            logger.bind(**extra).warning("<- {} {} ({})", status_code, method, elapsed_str)
