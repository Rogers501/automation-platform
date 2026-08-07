"""YAML-driven load-test scenario models.

A scenario is a named sequence of HTTP steps with think-time between them.
Scenarios are loaded from YAML (``load_scenarios``) and fed to a Locust
``HttpUser`` in the loadtest project. The models are plain pydantic --
no Locust import here (rule 11).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from framework.core.exceptions import FrameworkError

__all__ = ["LoadScenario", "LoadStep", "ScenarioError", "load_scenarios"]


class ScenarioError(FrameworkError):
    """Raised when a scenario file is missing or malformed."""


class LoadStep(BaseModel):
    """A single HTTP request within a load-test scenario.

    Attributes:
        name: Human-readable label (shown in Locust / Allure).
        method: HTTP verb (GET, POST, ...).
        url: Request path (relative to base_url) or absolute URL.
        params: Query parameters.
        headers: Per-step headers (merged over scenario defaults).
        json: JSON body (serializable object).
        data: Form-encoded body.
        expected_status: Expected HTTP status (for assertion).
        think_time: Pause (seconds) after this step before the next.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str = ""
    method: str = "GET"
    url: str
    params: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    json_body: Any | None = Field(default=None, alias="json")
    data: dict[str, Any] | None = None
    expected_status: int | None = None
    think_time: float = 0.0


class LoadScenario(BaseModel):
    """A named, weighted load-test scenario (sequence of steps).

    Attributes:
        name: Scenario identifier (used as Locust task name).
        description: Human-readable summary.
        weight: Relative frequency (Locust picks scenarios proportional
            to weight; default 1).
        base_url: Override the environment base_url for this scenario.
        headers: Default headers applied to every step in this scenario.
        think_time: Default think-time between steps (seconds).
        steps: Ordered list of HTTP requests.
    """

    model_config = ConfigDict(extra="ignore")

    name: str
    description: str = ""
    weight: int = 1
    base_url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    think_time: float = 1.0
    steps: list[LoadStep]


def load_scenarios(path: str | Path) -> list[LoadScenario]:
    """Load load-test scenarios from a YAML file.

    The file may be a top-level list of scenario mappings, or a mapping
    with a ``scenarios`` key holding the list.

    Args:
        path: Path to the YAML scenario file.

    Returns:
        A list of :class:`LoadScenario` objects.

    Raises:
        ScenarioError: If the file cannot be read or is malformed.
    """
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ScenarioError(
            f"failed to load scenarios from {p}", context={"path": str(p)}
        ) from exc

    items = raw.get("scenarios", raw) if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise ScenarioError(
            f"scenarios in {p} must be a list", context={"path": str(p)}
        )
    return [LoadScenario.model_validate(item) for item in items]
