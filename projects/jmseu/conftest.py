"""jmseu 项目 conftest: 框架插件 + 配置定位 + WebUI fixtures 再导出.

jmseu = JMS + EU (德国/欧洲 JMS 系统). 参见 README.md 命名约定.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from loguru import logger

# Load .env from project root (APP_ENV, APP_LOG_LEVEL, etc.).
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

from fixture.web_client import (  # noqa: F401 (pytest fixture re-export)
    base_url,
    screenshot_provider,
    web_client,
)

# Point the framework config center at this project's config dir (rule 10).
os.environ.setdefault("APP_CONFIG_DIR", str(Path(__file__).parent / "config" / "envs"))
os.environ.setdefault("APP_ENV", "dev")

# Enable the framework's pytest plugin (env init, trace context, failure artifacts).
pytest_plugins = ["framework.testing.hooks.fixtures"]


def pytest_sessionfinish(session: object, exitstatus: int) -> None:
    """Write Allure environment/categories, then generate HTML and open it.

    Done in sessionfinish (not terminal_summary) so it also runs under IDEs
    that pass ``--no-summary`` (e.g. PyCharm's pytest runner), which suppress
    ``pytest_terminal_summary``.
    """
    results_dir_str = session.config.getoption("--alluredir", default=None)  # type: ignore[attr-defined]
    if not results_dir_str:
        return
    results_dir = Path(results_dir_str)
    if not results_dir.exists():
        return

    from framework.core.config import get_settings
    from framework.reporting.environment import write_categories, write_environment

    s = get_settings()
    write_environment(
        results_dir,
        {
            "env": s.env.value,
            "base_url": s.web.base_url,
            "browser": s.web.browser,
            "headless": str(s.web.headless),
            "channel": s.web.channel or "(bundled)",
            "slow_mo_ms": str(s.web.slow_mo_ms),
            "timeout_ms": str(s.web.timeout_ms),
        },
    )
    write_categories(results_dir)

    _generate_and_open_report(results_dir)


def _kill_port_process(port: int) -> None:
    """Kill stale allure/node/java servers listening on *port* (Windows).

    Uses ``netstat -ano`` instead of ``Get-NetTCPConnection``: the cmdlet
    fails to report wildcard (``0.0.0.0`` / ``[::]``) listeners on some hosts,
    so stale ``allure open`` servers stay invisible and the next run dies on
    ``EADDRINUSE``.
    """
    if sys.platform != "win32":
        return
    script = r"""$lines = netstat -ano | Select-String 'LISTENING' |
 Where-Object { $_.Line -match ':__PORT__(\s|$)' }
$killed = @()
foreach ($m in $lines) {
  $procId = ($m.Line -split '\s+')[-1]
  $name = (Get-Process -Id $procId -ErrorAction SilentlyContinue).ProcessName
  if ($name -match 'java|allure|node') {
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    $killed += "$procId/$name"
  }
}
if ($killed) { Write-Output ($killed -join ', ') }
""".replace("__PORT__", str(port))
    with contextlib.suppress(Exception):
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        killed = out.stdout.strip()
        if killed:
            logger.info("端口 {} 旧服务器已清理: {}", port, killed)


def _generate_and_open_report(results_dir: Path) -> None:
    """Generate Allure HTML report and open it (CI/Jenkins skipped).

    Uses ``allure open`` (local HTTP server) so the SPA can fetch its data
    without the file:// CORS restriction that makes Chrome hang.
    """
    report_dir = results_dir.parent / "allure-report"
    if report_dir.exists():
        shutil.rmtree(report_dir)
    allure_bin = shutil.which("allure")
    if not allure_bin:
        logger.warning("allure CLI 未安装, 跳过 HTML 生成 (npm i -g allure-commandline)")
        return
    try:
        subprocess.run(
            [allure_bin, "generate", "-o", str(report_dir), str(results_dir)],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:
        logger.warning("Allure HTML 生成异常: {}", exc)
        return
    if not report_dir.exists():
        logger.warning(
            "Allure HTML 生成失败, 请手动: allure generate {} -o allure-report", results_dir
        )
        return

    index_html = report_dir / "index.html"
    abs_index = index_html.resolve()
    abs_report = report_dir.resolve()
    logger.info("Allure 报告路径: {}", abs_index)
    logger.info('查看命令(不转圈): allure open "{}"', abs_report)

    # 自动打开报告: 本地交互场景生效; CI/无 GUI 环境静默跳过。
    # 固定端口 5274, 启动前清理旧服务器避免进程堆积。
    if os.environ.get("CI") or os.environ.get("JENKINS_HOME"):
        return
    port = 5274
    _kill_port_process(port)
    try:
        subprocess.Popen(
            [allure_bin, "open", "--port", str(port), str(report_dir)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("Allure 报告(服务器, 不转圈): http://localhost:{}", port)
        logger.info("已启动 allure open(端口 {}, 旧服务器已清理)并打开浏览器", port)
    except Exception as exc:
        logger.warning(
            'allure open 启动失败: {}; 请手动: allure open --port {} "{}"',
            exc,
            port,
            abs_report,
        )


def pytest_report_header(config: pytest.Config) -> list[str]:
    """Print inifile + alluredir to help diagnose report generation in IDEs."""
    inifile = getattr(config, "inifile", None)
    alluredir = config.getoption("--alluredir", default=None)
    return [f"jmseu conftest: inifile={inifile}  alluredir={alluredir}"]


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter,
    exitstatus: int,
    config: pytest.Config,
) -> None:
    """Print Allure report info at session end (command-line only).

    Suppressed by ``--no-summary`` (PyCharm runner); HTML generation and
    auto-open happen in ``pytest_sessionfinish`` instead.
    """
    results_dir_str = config.getoption("--alluredir", default=None)
    if not results_dir_str:
        return
    results_dir = Path(results_dir_str)
    report_dir = results_dir.parent / "allure-report"
    if not report_dir.exists():
        return  # generated in sessionfinish; nothing to print if it failed

    file_count = len(list(results_dir.iterdir())) if results_dir.exists() else 0
    try:
        display_path = results_dir.resolve().relative_to(Path.cwd())
    except ValueError:
        display_path = results_dir.resolve()

    terminalreporter.write_line("")
    terminalreporter.write_line("=" * 60, bold=True)
    terminalreporter.write_line("Allure 报告", bold=True)
    terminalreporter.write_line("=" * 60, bold=True)
    terminalreporter.write_line(f"  结果目录: {display_path} ({file_count} files)")
    terminalreporter.write_line(f"  HTML 报告: {report_dir}")
    terminalreporter.write_line(f"  打开文件: {report_dir / 'index.html'}")
    terminalreporter.write_line("=" * 60, bold=True)
