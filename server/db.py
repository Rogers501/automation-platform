"""Async database layer for the test-management server."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DEFAULT_DATABASE_URL = "mysql+aiomysql://tester:testerpw@127.0.0.1:3306/automation"


class Base(DeclarativeBase):
    """Base class for platform metadata tables."""


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    envs: Mapped[list[str]] = mapped_column(JSON, default=list)
    case_count: Mapped[int] = mapped_column(Integer, default=0)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class TestCaseRow(Base):
    __tablename__ = "test_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_name: Mapped[str] = mapped_column(String(100), index=True)
    case_id: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    file: Mapped[str] = mapped_column(String(500))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    data_driven: Mapped[bool] = mapped_column(Boolean, default=False)
    data_cases: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ExecutionRow(Base):
    __tablename__ = "executions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project: Mapped[str] = mapped_column(String(100), index=True)
    env: Mapped[str] = mapped_column(String(50))
    test_paths: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ReportSnapshotRow(Base):
    __tablename__ = "report_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project: Mapped[str] = mapped_column(String(100), index=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    broken: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    cases: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def database_url() -> str:
    """Read the configured async database URL without leaking secrets into code."""
    return os.getenv("APP_DATABASE_URL", DEFAULT_DATABASE_URL)


async def init_db(url: str | None = None) -> None:
    """Create the engine and metadata tables for the platform database."""
    global _engine, _session_factory
    _engine = create_async_engine(url or database_url(), pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    async with _engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def dispose_db() -> None:
    """Release database connections on application shutdown."""
    if _engine is not None:
        await _engine.dispose()


def session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the active session factory."""
    if _session_factory is None:
        raise RuntimeError("database has not been initialized")
    return _session_factory


def execution_to_dict(row: ExecutionRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "project": row.project,
        "env": row.env,
        "test_paths": row.test_paths,
        "status": row.status,
        "started_at": row.started_at.isoformat(),
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


def report_to_dict(row: ReportSnapshotRow) -> dict[str, Any]:
    return {
        "project": row.project,
        "total": row.total,
        "passed": row.passed,
        "failed": row.failed,
        "broken": row.broken,
        "skipped": row.skipped,
        "cases": row.cases,
        "created_at": row.created_at.isoformat(),
    }


async def sync_projects(session: AsyncSession, projects: list[dict[str, Any]]) -> None:
    """Upsert scanned projects and remove projects no longer present on disk."""
    names = {item["name"] for item in projects}
    existing = (await session.scalars(select(ProjectRow))).all()
    by_name = {row.name: row for row in existing}
    for item in projects:
        row = by_name.get(item["name"])
        if row is None:
            session.add(ProjectRow(**item, synced_at=datetime.now()))
            continue
        row.description = item["description"]
        row.envs = item["envs"]
        row.case_count = item["case_count"]
        row.synced_at = datetime.now()
    for row in existing:
        if row.name not in names:
            await session.delete(row)
    await session.commit()


async def sync_cases(
    session: AsyncSession,
    project_name: str,
    cases: list[dict[str, Any]],
) -> None:
    """Replace a project's cached cases with the latest scan result."""
    rows = await session.scalars(
        select(TestCaseRow).where(TestCaseRow.project_name == project_name)
    )
    for row in rows:
        await session.delete(row)
    for item in cases:
        session.add(
            TestCaseRow(
                project_name=project_name,
                case_id=item["id"],
                file=item["file"],
                name=item["name"],
                description=item["description"],
                tags=item["tags"],
                data_driven=item["data_driven"],
                data_cases=item["data_cases"],
                synced_at=datetime.now(),
            )
        )
    await session.commit()


async def save_execution(session: AsyncSession, record: dict[str, Any]) -> None:
    """Insert or update one execution record."""
    row = await session.get(ExecutionRow, record["id"])
    if row is None:
        session.add(
            ExecutionRow(
                id=record["id"],
                project=record["project"],
                env=record["env"],
                test_paths=record["test_paths"],
                status=record["status"],
                started_at=datetime.fromisoformat(record["started_at"]),
                finished_at=(
                    datetime.fromisoformat(record["finished_at"])
                    if record.get("finished_at")
                    else None
                ),
            )
        )
    else:
        row.status = record["status"]
        row.finished_at = (
            datetime.fromisoformat(record["finished_at"]) if record.get("finished_at") else None
        )
    await session.commit()


async def list_executions(session: AsyncSession, limit: int = 100) -> list[dict[str, Any]]:
    rows = await session.scalars(
        select(ExecutionRow).order_by(ExecutionRow.started_at.desc()).limit(limit)
    )
    return [execution_to_dict(row) for row in rows]


async def save_report(
    session: AsyncSession,
    project: str,
    report: dict[str, Any],
) -> None:
    """Persist the latest structured Allure result snapshot."""
    session.add(
        ReportSnapshotRow(
            project=project,
            **{
                "total": report["total"],
                "passed": report["passed"],
                "failed": report["failed"],
                "broken": report["broken"],
                "skipped": report["skipped"],
                "cases": report["cases"],
                "created_at": datetime.now(),
            },
        )
    )
    await session.commit()


async def latest_report(session: AsyncSession, project: str) -> dict[str, Any] | None:
    row = await session.scalar(
        select(ReportSnapshotRow)
        .where(ReportSnapshotRow.project == project)
        .order_by(ReportSnapshotRow.created_at.desc())
        .limit(1)
    )
    return report_to_dict(row) if row else None
