"""jmseg 驿站报价 DTO(Pydantic v2).

设计要点:
- 字段名恢复:ApiFox 导出将部分请求字段名污染为中文前缀(如 ``登录loginUserId``),
  其真实服务端字段名记录在 description 第二行;此处统一恢复为 camelCase 别名,
  Python 字段使用 snake_case,序列化时按别名输出(``by_alias=True``)。
- 去重:登录上下文字段抽为 :class:`LoginContext`;VO 公共字段抽为
  :class:`StationQuoteBaseVO`;5 个 ``Result*`` 信封合并为泛型 :class:`Result[T]`。
- 全部字段默认可空(响应模型),请求模型仅对规格中 ``required`` 字段设为必填。
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AuditStationQuoteCmdRequest",
    "CreateStationQuoteCmdRequest",
    "DeleteStationQuoteCmdRequest",
    "DetailQuery",
    "FormulaInfo",
    "GroupInfo",
    "LoginContext",
    "PageStationQuotePageVO",
    "PageStationQuoteQueryRequest",
    "Result",
    "ResultDetail",
    "ResultList",
    "ResultPage",
    "ResultVoid",
    "StationQuoteBaseVO",
    "StationQuoteDetailVO",
    "StationQuoteFormulaCmdRequest",
    "StationQuotePageVO",
    "UnauditStationQuoteCmdRequest",
    "UpdateStationQuoteCmdRequest",
    "UpsUser",
]

#: 共享模型配置:接受别名输入、忽略未知字段。
_MODEL_CONFIG = ConfigDict(populate_by_name=True, extra="ignore")

T = TypeVar("T")


class LoginContext(BaseModel):
    """登录上下文(各请求公共字段,去重基类)."""

    model_config = _MODEL_CONFIG

    login_user_id: int | None = Field(None, alias="loginUserId")
    login_user_name: str | None = Field(None, alias="loginUserName")
    login_user_code: str | None = Field(None, alias="loginUserCode")
    login_network_id: int | None = Field(None, alias="loginNetworkId")
    login_network_code: str | None = Field(None, alias="loginNetworkCode")
    login_network_name: str | None = Field(None, alias="loginNetworkName")
    login_institutional_level_id: int | None = Field(None, alias="loginInstitutionalLevelId")
    is_financial_center: int | None = Field(None, alias="isFinancialCenter")
    is_first_franchisee: int | None = Field(None, alias="isFirstFranchisee")
    is_second_franchisee: int | None = Field(None, alias="isSecondFranchisee")
    lang_type: str | None = Field(None, alias="langType")


class StationQuoteFormulaCmdRequest(BaseModel):
    """报价重量区间价格公式(请求)."""

    model_config = _MODEL_CONFIG

    start_weight: float = Field(..., alias="startWeight")
    end_weight: float = Field(..., alias="endWeight")
    price_formula: str = Field(..., alias="priceFormula")
    price: float | None = Field(None, alias="price")


class UpsUser(BaseModel):
    """用户信息(分页查询上下文)."""

    model_config = _MODEL_CONFIG

    uuid: str | None = None
    id: int | None = None
    name: str | None = None
    staff_no: str | None = Field(None, alias="staffNo")
    network_id: int | None = Field(None, alias="networkId")
    network_name: str | None = Field(None, alias="networkName")
    network_code: str | None = Field(None, alias="networkCode")
    user_type: int | None = Field(None, alias="userType")
    institutional_level_id: int | None = Field(None, alias="institutionalLevelId")
    institutional_level_desc: str | None = Field(None, alias="institutionalLevelDesc")
    financial_center_id: int | None = Field(None, alias="financialCenterId")
    is_financial_center: int | None = Field(None, alias="isFinancialCenter")
    login_time: str | None = Field(None, alias="loginTime")
    is_distribution_center: int | None = Field(None, alias="isDistributionCenter")
    is_first_franchisee: int | None = Field(None, alias="isFirstFranchisee")
    is_second_franchisee: int | None = Field(None, alias="isSecondFranchisee")


class CreateStationQuoteCmdRequest(LoginContext):
    """新增驿站报价(请求)."""

    quote_name: str = Field(..., alias="quoteName", max_length=50)
    fee_type: int = Field(..., alias="feeType")
    rounding_mode: str = Field(..., alias="roundingMode")
    effective_start_time: str = Field(..., alias="effectiveStartTime")
    effective_end_time: str = Field(..., alias="effectiveEndTime")
    outbound_type: int | None = Field(None, alias="outboundType")
    abnormal_outbound_days: int | None = Field(None, alias="abnormalOutboundDays")
    group_ids: list[int] | None = Field(None, alias="groupIds")
    formulas: list[StationQuoteFormulaCmdRequest] | None = Field(None, alias="formulas")


class UpdateStationQuoteCmdRequest(CreateStationQuoteCmdRequest):
    """修改驿站报价(请求,在新增基础上增加必填 ``id``)."""

    id: int = Field(..., alias="id")


class DeleteStationQuoteCmdRequest(LoginContext):
    """删除驿站报价(请求)."""

    id: int = Field(..., alias="id")


class AuditStationQuoteCmdRequest(LoginContext):
    """审核驿站报价(请求,待审核 id 列表)."""

    ids: list[int] = Field(..., alias="ids")


class UnauditStationQuoteCmdRequest(LoginContext):
    """反审核驿站报价(请求,待反审核 id 列表)."""

    ids: list[int] = Field(..., alias="ids")


class PageStationQuoteQueryRequest(LoginContext):
    """分页查询驿站报价(请求)."""

    current: int | None = None
    size: int | None = None
    id: str | None = Field(None, alias="id", description="上一份ID")
    export_type: int | None = Field(None, alias="exportType")
    user: UpsUser | None = None
    langtype: str | None = Field(None, alias="langtype", description="语言类型(小写)")
    quote_name: str | None = Field(None, alias="quoteName")
    group_name: str | None = Field(None, alias="groupName")
    station_keyword: str | None = Field(None, alias="stationKeyword")
    fee_type: int | None = Field(None, alias="feeType")
    audit_status: int | None = Field(None, alias="auditStatus")
    effective_time: str | None = Field(None, alias="effectiveTime")


class StationQuoteBaseVO(BaseModel):
    """驿站报价 VO 公共字段(去重基类)."""

    model_config = _MODEL_CONFIG

    id: int | None = None
    quote_name: str | None = Field(None, alias="quoteName")
    fee_type: int | None = Field(None, alias="feeType")
    rounding_mode: str | None = Field(None, alias="roundingMode")
    network_id: int | None = Field(None, alias="networkId")
    network_code: str | None = Field(None, alias="networkCode")
    network_name: str | None = Field(None, alias="networkName")
    effective_start_time: str | None = Field(None, alias="effectiveStartTime")
    effective_end_time: str | None = Field(None, alias="effectiveEndTime")
    outbound_type: int | None = Field(None, alias="outboundType")
    abnormal_outbound_days: int | None = Field(None, alias="abnormalOutboundDays")
    audit_status: int | None = Field(None, alias="auditStatus")
    audit_by: int | None = Field(None, alias="auditBy")
    audit_by_name: str | None = Field(None, alias="auditByName")
    audit_network_id: int | None = Field(None, alias="auditNetworkId")
    audit_network_name: str | None = Field(None, alias="auditNetworkName")
    audit_time: str | None = Field(None, alias="auditTime")
    create_by: int | None = Field(None, alias="createBy")
    create_by_name: str | None = Field(None, alias="createByName")
    create_time: str | None = Field(None, alias="createTime")
    update_by: int | None = Field(None, alias="updateBy")
    update_by_name: str | None = Field(None, alias="updateByName")
    update_time: str | None = Field(None, alias="updateTime")


class StationQuotePageVO(StationQuoteBaseVO):
    """分页查询返回的报价记录(含分组名称拼接串)."""

    group_names: str | None = Field(None, alias="groupNames")


class GroupInfo(BaseModel):
    """报价绑定的驿站分组(详情)."""

    model_config = _MODEL_CONFIG

    group_id: int | None = Field(None, alias="groupId")
    group_name: str | None = Field(None, alias="groupName")
    network_id: int | None = Field(None, alias="networkId")
    network_code: str | None = Field(None, alias="networkCode")
    network_name: str | None = Field(None, alias="networkName")


class FormulaInfo(BaseModel):
    """报价重量区间价格公式(详情)."""

    model_config = _MODEL_CONFIG

    id: int | None = None
    start_weight: float | None = Field(None, alias="startWeight")
    end_weight: float | None = Field(None, alias="endWeight")
    price_formula: str | None = Field(None, alias="priceFormula")
    price: float | None = None


class StationQuoteDetailVO(StationQuoteBaseVO):
    """报价详情(含分组列表与公式列表)."""

    groups: list[GroupInfo] | None = None
    formulas: list[FormulaInfo] | None = None


class PageStationQuotePageVO(BaseModel):
    """分页结果包装(MyBatis-Plus 风格)."""

    model_config = _MODEL_CONFIG

    records: list[StationQuotePageVO] | None = None
    current: int | None = None
    size: int | None = None
    total: int | None = None
    ascs: list[str] | None = None
    descs: list[str] | None = None
    search_count: bool | None = Field(None, alias="searchCount")
    max_id: Any | None = Field(None, alias="maxId")
    max_limit: int | None = Field(None, alias="maxLimit")


class DetailQuery(BaseModel):
    """详情查询参数(``GET /station-quote/detail`` 的 query)."""

    model_config = _MODEL_CONFIG

    id: int


class Result(BaseModel, Generic[T]):  # noqa: UP046  (PEP 695 与 Generic[T] 等价,保留经典写法)
    """统一响应信封(泛型,替代 5 个重复 ``Result*`` schema)."""

    model_config = _MODEL_CONFIG

    code: int
    msg: str | None = None
    data: T | None = None
    trace_id: str | None = Field(None, alias="traceId")
    timestamp: int | None = None


#: ``Result[None]`` —— 无数据负载的响应(save/update/delete/audit/unaudit)。
ResultVoid = Result[None]
#: ``Result[PageStationQuotePageVO]`` —— 分页查询响应。
ResultPage = Result[PageStationQuotePageVO]
#: ``Result[list[StationQuotePageVO]]`` —— 原始导出分页响应。
ResultList = Result[list[StationQuotePageVO]]
#: ``Result[StationQuoteDetailVO]`` —— 详情查询响应。
ResultDetail = Result[StationQuoteDetailVO]
