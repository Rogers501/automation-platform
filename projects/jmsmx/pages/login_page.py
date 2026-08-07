"""Login page object for the jmsmx (墨西哥 JMS) system.

Encapsulates login-page selectors and the happy-path login flow. Selectors
are based on the real jmsmx UAT environment (Playwright recording). The
login uses a slide-puzzle captcha after form submission; see
:mod:pages.captcha_page for captcha handling.

jmsmx = JMS + MX (墨西哥 JMS 系统). See README.md for naming convention.
"""

from __future__ import annotations

from pages.base_page import BasePage


class LoginPage(BasePage):
    """JMS login page (jmsmx / 墨西哥)."""

    #: Login page relative path.
    path = "/login"

    # --- Selectors (from Playwright recording of real UAT env) ----------
    USERNAME_INPUT = "input[placeholder='请输入员工编号']"
    PASSWORD_INPUT = "input[placeholder='请输密码']"
    LOGIN_BUTTON = "button:has-text('登录')"
    REMEMBER_PWD = ".rp-check"

    # Post-login verification
    WELCOME_TEXT = ".welcome"

    async def ensure_chinese_language(self) -> None:
        """Switch the interface to Chinese if a language selector is present.

        Login form selectors use Chinese placeholders, so the interface must
        be in Chinese for them to match. Uses raw Playwright locators to
        match the recording's selectors.
        """
        page = self.client.page
        if page is None:
            return
        if await page.is_visible("i"):
            await page.locator("i").first.click()
            await page.get_by_text("中文").click()

    async def login(self, username: str, password: str, *, remember: bool = False) -> None:
        """Fill credentials and submit the login form.

        Args:
            username: Login account name (员工编号).
            password: Login password (supply via env/config, rule 10).
            remember: If True, check the remember-password box.
        """
        await self.fill(self.USERNAME_INPUT, username)
        await self.fill(self.PASSWORD_INPUT, password)
        if remember:
            await self.click(self.REMEMBER_PWD)
        await self.click(self.LOGIN_BUTTON)

    async def wait_for_login_success(self, *, timeout_ms: int = 30000) -> None:
        """Wait for successful login (URL changes away from /login).

        Raises ClientError (wrapped Playwright timeout) if login failed.
        """
        await self.wait_for_function(
            "() => !window.location.pathname.includes('/login')",
            timeout_ms=timeout_ms,
        )

    async def welcome_message(self) -> str:
        """The welcome message shown after successful login."""
        return await self.text(self.WELCOME_TEXT)
