"""Unit tests for framework.core.logger (isolated loguru state, rule 14)."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest
from loguru import logger as _logger

from framework.core.config import FrameworkSettings, reset_settings
from framework.core.context import clear_context, trace
from framework.core.logger import (
    CONSOLE_FORMAT,
    FILE_FORMAT,
    MAX_BODY_LENGTH,
    _truncate_body,
    format_record_as_json,
    get_logger,
    log_exception,
    log_request,
    setup_logging,
)


@pytest.fixture(autouse=True)
def _clean_logger() -> None:
    """Remove all loguru handlers before and after each test."""
    _logger.remove()
    yield
    _logger.remove()


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> Iterator[None]:
    """Isolate APP_ env vars and config dir for FrameworkSettings construction."""
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    for key in list(os.environ):
        if key.startswith("APP_") and key != "APP_CONFIG_DIR":
            monkeypatch.delenv(key, raising=False)
    reset_settings()
    clear_context()
    yield
    reset_settings()
    clear_context()


def _capture(level: str = "DEBUG") -> list[str]:
    """Add a memory sink and return the messages list."""
    messages: list[str] = []
    _logger.add(messages.append, level=level, format="{message}")
    return messages


def _settings(tmp_path: Any, **kwargs: Any) -> FrameworkSettings:
    """Build FrameworkSettings with a tmp log_dir."""
    defaults: dict[str, Any] = {"log_level": "DEBUG", "log_dir": tmp_path / "logs"}
    defaults.update(kwargs)
    return FrameworkSettings(**defaults)


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------


def test_setup_logging_creates_log_dir(tmp_path: Any) -> None:
    """setup_logging creates the log directory if it does not exist."""
    log_dir = tmp_path / "logs"
    assert not log_dir.exists()
    setup_logging(_settings(tmp_path))
    assert log_dir.exists()


def test_setup_logging_writes_file(tmp_path: Any) -> None:
    """Log messages are written to the file sink."""
    setup_logging(_settings(tmp_path))
    log = get_logger("test")
    log.info("file message")
    log_file = tmp_path / "logs" / "app.log"
    assert log_file.exists()
    assert "file message" in log_file.read_text(encoding="utf-8")


def test_setup_logging_json_sink(tmp_path: Any) -> None:
    """The JSON sink produces serialized JSON output."""
    json_file = tmp_path / "app.json"
    setup_logging(_settings(tmp_path), json_file=json_file)
    log = get_logger("test")
    log.info("json message")
    content = json_file.read_text(encoding="utf-8")
    assert "json message" in content
    parsed = json.loads(content.strip().split("\n")[0])
    assert "record" in parsed


def test_setup_logging_idempotent(tmp_path: Any) -> None:
    """Calling setup_logging twice does not duplicate handlers."""
    settings = _settings(tmp_path)
    setup_logging(settings)
    setup_logging(settings)
    log = get_logger("test")
    log.info("once only")
    content = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert content.count("once only") == 1


def test_setup_logging_level_filtering(tmp_path: Any) -> None:
    """Messages below the configured level are not written."""
    setup_logging(_settings(tmp_path, log_level="WARNING"))
    log = get_logger("test")
    log.info("info filtered")
    log.warning("warning kept")
    content = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "info filtered" not in content
    assert "warning kept" in content


# ---------------------------------------------------------------------------
# get_logger
# ---------------------------------------------------------------------------


def test_get_logger_returns_logger() -> None:
    """get_logger returns a loguru-compatible logger."""
    log = get_logger("comp")
    assert hasattr(log, "info")
    assert hasattr(log, "error")


def test_get_logger_binds_name() -> None:
    """The name is bound as 'component' in the extra context."""
    messages: list[str] = []
    _logger.add(messages.append, level="DEBUG", format="{message} | {extra}")
    log = get_logger("my_component")
    log.info("hello")
    assert any("my_component" in m for m in messages)


def test_get_logger_binds_extra() -> None:
    """Extra kwargs are bound to the logger."""
    messages: list[str] = []
    _logger.add(messages.append, level="DEBUG", format="{message} | {extra}")
    log = get_logger("svc", trace_id="abc-123")
    log.info("request")
    assert any("abc-123" in m for m in messages)


def test_get_logger_no_name() -> None:
    """get_logger without a name still works."""
    messages = _capture()
    log = get_logger()
    log.info("no name")
    assert any("no name" in m for m in messages)


def test_get_logger_auto_binds_trace_id() -> None:
    """get_logger auto-binds the current context trace_id."""
    messages: list[str] = []
    _logger.add(messages.append, level="DEBUG", format="{message} | {extra}")
    with trace(trace_id="trace-xyz"):
        log = get_logger("svc")
        log.info("hello")
    assert any("trace-xyz" in m for m in messages)


def test_get_logger_explicit_binding_overrides_context() -> None:
    """Explicit trace_id binding takes priority over the context."""
    messages: list[str] = []
    _logger.add(messages.append, level="DEBUG", format="{extra}")
    with trace(trace_id="context-id"):
        log = get_logger("svc", trace_id="explicit-id")
        log.info("hello")
    joined = " ".join(messages)
    assert "explicit-id" in joined
    assert "context-id" not in joined


def test_get_logger_no_context_no_trace() -> None:
    """Without an active trace, no trace_id is bound."""
    messages: list[str] = []
    _logger.add(messages.append, level="DEBUG", format="{extra}")
    log = get_logger("svc")
    log.info("hello")
    assert "trace_id" not in " ".join(messages)


# ---------------------------------------------------------------------------
# log_exception
# ---------------------------------------------------------------------------


def test_log_exception_logs_message() -> None:
    """log_exception logs the exception message at ERROR level."""
    messages = _capture("ERROR")
    try:
        raise ValueError("test error")
    except ValueError as exc:
        log_exception(exc)
    assert any("test error" in m for m in messages)


def test_log_exception_includes_error_type() -> None:
    """log_exception adds error_type to the context."""
    messages: list[str] = []
    _logger.add(messages.append, level="ERROR", format="{message} | {extra}")
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        log_exception(exc)
    assert any("ValueError" not in m and "RuntimeError" in m for m in messages)


def test_log_exception_with_context() -> None:
    """Custom context is included in the log."""
    messages: list[str] = []
    _logger.add(messages.append, level="ERROR", format="{message} | {extra}")
    try:
        raise KeyError("missing")
    except KeyError as exc:
        log_exception(exc, context={"url": "http://test", "phase": "fetch"})
    assert any("http://test" in m and "fetch" in m for m in messages)


# ---------------------------------------------------------------------------
# log_request
# ---------------------------------------------------------------------------


def test_log_request_outgoing() -> None:
    """Outgoing request is logged with -> prefix."""
    messages = _capture("INFO")
    log_request("GET", "http://example.com/api")
    assert any("-> GET http://example.com/api" in m for m in messages)


def test_log_request_response_success() -> None:
    """Successful response is logged at INFO with status and elapsed."""
    messages = _capture("INFO")
    log_request("POST", "http://example.com/api", status_code=201, elapsed=0.05)
    assert any("<- 201 POST" in m for m in messages)
    assert any("50.0ms" in m for m in messages)


def test_log_request_response_error() -> None:
    """Non-2xx response is logged at WARNING level."""
    messages: list[str] = []
    _logger.add(messages.append, level="WARNING", format="{message}")
    log_request("GET", "http://example.com/api", status_code=500, elapsed=0.1)
    assert any("<- 500 GET" in m for m in messages)


def test_log_request_with_body() -> None:
    """Request body is included (truncated) in the extra context."""
    messages: list[str] = []
    _logger.add(messages.append, level="INFO", format="{message} | {extra}")
    log_request("POST", "http://example.com/api", request_body='{"id":1}')
    assert any('"id":1' in m or "id" in m for m in messages)


def test_log_request_truncates_long_body() -> None:
    """Long bodies are truncated to MAX_BODY_LENGTH."""
    long_body = "x" * (MAX_BODY_LENGTH + 500)
    messages: list[str] = []
    _logger.add(messages.append, level="INFO", format="{extra}")
    log_request("POST", "http://example.com/api", request_body=long_body)
    assert any("..." in m for m in messages)


def test_log_request_bytes_body() -> None:
    """Bytes bodies are decoded for logging."""
    messages: list[str] = []
    _logger.add(messages.append, level="INFO", format="{extra}")
    log_request("POST", "http://example.com/api", request_body=b"raw bytes")
    assert any("raw bytes" in m for m in messages)


# ---------------------------------------------------------------------------
# format_record_as_json
# ---------------------------------------------------------------------------


def _fake_record(
    message: str = "test", level: str = "INFO", extra: dict | None = None
) -> dict[str, Any]:
    """Build a minimal loguru record dict for testing."""
    return {
        "time": datetime(2024, 1, 1, 12, 0, 0),
        "level": SimpleNamespace(name=level),
        "message": message,
        "name": "test_module",
        "function": "test_func",
        "line": 42,
        "extra": extra or {},
    }


def test_format_record_as_json_basic() -> None:
    """format_record_as_json produces valid JSON with expected fields."""
    result = format_record_as_json(_fake_record("hello", "INFO"))
    data = json.loads(result)
    assert data["message"] == "hello"
    assert data["level"] == "INFO"
    assert data["module"] == "test_module"
    assert data["function"] == "test_func"
    assert data["line"] == 42


def test_format_record_as_json_with_extra() -> None:
    """Extra fields are included in the JSON output."""
    record = _fake_record(extra={"component": "svc", "trace_id": "abc"})
    data = json.loads(format_record_as_json(record))
    assert data["extra"] == {"component": "svc", "trace_id": "abc"}


def test_format_record_as_json_no_extra() -> None:
    """Empty extra dict is omitted from the JSON output."""
    data = json.loads(format_record_as_json(_fake_record()))
    assert "extra" not in data


# ---------------------------------------------------------------------------
# _truncate_body
# ---------------------------------------------------------------------------


def test_truncate_body_none() -> None:
    """None passes through unchanged."""
    assert _truncate_body(None) is None


def test_truncate_body_short_string() -> None:
    """Short strings are returned unchanged."""
    assert _truncate_body("hello") == "hello"


def test_truncate_body_long_string() -> None:
    """Long strings are truncated with '...' suffix."""
    long_text = "x" * (MAX_BODY_LENGTH + 500)
    result = _truncate_body(long_text)
    assert result is not None
    assert len(result) == MAX_BODY_LENGTH + 3
    assert result.endswith("...")


def test_truncate_body_bytes() -> None:
    """Bytes are decoded to string."""
    assert _truncate_body(b"hello") == "hello"


def test_truncate_body_custom_max() -> None:
    """Custom max_length is respected."""
    result = _truncate_body("abcdef", max_length=3)
    assert result == "abc..."


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_format_constants() -> None:
    """Format constants are non-empty strings."""
    assert isinstance(CONSOLE_FORMAT, str)
    assert len(CONSOLE_FORMAT) > 0
    assert isinstance(FILE_FORMAT, str)
    assert len(FILE_FORMAT) > 0


def test_max_body_length_positive() -> None:
    """MAX_BODY_LENGTH is a positive integer."""
    assert isinstance(MAX_BODY_LENGTH, int)
    assert MAX_BODY_LENGTH > 0
