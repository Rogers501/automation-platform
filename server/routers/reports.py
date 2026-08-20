"""报告查看路由: Allure 结果解析 / 历史记录."""

from typing import Any

from fastapi import APIRouter
from sqlalchemy.exc import SQLAlchemyError

from ..db import latest_report, save_report, session_factory
from ..services.allure_parser import parse_project_results

router = APIRouter()


@router.get("/projects/{project_name}/report")
async def get_project_report(project_name: str) -> dict[str, Any]:
    """获取项目最近的 Allure 测试报告 (结构化数据)."""
    report = parse_project_results(project_name)
    try:
        async with session_factory()() as session:
            if report["total"] > 0:
                await save_report(session, project_name, report)
            else:
                cached = await latest_report(session, project_name)
                if cached:
                    return cached
    except (RuntimeError, SQLAlchemyError):
        pass
    if report["total"] == 0:
        # 不报 404, 返回空报告让前端显示 "暂无数据"
        return {"project": project_name, "message": "暂无执行结果", **report}
    return {"project": project_name, **report}
