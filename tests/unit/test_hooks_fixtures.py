"""Integration tests for the framework.testing.hooks fixtures (via pytester)."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

pytest_plugins = ["pytester"]


def test_test_context_persists_artifacts_on_failure(pytester: pytest.Pytester) -> None:
    """On test failure, recorded exchanges are saved to the artifact dir.

    The sub-suite overrides ``framework_env`` and ``artifact_dir`` to avoid
    real logging setup and env coupling; ``test_context`` (from the plugin)
    still wires the recorder + failure artifact persistence.
    """
    pytester.makeconftest(
        "pytest_plugins = ['framework.testing.hooks.fixtures']\n"
        "from pathlib import Path\n"
        "import pytest\n"
        "\n"
        "@pytest.fixture(scope='session')\n"
        "def framework_env():\n"
        "    return None\n"
        "\n"
        "@pytest.fixture(scope='session')\n"
        "def artifact_dir():\n"
        "    d = Path(__file__).parent / 'my_artifacts'\n"
        "    d.mkdir(parents=True, exist_ok=True)\n"
        "    return d\n"
    )
    pytester.makepyfile(
        test_sample=(
            "from framework.core.recorder import record_exchange, HttpExchange\n"
            "\n"
            "\n"
            "def test_fail(test_context):\n"
            "    record_exchange(HttpExchange(\n"
            "        method='GET', url='http://x', request_headers={},\n"
            "        request_body=None, status_code=200, response_headers={},\n"
            "        response_body=None, elapsed_seconds=0.1, trace_id='t1'))\n"
            "    assert False\n"
            "\n"
            "\n"
            "def test_pass(test_context):\n"
            "    assert True\n"
        )
    )
    result = pytester.runpytest("-p", "no:cacheprovider", "-p", "no:asyncio", "-q")
    result.assert_outcomes(failed=1, passed=1)

    artifacts = list((pytester.path / "my_artifacts").rglob("exchanges.json"))
    assert artifacts, "exchanges.json should be created on failure"
    data = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["trace_id"] == "t1"
    assert data[0]["method"] == "GET"


def test_test_context_skips_artifacts_on_pass(pytester: pytest.Pytester) -> None:
    """A passing test does not create any artifact."""
    pytester.makeconftest(
        "pytest_plugins = ['framework.testing.hooks.fixtures']\n"
        "from pathlib import Path\n"
        "import pytest\n"
        "\n"
        "@pytest.fixture(scope='session')\n"
        "def framework_env():\n"
        "    return None\n"
        "\n"
        "@pytest.fixture(scope='session')\n"
        "def artifact_dir():\n"
        "    d = Path(__file__).parent / 'my_artifacts'\n"
        "    d.mkdir(parents=True, exist_ok=True)\n"
        "    return d\n"
    )
    pytester.makepyfile(test_sample=("def test_pass(test_context):\n    assert True\n"))
    result = pytester.runpytest("-p", "no:cacheprovider", "-p", "no:asyncio", "-q")
    result.assert_outcomes(passed=1)
    assert not list((pytester.path / "my_artifacts").rglob("exchanges.json"))


class _AttachmentType:
    JSON = "application/json"
    TEXT = "text/plain"


class _RecordingAllure:
    """Fake allure for the in-process pytester sub-run; records attach calls."""

    attachment_type = _AttachmentType

    def __init__(self) -> None:
        self.attaches: list[dict[str, Any]] = []

    def attach(
        self,
        body: str,
        name: str | None = None,
        attachment_type: Any = None,
        **kw: Any,
    ) -> None:
        self.attaches.append({"body": body, "name": name})

    @contextmanager
    def step(self, title: str) -> Iterator[None]:
        yield


def test_test_context_attaches_exchanges_to_allure(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recorded exchanges are attached to Allure at teardown when allure present.

    A fake `allure` is injected via `sys.modules` (auto-cleaned by
    monkeypatch); the sub-run records one exchange and passes, so teardown
    auto-attaches it.
    """
    fake = _RecordingAllure()
    monkeypatch.setitem(sys.modules, "allure", fake)
    pytester.makeconftest(
        "pytest_plugins = ['framework.testing.hooks.fixtures']\n"
        "from pathlib import Path\n"
        "import pytest\n"
        "\n"
        "@pytest.fixture(scope='session')\n"
        "def framework_env():\n"
        "    return None\n"
        "\n"
        "@pytest.fixture(scope='session')\n"
        "def artifact_dir():\n"
        "    d = Path(__file__).parent / 'my_artifacts'\n"
        "    d.mkdir(parents=True, exist_ok=True)\n"
        "    return d\n"
    )
    pytester.makepyfile(
        test_sample=(
            "from framework.core.recorder import record_exchange, HttpExchange\n"
            "\n"
            "def test_ok(test_context):\n"
            "    record_exchange(HttpExchange(\n"
            "        method='GET', url='http://x/y', request_headers={},\n"
            "        request_body=None, status_code=200, response_headers={},\n"
            "        response_body=None, elapsed_seconds=0.1, trace_id='t1'))\n"
            "    assert True\n"
        )
    )
    result = pytester.runpytest("-p", "no:cacheprovider", "-p", "no:asyncio", "-q")
    result.assert_outcomes(passed=1)
    assert len(fake.attaches) == 1
    assert "http://x/y" in fake.attaches[0]["name"]
    assert "GET" in fake.attaches[0]["name"]
