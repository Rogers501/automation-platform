from datetime import datetime

from server.db import (
    Base,
    ExecutionRow,
    ProjectRow,
    execution_to_dict,
    latest_report,
    list_executions,
    save_execution,
    save_report,
    sync_cases,
    sync_projects,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def test_metadata_repositories_round_trip() -> None:
    """Repositories persist scanned metadata and execution history consistently."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async with sessions() as session:
            await sync_projects(
                session,
                [
                    {
                        "name": "demo",
                        "description": "演示项目",
                        "envs": ["test", "uat"],
                        "case_count": 1,
                    }
                ],
            )
            await sync_cases(
                session,
                "demo",
                [
                    {
                        "id": "testcase/test_demo.py::test_ok",
                        "file": "testcase/test_demo.py",
                        "name": "test_ok",
                        "description": "成功",
                        "tags": ["smoke"],
                        "data_driven": False,
                        "data_cases": [],
                    }
                ],
            )
            await save_execution(
                session,
                {
                    "id": "12345678",
                    "project": "demo",
                    "env": "test",
                    "test_paths": ["testcase/"],
                    "status": "pending",
                    "started_at": datetime(2026, 8, 18, 12, 0).isoformat(),
                },
            )
            await save_report(
                session,
                "demo",
                {
                    "total": 2,
                    "passed": 1,
                    "failed": 1,
                    "broken": 0,
                    "skipped": 0,
                    "cases": [{"name": "test_ok", "status": "passed"}],
                },
            )

        async with sessions() as session:
            project = await session.scalar(select(ProjectRow).where(ProjectRow.name == "demo"))
            execution = await session.get(ExecutionRow, "12345678")
            history = await list_executions(session)
            report = await latest_report(session, "demo")

            assert project is not None
            assert project.envs == ["test", "uat"]
            assert execution is not None
            assert execution_to_dict(execution)["test_paths"] == ["testcase/"]
            assert history[0]["id"] == "12345678"
            assert report is not None
            assert report["passed"] == 1
    finally:
        await engine.dispose()


async def test_sync_projects_removes_stale_projects() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async with sessions() as session:
            session.add(ProjectRow(name="old", description="", envs=[], case_count=0))
            await session.commit()
            await sync_projects(session, [])

        async with sessions() as session:
            assert (await session.scalars(select(ProjectRow))).all() == []
    finally:
        await engine.dispose()
