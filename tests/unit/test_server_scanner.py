from pathlib import Path

from server.services import scanner


def test_scan_projects_uses_isolated_projects_dir(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "demo"
    (project / "testcase").mkdir(parents=True)
    (project / "config" / "envs").mkdir(parents=True)
    newline = chr(10)
    (project / "pytest.ini").write_text("[pytest]" + newline, encoding="utf-8")
    (project / "README.md").write_text("# demo" + newline + "演示项目" + newline, encoding="utf-8")
    (project / "config" / "envs" / "uat.yaml").write_text("app: {}" + newline, encoding="utf-8")
    test_code = "def test_ok():" + newline + "    pass" + newline
    (project / "testcase" / "test_demo.py").write_text(test_code, encoding="utf-8")
    monkeypatch.setattr(scanner, "PROJECTS_DIR", tmp_path)

    result = scanner.scan_projects()

    assert result == [
        {
            "name": "demo",
            "description": "演示项目",
            "envs": ["uat"],
            "case_count": 1,
        }
    ]


def test_scan_test_files_returns_relative_path(tmp_path: Path, monkeypatch) -> None:
    test_file = tmp_path / "web" / "test_login.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_login():" + chr(10) + "    pass" + chr(10), encoding="utf-8")
    monkeypatch.setattr(scanner, "PROJECTS_DIR", tmp_path)
