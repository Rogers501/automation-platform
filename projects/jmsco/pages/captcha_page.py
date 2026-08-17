"""Captcha handler for jmsmx login (auto-solve + manual fallback).

The jmsmx login uses a Tencent slide-puzzle captcha (tencent-captcha-dy).
Auto-solve via OpenCV gap detection + human-like drag; falls back to
manual mode if dependencies missing or auto-solve fails.

Auto-solve requires: pip install opencv-python-headless numpy
"""

from __future__ import annotations

from loguru import logger

from framework.clients.web.captcha_solver import TencentCaptchaSolver
from pages.base_page import BasePage

__all__ = ["SlidePuzzleCaptcha"]


class SlidePuzzleCaptcha(BasePage):
    """Tencent slide-puzzle captcha handler (auto-solve + manual fallback)."""

    SUCCESS_TEXT = "text=\u529f\u80fd\u5165\u53e3"

    async def solve(self, *, timeout_ms: int = 120000) -> bool:
        page = self.client.page
        if page is None:
            logger.warning("no active page; cannot handle captcha")
            return False

        if "/login" not in page.url:
            logger.info("already past login page; no captcha needed")
            return True

        try:
            await page.wait_for_function(
                "() => !window.location.pathname.includes('/login')",
                timeout=5000,
            )
            logger.info("login redirected without captcha; no captcha needed")
            return True
        except Exception:
            pass

        solver = TencentCaptchaSolver(page)
        logger.info("attempting automatic captcha solving")
        solved = await solver.solve(timeout_ms=10000, max_retries=3)
        if solved:
            return True

        logger.warning(
            "auto-solve failed or unavailable; "
            "falling back to manual mode (operator slides in browser)"
        )
        try:
            await page.wait_for_selector(self.SUCCESS_TEXT, timeout=timeout_ms)
            logger.info("login success detected (manual)")
            return True
        except Exception:
            logger.warning("login success text not detected; login may have failed")
            await self._debug_screenshot()
            return False

    async def _debug_screenshot(self) -> None:
        page = self.client.page
        if page is None:
            return
        try:
            await page.screenshot(path="captcha_debug.png")
            logger.warning("debug: screenshot saved to captcha_debug.png")
        except Exception as exc:
            logger.warning("debug: screenshot failed: {}", exc)
