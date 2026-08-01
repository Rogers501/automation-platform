"""jmseg 驿站报价领域枚举.

枚举值与后端契约一致(整数/字符串码),同时提供 ``from_code`` 安全解析,
便于从接口返回或数据驱动用例中还原枚举成员.
"""

from __future__ import annotations

import enum

__all__ = [
    "AuditStatus",
    "ExportType",
    "FeeType",
    "FranchiseeFlag",
    "RoundingMode",
]


class FeeType(enum.IntEnum):
    """费用类型(取件费/派件费/仓储费)."""

    PICKUP = 1
    """取件费."""

    DELIVERY = 2
    """派件费."""

    WAREHOUSE = 3
    """仓储费."""

    @classmethod
    def from_code(cls, code: int | str | None) -> FeeType | None:
        """按原始码还原枚举;``None``/0 返回 ``None``(表示全部)."""
        if code is None or code == 0:
            return None
        return cls(int(code))


class AuditStatus(enum.IntEnum):
    """审核状态(未审核/已审核)."""

    UNAUDITED = 0
    """未审核."""

    AUDITED = 1
    """已审核."""

    @classmethod
    def from_code(cls, code: int | str | None) -> AuditStatus | None:
        """按原始码还原枚举;``None`` 返回 ``None``(表示全部)."""
        if code is None:
            return None
        return cls(int(code))


class ExportType(enum.IntEnum):
    """导出类型(明文/密文)."""

    PLAINTEXT = 0
    """明文."""

    CIPHER = 1
    """密文."""


class FranchiseeFlag(enum.IntEnum):
    """加盟商标识(是/否)."""

    YES = 1
    NO = 2

    @classmethod
    def from_code(cls, code: int | str | None) -> FranchiseeFlag | None:
        """按原始码还原枚举;``None`` 返回 ``None``."""
        if code is None:
            return None
        return cls(int(code))


class RoundingMode(enum.StrEnum):
    """计费重量进位方式.

    规格未穷举所有取值,因此使用 ``str`` 枚举并保留 ``UNKNOWN`` 兜底,
    避免后端新增码值时反序列化失败.
    """

    ACTUAL = "B01"
    """实际重量."""

    ROUND_HALF_UP = "B02"
    """四舍五入."""

    UNKNOWN = "UNKNOWN"
    """未知/兜底码(后端新增值时落到此处)."""

    @classmethod
    def from_code(cls, code: str | None) -> RoundingMode:
        """按原始码还原枚举;未知码回落到 :attr:`UNKNOWN`."""
        if code is None:
            return cls.UNKNOWN
        try:
            return cls(code)
        except ValueError:
            return cls.UNKNOWN
