"""pytest 执行器: 通过 subprocess 调用 pytest 运行测试.

执行流程:
  1. 接收前端请求 (项目名, 环境, 用例列表)
  2. 构造 pytest 命令行参数
  3. subprocess.Popen 启动, 逐行读取 stdout
  4. 通过 WebSocket 实时推送进度到前端
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from ..db import save_execution, session_factory
from .scanner import ROOT

#: Python 解释器路径 (项目 venv).
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

#: 运行中的任务 (execution_id -> 任务信息).
_running: dict[str, dict[str, Any]] = {}

#: WebSocket 订阅者 (execution_id -> callback).
_subscribers: dict[str, list[Any]] = {}


async def create_execution(project: str, env: str, test_paths: list[str]) -> str:
    """创建一次测试执行, 返回 execution_id."""
    execution_id = str(uuid.uuid4())[:8]
    _running[execution_id] = {
        "id": execution_id,
        "project": project,
        "env": env,
        "test_paths": test_paths,
        "status": "pending",
        "started_at": datetime.now().isoformat(),
        "output_lines": [],
    }
    await _persist(execution_id)
    return execution_id


async def run_execution(execution_id: str) -> None:
    """后台执行 pytest 并推送进度."""
    task = _running.get(execution_id)
    if not task:
        return

    task["status"] = "running"
    await _persist(execution_id)
    project_dir = ROOT / "projects" / task["project"]

    cmd = [
        str(PYTHON),
        "-m",
        "pytest",
        *task["test_paths"],
        "-v",
        "--tb=short",
    ]

    await _notify(execution_id, {"event": "started", "cmd": " ".join(cmd)})

    child_env = os.environ.copy()
    child_env["APP_ENV"] = task["env"]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(project_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=child_env,
    )

    assert proc.stdout is not None
    async for line in proc.stdout:
        text = line.decode("utf-8", errors="replace").rstrip()
        task["output_lines"].append(text)
        await _notify(execution_id, {"event": "output", "line": text})

    await proc.wait()
    task["status"] = "passed" if proc.returncode == 0 else "failed"
    task["finished_at"] = datetime.now().isoformat()
    await _persist(execution_id)
    await _notify(
        execution_id,
        {
            "event": "finished",
            "status": task["status"],
            "returncode": proc.returncode,
        },
    )


def get_execution(execution_id: str) -> dict[str, Any] | None:
    """获取执行状态."""
    return _running.get(execution_id)


def list_executions() -> list[dict[str, Any]]:
    """列出所有执行记录."""
    return sorted(_running.values(), key=lambda x: x["started_at"], reverse=True)


async def subscribe(execution_id: str, callback: Any) -> None:
    """订阅执行进度推送."""
    _subscribers.setdefault(execution_id, []).append(callback)


async def _persist(execution_id: str) -> None:
    """Persist an execution snapshot while keeping in-memory execution usable."""
    task = _running.get(execution_id)
    if not task:
        return
    try:
        async with session_factory()() as session:
            await save_execution(session, task)
    except (RuntimeError, SQLAlchemyError):
        return


async def _notify(execution_id: str, message: dict[str, Any]) -> None:
    """通知所有订阅者."""
    for cb in _subscribers.get(execution_id, []):
        with contextlib.suppress(Exception):
            await cb(message)
