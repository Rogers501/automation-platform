"""Allure 报告集成测试(未安装 allure-pytest 时全部 no-op,用例仍绿色).

test_context 在 teardown 会自动把本次录制的 HTTP 交换作为附件
(由 framework.testing.hooks 触发);此处补充显式步骤与附件演示。
"""

from __future__ import annotations

import pytest
from api.station_quote import StationQuoteClient
from factories import make_create_request, make_page_request

from framework.reporting.allure import attach_json, is_allure_available, step


@pytest.mark.regression
async def test_allure_step_and_attach(api_client: StationQuoteClient) -> None:
    """显式 Allure 步骤 + 附件(无 allure 时 no-op,不报错)."""
    with step("新增驿站报价"):
        resp = await api_client.save(make_create_request())
        attach_json("save-response", resp.json)

    with step("分页查询并校验"):
        page_resp = await api_client.page(make_page_request())
        result = StationQuoteClient.parse_page(page_resp)
        attach_json("page-response", page_resp.json)
        assert result.data is not None
        assert result.data.total == 1

    # 无 allure 环境下 is_allure_available() 为 False,但全程不抛错
    assert isinstance(is_allure_available(), bool)
