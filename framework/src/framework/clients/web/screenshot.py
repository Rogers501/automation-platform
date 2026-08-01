"""Playwright screenshot provider for the hooks layer.

Implements :class:`framework.testing.hooks.screenshot.ScreenshotProvider`
using the active ``WebClient`` page. When no page is available (e.g. the
web client was never started), capture is a no-op (returns ``None``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from framework.testing.hooks.screenshot import ScreenshotProvider

__all__ = ["PlaywrightScreenshotProvider"]


class PlaywrightScreenshotProvider(ScreenshotProvider):
    """Screenshot provider backed by a Playwright WebClient page.

    Args:
        client: A :class:`WebClient` whose page will be used for capture.
        screenshot_dir: Directory to save screenshots (defaults to ``logs/screenshots``).
    """

    def __init__(
        self,
        client: Any,
        *,
        screenshot_dir: Path | str = "logs/screenshots",
    ) -> None:
        self._client = client
        self._dir = Path(screenshot_dir)

    def screenshot(self, name: str) -> Path | None:
        """Capture a screenshot if a page is active.

        Sync wrapper around the async Playwright screenshot call.
        When the event loop is already running (async tests), the screenshot
        is scheduled as a task without blocking.
        """
        page = getattr(self._client, "page", None)
        if page is None:
            return None

        import asyncio

        self._dir.mkdir(parents=True, exist_ok=True)
        safe_name = name.replace("/", "_").replace("\\", "_")
        path = self._dir / f"{safe_name}.png"

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                _task = loop.create_task(
                    page.screenshot(path=str(path), full_page=False),
                )
            else:
                asyncio.run(
                    page.screenshot(path=str(path), full_page=False),
                )
            return path
        except Exception:
            return None
