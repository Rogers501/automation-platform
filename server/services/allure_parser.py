"""Allure 报告解析器: 读取 allure-results/ JSON 文件, 结构化返回测试结果."""

from __future__ import annotations

import json

from .scanner import ROOT


def parse_project_results(project: str) -> dict:
    """解析项目最近的 Allure 结果.

    Returns:
        {total, passed, failed, broken, skipped, duration, cases: [...]}
    """
    results_dir = ROOT / "projects" / project / "allure-results"
    if not results_dir.exists():
        return {"total": 0, "passed": 0, "failed": 0, "broken": 0, "skipped": 0, "cases": []}

    cases = []
    for f in sorted(results_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue

        if not isinstance(data, dict):
            continue
        status = data.get("status", "unknown")
        stage_results = data.get("stageResults", [])
        duration = sum(s.get("duration", 0) for s in stage_results)

        cases.append(
            {
                "name": data.get("name", ""),
                "status": status,
                "duration_ms": duration,
                "start": data.get("start", 0),
                "labels": [
                    label["value"]
                    for label in data.get("labels", [])
                    if label.get("name") == "severity"
                ],
            }
        )

    stats = {
        "total": len(cases),
        "passed": sum(1 for c in cases if c["status"] == "passed"),
        "failed": sum(1 for c in cases if c["status"] == "failed"),
        "broken": sum(1 for c in cases if c["status"] == "broken"),
        "skipped": sum(1 for c in cases if c["status"] == "skipped"),
        "cases": sorted(cases, key=lambda c: c.get("start", 0), reverse=True),
    }
    return stats
