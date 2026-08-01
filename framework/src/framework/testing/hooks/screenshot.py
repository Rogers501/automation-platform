"""Screenshot provider interface (extension point for Web/App automation).

Defines the abstract :class:`ScreenshotProvider` and a no-op
:class:`NullScreenshotProvider` default. The hooks layer calls the provider on
test failure; with the default active, capture is a no-op so API-only phases
incur no Web/App dependency.

Concrete implementations:
    - PlaywrightScreenshotProvider (``framework.clients.web.screenshot``)
      for Web automation.
    - AppClient screenshot support (``framework.clients.app.client``)
      for App automation.

Override the ``screenshot_provider`` fixture in a system conftest to enable
capture for the active driver.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

__all__ = ["NullScreenshotProvider", "ScreenshotProvider"]


class ScreenshotProvider(ABC):
    """Abstract screenshot capture interface for Web/App automation."""

    @abstractmethod
    def screenshot(self, name: str) -> Path | None:
        """Capture a screenshot named ``name``; return its path or ``None``.

        Implementations (Playwright, Appium) manage their own async/event-loop
        details. Returning ``None`` signals that no screenshot was captured
        (e.g. no driver available).
        """


class NullScreenshotProvider(ScreenshotProvider):
    """No-op provider used when no Web/App driver is available."""

    def screenshot(self, name: str) -> Path | None:
        return None
