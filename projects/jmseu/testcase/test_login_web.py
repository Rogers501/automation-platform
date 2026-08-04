"""WebUI login test for jmseu (German JMS system).

Two test paths:
  1. test_login_normal_scenario -- CI fake-page test (rule 14: no browser).
  2. test_login_real_browser     -- real test-env login with captcha solving.

The real-browser test requires:
  - JMSEU_REAL_BROWSER=1 (launches Playwright)
  - .env: JMSEU_TEST_USERNAME / JMSEU_TEST_PASSWORD
  - APP_ENV=test (uses test environment config)

Allure reporting: each step is wrapped with ``step`` and enriched with
screenshots, URL, and page-title attachments for the real-browser path.
Run with ``--alluredir=<dir>`` to emit results, then ``allure generate``.

jmseu = JMS + EU (德国/欧洲 JMS 系统). See README.md for naming convention.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Any

import allure
import pytest
from pages.captcha_page import TencentSliderCaptcha
from pages.login_page import LoginPage

from framework.clients.web import WebClient
from framework.reporting.allure import attach_text, step
from framework.testing.datadriven import case_ids, load_cases

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_CASES = load_cases(_DATA_DIR / "login_cases.yaml")


async def _attach_page_state(page: Any, label: str) -> None:
    """Attach current URL, title, and screenshot to the Allure report.

    Safe to call with a fake page (attachments are skipped silently when the
    underlying Playwright calls are unavailable).
    """
    if page is None:
        return
    with contextlib.suppress(Exception):
        allure.attach(page.url, name=f"{label} - URL", attachment_type=allure.attachment_type.TEXT)
    with contextlib.suppress(Exception):
        title = await page.title()
        allure.attach(
            title, name=f"{label} - Page Title", attachment_type=allure.attachment_type.TEXT
        )
    with contextlib.suppress(Exception):
        png = await page.screenshot()
        allure.attach(png, name=f"{label} - Screenshot", attachment_type=allure.attachment_type.PNG)


@allure.epic("JMS 系统")
@allure.feature("登录")
@allure.story("正常登录 - CI假页面")
@allure.severity(allure.severity_level.CRITICAL)
@allure.suite("jmseu-login")
@allure.label("owner", "jmseu")
@allure.tag("smoke", "fake-page")
@pytest.mark.smoke
@pytest.mark.parametrize("case", _CASES, ids=case_ids(_CASES))
async def test_login_normal_scenario(
    web_client: WebClient, base_url: str, case: dict[str, Any]
) -> None:
    """正常场景: 有效账号登录 -> 登录成功 -> 显示欢迎信息 (CI假页面)."""
    login_page = LoginPage(web_client, base_url=base_url)

    with step("打开登录页"):
        await login_page.open()

    with step("输入账号密码并提交"):
        await login_page.login(case["username"], case["password"])

    with step("验证登录成功"):
        await login_page.wait_for_login_success()

    with step("验证欢迎信息包含用户名"):
        welcome = await login_page.welcome_message()
        attach_text("welcome message", welcome)
        assert case["expected_welcome_contains"] in welcome, (
            f"欢迎信息应包含 '{case['expected_welcome_contains']}', 实际: {welcome}"
        )

    with step("截图留存"):
        await login_page.screenshot()


@allure.epic("JMS 系统")
@allure.feature("登录")
@allure.story("真实浏览器登录 - test环境")
@allure.severity(allure.severity_level.BLOCKER)
@allure.suite("jmseu-login")
@allure.label("owner", "jmseu")
@allure.tag("regression", "real-browser")
@allure.description(
    "真实test环境登录全流程: 打开登录页 -> 接受Cookie(GDPR) -> 切换中文 -> "
    "输入凭据(记住密码) -> 提交 -> 人工处理腾讯滑块验证码 -> 检测「功能入口」"
    "判定登录成功。每步附带截图/URL/页面标题附件。"
)
@pytest.mark.regression
@pytest.mark.skipif(
    os.environ.get("JMSEU_REAL_BROWSER") != "1",
    reason="需要真实浏览器环境 (JMSEU_REAL_BROWSER=1)",
)
async def test_login_real_browser(web_client: WebClient, base_url: str) -> None:
    """真实test环境登录: 账号密码 -> 人工滑块验证码 -> 检测登录成功."""
    username = os.environ.get("JMSEU_TEST_USERNAME", "")
    password = os.environ.get("JMSEU_TEST_PASSWORD", "")
    assert username, "JMSEU_TEST_USERNAME 未设置 (检查 .env)"
    assert password, "JMSEU_TEST_PASSWORD 未设置 (检查 .env)"

    login_page = LoginPage(web_client, base_url=base_url)
    captcha = TencentSliderCaptcha(web_client)

    with step("打开登录页"):
        await login_page.open()
        await _attach_page_state(web_client.page, "01-登录页加载")

    with step("接受Cookie consent (Alle akzeptieren)"):
        await login_page.accept_cookie_consent()
        await _attach_page_state(web_client.page, "02-Cookie处理后")

    with step("切换中文界面"):
        await login_page.ensure_chinese_language()
        await _attach_page_state(web_client.page, "03-切换中文后")

    with step("输入账号密码并提交 (记住密码)"):
        await login_page.login(username, password, remember=True)
        await _attach_page_state(web_client.page, "04-提交登录后")

    with step("人工处理滑块验证码"):
        allure.attach(
            "操作员在浏览器中手动滑动滑块; 脚本等待「功能入口」文本出现 (120s超时)",
            name="验证码处理说明",
            attachment_type=allure.attachment_type.TEXT,
        )
        solved = await captcha.solve()
        allure.attach(
            "成功" if solved else "失败",
            name="验证码结果",
            attachment_type=allure.attachment_type.TEXT,
        )
        await _attach_page_state(web_client.page, "05-验证码处理后")
        assert solved, "未检测到登录成功标志，登录失败"  # noqa: RUF001

    with step("登录成功 - 截图留存"):
        await login_page.screenshot()
        await _attach_page_state(web_client.page, "06-登录成功")
        allure.attach(
            web_client.page.url if web_client.page else "",
            name="最终URL",
            attachment_type=allure.attachment_type.TEXT,
        )
