"""Web automation client (Playwright).

Public API: ``WebClient`` for async browser automation, and
``PlaywrightScreenshotProvider`` for integration with the framework's
screenshot hook on test failure.

Usage::

    async with WebClient() as client:
        await client.goto("https://example.com")
        await client.screenshot("home.png")

The ``playwright`` package is imported lazily; the framework does not
hard-depend on it at import time.
"""

from framework.clients.web.captcha_solver import TencentCaptchaSolver
from framework.clients.web.client import WebClient
from framework.clients.web.screenshot import PlaywrightScreenshotProvider

__all__ = ["PlaywrightScreenshotProvider", "TencentCaptchaSolver", "WebClient"]
