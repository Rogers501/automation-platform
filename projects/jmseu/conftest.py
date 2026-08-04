"""jmseu 项目 conftest: 框架插件 + 配置定位 + WebUI fixtures 再导出.

jmseu = JMS + EU (德国/欧洲 JMS 系统). 参见 README.md 命名约定.
"""

from __future__ import annotations

import os
from pathlib import Path

# Load .env from project root for jmseu credentials (JMSEU_TEST_*).
# The framework's pydantic-settings only reads APP_* prefixed vars from .env;
# this makes JMSEU_TEST_USERNAME/PASSWORD available via os.environ.
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
    """Write Allure environment.properties + categories.json after the session.

    Enriches the Allure report with runtime environment metadata (base_url,
    browser, headless, channel, env) and default failure categories. Only
    writes when ``--alluredir`` is set.
    """
    results_dir_str = session.config.getoption("--alluredir", default=None)  # type: ignore[attr-defined]
    if not results_dir_str:
        return
    from pathlib import Path

    from framework.core.config import get_settings
    from framework.reporting.environment import write_categories, write_environment

    results_dir = Path(results_dir_str)
    if not results_dir.exists():
        return
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
