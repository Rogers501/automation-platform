"""Web automation client built on Playwright.

Implements async browser automation (navigation, interaction, screenshots)
using Playwright's async API. The ``playwright`` package is imported lazily
so the framework does not hard-depend on it at import time; a missing package
surfaces as a clear error on first use. Pass an explicit ``page`` for
isolation in tests (rule 14).

Usage::

    async with WebClient() as client:
        await client.goto("https://example.com")
        await client.fill("#username", "alice")
        await client.click("#submit")
        text = await client.text(".welcome")

Defaults come from :attr:`FrameworkSettings.web`.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loguru import logger

from framework.core.config import WebSettings, get_settings
from framework.core.exceptions import ClientError

__all__ = ["WebClient"]


class WebClient:
    """Async Playwright web automation client.

    The browser and page are created lazily on first use. Use ``async with``
    to guarantee the browser is closed.

    Args:
        settings: Web settings; defaults to :func:`get_settings().web`.
        page: Pre-built Playwright page for testing (bypasses lazy import).
        name: Logical client name for log correlation.
    """

    def __init__(
        self,
        settings: WebSettings | None = None,
        *,
        page: Any = None,
        name: str = "web",
    ) -> None:
        self._settings = settings if settings is not None else get_settings().web
        self._injected_page = page
        self._page: Any = page
        self._browser: Any = None
        self._playwright: Any = None
        self._context: Any = None
        self._name = name
        self._logger = logger.bind(component="web_client", client=name)
        self._closed = False

    # --- lifecycle -----------------------------------------------------

    async def _ensure_page(self) -> Any:
        """Lazily build the browser and page on first use."""
        if self._closed:
            raise ClientError("WebClient is closed")
        if self._page is not None:
            return self._page

        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ClientError(
                "playwright package is not installed; run 'uv sync' to install it",
                context={"error_type": type(exc).__name__},
            ) from exc

        self._playwright = await async_playwright().start()

        browser_type = getattr(self._playwright, self._settings.browser, None)
        if browser_type is None:
            raise ClientError(
                f"Unknown browser: {self._settings.browser}",
                context={"valid": ["chromium", "firefox", "webkit"]},
            )

        launch_kwargs: dict[str, Any] = {
            "headless": self._settings.headless,
            "slow_mo": self._settings.slow_mo_ms,
        }
        # Use the system-installed browser when a channel is configured
        # (e.g. channel="chrome" uses the local Google Chrome install,
        # avoiding a separate `playwright install` download).
        if self._settings.channel:
            launch_kwargs["channel"] = self._settings.channel
        self._browser = await browser_type.launch(**launch_kwargs)

        context_kwargs: dict[str, Any] = {
            "viewport": {
                "width": self._settings.viewport_width,
                "height": self._settings.viewport_height,
            },
            "ignore_https_errors": self._settings.ignore_https_errors,
        }
        if self._settings.base_url:
            context_kwargs["base_url"] = self._settings.base_url
        if self._settings.http_username:
            context_kwargs["http_credentials"] = {
                "username": self._settings.http_username,
                "password": self._settings.http_password,
            }

        self._context = await self._browser.new_context(**context_kwargs)
        self._page = await self._context.new_page()
        self._page.set_default_timeout(self._settings.timeout_ms)
        self._logger.info(
            "playwright browser started: {} headless={}",
            self._settings.browser,
            self._settings.headless,
        )
        return self._page

    async def close(self) -> None:
        """Close the page, context, browser, and playwright runtime."""
        self._closed = True
        for resource in (self._page, self._context, self._browser):
            if resource is not None:
                try:
                    await resource.close()
                except Exception as exc:
                    self._logger.warning("resource close error: {}", exc)
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as exc:
                self._logger.warning("playwright stop error: {}", exc)
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    async def __aenter__(self) -> WebClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    @property
    def is_closed(self) -> bool:
        """Whether the client has been closed."""
        return self._closed

    @property
    def page(self) -> Any:
        """The underlying Playwright page (or None if not started)."""
        return self._page

    # --- navigation -----------------------------------------------------

    async def goto(
        self,
        url: str,
        *,
        wait_until: str = "domcontentloaded",
        timeout_ms: int | None = None,
    ) -> None:
        """Navigate to a URL."""
        page = await self._ensure_page()
        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
        except Exception as exc:
            raise self._wrap(exc, context={"op": "goto", "url": url}) from exc

    # --- interaction ----------------------------------------------------

    async def click(self, selector: str, *, timeout_ms: int | None = None) -> None:
        """Click an element matched by ``selector``."""
        page = await self._ensure_page()
        try:
            await page.click(selector, timeout=timeout_ms)
        except Exception as exc:
            raise self._wrap(exc, context={"op": "click", "selector": selector}) from exc

    async def fill(
        self,
        selector: str,
        value: str,
        *,
        timeout_ms: int | None = None,
    ) -> None:
        """Fill an input element matched by ``selector`` with ``value``."""
        page = await self._ensure_page()
        try:
            await page.fill(selector, value, timeout=timeout_ms)
        except Exception as exc:
            raise self._wrap(
                exc,
                context={"op": "fill", "selector": selector},
            ) from exc

    async def text(self, selector: str, *, timeout_ms: int | None = None) -> str:
        """Get the text content of an element matched by ``selector``."""
        page = await self._ensure_page()
        try:
            return await page.text_content(selector, timeout=timeout_ms) or ""
        except Exception as exc:
            raise self._wrap(exc, context={"op": "text", "selector": selector}) from exc

    async def inner_text(self, selector: str, *, timeout_ms: int | None = None) -> str:
        """Get the inner text of an element matched by ``selector``."""
        page = await self._ensure_page()
        try:
            return await page.inner_text(selector, timeout=timeout_ms)
        except Exception as exc:
            raise self._wrap(exc, context={"op": "inner_text", "selector": selector}) from exc

    async def get_attribute(
        self,
        selector: str,
        name: str,
        *,
        timeout_ms: int | None = None,
    ) -> str | None:
        """Get an attribute value from an element matched by ``selector``."""
        page = await self._ensure_page()
        try:
            return await page.get_attribute(selector, name, timeout=timeout_ms)
        except Exception as exc:
            raise self._wrap(
                exc,
                context={"op": "get_attribute", "selector": selector, "attr": name},
            ) from exc

    # --- waiting --------------------------------------------------------

    async def wait_for_selector(
        self,
        selector: str,
        *,
        state: str = "visible",
        timeout_ms: int | None = None,
    ) -> None:
        """Wait for an element to reach a given state."""
        page = await self._ensure_page()
        try:
            await page.wait_for_selector(
                selector,
                state=state,
                timeout=timeout_ms,
            )
        except Exception as exc:
            raise self._wrap(
                exc,
                context={"op": "wait_for_selector", "selector": selector},
            ) from exc

    async def wait_for_url(
        self,
        url: str,
        *,
        timeout_ms: int | None = None,
    ) -> None:
        """Wait for the page URL to match ``url`` (glob pattern)."""
        page = await self._ensure_page()
        try:
            await page.wait_for_url(url, timeout=timeout_ms)
        except Exception as exc:
            raise self._wrap(exc, context={"op": "wait_for_url", "url": url}) from exc

    # --- screenshots ----------------------------------------------------

    async def screenshot(
        self,
        path: str | Path | None = None,
        *,
        full_page: bool = False,
    ) -> bytes:
        """Capture a screenshot; returns the image bytes."""
        page = await self._ensure_page()
        try:
            return await page.screenshot(
                path=str(path) if path else None,
                full_page=full_page,
            )
        except Exception as exc:
            raise self._wrap(exc, context={"op": "screenshot"}) from exc

    # --- internals ------------------------------------------------------

    def _wrap(self, exc: Exception, *, context: Mapping[str, Any] | None = None) -> ClientError:
        """Convert a Playwright error into a :class:`ClientError`."""
        ctx: dict[str, Any] = dict(context or {})
        ctx.setdefault("error_type", type(exc).__name__)
        self._logger.warning("web client error: {}", exc)
        return ClientError(str(exc), context=ctx)
