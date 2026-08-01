"""Unit tests for framework.reporting.labels using a fake allure (rule 14)."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from typing import Any

import pytest

from framework.reporting import labels


class _FakeDynamic:
    """Records calls to allure.dynamic.*."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def label(self, name: str, value: str) -> None:
        self.calls.append(("label", (name, value)))

    def severity(self, level: str) -> None:
        self.calls.append(("severity", (level,)))

    def feature(self, name: str) -> None:
        self.calls.append(("feature", (name,)))

    def story(self, name: str) -> None:
        self.calls.append(("story", (name,)))

    def tag(self, name: str) -> None:
        self.calls.append(("tag", (name,)))

    def epic(self, name: str) -> None:
        self.calls.append(("epic", (name,)))

    def suite(self, name: str) -> None:
        self.calls.append(("suite", (name,)))

    def link(self, url: str, name: str | None = None, link_type: str = "link") -> None:
        self.calls.append(("link", (url, name, link_type)))

    def issue(self, url: str, name: str | None = None) -> None:
        self.calls.append(("issue", (url, name)))

    def test_case(self, url: str, name: str | None = None) -> None:
        self.calls.append(("test_case", (url, name)))

    def description(self, text: str) -> None:
        self.calls.append(("description", (text,)))


class _FakeAllure:
    """Fake allure module with .dynamic attribute."""

    def __init__(self) -> None:
        self.dynamic = _FakeDynamic()


@pytest.fixture
def fake_allure() -> Iterator[_FakeAllure]:
    """Inject a fake allure module into sys.modules."""
    fake = _FakeAllure()
    original = sys.modules.get("allure")
    sys.modules["allure"] = fake
    labels._try_import_allure.cache_clear() if hasattr(
        labels._try_import_allure, "cache_clear"
    ) else None
    yield fake
    if original is not None:
        sys.modules["allure"] = original
    else:
        sys.modules.pop("allure", None)


# ---------------------------------------------------------------------------
# No-op without allure
# ---------------------------------------------------------------------------


def test_all_noop_without_allure() -> None:
    """All label helpers are no-ops when allure is not installed."""
    original = sys.modules.pop("allure", None)
    try:
        labels.severity("critical")
        labels.feature("Auth")
        labels.story("Login")
        labels.owner("dev")
        labels.tag("smoke")
        labels.epic("Epic1")
        labels.suite("Suite1")
        labels.label("custom", "value")
        labels.link("http://x", name="L", link_type="link")
        labels.issue("JIRA-1")
        labels.test_case("TC-1")
        labels.description("desc")
    finally:
        if original is not None:
            sys.modules["allure"] = original


# ---------------------------------------------------------------------------
# With fake allure
# ---------------------------------------------------------------------------


def test_severity(fake_allure: _FakeAllure) -> None:
    labels.severity("critical")
    assert fake_allure.dynamic.calls == [("severity", ("critical",))]


def test_feature(fake_allure: _FakeAllure) -> None:
    labels.feature("Authentication")
    assert fake_allure.dynamic.calls == [("feature", ("Authentication",))]


def test_story(fake_allure: _FakeAllure) -> None:
    labels.story("User login")
    assert fake_allure.dynamic.calls == [("story", ("User login",))]


def test_owner(fake_allure: _FakeAllure) -> None:
    labels.owner("dev-team")
    assert fake_allure.dynamic.calls == [("label", ("owner", "dev-team"))]


def test_tag(fake_allure: _FakeAllure) -> None:
    labels.tag("smoke")
    assert fake_allure.dynamic.calls == [("tag", ("smoke",))]


def test_epic(fake_allure: _FakeAllure) -> None:
    labels.epic("Platform")
    assert fake_allure.dynamic.calls == [("epic", ("Platform",))]


def test_suite(fake_allure: _FakeAllure) -> None:
    labels.suite("Auth Suite")
    assert fake_allure.dynamic.calls == [("suite", ("Auth Suite",))]


def test_label(fake_allure: _FakeAllure) -> None:
    labels.label("module", "billing")
    assert fake_allure.dynamic.calls == [("label", ("module", "billing"))]


def test_link(fake_allure: _FakeAllure) -> None:
    labels.link("http://jira/x", name="JIRA-X", link_type="issue")
    assert fake_allure.dynamic.calls == [
        ("link", ("http://jira/x", "JIRA-X", "issue")),
    ]


def test_issue(fake_allure: _FakeAllure) -> None:
    labels.issue("JIRA-123", name="Bug 123")
    assert fake_allure.dynamic.calls == [("issue", ("JIRA-123", "Bug 123"))]


def test_test_case(fake_allure: _FakeAllure) -> None:
    labels.test_case("TC-456")
    assert fake_allure.dynamic.calls == [("test_case", ("TC-456", None))]


def test_description(fake_allure: _FakeAllure) -> None:
    labels.description("This tests login")
    assert fake_allure.dynamic.calls == [("description", ("This tests login",))]


def test_all_exported() -> None:
    """All functions in __all__ are callable."""
    for name in labels.__all__:
        assert callable(getattr(labels, name)), f"{name} not callable"
