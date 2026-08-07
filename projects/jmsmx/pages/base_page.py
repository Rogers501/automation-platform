"""Base page object: wraps WebClient with common page operations.

All page objects inherit from BasePage to reuse navigation, waiting, and
screenshot logic (rule 4: public capabilities abstracted; rule 8: no
duplication).
"""

from __future__ import annotations

from typing import Any

from framework.clients.web import WebClient


class BasePage:
    """Base page object wrapping a :class:`WebClient`.

    Subclasses define ``path`` and page-specific selectors/actions.
    """

    #: Page-relative path (appended to base_url), override in subclasses.
    path: str = ""

    def __init__(self, client: WebClient, *, base_url: str = "") -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def open(self) -> None:
        """Navigate to this page (base_url + path)."""
        url = f"{self._base_url}{self.path}" if self._base_url else self.path
        await self._client.goto(url)

    async def click(self, selector: str) -> None:
        """Click an element."""
        await self._client.click(selector)

    async def fill(self, selector: str, value: str) -> None:
        """Fill an input field."""
        await self._client.fill(selector, value)

    async def text(self, selector: str) -> str:
        """Get text content of an element."""
        return await self._client.text(selector)

    async def wait_for_selector(
        self, selector: str, *, state: str = "visible", timeout_ms: int | None = None
    ) -> None:
        """Wait for an element to reach a state."""
        await self._client.wait_for_selector(selector, state=state, timeout_ms=timeout_ms)

    async def wait_for_url(self, url: str) -> None:
        """Wait for the page URL to match a glob pattern."""
        await self._client.wait_for_url(url)

    async def screenshot(self, path: str | None = None) -> bytes:
        """Capture a screenshot; returns image bytes."""
        return await self._client.screenshot(path)

    async def is_visible(self, selector: str) -> bool:
        """Check if an element is visible on the page."""
        page = self.client.page
        if page is None:
            return False
        try:
            return bool(await page.is_visible(selector))
        except Exception:
            return False

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        """Evaluate a JavaScript expression on the page."""
        return await self.client.page.evaluate(script, arg)

    async def wait_for_function(self, script: str, *, timeout_ms: int | None = None) -> None:
        """Wait for a JavaScript function to return truthy."""
        await self.client.page.wait_for_function(script, timeout=timeout_ms)

    def locator(self, selector: str) -> Any:
        """Get a Playwright Locator for advanced operations."""
        return self.client.page.locator(selector)

    @property
    def mouse(self) -> Any:
        """The page's Mouse object for low-level mouse control."""
        return self.client.page.mouse

    @property
    def client(self) -> WebClient:
        """The underlying WebClient."""
        return self._client
