"""YAML data-driven test case loading.

Loads test cases from YAML files for ``pytest.mark.parametrize``-driven tests.
A case file is either a top-level list of mappings or a mapping with a
``cases`` key holding the list. Each case is a ``dict``; a ``name`` (or ``id``)
field is used to generate readable test ids.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from framework.core.exceptions import FrameworkError

__all__ = ["CaseError", "case_ids", "load_cases"]


class CaseError(FrameworkError):
    """Raised when a data-driven case file is missing or malformed."""


def load_cases(path: str | Path) -> list[dict[str, Any]]:
    """Load test cases from a YAML file.

    The file may be a top-level list of case mappings, or a mapping with a
    ``cases`` key holding the list.

    Args:
        path: Path to the YAML case file.

    Returns:
        A list of case dictionaries.

    Raises:
        CaseError: If the file cannot be read or is not a list of mappings.
    """
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CaseError(f"failed to load cases from {p}", context={"path": str(p)}) from exc

    cases = raw["cases"] if isinstance(raw, dict) and "cases" in raw else raw

    if not isinstance(cases, list) or not all(isinstance(c, dict) for c in cases):
        raise CaseError(
            f"cases in {p} must be a list of mappings",
            context={"path": str(p)},
        )
    return cases


def case_ids(cases: list[dict[str, Any]]) -> list[str]:
    """Generate pytest parametrize ids from a case list.

    Uses each case's ``name`` (or ``id``) when present, falling back to the
    zero-based index.

    Args:
        cases: The list returned by :func:`load_cases`.

    Returns:
        A list of id strings suitable for ``pytest.mark.parametrize(ids=...)``.
    """
    return [str(case.get("name") or case.get("id") or i) for i, case in enumerate(cases)]
