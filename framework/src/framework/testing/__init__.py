"""Test infrastructure: fixtures, data-driven, dependency, extractors, assertions.

The :mod:`framework.testing.hooks` package provides the pytest plugin (env init,
trace context, failure artifacts) and the screenshot provider interface.
"""

from framework.testing.hooks import (
    NullScreenshotProvider,
    ScreenshotProvider,
    sanitize_node_id,
    save_failure_artifacts,
)

__all__ = [
    "NullScreenshotProvider",
    "ScreenshotProvider",
    "sanitize_node_id",
    "save_failure_artifacts",
]
