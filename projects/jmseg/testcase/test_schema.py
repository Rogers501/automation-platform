"""JSON Schema 校验测试(基于 Pydantic model_json_schema + framework assert_schema).

jsonschema 未安装时跳过(保持基线全绿);CI 安装 jsonschema 后自动执行。
"""

from __future__ import annotations

import importlib.util

import pytest
from models.dto import ResultDetail, ResultPage

from framework.testing.assertions.base import FrameworkAssertionError
from framework.testing.assertions.schema import assert_schema

_HAS_JSONSCHEMA = importlib.util.find_spec("jsonschema") is not None
_skip = pytest.mark.skipif(not _HAS_JSONSCHEMA, reason="jsonschema 未安装")


@_skip
def test_page_response_matches_schema() -> None:
    schema = ResultPage.model_json_schema()
    data = {
        "code": 200,
        "msg": "ok",
        "data": {"records": [{"id": 1, "quoteName": "q", "feeType": 1}], "total": 1},
        "traceId": "t",
        "timestamp": 1700000000,
    }
    assert_schema(data, schema)


@_skip
def test_detail_response_matches_schema() -> None:
    schema = ResultDetail.model_json_schema()
    data = {
        "code": 200,
        "data": {
            "id": 5,
            "groups": [{"groupId": 1, "groupName": "g"}],
            "formulas": [{"startWeight": 0.0, "endWeight": 10.0, "priceFormula": "w"}],
        },
    }
    assert_schema(data, schema)


@_skip
def test_schema_violation_raises() -> None:
    schema = ResultPage.model_json_schema()
    # code 应为 integer,这里给字符串,校验失败
    with pytest.raises(FrameworkAssertionError):
        assert_schema({"code": "not-an-int", "data": None}, schema)
