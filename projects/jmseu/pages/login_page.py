"""Login page object for the jmseu (German JMS) system.

Encapsulates login-page selectors and the happy-path login flow. Selectors
are based on the real jmseu test environment (Playwright recording). The
login uses a Tencent slider captcha after form submission; see
:mod:`pages.captcha_page` for captcha handling.

jmseu = JMS + EU (德国/欧洲 JMS 系统). See README.md for naming convention.
"""

from __future__ import annotations

from pages.base_page import BasePage


class LoginPage(BasePage):
    """JMS login page (jmseu / Germany)."""

    #: Login page relative path.
    path = "/login"

    # --- Selectors (from Playwright recording of real test env) ---------
    USERNAME_INPUT = "input[placeholder='请输入员工编号']"
    PASSWORD_INPUT = "input[placeholder='请输密码']"
    LOGIN_BUTTON = "button:has-text('登录')"
    REMEMBER_PWD = ".lm-bottom-box > .remember-pwd > .rp-check"

    # Cookie consent (EU GDPR banner, may not always appear)
    COOKIE_ACCEPT = "text=Alle akzeptieren"

    # Post-login verification
    WELCOME_TEXT = ".welcome"

    async def accept_cookie_consent(self) -> None:
        """Accept the cookie consent banner if present (EU GDPR).

        The banner is Vue-rendered and may take a moment to appear after
        DOMContentLoaded. Waits up to 5s for it, clicks accept, then waits
        for it to disappear before continuing. Safe to call unconditionally
        -- skips silently if the banner is absent.
        """
        page = self.client.page
        if page is None:
            return
        try:
            await page.wait_for_selector(self.COOKIE_ACCEPT, timeout=5000)
            await page.click(self.COOKIE_ACCEPT)
            await page.wait_for_selector(self.COOKIE_ACCEPT, state="hidden", timeout=5000)
        except Exception:
            pass  # banner not present or already dismissed

    async def ensure_chinese_language(self) -> None:
        """Switch the interface to Chinese if a language selector is present.

        Login form selectors use Chinese placeholders, so the interface must
        be in Chinese for them to match. Uses raw Playwright locators to
        match the recording's role-based selectors.
        """
        page = self.client.page
        if page is None:
            return
        # The language icon is the first <i> element in the cookie banner.
        if await page.is_visible("i"):
            await page.locator("i").first.click()
            await page.get_by_role("list").get_by_text("中文").click()

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
