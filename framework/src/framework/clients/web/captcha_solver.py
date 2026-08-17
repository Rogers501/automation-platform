"""Tencent slide-puzzle captcha auto-solver (tencent-captcha-dy).

v5: reliable drag via CDP Input.dispatchMouseEvent + template matching.

Key fixes from v4:
    - Drag uses CDP Input.dispatchMouseEvent (not page.mouse) for reliability.
    - Gap detection uses template matching with edge images (more robust).
    - Refresh properly waits for new image to load.
    - Detailed logging at every step for debugging.
"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    pass

__all__ = ["TencentCaptchaSolver"]

_BG_IMG_SEL = ".tencent-captcha-dy__verify-bg-img"
_FG_ITEM_SEL = ".tencent-captcha-dy__fg-item"
_SLIDER_SEL = ".tencent-captcha-dy__slider-block"
_SUCCESS_TEXT = "text=\u529f\u80fd\u5165\u53e3"


class TencentCaptchaSolver:
    """Auto-solver for Tencent slide-puzzle captcha."""

    def __init__(self, page: Any) -> None:
        self._page = page
        self._frame: Any = None
        self._cdp: Any = None

    async def solve(self, *, timeout_ms: int = 10_000, max_retries: int = 5) -> bool:
        if self._page is None:
            return False
        if "/login" not in self._page.url:
            return True

        try:
            import cv2  # noqa: F401
            import numpy as np  # noqa: F401
        except ImportError:
            logger.warning("opencv/numpy not installed; cannot auto-solve")
            return False

        # Get CDP session for reliable mouse events.
        self._cdp = await self._page.context.new_cdp_session(self._page)

        self._frame = await self._find_captcha_frame()
        scope = self._frame if self._frame else self._page
        logger.info("captcha scope: {}", "iframe" if self._frame else "main page")

        try:
            await scope.wait_for_selector(_SLIDER_SEL, timeout=10_000)
        except Exception:
            logger.warning("slider element not found")
            return False

        await asyncio.sleep(1.5)

        for attempt in range(1, max_retries + 1):
            logger.info("=== attempt {}/{} ===", attempt, max_retries)

            gap_x_css = await self._detect_gap_css_x(scope)
            if gap_x_css is None:
                logger.warning("gap detection failed")
                await self._refresh_captcha(scope)
                await asyncio.sleep(2)
                continue

            bg_box = await scope.locator(_BG_IMG_SEL).bounding_box()
            fg_box = await scope.locator(_FG_ITEM_SEL).bounding_box()
            if not bg_box or not fg_box:
                continue

            puzzle_initial_x = fg_box["x"] - bg_box["x"]
            drag_distance = gap_x_css - puzzle_initial_x
            logger.info("gap_css={:.1f}, puzzle_x={:.1f}, drag={:.1f}",
                        gap_x_css, puzzle_initial_x, drag_distance)

            if drag_distance <= 5:
                await self._refresh_captcha(scope)
                await asyncio.sleep(2)
                continue

            moved = await self._cdp_drag(scope, drag_distance)
            if not moved:
                logger.warning("slider did not move; refreshing")
                await self._refresh_captcha(scope)
                await asyncio.sleep(2)
                continue

            await asyncio.sleep(2)
            if await self._wait_for_success(timeout_ms=5000):
                logger.info("CAPTCHA SOLVED on attempt {}", attempt)
                return True

            logger.info("attempt {} drag worked but captcha not passed; refreshing", attempt)
            await self._refresh_captcha(scope)
            await asyncio.sleep(2)

        return await self._wait_for_success(timeout_ms=timeout_ms)

    async def _find_captcha_frame(self) -> Any | None:
        try:
            for f in self._page.frames:
                if f == self._page.main_frame:
                    continue
                try:
                    el = await f.query_selector(_SLIDER_SEL)
                    if el:
                        logger.info("captcha in iframe: {}", f.url[:60])
                        return f
                except Exception:
                    continue
        except Exception:
            pass
        return None

    async def _detect_gap_css_x(self, scope: Any) -> float | None:
        """Detect gap via template matching on edge images."""
        try:
            import cv2
            import numpy as np
        except ImportError:
            return None

        info = await scope.evaluate(
            """(sels) => {
                const bg = document.querySelector(sels[0]);
                const fg = document.querySelector(sels[1]);
                if (!bg || !fg) return null;
                const bgS = getComputedStyle(bg);
                const fgS = getComputedStyle(fg);
                const ex = (s) => (s.match(/url\\(["']?(.+?)["']?\\)/) || [])[1];
                const bp = fgS.backgroundPosition.split(' ').map(parseFloat);
                const bs = fgS.backgroundSize.split(' ').map(parseFloat);
                return {
                    bgUrl: ex(bgS.backgroundImage),
                    fgUrl: ex(fgS.backgroundImage),
                    fgWidth: parseFloat(fgS.width) || 0,
                    fgHeight: parseFloat(fgS.height) || 0,
                    bp: bp, bs: bs
                };
            }""",
            [_BG_IMG_SEL, _FG_ITEM_SEL],
        )
        if not info or not info.get("bgUrl") or not info.get("fgUrl"):
            logger.warning("cannot extract image URLs")
            return None

        bg_bytes = await self._download_image(info["bgUrl"])
        fg_bytes = await self._download_image(info["fgUrl"])
        if not bg_bytes or not fg_bytes:
            return None

        bg_img = cv2.imdecode(np.frombuffer(bg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        fg_img = cv2.imdecode(np.frombuffer(fg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if bg_img is None or fg_img is None:
            return None

        bg_h, bg_w = bg_img.shape[:2]
        logger.info("bg image: {}x{}", bg_w, bg_h)

        # Extract puzzle piece from sprite.
        bp = info["bp"]
        bs = info["bs"]
        sprite_w_px = fg_img.shape[1]
        sprite_h_px = fg_img.shape[0]
        sx = sprite_w_px / bs[0] if bs[0] > 0 else 1.0
        sy = sprite_h_px / bs[1] if bs[1] > 0 else 1.0
        px = int(abs(bp[0]) * sx)
        py = int(abs(bp[1]) * sy)
        pw = int(info["fgWidth"] * sx)
        ph = int(info["fgHeight"] * sy) if info.get("fgHeight") else pw
        x2 = min(px + pw, sprite_w_px)
        y2 = min(py + ph, sprite_h_px)
        puzzle_piece = fg_img[py:y2, px:x2]
        if puzzle_piece.size == 0:
            logger.warning("puzzle piece extraction failed")
            return None
        logger.info("puzzle piece: ({},{}) {}x{}",
                     px, py, puzzle_piece.shape[1], puzzle_piece.shape[0])

        # Match using edge images (more robust than grayscale for captcha).
        bg_gray = cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY)
        piece_gray = cv2.cvtColor(puzzle_piece, cv2.COLOR_BGR2GRAY)
        bg_edges = cv2.Canny(bg_gray, 60, 180)
        piece_edges = cv2.Canny(piece_gray, 60, 180)

        gap_x_img = self._match_template(bg_edges, piece_edges)
        if gap_x_img is None:
            # Fallback: grayscale match.
            gap_x_img = self._match_template(bg_gray, piece_gray)
            if gap_x_img is None:
                # Fallback: edge detection on bg.
                gap_x_img = self._find_gap_edge(bg_img)
                if gap_x_img is None:
                    return None

        # Scale to CSS.
        bg_box = await scope.locator(_BG_IMG_SEL).bounding_box()
        if not bg_box:
            return None
        scale = bg_box["width"] / bg_w
        gap_x_css = gap_x_img * scale
        logger.info("gap_img={:.1f}, scale={:.3f}, gap_css={:.1f}",
                     gap_x_img, scale, gap_x_css)
        return gap_x_css

    @staticmethod
    def _match_template(bg: Any, piece: Any) -> float | None:
        import cv2

        ph, pw = piece.shape[:2]
        bh, bw = bg.shape[:2]
        if pw > bw or ph > bh:
            return None

        result = cv2.matchTemplate(bg, piece, cv2.TM_CCOEFF_NORMED)
        _min_v, max_v, _min_l, max_l = cv2.minMaxLoc(result)
        logger.info("template match: val={:.3f}, loc=({}, {})", max_v, max_l[0], max_l[1])
        if max_v < 0.2:
            return None
        return float(max_l[0])

    @staticmethod
    def _find_gap_edge(img: Any) -> float | None:
        import cv2
        import numpy as np

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 60, 180)
        col_sums = np.sum(edges, axis=0).astype(float)
        threshold = np.mean(col_sums) + 1.5 * np.std(col_sums)
        high_cols = np.where(col_sums > threshold)[0]
        if len(high_cols) < 2:
            return None

        clusters = []
        cur = [high_cols[0]]
        for c in high_cols[1:]:
            if c - cur[-1] <= 5:
                cur.append(c)
            else:
                clusters.append(cur)
                cur = [c]
        clusters.append(cur)

        img_w = img.shape[1]
        for i in range(len(clusters) - 1):
            left = clusters[i][-1]
            right = clusters[i + 1][0]
            gw = right - left
            if 40 < gw < 150 and left > img_w * 0.1:
                return float(left)
        min_x = int(img_w * 0.1)
        for cl in clusters:
            if cl[0] > min_x:
                return float(cl[0])
        return None

    @staticmethod
    async def _download_image(url: str) -> bytes | None:
        try:
            import httpx

            def _fetch():
                with httpx.Client(follow_redirects=True, timeout=15) as c:
                    r = c.get(url)
                    return r.content if r.status_code == 200 else None
            return await asyncio.to_thread(_fetch)
        except Exception as exc:
            logger.warning("download failed: {}", exc)
            return None

    async def _cdp_drag(self, scope: Any, distance: float) -> bool:
        """Drag slider using CDP Input.dispatchMouseEvent (reliable).

        This bypasses page.mouse and sends events directly to the browser
        via CDP, which works even when the window is not focused.
        """
        slider = scope.locator(_SLIDER_SEL)
        box = await slider.bounding_box()
        if not box:
            return False

        start_x = box["x"] + box["width"] / 2
        start_y = box["y"] + box["height"] / 2
        target_x = start_x + distance
        logger.info("cdp drag: start=({:.1f},{:.1f}) target_x={:.1f} dist={:.1f}",
                     start_x, start_y, target_x, distance)

        try:
            # Phase 1: move to slider center, then mouse down.
            await self._cdp_mouse("mouseMoved", start_x, start_y)
            await asyncio.sleep(random.uniform(0.1, 0.2))
            await self._cdp_mouse("mousePressed", start_x, start_y, button="left")
            await asyncio.sleep(random.uniform(0.05, 0.1))

            # Phase 2: drag in steps with ease-in-out.
            n_steps = random.randint(10, 14)
            for i in range(1, n_steps + 1):
                t = i / n_steps
                eased = 4 * t * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 3) / 2
                x = start_x + distance * eased
                y = start_y + random.uniform(-2, 2)
                await self._cdp_mouse("mouseMoved", x, y)
                await asyncio.sleep(random.uniform(0.005, 0.015))

            # Phase 3: overshoot + correction.
            overshoot = random.uniform(3, 7)
            for i in range(random.randint(1, 2)):
                x = start_x + distance + overshoot * (1 - i / 2)
                await self._cdp_mouse("mouseMoved", x, start_y + random.uniform(-1, 1))
                await asyncio.sleep(random.uniform(0.01, 0.02))

            await self._cdp_mouse("mouseMoved", target_x, start_y)
            await asyncio.sleep(random.uniform(0.05, 0.1))
            await self._cdp_mouse("mouseReleased", target_x, start_y, button="left")

            logger.info("cdp drag done: {} steps", n_steps)
        except Exception as exc:
            logger.warning("cdp drag error: {}", exc)
            return False

        # Verify.
        await asyncio.sleep(0.3)
        new_box = await slider.bounding_box()
        if new_box:
            moved = abs(new_box["x"] - box["x"]) > 5
            logger.info("slider moved: {} (old={:.1f} new={:.1f})",
                         moved, box["x"], new_box["x"])
            return moved
        return True

    async def _cdp_mouse(self, etype: str, x: float, y: float, button: str = "none") -> None:
        """Send a single CDP Input.dispatchMouseEvent."""
        await self._cdp.send(
            "Input.dispatchMouseEvent",
            {"type": etype, "x": x, "y": y,
             "button": button,
             "clickCount": 1 if "Pressed" in etype else 0},
        )

    async def _refresh_captcha(self, scope: Any) -> None:
        """Refresh captcha and wait for new image to load."""
        old_url = await scope.evaluate(
            """() => {
                const el = document.querySelector('.tencent-captcha-dy__verify-bg-img');
                if (!el) return '';
                const s = getComputedStyle(el).backgroundImage;
                return (s.match(/url\\(["']?(.+?)["']?\\)/) || [])[1] || '';
            }"""
        )
        try:
            await scope.locator(_BG_IMG_SEL).click(timeout=2000)
            logger.info("clicked refresh")
        except Exception:
            try:
                await scope.click(".tencent-captcha-dy__verify-bg", timeout=2000)
            except Exception:
                logger.warning("refresh click failed")

        # Wait for new image (URL change).
        for _ in range(10):
            await asyncio.sleep(0.5)
            new_url = await scope.evaluate(
                """() => {
                    const el = document.querySelector('.tencent-captcha-dy__verify-bg-img');
                    if (!el) return '';
                    const s = getComputedStyle(el).backgroundImage;
                    return (s.match(/url\\(["']?(.+?)["']?\\)/) || [])[1] || '';
                }"""
            )
            if new_url and new_url != old_url:
                logger.info("new captcha image loaded")
                await asyncio.sleep(0.5)
                return
        logger.warning("refresh did not change image URL")

    async def _wait_for_success(self, *, timeout_ms: int = 5000) -> bool:
        try:
            await self._page.wait_for_selector(_SUCCESS_TEXT, timeout=timeout_ms)
            logger.info("login success detected")
            return True
        except Exception:
            return False
