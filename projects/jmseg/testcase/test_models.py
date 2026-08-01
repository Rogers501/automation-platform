"""DTO 与枚举单元测试:字段名恢复、别名往返、必填校验、泛型信封、枚举解析."""

from __future__ import annotations

import pytest
from models.dto import (
    CreateStationQuoteCmdRequest,
    DetailQuery,
    PageStationQuoteQueryRequest,
    Result,
    ResultDetail,
    ResultList,
    ResultPage,
    ResultVoid,
    StationQuoteFormulaCmdRequest,
    StationQuotePageVO,
    UpdateStationQuoteCmdRequest,
    UpsUser,
)
from models.enums import AuditStatus, FeeType, FranchiseeFlag, RoundingMode
from pydantic import ValidationError


def _create_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "quoteName": "报价-单测",
        "feeType": 1,
        "roundingMode": "B01",
        "effectiveStartTime": "2026-01-01 00:00:00",
        "effectiveEndTime": "2026-02-01 00:00:00",
        "loginUserId": 1001,
        "loginNetworkCode": "NET001",
    }
    payload.update(overrides)
    return payload


class TestFieldRecovery:
    """验证 ApiFox 中文前缀字段名已恢复为服务端 camelCase 别名."""

    def test_login_fields_recovered_to_camel_aliases(self) -> None:
        req = CreateStationQuoteCmdRequest.model_validate(_create_payload())
        dumped = req.model_dump(by_alias=True, exclude_none=True)
        assert dumped["loginUserId"] == 1001
        assert dumped["loginNetworkCode"] == "NET001"
        assert "登录loginUserId" not in dumped
        assert "登录网点编码" not in dumped

    def test_request_serializes_with_camelcase_aliases(self) -> None:
        req = CreateStationQuoteCmdRequest.model_validate(
            _create_payload(formulas=[{"startWeight": 0.0, "endWeight": 10.0, "priceFormula": "w"}])
        )
        dumped = req.model_dump(by_alias=True, exclude_none=True)
        assert dumped["effectiveStartTime"] == "2026-01-01 00:00:00"
        assert dumped["formulas"][0]["priceFormula"] == "w"


class TestValidation:
    def test_required_fields_enforced(self) -> None:
        with pytest.raises(ValidationError):
            CreateStationQuoteCmdRequest.model_validate({"quoteName": "x"})

    def test_extra_fields_ignored(self) -> None:
        req = CreateStationQuoteCmdRequest.model_validate(_create_payload(unknownField=99))
        assert req.quote_name == "报价-单测"

    def test_formula_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            StationQuoteFormulaCmdRequest.model_validate({"startWeight": 1.0})

    def test_update_requires_id(self) -> None:
        with pytest.raises(ValidationError):
            UpdateStationQuoteCmdRequest.model_validate(_create_payload())

    def test_update_inherits_create_fields(self) -> None:
        req = UpdateStationQuoteCmdRequest.model_validate(_create_payload(id=7))
        assert req.id == 7
        assert req.quote_name == "报价-单测"


class TestResultEnvelope:
    def test_result_page_round_trip(self) -> None:
        raw = {
            "code": 200,
            "msg": "ok",
            "data": {"records": [{"id": 1, "quoteName": "q"}], "total": 1},
            "traceId": "t1",
            "timestamp": 1700000000,
        }
        result = ResultPage.model_validate(raw)
        assert result.code == 200
        assert result.trace_id == "t1"
        assert result.data is not None
        assert result.data.records[0].quote_name == "q"

    def test_result_void_data_is_null(self) -> None:
        result = ResultVoid.model_validate({"code": 200, "data": None})
        assert result.data is None

    def test_result_list_parses_array_data(self) -> None:
        result = ResultList.model_validate({"code": 200, "data": [{"id": 1}, {"id": 2}]})
        assert result.data is not None
        assert len(result.data) == 2

    def test_result_detail_parses_vo(self) -> None:
        result = ResultDetail.model_validate(
            {"code": 200, "data": {"id": 5, "groups": [{"groupId": 1}], "formulas": []}}
        )
        assert result.data is not None
        assert result.data.groups[0].group_id == 1

    def test_result_parametrization_validates_inner_type(self) -> None:
        # 泛型下标每次生成新类(非同一对象),但都能正确校验内部类型
        page = Result[StationQuotePageVO].model_validate(
            {"code": 200, "data": {"id": 1, "quoteName": "q"}}
        )
        assert page.data is not None
        assert page.data.quote_name == "q"


class TestEnums:
    def test_fee_type_from_code(self) -> None:
        assert FeeType.from_code(1) is FeeType.PICKUP
        assert FeeType.from_code(0) is None
        assert FeeType.from_code(None) is None

    def test_audit_status_from_code(self) -> None:
        assert AuditStatus.from_code(0) is AuditStatus.UNAUDITED
        assert AuditStatus.from_code(1) is AuditStatus.AUDITED
        assert AuditStatus.from_code(None) is None

    def test_franchisee_flag(self) -> None:
        assert FranchiseeFlag.from_code(1) is FranchiseeFlag.YES
        assert FranchiseeFlag.from_code(2) is FranchiseeFlag.NO

    def test_rounding_mode_unknown_falls_back(self) -> None:
        assert RoundingMode.from_code("B01") is RoundingMode.ACTUAL
        assert RoundingMode.from_code("B99") is RoundingMode.UNKNOWN
        assert RoundingMode.from_code(None) is RoundingMode.UNKNOWN


def test_detail_query_model() -> None:
    q = DetailQuery(id=42)
    assert q.model_dump(by_alias=True) == {"id": 42}


def test_page_query_langtype_distinct_from_lang_type() -> None:
    req = PageStationQuoteQueryRequest.model_validate(
        {"langType": "zh_CN", "langtype": "en_US", "current": 1, "size": 10}
    )
    dumped = req.model_dump(by_alias=True, exclude_none=True)
    assert dumped["langType"] == "zh_CN"
    assert dumped["langtype"] == "en_US"


def test_ups_user_aliases() -> None:
    user = UpsUser.model_validate({"staffNo": "S001", "networkId": 9})
    assert user.staff_no == "S001"
    assert user.network_id == 9
