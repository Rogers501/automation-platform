"""Unit tests for WebClient using a fake Playwright page (rule 14)."""

from __future__ import annotations

from typing import Any

import pytest

from framework.clients.web import PlaywrightScreenshotProvider, WebClient
from framework.core.config import WebSettings
from framework.core.exceptions import ClientError

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakePage:
    """Fake Playwright page."""

    def __init__(self) -> None:
        self.url_visited: list[str] = []
        self.clicked: list[str] = []
        self.filled: list[tuple[str, str]] = []
        self.screenshots: int = 0
        self.screenshot_bytes: bytes = b"fake-png"
        self._closed = False
        self._default_timeout: int | None = None

    async def goto(self, url: str, **kwargs: Any) -> None:
        self.url_visited.append(url)

    async def click(self, selector: str, **kwargs: Any) -> None:
        self.clicked.append(selector)

    async def fill(self, selector: str, value: str, **kwargs: Any) -> None:
        self.filled.append((selector, value))

    async def text_content(self, selector: str, **kwargs: Any) -> str:
        return f"text-of-{selector}"

    async def inner_text(self, selector: str, **kwargs: Any) -> str:
        return f"inner-{selector}"

    async def get_attribute(self, selector: str, name: str, **kwargs: Any) -> str | None:
        return f"attr-{name}"

    async def wait_for_selector(self, selector: str, **kwargs: Any) -> None:
        pass

    async def wait_for_url(self, url: str, **kwargs: Any) -> None:
        pass

    async def screenshot(self, **kwargs: Any) -> bytes:
        self.screenshots += 1
        return self.screenshot_bytes

    def set_default_timeout(self, timeout: int) -> None:
        self._default_timeout = timeout

    async def close(self) -> None:
        self._closed = True


def _client(page: _FakePage | None = None) -> WebClient:
    """Build a WebClient wired to a fake page."""
    return WebClient(settings=WebSettings(), page=page)


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


async def test_goto_navigates() -> None:
    """goto calls page.goto with the URL."""
    page = _FakePage()
    client = _client(page=page)

    await client.goto("https://example.com")

    assert page.url_visited == ["https://example.com"]


async def test_goto_error_wrapped() -> None:
    """A navigation error surfaces as ClientError."""

    class _ErrorPage(_FakePage):
        async def goto(self, url: str, **kwargs: Any) -> None:
            raise RuntimeError("net::ERR_CONNECTION_REFUSED")

    client = _client(page=_ErrorPage())

    with pytest.raises(ClientError) as info:
        await client.goto("https://fail.com")

    assert "ERR_CONNECTION_REFUSED" in str(info.value)
    assert info.value.context["op"] == "goto"


# ---------------------------------------------------------------------------
# Interaction
# ---------------------------------------------------------------------------


async def test_click() -> None:
    """click calls page.click."""
    page = _FakePage()
    client = _client(page=page)

    await client.click("#submit")

    assert page.clicked == ["#submit"]


async def test_fill() -> None:
    """fill calls page.fill with value."""
    page = _FakePage()
    client = _client(page=page)

    await client.fill("#username", "alice")

    assert page.filled == [("#username", "alice")]


async def test_text() -> None:
    """text returns the element's text content."""
    page = _FakePage()
    client = _client(page=page)

    result = await client.text(".welcome")

    assert result == "text-of-.welcome"


async def test_inner_text() -> None:
    """inner_text returns the element's inner text."""
    page = _FakePage()
    client = _client(page=page)

    result = await client.inner_text(".title")

    assert result == "inner-.title"


async def test_get_attribute() -> None:
    """get_attribute returns the attribute value."""
    page = _FakePage()
    client = _client(page=page)

    result = await client.get_attribute("#link", "href")

    assert result == "attr-href"


# ---------------------------------------------------------------------------
# Waiting
# ---------------------------------------------------------------------------


async def test_wait_for_selector() -> None:
    """wait_for_selector does not raise when element appears."""
    page = _FakePage()
    client = _client(page=page)

    await client.wait_for_selector("#loaded")

    # No exception means success.


async def test_wait_for_url() -> None:
    """wait_for_url does not raise."""
    page = _FakePage()
    client = _client(page=page)

    await client.wait_for_url("**/dashboard")

    # No exception means success.


# ---------------------------------------------------------------------------
# Screenshots
# ---------------------------------------------------------------------------


async def test_screenshot_returns_bytes() -> None:
    """screenshot returns image bytes."""
    page = _FakePage()
    client = _client(page=page)

    result = await client.screenshot()

    assert result == b"fake-png"
    assert page.screenshots == 1


async def test_screenshot_with_path() -> None:
    """screenshot accepts a path."""
    page = _FakePage()
    client = _client(page=page)

    await client.screenshot("shot.png")

    assert page.screenshots == 1


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


async def test_close() -> None:
    """close marks the client as closed."""
    page = _FakePage()
    client = _client(page=page)
    await client.goto("https://test.com")
    await client.close()

    assert client.is_closed


async def test_async_context_manager() -> None:
    """async with closes the client."""
    page = _FakePage()
    async with _client(page=page) as client:
        await client.goto("https://test.com")
    assert client.is_closed


async def test_operations_after_close_raise() -> None:
    """Operations on a closed client raise ClientError."""
    page = _FakePage()
    client = _client(page=page)
    await client.close()

    with pytest.raises(ClientError):
        await client.goto("https://test.com")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_web_settings_defaults() -> None:
    """WebSettings has sensible defaults."""
    settings = WebSettings()
    assert settings.browser == "chromium"
    assert settings.headless is True
    assert settings.timeout_ms == 30000
    assert settings.viewport_width == 1280
    assert settings.viewport_height == 720


def test_web_settings_custom() -> None:
    """WebSettings accepts custom values."""
    settings = WebSettings(browser="firefox", headless=False, base_url="https://staging.test")
    assert settings.browser == "firefox"
    assert settings.headless is False
    assert settings.base_url == "https://staging.test"


# ---------------------------------------------------------------------------
# PlaywrightScreenshotProvider
# ---------------------------------------------------------------------------


def test_screenshot_provider_no_page() -> None:
    """Provider returns None when no page is active."""
    client = WebClient(settings=WebSettings())
    provider = PlaywrightScreenshotProvider(client)

    result = provider.screenshot("test")

    assert result is None


def test_screenshot_provider_with_page(tmp_path: Any) -> None:
    """Provider captures a screenshot when a page is active."""
    page = _FakePage()
    client = _client(page=page)
    provider = PlaywrightScreenshotProvider(client, screenshot_dir=tmp_path)

    result = provider.screenshot("my_test")

    assert result is not None
    assert result.name == "my_test.png"
