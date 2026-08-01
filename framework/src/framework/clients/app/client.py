"""App automation client built on Appium-Python-Client.

Implements async mobile app automation (navigation, interaction, screenshots)
using Appium's WebDriver API. The ``appium`` package is imported lazily so the
framework does not hard-depend on it; a missing package surfaces as a clear
error on first use. All blocking calls are dispatched via
:func:`asyncio.to_thread` (rule 16).

Pass an explicit ``driver`` for isolation in tests (rule 14).

Usage::

    async with AppClient() as client:
        await client.click("id=login_button")
        await client.send_keys("id=username", "alice")
        text = await client.text("id=welcome")

Defaults come from :attr:`FrameworkSettings.app`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loguru import logger

from framework.core.config import AppSettings, get_settings
from framework.core.exceptions import ClientError

__all__ = ["AppClient"]


class AppClient:
    """Async Appium app automation client.

    The driver is created lazily on first use. Use ``async with`` to
    guarantee cleanup.

    Args:
        settings: App settings; defaults to :func:`get_settings().app`.
        driver: Pre-built Appium driver for testing (bypasses lazy import).
        name: Logical client name for log correlation.
    """

    def __init__(
        self,
        settings: AppSettings | None = None,
        *,
        driver: Any = None,
        name: str = "app",
    ) -> None:
        self._settings = settings if settings is not None else get_settings().app
        self._injected_driver = driver
        self._driver: Any = driver
        self._name = name
        self._logger = logger.bind(component="app_client", client=name)
        self._closed = False

    # --- lifecycle -----------------------------------------------------

    async def _ensure_driver(self) -> Any:
        """Lazily build the Appium driver on first use."""
        if self._closed:
            raise ClientError("AppClient is closed")
        if self._driver is not None:
            return self._driver

        try:
            from appium import webdriver
        except ImportError as exc:
            raise ClientError(
                "appium-python-client package is not installed; run 'uv sync' to install it",
                context={"error_type": type(exc).__name__},
            ) from exc

        caps: dict[str, Any] = {
            "platformName": self._settings.platform_name,
            "automationName": self._settings.automation_name,
            "noReset": self._settings.no_reset,
            "fullReset": self._settings.full_reset,
            "newCommandTimeout": self._settings.new_command_timeout,
        }
        if self._settings.device_name:
            caps["deviceName"] = self._settings.device_name
        if self._settings.app_package:
            caps["appPackage"] = self._settings.app_package
        if self._settings.app_activity:
            caps["appActivity"] = self._settings.app_activity
        if self._settings.app_path:
            caps["app"] = self._settings.app_path
        if self._settings.udid:
            caps["udid"] = self._settings.udid
        if self._settings.platform_version:
            caps["platformVersion"] = self._settings.platform_version

        try:
            self._driver = await asyncio.to_thread(
                webdriver.Remote,
                self._settings.server_url,
                options=self._build_options(caps),
            )
        except TypeError:
            # Older appium versions use desired_capabilities kwarg.
            self._driver = await asyncio.to_thread(
                webdriver.Remote,
                self._settings.server_url,
                desired_capabilities=caps,
            )
        if self._settings.implicit_wait_ms:
            await asyncio.to_thread(
                self._driver.implicitly_wait,
                self._settings.implicit_wait_ms / 1000,
            )
        self._logger.info(
            "appium driver started: {} platform={}",
            self._settings.server_url,
            self._settings.platform_name,
        )
        return self._driver

    def _build_options(self, caps: dict[str, Any]) -> Any:
        """Build Appium options from capabilities (lazy import).

        Override in tests to inject a fake options object.
        """
        from appium.options.android import UiAutomator2Options

        if self._settings.platform_name.lower() == "ios":
            from appium.options.ios import XCUITestOptions

            return XCUITestOptions().load_capabilities(caps)
        return UiAutomator2Options().load_capabilities(caps)

    async def close(self) -> None:
        """Quit the Appium driver."""
        self._closed = True
        if self._driver is not None:
            try:
                await asyncio.to_thread(self._driver.quit)
            except Exception as exc:
                self._logger.warning("driver quit error: {}", exc)
            self._driver = None

    async def __aenter__(self) -> AppClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    @property
    def is_closed(self) -> bool:
        """Whether the client has been closed."""
        return self._closed

    @property
    def driver(self) -> Any:
        """The underlying Appium driver (or None if not started)."""
        return self._driver

    # --- interaction ----------------------------------------------------

    async def click(self, element: str) -> None:
        """Click an element by its locator string (e.g. ``id=btn``)."""
        drv = await self._ensure_driver()
        by, value = self._parse_locator(element)
        try:
            el = await asyncio.to_thread(drv.find_element, by, value)
            await asyncio.to_thread(el.click)
        except Exception as exc:
            raise self._wrap(exc, context={"op": "click", "element": element}) from exc

    async def send_keys(self, element: str, text: str) -> None:
        """Type text into an input element."""
        drv = await self._ensure_driver()
        by, value = self._parse_locator(element)
        try:
            el = await asyncio.to_thread(drv.find_element, by, value)
            await asyncio.to_thread(el.send_keys, text)
        except Exception as exc:
            raise self._wrap(exc, context={"op": "send_keys", "element": element}) from exc

    async def text(self, element: str) -> str:
        """Get the text content of an element."""
        drv = await self._ensure_driver()
        by, value = self._parse_locator(element)
        try:
            el = await asyncio.to_thread(drv.find_element, by, value)
            return await asyncio.to_thread(lambda: el.text) or ""
        except Exception as exc:
            raise self._wrap(exc, context={"op": "text", "element": element}) from exc

    async def get_attribute(self, element: str, name: str) -> str | None:
        """Get an attribute value from an element."""
        drv = await self._ensure_driver()
        by, value = self._parse_locator(element)
        try:
            el = await asyncio.to_thread(drv.find_element, by, value)
            return await asyncio.to_thread(el.get_attribute, name)
        except Exception as exc:
            raise self._wrap(exc, context={"op": "get_attribute", "element": element}) from exc

    # --- waiting --------------------------------------------------------

    async def wait_for_element(
        self,
        element: str,
        *,
        timeout_s: float = 10.0,
    ) -> None:
        """Wait for an element to be present."""
        try:
            from selenium.webdriver.support.ui import WebDriverWait
        except ImportError as exc:
            raise ClientError(
                "selenium package is not installed",
                context={"error_type": type(exc).__name__},
            ) from exc

        drv = await self._ensure_driver()
        by, value = self._parse_locator(element)
        try:
            await asyncio.to_thread(
                WebDriverWait(drv, timeout_s).until,
                lambda d: d.find_element(by, value),
            )
        except Exception as exc:
            raise self._wrap(exc, context={"op": "wait_for_element", "element": element}) from exc

    # --- screenshots ----------------------------------------------------

    async def screenshot(self, path: str | Path | None = None) -> bytes:
        """Capture a screenshot; returns the image bytes."""
        drv = await self._ensure_driver()
        try:
            return await asyncio.to_thread(drv.get_screenshot_as_png)
        except Exception as exc:
            raise self._wrap(exc, context={"op": "screenshot"}) from exc

    # --- internals ------------------------------------------------------

    @staticmethod
    def _parse_locator(locator: str) -> tuple[str, str]:
        """Parse a locator string into (by, value).

        Supported prefixes: ``id=``, ``xpath=``, ``class=``,
        ``accessibility_id=``, ``name=``, ``css=``. If no prefix, defaults
        to ``id=``.
        """
        prefix_map = {
            "id=": "id",
            "xpath=": "xpath",
            "class=": "class name",
            "accessibility_id=": "accessibility id",
            "name=": "name",
            "css=": "css selector",
        }
        for prefix, by in prefix_map.items():
            if locator.startswith(prefix):
                return by, locator[len(prefix) :]
        return "id", locator

    def _wrap(self, exc: Exception, *, context: Mapping[str, Any] | None = None) -> ClientError:
        """Convert an Appium error into a :class:`ClientError`."""
        ctx: dict[str, Any] = dict(context or {})
        ctx.setdefault("error_type", type(exc).__name__)
        self._logger.warning("app client error: {}", exc)
        return ClientError(str(exc), context=ctx)
