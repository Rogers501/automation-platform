"""Unit tests for framework.testing.hooks.screenshot."""

from __future__ import annotations

from pathlib import Path

import pytest

from framework.testing.hooks.screenshot import NullScreenshotProvider, ScreenshotProvider


def test_screenshot_provider_is_abstract() -> None:
    """ScreenshotProvider cannot be instantiated directly."""
    with pytest.raises(TypeError):
        ScreenshotProvider()  # type: ignore[abstract]


def test_null_provider_returns_none() -> None:
    """NullScreenshotProvider.screenshot returns None (no-op)."""
    assert NullScreenshotProvider().screenshot("test") is None


def test_null_provider_is_screenshot_provider() -> None:
    """NullScreenshotProvider is a ScreenshotProvider subclass."""
    assert isinstance(NullScreenshotProvider(), ScreenshotProvider)


def test_custom_provider_returns_path() -> None:
    """A custom provider can return a path and is invoked with the name."""

    class FakeProvider(ScreenshotProvider):
        def __init__(self) -> None:
            self.called: list[str] = []

        def screenshot(self, name: str) -> Path | None:
            self.called.append(name)
            return Path("/tmp") / f"{name}.png"

    provider = FakeProvider()
    result = provider.screenshot("fail_test")
    assert result == Path("/tmp/fail_test.png")
    assert provider.called == ["fail_test"]
