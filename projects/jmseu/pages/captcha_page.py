"""Captcha handler for jmseu login (auto-solve + manual fallback).

The jmseu login uses a Tencent slide-puzzle captcha (tencent-captcha-dy).
This handler first attempts automatic solving via OpenCV gap detection
and human-like mouse trajectory. If auto-solve is unavailable (missing
dependencies) or fails, it falls back to manual mode: the operator
completes the slide in the visible browser.

Auto-solve requires: pip install opencv-python-headless numpy
"""

from __future__ import annotations

from loguru import logger

from framework.clients.web.captcha_solver import TencentCaptchaSolver
from pages.base_page import BasePage

__all__ = ["TencentSliderCaptcha"]


class TencentSliderCaptcha(BasePage):
    """Tencent slide-captcha handler (auto-solve + manual fallback).

    Tries automatic solving first; falls back to manual if:
      - opencv/numpy not installed
      - gap detection fails
      - auto-solve attempts exhausted
    """

    #: Dashboard text confirming login success after captcha.
    SUCCESS_TEXT = "text=\u529f\u80fd\u5165\u53e3"

    async def solve(self, *, timeout_ms: int = 120000) -> bool:
        """Attempt auto-solve, fall back to manual if needed.

        Args:
            timeout_ms: Max wait for success text (manual fallback).

        Returns:
            True if login success detected; False otherwise.
        """
        page = self.client.page
        if page is None:
            logger.warning("no active page; cannot handle captcha")
            return False

        # Login may have succeeded without captcha.
        if "/login" not in page.url:
            logger.info("already past login page; no captcha needed")
            return True

        # Brief wait: login click may redirect without captcha.
        try:
            await page.wait_for_function(
                "() => !window.location.pathname.includes('/login')",
                timeout=5000,
            )
            logger.info("login redirected without captcha; no captcha needed")
            return True
        except Exception:
            pass  # still on /login; captcha challenge likely

        # --- Attempt automatic solving ---
        solver = TencentCaptchaSolver(page)
        logger.info("attempting automatic captcha solving")
        solved = await solver.solve(timeout_ms=10000, max_retries=3)
        if solved:
            return True

        # --- Fall back to manual mode ---
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
        """Save a diagnostic screenshot when login success is not detected."""
        page = self.client.page
        if page is None:
            return
        try:
            await page.screenshot(path="captcha_debug.png")
            logger.warning("debug: screenshot saved to captcha_debug.png")
        except Exception as exc:
            logger.warning("debug: screenshot failed: {}", exc)
