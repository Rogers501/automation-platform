"""jmseg 项目 conftest:框架插件 + 配置定位 + fixtures 再导出."""

from __future__ import annotations

import os
from pathlib import Path

from fixture.auth import token, ups_user  # noqa: F401 (pytest fixture re-export)
from fixture.clients import (  # noqa: F401 (pytest fixture re-export)
    api_client,
    mock_transport,
    sync_client,
)

os.environ.setdefault("APP_CONFIG_DIR", str(Path(__file__).parent / "config"))
os.environ.setdefault("APP_ENV", "dev")

pytest_plugins = ["framework.testing.hooks.fixtures"]
