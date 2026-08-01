"""Allure environment and categories files for enterprise reports.

Writes ``environment.properties`` and ``categories.json`` to the Allure
results directory so the generated HTML report shows environment info
(server URL, DB version, etc.) and failure classification (product defects,
test defects, flaky tests).

These are standalone file-writing functions: they take the results directory
explicitly and do not depend on pytest configuration, so they are easy to
unit-test (rule 14) and can be called from a session-scoped fixture or a
``pytest_sessionfinish`` hook.

Usage::

    from framework.reporting.environment import (
        write_environment,
        write_categories,
        default_categories,
    )

    # In conftest.py:
    def pytest_sessionfinish(session, exitstatus):
        results_dir = Path(os.environ.get("ALLURE_RESULTS_DIR", "allure-results"))
        write_environment(results_dir, {"base_url": "https://api.example.com",
                                        "env": "test"})
        write_categories(results_dir)
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

__all__ = [
    "default_categories",
    "write_categories",
    "write_environment",
]


def write_environment(results_dir: Path, env: Mapping[str, str]) -> Path:
    """Write ``environment.properties`` to the Allure results directory.

    Args:
        results_dir: The ``--alluredir`` directory.
        env: Key-value pairs (e.g. ``{"base_url": "...", "env": "test"}``).

    Returns:
        The path to the written ``environment.properties`` file.
    """
    results_dir.mkdir(parents=True, exist_ok=True)
    target = results_dir / "environment.properties"
    lines = [f"{k}={v}" for k, v in env.items()]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def default_categories() -> list[dict[str, Any]]:
    """Return sensible default Allure failure categories.

    Categories:
        - Product defects: failed tests (assertion failures).
        - Test defects: broken tests (errors in test code / infrastructure).
        - Flaky tests: passed with retries.
    """
    return [
        {
            "name": "Product defects",
            "matchedStatuses": ["failed"],
            "flaky": False,
        },
        {
            "name": "Test defects",
            "matchedStatuses": ["broken"],
            "flaky": False,
        },
        {
            "name": "Flaky tests",
            "matchedStatuses": ["failed", "broken"],
            "flaky": True,
        },
    ]


def write_categories(
    results_dir: Path,
    categories: Sequence[Mapping[str, Any]] | None = None,
) -> Path:
    """Write ``categories.json`` to the Allure results directory.

    Args:
        results_dir: The ``--alluredir`` directory.
        categories: Category definitions; defaults to
            :func:`default_categories`.

    Returns:
        The path to the written ``categories.json`` file.
    """
    cats = list(categories) if categories is not None else default_categories()
    results_dir.mkdir(parents=True, exist_ok=True)
    target = results_dir / "categories.json"
    target.write_text(
        json.dumps(cats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target
