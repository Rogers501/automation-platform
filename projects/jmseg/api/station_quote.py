"""驿站报价维护接口客户端(单 Tag 生成单 Client).

端点清单(来自 ``projects/jmseg/openapi.json``):
``POST /station-quote/save``      新增
``POST /station-quote/update``    修改
``POST /station-quote/delete``    删除
``POST /station-quote/audit``     审核
``POST /station-quote/unaudit``   反审核
``POST /station-quote/page``      分页查询
``POST /station-quote/ark-export/page`` 分页查询(Raw)
``GET  /station-quote/detail``    详情
"""

from __future__ import annotations

from typing import ClassVar

from models.dto import (
    AuditStationQuoteCmdRequest,
    CreateStationQuoteCmdRequest,
    DeleteStationQuoteCmdRequest,
    DetailQuery,
    PageStationQuoteQueryRequest,
    ResultDetail,
    ResultList,
    ResultPage,
    ResultVoid,
    UnauditStationQuoteCmdRequest,
    UpdateStationQuoteCmdRequest,
)

from api.base import BaseClient, EndpointSpec
from framework.clients.http.models import ApiResponse

__all__ = ["StationQuoteClient"]


class StationQuoteClient(BaseClient):
    """驿站报价维护客户端(异步主路径)."""

    base_path = "/station-quote"
    token_header = "authtoken"

    _ENDPOINTS: ClassVar[dict[str, EndpointSpec]] = {
        "save": EndpointSpec("save", "POST", "/save", CreateStationQuoteCmdRequest, ResultVoid),
        "update": EndpointSpec(
            "update", "POST", "/update", UpdateStationQuoteCmdRequest, ResultVoid
        ),
        "delete": EndpointSpec(
            "delete", "POST", "/delete", DeleteStationQuoteCmdRequest, ResultVoid
        ),
        "audit": EndpointSpec("audit", "POST", "/audit", AuditStationQuoteCmdRequest, ResultVoid),
        "unaudit": EndpointSpec(
            "unaudit", "POST", "/unaudit", UnauditStationQuoteCmdRequest, ResultVoid
        ),
        "page": EndpointSpec("page", "POST", "/page", PageStationQuoteQueryRequest, ResultPage),
        "ark_export_page": EndpointSpec(
            "ark_export_page",
            "POST",
            "/ark-export/page",
            PageStationQuoteQueryRequest,
            ResultList,
        ),
        "detail": EndpointSpec(
            "detail", "GET", "/detail", None, ResultDetail, query_model=DetailQuery
        ),
    }

    async def save(self, body: CreateStationQuoteCmdRequest) -> ApiResponse:
        """新增驿站报价。"""
        return await self._arequest(self.endpoint("save"), body=body)

    async def update(self, body: UpdateStationQuoteCmdRequest) -> ApiResponse:
        """修改驿站报价。"""
        return await self._arequest(self.endpoint("update"), body=body)

    async def delete(self, body: DeleteStationQuoteCmdRequest) -> ApiResponse:
        """删除驿站报价。"""
        return await self._arequest(self.endpoint("delete"), body=body)

    async def audit(self, body: AuditStationQuoteCmdRequest) -> ApiResponse:
        """审核驿站报价。"""
        return await self._arequest(self.endpoint("audit"), body=body)

    async def unaudit(self, body: UnauditStationQuoteCmdRequest) -> ApiResponse:
        """反审核驿站报价。"""
        return await self._arequest(self.endpoint("unaudit"), body=body)

    async def page(self, body: PageStationQuoteQueryRequest) -> ApiResponse:
        """分页查询驿站报价。"""
        return await self._arequest(self.endpoint("page"), body=body)

    async def ark_export_page(self, body: PageStationQuoteQueryRequest) -> ApiResponse:
        """分页查询驿站报价(Raw 导出)。"""
        return await self._arequest(self.endpoint("ark_export_page"), body=body)

    async def detail(self, query: DetailQuery) -> ApiResponse:
        """查询驿站报价详情。"""
        return await self._arequest(self.endpoint("detail"), params=query)

    @staticmethod
    def parse_void(resp: ApiResponse) -> ResultVoid:
        """将 ``save/update/delete/audit/unaudit`` 响应解析为 :class:`ResultVoid`."""
        return ResultVoid.model_validate(resp.json)

    @staticmethod
    def parse_page(resp: ApiResponse) -> ResultPage:
        """将 ``page`` 响应解析为 :class:`ResultPage`."""
        return ResultPage.model_validate(resp.json)

    @staticmethod
    def parse_list(resp: ApiResponse) -> ResultList:
        """将 ``ark_export_page`` 响应解析为 :class:`ResultList`."""
        return ResultList.model_validate(resp.json)

    @staticmethod
    def parse_detail(resp: ApiResponse) -> ResultDetail:
        """将 ``detail`` 响应解析为 :class:`ResultDetail`."""
        return ResultDetail.model_validate(resp.json)
