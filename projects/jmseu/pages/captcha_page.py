"""Tencent slider captcha handler for jmseu login (manual, human-in-the-loop).

The jmseu (German JMS) login uses Tencent's slide verification
(tencent-captcha-dy), rendered inside an iframe. Automatic gap-cracking is
brittle and risks IP bans, so this handler takes a human-in-the-loop approach:

1. Wait for the captcha iframe to attach, then switch into it via
   ``frame_locator``.
2. Confirm the slider groove is visible (proves we are in the right frame).
3. Pause the script on an interactive prompt; the operator completes the
   slide manually in the real browser.
4. After the operator presses Enter, click the "确定" (confirm) button inside
   the iframe, then return control for post-login assertions.

Only runs in real-browser mode (``JMSEU_REAL_BROWSER=1``); the CI fake page
bypasses the captcha entirely (rule 14).
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from loguru import logger

from pages.base_page import BasePage

__all__ = ["TencentSliderCaptcha"]


class TencentSliderCaptcha(BasePage):
    """Tencent slide-puzzle captcha handler (tencent-captcha-dy, manual).

    Human-in-the-loop: the operator completes the slide while the script
    pauses on an interactive prompt. No automatic gap detection or dragging.
    """

    #: Captcha iframe selector. Tencent loads the widget in an iframe whose
    #: ``src`` contains "captcha"; override on the class if a deployment
    #: uses a different iframe locator.
    CAPTCHA_IFRAME = 'iframe[src*="captcha"]'

    #: Slider groove (滑动轨道) -- exact class per F12 DOM analysis.
    SLIDER_GROOVE = ".tencent-captcha-dy_slider-groove"

    #: Slider handle (滑动按钮) -- partial class match ("class 包含").
    SLIDER_BLOCK = '[class*="tencent-captcha-dy_slider-block-normal"]'

    #: Confirm button (确定) -- partial class match ("class 包含").
    CONFIRM_BUTTON = '[class*="tencent-captcha-dy_verify-confirm-btn"]'

    async def solve(self, *, timeout_ms: int = 30000) -> bool:
        """Handle the slider captcha with manual operator completion.

        Waits for the captcha iframe, switches into it via ``frame_locator``,
        confirms the slider groove is visible, then pauses for the operator
        to complete the slide manually. After Enter, clicks the confirm
        button (best-effort) and returns.

        Args:
            timeout_ms: Wait timeout for the iframe and groove to appear.

        Returns:
            True if the captcha iframe was found and the operator was
            prompted; False if no iframe appeared within the timeout. Also
            returns True (early) when login already succeeded without a
            captcha.
        """
        page = self.client.page
        if page is None:
            logger.warning("no active page; cannot handle captcha")
            return False

        # Login may have succeeded without a captcha (URL left /login).
        if "/login" not in page.url:
            logger.info("already past login page; no captcha needed")
            return True

        # Brief wait: the login click may redirect without a captcha. Give
        # the page a short window to leave /login before assuming a captcha
        # is required. This avoids a false "iframe not found" when login
        # succeeds instantly (no captcha challenge).
        try:
            await page.wait_for_function(
                "() => !window.location.pathname.includes('/login')",
                timeout=5000,
            )
            logger.info("login redirected without captcha; no captcha needed")
            return True
        except Exception:
            pass  # still on /login; a captcha challenge is likely

        logger.info("waiting for tencent captcha iframe")
        frame = await self._captcha_frame(timeout_ms=timeout_ms)
        if frame is None:
            logger.warning("captcha iframe not found within {}ms", timeout_ms)
            await self._debug_capture()
            return False

        # Confirm we are inside the right frame by locating the groove.
        try:
            await frame.locator(self.SLIDER_GROOVE).wait_for(state="visible", timeout=timeout_ms)
        except Exception as exc:
            logger.warning("slider groove not visible in captcha iframe: {}", exc)
            return False

        logger.info("captcha iframe ready; pausing for manual slide")
        # Human-in-the-loop: the operator drags the slider in the real
        # browser. input() blocks the calling thread, so run it off the
        # asyncio event loop to comply with rule 16 (no blocking in async).
        # When stdin is a TTY (interactive terminal) the operator gets the
        # input() prompt and presses Enter after sliding. When stdin is not
        # a TTY (e.g. launched by a non-interactive runner), skip the prompt
        # and wait for the page to leave /login -- the operator slides in the
        # visible browser and the URL change signals captcha completion.
        if sys.stdin.isatty():
            await asyncio.to_thread(input, "请手动完成滑动验证，完成后按回车继续...")  # noqa: RUF001
            # After the operator finished, click "确定" (best-effort: Tencent
            # sometimes auto-submits without a confirm button).
            await self._click_confirm(frame)
        else:
            logger.info("non-interactive stdin; waiting for captcha completion via URL change")
            await self._wait_for_captcha_solved()
        return True

    async def _captcha_frame(self, *, timeout_ms: int) -> Any:
        """Wait for the captcha iframe and return its ``frame_locator``.

        Returns None if the iframe does not attach within ``timeout_ms``.
        """
        page = self.client.page
        try:
            await page.wait_for_selector(self.CAPTCHA_IFRAME, timeout=timeout_ms)
        except Exception:
            return None
        return page.frame_locator(self.CAPTCHA_IFRAME)

    async def _debug_capture(self) -> None:
        """Capture diagnostics when the captcha iframe is not found.

        Logs the current URL, lists every <iframe> src on the page, and
        saves a screenshot so the operator can see the actual page state.
        """
        page = self.client.page
        if page is None:
            return
        logger.warning("debug: current URL = {}", page.url)
        try:
            iframes = await page.evaluate(
                "() => Array.from(document.querySelectorAll('iframe'))"
                ".map(f => ({ src: f.src, id: f.id, class: f.className }))"
            )
            logger.warning("debug: iframes on page = {}", iframes)
        except Exception as exc:
            logger.warning("debug: could not list iframes: {}", exc)
        try:
            await page.screenshot(path="captcha_debug.png")
            logger.warning("debug: screenshot saved to captcha_debug.png")
        except Exception as exc:
            logger.warning("debug: screenshot failed: {}", exc)

    async def _click_confirm(self, frame: Any) -> None:
        """Click the "确定" confirm button inside the captcha iframe.

        Best-effort: the button may be absent when verification auto-submitted
        after the slide. Logs and continues on failure.
        """
        confirm = frame.locator(self.CONFIRM_BUTTON)
        try:
            await confirm.wait_for(state="visible", timeout=5000)
            await confirm.click()
            logger.info("clicked captcha confirm button")
        except Exception:
            logger.debug("confirm button not present (auto-submitted?)")

    async def _wait_for_captcha_solved(self, *, timeout_ms: int = 120000) -> None:
        """Wait for captcha completion by detecting URL change (non-interactive).

        When stdin is not a TTY, the operator slides the captcha manually in
        the visible browser; this detects success by waiting for the page to
        leave ``/login``.
        """
        page = self.client.page
        try:
            await page.wait_for_function(
                "() => !window.location.pathname.includes('/login')",
                timeout=timeout_ms,
            )
        except Exception:
            logger.warning("captcha completion wait timed out after {}ms", timeout_ms)
