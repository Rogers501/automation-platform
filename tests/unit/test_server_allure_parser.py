import json
from pathlib import Path

from server.services import allure_parser as parser_module
from server.services.allure_parser import parse_project_results
from server.services.scanner import ROOT


def test_parse_project_results_returns_empty_when_missing() -> None:
    project = ROOT / "projects" / "definitely-not-exists-project"
    assert not project.exists()

    result = parse_project_results(project.name)

    assert result == {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "broken": 0,
        "skipped": 0,
        "cases": [],
    }


def test_parse_project_results_skips_container_json(tmp_path: Path, monkeypatch) -> None:
    results = tmp_path / "projects" / "demo" / "allure-results"
    results.mkdir(parents=True)
    (results / "container.json").write_text("[]", encoding="utf-8")
    result_json = {"name": "test_demo", "status": "passed", "start": 1, "stageResults": []}
    (results / "result.json").write_text(json.dumps(result_json), encoding="utf-8")
    monkeypatch.setattr(parser_module, "ROOT", tmp_path)

    report = parser_module.parse_project_results("demo")

    assert report["total"] == 1
    assert report["passed"] == 1
    assert report["cases"][0]["name"] == "test_demo"
