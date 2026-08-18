"""测试管理平台后端 API 服务.

基于 FastAPI, 提供项目扫描、用例查询、测试执行、报告查看等接口.
前端 Vue 3 页面通过 HTTP + WebSocket 调用这些接口.

启动方式:
    .venv/Scripts/python.exe -m uvicorn server.main:app --reload --port 8900
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import cases, executions, projects, reports

app = FastAPI(
    title="自动化测试管理平台",
    description="项目扫描 / 用例查询 / 测试执行 / 报告查看",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/api", tags=["项目管理"])
app.include_router(cases.router, prefix="/api", tags=["用例查询"])
app.include_router(executions.router, prefix="/api", tags=["测试执行"])
app.include_router(reports.router, prefix="/api", tags=["报告查看"])


@app.get("/")
async def root() -> dict:
    return {"message": "自动化测试管理平台 API 运行中", "docs": "/docs"}


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "service": "automation-platform-api"}
