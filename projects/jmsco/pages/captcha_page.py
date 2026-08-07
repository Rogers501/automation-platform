"""Manual captcha handler for jmsco login (human-in-the-loop).

The jmsco login uses a slide-puzzle captcha (拖动下方滑块完成拼图). Automatic
solving is brittle and risks IP bans, so this handler takes a
human-in-the-loop approach: the operator completes the slide manually in
the visible browser, then the script waits for the dashboard's text to
confirm login success.

Only runs in real-browser mode; this project has no CI fake-page test.
"""

from __future__ import annotations

from loguru import logger

from pages.base_page import BasePage

__all__ = ["SlidePuzzleCaptcha"]


class SlidePuzzleCaptcha(BasePage):
    """Manual slide-puzzle captcha handler (human-in-the-loop).

    The operator completes the slide in the real browser while the script
    waits; success is detected by the dashboard text.
    """

    #: Dashboard text that confirms login success after captcha.
    SUCCESS_TEXT = "text=功能入口"

    async def solve(self, *, timeout_ms: int = 120000) -> bool:
        """Wait for manual captcha completion, then confirm login success.

        If login already succeeded without a captcha (URL left `/login`),
        returns True immediately. Otherwise waits for the operator to
        complete the slide manually in the visible browser, then detects
        success by the dashboard text.

        Args:
            timeout_ms: Max wait for the success text to appear.

        Returns:
            True if login success detected; False otherwise.
        """
        page = self.client.page
        if page is None:
            logger.warning("no active page; cannot handle captcha")
            return False

        # Login may have succeeded without a captcha (URL left /login).
        if "/login" not in page.url:
            logger.info("already past login page; no captcha needed")
            return True

        # Brief wait: the login click may redirect without a captcha.
        try:
            await page.wait_for_function(
                "() => !window.location.pathname.includes('/login')",
                timeout=5000,
            )
            logger.info("login redirected without captcha; no captcha needed")
            return True
        except Exception:
            pass  # still on /login; a captcha challenge is likely

        logger.info("waiting for manual captcha completion (operator slides in browser)")

        # Wait for the dashboard success text -- the operator completes the
        # slide manually; this confirms both captcha solved and login succeeded.
        try:
            await page.wait_for_selector(self.SUCCESS_TEXT, timeout=timeout_ms)
            logger.info("login success detected")
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
