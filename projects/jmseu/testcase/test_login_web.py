"""WebUI login test for jmseu (German JMS system).

Two test paths:
  1. test_login_normal_scenario -- CI fake-page test (rule 14: no browser).
  2. test_login_real_browser     -- real test-env login with captcha solving.

The real-browser test requires:
  - JMSEU_REAL_BROWSER=1 (launches Playwright)
  - .env: JMSEU_TEST_USERNAME / JMSEU_TEST_PASSWORD
  - APP_ENV=test (uses test environment config)

jmseu = JMS + EU (德国/欧洲 JMS 系统). See README.md for naming convention.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from pages.captcha_page import TencentSliderCaptcha
from pages.login_page import LoginPage

from framework.clients.web import WebClient
from framework.reporting.allure import step
from framework.testing.datadriven import case_ids, load_cases

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_CASES = load_cases(_DATA_DIR / "login_cases.yaml")


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
        assert case["expected_welcome_contains"] in welcome, (
            f"欢迎信息应包含 '{case['expected_welcome_contains']}', 实际: {welcome}"
        )

    with step("截图留存"):
        await login_page.screenshot()


@pytest.mark.regression
@pytest.mark.skipif(
    os.environ.get("JMSEU_REAL_BROWSER") != "1",
    reason="需要真实浏览器环境 (JMSEU_REAL_BROWSER=1)",
)
async def test_login_real_browser(web_client: WebClient, base_url: str) -> None:
    """真实test环境登录: 账号密码 -> 滑块验证码 -> 登录成功."""
    username = os.environ.get("JMSEU_TEST_USERNAME", "")
    password = os.environ.get("JMSEU_TEST_PASSWORD", "")
    assert username, "JMSEU_TEST_USERNAME 未设置 (检查 .env)"
    assert password, "JMSEU_TEST_PASSWORD 未设置 (检查 .env)"

    login_page = LoginPage(web_client, base_url=base_url)
    captcha = TencentSliderCaptcha(web_client)

    with step("打开登录页"):
        await login_page.open()

    with step("接受Cookie consent"):
        await login_page.accept_cookie_consent()

    with step("切换中文界面"):
        await login_page.ensure_chinese_language()

    with step("输入账号密码并提交"):
        await login_page.login(username, password)

    with step("处理滑块验证码"):
        solved = await captcha.solve()
        assert solved, "滑块验证码处理失败 (iframe 未出现或已跳过)"

    with step("验证登录成功"):
        await login_page.wait_for_login_success()

    with step("截图留存"):
        await login_page.screenshot()
