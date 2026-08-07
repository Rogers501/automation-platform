"""WebClient fixture: real browser for jmseu (德国) testing.

Always launches a visible Playwright browser (slow_mo >= 1s for observation).
Configure web.base_url via config/envs/*.yaml and credentials via data files.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from framework.clients.web import PlaywrightScreenshotProvider, WebClient
from framework.core.config import get_settings
from framework.testing.hooks.screenshot import ScreenshotProvider


@pytest.fixture
def base_url() -> str:
    """Web base URL from framework config (``web.base_url``)."""
    return get_settings().web.base_url


@pytest.fixture
async def web_client(base_url: str) -> AsyncIterator[WebClient]:
    """WebClient with a real Playwright browser (visible, slow_mo >= 1s)."""
    settings = get_settings().web
    if settings.slow_mo_ms < 1000:
        settings = settings.model_copy(update={"slow_mo_ms": 1000})
    async with WebClient(settings=settings) as client:
        yield client


@pytest.fixture
def screenshot_provider(web_client: WebClient) -> ScreenshotProvider:
    """Override the framework null provider: capture failure screenshots."""
    return PlaywrightScreenshotProvider(web_client)
