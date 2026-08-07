"""WebUI login test for jmseu (德国 JMS system).

Data-driven real-browser login test. Test cases are loaded from
``data/{APP_ENV}/login_cases.yaml`` -- test and UAT environments use
separate data files for environment isolation.

Requires:
  - APP_ENV=test or APP_ENV=uat (selects config + data file)
  - data/{APP_ENV}/login_cases.yaml (test case data with credentials)

Allure reporting: each step is wrapped with ``step`` and enriched with
screenshots, URL, and page-title attachments.

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
from framework.reporting.allure import step
from framework.testing.datadriven import case_ids, load_cases

#: Active environment (selects both config YAML and data directory).
_ENV = os.environ.get("APP_ENV", "dev")
#: Data directory per environment: data/test/, data/uat/, etc.
_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / _ENV
#: Cases loaded at collection time for parametrize.
_CASES = load_cases(_DATA_DIR / "login_cases.yaml")


async def _attach_page_state(page: Any, label: str) -> None:
    """Attach current URL, title, and screenshot to the Allure report."""
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
@allure.story(f"数据驱动登录 - {_ENV}环境")
@allure.severity(allure.severity_level.BLOCKER)
@allure.suite("jmseu-login")
@allure.label("owner", "jmseu")
@allure.tag("regression", "real-browser", "data-driven")
@allure.description(
    f"数据驱动登录测试 (环境: {_ENV}). 测试数据从 data/{_ENV}/login_cases.yaml 加载. "
    "每条 case: 打开登录页 -> 接受Cookie(GDPR) -> 切换中文 -> 输入凭据(记住密码) "
    "-> 人工处理滑块验证码 -> 检测「功能入口」判定登录成功。"
)
@pytest.mark.regression
@pytest.mark.parametrize("case", _CASES, ids=case_ids(_CASES))
async def test_login(web_client: WebClient, base_url: str, case: dict[str, Any]) -> None:
    """数据驱动登录: 打开浏览器 -> Cookie -> 切换中文 -> 凭据 -> 人工验证码 -> 检测成功."""
    login_page = LoginPage(web_client, base_url=base_url)
    captcha = TencentSliderCaptcha(web_client)

    with step(f"打开登录页 (case: {case['id']})"):
        await login_page.open()
        await _attach_page_state(web_client.page, "01-登录页加载")

    with step("接受Cookie consent (Alle akzeptieren)"):
        await login_page.accept_cookie_consent()
        await _attach_page_state(web_client.page, "02-Cookie处理后")

    with step("切换中文界面"):
        await login_page.ensure_chinese_language()
        await _attach_page_state(web_client.page, "03-切换中文后")

    with step(f"输入账号密码并提交 (case: {case['id']})"):
        await login_page.login(
            case["username"], case["password"], remember=case.get("remember", False)
        )
        allure.attach(
            case["username"], name="登录账号", attachment_type=allure.attachment_type.TEXT
        )
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
        assert solved, f"未检测到登录成功标志，登录失败 (case: {case['id']})"  # noqa: RUF001

    with step("登录成功 - 截图留存"):
        await login_page.screenshot()
        await _attach_page_state(web_client.page, "06-登录成功")
        allure.attach(
            web_client.page.url if web_client.page else "",
            name="最终URL",
            attachment_type=allure.attachment_type.TEXT,
        )
