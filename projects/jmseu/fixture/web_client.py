"""WebClient fixture: fake page for CI (rule 14), real browser for prod.

By default the fixture injects a fake Playwright page so tests run without a
browser or network (rule 14: unit tests must isolate external dependencies).
Set env ``JMSEU_REAL_BROWSER=1`` and configure ``web.base_url`` to run against
a real browser.

The ``screenshot_provider`` fixture overrides the framework's null provider so
failure screenshots are captured via Playwright during WebUI tests.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
from pages.login_page import LoginPage

from framework.clients.web import PlaywrightScreenshotProvider, WebClient
from framework.core.config import get_settings
from framework.testing.hooks.screenshot import ScreenshotProvider


class _FakeMouse:
    """Fake Playwright Mouse for CI isolation (rule 14)."""

    async def move(self, x: float, y: float, **kwargs: Any) -> None:
        pass

    async def down(self, **kwargs: Any) -> None:
        pass

    async def up(self, **kwargs: Any) -> None:
        pass


class _FakeLocator:
    """Fake Playwright Locator for CI isolation (rule 14)."""

    def __init__(self, selector: str = "") -> None:
        self._selector = selector

    async def screenshot(self, **kwargs: Any) -> bytes:
        return b"fake-screenshot"

    async def bounding_box(self) -> dict[str, float] | None:
        return {"x": 0.0, "y": 0.0, "width": 100.0, "height": 100.0}

    async def click(self, **kwargs: Any) -> None:
        pass

    @property
    def first(self) -> _FakeLocator:
        return self

    def get_by_text(self, text: str, **kwargs: Any) -> _FakeLocator:
        return _FakeLocator(f"text={text}")

    def get_by_role(self, role: str, **kwargs: Any) -> _FakeLocator:
        return _FakeLocator(f"role={role}")


class _FakeJmseuPage:
    """Fake Playwright page simulating the jmseu login -> dashboard flow.

    Behaves like a real page but without a browser (rule 14). After the login
    button is clicked, the page transitions to the "logged-in" state; subsequent
    ``wait_for_function`` / ``text_content`` calls reflect the dashboard.
    Selector checks reference :class:`LoginPage` constants to verify the page
    object uses the correct selectors.
    """

    def __init__(self) -> None:
        self.visited: list[str] = []
        self.filled: list[tuple[str, str]] = []
        self.clicked: list[str] = []
        self._logged_in = False
        self._username = ""
        self.mouse = _FakeMouse()

    async def goto(self, url: str, **kwargs: Any) -> None:
        self.visited.append(url)

    async def fill(self, selector: str, value: str, **kwargs: Any) -> None:
        self.filled.append((selector, value))
        if selector == LoginPage.USERNAME_INPUT:
            self._username = value

    async def click(self, selector: str, **kwargs: Any) -> None:
        self.clicked.append(selector)
        if selector == LoginPage.LOGIN_BUTTON:
            self._logged_in = True

    async def text_content(self, selector: str, **kwargs: Any) -> str:
        if selector == LoginPage.WELCOME_TEXT and self._logged_in:
            return f"Welcome, {self._username}"
        return ""

    async def inner_text(self, selector: str, **kwargs: Any) -> str:
        return await self.text_content(selector)

    async def get_attribute(self, selector: str, name: str, **kwargs: Any) -> str | None:
        return None

    async def is_visible(self, selector: str, **kwargs: Any) -> bool:
        # Cookie consent and language selector are not present in fake mode.
        if "接受" in selector or selector == "i":
            return False
        # Login form elements are visible before login.
        return selector in (
            LoginPage.USERNAME_INPUT,
            LoginPage.PASSWORD_INPUT,
            LoginPage.LOGIN_BUTTON,
        )

    async def wait_for_selector(self, selector: str, **kwargs: Any) -> None:
        pass  # fake page: all selectors are immediately "found"

    async def wait_for_url(self, url: str, **kwargs: Any) -> None:
        if not self._logged_in:
            raise RuntimeError("timeout: URL did not change to dashboard")

    async def wait_for_function(self, expression: str, *args: Any, **kwargs: Any) -> None:
        # Used by LoginPage.wait_for_login_success to detect URL change.
        if not self._logged_in:
            raise RuntimeError("timeout: still on login page")

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        return None

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator(selector)

    def get_by_role(self, role: str, **kwargs: Any) -> _FakeLocator:
        return _FakeLocator(f"role={role}")

    def set_default_timeout(self, timeout: int) -> None:
        pass

    async def screenshot(self, **kwargs: Any) -> bytes:
        return b"fake-jmseu-screenshot-png"

    async def close(self) -> None:
        pass


@pytest.fixture
def base_url() -> str:
    """Web base URL from framework config (``web.base_url``)."""
    return get_settings().web.base_url


@pytest.fixture
async def web_client(base_url: str) -> AsyncIterator[WebClient]:
    """WebClient with an injected fake page (CI) or real browser (prod).

    Set ``JMSEU_REAL_BROWSER=1`` to launch a real Playwright browser. The fake
    page keeps tests fast and isolated (rule 14).
    """
    settings = get_settings().web

    if os.environ.get("JMSEU_REAL_BROWSER") == "1":
        # 真实浏览器模式: 每步操作至少间隔1秒(>=1000ms), 方便观察页面变化
        if settings.slow_mo_ms < 1000:
            settings = settings.model_copy(update={"slow_mo_ms": 1000})
        async with WebClient(settings=settings) as client:
            yield client
    else:
        client = WebClient(settings=settings, page=_FakeJmseuPage())
        try:
            yield client
        finally:
            await client.close()


@pytest.fixture
def screenshot_provider(web_client: WebClient) -> ScreenshotProvider:
    """Override the framework's null provider: capture failure screenshots."""
    return PlaywrightScreenshotProvider(web_client)
