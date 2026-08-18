"""项目管理路由: 项目列表 / 项目详情."""

from fastapi import APIRouter, HTTPException

from ..services.scanner import scan_projects, scan_test_files

router = APIRouter()


@router.get("/projects")
async def list_projects() -> list[dict]:
    """获取所有测试项目列表."""
    return scan_projects()


@router.get("/projects/{project_name}")
async def get_project(project_name: str) -> dict:
    """获取项目详情 (包含测试文件列表)."""
    projects = scan_projects()
    for p in projects:
        if p["name"] == project_name:
            p["test_files"] = scan_test_files(project_name)
            return p
    raise HTTPException(status_code=404, detail=f"项目 {project_name} 不存在")
