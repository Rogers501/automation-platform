"""用例查询路由: 用例列表 / 数据驱动参数."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from ..db import session_factory, sync_cases
from ..services.scanner import get_project_path, scan_test_files

router = APIRouter()


@router.get("/projects/{project_name}/cases")
async def list_cases(project_name: str, env: str = "test") -> dict[str, Any]:
    """获取项目的测试用例列表.

    扫描 testcase/ 目录下的测试文件, 解析 docstring 中的用例描述.
    如果有 data/{env}/ 下的数据驱动文件, 也一并返回参数化信息.
    """
    pdir = get_project_path(project_name)
    if not pdir:
        raise HTTPException(status_code=404, detail=f"项目 {project_name} 不存在")

    cases: list[dict[str, Any]] = []
    test_files = scan_test_files(project_name)

    for tf in test_files:
        fpath = pdir / tf["path"]
        if not fpath.exists():
            continue

        content = fpath.read_text(encoding="utf-8")
        # 提取 docstring 中的描述
        docstring = _extract_docstring(content)
        # 提取测试函数名
        test_functions = _extract_test_functions(content)
        # 检查是否有数据驱动文件
        data_cases = _load_data_cases(pdir, env, tf["name"])

        for func_name, func_doc in test_functions:
            case = {
                "id": f"{tf['path']}::{func_name}",
                "file": tf["path"],
                "name": func_name,
                "description": func_doc or docstring,
                "tags": _extract_tags(content),
                "data_driven": bool(data_cases),
                "data_cases": data_cases,
            }
            cases.append(case)

    try:
        async with session_factory()() as session:
            await sync_cases(session, project_name, cases)
    except (RuntimeError, SQLAlchemyError):
        pass
    return {"project": project_name, "env": env, "total": len(cases), "cases": cases}


def _extract_docstring(content: str) -> str:
    """提取模块级 docstring."""
    lines = content.splitlines()
    in_doc = False
    doc_lines = []
    for line in lines[:20]:
        stripped = line.strip()
        if stripped.startswith('"""') and not in_doc:
            in_doc = True
            continue
        if in_doc:
            if stripped.endswith('"""'):
                break
            doc_lines.append(stripped)
    return " ".join(doc_lines)[:200] if doc_lines else ""


def _extract_test_functions(content: str) -> list[tuple[str, str]]:
    """提取所有 test_ 开头的函数及其 docstring."""
    import re

    functions = []
    pattern = r'(?:async\s+)?def\s+(test_\w+)\s*\([^)]*\)\s*(?:->[^:]*)?:\s*(?:"""(.*?)"""|\'\'\'(.*?)\'\'\')?'  # noqa: E501
    for m in re.finditer(pattern, content, re.DOTALL):
        name = m.group(1)
        doc = (m.group(2) or m.group(3) or "").strip().splitlines()
        doc_str = doc[0] if doc else ""
        functions.append((name, doc_str))
    return functions


def _extract_tags(content: str) -> list[str]:
    """提取 pytest 标签."""
    import re

    return list(set(re.findall(r"pytest\.mark\.(\w+)", content)))


def _load_data_cases(pdir: Path, env: str, test_file: str) -> list[dict[str, Any]]:
    """加载数据驱动的用例参数."""
    data_dir = pdir / "data" / env
    if not data_dir.exists():
        return []

    cases: list[dict[str, Any]] = []
    for yml in data_dir.glob("*.yaml"):
        try:
            data = yaml.safe_load(yml.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "cases" in data:
                for c in data["cases"]:
                    cases.append({"file": yml.name, "case": c})
        except Exception:
            continue
    return cases
