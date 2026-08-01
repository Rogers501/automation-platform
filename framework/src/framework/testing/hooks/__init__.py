"""Test hooks: pytest fixtures for env init, trace context, and failure artifacts.

This package exposes the screenshot interface, artifact persistence, and the
pytest plugin module (:mod:`framework.testing.hooks.fixtures`) that wires them
into the test lifecycle.
"""

from framework.testing.hooks.artifacts import sanitize_node_id, save_failure_artifacts
from framework.testing.hooks.screenshot import NullScreenshotProvider, ScreenshotProvider

__all__ = [
    "NullScreenshotProvider",
    "ScreenshotProvider",
    "sanitize_node_id",
    "save_failure_artifacts",
]
