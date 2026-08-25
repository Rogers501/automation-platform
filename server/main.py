"""测试管理平台后端 API 服务.

基于 FastAPI, 提供项目扫描、用例查询、测试执行、报告查看等接口.
前端 Vue 3 页面通过 HTTP + WebSocket 调用这些接口.

启动方式:
    .venv/Scripts/python.exe -m uvicorn server.main:app --reload --port 8900
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .db import dispose_db, init_db, session_factory, sync_projects
from .routers import cases, executions, projects, reports
from .services.scanner import scan_projects


def _cors_origins() -> list[str]:
    """Read allowed CORS origins from env, fall back to local dev defaults."""
    env = os.getenv("APP_CORS_ORIGINS", "").strip()
    if env:
        return [o.strip() for o in env.split(",") if o.strip()]
    return ["http://localhost:5173", "http://127.0.0.1:5173"]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize MySQL metadata and release connections deterministically."""
    try:
        await init_db()
        async with session_factory()() as session:
            await sync_projects(session, scan_projects())
    except (RuntimeError, SQLAlchemyError):
        # File-scan APIs remain usable while the local database is unavailable.
        pass
    yield
    await dispose_db()


app = FastAPI(
    title="自动化测试管理平台",
    description="项目扫描 / 用例查询 / 测试执行 / 报告查看",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/api", tags=["项目管理"])
app.include_router(cases.router, prefix="/api", tags=["用例查询"])
app.include_router(executions.router, prefix="/api", tags=["测试执行"])
app.include_router(reports.router, prefix="/api", tags=["报告查看"])


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "自动化测试管理平台 API 运行中", "docs": "/docs"}


@app.get("/api/health")
async def health() -> dict[str, str]:
    database = False
    try:
        async with session_factory()() as session:
            await session.execute(text("SELECT 1"))
            database = True
    except (RuntimeError, SQLAlchemyError):
        pass
    return {
        "status": "ok",
        "service": "automation-platform-api",
        "database": "connected" if database else "unavailable",
    }
