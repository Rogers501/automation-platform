"""测试执行路由: 触发执行 / 查看状态 / WebSocket 实时进度."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from ..db import ExecutionRow, execution_to_dict, session_factory
from ..db import list_executions as list_db_executions
from ..services import runner

_background_tasks: set[asyncio.Task[None]] = set()

router = APIRouter()


class ExecutionRequest(BaseModel):
    """执行测试请求体."""

    project: str
    env: str = "test"
    test_paths: list[str] = Field(default_factory=lambda: ["testcase/"])


@router.post("/executions")
async def create_execution(req: ExecutionRequest) -> dict[str, str]:
    """创建并启动一次测试执行."""
    if not req.test_paths:
        req.test_paths = ["testcase/"]
    execution_id = await runner.create_execution(req.project, req.env, req.test_paths)
    task = asyncio.create_task(runner.run_execution(execution_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"execution_id": execution_id, "status": "started"}


@router.get("/executions")
async def list_executions() -> list[dict[str, Any]]:
    """获取所有执行记录."""
    try:
        async with session_factory()() as session:
            records = await list_db_executions(session)
        live = {item["id"]: item for item in runner.list_executions()}
        return [live.get(row["id"], row) for row in records]
    except (RuntimeError, SQLAlchemyError):
        return runner.list_executions()


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: str) -> dict[str, Any]:
    """获取单次执行详情."""
    task = runner.get_execution(execution_id)
    if not task:
        try:
            async with session_factory()() as session:
                result = await session.get(ExecutionRow, execution_id)
        except (RuntimeError, SQLAlchemyError, ValueError):
            result = None
        if result is None:
            raise HTTPException(status_code=404, detail="执行记录不存在")
        return execution_to_dict(result)
    return task


@router.websocket("/ws/executions/{execution_id}")
async def ws_execution(websocket: WebSocket, execution_id: str) -> None:
    """WebSocket 实时推送执行进度."""
    await websocket.accept()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def on_message(msg: dict[str, Any]) -> None:
        await queue.put(msg)

    await runner.subscribe(execution_id, on_message)

    try:
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=1.0)
                await websocket.send_json(msg)
            except TimeoutError:
                task = runner.get_execution(execution_id)
                if task and task["status"] in ("passed", "failed"):
                    await websocket.send_json({"event": "done", "status": task["status"]})
                    break
    except WebSocketDisconnect:
        pass
