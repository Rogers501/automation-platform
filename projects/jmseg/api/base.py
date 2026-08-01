"""jmseg API 客户端基座:端点注册表 + 异步/同步客户端 + 鉴权自动识别.

设计要点:
- ``BaseClient`` 基于 framework ``AsyncHttpClient``(异步主路径,完整重试/日志/录制).
- ``SyncClient`` 基于 ``httpx.Client``(同步路径),复用同一 ``_ENDPOINTS`` 注册表,
  与异步路径零逻辑重复(仅传输层不同),满足"支持同步和异步 httpx".
- 鉴权自动识别:``detect_auth_scheme`` 扫描 OpenAPI 的 header/cookie/securitySchemes,
  自动判断 Bearer / 自定义 header(如 ``authtoken``)/ Cookie / 无鉴权.
- 项目本地化:framework 核心零修改(遵守"不允许修改已有 framework 核心代码").
  当第二个业务系统需要时,可提升为 framework 公共能力(rule 4).
"""

from __future__ import annotations

import enum
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

import httpx
from pydantic import BaseModel

from framework.clients.http.client import AsyncHttpClient
from framework.clients.http.models import ApiResponse

__all__ = [
    "AuthKind",
    "AuthScheme",
    "BaseClient",
    "EndpointSpec",
    "SyncClient",
    "detect_auth_scheme",
]

#: 视为自定义 token 头的常见命名(小写匹配)。
_TOKEN_HEADER_CANDIDATES: tuple[str, ...] = (
    "authtoken",
    "token",
    "x-auth-token",
    "x-api-key",
    "api-key",
)


class AuthKind(enum.Enum):
    """鉴权类型."""

    BEARER = "bearer"
    CUSTOM_HEADER = "custom_header"
    COOKIE = "cookie"
    NONE = "none"


@dataclass(frozen=True)
class AuthScheme:
    """识别出的鉴权方案."""

    kind: AuthKind
    header_name: str | None = None
    cookie_name: str | None = None


@dataclass(frozen=True)
class EndpointSpec:
    """端点声明(驱动异步与同步两条路径,避免重复定义)."""

    name: str
    method: str
    path: str
    request_model: type[BaseModel] | None = None
    response_model: type[BaseModel] | None = None
    query_model: type[BaseModel] | None = None


def detect_auth_scheme(spec: Mapping[str, Any]) -> AuthScheme:
    """从 OpenAPI 规格自动识别鉴权方式.

    扫描顺序:securitySchemes -> 各操作的 header/cookie 参数。
    Bearer 优先于自定义 header 优先于 Cookie;均无则 :attr:`AuthKind.NONE`。

    Args:
        spec: 解析后的 OpenAPI 文档(dict)。

    Returns:
        识别到的 :class:`AuthScheme`。
    """
    header_names: dict[str, str] = {}
    cookie_names: list[str] = []

    security_schemes = spec.get("components", {}).get("securitySchemes", {}) or {}
    for scheme in security_schemes.values():
        kind = scheme.get("type")
        if kind == "http" and scheme.get("scheme") == "bearer":
            return AuthScheme(AuthKind.BEARER, header_name="Authorization")
        if kind == "apiKey":
            location = scheme.get("in")
            name = scheme.get("name")
            if location == "header" and name:
                header_names[name.lower()] = name
            elif location == "cookie" and name:
                cookie_names.append(name)

    for path_item in (spec.get("paths", {}) or {}).values():
        if not isinstance(path_item, dict):
            continue
        for op in path_item.values():
            if not isinstance(op, dict) or "parameters" not in op:
                continue
            for param in op.get("parameters", []) or []:
                if not isinstance(param, dict):
                    continue
                location = param.get("in")
                name = param.get("name")
                if not name:
                    continue
                if location == "header":
                    header_names[name.lower()] = name
                elif location == "cookie":
                    cookie_names.append(name)

    if "authorization" in header_names:
        return AuthScheme(AuthKind.BEARER, header_name=header_names["authorization"])
    for candidate in _TOKEN_HEADER_CANDIDATES:
        if candidate in header_names:
            return AuthScheme(AuthKind.CUSTOM_HEADER, header_name=header_names[candidate])
    if cookie_names:
        return AuthScheme(AuthKind.COOKIE, cookie_name=cookie_names[0])
    return AuthScheme(AuthKind.NONE)


def _build_headers(
    *,
    token: str | None,
    token_header: str,
    user: str | None,
    extra: Mapping[str, str],
) -> dict[str, str]:
    """构造公共请求头(异步/同步复用,避免重复)."""
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "lang": "zh-CN",
        "langtype": "zh_CN",
    }
    if user:
        headers["X-UPS-USER"] = user
    headers.update(extra)
    if token:
        headers[token_header] = token
    return headers


def _model_payload(model: BaseModel | None) -> dict[str, Any] | None:
    """将请求模型序列化为按别名输出的 dict(剔除空值)."""
    if model is None:
        return None
    return model.model_dump(by_alias=True, exclude_none=True)


class BaseClient:
    """异步 API 客户端基类(基于 framework ``AsyncHttpClient``).

    子类声明 ``base_path``、``token_header`` 与 ``_ENDPOINTS`` 注册表,
    并为每个端点提供一个薄异步方法(委托 :meth:`_arequest`)。
    """

    base_path: ClassVar[str] = ""
    token_header: ClassVar[str] = "authtoken"
    _ENDPOINTS: ClassVar[dict[str, EndpointSpec]] = {}

    def __init__(
        self,
        client: AsyncHttpClient,
        *,
        token: str | None = None,
        user: str | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        self._client = client
        self._token = token
        self._user = user
        self._extra: dict[str, str] = dict(extra_headers or {})

    def _headers(self) -> dict[str, str]:
        """构造请求头(含 token 注入)."""
        return _build_headers(
            token=self._token,
            token_header=type(self).token_header,
            user=self._user,
            extra=self._extra,
        )

    @classmethod
    def endpoint(cls, name: str) -> EndpointSpec:
        """按名称查找端点声明。"""
        try:
            return cls._ENDPOINTS[name]
        except KeyError as exc:
            raise KeyError(f"{cls.__name__} has no endpoint {name!r}") from exc

    async def _arequest(
        self,
        ep: EndpointSpec,
        *,
        body: BaseModel | None = None,
        params: BaseModel | None = None,
        path_params: Mapping[str, Any] | None = None,
    ) -> ApiResponse:
        """执行一次异步请求并返回 :class:`ApiResponse`."""
        url = self.base_path + ep.path.format(**(path_params or {}))
        kwargs: dict[str, Any] = {"headers": self._headers()}
        payload = _model_payload(body)
        if payload is not None:
            kwargs["json"] = payload
        query = _model_payload(params)
        if query is not None:
            kwargs["params"] = query
        return await self._client.request(ep.method, url, **kwargs)


class SyncClient:
    """同步 API 客户端适配器(基于 ``httpx.Client``).

    复用某 ``BaseClient`` 子类的 ``_ENDPOINTS`` 注册表,以同步方式调用相同端点,
    与异步路径共享 DTO 与端点声明(零逻辑重复)。适合脚本/REPL 场景;
    测试与并发执行仍以异步客户端为主。
    """

    def __init__(
        self,
        client_cls: type[BaseClient],
        client: httpx.Client,
        *,
        token: str | None = None,
        user: str | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        self._cls = client_cls
        self._client = client
        self._token = token
        self._user = user
        self._extra: dict[str, str] = dict(extra_headers or {})

    def _headers(self) -> dict[str, str]:
        """构造请求头(含 token 注入,与异步一致)."""
        return _build_headers(
            token=self._token,
            token_header=self._cls.token_header,
            user=self._user,
            extra=self._extra,
        )

    def _request(
        self,
        ep: EndpointSpec,
        *,
        body: BaseModel | None = None,
        params: BaseModel | None = None,
    ) -> ApiResponse:
        """执行一次同步请求并返回 :class:`ApiResponse`."""
        url = self._cls.base_path + ep.path
        kwargs: dict[str, Any] = {"headers": self._headers()}
        payload = _model_payload(body)
        if payload is not None:
            kwargs["json"] = payload
        query = _model_payload(params)
        if query is not None:
            kwargs["params"] = query
        start = time.perf_counter()
        resp = self._client.request(ep.method, url, **kwargs)
        elapsed = time.perf_counter() - start
        return ApiResponse.from_httpx(resp, elapsed_seconds=elapsed)

    def __getattr__(self, name: str) -> Callable[..., ApiResponse]:
        """按端点名生成同步调用方法(复用注册表)."""
        if name.startswith("_"):
            raise AttributeError(name)
        endpoints = self.__dict__.get("_cls", type(None))._ENDPOINTS
        if name not in endpoints:
            raise AttributeError(f"{self._cls.__name__} has no endpoint {name!r}")
        ep = endpoints[name]

        def caller(model: BaseModel | None = None) -> ApiResponse:
            if ep.query_model is not None:
                return self._request(ep, params=model)
            return self._request(ep, body=model)

        caller.__name__ = name
        return caller

    def close(self) -> None:
        """关闭底层同步连接。"""
        self._client.close()

    def __enter__(self) -> SyncClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
