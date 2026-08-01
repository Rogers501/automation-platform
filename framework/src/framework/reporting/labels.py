"""Allure dynamic labels and links (no-op without allure).

Enterprise reports require severity, feature, story, owner, epic, and suite
labels, plus links to issues and test cases. These helpers wrap
``allure.dynamic.*`` and gracefully no-op when ``allure`` is not installed,
so test code can use them unconditionally without conditional imports.

Layering: depends only on the optional ``allure`` package (lazy import).
Never depends on ``clients`` or ``testing`` (rule 11).

Usage::

    from framework.reporting.labels import severity, feature, story, issue

    async def test_login(test_context):
        feature("Authentication")
        story("User login")
        severity("critical")
        issue("JIRA-123")
        # ... test body ...
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "description",
    "epic",
    "feature",
    "issue",
    "label",
    "link",
    "owner",
    "severity",
    "story",
    "suite",
    "tag",
    "test_case",
]


def _try_import_allure() -> Any:
    """Import and return the ``allure`` module, or ``None`` if unavailable."""
    try:
        import allure
    except ImportError:
        return None
    return allure


def label(name: str, value: str) -> None:
    """Add a custom dynamic label to the current test (no-op without allure).

    Args:
        name: Label name (e.g. ``"platform"``, ``"module"``).
        value: Label value.
    """
    allure = _try_import_allure()
    if allure is not None:
        allure.dynamic.label(name, value)


def severity(level: str) -> None:
    """Set the severity of the current test (no-op without allure).

    Args:
        level: One of ``"blocker"``, ``"critical"``, ``"normal"``,
            ``"minor"``, ``"trivial"``.
    """
    allure = _try_import_allure()
    if allure is not None:
        allure.dynamic.severity(level)


def feature(name: str) -> None:
    """Assign the current test to a feature (no-op without allure)."""
    allure = _try_import_allure()
    if allure is not None:
        allure.dynamic.feature(name)


def story(name: str) -> None:
    """Assign the current test to a story (no-op without allure)."""
    allure = _try_import_allure()
    if allure is not None:
        allure.dynamic.story(name)


def owner(name: str) -> None:
    """Set the owner of the current test (no-op without allure)."""
    allure = _try_import_allure()
    if allure is not None:
        allure.dynamic.label("owner", name)


def tag(name: str) -> None:
    """Add a tag to the current test (no-op without allure)."""
    allure = _try_import_allure()
    if allure is not None:
        allure.dynamic.tag(name)


def epic(name: str) -> None:
    """Set the epic of the current test (no-op without allure)."""
    allure = _try_import_allure()
    if allure is not None:
        allure.dynamic.epic(name)


def suite(name: str) -> None:
    """Set the suite of the current test (no-op without allure)."""
    allure = _try_import_allure()
    if allure is not None:
        allure.dynamic.suite(name)


def link(url: str, name: str | None = None, link_type: str = "link") -> None:
    """Add a generic link to the current test (no-op without allure).

    Args:
        url: The link URL.
        name: Optional display name.
        link_type: Link type (``"link"``, ``"issue"``, ``"test_case"``).
    """
    allure = _try_import_allure()
    if allure is not None:
        allure.dynamic.link(url, name=name, link_type=link_type)


def issue(url: str, name: str | None = None) -> None:
    """Add an issue link to the current test (no-op without allure).

    Args:
        url: Issue URL or identifier (e.g. ``"JIRA-123"`` or full URL).
        name: Optional display name.
    """
    allure = _try_import_allure()
    if allure is not None:
        allure.dynamic.issue(url, name=name)


def test_case(url: str, name: str | None = None) -> None:
    """Add a test-case link to the current test (no-op without allure).

    Args:
        url: Test-case URL or identifier.
        name: Optional display name.
    """
    allure = _try_import_allure()
    if allure is not None:
        allure.dynamic.test_case(url, name=name)


def description(text: str) -> None:
    """Set the description of the current test (no-op without allure).

    Args:
        text: The description text (supports Markdown).
    """
    allure = _try_import_allure()
    if allure is not None:
        allure.dynamic.description(text)
