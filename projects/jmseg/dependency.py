"""jmseg 驿站报价接口依赖 DAG(基于 framework.testing.dependency).

依赖编排与拓扑排序已提升为 framework 公共能力,此处仅声明业务依赖图。
提取采用"生产者推送"模型:``page`` 从自身响应提取报价 id 入上下文,
``detail/update/audit/delete`` 读取上下文中的 id;``unaudit`` 依赖 ``audit``。

链路:
    save -> page(提取 id) -> {detail, update, audit -> unaudit, delete}
"""

from __future__ import annotations

from framework.testing.dependency import (
    DependencyGraph,
    DependencyNode,
    DependencyRunner,
)

__all__ = ["STATION_QUOTE_DAG", "DependencyGraph", "DependencyNode", "DependencyRunner"]

#: 驿站报价接口依赖图(save 创建 -> page 查询并提取 id -> 派生操作)。
STATION_QUOTE_DAG = DependencyGraph(
    [
        DependencyNode("save"),
        DependencyNode("page", depends_on=("save",), extract={"id": "$.data.records[0].id"}),
        DependencyNode("detail", depends_on=("page",)),
        DependencyNode("update", depends_on=("page",)),
        DependencyNode("audit", depends_on=("page",)),
        DependencyNode("unaudit", depends_on=("audit",)),
        DependencyNode("delete", depends_on=("page",)),
    ]
)
