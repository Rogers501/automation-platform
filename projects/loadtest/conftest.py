"""loadtest conftest: point framework config at this project config dir."""

from __future__ import annotations

import os
from pathlib import Path

# Point framework config center at this project config dir (rule 10).
os.environ.setdefault("APP_CONFIG_DIR", str(Path(__file__).parent / "config" / "envs"))

# Enable framework pytest plugin (for allure attachments + metrics tests).
pytest_plugins = ["framework.testing.hooks.fixtures"]
