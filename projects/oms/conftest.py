"""Project conftest: framework hooks, config location, and project fixtures.

This wires the shared framework (env init, trace context, failure artifacts)
into this business system and re-exports the project's own fixtures so tests
can request them by name. The imports below are intentionally unused here -
pytest discovers fixtures through the conftest namespace.
"""

from __future__ import annotations

import os
from pathlib import Path

from fixture.auth import auth, token_manager  # noqa: F401 (pytest fixture re-export)
from fixture.clients import (  # noqa: F401 (pytest fixture re-export)
    api_client,
    db_client,
    http_client,
    mock_transport,
)

# Point the framework config center at this project's config dir (rule 10).
# Must be set before any fixture calls get_settings().
os.environ.setdefault("APP_CONFIG_DIR", str(Path(__file__).parent / "config"))
os.environ.setdefault("APP_ENV", "dev")

# Enable the framework's pytest plugin (env init, trace context, failure artifacts).
pytest_plugins = ["framework.testing.hooks.fixtures"]
