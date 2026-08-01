"""yaml 数据驱动测试:新增报价参数化."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from api.station_quote import StationQuoteClient
from factories import make_create_request

from framework.testing.assertions.response import assert_ok
from framework.testing.datadriven import case_ids, load_cases

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_CASES = load_cases(_DATA_DIR / "station_quote_cases.yaml")


@pytest.mark.regression
@pytest.mark.parametrize("case", _CASES, ids=case_ids(_CASES))
async def test_save_data_driven(api_client: StationQuoteClient, case: dict[str, Any]) -> None:
    """每个 yaml 用例构造新增请求并校验响应信封 code=200."""
    overrides = {k: v for k, v in case.items() if k != "name"}
    resp = await api_client.save(make_create_request(**overrides))
    assert_ok(resp)
    assert StationQuoteClient.parse_void(resp).code == 200
