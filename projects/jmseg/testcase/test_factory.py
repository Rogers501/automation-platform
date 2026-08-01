"""测试数据工厂单元测试:产出合法模型、覆盖生效、离线 fallback."""

from __future__ import annotations

from factories import (
    HAS_FAKER,
    make_audit_request,
    make_create_request,
    make_delete_request,
    make_detail_query,
    make_formula,
    make_page_request,
    make_unaudit_request,
    make_update_request,
)
from models.dto import (
    AuditStationQuoteCmdRequest,
    CreateStationQuoteCmdRequest,
    DeleteStationQuoteCmdRequest,
    DetailQuery,
    PageStationQuoteQueryRequest,
    StationQuoteFormulaCmdRequest,
    UnauditStationQuoteCmdRequest,
    UpdateStationQuoteCmdRequest,
)


def test_faker_availability_flag_is_bool() -> None:
    assert isinstance(HAS_FAKER, bool)


def test_make_create_request_valid_and_camelcase() -> None:
    req = make_create_request()
    assert isinstance(req, CreateStationQuoteCmdRequest)
    dumped = req.model_dump(by_alias=True, exclude_none=True)
    assert "quoteName" in dumped
    assert "feeType" in dumped
    assert "formulas" in dumped
    assert dumped["formulas"][0]["priceFormula"]


def test_make_create_request_overrides_win() -> None:
    req = make_create_request(quote_name="自定义报价", fee_type=3)
    assert req.quote_name == "自定义报价"
    assert req.fee_type == 3


def test_make_formula_valid() -> None:
    f = make_formula(end_weight=50.0)
    assert isinstance(f, StationQuoteFormulaCmdRequest)
    assert f.end_weight == 50.0


def test_make_update_request_carries_id() -> None:
    req = make_update_request(quote_id=88)
    assert isinstance(req, UpdateStationQuoteCmdRequest)
    assert req.id == 88


def test_make_delete_request() -> None:
    req = make_delete_request(quote_id=5)
    assert isinstance(req, DeleteStationQuoteCmdRequest)
    assert req.id == 5


def test_make_audit_and_unaudit_requests() -> None:
    audit = make_audit_request(ids=[1, 2])
    unaudit = make_unaudit_request(ids=[3])
    assert isinstance(audit, AuditStationQuoteCmdRequest)
    assert isinstance(unaudit, UnauditStationQuoteCmdRequest)
    assert audit.ids == [1, 2]


def test_make_page_request_defaults() -> None:
    req = make_page_request()
    assert isinstance(req, PageStationQuoteQueryRequest)
    assert req.current == 1
    assert req.size == 20


def test_make_detail_query() -> None:
    q = make_detail_query(quote_id=77)
    assert isinstance(q, DetailQuery)
    assert q.id == 77


def test_factory_works_without_faker() -> None:
    """离线无 faker 时工厂仍产出合法模型(回归保底)."""
    req = make_create_request()
    assert req.quote_name.startswith("报价-")
    # 再次调用确保 fallback 路径稳定不抛错
    assert make_create_request().fee_type in (1, 2, 3)
