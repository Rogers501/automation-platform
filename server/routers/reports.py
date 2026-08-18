"""报告查看路由: Allure 结果解析 / 历史记录."""

from fastapi import APIRouter

from ..services.allure_parser import parse_project_results

router = APIRouter()


@router.get("/projects/{project_name}/report")
async def get_project_report(project_name: str) -> dict:
    """获取项目最近的 Allure 测试报告 (结构化数据)."""
    report = parse_project_results(project_name)
    if report["total"] == 0:
        # 不报 404, 返回空报告让前端显示 "暂无数据"
        return {"project": project_name, "message": "暂无执行结果", **report}
    return {"project": project_name, **report}
