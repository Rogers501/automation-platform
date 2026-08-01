"""jmseg token / 用户上下文 fixtures.

jmseg 规格无登录端点,token 由环境变量外置(rule 10):``APP_JMSEG_TOKEN``。
未设置时使用测试占位 token;真实环境通过 CI 变量或 .env 注入。
"""

from __future__ import annotations

import os

import pytest

__all__ = ["token", "ups_user"]


@pytest.fixture
def token() -> str:
    """从 ``APP_JMSEG_TOKEN`` 读取 token(默认测试占位)."""
    return os.environ.get("APP_JMSEG_TOKEN", "test-token-jmseg")


@pytest.fixture
def ups_user() -> str:
    """X-UPS-USER 头取值(默认测试占位)."""
    return os.environ.get("APP_JMSEG_UPS_USER", "auto-tester")
