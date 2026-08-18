"""项目扫描器: 自动发现 projects/ 下的所有测试项目.

扫描逻辑:
  1. 遍历 projects/ 目录, 跳过 template 和非项目目录
  2. 读取每个项目的 README.md 获取项目描述
  3. 读取 config/envs/ 获取可用环境列表
  4. 扫描 testcase/ 目录统计用例数量
"""

from __future__ import annotations

from pathlib import Path

#: 平台根目录 (server/ 的上一级).
ROOT = Path(__file__).resolve().parents[2]

#: 测试项目根目录.
PROJECTS_DIR = ROOT / "projects"

#: 需要跳过的目录 (模板和负载测试项目特殊处理).
SKIP_DIRS = {"template", "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules"}


def scan_projects() -> list[dict]:
    """扫描所有测试项目, 返回项目列表.

    Returns:
        项目列表, 每项包含: name(项目名), description(描述), envs(环境列表), case_count(用例数)
    """
    projects = []
    if not PROJECTS_DIR.exists():
        return projects

    for pdir in sorted(PROJECTS_DIR.iterdir()):
        if not pdir.is_dir() or pdir.name in SKIP_DIRS:
            continue
        if not (pdir / "pytest.ini").exists() and not (pdir / "pyproject.toml").exists():
            continue

        info: dict = {
            "name": pdir.name,
            "description": _read_description(pdir),
            "envs": _scan_envs(pdir),
            "case_count": _count_cases(pdir),
        }
        projects.append(info)

    return projects


def get_project_path(project_name: str) -> Path | None:
    """获取项目目录路径."""
    p = PROJECTS_DIR / project_name
    return p if p.exists() and p.is_dir() else None


def _read_description(pdir: Path) -> str:
    """从 README.md 提取第一行描述."""
    readme = pdir / "README.md"
    if readme.exists():
        for line in readme.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("!"):
                return line[:120]
    return ""


def _scan_envs(pdir: Path) -> list[str]:
    """扫描 config/envs/ 目录, 返回环境名列表 (如 test, uat)."""
    envs_dir = pdir / "config" / "envs"
    if not envs_dir.exists():
        return []
    return sorted(f.stem for f in envs_dir.glob("*.yaml"))


def _count_cases(pdir: Path) -> int:
    """统计 testcase/ 目录下的 Python 测试文件数."""
    tc_dir = pdir / "testcase"
    if not tc_dir.exists():
        return 0
    return len(list(tc_dir.rglob("test_*.py")))


def scan_test_files(project_name: str) -> list[dict]:
    """扫描项目下所有测试文件, 返回文件信息列表."""
    pdir = get_project_path(project_name)
    if not pdir:
        return []

    files = []
    tc_dir = pdir / "testcase"
    if tc_dir.exists():
        for f in sorted(tc_dir.rglob("test_*.py")):
            rel = f.relative_to(pdir)
            files.append(
                {
                    "path": str(rel).replace("\\", "/"),
                    "name": f.stem,
                    "module": str(rel.parent).replace("\\", "/"),
                }
            )
    return files
