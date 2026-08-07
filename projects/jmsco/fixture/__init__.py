"""jmsco 项目级 pytest fixtures."""

from fixture.web_client import (  # noqa: F401 (pytest fixture re-export)
    base_url,
    screenshot_provider,
    web_client,
)
