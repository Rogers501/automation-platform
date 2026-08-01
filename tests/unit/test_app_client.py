"""Unit tests for AppClient using a fake Appium driver (rule 14)."""

from __future__ import annotations

import pytest

from framework.clients.app import AppClient
from framework.core.config import AppSettings
from framework.core.exceptions import ClientError

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeElement:
    """Fake Selenium/Appium WebElement."""

    def __init__(self, text: str = "fake-text") -> None:
        self.text = text
        self.clicked = False
        self.typed: list[str] = []
        self._attributes: dict[str, str] = {}

    def click(self) -> None:
        self.clicked = True

    def send_keys(self, text: str) -> None:
        self.typed.append(text)

    def get_attribute(self, name: str) -> str | None:
        return self._attributes.get(name, f"attr-{name}")


class _FakeDriver:
    """Fake Appium WebDriver."""

    def __init__(self) -> None:
        self.elements: dict[str, _FakeElement] = {}
        self.screenshot_count = 0
        self.screenshot_bytes = b"fake-png"
        self.implicit_wait_set: float | None = None
        self._quit = False

    def find_element(self, by: str, value: str) -> _FakeElement:
        key = f"{by}={value}"
        if key not in self.elements:
            self.elements[key] = _FakeElement()
        return self.elements[key]

    def get_screenshot_as_png(self) -> bytes:
        self.screenshot_count += 1
        return self.screenshot_bytes

    def implicitly_wait(self, seconds: float) -> None:
        self.implicit_wait_set = seconds

    def quit(self) -> None:
        self._quit = True


def _client(driver: _FakeDriver | None = None) -> AppClient:
    """Build an AppClient wired to a fake driver."""
    return AppClient(settings=AppSettings(), driver=driver)


# ---------------------------------------------------------------------------
# Interaction
# ---------------------------------------------------------------------------


async def test_click() -> None:
    """click finds and clicks the element."""
    driver = _FakeDriver()
    client = _client(driver=driver)

    await client.click("id=submit")

    el = driver.elements["id=submit"]
    assert el.clicked


async def test_send_keys() -> None:
    """send_keys types text into the element."""
    driver = _FakeDriver()
    client = _client(driver=driver)

    await client.send_keys("id=username", "alice")

    el = driver.elements["id=username"]
    assert el.typed == ["alice"]


async def test_text() -> None:
    """text returns the element's text."""
    driver = _FakeDriver()
    driver.elements["id=welcome"] = _FakeElement(text="Hello Alice")
    client = _client(driver=driver)

    result = await client.text("id=welcome")

    assert result == "Hello Alice"


async def test_get_attribute() -> None:
    """get_attribute returns the attribute value."""
    driver = _FakeDriver()
    client = _client(driver=driver)

    result = await client.get_attribute("id=link", "href")

    assert result == "attr-href"


async def test_click_xpath_locator() -> None:
    """click supports xpath locator prefix."""
    driver = _FakeDriver()
    client = _client(driver=driver)

    await client.click("xpath=//button[@id='login']")

    assert "xpath=//button[@id='login']" in driver.elements


async def test_click_accessibility_id_locator() -> None:
    """click supports accessibility_id locator prefix."""
    driver = _FakeDriver()
    client = _client(driver=driver)

    await client.click("accessibility_id=login_button")

    assert "accessibility id=login_button" in driver.elements


# ---------------------------------------------------------------------------
# Screenshots
# ---------------------------------------------------------------------------


async def test_screenshot_returns_bytes() -> None:
    """screenshot returns image bytes."""
    driver = _FakeDriver()
    client = _client(driver=driver)

    result = await client.screenshot()

    assert result == b"fake-png"
    assert driver.screenshot_count == 1


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


async def test_click_error_wrapped() -> None:
    """An Appium error surfaces as ClientError."""

    class _ErrorDriver(_FakeDriver):
        def find_element(self, by: str, value: str) -> _FakeElement:
            raise RuntimeError("element not found")

    client = _client(driver=_ErrorDriver())

    with pytest.raises(ClientError) as info:
        await client.click("id=missing")

    assert "element not found" in str(info.value)
    assert info.value.context["op"] == "click"


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


async def test_close() -> None:
    """close marks the client as closed."""
    driver = _FakeDriver()
    client = _client(driver=driver)
    await client.click("id=btn")
    await client.close()

    assert client.is_closed
    assert driver._quit


async def test_async_context_manager() -> None:
    """async with closes the client."""
    driver = _FakeDriver()
    async with _client(driver=driver) as client:
        await client.click("id=btn")
    assert client.is_closed
    assert driver._quit


async def test_operations_after_close_raise() -> None:
    """Operations on a closed client raise ClientError."""
    driver = _FakeDriver()
    client = _client(driver=driver)
    await client.close()

    with pytest.raises(ClientError):
        await client.click("id=btn")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_app_settings_defaults() -> None:
    """AppSettings has sensible defaults."""
    settings = AppSettings()
    assert settings.server_url == "http://localhost:4723"
    assert settings.platform_name == "Android"
    assert settings.automation_name == "UiAutomator2"
    assert settings.no_reset is True
    assert settings.new_command_timeout == 300


def test_app_settings_ios() -> None:
    """AppSettings accepts iOS platform."""
    settings = AppSettings(platform_name="iOS", automation_name="XCUITest")
    assert settings.platform_name == "iOS"
    assert settings.automation_name == "XCUITest"


# ---------------------------------------------------------------------------
# _parse_locator
# ---------------------------------------------------------------------------


def test_parse_locator_id() -> None:
    """_parse_locator handles id= prefix."""
    by, value = AppClient._parse_locator("id=submit")
    assert by == "id"
    assert value == "submit"


def test_parse_locator_xpath() -> None:
    """_parse_locator handles xpath= prefix."""
    by, value = AppClient._parse_locator("xpath=//button")
    assert by == "xpath"
    assert value == "//button"


def test_parse_locator_no_prefix() -> None:
    """_parse_locator defaults to id when no prefix."""
    by, value = AppClient._parse_locator("plain")
    assert by == "id"
    assert value == "plain"


def test_parse_locator_accessibility_id() -> None:
    """_parse_locator handles accessibility_id= prefix."""
    by, value = AppClient._parse_locator("accessibility_id=btn")
    assert by == "accessibility id"
    assert value == "btn"
