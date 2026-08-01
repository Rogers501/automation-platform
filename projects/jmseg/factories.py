"""测试数据工厂(Faker 优先,离线 fallback 保底).

faker 未安装时回退到纯 Python 生成器(确定性随机),保证测试在无网络/无 faker
环境下依然全绿(与 framework 懒加载可选依赖的理念一致)。所有工厂接受
``**overrides`` 覆盖任意字段,并通过 Pydantic 校验确保产出合法。
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta

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

__all__ = [
    "HAS_FAKER",
    "make_audit_request",
    "make_create_request",
    "make_delete_request",
    "make_detail_query",
    "make_formula",
    "make_page_request",
    "make_unaudit_request",
    "make_update_request",
]

try:
    from faker import Faker

    _FK = Faker("zh_CN")
    Faker.seed(0)
    HAS_FAKER = True
except ImportError:
    _FK = None
    HAS_FAKER = False

_RNG = random.Random(20260722)


def _now_iso() -> str:
    """当前时间(yyyy-MM-dd HH:mm:ss)."""
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _future_iso(days: int = 30) -> str:
    """未来时间(默认 +30 天)."""
    return (datetime.now(UTC) + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def _quote_name() -> str:
    """唯一报价名称."""
    suffix = _FK.uuid4()[:8] if HAS_FAKER else uuid.uuid4().hex[:8]
    return f"报价-{suffix}"


def _fee_type() -> int:
    """随机费用类型(取件/派件/仓储)."""
    return _RNG.choice([1, 2, 3])


def _login_context() -> dict[str, object]:
    """登录上下文默认值."""
    return {
        "login_user_id": 1001,
        "login_user_name": "auto-tester",
        "login_user_code": "AUTO001",
        "login_network_id": 200,
        "login_network_code": "NET001",
        "login_network_name": "自动化测试网点",
        "login_institutional_level_id": 1,
        "is_financial_center": 2,
        "is_first_franchisee": 2,
        "is_second_franchisee": 2,
        "lang_type": "zh_CN",
    }


def make_formula(**overrides: object) -> StationQuoteFormulaCmdRequest:
    """生成价格公式请求(默认 0~100kg,公式 weight*1.0)."""
    data: dict[str, object] = {
        "start_weight": 0.0,
        "end_weight": 100.0,
        "price_formula": "weight*1.0",
        "price": 10.0,
    }
    data.update(overrides)
    return StationQuoteFormulaCmdRequest.model_validate(data)


def make_create_request(**overrides: object) -> CreateStationQuoteCmdRequest:
    """生成新增报价请求(必填字段齐全,附一条公式)."""
    data: dict[str, object] = {
        **_login_context(),
        "quote_name": _quote_name(),
        "fee_type": _fee_type(),
        "rounding_mode": "B01",
        "effective_start_time": _now_iso(),
        "effective_end_time": _future_iso(),
        "outbound_type": 1,
        "abnormal_outbound_days": 0,
        "group_ids": [],
        "formulas": [make_formula()],
    }
    data.update(overrides)
    return CreateStationQuoteCmdRequest.model_validate(data)


def make_update_request(quote_id: int, **overrides: object) -> UpdateStationQuoteCmdRequest:
    """生成修改报价请求(在新增基础上追加必填 id)."""
    data: dict[str, object] = {
        **_login_context(),
        "quote_name": _quote_name(),
        "fee_type": _fee_type(),
        "rounding_mode": "B01",
        "effective_start_time": _now_iso(),
        "effective_end_time": _future_iso(),
        "outbound_type": 1,
        "abnormal_outbound_days": 0,
        "group_ids": [],
        "formulas": [make_formula()],
        "id": quote_id,
    }
    data.update(overrides)
    return UpdateStationQuoteCmdRequest.model_validate(data)


def make_delete_request(quote_id: int, **overrides: object) -> DeleteStationQuoteCmdRequest:
    """生成删除报价请求."""
    data: dict[str, object] = {**_login_context(), "id": quote_id}
    data.update(overrides)
    return DeleteStationQuoteCmdRequest.model_validate(data)


def make_audit_request(ids: list[int], **overrides: object) -> AuditStationQuoteCmdRequest:
    """生成审核报价请求."""
    data: dict[str, object] = {**_login_context(), "ids": ids}
    data.update(overrides)
    return AuditStationQuoteCmdRequest.model_validate(data)


def make_unaudit_request(ids: list[int], **overrides: object) -> UnauditStationQuoteCmdRequest:
    """生成反审核报价请求."""
    data: dict[str, object] = {**_login_context(), "ids": ids}
    data.update(overrides)
    return UnauditStationQuoteCmdRequest.model_validate(data)


def make_page_request(**overrides: object) -> PageStationQuoteQueryRequest:
    """生成分页查询请求(默认第 1 页,每页 20 条)."""
    data: dict[str, object] = {**_login_context(), "current": 1, "size": 20}
    data.update(overrides)
    return PageStationQuoteQueryRequest.model_validate(data)


def make_detail_query(quote_id: int) -> DetailQuery:
    """生成详情查询参数."""
    return DetailQuery(id=quote_id)
